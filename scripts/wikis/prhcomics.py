"""Parser de PRH Comics — ediciones especiales de manga en inglés (US/CA).

prhcomics.com es el portal editorial de Penguin Random House para cómics
y manga. Su sección /manga/ lista el catálogo activo de publishers
distribuidos por PRH: Dark Horse Manga, Kodansha Comics, Seven Seas
Entertainment, Square Enix Manga, TOKYOPOP, Titan Comics, Vertical Comics,
Inklore.

No cubre VIZ Media ni Yen Press (tienen distribución propia).

Endpoint::

    GET https://prhcomics.com/manga/

Una sola página HTML estática. Sin paginación, sin JS, sin autenticación.
Todos los metadatos del listing están disponibles en el HTML directamente —
no se necesita hitear páginas de detalle.

Schema de un item (HTML)::

    <li class="toast-anchor">
      <div class="carousel-book">
        <a href="https://prhcomics.com/book/?isbn=9798888776346">
          <img alt="Mushishi Collector's Edition 1"
               src="https://images.penguinrandomhouse.com/cover/9798888776346?width=180">
        </a>
      </div>
      <div class="carousel-meta" data-component="carousel-meta">
        <div data-component="carousel-meta-title">
          <a href="...">Mushishi Collector's Edition 1</a>
        </div>
        <div data-component="carousel-meta-author"><a>Yuki Urushibara</a></div>
        <div data-component="carousel-meta-isbn">9798888776346</div>
        <div data-component="carousel-meta-price">
          <span class="price-usa">$34.99 US</span>
        </div>
        <div data-component="carousel-meta-format">Hardcover</div>
        <div data-component="carousel-meta-division">Kodansha Comics</div>
        <div data-component="carousel-meta-on-sale-date">On sale May 19, 2026</div>
      </div>
    </li>

Cover URL determinística: ``https://images.penguinrandomhouse.com/cover/{isbn13}``
Product URL: ``https://prhcomics.com/book/?isbn={isbn13}``

API pública (misma firma que los demás wiki parsers)::

    parse_item(li_tag)              -> Candidate | None
    fetch_manga_page(session, ...)  -> list[Tag]  (BeautifulSoup tags)
    bootstrap(yf, mf, yt, mt, ...) -> list[Candidate]
    iter_year_months(yf, mf, yt, mt) -> [(yf, mf)]  (batch único)
"""

from __future__ import annotations

import sys
from datetime import datetime
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


PRH_MANGA_URL = "https://prhcomics.com/manga/"
COVER_BASE = "https://images.penguinrandomhouse.com/cover"
BOOK_BASE = "https://prhcomics.com/book/?isbn="

# Publishers en la página /manga/ de PRH que NO publican manga
# (libros infantiles, guías de referencia, graphic novels mainstream).
# PRH Comics agrupa todo su catálogo bajo /manga/ incluyendo licencias
# de franquicias que no son manga (DK readers de Pokémon, guías DK, etc.).
_NON_MANGA_PUBLISHERS: frozenset[str] = frozenset({
    "DK Children",
    "DK",
    "Golden Books",
    "Random House Books for Young Readers",
    "Prestel",
    "Pantheon",
})

# Formatos de binding que indican edición especial sin necesidad de
# analizar el título (los paperbacks regulares no aparecen aquí).
_COLLECTIBLE_FORMATS: frozenset[str] = frozenset({
    "hardcover",
    "boxed set",
    "box set",
    "slipcase",
})

# Keywords en el título que hacen coleccionable un item cuyo formato
# no es explícito o ambiguo.
_COLLECTIBLE_TITLE_KWS: frozenset[str] = frozenset({
    "collector",
    "deluxe",
    "artbook",
    "art book",
    "limited edition",
    "box set",
    "complete edition",
    "omnibus hardcover",
    "hardcover collection",
    "premium",
    "kanzenban",
    "anniversary",
    "special edition",
})

# Meses en inglés → número
_MONTH_MAP: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _is_collectible(title: str, fmt: str) -> bool:
    """True si el item parece una edición especial por formato o título."""
    # El formato "Hardcover(Manga RTL - HC)" tiene el tipo antes del paréntesis
    fmt_base = fmt.lower().split("(")[0].strip()
    if fmt_base in _COLLECTIBLE_FORMATS:
        return True
    tl = title.lower()
    return any(kw in tl for kw in _COLLECTIBLE_TITLE_KWS)


