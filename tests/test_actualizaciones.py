"""Actualización automática: aviso, descarga verificada con sha256 y novedades. Red simulada."""

import hashlib
import io
import json
import zipfile

import pytest

from maquetador import actualizaciones as act
from maquetador.novedades import novedades

VERSION = "9.9.9"
NOMBRE = f"MaquetadorProgramaciones-{VERSION}-Windows-Portable.zip"
URL = f"{act.DESCARGAS_WEB}/v{VERSION}/{NOMBRE}"
API_TAG = f"https://api.github.com/repos/{act.REPO}/releases/tags/v{VERSION}"
CONTENIDO = b"archivo ficticio " * 5000


class _Respuesta(io.BytesIO):
    def __init__(self, datos: bytes, url: str):
        super().__init__(datos)
        self.headers = {"Content-Length": str(len(datos))}
        self._url = url

    def geturl(self):
        return self._url


@pytest.fixture
def red(monkeypatch):
    """Sustituye urlopen: la API da el digest que se pida y la descarga, el contenido que se pida."""
    estado = {"digest": "sha256:" + hashlib.sha256(CONTENIDO).hexdigest(), "contenido": CONTENIDO, "pedidas": []}

    def urlopen(req, timeout=None, context=None):
        url = req.full_url
        estado["pedidas"].append((url, timeout))
        if url == API_TAG:
            assets = [{"name": NOMBRE, "browser_download_url": URL}]
            if estado["digest"] is not None:
                assets[0]["digest"] = estado["digest"]
            return _Respuesta(json.dumps({"tag_name": f"v{VERSION}", "assets": assets}).encode(), url)
        if url == URL:
            return _Respuesta(estado["contenido"], url)
        raise AssertionError(f"URL inesperada: {url}")

    monkeypatch.setattr(act.urllib.request, "urlopen", urlopen)
    return estado


def test_el_repositorio_es_el_de_las_releases():
    assert act.REPO == "cferrerobonet/maquetador_programaciones"


def test_comparar_versiones():
    assert act.es_mas_nueva("0.2.0", "0.1.0")
    assert act.es_mas_nueva("0.10.0", "0.9.9")
    assert not act.es_mas_nueva("0.1.0", "0.1.0")
    assert not act.es_mas_nueva("x", "0.1.0")


def test_ultima_version_por_la_api(monkeypatch):
    monkeypatch.setattr(act.platform, "system", lambda: "Windows")

    def urlopen(req, timeout=None, context=None):
        assert req.full_url == act.RELEASES_URL
        cuerpo = {"tag_name": "v1.2.3", "body": "Novedad", "assets": [
            {"name": "x_macOS.dmg", "browser_download_url": f"{act.DESCARGAS_WEB}/v1.2.3/x_macOS.dmg"},
            {"name": "x.zip", "browser_download_url": f"{act.DESCARGAS_WEB}/v1.2.3/x.zip"}]}
        return _Respuesta(json.dumps(cuerpo).encode(), req.full_url)

    monkeypatch.setattr(act.urllib.request, "urlopen", urlopen)
    assert act.ultima_version() == ("1.2.3", f"{act.DESCARGAS_WEB}/v1.2.3/x.zip", "Novedad")


def test_si_la_api_falla_se_pregunta_a_la_web(monkeypatch):
    monkeypatch.setattr(act.platform, "system", lambda: "Darwin")

    def urlopen(req, timeout=None, context=None):
        if req.full_url == act.RELEASES_URL:
            raise OSError("límite de la API")
        return _Respuesta(b"", f"https://github.com/{act.REPO}/releases/tag/v3.0.0")

    monkeypatch.setattr(act.urllib.request, "urlopen", urlopen)
    version, url, notas = act.ultima_version()
    assert version == "3.0.0"
    assert url == f"{act.DESCARGAS_WEB}/v3.0.0/MaquetadorProgramaciones_v3.0.0_macOS.dmg"
    assert notas == ""


def test_comprobar_avisa_solo_si_hay_version_nueva(monkeypatch):
    import threading

    monkeypatch.setattr(act, "ultima_version", lambda: ("0.2.0", "https://github.com/x", "notas"))
    recibido, hecho = [], threading.Event()
    act.comprobar("0.1.0", lambda *a: (recibido.append(a), hecho.set()))
    assert hecho.wait(5)
    assert recibido == [("0.2.0", "https://github.com/x", "notas")]


