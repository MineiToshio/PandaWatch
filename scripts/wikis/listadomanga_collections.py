"""Parser de listadomanga.es — colecciones individuales (coleccion.php?id=N).

Complementa el calendario mensual (wikis/listadomanga.py) capturando
**ediciones especiales / portadas alternativas / cofres / extras de primera
edición / formato premium** que el calendario no marca explícitamente.

Cada URL `coleccion.php?id=N` corresponde a UNA edición concreta de una obra
(ej. id=1606 → "Ataque a los Titanes" Norma, id=6242 → "Edición Grimorio"
de Witch Hat). Hay ~6500 colecciones distintas en el catálogo. La estrategia
de discovery es **iteración secuencial** id=1..MAX — sin grafo "Otras
ediciones de X" (la enumeración cubre todo igual).

Estructura típica del HTML:

    <h2>Berserk (Panini)</h2>                         ← título de la colección
    <b>Formato:</b> Tomo doble A5 (148x210) cartoné…  ← formato (premium o no)
    <h2>Números editados</h2>                          ← sección regular
      <table class="ventana_id1" style="width: 184px;">
        <tr><td class="cen">
          <img class="portada" src="…" alt="Berserk nº37"/>
          Berserk nº37<br/>
          224 páginas en B/N<br/>
          10,00 €<br/>
          <a href="novedades.php?mes=6&ano=2017">Junio 2017</a>
        </td></tr>
      </table>
    <h2>Números editados (Ediciones Especiales)</h2>   ← sección con signal especial
      <table class="ventana_id1">…</table>
    <h2>Números editados (Portadas alternativas)</h2>
    <h2>Números editados (Packs)</h2>
    <h2>Cofres de regalo con las primeras ediciones de Berserk</h2>
    <h2>Extras de Berserk (Panini)</h2>
    <h2>Otras ediciones de Berserk</h2>                ← descartado (links a otras pages)
    …

**Layout A** — items en `<table class="ventana_id1" style="width: 184px;">`. Cubre:
- `Números editados` → solo si el `Formato:` de la página es premium
  (kanzenban, cartoné/tapa dura, A5, Tomo doble, doble sobrecubierta,
  Libro de ilustraciones).
- `Números editados (Ediciones Especiales)` → siempre, signal `special_edition`.
- `Números editados (Portadas alternativas)` → siempre, signal `variant_cover`.
- `Números editados (Packs)` → solo si la línea descriptiva del pack incluye
  keywords de extras (postales, bookmark, lámina, etc.).
- `Números editados (Edición Revisada)` → descartado (re-impresión).
- `Números en preparación` / `Números no editados` → descartado (sin precio).

**Layout B** (`<table width="920">`) — IMPLEMENTADO: Cofres/Regalos/Extras. Cada
extra se vincula a su tomo destino (`_merge_extras_into_items`): la foto del extra
va al carrusel (`images[]`) del tomo y el extra se documenta en `extras[]`. Si el
tomo regular destino fue descartado por el gate de premium, se crea un item
`from_extras` con la foto del cofre (caso edición normal con cofre de 1ª edición).

URLs sintéticas determinísticas: cada tomo genera
`coleccion.php?id=<N>&item=<edition_slug>-<vol>` (gotcha #27 generalizada).
El param `item` NO está en TRACKING_PARAMS, sobrevive normalización.
"""

from __future__ import annotations

import html as html_lib
import re
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Permite importar el módulo principal aunque corramos desde scripts/wikis/
# o desde el root del repo.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    from scripts.manga_watch import (  # type: ignore[import-not-found]
        Candidate,
        Source,
        candidate_from_source,
        clean_text,
        score_candidate,
    )
except ImportError:
    from manga_watch import (  # type: ignore[no-redef]
        Candidate,
        Source,
        candidate_from_source,
        clean_text,
        score_candidate,
    )


BASE_URL = "https://www.listadomanga.es/"
COLECCION_URL_TEMPLATE = "https://www.listadomanga.es/coleccion.php?id={cid}"
LISTA_URL = "https://www.listadomanga.es/lista.php"
CALENDAR_URL_TEMPLATE = "https://www.listadomanga.es/calendario.php?mes={month}&ano={year}"
# Hash del placeholder de "portada censurada" que listadomanga sirve para
# algunas ediciones adultas / sin cover real (gotcha #40/#41). No es portada.
CENSORED_COVER_HASH = "08a02c268a6d6b2304c152aa0acdc7a0"

# Meses para parsear fechas tipo "23 Marzo 2023" o "Junio 2017"
SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
DATE_LINE_PATTERN = re.compile(
    r"^(?:(\d{1,2})\s+)?(" + "|".join(SPANISH_MONTHS.keys()) + r")\s+(\d{4})$",
    re.IGNORECASE | re.UNICODE,
)

# Volumen en el alt del img o en la primera línea del item.
# Soporta "nº37", "n.37", "#37", "nº 37" en cualquier capitalización.
VOLUME_PATTERN = re.compile(r"n[º°.]?\s*(\d+)", re.IGNORECASE | re.UNICODE)

# Línea de PRECIO de un número GRATUITO. En "Números editados", donde un tomo
# de pago muestra "9,98 €", un folleto promocional regalado por la editorial
# (preview del primer capítulo, mini-artbook de regalo, avance bundleado con un
# videojuego, etc.) muestra "Número Gratuito". NO es una edición comprable ni
# coleccionable — es material de marketing — y se descarta en la ingestión.
# Señal universal y 100% fiable: verificada contra todas las colecciones de la
# categoría editorial "Previews" + promos sueltas (gotcha #103, owner 2026-06-14).
FREE_PRICE_PATTERN = re.compile(r"^(?:n[úu]mero\s+)?gratuito$", re.IGNORECASE | re.UNICODE)

# `<b>Formato:</b> <valor>` en la cabecera.
FORMATO_PATTERN = re.compile(
    r"<b>\s*Formato\s*:\s*</b>\s*([^<\n]+?)\s*<", re.IGNORECASE
)

# Tipos de colección que son coleccionables por concepto (no por formato).
# Cuando el TÍTULO de la colección menciona una de estas palabras (ej.
# "Demon Slayer: Fanbook"), TODOS los tomos son coleccionables aunque la
# página NO sea formato premium (rústica regular). El signal_type asociado
# se inyecta a TODOS los items de la colección. Esto cubre el caso de
# fanbooks, artbooks, guidebooks, datebooks que listadomanga publica con
# tomos numerados en sección "Números editados" regular.
COLLECTION_TYPE_RULES: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"\b(?:fanbook|fan\s+book)\b", re.IGNORECASE), ["fanbook"]),
    (re.compile(r"\b(?:artbook|art\s+book|art\s+works|illustrations?|ilustraciones)\b", re.IGNORECASE), ["artbook"]),
    (re.compile(r"\b(?:guidebook|guide\s+book|gu[íi]a\s+oficial|manual\s+oficial|enciclopedia)\b", re.IGNORECASE), ["guidebook"]),
    (re.compile(r"\b(?:databook|data\s+book)\b", re.IGNORECASE), ["fanbook"]),
]


def _detect_collection_type_signals(collection_title: str) -> list[str]:
    """Detecta si el title de la colección indica un tipo "coleccionable por
    concepto" (fanbook/artbook/guidebook). Si lo es, devuelve signal_types
    que aplican a TODOS los tomos — pasan el gate aunque el formato sea regular.
    """
    if not collection_title:
        return []
    signals: list[str] = []
    seen: set[str] = set()
    for pattern, sigs in COLLECTION_TYPE_RULES:
        if pattern.search(collection_title):
            for s in sigs:
                if s not in seen:
                    seen.add(s)
                    signals.append(s)
    return signals


# Ediciones coleccionables identificadas por el TÍTULO de la colección
# (no por formato). ListadoManga publica cada edición premium como una
# colección SEPARADA cuyo título lleva el nombre de la edición entre
# paréntesis ("Berserk (Maximum)", "Ataque a los Titanes (Edición Integral)").
# Cuando el Formato NO trae keyword premium (caso real AoT Integral id=5639:
# "Tomo (177x266) rústica (tapa blanda)") estos tomos se perdían ENTEROS por
# el gate de "regular sin premium". Estas reglas fuerzan la captura de TODOS
# los tomos con el signal correspondiente, igual que COLLECTION_TYPE_RULES.
# Conservador a propósito: solo marcadores claros de edición coleccionista /
# premium. NO se incluye "Nueva Edición" / "New Edition" (suelen ser
# re-impresiones estándar, no coleccionables).
EDITION_TITLE_RULES: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"\bkanzenban\b", re.IGNORECASE), ["kanzenban"]),
    (re.compile(r"\b(?:edici[oó]n\s+integral|complete\s+edition|edici[oó]n\s+completa)\b", re.IGNORECASE | re.UNICODE), ["special_edition", "omnibus"]),
    (re.compile(r"\b(?:edici[oó]n\s+coleccionista|collector'?s?\s+edition)\b", re.IGNORECASE | re.UNICODE), ["special_edition"]),
    (re.compile(r"\b(?:edici[oó]n\s+(?:deluxe|de\s+lujo)|deluxe\s+edition)\b", re.IGNORECASE | re.UNICODE), ["deluxe", "special_edition"]),
    (re.compile(r"\b(?:master\s+edition|maximum|ultimate\s+edition)\b", re.IGNORECASE), ["deluxe", "special_edition"]),
    (re.compile(r"\b(?:eternal\s+edition|perfect\s+edition)\b", re.IGNORECASE), ["special_edition"]),
    (re.compile(r"\b(?:black\s+edition|white\s+edition)\b", re.IGNORECASE), ["special_edition"]),
    (re.compile(r"\bedici[oó]n\s+especial\b", re.IGNORECASE | re.UNICODE), ["special_edition"]),
    # Paréntesis "(Especial)" / "(Special)" — convención de listadomanga para
    # ediciones especiales (Ao Ashi, Edens Zero, Tokyo Revengers, Guardianes
    # de la Noche…). SOLO la forma entre paréntesis: "Especial" suelto suele
    # ser parte del nombre de la obra ("Patrulla Especial", "Detective Conan
    # Especial") y NO una edición.
    (re.compile(r"\(\s*(?:especial|special)\s*\)", re.IGNORECASE | re.UNICODE), ["special_edition"]),
    (re.compile(r"\b(?:edici[oó]n\s+\d+\s*[ºo]?\s*aniversario|\d+\s*th\s+anniversary)\b", re.IGNORECASE | re.UNICODE), ["special_edition"]),
]


def _detect_edition_title_signals(collection_title: str) -> list[str]:
    """Como `_detect_collection_type_signals` pero para ediciones premium /
    coleccionista identificadas por el título (Integral, Coleccionista,
    Kanzenban, Maximum, Master/Eternal/Black Edition, Deluxe, Aniversario…).
    Devuelve los signal_types que fuerzan la captura de TODOS los tomos
    aunque el Formato de la página no sea premium.
    """
    if not collection_title:
        return []
    signals: list[str] = []
    seen: set[str] = set()
    for pattern, sigs in EDITION_TITLE_RULES:
        if pattern.search(collection_title):
            for s in sigs:
                if s not in seen:
                    seen.add(s)
                    signals.append(s)
    return signals


# Tokens en `Formato` que indican que la página entera ES un cofre/box
# set. Cuando matchea, los tomos numerados (alt="X nº1", "X nº2"…) que
# aparecen en `Números editados` NO se venden sueltos — viven dentro del
# cofre. El parser entonces emite UN único item box-level y descarta los
# tomos individuales. Ver gotcha #28.
BOX_FORMAT_PATTERN = re.compile(
    r"\ben\s+(?:cofre|estuche)\b",
    re.IGNORECASE,
)

# Prefijos de Formato que indican un producto NO-manga (cuentos ilustrados,
# novelas gráficas occidentales). Se usan para NO ensuciar ZERO_YIELD_LOG con
# libros que son cartoné (→ falso premium hardcover) pero no son tomos de manga
# — el filtro de layout ya los excluye; acá solo evitamos el ruido de auditoría.
NON_MANGA_FORMAT_PATTERN = re.compile(
    r"^\s*(?:cuento\s+ilustrado|novela\s+gr[áa]fica|libro\s*\()",
    re.IGNORECASE | re.UNICODE,
)


