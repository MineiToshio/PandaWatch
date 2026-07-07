"""Parser de otakucalendar.com — calendario de releases de manga (EN/US).

Estructura del HTML (Calendar/YYYY/M):

    <div class="dateListing">
      <h3>May 2026</h3>
      <div class="dateListingContainer">
        Tuesday 5 May 2026
        <div>
          <a href="/Release/22805/a-tale-of-the-secret-saint-...">
            A Tale of the Secret Saint (Manga) Volume 11 (Manga) US
          </a><br/>
          <a href="/Release/22809/betrothed-to-my-sisters-ex-...">
            Betrothed to My Sister’s Ex (Light Novel) Volume 2 (Manga) US
          </a><br/>
          ...
        </div>
      </div>
      <div class="dateListingContainer">
        Wednesday 6 May 2026
        ...
      </div>
    </div>

Cada release link es de la forma /Release/<id>/<slug> y el texto incluye
"(Manga)" o "(Light Novel)" + país ("US", "AU", etc.). Filtramos por país
US (mercado inglés principal) por defecto.

API pública (paralela a listadomanga.py):
    parse_calendar_page(html_text, source_url) -> list[Candidate]
    fetch_calendar_month(year, month, session, timeout) -> list[Candidate]
    iter_year_months(yf, mf, yt, mt) -> list[(year, month)]
    bootstrap(yf, mf, yt, mt, session, ...) -> list[Candidate]
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path
from typing import Any, Callable
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
        is_likely_manga,
        score_candidate,
    )
except ImportError:
    from manga_watch import (  # type: ignore[no-redef]
        Candidate,
        Source,
        candidate_from_source,
        clean_text,
        is_likely_manga,
        score_candidate,
    )


BASE_URL = "https://otakucalendar.com"
DEFAULT_COUNTRIES = ("US",)  # mercado inglés principal


def _virtual_source() -> Source:
    """Source sintética para que candidate_from_source no necesite una real."""
    return Source(
        name="EN - Otaku Calendar",
        url=BASE_URL,
        country="Estados Unidos",
        language="Inglés",
        publisher="",
        source_class="trusted_media",
        kind="wiki",
        enabled=True,
        tags=["wiki", "otakucalendar", "english", "calendar"],
        notes="otakucalendar.com community release calendar",
        selectors={},
        max_pages=0,
    )


# Date header text: "Tuesday 5 May 2026" or similar.
_DATE_RE = re.compile(
    r"(?P<wd>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+"
    r"(?P<year>\d{4})",
    re.IGNORECASE,
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# Country suffix on release titles: "(Manga) US", "(Light Novel) AU".
# Captura format + country en grupos separados.
_COUNTRY_SUFFIX_RE = re.compile(
    r"\s*\((Manga|Light Novel)\)\s+([A-Z]{2})\s*$", re.IGNORECASE
)
# Format hint embedded earlier in title: "(Manga)" or "(Light Novel)".
_FORMAT_HINT_RE = re.compile(r"\((Manga|Light Novel)\)", re.IGNORECASE)


def _parse_date_text(text: str) -> str:
    """Devuelve fecha ISO (YYYY-MM-DD) o ""."""
    m = _DATE_RE.search(text)
    if not m:
        return ""
    month = _MONTHS.get(m.group("month").lower())
    if not month:
        return ""
    try:
        return f"{int(m.group('year')):04d}-{month:02d}-{int(m.group('day')):02d}"
    except ValueError:
        return ""


def _strip_format_and_country(title: str) -> tuple[str, str, str]:
    """Devuelve (clean_title, format_label, country_code)."""
    raw = title
    country = ""
    fmt = ""
    m = _COUNTRY_SUFFIX_RE.search(raw)
    if m:
        fmt = m.group(1).lower().replace(" ", "_")
        country = m.group(2).upper()
        raw = raw[: m.start()].strip()
    # Si todavía hay "(Manga)" / "(Light Novel)" interno (caso doble), lo quitamos.
    m2 = _FORMAT_HINT_RE.search(raw)
    if m2:
        if not fmt:
            fmt = m2.group(1).lower().replace(" ", "_")
        raw = (raw[: m2.start()] + raw[m2.end():]).replace("  ", " ").strip()
    return raw.strip(), fmt, country


def parse_calendar_page(
    html_text: str,
    source_url: str = BASE_URL,
    allowed_countries: tuple[str, ...] = DEFAULT_COUNTRIES,
) -> list[Candidate]:
    """Parsea una página de calendario mensual de otakucalendar."""
    if not html_text:
        return []
    soup = BeautifulSoup(html_text, "html.parser")
    source = _virtual_source()
    candidates: list[Candidate] = []

    # Itera contenedores por día. Cada div.dateListingContainer empieza con
    # texto fecha y contiene <a> por cada release.
    for container in soup.find_all("div", class_="dateListingContainer"):
        text = container.get_text(" ", strip=True)
        iso_date = _parse_date_text(text)

        for a in container.find_all("a", href=True):
            href = a.get("href", "")
            if "/Release/" not in href:
                continue
            raw_title = clean_text(a.get_text(" ", strip=True))
            if not raw_title:
                continue
            cleaned, fmt, country = _strip_format_and_country(raw_title)
            if not cleaned:
                continue
            # Filtro por país si está configurado
            if allowed_countries and country and country not in allowed_countries:
                continue
            url = urljoin(source_url, href)
            # Description corta para que el scorer tenga algo
            description = (
                f"{cleaned} ({fmt})" if fmt else cleaned
            )
            cand = candidate_from_source(
                source, title=cleaned, url=url, description=description,
                published_at=iso_date or "",
            )
            cand.release_date = iso_date
            cand.tags = list(source.tags) + (
                [f"format:{fmt}"] if fmt else []
            ) + ([f"country:{country.lower()}"] if country else [])
            # Filtro non-manga (rescata art books, etc. via is_likely_manga).
            keep, _ = is_likely_manga(cand.title, cand.description, tags=cand.tags)
            if not keep:
                continue
            score_candidate(cand)
            candidates.append(cand)

    return candidates


def fetch_calendar_month(
    year: int,
    month: int,
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
    allowed_countries: tuple[str, ...] = DEFAULT_COUNTRIES,
) -> list[Candidate]:
    """Descarga el calendario de un mes y devuelve candidates parseados.

    El mes va como PATH-SEGMENT (`/Calendar/YYYY/M`), NO como query string
    (`?month=YYYY-M`). El servidor IGNORA el query string y sirve siempre el
    mes por defecto, así que `?month=` daba el mismo HTML para cualquier mes
    (bootstrapear un rango producía duplicados). La vista por-path devuelve el
    mes solicitado (~375 releases/mes) con la MISMA estructura de HTML
    (`div.dateListingContainer` + `/Release/<id>/<slug>`), así que el parser no
    cambia. Verificado 2026-07-07.
    """
    url = f"{BASE_URL}/Calendar/{year}/{month}"
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        if not response.encoding:
            response.encoding = response.apparent_encoding or "utf-8"
        html_text = response.text
    except (requests.RequestException, Exception):
        return []
    return parse_calendar_page(html_text, source_url=url, allowed_countries=allowed_countries)


def iter_year_months(
    year_from: int, month_from: int, year_to: int, month_to: int
) -> list[tuple[int, int]]:
    """Itera (year, month) entre [from, to] inclusivo."""
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
    fetch_details: bool = False,
    allowed_countries: tuple[str, ...] = DEFAULT_COUNTRIES,
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Recorre meses [from, to] y devuelve candidates con score >= min_score."""
    import time
    all_candidates: list[Candidate] = []
    pairs = iter_year_months(year_from, month_from, year_to, month_to)
    for idx, (y, m) in enumerate(pairs, start=1):
        print(f"[{idx}/{len(pairs)}] OtakuCalendar {y}-{m:02d}")
        cands = fetch_calendar_month(y, m, session, timeout=timeout,
                                     allowed_countries=allowed_countries)
        kept = [c for c in cands if c.score >= min_score]
        print(f"    {len(cands)} items totales, {len(kept)} con score >= {min_score}")
        all_candidates.extend(kept)
        if flush_fn and kept:
            flush_fn(kept)
        if sleep_seconds > 0 and idx < len(pairs):
            time.sleep(sleep_seconds)
    # fetch_details no aplica: otakucalendar no expone cover/precio/ISBN en
    # sus páginas de release; el dato útil ya está en el listing.
    return all_candidates


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="frm", default="2026-04")
    parser.add_argument("--to", default="2026-06")
    parser.add_argument("--country", default="US")
    args = parser.parse_args()

    yf, mf = (int(x) for x in args.frm.split("-"))
    yt, mt = (int(x) for x in args.to.split("-"))

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; manga-watch-debug)"
    cands = bootstrap(
        yf, mf, yt, mt,
        session=s, sleep_seconds=0.2, min_score=10,
        allowed_countries=(args.country.upper(),),
    )
    print(f"\nTotal: {len(cands)} candidates")
    for c in cands[:10]:
        print(f"  [{c.score}] {c.release_date} | {c.title[:60]}")
