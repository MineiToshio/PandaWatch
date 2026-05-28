"""Parser de manga-passion.de — ediciones especiales alemanas (Sonderausgaben + Variant-Covers).

manga-passion.de es el catálogo de referencia más completo del mercado DACH.
Expone una API pública REST JSON-LD (Hydra) en ``api.manga-passion.de``
sin autenticación requerida.

Endpoint base::

    GET https://api.manga-passion.de/volumes
        ?type[]=3               # Sonderausgabe (Limited/Collector/Premium/Box)
        &itemsPerPage=50
        &page=N
        &date[after]=YYYY-MM-DD  # filtro delta, opcional

Tipos de volumen relevantes:
  - ``type=3`` (Sonderausgabe): cualquier edición especial — Limited Edition,
    Collector's Edition, Premium Edition, Sammelschuber (estuche), etc.
  - ``type=0 + tags.tag.id=200``: tomos regulares con Variant-Cover.

Schema de un volumen (campos relevantes)::

    {
      "id": 18905,
      "type": 3,
      "specialType": 0,      # 0=limited/collector, 1=Sammelschuber (box/estuche)
      "title": "Limited Edition",  # qualifier de la edición, NO el título de la serie
      "numberDisplay": "1",        # número de tomo como string
      "price": 1900,               # en centavos → EUR 19.00
      "year": 2025, "month": 1, "day": 7,
      "isbn13": "978-3-98745-044-0",
      "isbn10": null,
      "cover": "https://media.manga-passion.de/volume/cover/...",
      "tags": [{"tag": {"id": 189, "name": "Anhänger"}, "description": "Acryl-Schlüsselanhänger"}],
      "contributors": [{"contributor": {"name": "Autor"}, "role": "Zeichner"}],
      "edition": {
        "id": 3116,
        "title": "My Tiny Senpai",   # título de la serie
        "publishers": [{"id": 186, "name": "Dokico"}],
        "sources": [{"country": "JP"}]
      }
    }

El precio está en **centavos** (1900 = EUR 19.00).
La URL canónica de cada item usa el ID de la API (``api.manga-passion.de/volumes/{id}``),
estable y único por volumen.

API pública (misma firma que los demás wiki parsers)::

    parse_volume(item)             -> Candidate | None
    fetch_volumes(session, ...)    -> list[dict]
    bootstrap(yf, mf, yt, mt, ...) -> list[Candidate]
    iter_year_months(yf, mf, yt, mt) -> [(yf, mf)]  (batch único)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Callable

import requests

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


API_BASE = "https://api.manga-passion.de"
SITE_BASE = "https://www.manga-passion.de"
VOLUMES_ENDPOINT = f"{API_BASE}/volumes"

# Consultas que lanzamos. Cada dict es el conjunto de parámetros fijos;
# fetch_volumes añade date[after], itemsPerPage y page encima.
QUERY_TYPES: list[dict] = [
    {"type[]": "3"},                          # Sonderausgaben (Limited/Collector/etc.)
    {"type[]": "0", "tags.tag.id": "200"},    # Variant-Covers de tomos regulares
]

PAGE_SIZE = 50
MAX_PAGES = 300   # safety cap; ~437 Sonderausgaben / 50 = ~9 páginas reales

# specialType=1 → Sammelschuber (estuche/slipcase = box_set)
_SPECIAL_TYPE_SCHUBER = 1

# Tag IDs → keywords en inglés que detect_signals entiende.
# Solo para tags que NO aparecen ya en el título del volumen como qualifier.
_TAG_ID_TO_HINT: dict[int, str] = {
    261: "Box Set Schuber",     # Box / Sammelschuber (tag físico en catálogo)
    228: "DVD Blu-ray bonus",   # DVD/Blu-ray incluido
}

# Publishers alemanes no cubiertos por el _PUBLISHER_SLUG_MAP global.
# La función _publisher_slug_de() los consulta localmente; el slug global
# (_publisher_slug en manga_watch.py) también aplica para los ya conocidos
# (tokyopop, kazé/kaze, panini, etc.).
_DE_PUBLISHER_EXTRA: dict[str, str] = {
    "carlsen": "carlsen",
    "egmont": "egmont",
    "dokico": "dokico",
    "papertoons": "papertoons",
    "cross cult": "crosscult",
    "manga cult": "mangacult",
    "loewe": "loewe",
    "reprodukt": "reprodukt",
    "b-love": "blove",
    "altraverse": "altraverse",
    "universe": "universe-de",
}


def _publisher_slug_de(publisher: str) -> str:
    """Slug canónico para publishers alemanes (complementa el map global)."""
    lc = publisher.lower()
    for key, slug in _DE_PUBLISHER_EXTRA.items():
        if key in lc:
            return slug
    # Fallback: slug del nombre crudo (para publishers futuros desconocidos)
    return lc.replace(" ", "-")[:24]


def _virtual_source(type_label: str) -> Source:
    """Source sintética diferenciada por tipo de query."""
    if type_label == "variant":
        name = "DE - Manga-Passion Variant-Covers"
        notes = "manga-passion.de API — Variant-Covers del catálogo alemán."
    else:
        name = "DE - Manga-Passion Sonderausgaben"
        notes = "manga-passion.de API — Sonderausgaben del catálogo alemán (Limited/Collector/Premium/Box)."
    return Source(
        name=name,
        url=SITE_BASE,
        country="Alemania",
        language="Deutsch",
        publisher="",
        source_class="trusted_catalog",
        kind="wiki",
        enabled=True,
        tags=["wiki", "mangapassion", "deutschland"],
        notes=notes,
        selectors={},
        max_pages=0,
        purity="manga_only",
    )


def parse_volume(item: dict, type_label: str = "sonderausgabe") -> Candidate | None:
    """Mapea un volumen de la API a un Candidate.

    Devuelve None si faltan los campos mínimos (id o título de serie).
    """
    if not isinstance(item, dict):
        return None

    volume_id = item.get("id")
    if not volume_id:
        return None

    edition = item.get("edition") or {}
    series_title = clean_text(edition.get("title") or "")
    if not series_title:
        return None

    vol_display = str(item.get("numberDisplay") or item.get("number") or "").strip()
    edition_qualifier = clean_text(item.get("title") or "")  # "Limited Edition", etc.

    # Título completo: "My Tiny Senpai Band 1 – Limited Edition"
    parts = [series_title]
    if vol_display:
        parts.append(f"Band {vol_display}")
    title = " ".join(parts)
    if edition_qualifier:
        title = f"{title} – {edition_qualifier}"

    # URL canónica: API URL del volumen — estable, única por ID de base de datos
    url = f"{API_BASE}/volumes/{volume_id}"

    # Publisher
    publishers = edition.get("publishers") or []
    publisher = clean_text(publishers[0].get("name") or "") if publishers else ""

    # Precio en centavos → "XX.XX €"
    price_cents = item.get("price")
    price = (
        f"{price_cents / 100:.2f} €"
        if isinstance(price_cents, (int, float)) and price_cents > 0
        else ""
    )

    # Fecha de lanzamiento
    year = item.get("year")
    month = item.get("month")
    day = item.get("day")
    release_date = (
        f"{year:04d}-{month:02d}-{day:02d}"
        if year and month and day
        else ""
    )

    # ISBN (preferir ISBN-13 limpio)
    isbn13 = (item.get("isbn13") or "").replace("-", "").strip()
    isbn10 = (item.get("isbn10") or "").strip()
    isbn = isbn13 or isbn10

    # Portada
    image_url = (item.get("cover") or "").strip()

    # Autor: primer contributor disponible
    author = ""
    for contrib in (item.get("contributors") or []):
        c = contrib.get("contributor") or {}
        name = clean_text(c.get("name") or "")
        if name:
            author = name
            break

    # Tags → extras descriptivos + hints de señal para detect_signals
    tags_data = item.get("tags") or []
    extra_names: list[str] = []
    signal_hints: list[str] = []
    for tag_entry in tags_data:
        tag = tag_entry.get("tag") or {}
        tag_id = tag.get("id")
        tag_name = clean_text(tag.get("name") or "")
        tag_desc = clean_text(tag_entry.get("description") or "")
        hint = _TAG_ID_TO_HINT.get(tag_id)
        if hint:
            signal_hints.append(hint)
        display = tag_desc or tag_name
        if display:
            extra_names.append(display)

    # specialType=1 → Sammelschuber: inyectamos "Box Set" para que detect_signals
    # levante box_set (el término alemán "Sammelschuber" no está en los patterns).
    if item.get("specialType") == _SPECIAL_TYPE_SCHUBER:
        signal_hints.append("Sammelschuber Box Set")

    # Para type=variant query: garantizar que "Variant Cover" aparezca en descripción
    if type_label == "variant" and "Variant" not in (edition_qualifier or ""):
        signal_hints.append("Variant Cover")

    # Descripción: extras + hints + metadata
    descr_parts: list[str] = []
    if extra_names:
        descr_parts.append("Extras: " + ", ".join(extra_names) + ".")
    descr_parts.extend(signal_hints)
    if publisher:
        descr_parts.append(f"Verlag: {publisher}.")
    if release_date:
        descr_parts.append(f"Erscheinungsdatum: {release_date}.")
    description = " ".join(descr_parts)

    source = _virtual_source(type_label)
    if publisher:
        source.publisher = publisher

    cand = candidate_from_source(
        source,
        title=title,
        url=url,
        description=description,
        published_at=release_date,
    )
    cand.image_url = image_url
    cand.release_date = release_date
    cand.price = price
    if author:
        cand.author = author
    if isbn:
        cand.isbn = isbn

    score_candidate(cand)
    return cand


def fetch_volumes(
    session: requests.Session,
    query_params: dict,
    date_after: str = "",
    timeout: tuple[int, int] = (10, 30),
    max_pages: int = MAX_PAGES,
    sleep_seconds: float = 0.3,
) -> list[dict]:
    """Pagina el endpoint /volumes hasta agotar resultados o max_pages.

    La API usa Hydra: cada respuesta incluye ``hydra:member`` (items de la
    página) y ``hydra:view.hydra:next`` (URL de la siguiente página si existe).
    """
    params = dict(query_params)
    params["itemsPerPage"] = str(PAGE_SIZE)
    params["order[year]"] = "asc"
    params["order[month]"] = "asc"
    params["order[day]"] = "asc"
    if date_after:
        params["date[after]"] = date_after

    items: list[dict] = []
    for page in range(1, max_pages + 1):
        params["page"] = str(page)
        try:
            resp = session.get(
                VOLUMES_ENDPOINT,
                params=params,
                headers={"Accept": "application/ld+json"},
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"[mangapassion] WARN page={page}: {exc}")
            break

        members = data.get("hydra:member") or []
        if not members:
            break
        items.extend(members)

        # Sin hydra:next → última página
        view = data.get("hydra:view") or {}
        if not view.get("hydra:next"):
            break

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return items


def bootstrap(
    year_from: int,
    month_from: int,
    year_to: int,    # noqa: ARG001 (firma compatible con dispatcher)
    month_to: int,   # noqa: ARG001
    session: requests.Session,
    sleep_seconds: float = 0.3,
    timeout: tuple[int, int] = (15, 45),
    min_score: int = 0,
    fetch_details: bool = False,  # noqa: ARG001 (la API ya trae todo)
    query_types: list[dict] | None = None,
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Descarga Sonderausgaben y Variant-Covers del catálogo alemán.

    ``year_from``/``month_from`` definen el ``date[after]`` para modo delta.
    Si ``year_from`` < 2010 se descarga todo el catálogo histórico sin filtro.
    """
    if query_types is None:
        query_types = QUERY_TYPES

    # Filtro de fecha: si year_from es muy antiguo (full mode) no lo aplicamos
    date_after = ""
    if year_from >= 2010:
        date_after = f"{year_from:04d}-{month_from:02d}-01"

    print(
        f"[mangapassion] date_after={date_after or '(catálogo completo)'} | "
        f"queries: {len(query_types)}"
    )

    candidates: list[Candidate] = []
    seen_ids: set[int] = set()

    for q_params in query_types:
        type_val = q_params.get("type[]", "?")
        tag_val = q_params.get("tags.tag.id", "")
        label = f"type={type_val}" + (f"/tag={tag_val}" if tag_val else "")
        type_label = "variant" if tag_val == "200" else "sonderausgabe"

        raw = fetch_volumes(
            session,
            q_params,
            date_after=date_after,
            timeout=timeout,
            sleep_seconds=sleep_seconds,
        )
        print(f"[mangapassion] {label}: {len(raw)} volumes raw")

        kept = 0
        type_kept: list[Candidate] = []
        for item in raw:
            vid = item.get("id")
            if vid in seen_ids:
                continue
            seen_ids.add(vid)

            cand = parse_volume(item, type_label)
            if cand is None:
                continue
            if min_score and cand.score < min_score:
                continue
            candidates.append(cand)
            type_kept.append(cand)
            kept += 1

        print(f"[mangapassion] {label}: {kept} candidates tras filtro")
        if flush_fn and type_kept:
            flush_fn(type_kept)

    print(f"[mangapassion] terminado: {len(candidates)} candidates total")
    return candidates


def iter_year_months(
    year_from: int, month_from: int,
    year_to: int, month_to: int,    # noqa: ARG001
) -> list[tuple[int, int]]:
    """La API no particiona por mes; devuelve un único batch."""
    return [(year_from, month_from)]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingesta manga-passion.de")
    parser.add_argument(
        "--wiki-from", default="",
        help="Filtro delta: YYYY-MM (ej. 2025-01). Vacío = todo el catálogo.",
    )
    parser.add_argument("--sleep", type=float, default=0.3)
    args = parser.parse_args()

    year_from, month_from = 2000, 1
    if args.wiki_from:
        parts = args.wiki_from.split("-")
        year_from, month_from = int(parts[0]), int(parts[1])

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; manga-watch-personal/0.2)"

    cands = bootstrap(
        year_from, month_from, 2030, 12,
        session=s,
        sleep_seconds=args.sleep,
        min_score=0,
    )
    print(f"\nTotal: {len(cands)} candidates")
    for c in cands[:15]:
        print(f"  [{c.score:3d}] {c.publisher:<20} {c.title[:70]}")
