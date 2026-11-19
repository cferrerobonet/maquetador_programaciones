"""Lógica sin interfaz: qué archivos se añaden, adónde se escribe cada copia y cómo se pagina."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

SUFIJO = " (maquetada)"


def es_docx_valido(ruta: Path) -> bool:
    """Un .docx de verdad: sin los temporales de Word (`~$`) ni los ocultos (`.`)."""
    n = ruta.name
    return ruta.suffix.lower() == ".docx" and not n.startswith(("~$", "."))


def expandir_rutas(rutas: Iterable[Path]) -> list[Path]:
    """Archivos sueltos y carpetas (con sus subcarpetas) a una lista de .docx sin repetidos."""
    vistos: set[Path] = set()
    salida: list[Path] = []

    def añadir(p: Path) -> None:
        clave = p.resolve()
        if clave not in vistos:
            vistos.add(clave)
            salida.append(p)

    for ruta in rutas:
        ruta = Path(ruta)
        if ruta.is_dir():
            for p in sorted(ruta.rglob("*")):
                if any(parte.startswith(".") for parte in p.relative_to(ruta).parts):
                    continue
                if p.is_file() and es_docx_valido(p):
                    añadir(p)
        elif ruta.is_file() and es_docx_valido(ruta):
            añadir(ruta)
    return salida


def ruta_salida(entrada: Path, carpeta: Path | None = None) -> Path:
    """`<nombre> (maquetada).docx` junto al original o en `carpeta`; nunca pisa: « (2)», « (3)»…"""
    base = carpeta if carpeta is not None else entrada.parent
    candidato = base / f"{entrada.stem}{SUFIJO}.docx"
    n = 2
    while candidato.exists():
        candidato = base / f"{entrada.stem}{SUFIJO} ({n}).docx"
        n += 1
    return candidato


def paginas_visibles(actual: int, total: int, cuantas: int = 5) -> list[int]:
    """Números de página (1..total) que se muestran en el pie: hasta `cuantas`, con la actual dentro."""
    if total <= 0:
        return [1]
    cuantas = min(cuantas, total)
    inicio = max(1, min(actual - cuantas // 2, total - cuantas + 1))
    return list(range(inicio, inicio + cuantas))


def total_paginas(filas: int, por_pagina: int) -> int:
    return max(1, -(-filas // por_pagina))
