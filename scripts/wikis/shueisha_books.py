"""Parser de Shueisha Books — artbooks, magazines, databooks JP (One Piece).

shueisha.co.jp/books/ es el catálogo editorial de Shueisha. Cada libro
tiene una página individual con ISBN, precio, fecha, formato, portada
CloudFront y navegación prev/next entre volúmenes de la misma serie.

⚠️ ALCANCE Y LIMITACIÓN DE GENERALIZACIÓN (auditoría 2026-06-01):

    El DETAIL page (``contents.html?isbn=``) es server-rendered y funciona,
    pero el LISTADO / buscador de shueisha.co.jp inyecta los productos por
    JavaScript y NO expone un filtro de ediciones especiales (限定版/特装版/
    画集). Es decir: no hay forma programática (sin Playwright + reverse-
    engineering de XHR) de DESCUBRIR qué series/ediciones especiales existen.
    Por eso este parser NO es un crawler de catálogo general: descubre
    caminando los links "次巻" desde ``seed_isbn`` HARDCODEADOS — hoy todos
    de One Piece (artbooks Color Walk, One Piece Magazine, databooks JP-native).

    Las franquicias de Shueisha (Shonen Jump) ya entran al corpus por dos
    vías sin tocar el sitio JP: (1) en inglés vía el parser VIZ generalizado
    (viz_artbooks.py — VIZ es el editor oficial EN de Shueisha); (2) las
    ediciones limitadas JP vía sumikko (限定版/特装版) y booksprivilege
    (店舗特典). Este parser queda como suplemento JP-native específico de
    One Piece. Para sumar otra serie, agregar su seed ISBN a ``SERIES``.

Discovery::

    Cada serie se define con un ``seed_isbn`` (primer volumen).
    El parser arranca desde el seed y sigue los links "次巻" (siguiente)
    hasta que no hay más. En modo delta, arranca desde los últimos ISBNs
    conocidos y solo busca "次巻" nuevos.

Endpoint por libro::

    GET https://www.shueisha.co.jp/books/items/contents.html?isbn={isbn-dashes}

HTML server-rendered (no JS). Metadata en selectores estables:
- ``h1.bktitle cite b``     → título
- ``li.current-kamidigi p`` → fecha, precio, formato, ISBN
- ``figure.slide-item a``   → cover CloudFront 1200px
- ``nav.item-btn-zenkan a`` → prev/next volume ISBNs

API pública (misma firma que los demás wiki parsers)::

    parse_book_page(html, isbn)  -> dict | None
    bootstrap(yf, mf, yt, mt, session, ...) -> list[Candidate]
    iter_year_months(yf, mf, yt, mt)  -> [(yf, mf)]
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


# ── URL patterns ──────────────────────────────────────────────────
BASE_URL = "https://www.shueisha.co.jp/books/items/contents.html"
COVER_CDN = "https://dosbg3xlm0x1t.cloudfront.net/images/items"
UA = "manga-watch-personal/0.2"

# ── Regex helpers ─────────────────────────────────────────────────
_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
_PRICE_RE = re.compile(r"([\d,]+)円")
_FORMAT_RE = re.compile(r"(.+?)判[／/](\d+)ページ")
_ISBN_RE = re.compile(r"ISBN[：:]?\s*([\d\-]+)")
_NEXT_ISBN_RE = re.compile(r"isbn=([\d\-]+)")


# ── Series definitions ────────────────────────────────────────────
# Each entry: (id, name, seed_isbn, signals, product_type, description)
# seed_isbn is the FIRST volume — the parser walks forward from there.
SERIES = [
    (
        "one-piece-magazine",
        "ONE PIECE Magazine",
        "9784081022328",
        ["fanbook", "special_edition"],
        "magazine",
        "Mook with exclusive manga chapters, interviews, and bonus content.",
    ),
    (
        "one-piece-colorwalk",
        "ONE PIECE Color Walk",
        "9784088592176",
        ["artbook"],
        "artbook",
        "Official illustration collection by Eiichiro Oda.",
    ),
    (
        "one-piece-allfaces",
        "ONE PIECE All Faces",
        "9784087925968",
        ["artbook"],
        "artbook",
        "Exhaustive catalog of every character face from the manga.",
    ),
    (
        "one-piece-doors",
        "ONE PIECE Doors!",
        "9784088815596",
        ["artbook", "fanbook"],
        "artbook",
        "Collection of Oda's chapter door/cover illustrations.",
    ),
]

# Standalone ISBNs (books not in a chain — no prev/next navigation).
STANDALONE_ISBNS = [
    # Databooks
    ("9784088732114", "ONE PIECE RED Grand Characters", ["fanbook"], "fanbook",
     "Official databook — character data for East Blue + Arabasta."),
    ("9784088733586", "ONE PIECE BLUE Grand Data File", ["fanbook"], "fanbook",
     "Official databook — world and story data."),
    ("9784088740980", "ONE PIECE YELLOW Grand Elements", ["fanbook"], "fanbook",
     "Official databook — Jaya through Water 7 Saga."),
    ("9784088748484", "ONE PIECE GREEN Secret Pieces", ["fanbook"], "fanbook",
     "Official databook — Thriller Bark through Sabaody."),
    ("9784088704452", "ONE PIECE BLUE DEEP Characters World", ["fanbook"], "fanbook",
     "Official databook — Devil Fruits, Haki, New World."),
    # Misc
    ("9784087806588", "ONE PIECE PIRATE RECIPES", ["fanbook"], "fanbook",
     "Official One Piece cookbook."),
    ("9784087822519", "ONE PIECE FILM STRONG WORLD Artbook", ["artbook"], "artbook",
     "Concept art and interviews for Film Strong World."),
    ("9784088592916", "ONE PIECE Animation Logbook", ["artbook"], "artbook",
     "Anime production art collection."),
]


# ── HTML parsing ──────────────────────────────────────────────────

def _isbn_to_dashes(isbn: str) -> str:
    """Add dashes to a bare ISBN-13 for URL queries."""
    isbn = isbn.replace("-", "")
    if len(isbn) == 13:
        # 978-4-08-XXXXXX-C → standard grouping
        return f"{isbn[:3]}-{isbn[3]}-{isbn[4:6]}-{isbn[6:12]}-{isbn[12]}"
    return isbn


def _isbn_clean(isbn: str) -> str:
    return isbn.replace("-", "").strip()


def _book_url(isbn: str) -> str:
    return f"{BASE_URL}?isbn={_isbn_to_dashes(isbn)}"


def _cover_url(isbn: str) -> str:
    clean = _isbn_clean(isbn)
    return f"{COVER_CDN}/{clean}/1200/{clean}.jpg"


def parse_book_page(html: str, isbn: str) -> dict | None:
    """Parse a Shueisha book detail page and return metadata dict.

    Returns None if the page doesn't contain valid book data.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Title — h1.bktitle cite b
    title_tag = soup.select_one("h1.bktitle cite b")
    if not title_tag:
        title_tag = soup.select_one("h1.bktitle")
    if not title_tag:
        return None
    title = clean_text(title_tag.get_text())
    if not title:
        return None

    # Author — from <title> tag "TITLE／AUTHOR | 集英社"
    author = ""
    title_el = soup.find("title")
    if title_el:
        tt = title_el.get_text()
        if "／" in tt:
            author = tt.split("／")[1].split("|")[0].strip()

    # Paper edition section — li.current-kamidigi section p
    paper_section = soup.select_one("li.current-kamidigi section")
    release_date = ""
    price = ""
    format_str = ""
    pages = ""
    page_isbn = _isbn_clean(isbn)

    if paper_section:
        for p in paper_section.find_all("p"):
            text = p.get_text().strip()
            # Release date: 2017年7月7日発売
            m = _DATE_RE.search(text)
            if m:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                release_date = f"{y:04d}-{mo:02d}-{d:02d}"
                continue
            # Price: 990円（税込）
            m = _PRICE_RE.search(text)
            if m:
                price = f"¥{m.group(1)}"
                continue
            # Format: Ｂ５判／170ページ
            m = _FORMAT_RE.search(text)
            if m:
                format_str = m.group(1).strip()
                pages = m.group(2)
                continue
            # ISBN
            m = _ISBN_RE.search(text)
            if m:
                page_isbn = _isbn_clean(m.group(1))

    # Cover image — figure.slide-item a href or og:image
    cover_url = _cover_url(page_isbn)
    fig = soup.select_one("figure.slide-item a")
    if fig and fig.get("href"):
        cover_url = fig["href"]

    # Navigation — nav.item-btn-zenkan
    next_isbn = ""
    nav = soup.select_one("nav.item-btn-zenkan")
    if nav:
        links = nav.find_all("a")
        for a in links:
            href = a.get("href", "")
            text = a.get_text().strip()
            if "次巻" in text:
                m = _NEXT_ISBN_RE.search(href)
                if m:
                    next_isbn = _isbn_clean(m.group(1))

    # Imprint — small tag before title
    imprint = ""
    small = soup.select_one(".item-info-top-inner2 small")
    if small:
        imprint = small.get_text().strip()

    return {
        "title": title,
        "author": author,
        "isbn": page_isbn,
        "release_date": release_date,
        "price": price,
        "format": format_str,
        "pages": pages,
        "cover_url": cover_url,
        "next_isbn": next_isbn,
        "imprint": imprint,
        "url": _book_url(page_isbn),
    }