# Tokens en `Formato` que disparan "página entera = edición premium".
# Cuando matchea, los items de `Números editados` reciben el signal
# correspondiente automáticamente.
PREMIUM_FORMAT_RULES: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"\bkanzenban\b", re.IGNORECASE), ["kanzenban"]),
    # NOTE: NO hay rule por tamaño A5 ni por "doble sobrecubierta" (gotcha #51).
    # El A5 (148x210) es el estándar de muchas series clásicas; y una "doble
    # sobrecubierta" (dust jacket doble/reversible) es un detalle cosmético común
    # en ediciones REGULARES, NO una Kanzenban (caso real: Zetman Ivrea cole 1648,
    # "Tomo (133x185) rústica con doble sobrecubierta" — regular, no kanzenban).
    # El kanzenban REAL lo da el título "(Kanzenban)" (P0-A) o el literal
    # "kanzenban" en el formato. Ver gotcha #41/#51.
    # Cartoné / tapa dura: hardcover
    (re.compile(r"\bcarton[ée]\b", re.IGNORECASE | re.UNICODE), ["hardcover", "deluxe"]),
    (re.compile(r"\btapa\s+dura\b", re.IGNORECASE), ["hardcover", "deluxe"]),
    # Tomo doble = omnibus (2-en-1)
    (re.compile(r"\bTomo\s+doble\b", re.IGNORECASE), ["omnibus"]),
    # Libro de ilustraciones = artbook
    (re.compile(r"\bLibro\s+de\s+ilustraciones\b", re.IGNORECASE), ["artbook"]),
]

# Keywords que justifican mantener un item Pack (sino se descarta — packs
# regulares de "tomos 1+2 juntos" sin extra no son coleccionables).
PACK_EXTRAS_KEYWORDS = re.compile(
    r"\b(postal(?:es)?|bookmark|marcap[áa]gin[ao]s?|sticker|p[oó]ster|"
    r"l[áa]mina|shikishi|exclusiv|edici[oó]n\s+especial|edici[oó]n\s+limitada|"
    r"regalo|extras?|tarjetas?|cards?|brinde|coleccionable|cofre)\b",
    re.IGNORECASE | re.UNICODE,
)

# Cofre listado INLINE dentro de la sección regular "Números editados"
# ("Cofre de 2 tomos" — caso real Boichi cole 6240): único caso en que un
# item de la sección regular sin premium es coleccionable; se emite como box.
INLINE_BOX_RE = re.compile(r"\bcofres?\b", re.IGNORECASE)

# Marcadores de EDICIÓN dentro de la descripción de un item inline de "Números
# editados". Si la línea trae uno ADEMÁS del cofre, el item NO es un box set: es
# esa edición (especial/limitada/variante) que INCLUYE un cofre — caso real orange
# nº7 "-queridos amigos- Edición Especial + Cofre + Set 4 postales" (id=1970).
# Clasificarlo como box (a) crea una edición box-set FANTASMA y (b) DUPLICA el
# especial que la sección "Regalos/Cofres" (Layout B) emite para el mismo vol
# (gotcha #102). Orden: Limitada antes que Especial.
INLINE_EDITION_MARKERS: list[tuple[re.Pattern[str], str, str, list[str]]] = [
    (re.compile(r"\bEdici[oó]n\s+(?:Especial\s+)?Limitada\b", re.IGNORECASE | re.UNICODE),
     "limitada", "Edición Limitada", ["limited", "special_edition"]),
    (re.compile(r"\bEdici[oó]n\s+Especial\b", re.IGNORECASE | re.UNICODE),
     "especial", "Edición Especial", ["special_edition"]),
    (re.compile(r"\b(?:Portada|Sobrecubierta)\s+Alternativa\b", re.IGNORECASE | re.UNICODE),
     "alternativa", "Portada Alternativa", ["variant_cover"]),
]


def _match_inline_edition(desc: str) -> tuple[str, str, list[str]] | None:
    """Si `desc` (de un item inline de 'Números editados' que trae cofre) incluye
    un marcador de edición especial/limitada/variante, devuelve (kind, display,
    signals) — el item es esa edición, NO un box set. None si no hay marcador.
    Ver gotcha #102."""
    if not desc:
        return None
    for pat, kind, display, sigs in INLINE_EDITION_MARKERS:
        if pat.search(desc):
            return (kind, display, list(sigs))
    return None


def _strip_series_prefix(text: str, series_title: str) -> str:
    """Quita el prefijo del nombre de la colección de `text` (para extraer el
    volumen): en series con número embebido en el NOMBRE ("Kaiju Nº8"), el
    primer `nº` del texto es el de la serie, no el del tomo. Prueba el título
    completo y su forma sin el sufijo parentético ("InuYasha (Kanzenban)")."""
    t = text or ""
    full = (series_title or "").strip()
    bases = [full, re.sub(r"\s*\([^)]*\)\s*$", "", full).strip()]
    for b in bases:
        if b and t.lower().startswith(b.lower()):
            return t[len(b):]
    return t


# Marcador de volumen "nº"/"n°" a quitar del título de display (gotcha #52):
# "Atelier of Witch Hat nº5" → "Atelier of Witch Hat 5".
_VOL_MARKER_RE = re.compile(r"\s*n[º°]\s*(\d+)", re.IGNORECASE)
# "Edición Especial" (ES) o "Special Edition" (EN) en CUALQUIER posición del título
# (con o sin paréntesis). Se remueve siempre y, si el tomo es especial, se re-apenda
# UNA sola vez al final en español — así un qualifier embebido (contaminación) no
# queda en el medio (gotcha #54/#56) y un título que llega ya decorado en inglés no
# duplica el marcador ("X no Special Edition" + "Edición Especial" → un solo marcador,
# gotcha #93). Caso real: "The Promised Neverland Edición Especial 13"; "Pájaro que
# trina no vuela no Special Edition" (título corrompido por el skill viejo).
_ESP_ANY_RE = re.compile(
    r"\s*\(?\s*(?:Edici[óo]n\s+Especial|Special\s+Edition)\s*\)?\s*", re.IGNORECASE)


# Marcador de display por kind: distingue variantes del MISMO volumen que conviven
# en una edición (regular vs especial vs variant vs limited) para que NO se vean
# como tomos duplicados (gotcha #54/#56). El marcador va al FINAL.
_KIND_MARKER = {
    "especial": "Edición Especial", "special": "Edición Especial",
    "variant": "Variant", "alternativa": "Variant",
    "limited": "Edición Limitada", "limitada": "Edición Limitada",
    "collector": "Edición Coleccionista",
}
_MARKER_PRESENT = {
    "Edición Especial": r"especial|special",
    "Variant": r"variant|alternativa",
    "Edición Limitada": r"limitad|limited",
    "Edición Coleccionista": r"coleccionista|collector",
}


