"""Parser de VIZ Media — artbooks, box sets, companion books EN.

viz.com vende publicaciones especiales de manga en inglés: Color Walk
Compendiums, box sets, cookbooks, artbooks, spin-off manga. Cada serie
tiene una listing page en /manga-books/art-book/<series>/all que lista
los volúmenes, y cada volumen tiene un detail page en
/manga-books/art-book/<series>/product/<id> con metadata completa
(ISBN, precio, fecha, formato, portada CloudFront).

Discovery::

    Listing pages conocidas → product links → detail pages con metadata.
    Catálogo chico (~20-30 items), sin paginación.

Endpoints::

    Listing: GET https://www.viz.com/manga-books/art-book/<series>/all
    Detail:  GET https://www.viz.com/manga-books/art-book/<series>/product/<id>

HTML server-rendered. Cover URL: ``https://dw9to29mmj727.cloudfront.net/products/{isbn10}.jpg``

API pública::

    parse_product_page(html) -> dict | None
    bootstrap(yf, mf, yt, mt, session, ...) -> list[Candidate]
    iter_year_months(yf, mf, yt, mt) -> [(yf, mf)]
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    from scripts.manga_watch import (
        Candidate,
        Source,
        candidate_from_source,
        clean_text,
        score_candidate,
    )
except ImportError:
    from manga_watch import (
        Candidate,
        Source,
        candidate_from_source,
        clean_text,
        score_candidate,
    )


VIZ_BASE = "https://www.viz.com"
COVER_CDN = "https://dw9to29mmj727.cloudfront.net/products"
UA = "manga-watch-personal/0.2"

# ── Listing pages to crawl ────────────────────────────────────────
# Each: (url_path, category_hint)
LISTING_PAGES = [
    # One Piece artbooks
    ("/manga-books/art-book/one-piece-color-walk-compendium/all", "artbook"),
    # Box sets
    ("/manga-books/box-set/one-piece/all", "box_set"),
    # More categories can be added here as needed
]

# Known product detail URLs for items NOT discoverable from listings
# (standalone products, special editions, companion books).
# Each: (url_path, signals, product_type, description)
KNOWN_PRODUCTS = [
    ("/manga-books/art-book/one-piece-pirate-recipes/product/7142",
     ["fanbook"], "fanbook", "Official One Piece cookbook."),
    ("/manga-books/art-book/set-sail-the-art-and-making-of-one-piece/product/8126",
     ["artbook", "hardcover"], "artbook",
     "Behind-the-scenes artbook for the Netflix live-action."),
]

# Month map for date parsing
_MONTH_MAP: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


# ── HTML parsing ──────────────────────────────────────────────────

def _parse_date(raw: str) -> str:
    """'July 03, 2018' or 'July 3, 2018' → '2018-07-03'."""
    raw = raw.strip()
    for pfx in ("On sale ", "On Sale "):
        if raw.startswith(pfx):
            raw = raw[len(pfx):]
    try:
        parts = raw.replace(",", "").split()
        if len(parts) == 3:
            m = _MONTH_MAP.get(parts[0].lower())
            d, y = int(parts[1]), int(parts[2])
            if m:
                return f"{y:04d}-{m:02d}-{d:02d}"
    except (ValueError, IndexError):
        pass
    return ""


def parse_product_page(html: str) -> dict | None:
    """Parse a VIZ product detail page.

    Returns dict with: title, isbn, price, release_date, pages,
    format, cover_url, description, trim_size, url.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Title — typically in an h2 tag
    title = ""
    for h in soup.find_all(["h1", "h2"]):
        text = h.get_text().strip()
        # Skip navigation/menu headers
        if text and len(text) > 5 and "manga" not in text.lower()[:10]:
            title = clean_text(text)
            break
    if not title:
        return None

    # Look for dt/dd pairs or labeled data
    isbn = ""
    release_date = ""
    pages = ""
    trim_size = ""
    price = ""
    fmt = ""

    # Try dt/dd pairs first
    for dt in soup.find_all("dt"):
        label = dt.get_text().strip().lower()
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        val = dd.get_text().strip()

        if "isbn" in label:
            isbn = val.replace("-", "").strip()
        elif "release" in label:
            release_date = _parse_date(val)
        elif "length" in label or "pages" in label:
            pages = re.sub(r"[^\d]", "", val)
        elif "trim" in label:
            trim_size = val
        elif "imprint" in label:
            pass  # skip for now

    # Try finding ISBN in any text
    if not isbn:
        for text in soup.stripped_strings:
            if re.match(r"978[\d\-]{10,}", text.replace(" ", "")):
                isbn = text.replace("-", "").replace(" ", "").strip()[:13]
                break

    # Price — look for dollar amount
    if not price:
        for text in soup.stripped_strings:
            m = re.search(r"\$(\d+\.\d{2})", text)
            if m:
                price = f"${m.group(1)}"
                break

    # Format — look for "Hardcover" or "Paperback"
    for text in soup.stripped_strings:
        tl = text.strip().lower()
        if tl in ("hardcover", "paperback", "boxed set", "box set"):
            fmt = text.strip()
            break

    # Cover image — look for cloudfront URL
    cover_url = ""
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "cloudfront.net" in src:
            cover_url = src
            break
    # Also check og:image
    if not cover_url:
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            cover_url = og["content"]

    # Description
    description = ""
    for p in soup.find_all("p"):
        text = p.get_text().strip()
        if len(text) > 50 and not text.startswith("©"):
            description = text[:500]
            break

    if not isbn:
        return None

    return {
        "title": title,
        "isbn": isbn,
        "price": price,
        "release_date": release_date,
        "pages": pages,
        "format": fmt,
        "trim_size": trim_size,
        "cover_url": cover_url,
        "description": description,
    }


