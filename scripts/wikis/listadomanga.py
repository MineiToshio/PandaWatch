"""Parser de listadomanga.es — calendario histórico de manga en España.

Estructura del HTML (calendario.php?mes=N&ano=YYYY):

    <h2>Norma Editorial</h2>            ← editorial
    <h2>Sábado, 2 Mayo 2026</h2>        ← fecha
      <table class="ventana_id2">
        <tr><td class="izq">
          <b><u>Shojo</u></b>            ← categoría
          - <a href="coleccion.php?id=3541">Título nº7 (de 9)</a> /
            <a href="autor.php?id=21">Autor</a>
          - <a ...>Otro título...</a>
        </td></tr>
      </table>
    <h2>Lunes, 4 Mayo 2026</h2>
    ...
    <h2>Ediciones Tomodomo</h2>          ← otra editorial
    ...

Por convención los <h2> "Abril 2026" y "Junio 2026" son links a meses
adyacentes — los ignoramos.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Permite importar el módulo principal aunque corramos desde scripts/wikis/
# o desde el root del repo (donde hay un wrapper manga_watch.py).
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# Importamos via scripts.manga_watch para evitar colisión con el wrapper raíz.
try:
    from scripts.manga_watch import (  # type: ignore[import-not-found]
        Candidate,
        Source,
        candidate_from_source,
        clean_text,
        score_candidate,
    )
except ImportError:
    # Si scripts/ ya está en sys.path (caso del CLI corriendo desde root)
    from manga_watch import (  # type: ignore[no-redef]
        Candidate,
        Source,
        candidate_from_source,
        clean_text,
        score_candidate,
    )


BASE_URL = "https://www.listadomanga.es/"
CALENDAR_URL_TEMPLATE = "https://www.listadomanga.es/calendario.php?mes={month}&ano={year}"

WEEKDAYS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
DATE_PATTERN = re.compile(
    r"^(?:" + "|".join(WEEKDAYS) + r"),\s*(\d{1,2})\s+(\w+)\s+(\d{4})$",
    re.IGNORECASE | re.UNICODE,
)
# Meses adyacentes: solo "Mes YYYY" (sin día de semana).
MONTH_HEADER_PATTERN = re.compile(r"^\w+\s+\d{4}$", re.UNICODE)

# Para convertir nombre de mes español → número.
SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def _virtual_source() -> Source:
    """Source 'virtual' que usamos para taggear los items de ListadoManga."""
    return Source(
        name="ListadoManga (calendario)",
        url=BASE_URL,
        country="España",
        language="Español",
        publisher="",  # se llena por item según la editorial detectada
        source_class="trusted_media",
        kind="html",
        enabled=True,
        tags=["wiki", "listadomanga", "manga", "spain"],
    )


def _parse_date_header(text: str) -> str:
    """Convierte 'Sábado, 2 Mayo 2026' → '2026-05-02'. "" si no parsea."""
    match = DATE_PATTERN.match(text.strip())
    if not match:
        return ""
    day, month_name, year = match.groups()
    month_num = SPANISH_MONTHS.get(month_name.lower())
    if not month_num:
        return ""
    try:
        return f"{int(year):04d}-{month_num:02d}-{int(day):02d}"
    except ValueError:
        return ""


def _is_publisher_header(text: str) -> bool:
    """¿Este <h2> es nombre de editorial? (No fecha ni mes adyacente.)"""
    text = text.strip()
    if not text:
        return False
    if DATE_PATTERN.match(text):
        return False
    # "Mayo 2026" o "Calendario de Mayo 2026" son headers de navegación.
    if MONTH_HEADER_PATTERN.match(text):
        return False
    if "calendario" in text.lower():
        return False
    return True


def _extract_items_from_table(
    table: Any,
    publisher: str,
    sale_date: str,
    source: Source,
) -> list[Candidate]:
    """Extrae items de un <table class='ventana_id2'>.

    Estructura: <b><u>Categoría</u></b> + lista de <a href='coleccion.php...'>.
    """
    items: list[Candidate] = []
    if not publisher:
        return items

    # Categoría: el primer <b><u>
    category_el = table.find("u")
    category = clean_text(category_el.get_text(" ", strip=True)) if category_el else ""

    # Cada link a coleccion.php?id=... es un manga; los autor.php son metadata
    raw_text = clean_text(table.get_text(" ", strip=True))
    for anchor in table.find_all("a", href=True):
        href = anchor.get("href", "")
        if "coleccion.php" not in href:
            continue
        title = clean_text(anchor.get_text(" ", strip=True))
        if not title or len(title) < 3:
            continue

        # Author: link a autor.php que sigue al de coleccion
        author = ""
        next_sib = anchor.find_next_sibling()
        # ListadoManga separa con " / " — buscar el siguiente <a> de autor.php
        for tag in anchor.find_all_next("a", limit=3):
            if "autor.php" in (tag.get("href") or ""):
                author = clean_text(tag.get_text(" ", strip=True))
                break
            if "coleccion.php" in (tag.get("href") or ""):
                break  # llegamos al siguiente manga sin pasar por autor

        # Description: usar todo el bloque de tabla (categoría + título + autor)
        # para que detect_signals tenga contexto.
        description = clean_text(f"{publisher} · {category} · {title}")
        if author:
            description += f" · {author}"

        url = urljoin(BASE_URL, href)
        cand = candidate_from_source(
            source,
            title=title[:260],
            url=url,
            description=description,
            published_at=sale_date,
        )
        cand.publisher = publisher
        cand.release_date = sale_date
        cand.author = author
        # Aplicar tags con metadata útil
        cand.tags = list(source.tags or []) + (
            [f"category:{category}"] if category else []
        )
        items.append(cand)

    return items


def parse_calendar_page(html_text: str, source_url: str = BASE_URL) -> list[Candidate]:
    """Parsea una página de calendario (mes-año) y devuelve candidates."""
    soup = BeautifulSoup(html_text, "html.parser")
    source = _virtual_source()

    current_publisher = ""
    current_date = ""
    candidates: list[Candidate] = []

    # Iterar por nodos en orden de aparición.
    for el in soup.find_all(["h2", "table"]):
        if el.name == "h2":
            text = clean_text(el.get_text(" ", strip=True))
            iso_date = _parse_date_header(text)
            if iso_date:
                current_date = iso_date
            elif _is_publisher_header(text):
                current_publisher = text
                current_date = ""  # nueva editorial reinicia fecha
            continue

        # Las tablas de contenido tienen clase ventana_idN (N varía por editorial).
        classes = el.get("class") or []
        if not any(c.startswith("ventana_id") for c in classes):
            continue
        if not current_publisher:
            continue

        items = _extract_items_from_table(el, current_publisher, current_date, source)
        candidates.extend(items)

    return candidates


def fetch_calendar_month(
    year: int, month: int, session: requests.Session, timeout: tuple[int, int] = (10, 30)
) -> list[Candidate]:
    """Descarga + parsea un mes del calendario. Devuelve candidates scored."""
    url = CALENDAR_URL_TEMPLATE.format(month=month, year=year)
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        if not response.encoding:
            response.encoding = response.apparent_encoding
        text = response.text
    except requests.RequestException:
        return []
    raw_candidates = parse_calendar_page(text, source_url=url)
    return [score_candidate(c) for c in raw_candidates]


def iter_year_months(
    year_from: int, month_from: int, year_to: int, month_to: int
) -> list[tuple[int, int]]:
    """Itera mes-año en orden. Inclusivo en ambos extremos."""
    pairs: list[tuple[int, int]] = []
    y, m = year_from, month_from
    while (y, m) <= (year_to, month_to):
        pairs.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
        if y > year_to + 5:  # safety
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
) -> list[Candidate]:
    """Recorre meses entre [from, to] inclusivo y devuelve candidates scored.

    Solo retorna los que tengan score >= min_score (mismo criterio que el scraper).
    """
    import time
    all_candidates: list[Candidate] = []
    pairs = iter_year_months(year_from, month_from, year_to, month_to)
    for idx, (y, m) in enumerate(pairs, start=1):
        print(f"[{idx}/{len(pairs)}] ListadoManga {y}-{m:02d}")
        cands = fetch_calendar_month(y, m, session, timeout=timeout)
        kept = [c for c in cands if c.score >= min_score]
        print(f"    {len(cands)} items totales, {len(kept)} con score >= {min_score}")
        all_candidates.extend(kept)
        if sleep_seconds > 0 and idx < len(pairs):
            time.sleep(sleep_seconds)
    return all_candidates


if __name__ == "__main__":
    # Quick smoke run para debug
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="frm", default="2026-01")
    parser.add_argument("--to", default="2026-05")
    parser.add_argument("--sleep-seconds", type=float, default=0.5)
    args = parser.parse_args()

    yf, mf = map(int, args.frm.split("-"))
    yt, mt = map(int, args.to.split("-"))
    s = requests.Session()
    s.headers["User-Agent"] = "manga-watch/0.2 (+listadomanga-bootstrap)"
    items = bootstrap(yf, mf, yt, mt, session=s, sleep_seconds=args.sleep_seconds)
    print(f"\nTotal con señales: {len(items)}")
    for it in items[:5]:
        print(f"  [{it.score}] {it.publisher} · {it.title}  ({it.release_date})")
