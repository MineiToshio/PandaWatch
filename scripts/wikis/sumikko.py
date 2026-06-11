"""Parser de comic.sumikko.info — コミック新刊チェック (Japón).

Catálogo japonés especializado en **ediciones limitadas y especiales**
de manga (限定版 / 特装版 / 完全版 / 同梱版 / BOX / con extras como
アクリルスタンド, 小冊子, ブロマイド, etc.). Cubre la dimensión "qué
EDICIÓN es" que las sources JP regulares (Rakuten, Kadokawa Store,
Sanyodo) no marcan explícitamente, y es complementario a
`wikis/booksprivilege.py` (que cubre 店舗特典 / extras de tienda).

Estructura del listing /limited-item/:

    <a href="/item-select/<isbn10>"><div class="Types"><span class="type type-tag">コミック</span></div>
       <div class="name">勇者... 8 アクリルスタンド付き特装版</div>
       <div class="sab"><span>26年10月23日(金)</span><span>久遠まこと/石のやっさん</span></div>
       <div class="sab"><span>MFコミックス</span><span>KADOKAWA</span></div>
       <div class="image"><img class="lazy" data-src="https://images-na.ssl-images-amazon.com/images/P/<isbn>.09_*.jpg"/></div>
    </a>

Discovery:
- `/limited-item/?p=N` paginado, 90 items por página (N=1..~32 cubren todo).
- Total declarado en la home: ~3178 items.
- Endpoints alternativos no usados por ahora (más caros, menos cobertura):
  `/month-list/item/YYYYMM/` (catálogo COMPLETO del mes, no solo limited).
  `/weekly-list/item/YYYY-MM-DD/` ídem semanal.
  `/rss.xml` feed.

Estrategia: iteramos `?p=N` desde 1 hasta encontrar página vacía
(early-stop). Cada página da metadata completa — NO se necesita hitear
detail pages (`/item-select/<isbn>`).

Tag de tipo: el sitio marca cada item con `<span class="type type-tag">`,
pero esa etiqueta describe el **TIPO DEL EXTRA** que trae la edición
limitada (`CD等` cuando el bonus es un CD/drama, `カセット等` cuando es
una cassette, `単行本` para la categoría base, etc.), NO si el producto
es manga o no. Verificado contra fixtures reales (2026-05): items
etiquetados `カセット、ＣＤ等` incluyen "薬屋のひとりごと 22 マスキング
テープ付特装版" (Apothecary Diaries vol 22 — manga puro). Por eso por
default NO filtramos por tipo. `accept_types=frozenset()` (default) =
aceptar todo lo que esté en `/limited-item/` porque la curación del
sitio ya garantiza que son ediciones especiales de manga.

API pública (paralela a blogbbm.py / booksprivilege.py):
    parse_listing_page(html_text) -> list[Candidate]
    fetch_html(session, url, timeout) -> str | None
    bootstrap(yf, mf, yt, mt, session, ...) -> list[Candidate]
    iter_year_months(yf, mf, yt, mt) -> [(yf, mf)]  (single batch; no calendar)
"""

from __future__ import annotations

import re
import sys
import time
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


BASE_URL = "https://comic.sumikko.info"
LISTING_URL_TEMPLATE = "https://comic.sumikko.info/limited-item/?p={page}"
DETAIL_URL_TEMPLATE = "https://comic.sumikko.info/item-select/{isbn}"

# Tipos aceptados por default. Configurable via bootstrap(accept_types=...).
# Por default: frozenset vacío = NO filtramos por tipo, porque el `type-tag`
# del sitio describe el extra de la edición (CD, cassette, etc.) y no el
# producto en sí. Toda /limited-item/ es manga por curación del sitio.
# Si querés acotar a un solo tipo, pasá frozenset({"コミック"}).
_DEFAULT_ACCEPT_TYPES: frozenset[str] = frozenset()

# Date format JP: "26年10月23日(金)" → 2026-10-23.
# El parser asume siglo 20XX (válido desde 2020 al menos +50 años, sin
# riesgo realista de colisión con el siglo XX en este sitio).
_DATE_RE = re.compile(r"(\d{1,2})年(\d{1,2})月(\d{1,2})日")