def normalize_display_title(title: str, edition_kind: str = "regular") -> str:
    """Normaliza el título de display de un tomo de listadomanga (gotcha #52/#54/#56):
    (a) quita el marcador de volumen "nº" ("…nº5" → "… 5");
    (b) AUTORITATIVO sobre el marcador de kind, para distinguir variantes del MISMO
        volumen que conviven en la edición:
        - especial/special → "… Edición Especial"; variant → "… Variant";
          limited → "… Edición Limitada" (lo apenda si falta);
        - regular (u otro kind base: kanzenban/deluxe/…) → QUITA un sufijo
          "Edición Especial" stale. Un tomo regular NUNCA lo lleva.
    """
    t = _VOL_MARKER_RE.sub(r" \1", title or "")
    # Quitar SIEMPRE "Edición Especial" (en cualquier posición) — evita que un
    # qualifier embebido quede en el medio o lo reordene otro paso al final.
    t = _ESP_ANY_RE.sub(" ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    marker = _KIND_MARKER.get(edition_kind)
    if marker == "Edición Especial":
        t = f"{t} Edición Especial"                      # especial: re-apendar al final
    elif marker:                                          # variant / limited
        if not re.search(_MARKER_PRESENT[marker], t, re.IGNORECASE):
            t = f"{t} {marker}"
    # regular/base: "Edición Especial" ya removido; nada más que hacer.
    return t


# Headers que indican secciones a procesar en Fase 1 (Layout A solamente).
# El orden importa: más específico primero (paréntesis-variants antes que
# el header base "Números editados").
# Cada entry: (regex, edition_kind, edition_display, signal_types_inject)
SECTION_RULES: list[tuple[re.Pattern[str], str, str, list[str]]] = [
    (
        re.compile(r"^N[úu]meros\s+editados\s*\(\s*Ediciones?\s+Especiales?\s*\)", re.IGNORECASE),
        "especial",
        "Edición Especial",
        ["special_edition"],
    ),
    (
        # Variante descubierta en Fase 3: "Ediciones Limitadas".
        re.compile(r"^N[úu]meros\s+editados\s*\(\s*Ediciones?\s+Limitadas?\s*\)", re.IGNORECASE),
        "limitada",
        "Edición Limitada",
        ["limited", "special_edition"],
    ),
    (
        re.compile(r"^N[úu]meros\s+editados\s*\(\s*Portadas?\s+alternativas?\s*\)", re.IGNORECASE),
        "alternativa",
        "Portada Alternativa",
        ["variant_cover"],
    ),
    (
        re.compile(r"^N[úu]meros\s+editados\s*\(\s*Packs?\s*\)", re.IGNORECASE),
        "pack",
        "Pack",
        ["bundle"],
    ),
    (
        re.compile(r"^N[úu]meros\s+editados\s*$", re.IGNORECASE),
        "regular",
        "",  # display vacío para tomos regulares
        [],
    ),
    # `Números editados (Planeta DeAgostini Cómics)` / `(Planeta Cómic)`:
    # estas secciones son tomos del MISMO catálogo, solo separados por
    # editorial (Planeta cambió de nombre de "DeAgostini Cómics" a
    # "Planeta Cómic"). Las tratamos como REGULAR — el filtro de
    # premium-format de la página decide si pasan al catálogo (igual que
    # `Números editados` sin paréntesis). Sin esta regla, colecciones
    # como id=1832 "Dragon Ball Box Set" (Edición de Lujo cartoné) NO
    # se procesaban porque sus tomos vivían SOLO en estas secciones.
    (
        re.compile(r"^N[úu]meros\s+editados\s*\(\s*Planeta\s+(?:DeAgostini\s+C[óo]mics|C[óo]mic)\s*\)", re.IGNORECASE),
        "regular",
        "",
        [],
    ),
    # `Números editados (Novela Gráfica)` / `(Manga Bara)`: subtipos
    # editoriales. Mismo razonamiento — REGULAR con premium-format gate.
    (
        re.compile(r"^N[úu]meros\s+editados\s*\(\s*(?:Novela\s+Gr[áa]fica|Manga\s+Bara)\s*\)", re.IGNORECASE),
        "regular",
        "",
        [],
    ),
    # P0-B: `Números en preparación (...)` — ediciones ANUNCIADAS aún no a la
    # venta. Se clasifican IGUAL que sus contrapartes "editados"; los items
    # resultantes se marcan con la tag `status:upcoming` en el loop de
    # emisión. Habilita descubrimiento temprano de ediciones especiales /
    # limitadas y de tomos de colecciones premium cuyos volúmenes viven
    # solo en "en preparación" (caso real Berserk Master Edition id=6325:
    # todos sus tomos cartoné están en preparación → antes daba 0 items).
    # El plano "Números en preparación" (regular) queda gateado por
    # premium_signals igual que "Números editados" (regular sin premium se
    # descarta). Orden: parentéticos específicos antes que el base.
    (
        re.compile(r"^N[úu]meros\s+en\s+preparaci[oó]n\s*\(\s*Ediciones?\s+Especiales?\s*\)", re.IGNORECASE),
        "especial",
        "Edición Especial",
        ["special_edition"],
    ),
    (
        re.compile(r"^N[úu]meros\s+en\s+preparaci[oó]n\s*\(\s*Ediciones?\s+Limitadas?\s*\)", re.IGNORECASE),
        "limitada",
        "Edición Limitada",
        ["limited", "special_edition"],
    ),
    (
        re.compile(r"^N[úu]meros\s+en\s+preparaci[oó]n\s*\(\s*Portadas?\s+alternativas?\s*\)", re.IGNORECASE),
        "alternativa",
        "Portada Alternativa",
        ["variant_cover"],
    ),
    # `Números en preparación (Packs)` — packs ANUNCIADOS (caso real id=5584,
    # detectado en logs/listadomanga_unknown_h2.txt). Mismo tratamiento que
    # `Números editados (Packs)`: kind=pack + filtro PACK_EXTRAS_KEYWORDS;
    # `status:upcoming` se aplica vía EN_PREPARACION_PATTERN (prefijo).
    (
        re.compile(r"^N[úu]meros\s+en\s+preparaci[oó]n\s*\(\s*Packs?\s*\)", re.IGNORECASE),
        "pack",
        "Pack",
        ["bundle"],
    ),
    (
        re.compile(r"^N[úu]meros\s+en\s+preparaci[oó]n\s*$", re.IGNORECASE),
        "regular",
        "",
        [],
    ),
]

# Header "en preparación" (cualquier variante) → los items emitidos se
# marcan upcoming. Match por prefijo (no anclado al final).
EN_PREPARACION_PATTERN = re.compile(r"^N[úu]meros\s+en\s+preparaci[oó]n", re.IGNORECASE)

# Headers que descartamos explícitamente (no son productos comprables ni
# tienen suficiente info como item independiente).
DISCARD_SECTION_PATTERNS = [
    re.compile(r"^N[úu]meros\s+editados\s*\(\s*Edici[oó]n\s+Revisada\s*\)", re.IGNORECASE),
    re.compile(r"^N[úu]meros\s+no\s+editados", re.IGNORECASE),
    # NOTE (P0-B 2026-06-06): `Números en preparación` SE QUITÓ de DISCARD.
    # Ahora se clasifica vía SECTION_RULES (variantes Especiales/Limitadas/
    # Alternativas + base regular gateada por premium) y los items se marcan
    # `status:upcoming`. Antes se descartaba entero → Berserk Master Edition
    # (todos sus tomos en preparación) daba 0 items.
    re.compile(r"^Sinopsis\s+de\b", re.IGNORECASE),
    re.compile(r"^Otras\s+ediciones\s+de\b", re.IGNORECASE),
    re.compile(r"^T[íi]tulos\s+de\b", re.IGNORECASE),
    re.compile(r"^Aviso\b", re.IGNORECASE),
    # Variantes descubiertas en Fase 3:
    # NOTE (2026-05-23): movido `Planeta DeAgostini Cómics` / `Planeta Cómic`
    # y `Novela Gráfica` / `Manga Bara` a SECTION_RULES como REGULAR. Antes
    # estaban acá como DISCARD lo cual perdía ~222 colecciones legítimas
    # premium (Dragon Ball Box Set Edición de Lujo, etc.) que tenían sus
    # tomos SOLO en esas secciones. Ahora se procesan y se filtran por el
    # gate de premium-format si la página no es premium.
    # - "Ilustración de las portadas de X" / "Ilustración del lomo de X":
    #   galerías de ilustración (composición visual), no productos comprables.
    re.compile(r"^Ilustraci[oó]n\s+de\s+(?:las\s+portadas|los\s+lomos)\s+de\b", re.IGNORECASE),
    re.compile(r"^Ilustraci[oó]n\s+del\s+(?:lomo|frontal|reverso)\s+de\b", re.IGNORECASE),
    # - "Ediciones de X en Japón y España": galería comparativa entre ediciones.
    re.compile(r"^Ediciones\s+de\s+.+\s+en\s+\w+", re.IGNORECASE),
]

# Headers que activan el parser Layout B (Fase 2 — extras / cofres / regalos).
# Cada match alimenta el merge extra→tomo en `_merge_extras_into_items`.
LAYOUT_B_SECTION_PATTERNS = [
    re.compile(r"^Cofres?\s+de\s+regalo\b", re.IGNORECASE),
    re.compile(r"^Regalos?\s+con\s+las\s+primeras\s+ediciones\b", re.IGNORECASE),
    re.compile(r"^Regalo\s+con\s+la\s+primera\s+edici[oó]n\b", re.IGNORECASE),
    re.compile(r"^Regalos?\s+de\b", re.IGNORECASE),
    re.compile(r"^Extras\s+de\b", re.IGNORECASE),
    # Variantes descubiertas en Fase 3 (corrida masiva):
    re.compile(r"^Packs?\s+especiales?\s+en\s+cofres?\b", re.IGNORECASE),
    re.compile(r"^Pack\s+especial\s+en\s+cofre\s+de\b", re.IGNORECASE),  # singular
    # "Regalo[s] con X" / "Extras con X" (sin "primeras ediciones" explícito).
    # Cubre casos tipo "Regalo con Death Note", "Extras con Reverberación".
    # Usamos lookhead negativo para NO chocar con "Regalos con las primeras
    # ediciones" que ya está arriba.
    re.compile(r"^Regalos?\s+con\b(?!\s+las\s+primeras\s+ediciones)", re.IGNORECASE),
    re.compile(r"^Extras\s+con\b", re.IGNORECASE),
    # Variantes "online" / "pre-reservas" / "preventas".
    re.compile(r"^Cartas?\s+(?:de\s+)?(?:regalo|p[óo]ker)?\s*(?:de\s+)?(?:regalo\s+)?con\b", re.IGNORECASE),
    re.compile(r"^Regalos?\s+exclusivos?\s+(?:de\s+la\s+)?tienda\b", re.IGNORECASE),
    re.compile(r"^L[áa]mina\s+de\s+regalo\b", re.IGNORECASE),
    # Cofres genéricos: "Cofre de Death Note (Edición Integral)".
    re.compile(r"^Cofres?\s+de\b(?!\s+regalo)", re.IGNORECASE),
]

# Markers de edición en la 2da línea de cada celda Layout B. El orden importa:
# patterns más específicos primero (Limitada antes que Especial sola).
# Cada entry: (regex, target_edition_kind)
LAYOUT_B_MARKERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^\(?\s*Edici[oó]n\s+Especial\s+Limitada\s*\)?\s*$", re.IGNORECASE), "especial"),
    (re.compile(r"^\(?\s*Edici[oó]n\s+Especial\s*\)?\s*$", re.IGNORECASE), "especial"),
    (re.compile(r"^\(?\s*Portada\s+Alternativa\s*\)?\s*$", re.IGNORECASE), "alternativa"),
    (re.compile(r"^\(?\s*Sobrecubierta\s+Alternativa\s*\)?\s*$", re.IGNORECASE), "alternativa"),
    (re.compile(r"^\(?\s*1[ºª]\s+Edici[oó]n\s*\)?\s*$", re.IGNORECASE), "regular"),
    (re.compile(r"^Pack\s+iniciaci[oó]n", re.IGNORECASE), "pack"),
]


def _decode_text(text: str) -> str:
    """Decode HTML entities + collapse whitespace + strip tabs trailing."""
    if not text:
        return ""
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_discarded_section(header_text: str) -> bool:
    for pat in DISCARD_SECTION_PATTERNS:
        if pat.search(header_text):
            return True
    return False


def _classify_section(header_text: str) -> tuple[str, str, list[str]] | None:
    """Devuelve (edition_kind, edition_display, signal_types_inject) si el
    header matchea una sección procesable; None si no.
    """
    for pattern, kind, display, signals in SECTION_RULES:
        if pattern.search(header_text):
            return (kind, display, signals)
    return None


def _extract_collection_title(soup: BeautifulSoup) -> str:
    """El primer <h2> de la página es el título de la colección."""
    for h2 in soup.find_all("h2"):
        txt = _decode_text(h2.get_text(" ", strip=True))
        if txt:
            return txt
    return ""


def _extract_formato(html_text: str) -> str:
    """Extrae el valor de `<b>Formato:</b> ...` de la cabecera."""
    m = FORMATO_PATTERN.search(html_text)
    if not m:
        return ""
    return _decode_text(m.group(1))


def _detect_premium_signals(formato: str) -> list[str]:
    """Si el formato matchea reglas premium, devuelve los signal_types a
    inyectar en TODOS los items de "Números editados" regulares.
    """
    if not formato:
        return []
    signals: list[str] = []
    seen: set[str] = set()
    for pattern, sigs in PREMIUM_FORMAT_RULES:
        if pattern.search(formato):
            for s in sigs:
                if s not in seen:
                    seen.add(s)
                    signals.append(s)
    return signals


def _is_box_format(formato: str) -> bool:
    """True si el formato indica 'X en cofre' / 'X en estuche'.

    Cuando matchea, la colección entera es un box set: los tomos
    individuales solo existen dentro del cofre y NO se venden sueltos.
    El parser entonces emite UN solo item box-level (representando el
    cofre) y descarta los tomos numerados en `Números editados`.

    Caso semilla: id=5959 "Gon (Edición Coleccionista) (Norma)" — formato
    "Tomo cuádruple A5 (148x210) cartoné (tapa dura) en cofre" tenía 2
    tomos numerados que el corpus mostraba como items separados pese a
    no venderse sueltos.
    """
    if not formato:
        return False
    return bool(BOX_FORMAT_PATTERN.search(formato))


def _virtual_source(publisher_hint: str = "") -> Source:
    """Source 'virtual' para taggear items de listadomanga colecciones."""
    return Source(
        name="ListadoManga (colecciones)",
        url=BASE_URL,
        country="España",
        language="Español",
        publisher=publisher_hint,
        source_class="trusted_media",
        kind="html",
        enabled=True,
        tags=["wiki", "listadomanga", "listadomanga-collections", "manga", "spain"],
    )


def _extract_publisher_from_header(html_text: str) -> str:
    """Extrae `<b>Editorial española:</b> <a>Norma Editorial</a>`.

    El HTML viene con entities (`Editorial espa&ntilde;ola`); decodificamos
    primero para matchear con el regex en texto plano.
    """
    decoded = html_lib.unescape(html_text)
    m = re.search(
        r"<b>\s*Editorial\s+espa[ñn]ola\s*:\s*</b>\s*<a[^>]*>([^<]+)</a>",
        decoded, re.IGNORECASE | re.UNICODE,
    )
    if m:
        return _decode_text(m.group(1))
    return ""


def _extract_author_from_header(html_text: str) -> str:
    """Extrae el primer `<b>Guion:</b> <a>Autor</a>` o `Dibujo:`."""
    decoded = html_lib.unescape(html_text)
    for label in ("Guion", "Guión", "Dibujo", "Autor"):
        m = re.search(
            rf"<b>\s*{label}\s*:\s*</b>\s*<a[^>]*>([^<]+)</a>",
            decoded, re.IGNORECASE | re.UNICODE,
        )
        if m:
            return _decode_text(m.group(1))
    return ""


def _slugify(text: str) -> str:
    """Slug simple ASCII-only minúsculas para construir URLs sintéticas."""
    text = text.lower().strip()
    # Reemplazar acentos comunes y caracteres no-ASCII
    text = (text
            .replace("á", "a").replace("é", "e").replace("í", "i")
            .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
            .replace("ü", "u").replace("º", "").replace("°", ""))
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:60]


def _make_synthetic_url(
    coleccion_id: int,
    edition_kind: str,
    volume: str,
    disambiguator: str = "",
) -> str:
    """URL sintética determinística por tomo dentro de una colección.

    `coleccion.php?id=<N>&item=<edition_slug>-<vol>[-<disambig>]` — el param
    `item` no está en TRACKING_PARAMS, sobrevive `normalize_url_for_dedup`.
    Mismo input siempre da mismo URL (idempotente para re-scrapes).

    `disambiguator`: usado cuando un mismo (edition, vol) tiene MÚLTIPLES
    productos distintos en la misma página (caso real Berserk vol 42 en
    "Ediciones Especiales" — hay 2 ediciones limitadas distintas con
    extras distintos publicadas en fechas distintas). Se pasa el slug de
    la descripción del extra o el image_id; mismo extra → mismo URL.
    """
    kind_slug = _slugify(edition_kind) or "regular"
    vol_part = volume.strip() if volume else "0"
    entry_id = f"{kind_slug}-{vol_part}"
    if disambiguator:
        d_slug = _slugify(disambiguator)[:20]
        if d_slug:
            entry_id = f"{entry_id}-{d_slug}"
    base = BASE_URL.rstrip("/") if not BASE_URL.endswith("//") else BASE_URL[:-1]
    return urljoin(base + "/", f"coleccion.php?id={coleccion_id}&item={entry_id}")


