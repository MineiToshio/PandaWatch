"""Parser de Kodansha USA — ediciones especiales de manga (US/EN).

kodansha.us es la editorial US de Kodansha; publica **deluxe hardcovers,
omnibus, box sets y collector's editions** de sus franquicias principales
(Vinland Saga, Attack on Titan, Ghost in the Shell, Battle Angel Alita, etc.).

Estrategia (investigación 2026-06-12):

1. **Discovery vía API propia** (JSON, sin scraping de HTML)::

       GET /wp-json/kodansha/v1/search-series?q={keyword}&per_page=100

   La API devuelve lotes de ~25 series por keyword. Iteramos múltiples
   keywords para cubrir el catálogo de especiales; deduplicamos por slug.

2. **Volumes desde la página de la serie** (HTML)::

       GET /series/{slug}/

   Scrapeamos ``div.volume-card a[href]`` → lista de URLs de volumen.

3. **Datos por volumen** (JSON-LD)::

       GET /series/{slug}/volume-N/

   El JSON-LD ``@type=Book`` de cada volumen contiene: nombre, URL, imagen
   (azuki.co CDN), autor. El subitem ``workExample[0]`` (Paperback) da: ISBN,
   fecha de publicación, precio USD. El precio NO se captura (decisión 2026-06-11).

Modo delta: ``year_from``/``month_from`` filtran volúmenes cuya
``datePublished`` >= esa fecha. ``year_from`` < 2010 = catálogo completo.

API pública (misma firma que los demás wiki parsers)::

    bootstrap(yf, mf, yt, mt, ...)      -> list[Candidate]
    iter_year_months(yf, mf, yt, mt)    -> [(yf, mf)]     (un único batch)
"""

from __future__ import annotations

import json
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

BASE = "https://kodansha.us"
_API_SEARCH = f"{BASE}/wp-json/kodansha/v1/search-series"
_IMAGE_BASE = "https://production.image.azuki.co"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Keywords para descubrir series especiales. La API acepta búsqueda textual
# sobre el nombre de la serie — múltiples keywords garantizan cobertura.
_SEARCH_KEYWORDS = [
    "deluxe",
    "omnibus",
    "collector",
    "hardcover",
    "box set",
    "boxset",
    "definitive",
    "complete",
]

# Señales de edición especial en el nombre de la serie.
SPECIAL_RE = re.compile(
    r"\b(?:deluxe|omnibus|box\s*set|boxset|collector(?:'s)?|hardcover"
    r"|definitive|complete\s+(?:box\s+set|edition|collection)|artbook)\b",
    re.IGNORECASE,
)


def is_special_series(name: str) -> bool:
    """¿El nombre de la serie indica una edición especial coleccionable?"""
    return bool(SPECIAL_RE.search(name))


def _virtual_source() -> Source:
    return Source(
        name="US - Kodansha USA (ediciones especiales)",
        url=f"{BASE}/",
        country="Estados Unidos",
        language="Inglés",
        publisher="Kodansha",
        source_class="official",
        kind="wiki",
        purity="manga_only",
        tags=["manga", "wiki", "kodansha", "official", "us"],
    )


def _image_url(image: Any) -> str:
    """Construye URL de imagen desde el dict de imagen de la API."""
    if isinstance(image, str) and image.startswith("http"):
        return image
    if isinstance(image, dict):
        uuid = image.get("uuid", "")
        if uuid:
            return f"{_IMAGE_BASE}/{uuid}/800.webp"
    return ""


def search_series(
    session: requests.Session,
    keyword: str,
    timeout: tuple[int, int] = (15, 45),
    max_pages: int = 10,
) -> list[dict]:
    """Busca series por keyword en la API de Kodansha. Pagina hasta obtenerlas todas."""
    out: list[dict] = []
    seen_slugs: set[str] = set()
    for page in range(1, max_pages + 1):
        try:
            resp = session.get(
                _API_SEARCH,
                params={"q": keyword, "per_page": 100, "page": page},
                headers=_HEADERS,
                timeout=timeout,
            )
            if not resp.ok:
                break
            data = resp.json()
            batch = data.get("data") or []
            if not batch:
                break
            new_items = [s for s in batch if s.get("slug") not in seen_slugs]
            for s in new_items:
                seen_slugs.add(s.get("slug", ""))
            out.extend(new_items)
            # Si count == total_count ya los tenemos todos.
            if data.get("count", 0) >= data.get("total_count", 0):
                break
        except (requests.RequestException, ValueError):
            break
    return out


def get_volume_urls(
    session: requests.Session,
    slug: str,
    timeout: tuple[int, int] = (15, 45),
) -> list[str]:
    """Scrapea la página de la serie para obtener URLs de volúmenes."""
    try:
        resp = session.get(f"{BASE}/series/{slug}/", headers=_HEADERS, timeout=timeout)
        if not resp.ok:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        urls = []
        seen: set[str] = set()
        for card in soup.select("div.volume-card"):
            a = card.find("a", href=True)
            if not a:
                continue
            href = a["href"]
            if not href.startswith("http"):
                href = f"{BASE}{href}"
            if href not in seen:
                seen.add(href)
                urls.append(href)
        return urls
    except (requests.RequestException, Exception):
        return []


