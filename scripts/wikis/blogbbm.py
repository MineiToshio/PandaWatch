"""Parser de blogbbm.com — Biblioteca Brasileira de Mangás (curated wiki BR).

BBM mantiene posts-guía CONSOLIDADOS que enumeran ediciones especiales /
capas variantes / volúmenes con extras del mercado brasileño. Cada post
está actualizado **continuamente** (no archivado): la entrada más
reciente se sigue agregando con cada nuevo lanzamiento que el editor
considera notable. Cubre publishers BR que el scrape directo cubre
poco a la hora de marcar "esto es variant cover" / "esto trae brinde":
JBC, NewPOP, Panini Brasil, Pipoca & Nanquim, MPEG, Devir, Conrad.

Posts soportados hoy (BBM_POSTS):

1. /2020/10/09/capas_variantes/   — Capas variantes (todas las entradas
                                    son variant cover por curación).
2. /2024/05/15/guia-volumes-especiais-de-mangas-com-itens-especiais/
                                  — Volúmenes con extras (postais,
                                    marcapáginas, stickers, cards...).
                                    Todas las entradas son
                                    `special_edition` + `bonus`.

Estructura del HTML (los dos posts usan layouts ligeramente distintos
pero parseables con la misma heurística title-driven):

**Layout A** (/capas_variantes/):
    <div class="entry-content">
       <p>intro...</p>
       <hr/>
       <div class="gallery">                    ← gallery DIV con 2 imgs
          <img src=".../<series>NN.jpg"/>          cover normal + variant
          <img src=".../<series>NN-variant.jpg"/>
       </div>
       <p><strong>Título #NN</strong></p>       ← título (con link a ficha)
       <p>Em janeiro de 2014, a editora JBC… R$ 11,90…</p>
       ...

**Layout B** (/guia-volumes-especiais.../):
    <hr/>
    <p>Ataque dos Titãs #34 (12/2021)</p>      ← título con (MM/YYYY)
    <hr/>
    <p>O volume final…</p>                     ← prose
    <p>A versão especial teve…</p>
    <figure><img src=".../regular.jpg"/></figure>  ← figures separados
    <figure><img src=".../especial.jpg"/></figure>
    <hr/>
    <p>Shangri-la Frontier #01 (04/2022)</p>   ← siguiente entry
    ...

Por eso el parser NO divide por `<hr>` ni busca gallery divs específicos:
**escanea todos los `<p>` con "title shape"** (texto corto con marker de
volumen `#NN` o fecha `(MM/YYYY)` entre paréntesis o link a
`/manga/<slug>/`). Cada title abre un entry; el entry se cierra al
encontrar el próximo title. Entre uno y otro, se acumulan imgs (de
gallery divs, figures, o img sueltos) y prose.

API pública (paralela a mangavariant.py / socialanime.py):
    parse_post(html_text, post_url, signal_types_inject) -> list[Candidate]
    fetch_post(session, post_url, timeout) -> str | None
    bootstrap(yf, mf, yt, mt, session, ...) -> list[Candidate]
    iter_year_months(yf, mf, yt, mt) -> [(yf, mf)]  (single batch; no calendar)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Callable

import requests
from bs4 import BeautifulSoup

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


BASE_URL = "https://blogbbm.com"

# Posts soportados. Cada uno aporta una colección distinta:
#  - signal_inject: keywords que se garantizan en la descripción para que
#    `detect_signals` levante el signal_type adecuado (los del post están
#    implícitos por curación: si está en /capas_variantes/ es por
#    definición un variant cover; si está en /volumes-especiais-com-itens/
#    es un special_edition con bonus).
#  - source_suffix: discrimina el source name en items.jsonl.
#  - tag: discrimina la categoría en `tags`.
#  - layout: "AB" (default) usa la heurística title-driven que cubre los
#    layouts A (gallery div ANTES del título, /capas_variantes/) y B
#    (título con (MM/YYYY) + figures después, /volumes-especiais/).
#    "C" usa el parser de tablas supsystic (Layout C, /guia-box-de-manga/).
BBM_POSTS: tuple[dict[str, str], ...] = (
    {
        "url": f"{BASE_URL}/2020/10/09/capas_variantes/",
        "source_suffix": "Capas Variantes",
        "tag": "capas-variantes",
        "signal_inject": "Capa variante / variant cover.",
        "layout": "AB",
    },
    {
        "url": f"{BASE_URL}/2024/05/15/guia-volumes-especiais-de-mangas-com-itens-especiais/",
        "source_suffix": "Volumes Especiais",
        "tag": "volumes-especiais",
        "signal_inject": "Edição especial com brinde / special edition with bonus.",
        "layout": "AB",
    },
    {
        "url": f"{BASE_URL}/2024/02/09/guia-box-de-manga-no-brasil/",
        "source_suffix": "Box de Mangá",
        "tag": "box-de-manga",
        "signal_inject": "Cofre / box set / boxset.",
        "layout": "C",
    },
)


def _virtual_source(source_suffix: str, tag: str) -> Source:
    return Source(
        name=f"BR - Biblioteca Brasileira de Mangás ({source_suffix})",
        url=BASE_URL,
        country="Brasil",
        language="Portugués",
        publisher="",                 # se sobreescribe por item desde el prose
        source_class="trusted_media",  # blog comunitario curado
        kind="wiki",
        enabled=True,
        tags=["wiki", "blogbbm", "brasil", tag],
        notes="blogbbm.com — guías curadas de ediciones especiales BR",
        selectors={},
        max_pages=0,
        purity="manga_only",  # ambos posts son 100% manga curado
    )


# Editoras conocidas BR (regex sobre prose). El orden no importa para
# detección — sí cuál matchea primero (devolvemos display canónico).
_EDITORA_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\beditora\s+JBC\b", re.IGNORECASE), "JBC"),
    (re.compile(r"\beditora\s+NewPOP\b", re.IGNORECASE), "NewPOP"),
    (re.compile(r"\beditora\s+Panini\b", re.IGNORECASE), "Panini"),
    (re.compile(r"\beditora\s+Pipoca\s*&\s*Nanquim\b", re.IGNORECASE),
        "Pipoca & Nanquim"),
    (re.compile(r"\beditora\s+MPEG\b", re.IGNORECASE), "MPEG"),
    (re.compile(r"\beditora\s+Devir\b", re.IGNORECASE), "Devir"),
    (re.compile(r"\beditora\s+Conrad\b", re.IGNORECASE), "Conrad"),
    # Sin "editora" prefix por si aparece pelado.
    (re.compile(r"\bpela\s+JBC\b", re.IGNORECASE), "JBC"),
    (re.compile(r"\bpela\s+NewPOP\b", re.IGNORECASE), "NewPOP"),
    (re.compile(r"\bpela\s+Panini\b", re.IGNORECASE), "Panini"),
    (re.compile(r"\bpela\s+Pipoca\s*&\s*Nanquim\b", re.IGNORECASE),
        "Pipoca & Nanquim"),
    (re.compile(r"\bpela\s+MPEG\b", re.IGNORECASE), "MPEG"),
)

# Precio en R$ — devuelve la primera ocurrencia (price normal, no premium).
_PRICE_RE = re.compile(r"R\$\s*([\d.,]+)")

# Volumen del título: "#NN" o "Vol N" o "Volume N" o "Tomo N".
_VOL_RE = re.compile(
    r"(?:#|Vol(?:ume)?\.?\s*|Tomo\s*|n[°º]?\s*)(\d{1,4})\b",
    re.IGNORECASE,
)

# Fecha en prose: "janeiro de 2014", "outubro de 2017", "05/2023", "fev/2024".
_MONTHS_PT: dict[str, str] = {
    "janeiro": "01", "fevereiro": "02", "março": "03", "marco": "03",
    "abril": "04", "maio": "05", "junho": "06", "julho": "07",
    "agosto": "08", "setembro": "09", "outubro": "10",
    "novembro": "11", "dezembro": "12",
}
_DATE_RE_LONG = re.compile(
    r"\b(janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})\b",
    re.IGNORECASE,
)
_DATE_RE_SHORT = re.compile(r"\b(\d{1,2})/(\d{4})\b")  # 05/2023


def _extract_date(prose: str) -> str:
    """Devuelve YYYY-MM o '' si no detecta fecha. Usa la PRIMERA ocurrencia
    (probablemente la fecha de lanzamiento mencionada al principio del prose)."""
    if not prose:
        return ""
    m = _DATE_RE_LONG.search(prose)
    if m:
        mon = _MONTHS_PT.get(m.group(1).lower(), "")
        if mon:
            return f"{m.group(2)}-{mon}"
    m2 = _DATE_RE_SHORT.search(prose)
    if m2:
        mm = m2.group(1).zfill(2)
        if 1 <= int(mm) <= 12:
            return f"{m2.group(2)}-{mm}"
    return ""


def _node_imgs(node) -> list[dict[str, str]]:
    """Extrae todas las imágenes de `wp-content/uploads/` adentro del nodo
    (recursivo). Devuelve lista de {src, alt} con URLs sin query params
    y con el proxy `i0.wp.com` quitado para que el espejo local descargue
    desde blogbbm.com directo."""
    out: list[dict[str, str]] = []
    for img in node.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
        if "wp-content/uploads" not in src:
            continue
        src_clean = src.split("?", 1)[0]
        # i0.wp.com / i1.wp.com / i2.wp.com → blogbbm.com directo.
        src_clean = re.sub(
            r"^https?://i\d+\.wp\.com/", "https://", src_clean,
        )
        alt = (img.get("alt") or "").strip()
        out.append({"src": src_clean, "alt": alt})
    return out


# Title shape: short `<p>` con marker de volumen (#NN / Vol N / Tomo N) o
# parenthesized date (MM/YYYY). Si además hay un link `/manga/<slug>/`
# adentro, es muy probablemente un título también.
_TITLE_DATE_PAREN = re.compile(r"\(\s*\d{1,2}/\d{4}")  # "(12/2021)"


# Prefijos narrativos que descartan un `<p>` como título. Cuidado al
# extender: "no " choca con títulos legítimos como "No Game No Life",
# así que usamos prefijos de 2 palabras donde es ambiguo.
_TITLE_REJECT_PREFIXES: tuple[str, ...] = (
    "em janeiro", "em fevereiro", "em março", "em marco", "em abril",
    "em maio", "em junho", "em julho", "em agosto", "em setembro",
    "em outubro", "em novembro", "em dezembro", "em meados", "em fins",
    "em início", "em inicio", "em 20", "em 19",
    "no brasil", "no japão", "no japao", "no início", "no inicio",
    "no entanto", "na época", "na epoca", "na altura",
    "assim ", "assim,", "a versão", "a versao", "a edição", "a edicao",
    "a editora", "após", "apos", "esse ", "esta ", "este ", "há que",
    "ha que", "fora isso", "veja a lista", "atualizado", "texto atualizado",
    "o preço", "o preco",
    # Sub-bullets dentro de un entry (sin `<hr>` antes).
    "-volume", "volume #", "o volume",
)


def _is_title_p(p, lenient: bool = False, max_len: int = 200) -> bool:
    """Devuelve True si este `<p>` tiene shape de título de entry.

    Modo estricto (`lenient=False`, default):
    - Layout B (volumes-especiais): `<p>` con fecha parenthesized
      `(MM/YYYY)` o `(MM/YYYY – MM/YYYY)`.
    - Layout A con ficha: el `<p>` es esencialmente un link a
      `/manga/<slug>/` cubriendo ≥80% del texto.
    - El volume marker `#NN` solo NO es suficiente — la prose narrativa
      menciona volúmenes ("Volume #21 veio com…") y se colaba como title.

    Modo lenient (`lenient=True`): el parser lo activa cuando
    contextualmente sabe que el próximo `<p>` debe ser un título
    (acabamos de ver gallery div y pending_imgs está cargado pero no
    asignado). En lenient basta con cualquiera de:
    - volume marker (`#NN`, `Vol N`, `Tomo N`)
    - fecha parenthesized
    - ficha link
    - `<strong>` envolviendo el texto entero (header bold típico WP)
    Los rejects narrativos siguen aplicando para no agarrar prose por
    accidente.
    """
    if not p or p.name != "p":
        return False
    txt = p.get_text(" ", strip=True)
    if not txt or len(txt) > max_len:
        return False
    lower = txt[:30].lower()
    if any(lower.startswith(r) for r in _TITLE_REJECT_PREFIXES):
        return False
    has_paren_date = bool(_TITLE_DATE_PAREN.search(txt))
    has_ficha_bold = False
    a = p.find("a", href=re.compile(r"^https://blogbbm\.com/manga/[^/]+/?$"))
    if a:
        a_text = a.get_text(" ", strip=True)
        if a_text and len(a_text) >= 0.8 * len(txt):
            has_ficha_bold = True
    if has_paren_date or has_ficha_bold:
        return True
    if not lenient:
        return False
    if _VOL_RE.search(txt):
        return True
    strong = p.find(["strong", "b"])
    if strong and strong.get_text(" ", strip=True) == txt:
        return True
    return False


def _pick_variant_image(imgs: list[dict[str, str]]) -> str:
    """De la lista de imágenes del gallery, elige la VARIANTE como image_url
    canónica. Heurística: alt o filename con 'variant'/'b.jpg'/'b-')."""
    if not imgs:
        return ""
    for img in imgs:
        alt = img["alt"].lower()
        src_lower = img["src"].lower()
        if "variant" in alt or "variante" in alt or "variant" in src_lower:
            return img["src"]
        # Suffix 'b' del filename común en BBM (ej: genshiken06b.jpg).
        fn = src_lower.rsplit("/", 1)[-1]
        stem = fn.rsplit(".", 1)[0]
        if stem.endswith("b") and len(stem) > 1:
            return img["src"]
    # Fallback: segunda imagen (BBM siempre pone normal primero, variant después).
    if len(imgs) >= 2:
        return imgs[1]["src"]
    return imgs[0]["src"]


def _series_slug_from_ficha(ficha_url: str) -> str:
    """De https://blogbbm.com/manga/genshiken/ → 'genshiken'."""
    if not ficha_url:
        return ""
    m = re.search(r"/manga/([^/?#]+)/?", ficha_url)
    return m.group(1) if m else ""


