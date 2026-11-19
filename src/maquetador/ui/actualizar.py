"""Diálogos de actualización: aviso de versión nueva, descarga verificada y novedades."""

from __future__ import annotations

import tempfile
import webbrowser
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from .. import NOMBRE_APP, __version__
from ..actualizaciones import PAGINA_DE_RELEASES, comprobar, descargar_verificado, instalar_descarga
from . import estilo


class _Puente(QObject):
    """Lleva la respuesta de GitHub del hilo de comprobación a la interfaz."""

    respuesta = pyqtSignal(str, str, str)


_puentes: list[_Puente] = []


def buscar_actualizaciones(padre, avisar_si_al_dia: bool = False, al_encontrar=None) -> None:
    """Pregunta a GitHub en segundo plano; con versión nueva llama a `al_encontrar(version, url, notas)`."""
    puente = _Puente()
    _puentes.append(puente)

    def recibir(version: str, url: str, notas: str):
        _puentes.remove(puente)
        if version:
            (al_encontrar or (lambda v, u, n: ofrecer(padre, v, u, n)))(version, url, notas)
        elif avisar_si_al_dia:
            if notas:
                QMessageBox.information(padre, "Actualizaciones", f"No he podido comprobarlo:\n{notas}")
            else:
                QMessageBox.information(padre, "Actualizaciones", f"Tienes la última versión ({__version__}).")

    puente.respuesta.connect(recibir)
    comprobar(__version__, puente.respuesta.emit, siempre=avisar_si_al_dia)


def _titulo(texto: str):
    lb = QLabel(texto)
    lb.setFont(estilo.fuente(24, QFont.Weight.Bold, estilo.TITULAR))
    lb.setWordWrap(True)
    return lb


def _notas(notas: str) -> QTextBrowser:
    texto = QTextBrowser()
    texto.setOpenExternalLinks(True)
    texto.setMarkdown(notas)
    return texto


class DialogoActualizacion(QDialog):
    """Aviso de versión nueva: actualizar es la opción destacada."""

    def __init__(self, version: str, notas: str, padre=None):
        super().__init__(padre)
        self.setWindowTitle("Actualización disponible")
        self.setModal(True)
        self.resize(520, 420 if notas else 240)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(26, 22, 26, 20)
        capa.setSpacing(12)
        capa.addWidget(_titulo(f"Hay una versión nueva: {version}"))
        aviso = QLabel(f"Tienes la {__version__}. Se descarga, se comprueba y se sustituye; tus ajustes se conservan.")
        aviso.setProperty("rol", "muted")
        aviso.setWordWrap(True)
        capa.addWidget(aviso)
        if notas:
            etiqueta = QLabel("Novedades")
            etiqueta.setProperty("rol", "etiqueta")
            etiqueta.setFont(estilo.etiqueta_fuente())
            capa.addWidget(etiqueta)
            capa.addWidget(_notas(notas), 1)
        else:
            capa.addStretch(1)
        botones = QHBoxLayout()
        botones.addStretch(1)
        luego = QPushButton("Más tarde")
        ahora = QPushButton("Actualizar ahora")
        ahora.setProperty("primario", True)
        ahora.setDefault(True)
        luego.clicked.connect(self.reject)
        ahora.clicked.connect(self.accept)
        botones.addWidget(luego)
        botones.addWidget(ahora)
        capa.addLayout(botones)


class DialogoNovedades(QDialog):
    """Qué trae la versión instalada, tomado de `CHANGELOG.md`."""

    def __init__(self, version: str, notas: str, padre=None):
        super().__init__(padre)
        self.setWindowTitle("Novedades")
        self.resize(520, 380)
        capa = QVBoxLayout(self)
        capa.setContentsMargins(26, 22, 26, 20)
        capa.setSpacing(12)
        capa.addWidget(_titulo(f"Novedades de la versión {version}"))
        capa.addWidget(_notas(notas or "Esta versión no trae notas."), 1)
        cerrar = QPushButton("Entendido")
        cerrar.setProperty("primario", True)
        cerrar.clicked.connect(self.accept)
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(cerrar)
        capa.addLayout(fila)


def ofrecer(padre, version: str, url: str, notas: str) -> None:
    dialogo = DialogoActualizacion(version, notas, padre)
    dialogo.raise_()
    dialogo.activateWindow()
    if dialogo.exec() != QDialog.DialogCode.Accepted:
        return
    if not url:
        webbrowser.open(PAGINA_DE_RELEASES)
        return
    _descargar(padre, url, version)


class _Descargador(QThread):
    avance = pyqtSignal(int)
    listo = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, url: str, destino: Path):
        super().__init__()
        self._url = url
        self._destino = destino

    def run(self):
        # Solo se usa si el sha256 coincide con el digest del asset en la API de releases.
        try:
            ruta = descargar_verificado(self._url, self._destino, self.avance.emit)
        except ValueError:
            self.error.emit("La dirección de descarga no es de confianza; se cancela.")
            return
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"{e}\n\nPuedes descargarla a mano desde {PAGINA_DE_RELEASES}")
            return
        self.listo.emit(str(ruta))


def _descargar(padre, url: str, version: str) -> None:
    destino = Path(tempfile.mkdtemp(prefix="maquetador-actualizacion-")) / url.rsplit("/", 1)[-1]
    progreso = QProgressDialog(f"Descargando {NOMBRE_APP} {version}…", "Cancelar", 0, 100, padre)
    progreso.setWindowTitle("Actualización")
    progreso.setMinimumDuration(0)
    progreso.setWindowModality(Qt.WindowModality.WindowModal)
    hilo = _Descargador(url, destino)
    progreso._hilo = hilo
    hilo.avance.connect(progreso.setValue)
    progreso.canceled.connect(hilo.terminate)

    def instalar(ruta):
        progreso.close()
        try:
            aviso = instalar_descarga(ruta)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(padre, "Actualización", f"{e}\n\nPuedes descargarla a mano desde {PAGINA_DE_RELEASES}")
            return
        if aviso:
            QMessageBox.information(padre, "Actualización", aviso)
        QApplication.instance().quit()

    hilo.listo.connect(instalar)
    hilo.error.connect(lambda e: (progreso.close(), QMessageBox.critical(padre, "Error de descarga", e)))
    hilo.start()
