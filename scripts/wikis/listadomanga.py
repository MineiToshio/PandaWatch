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
from typing import Any, Callable
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
        _extract_images_from_detail_soup,
        candidate_from_source,
        clean_text,
        score_candidate,
    )
except ImportError:
    # Si scripts/ ya está en sys.path (caso del CLI corriendo desde root)
    from manga_watch import (  # type: ignore[no-redef]
        Candidate,
        Source,
        _extract_images_from_detail_soup,
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

        # Description: NO inyectar `category` como keyword en description —
        # contamina `detect_signals` cuando el `<u>` del HTML pertenece a otro
        # contexto (autor, sección distinta, item adyacente). Bug real
        # (2026-05-23): "Ataque a los Titanes: Antes de la caída nº11" se
        # marcó como signal=artbook + product_type=artbook porque una `<u>`
        # cercana decía "Artbook" — el item ES un tomo manga regular y no
        # debería haber entrado a items.jsonl como artbook.
        # La categoría sigue siendo útil como contexto/tag, pero no como
        # keyword que detect_signals pueda interpretar como signal premium.
        description = clean_text(f"{publisher} · {title}")
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


def fetch_detail_metadata(
    url: str, session: requests.Session, timeout: tuple[int, int] = (10, 30)
) -> dict[str, str]:
    """Fetch a coleccion.php?id=N y extrae portada + precio + descripción enriquecida.

    Devuelve dict con image_url, price, description. Vacíos si no se encuentra.

    NO devolver image_url cuando la página es una colección con múltiples
    volúmenes — el calendario sabe el título/volumen pero no puede mapear
    cuál `<img>` de la página corresponde sin reimplementar el parser de
    listadomanga_collections. Mejor placeholder vacío que cover incorrecto
    (gotcha #28: el bug histórico era tomar el primer `<img>` que siempre
    era vol 1 aunque el item del calendario fuera vol 34 Especial).
    """
    result: dict[str, Any] = {
        "image_url": "", "price": "", "description_extra": "", "images": [],
    }
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

    # 1) Imagen principal: SOLO si la página tiene un único item Layout A
    # (colección de un solo tomo / artbook standalone). Si tiene múltiples
    # tomos, dejamos image_url vacío para que el dashboard muestre placeholder
    # — es preferible a un cover wrong. Para enriquecer correctamente el
    # cover de items del calendario que apuntan a colecciones multi-volumen,
    # corré `--bootstrap-wiki listadomanga-collections` que parsea por vol+edition.
    item_imgs = [
        img for img in soup.find_all("img", class_="portada")
        if "static.listadomanga.com" in (img.get("src") or "")
    ]
    if len(item_imgs) == 1:
        result["image_url"] = item_imgs[0]["src"].strip()
        # Multi-imagen: SOLO cuando es un tomo único (artbook standalone /
        # colección de un solo volumen). Páginas multi-tomo agruparían
        # covers de hermanos distintos en una sola card, lo cual es wrong.
        try:
            gallery = _extract_images_from_detail_soup(soup, url)
        except Exception:
            gallery = []
        if len(gallery) > 1:
            result["images"] = gallery

    # 2) Precio: regex en el body buscando "X,YY €"
    body_text = soup.get_text(" ", strip=True)
    # ListadoManga muestra precios típicos del mercado español en €.
    price_match = re.search(r"(\d{1,3}[,.]\d{2})\s*€", body_text)
    if price_match:
        result["price"] = f"€ {price_match.group(1)}"

    # 3) Descripción enriquecida: capturamos secciones útiles del HTML.
    # ListadoManga usa <b>Etiqueta:</b> Valor en algunas filas. Buscamos
    # info de Formato y Editorial japonesa para contexto extra.
    enriched_parts: list[str] = []
    for label in ("Formato", "Editorial japonesa", "Números en castellano", "Géneros"):
        # Buscar <b>Label:</b> y capturar texto siguiente hasta siguiente <b>
        pattern = re.compile(rf"{re.escape(label)}\s*:\s*([^\n]{{3,200}}?)(?=\s+\w+:|\s*$)")
        m = pattern.search(body_text)
        if m:
            value = clean_text(m.group(1))
            if value and len(value) < 200:
                enriched_parts.append(f"{label}: {value}")
    if enriched_parts:
        result["description_extra"] = " · ".join(enriched_parts)

    return result


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
    fetch_details: bool = False,
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Recorre meses entre [from, to] inclusivo y devuelve candidates scored.

    Solo retorna los que tengan score >= min_score (mismo criterio que el scraper).
    Si fetch_details=True, hace un HTTP extra por item a la página de detalle
    (coleccion.php?id=N) para extraer portada, precio y datos enriquecidos.
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
        if flush_fn and kept:
            flush_fn(kept)
        if sleep_seconds > 0 and idx < len(pairs):
            time.sleep(sleep_seconds)

    # Fase de enrichment por detail-fetch (opt-in).
    if fetch_details and all_candidates:
        print(f"\n[DETAIL-FETCH] enriqueciendo {len(all_candidates)} items con portada/precio/extras")
        enriched_img = 0
        enriched_price = 0
        for i, c in enumerate(all_candidates, start=1):
            meta = fetch_detail_metadata(c.url, session, timeout=timeout)
            if meta["image_url"] and not c.image_url:
                c.image_url = meta["image_url"]
                enriched_img += 1
            if meta["price"] and not c.price:
                c.price = meta["price"]
                enriched_price += 1
            if meta["description_extra"]:
                c.description = f"{c.description} · {meta['description_extra']}"[:2500]
            meta_images = meta.get("images") or []
            if len(meta_images) > 1 and not c.images:
                c.images = meta_images
            if i % 50 == 0:
                print(f"  [{i}/{len(all_candidates)}] +imgs={enriched_img} +prices={enriched_price}")
            if sleep_seconds > 0 and i < len(all_candidates):
                time.sleep(min(sleep_seconds, 0.3))
        print(f"[DETAIL-FETCH] finalizado: {enriched_img} imágenes · {enriched_price} precios enriquecidos")

        # Re-score (porque description_extra puede aportar señales nuevas)
        for c in all_candidates:
            score_candidate(c)

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