def fetch_listing_page(
    url_path: str,
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
) -> list[str]:
    """Fetch a VIZ listing page and return product detail URL paths."""
    url = f"{VIZ_BASE}{url_path}"
    try:
        resp = session.get(
            url, timeout=timeout,
            headers={"User-Agent": UA, "Accept": "text/html"},
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[viz] ERROR listing {url}: {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    product_urls: list[str] = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/product/" in href and href not in product_urls:
            product_urls.append(href)

    print(f"[viz] {url_path} → {len(product_urls)} product links")
    return product_urls


def fetch_product(
    url_path: str,
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
) -> dict | None:
    """Fetch a VIZ product detail page and parse it."""
    url = f"{VIZ_BASE}{url_path}" if url_path.startswith("/") else url_path
    try:
        resp = session.get(
            url, timeout=timeout,
            headers={"User-Agent": UA, "Accept": "text/html"},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[viz] ERROR product {url}: {exc}")
        return None

    meta = parse_product_page(resp.text)
    if meta:
        meta["url"] = url
    return meta


# ── Virtual source ────────────────────────────────────────────────

def _virtual_source() -> Source:
    return Source(
        name="US - VIZ Media Artbooks",
        url="https://www.viz.com/manga-books",
        country="Estados Unidos",
        language="English",
        publisher="VIZ Media",
        source_class="trusted_catalog",
        kind="wiki",
        enabled=True,
        tags=["wiki", "viz", "usa", "english", "artbook", "box_set"],
        notes=(
            "VIZ Media's special publications catalog. Covers One Piece "
            "Color Walk Compendiums, box sets, artbooks, companion books."
        ),
        selectors={},
        max_pages=0,
        purity="manga_only",
    )


def _meta_to_candidate(meta: dict, signals: list[str],
                       product_type: str, extra_desc: str = "") -> Candidate:
    """Convert parsed metadata to a Candidate."""
    source = _virtual_source()

    desc_parts = []
    if extra_desc:
        desc_parts.append(extra_desc)
    if meta.get("format"):
        desc_parts.append(f"{meta['format']}.")
    if signals:
        for s in signals:
            if s == "artbook":
                desc_parts.insert(0, "Artbook.")
            elif s == "box_set":
                desc_parts.insert(0, "Box Set.")
            elif s == "hardcover":
                desc_parts.insert(0, "Hardcover.")

    cand = candidate_from_source(
        source,
        title=meta["title"],
        url=meta.get("url", ""),
        description=" ".join(desc_parts),
        published_at=meta.get("release_date", ""),
    )
    cand.image_url = meta.get("cover_url", "")
    cand.release_date = meta.get("release_date", "")
    cand.price = meta.get("price", "")
    if meta.get("isbn"):
        cand.isbn = meta["isbn"]

    score_candidate(cand)
    return cand


def _infer_signals(title: str, fmt: str) -> list[str]:
    """Infer signal_types from title and format."""
    tl = title.lower()
    signals = []
    if "art book" in tl or "artbook" in tl or "color walk" in tl:
        signals.append("artbook")
    if "box set" in tl or "boxed" in fmt.lower():
        signals.append("box_set")
    if "hardcover" in fmt.lower():
        signals.append("hardcover")
    if "compendium" in tl or "collector" in tl:
        signals.append("collector")
    if "recipe" in tl or "cookbook" in tl:
        signals.append("fanbook")
    if not signals:
        signals = ["special_edition"]
    return signals


# ── Bootstrap ─────────────────────────────────────────────────────

def bootstrap(
    year_from: int,
    month_from: int,
    year_to: int,
    month_to: int,
    session: requests.Session,
    sleep_seconds: float = 1.0,
    timeout: tuple[int, int] = (15, 45),
    min_score: int = 0,
    fetch_details: bool = True,
    flush_fn: Callable[[list[Candidate]], None] | None = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Fetch VIZ special publications catalog.

    Discovers products from listing pages and known product URLs.
    """
    delta = year_from >= 2020
    date_cutoff = f"{year_from:04d}-{month_from:02d}-01" if delta else ""

    print(f"[viz] mode={'delta ≥' + date_cutoff if delta else 'full'}")

    candidates: list[Candidate] = []
    seen_isbns: set[str] = set()
    product_paths: list[tuple[str, list[str], str, str]] = []

    # 1. Discover products from listing pages
    for listing_path, category in LISTING_PAGES:
        paths = fetch_listing_page(listing_path, session, timeout=timeout)
        for p in paths:
            product_paths.append((p, [], category, ""))
        time.sleep(sleep_seconds)

    # 2. Add known standalone products
    for path, sigs, ptype, desc in KNOWN_PRODUCTS:
        product_paths.append((path, sigs, ptype, desc))

    print(f"[viz] {len(product_paths)} product URLs to fetch")

    # 3. Fetch each product detail page
    for path, preset_sigs, preset_ptype, preset_desc in product_paths:
        meta = fetch_product(path, session, timeout=timeout)
        if meta is None:
            continue

        isbn = meta.get("isbn", "")
        if isbn and isbn in seen_isbns:
            continue
        if isbn:
            seen_isbns.add(isbn)

        # Date filter
        if date_cutoff and meta.get("release_date") and meta["release_date"] < date_cutoff:
            continue

        # Determine signals
        signals = preset_sigs or _infer_signals(
            meta.get("title", ""), meta.get("format", ""))
        ptype = preset_ptype or ("artbook" if "artbook" in signals else "special")

        cand = _meta_to_candidate(meta, signals, ptype, preset_desc)
        if min_score and cand.score < min_score:
            continue

        candidates.append(cand)
        print(f"[viz]   {meta['title']} ({isbn})")
        time.sleep(sleep_seconds)

    if flush_fn and candidates:
        flush_fn(candidates)

    print(f"[viz] Done: {len(candidates)} candidates")
    return candidates


def iter_year_months(
    year_from: int, month_from: int,
    year_to: int, month_to: int,
) -> list[tuple[int, int]]:
    """Single batch — small catalog, no monthly iteration needed."""
    return [(year_from, month_from)]
