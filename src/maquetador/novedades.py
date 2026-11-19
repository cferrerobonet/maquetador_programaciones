"""Novedades de cada versión, leídas de `CHANGELOG.md` (entradas `## [X.Y.Z] - AAAA-MM-DD`)."""

from __future__ import annotations

import re
from pathlib import Path

from .rutas import changelog


def novedades(version: str, ruta: Path | None = None) -> str:
    """Texto de la entrada de `version`; vacío si no existe o no se puede leer."""
    try:
        texto = (ruta or changelog()).read_text(encoding="utf-8")
    except OSError:
        return ""
    patron = rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)"
    m = re.search(patron, texto, re.M | re.S)
    return m.group(1).strip() if m else ""
