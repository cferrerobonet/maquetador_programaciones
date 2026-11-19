"""Aspecto común con Partes de salida: tipografías Barlow, colores claro/oscuro y hoja de estilos."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt6.QtCore import QDir, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QIcon, QPainter, QPalette, QPen, QPixmap

from ..rutas import recursos

CUERPO = "Barlow"
TITULAR = "Barlow Condensed"

CLARO = {
    "bg": "#f3f5f1", "surface": "#ffffff", "surface2": "#eef2ec", "line": "#d9e0d5",
    "fg": "#1d2a20", "muted": "#5d6b60", "accent": "#2c7a3a", "accent_ink": "#ffffff",
    "accent_soft": "#e2f0e3", "gold": "#b97a12", "gold_soft": "#fbf0d9",
    "warn": "#9a5b00", "warn_soft": "#fff3dc", "danger": "#a32d2d",
}
OSCURO = {
    "bg": "#121713", "surface": "#1a211c", "surface2": "#222b24", "line": "#323d35",
    "fg": "#e4ebe5", "muted": "#9aa89d", "accent": "#5fbf6e", "accent_ink": "#0d1a10",
    "accent_soft": "#1f3524", "gold": "#e3a94a", "gold_soft": "#3a2e17",
    "warn": "#f0b45a", "warn_soft": "#3a2c14", "danger": "#f08a8a",
}

T: dict[str, str] = dict(CLARO)


def cargar_fuentes() -> None:
    for f in sorted((recursos() / "fuentes").glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(f))


def es_oscuro() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        return False


def fuente(tam: float, peso: QFont.Weight = QFont.Weight.Normal, familia: str = CUERPO) -> QFont:
    f = QFont(familia)
    f.setPixelSize(round(tam))
    f.setWeight(peso)
    return f


def etiqueta_fuente(tam: float = 12) -> QFont:
    f = fuente(tam, QFont.Weight.Bold)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.9)
    f.setCapitalization(QFont.Capitalization.AllUppercase)
    return f


def hoja(t: dict[str, str]) -> str:
    return f"""
QMainWindow, QDialog, QWidget#raiz {{ background: {t['bg']}; }}
QFrame#separador {{ background: {t['line']}; }}
QLabel {{ background: transparent; }}
QLabel[rol="titulo"] {{ font-family: "{TITULAR}"; font-size: 26px; font-weight: 700; }}
QLabel[rol="subtitulo"] {{ color: {t['muted']}; font-size: 14px; }}
QLabel[rol="seccion"] {{ font-family: "{TITULAR}"; font-size: 19px; font-weight: 700; }}
QLabel[rol="muted"] {{ color: {t['muted']}; font-size: 13px; }}
QLabel[rol="pequeno"] {{ color: {t['muted']}; font-size: 12px; }}
QLabel[rol="etiqueta"] {{ color: {t['muted']}; }}
QLabel[rol="aviso"] {{ background: {t['warn_soft']}; color: {t['warn']}; font-size: 13px; padding: 7px 9px; border-radius: 7px; }}
QLabel[rol="error"] {{ background: {t['warn_soft']}; color: {t['danger']}; font-size: 13px; padding: 7px 9px; border-radius: 7px; }}
QLabel[rol="ok"] {{ color: {t['accent']}; font-size: 13px; font-weight: 600; }}
QFrame[rol="caja"] {{ background: {t['surface']}; border: 1px solid {t['line']}; border-radius: 12px; }}
QFrame[rol="soltar"] {{ border: 1.5px dashed {t['line']}; border-radius: 10px; background: {t['bg']}; }}
QFrame[rol="soltar"][encima="true"] {{ border-color: {t['accent']}; background: {t['accent_soft']}; }}
QLineEdit, QComboBox, QPlainTextEdit {{
  background: {t['bg']}; border: 1px solid {t['line']}; border-radius: 7px; padding: 6px 9px;
  selection-background-color: {t['accent']}; selection-color: {t['accent_ink']}; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 1px solid {t['accent']}; }}
QLineEdit#buscador {{ padding: 8px 10px; font-size: 14px; border-radius: 8px; }}
QComboBox QAbstractItemView {{ background: {t['surface']}; border: 1px solid {t['line']};
  selection-background-color: {t['accent_soft']}; selection-color: {t['fg']}; }}
QPushButton {{ background: {t['surface']}; border: 1px solid {t['line']}; border-radius: 8px;
  padding: 7px 13px; font-weight: 600; }}
