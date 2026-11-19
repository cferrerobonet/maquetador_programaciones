"""Arranque de la aplicación."""

from __future__ import annotations

import logging
import os
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from . import NOMBRE_APP, __version__
from .rutas import recursos

logger = logging.getLogger(__name__)
#: Prueba de humo del ejecutable congelado (CI): llega a la ventana, lo anuncia y sale.
PRUEBA = os.environ.get("MAQUETADOR_PRUEBA_DE_ARRANQUE")
MARCA_PRUEBA = "PRUEBA DE ARRANQUE: ventana principal a la vista"


def icono_app() -> QIcon:
    ruta = recursos() / "icono.png"
    return QIcon(str(ruta)) if ruta.exists() else QIcon()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Arranca %s %s (%s)", NOMBRE_APP, __version__, sys.platform)
    app = QApplication(argv)
    app.setApplicationName(NOMBRE_APP)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("EPLA")
    app.setWindowIcon(icono_app())

    from .ui import estilo

    estilo.cargar_fuentes()
    estilo.aplicar(app)

    from .ui.ventana import Ventana

    ventana = Ventana()
    ventana.show()
    if PRUEBA:
        def fin_de_prueba() -> None:
            print(MARCA_PRUEBA, flush=True)
            app.quit()

        QTimer.singleShot(2500, fin_de_prueba)
    else:
        # Al abrir y, como la app puede pasar el día abierta, cada 4 horas.
        QTimer.singleShot(800, ventana.novedades_si_cambio_de_version)
        QTimer.singleShot(4000, ventana.buscar_actualizaciones)
        revision = QTimer(app, interval=4 * 3600 * 1000)
        revision.timeout.connect(ventana.buscar_actualizaciones)
        revision.start()
    codigo = app.exec()
    logger.info("Cierre normal (%s)", codigo)
    return codigo
