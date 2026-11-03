"""Salida de voz del asistente (fase 2).

El núcleo no debe saber que existe Piper: solo conoce el contrato `Voz`.
Así podremos tener:
  - VozTexto: imprime por pantalla (tests, y usar el asistente sin altavoz).
  - VozPiper: sintetiza con Piper y reproduce con sounddevice.
Y mañana cambiar Piper por otro TTS sin tocar __main__.py ni las skills.

Es el mismo patrón que `skills/base.py`: un contrato abstracto y varias
implementaciones intercambiables.

Decisiones (ver ADR 0002):
  - `decir()` BLOQUEA hasta que termina el audio: el bucle principal sigue
    siendo lineal y el estado HABLANDO dura exactamente lo que el audio.
  - `parar()` forma parte del contrato, pero es opcional (por defecto no
    hace nada). Se usará en la fase 6 para las interrupciones.
  - Cada implementación es segura entre hilos: si dos hilos llaman a
    `decir()` a la vez (respuesta + aviso del temporizador), el segundo
    espera a que termine el primero. Nunca se pisan.
"""
from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from pathlib import Path

log = logging.getLogger(__name__)


class Voz(ABC):
    def __init__(self) -> None:
        # Un solo hablante a la vez. Las subclases lo usan dentro de decir().
        self._lock = threading.Lock()

    @abstractmethod
    def decir(self, texto: str) -> None:
        """Dice `texto` y no vuelve hasta que ha terminado.

        Seguro entre hilos: las llamadas concurrentes se ejecutan una detrás
        de otra, nunca solapadas.
        """

    def parar(self) -> None:
        """Corta lo que se esté diciendo. Por defecto, nada.

        Se llama desde OTRO hilo (el que detecta la interrupción), así que
        no debe esperar al lock de decir(): si lo hiciera, esperaría a que
        terminara justo lo que quiere cortar.
        """


class VozTexto(Voz):
    """Imprime en vez de hablar. Para tests y para usar sin altavoz."""

    def decir(self, texto: str) -> None:
        with self._lock:
            print(texto)


class VozPiper(Voz):
    """Sintetiza con Piper (CPU) y reproduce con sounddevice."""

    def __init__(self, modelo: Path | str) -> None:
        super().__init__()
        # Importes aquí dentro: quien use VozTexto (tests incluidos) no
        # necesita tener Piper ni sounddevice instalados.
        import sounddevice
        from piper import PiperVoice

        self._sd = sounddevice
        # ~3 s: se paga una vez al arrancar, nunca dentro de decir().
        self._voz = PiperVoice.load(modelo)
        self._cortar = threading.Event()

    def decir(self, texto: str) -> None:
        import numpy as np

        with self._lock:
            print(texto)  # mientras desarrollamos: ver qué dice ayuda a oír fallos
            self._cortar.clear()
            # synthesize() da un trozo por frase: cada frase empieza a sonar
            # sin esperar a que estén sintetizadas las siguientes.
            for chunk in self._voz.synthesize(texto):
                if self._cortar.is_set():
                    break
                audio = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
                self._sd.play(audio, chunk.sample_rate)
                self._sd.wait()

    def parar(self) -> None:
        # Sin lock (ver Voz.parar): marca el corte y detiene el audio actual.
        self._cortar.set()
        self._sd.stop()