def _image_stem(image_url: str) -> str:
    """De /wp-content/uploads/2022/02/Wotakoi.jpg → 'wotakoi-2022-02'.
    Sirve como discriminante por-variant en URL sintética."""
    if not image_url:
        return ""
    m = re.search(r"/wp-content/uploads/(\d{4})/(\d{2})/([^/?#]+)", image_url)
    if not m:
        return ""
    year, month, fn = m.groups()
    stem = fn.rsplit(".", 1)[0]
    stem = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return f"{stem}-{year}-{month}" if stem else ""


def _make_synthetic_url(
    post_url: str,
    ficha_url: str,
    volume: str,
    image_url: str,
) -> str:
    """Construye un URL único por entry.

    Usamos un **query param** `?bbm-entry=vol-NN-<image-stem>` (no fragment)
    porque `normalize_url_for_dedup` strippea fragments. El param NO está
    en `TRACKING_PARAMS` así que sobrevive a la normalización y discrimina
    cada variant aunque compartan la misma ficha. Clickeando el link, BBM
    ignora el param desconocido y muestra la ficha del manga.
    """
    stem = _image_stem(image_url) or "entry"
    entry_id = f"vol-{volume}-{stem}" if volume else stem
    if ficha_url:
        sep = "&" if "?" in ficha_url else "?"
        return f"{ficha_url.rstrip('/')}{sep}bbm-entry={entry_id}"
    sep = "&" if "?" in post_url else "?"
    return f"{post_url.rstrip('/')}{sep}bbm-entry={entry_id}"


