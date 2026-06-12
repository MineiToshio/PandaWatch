"""Parser de animeclick.it — edizioni speciali italiane.

AnimeClick.it è un sito comunitario italiano di manga/anime con un
**calendario settimanale** di uscite in fumetteria. Copre tutti i publisher
italiani: Star Comics, Panini Comics, J-POP, MangaYo!, Crunchyroll IT,
Jundo, Dokusho, Edizioni BD, ecc. Complementa SocialAnime (che ha ISBN al
95% ma copre solo ~7 publisher minori) con copertura più ampia ma senza ISBN.

Endpoint AJAX settimanale
-------------------------
Navigazione settimana per settimana tramite::

    GET /calendario-manga
        ?paging=prev-week          # o next-week
        &month=MM&year=YYYY&day=DD # data della settimana corrente
        &tipo[]=&inLista=false&nazioni[]=
    Headers: X-Requested-With: XMLHttpRequest
             Accept: application/json, */*

Risposta::

    {"ok": true, "data": {"html": "<div...>", "month": "05", "year": "2026", "day": "18"}}

State iniziale letto da ``div#calendario-pagination-div`` (attributi
``data-current-day`` / ``data-current-month`` / ``data-current-year``).

Struttura HTML delle card
-------------------------
::

    <div class="panel-evento-calendario edizione">
      <a href="/edizione/3110494/100-metres-variant-mangayo">
        <img class="img-evento" data-original="https://..." src="/placeholder.jpg">
      </a>
      <a href="/edizione/3110494/...">
        <h3>100 Metres - Hyakuemu Variant MangaYo! 1</h3>   ← titolo con qualifier
      </a>
      <h4 class="edizione">MangaYo!</h4>                     ← publisher
      <h5>100 Metres</h5>                                    ← serie
    </div>

Pagina di dettaglio — schema.org ``Book``
-----------------------------------------
::

    <h1 itemprop="name">Titolo edizione</h1>
    <img itemprop="image" src="/immagini/manga/.../edizione-ID.jpg">
    <p itemprop="description">Trama...</p>
    <meta itemprop="datePublished" content="2025-05-14">
    <strong>Editore:</strong> Star Comics
    <strong>Prezzo:</strong> 15,00 €

Nessun ISBN disponibile sul sito.

API pubblica (stessa firma degli altri wiki parsers)::

    parse_calendar_html(html)      -> list[dict]
    parse_detail_page(html, url)   -> dict
    is_collector_edition(title)    -> bool
    bootstrap(yf, mf, yt, mt, ...) -> list[Candidate]
    iter_year_months(yf, mf, yt, mt) -> [(yf, mf)]   (batch unico)
"""

from __future__ import annotations

import datetime as dt
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
    from scripts.manga_watch import (  # type: ignore[import-not-found]
        Candidate,
        Source,
        _extract_images_from_detail_soup,
        candidate_from_source,
        clean_text,
        score_candidate,
    )
except ImportError:
    from manga_watch import (  # type: ignore[no-redef]
        Candidate,
        Source,
        _extract_images_from_detail_soup,
        candidate_from_source,
        clean_text,
        score_candidate,
    )


BASE_URL = "https://www.animeclick.it"
CALENDAR_URL = f"{BASE_URL}/calendario-manga"

# Navega massimo ~10 anni di settimanale (safety cap)
MAX_WEEKS = 520

# Termini che identificano edizioni collector-grade nel titolo
_COLLECTOR_RE = re.compile(
    r"\b(variant|limitata|limited|special|deluxe|ultimate|extreme|"
    r"cofanetto|collector|esclusiva|exclusive|premium|artbook|kanzenban|"
    r"completa|integrale|box\s+set)\b",
    re.IGNORECASE,
)

# ID edizione dall'URL path /edizione/12345/slug
_EDITION_ID_RE = re.compile(r"/edizione/(\d+)/")