def _format_signal_hints(fmt: str) -> list[str]:
    """Palabras inyectadas en la descripción para que detect_signals
    levante las señales correctas desde el formato del binding."""
    fl = fmt.lower()
    if "boxed set" in fl or "box set" in fl or "slipcase" in fl:
        return ["Box Set"]
    if "hardcover" in fl:
        return ["Hardcover"]
    return []


def _parse_release_date(raw: str) -> str:
    """'On sale May 19, 2026' → '2026-05-19'. Vacío si no parseable."""
    # Quitar prefijo "On sale " o "On Sale "
    cleaned = raw.strip()
    for prefix in ("On sale ", "On Sale ", "on sale "):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    try:
        dt = datetime.strptime(cleaned.strip(), "%B %d, %Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass
    # Intento alternativo: parseo manual de "May 2026" sin día
    parts = cleaned.strip().split()
    if len(parts) == 2:
        month_name, year_str = parts
        mn = _MONTH_MAP.get(month_name.lower())
        if mn and year_str.isdigit():
            return f"{year_str}-{mn:02d}-01"
    return ""


def _virtual_source() -> Source:
    """Source sintética para PRH Comics."""
    return Source(
        name="US - PRH Comics",
        url=PRH_MANGA_URL,
        country="Estados Unidos",
        language="English",
        publisher="",
        source_class="trusted_catalog",
        kind="wiki",
        enabled=True,
        tags=["wiki", "prhcomics", "usa", "canada", "english"],
        notes=(
            "prhcomics.com — catálogo de ediciones especiales de manga en inglés "
            "distribuidas por Penguin Random House. Cubre: Dark Horse Manga, "
            "Kodansha Comics, Seven Seas, Square Enix Manga, TOKYOPOP, Titan, "
            "Vertical, Inklore. No incluye VIZ Media ni Yen Press."
        ),
        selectors={},
        max_pages=0,
        purity="manga_only",
    )


def parse_item(li_tag: Tag) -> Candidate | None:
    """Mapea un <li class='toast-anchor'> de PRH Comics a un Candidate.

    Devuelve None si faltan campos mínimos (ISBN o título) o si el item
    no es una edición especial (formato paperback sin keywords especiales).
    """
    if not isinstance(li_tag, Tag):
        return None

    # Título
    title_a = li_tag.select_one('div[data-component="carousel-meta-title"] a')
    if not title_a:
        return None
    title = clean_text(title_a.get_text())
    if not title:
        return None

    # ISBN — requerido para la URL canónica y la cover determinística
    isbn_div = li_tag.select_one('div[data-component="carousel-meta-isbn"]')
    isbn = (isbn_div.get_text().strip() if isbn_div else "").replace("-", "").strip()
    if not isbn:
        return None

    # Formato del binding — determina si es edición especial
    fmt_div = li_tag.select_one('div[data-component="carousel-meta-format"]')
    fmt = fmt_div.get_text().strip() if fmt_div else ""

    if not _is_collectible(title, fmt):
        return None

    # Publisher (división de PRH)
    pub_div = li_tag.select_one('div[data-component="carousel-meta-division"]')
    publisher = clean_text(pub_div.get_text()) if pub_div else ""

    # Rechazar publishers que no son manga (DK readers, Golden Books, etc.
    # que aparecen en /manga/ por tener licencias de franquicias manga)
    if publisher in _NON_MANGA_PUBLISHERS:
        return None

    # Autor
    author_a = li_tag.select_one('div[data-component="carousel-meta-author"] a')
    author = clean_text(author_a.get_text()) if author_a else ""

    # Precio (USD preferido)
    price_span = li_tag.select_one(
        'div[data-component="carousel-meta-price"] span.price-usa'
    )
    price = price_span.get_text().strip() if price_span else ""

    # Fecha de lanzamiento
    date_div = li_tag.select_one('div[data-component="carousel-meta-on-sale-date"]')
    date_raw = date_div.get_text().strip() if date_div else ""
    release_date = _parse_release_date(date_raw)

    # URLs canónicas
    url = f"{BOOK_BASE}{isbn}"
    image_url = f"{COVER_BASE}/{isbn}"

    # Descripción: hints de señal + metadata
    hints = _format_signal_hints(fmt)
    desc_parts = list(hints)
    if publisher:
        desc_parts.append(f"Publisher: {publisher}.")
    if fmt:
        desc_parts.append(f"Format: {fmt}.")
    if release_date:
        desc_parts.append(f"On sale: {release_date}.")
    description = " ".join(desc_parts)

    source = _virtual_source()
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
    cand.price = price
    if author:
        cand.author = author
    if isbn:
        cand.isbn = isbn

    score_candidate(cand)
    return cand


def fetch_manga_page(
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
) -> list[Tag]:
    """Descarga la página /manga/ de PRH Comics y devuelve todos los
    <li class='toast-anchor'> encontrados."""
    try:
        resp = session.get(
            PRH_MANGA_URL,
            timeout=timeout,
            headers={"Accept": "text/html,application/xhtml+xml"},
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[prhcomics] ERROR al obtener {PRH_MANGA_URL}: {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select("li.toast-anchor")
    print(f"[prhcomics] {len(items)} items encontrados en el HTML")
    return items


def bootstrap(
    year_from: int,
    month_from: int,
    year_to: int,
    month_to: int,
    session: requests.Session,
    sleep_seconds: float = 0.0,   # noqa: ARG001 (una sola request)
    timeout: tuple[int, int] = (15, 45),
    min_score: int = 0,
    fetch_details: bool = False,   # noqa: ARG001 (no se necesitan detail pages)
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Descarga el catálogo /manga/ de PRH Comics y extrae ediciones especiales.

    ``year_from``/``month_from`` filtran opcionalmente los items por fecha
    de lanzamiento — útil en modo delta para obtener solo lo reciente.
    Si ``year_from`` < 2010 se devuelven todos sin filtro de fecha.
    """
    date_filter = year_from >= 2010
    date_cutoff = f"{year_from:04d}-{month_from:02d}-01" if date_filter else ""

    print(
        f"[prhcomics] fetching {PRH_MANGA_URL} | "
        f"date_filter={'≥' + date_cutoff if date_cutoff else '(catálogo completo)'}"
    )

    li_tags = fetch_manga_page(session, timeout=timeout)
    if not li_tags:
        return []

    candidates: list[Candidate] = []
    seen_isbns: set[str] = set()
    skipped_format = 0
    skipped_date = 0

    for li in li_tags:
        cand = parse_item(li)
        if cand is None:
            skipped_format += 1
            continue

        # Dedup por ISBN dentro del mismo run (el mismo tomo puede aparecer
        # en varios carruseles de la página)
        if cand.isbn and cand.isbn in seen_isbns:
            continue
        if cand.isbn:
            seen_isbns.add(cand.isbn)

        # Filtro de fecha opcional
        if date_cutoff and cand.release_date and cand.release_date < date_cutoff:
            skipped_date += 1
            continue

        if min_score and cand.score < min_score:
            continue

        candidates.append(cand)

    print(
        f"[prhcomics] {len(candidates)} candidates "
        f"(descartados formato={skipped_format}, fecha={skipped_date})"
    )

    if flush_fn and candidates:
        flush_fn(candidates)

    return candidates


def iter_year_months(
    year_from: int, month_from: int,
    year_to: int, month_to: int,    # noqa: ARG001
) -> list[tuple[int, int]]:
    """La página /manga/ no particiona por mes; devuelve un único batch."""
    return [(year_from, month_from)]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingesta PRH Comics manga")
    parser.add_argument(
        "--wiki-from", default="",
        help="Filtro delta: YYYY-MM (ej. 2025-01). Vacío = todo el catálogo.",
    )
    args = parser.parse_args()

    year_from, month_from = 2000, 1
    if args.wiki_from:
        parts = args.wiki_from.split("-")
        year_from, month_from = int(parts[0]), int(parts[1])

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; manga-watch-personal/0.2)"

    cands = bootstrap(
        year_from, month_from, 2030, 12,
        session=s,
        min_score=0,
    )
    print(f"\nTotal: {len(cands)} candidates")
    for c in cands[:20]:
        print(f"  [{c.score:3d}] {c.publisher:<25} {c.isbn or 'no-isbn':<14} {c.title[:60]}")
