"""Parser del calendario de Yen Press — ediciones especiales EN (US).

yenpress.com/calendar lista los próximos lanzamientos mes a mes con
filtro de categoría: Manga, Comics, Light Novel, Audio. El parser
descarga solo las categorías manga + comics y aplica un pre-filtro por
keywords para quedarse solo con ediciones especiales (collector's, deluxe,
box set, artbook, hardcover, limited edition, etc.).

Estructura del HTML real (verificada 2026-05-27, una card por producto)::

    <a href="/titles/9798855416916-spice-and-wolf-collector-s-edition-vol-1-manga">
      <div class="inline_block col-d-25 col-t-50 col-m-100 released-box book-box">
        <div class="released-covers-wrapper flex-center prel">
          <span class="white-label manga upper">Manga</span>
          <div class="calendar-books-wrapper">
            <div class="prel">
              <p class="label-date upper">17
                <span class="month">Jun</span>
              </p>
              <img class="genre-col-img"
                   src="https://images.yenpress.com/imgs/9798855416916.jpg?...">
            </div>
          </div>
          <div class="genre-col-txt">
            <h3 class="heading small-h1">Spice and Wolf Collector's Edition, Vol. 1 (manga)</h3>
          </div>
        </div>
      </div>
    </a>

Notas de estructura:
- El ISBN-13 está en el href de la ``<a>`` EXTERIOR, no en un enlace
  anidado dentro de la card.
- La categoría usa ``white-label light-novels upper`` (no ``light``).
- El título está en ``h3.heading.small-h1`` dentro de ``div.genre-col-txt``,
  directamente (sin ``<a>`` interior).
- NO hay precio en la página (``<p class="label-price">`` no existe).
- La ``<img>`` usa la URL con parámetros de resize del servidor; el parser
  genera la cover URL determinística con ``COVER_URL_TPL``.

Cover URL determinístico: ``https://images.yenpress.com/imgs/{isbn13}.jpg``
Product URL: ``https://www.yenpress.com/titles/{isbn13}-{slug}``
ISBN-13 está en el path de cada link de producto.

La página acepta ``?year=YYYY&month=M`` para navegar meses distintos.
El parser itera los meses del rango solicitado (como manga_sanctuary.py)
— NO es un listing único (a diferencia de prhcomics/kinokuniya).

API pública (misma firma que los demás wiki parsers)::

    parse_calendar_page(html, year, month)     -> list[Candidate]
    fetch_calendar_month(year, month, session) -> str  (HTML raw)
    bootstrap(yf, mf, yt, mt, ...)             -> list[Candidate]
    iter_year_months(yf, mf, yt, mt)           -> list[(year, month)]
"""

from __future__ import annotations

import re
import sys
import time as time_module
from pathlib import Path
from typing import Any, Callable

import requests
from bs4 import BeautifulSoup, Tag

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


CALENDAR_URL = "https://www.yenpress.com/calendar"
PRODUCT_BASE = "https://www.yenpress.com"
COVER_URL_TPL = "https://images.yenpress.com/imgs/{isbn13}.jpg?w=285&h=422&type=books"

# Categorías de Yen Press que nos interesan (manga + comics).
# Clases CSS reales (verificadas 2026-05-27):
#   "manga"       → Manga
#   "light-novels" → Light Novels / LN  (excluidas)
#   "comics"      → Comics (manhwa/manhua OEL)
#   "audio"       → Audio books (excluidos)
_INCLUDE_CATS: frozenset[str] = frozenset({"manga", "comics"})

# ISBN-13 en el path del link de producto: /titles/{isbn13}-{slug}
_ISBN_PATH_RE = re.compile(r"/titles/(\d{13})-")

# Pre-filtro de keywords: solo títulos que mencionan algún qualifier
# premium. Yen Press publica ~50-80 títulos/mes; este filtro deja ~2-5.
_SPECIAL_KWS_RE = re.compile(
    r"\b(?:"
    r"collector['’s]*s?"
    r"|deluxe"
    r"|box\s*set"
    r"|boxed\s*set"
    r"|limited\s+edition"
    r"|special\s+edition"
    r"|complete\s+box"
    r"|complete\s+collection"
    r"|numbered"
    r"|slipcase"
    r"|art\s*book"
    r"|artbook"
    r"|hardcover"
    r"|omnibus"
    r")\b",
    re.IGNORECASE,
)

