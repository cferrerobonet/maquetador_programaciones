"""Filas del listado: una programación añadida, su estado y su modelo de tabla."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QBrush, QColor

from .ui.estilo import T

PENDIENTE = "Pendiente de comprobar"
CUMPLE = "Cumple"
NO_CUMPLE = "No cumple"
NO_PROGRAMACION = "No es una programación"
MAQUETADA = "Maquetada"
ERROR = "Error"
ESTADOS = (PENDIENTE, CUMPLE, NO_CUMPLE, NO_PROGRAMACION, MAQUETADA, ERROR)

COLUMNAS = ("Archivo", "Carpeta", "Estado", "Motivos")
RESALTE_SEGUNDOS = 4.0


@dataclass(eq=False)
class Item:
    ruta: Path
    estado: str = PENDIENTE
    motivos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    error: str | None = None
    salida: Path | None = None
    resaltado_hasta: float = 0.0

    @property
    def archivo(self) -> str:
        return self.ruta.name

    @property
    def carpeta(self) -> str:
        return self.ruta.parent.name or str(self.ruta.parent)

    def resaltar(self) -> None:
        self.resaltado_hasta = time.monotonic() + RESALTE_SEGUNDOS

    @property
    def resaltado(self) -> bool:
        return time.monotonic() < self.resaltado_hasta

    @property
    def resumen(self) -> str:
        if self.estado == ERROR:
            return self.error or ""
        if self.estado == MAQUETADA:
            extra = f" · {len(self.avisos)} aviso(s)" if self.avisos else ""
            return f"Guardada como {self.salida.name}{extra}" if self.salida else "Maquetada"
        return "; ".join(self.motivos)

    def detalle(self) -> str:
        partes = [f"{self.archivo}\n{self.ruta.parent}", f"Estado: {self.estado}"]
        if self.estado == ERROR and self.error:
            partes.append(f"Motivo del error: {self.error}")
        if self.motivos:
            partes.append("Motivos:\n" + "\n".join(f"· {m}" for m in self.motivos))
        if self.salida:
            partes.append(f"Archivo maquetado:\n{self.salida}")
        if self.avisos:
            partes.append("Avisos:\n" + "\n".join(f"· {a}" for a in self.avisos))
        return "\n\n".join(partes)

    def clave_orden(self, columna: int):
        if columna == 0:
            return (self.archivo.lower(), str(self.ruta).lower())
        if columna == 1:
            return (self.carpeta.lower(), self.archivo.lower())
        if columna == 2:
            return (ESTADOS.index(self.estado), self.archivo.lower())
        return (self.resumen.lower(), self.archivo.lower())


class ModeloLista(QAbstractTableModel):
    """Muestra solo la página actual; la ventana decide qué filas entran."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.filas: list[Item] = []

    def poner(self, filas: list[Item]) -> None:
        self.beginResetModel()
        self.filas = list(filas)
        self.endResetModel()

    def refrescar(self) -> None:
        if self.filas:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.filas) - 1, len(COLUMNAS) - 1))

    def rowCount(self, parent=QModelIndex()):  # noqa: N802, B008
        return 0 if parent.isValid() else len(self.filas)

    def columnCount(self, parent=QModelIndex()):  # noqa: N802, B008
        return 0 if parent.isValid() else len(COLUMNAS)

    def headerData(self, seccion, orientacion, rol=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientacion == Qt.Orientation.Horizontal and rol == Qt.ItemDataRole.DisplayRole:
            return COLUMNAS[seccion]
        return None

    def data(self, idx, rol=Qt.ItemDataRole.DisplayRole):
        if not idx.isValid():
            return None
        it = self.filas[idx.row()]
        c = idx.column()
        if rol == Qt.ItemDataRole.DisplayRole:
            return (it.archivo, it.carpeta, it.estado, it.resumen.replace("\n", " "))[c]
        if rol == Qt.ItemDataRole.ToolTipRole:
            return it.detalle()
        if rol == Qt.ItemDataRole.BackgroundRole and it.resaltado:
            return QBrush(QColor(T["gold_soft"]))
        if rol == Qt.ItemDataRole.ForegroundRole and c == 2:
            color = {
                CUMPLE: T["accent"], MAQUETADA: T["accent"], NO_CUMPLE: T["warn"],
                ERROR: T["danger"], NO_PROGRAMACION: T["muted"], PENDIENTE: T["muted"],
            }[it.estado]
            return QBrush(QColor(color))
        return None
