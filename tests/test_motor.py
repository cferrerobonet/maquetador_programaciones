"""Pruebas del motor con documentos ficticios generados al vuelo (nunca programaciones reales)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from docx import Document
from docx.enum.section import WD_SECTION
from docx.shared import Cm, Pt
from lxml import etree

from maquetador.motor import Referencia, comprobar, maquetar
from maquetador.paquete import NS

APARTADOS = [
    (1, "1.- Datos identificativos y contextualización"),
    (2, "1.1.- Normativa básica estatal"),
    (1, "2.- Metodología del proceso de enseñanza"),
    (1, "3.- Evaluación del aprendizaje"),
    (2, "3.1.- Instrumentos de evaluación"),
]


def _programacion(ruta: Path, *, fuente: str, tam: int, margen: float, cabecera: str, datos: dict[str, str],
                  etiqueta_prof: str = "Profesor:") -> Path:
    doc = Document()
    estilo = doc.styles["Normal"]
    estilo.font.name = fuente
    estilo.font.size = Pt(tam)
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(margen)
    sec.header.paragraphs[0].text = cabecera
    doc.add_paragraph("PROGRAMACIÓN DIDÁCTICA")
    tabla = doc.add_table(rows=3, cols=2)
    for fila, (etq, clave) in enumerate((("Familia profesional:", "familia"), (etiqueta_prof, "profesor"),
                                         ("Curso académico:", "curso"))):
        tabla.cell(fila, 0).text = etq
        tabla.cell(fila, 1).text = datos[clave]
    nueva = doc.add_section(WD_SECTION.NEW_PAGE)
    nueva.left_margin = nueva.right_margin = Cm(margen)
    for nivel, titulo in APARTADOS:
        doc.add_heading(titulo, level=nivel)
        doc.add_paragraph(f"Texto de ejemplo del apartado «{titulo[5:]}», con datos ficticios.")
        doc.add_paragraph("Elemento de lista de ejemplo", style="List Bullet")
    t = doc.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "Columna A", "Columna B"
    for c in t.rows[0].cells:
        c.paragraphs[0].runs[0].bold = True
    t.cell(1, 0).text, t.cell(1, 1).text = "Valor 1", "Valor 2"
    doc.save(ruta)
    return ruta


@pytest.fixture
def docs(tmp_path):
    ref = _programacion(tmp_path / "referencia.docx", fuente="Calibri", tam=10, margen=2.0, cabecera="Escuela Ficticia",
                        datos={"familia": "Electricidad", "profesor": "Ana Ejemplo", "curso": "2026-2027"})
    otra = _programacion(tmp_path / "otra.docx", fuente="Times New Roman", tam=12, margen=3.0, cabecera="Cabecera antigua",
                         datos={"familia": "Electrónica", "profesor": "Luis Ficticio", "curso": "2025-2026"},
                         etiqueta_prof="Profesora:")
    return ref, otra, tmp_path


def _textos(ruta: Path) -> list[str]:
    doc = etree.fromstring(zipfile.ZipFile(ruta).read("word/document.xml"))
    return ["".join(t.text or "" for t in p.iter(f"{{{NS['w']}}}t")) for p in doc.iter(f"{{{NS['w']}}}p")]


def test_la_referencia_cumple_consigo_misma(docs):
    ref, _, _ = docs
    r = Referencia.cargar(ref)
    assert "5 títulos" in r.resumen
    d = comprobar(r, ref)
    assert d.es_programacion and d.cumple, d.motivos


def test_detecta_lo_que_no_cumple(docs):
    ref, otra, _ = docs
    d = comprobar(Referencia.cargar(ref), otra)
    assert d.es_programacion and not d.cumple
    assert any("márgenes" in m for m in d.motivos)
    assert any("Cabecera" in m for m in d.motivos)


def test_maquetar_no_cambia_el_contenido(docs):
    ref, otra, tmp = docs
    salida = tmp / "salida.docx"
    res = maquetar(Referencia.cargar(ref), otra, salida)
    assert res.ok, res.error
    antes = [t for t in _textos(otra) if t]
    despues = [t for t in _textos(salida) if t]
    assert sorted(antes) == sorted(despues)
    # Los datos de la portada son los del documento, nunca los de la referencia.
    assert "Luis Ficticio" in despues and "2025-2026" in despues and "Profesora:" in despues
    assert "Ana Ejemplo" not in despues and "2026-2027" not in despues


def test_maquetar_aplica_la_maquetacion(docs):
    ref, otra, tmp = docs
    salida = tmp / "salida.docx"
    r = Referencia.cargar(ref)
    assert maquetar(r, otra, salida).ok
    resultado = Document(salida)
    assert abs(resultado.sections[-1].left_margin - Cm(2.0)) < Cm(0.01)
    assert resultado.styles["Normal"].font.name == "Calibri"
    assert "Escuela Ficticia" in resultado.sections[-1].header.paragraphs[0].text
    assert comprobar(r, salida).cumple


def test_no_es_una_programacion(docs):
    ref, _, tmp = docs
    ruta = tmp / "carta.docx"
    d = Document()
    d.add_heading("Carta de presentación", level=1)
    d.add_paragraph("Texto sin apartados de programación.")
    d.save(ruta)
    diag = comprobar(Referencia.cargar(ref), ruta)
    assert not diag.es_programacion


def test_nunca_sobrescribe_la_entrada_si_falla(docs, monkeypatch):
    ref, otra, tmp = docs
    import maquetador.motor as motor

    original = motor._huella_contenido
    llamadas = []

    def saboteada(doc, estilos, conocidas=None):
        lineas, d, t = original(doc, estilos, conocidas)
        llamadas.append(1)
        return (lineas + ["cambio"] if len(llamadas) == 2 else lineas), d, t

    monkeypatch.setattr(motor, "_huella_contenido", saboteada)
    salida = tmp / "salida.docx"
    res = maquetar(Referencia.cargar(ref), otra, salida)
    assert not res.ok and "seguridad" in res.error
    assert not salida.exists()