def _parse_release_date(line: str) -> str:
    """Convierte '24 Octubre 2024' / 'Junio 2017' → '2024-10-24' / '2017-06-01'.

    Las fechas pueden venir sin día (sólo mes-año). En ese caso usamos día 1.
    Devuelve "" si no parsea.
    """
    line = line.strip()
    m = DATE_LINE_PATTERN.match(line)
    if not m:
        return ""
    day_str, month_name, year_str = m.groups()
    month_num = SPANISH_MONTHS.get(month_name.lower())
    if not month_num:
        return ""
    try:
        day = int(day_str) if day_str else 1
        return f"{int(year_str):04d}-{month_num:02d}-{day:02d}"
    except (ValueError, TypeError):
        return ""


def _parse_item_text_lines(td: Any) -> list[str]:
    """Extrae las líneas de texto de un `<td class="cen">` separadas por <br/>.

    Las líneas pueden contener `<a>` (fecha con link a novedades.php) o ser
    texto plano. Devolvemos cada línea decoded + cleaned.
    """
    # Reemplazamos <br/> por marcador, extraemos texto plano, splitteamos.
    # Usamos separator="" para NO agregar \n extra entre nodos hermanos
    # (los unicos \n deben venir de los <br/> que ya inyectamos).
    for br in td.find_all("br"):
        br.replace_with("\n")
    raw = td.get_text("", strip=False)
    raw = html_lib.unescape(raw)
    lines = [ln.strip() for ln in raw.split("\n")]
    lines = [ln for ln in lines if ln]
    return lines


def _parse_item_table(
    item_table: Any,
    base_alt_fallback: str,
) -> dict[str, str] | None:
    """Parsea un `<table class="ventana_id1" style="width: 184px;">` (un tomo).

    Devuelve dict con title, image_url, description_extra, pages,
    release_date, volume. None si la tabla está vacía o no tiene img.portada
    (es un placeholder de relleno de la grid).
    """
    img = item_table.find("img", class_="portada")
    if not img:
        return None
    image_url = (img.get("src") or "").strip()
    alt = _decode_text(img.get("alt") or "")
    if not image_url:
        return None  # celda de relleno de la grid (sin img) → descartar
    # Placeholder de portada CENSURADA (`08a02c…png`): listadomanga lo sirve
    # server-side (sin la cookie CookieNSFW) para algunas ediciones adultas/
    # sin cover real. NO es una portada → vaciamos image_url para que el item
    # (que SÍ es válido: tiene título/precio) entre al worklist de search-covers
    # en vez de mostrar el placeholder. NO descartamos el item.
    # (Matiz de gotcha #40: la censura NO siempre es client-side.)
    if CENSORED_COVER_HASH in image_url:
        image_url = ""

    td = item_table.find("td", class_="cen") or item_table.find("td")
    if not td:
        return None

    lines = _parse_item_text_lines(td)
    if not lines:
        return None

    # Primera línea suele ser el título principal del item. En colecciones
    # donde el item title cubre dos líneas (Grimorio: "Atelier of Witch Hat" +
    # "Edición Grimorio nº1"), juntamos las primeras N hasta encontrar el
    # primer marcador "nº" que indica volumen.
    title = ""
    title_extra_lines: list[str] = []
    description_lines: list[str] = []
    pages = ""
    release_date = ""

    # Reglas heurísticas por línea:
    # - matchea VOLUME_PATTERN AND no contiene "páginas" → línea de título/edición
    # - contiene "páginas" → pages
    # - matchea fecha (con o sin día) → release_date
    # - no matchea nada de lo anterior → description extra (ediciones especiales)
    PAGES_PAT = re.compile(r"p[áa]ginas", re.IGNORECASE | re.UNICODE)
    PRICE_PAT = re.compile(r"€|EUR")

    title_part_built = False  # ya armamos la parte de título?
    for line in lines:
        if FREE_PRICE_PATTERN.match(line.strip()):
            # "Número Gratuito" = folleto promocional regalado (preview del 1er
            # capítulo, mini-artbook, avance bundleado). No es comprable ni
            # coleccionable → descartar el item entero. gotcha #103.
            return None
        if PAGES_PAT.search(line):
            pages = line
            title_part_built = True
            continue
        if PRICE_PAT.search(line):
            title_part_built = True
            continue  # línea de precio — descartar
        if _parse_release_date(line):
            release_date = _parse_release_date(line)
            title_part_built = True
            continue
        # Línea no es metadata estructurada
        if not title_part_built:
            # Si no tenemos title yet, primera no-metadata line es title.
            if not title:
                title = line
            else:
                # 2da+ línea no-metadata. Es parte del TÍTULO si:
                #  (a) tiene volumen nº y el title aún no (caso Grimorio: la 2da
                #      línea es "Edición Grimorio nº1"), o
                #  (b) aparece dentro del `alt` canónico de listadomanga — un
                #      subtítulo SIN número que va en 2da línea (ej.
                #      "CLAMP Art-book" + "North Side" → alt "CLAMP Art-book
                #      North Side"). Sin (b) se perdía el subtítulo y dos
                #      artbooks distintos (North/South Side) quedaban con título
                #      idéntico → la cover search los confundía (bug 2026-06-07).
                line_norm = _decode_text(line).lower()
                alt_norm = _decode_text(alt).lower()
                is_subtitle = bool(line_norm) and bool(alt_norm) and line_norm in alt_norm
                if (VOLUME_PATTERN.search(line) and not VOLUME_PATTERN.search(title)) or is_subtitle:
                    title_extra_lines.append(line)
                else:
                    description_lines.append(line)
        else:
            description_lines.append(line)

    if not title:
        title = alt or base_alt_fallback

    full_title = title
    if title_extra_lines:
        full_title = title + " " + " ".join(title_extra_lines)
    full_title = _decode_text(full_title)

    # Volumen: prefirir alt (que es canónico), sino del título compuesto.
    # ANTES de buscar el nº, quitar el prefijo del nombre de la colección:
    # series con número EMBEBIDO en el nombre ("Kaiju Nº8") hacían que el
    # primer match fuera el de la serie, no el del tomo — "Kaiju Nº8 nº16"
    # daba vol 8 (y el cofre cuyo alt es SOLO el nombre heredaba un vol 8
    # fantasma). Caso real cole 4139, prueba 2026-06-11.
    volume = ""
    vol_match = (
        VOLUME_PATTERN.search(_strip_series_prefix(alt, base_alt_fallback))
        or VOLUME_PATTERN.search(_strip_series_prefix(full_title, base_alt_fallback))
    )
    if vol_match:
        volume = vol_match.group(1)

    return {
        "title": full_title[:260],
        "alt": alt,
        "image_url": image_url,
        "pages": pages,
        "release_date": release_date,
        "description_extra": " · ".join(description_lines),
        "volume": volume,
    }


# Las tablas de item/tomo usan clase `ventana_id<N>` (width 184px) con la MISMA
# estructura de celda `<td class="cen">` (img.portada + texto). El número <N>
# es solo un skin CSS por tipo de edición/color: id1 = manga japonés B/N,
# id3 = manhwa a color (Sweet Home), id9 = packs/especiales (His Little Amber),
# etc. NO hay que whitelistar números concretos — matcheamos cualquier
# `ventana_id\d+` a width 184. (Antes solo se leía id1 → manhwa y varias
# ediciones especiales daban 0 items; detectado por ZERO_YIELD_LOG en el
# dry-run 2026-06-06. Ver gotcha #41.)
ITEM_TABLE_CLASS_RE = re.compile(r"^ventana_id\d+$")


def _iter_item_tables_after(header_h2: Any) -> list[Any]:
    """Devuelve las tablas de item (`ventana_id<N>`, width 184px) que aparecen
    DESPUÉS del header h2 dado y ANTES del próximo h2.

    Estructura: el `<h2>` está dentro de una tabla wrapper de width 974px.
    Las items van en tablas hermanas posteriores en el DOM hasta encontrar
    otro `<h2>`.
    """
    items: list[Any] = []
    # Caminamos por el árbol en orden DOM desde el h2 hasta el próximo h2.
    # Estrategia: subimos hasta el contenedor principal (un ancestro común)
    # y miramos los hermanos siguientes; pero el HTML de listadomanga tiene
    # tablas anidadas, así que es más simple usar find_all_next con stop.
    for elem in header_h2.find_all_next(["h2", "table"]):
        if elem.name == "h2":
            break
        if elem.name != "table":
            continue
        classes = elem.get("class") or []
        if not any(ITEM_TABLE_CLASS_RE.match(c) for c in classes):
            continue
        style = (elem.get("style") or "").lower()
        if "184" not in style:  # 184px = item; 974px = header wrapper
            continue
        items.append(elem)
    return items


# --- Layout B (Cofres / Regalos / Extras) ----------------------------------
#
# Estructura: `<h2>Extras de X</h2>` (con o sin `<strong>` envolvente)
# seguido por `<table width="920" border="0" align="center">` que tiene
# filas de celdas `<td width="150">`. Cada celda contiene un `<img>` y
# después dos `<br/>` + líneas de texto separadas por `<br/>`:
#   <Serie> nº<N>
#   <Marker de edición>
#   <Descripción del extra>
#   [<Detalle adicional>]
#   <Fecha>
#
# Caso especial Edición Grimorio (page-wide premium): la línea 1 es solo
# `<Serie>` (sin nº) y la línea 2 es `<Sub-line> nº<N>` (ej.
# "Edición Grimorio nº1"). En ese caso target_edition_kind = "regular"
# (page-wide premium), pero el item de Layout A ya tiene el sub-line
# embebido en el título.


def _iter_layout_b_tables_after(header_h2: Any) -> list[Any]:
    """Devuelve las `<table width="920">` que siguen al header dado hasta
    el próximo `<h2>`."""
    tables: list[Any] = []
    for elem in header_h2.find_all_next(["h2", "table"]):
        if elem.name == "h2":
            break
        if elem.name != "table":
            continue
        if str(elem.get("width") or "") != "920":
            continue
        tables.append(elem)
    return tables