def parse_post(
    html_text: str,
    post_meta: dict,
) -> list[Candidate]:
    """Parsea un post-guía de BBM y devuelve un Candidate por entry.

    `post_meta` es uno de los dicts de BBM_POSTS (url, source_suffix, tag,
    signal_inject, layout). Dispatch interno según `layout`:
    - "AB" (default): heurística title-driven (gallery div / figures /
      `<hr>` separators).
    - "C": parser de tablas supsystic (cada `<tr>` = entry; col 0 img,
      col 1 título, col 2 editora, col 3 fecha YYYY.MM).
    """
    if not html_text or len(html_text) < 5000:
        return []
    layout = post_meta.get("layout", "AB")
    if layout == "C":
        return _parse_layout_c(html_text, post_meta)
    return _parse_layout_ab(html_text, post_meta)


def _parse_layout_ab(html_text: str, post_meta: dict) -> list[Candidate]:
    """Parser histórico de los posts /capas_variantes/ y /volumes-especiais/."""
    soup = BeautifulSoup(html_text, "html.parser")
    ec = soup.find(class_="entry-content")
    if not ec:
        return []

    source = _virtual_source(post_meta["source_suffix"], post_meta["tag"])
    post_url = post_meta["url"]
    inject = post_meta.get("signal_inject", "")

    candidates: list[Candidate] = []
    current: dict | None = None
    # Buffer de imágenes "huérfanas" — aparecen entre dos entries (Layout A:
    # gallery viene ANTES del título). Al detectar el próximo título, este
    # buffer se mueve a sus imgs. Se llena cuando estamos "suspendidos"
    # (después de un `<hr>` y antes del próximo título).
    pending_imgs: list[dict[str, str]] = []
    suspended = True   # antes del primer título estamos suspendidos.

    def flush() -> None:
        if not current:
            return
        if not current.get("title") or not current.get("imgs"):
            return
        candidates.append(_build_candidate(current, source, post_url, inject))

    for child in ec.children:
        name = getattr(child, "name", None)
        if name is None:
            continue
        # Title `<p>` → flush previo y abre nuevo entry. Hereda pending_imgs.
        # Cuando hay pending_imgs cargado y estamos suspendidos, sabemos
        # contextualmente que el próximo `<p>` no-narrativo debe ser un
        # título — pasamos `lenient=True` para aceptar Layout A entries
        # sin ficha link ni parens-date.
        lenient = suspended and bool(pending_imgs)
        if name == "p" and _is_title_p(child, lenient=lenient):
            flush()
            txt = clean_text(child.get_text(" ", strip=True))
            current = {
                "imgs": list(pending_imgs),
                "title": txt[:260],
                "ficha_url": "",
                "prose_parts": [],
            }
            pending_imgs = []
            suspended = False
            a = child.find(
                "a",
                href=lambda h: bool(h) and re.match(
                    r"^https://blogbbm\.com/manga/[^/]+/?$", h),
            )
            if a:
                current["ficha_url"] = a["href"]
            continue
        # `<hr>` → suspende collection. Las próximas imgs van a pending,
        # no a current (es la frontera entre entries en Layout A).
        if name == "hr":
            suspended = True
            continue
        # `<p>` normal → prose (sólo si hay current activo y no suspendidos).
        if name == "p":
            if current is None or suspended:
                # `<p>` post-`<hr>` pero NO title — puede ser prose de un
                # entry largo (post 2 separa con `<hr>` title/prose). Volvemos
                # a "no suspendido" para que la prose se acumule.
                if current is not None:
                    suspended = False
                else:
                    continue
            txt = clean_text(child.get_text(" ", strip=True))
            if txt:
                current["prose_parts"].append(txt)
            for img in _node_imgs(child):
                current["imgs"].append(img)
            continue
        # Imágenes — distinguimos por tag:
        # - `<div>` (gallery block WP): **siempre** a pending_imgs.
        #   En ambos layouts el gallery div aparece ANTES del título.
        #   En Layout A multi-entry chunks NO hay `<hr>` entre entries,
        #   así que sin esta regla las galerías se asociaban al entry
        #   anterior. Tratar gallery como "entre-entries" siempre alinea
        #   correctamente. También fuerza `suspended=True` (entramos en
        #   modo "esperando próximo título").
        # - `<figure>` (Layout B): al current. En post 2 las figures
        #   están adentro del entry, después del título.
        if name == "div":
            imgs = _node_imgs(child)
            if imgs:
                pending_imgs.extend(imgs)
                suspended = True
            continue
        if name == "figure":
            imgs = _node_imgs(child)
            if not imgs:
                continue
            if current is not None and not suspended:
                current["imgs"].extend(imgs)
            else:
                pending_imgs.extend(imgs)
            continue
        # Otros elementos (script, blockquote, h3, etc.) los ignoramos.

    flush()
    return candidates