def get_volume_data(
    session: requests.Session,
    vol_url: str,
    timeout: tuple[int, int] = (15, 45),
) -> dict | None:
    """Extrae datos estructurados (JSON-LD) de una página de volumen."""
    try:
        resp = session.get(vol_url, headers=_HEADERS, timeout=timeout)
        if not resp.ok:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string:
                continue
            try:
                ld = json.loads(script.string)
                graph = ld.get("@graph", [ld] if isinstance(ld, dict) else [])
                for item in graph:
                    if item.get("@type") == "Book" and item.get("name"):
                        # workExample[0] (Paperback) tiene isbn/fecha/precio.
                        examples = item.get("workExample", [])
                        if isinstance(examples, dict):
                            examples = [examples]
                        pb = next(
                            (e for e in examples
                             if "paperback" in str(e.get("bookFormat", "")).lower()),
                            examples[0] if examples else {},
                        )
                        return {
                            "title": clean_text(item.get("name", "")),
                            "url": item.get("url") or vol_url,
                            "image": item.get("image", ""),
                            "author": (item.get("author") or {}).get("name", ""),
                            "isbn": re.sub(r"[^0-9Xx]", "", pb.get("isbn", "")),
                            "published_at": pb.get("datePublished", "")[:10],
                        }
            except (json.JSONDecodeError, AttributeError):
                continue
    except (requests.RequestException, Exception):
        pass
    return None


def _from_date(year_from: int, month_from: int) -> str:
    """Fecha límite inferior para filtro delta (YYYY-MM-DD)."""
    if year_from < 2010:
        return ""
    return f"{year_from:04d}-{month_from:02d}-01"


def bootstrap(
    year_from: int,
    month_from: int,
    year_to: int,    # noqa: ARG001
    month_to: int,   # noqa: ARG001
    session: requests.Session,
    sleep_seconds: float = 0.5,
    timeout: tuple[int, int] = (15, 45),
    min_score: int = 0,
    fetch_details: bool = True,
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Descarga el catálogo de especiales de Kodansha USA.

    En modo delta (``year_from`` >= 2010) solo se emiten volúmenes con
    ``datePublished`` >= la fecha de corte.
    """
    date_from = _from_date(year_from, month_from)
    print(f"[kodansha-us] {'delta desde ' + date_from if date_from else 'catálogo completo'}")

    # 1. Descubrir series especiales por keyword.
    all_series: dict[str, dict] = {}  # slug → entry
    for kw in _SEARCH_KEYWORDS:
        batch = search_series(session, kw, timeout=timeout)
        for s in batch:
            slug = s.get("slug", "")
            if slug and slug not in all_series:
                all_series[slug] = s
        if sleep_seconds:
            time.sleep(sleep_seconds)

    # Filtrar por nombre de serie (señales de edición especial).
    special_series = {
        slug: s for slug, s in all_series.items()
        if is_special_series(s.get("name", ""))
    }
    print(f"[kodansha-us] {len(all_series)} series encontradas → {len(special_series)} especiales")

    if not special_series:
        return []

    source = _virtual_source()
    candidates: list[Candidate] = []
    pending_flush: list[Candidate] = []

    # 2-3. Para cada serie especial, obtener volúmenes y datos.
    for i, (slug, series_entry) in enumerate(special_series.items(), 1):
        series_name = series_entry.get("name", slug)
        print(f"[kodansha-us] ({i}/{len(special_series)}) {series_name}")

        vol_urls = get_volume_urls(session, slug, timeout=timeout)
        if sleep_seconds:
            time.sleep(sleep_seconds * 0.5)

        for vol_url in vol_urls:
            vol_data = get_volume_data(session, vol_url, timeout=timeout) if fetch_details else None

            if vol_data:
                # Filtro delta: saltamos volúmenes fuera del rango.
                pub_date = vol_data.get("published_at", "")
                if date_from and pub_date and pub_date < date_from:
                    continue

                title = vol_data["title"] or series_name
                img = vol_data.get("image", "")
                image_url = img if isinstance(img, str) and img.startswith("http") else _image_url(img)
                cand = candidate_from_source(
                    source,
                    title=title,
                    url=vol_data["url"],
                    description=series_entry.get("short_description") or "",
                    published_at=pub_date,
                )
                cand.isbn = vol_data.get("isbn", "")
                # datePublished del JSON-LD ES la fecha de salida del tomo.
                cand.release_date = pub_date
                cand.author = clean_text(vol_data.get("author", ""))
                if image_url:
                    cand.image_url = image_url
            else:
                # Sin detalle: solo usamos la URL del volumen.
                cand = candidate_from_source(
                    source,
                    title=series_name,
                    url=vol_url,
                    description=series_entry.get("short_description") or "",
                )
                img_url = _image_url(series_entry.get("image", ""))
                if img_url:
                    cand.image_url = img_url

            score_candidate(cand)
            if min_score and cand.score < min_score:
                continue

            candidates.append(cand)
            pending_flush.append(cand)
            if flush_fn and len(pending_flush) >= 10:
                flush_fn(pending_flush)
                pending_flush = []

            if sleep_seconds and fetch_details:
                time.sleep(sleep_seconds * 0.5)

    if flush_fn and pending_flush:
        flush_fn(pending_flush)

    print(f"[kodansha-us] {len(candidates)} candidatos emitidos")
    return candidates


def iter_year_months(
    year_from: int, month_from: int,
    year_to: int, month_to: int,    # noqa: ARG001
) -> list[tuple[int, int]]:
    """Kodansha no particiona por mes; un único batch (el filtro de fecha es interno)."""
    return [(year_from, month_from)]


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Descarga especiales de Kodansha USA")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--wiki-from", default="2000-01")
    p.add_argument("--sleep-seconds", type=float, default=0.5)
    args_cli = p.parse_args()

    yf, mf = [int(x) for x in args_cli.wiki_from.split("-")]

    def _print_flush(cands: list) -> None:
        for c in cands:
            print(f"  {c.title[:60]} | {c.url[:80]}")

    with requests.Session() as sess:
        bootstrap(
            yf, mf, yf, mf,
            session=sess,
            sleep_seconds=args_cli.sleep_seconds,
            fetch_details=True,
            flush_fn=None if args_cli.dry_run else _print_flush,
        )