# Meses EN 3-letter → número (los que Yen Press usa en <span class="month">)
_MONTH_ABBR: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ---------------------------------------------------------------------------
# Source virtual
# ---------------------------------------------------------------------------

def _virtual_source() -> Source:
    """Source sintética para Yen Press Calendar."""
    return Source(
        name="US - Yen Press Calendar",
        url=CALENDAR_URL,
        country="Estados Unidos",
        language="English",
        publisher="Yen Press",
        source_class="trusted_catalog",
        kind="wiki",
        enabled=True,
        tags=["wiki", "yenpress", "usa", "english", "calendar"],
        notes=(
            "yenpress.com/calendar — calendario mensual de lanzamientos "
            "de Yen Press (US). Cubre: manga, comics (excluye light novels "
            "y audio). Filtrado por keywords de edición especial: collector's, "
            "deluxe, box set, hardcover, limited edition, artbook, etc."
        ),
        selectors={},
        max_pages=0,
        purity="manga_only",
    )


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_date_from_card(card: Tag, year: int, month: int) -> str:
    """Extrae fecha ISO 'YYYY-MM-DD' del elemento <p class="label-date">.

    Yen Press muestra el día y el mes-abreviado: ``06<span class="month">Jun</span>``.
    El año se infiere del parámetro de la página que se está parsando.
    """
    date_el = card.select_one("p.label-date")
    if not date_el:
        return f"{year:04d}-{month:02d}-01"  # fallback: primer día del mes

    # El texto directo (antes del <span>) es el día numérico.
    # Clonamos el tag para extraer el día sin el span de mes.
    day_text = ""
    for child in date_el.children:
        if isinstance(child, str):
            day_text += child
        elif hasattr(child, "name") and child.name == "span" and "month" in (child.get("class") or []):
            break  # el span de mes lo procesamos aparte
    day_text = day_text.strip()

    month_el = date_el.select_one("span.month")
    month_abbr = (month_el.get_text().strip().lower()[:3] if month_el else "")

    try:
        day = int(day_text)
    except ValueError:
        day = 1

    # Si el mes del span no coincide con el mes del parámetro URL,
    # podría ser un carryover del mes anterior/siguiente. Lo aceptamos
    # igual (Yen Press a veces lista pre-orders del mes siguiente).
    inferred_month = _MONTH_ABBR.get(month_abbr, month)
    inferred_year = year
    # Ajuste de año si el mes inferido es diciembre y estamos en enero, etc.
    if inferred_month > month and month == 1:
        inferred_year -= 1
    elif inferred_month < month and month == 12:
        inferred_year += 1

    try:
        return f"{inferred_year:04d}-{inferred_month:02d}-{day:02d}"
    except (ValueError, OverflowError):
        return f"{year:04d}-{month:02d}-01"


def _parse_price(card: Tag) -> str:
    """Extrae el precio de <p class="label-price">."""
    price_el = card.select_one("p.label-price")
    if not price_el:
        return ""
    return price_el.get_text().strip()


def _category_of_card(card: Tag) -> str:
    """Extrae la categoría ('manga', 'comics', 'light-novels', 'audio') del span white-label.

    El span tiene clases como::

        "white-label manga upper"
        "white-label light-novels upper"
        "white-label comics upper"
        "white-label audio upper"

    Devuelve la cadena de categoría en minúsculas (sin "upper" ni "white-label").
    """
    for span in card.select("span.white-label"):
        classes = set(span.get("class", []))
        # Quitar clases que no son la categoría en sí
        cats = classes - {"white-label", "upper", "lower"}
        if cats:
            return cats.pop().lower()
    return ""