def _parse_layout_b_cell(td: Any) -> dict[str, str] | None:
    """Parsea una `<td width="150">` Layout B y devuelve dict con
    target_volume, target_edition_kind, image_url, description, release_date,
    raw_target_series (línea 1 sin el nº).

    Devuelve None si la celda es padding (img src="" o sin contenido).
    """
    img = td.find("img")
    if not img:
        return None
    image_url = (img.get("src") or "").strip()
    if not image_url:
        return None  # cell de padding

    lines = _parse_item_text_lines(td)
    if not lines:
        return None

    # Línea 1: `<Serie> nº<N>` o `<Serie>` (pack).
    # Línea 2: marker de edición o sub-line con nº (Grimorio case).
    line1 = lines[0] if lines else ""
    line2 = lines[1] if len(lines) > 1 else ""

    # Detectar volumen + serie de la línea 1
    target_volume = ""
    raw_series = line1
    vm = VOLUME_PATTERN.search(line1)
    if vm:
        target_volume = vm.group(1)
        raw_series = VOLUME_PATTERN.sub("", line1).strip()

    # Detectar edition_kind del marker (línea 2)
    target_edition_kind = ""
    marker_text = line2
    for pattern, kind in LAYOUT_B_MARKERS:
        if pattern.search(line2):
            target_edition_kind = kind
            break

    # Si CUALQUIER línea (más allá de la 1) trae "Edición Especial" / "Limitada",
    # el item es una EDICIÓN ESPECIAL (artbook/limitada listada en la sección de
    # regalos), NO un cofre de tomo regular → kind especial (se fusiona con el
    # especial del mismo vol). Caso real Promised Neverland nº13: "Edición Especial
    # con Escape - Libro de ilustraciones" — el nombre de serie envuelto en 2 líneas
    # ("The Promised" / "Neverland nº13") hacía que el fallback Grimorio de abajo lo
    # tomara como regular (gotcha #59). Va ANTES del fallback Grimorio.
    if not target_edition_kind:
        _rest = " ".join(lines[1:])
        if re.search(r"\bEdici[oó]n\s+(?:Especial|Limitada)\b", _rest, re.IGNORECASE):
            target_edition_kind = "especial"
            if not target_volume:
                _vm = VOLUME_PATTERN.search(_rest)
                if _vm:
                    target_volume = _vm.group(1)

    # Caso Grimorio / page-wide premium: línea 2 es `<Sub-line> nº<N>`
    # (sin marker reconocido pero con nº). El target es "regular" y el
    # volumen viene de la línea 2.
    if not target_edition_kind and VOLUME_PATTERN.search(line2):
        vm2 = VOLUME_PATTERN.search(line2)
        if vm2:
            target_edition_kind = "regular"
            if not target_volume:
                target_volume = vm2.group(1)

    # Cofre que referencia "Serie nºN" (volumen en línea 1) y cuya línea 2 es un
    # descriptor de COFRE/EXTRA ("Cofre para tomos X a Y", "Cofre de regalo",
    # "Postal exclusiva"…) SIN marker de edición especial → es el cofre de 1ª
    # edición del tomo REGULAR N (gotcha #53). Sin esto, cofres comunes caían
    # (Medaka Box, Aoha Ride, Cells at Work…): target_edition_kind vacío → skip.
    # OJO: NO defaultear cuando la línea 2 es un marker de edición DESCONOCIDO
    # (ej. "(Edición Aniversario 30)") — eso sí se saltea (no inventamos regular).
    if (not target_edition_kind and target_volume
            and re.search(r"\b(?:cofre|regalo|postal(?:es)?|marcap[áa]gin|l[áa]mina|"
                          r"brinde|extras?|sticker|p[oó]ster|tarjeta)", line2, re.IGNORECASE)):
        target_edition_kind = "regular"

    # Descripción del extra: líneas entre marker y fecha (excluye fecha).
    # Buscar índice de la línea con fecha al final.
    date_idx = -1
    release_date = ""
    for i, ln in enumerate(lines):
        d = _parse_release_date(ln)
        if d:
            date_idx = i
            release_date = d
    # Marker ocupa línea 1 (target series+vol) o líneas 1-2 (Grimorio:
    # `<Serie>` + `<Sub-line> nº<N>`).
    desc_start = 2
    if VOLUME_PATTERN.search(line2) and not VOLUME_PATTERN.search(line1):
        desc_start = 2  # Grimorio: línea 1 = serie, línea 2 = sub-line+nº, líneas 3+ = desc
    desc_end = date_idx if date_idx > 0 else len(lines)
    desc_lines = lines[desc_start:desc_end]
    description = " ".join(desc_lines).strip()

    return {
        "target_volume": target_volume,
        "target_edition_kind": target_edition_kind,
        "raw_series": raw_series,
        "image_url": image_url,
        "description": description,
        "release_date": release_date,
        "marker_text": marker_text,
    }


def _iter_layout_b_cells(tables: list[Any]) -> list[dict[str, str]]:
    """Itera las celdas de un conjunto de Layout B tables y devuelve los
    extras parseados (skipping padding cells)."""
    extras: list[dict[str, str]] = []
    for tbl in tables:
        for td in tbl.find_all("td"):
            w = td.get("width")
            if str(w or "") != "150":
                continue
            parsed = _parse_layout_b_cell(td)
            if parsed:
                extras.append(parsed)
    return extras


def _merge_extras_into_items(
    layout_a_items: dict[tuple[str, str], Candidate],
    layout_b_extras: list[dict[str, str]],
    coleccion_id: int,
    source: Source,
    publisher: str,
    author: str,
    collection_title: str,
    formato: str,
    premium_signals: list[str],
    layout_a_covers: dict[tuple[str, str], str] | None = None,
) -> list[Candidate]:
    """Aplica el algoritmo merge extra→tomo. Devuelve la lista de tomos
    NUEVOS creados desde Layout B (los existentes ya se mutaron in-place).

    Reglas:
    1. Para cada extra, identificar target (edition_kind, volume).
    2. Si target ∈ layout_a_items → mutar el Candidate existente:
       - append imagen a `images` con kind=extra + description
       - append entry a `extras` con description + release_date
    3. Si target NO existe Y target_edition_kind ∈ {regular, especial,
       limitada, alternativa} → CREAR Candidate nuevo con la imagen del extra.
       `regular` lleva signal `bonus` (1ª edición con marcapáginas/postales);
       las demás llevan el signal de su edición (special_edition / limited /
       variant_cover). Sin esta regla, los extras cuyo tomo no está en
       Layout A (vive en "no editados" o sin sección propia) se perdían
       (caso real Berserk Master Edition id=6325). Otros kinds (pack…) no
       se crean acá.
    4. Casos sin volume detectado (packs Cofres tipo AoT "Pack iniciación
       tomos 1 y 2") → fuzzy-match contra packs Layout A por raw_series
       similarity. Si no hay match, descartar (no creamos packs nuevos —
       requieren raw_series legible que el cofre no siempre da).
    """
    created: list[Candidate] = []

    for ex in layout_b_extras:
        target_vol = ex.get("target_volume", "")
        target_kind = ex.get("target_edition_kind", "")
        if not target_kind:
            # Sin marker reconocido — saltamos (loggeo más abajo si activamos).
            continue

        if not target_vol and target_kind != "pack":
            # No reconocemos el volumen y no es un pack → skip.
            continue

        key = (target_kind, target_vol)
        target = layout_a_items.get(key)

        if target is not None:
            # ENRICH: agregar imagen + extra al item existente.
            target.images.append({
                "url": ex["image_url"],
                "local": "",
                "kind": "extra",
                "description": ex.get("description", ""),
            })
            target.extras.append({
                "description": ex.get("description", ""),
                "release_date": ex.get("release_date", ""),
                "source_section": "layout_b",
            })
        else:
            # CREATE: el extra apunta a un tomo que NO está en Layout A
            # (típicamente porque vive en "Números no editados" o no tiene
            # sección propia). Creamos el item para no perder el extra.
            #
            # P0-C (2026-06-06): antes SOLO se creaba para target_kind=regular;
            # ahora también para especial/limitada/alternativa. Caso real
            # Berserk Master Edition (id=6325): los extras cuyo tomo limitado
            # no estaba en Layout A se perdían enteros.
            #
            # Por kind: (nota de edición para la description, signal_keywords).
            # `regular` mantiene EXACTAMENTE el comportamiento previo: NO se
            # inyectan keywords de edición y la nota usa "regalos / brindes"
            # (score=20 c/u) para superar el umbral del dashboard sin disparar
            # box_set (la descripción literal del extra NUNCA se inyecta —
            # "Cofre para tomos 1 a 7" dispararía product_type=boxset).
            _CREATE_KINDS = {
                "regular": ("1ª Edición con extras / regalos / brindes", []),
                "especial": ("Edición Especial", ["edición especial"]),
                "limitada": ("Edición Limitada", ["edición especial", "edición limitada"]),
                "alternativa": ("Portada Alternativa", ["portada alternativa"]),
            }
            if target_kind not in _CREATE_KINDS:
                continue
            edition_note, signal_keywords = _CREATE_KINDS[target_kind]
            raw_series = ex.get("raw_series", "") or collection_title
            title = f"{raw_series} nº{target_vol}" if target_vol else raw_series
            desc_parts = [collection_title, edition_note]
            desc_parts.extend(signal_keywords)
            if formato:
                desc_parts.append(f"Formato: {formato}")
            description = " · ".join(p for p in desc_parts if p)

            disambig = ex["image_url"].rsplit("/", 1)[-1].rsplit(".", 1)[0][:16]
            synth_url = _make_synthetic_url(
                coleccion_id, target_kind, target_vol, disambiguator=disambig,
            )

            cand = candidate_from_source(
                source,
                title=title[:260],
                url=synth_url,
                description=description[:2500],
                published_at=ex.get("release_date", ""),
            )
            cand.publisher = publisher
            cand.author = author
            cand.edition_display = collection_title  # nombre oficial, sin traducir (gotcha #49)
            cand.release_date = ex.get("release_date", "")
            cand.tags = list(source.tags or []) + [
                f"edition:{target_kind}",
                f"coleccion:{coleccion_id}",
                "from_extras",  # marca de procedencia
            ]
            # Construir images[]: PREFERIR la cover del tomo regular si
            # existe en layout_a_covers (capturada de "Números editados"
            # incluso si esa sección se descartó por gate). Luego añadir
            # la imagen del extra como kind=extra.
            # Sin esto, el item from_extras solo tiene la foto del cofre
            # como única imagen — el dashboard muestra el cofre como
            # cover principal, cosa que confunde al usuario.
            images_list = []
            cover_url = None
            if layout_a_covers is not None:
                # Preferir la cover del MISMO kind/vol; fallback a la regular
                # del mismo vol (caso típico: el tomo especial reusa la cover
                # del tomo regular pre-capturada de "Números editados").
                cover_url = (
                    layout_a_covers.get((target_kind, target_vol))
                    or layout_a_covers.get(("regular", target_vol))
                )
            if cover_url and cover_url != ex["image_url"]:
                images_list.append({
                    "url": cover_url,
                    "local": "",
                    "kind": "gallery",
                    "description": "",
                })
                cand.image_url = cover_url  # alias del primer kind=cover
            else:
                cand.image_url = ex["image_url"]
            images_list.append({
                "url": ex["image_url"],
                "local": "",
                "kind": "extra",
                "description": ex.get("description", ""),
            })
            cand.images = images_list
            cand.extras = [{
                "description": ex.get("description", ""),
                "release_date": ex.get("release_date", ""),
                "source_section": "layout_b",
            }]
            created.append(cand)
            # Registrar en el dict para que extras subsiguientes del mismo
            # (regular, vol) se mergeen contra este Candidate recién creado.
            layout_a_items[key] = cand

    return created


def _is_layout_b_section(header_text: str) -> bool:
    for pat in LAYOUT_B_SECTION_PATTERNS:
        if pat.search(header_text):
            return True
    return False


# Registro de h2 desconocidos durante el parsing (módulo-level para que el
# bootstrap masivo pueda inspeccionarlo después de la corrida y descubrir
# patrones nuevos no cubiertos por DISCARD/SECTION_RULES/LAYOUT_B).
UNKNOWN_H2_LOG: list[tuple[int, str]] = []

# Registro de colecciones SOSPECHOSAS de miss: la página tenía indicación
# premium (formato/título premium) o secciones de extras (Layout B) pero el
# parser emitió 0 candidates. Es la señal que habría delatado el bug de
# Berserk Master Edition (premium cartoné → 0 items) ANTES del fix P0-B.
# Cada entry: (coleccion_id, collection_title, reason). Se vuelca al final
# del bootstrap (módulo-level para que el caller lo inspeccione).
ZERO_YIELD_LOG: list[tuple[int, str, str]] = []

# Registro de colecciones perdidas por ERROR DE RED (timeout, reset, 5xx tras
# agotar retries de la sesión). Antes esto se tragaba en silencio y era
# indistinguible de "colección vacía" — la colección quedaba fuera del run sin
# rastro. Cada entry: (coleccion_id, error). Se vuelca al final del bootstrap;
# los ids sirven para re-correr con --coleccion-ids-file.
NETWORK_ERROR_LOG: list[tuple[int, str]] = []


