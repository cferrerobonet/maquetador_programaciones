"""Ajustes recordados entre sesiones (QSettings en un .ini dentro de la carpeta de datos)."""

from PyQt6.QtCore import QSettings

from .rutas import carpeta_datos


def ajustes() -> QSettings:
    return QSettings(str(carpeta_datos() / "ajustes.ini"), QSettings.Format.IniFormat)