# Volume del título: "9", "(13)", "Vol. 5", "第5巻", " 8 アクリル", etc.
# El sitio pone el volumen como dígito separado del título (ej: "魔法使いの嫁 25 特装版").
# Heurística: el último dígito ≤ 4 chars al final del título o antes de un
# keyword 限定版/特装版/etc.
_VOL_PATTERNS = (
    re.compile(r"\((\d{1,4})\)"),                          # "Title (18)"
    re.compile(r"第\s*(\d{1,4})\s*巻"),                     # "第18巻"
    re.compile(r"\b[Vv]ol\.?\s*(\d{1,4})\b"),              # "vol. 18"
    re.compile(r"(?<![\d])(\d{1,4})\s*(?=(?:限定版|特装版|完全版|同梱版|愛蔵版|アクリル|オリジナル|BOX|缶|缶バッジ|缶バッヂ|ブロマイド|小冊子|ポストカード|ステッカー|フィギュア))"),
    re.compile(r"\s(\d{1,3})\s*$"),                        # "Title 8" sin más
)

# Publisher canónico del 2do span de sab[1]. Mapeamos los más frecuentes
# del corpus (los no listados quedan literales; el skill /watch-standardize-catalog
# los canonicaliza después).
_PUBLISHER_MAP: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^KADOKAWA$|^角川"), "Kadokawa"),
    (re.compile(r"^講談社"), "Kodansha"),
    (re.compile(r"^小学館"), "Shogakukan"),
    (re.compile(r"^集英社"), "Shueisha"),
    (re.compile(r"^白泉社"), "Hakusensha"),
    (re.compile(r"^秋田書店"), "Akita Shoten"),
    (re.compile(r"^一迅社"), "Ichijinsha"),
    (re.compile(r"^スクウェア・?エニックス|^SQUARE\s*ENIX"), "Square Enix"),
    (re.compile(r"^双葉社"), "Futabasha"),
    (re.compile(r"^竹書房"), "Takeshobo"),
    (re.compile(r"^徳間書店"), "Tokuma"),
    (re.compile(r"^フロンティアワークス"), "Frontier Works"),
    (re.compile(r"^マッグガーデン"), "Mag Garden"),
    (re.compile(r"^イースト・?プレス"), "East Press"),
    (re.compile(r"^芳文社"), "Houbunsha"),
    (re.compile(r"^少年画報社"), "Shounen Gahosha"),
    (re.compile(r"^リブレ"), "Libre"),
    (re.compile(r"^幻冬舎"), "Gentosha"),
    (re.compile(r"^ホビージャパン"), "Hobby Japan"),
    (re.compile(r"^オーバーラップ"), "Overlap"),
    (re.compile(r"^アスキー・?メディアワークス|^ASCII"), "ASCII Media Works"),
    (re.compile(r"^祥伝社"), "Shodensha"),
    (re.compile(r"^TOブックス"), "TO Books"),
    (re.compile(r"^ブシロード"), "Bushiroad Works"),
    (re.compile(r"^新潮社"), "Shinchosha"),
    (re.compile(r"^リイド"), "Leed"),
    (re.compile(r"^エンターブレイン"), "Enterbrain"),
    (re.compile(r"^太田出版"), "Ohta Publishing"),
    (re.compile(r"^朝日新聞出版"), "Asahi Shimbun"),
)


def _virtual_source() -> Source:
    return Source(
        name="JP - Sumikko (限定版・特装版)",
        url=BASE_URL,
        country="Japón",
        language="Japonés",
        publisher="",               # se rellena por item desde sab[1]
        source_class="trusted_media",
        kind="wiki",
        enabled=True,
        tags=["wiki", "sumikko", "japon", "limited"],
        notes="comic.sumikko.info — catálogo JP de 限定版/特装版 (3178 items aprox.)",
        selectors={},
        max_pages=0,
        purity="manga_only",        # el sitio cura solo limited/special editions
    )


def _publisher_canonical(raw: str) -> str:
    """Mapea un publisher japonés a canonical si está en _PUBLISHER_MAP;
    si no, devuelve el raw para que el skill /watch-standardize-catalog lo
    canonicalice después."""
    if not raw:
        return ""
    for pat, display in _PUBLISHER_MAP:
        if pat.search(raw):
            return display
    return raw.strip()