# ── Fetch logic ───────────────────────────────────────────────────

def fetch_book_page(
    isbn: str,
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
) -> str | None:
    """Fetch a single Shueisha book page by ISBN."""
    url = _book_url(isbn)
    try:
        resp = session.get(
            url,
            timeout=timeout,
            headers={"User-Agent": UA, "Accept": "text/html"},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        print(f"[shueisha] ERROR fetching {url}: {exc}")
        return None


def walk_series(
    seed_isbn: str,
    session: requests.Session,
    sleep_seconds: float = 0.5,
    timeout: tuple[int, int] = (10, 30),
    max_vols: int = 100,
    date_cutoff: str = "",
) -> list[dict]:
    """Walk a series from seed_isbn following "次巻" links.

    Returns list of parsed metadata dicts.
    """
    results: list[dict] = []
    current = _isbn_clean(seed_isbn)
    seen: set[str] = set()
    vol_num = 0

    while current and current not in seen and vol_num < max_vols:
        seen.add(current)
        vol_num += 1

        html = fetch_book_page(current, session, timeout=timeout)
        if html is None:
            print(f"[shueisha] {current} → 404 or error, stopping chain")
            break

        meta = parse_book_page(html, current)
        if meta is None:
            print(f"[shueisha] {current} → could not parse, stopping")
            break

        # Date filter: skip volumes before cutoff but continue walking
        if date_cutoff and meta["release_date"] and meta["release_date"] < date_cutoff:
            current = meta.get("next_isbn", "")
            if current:
                time.sleep(sleep_seconds)
            continue

        results.append(meta)
        print(f"[shueisha]   vol {vol_num}: {meta['title']} ({meta['isbn']})")

        current = meta.get("next_isbn", "")
        if current:
            time.sleep(sleep_seconds)

    return results


def fetch_standalone(
    isbn: str,
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
) -> dict | None:
    """Fetch a single standalone book page."""
    html = fetch_book_page(isbn, session, timeout=timeout)
    if html is None:
        return None
    return parse_book_page(html, isbn)


# ── Virtual source ────────────────────────────────────────────────

def _virtual_source() -> Source:
    return Source(
        name="JP - Shueisha Books",
        url="https://www.shueisha.co.jp/books/",
        country="Japón",
        language="Japanese",
        publisher="Shueisha",
        source_class="trusted_catalog",
        kind="wiki",
        enabled=True,
        tags=["wiki", "shueisha", "japan", "japanese", "artbook", "magazine"],
        notes=(
            "Shueisha's official book catalog. Covers artbooks, magazines, "
            "databooks, and companion publications for manga series."
        ),
        selectors={},
        max_pages=0,
        purity="manga_only",
    )


def _meta_to_candidate(meta: dict, signals: list[str], product_type: str,
                       description: str) -> Candidate:
    """Convert a parsed metadata dict to a Candidate."""
    source = _virtual_source()

    # Build description with hints for signal detection
    desc_parts = []
    if description:
        desc_parts.append(description)
    if meta.get("price"):
        desc_parts.append(f"Price: {meta['price']}.")
    if meta.get("format"):
        desc_parts.append(f"Format: {meta['format']}.")

    # Inject signal hints into description
    for sig in signals:
        if sig == "artbook":
            desc_parts.insert(0, "Artbook.")
        elif sig == "fanbook":
            desc_parts.insert(0, "Fanbook / Databook.")

    cand = candidate_from_source(
        source,
        title=meta["title"],
        url=meta["url"],
        description=" ".join(desc_parts),
        published_at=meta.get("release_date", ""),
    )
    cand.image_url = meta.get("cover_url", "")
    cand.release_date = meta.get("release_date", "")
    cand.price = meta.get("price", "")
    if meta.get("author"):
        cand.author = meta["author"]
    if meta.get("isbn"):
        cand.isbn = meta["isbn"]

    score_candidate(cand)
    return cand


# ── Bootstrap (main entry point) ──────────────────────────────────

def bootstrap(
    year_from: int,
    month_from: int,
    year_to: int,
    month_to: int,
    session: requests.Session,
    sleep_seconds: float = 0.5,
    timeout: tuple[int, int] = (15, 45),
    min_score: int = 0,
    fetch_details: bool = False,
    flush_fn: Callable[[list[Candidate]], None] | None = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Fetch Shueisha special publications (artbooks, magazines, databooks).

    In delta mode (year_from >= 2020): only fetch volumes published after
    the cutoff date (discovers new Magazine issues, Color Walk volumes, etc.).
    In full mode (year_from < 2020): walk entire series from vol 1.
    """
    delta = year_from >= 2020
    date_cutoff = f"{year_from:04d}-{month_from:02d}-01" if delta else ""

    mode = f"delta ≥{date_cutoff}" if delta else "full (catálogo completo)"
    print(f"[shueisha] mode={mode}, {len(SERIES)} series + {len(STANDALONE_ISBNS)} standalone")

    candidates: list[Candidate] = []
    seen_isbns: set[str] = set()

    # 1. Walk each series chain
    for series_id, name, seed_isbn, signals, ptype, desc in SERIES:
        print(f"[shueisha] Walking series: {name} (seed={seed_isbn})")
        metas = walk_series(
            seed_isbn, session,
            sleep_seconds=sleep_seconds,
            timeout=timeout,
            date_cutoff=date_cutoff,
        )
        for meta in metas:
            if meta["isbn"] in seen_isbns:
                continue
            seen_isbns.add(meta["isbn"])
            cand = _meta_to_candidate(meta, signals, ptype, desc)
            if min_score and cand.score < min_score:
                continue
            candidates.append(cand)

        if flush_fn and candidates:
            flush_fn(candidates)

    # 2. Fetch standalone books
    if not delta:  # standalone books don't change, only fetch in full mode
        print(f"[shueisha] Fetching {len(STANDALONE_ISBNS)} standalone books...")
        for isbn, title_hint, signals, ptype, desc in STANDALONE_ISBNS:
            if isbn in seen_isbns:
                continue
            meta = fetch_standalone(isbn, session, timeout=timeout)
            if meta:
                seen_isbns.add(isbn)
                cand = _meta_to_candidate(meta, signals, ptype, desc)
                if min_score and cand.score < min_score:
                    continue
                candidates.append(cand)
                print(f"[shueisha]   standalone: {meta['title']} ({isbn})")
            time.sleep(sleep_seconds)

        if flush_fn and candidates:
            flush_fn(candidates)

    print(
        f"[shueisha] Done: {len(candidates)} candidates "
        f"({len(seen_isbns)} ISBNs fetched)"
    )
    return candidates


def iter_year_months(
    year_from: int, month_from: int,
    year_to: int, month_to: int,
) -> list[tuple[int, int]]:
    """Single batch — the parser handles its own iteration internally."""
    return [(year_from, month_from)]