def _virtual_source() -> Source:
    return Source(
        name="IT - AnimeClick (edizioni speciali)",
        url=BASE_URL,
        country="Italia",
        language="Italiano",
        publisher="",
        source_class="trusted_media",
        kind="wiki",
        enabled=True,
        tags=["wiki", "animeclick", "italia"],
        notes="animeclick.it — calendario settimanale IT: variant/limited/cofanetto.",
        selectors={},
        max_pages=0,
        purity="manga_only",   # solo edizioni collector emesse (keyword filter)
    )


def is_collector_edition(title: str) -> bool:
    """True se il titolo contiene un qualifier da edizione speciale."""
    return bool(_COLLECTOR_RE.search(title))


def _inject_collector_hints(title: str, description: str) -> str:
    """Inietta hints nella descrizione perché detect_signals li rilevi."""
    hints: list[str] = []
    title_lc = title.lower()
    if "cofanetto" in title_lc:
        hints.append("Cofanetto Box Set")
    if "integrale" in title_lc or "completa" in title_lc:
        hints.append("Complete edition integral")
    if hints:
        sep = " — " if description else ""
        return " ".join(hints) + sep + description
    return description


def parse_calendar_html(html: str) -> list[dict]:
    """Estrae le card edizione da un frammento HTML del calendario.

    Restituisce una lista di dict con chiavi ``title``, ``url``,
    ``publisher`` e ``image_url``.
    """
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for card in soup.find_all("div", class_="panel-evento-calendario"):
        # Cerca il link all'edizione
        link_tag = None
        for a in card.find_all("a"):
            href = a.get("href", "")
            if "/edizione/" in href:
                link_tag = a
                break
        if not link_tag:
            continue
        href = link_tag["href"]
        full_url = href if href.startswith("http") else f"{BASE_URL}{href}"

        h3 = card.find("h3")
        title = clean_text(h3.get_text(strip=True)) if h3 else ""
        if not title:
            continue

        h4 = card.find("h4", class_="edizione")
        publisher = clean_text(h4.get_text(strip=True)) if h4 else ""

        img_tag = card.find("img", class_="img-evento")
        image_url = ""
        if img_tag:
            raw = img_tag.get("data-original") or img_tag.get("src") or ""
            if raw and not raw.startswith("http"):
                raw = urljoin(BASE_URL, raw)
            # Scarta placeholder interni (URL senza estensione immagine reale)
            if raw and any(ext in raw for ext in (".jpg", ".jpeg", ".png", ".webp")):
                image_url = raw

        items.append({
            "title": title,
            "url": full_url,
            "publisher": publisher,
            "image_url": image_url,
        })
    return items


def parse_detail_page(html: str, detail_url: str) -> dict:
    """Estrae i campi dalla pagina di dettaglio di un'edizione.

    Restituisce un dict con ``title``, ``image_url``, ``description``,
    ``release_date``, ``publisher``.
    """
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, str] = {}

    # Titolo (itemprop="name" sull'h1)
    h1 = soup.find("h1", itemprop="name")
    if h1:
        result["title"] = clean_text(h1.get_text(strip=True))

    # Copertina (itemprop="image")
    img = soup.find("img", itemprop="image")
    if img:
        src = img.get("src") or ""
        if src and not src.startswith("http"):
            src = urljoin(BASE_URL, src)
        if src:
            result["image_url"] = src

    # Descrizione (itemprop="description")
    desc_p = soup.find("p", itemprop="description")
    if desc_p:
        result["description"] = clean_text(desc_p.get_text(strip=True))

    # Data di uscita (meta itemprop="datePublished")
    date_meta = soup.find("meta", itemprop="datePublished")
    if date_meta and date_meta.get("content"):
        result["release_date"] = date_meta["content"].strip()

    # Editore e Prezzo: cerca <strong> con "Editore:" / "Prezzo:"
    for strong in soup.find_all("strong"):
        text = strong.get_text(strip=True)
        if "Editore" in text and "publisher" not in result:
            parent_text = strong.parent.get_text(separator=" ")
            after = parent_text.split("Editore", 1)[-1]
            # Strip leading colon/spaces
            after = re.sub(r"^[\s\:]+", "", after)
            # The next label is the word immediately before the next colon.
            # E.g. "Editoriale Cosmo Nazionalità: Italia" → remove " Nazionalità"
            colon_pos = after.find(":")
            if colon_pos > 0:
                before_colon = after[:colon_pos]
                last_word = re.search(r"\s+\S+$", before_colon)
                after = before_colon[: last_word.start()].strip() if last_word else before_colon.strip()
            publisher = after.strip()
            if publisher:
                result["publisher"] = publisher
    # Galería multi-imagen del detail (cuando hay más de la cover principal).
    try:
        gallery = _extract_images_from_detail_soup(soup, detail_url)
    except Exception:
        gallery = []
    if len(gallery) > 1:
        result["images"] = gallery

    return result


