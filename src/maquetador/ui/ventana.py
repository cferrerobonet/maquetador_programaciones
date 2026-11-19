"""Ventana principal: referencia, programaciones a maquetar, destino y botones de acción."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QModelIndex, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .. import NOMBRE_APP, __version__
from ..ajustes import ajustes
from ..archivos import expandir_rutas, paginas_visibles, ruta_salida, total_paginas
from ..hilos import Ejecutor, Senales
from ..modelo import (
    CUMPLE,
    ERROR,
    ESTADOS,
    MAQUETADA,
    NO_CUMPLE,
    NO_PROGRAMACION,
    PENDIENTE,
    Item,
    ModeloLista,
)
from . import estilo
from .estilo import T

logger = logging.getLogger(__name__)

TODOS = "Todos los estados"
FILAS_POR_PAGINA = (5, 10, 15, 20, 50)
NUM_BOTONES = 5


def cargar_motor():
    """El motor se importa al usarlo; las pruebas lo sustituyen por uno falso."""
    from maquetador import motor

    return motor


def _boton(texto: str, **props) -> QPushButton:
    b = QPushButton(texto)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    for k, v in props.items():
        b.setProperty(k, v)
    return b


def _rotulo(texto: str, rol: str) -> QLabel:
    lb = QLabel(texto)
    lb.setProperty("rol", rol)
    return lb


def _caja() -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setProperty("rol", "caja")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 14, 18, 14)
    lay.setSpacing(10)
    return f, lay


class Ventana(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{NOMBRE_APP} {__version__}")
        self.setMinimumSize(QSize(980, 700))
        self.resize(1100, 820)
        self.setAcceptDrops(True)

        self.ref = None
        self._gen = 0
        self.items: list[Item] = []
        self._vista: list[Item] = []
        self._pagina = 1
        self._orden_col = 0
        self._orden_desc = False
        self._pendientes = 0
        self._lote_total = 0
        self._lote_hechas = 0
        self._ultima_salida: Path | None = None
        self.carpeta_destino: Path | None = None

        self.senales = Senales(self)
        self.senales.terminada.connect(self._al_terminar_tarea)
        self.ejecutor = Ejecutor(self.senales)
        self._temporizador_resalte = QTimer(self, singleShot=True, interval=4300)
        self._temporizador_resalte.timeout.connect(lambda: (self.modelo.refrescar()))

        self._construir()
        self._restaurar_ajustes()
        self._rehacer_vista()
        self._actualizar_botones()

    # ------------------------------------------------------------------ interfaz
    def _construir(self) -> None:
        raiz = QWidget()
        raiz.setObjectName("raiz")
        self.setCentralWidget(raiz)
        col = QVBoxLayout(raiz)
        col.setContentsMargins(24, 18, 24, 16)
        col.setSpacing(12)

        cabecera = QHBoxLayout()
        cabecera.addWidget(_rotulo(NOMBRE_APP, "titulo"), 1)
        # Aviso de versión nueva: oculto hasta que GitHub diga que la hay.
        self.boton_actualizar = _boton("", pequeno=True, primario=True)
        self.boton_actualizar.hide()
        self.boton_actualizar.clicked.connect(self._ofrecer_actualizacion)
        btn_novedades = _boton("Novedades", pequeno=True)
        btn_novedades.clicked.connect(lambda: self.mostrar_novedades())
        btn_buscar = _boton("Buscar actualizaciones", pequeno=True)
        btn_buscar.clicked.connect(lambda: self.buscar_actualizaciones(avisar_si_al_dia=True))
        for b in (self.boton_actualizar, btn_novedades, btn_buscar):
            cabecera.addWidget(b)
        col.addLayout(cabecera)
        col.addWidget(_rotulo(
            "Elige la programación cuya maquetación manda y añade las que no la respetan: "
            "te devuelvo copias con su maquetación y el mismo contenido.", "subtitulo"))

        col.addWidget(self._bloque_referencia())
        col.addWidget(self._bloque_programaciones(), 1)
        col.addWidget(self._bloque_destino())

        pie = QHBoxLayout()
        self.estado_lbl = _rotulo("", "muted")
        self.progreso = QProgressBar()
        self.progreso.setFixedWidth(260)
        self.progreso.setVisible(False)
        pie.addWidget(self.estado_lbl, 1)
        pie.addWidget(self.progreso)
        col.addLayout(pie)

        QShortcut(QKeySequence.StandardKey.Delete, self.tabla, activated=self.quitar_seleccionadas)

    def _bloque_referencia(self) -> QFrame:
        caja, lay = _caja()
        lay.addWidget(_rotulo("Programación de referencia", "seccion"))
        fila = QHBoxLayout()
        self.ref_ruta = QLineEdit()
        self.ref_ruta.setReadOnly(True)
        self.ref_ruta.setPlaceholderText("Todavía no has elegido ninguna programación de referencia")
        self.btn_ref = _boton("Elegir…")
        self.btn_ref.clicked.connect(self.elegir_referencia)
        fila.addWidget(self.ref_ruta, 1)
        fila.addWidget(self.btn_ref)
        lay.addLayout(fila)
        self.ref_resumen = _rotulo("", "muted")
        self.ref_resumen.setWordWrap(True)
        lay.addWidget(self.ref_resumen)
        return caja

    def _bloque_programaciones(self) -> QFrame:
        caja, lay = _caja()
        lay.addWidget(_rotulo("Programaciones a maquetar", "seccion"))

        self.zona_soltar = QFrame()
        self.zona_soltar.setProperty("rol", "soltar")
        fz = QHBoxLayout(self.zona_soltar)
        fz.setContentsMargins(14, 8, 14, 8)
        fz.addWidget(_rotulo("Arrastra aquí archivos .docx o carpetas con programaciones", "muted"), 1)
        self.btn_anadir = _boton("Añadir programaciones…", primario=True)
        self.btn_anadir.clicked.connect(self.elegir_programaciones)
        fz.addWidget(self.btn_anadir)
        lay.addWidget(self.zona_soltar)

        filtros = QHBoxLayout()
        self.buscador = QLineEdit()
        self.buscador.setObjectName("buscador")
        self.buscador.setPlaceholderText("Buscar por archivo, carpeta, estado o motivo")
        self.buscador.addAction(estilo.icono_lupa(T["muted"]), QLineEdit.ActionPosition.LeadingPosition)
        self.buscador.setClearButtonEnabled(True)
        self.buscador.textChanged.connect(self._filtros_cambiados)
        self.filtro_estado = QComboBox()
        self.filtro_estado.addItems([TODOS, *ESTADOS])
        self.filtro_estado.currentIndexChanged.connect(self._filtros_cambiados)
        self.btn_limpiar = _boton("Limpiar filtros", pequeno=True)
        self.btn_limpiar.clicked.connect(self.limpiar_filtros)
        self.btn_quitar = _boton("Quitar seleccionadas", pequeno=True, peligro=True)
        self.btn_quitar.clicked.connect(self.quitar_seleccionadas)
        filtros.addWidget(self.buscador, 1)
        filtros.addWidget(self.filtro_estado)
        filtros.addWidget(self.btn_limpiar)
        filtros.addSpacing(12)
        filtros.addWidget(self.btn_quitar)
        lay.addLayout(filtros)

        self.modelo = ModeloLista(self)
        self.tabla = QTableView()
        self.tabla.setModel(self.modelo)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setShowGrid(False)
        self.tabla.setWordWrap(False)
        self.tabla.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tabla.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(34)
        cab = self.tabla.horizontalHeader()
        cab.setSectionsClickable(True)
        cab.setSortIndicatorShown(True)
        cab.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        cab.setStretchLastSection(True)
        cab.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for i, ancho in enumerate((300, 170, 190)):
            self.tabla.setColumnWidth(i, ancho)
        cab.sectionClicked.connect(self.ordenar_por)
        self.tabla.doubleClicked.connect(self._doble_clic)
        self.tabla.selectionModel().selectionChanged.connect(self._seleccion_cambiada)
        lay.addWidget(self.tabla, 1)

        self.detalle = QPlainTextEdit()
        self.detalle.setReadOnly(True)
        self.detalle.setFixedHeight(84)
        self.detalle.setPlaceholderText("Selecciona una programación para ver el detalle de su comprobación.")
        lay.addWidget(self.detalle)

        lay.addLayout(self._pie_paginacion())
        return caja

    def _pie_paginacion(self) -> QHBoxLayout:
        pie = QHBoxLayout()
        self.lbl_rango = _rotulo("", "muted")
        pie.addWidget(self.lbl_rango, 1)
        pie.addWidget(_rotulo("Filas por página", "muted"))
        self.combo_filas = QComboBox()
        for n in FILAS_POR_PAGINA:
            self.combo_filas.addItem(str(n), n)
        self.combo_filas.setCurrentIndex(FILAS_POR_PAGINA.index(10))
        self.combo_filas.currentIndexChanged.connect(self._filas_cambiadas)
        pie.addWidget(self.combo_filas)
        pie.addSpacing(12)

        def pag(texto: str, tip: str) -> QPushButton:
            b = _boton(texto, pagina=True)
            b.setToolTip(tip)
            return b

        self.btn_primera = pag("«", "Primera página")
        self.btn_anterior = pag("‹", "Página anterior")
        self.btn_siguiente = pag("›", "Página siguiente")
        self.btn_ultima = pag("»", "Última página")
        self.btn_primera.clicked.connect(lambda: self.ir_a_pagina(1))
        self.btn_anterior.clicked.connect(lambda: self.ir_a_pagina(self._pagina - 1))
        self.btn_siguiente.clicked.connect(lambda: self.ir_a_pagina(self._pagina + 1))
        self.btn_ultima.clicked.connect(lambda: self.ir_a_pagina(self.total_paginas()))
        pie.addWidget(self.btn_primera)
        pie.addWidget(self.btn_anterior)
        self.btns_numero: list[QPushButton] = []
        for _ in range(NUM_BOTONES):
            b = _boton("", pagina=True)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, bb=b: self.ir_a_pagina(int(bb.text())))
            self.btns_numero.append(b)
            pie.addWidget(b)
        pie.addWidget(self.btn_siguiente)
        pie.addWidget(self.btn_ultima)
        return pie

    def _bloque_destino(self) -> QFrame:
        caja, lay = _caja()
        lay.addWidget(_rotulo("Destino", "seccion"))
        fila = QHBoxLayout()
        self.rb_junto = QRadioButton("Junto a cada original, con el sufijo « (maquetada)»")
        self.rb_carpeta = QRadioButton("En una carpeta…")
        self.rb_junto.setChecked(True)
        self.rb_junto.toggled.connect(self._destino_cambiado)
        self.btn_carpeta = _boton("Elegir carpeta…", pequeno=True)
        self.btn_carpeta.clicked.connect(self.elegir_carpeta_destino)
        self.lbl_carpeta = _rotulo("", "muted")
        fila.addWidget(self.rb_junto)
        fila.addSpacing(16)
        fila.addWidget(self.rb_carpeta)
        fila.addWidget(self.btn_carpeta)
        fila.addWidget(self.lbl_carpeta, 1)
        lay.addLayout(fila)

        self.chk_indice = QCheckBox("Actualizar el índice al abrir en Word")
        self.chk_indice.setChecked(True)
        self.chk_indice.toggled.connect(self._destino_cambiado)
        lay.addWidget(self.chk_indice)
        lay.addWidget(_rotulo("Nunca se sobrescribe nada: si ya existe un archivo con ese nombre, se añade « (2)», « (3)»…", "pequeno"))

        acciones = QHBoxLayout()
        self.btn_abrir_carpeta = _boton("Abrir carpeta de destino")
        self.btn_abrir_carpeta.clicked.connect(self.abrir_carpeta_destino)
        self.btn_maquetar_sel = _boton("Maquetar seleccionadas")
        self.btn_maquetar_sel.clicked.connect(self.maquetar_seleccionadas)
        self.btn_maquetar_no = _boton("Maquetar las que no cumplen", primario=True)
        self.btn_maquetar_no.clicked.connect(self.maquetar_no_cumplen)
        acciones.addWidget(self.btn_abrir_carpeta)
        acciones.addStretch(1)
        acciones.addWidget(self.btn_maquetar_sel)
        acciones.addWidget(self.btn_maquetar_no)
        lay.addLayout(acciones)
        return caja

    # ------------------------------------------------------------------ ajustes
    def _restaurar_ajustes(self) -> None:
        s = ajustes()
        if s.value("destino_modo", "junto") == "carpeta":
            self.rb_carpeta.setChecked(True)
        carpeta = s.value("destino_carpeta", "")
        if carpeta:
            self.carpeta_destino = Path(str(carpeta))
        self.chk_indice.setChecked(str(s.value("actualizar_indice", "true")).lower() == "true")
        self._pintar_destino()
        ref = str(s.value("referencia", "") or "")
        if ref:
            if Path(ref).is_file():
                self.cargar_referencia(Path(ref))
            else:
                self.ref_ruta.setText(ref)
                self._mostrar_error_ref("No se encuentra la programación de referencia recordada. Elige otra.")

    def _destino_cambiado(self, *_):
        s = ajustes()
        s.setValue("destino_modo", "carpeta" if self.rb_carpeta.isChecked() else "junto")
        s.setValue("destino_carpeta", str(self.carpeta_destino or ""))
        s.setValue("actualizar_indice", "true" if self.chk_indice.isChecked() else "false")
        self._pintar_destino()
        self._actualizar_botones()

    def _pintar_destino(self) -> None:
        self.btn_carpeta.setEnabled(self.rb_carpeta.isChecked())
        self.lbl_carpeta.setText(str(self.carpeta_destino) if self.carpeta_destino else "Sin carpeta elegida")
        self.lbl_carpeta.setVisible(self.rb_carpeta.isChecked())

    # ------------------------------------------------------------------ referencia
    def elegir_referencia(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Elige la programación de referencia", self._carpeta_inicial(), "Documentos de Word (*.docx)")
        if ruta:
            self.cargar_referencia(Path(ruta))

    def _carpeta_inicial(self) -> str:
        return str(ajustes().value("ultima_carpeta", str(Path.home())))

    def cargar_referencia(self, ruta: Path) -> None:
        self._gen += 1
        gen = self._gen
        self.ref = None
        self.ref_ruta.setText(str(ruta))
        self.ref_resumen.setProperty("rol", "muted")
        self._repintar(self.ref_resumen)
        self.ref_resumen.setText("Leyendo la referencia…")
        s = ajustes()
        s.setValue("referencia", str(ruta))
        s.setValue("ultima_carpeta", str(ruta.parent))
        self._encolar(("ref", gen, ruta), lambda: cargar_motor().Referencia.cargar(ruta))
        self._actualizar_botones()

    def _mostrar_error_ref(self, texto: str) -> None:
        self.ref_resumen.setProperty("rol", "error")
        self._repintar(self.ref_resumen)
        self.ref_resumen.setText(texto)

    @staticmethod
    def _repintar(w: QWidget) -> None:
        w.style().unpolish(w)
        w.style().polish(w)

    # ------------------------------------------------------------------ añadir
    def elegir_programaciones(self) -> None:
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Añadir programaciones", self._carpeta_inicial(), "Documentos de Word (*.docx)")
        if rutas:
            ajustes().setValue("ultima_carpeta", str(Path(rutas[0]).parent))
            self.anadir_rutas([Path(r) for r in rutas])

    def anadir_rutas(self, rutas: list[Path]) -> int:
        """Añade archivos y carpetas; devuelve cuántas programaciones nuevas entran."""
        existentes = {it.ruta.resolve() for it in self.items}
        nuevas = [Item(p) for p in expandir_rutas(rutas) if p.resolve() not in existentes]
        if not nuevas:
            self.estado_lbl.setText("No hay archivos .docx nuevos que añadir.")
            return 0
        for it in nuevas:
            it.resaltar()
        self.items.extend(nuevas)
        self._temporizador_resalte.start()
        self._rehacer_vista(mostrar=nuevas[0])
        if self.ref is not None:
            for it in nuevas:
                self._comprobar(it)
            self.estado_lbl.setText(f"Se han añadido {len(nuevas)} programaciones; las estoy comprobando.")
        else:
            self.estado_lbl.setText(
                f"Se han añadido {len(nuevas)} programaciones. Se comprobarán en cuanto haya una referencia válida.")
        self._actualizar_botones()
        return len(nuevas)

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._soltar_encima(True)

    def dragLeaveEvent(self, e):  # noqa: N802
        self._soltar_encima(False)

    def dropEvent(self, e):  # noqa: N802
        self._soltar_encima(False)
        rutas = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        if rutas:
            e.acceptProposedAction()
            self.anadir_rutas(rutas)

    def _soltar_encima(self, si: bool) -> None:
        self.zona_soltar.setProperty("encima", "true" if si else "false")
        self._repintar(self.zona_soltar)

    # ------------------------------------------------------------------ tareas
    def _encolar(self, clave, funcion) -> None:
        if self._pendientes == 0:
            self._lote_total = self._lote_hechas = 0
        self._pendientes += 1
        self._lote_total += 1
        self._pintar_progreso()
        self.ejecutor.lanzar(clave, funcion)

    def _pintar_progreso(self) -> None:
        self.progreso.setVisible(self._pendientes > 0)
        self.progreso.setMaximum(max(1, self._lote_total))
        self.progreso.setValue(self._lote_hechas)
        self.progreso.setFormat(f"{self._lote_hechas} de {self._lote_total}")

    def ocupada(self) -> bool:
        return self._pendientes > 0

    def _comprobar(self, it: Item) -> None:
        ref, gen = self.ref, self._gen
        self._encolar(("comprobar", gen, it), lambda: cargar_motor().comprobar(ref, it.ruta))

    def _al_terminar_tarea(self, clave, resultado, error) -> None:
        tipo, gen, objeto = clave
        self._pendientes -= 1
        self._lote_hechas += 1
        if tipo == "ref":
            self._referencia_lista(gen, resultado, error)
        elif tipo == "comprobar":
            self._comprobacion_lista(gen, objeto, resultado, error)
        else:
            self._maquetado_listo(objeto, resultado, error)
        self._pintar_progreso()
        if self._pendientes == 0:
            self._temporizador_resalte.start()
        self._actualizar_botones()

    def _referencia_lista(self, gen: int, resultado, error) -> None:
        if gen != self._gen:
            return
        if error is not None:
            self._mostrar_error_ref(error)
            return
        self.ref = resultado
        self.ref_resumen.setProperty("rol", "ok")
        self._repintar(self.ref_resumen)
        self.ref_resumen.setText(str(resultado.resumen))
        for it in self.items:
            if it.estado != MAQUETADA:
                it.estado, it.motivos, it.error = PENDIENTE, [], None
                self._comprobar(it)
        self._rehacer_vista()

    def _comprobacion_lista(self, gen: int, it: Item, diag, error) -> None:
        if gen != self._gen or it not in self.items:
            return
        if error is not None:
            it.estado, it.error, it.motivos = ERROR, error, []
        else:
            it.error = None
            it.motivos = list(diag.motivos)
            it.estado = NO_PROGRAMACION if not diag.es_programacion else (CUMPLE if diag.cumple else NO_CUMPLE)
        it.resaltar()
        self._rehacer_vista()

    def _maquetado_listo(self, it: Item, resultado, error) -> None:
        if it not in self.items:
            return
        salida, res = resultado if error is None else (None, None)
        if error is None and res.ok:
            it.estado, it.salida, it.error = MAQUETADA, salida, None
            it.avisos = list(res.avisos)
            self._ultima_salida = salida
        else:
            it.estado = ERROR
            it.error = error if error is not None else (res.error or "No se pudo maquetar.")
            it.avisos = list(res.avisos) if res is not None else []
        it.resaltar()
        self._rehacer_vista()

    # ------------------------------------------------------------------ maquetar
    def maquetar_no_cumplen(self) -> None:
        self._maquetar([it for it in self.items if it.estado == NO_CUMPLE])

    def maquetar_seleccionadas(self) -> None:
        validas = [it for it in self.seleccionadas() if it.estado != NO_PROGRAMACION]
        if len(validas) < len(self.seleccionadas()):
            self.estado_lbl.setText("Se han saltado las que no son programaciones.")
        self._maquetar(validas)

    def _maquetar(self, lista: list[Item]) -> None:
        if self.ref is None or self.ocupada() or not lista:
            return
        carpeta = None
        if self.rb_carpeta.isChecked():
            if self.carpeta_destino is None:
                self.elegir_carpeta_destino()
            if self.carpeta_destino is None:
                return
            carpeta = self.carpeta_destino
        ref, gen, indice = self.ref, self._gen, self.chk_indice.isChecked()
        for it in lista:
            self._encolar(("maquetar", gen, it), self._tarea_maquetar(ref, it.ruta, carpeta, indice))
        self.estado_lbl.setText(f"Maquetando {len(lista)} programaciones…")

    @staticmethod
    def _tarea_maquetar(ref, entrada: Path, carpeta: Path | None, indice: bool):
        def tarea():
            if carpeta is not None:
                carpeta.mkdir(parents=True, exist_ok=True)
            salida = ruta_salida(entrada, carpeta)
            res = cargar_motor().maquetar(ref, entrada, salida, actualizar_indice=indice)
            return salida, res

        return tarea

    # ------------------------------------------------------------------ destino
    def elegir_carpeta_destino(self) -> None:
        ruta = QFileDialog.getExistingDirectory(self, "Carpeta de destino", self._carpeta_inicial())
        if ruta:
            self.fijar_carpeta_destino(Path(ruta))

    def fijar_carpeta_destino(self, ruta: Path) -> None:
        self.carpeta_destino = ruta
        self.rb_carpeta.setChecked(True)
        self._destino_cambiado()

    def carpeta_destino_actual(self) -> Path | None:
        if self.rb_carpeta.isChecked() and self.carpeta_destino is not None:
            return self.carpeta_destino
        sel = self.seleccionadas()
        if sel:
            return (sel[0].salida or sel[0].ruta).parent
        if self._ultima_salida is not None:
            return self._ultima_salida.parent
        return None

    def abrir_carpeta_destino(self) -> None:
        carpeta = self.carpeta_destino_actual()
        if carpeta is not None:
            self.abrir_ruta(carpeta)

    def abrir_ruta(self, ruta: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta)))

    def _doble_clic(self, idx: QModelIndex) -> None:
        it = self.modelo.filas[idx.row()]
        destino = it.salida if it.salida is not None and it.salida.exists() else it.ruta
        self.abrir_ruta(destino)

    # ------------------------------------------------------------------ listado
    def seleccionadas(self) -> list[Item]:
        return [self.modelo.filas[i.row()] for i in self.tabla.selectionModel().selectedRows()]

    def quitar_seleccionadas(self) -> None:
        if self.ocupada():
            return
        sel = self.seleccionadas()
        if not sel:
            return
        quitar = set(map(id, sel))
        self.items = [it for it in self.items if id(it) not in quitar]
        self.estado_lbl.setText(f"Se han quitado {len(sel)} programaciones de la lista (los archivos no se tocan).")
        self._rehacer_vista()
        self._actualizar_botones()

    def total_paginas(self) -> int:
        return total_paginas(len(self._vista), self.filas_por_pagina())

    def filas_por_pagina(self) -> int:
        return int(self.combo_filas.currentData())

    def ir_a_pagina(self, n: int) -> None:
        self._pagina = max(1, min(n, self.total_paginas()))
        self._pintar_pagina()

    def ordenar_por(self, columna: int) -> None:
        if columna == self._orden_col:
            self._orden_desc = not self._orden_desc
        else:
            self._orden_col, self._orden_desc = columna, False
        self.tabla.horizontalHeader().setSortIndicator(
            columna, Qt.SortOrder.DescendingOrder if self._orden_desc else Qt.SortOrder.AscendingOrder)
        self._rehacer_vista()

    def _filtros_cambiados(self, *_):
        self._pagina = 1
        self._rehacer_vista()

    def _filas_cambiadas(self, *_):
        self._pagina = 1
        self._rehacer_vista()

    def limpiar_filtros(self) -> None:
        self.buscador.blockSignals(True)
        self.filtro_estado.blockSignals(True)
        self.buscador.clear()
        self.filtro_estado.setCurrentIndex(0)
        self.buscador.blockSignals(False)
        self.filtro_estado.blockSignals(False)
        self._pagina = 1
        self._rehacer_vista()

    def _hay_filtros(self) -> bool:
        return bool(self.buscador.text().strip()) or self.filtro_estado.currentIndex() > 0

    def _rehacer_vista(self, mostrar: Item | None = None) -> None:
        q = self.buscador.text().strip().lower()
        estado = self.filtro_estado.currentText()
        vista = []
        for it in self.items:
            if estado != TODOS and it.estado != estado:
                continue
            if q and q not in f"{it.archivo} {it.ruta.parent} {it.estado} {it.resumen}".lower():
                continue
            vista.append(it)
        vista.sort(key=lambda it: it.clave_orden(self._orden_col), reverse=self._orden_desc)
        self._vista = vista
        if mostrar is not None and mostrar in vista:
            self._pagina = vista.index(mostrar) // self.filas_por_pagina() + 1
        self._pagina = max(1, min(self._pagina, self.total_paginas()))
        self._pintar_pagina()

    def _pintar_pagina(self) -> None:
        n = self.filas_por_pagina()
        ini = (self._pagina - 1) * n
        trozo = self._vista[ini:ini + n]
        seleccion = {id(it) for it in self.seleccionadas()}
        self.modelo.poner(trozo)
        sm = self.tabla.selectionModel()
        for fila, it in enumerate(trozo):
            if id(it) in seleccion:
                sm.select(self.modelo.index(fila, 0), sm.SelectionFlag.Select | sm.SelectionFlag.Rows)
        total = len(self._vista)
        texto = "Mostrando 0 de 0" if total == 0 else f"Mostrando {ini + 1}–{ini + len(trozo)} de {total}"
        if self._hay_filtros():
            texto += f" (filtradas de {len(self.items)})"
        self.lbl_rango.setText(texto)

        paginas = self.total_paginas()
        self.btn_primera.setEnabled(self._pagina > 1)
        self.btn_anterior.setEnabled(self._pagina > 1)
        self.btn_siguiente.setEnabled(self._pagina < paginas)
        self.btn_ultima.setEnabled(self._pagina < paginas)
        visibles = paginas_visibles(self._pagina, paginas, NUM_BOTONES)
        for b, num in zip(self.btns_numero, visibles + [None] * NUM_BOTONES, strict=False):
            b.setVisible(num is not None)
            if num is not None:
                b.setText(str(num))
                b.setChecked(num == self._pagina)
        self._seleccion_cambiada()
        self._actualizar_botones()

    # ------------------------------------------------------------------ detalle y botones
    def _seleccion_cambiada(self, *_):
        sel = self.seleccionadas()
        if len(sel) == 1:
            self.detalle.setPlainText(sel[0].detalle())
        elif sel:
            self.detalle.setPlainText(f"{len(sel)} programaciones seleccionadas.")
        else:
            self.detalle.clear()
        self._actualizar_botones()

    def _actualizar_botones(self) -> None:
        libre = not self.ocupada()
        hay_ref = self.ref is not None
        self.btn_maquetar_no.setEnabled(
            libre and hay_ref and any(it.estado == NO_CUMPLE for it in self.items))
        self.btn_maquetar_sel.setEnabled(
            libre and hay_ref and any(it.estado != NO_PROGRAMACION for it in self.seleccionadas()))
        self.btn_quitar.setEnabled(libre and bool(self.seleccionadas()))
        self.btn_limpiar.setEnabled(self._hay_filtros())
        self.btn_abrir_carpeta.setEnabled(self.carpeta_destino_actual() is not None)
        self.btn_ref.setEnabled(libre)

    # ------------------------------------------------------------------ actualizaciones
    def buscar_actualizaciones(self, avisar_si_al_dia: bool = False) -> None:
        from .actualizar import buscar_actualizaciones

        buscar_actualizaciones(self, avisar_si_al_dia, al_encontrar=self.actualizacion_disponible)

    def actualizacion_disponible(self, version: str, url: str, notas: str) -> None:
        """Hay versión nueva: botón fijo y, la primera vez, el diálogo por encima."""
        nueva = getattr(self, "_actualizacion", None) is None or self._actualizacion[0] != version
        self._actualizacion = (version, url, notas)
        self.boton_actualizar.setText(f"↑  Actualizar a {version}")
        self.boton_actualizar.setToolTip("Hay una versión nueva de la aplicación")
        self.boton_actualizar.show()
        if nueva and self.isVisible():
            self._ofrecer_actualizacion()

    def _ofrecer_actualizacion(self) -> None:
        from .actualizar import ofrecer

        if getattr(self, "_actualizacion", None):
            ofrecer(self, *self._actualizacion)

    def mostrar_novedades(self, version: str = __version__) -> None:
        from ..novedades import novedades
        from .actualizar import DialogoNovedades

        DialogoNovedades(version, novedades(version), self).exec()

    def novedades_si_cambio_de_version(self) -> None:
        """Tras actualizar, enseña una vez las novedades; en la primera instalación no dice nada."""
        s = ajustes()
        vista = str(s.value("version_vista", "") or "")
        s.setValue("version_vista", __version__)
        if vista and vista != __version__:
            self.mostrar_novedades()

    def closeEvent(self, e):  # noqa: N802
        if self.ocupada():
            r = QMessageBox.question(
                self, NOMBRE_APP, "Todavía estoy trabajando. ¿Quieres salir de todos modos?")
            if r != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
        self.ejecutor.esperar(3000)
        super().closeEvent(e)
