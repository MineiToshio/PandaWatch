"""Parser de Seven Seas Entertainment — ediciones especiales de manga/LN (US/EN).

sevenseasentertainment.com es la editorial US (manga, manhwa, light novels,
danmei). Publica un volumen alto de **deluxe hardcovers, omnibus, box sets y
collector's editions** que ninguna fuente actual cubre sistemáticamente
(PRH Comics solo lista su carrusel activo distribuido por PRH; Otaku Calendar
captura algunos releases sueltos).

Estrategia (evaluación 2026-06-12, /watch-evaluate-sources):

1. **Listing vía WordPress REST API** (estable, sin scraping de HTML)::

       GET /wp-json/wp/v2/books?per_page=100&page=N[&after=ISO8601]

   CPT ``books`` (~6150 items). El header ``X-WP-TotalPages`` da la paginación.
   ``after=`` filtra por fecha de creación del post → modo DELTA natural
   (los anuncios nuevos son posts nuevos).

2. **Filtro local por título** (`SPECIAL_RE`): deluxe / box set / collector /
   special edition / omnibus / hardcover / artbook / anniversary. El catálogo
   es ~97% tomos regulares; solo se fetchea detalle de los que matchean.
   Exclusión: «[Mature Hardcover]» sin otro qualifier = variante sin censura
   del tomo regular, NO coleccionable (hallazgo de la evaluación).

3. **Por cada match** (2 requests):
   - ``/wp-json/wp/v2/media?parent=<id>`` → portada (la imagen de mayor
     resolución; preferencia por archivos ``*coverFRONT*``).
   - la página del libro (HTML) → ``<b>ISBN:</b>`` / ``<b>Release Date:</b>``
     / staff (Story/Art by). El precio NO se captura (decisión 2026-06-11).

⚠️ Anti-bot: el sitio devuelve 403 a clients sin headers de browser — TODAS
las requests llevan User-Agent de Chrome (``_HEADERS``). No hay Cloudflare
challenge; con UA correcto responde 200 estable.

API pública (misma firma que los demás wiki parsers)::

    parse_book(book_json)               -> Candidate | None  (sin red)
    fetch_books(session, after, ...)    -> list[dict]        (paginado)
    enrich_candidate(session, cand, id) -> None              (cover+ISBN+fecha)
    bootstrap(yf, mf, yt, mt, ...)      -> list[Candidate]
    iter_year_months(yf, mf, yt, mt)    -> [(yf, mf)]        (batch único)
"""

from __future__ import annotations

import re
import sys
import time
from datetime import datetime
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

BASE = "https://sevenseasentertainment.com"
API_BOOKS = f"{BASE}/wp-json/wp/v2/books"
API_MEDIA = f"{BASE}/wp-json/wp/v2/media"

# El sitio responde 403 a clients sin pinta de browser. Sin Cloudflare
# challenge: basta el UA. (Evaluación 2026-06-12.)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Qualifiers de edición especial en el TÍTULO. `hardcover` califica solo
# (la categoría hardcover es ~85% especiales reales) SALVO la variante
# "[Mature Hardcover]" sin otro qualifier (uncensored del tomo regular).
# `omnibus` a secas NO está (gotcha #18: 2-en-1 rústica = tomo grueso, el
# gate de coleccionables lo expulsaría igual); los omnibus premium entran
# por deluxe/hardcover ("Deluxe Edition (Vol. 4-6 Hardcover Omnibus)").
SPECIAL_RE = re.compile(
    r"\b(?:deluxe|box\s*set|boxset|collector(?:'s)?|special\s+edition"
    r"|hardcover|artbook|art\s+of|anniversary\s+edition"
    r"|(?:full\s+)?colou?r\s+edition)\b",
    re.IGNORECASE,
)
_MATURE_RE = re.compile(r"\bmature\s+hardcover\b", re.IGNORECASE)
_REAL_QUALIFIER_RE = re.compile(
    r"\b(?:deluxe|box\s*set|boxset|collector|special\s+edition|omnibus"
    r"|artbook|art\s+of|anniversary)\b",
    re.IGNORECASE,
)