def _parse_card(
    anchor: Tag,
    year: int,
    month: int,
    source: Source,
) -> "Candidate | None":
    """Mapea un ``<a href='/titles/...'>`` del calendario a un Candidate.

    La estructura real (verificada 2026-05-27) es::

        <a href="/titles/{isbn13}-{slug}">
          <div class="... book-box">
            <div class="released-covers-wrapper ...">
              <span class="white-label manga upper">Manga</span>
              <div class="calendar-books-wrapper">
                <div class="prel">
                  <p class="label-date upper">17<span class="month">Jun</span></p>
                  <img class="genre-col-img" src="...">
                </div>
              </div>
              <div class="genre-col-txt">
                <h3 class="heading small-h1">Title here</h3>
              </div>
            </div>
          </div>
        </a>

    Devuelve None si:
    - La categoría no es manga/comics.
    - El título no contiene keywords de edición especial.
    - Faltan campos mínimos (título, ISBN).
    """
    # ISBN-13 del href de la <a> exterior
    href = anchor.get("href", "")
    m = _ISBN_PATH_RE.search(href)
    if not m:
        return None
    isbn = m.group(1)
    if not (isbn.startswith("978") or isbn.startswith("979")):
        return None

    # Filtro de categoría — el span white-label está dentro del anchor
    cat = _category_of_card(anchor)
    if cat not in _INCLUDE_CATS:
        return None

    # Título — h3 dentro de div.genre-col-txt (sin <a> interior)
    title_el = anchor.select_one("div.genre-col-txt h3") or anchor.select_one("h3.heading")
    if not title_el:
        return None
    title = clean_text(title_el.get_text())
    if not title or len(title) < 3:
        return None

    # Pre-filtro de keywords — descartamos paperbacks regulares
    if not _SPECIAL_KWS_RE.search(title):
        return None

    # URLs canónicas
    full_href = href if href.startswith("http") else f"{PRODUCT_BASE}{href}"
    url = full_href
    image_url = COVER_URL_TPL.format(isbn13=isbn)

    # Fecha (precio no está disponible en la página del calendario)
    release_date = _parse_date_from_card(anchor, year, month)
    price = _parse_price(anchor)  # siempre "" — no hay precios en el calendario

    # Descripción con hints para detect_signals
    description = f"{title}."
    if price:
        description += f" Price: {price}."

    cand = candidate_from_source(
        source,
        title=title,
        url=url,
        description=description,
        published_at=release_date,
    )
    cand.isbn = isbn
    cand.image_url = image_url
    cand.release_date = release_date
    cand.price = price

    score_candidate(cand)
    return cand


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_calendar_page(html: str, year: int, month: int) -> "list[Candidate]":
    """Parsea el HTML de un mes del calendario de Yen Press.

    Extrae las cards de categoría manga/comics que cumplan el pre-filtro
    de keywords de edición especial. Dedup por ISBN dentro de la página.

    Estructura real (verificada 2026-05-27): cada producto está envuelto en
    un ``<a href="/titles/{isbn13}-{slug}">`` que actúa como card raíz.
    Dentro hay ``div.book-box`` con categoría, fecha, imagen y título.
    """
    soup = BeautifulSoup(html, "html.parser")
    source = _virtual_source()

    seen_isbns: set[str] = set()
    candidates: list[Candidate] = []

    # Las cards son <a href="/titles/..."> que contienen un div.book-box.
    # Buscamos todos los anchors cuyo href apunta a /titles/ con ISBN-13.
    anchors: list[Tag] = [
        t for t in soup.find_all("a", href=_ISBN_PATH_RE)
        if isinstance(t, Tag)
        # Excluir anchors del menú de navegación (no tienen div.book-box ni
        # el span white-label de categoría con clase genre-col-img).
        and t.select_one("img.genre-col-img") is not None
    ]

    if not anchors:
        # Fallback para cambios futuros de markup: cualquier <a> con /titles/
        # que tenga dentro un span.white-label (la señal de categoría).
        anchors = [
            t for t in soup.find_all("a", href=_ISBN_PATH_RE)
            if isinstance(t, Tag) and t.select_one("span.white-label")
        ]

    for anchor in anchors:
        cand = _parse_card(anchor, year, month, source)
        if cand is None:
            continue

        if cand.isbn and cand.isbn in seen_isbns:
            continue
        if cand.isbn:
            seen_isbns.add(cand.isbn)

        candidates.append(cand)

    return candidates