def _parse_jp_date(raw: str) -> str:
    """De '26年10月23日(金)' → '2026-10-23'. Vacío si no parsea."""
    if not raw:
        return ""
    m = _DATE_RE.search(raw)
    if not m:
        return ""
    yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
    # 2-digit year — asumimos 20XX (el sitio no tiene items pre-2000).
    year = 2000 + yy if yy < 100 else yy
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return ""
    return f"{year:04d}-{mm:02d}-{dd:02d}"


# Spans entre corchetes de título de obra: 『…』 y 「…」. Lo que está ADENTRO
# es parte del nombre de la obra (p.ej. サツジンゲーム『配神限定』) — un 限定
# ahí NO indica edición limitada.
_BRACKET_SPAN_RE = re.compile(r"『[^』]*』|「[^」]*」")

# Marcadores de edición especial que deben aparecer FUERA de los corchetes
# para que el item sea emitido (gate anti falso-positivo, ver
# _has_edition_marker_outside_brackets).
_EDITION_MARKER_RE = re.compile(
    r"特装版|限定版|完全版|愛蔵版|豪華版|同梱|付き|付録|BOX|ＢＯＸ|セット|画集|特典",
    re.IGNORECASE,
)

# Caracteres "de contenido": alfanuméricos ASCII + kana + kanji (CJK).
_CONTENT_CHAR_RE = re.compile(r"[0-9A-Za-z぀-ヿ㐀-鿿豈-﫿]")


def _strip_bracketed_spans(title: str) -> str:
    """Quita los spans 『…』/「…」 (títulos de obra citados) del título."""
    return _BRACKET_SPAN_RE.sub(" ", title or "")


def _has_edition_marker_outside_brackets(title: str) -> bool:
    """True si el título tiene un marcador de edición FUERA de 『』/「」.

    El parser inyecta boilerplate "限定版・特装版 / limited edition…" en la
    description de TODOS los items, así que sin este gate cualquier título
    cuyo único 限定 está DENTRO de corchetes (parte del nombre de la obra)
    se vuelve falso positivo. Auditado 2026-06-10 sobre los 2671 items
    sumikko existentes: el gate sólo excluye los 2 falsos positivos
    confirmados (サツジンゲーム『配神限定』) — cero riesgo de falso negativo.
    """
    return bool(_EDITION_MARKER_RE.search(_strip_bracketed_spans(title)))


def _extract_volume(title: str) -> str:
    """Extrae volumen del título JP. Devuelve '' si no detecta."""
    if not title:
        return ""
    for pat in _VOL_PATTERNS:
        m = pat.search(title)
        if m:
            v = m.group(1).lstrip("0") or m.group(1)
            return v
    return ""


