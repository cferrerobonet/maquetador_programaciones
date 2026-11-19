"""Ventana sin pantalla (QT_QPA_PLATFORM=offscreen), con el motor sustituido. Datos ficticios."""

import sys
import time
import types
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from maquetador import __version__
from maquetador.archivos import expandir_rutas, paginas_visibles, ruta_salida, total_paginas
from maquetador.modelo import CUMPLE, ERROR, MAQUETADA, NO_CUMPLE, NO_PROGRAMACION, PENDIENTE
from maquetador.ui import estilo
from maquetador.ui import ventana as vmod


@pytest.fixture(scope="session")
def app():
    a = QApplication.instance() or QApplication(sys.argv)
    estilo.cargar_fuentes()
    estilo.aplicar(a)
    return a


class ErrorMaquetador(Exception):
    pass


def motor_falso(llamadas):
    """Motor de mentira: «NOCUMPLE» en el nombre incumple, «OTRO» no es programación, «FALLA» da error."""

    class Referencia:
        resumen = "12 títulos · 7 tablas · portada con 6 campos"

        @classmethod
        def cargar(cls, ruta):
            if "mala" in Path(ruta).name:
                raise ErrorMaquetador("La referencia no tiene portada.")
            return cls()

    def comprobar(ref, ruta):
        n = Path(ruta).name
        llamadas.append(("comprobar", n))
        if "FALLA" in n:
            raise ErrorMaquetador("Archivo ilegible.")
        return types.SimpleNamespace(
            es_programacion="OTRO" not in n, cumple="NOCUMPLE" not in n,
            motivos=["Falta la portada", "Tabla sin cabecera"] if "NOCUMPLE" in n else [])

    def maquetar(ref, entrada, salida, actualizar_indice=True):
        llamadas.append(("maquetar", Path(entrada).name, Path(salida), actualizar_indice))
        Path(salida).write_bytes(b"docx ficticio")
        return types.SimpleNamespace(ok="FALLA" not in Path(entrada).name, avisos=["Revisa la tabla 3"],
                                     error="No se pudo guardar" if "FALLA" in Path(entrada).name else None)

    return types.SimpleNamespace(Referencia=Referencia, comprobar=comprobar, maquetar=maquetar,
                                 ErrorMaquetador=ErrorMaquetador)


def esperar(condicion, ms=5000):
    fin = time.monotonic() + ms / 1000
    while time.monotonic() < fin:
        QApplication.processEvents()
        if condicion():
            return
        time.sleep(0.01)
    raise AssertionError("Tiempo de espera agotado")


def crear(tmp_path, nombres):
    carpeta = tmp_path / "entrada"
    carpeta.mkdir(exist_ok=True)
    rutas = []
    for n in nombres:
        r = carpeta / n
        r.write_bytes(b"docx ficticio")
        rutas.append(r)
    return rutas


@pytest.fixture
def v(app, monkeypatch, tmp_path):
    llamadas = []
    monkeypatch.setattr(vmod, "cargar_motor", lambda: motor_falso(llamadas))
    ventana = vmod.Ventana()
    ventana.llamadas = llamadas
    ventana.show()
    yield ventana
    ventana.ejecutor.esperar()
    ventana.close()


def con_referencia(v, tmp_path):
    ref = crear(tmp_path, ["referencia.docx"])[0]
    v.cargar_referencia(ref)
    esperar(lambda: v.ref is not None)
    return ref


def listos(v):
    esperar(lambda: not v.ocupada())


def test_arranca_vacia(v):
    assert __version__ in v.windowTitle()
    assert v.lbl_rango.text() == "Mostrando 0 de 0"
    assert not v.btn_maquetar_no.isEnabled()
    assert not v.btn_primera.isEnabled() and not v.btn_ultima.isEnabled()
    assert v.chk_indice.isChecked()
    assert v.rb_junto.isChecked()


def test_referencia_valida_muestra_resumen(v, tmp_path):
    con_referencia(v, tmp_path)
    assert "12 títulos" in v.ref_resumen.text()


def test_referencia_con_error_muestra_el_error_y_no_se_puede_maquetar(v, tmp_path):
    ref = crear(tmp_path, ["mala.docx"])[0]
    v.cargar_referencia(ref)
    esperar(lambda: "portada" in v.ref_resumen.text())
    assert v.ref is None
    assert v.ref_resumen.property("rol") == "error"


def test_la_referencia_se_recuerda_entre_sesiones(v, app, monkeypatch, tmp_path):
    ref = con_referencia(v, tmp_path)
    v.ejecutor.esperar()
    otra = vmod.Ventana()
    try:
        assert otra.ref_ruta.text() == str(ref)
        esperar(lambda: otra.ref is not None)
    finally:
        otra.ejecutor.esperar()
        otra.close()


