"""Parser de Kinokuniya USA Exclusives — ediciones especiales con exclusividad Kino.

usa.kinokuniya.com/kinokuniya-exclusives lista todos los títulos exclusivos
actuales: variant covers, dust jackets exclusivos, shikishi, ID cards,
sticker packs, limited editions con bonus, etc.

El sitio corre sobre Squarespace — los class names son dinámicos y cambian
con cada redeploy. El único selector estable es el patrón de URL de producto::

    https://united-states.kinokuniya.com/bw/{isbn13}

El ISBN-13 está en el path de cada link de producto. Las páginas de detalle
devuelven 403, así que todos los metadatos se extraen del listing.

Cover URL: ``https://images.penguinrandomhouse.com/cover/{isbn13}``
(Los publishers EN que usan Kinokuniya para exclusivos — Kodansha, Seven Seas,
Square Enix, Yen Press, TOKYOPOP, etc. — en su mayoría tienen covers en el
CDN de PRH; los que no, quedan con backfill para el espejo local.)

API pública (misma firma que los demás wiki parsers)::

    parse_listing(html)                  -> list[Candidate]
    fetch_listing(session, timeout)      -> str  (HTML raw)
    bootstrap(yf, mf, yt, mt, ...)       -> list[Candidate]
    iter_year_months(yf, mf, yt, mt)     -> [(yf, mf)]  (batch único)
"""

from __future__ import annotations

import re
import sys
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


LISTING_URL = "https://usa.kinokuniya.com/kinokuniya-exclusives"
PRODUCT_BASE = "https://united-states.kinokuniya.com/bw/"
COVER_BASE = "https://images.penguinrandomhouse.com/cover"

# Pattern: /bw/{isbn13}  (13 dígitos al final del path)
_ISBN_URL_RE = re.compile(r"/bw/(\d{13})(?:[/?#]|$)")


def _virtual_source() -> Source:
    """Source sintética para Kinokuniya USA Exclusives."""
    return Source(
        name="US - Kinokuniya Exclusives",
        url=LISTING_URL,
        country="Estados Unidos",
        language="English",
        # Kinokuniya es el RETAILER, NO la editorial. NO poner el nombre de la
        # tienda como publisher (gotcha: la tienda no es la editorial). La
        # editorial real (Viz, Kodansha Comics, Seven Seas, TOKYOPOP…) la deriva
        # /watch-standardize-catalog en el edition_key. Dejar vacío.
        publisher="",
        source_class="retailer",
        kind="wiki",
        enabled=True,
        tags=["wiki", "kinokuniya", "usa", "english", "exclusive", "variant"],
        notes=(
            "usa.kinokuniya.com/kinokuniya-exclusives — ediciones exclusivas "
            "de Kinokuniya USA: variant covers, dust jackets, shikishi, ID cards, "
            "sticker packs. Cubre publishers EN principales (Kodansha, Seven Seas, "
            "Square Enix, Yen Press, VIZ, TOKYOPOP, etc.)."
        ),
        selectors={},
        max_pages=0,
        purity="manga_only",
    )


def parse_listing(html: str) -> list[Candidate]:
    """Parsea el HTML del listing de Kinokuniya Exclusives.

    Extrae todos los ``<a href>`` con patrón ``/bw/{isbn13}`` y crea un
    Candidate por cada ISBN único. El ISBN-13 se usa como URL canónica y
    como key de dedup dentro del run.

    Squarespace renderiza los productos como bloques imagen-link: la URL del
    producto está en ``href``, el título en ``<img alt>`` (no en el texto del
    anchor). Los ``*`` al inicio/final del alt son marcadores de estado de
    Squarespace (p.ej. próximamente) — se eliminan.
    """
    soup = BeautifulSoup(html, "html.parser")
    source = _virtual_source()

    seen_isbns: set[str] = set()
    candidates: list[Candidate] = []

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        m = _ISBN_URL_RE.search(href)
        if not m:
            continue

        isbn = m.group(1)
        # ISBN-13 válido: empieza con 978 o 979 (los 0810… son UPCs/EANs de regalo).
        if not (isbn.startswith("978") or isbn.startswith("979")):
            continue

        if isbn in seen_isbns:
            continue
        seen_isbns.add(isbn)

        # Título: Squarespace pone el producto en img.alt, no en anchor.text.
        img = anchor.find("img")
        raw_alt = (img.get("alt", "") if img else anchor.get_text()).strip()
        # Strip leading/trailing '*' (Squarespace status markers) + whitespace
        title = clean_text(raw_alt.strip("*").strip())
        if not title or len(title) < 3:
            continue

        url = f"{PRODUCT_BASE}{isbn}"
        image_url = f"{COVER_BASE}/{isbn}"

        # "kinokuniya exclusive" está en KEYWORD_RULES (score=45, type=retailer_exclusive)
        # — inyectarlo en la descripción asegura que detect_signals lo levante
        # aunque el título no mencione explícitamente el tipo de exclusivo.
        description = f"Kinokuniya Exclusive. ISBN: {isbn}."

        cand = candidate_from_source(
            source,
            title=title,
            url=url,
            description=description,
        )
        cand.isbn = isbn
        cand.image_url = image_url

        score_candidate(cand)
        candidates.append(cand)

    return candidates


def fetch_listing(
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
) -> str:
    """Descarga la página de exclusivos de Kinokuniya USA."""
    try:
        resp = session.get(
            LISTING_URL,
            timeout=timeout,
            headers={"Accept": "text/html,application/xhtml+xml"},
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        print(f"[kinokuniya] ERROR al obtener {LISTING_URL}: {exc}")
        return ""


def bootstrap(
    year_from: int,
    month_from: int,
    year_to: int,
    month_to: int,
    session: requests.Session,
    sleep_seconds: float = 0.0,   # noqa: ARG001 (una sola request)
    timeout: tuple[int, int] = (15, 45),
    min_score: int = 0,
    fetch_details: bool = False,   # noqa: ARG001 (detail pages devuelven 403)
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Descarga y parsea el catálogo de exclusivos de Kinokuniya USA.

    No aplica filtro de fecha — la página siempre muestra el catálogo activo
    completo (no tiene paginación histórica).
    """
    print(f"[kinokuniya] fetching {LISTING_URL}")

    html = fetch_listing(session, timeout=timeout)
    if not html:
        return []

    candidates = parse_listing(html)

    if min_score:
        candidates = [c for c in candidates if c.score >= min_score]

    print(f"[kinokuniya] {len(candidates)} candidates")

    if flush_fn and candidates:
        flush_fn(candidates)

    return candidates


def iter_year_months(
    year_from: int, month_from: int,
    year_to: int, month_to: int,    # noqa: ARG001
) -> list[tuple[int, int]]:
    """Página única sin paginación por mes — devuelve un único batch."""
    return [(year_from, month_from)]


if __name__ == "__main__":
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; manga-watch-personal/0.2)"

    cands = bootstrap(2000, 1, 2030, 12, session=s, min_score=0)
    print(f"\nTotal: {len(cands)} candidates")
    for c in cands[:20]:
        print(f"  [{c.score:3d}] {c.isbn or 'no-isbn':<14} {c.title[:60]}")
