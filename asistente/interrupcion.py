"""Detector de interrupciones (fase 6): "Oye Numa" MIENTRAS Numa habla.

Es distinto del detector de activación (activacion.py), que trabaja en REPOSO
cortando frases por silencios: mientras Piper habla NUNCA hay silencio en el
micrófono. Aquí, cada 0,75 s se mira la ventana de los últimos 2 s:

  1. Puerta de volumen: Piper llega al micro muy débil (pico medido ~0,003)
     y tu voz muy fuerte (~0,12). Por debajo del umbral, ni se transcribe:
     con audio débil, la pista "Oye Numa" hace que Whisper la alucine.
  2. Si pasa, se transcribe y se busca "numa".
  3. Si está: este hilo llama a voz.parar() (pensado para llamarse desde
     otro hilo, ver ADR 0002) y publica lo que viene después:
        "Oye Numa"              → Activar()     (pita y escucha)
        "Oye Numa, ¿qué hora?"  → Activar()     (la ventana puede cortar la
                                                 orden: "qué"; mejor repetirla)
        "Oye Numa, para"        → nada          (solo callar)
  4. Periodo refractario: tras cortar, se ignoran VENTANA_S segundos. Si no,
     las ventanas solapadas volverían a oír el final de tu frase e
     interrumpirían la respuesta siguiente.

Solo escucha cuando el hilo principal le da paso (`hablando`). Ver ADR 0007.
El umbral depende del hardware: recalibrar con experimentos/probar_interrupcion.py.
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Callable, Iterable

import numpy as np

from asistente.activacion import FRASE_ACTIVACION, evento_para
from asistente.eventos import Activar, Evento, Frase
from asistente.oido import FRECUENCIA
from asistente.router import normalizar

log = logging.getLogger(__name__)

VENTANA_S = 2.0       # audio que se transcribe cada vez ("Oye Numa" dura ~0,6 s)
PASO_S = 0.75         # cada cuánto se mira (solape de 1,25 s: nunca cae partido)
UMBRAL_RMS = 0.005    # medido en este portátil: Piper ≤ 0,003, mi voz ~0,12
ORDENES_CALLAR = {"para", "parate", "calla", "callate", "silencio", "basta", "stop"}


# --- Funciones puras -------------------------------------------------------

def nivel(ventana: np.ndarray, trozos: int = 20) -> float:
    """Volumen (RMS) del tramo más fuerte de la ventana.

    El pico de ~100 ms, no la media: un "Oye Numa" corto rodeado del murmullo
    de Piper se diluiría en la media de 2 s.
    """
    if len(ventana) == 0:
        return 0.0
    return max(float(np.sqrt(np.mean(t ** 2))) for t in np.array_split(ventana, trozos) if len(t))


def es_orden_de_callar(texto: str) -> bool:
    """"para", "cállate ya", "silencio": callar. "para qué sirve…": no.

    Solo frases de 1-2 palabras: una orden de silencio es corta, y así
    "para cuándo es el examen" no se confunde con "para".
    """
    palabras = normalizar(texto).split()
    return 1 <= len(palabras) <= 2 and palabras[0] in ORDENES_CALLAR


def decidir(texto: str | None) -> tuple[bool, Evento | None]:
    """(¿hay que cortar?, evento a publicar después).

    (False, None)       no han dicho "numa": seguir hablando.
    (True, None)        "Oye Numa, para": cortar y nada más.
    (True, Activar())   cualquier otra cosa: cortar, pitar y escuchar. No se
                        usa la orden: la ventana puede haberla cortado a medias.
    """
    evento = evento_para(texto)
    if evento is None:
        return False, None
    if isinstance(evento, Frase) and es_orden_de_callar(evento.texto):
        return True, None
    return True, Activar()


class Ventanas:
    """Acumula bloques de audio y, cada `paso_s`, entrega los últimos `ventana_s`.

    Con `reiniciar()` olvida lo acumulado: tras una interrupción, la siguiente
    ventana (que se solapa con la anterior) volvería a contener "Oye Numa".
    """

    def __init__(self, ventana_s: float = VENTANA_S, paso_s: float = PASO_S) -> None:
        self._tam = int(ventana_s * FRECUENCIA)
        self._paso = int(paso_s * FRECUENCIA)
        self.reiniciar()

    def reiniciar(self) -> None:
        self._audio = np.zeros(0, np.float32)
        self._desde_ultima = 0

    def añadir(self, bloque: np.ndarray) -> np.ndarray | None:
        self._audio = np.concatenate([self._audio, bloque])[-self._tam:]
        self._desde_ultima += len(bloque)
        if self._desde_ultima < self._paso:
            return None
        # Restar, no poner a 0: si no, lo que sobra de cada bloque se pierde y
        # "cada 0,75 s" se convierte en "cada 0,8 s" (deriva acumulada).
        self._desde_ultima -= self._paso
        return self._audio


# --- El productor ----------------------------------------------------------

def producir_interrupciones(cola: queue.Queue[Evento], bloques: Iterable[np.ndarray],
                            transcribir: Callable[[np.ndarray], str | None],
                            hablando: threading.Event, parar: Callable[[], None],
                            umbral: float = UMBRAL_RMS) -> None:
    """Bucle del detector. Sin hilos ni micro: se testea con bloques falsos."""
    ventanas = Ventanas()
    refractario = 0  # muestras que quedan por ignorar tras una interrupción
    try:
        for bloque in bloques:
            if refractario > 0:
                refractario -= len(bloque)
                ventanas.reiniciar()
                continue
            if not hablando.is_set():
                ventanas.reiniciar()  # no juntar audio de antes y después de hablar
                continue
            ventana = ventanas.añadir(bloque)
            if ventana is None or nivel(ventana) < umbral:
                continue
            cortar, evento = decidir(transcribir(ventana))
            if cortar and hablando.is_set():  # check-then-act: ¿sigue hablando?
                log.debug("Interrupción: %r", evento)
                parar()
                ventanas.reiniciar()
                refractario = int(VENTANA_S * FRECUENCIA)
                if evento is not None:
                    cola.put(evento)
    except Exception:
        # Sin este detector el asistente sigue funcionando: solo no se le
        # puede interrumpir. No se publica Salir().
        log.exception("El detector de interrupciones ha fallado")


def iniciar_interrupciones(cola: queue.Queue[Evento],
                           transcribir: Callable[[np.ndarray, str | None], str | None],
                           hablando: threading.Event,
                           parar: Callable[[], None]) -> threading.Thread:
    from asistente.activacion import _bloques_del_micro

    hilo = threading.Thread(
        target=producir_interrupciones,
        args=(cola, _bloques_del_micro(), lambda audio: transcribir(audio, FRASE_ACTIVACION),
              hablando, parar),
        name="interrupcion", daemon=True,
    )
    hilo.start()
    return hilo