def test_anadir_comprueba_solas_y_asigna_estados(v, tmp_path):
    con_referencia(v, tmp_path)
    rutas = crear(tmp_path, ["a.docx", "b NOCUMPLE.docx", "c OTRO.docx", "d FALLA.docx"])
    assert v.anadir_rutas(rutas) == 4
    listos(v)
    estados = {it.archivo: it.estado for it in v.items}
    assert estados == {"a.docx": CUMPLE, "b NOCUMPLE.docx": NO_CUMPLE, "c OTRO.docx": NO_PROGRAMACION,
                       "d FALLA.docx": ERROR}
    assert v.btn_maquetar_no.isEnabled()
    assert all(it.resaltado for it in v.items)


def test_sin_referencia_quedan_pendientes_y_luego_se_comprueban(v, tmp_path):
    v.anadir_rutas(crear(tmp_path, ["a.docx"]))
    assert v.items[0].estado == PENDIENTE
    assert v.llamadas == []
    con_referencia(v, tmp_path)
    listos(v)
    assert v.items[0].estado == CUMPLE


def test_carpetas_y_filtro_de_temporales(v, tmp_path):
    base = tmp_path / "carpeta"
    (base / "sub").mkdir(parents=True)
    for n in ("uno.docx", "~$uno.docx", ".oculto.docx", "nota.txt", "sub/dos.DOCX"):
        (base / n).write_bytes(b"x")
    assert [p.name for p in expandir_rutas([base])] == ["dos.DOCX", "uno.docx"]
    assert v.anadir_rutas([base, base / "uno.docx"]) == 2  # sin repetidos
    assert v.anadir_rutas([base]) == 0


def test_paginacion_y_pie(v, tmp_path):
    v.anadir_rutas(crear(tmp_path, [f"p{i:02d}.docx" for i in range(23)]))
    assert v.lbl_rango.text() == "Mostrando 1–10 de 23"
    assert not v.btn_primera.isEnabled() and not v.btn_anterior.isEnabled()
    assert v.btn_siguiente.isEnabled() and v.btn_ultima.isEnabled()
    assert [b.text() for b in v.btns_numero if b.isVisible()] == ["1", "2", "3"]
    v.btn_siguiente.click()
    assert v.lbl_rango.text() == "Mostrando 11–20 de 23"
    assert v.btn_primera.isEnabled()
    v.btn_ultima.click()
    assert v.lbl_rango.text() == "Mostrando 21–23 de 23"
    assert not v.btn_siguiente.isEnabled() and not v.btn_ultima.isEnabled()
    v.combo_filas.setCurrentIndex(4)  # 50
    assert v.lbl_rango.text() == "Mostrando 1–23 de 23"
    assert [v.combo_filas.itemText(i) for i in range(v.combo_filas.count())] == ["5", "10", "15", "20", "50"]


def test_cinco_numeros_con_la_pagina_actual_dentro():
    assert paginas_visibles(1, 20) == [1, 2, 3, 4, 5]
    assert paginas_visibles(10, 20) == [8, 9, 10, 11, 12]
    assert paginas_visibles(20, 20) == [16, 17, 18, 19, 20]
    assert paginas_visibles(1, 2) == [1, 2]
    assert paginas_visibles(1, 0) == [1]
    assert total_paginas(0, 10) == 1 and total_paginas(21, 10) == 3


def test_orden_por_cabecera(v, tmp_path):
    v.anadir_rutas(crear(tmp_path, ["b.docx", "a.docx", "c.docx"]))
    assert [it.archivo for it in v.modelo.filas] == ["a.docx", "b.docx", "c.docx"]
    v.tabla.horizontalHeader().sectionClicked.emit(0)
    assert [it.archivo for it in v.modelo.filas] == ["c.docx", "b.docx", "a.docx"]
    v.tabla.horizontalHeader().sectionClicked.emit(2)
    assert v._orden_col == 2 and not v._orden_desc


def test_buscador_filtro_y_limpiar(v, tmp_path):
    con_referencia(v, tmp_path)
    v.anadir_rutas(crear(tmp_path, ["a.docx", "b NOCUMPLE.docx", "c.docx"]))
    listos(v)
    v.buscador.setText("nocumple")
    assert [it.archivo for it in v.modelo.filas] == ["b NOCUMPLE.docx"]
    v.limpiar_filtros()
    assert len(v.modelo.filas) == 3 and v.buscador.text() == ""
    v.filtro_estado.setCurrentText(NO_CUMPLE)
    assert [it.archivo for it in v.modelo.filas] == ["b NOCUMPLE.docx"]
    assert "filtradas de 3" in v.lbl_rango.text()
    v.limpiar_filtros()
    assert v.filtro_estado.currentIndex() == 0