def fetch_calendar_month(
    year: int,
    month: int,
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
) -> str:
    """Descarga el HTML del calendario de Yen Press para un mes dado."""
    url = f"{CALENDAR_URL}?year={year}&month={month}"
    try:
        resp = session.get(
            url,
            timeout=timeout,
            headers={"Accept": "text/html,application/xhtml+xml"},
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        print(f"[yenpress] ERROR al obtener {url}: {exc}")
        return ""


def iter_year_months(
    year_from: int,
    month_from: int,
    year_to: int,
    month_to: int,
) -> list[tuple[int, int]]:
    """Genera la lista de (year, month) pares en el rango [from, to]."""
    pairs: list[tuple[int, int]] = []
    y, m = year_from, month_from
    while (y, m) <= (year_to, month_to):
        pairs.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
        if y > year_to + 5:
            break
    return pairs


def bootstrap(
    year_from: int,
    month_from: int,
    year_to: int,
    month_to: int,
    session: requests.Session,
    sleep_seconds: float = 0.5,
    timeout: tuple[int, int] = (15, 45),
    min_score: int = 0,
    fetch_details: bool = False,   # noqa: ARG001 (no se necesitan detail pages)
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> "list[Candidate]":
    """Descarga el calendario de Yen Press mes a mes y extrae ediciones especiales.

    Filtra por categoría (manga/comics, excluye LN y audio) y por keywords
    de edición especial (collector's, deluxe, box set, hardcover, etc.).
    """
    pairs = iter_year_months(year_from, month_from, year_to, month_to)
    all_candidates: list[Candidate] = []
    seen_isbns: set[str] = set()

    for idx, (y, m) in enumerate(pairs, start=1):
        print(f"[{idx}/{len(pairs)}] Yen Press Calendar {y}-{m:02d}")
        html = fetch_calendar_month(y, m, session, timeout=timeout)
        if not html:
            if sleep_seconds > 0 and idx < len(pairs):
                time_module.sleep(sleep_seconds)
            continue

        month_cands = parse_calendar_page(html, y, m)

        kept: list[Candidate] = []
        for cand in month_cands:
            # Dedup cross-month por ISBN
            if cand.isbn and cand.isbn in seen_isbns:
                continue
            if cand.isbn:
                seen_isbns.add(cand.isbn)

            if min_score and cand.score < min_score:
                continue

            kept.append(cand)

        print(f"    {len(month_cands)} candidatos en página, {len(kept)} kept")
        all_candidates.extend(kept)

        if flush_fn and kept:
            flush_fn(kept)

        if sleep_seconds > 0 and idx < len(pairs):
            time_module.sleep(sleep_seconds)

    print(f"[yenpress] total: {len(all_candidates)} candidates")
    return all_candidates


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Yen Press Calendar parser")
    parser.add_argument(
        "--wiki-from", default="",
        help="Mes inicial YYYY-MM. Vacío = mes actual.",
    )
    parser.add_argument(
        "--wiki-to", default="",
        help="Mes final YYYY-MM. Vacío = mismo que --wiki-from.",
    )
    parser.add_argument("--sleep-seconds", type=float, default=0.5)
    parser.add_argument("--min-score", type=int, default=0)
    args = parser.parse_args()

    import datetime
    today = datetime.date.today()

    if args.wiki_from:
        parts = args.wiki_from.split("-")
        yf, mf = int(parts[0]), int(parts[1])
    else:
        yf, mf = today.year, today.month

    if args.wiki_to:
        parts = args.wiki_to.split("-")
        yt, mt = int(parts[0]), int(parts[1])
    else:
        yt, mt = yf, mf

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; manga-watch-personal/0.2)"

    cands = bootstrap(
        yf, mf, yt, mt,
        session=s,
        sleep_seconds=args.sleep_seconds,
        min_score=args.min_score,
    )
    print(f"\nTotal: {len(cands)} candidates")
    for c in cands[:20]:
        print(f"  [{c.score:3d}] {c.isbn or 'no-isbn':<14} {c.release_date or '?':10} {c.title[:60]}")