def _item_block_to_candidate(
    block_html: str,
    accept_types: frozenset[str],
) -> Candidate | None:
    """Parsea un bloque `<a href='/item-select/...'>...</a>` y construye un
    Candidate. Devuelve None si:
    - no hay ISBN en la URL.
    - el tipo no está en `accept_types` (default: solo コミック).
    - no hay título.
    """
    soup = BeautifulSoup(block_html, "html.parser")
    a = soup.find("a", href=re.compile(r"/item-select/(\d{10,13})"))
    if not a:
        return None
    m = re.search(r"/item-select/(\d{10,13})", a.get("href", ""))
    if not m:
        return None
    isbn = m.group(1)
    # Solo aceptamos ISBN-10 (10 chars, dígitos). Algunos productos
    # pueden tener ISBN-13 ahí; los aceptamos también.
    if len(isbn) not in (10, 13):
        return None

    # Type filter (opt-in). Por default `accept_types` está vacío =
    # aceptamos todo (el type-tag del sitio describe el extra, no el
    # producto — ver docstring del módulo).
    if accept_types:
        type_el = soup.find("span", class_="type")
        item_type = clean_text(type_el.get_text(" ", strip=True)) if type_el else ""
        if item_type and item_type not in accept_types:
            return None

    # Title
    name_el = soup.find("div", class_="name")
    if not name_el:
        return None
    title = clean_text(name_el.get_text(" ", strip=True))
    if not title:
        return None

    # Gate anti falso-positivo: como más abajo inyectamos boilerplate
    # "限定版・特装版 / limited edition…" en la description de TODOS los
    # items, sólo emitimos los que tienen un marcador de edición REAL en
    # el título FUERA de los corchetes 『』「」 (dentro de los corchetes,
    # 限定 es parte del nombre de la obra). Sin marcador → skip total.
    if not _has_edition_marker_outside_brackets(title):
        return None

    # Junk: títulos con menos de 3 caracteres alfanuméricos/CJK
    # (artefactos de parsing tipo ">>>>>>&").
    if len(_CONTENT_CHAR_RE.findall(title)) < 3:
        return None

    # Sabs: 2 bloques. sab[0] = [date, author]; sab[1] = [imprint, publisher].
    sabs = soup.find_all("div", class_="sab")
    date_raw = ""
    author = ""
    imprint = ""
    publisher_raw = ""
    if len(sabs) >= 1:
        spans = sabs[0].find_all("span")
        if spans:
            date_raw = clean_text(spans[0].get_text(" ", strip=True))
        if len(spans) >= 2:
            author = clean_text(spans[1].get_text(" ", strip=True))
    if len(sabs) >= 2:
        spans = sabs[1].find_all("span")
        if spans:
            imprint = clean_text(spans[0].get_text(" ", strip=True))
        if len(spans) >= 2:
            publisher_raw = clean_text(spans[1].get_text(" ", strip=True))
    # Si sab[1] tiene 1 solo span, el imprint actúa también como publisher.
    if not publisher_raw:
        publisher_raw = imprint

    publisher = _publisher_canonical(publisher_raw)
    release_date = _parse_jp_date(date_raw)

    # Image: data-src del primer <img> dentro del bloque. NO filtramos
    # por `class="lazy"` porque los items BL usan `class="touch18"` (R18
    # wrapper) y otros pueden cambiar de wrapper. El `data-src` real al
    # CDN de Amazon es lo que necesitamos en cualquier caso.
    img = soup.find("img")
    image_url = ""
    if img:
        # data-src (lazy real) preferido sobre src (placeholder).
        image_url = img.get("data-src") or img.get("data-src2") or img.get("src") or ""
        # Descartar placeholders / wrappers que NO son portadas:
        # `reload200_299.svg` (lazy loading spinner), `no_image200_299_BL.png`
        # (18+ blur cover), `/loading/` (cualquier loading variant).
        bad = ("reload200_299", "/loading/", "no_image200_299")
        if any(b in image_url for b in bad):
            image_url = ""

    source = _virtual_source()
    if publisher:
        source.publisher = publisher

    # URL canónica: el detail page del sitio. Sirve como referencia
    # estable (no cambia si el listing reordena items).
    url = DETAIL_URL_TEMPLATE.format(isbn=isbn)

    # Description: explícito de "限定版/特装版/edition with bonus" para
    # garantizar que detect_signals levante el signal correcto. El título
    # ya suele decir "特装版"/"限定版", pero el inject blinda a items
    # que solo dicen "BOX" o "完全版".
    descr_parts: list[str] = ["限定版・特装版 / limited edition / special edition / bonus edition."]
    if imprint and imprint != publisher_raw:
        descr_parts.append(f"Imprint: {imprint}.")
    if author:
        descr_parts.append(f"著者: {author}.")
    description = " ".join(descr_parts).strip()[:2500]

    cand = candidate_from_source(
        source,
        title=title,
        url=url,
        description=description,
        published_at=release_date,
    )
    cand.image_url = image_url
    cand.release_date = release_date
    cand.isbn = isbn if len(isbn) == 10 else isbn   # both fine
    if author:
        cand.author = author

    volume = _extract_volume(title)
    if volume:
        cand.tags = list(source.tags) + [f"sk-vol:{volume}"]

    score_candidate(cand)
    return cand


def parse_listing_page(
    html_text: str,
    accept_types: frozenset[str] = _DEFAULT_ACCEPT_TYPES,
) -> list[Candidate]:
    """Parsea una página de listing (`?p=N`) y devuelve la lista de
    Candidates. Filtra por `accept_types` (default: solo コミック)."""
    if not html_text:
        return []
    # Cada item está envuelto en `<a href="/item-select/...">...</a>` —
    # extraemos cada bloque y delegamos a _item_block_to_candidate.
    blocks = re.findall(
        r'<a[^>]+href="[^"]*/item-select/\d{10,13}"[^>]*>.*?</a>',
        html_text,
        re.DOTALL,
    )
    out: list[Candidate] = []
    seen_isbns: set[str] = set()
    for block in blocks:
        cand = _item_block_to_candidate(block, accept_types)
        if not cand:
            continue
        # Dedupe por ISBN dentro de la página (raro pero por las dudas).
        if cand.isbn and cand.isbn in seen_isbns:
            continue
        seen_isbns.add(cand.isbn)
        out.append(cand)
    return out