def _get_calendar_state(html: str) -> tuple[int, int, int]:
    """Legge day/month/year correnti dal div#calendario-pagination-div."""
    soup = BeautifulSoup(html, "html.parser")
    div = soup.find("div", id="calendario-pagination-div")
    if div:
        try:
            day = int(div.get("data-current-day", 1))
            month = int(div.get("data-current-month", 1))
            year = int(div.get("data-current-year", 2024))
            return day, month, year
        except (ValueError, TypeError):
            pass
    today = dt.date.today()
    return today.day, today.month, today.year


def fetch_html(
    session: requests.Session,
    url: str,
    timeout: tuple[int, int] = (10, 30),
) -> str | None:
    """Scarica l'HTML di una URL; restituisce None in caso di errore."""
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        print(f"[animeclick] WARN fetch {url}: {exc}")
        return None


def fetch_week_ajax(
    session: requests.Session,
    day: int,
    month: int,
    year: int,
    direction: str = "prev-week",
    timeout: tuple[int, int] = (10, 30),
) -> tuple[str | None, int, int, int]:
    """Chiama l'endpoint AJAX per navigare di una settimana.

    Restituisce ``(html_fragment, new_day, new_month, new_year)``.
    ``html_fragment`` è None in caso di errore.
    """
    params = {
        "paging": direction,
        "month": f"{month:02d}",
        "year": str(year),
        "day": f"{day:02d}",
        "tipo[]": "",
        "inLista": "false",
        "nazioni[]": "",
    }
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, */*",
    }
    try:
        resp = session.get(
            CALENDAR_URL, params=params, headers=headers, timeout=timeout
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        print(
            f"[animeclick] WARN AJAX {direction} {year}-{month:02d}-{day:02d}: {exc}"
        )
        return None, day, month, year

    if not data.get("ok"):
        return None, day, month, year

    info = data.get("data") or {}
    html = info.get("html") or ""
    try:
        new_day = int(info.get("day", day))
        new_month = int(info.get("month", month))
        new_year = int(info.get("year", year))
    except (ValueError, TypeError):
        new_day, new_month, new_year = day, month, year

    return html, new_day, new_month, new_year


_FLUSH_EVERY = 25  # escribe cada N candidates durante el detail-fetch loop


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
    """Navega il calendario settimanale e raccoglie edizioni speciali.

    ``year_from``/``month_from`` definiscono il cutoff: si naviga indietro
    finché il calendario mostra settimane precedenti a quella data.
    """
    cutoff = dt.date(year_from, month_from, 1)

    # Sessione iniziale: cookie + stato corrente
    print(f"[animeclick] inizializzazione sessione (cutoff: {cutoff})")
    initial_html = fetch_html(session, CALENDAR_URL, timeout=timeout)
    if not initial_html:
        print("[animeclick] ERRORE: impossibile caricare la pagina iniziale")
        return []

    cur_day, cur_month, cur_year = _get_calendar_state(initial_html)
    print(f"[animeclick] stato iniziale: {cur_year}-{cur_month:02d}-{cur_day:02d}")

    # Includi la settimana corrente dalla pagina iniziale
    soup0 = BeautifulSoup(initial_html, "html.parser")
    container = soup0.find("div", id="calendario-days-thumbs")
    weeks_html: list[str] = [str(container) if container else ""]

    # Naviga indietro settimana per settimana
    for _ in range(MAX_WEEKS):
        html_frag, new_day, new_month, new_year = fetch_week_ajax(
            session, cur_day, cur_month, cur_year,
            direction="prev-week",
            timeout=timeout,
        )

        try:
            new_date = dt.date(new_year, new_month, new_day)
        except ValueError:
            new_date = dt.date(new_year, new_month, 1)

        if new_date < cutoff:
            print(f"[animeclick] raggiunto il cutoff ({new_date} < {cutoff}), stop")
            break

        if html_frag:
            weeks_html.append(html_frag)

        cur_day, cur_month, cur_year = new_day, new_month, new_year

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    print(f"[animeclick] {len(weeks_html)} settimane recuperate")

    # Estrai card da tutte le settimane, applicando il keyword filter
    seen_ids: set[str] = set()
    candidate_queue: list[dict] = []

    for week_html in weeks_html:
        if not week_html:
            continue
        for card in parse_calendar_html(week_html):
            m = _EDITION_ID_RE.search(card["url"])
            edition_id = m.group(1) if m else None
            if not edition_id or edition_id in seen_ids:
                continue
            if not is_collector_edition(card["title"]):
                continue
            seen_ids.add(edition_id)
            candidate_queue.append(card)

    print(f"[animeclick] {len(candidate_queue)} edizioni speciali da processare")

    # Fetch dettagli + costruzione candidati
    candidates: list[Candidate] = []

    for i, card in enumerate(candidate_queue):
        detail: dict = {}
        if fetch_details:
            if sleep_seconds > 0 and i > 0:
                time.sleep(sleep_seconds)
            detail_html = fetch_html(session, card["url"], timeout=timeout)
            if detail_html:
                detail = parse_detail_page(detail_html, card["url"])

        title = detail.get("title") or card["title"]
        publisher = detail.get("publisher") or card["publisher"]
        image_url = detail.get("image_url") or card.get("image_url") or ""
        description = detail.get("description") or ""
        release_date = detail.get("release_date") or ""

        description = _inject_collector_hints(title, description)

        src = _virtual_source()
        if publisher:
            src.publisher = publisher

        cand = candidate_from_source(
            src,
            title=title,
            url=card["url"],
            description=description,
            published_at=release_date,
        )
        cand.image_url = image_url
        cand.release_date = release_date
        detail_images = detail.get("images") or []
        if len(detail_images) > 1:
            cand.images = detail_images

        score_candidate(cand)

        if min_score and cand.score < min_score:
            continue
        candidates.append(cand)

        if flush_fn and len(candidates) % _FLUSH_EVERY == 0:
            flush_fn(candidates[-_FLUSH_EVERY:])

    print(f"[animeclick] {len(candidates)} candidates totali")
    return candidates


def iter_year_months(
    year_from: int, month_from: int,
    year_to: int, month_to: int,    # noqa: ARG001
) -> list[tuple[int, int]]:
    """La navigazione è settimanale; restituisce un batch unico."""
    return [(year_from, month_from)]


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Ingesta animeclick.it")
    ap.add_argument(
        "--wiki-from", default="",
        help="Cutoff data: YYYY-MM (es. 2026-01). Vuoto = ultimi 3 mesi.",
    )
    ap.add_argument("--sleep", type=float, default=0.5)
    ap.add_argument(
        "--no-details", action="store_true",
        help="Salta il fetch della pagina di dettaglio.",
    )
    args = ap.parse_args()

    if args.wiki_from:
        parts = args.wiki_from.split("-")
        yf, mf = int(parts[0]), int(parts[1])
    else:
        d = dt.date.today() - dt.timedelta(days=90)
        yf, mf = d.year, d.month

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; manga-watch-personal/0.2)",
        "Accept-Language": "it-IT,it;q=0.9",
    })

    cands = bootstrap(
        yf, mf, dt.date.today().year + 1, 12,
        session=s,
        sleep_seconds=args.sleep,
        fetch_details=not args.no_details,
        min_score=0,
    )
    print(f"\nTotale: {len(cands)} candidates")
    for c in cands[:20]:
        print(f"  [{c.score:3d}] {c.publisher:<25} {c.title[:70]}")
