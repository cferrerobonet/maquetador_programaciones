"""Dibuja el icono de la app (un documento con escuadra y regla, verde EPLA) con QPainter.

Uso: QT_QPA_PLATFORM=offscreen python scripts/build/generar_icono.py
Escribe imagenes/icono.png, imagenes/icono.ico y src/maquetador/recursos/icono.png.
Después, en macOS, scripts/build/crear_icono.sh crea imagenes/icono.icns.
"""

import sys
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPolygonF

RAIZ = Path(__file__).resolve().parents[2]
VERDE, VERDE_OSCURO, DORADO = QColor("#2c7a3a"), QColor("#1f5a29"), QColor("#e3a94a")


def dibujar(tam: int = 1024) -> QImage:
    img = QImage(tam, tam, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    u = tam / 100.0
    p.scale(u, u)

    fondo = QPainterPath()
    fondo.addRoundedRect(QRectF(4, 4, 92, 92), 21, 21)
    p.fillPath(fondo, QBrush(VERDE))

    # Hoja con la esquina doblada.
    hoja = QPainterPath()
    hoja.moveTo(24, 16)
    hoja.lineTo(56, 16)
    hoja.lineTo(72, 32)
    hoja.lineTo(72, 84)
    hoja.lineTo(24, 84)
    hoja.closeSubpath()
    p.fillPath(hoja, QBrush(QColor("#ffffff")))
    doblez = QPolygonF([QPointF(56, 16), QPointF(56, 32), QPointF(72, 32)])
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#cfe3d2"))
    p.drawPolygon(doblez)

    # Título y líneas de texto.
    p.setBrush(VERDE_OSCURO)
    p.drawRoundedRect(QRectF(31, 38, 26, 5), 2.5, 2.5)
    p.setBrush(QColor("#b9c9bc"))
    for i, ancho in enumerate((34, 34, 22)):
        p.drawRoundedRect(QRectF(31, 49 + i * 8, ancho, 3.6), 1.8, 1.8)

    # Escuadra dorada (triángulo rectángulo con hueco) sobre la esquina inferior derecha.
    esc = QPainterPath()
    esc.moveTo(46, 90)
    esc.lineTo(90, 90)
    esc.lineTo(90, 46)
    esc.closeSubpath()
    hueco = QPainterPath()
    hueco.moveTo(62, 82)
    hueco.lineTo(82, 82)
    hueco.lineTo(82, 62)
    hueco.closeSubpath()
    p.fillPath(esc.subtracted(hueco), QBrush(DORADO))
    # Marcas de regla en el cateto horizontal.
    p.setPen(QPen(VERDE_OSCURO, 1.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for i in range(5):
        x = 52 + i * 7.5
        p.drawLine(QPointF(x, 90), QPointF(x, 90 - (5 if i % 2 == 0 else 3)))
    p.end()
    return img


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841 - Qt necesita la aplicación viva para dibujar
    img = dibujar(1024)
    destinos = (RAIZ / "imagenes" / "icono.png", RAIZ / "src" / "maquetador" / "recursos" / "icono.png")
    for d in destinos:
        d.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(d))
    img.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation).save(
        str(RAIZ / "imagenes" / "icono.ico"))
    print("Iconos creados en imagenes/ y recursos/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