def fetch_html(
    session: requests.Session,
    url: str,
    timeout: tuple[int, int] = (10, 30),
) -> str | None:
    """Descarga `url` y devuelve el HTML. UTF-8 limpio (LiteSpeed server)."""
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        print(f"[sumikko] WARN {url}: {exc}")
        return None


def iter_year_months(
    year_from: int, month_from: int,
    year_to: int, month_to: int,   # noqa: ARG001
) -> list[tuple[int, int]]:
    """Sumikko no usa calendario mensual — devolvemos batch único como blogbbm/
    socialanime."""
    return [(year_from, month_from)]


def bootstrap(
    year_from: int,         # noqa: ARG001 (signature compat con dispatcher)
    month_from: int,        # noqa: ARG001
    year_to: int,           # noqa: ARG001
    month_to: int,          # noqa: ARG001
    session: requests.Session,
    sleep_seconds: float = 0.3,
    timeout: tuple[int, int] = (10, 30),
    min_score: int = 0,
    fetch_details: bool = False,  # noqa: ARG001 (no detail-fetch — listing tiene todo)
    accept_types: frozenset[str] = _DEFAULT_ACCEPT_TYPES,
    max_pages: int = 40,
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Itera `?p=1..max_pages` con early-stop en página vacía (3 consecutivas)
    para soportar gaps temporales. Default max_pages=40 cubre el catálogo
    completo (~32 páginas reales).

    No tiene sentido respetar `year_from/year_to` porque el sitio no
    permite filtrar por fecha — siempre devuelve el catálogo completo
    ordenado por release_date desc.
    """
    print(f"[sumikko] iterando hasta p={max_pages} (early-stop en empty)")
    candidates: list[Candidate] = []
    seen_isbns: set[str] = set()
    empty_streak = 0
    for page in range(1, max_pages + 1):
        url = LISTING_URL_TEMPLATE.format(page=page)
        html = fetch_html(session, url, timeout=timeout)
        if html is None:
            # network fail — count as empty for early-stop, no break
            empty_streak += 1
            if empty_streak >= 3:
                break
            if sleep_seconds:
                time.sleep(sleep_seconds)
            continue
        page_cands = parse_listing_page(html, accept_types=accept_types)
        if not page_cands:
            empty_streak += 1
            print(f"[sumikko] p={page}: 0 items (streak {empty_streak}/3)")
            if empty_streak >= 3:
                break
            if sleep_seconds:
                time.sleep(sleep_seconds)
            continue
        empty_streak = 0
        new_on_page = 0
        page_kept: list[Candidate] = []
        for cand in page_cands:
            if min_score and cand.score < min_score:
                continue
            if cand.isbn and cand.isbn in seen_isbns:
                continue
            if cand.isbn:
                seen_isbns.add(cand.isbn)
            candidates.append(cand)
            page_kept.append(cand)
            new_on_page += 1
        print(f"[sumikko] p={page}: {len(page_cands)} items, {new_on_page} nuevos (total {len(candidates)})")
        if flush_fn and page_kept:
            flush_fn(page_kept)
        if sleep_seconds:
            time.sleep(sleep_seconds)

    print(f"[sumikko] terminado: {len(candidates)} candidates con score>={min_score}")
    return candidates


if __name__ == "__main__":
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; manga-watch-personal/0.2)"
    # Demo: 2 páginas para testing rápido.
    cands = bootstrap(2024, 1, 2026, 12, session=s, min_score=0,
                      sleep_seconds=0.2, max_pages=2)
    print(f"\nTotal: {len(cands)} candidates")
    for c in cands[:5]:
        print(f"  [{c.score:3d}] {c.publisher[:15]:15s} | isbn={c.isbn:13s} | {c.title[:60]}")