_ISBN_RE = re.compile(r"<b>\s*ISBN:\s*</b>\s*([0-9Xx][0-9Xx\-\s]{8,20})")
_RELEASE_RE = re.compile(r"<b>\s*Release Date:\s*</b>\s*([A-Z][a-z]+ \d{1,2}, \d{4})")
_STAFF_RE = re.compile(
    r"<strong>\s*(?:Story (?:&(?:amp;)? |and )?Art by|Story by|Art by|Author):?\s*"
    r"</strong>:?\s*([^<]{2,60})",
    re.IGNORECASE,
)


def is_special_title(title: str) -> bool:
    """¿El título indica una edición especial coleccionable?"""
    if not SPECIAL_RE.search(title):
        return False
    if _MATURE_RE.search(title) and not _REAL_QUALIFIER_RE.search(
        _MATURE_RE.sub("", title)
    ):
        return False
    return True


def _virtual_source() -> Source:
    return Source(
        name="US - Seven Seas (ediciones especiales)",
        url=f"{BASE}/books/",
        country="Estados Unidos",
        language="Inglés",
        publisher="Seven Seas",
        source_class="official",
        kind="wiki",
        purity="manga_only",
        tags=["manga", "wiki", "sevenseas", "official", "us"],
    )


def parse_book(book: dict) -> Candidate | None:
    """Entry del API ``books`` → Candidate (sin red). None si no es especial."""
    if not isinstance(book, dict):
        return None
    raw_title = ((book.get("title") or {}).get("rendered") or "").strip()
    url = (book.get("link") or "").strip()
    if not raw_title or not url:
        return None
    title = clean_text(BeautifulSoup(raw_title, "html.parser").get_text())
    if not is_special_title(title):
        return None

    content = ((book.get("content") or {}).get("rendered") or "")
    descr = clean_text(BeautifulSoup(content, "html.parser").get_text(" "))[:1200]

    cand = candidate_from_source(
        _virtual_source(),
        title=title,
        url=url,
        description=descr,
        published_at=(book.get("date") or "")[:10],
    )
    score_candidate(cand)
    return cand


def fetch_books(
    session: requests.Session,
    after: str = "",
    timeout: tuple[int, int] = (15, 45),
    sleep_seconds: float = 0.3,
    max_pages: int = 80,
) -> list[dict]:
    """Pagina el CPT books completo (o desde ``after`` ISO8601 en modo delta)."""
    out: list[dict] = []
    page = 1
    total_pages = 0  # se fija con el header cuando aparece (sticky: algunos
    # hops de caché/CDN lo omiten — NO tratar su ausencia como "última página")
    while page <= max_pages:
        params: dict[str, Any] = {"per_page": 100, "page": page,
                                  "orderby": "date", "order": "desc"}
        if after:
            params["after"] = after

        # Bajo ráfaga el WAF a veces devuelve 200 con cuerpo no-JSON o corta
        # la conexión — una página perdida NO debe truncar el catálogo en
        # silencio (bug 2026-06-12: el run se cortaba en ~2245/6153 books).
        batch = None
        for attempt in range(3):
            try:
                resp = session.get(API_BOOKS, params=params, headers=_HEADERS,
                                   timeout=timeout)
                if resp.status_code == 400:  # página fuera de rango = fin real
                    return out
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    batch = data
                    break
            except (requests.RequestException, ValueError):
                pass
            time.sleep(1.5 * (attempt + 1))
        if batch is None:
            print(f"[sevenseas] WARN página {page} falló 3 intentos — "
                  f"continúo con {len(out)} books")
            break
        if not batch:
            break
        out.extend(batch)
        hdr = resp.headers.get("X-WP-TotalPages")
        if hdr and str(hdr).isdigit():
            total_pages = max(total_pages, int(hdr))
        if total_pages and page >= total_pages:
            break
        if len(batch) < 100 and not after:
            break
        page += 1
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return out


