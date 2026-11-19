# -*- mode: python ; coding: utf-8 -*-
# Un único spec para macOS y Windows (como Partes de salida):
#   · nombre: «Maquetador de programaciones» en macOS y `MaquetadorProgramaciones` en Windows;
#   · icono: .icns en macOS, .ico en Windows; el BUNDLE solo existe en macOS.
# Ningún archivo empaquetado lleva acentos en el nombre (rompería la firma del .app).
import re
import sys
from pathlib import Path

ES_MACOS = sys.platform == "darwin"
NOMBRE = "Maquetador de programaciones" if ES_MACOS else "MaquetadorProgramaciones"
VERSION = re.search(
    r'^version = "([^"]+)"', (Path(SPECPATH) / "pyproject.toml").read_text(encoding="utf-8"), re.M
).group(1)
ICONO = "imagenes/icono.icns" if ES_MACOS else "imagenes/icono.ico"

datas = [
    ("src/maquetador/recursos", "maquetador/recursos"),
    # Las novedades de la ventana de actualización salen de aquí.
    ("CHANGELOG.md", "."),
]
# El motor se importa al usarlo: se declara para que PyInstaller lo empaquete.
hiddenimports = ["maquetador.motor", "lxml.etree", "lxml._elementpath"]

a = Analysis(
    ["src/main.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PyQt6.QtWebEngineCore", "PyQt6.QtQml", "PyQt6.QtQuick"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# Sin UPX: el empaquetado comprimido dispara los antivirus.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NOMBRE,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[ICONO],
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, upx_exclude=[], name=NOMBRE)

if ES_MACOS:
    app = BUNDLE(
        coll,
        name=f"{NOMBRE}.app",
        icon=ICONO,
        bundle_identifier="es.epla.maquetador",
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
        },
    )
