"""Tareas del motor fuera del hilo de la ventana (cada llamada puede tardar un segundo)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal


class Senales(QObject):
    #: (clave de la tarea, resultado, error en texto o None)
    terminada = pyqtSignal(object, object, object)


class _Tarea(QRunnable):
    def __init__(self, clave: Any, funcion: Callable[[], Any], senales: Senales):
        super().__init__()
        self.clave = clave
        self.funcion = funcion
        self.senales = senales

    def run(self) -> None:
        resultado, error = None, None
        try:
            resultado = self.funcion()
        except Exception as e:  # noqa: BLE001 - el motor puede fallar de cualquier forma; se cuenta en la fila
            error = str(e) or e.__class__.__name__
        self.senales.terminada.emit(self.clave, resultado, error)


class Ejecutor:
    """Un solo hilo de trabajo: las tareas salen en el orden en que se encolan."""

    def __init__(self, senales: Senales):
        self.senales = senales
        self.pool = QThreadPool(senales)
        self.pool.setMaxThreadCount(1)

    def lanzar(self, clave: Any, funcion: Callable[[], Any]) -> None:
        self.pool.start(_Tarea(clave, funcion, self.senales))

    def esperar(self, ms: int = 5000) -> None:
        self.pool.waitForDone(ms)
