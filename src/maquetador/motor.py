"""Motor: aprende la maquetación de una programación de referencia y la aplica a otras sin tocar su texto.

Partes de un documento: portada (hasta el primer salto de sección anterior al índice o al primer título),
índice (hasta el primer título) y cuerpo. Cada párrafo del índice y del cuerpo tiene un «papel» (título de
nivel n, entrada de índice de nivel n, título del índice, texto, lista, celda, celda de cabecera) y la
referencia da, para cada papel, el formato que se aplica.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .paquete import (
    CT_NUMBERING,
    NS,
    REL_FONTTABLE,
    REL_FOOTER,
    REL_HEADER,
    REL_NUMBERING,
    REL_SETTINGS,
    REL_STYLES,
    REL_THEME,
    Paquete,
    parte_principal,
    r,
    w,
)

# ---------------------------------------------------------------------------------------------
# Resultados públicos


class ErrorMaquetador(Exception):
    """Error con mensaje en castellano para mostrar tal cual."""


@dataclass
class Diagnostico:
    es_programacion: bool
    cumple: bool
    motivos: list[str] = field(default_factory=list)


@dataclass
class Resultado:
    ok: bool
    avisos: list[str] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------------------------
# Utilidades XML

ORDEN_PPR = [
    "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl", "numPr",
    "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
    "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
    "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc",
    "textDirection", "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr",
    "sectPr", "pPrChange",
]
ORDEN_RPR = [
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike", "outline",
    "shadow", "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden", "color", "spacing",
    "w", "kern", "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText",
    "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath",
]
ENFASIS = {"b", "bCs", "i", "iCs", "u", "strike", "dstrike", "vertAlign", "highlight"}
PAPELES_FORZADOS = ("titulo", "toc", "titulo-indice", "celda-cab")


def local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def ordenar(contenedor, orden: list[str]) -> None:
    pos = {n: i for i, n in enumerate(orden)}
    hijos = list(contenedor)
    hijos.sort(key=lambda e: (e.tag.startswith(f"{{{NS['w']}}}") is False, pos.get(local(e), len(orden))))
    for h in hijos:
        contenedor.remove(h)
        contenedor.append(h)


def limpiar_rsid(el):
    for x in el.iter():
        if not isinstance(x.tag, str):
            continue
        for a in list(x.attrib):
            if "rsid" in a:
                del x.attrib[a]
    return el


def firma(el, quitar=("pStyle", "numPr", "sectPr", "tabs", "lang", "noProof", "rPrChange", "pPrChange")) -> str:
    if el is None:
        return ""
    e = limpiar_rsid(deepcopy(el))
    for nombre in quitar:
        for x in e.findall(f".//w:{nombre}", NS):
            x.getparent().remove(x)
    return etree.tostring(e, encoding="unicode")


def texto(el) -> str:
    """Texto de un párrafo (solo sus propias ejecuciones, no los cuadros de texto anidados)."""
    partes = []
    for t in el.iter(w("t"), w("tab"), w("br")):
        if t.xpath("ancestor::w:txbxContent", namespaces=NS) and not el.xpath("ancestor::w:txbxContent", namespaces=NS):
            continue
        if local(t) == "t":
            partes.append(t.text or "")
        else:
            partes.append(" ")
    return "".join(partes)


def normal(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


RE_NUMERO = re.compile(r"^\s*(\d{1,2}(?:\s*\.\s*\d{1,2})*)\s*(\.-|\.\s*-|-|\.|\))?\s+(?=\S)")


def prefijo_numerico(s: str):
    m = RE_NUMERO.match(s)
    if not m:
        return None
    cadena = re.sub(r"\s", "", m.group(1))
    return m, cadena, (m.group(2) or "").replace(" ", "")


def parrafos_propios(raiz):
    return [p for p in raiz.iter(w("p")) if not p.xpath("ancestor::w:txbxContent", namespaces=NS)]


def ejecuciones(p):
    return [x for x in p.iter(w("r")) if x.xpath("ancestor::w:p[1]", namespaces=NS)[0] is p]


# ---------------------------------------------------------------------------------------------
# Estilos


class Estilos:
    def __init__(self, raiz):
        self.raiz = raiz
        self.por_id = {s.get(w("styleId")): s for s in raiz.findall("w:style", NS)}
        self.defecto_parrafo = next(
            (s.get(w("styleId")) for s in raiz.findall("w:style", NS)
             if s.get(w("type")) == "paragraph" and s.get(w("default")) in ("1", "true")), "Normal")

    def nombre(self, sid):
        s = self.por_id.get(sid)
        n = s.find("w:name", NS) if s is not None else None
        return (n.get(w("val")) if n is not None else sid or "").lower()

    def cadena(self, sid):
        vistos = []
        while sid and sid in self.por_id and sid not in vistos:
            vistos.append(sid)
            b = self.por_id[sid].find("w:basedOn", NS)
            sid = b.get(w("val")) if b is not None else None
        return [self.por_id[s] for s in vistos]

    def nivel_titulo(self, sid):
        nombre = self.nombre(sid)
        m = re.fullmatch(r"heading (\d)", nombre)
        if m:
            return int(m.group(1))
        for s in self.cadena(sid):
            o = s.find("w:pPr/w:outlineLvl", NS)
            if o is not None and o.get(w("val")) not in (None, "9"):
                return int(o.get(w("val"))) + 1
        return None

    def nivel_indice(self, sid):
        m = re.fullmatch(r"toc (\d)", self.nombre(sid))
        return int(m.group(1)) if m else None

    def numerado(self, sid):
        for s in self.cadena(sid):
            n = s.find("w:pPr/w:numPr/w:numId", NS)
            if n is not None:
                return n.get(w("val")) != "0"
        return False

    def es_lista(self, sid):
        return self.nombre(sid) == "list paragraph" or self.numerado(sid) and self.nivel_titulo(sid) is None

    def propiedad_r(self, sid, nombre):
        for s in self.cadena(sid):
            x = s.find(f"w:rPr/w:{nombre}", NS)
            if x is not None:
                return x
        return None


def estilo_de(p, estilos: Estilos):
    s = p.find("w:pPr/w:pStyle", NS)
    return s.get(w("val")) if s is not None else estilos.defecto_parrafo


# ---------------------------------------------------------------------------------------------
# Estructura del documento


@dataclass
class Estructura:
    bloques: list
    fin_portada: int          # índice del último bloque de la portada (-1 si no hay)
    inicio_cuerpo: int        # índice del primer título del cuerpo
    titulos: list             # [(p, nivel)]


def es_titulo(p, estilos):
    if p.getparent().tag != w("body"):
        return None
    nivel = estilos.nivel_titulo(estilo_de(p, estilos))
    if nivel is None:
        o = p.find("w:pPr/w:outlineLvl", NS)
        if o is not None and o.get(w("val")) != "9":
            nivel = int(o.get(w("val"))) + 1
    if nivel is not None and normal(texto(p)):
        return nivel
    return None


def estructura(doc, estilos: Estilos, conocidas: set | None = None) -> Estructura:
    cuerpo = doc.find("w:body", NS)
    bloques = [b for b in cuerpo if local(b) in ("p", "tbl", "sdt")]
    primer_titulo = next((i for i, b in enumerate(bloques) if local(b) == "p" and es_titulo(b, estilos)), len(bloques))
    primer_indice = next((i for i, b in enumerate(bloques)
                          if local(b) == "p" and estilos.nivel_indice(estilo_de(b, estilos))), primer_titulo)
    if any(local(b) == "sdt" and b.find(".//w:docPartGallery[@w:val='Table of Contents']", NS) is not None
           for b in bloques[:primer_titulo]):
        primer_indice = min(primer_indice, next(i for i, b in enumerate(bloques) if local(b) == "sdt"))
    limite = min(primer_indice, primer_titulo)
    fin_portada = -1
    for i, b in enumerate(bloques[:limite]):
        if local(b) == "p" and b.find("w:pPr/w:sectPr", NS) is not None:
            fin_portada = i
            break
    if fin_portada < 0 and conocidas and limite > 0:
        # Portada sin salto de sección: lo que hay antes del título del índice, si tiene los campos de portada.
        k = limite
        while k > 0 and local(bloques[k - 1]) == "p" and not normal(texto(bloques[k - 1])):
            k -= 1
        if k > 0 and local(bloques[k - 1]) == "p" and len(normal(texto(bloques[k - 1]))) <= 40 and limite == primer_indice:
            k -= 1
        if k > 0 and len(campos_portada(bloques[:k], conocidas)) >= 2:
            fin_portada = k - 1
    titulos = [(b, es_titulo(b, estilos)) for b in bloques[primer_titulo:] if local(b) == "p" and es_titulo(b, estilos)]
    return Estructura(bloques, fin_portada, primer_titulo, titulos)


def filas_cabecera(tbl, estilos: Estilos):
    filas = tbl.findall("w:tr", NS)
    if not filas:
        return set()
    marcadas = {f for f in filas if f.find("w:trPr/w:tblHeader", NS) is not None}
    if marcadas:
        return marcadas
    primera = filas[0]
    celdas = primera.findall("w:tc", NS)
    if len(filas) > 1 and celdas:
        def destacada(tc):
            if tc.find("w:tcPr/w:shd", NS) is not None and tc.find("w:tcPr/w:shd", NS).get(w("fill"), "auto") not in ("auto", "FFFFFF"):
                return True
            runs = [x for x in tc.iter(w("r")) if x.find("w:t", NS) is not None and (x.find("w:t", NS).text or "").strip()]
            return bool(runs) and all(x.find("w:rPr/w:b", NS) is not None and x.find("w:rPr/w:b", NS).get(w("val"), "1") not in ("0", "false") for x in runs)
        if all(destacada(tc) for tc in celdas):
            return {primera}
    return set()


def papel(p, estilos: Estilos, en_indice: bool, cabeceras: set, rangos: dict) -> str:
    sid = estilo_de(p, estilos)
    tc = next(iter(p.xpath("ancestor::w:tc[1]", namespaces=NS)), None)
    if tc is not None:
        tr = tc.getparent()
        return "celda-cab" if tr in cabeceras else "celda"
    nivel = estilos.nivel_indice(sid)
    if nivel:
        return f"toc:{rangos['toc'].get(nivel, 0)}"
    nivel = es_titulo(p, estilos)
    if nivel and not en_indice:
        return f"titulo:{rangos['titulo'].get(nivel, 0)}"
    if en_indice and normal(texto(p)):
        return "titulo-indice"
    if p.find("w:pPr/w:numPr", NS) is not None or estilos.es_lista(sid):
        return "lista"
    return "texto"


def rangos_de(estilos, est: Estructura, bloques_indice):
    nt = sorted({n for _, n in est.titulos})
    ni = sorted({estilos.nivel_indice(estilo_de(p, estilos)) for b in bloques_indice for p in parrafos_propios(b)} - {None})
    return {"titulo": {n: i for i, n in enumerate(nt)}, "toc": {n: i for i, n in enumerate(ni)}}


def recorrer(est: Estructura, estilos: Estilos):
    """Genera (párrafo, papel) del índice y del cuerpo."""
    indice = est.bloques[est.fin_portada + 1: est.inicio_cuerpo]
    cuerpo = est.bloques[est.inicio_cuerpo:]
    rangos = rangos_de(estilos, est, indice)
    cabeceras = set()
    for b in indice + cuerpo:
        for tbl in b.iter(w("tbl")):
            cabeceras |= filas_cabecera(tbl, estilos)
    for grupo, en_indice in ((indice, True), (cuerpo, False)):
        for b in grupo:
            for p in parrafos_propios(b):
                yield p, papel(p, estilos, en_indice, cabeceras, rangos)


# ---------------------------------------------------------------------------------------------
# Portada: pares etiqueta → valor

PALABRAS_VACIAS = {"n", "no", "num", "numero", "de", "del", "el", "la", "los", "las", "y", "o"}


def clave_etiqueta(s: str, conocidas: set | None = None) -> str | None:
    """Clave de una etiqueta de portada («Familia profesional:» → «fami»). Sin dos puntos, solo si es conocida."""
    s = normal(s)
    if not s or len(s) > 40:
        return None
    palabras = [x for x in re.split(r"[^a-z0-9]+", sin_acentos(s.lower())) if x and x not in PALABRAS_VACIAS]
    if not palabras or palabras[0].isdigit():
        return None
    clave = palabras[0][:4]
    if s.endswith(":") or (conocidas and clave in conocidas and len(palabras) <= 4 and not re.search(r"\d", s)):
        return clave
    return None


def campos_portada(bloques, conocidas: set | None = None) -> list[tuple[str, object, list]]:
    """[(clave, párrafo de etiqueta, [párrafos de valor])] en orden."""
    campos = []
    for b in bloques:
        if local(b) != "tbl":
            continue
        for tr in b.iter(w("tr")):
            celdas = tr.findall("w:tc", NS)
            saltar = set()
            for i, tc in enumerate(celdas):
                if i in saltar:
                    continue
                ps = tc.findall("w:p", NS)
                llenos = [p for p in ps if normal(texto(p))]
                if not llenos:
                    continue
                clave = clave_etiqueta(texto(llenos[0]), conocidas)
                if not clave:
                    continue
                valores = llenos[1:]
                if not valores and i + 1 < len(celdas):
                    siguiente = celdas[i + 1].findall("w:p", NS)
                    valores = [p for p in siguiente if normal(texto(p))] or siguiente[:1]
                    saltar.add(i + 1)
                campos.append((clave, llenos[0], valores))
    return campos


def escribir_texto(p, valor: str) -> None:
    """Deja el párrafo con un único texto, conservando el formato de su primera ejecución con texto."""
    runs = ejecuciones(p)
    modelo = next((x for x in runs if x.find("w:t", NS) is not None), runs[0] if runs else None)
    rpr = deepcopy(modelo.find("w:rPr", NS)) if modelo is not None and modelo.find("w:rPr", NS) is not None else None
    for x in runs:
        x.getparent().remove(x)
    for h in list(p):
        if local(h) in ("hyperlink", "fldSimple", "smartTag"):
            p.remove(h)
    nueva = etree.SubElement(p, w("r"))
    if rpr is not None:
        nueva.append(rpr)
    t = etree.SubElement(nueva, w("t"))
    t.text = valor
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


# ---------------------------------------------------------------------------------------------
# Referencia


@dataclass
class Perfil:
    ppr: object
    rpr: object
    estilo: str | None


class Referencia:
    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        try:
            self.paq = Paquete(self.ruta)
        except Exception as e:  # noqa: BLE001
            raise ErrorMaquetador(f"No se puede abrir «{self.ruta.name}»: no es un .docx válido.") from e
        self.parte = parte_principal(self.paq)
        self.doc = self.paq.xml(self.parte)
        p_estilos = self.paq.parte_por_tipo(self.parte, REL_STYLES)
        if not p_estilos:
            raise ErrorMaquetador("La referencia no tiene estilos.")
        self.parte_estilos = p_estilos
        self.estilos = Estilos(self.paq.xml(p_estilos))
        self.est = estructura(self.doc, self.estilos)
        if not self.est.titulos:
            raise ErrorMaquetador("La referencia no tiene títulos con estilo de título: no se puede usar como modelo.")
        self._aprender()

    @classmethod
    def cargar(cls, ruta) -> Referencia:
        return cls(Path(ruta))

    # --- aprendizaje ----------------------------------------------------------
    def _aprender(self):
        ppr, rpr, sty = {}, {}, {}
        for p, pap in recorrer(self.est, self.estilos):
            ppr.setdefault(pap, Counter())[firma(p.find("w:pPr", NS))] += 1
            sty.setdefault(pap, Counter())[estilo_de(p, self.estilos)] += 1
            for x in ejecuciones(p):
                if normal("".join(t.text or "" for t in x.findall("w:t", NS))):
                    grupo = rpr.setdefault(pap, {}).setdefault(tipografia(x, p, self.estilos, self.paq), Counter())
                    grupo[firma(x.find("w:rPr", NS), quitar=("rStyle", "lang", "noProof", "rPrChange"))] += 1
        self.perfiles: dict[str, Perfil] = {}
        for pap in ppr:
            fp = ppr[pap].most_common(1)[0][0]
            # Primero la tipografía real dominante (fuente y tamaño) y, dentro de ella, la variante más común.
            grupos = rpr.get(pap) or {None: Counter({"": 1})}
            fr = max(grupos.values(), key=lambda c: sum(c.values())).most_common(1)[0][0]
            self.perfiles[pap] = Perfil(etree.fromstring(fp) if fp else None, etree.fromstring(fr) if fr else None,
                                        sty[pap].most_common(1)[0][0])
        # Viñeta de las listas: la definición de numeración de viñetas más usada en la referencia.
        vinetas = Counter()
        for p, pap in recorrer(self.est, self.estilos):
            n = p.find("w:pPr/w:numPr", NS)
            if pap == "lista" and n is not None and n.find("w:numId", NS) is not None:
                nid = n.find("w:numId", NS).get(w("val"))
                ilvl = n.find("w:ilvl", NS).get(w("val")) if n.find("w:ilvl", NS) is not None else "0"
                if formato_nivel(self.paq, self.parte, nid, ilvl) == "bullet":
                    vinetas[nid] += 1
        self.vineta = vinetas.most_common(1)[0][0] if vinetas else None
        self.estilo_titulo = {int(k.split(":")[1]): v.estilo for k, v in self.perfiles.items() if k.startswith("titulo:")}
        self.estilo_toc = {int(k.split(":")[1]): v.estilo for k, v in self.perfiles.items() if k.startswith("toc:")}
        # Numeración de los títulos: automática (estilo) o escrita a mano, con su separador por nivel.
        sep = {}
        manual = 0
        for p, nivel in self.est.titulos:
            pref = prefijo_numerico(texto(p))
            if pref:
                manual += 1
                rango = sorted({n for _, n in self.est.titulos}).index(nivel)
                sep.setdefault(rango, Counter())[pref[2]] += 1
        self.titulos_a_mano = manual >= len(self.est.titulos) / 2
        self.separador = {k: v.most_common(1)[0][0] for k, v in sep.items()}
        # Tablas del cuerpo.
        tablas = [t for b in self.est.bloques[self.est.inicio_cuerpo:] for t in b.iter(w("tbl"))]
        self.n_tablas = len(tablas)
        firmas = Counter(firma(t.find("w:tblPr", NS)) for t in tablas)
        self.tblpr = etree.fromstring(firmas.most_common(1)[0][0]) if firmas and firmas.most_common(1)[0][0] else None
        cab = Counter()
        for t in tablas:
            for tr in t.findall("w:tr", NS):
                if tr in filas_cabecera(t, self.estilos):
                    for tc in tr.findall("w:tc", NS):
                        cab[firma(tc.find("w:tcPr/w:shd", NS))] += 1
        self.shd_cabecera = etree.fromstring(cab.most_common(1)[0][0]) if cab and cab.most_common(1)[0][0] else None
        # Secciones y portada.
        self.secciones = [p.find("w:pPr/w:sectPr", NS) for p in self.doc.iter(w("p")) if p.find("w:pPr/w:sectPr", NS) is not None]
        self.secciones.append(self.doc.find("w:body/w:sectPr", NS))
        self.portada = self.est.bloques[: self.est.fin_portada + 1] if self.est.fin_portada >= 0 else []
        self.campos = campos_portada(self.portada)
        self.claves = {c for c, _, _ in self.campos}
        self.huellas = self._huellas(self.paq, self.doc, self.estilos, self.est, self.claves)

    @property
    def resumen(self) -> str:
        partes = [f"{len(self.est.titulos)} títulos", f"{self.n_tablas} tablas"]
        partes.append(f"portada con {len(self.campos)} campos" if self.portada else "sin portada separada")
        return " · ".join(partes)

    # --- huellas para comprobar si un documento cumple -------------------------
    @staticmethod
    def _huellas(paq: Paquete, doc, estilos: Estilos, est: Estructura, conocidas: set | None = None) -> dict:
        h = {}
        final = doc.find("w:body/w:sectPr", NS)
        h["pagina"] = firma(final.find("w:pgSz", NS)) + firma(final.find("w:pgMar", NS)) if final is not None else ""
        cab = []
        parte = parte_principal(paq)
        secciones = [p.find("w:pPr/w:sectPr", NS) for p in doc.iter(w("p")) if p.find("w:pPr/w:sectPr", NS) is not None]
        secciones.append(final)
        heredadas = {}
        for sec in reversed([x for x in secciones if x is not None]):
            for ref in sec.findall("w:headerReference", NS) + sec.findall("w:footerReference", NS):
                heredadas.setdefault((local(ref), ref.get(w("type"))), ref)
        if heredadas:
            for ref in heredadas.values():
                info = paq.destino(parte, ref.get(r("id")))
                if info and info[1] in paq.partes:
                    x = paq.xml(info[1])
                    cab.append((ref.get(w("type")), normal(texto(x)), len(x.findall(".//w:drawing", NS)) + len(x.findall(".//w:pict", NS))))
        h["cabecera"] = sorted(cab)
        portada = est.bloques[: est.fin_portada + 1] if est.fin_portada >= 0 else []
        h["portada"] = [k for k, _, _ in campos_portada(portada, conocidas)]
        h["portada_con_salto"] = bool(portada) and portada[-1].find("w:pPr/w:sectPr", NS) is not None
        h["titulos"] = {}
        for p, n in est.titulos:
            h["titulos"].setdefault(n, Counter())[estilo_de(p, estilos)] += 1
        h["titulos_numerados"] = sum(1 for p, _ in est.titulos if prefijo_numerico(texto(p))) >= len(est.titulos) / 2 if est.titulos else False
        tipos = {}
        for p, pap in recorrer(est, estilos):
            for x in ejecuciones(p):
                if normal("".join(t.text or "" for t in x.findall("w:t", NS))):
                    tipos.setdefault(pap.split(":")[0], Counter())[tipografia(x, p, estilos, paq)] += 1
        h["tipografia"] = {k: v.most_common(1)[0][0] for k, v in tipos.items()}
        return h


def tema_fuentes(paq: Paquete) -> dict:
    parte = paq.parte_por_tipo(parte_principal(paq), REL_THEME)
    res = {}
    if parte and parte in paq.partes:
        a = "http://schemas.openxmlformats.org/drawingml/2006/main"
        x = paq.xml(parte)
        for clave, ruta in (("minor", "minorFont"), ("major", "majorFont")):
            lat = x.find(f".//{{{a}}}{ruta}/{{{a}}}latin")
            if lat is not None:
                res[clave] = lat.get("typeface")
    return res


def tipografia(run, p, estilos: Estilos, paq: Paquete) -> tuple:
    """(fuente, tamaño en pt) efectivos de una ejecución."""
    def buscar(nombre):
        x = run.find(f"w:rPr/w:{nombre}", NS)
        if x is not None:
            return x
        rs = run.find("w:rPr/w:rStyle", NS)
        if rs is not None:
            x = estilos.propiedad_r(rs.get(w("val")), nombre)
            if x is not None:
                return x
        x = estilos.propiedad_r(estilo_de(p, estilos), nombre)
        if x is not None:
            return x
        return estilos.raiz.find(f"w:docDefaults/w:rPrDefault/w:rPr/w:{nombre}", NS)

    f = buscar("rFonts")
    fuente = "?"
    if f is not None:
        fuente = f.get(w("ascii")) or f.get(w("hAnsi"))
        if not fuente:
            tema = f.get(w("asciiTheme")) or f.get(w("hAnsiTheme")) or ""
            fuente = tema_fuentes(paq).get("major" if tema.startswith("major") else "minor", tema)
    s = buscar("sz")
    tam = int(s.get(w("val"))) / 2 if s is not None and s.get(w("val"), "").isdigit() else 10
    return fuente, tam


# ---------------------------------------------------------------------------------------------
# Comprobación


def _abrir(ruta: Path):
    try:
        paq = Paquete(ruta)
    except Exception as e:  # noqa: BLE001
        raise ErrorMaquetador("No es un .docx válido o está dañado.") from e
    parte = parte_principal(paq)
    doc = paq.xml(parte)
    p_estilos = paq.parte_por_tipo(parte, REL_STYLES)
    estilos = Estilos(paq.xml(p_estilos)) if p_estilos else Estilos(etree.Element(w("styles")))
    return paq, parte, doc, estilos


def clave_titulo(s: str) -> str:
    pref = prefijo_numerico(s)
    if pref:
        s = s[pref[0].end():]
    return re.sub(r"[^a-z0-9 ]", "", sin_acentos(normal(s).lower())).strip()


def comprobar(ref: Referencia, ruta) -> Diagnostico:
    ruta = Path(ruta)
    paq, parte, doc, estilos = _abrir(ruta)
    est = estructura(doc, estilos, ref.claves)
    claves_ref = {clave_titulo(texto(p)) for p, _ in ref.est.titulos}
    claves = {clave_titulo(texto(p)) for p, _ in est.titulos}
    # Programaciones antiguas con títulos sin estilo: se buscan los títulos de la referencia en todo el texto.
    if len(claves & claves_ref) < max(2, len(claves_ref) // 3):
        todos = {clave_titulo(texto(p)) for p in parrafos_propios(doc.find("w:body", NS))}
        coincidencias = len(todos & claves_ref)
        if coincidencias < max(2, len(claves_ref) // 3):
            return Diagnostico(False, False, ["No tiene los apartados de la referencia: no parece una programación."])
        return Diagnostico(True, False, ["Los títulos no usan estilos de título: hay que revisarla a mano en Word."])
    h = Referencia._huellas(paq, doc, estilos, est, ref.claves)
    hr = ref.huellas
    motivos = []
    if h["pagina"] != hr["pagina"]:
        motivos.append("Tamaño de página o márgenes distintos.")
    if h["cabecera"] != hr["cabecera"]:
        motivos.append("Cabecera o pie de página distintos.")
    if hr["portada"] and h["portada"] != hr["portada"]:
        motivos.append("Portada con otra estructura.")
    ranks_ref = sorted(hr["titulos"])
    ranks = sorted(h["titulos"])
    for i, n in enumerate(ranks):
        if i < len(ranks_ref) and h["titulos"][n].most_common(1)[0][0] != hr["titulos"][ranks_ref[i]].most_common(1)[0][0]:
            motivos.append("Los títulos usan otros niveles de estilo.")
            break
    if h["titulos_numerados"] != hr["titulos_numerados"]:
        motivos.append("Numeración de los títulos distinta (automática o escrita a mano).")
    nombres = {"titulo": "títulos", "texto": "texto", "lista": "listas", "celda": "tablas", "celda-cab": "cabeceras de tabla", "toc": "índice"}
    for pap, nombre in nombres.items():
        a, b = h["tipografia"].get(pap), hr["tipografia"].get(pap)
        if a and b and (a[0] != b[0] or abs(a[1] - b[1]) > 0.1):
            motivos.append(f"Tipografía de {nombre}: {a[0]} {a[1]:g} pt en vez de {b[0]} {b[1]:g} pt.")
    if ref.portada and not h["portada_con_salto"]:
        motivos.append("Sin portada separada por un salto de sección.")
    return Diagnostico(True, not motivos, motivos)


# ---------------------------------------------------------------------------------------------
# Maquetación


def _huella_contenido(doc, estilos, conocidas=None):
    est = estructura(doc, estilos, conocidas)
    lineas = []
    for b in est.bloques[est.fin_portada + 1:]:
        for p in parrafos_propios(b):
            t = normal(texto(p))
            if es_titulo(p, estilos) and prefijo_numerico(t):
                t = t[prefijo_numerico(t)[0].end():]
            if t:
                lineas.append(t)
    return lineas, len(doc.findall(".//w:drawing", NS)), len(doc.findall(".//w:tbl", NS))


def maquetar(ref: Referencia, entrada, salida, actualizar_indice: bool = True) -> Resultado:
    entrada, salida = Path(entrada), Path(salida)
    try:
        return _maquetar(ref, entrada, salida, actualizar_indice)
    except ErrorMaquetador as e:
        return Resultado(False, [], str(e))
    except Exception as e:  # noqa: BLE001
        return Resultado(False, [], f"Error inesperado: {type(e).__name__}: {e}")


def _maquetar(ref: Referencia, entrada: Path, salida: Path, actualizar_indice: bool) -> Resultado:
    avisos: list[str] = []
    paq, parte, doc, estilos_doc = _abrir(entrada)
    est = estructura(doc, estilos_doc, ref.claves)
    if not est.titulos:
        raise ErrorMaquetador("Los títulos no usan estilos de título: no se puede maquetar sin riesgo.")
    antes_lineas, antes_dibujos, antes_tablas = _huella_contenido(doc, estilos_doc, ref.claves)
    cuerpo = doc.find("w:body", NS)

    # 1. Párrafos del índice y del cuerpo.
    rangos_t = sorted({n for _, n in est.titulos})
    a_mano = sum(1 for p, _ in est.titulos if prefijo_numerico(texto(p))) >= len(est.titulos) / 2
    contadores = [0] * 10
    trabajo = list(recorrer(est, estilos_doc))
    _vinetas(paq, parte, ref, [p for p, pap in trabajo if pap == "lista"])
    for p, pap in trabajo:
        clase, _, rango = pap.partition(":")
        if clase == "titulo":
            rango = int(rango)
            _numerar(p, rango, estilos_doc, ref, a_mano, contadores)
            _aplicar_parrafo(p, pap, ref, estilos_doc, nuevo_estilo=ref.estilo_titulo.get(rango, ref.estilo_titulo[max(ref.estilo_titulo)]))
        elif clase == "toc":
            r_ = int(rango)
            sty = ref.estilo_toc.get(r_, ref.estilo_toc[max(ref.estilo_toc)]) if ref.estilo_toc else None
            _aplicar_parrafo(p, pap, ref, estilos_doc, nuevo_estilo=sty)
        else:
            _aplicar_parrafo(p, pap, ref, estilos_doc)
    if len(rangos_t) > len(ref.estilo_titulo):
        avisos.append("Tiene más niveles de título que la referencia: los sobrantes toman el último nivel.")

    # 2. Tablas del índice y del cuerpo.
    texto_util = _ancho_util(ref.secciones[-1])
    for b in est.bloques[est.fin_portada + 1:]:
        for tbl in b.iter(w("tbl")):
            _aplicar_tabla(tbl, ref, estilos_doc, texto_util)

    # 3. Portada (las cabeceras y pies del documento se quitan antes de importar nada de la referencia).
    _quitar_cabeceras(paq, parte)
    if ref.portada and est.fin_portada >= 0:
        _portada(paq, parte, cuerpo, est, ref, avisos)
    elif ref.portada:
        avisos.append("No tiene portada separada por un salto de sección: se deja como está.")

    # 4. Paquete: estilos, numeración, tema, fuentes, ajustes, cabeceras, pies y secciones.
    _estilos(paq, parte, doc, ref)
    _secciones(paq, parte, doc, ref)
    _tema_y_fuentes(paq, parte, ref)
    _ajustes(paq, parte, ref, actualizar_indice)

    # 5. Verificación: el texto no puede cambiar.
    estilos_nuevos = Estilos(paq.xml(paq.parte_por_tipo(parte, REL_STYLES)))
    despues_lineas, despues_dibujos, despues_tablas = _huella_contenido(doc, estilos_nuevos, ref.claves)
    if despues_lineas != antes_lineas:
        dif = next((i for i, (a, b) in enumerate(zip(antes_lineas, despues_lineas, strict=False)) if a != b), min(len(antes_lineas), len(despues_lineas)))
        muestra = antes_lineas[dif][:60] if dif < len(antes_lineas) else "(final)"
        raise ErrorMaquetador(f"Comprobación de seguridad: el texto cambiaría cerca de «{muestra}». No se guarda.")
    if despues_dibujos < antes_dibujos - _dibujos_portada(est) or despues_tablas < antes_tablas - _tablas_portada(est):
        raise ErrorMaquetador("Comprobación de seguridad: se perderían imágenes o tablas. No se guarda.")
    salida.parent.mkdir(parents=True, exist_ok=True)
    paq.guardar(salida)
    Paquete(salida).xml(parte)  # se puede volver a abrir
    return Resultado(True, avisos, None)


def _dibujos_portada(est):
    return sum(len(b.findall(".//w:drawing", NS)) for b in est.bloques[: est.fin_portada + 1])


def _tablas_portada(est):
    return sum((1 if local(b) == "tbl" else 0) + len(b.findall(".//w:tbl", NS)) for b in est.bloques[: est.fin_portada + 1])


# --- párrafos ----------------------------------------------------------------------------------


def formato_nivel(paq: Paquete, parte, num_id, ilvl) -> str | None:
    """numFmt de un nivel de una lista («bullet», «decimal»…)."""
    p_num = paq.parte_por_tipo(parte, REL_NUMBERING)
    if not p_num or num_id in (None, "0"):
        return None
    raiz = paq.xml(p_num)
    num = next((n for n in raiz.findall("w:num", NS) if n.get(w("numId")) == num_id), None)
    if num is None:
        return None
    for o in num.findall("w:lvlOverride", NS):
        if o.get(w("ilvl")) == ilvl:
            f = o.find("w:lvl/w:numFmt", NS)
            if f is not None:
                return f.get(w("val"))
    aid = num.find("w:abstractNumId", NS).get(w("val"))
    a = next((x for x in raiz.findall("w:abstractNum", NS) if x.get(w("abstractNumId")) == aid), None)
    if a is None:
        return None
    lvl = next((x for x in a.findall("w:lvl", NS) if x.get(w("ilvl")) == ilvl), None)
    f = lvl.find("w:numFmt", NS) if lvl is not None else None
    return f.get(w("val")) if f is not None else None


def _vinetas(paq: Paquete, parte, ref: Referencia, parrafos):
    """Las listas de viñetas pasan a usar la viñeta de la referencia (las numeradas no se tocan)."""
    if ref.vineta is None:
        return
    cambiar = []
    for p in parrafos:
        n = p.find("w:pPr/w:numPr", NS)
        if n is None or n.find("w:numId", NS) is None:
            continue
        ilvl = n.find("w:ilvl", NS).get(w("val")) if n.find("w:ilvl", NS) is not None else "0"
        if formato_nivel(paq, parte, n.find("w:numId", NS).get(w("val")), ilvl) == "bullet":
            cambiar.append(n.find("w:numId", NS))
    if not cambiar:
        return
    nuevo = _importar_numeracion(paq, parte, ref, {ref.vineta}).get(ref.vineta)
    if nuevo:
        for x in cambiar:
            x.set(w("val"), nuevo)


def _numerar(p, rango, estilos_doc, ref: Referencia, a_mano: bool, contadores):
    t = texto(p)
    pref = prefijo_numerico(t)
    np_ = p.find("w:pPr/w:numPr/w:numId", NS)
    automatico = (np_.get(w("val")) != "0") if np_ is not None else estilos_doc.numerado(estilo_de(p, estilos_doc))
    for i in range(rango + 1, len(contadores)):
        contadores[i] = 0
    contadores[rango] += 1
    numero = ".".join(str(c) for c in contadores[: rango + 1]) if all(contadores[: rango + 1]) else None
    if ref.titulos_a_mano:
        sep = ref.separador.get(rango, ref.separador.get(max(ref.separador) if ref.separador else 0, "."))
        if pref:
            _quitar_inicio(p, pref[0].end())
            _poner_inicio(p, f"{pref[1]}{sep} ")
        elif automatico and not a_mano and numero:
            _poner_inicio(p, f"{numero}{sep} ")
        np_ = p.find("w:pPr/w:numPr", NS)
        if np_ is not None:
            np_.getparent().remove(np_)
    elif pref:
        _quitar_inicio(p, pref[0].end())


def _quitar_inicio(p, n):
    # Recorre lo mismo que texto(): w:t, w:tab y w:br (estos dos cuentan como un carácter).
    for t in [x for x in p.iter(w("t"), w("tab"), w("br")) if not x.xpath("ancestor::w:txbxContent", namespaces=NS)]:
        if n <= 0:
            break
        if local(t) != "t":
            t.getparent().remove(t)
            n -= 1
            continue
        s = t.text or ""
        quita = min(n, len(s))
        t.text = s[quita:]
        n -= quita


def _poner_inicio(p, s):
    t = next((x for x in p.iter(w("t")) if not x.xpath("ancestor::w:txbxContent", namespaces=NS)), None)
    if t is None:
        return
    t.text = s + (t.text or "")
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def _aplicar_parrafo(p, pap, ref: Referencia, estilos_doc: Estilos, nuevo_estilo=None):
    perfil = ref.perfiles.get(pap) or ref.perfiles.get(pap.split(":")[0] + ":0") or ref.perfiles.get("texto")
    if perfil is None:
        return
    viejo = p.find("w:pPr", NS)
    nuevo = deepcopy(perfil.ppr) if perfil.ppr is not None else etree.Element(w("pPr"))
    nuevo.tag = w("pPr")
    conservar = ["numPr", "sectPr", "pageBreakBefore", "framePr"]
    if pap.startswith("celda"):
        conservar.append("jc")
    if viejo is not None:
        for nombre in conservar:
            x = viejo.find(f"w:{nombre}", NS)
            if x is not None:
                if nombre == "numPr" and pap.startswith(("titulo", "toc")):
                    continue
                y = nuevo.find(f"w:{nombre}", NS)
                if y is not None:
                    nuevo.remove(y)
                nuevo.append(deepcopy(x))
        p.remove(viejo)
    estilo = nuevo_estilo or perfil.estilo
    if estilo and estilo != ref.estilos.defecto_parrafo:
        s = etree.SubElement(nuevo, w("pStyle"))
        s.set(w("val"), estilo)
    ordenar(nuevo, ORDEN_PPR)
    if len(nuevo):
        p.insert(0, nuevo)
    forzado = pap.startswith(PAPELES_FORZADOS)
    for x in ejecuciones(p):
        _aplicar_run(x, perfil.rpr, forzado)


def _aplicar_run(run, perfil_rpr, forzado: bool):
    viejo = run.find("w:rPr", NS)
    nuevo = deepcopy(perfil_rpr) if perfil_rpr is not None else etree.Element(w("rPr"))
    nuevo.tag = w("rPr")
    if not forzado:
        for x in list(nuevo):
            if local(x) in ENFASIS:
                nuevo.remove(x)
    if viejo is not None:
        for x in viejo:
            nombre = local(x)
            if nombre == "rStyle" or (nombre in ENFASIS and not forzado) or nombre in ("vanish", "webHidden", "rPrChange"):
                y = nuevo.find(f"w:{nombre}", NS)
                if y is not None:
                    nuevo.remove(y)
                nuevo.append(deepcopy(x))
        run.remove(viejo)
    ordenar(nuevo, ORDEN_RPR)
    if len(nuevo):
        run.insert(0, nuevo)


# --- tablas ------------------------------------------------------------------------------------


def _ancho_util(sect) -> int:
    if sect is None:
        return 9000
    pg, mg = sect.find("w:pgSz", NS), sect.find("w:pgMar", NS)
    try:
        return int(pg.get(w("w"))) - int(mg.get(w("left"))) - int(mg.get(w("right")))
    except (AttributeError, TypeError, ValueError):
        return 9000


def _aplicar_tabla(tbl, ref: Referencia, estilos_doc, ancho: int):
    if ref.tblpr is not None:
        viejo = tbl.find("w:tblPr", NS)
        nuevo = deepcopy(ref.tblpr)
        if viejo is not None:
            tbl.replace(viejo, nuevo)
        else:
            tbl.insert(0, nuevo)
    cabeceras = filas_cabecera(tbl, estilos_doc)
    for tr in tbl.findall("w:tr", NS):
        if tr not in cabeceras:
            continue
        for tc in tr.findall("w:tc", NS):
            tcpr = tc.find("w:tcPr", NS)
            if tcpr is None:
                tcpr = etree.Element(w("tcPr"))
                tc.insert(0, tcpr)
            viejo = tcpr.find("w:shd", NS)
            if viejo is not None:
                tcpr.remove(viejo)
            if ref.shd_cabecera is not None:
                pos = [local(x) for x in tcpr]
                indice = next((i for i, n in enumerate(pos) if n in ("noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark")), len(pos))
                tcpr.insert(indice, deepcopy(ref.shd_cabecera))
    # Columnas: si no caben en el ancho útil de la referencia, se escalan.
    grid = tbl.find("w:tblGrid", NS)
    if grid is None:
        return
    cols = [c for c in grid.findall("w:gridCol", NS) if (c.get(w("w")) or "").isdigit()]
    total = sum(int(c.get(w("w"))) for c in cols)
    if total <= ancho or total == 0:
        return
    f = ancho / total
    for c in cols:
        c.set(w("w"), str(int(int(c.get(w("w"))) * f)))
    for tcw in tbl.iter(w("tcW")):
        if tcw.get(w("type")) == "dxa" and (tcw.get(w("w")) or "").isdigit():
            tcw.set(w("w"), str(int(int(tcw.get(w("w"))) * f)))
    tw = tbl.find("w:tblPr/w:tblW", NS)
    if tw is not None and tw.get(w("type")) == "dxa" and (tw.get(w("w")) or "").isdigit() and int(tw.get(w("w"))) > ancho:
        tw.set(w("w"), str(ancho))


# --- portada -----------------------------------------------------------------------------------


def palabras(textos) -> set:
    return {x for t in textos for x in re.findall(r"\w+", sin_acentos(t.lower()))}


def _textos_cabeceras(paq: Paquete, parte) -> list[str]:
    res = []
    for rel in paq.relaciones(parte):
        if rel.get("Type") in (REL_HEADER, REL_FOOTER) and rel.get("TargetMode") != "External":
            info = paq.destino(parte, rel.get("Id"))
            if info and info[1] in paq.partes:
                res.append(" ".join(t.text or "" for t in paq.xml(info[1]).iter(w("t"))))
    return res


def _portada(paq: Paquete, parte, cuerpo, est: Estructura, ref: Referencia, avisos):
    """Pone la portada de la referencia con las etiquetas y los datos de la programación.

    Solo se hace si no se pierde ni se añade ninguna palabra: lo que se quita tiene que seguir en la
    portada nueva o en la cabecera/pie de la referencia. Si no, se deja la portada original.
    """
    viejos = est.bloques[: est.fin_portada + 1]
    datos: dict[str, tuple[str, list[str]]] = {}
    for clave, etiqueta, valores in campos_portada(viejos, ref.claves):
        if clave not in datos:
            datos[clave] = (normal(texto(etiqueta)), [normal(texto(v)) for v in valores if normal(texto(v))])
    if len(datos) < 2:
        avisos.append("No se reconocen los datos de la portada: se deja la portada original.")
        return
    nuevos = [deepcopy(b) for b in ref.portada]
    rellenados = set()
    for clave, etiqueta, valores in campos_portada(nuevos, ref.claves):
        if clave in rellenados:
            continue
        rellenados.add(clave)
        etiqueta_doc, lineas = datos.get(clave, ("", []))
        escribir_texto(etiqueta, etiqueta_doc)
        if not valores:
            continue
        modelo = valores[0]
        for v in valores[1:]:
            v.getparent().remove(v)
        escribir_texto(modelo, lineas[0] if lineas else "")
        anterior = modelo
        for linea in lineas[1:]:
            copia = deepcopy(modelo)
            escribir_texto(copia, linea)
            anterior.addnext(copia)
            anterior = copia
    antes = palabras(normal(texto(p)) for b in viejos for p in parrafos_propios(b))
    despues = palabras(normal(texto(p)) for b in nuevos for p in parrafos_propios(b))
    perdidas = antes - despues - palabras(_textos_cabeceras(ref.paq, ref.parte))
    ganadas = despues - antes
    if perdidas or ganadas:
        detalle = []
        if perdidas:
            detalle.append("se perdería «" + " ".join(sorted(perdidas)[:8]) + "»")
        if ganadas:
            detalle.append("se añadiría «" + " ".join(sorted(ganadas)[:8]) + "»")
        avisos.append("Portada original sin cambiar: con la de la referencia " + " y ".join(detalle) + ".")
        return
    for b in nuevos:
        paq.importar_referencias(ref.paq, ref.parte, b, parte)
    primero = viejos[0]
    for b in nuevos:
        primero.addprevious(b)
    for b in viejos:
        cuerpo.remove(b)


# --- estilos y numeración ----------------------------------------------------------------------


def _estilos(paq: Paquete, parte, doc, ref: Referencia):
    p_viejo = paq.parte_por_tipo(parte, REL_STYLES)
    viejos = Estilos(paq.xml(p_viejo))
    nuevos = deepcopy(ref.paq.xml(ref.parte_estilos))
    # Numeración que usan los estilos de la referencia (p. ej., títulos numerados).
    mapa = _importar_numeracion(paq, parte, ref, {n.get(w("val")) for n in nuevos.iter(w("numId"))} - {"0"})
    for n in nuevos.iter(w("numId")):
        if n.get(w("val")) in mapa:
            n.set(w("val"), mapa[n.get(w("val"))])
    # Estilos que el documento usa y la referencia no tiene: se copian.
    ids_nuevos = {s.get(w("styleId")) for s in nuevos.findall("w:style", NS)}
    usados = set()
    for nombre in list(paq.partes):
        if nombre.startswith("word/") and nombre.endswith(".xml") and nombre != p_viejo:
            try:
                raiz = paq.xml(nombre)
            except etree.XMLSyntaxError:
                continue
            for etiqueta in ("pStyle", "rStyle", "tblStyle", "numStyleLink", "styleLink"):
                usados |= {x.get(w("val")) for x in raiz.iter(w(etiqueta))}
    pendientes = list(usados - ids_nuevos - {None})
    while pendientes:
        sid = pendientes.pop()
        if sid in ids_nuevos or sid not in viejos.por_id:
            continue
        copia = deepcopy(viejos.por_id[sid])
        nuevos.append(copia)
        ids_nuevos.add(sid)
        for etiqueta in ("basedOn", "link", "next"):
            x = copia.find(f"w:{etiqueta}", NS)
            if x is not None and x.get(w("val")) not in ids_nuevos:
                pendientes.append(x.get(w("val")))
    paq.poner_xml(p_viejo, nuevos)


def _importar_numeracion(paq: Paquete, parte, ref: Referencia, num_ids: set) -> dict:
    if not num_ids:
        return {}
    p_ref = ref.paq.parte_por_tipo(ref.parte, REL_NUMBERING)
    if not p_ref:
        return {}
    num_ref = ref.paq.xml(p_ref)
    p_doc = paq.parte_por_tipo(parte, REL_NUMBERING)
    if not p_doc:
        p_doc = "word/numbering.xml"
        while p_doc in paq.partes:
            p_doc = p_doc.replace(".xml", "_ref.xml")
        paq.poner_xml(p_doc, etree.Element(w("numbering"), nsmap={"w": NS["w"]}))
        paq.registrar_tipo(p_doc, CT_NUMBERING)
        paq.anadir_relacion(parte, REL_NUMBERING, p_doc)
    destino = paq.xml(p_doc)
    max_abs = max([int(a.get(w("abstractNumId"))) for a in destino.findall("w:abstractNum", NS)] + [0])
    max_num = max([int(n.get(w("numId"))) for n in destino.findall("w:num", NS)] + [0])
    mapa = {}
    abstractos = {a.get(w("abstractNumId")): a for a in num_ref.findall("w:abstractNum", NS)}
    for nid in sorted(num_ids):
        num = next((n for n in num_ref.findall("w:num", NS) if n.get(w("numId")) == nid), None)
        if num is None:
            continue
        aid = num.find("w:abstractNumId", NS).get(w("val"))
        if aid not in abstractos:
            continue
        max_abs += 1
        max_num += 1
        a = deepcopy(abstractos[aid])
        a.set(w("abstractNumId"), str(max_abs))
        nsid = a.find("w:nsid", NS)
        if nsid is not None:
            nsid.set(w("val"), f"{(0x5A000000 + max_abs) & 0xFFFFFFFF:08X}")
        for x in a.findall("w:lvl/w:lvlPicBulletId", NS):
            x.getparent().remove(x)
        n = deepcopy(num)
        n.set(w("numId"), str(max_num))
        n.find("w:abstractNumId", NS).set(w("val"), str(max_abs))
        ultimos_abs = destino.findall("w:abstractNum", NS)
        if ultimos_abs:
            ultimos_abs[-1].addnext(a)
        else:
            primero_num = destino.find("w:num", NS)
            if primero_num is not None:
                primero_num.addprevious(a)
            else:
                destino.append(a)
        ultimos_num = destino.findall("w:num", NS)
        if ultimos_num:
            ultimos_num[-1].addnext(n)
        else:
            a.addnext(n)
        mapa[nid] = str(max_num)
    return mapa


# --- secciones, cabeceras y pies ---------------------------------------------------------------


def _quitar_cabeceras(paq: Paquete, parte):
    """Quita las cabeceras y pies del documento (antes de importar los de la referencia)."""
    for rel in list(paq.relaciones(parte)):
        if rel.get("Type") in (REL_HEADER, REL_FOOTER):
            info = paq.destino(parte, rel.get("Id"))
            paq.quitar_relacion(parte, rel.get("Id"))
            if info and not info[2]:
                paq.borrar(info[1])


def _secciones(paq: Paquete, parte, doc, ref: Referencia):
    est_secciones = [p.find("w:pPr/w:sectPr", NS) for p in doc.iter(w("p")) if p.find("w:pPr/w:sectPr", NS) is not None]
    final = doc.find("w:body/w:sectPr", NS)
    if final is None:
        final = etree.SubElement(doc.find("w:body", NS), w("sectPr"))
    todas = est_secciones + [final]
    n_ref = len(ref.secciones)
    for i, viejo in enumerate(todas):
        if i == len(todas) - 1:
            modelo = ref.secciones[-1]
        elif i == 0 and n_ref > 1:
            modelo = ref.secciones[0]
        elif i == 1 and n_ref > 2 and len(todas) > 2:
            modelo = ref.secciones[1]
        else:
            modelo = ref.secciones[-1]
        nuevo = limpiar_rsid(deepcopy(modelo))
        paq.importar_referencias(ref.paq, ref.parte, nuevo, parte)
        # Se conserva el tipo de salto y la orientación del documento.
        tipo = viejo.find("w:type", NS)
        t_nuevo = nuevo.find("w:type", NS)
        if t_nuevo is not None:
            nuevo.remove(t_nuevo)
        if tipo is not None:
            refs = [x for x in nuevo if local(x) in ("headerReference", "footerReference", "footnotePr", "endnotePr")]
            if refs:
                refs[-1].addnext(deepcopy(tipo))
            else:
                nuevo.insert(0, deepcopy(tipo))
        pg_v = viejo.find("w:pgSz", NS)
        pg_n = nuevo.find("w:pgSz", NS)
        if pg_v is not None and pg_n is not None and pg_v.get(w("orient")) == "landscape" and pg_n.get(w("orient")) != "landscape":
            ancho, alto = pg_n.get(w("w")), pg_n.get(w("h"))
            pg_n.set(w("w"), alto)
            pg_n.set(w("h"), ancho)
            pg_n.set(w("orient"), "landscape")
        viejo.getparent().replace(viejo, nuevo)


def _tema_y_fuentes(paq: Paquete, parte, ref: Referencia):
    for tipo in (REL_THEME, REL_FONTTABLE):
        p_ref = ref.paq.parte_por_tipo(ref.parte, tipo)
        if not p_ref:
            continue
        for rel in list(paq.relaciones(parte)):
            if rel.get("Type") == tipo:
                info = paq.destino(parte, rel.get("Id"))
                paq.quitar_relacion(parte, rel.get("Id"))
                if info:
                    paq.borrar(info[1])
        paq.anadir_relacion(parte, tipo, paq.importar(ref.paq, p_ref))


def _ajustes(paq: Paquete, parte, ref: Referencia, actualizar_indice: bool):
    p_doc = paq.parte_por_tipo(parte, REL_SETTINGS)
    p_ref = ref.paq.parte_por_tipo(ref.parte, REL_SETTINGS)
    if not p_doc or not p_ref:
        return
    doc, modelo = paq.xml(p_doc), ref.paq.xml(p_ref)
    for nombre in ("embedTrueTypeFonts", "embedSystemFonts", "saveSubsetFonts", "evenAndOddHeaders", "defaultTabStop", "compat", "updateFields"):
        viejo = doc.find(f"w:{nombre}", NS)
        nuevo = modelo.find(f"w:{nombre}", NS)
        if viejo is not None:
            doc.remove(viejo)
        if nuevo is not None and nombre != "updateFields":
            _insertar_ajuste(doc, deepcopy(nuevo))
    if actualizar_indice:
        u = etree.Element(w("updateFields"))
        u.set(w("val"), "true")
        _insertar_ajuste(doc, u)


ORDEN_AJUSTES = [
    "writeProtection", "view", "zoom", "removePersonalInformation", "removeDateAndTime", "doNotDisplayPageBoundaries",
    "displayBackgroundShape", "printPostScriptOverText", "printFractionalCharacterWidth", "printFormsData",
    "embedTrueTypeFonts", "embedSystemFonts", "saveSubsetFonts", "saveFormsData", "mirrorMargins",
    "alignBordersAndEdges", "bordersDoNotSurroundHeader", "bordersDoNotSurroundFooter", "gutterAtTop",
    "hideSpellingErrors", "hideGrammaticalErrors", "activeWritingStyle", "proofState", "formsDesign",
    "attachedTemplate", "linkStyles", "stylePaneFormatFilter", "stylePaneSortMethod", "documentType", "mailMerge",
    "revisionView", "trackRevisions", "doNotTrackMoves", "doNotTrackFormatting", "documentProtection",
    "autoFormatOverride", "styleLockTheme", "styleLockQFSet", "defaultTabStop", "autoHyphenation",
    "consecutiveHyphenLimit", "hyphenationZone", "doNotHyphenateCaps", "showEnvelope", "summaryLength",
    "clickAndTypeStyle", "defaultTableStyle", "evenAndOddHeaders", "bookFoldRevPrinting", "bookFoldPrinting",
    "bookFoldPrintingSheets", "drawingGridHorizontalSpacing", "drawingGridVerticalSpacing",
    "displayHorizontalDrawingGridEvery", "displayVerticalDrawingGridEvery", "doNotUseMarginsForDrawingGridOrigin",
    "drawingGridHorizontalOrigin", "drawingGridVerticalOrigin", "doNotShadeFormData", "noPunctuationKerning",
    "characterSpacingControl", "printTwoOnOne", "strictFirstAndLastChars", "noLineBreaksAfter",
    "noLineBreaksBefore", "savePreviewPicture", "doNotValidateAgainstSchema", "saveInvalidXml", "ignoreMixedContent",
    "alwaysShowPlaceholderText", "doNotDemarcateInvalidXml", "saveXmlDataOnly", "useXSLTWhenSaving",
    "saveThroughXslt", "showXMLTags", "alwaysMergeEmptyNamespace", "updateFields", "hdrShapeDefaults",
    "footnotePr", "endnotePr", "compat", "docVars", "rsids",
]


def _insertar_ajuste(raiz, el):
    pos = {n: i for i, n in enumerate(ORDEN_AJUSTES)}
    mio = pos.get(local(el), len(ORDEN_AJUSTES))
    for h in raiz:
        if h.tag.startswith(f"{{{NS['w']}}}") and pos.get(local(h), len(ORDEN_AJUSTES)) > mio:
            h.addprevious(el)
            return
    raiz.append(el)
