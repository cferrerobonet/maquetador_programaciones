"""Lectura y escritura del paquete .docx (OOXML): partes, relaciones y tipos de contenido."""

from __future__ import annotations

import posixpath
import zipfile
from copy import deepcopy
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"w": W, "r": R}

T_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
REL_HEADER = T_REL + "header"
REL_FOOTER = T_REL + "footer"
REL_STYLES = T_REL + "styles"
REL_NUMBERING = T_REL + "numbering"
REL_THEME = T_REL + "theme"
REL_FONTTABLE = T_REL + "fontTable"
REL_SETTINGS = T_REL + "settings"

CT_NUMBERING = "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"

TIPOS_POR_EXTENSION = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
    "bmp": "image/bmp", "tif": "image/tiff", "tiff": "image/tiff", "emf": "image/x-emf",
    "wmf": "image/x-wmf", "svg": "image/svg+xml",
    "odttf": "application/vnd.openxmlformats-officedocument.obfuscatedFont",
    "ttf": "application/x-font-ttf", "xml": "application/xml",
    "rels": "application/vnd.openxmlformats-package.relationships+xml",
}


def w(etiqueta: str) -> str:
    return f"{{{W}}}{etiqueta}"


def r(etiqueta: str) -> str:
    return f"{{{R}}}{etiqueta}"