def test_digest_del_asset_lee_la_api_de_releases(red):
    assert act.digest_del_asset(URL) == hashlib.sha256(CONTENIDO).hexdigest()


def test_digest_sin_formato_valido_es_vacio(red):
    red["digest"] = "md5:abc"
    assert act.digest_del_asset(URL) == ""


def test_digest_de_una_url_ajena_no_consulta_nada(red):
    assert act.digest_del_asset("https://ejemplo.example.com/v1/x.zip") == ""
    assert red["pedidas"] == []


def test_descarga_correcta_se_guarda_y_avanza(red, tmp_path):
    destino = tmp_path / NOMBRE
    avances = []
    assert act.descargar_verificado(URL, destino, avances.append) == destino
    assert destino.read_bytes() == CONTENIDO
    assert avances and avances[-1] == 100


def test_descarga_manipulada_se_borra(red, tmp_path):
    red["contenido"] = CONTENIDO + b"cambiado"
    destino = tmp_path / NOMBRE
    with pytest.raises(act.DescargaNoVerificada, match="no coincide"):
        act.descargar_verificado(URL, destino)
    assert not destino.exists()


def test_sin_digest_no_se_descarga(red, tmp_path):
    red["digest"] = None
    with pytest.raises(act.DescargaNoVerificada, match="comprobar"):
        act.descargar_verificado(URL, tmp_path / NOMBRE)
    assert [u for u, _ in red["pedidas"]] == [API_TAG]


def test_toda_peticion_lleva_timeout(red, tmp_path):
    act.descargar_verificado(URL, tmp_path / NOMBRE)
    assert red["pedidas"] and all(t for _, t in red["pedidas"])


def test_url_no_de_confianza_se_rechaza(red, tmp_path):
    with pytest.raises(ValueError):
        act.descargar_verificado("http://github.com/x/releases/download/v1/x.zip", tmp_path / "x.zip")
    assert red["pedidas"] == []


def test_en_macos_la_descarga_se_pasa_a_actualizar_mac(monkeypatch, tmp_path):
    from maquetador import actualizar_mac
    from maquetador.rutas import carpeta_datos

    pedidas = []
    monkeypatch.setattr(act.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        actualizar_mac, "instalar",
        lambda dmg, registros: pedidas.append((dmg, registros)) or actualizar_mac.Resultado(False, "arrástrala"))
    assert act.instalar_descarga(str(tmp_path / "x.dmg")) == "arrástrala"
    assert pedidas == [(tmp_path / "x.dmg", carpeta_datos() / "logs")]


def test_en_windows_se_descomprime_el_portable_y_se_abre_la_carpeta(monkeypatch, tmp_path):
    zip_ = tmp_path / "MaquetadorProgramaciones-1.0.0-Windows-Portable.zip"
    with zipfile.ZipFile(zip_, "w") as z:
        z.writestr("MaquetadorProgramaciones.exe", "ficticio")
    abiertas = []
    monkeypatch.setattr(act.platform, "system", lambda: "Windows")
    monkeypatch.setattr(act, "abrir_ruta", abiertas.append)
    aviso = act.instalar_descarga(str(zip_))
    carpeta = zip_.with_suffix("")
    assert (carpeta / "MaquetadorProgramaciones.exe").read_text() == "ficticio"
    assert abiertas == [str(carpeta)]
    assert str(carpeta) in aviso


def test_un_zip_con_rutas_fuera_de_la_carpeta_se_rechaza(tmp_path):
    zip_ = tmp_path / "malo.zip"
    with zipfile.ZipFile(zip_, "w") as z:
        z.writestr("../fuera.txt", "x")
    with pytest.raises(act.DescargaNoVerificada):
        act.descomprimir_portable(zip_, tmp_path / "malo")
    assert not (tmp_path / "fuera.txt").exists()


def test_novedades_de_una_version(tmp_path):
    md = tmp_path / "CHANGELOG.md"
    md.write_text("# Cambios\n\n## [0.2.0] - 2026-12-01\n\n- Algo nuevo\n\n## [0.1.0] - 2026-11-19\n\n- Primera\n",
                  encoding="utf-8")
    assert novedades("0.2.0", md) == "- Algo nuevo"
    assert novedades("0.1.0", md) == "- Primera"
    assert novedades("7.0.0", md) == ""
    assert novedades("0.1.0", tmp_path / "no_existe.md") == ""


def test_el_changelog_del_repositorio_trae_la_version_actual():
    from maquetador import __version__

    assert novedades(__version__)