def _parse_release_date(raw: str) -> str:
    """'February 17, 2026' → '2026-02-17'."""
    try:
        return datetime.strptime(raw.strip(), "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def enrich_candidate(
    session: requests.Session,
    cand: Candidate,
    book_id: int,
    timeout: tuple[int, int] = (15, 45),
) -> None:
    """Completa cover (media API) + ISBN/fecha/autor (HTML detail). Best-effort."""
    # Portada: imagen de mayor resolución; preferencia por '*coverFRONT*'.
    try:
        resp = session.get(API_MEDIA, params={"parent": book_id, "per_page": 20},
                           headers=_HEADERS, timeout=timeout)
        if resp.ok:
            media = resp.json() or []
            best, best_key = "", (-1, -1)
            for m in media:
                u = (m.get("source_url") or "").strip()
                if not u:
                    continue
                w = int((m.get("media_details") or {}).get("width") or 0)
                key = (1 if "coverfront" in u.lower() else 0, w)
                if key > best_key:
                    best, best_key = u, key
            if best:
                cand.image_url = best
    except (requests.RequestException, ValueError):
        pass

    # ISBN / release date / staff desde la página del libro.
    try:
        resp = session.get(cand.url, headers=_HEADERS, timeout=timeout)
        if not resp.ok:
            return
        html = resp.text
        m = _ISBN_RE.search(html)
        if m:
            cand.isbn = re.sub(r"[^0-9Xx]", "", m.group(1))
        m = _RELEASE_RE.search(html)
        if m:
            cand.release_date = _parse_release_date(m.group(1))
        m = _STAFF_RE.search(html)
        if m:
            cand.author = clean_text(m.group(1))
    except requests.RequestException:
        pass


def bootstrap(
    year_from: int,
    month_from: int,
    year_to: int,    # noqa: ARG001
    month_to: int,   # noqa: ARG001
    session: requests.Session,
    sleep_seconds: float = 0.3,
    timeout: tuple[int, int] = (15, 45),
    min_score: int = 0,
    fetch_details: bool = True,
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Descarga el catálogo books de Seven Seas y emite las ediciones especiales.

    ``year_from``/``month_from`` → modo DELTA vía el param ``after`` del API
    (posts creados desde esa fecha). ``year_from`` < 2010 = catálogo completo.
    """
    after = (f"{year_from:04d}-{month_from:02d}-01T00:00:00"
             if year_from >= 2010 else "")
    print(f"[sevenseas] fetching {API_BOOKS} | "
          f"{'after=' + after if after else '(catálogo completo)'}")

    books = fetch_books(session, after=after, timeout=timeout,
                        sleep_seconds=sleep_seconds)
    print(f"[sevenseas] {len(books)} books en el listing")

    candidates: list[Candidate] = []
    seen_urls: set[str] = set()
    pending_flush: list[Candidate] = []
    for book in books:
        cand = parse_book(book)
        if cand is None or cand.url in seen_urls:
            continue
        seen_urls.add(cand.url)
        if fetch_details:
            enrich_candidate(session, cand, int(book.get("id") or 0),
                             timeout=timeout)
            # re-score con la metadata enriquecida (fecha/isbn no cambian
            # señales, pero clean/normalize sí pueden)
            score_candidate(cand)
            if sleep_seconds:
                time.sleep(sleep_seconds)
        if min_score and cand.score < min_score:
            continue
        candidates.append(cand)
        pending_flush.append(cand)
        # Flush incremental: el enrich es red por item — un write único al
        # final perdería todo si el proceso muere (convención del repo).
        if flush_fn and len(pending_flush) >= 10:
            flush_fn(pending_flush)
            pending_flush = []

    if flush_fn and pending_flush:
        flush_fn(pending_flush)
    print(f"[sevenseas] {len(candidates)} candidatos especiales")
    return candidates


def iter_year_months(
    year_from: int, month_from: int,
    year_to: int, month_to: int,    # noqa: ARG001
) -> list[tuple[int, int]]:
    """El API no particiona por mes; un único batch (after= hace el delta)."""
    return [(year_from, month_from)]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingesta Seven Seas especiales")
    parser.add_argument("--wiki-from", default="",
                        help="Filtro delta: YYYY-MM. Vacío = catálogo completo.")
    parser.add_argument("--no-details", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    yf, mf = 2000, 1
    if args.wiki_from:
        p = args.wiki_from.split("-")
        yf, mf = int(p[0]), int(p[1])

    s = requests.Session()
    cands = bootstrap(yf, mf, 2030, 12, session=s,
                      fetch_details=not args.no_details, min_score=0)
    if args.limit:
        cands = cands[:args.limit]
    for c in cands[:30]:
        print(f"  [{c.score:3d}] {c.title[:70]} | {c.release_date} | "
              f"isbn={c.isbn or '-'} | img={'sí' if c.image_url else 'no'}")
    print(f"\nTotal: {len(cands)}")
