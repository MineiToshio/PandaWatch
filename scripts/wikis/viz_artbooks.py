"""Parser de VIZ Media — ediciones especiales EN (US), catálogo COMPLETO.

viz.com es el editor oficial en inglés del catálogo de Shueisha (Shonen
Jump: One Piece, Naruto, Bleach, Jujutsu Kaisen, Chainsaw Man…) además de
sus propias licencias. Vende ediciones especiales físicas: box sets,
deluxe / definitive editions, hardcovers, collector's / anniversary /
legendary editions, artbooks (Color Walk Compendium), companion books.

Discovery GENERALIZADO (no hardcodeado) — calendario mensual::

    GET https://www.viz.com/calendar/{YYYY}/{M}  (server-rendered, sin JS)

El calendario lista TODOS los lanzamientos del mes con la edición codificada
en el slug de la URL del producto y el formato en el sufijo del path:

    /manga-books/manga/vagabond-definitive-edition-volume-5-0/product/8681/hardcover
    /manga-books/art-book/one-piece-color-walk-compendium-.../product/.../hardcover
    /manga-books/manga/one-piece-box-set-.../product/...

El parser PRE-FILTRA por la URL (segmento ``art-book``, sufijo ``/hardcover``,
o keywords de edición especial en el slug) para quedarse SOLO con ediciones
especiales — los tomos paperback regulares se descartan sin hitear el detail
page. Los omnibus / 3-in-1 "pelados" NO califican solos (gotcha #18); el gate
``is_collectible_edition`` aguas abajo termina de filtrar.

El calendario llega hasta ~2013 (verificado), así que la iteración mensual
cubre el catálogo histórico completo. NO requiere listas hardcodeadas por
serie. La fecha de lanzamiento sale del mes del calendario (el detail page de
VIZ no expone la fecha). El resto de metadata (título, ISBN, precio, portada)
sale del detail page server-rendered.

Cover URL: la imagen real de CloudFront del detail page
(``dw9to29mmj727.cloudfront.net/products/{isbn10}.{jpg|png}``).

API pública (misma firma que los demás wiki parsers)::

    parse_product_page(html)                   -> dict | None
    fetch_calendar_month(y, m, session)        -> list[str]  (product paths)
    bootstrap(yf, mf, yt, mt, session, ...)    -> list[Candidate]
    iter_year_months(yf, mf, yt, mt)           -> list[(year, month)]
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


VIZ_BASE = "https://www.viz.com"
CALENDAR_URL = "https://www.viz.com/calendar"
UA = "Mozilla/5.0 (compatible; manga-watch-personal/0.2)"

# El calendario de VIZ no tiene datos antes de ~2013 (lanzamiento del catálogo
# online). Clamp para no malgastar ~150 requests vacíos en modo full.
_MIN_YEAR = 2013

# Product URL: /manga-books/{manga|art-book}/{slug}/product/{id}[/{format}]
_PRODUCT_RE = re.compile(r"/(?:manga-books|read)/(manga|art-book)/([^/]+)/product/(\d+)(?:/(\w+))?")

# Keywords de edición especial en el slug de la URL. Cada uno → (signal, product_type).
# NOTA (gotcha #18): "omnibus" / "3-in-1" NO están acá — un omnibus pelado no
# califica solo; sí lo hace si además es hardcover (sufijo /hardcover) o tiene
# otro qualifier premium.
_SLUG_SIGNALS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\bbox-set\b"),                "box_set",      "boxset"),
    (re.compile(r"\bcomplete-box\b"),           "box_set",      "boxset"),
    (re.compile(r"\bdeluxe\b"),                 "deluxe",       "special"),
    (re.compile(r"\bdefinitive-edition\b"),     "deluxe",       "special"),
    (re.compile(r"\blegendary-edition\b"),      "deluxe",       "special"),
    (re.compile(r"\bcollector"),                "collector",    "special"),
    (re.compile(r"\d+\w*-anniversary"),         "lore_edition", "special"),
    (re.compile(r"\bcolor-walk\b"),             "artbook",      "artbook"),
    (re.compile(r"\bcompendium\b"),             "artbook",      "artbook"),
    (re.compile(r"\billustration"),             "artbook",      "artbook"),
    (re.compile(r"\bart-of\b|\bartbook\b|art-book"), "artbook", "artbook"),
    (re.compile(r"\bfanbook\b|\brecipes?\b|\bcookbook\b"), "fanbook", "fanbook"),
]

_MONTH_MAP: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


# ── URL-based special-edition filter ──────────────────────────────

def special_signals_from_url(href: str) -> tuple[bool, list[str], str]:
    """Decide si una URL de producto VIZ es una edición especial.

    Devuelve ``(qualifies, signals, product_type)``. Pre-filtro barato que
    evita hitear el detail page de los miles de tomos paperback regulares.

    Califica si:
    - el path es ``/art-book/`` (artbooks), o
    - el sufijo de formato es ``/hardcover``, o
    - el slug contiene un keyword de edición especial (box-set, deluxe,
      definitive-edition, collector, anniversary, color-walk, etc.).
    """
    m = _PRODUCT_RE.search(href)
    if not m:
        return False, [], ""
    section, slug, _pid, fmt = m.group(1), m.group(2), m.group(3), (m.group(4) or "")

    signals: list[str] = []
    product_type = ""

    if section == "art-book":
        signals.append("artbook")
        product_type = "artbook"

    if fmt.lower() == "hardcover":
        signals.append("hardcover")
        if not product_type:
            product_type = "special"

    for pat, sig, ptype in _SLUG_SIGNALS:
        if pat.search(slug):
            if sig not in signals:
                signals.append(sig)
            if not product_type or product_type == "special":
                product_type = ptype

    qualifies = bool(signals)
    if qualifies and not product_type:
        product_type = "special"
    return qualifies, signals, product_type


# ── HTML parsing ──────────────────────────────────────────────────

def _parse_date(raw: str) -> str:
    """'July 03, 2018' → '2018-07-03'."""
    raw = raw.strip()
    for pfx in ("On sale ", "On Sale ", "Release Date ", "Publication Date "):
        if raw.startswith(pfx):
            raw = raw[len(pfx):]
    try:
        parts = raw.replace(",", "").split()
        if len(parts) == 3:
            mm = _MONTH_MAP.get(parts[0].lower())
            d, y = int(parts[1]), int(parts[2])
            if mm:
                return f"{y:04d}-{mm:02d}-{d:02d}"
    except (ValueError, IndexError):
        pass
    return ""


def parse_product_page(html: str) -> dict | None:
    """Parsea un detail page de producto VIZ.

    Devuelve dict con title, isbn, format, cover_url, description.
    (La fecha NO está en el detail page de VIZ — se setea desde el calendario.)
    """
    soup = BeautifulSoup(html, "html.parser")

    # Título — og:title es la fuente más confiable: "VIZ: See {title}".
    title = ""
    og_t = soup.find("meta", property="og:title")
    if og_t and og_t.get("content"):
        title = re.sub(r"^VIZ:\s*See\s+", "", og_t["content"]).strip()
    if not title:
        for h in soup.find_all(["h1", "h2"]):
            text = h.get_text().strip()
            if text and len(text) > 5 and "manga" not in text.lower()[:10]:
                title = clean_text(text)
                break
    if not title:
        return None
    title = clean_text(title)

    # ISBN-13: regex sobre el texto (978/979 + 10 dígitos).
    isbn = ""
    for text in soup.stripped_strings:
        cleaned = text.replace("-", "").replace(" ", "")
        m = re.search(r"\b(97[89]\d{10})\b", cleaned)
        if m:
            isbn = m.group(1)
            break

    # Portada CloudFront real (skip placeholders del CDN).
    cover_url = ""
    for img in soup.find_all("img"):
        src = img.get("src", "") or ""
        if "cloudfront.net/products/" in src and "placeholder" not in src:
            cover_url = src
            break
    if not cover_url:
        og = soup.find("meta", property="og:image")
        if og and og.get("content") and "placeholder" not in og["content"]:
            cover_url = og["content"]

    # Fallback de ISBN desde la portada CloudFront (/products/{isbn10}.ext).
    if not isbn and cover_url:
        mm = re.search(r"/products/(\d{9}[\dXx])\.", cover_url)
        if mm:
            isbn = _isbn10_to_13(mm.group(1))

    # Formato — Hardcover / Paperback / Box set.
    fmt = ""
    for text in soup.stripped_strings:
        tl = text.strip().lower()
        if tl in ("hardcover", "paperback", "boxed set", "box set"):
            fmt = text.strip()
            break

    # Descripción larga.
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
        "format": fmt,
        "cover_url": cover_url,
        "description": description,
    }


def _isbn10_to_13(isbn10: str) -> str:
    """Convierte ISBN-10 → ISBN-13 (prefijo 978 + recálculo de dígito)."""
    core = "978" + isbn10[:9]
    total = sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(core))
    check = (10 - total % 10) % 10
    return core + str(check)


# ── HTTP ──────────────────────────────────────────────────────────

def fetch_calendar_month(
    year: int,
    month: int,
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
) -> list[str]:
    """Descarga un mes del calendario de VIZ y devuelve los paths de producto
    que pre-califican como edición especial (deduplicados)."""
    url = f"{CALENDAR_URL}/{year}/{month}"
    try:
        resp = session.get(url, timeout=timeout,
                           headers={"User-Agent": UA, "Accept": "text/html"})
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[viz] ERROR calendar {url}: {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    seen: set[str] = set()
    paths: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/product/" not in href:
            continue
        # Normalizar al path canónico sin el sufijo de formato para dedup.
        m = _PRODUCT_RE.search(href)
        if not m:
            continue
        key = m.group(0)
        if key in seen:
            continue
        qualifies, _sigs, _pt = special_signals_from_url(href)
        if not qualifies:
            continue
        seen.add(key)
        paths.append(href)
    return paths


def fetch_product(
    url_path: str,
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
) -> dict | None:
    """Descarga y parsea un detail page de producto VIZ."""
    url = f"{VIZ_BASE}{url_path}" if url_path.startswith("/") else url_path
    try:
        resp = session.get(url, timeout=timeout,
                           headers={"User-Agent": UA, "Accept": "text/html"})
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


# ── Candidate building ────────────────────────────────────────────

def _virtual_source() -> Source:
    return Source(
        name="US - VIZ Media Special Editions",
        url=CALENDAR_URL,
        country="Estados Unidos",
        language="English",
        publisher="VIZ Media",
        source_class="trusted_catalog",
        kind="wiki",
        enabled=True,
        tags=["wiki", "viz", "usa", "english", "special-edition",
              "box_set", "artbook", "hardcover"],
        notes=(
            "viz.com/calendar — catálogo completo de ediciones especiales EN "
            "de VIZ Media (editor oficial en inglés de Shueisha/Shonen Jump). "
            "Discovery por calendario mensual; pre-filtro por URL (art-book / "
            "hardcover / box-set / deluxe / definitive / collector / artbook). "
            "Cubre el catálogo histórico desde ~2013."
        ),
        selectors={},
        max_pages=0,
        purity="manga_only",
    )


def _meta_to_candidate(
    meta: dict,
    signals: list[str],
    product_type: str,
    release_date: str,
    source: Source,
) -> Candidate:
    """Construye un Candidate desde la metadata + signals derivadas de la URL."""
    # Hints en la descripción para que detect_signals levante las señales.
    hint_map = {
        "artbook": "Artbook.", "box_set": "Box Set.", "hardcover": "Hardcover.",
        "deluxe": "Deluxe edition.", "collector": "Collector's Edition.",
        "lore_edition": "Anniversary Edition.", "fanbook": "Fanbook.",
    }
    parts: list[str] = []
    for s in signals:
        if hint_map.get(s):
            parts.append(hint_map[s])
    if meta.get("format"):
        parts.append(f"{meta['format']}.")
    if meta.get("description"):
        parts.append(meta["description"])
    description = " ".join(parts).strip()

    cand = candidate_from_source(
        source,
        title=meta["title"],
        url=meta.get("url", ""),
        description=description,
        published_at=release_date,
    )
    cand.isbn = meta.get("isbn", "")
    cand.image_url = meta.get("cover_url", "")
    cand.release_date = release_date

    score_candidate(cand)
    return cand


# ── Bootstrap ─────────────────────────────────────────────────────

def iter_year_months(
    year_from: int, month_from: int,
    year_to: int, month_to: int,
) -> list[tuple[int, int]]:
    """Pares (year, month) en el rango [from, to], con clamp a ``_MIN_YEAR``."""
    if year_from < _MIN_YEAR:
        year_from, month_from = _MIN_YEAR, 1
    pairs: list[tuple[int, int]] = []
    y, m = year_from, month_from
    while (y, m) <= (year_to, month_to):
        pairs.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
        if y > year_to + 5:
            break
    return pairs


def bootstrap(
    year_from: int,
    month_from: int,
    year_to: int,
    month_to: int,
    session: requests.Session,
    sleep_seconds: float = 1.0,
    timeout: tuple[int, int] = (15, 45),
    min_score: int = 0,
    fetch_details: bool = True,  # noqa: ARG001
    flush_fn: Callable[[list[Candidate]], None] | None = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Descubre ediciones especiales de VIZ recorriendo el calendario mensual.

    Para cada mes: lista los productos, pre-filtra por URL las ediciones
    especiales, fetchea el detail page de cada una y construye el Candidate.
    Dedup por ISBN cross-month. La fecha sale del mes del calendario.
    """
    pairs = iter_year_months(year_from, month_from, year_to, month_to)
    source = _virtual_source()
    all_candidates: list[Candidate] = []
    seen_isbns: set[str] = set()

    print(f"[viz] {len(pairs)} meses a recorrer "
          f"({pairs[0][0]}-{pairs[0][1]:02d} → {pairs[-1][0]}-{pairs[-1][1]:02d})")

    for idx, (y, m) in enumerate(pairs, start=1):
        paths = fetch_calendar_month(y, m, session, timeout=timeout)
        kept: list[Candidate] = []
        for href in paths:
            qualifies, signals, ptype = special_signals_from_url(href)
            if not qualifies:
                continue
            meta = fetch_product(href, session, timeout=timeout)
            if meta is None:
                continue
            isbn = meta.get("isbn", "")
            if isbn and isbn in seen_isbns:
                continue
            if isbn:
                seen_isbns.add(isbn)

            release_date = f"{y:04d}-{m:02d}-01"
            cand = _meta_to_candidate(meta, signals, ptype, release_date, source)
            if min_score and cand.score < min_score:
                continue
            kept.append(cand)
            time.sleep(sleep_seconds)

        if kept:
            print(f"[{idx}/{len(pairs)}] VIZ {y}-{m:02d}: {len(paths)} especiales, {len(kept)} kept")
            all_candidates.extend(kept)
            if flush_fn:
                flush_fn(kept)
        if sleep_seconds > 0 and idx < len(pairs):
            time.sleep(sleep_seconds)

    print(f"[viz] total: {len(all_candidates)} candidates")
    return all_candidates