def parse_collection_page(
    html_text: str,
    coleccion_id: int,
    source_url: str = "",
    enable_layout_b: bool = True,
) -> list[Candidate]:
    """Parsea una página `coleccion.php?id=N` y devuelve candidates.

    Pasa Layout A (tomos en `table.ventana_id1[width:184px]`) bajo secciones
    whitelistadas (Números editados con paréntesis-variants, y el regular
    cuando el Formato es premium).

    Si `enable_layout_b=True` (default), también parsea secciones de
    extras/cofres/regalos (`<table width="920">`) y aplica el algoritmo
    merge extra→tomo (Fase 2 — gotcha #28). Cada extra:
    - matchea contra un item Layout A → enrich (`images[]` += imagen,
      `extras[]` += descripción).
    - no matchea Y target_edition_kind=regular → crea tomo nuevo con
      la imagen del extra y signal `bonus` (abre la puerta a tomos
      regulares de 1ª edición con brindes que de otro modo no entran).
    """
    if not html_text or len(html_text) < 1000:
        return []

    soup = BeautifulSoup(html_text, "html.parser")
    collection_title = _extract_collection_title(soup)
    if not collection_title:
        return []

    formato = _extract_formato(html_text)
    premium_signals = _detect_premium_signals(formato)
    # NOTA (2026-06-06): el heurístico "A5 (148x210) → kanzenban" se ELIMINÓ.
    # En España el formato A5 es el ESTÁNDAR de muchas series clásicas
    # (Detective Conan, Monster, Dr. Slump, obras de Rumiko Takahashi…), no solo
    # de kanzenban → marcaba como premium cientos de tomos estándar (sobre-
    # captura confirmada en el run real sobre ids 1-100: 254/266 items). El
    # kanzenban GENUINO se detecta por título "(Kanzenban)" (P0-A), formato
    # "doble sobrecubierta" o literal "kanzenban" (PREMIUM_FORMAT_RULES). Decisión
    # del owner 2026-06-06. Ver gotcha #41.
    # Detección por title de colección: si el título contiene "Fanbook" /
    # "Artbook" / "Guía" / "Databook" / etc., todos los tomos son
    # coleccionables aunque el formato sea regular. Combinamos esos signals
    # con los premium del Formato para que TODOS los items pasen el gate.
    collection_type_signals = _detect_collection_type_signals(collection_title)
    if collection_type_signals:
        premium_signals = premium_signals + [
            s for s in collection_type_signals if s not in premium_signals
        ]
    # P0-A: ediciones premium identificadas por el título (Integral,
    # Coleccionista, Kanzenban, Maximum, Master/Eternal/Black Edition…).
    # Igual que collection_type_signals: fuerzan que los tomos regulares
    # pasen el gate aunque el Formato sea rústica (caso AoT Edición Integral).
    edition_title_signals = _detect_edition_title_signals(collection_title)
    if edition_title_signals:
        premium_signals = premium_signals + [
            s for s in edition_title_signals if s not in premium_signals
        ]
    # ¿La colección es premium por TÍTULO (P0-A) o tipo (fanbook/artbook)?
    # Es evidencia FUERTE de edición coleccionista — entonces sí emitimos sus
    # tomos regulares aunque estén en un layout no-id1 (caso real: ediciones
    # catalanas premium "Berserk (Maximum) (Català)", "Ranma ½ (Kanzenban)
    # (Català)" usan ventana_id2). Si el premium viene SOLO del formato (A5/
    # cartoné), la sección regular se restringe a id1 para no inundar con
    # ediciones estándar (manhwa id3, manga regional id2, revistas id12).
    title_premium = bool(collection_type_signals or edition_title_signals)
    # Formato "en cofre" → emitimos UN solo item box-level y descartamos
    # los tomos numerados. Inyectamos box_set explícito al set de signals
    # premium para que el box item lo lleve (y se siga inyectando vía
    # keyword_hints en la descripción).
    is_box_format = _is_box_format(formato)
    if is_box_format and "box_set" not in premium_signals:
        premium_signals = premium_signals + ["box_set"]
    publisher = _extract_publisher_from_header(html_text)
    author = _extract_author_from_header(html_text)

    source = _virtual_source(publisher_hint=publisher)
    candidates: list[Candidate] = []
    # Indexamos Layout A por (edition_kind, volume) para el merge Layout B.
    layout_a_index: dict[tuple[str, str], Candidate] = {}
    # SEPARADO del index: capturamos las covers de TODOS los items Layout A
    # (incluso los descartados por el gate de "regular sin premium"). Esto
    # es para que items from_extras puedan tener la foto del tomo regular
    # como kind=cover, además de la foto del cofre/extra como kind=extra.
    # Ej: AoT id=1606 — los tomos 1, 17, 27 regulares se descartan por el
    # gate (no es página premium), pero sus covers se preservan acá para
    # que los items from_extras (creados desde cofres "(1ª Edición)") las
    # usen al armar el carrusel.
    layout_a_covers: dict[tuple[str, str], str] = {}

    # Layout B sections — diferimos al final cuando layout_a_index está completo.
    layout_b_headers: list[Any] = []

    # PASADA 1 — Layout A
    for h2 in soup.find_all("h2"):
        header_text = _decode_text(h2.get_text(" ", strip=True))
        if not header_text:
            continue
        if _is_layout_b_section(header_text):
            layout_b_headers.append(h2)
            continue

        # PRE-CAPTURA covers de TODA sección DISCARD con items Layout A
        # (hoy "Números no editados" / "Edición Revisada"). Razón: items
        # from_extras pueden referenciar tomos que aún no salieron — el cofre
        # con marcapáginas ya está documentado pero el tomo no se editó.
        # Sin esta captura, el item from_extras solo tiene foto del extra.
        # Tratamos las DISCARD como sección "regular" (para el key del index).
        # (Nota P0-B: "en preparación" ya NO es DISCARD — se clasifica abajo.)
        if _is_discarded_section(header_text):
            for item_tbl in _iter_item_tables_after(h2):
                parsed_for_cover = _parse_item_table(item_tbl, base_alt_fallback=collection_title)
                if parsed_for_cover and parsed_for_cover.get("image_url"):
                    vol_for_cover = parsed_for_cover.get("volume", "")
                    key_for_cover = ("regular", vol_for_cover)
                    if key_for_cover not in layout_a_covers:
                        layout_a_covers[key_for_cover] = parsed_for_cover["image_url"]
            continue

        classification = _classify_section(header_text)
        if not classification:
            # Header desconocido. Lo registramos (excepto el primer h2 que
            # siempre es el título de la colección).
            if header_text != collection_title:
                UNKNOWN_H2_LOG.append((coleccion_id, header_text))
            continue

        edition_kind, edition_display, signal_inject = classification
        # P0-B: ediciones anunciadas (sección "en preparación") → items
        # marcados upcoming (mismo edition_kind/signals que su contraparte
        # "editados"; el dedup/cluster_key no cambia, así que cuando el tomo
        # pase a "editados" hace upsert, no duplica).
        is_upcoming = bool(EN_PREPARACION_PATTERN.match(header_text))

        # PRE-CAPTURA covers de TODA sección Layout A — antes de aplicar el
        # gate "regular sin premium". Garantiza que items from_extras puedan
        # asociar la foto del tomo regular aunque la sección se descarte.
        for item_tbl in _iter_item_tables_after(h2):
            parsed_for_cover = _parse_item_table(item_tbl, base_alt_fallback=collection_title)
            if parsed_for_cover and parsed_for_cover.get("image_url"):
                vol_for_cover = parsed_for_cover.get("volume", "")
                key_for_cover = (edition_kind, vol_for_cover)
                if key_for_cover not in layout_a_covers:
                    layout_a_covers[key_for_cover] = parsed_for_cover["image_url"]

        # Filtro: si es "regular" y NO hay premium signals, descartar
        # toda la sección (tomos regulares no son coleccionables salvo
        # que la página entera sea formato premium). EXCEPCIÓN: cofres
        # listados inline en la sección ("Cofre de 2 tomos", Boichi cole
        # 6240 — antes solo lo capturaba el calendario plano legacy); si
        # los hay, se emiten SOLO esos items (como box), el resto se
        # sigue descartando.
        inline_box_only = False
        if edition_kind == "regular" and not premium_signals:
            inline_box_only = any(
                p and INLINE_BOX_RE.search(p.get("description_extra", ""))
                for p in (
                    _parse_item_table(t, base_alt_fallback=collection_title)
                    for t in _iter_item_tables_after(h2)
                )
            )
            if not inline_box_only:
                continue

        # Si el formato es "en cofre", saltamos la emisión de items
        # individuales — los tomos numerados viven dentro del cofre y
        # no se venden sueltos. La emisión box-level se hace después
        # del loop. layout_a_covers ya fue pre-poblado arriba para que
        # el box item pueda elegir su cover.
        if is_box_format:
            continue

        for item_tbl in _iter_item_tables_after(h2):
            # La sección REGULAR ("Números editados") solo emite tomos
            # `ventana_id1` (manga japonés B/N estándar) SALVO que la colección
            # sea premium por título/tipo (title_premium). Otros layouts en la
            # sección regular sin title_premium son ediciones estándar no-
            # coleccionables: manhwa a color (id3), manga regional (id2),
            # revistas/libros (id12) — emitirlos inundaría el catálogo (caso
            # real Detectiu Conan id2, Mundo Manganime id12, dry-run 2026-06-06).
            # Con title_premium SÍ se emiten (ediciones catalanas premium en id2:
            # Berserk Maximum, Ranma Kanzenban). Las SECCIONES ESPECIALES
            # siempre aceptan cualquier layout (His Little Amber especial = id9).
            if edition_kind == "regular" and not title_premium:
                classes = item_tbl.get("class") or []
                if "ventana_id1" not in classes:
                    continue
            parsed = _parse_item_table(item_tbl, base_alt_fallback=collection_title)
            if not parsed:
                continue

            # Modo cofre-inline: SOLO se emiten los items marcados como
            # cofre; toman kind=box (el resto de la sección regular no
            # premium sigue descartado). EXCEPCIÓN (gotcha #102): si el item
            # trae un marcador de edición (Edición Especial/Limitada, Portada
            # Alternativa) ADEMÁS del cofre, NO es un box set — es esa edición
            # con cofre incluido (caso orange nº7). Clasificarlo por su edición
            # evita (a) una edición box-set fantasma y (b) duplicar el especial
            # que la sección "Regalos/Cofres" (Layout B) emite para el mismo vol
            # (el merge tomo↔extra lo fusiona por (kind, vol)).
            item_kind = edition_kind
            item_display = edition_display
            item_signal_inject = signal_inject
            if inline_box_only:
                desc_x = parsed.get("description_extra", "")
                if not INLINE_BOX_RE.search(desc_x):
                    continue
                ed = _match_inline_edition(desc_x)
                if ed:
                    item_kind, item_display, item_signal_inject = ed
                else:
                    item_kind = "box"
                    item_display = "Cofre"
                    item_signal_inject = ["box_set"]

            # Filtro pack: solo aceptar si la descripción tiene keywords de extras.
            if item_kind == "pack":
                desc = parsed.get("description_extra", "")
                if not PACK_EXTRAS_KEYWORDS.search(desc):
                    continue

            # Construir título display + descripción.
            # Caso especial PACK/BOX inline: el title de listadomanga es solo
            # el nombre de la serie (sin nº) — "The Legend of Zelda". El gate
            # is_collectible_edition exige number-shape en el title o URL
            # canónica para aprobar signals como box_set. Enriquecemos el
            # title con el desc_extra (que sí lleva info distintiva:
            # "Pack especial tomos 1 a 5 + cofre de regalo") para que el
            # gate lo apruebe correctamente.
            title = parsed["title"]
            if item_kind in ("pack", "box") and parsed.get("description_extra"):
                title = f"{title} — {parsed['description_extra']}"
            else:
                # Quitar "nº" + marcar edición especial en el display (gotcha #52).
                title = normalize_display_title(title, item_kind)
            desc_parts = [collection_title]
            if item_display:
                desc_parts.append(item_display)
            if parsed.get("description_extra"):
                desc_parts.append(parsed["description_extra"])
            if parsed.get("pages"):
                desc_parts.append(parsed["pages"])
            # NO incluir el campo `Formato:` literal en la description —
            # contamina `detect_signals` cuando dice palabras como "en
            # cofre" (tomo individual en presentación de cofre, NO box
            # set). Los premium signals ya se inyectaron explícitamente
            # via PREMIUM_FORMAT_RULES, no necesitamos el texto raw.
            description = " · ".join(p for p in desc_parts if p)

            # Inyectar keywords de signal en la descripción para que
            # detect_signals levante los signal_types apropiados.
            # Para "regular" con premium format, inyectamos los premium signals.
            # Para especial/alternativa/pack, inyectamos los del section_rules.
            extra_signals = list(item_signal_inject)
            if item_kind == "regular":
                extra_signals.extend(premium_signals)
            elif premium_signals:
                # En secciones especial/alternativa de una página premium,
                # también propagar los signals premium (ej. kanzenban con
                # portada alternativa = ambos signals).
                for s in premium_signals:
                    if s not in extra_signals:
                        extra_signals.append(s)
            # Convertir signal_types a keywords detectables: añadir tokens
            # naturales al final de la descripción.
            keyword_hints = []
            for s in extra_signals:
                if s == "special_edition":
                    keyword_hints.append("edición especial")
                elif s == "variant_cover":
                    keyword_hints.append("portada alternativa")
                elif s == "kanzenban":
                    keyword_hints.append("Kanzenban")
                elif s == "hardcover":
                    keyword_hints.append("Hardcover Tapa Dura")
                elif s == "deluxe":
                    keyword_hints.append("edición deluxe")
                elif s == "omnibus":
                    keyword_hints.append("Omnibus 2-en-1")
                elif s == "artbook":
                    keyword_hints.append("Artbook")
                elif s == "bundle":
                    keyword_hints.append("Pack")
                elif s == "box_set":
                    keyword_hints.append("Box Set")
            if keyword_hints:
                description += " · " + " · ".join(keyword_hints)

            # Disambiguator: cuando un (edition_kind, vol) tiene múltiples
            # productos distintos (ej. Berserk vol 42 Ediciones Especiales
            # tiene 2 ediciones limitadas con extras distintos; o Zelda con
            # 2 packs "tomos 1 a 5" / "tomos 6 a 10" donde el slug del desc
            # arranca igual y colisiona si truncamos).
            #
            # Usamos el image_id (hash del filename del CDN) como
            # disambiguator primario: es ÚNICO por producto distinto, y es
            # estable para el mismo producto en re-scrapes (idempotente).
            # Fallback al desc_extra si por algún motivo no hay image.
            image_id = ""
            iu = parsed.get("image_url", "")
            if iu:
                fn = iu.rsplit("/", 1)[-1]
                image_id = fn.rsplit(".", 1)[0][:16]  # hash hex corto
            disambig = image_id or parsed.get("description_extra", "")
            synthetic_url = _make_synthetic_url(
                coleccion_id,
                item_kind,
                parsed.get("volume", ""),
                disambiguator=disambig,
            )

            cand = candidate_from_source(
                source,
                title=title,
                url=synthetic_url,
                description=description[:2500],
                published_at=parsed.get("release_date", ""),
            )
            cand.publisher = publisher
            cand.author = author
            # edition_display = nombre OFICIAL de la edición (título de la
            # coleccion), SIN traducir (gotcha #49). NO el slug genérico
            # "Special/Regular". El nombre del TOMO sí se traduce (lo hace el
            # skill); el de la EDICIÓN no.
            cand.edition_display = collection_title
            cand.image_url = parsed["image_url"]
            cand.release_date = parsed.get("release_date", "")
            # Propagar volumen al candidato para que candidate_to_json lo preserve
            # aunque _extract_volume no lo detecte en el título normalizado (gotcha #60).
            # El volumen LMC viene del alt "nº13" en _parse_item_table; sin esto queda "".
            if parsed.get("volume"):
                cand.volume = parsed["volume"]
            cand.tags = list(source.tags or []) + [
                f"edition:{item_kind}",
                f"coleccion:{coleccion_id}",
            ]
            if is_upcoming:
                cand.tags.append("status:upcoming")
            # Score floor para colecciones PREMIUM por título (gotcha #50):
            # si el TÍTULO de la coleccion indica una edición premium
            # (Kanzenban, Integral, Deluxe, Coleccionista…), TODOS sus tomos son
            # de esa edición premium → garantizamos que superen min_score (30),
            # aunque el signal puntual puntúe bajo. Sin esto, colecciones enteras
            # tipo "20th Century Boys (Kanzenban)" caían por score 25<30.
            if title_premium and cand.score < 31:
                cand.score = 31
            # Inicializar images[] con la cover (Fase 2 schema). Cuando el
            # merge Layout B encuentre extras para este tomo, los appendea.
            if parsed["image_url"]:
                cand.images = [{
                    "url": parsed["image_url"],
                    "local": "",
                    "kind": "gallery",
                    "description": "",
                }]
            candidates.append(cand)
            # Registrar en el index del merge — first-wins por key. Si hay
            # múltiples productos físicos con misma (kind, vol) — caso real
            # Berserk vol 42 con 2 Ediciones Especiales — solo el primero
            # recibe los extras del merge. Los demás coexisten en `candidates`
            # con sus propias covers únicas (disambiguator por image_id).
            vol = parsed.get("volume", "")
            idx_key = (item_kind, vol)
            if idx_key not in layout_a_index:
                layout_a_index[idx_key] = cand

    # EMISIÓN BOX-LEVEL — solo cuando formato es "en cofre".
    # Construimos UN único Candidate representando el cofre. Los Layout B
    # extras (si los hay) se appendean directamente al carrusel del box,
    # NO se rutean al merge tomo-por-tomo (no hay tomos individuales).
    if is_box_format:
        # Cover preferida: la del cofre (alt sin nº → key=("regular", "")).
        # Fallback: primera cover capturada (cualquier tomo).
        cover_url = layout_a_covers.get(("regular", ""))
        if not cover_url:
            for url in layout_a_covers.values():
                if url:
                    cover_url = url
                    break

        tomo_count = sum(
            1 for k, v in layout_a_covers.items()
            if v and k != ("regular", "")
        )

        desc_parts = [collection_title]
        if formato:
            desc_parts.append(f"Formato: {formato}")
        if tomo_count:
            desc_parts.append(f"Cofre con {tomo_count} tomos")

        # Inyectar keyword hints para que detect_signals levante box_set +
        # signals premium en el item box-level.
        keyword_hints = ["Cofre", "Box Set"]
        for s in premium_signals:
            if s == "kanzenban":
                keyword_hints.append("Kanzenban")
            elif s == "hardcover":
                keyword_hints.append("Hardcover Tapa Dura")
            elif s == "deluxe":
                keyword_hints.append("edición deluxe")
            elif s == "omnibus":
                keyword_hints.append("Omnibus 2-en-1")
            elif s == "artbook":
                keyword_hints.append("Artbook")
        description = " · ".join(desc_parts + keyword_hints)

        disambig = ""
        if cover_url:
            fn = cover_url.rsplit("/", 1)[-1]
            disambig = fn.rsplit(".", 1)[0][:16]
        synth_url = _make_synthetic_url(
            coleccion_id, "box", "", disambiguator=disambig,
        )

        # Enriquecemos el title con "— Cofre" (a menos que ya lo lleve)
        # para que `detect_signals` sobre el title detecte box_set, y así
        # `is_collectible_edition` no rechace el item como "regular_tomo"
        # cuando el collection_title no tiene boxset-word naturalmente
        # (ej. "La Biblia", "Golgo 13: ...", "Utena (Edición Integral)").
        box_title = collection_title
        if not re.search(r"\b(?:cofre|box\s*set|cofanetto|coffret|estuche|slipcase)\b",
                         box_title, re.IGNORECASE):
            box_title = f"{collection_title} — Cofre"

        box_cand = candidate_from_source(
            source,
            title=box_title[:260],
            url=synth_url,
            description=description[:2500],
            published_at="",
        )
        box_cand.publisher = publisher
        box_cand.author = author
        box_cand.edition_display = collection_title  # nombre oficial, sin traducir (gotcha #49)

        # Carrusel: box cover primero, luego cada tomo del cofre como
        # kind=extra (para dar contexto visual sin emitir cards separadas).
        # Regla del owner (2026-05-24): "los box sets son solo el item del
        # box set. Lo que se puede hacer es poner 1ro la foto del box set
        # y luego para agregar más contexto poner las fotos de los tomos
        # que vienen dentro, pero como 1 mismo item".
        images_list: list[dict[str, str]] = []
        if cover_url:
            box_cand.image_url = cover_url
            images_list.append({
                "url": cover_url,
                "local": "",
                "kind": "gallery",
                "description": "",
            })

        # Tomos numerados dentro del cofre (covers capturados en layout_a_covers).
        # Excluimos la key ("regular", "") que es el cover del cofre y la
        # cover_url ya appendeada. Ordenamos por volumen ascendente para
        # un carrusel coherente.
        def _vol_sort_key(item: tuple[tuple[str, str], str]) -> tuple[int, str]:
            (_, vol), _ = item
            try:
                return (int(vol), vol) if vol else (10**9, "")
            except (ValueError, TypeError):
                return (10**9, vol)

        for (kind, vol), url in sorted(layout_a_covers.items(), key=_vol_sort_key):
            if not url or url == cover_url:
                continue
            desc = f"Tomo {vol}" if vol else ""
            images_list.append({
                "url": url,
                "local": "",
                "kind": "extra",
                "description": desc,
            })

        box_cand.images = images_list
        box_cand.tags = list(source.tags or []) + [
            "edition:box",
            f"coleccion:{coleccion_id}",
        ]

        # Layout B extras (cofres-extra / regalos / cards / marcapáginas) →
        # también al carrusel del box, después de los tomos.
        if enable_layout_b and layout_b_headers:
            for h2 in layout_b_headers:
                tables = _iter_layout_b_tables_after(h2)
                for ex in _iter_layout_b_cells(tables):
                    if not ex.get("image_url"):
                        continue
                    box_cand.images.append({
                        "url": ex["image_url"],
                        "local": "",
                        "kind": "extra",
                        "description": ex.get("description", ""),
                    })
                    box_cand.extras.append({
                        "description": ex.get("description", ""),
                        "release_date": ex.get("release_date", ""),
                        "source_section": "layout_b",
                    })

        candidates.append(box_cand)
        return candidates

    # PASADA 2 — Layout B (extras / cofres / regalos)
    if enable_layout_b and layout_b_headers:
        all_extras: list[dict[str, str]] = []
        for h2 in layout_b_headers:
            tables = _iter_layout_b_tables_after(h2)
            all_extras.extend(_iter_layout_b_cells(tables))

        if all_extras:
            created = _merge_extras_into_items(
                layout_a_items=layout_a_index,
                layout_b_extras=all_extras,
                coleccion_id=coleccion_id,
                source=source,
                publisher=publisher,
                author=author,
                collection_title=collection_title,
                formato=formato,
                premium_signals=premium_signals,
                layout_a_covers=layout_a_covers,
            )
            candidates.extend(created)

    # P4: detección de miss. Si la página tenía indicación premium (formato/
    # título) o secciones de extras pero NO emitió ningún candidate, lo
    # registramos para auditoría (habría delatado Berserk Master pre-P0-B).
    # NO flaggear productos NO-manga (cuentos ilustrados / novelas gráficas /
    # libros-ensayo): son cartoné → falso premium hardcover, pero nunca son
    # misses de manga (el filtro de layout ya los excluyó correctamente).
    if not candidates and not NON_MANGA_FORMAT_PATTERN.match(formato or ""):
        reasons = []
        if premium_signals:
            reasons.append(f"premium={','.join(premium_signals)}")
        if layout_b_headers:
            reasons.append(f"layout_b={len(layout_b_headers)}")
        if reasons:
            ZERO_YIELD_LOG.append((coleccion_id, collection_title[:80], "; ".join(reasons)))

    return candidates


