"""Memoria corta de la conversación (fase 6, ADR 0009).

Un LLM no recuerda nada entre llamadas: lo que parece memoria es reenviarle
los últimos turnos. Esta clase los guarda:

  - Los últimos `turnos` intercambios (tu frase + lo que Numa llegó a DECIR;
    si la interrumpiste, solo lo que sonó).
  - Caducan tras `caduca_s` segundos sin hablar: un tema viejo no contamina
    uno nuevo, y num_ctx=2048 no da para mucho.

La posee el hilo principal (único dueño del estado, ADR 0004): no necesita
Lock. En la fase 7 habría una por satélite. Las skills NO guardan
conversación (lección del `self._ultimo` del chiste, fase 1).
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Turno:
    usuario: str
    numa: str


class Conversacion:
    def __init__(self, turnos: int = 3, caduca_s: float = 120.0,
                 reloj: Callable[[], float] = time.monotonic) -> None:
        # deque con maxlen: al añadir el 4.º turno, el 1.º sale solo.
        self._turnos: deque[Turno] = deque(maxlen=turnos)
        self._caduca_s = caduca_s
        self._reloj = reloj  # inyectado: los tests "adelantan el tiempo"
        self._ultimo = 0.0

    def empezar_turno(self) -> int:
        """Llamar al empezar a atender cada frase. Olvida si ha caducado y
        devuelve cuántos turnos se van a usar como memoria."""
        self._olvidar_si_caducada()
        return len(self._turnos)

    def anotar(self, usuario: str, numa: str) -> None:
        # Aquí NO se comprueba la caducidad: se comprobó en empezar_turno().
        # Si se comprobara también aquí, un turno que empezó a los 115 s (y
        # usó la memoria) la borraría al acabar, a los 125 s, junto con el
        # contexto que acababa de usar.
        self._turnos.append(Turno(usuario.strip(), numa.strip()))
        self._ultimo = self._reloj()

    def turnos(self) -> list[Turno]:
        self._olvidar_si_caducada()
        return list(self._turnos)

    def mensajes(self) -> list[dict]:
        """Formato chat de Ollama: [{"role": "user"...}, {"role": "assistant"...}]."""
        mensajes = []
        for t in self.turnos():
            mensajes.append({"role": "user", "content": t.usuario})
            mensajes.append({"role": "assistant", "content": t.numa})
        return mensajes

    def resumen(self) -> str:
        """Texto plano, para meterlo como contexto dentro de un mensaje."""
        return "\n".join(f"Usuario: {t.usuario}\nNuma: {t.numa}" for t in self.turnos())

    def _olvidar_si_caducada(self) -> None:
        if self._turnos and self._reloj() - self._ultimo > self._caduca_s:
            self._turnos.clear()