if __name__ == "__main__":
    import argparse
    import datetime

    p = argparse.ArgumentParser(description="VIZ Media special-editions parser")
    p.add_argument("--wiki-from", default="", help="Mes inicial YYYY-MM. Vacío = mes actual.")
    p.add_argument("--wiki-to", default="", help="Mes final YYYY-MM. Vacío = mismo que --wiki-from.")
    p.add_argument("--sleep-seconds", type=float, default=1.0)
    p.add_argument("--min-score", type=int, default=0)
    args = p.parse_args()

    today = datetime.date.today()
    if args.wiki_from:
        yf, mf = (int(x) for x in args.wiki_from.split("-")[:2])
    else:
        yf, mf = today.year, today.month
    if args.wiki_to:
        yt, mt = (int(x) for x in args.wiki_to.split("-")[:2])
    else:
        yt, mt = today.year, today.month

    s = requests.Session()
    s.headers["User-Agent"] = UA
    cands = bootstrap(yf, mf, yt, mt, session=s,
                      sleep_seconds=args.sleep_seconds, min_score=args.min_score)
    print(f"\nTotal: {len(cands)} candidates")
    for c in cands[:25]:
        print(f"  [{c.score:3d}] {c.isbn or 'no-isbn':<14} {c.release_date or '?':10} {c.title[:60]}")
