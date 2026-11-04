"""Productor de entrada: convierte lo que pasa en el teclado en eventos.

Corre en su propio hilo para que el bucle principal NUNCA se quede bloqueado
esperando al teclado: así puede atender un Aviso aunque no pulses nada.

    modo micrófono:  Enter            → Activar()
    modo teclado:    "que hora es"    → Frase("que hora es")
    ambos:           Ctrl+Z / Ctrl+D  → Salir()

En la fase 4, el hilo de la palabra de activación producirá también Activar().
"""
from __future__ import annotations

import logging
import queue
import sys
import threading
from typing import Callable

from asistente.eventos import Activar, Evento, Frase, Salir

log = logging.getLogger(__name__)


def leer_linea() -> str:
    """Como input(), pero sin tocar stdout.

    input() coge el lock de stdout (para escribir el prompt y vaciar el
    búfer). Si el programa termina mientras este hilo daemon está dentro de
    input(), Python no puede cerrar stdout y aborta con "Fatal Python error:
    could not acquire lock for stdout". sys.stdin.readline() solo lee.
    """
    linea = sys.stdin.readline()
    if not linea:  # readline() devuelve "" en el fin de la entrada
        raise EOFError
    return linea


def producir_entrada(cola: queue.Queue[Evento], con_texto: bool,
                     leer: Callable[[], str] = leer_linea) -> None:
    """Lee líneas hasta el fin de la entrada y publica un evento por cada una.

    Es un bucle normal (no lanza hilos): así se puede testear con un `leer` falso.
    No imprime ningún prompt: la consola es del hilo principal, que lo
    muestra cuando de verdad está listo para escuchar.
    """
    try:
        while True:
            linea = leer().strip()
            if not con_texto:
                cola.put(Activar())
            elif linea:
                cola.put(Frase(linea))
    except EOFError:
        pass  # Ctrl+Z / Ctrl+D: fin normal
    except Exception:
        # Una excepción en un hilo NO llega al hilo principal: lo registramos
        # aquí, o el hilo moriría en silencio.
        log.exception("El hilo de entrada ha fallado")
    finally:
        # Pase lo que pase, el bucle principal se entera de que no habrá más
        # entrada; si no, se quedaría esperando eventos para siempre.
        cola.put(Salir())


def iniciar_entrada(cola: queue.Queue[Evento], con_texto: bool,
                    leer: Callable[[], str] = leer_linea) -> threading.Thread:
    # daemon: un hilo bloqueado leyendo el teclado no se puede parar desde fuera.
    # Al ser daemon, no impide que el programa termine.
    hilo = threading.Thread(target=producir_entrada, args=(cola, con_texto, leer),
                            name="entrada", daemon=True)
    hilo.start()
    return hilo