def test_quitar_seleccionadas(v, tmp_path):
    v.anadir_rutas(crear(tmp_path, ["a.docx", "b.docx"]))
    v.tabla.selectRow(0)
    assert v.btn_quitar.isEnabled()
    v.quitar_seleccionadas()
    assert [it.archivo for it in v.items] == ["b.docx"]


def test_maquetar_las_que_no_cumplen_junto_al_original_sin_pisar(v, tmp_path):
    con_referencia(v, tmp_path)
    rutas = crear(tmp_path, ["a.docx", "b NOCUMPLE.docx"])
    (tmp_path / "entrada" / "b NOCUMPLE (maquetada).docx").write_bytes(b"ya existe")
    v.anadir_rutas(rutas)
    listos(v)
    v.maquetar_no_cumplen()
    listos(v)
    it = next(i for i in v.items if i.estado == MAQUETADA)
    assert it.salida.name == "b NOCUMPLE (maquetada) (2).docx"
    assert (tmp_path / "entrada" / "b NOCUMPLE (maquetada).docx").read_bytes() == b"ya existe"
    assert it.avisos == ["Revisa la tabla 3"]
    assert "Revisa la tabla 3" in it.detalle()
    assert v.llamadas[-1][3] is True  # actualizar índice
    assert next(i for i in v.items if i.archivo == "a.docx").estado == CUMPLE


def test_maquetar_en_carpeta_y_sin_actualizar_indice(v, tmp_path):
    con_referencia(v, tmp_path)
    v.anadir_rutas(crear(tmp_path, ["a.docx"]))
    listos(v)
    destino = tmp_path / "salida" / "nueva"
    v.fijar_carpeta_destino(destino)
    v.chk_indice.setChecked(False)
    v.tabla.selectRow(0)
    v.maquetar_seleccionadas()
    listos(v)
    assert v.items[0].estado == MAQUETADA
    assert v.items[0].salida == destino / "a (maquetada).docx"
    assert v.llamadas[-1][3] is False
    assert v.carpeta_destino_actual() == destino


def test_error_del_motor_deja_la_fila_en_error(v, tmp_path):
    con_referencia(v, tmp_path)
    v.anadir_rutas(crear(tmp_path, ["z FALLA.docx"]))
    listos(v)
    v.tabla.selectRow(0)
    v.items[0].estado = CUMPLE
    v.maquetar_seleccionadas()
    listos(v)
    assert v.items[0].estado == ERROR
    assert "No se pudo guardar" in v.items[0].detalle()


def test_doble_clic_abre_el_maquetado_si_existe(v, tmp_path, monkeypatch):
    con_referencia(v, tmp_path)
    v.anadir_rutas(crear(tmp_path, ["a NOCUMPLE.docx"]))
    listos(v)
    abiertas = []
    monkeypatch.setattr(v, "abrir_ruta", abiertas.append)
    v._doble_clic(v.modelo.index(0, 0))
    v.maquetar_no_cumplen()
    listos(v)
    v._doble_clic(v.modelo.index(0, 0))
    assert [p.name for p in abiertas] == ["a NOCUMPLE.docx", "a NOCUMPLE (maquetada).docx"]


def test_ruta_salida_nunca_pisa(tmp_path):
    ent = tmp_path / "x.docx"
    assert ruta_salida(ent).name == "x (maquetada).docx"
    (tmp_path / "x (maquetada).docx").touch()
    (tmp_path / "x (maquetada) (2).docx").touch()
    assert ruta_salida(ent).name == "x (maquetada) (3).docx"
    assert ruta_salida(ent, tmp_path / "otra").parent == tmp_path / "otra"


def test_aviso_de_version_nueva_y_novedades(v):
    assert v.boton_actualizar.isHidden()
    v.isVisible = lambda: False  # sin abrir el diálogo modal en la prueba
    v.actualizacion_disponible("9.0.0", "https://github.com/x", "notas")
    assert not v.boton_actualizar.isHidden()
    assert "9.0.0" in v.boton_actualizar.text()


def test_novedades_solo_tras_cambiar_de_version(v, monkeypatch):
    from maquetador.ajustes import ajustes

    vistas = []
    monkeypatch.setattr(v, "mostrar_novedades", lambda *a: vistas.append(1))
    v.novedades_si_cambio_de_version()
    assert vistas == []  # primera instalación
    ajustes().setValue("version_vista", "0.0.1")
    v.novedades_si_cambio_de_version()
    assert vistas == [1]
    v.novedades_si_cambio_de_version()
    assert vistas == [1]