# --- Layout C (supsystic tables: /guia-box-de-manga-no-brasil/) ----------

# Imagen placeholder de "sin imagen" en BBM box post — el wiki marca rows
# pendientes con este png. No es portada real.
_BBM_PLACEHOLDER_PATTERNS: tuple[str, ...] = (
    "Sem-Imagem",
    "sem-imagem",
    "/Sem-Imagem.png",
)

# Fecha YYYY.MM. "Em breve" / "" → release_date vacío (preventa).
_LAYOUT_C_DATE_RE = re.compile(r"^\s*(\d{4})\.(\d{1,2})\s*$")


def _slugify_pt(text: str) -> str:
    """Slug minimalista PT-BR: lowercase, ASCII, palabras separadas por '-'.
    Sirve como disambiguator único en URL sintética por-entry."""
    if not text:
        return ""
    s = text.lower()
    # Reemplazos manuales para diacríticos PT-BR comunes (sin unicodedata).
    for src, dst in (
        ("ã", "a"), ("á", "a"), ("à", "a"), ("â", "a"),
        ("é", "e"), ("ê", "e"),
        ("í", "i"),
        ("ó", "o"), ("ô", "o"), ("õ", "o"),
        ("ú", "u"), ("ü", "u"),
        ("ç", "c"),
        ("ñ", "n"),
    ):
        s = s.replace(src, dst)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80]


