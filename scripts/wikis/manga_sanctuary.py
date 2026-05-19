"""Parser de manga-sanctuary.com — calendario histórico de manga en Francia.

Estructura del HTML (planning/?&deb=<unix_timestamp>):

    <h3>mercredi 6 mai 2026</h3>          ← fecha del bloque
    <div class="post sortie sorties-liste" fiche_id=... objet_id=...>
      <div class="post-thumbnail">
        <a href="/manga-404-demons-vol-6-...html">
          <img src="https://img.sanctuary.fr/objet/300/441375.jpg">
        </a>
      </div>
      <div class="post-block">
        <div class="post-title-container">
          <h2 class="post-title"><a href="...">404 Démons 6</a></h2>
          <span class="sortie-edition">
            <a class="sortie-editeur" href="/editeur/44/">doki-doki</a> / simple
          </span>
        </div>
        <div class="post-meta"><span class="badge_sm">Manga</span></div>
        <div class="affiliation" ean="9791041114405">... 7,95€ ...</div>
      </div>
    </div>
    ...

URL pattern: /planning/?&deb=<unix_timestamp_inicio_mes>
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
import sys
import time as time_module
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

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


BASE_URL = "https://www.manga-sanctuary.com/"
PLANNING_URL = "https://www.manga-sanctuary.com/planning/"

FRENCH_MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}

DATE_HEADER_PATTERN = re.compile(
    r"\b(\d{1,2})\s+(\w+)\s+(\d{4})\b",
    re.IGNORECASE | re.UNICODE,
)


def _virtual_source() -> Source:
    return Source(
        name="Manga-Sanctuary (planning)",
        url=BASE_URL,
        country="Francia",
        language="Francés",
        publisher="",
        source_class="trusted_media",
        kind="html",
        enabled=True,
        tags=["wiki", "manga-sanctuary", "manga", "france"],
    )


def month_to_deb_param(year: int, month: int) -> int:
    """Devuelve el timestamp Unix del primer día del mes (00:00 UTC) que usa el deb param."""
    # Manga-Sanctuary usa el timestamp del 1er día del mes UTC, según observación.
    return int(dt.datetime(year, month, 1, tzinfo=dt.timezone.utc).timestamp())


def _parse_date_header(text: str) -> str:
    """Convierte 'mercredi 6 mai 2026' → '2026-05-06'. "" si no parsea."""
    match = DATE_HEADER_PATTERN.search(text)
    if not match:
        return ""
    day, month_name, year = match.groups()
    month_num = FRENCH_MONTHS.get(month_name.lower())
    if not month_num:
        return ""
    try:
        return f"{int(year):04d}-{month_num:02d}-{int(day):02d}"
    except ValueError:
        return ""


def _parse_post(post: Any, current_date: str, source: Source) -> Candidate | None:
    """Extrae un Candidate de un <div class='post sortie ...'>."""
    title_el = post.select_one(".post-title a")
    if title_el is None:
        return None
    title = clean_text(title_el.get_text(" ", strip=True))
    if not title or len(title) < 3:
        return None

    href = title_el.get("href", "")
    url = urljoin(BASE_URL, href)

    # Publisher.
    publisher_el = post.select_one(".sortie-editeur")
    publisher = clean_text(publisher_el.get_text(" ", strip=True)) if publisher_el else ""

    # Edition type: lo que sigue al " / " en .sortie-edition
    edition_text = ""
    edition_el = post.select_one(".sortie-edition")
    if edition_el:
        full = clean_text(edition_el.get_text(" ", strip=True))
        # Formato: "<editor> / <edition_type>"
        if "/" in full and publisher:
            parts = full.split("/", 1)
            if len(parts) == 2:
                edition_text = parts[1].strip()

    # Type / categoría (Manga, Light novel, Magazine…)
    type_el = post.select_one(".badge_sm")
    type_label = clean_text(type_el.get_text(" ", strip=True)) if type_el else ""

    # EAN (ISBN-13 en europa para libros)
    affiliation = post.select_one(".affiliation")
    isbn = ""
    if affiliation and affiliation.get("ean"):
        ean = re.sub(r"\D", "", affiliation["ean"])
        if len(ean) == 13:
            isbn = ean

    # Precio: regex en el post entero.
    price = ""
    price_match = re.search(r"(\d{1,3}[,.]\d{2})\s*€", post.get_text(" ", strip=True))
    if price_match:
        price = f"€ {price_match.group(1)}"

    # Imagen.
    img = post.select_one(".post-thumbnail img")
    image_url = ""
    if img:
        for attr in ("src", "data-src", "data-original"):
            v = img.get(attr)
            if v and v.strip():
                image_url = urljoin(BASE_URL, v.strip())
                break

    # Description: combinamos publisher + edition + type para que detect_signals
    # tenga contexto sobre si es coleccionista o regular.
    description_parts = [publisher, edition_text, type_label, title]
    description = clean_text(" · ".join(p for p in description_parts if p))

    cand = candidate_from_source(
        source,
        title=title[:260],
        url=url,
        description=description,
        published_at=current_date,
    )
    cand.publisher = publisher
    cand.release_date = current_date
    cand.price = price
    cand.image_url = image_url
    cand.isbn = isbn
    if type_label:
        cand.tags = list(source.tags or []) + [f"type:{type_label.lower()}"]
    if edition_text:
        cand.tags.append(f"edition:{edition_text.lower()}")
    return cand


def parse_planning_page(html_text: str) -> list[Candidate]:
    """Parsea una página de planning y devuelve candidates."""
    soup = BeautifulSoup(html_text, "html.parser")
    source = _virtual_source()
    candidates: list[Candidate] = []
    current_date = ""

    # Iterar los nodos en orden de aparición.
    # Manga-Sanctuary pone las fechas en <div class="sortie-date subtitle"> y
    # los productos en <div class="post sortie sorties-liste">.
    for el in soup.find_all("div"):
        cls = el.get("class") or []
        # ¿Encabezado de fecha?
        if "sortie-date" in cls:
            text = clean_text(el.get_text(" ", strip=True))
            iso = _parse_date_header(text)
            if iso:
                current_date = iso
            continue
        # ¿Post de producto?
        if "sortie" in cls and "post" in cls:
            cand = _parse_post(el, current_date, source)
            if cand:
                candidates.append(cand)

    return candidates


def fetch_planning_month(
    year: int, month: int, session: requests.Session, timeout: tuple[int, int] = (10, 30)
) -> list[Candidate]:
    """Descarga + parsea un mes del planning. Devuelve candidates scored."""
    deb = month_to_deb_param(year, month)
    url = f"{PLANNING_URL}?&deb={deb}"
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        if not response.encoding:
            response.encoding = response.apparent_encoding
        text = response.text
    except requests.RequestException:
        return []
    raw = parse_planning_page(text)
    return [score_candidate(c) for c in raw]


def iter_year_months(
    year_from: int, month_from: int, year_to: int, month_to: int
) -> list[tuple[int, int]]:
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
    timeout: tuple[int, int] = (10, 30),
    min_score: int = 30,
    fetch_details: bool = False,  # no-op por ahora; planning ya tiene cover/price/ean
) -> list[Candidate]:
    """Recorre meses entre [from, to] inclusivo y devuelve candidates con score >= min_score."""
    all_candidates: list[Candidate] = []
    pairs = iter_year_months(year_from, month_from, year_to, month_to)
    for idx, (y, m) in enumerate(pairs, start=1):
        print(f"[{idx}/{len(pairs)}] Manga-Sanctuary {y}-{m:02d}")
        cands = fetch_planning_month(y, m, session, timeout=timeout)
        kept = [c for c in cands if c.score >= min_score]
        print(f"    {len(cands)} items totales, {len(kept)} con score >= {min_score}")
        all_candidates.extend(kept)
        if sleep_seconds > 0 and idx < len(pairs):
            time_module.sleep(sleep_seconds)
    return all_candidates


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="frm", default="2026-05")
    parser.add_argument("--to", default="2026-05")
    parser.add_argument("--sleep-seconds", type=float, default=0.5)
    args = parser.parse_args()

    yf, mf = map(int, args.frm.split("-"))
    yt, mt = map(int, args.to.split("-"))
    s = requests.Session()
    s.headers["User-Agent"] = "manga-watch/0.2 (+manga-sanctuary-bootstrap)"
    items = bootstrap(yf, mf, yt, mt, session=s, sleep_seconds=args.sleep_seconds)
    print(f"\nTotal con señales: {len(items)}")
    for it in items[:5]:
        print(f"  [{it.score:3d}] {it.publisher[:20]:20s} · {it.title[:70]}")
        print(f"        ean={it.isbn or '—':14s} price={it.price or '—':10s}  ({it.release_date})")