def fetch_collection(
    coleccion_id: int,
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
) -> list[Candidate]:
    """Descarga + parsea una colección por id. Devuelve candidates scored."""
    url = COLECCION_URL_TEMPLATE.format(cid=coleccion_id)
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        if not response.encoding:
            response.encoding = response.apparent_encoding
        text = response.text
    except requests.RequestException as exc:
        # Error de red ≠ colección vacía: dejarlo visible y registrado para
        # poder re-correr esos ids (antes se trataba igual que una página
        # inexistente y la colección se perdía en silencio).
        print(f"  [WARN] coleccion {coleccion_id}: error de red ({exc.__class__.__name__}: {exc}); omitida")
        NETWORK_ERROR_LOG.append((coleccion_id, f"{exc.__class__.__name__}: {exc}"))
        return []
    # Páginas inexistentes devuelven HTML mínimo o redirect a lista.
    if len(text) < 2000:
        return []
    raw = parse_collection_page(text, coleccion_id, source_url=url)
    return [score_candidate(c) for c in raw]


def iter_year_months(
    year_from: int, month_from: int, year_to: int, month_to: int
) -> list[tuple[int, int]]:
    """Stub para compat con dispatcher. Esta wiki no usa calendario;
    devuelve un único 'mes virtual' para que el dispatcher loguee.
    """
    return [(year_from, month_from)]