def _is_placeholder_image(src: str) -> bool:
    if not src:
        return True
    return any(p in src for p in _BBM_PLACEHOLDER_PATTERNS)


def _clean_wp_image_url(src: str) -> str:
    """Quita el proxy i0.wp.com/ y query params (mismo que _node_imgs)."""
    if not src:
        return ""
    src = src.split("?", 1)[0]
    src = re.sub(r"^https?://i\d+\.wp\.com/", "https://", src)
    return src


def _parse_layout_c(html_text: str, post_meta: dict) -> list[Candidate]:
    """Parsea el post /guia-box-de-manga-no-brasil/ — 2 tablas supsystic
    con esquema [imagen, título, editora, fecha YYYY.MM].

    El sitio renderiza ambas tablas (78=desde 2013, 79=hasta 2012) en HTML
    server-side. Cada `<tr>` data row contiene un Box brasileño con:
      col 0: <img> de la cover (o 'Sem-Imagem.png' placeholder).
      col 1: título del manga ("Pink Heart Jam - Deluxe Box").
      col 2: editora (Panini / JBC / NewPOP / Nova Sampa / Conrad / etc.).
      col 3: fecha YYYY.MM o "Em breve" (preventa) o vacío.

    URL sintética por entry: `?bbm-entry=box-<slug-from-title>`.
    Sin imagen real, igualmente generamos candidate (el frontend cae al
    placeholder 📚). Sin fecha, queda como preventa con release_date="".
    """
    soup = BeautifulSoup(html_text, "html.parser")
    ec = soup.find(class_="entry-content")
    if not ec:
        return []

    source = _virtual_source(post_meta["source_suffix"], post_meta["tag"])
    post_url = post_meta["url"]
    inject = post_meta.get("signal_inject", "")

    candidates: list[Candidate] = []
    seen_urls: set[str] = set()

    for table in ec.find_all("table", class_="supsystic-table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        # Skip header (first <tr>). Data rows: 1..N
        for tr in rows[1:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) < 4:
                continue
            img = cells[0].find("img")
            img_src = ""
            if img:
                img_src = (img.get("src") or img.get("data-src")
                           or img.get("data-lazy-src") or "")
            title = clean_text(cells[1].get_text(" ", strip=True))
            publisher = clean_text(cells[2].get_text(" ", strip=True))
            date_raw = clean_text(cells[3].get_text(" ", strip=True))
            if not title:
                continue
            # release_date: YYYY.MM → YYYY-MM; "Em breve" / vacío → "".
            release_date = ""
            m = _LAYOUT_C_DATE_RE.match(date_raw)
            if m:
                month_num = int(m.group(2))
                if 1 <= month_num <= 12:
                    release_date = f"{m.group(1)}-{month_num:02d}"
            # Image — si es placeholder, no la usamos.
            image_url = ""
            if img_src and not _is_placeholder_image(img_src):
                image_url = _clean_wp_image_url(img_src)
            # URL sintética por título (no hay ficha link en las tablas).
            slug = _slugify_pt(title) or "box"
            sep = "&" if "?" in post_url else "?"
            url = f"{post_url.rstrip('/')}{sep}bbm-entry=box-{slug}"
            if url in seen_urls:
                # Misma fila replicada (raro, pero por las dudas). Skipping.
                continue
            seen_urls.add(url)
            # Description: inject (garantiza box_set signal) + editora + estado
            descr_parts: list[str] = [inject]
            if publisher:
                descr_parts.append(f"Editora: {publisher}.")
            if date_raw and not release_date:
                # "Em breve" o similar → preventa
                descr_parts.append(f"Status: {date_raw}.")
            description = " ".join(descr_parts).strip()[:2500]
            if publisher:
                source.publisher = publisher
            cand = candidate_from_source(
                source,
                title=title,
                url=url,
                description=description,
                published_at=release_date,
            )
            cand.image_url = image_url
            cand.release_date = release_date
            cand.tags = list(source.tags) + ["bbm-box"]
            score_candidate(cand)
            candidates.append(cand)
    return candidates


def _build_candidate(
    entry: dict,
    source: Source,
    post_url: str,
    inject: str,
) -> Candidate:
    """Construye un Candidate desde el dict acumulado en parse_post."""
    title = entry["title"]
    prose = " ".join(entry["prose_parts"])

    # Volume del título (preferimos) o del prose.
    volume = ""
    m = _VOL_RE.search(title)
    if m:
        volume = m.group(1).lstrip("0") or m.group(1)
    if not volume:
        m2 = _VOL_RE.search(prose[:200])
        if m2:
            volume = m2.group(1).lstrip("0") or m2.group(1)

    # Publisher del prose.
    publisher = ""
    for pat, display in _EDITORA_PATTERNS:
        if pat.search(prose):
            publisher = display
            break

    # Price.
    price = ""
    pm = _PRICE_RE.search(prose)
    if pm:
        price = pm.group(0).replace(" ", "")

    # Release date YYYY-MM. Probamos primero el título (post 2 lleva
    # `(MM/YYYY)` ahí); si no aparece, vamos al prose.
    release_date = _extract_date(title) or _extract_date(prose)

    # Variant cover image (preferida) y URL sintética por entry.
    image_url = _pick_variant_image(entry["imgs"])
    url = _make_synthetic_url(
        post_url=post_url,
        ficha_url=entry["ficha_url"],
        volume=volume,
        image_url=image_url,
    )

    # Description: prose + inject (garantiza signal_type) + publisher hint.
    descr_parts: list[str] = [prose] if prose else []
    if inject:
        descr_parts.append(inject)
    if publisher and publisher.lower() not in prose.lower()[:120]:
        descr_parts.append(f"Editora: {publisher}.")
    description = " ".join(descr_parts).strip()[:2500]

    if publisher:
        source.publisher = publisher

    cand = candidate_from_source(
        source,
        title=title,
        url=url,
        description=description,
        published_at=release_date,
    )
    cand.image_url = image_url
    # Carrusel multi-imagen: BBM expone gallery con 2+ imgs por entry (normal +
    # variant cover típicamente). Antes _pick_variant_image() elegía la variant
    # y descartábamos la regular; ahora preservamos TODAS en images[] con la
    # variant como cover y las demás como gallery (para mostrar comparación
    # normal vs variant en el modal del dashboard).
    if entry["imgs"]:
        seen_urls: set[str] = set()
        images_list: list[dict[str, str]] = []
        # 1) Cover = variant elegida.
        if image_url and image_url not in seen_urls:
            images_list.append({
                "url": image_url, "kind": "gallery", "description": ""
            })
            seen_urls.add(image_url)
        # 2) Resto del gallery como entries kind=gallery, en orden BBM.
        for im in entry["imgs"]:
            src = im.get("src") or ""
            if not src or src in seen_urls:
                continue
            seen_urls.add(src)
            alt = (im.get("alt") or "").strip()
            images_list.append({
                "url": src, "kind": "gallery",
                "description": alt[:120],
            })
        if len(images_list) > 1:
            cand.images = images_list
    cand.release_date = release_date
    cand.price = price
    cand.tags = list(source.tags) + [f"bbm-vol:{volume}"] if volume else list(source.tags)

    score_candidate(cand)
    return cand


def fetch_post(
    session: requests.Session,
    post_url: str,
    timeout: tuple[int, int] = (10, 30),
) -> str | None:
    """Descarga el HTML del post. Devuelve None si falla."""
    try:
        resp = session.get(post_url, timeout=timeout)
        resp.raise_for_status()
        if not resp.encoding:
            resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    except requests.RequestException as exc:
        print(f"[blogbbm] WARN {post_url}: {exc}")
        return None


def bootstrap(
    year_from: int,        # noqa: ARG001 (signature compat con dispatcher)
    month_from: int,       # noqa: ARG001
    year_to: int,          # noqa: ARG001
    month_to: int,         # noqa: ARG001
    session: requests.Session,
    sleep_seconds: float = 0.0,  # noqa: ARG001 (sólo 2 posts, no hace falta)
    timeout: tuple[int, int] = (15, 45),
    min_score: int = 0,
    fetch_details: bool = False,  # noqa: ARG001 (no detail-fetch — el post trae todo)
    posts: tuple[dict, ...] = BBM_POSTS,
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Descarga los posts BBM configurados y devuelve la lista de Candidates.

    Los posts son curated guides actualizadas continuamente; no hay
    rango año/mes que respetar. Lo aceptamos en la signature solo por
    compat con el dispatcher de manga_watch.py.
    """
    print(f"[blogbbm] procesando {len(posts)} post(s) curados")
    candidates: list[Candidate] = []
    seen_urls: set[str] = set()
    for post_meta in posts:
        url = post_meta["url"]
        print(f"[blogbbm] GET {url}")
        html = fetch_post(session, url, timeout=timeout)
        if not html:
            continue
        entries = parse_post(html, post_meta)
        print(f"[blogbbm] {len(entries)} entries del post '{post_meta['source_suffix']}'")
        post_kept: list[Candidate] = []
        for cand in entries:
            if min_score and cand.score < min_score:
                continue
            if cand.url in seen_urls:
                continue
            seen_urls.add(cand.url)
            candidates.append(cand)
            post_kept.append(cand)
        if flush_fn and post_kept:
            flush_fn(post_kept)
    print(f"[blogbbm] terminado: {len(candidates)} candidates con score>={min_score}")
    return candidates


def iter_year_months(
    year_from: int, month_from: int,
    year_to: int, month_to: int,   # noqa: ARG001
) -> list[tuple[int, int]]:
    """BBM no tiene calendario mensual; devolvemos un único batch."""
    return [(year_from, month_from)]


if __name__ == "__main__":
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; manga-watch-personal/0.2)"
    cands = bootstrap(2024, 1, 2026, 12, session=s, min_score=0)
    print(f"\nTotal: {len(cands)} candidates")
    for c in cands[:10]:
        print(f"  [{c.score:3d}] {c.publisher[:15]:15s} | {c.signal_types} | {c.title[:60]}")
