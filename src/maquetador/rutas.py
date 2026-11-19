"""Dónde vive cada cosa: los ajustes de este equipo y los recursos de la aplicación."""

import os
import sys
from pathlib import Path

CARPETA = "MaquetadorProgramaciones"


def carpeta_datos() -> Path:
    """Carpeta de datos del usuario. `MAQUETADOR_DATOS` la cambia (pruebas)."""
    propia = os.environ.get("MAQUETADOR_DATOS")
    if propia:
        base = Path(propia)
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / CARPETA
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home()) / CARPETA
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / CARPETA
    base.mkdir(parents=True, exist_ok=True)
    return base


def recursos() -> Path:
    """Tipografías e icono, dentro del paquete o de la app congelada."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "maquetador" / "recursos"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / "recursos"


def changelog() -> Path:
    """`CHANGELOG.md`: en la raíz del repositorio o, en la app congelada, junto a los recursos."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "CHANGELOG.md"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2] / "CHANGELOG.md"
