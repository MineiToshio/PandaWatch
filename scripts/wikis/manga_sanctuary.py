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

# La planning page expone el tipo de edición como label "bare" ("Perfect",
# "Ultimate", "Prestige", "limitée", "Collector"…) pero detect_signals()
# sólo matchea bigramas ("perfect edition", "édition limitée"…), así que
# ~100+ ediciones especiales FR quedaban con score 0. Mapeamos el label a
# la frase canónica que SÍ levanta señal y la APPENDEMOS a la descripción
# (sin reemplazar el label original, para no degradar el texto de display).
# "Intégrale" se deja sin mapear a propósito: es omnibus/recopilatorio,
# fuera de scope (gotcha #18). Labels desconocidos quedan verbatim.
_EDITION_LABEL_CANONICAL: dict[str, str] = {
    "perfect": "perfect edition",
    "ultimate": "ultimate edition",
    "prestige": "édition prestige",
    "limitée": "édition limitée",
    "limitee": "édition limitée",
    "unlimited double": "limited edition",
    "deluxe": "deluxe",
    "collector": "collector edition",
}


def canonical_edition_phrase(label: str) -> str:
    """Frase canónica (con señal para detect_signals) para un label de
    edición bare de la planning page. "" si no hay mapeo."""
    return _EDITION_LABEL_CANONICAL.get((label or "").strip().lower(), "")


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
    # El thumbnail por defecto (placeholder "sin imagen") no es portada — dejarlo
    # vacío para que el dashboard muestre el placeholder 📚 (ver gotcha #6).
    if "visuel_defaut" in image_url:
        image_url = ""

    # Description: combinamos publisher + edition + type para que detect_signals
    # tenga contexto sobre si es coleccionista o regular. El label de edición
    # llega "bare" (p.ej. "Prestige") → appendeamos además la frase canónica
    # que detect_signals reconoce (manteniendo el label original para display).
    edition_signal = canonical_edition_phrase(edition_text)
    if edition_signal and edition_signal.lower() == edition_text.strip().lower():
        edition_signal = ""  # el label ya ES la frase canónica; no duplicar
    description_parts = [publisher, edition_text, edition_signal, type_label, title]
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
                # Filtro non-manga (figuras, estatuas, etc. — algunos releases
                # de Manga-Sanctuary planning son productos derivados).
                try:
                    from manga_watch import is_likely_manga  # type: ignore
                except ImportError:
                    is_likely_manga = None  # noqa: N816
                if is_likely_manga is not None:
                    keep, _reason = is_likely_manga(
                        cand.title, cand.description, tags=cand.tags
                    )
                    if not keep:
                        continue
                candidates.append(cand)

    return candidates


def _title_matches_page(expected_title: str, page_title: str, body_text: str) -> bool:
    """Verifica que la página de detalle realmente corresponda al item esperado.

    Manga-Sanctuary a veces devuelve una página default (de otro manga) para
    URLs de releases futuros. Tomamos las 2-3 palabras significativas del
    título y verificamos que al menos UNA aparezca en <title> o body.
    """
    if not expected_title:
        return True  # sin verificación, asumimos OK
    # Normalizamos para comparar (lowercase, sin acentos básicos)
    def norm(s: str) -> str:
        return clean_text(s).lower()
    exp = norm(expected_title)
    # Palabras significativas (>=4 chars, no numéricas)
    words = [w for w in re.split(r"\W+", exp) if len(w) >= 4 and not w.isdigit()]
    if not words:
        return True  # título muy genérico, no validar
    page_norm = norm(page_title) + " " + norm(body_text[:2000])
    matches = sum(1 for w in words[:5] if w in page_norm)
    # Si al menos una palabra significativa aparece, consideramos válido.
    return matches >= 1


def fetch_detail_metadata(
    url: str,
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
    expected_title: str = "",
) -> dict[str, Any]:
    """Fetch a página de producto y extrae autor (con validación de matching).

    También captura la galería multi-imagen (covers secundarias, box-set
    composition shots) cuando la ficha la expone.
    """
    result: dict[str, Any] = {"author": "", "images": []}
    if not url:
        return result
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        if not response.encoding:
            response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, "html.parser")
    except (requests.RequestException, Exception):
        return result

    # Validar que la página corresponde al item esperado.
    page_title = ""
    if soup.title:
        page_title = clean_text(soup.title.get_text())
    body_text = clean_text(soup.get_text(" ", strip=True))
    if not _title_matches_page(expected_title, page_title, body_text):
        return result  # URL devolvió la página de otro manga; abortar.

    # Galería multi-imagen del detail (cuando hay más de la cover principal).
    try:
        gallery = _extract_images_from_detail_soup(soup, url)
    except Exception:
        gallery = []
    if len(gallery) > 1:
        result["images"] = gallery

    # 1) Buscar links a /bdd/personnalites/ (páginas de autor)
    persons: list[str] = []
    for a in soup.find_all("a", href=re.compile(r"/bdd/personnalites/")):
        name = clean_text(a.get_text(" ", strip=True))
        if name and name not in persons and 2 < len(name) < 80:
            persons.append(name)
        if len(persons) >= 3:
            break
    if persons:
        result["author"] = " / ".join(persons[:2])
        return result

    # 2) Fallback: regex sobre el body buscando labels.
    for label in ("Scénariste", "Dessinateur", "Auteur"):
        m = re.search(rf"{label}\s+([^\n]{{2,80}}?)(?=\s+(?:Sc[ée]nariste|Dessinateur|Auteur|Editeur|Pages|Date|EAN|$))", body_text)
        if m:
            name = clean_text(m.group(1))
            if name and 2 < len(name) < 80:
                result["author"] = name
                break
    return result


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
    fetch_details: bool = False,
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Recorre meses [from, to] y devuelve candidates con score >= min_score.

    Si fetch_details=True, hace un HTTP extra por item a la página de detalle
    para extraer el autor (dessinateur + scénariste).
    """
    all_candidates: list[Candidate] = []
    pairs = iter_year_months(year_from, month_from, year_to, month_to)
    for idx, (y, m) in enumerate(pairs, start=1):
        print(f"[{idx}/{len(pairs)}] Manga-Sanctuary {y}-{m:02d}")
        cands = fetch_planning_month(y, m, session, timeout=timeout)
        kept = [c for c in cands if c.score >= min_score]
        print(f"    {len(cands)} items totales, {len(kept)} con score >= {min_score}")
        all_candidates.extend(kept)
        if flush_fn and kept:
            flush_fn(kept)
        if sleep_seconds > 0 and idx < len(pairs):
            time_module.sleep(sleep_seconds)

    if fetch_details and all_candidates:
        print(f"\n[DETAIL-FETCH] enriqueciendo {len(all_candidates)} items con autor")
        enriched = 0
        for i, c in enumerate(all_candidates, start=1):
            md = fetch_detail_metadata(c.url, session, timeout=timeout, expected_title=c.title)
            if md["author"] and not c.author:
                c.author = md["author"]
                enriched += 1
            md_images = md.get("images") or []
            if len(md_images) > 1 and not c.images:
                c.images = md_images
            if i % 100 == 0:
                print(f"  [{i}/{len(all_candidates)}] +autores={enriched}")
            if sleep_seconds > 0 and i < len(all_candidates):
                time_module.sleep(min(sleep_seconds, 0.3))
        print(f"[DETAIL-FETCH] {enriched} autores enriquecidos")
        # Re-score por si el autor agregó nueva señal (unlikely but safe).
        for c in all_candidates:
            score_candidate(c)
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