QPushButton:hover {{ border-color: {t['accent']}; }}
QPushButton:pressed {{ background: {t['surface2']}; }}
QPushButton:disabled {{ color: {t['muted']}; }}
QPushButton[pequeno="true"] {{ font-size: 13px; padding: 4px 10px; border-radius: 7px; }}
QPushButton[peligro="true"] {{ color: {t['danger']}; }}
QPushButton[primario="true"] {{ background: {t['accent']}; border-color: {t['accent']}; color: {t['accent_ink']}; }}
QPushButton[primario="true"]:hover {{ border-color: {t['fg']}; }}
QPushButton[primario="true"]:disabled {{ background: {t['line']}; border-color: {t['line']}; color: {t['muted']}; }}
QPushButton[pagina="true"] {{ font-size: 13px; padding: 3px 0; min-width: 30px; border-radius: 7px; }}
QPushButton[pagina="true"]:checked {{ background: {t['accent']}; border-color: {t['accent']}; color: {t['accent_ink']}; }}
QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {t['line']}; border-radius: 4px; background: {t['surface']}; }}
QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; image: url(:/marca); }}
QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {t['line']}; border-radius: 8px; background: {t['surface']}; }}
QRadioButton::indicator:checked {{ background: {t['accent']}; border: 3px solid {t['surface']}; outline: 1px solid {t['accent']}; }}
QTableView {{ background: {t['surface']}; border: 1px solid {t['line']}; border-radius: 8px; outline: 0;
  gridline-color: {t['line']}; selection-background-color: {t['accent_soft']}; selection-color: {t['fg']}; }}
QTableView::item {{ padding: 4px 8px; border-bottom: 1px solid {t['line']}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {t['surface2']}; color: {t['muted']}; border: 0; border-bottom: 1px solid {t['line']};
  padding: 7px 8px; font-weight: 700; font-size: 12px; }}
QHeaderView::section:hover {{ color: {t['fg']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t['line']}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t['line']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollArea {{ background: transparent; border: 0; }}
QToolTip {{ background: {t['fg']}; color: {t['bg']}; border: 0; padding: 5px 8px; }}
QProgressBar {{ border: 1px solid {t['line']}; border-radius: 6px; background: {t['surface2']}; text-align: center; height: 14px; }}
QProgressBar::chunk {{ background: {t['accent']}; border-radius: 5px; }}
"""


def aplicar(app) -> None:
    T.clear()
    T.update(OSCURO if es_oscuro() else CLARO)
    app.setStyle("Fusion")
    pal = app.palette()
    for rol, clave in (
        (QPalette.ColorRole.Window, "bg"),
        (QPalette.ColorRole.Base, "surface"),
        (QPalette.ColorRole.AlternateBase, "surface2"),
        (QPalette.ColorRole.Text, "fg"),
        (QPalette.ColorRole.WindowText, "fg"),
        (QPalette.ColorRole.ButtonText, "fg"),
        (QPalette.ColorRole.Button, "surface"),
        (QPalette.ColorRole.Highlight, "accent"),
        (QPalette.ColorRole.HighlightedText, "accent_ink"),
        (QPalette.ColorRole.PlaceholderText, "muted"),
    ):
        pal.setColor(rol, QColor(T[clave]))
    app.setPalette(pal)
    marca = _marca()
    QDir.addSearchPath("icono", str(marca.parent))
    app.setStyleSheet(hoja(T).replace("url(:/marca)", f"url('{marca.as_posix()}')"))
    app.setFont(fuente(14))


def _marca() -> Path:
    """La marca blanca de las casillas, dibujada una vez en la carpeta temporal."""
    ruta = Path(tempfile.gettempdir()) / "maquetador-marca.png"
    if not ruta.exists():
        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#ffffff"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPolyline([QPointF(7, 17), QPointF(13, 23), QPointF(25, 9)])
        p.end()
        pm.save(str(ruta))
    return ruta


def icono_lupa(color: str, tam: int = 18) -> QIcon:
    pm = QPixmap(tam * 2, tam * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color), 3.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawEllipse(QRectF(5, 5, tam * 1.15, tam * 1.15))
    p.drawLine(QPointF(tam * 1.32, tam * 1.32), QPointF(tam * 1.8, tam * 1.8))
    p.end()
    return QIcon(pm)