class Paquete:
    """Un .docx en memoria. Las partes XML se analizan bajo demanda y se guardan al final."""

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        with zipfile.ZipFile(self.ruta) as z:
            self.partes: dict[str, bytes] = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}
        self._xml: dict[str, etree._Element] = {}
        self._importadas: dict[tuple[int, str], str] = {}

    # --- partes ---------------------------------------------------------------
    def xml(self, nombre: str) -> etree._Element:
        if nombre not in self._xml:
            self._xml[nombre] = etree.fromstring(self.partes[nombre])
        return self._xml[nombre]

    def poner_xml(self, nombre: str, raiz: etree._Element) -> None:
        self._xml[nombre] = raiz
        self.partes.setdefault(nombre, b"")

    def borrar(self, nombre: str) -> None:
        self.partes.pop(nombre, None)
        self._xml.pop(nombre, None)
        rels = ruta_rels(nombre)
        self.partes.pop(rels, None)
        self._xml.pop(rels, None)
        tipos = self.xml("[Content_Types].xml")
        for o in tipos.findall(f"{{{CT}}}Override"):
            if o.get("PartName") == "/" + nombre:
                tipos.remove(o)

    def guardar(self, ruta: Path) -> None:
        for nombre, raiz in self._xml.items():
            self.partes[nombre] = etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", standalone=True)
        orden = ["[Content_Types].xml"] + [n for n in self.partes if n != "[Content_Types].xml"]
        with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
            for n in orden:
                z.writestr(n, self.partes[n])

    # --- relaciones -----------------------------------------------------------
    def rels(self, parte: str) -> etree._Element:
        nombre = ruta_rels(parte)
        if nombre not in self.partes and nombre not in self._xml:
            self.poner_xml(nombre, etree.Element(f"{{{PKG_REL}}}Relationships", nsmap={None: PKG_REL}))
        return self.xml(nombre)

    def relaciones(self, parte: str) -> list[etree._Element]:
        if ruta_rels(parte) not in self.partes and ruta_rels(parte) not in self._xml:
            return []
        return list(self.rels(parte).findall(f"{{{PKG_REL}}}Relationship"))

    def destino(self, parte: str, rid: str) -> tuple[str, str, bool] | None:
        """(tipo, ruta de la parte o URL, externa) de una relación."""
        for rel in self.relaciones(parte):
            if rel.get("Id") == rid:
                externa = rel.get("TargetMode") == "External"
                objetivo = rel.get("Target") if externa else resolver(parte, rel.get("Target"))
                return rel.get("Type"), objetivo, externa
        return None

    def parte_por_tipo(self, parte: str, tipo: str) -> str | None:
        for rel in self.relaciones(parte):
            if rel.get("Type") == tipo and rel.get("TargetMode") != "External":
                return resolver(parte, rel.get("Target"))
        return None

    def anadir_relacion(self, parte: str, tipo: str, objetivo: str, externa: bool = False) -> str:
        raiz = self.rels(parte)
        usados = {rel.get("Id") for rel in raiz}
        n = 1
        while f"rIdM{n}" in usados:
            n += 1
        rid = f"rIdM{n}"
        rel = etree.SubElement(raiz, f"{{{PKG_REL}}}Relationship")
        rel.set("Id", rid)
        rel.set("Type", tipo)
        if externa:
            rel.set("Target", objetivo)
            rel.set("TargetMode", "External")
        else:
            rel.set("Target", posixpath.relpath(objetivo, posixpath.dirname(parte) or "."))
        return rid

    def quitar_relacion(self, parte: str, rid: str) -> None:
        raiz = self.rels(parte)
        for rel in list(raiz):
            if rel.get("Id") == rid:
                raiz.remove(rel)

    # --- tipos de contenido ---------------------------------------------------
    def tipo_contenido(self, nombre: str) -> str | None:
        tipos = self.xml("[Content_Types].xml")
        for o in tipos.findall(f"{{{CT}}}Override"):
            if o.get("PartName") == "/" + nombre:
                return o.get("ContentType")
        ext = nombre.rsplit(".", 1)[-1].lower()
        for d in tipos.findall(f"{{{CT}}}Default"):
            if d.get("Extension", "").lower() == ext:
                return d.get("ContentType")
        return None

    def registrar_tipo(self, nombre: str, tipo: str | None) -> None:
        tipos = self.xml("[Content_Types].xml")
        ext = nombre.rsplit(".", 1)[-1].lower()
        defecto = {d.get("Extension", "").lower(): d.get("ContentType") for d in tipos.findall(f"{{{CT}}}Default")}
        if tipo is None:
            tipo = TIPOS_POR_EXTENSION.get(ext, "application/octet-stream")
        if defecto.get(ext) == tipo:
            return
        o = etree.SubElement(tipos, f"{{{CT}}}Override")
        o.set("PartName", "/" + nombre)
        o.set("ContentType", tipo)

    # --- importar partes de otro paquete --------------------------------------
    def importar(self, origen: Paquete, nombre: str) -> str:
        """Copia una parte de `origen` (con sus relaciones, recursivamente) y devuelve su nombre nuevo."""
        clave = (id(origen), nombre)
        if clave in self._importadas:
            return self._importadas[clave]
        carpeta, base = posixpath.split(nombre)
        raiz_nombre, punto, ext = base.rpartition(".")
        if not punto:
            raiz_nombre, ext = base, ""
        n = 1
        while True:
            nuevo = posixpath.join(carpeta, f"{raiz_nombre}_ref{n}{'.' + ext if ext else ''}")
            if nuevo not in self.partes:
                break
            n += 1
        self._importadas[clave] = nuevo
        if nombre in origen._xml:
            self.poner_xml(nuevo, deepcopy(origen._xml[nombre]))
        else:
            self.partes[nuevo] = origen.partes[nombre]
        self.registrar_tipo(nuevo, origen.tipo_contenido(nombre))
        relaciones = origen.relaciones(nombre)
        if relaciones:
            nuevas = etree.Element(f"{{{PKG_REL}}}Relationships", nsmap={None: PKG_REL})
            for rel in relaciones:
                copia = deepcopy(rel)
                if rel.get("TargetMode") != "External":
                    destino = resolver(nombre, rel.get("Target"))
                    if destino in origen.partes:
                        nuevo_destino = self.importar(origen, destino)
                        copia.set("Target", posixpath.relpath(nuevo_destino, carpeta or "."))
                nuevas.append(copia)
            self.poner_xml(ruta_rels(nuevo), nuevas)
        return nuevo

    def importar_referencias(self, origen: Paquete, parte_origen: str, elemento: etree._Element, parte_destino: str) -> None:
        """Rehace los r:id/r:embed… de un fragmento copiado de `origen` para que apunten a partes de este paquete."""
        for el in elemento.iter():
            for atributo in list(el.attrib):
                if not atributo.startswith(f"{{{R}}}"):
                    continue
                rid = el.get(atributo)
                info = origen.destino(parte_origen, rid)
                if info is None:
                    del el.attrib[atributo]
                    continue
                tipo, objetivo, externa = info
                if externa:
                    el.set(atributo, self.anadir_relacion(parte_destino, tipo, objetivo, externa=True))
                else:
                    el.set(atributo, self.anadir_relacion(parte_destino, tipo, self.importar(origen, objetivo)))


def ruta_rels(parte: str) -> str:
    carpeta, base = posixpath.split(parte)
    return posixpath.join(carpeta, "_rels", base + ".rels")


def resolver(parte: str, objetivo: str) -> str:
    if objetivo.startswith("/"):
        return objetivo.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(parte), objetivo))


def parte_principal(paq: Paquete) -> str:
    for rel in paq.relaciones(""):
        if rel.get("Type", "").endswith("/officeDocument"):
            return resolver("", rel.get("Target"))
    return "word/document.xml"