def _discover_via_lista(
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
) -> list[int]:
    """Discovery via `lista.php` (índice oficial alfabético del catálogo).

    Devuelve los ~3432 ids de colecciones ACTIVAS en el orden que aparecen
    en la página (alfabético por título). Es el discovery preferido sobre
    iteración numérica 1..6500 porque:
    - 3432 vs 6500 → 47% menos requests (no procesa ids huérfanos/eliminados).
    - Cubre colecciones MÁS NUEVAS que el tope numérico (lista.php incluye
      ids hasta 6624+).
    - Es el listado canónico que el usuario quería recorrer (decisión
      explícita 2026-05-23: "el listado es el que yo quería que tú vayas
      uno por uno").

    En caso de fallo HTTP, devuelve [] (el caller debe caer a iteración
    numérica como fallback).
    """
    try:
        response = session.get(LISTA_URL, timeout=timeout)
        response.raise_for_status()
        if not response.encoding:
            response.encoding = response.apparent_encoding
        text = response.text
    except requests.RequestException:
        return []

    soup = BeautifulSoup(text, "html.parser")
    anchor_re = re.compile(r"coleccion\.php\?id=(\d+)")
    seen: set[int] = set()
    ids: list[int] = []
    for a in soup.find_all("a", href=anchor_re):
        m = anchor_re.search(a.get("href") or "")
        if not m:
            continue
        cid = int(m.group(1))
        if cid in seen:
            continue
        seen.add(cid)
        ids.append(cid)
    return ids


def _iter_calendar_months(
    year_from: int, month_from: int, year_to: int, month_to: int
) -> list[tuple[int, int]]:
    """Lista (year, month) inclusive de from..to. Si el rango está invertido
    o vacío, devuelve al menos el mes `from`."""
    months: list[tuple[int, int]] = []
    y, m = year_from, month_from
    guard = 0
    while (y, m) <= (year_to, month_to) and guard < 240:
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
        guard += 1
    return months or [(year_from, month_from)]


def _discover_via_calendar(
    year_from: int,
    month_from: int,
    year_to: int,
    month_to: int,
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
    sleep_seconds: float = 0.3,
) -> list[int]:
    """Discovery DELTA: ids de colección con actividad en `calendario.php`
    dentro de la ventana [from..to] (inclusive).

    Recorre cada mes del calendario y extrae los `coleccion.php?id=N`
    referenciados (cada lanzamiento del mes apunta a su colección). Devuelve
    los ids únicos en orden de primera aparición. Permite que el DELTA parsee
    SOLO las colecciones tocadas recientemente — con toda la riqueza del
    parser de colecciones (ediciones especiales / cofres / variantes / en
    preparación) — en vez de las ~3432 del catálogo completo.

    Fallo HTTP de un mes → se saltea ese mes (no aborta el resto).
    """
    import time

    anchor_re = re.compile(r"coleccion\.php\?id=(\d+)")
    seen: set[int] = set()
    ids: list[int] = []
    months = _iter_calendar_months(year_from, month_from, year_to, month_to)
    for i, (y, m) in enumerate(months):
        url = CALENDAR_URL_TEMPLATE.format(month=m, year=y)
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            if not response.encoding:
                response.encoding = response.apparent_encoding
            text = response.text
        except requests.RequestException:
            continue
        for m_id in anchor_re.finditer(text):
            cid = int(m_id.group(1))
            if cid in seen:
                continue
            seen.add(cid)
            ids.append(cid)
        if sleep_seconds > 0 and i < len(months) - 1:
            time.sleep(sleep_seconds)
    return ids


def bootstrap(
    year_from: int,
    month_from: int,
    year_to: int,
    month_to: int,
    session: requests.Session,
    sleep_seconds: float = 0.3,
    timeout: tuple[int, int] = (10, 30),
    min_score: int = 30,
    fetch_details: bool = False,
    id_from: int = 1,
    id_to: int = 6500,
    skip_404_streak: int = 500,
    mode: str = "lista",
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Recorre las colecciones de listadomanga.es.

    Args:
        mode: `"lista"` (default, FULL) usa `lista.php` como discovery —
            ~3432 colecciones activas en orden alfabético, ignora id_from/id_to.
            `"range"` itera secuencialmente desde `id_from` a `id_to`
            (modo legacy, útil para re-procesar rangos específicos).
            `"calendar"` (DELTA) descubre los ids con actividad en
            `calendario.php` dentro de [year_from/month_from .. year_to/
            month_to] y parsea SOLO esas colecciones (misma riqueza que el
            full, acotado a lo reciente).
        id_from, id_to: rango de ids para `mode=range`. Default 1..6500.
        skip_404_streak: cuando `mode=range`, corta tras esta cantidad de
            ids consecutivos sin contenido. Ignorado en otros modos.

    year/month se usan SOLO en `mode=calendar` (ventana del calendario); los
    demás modos los ignoran. fetch_details no aplica (cada coleccion.php ya
    contiene toda la info en una sola request).
    """
    import time

    all_candidates: list[Candidate] = []

    # Lista EXPLÍCITA de ids (mayor prioridad): para ingesta por chunks
    # resumible — el driver descubre lista.php UNA vez, cachea el orden y pasa
    # cada chunk de ids acá. Determinístico y reanudable.
    explicit_ids = kwargs.get("explicit_ids")
    if explicit_ids:
        ids_to_process = [int(x) for x in explicit_ids]
        print(f"[BOOTSTRAP] lista EXPLÍCITA de {len(ids_to_process)} ids (chunk resumible).")
        mode = "explicit"
    # Resolver lista de ids según mode.
    elif mode == "lista":
        print(f"[BOOTSTRAP] discovery via lista.php (modo 'lista', recomendado)")
        ids_to_process = _discover_via_lista(session, timeout=timeout)
        if not ids_to_process:
            print(f"[BOOTSTRAP] lista.php falló; cayendo a iteración numérica "
                  f"{id_from}..{id_to} (fallback).")
            ids_to_process = list(range(id_from, id_to + 1))
        else:
            print(f"[BOOTSTRAP] lista.php devolvió {len(ids_to_process)} colecciones activas "
                  f"(en orden alfabético del catálogo).")
    elif mode == "range":
        print(f"[BOOTSTRAP] iteración numérica {id_from}..{id_to} (modo 'range', legacy)")
        ids_to_process = list(range(id_from, id_to + 1))
    elif mode == "calendar":
        print(f"[BOOTSTRAP] discovery via calendario.php (modo 'calendar', DELTA): "
              f"{year_from:04d}-{month_from:02d} → {year_to:04d}-{month_to:02d}")
        ids_to_process = _discover_via_calendar(
            year_from, month_from, year_to, month_to,
            session, timeout=timeout, sleep_seconds=sleep_seconds,
        )
        print(f"[BOOTSTRAP] calendario devolvió {len(ids_to_process)} colecciones "
              f"con actividad reciente.")
    else:
        raise ValueError(f"mode desconocido: {mode!r} (esperado 'lista', 'range' o 'calendar')")

    total_ids = len(ids_to_process)
    consecutive_empty = 0

    for idx, cid in enumerate(ids_to_process, start=1):
        cands = fetch_collection(cid, session, timeout=timeout)
        kept = [c for c in cands if c.score >= min_score]
        all_candidates.extend(kept)
        if flush_fn and kept:
            flush_fn(kept)

        if not cands:
            consecutive_empty += 1
        else:
            consecutive_empty = 0

        if idx % 50 == 0 or kept:
            print(
                f"[{idx}/{total_ids}] coleccion {cid}: "
                f"{len(cands)} cands, {len(kept)} con score>={min_score} "
                f"(total acumulado: {len(all_candidates)})"
            )

        # Si llevamos mucha racha sin resultados, asumimos fin del catálogo.
        # SOLO aplica en mode=range (en mode=lista los ids vienen del índice
        # oficial, no debería haber muchos sin contenido).
        if mode == "range" and consecutive_empty >= skip_404_streak:
            print(
                f"[BOOTSTRAP] {consecutive_empty} ids consecutivos sin contenido; "
                f"asumiendo fin del catálogo en id={cid}."
            )
            break

        if sleep_seconds > 0 and idx < total_ids:
            time.sleep(sleep_seconds)

    # Dump UNKNOWN_H2_LOG al final — patrones de h2 que ni SECTION_RULES ni
    # LAYOUT_B_SECTION_PATTERNS reconocieron. Útil para detectar variantes
    # nuevas durante la corrida masiva (Fase 3).
    if UNKNOWN_H2_LOG:
        # Conteo por header (normalizado) para reportar los más frecuentes.
        from collections import Counter
        counter = Counter(h for _, h in UNKNOWN_H2_LOG)
        print(f"\n[UNKNOWN h2] {len(UNKNOWN_H2_LOG)} headers no reconocidos "
              f"({len(counter)} únicos):")
        for header, n in counter.most_common(30):
            sample_ids = [str(cid) for cid, h in UNKNOWN_H2_LOG[:200] if h == header][:5]
            print(f"  {n:5d}× '{header}'  (ej. id={','.join(sample_ids)})")
        # Persistir log para inspección posterior.
        try:
            log_path = Path("logs") / "listadomanga_unknown_h2.txt"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("w", encoding="utf-8") as f:
                for cid, h in UNKNOWN_H2_LOG:
                    f.write(f"{cid}\t{h}\n")
            print(f"  Log completo: {log_path}")
        except OSError:
            pass

    # P4: dump del log de colecciones premium/con-extras que dieron 0 items.
    # Son candidatos a miss del parser (deben revisarse manualmente).
    if ZERO_YIELD_LOG:
        print(f"\n[ZERO-YIELD] {len(ZERO_YIELD_LOG)} colecciones con indicación "
              f"premium/extras pero 0 items (posibles misses):")
        for cid, title, reason in ZERO_YIELD_LOG[:30]:
            print(f"  id={cid:<5} [{reason}] :: {title}")
        if len(ZERO_YIELD_LOG) > 30:
            print(f"  … y {len(ZERO_YIELD_LOG) - 30} más.")
        try:
            log_path = Path("logs") / "listadomanga_zero_yield.txt"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("w", encoding="utf-8") as f:
                for cid, title, reason in ZERO_YIELD_LOG:
                    f.write(f"{cid}\t{reason}\t{title}\n")
            print(f"  Log completo: {log_path}")
        except OSError:
            pass

    # Dump de colecciones perdidas por error de red. El archivo contiene un
    # id por línea → re-procesable directo con --coleccion-ids-file.
    if NETWORK_ERROR_LOG:
        print(f"\n[NETWORK-ERROR] {len(NETWORK_ERROR_LOG)} colecciones omitidas "
              f"por error de red (NO están en el corpus de este run):")
        for cid, err in NETWORK_ERROR_LOG[:30]:
            print(f"  id={cid:<5} {err}")
        if len(NETWORK_ERROR_LOG) > 30:
            print(f"  … y {len(NETWORK_ERROR_LOG) - 30} más.")
        try:
            log_path = Path("logs") / "listadomanga_network_errors.txt"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("w", encoding="utf-8") as f:
                for cid, _err in NETWORK_ERROR_LOG:
                    f.write(f"{cid}\n")
            print(f"  Ids re-procesables: {log_path} "
                  f"(usar con --coleccion-ids-file)")
        except OSError:
            pass

    return all_candidates


if __name__ == "__main__":
    # Smoke run sobre los 5 piloto que conocemos.
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--id-from", type=int, default=1)
    parser.add_argument("--id-to", type=int, default=10)
    parser.add_argument("--ids", help="lista coma-sep de ids específicos")
    parser.add_argument("--sleep-seconds", type=float, default=0.3)
    args = parser.parse_args()

    s = requests.Session()
    s.headers["User-Agent"] = "manga-watch/0.2 (+listadomanga-collections-bootstrap)"

    if args.ids:
        ids = [int(x.strip()) for x in args.ids.split(",") if x.strip()]
        items: list[Candidate] = []
        for cid in ids:
            cands = fetch_collection(cid, s)
            print(f"coleccion {cid}: {len(cands)} items")
            for c in cands:
                print(f"  [{c.score}] {c.title}  → {c.url}")
            items.extend(cands)
        print(f"\nTotal: {len(items)}")
    else:
        items = bootstrap(
            2026, 1, 2026, 1, session=s,
            id_from=args.id_from, id_to=args.id_to,
            sleep_seconds=args.sleep_seconds,
        )
        print(f"\nTotal con señales: {len(items)}")
