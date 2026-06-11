"""Parser de socialanime.it — variant / limited / special editions italianas.

SocialAnime es un portal italiano de noticias anime/manga con una sección
**MangaStore** curada (https://socialanime.it/store/) que cataloga variants,
ediciones limitadas, special editions y cofanetti del mercado italiano.
Cubre Star Comics, Panini Comics, Edizioni BD, J-Pop, 001 Edizioni, Goen,
Magic Press, Dynit, Coconino y otros publishers italianos chicos que
nuestras sources directas (Panini IT search, Star Comics search) NO cubren
exhaustivamente.

La página `/store/manga/variant` es JS-renderizada — los items se cargan
vía AJAX al div `#results`. El endpoint expuesto por `store.js` es:

    GET /store/backend/flow_mangafeed.php
        ?type={variant|box}
        &group_no={0,1,2,...}            # paginación, 25 items por página
        &macro_filter=best_of_all        # default = últimos 8 meses

y devuelve JSON puro con la forma:

    [
      {
        "id": "2255",
        "nome": "Mob Psycho 100. Variant (Vol. 1)",
        "link": "https://www.amazon.it/dp/8822607155?tag=socianim0c-21",
        "img":  "https://m.media-amazon.com/images/I/91UJQpcT86L._AC_UL960_FMwebp_QL65_.jpg",
        "prezzo": "4.9",
        "prezzo_nn_scontato": "0",
        "PublicationDate": "1 Jan 2030",
        "editore": "Star Comics",
        "autore": "One",
        "trama": "Shigeo, detto anche 'Mob', è uno studente delle medie…",
        "extra": " Variant ",
        "extra_class": "variant"
      },
      ...
    ]

`type=variant` cubre las tres categorías que el sitio anuncia
(Variant, Limited, Special Edition) — están todas en la misma colección,
distinguibles por el texto del `nome`. `type=box` cubre cofanetti / box sets.

**Las URLs son afiliados Amazon** (`amazon.it/dp/<ASIN>?tag=socianim0c-21`).
`normalize_url_for_dedup` strippea `tag`/`linkCode`/`th`/`psc`/`ref=...`
para que dos URLs con afiliados distintos del mismo ASIN colapsen.

API pública (paralela a otaku_calendar.py / mangavariant.py):
    parse_feed_item(item, type_label) -> Candidate | None
    fetch_feed_pages(session, type_label, macro_filter, timeout) -> list[dict]
    bootstrap(yf, mf, yt, mt, session, ...) -> list[Candidate]
    iter_year_months(yf, mf, yt, mt) -> [(yf, mf)]  (single batch; no calendar)
"""

from __future__ import annotations

import re
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


BASE_URL = "https://socialanime.it"
FEED_ENDPOINT = f"{BASE_URL}/store/backend/flow_mangafeed.php"

# Tipos del feed que nos interesan. Cada uno mapea a una sección del store.
# `popolari` y `novita-piu-interessanti` no se incluyen — son mix de catálogo
# general (la mayoría son tomos regulares, no special editions).
FEED_TYPES: tuple[str, ...] = ("variant", "box")

# Macro-filtros que el sitio expone. `best_of_all` baja TODO el catálogo
# histórico; `next_from_now` solo upcoming; default = últimos 8 meses.
# Usamos best_of_all como import inicial; las wikis se relanzan periódicamente
# para captar nuevas entries.
DEFAULT_MACRO_FILTER = "best_of_all"

# Items por página. El backend devuelve 25 fijos.
PAGE_SIZE = 25

# Máximo de páginas a probar por tipo. variant=466 items ≈ 19 páginas,
# box=375 items ≈ 15 páginas. 40 es holgado.
MAX_PAGES_PER_TYPE = 40


# Mapping de `extra_class` y/o keywords del título al hint que metemos en
# la descripción para que `detect_signals` levante el `signal_types` correcto.
# detect_signals matchea por word-boundary sobre title+description, así que
# no inventamos signals — solo nos aseguramos que la palabra aparezca.
_EXTRA_CLASS_HINTS: dict[str, str] = {
    "variant": "Edizione variant cover italiana.",
    "ristampa": "Ristampa.",
    "volume_unico": "Volume unico.",
    # `box` no es un valor real de extra_class — para items de type=box que
    # no tienen `extra_class` set, agregamos cofanetto/box set abajo.
}


def _virtual_source_for_type(type_label: str) -> Source:
    """Source sintética. Una por type (variant vs box) para que el name
    del source en items.jsonl indique qué colección lo trajo."""
    if type_label == "variant":
        name = "IT - SocialAnime Variant"
        notes = "socialanime.it MangaStore — variant/limited/special editions italianas."
    elif type_label == "box":
        name = "IT - SocialAnime Cofanetti"
        notes = "socialanime.it MangaStore — cofanetti / box sets italianos."
    else:
        name = f"IT - SocialAnime {type_label.title()}"
        notes = f"socialanime.it MangaStore — {type_label}."
    return Source(
        name=name,
        url=BASE_URL,
        country="Italia",
        language="Italiano",
        publisher="",                 # se sobreescribe por item desde `editore`
        source_class="trusted_media",  # blog/portal curado, no retailer directo
        kind="wiki",
        enabled=True,
        tags=["wiki", "socialanime", "italia", type_label],
        notes=notes,
        selectors={},
        max_pages=0,
        purity="manga_only",  # toda la colección variant/box es manga curado
    )


# ASIN Amazon: 10 chars alfanuméricos en /dp/<ASIN> o /gp/product/<ASIN>.
# Italian books legacy: ASIN == ISBN-10 (empieza por 88 — prefijo país IT).
_AMAZON_ASIN_RE = re.compile(
    r"/(?:dp|gp/product)/([0-9A-Z]{10})(?:[/?]|$)",
    re.IGNORECASE,
)
# ISBN-10 válido (dígitos, último puede ser X). Los ASIN que NO son ISBN
# empiezan por "B0" (kindle/non-book). Items con ASIN no-ISBN no llevan isbn.
_ISBN10_RE = re.compile(r"^\d{9}[\dXx]$")


def _isbn_from_amazon_url(url: str) -> str:
    """Si el link es amazon.<tld>/dp/<ASIN> y el ASIN parece ISBN-10, lo
    devuelve. ASINs Kindle/non-book (B0xxxxxxxx) → ''."""
    if not url or "amazon." not in url.lower():
        return ""
    m = _AMAZON_ASIN_RE.search(url)
    if not m:
        return ""
    asin = m.group(1).upper()
    return asin if _ISBN10_RE.match(asin) else ""


def _normalize_price(raw: str) -> str:
    """Normaliza el `prezzo` del feed. El feed manda "0" (también "0.00",
    "0,00", "€0", "0 €"…) como placeholder de "precio desconocido" — esos
    valores se tratan como vacío para no corromper el corpus con precios 0.
    Cualquier otro valor se devuelve tal cual (verbatim)."""
    p = (raw or "").strip()
    if not p:
        return ""
    numeric = p.replace("€", "").replace("EUR", "").replace(",", ".").strip()
    try:
        if float(numeric) == 0.0:
            return ""
    except ValueError:
        pass
    return p


# Mes EN → número (PublicationDate viene en "DD MMM YYYY" inglés).
_MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}
_PUB_DATE_RE = re.compile(r"^\s*(\d{1,2})\s+([A-Z][a-z]{2})\s+(\d{4})\s*$")


def _parse_pub_date(raw: str) -> str:
    """'22 Nov 2017' → '2017-11-22'. '1 Jan 2030' (placeholder) → ''.
    Cualquier formato no reconocido → ''."""
    if not raw:
        return ""
    m = _PUB_DATE_RE.match(raw)
    if not m:
        return ""
    day, mon, year = m.groups()
    mm = _MONTHS.get(mon)
    if not mm:
        return ""
    # Placeholder usado por socialanime para "fecha desconocida":
    # "1 Jan 2030" (siempre el mismo). Lo descartamos.
    if year == "2030" and mon == "Jan" and day == "1":
        return ""
    return f"{year}-{mm}-{int(day):02d}"


def parse_feed_item(item: dict, type_label: str) -> Candidate | None:
    """Mapea una entry del JSON feed a un Candidate.

    Devuelve None si el item no tiene los campos mínimos (título o link
    Amazon). Items sin link son ~10% del feed — son entries delisteadas;
    sin URL no podemos dedupar contra el resto del corpus, así que los
    descartamos.
    """
    if not isinstance(item, dict):
        return None

    title_raw = clean_text(item.get("nome") or "")
    url = (item.get("link") or "").strip()
    if not title_raw or not url:
        return None

    image_url = (item.get("img") or "").strip()
    price = _normalize_price(item.get("prezzo") or "")
    publisher = clean_text(item.get("editore") or "")
    author = clean_text(item.get("autore") or "")
    trama = clean_text(item.get("trama") or "")
    extra_class = (item.get("extra_class") or "").strip().lower()
    pub_date = _parse_pub_date(item.get("PublicationDate") or "")

    # Description: trama + hint del extra_class + hint del tipo (si es box
    # y el título no menciona "cofanetto" o "box", inyectamos el keyword
    # para que detect_signals lo levante).
    descr_parts: list[str] = []
    if trama:
        descr_parts.append(trama)

    hint = _EXTRA_CLASS_HINTS.get(extra_class)
    if hint:
        descr_parts.append(hint)

    # Para type=box: el feed entero ES la sección cofanetti, así que
    # garantizamos que `cofanetto` aparezca para que detect_signals levante
    # `box_set` aunque el título no lo diga explícitamente (p.ej. items con
    # "Collector's box" sin "box set", o títulos que solo nombran la serie).
    # Si el título ya contiene `cofanetto`/`box set`/`boxset`, no duplicamos.
    if type_label == "box":
        title_lower = title_raw.lower()
        if not any(kw in title_lower for kw in ("cofanetto", "box set", "boxset")):
            descr_parts.append("Cofanetto / box set.")

    if publisher:
        descr_parts.append(f"Editore: {publisher}.")
    if pub_date:
        descr_parts.append(f"Data uscita: {pub_date}.")
    description = " ".join(descr_parts).strip()

    source = _virtual_source_for_type(type_label)
    if publisher:
        source.publisher = publisher

    cand = candidate_from_source(
        source,
        title=title_raw,
        url=url,
        description=description,
        published_at=pub_date,
    )
    cand.image_url = image_url
    cand.release_date = pub_date
    cand.price = price
    if author:
        cand.author = author

    # ISBN: si el ASIN Amazon parece ISBN-10 (libros italianos legacy con
    # prefijo 88…), lo guardamos. Mejora el cluster_key contra retailers
    # europeos que sí publican ISBN.
    isbn = _isbn_from_amazon_url(url)
    if isbn:
        cand.isbn = isbn

    # Tags: discriminantes de socialanime.
    extra_tags: list[str] = []
    if extra_class:
        extra_tags.append(f"sa-class:{extra_class}")
    cand.tags = list(source.tags) + extra_tags

    # score_candidate levanta signal_types desde title+description. La
    # descripción ya tiene los keywords italianos (variant/cofanetto/limited)
    # gracias a los hints — el scorer hace el resto.
    score_candidate(cand)
    return cand


def fetch_feed_pages(
    session: requests.Session,
    type_label: str,
    macro_filter: str = DEFAULT_MACRO_FILTER,
    timeout: tuple[int, int] = (10, 30),
    max_pages: int = MAX_PAGES_PER_TYPE,
    sleep_seconds: float = 0.0,
) -> list[dict]:
    """Itera group_no=0..N hasta recibir una página vacía. Devuelve la lista
    de items raw (dicts del JSON)."""
    items: list[dict] = []
    referer = f"{BASE_URL}/store/manga/{type_label}"
    for g in range(max_pages):
        params = {"type": type_label, "group_no": str(g)}
        if macro_filter:
            params["macro_filter"] = macro_filter
        try:
            resp = session.get(
                FEED_ENDPOINT,
                params=params,
                headers={
                    "Referer": referer,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/plain, */*",
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            page = resp.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"[socialanime] WARN type={type_label} group_no={g}: {exc}")
            break
        if not isinstance(page, list) or not page:
            break
        items.extend(page)
        if len(page) < PAGE_SIZE:
            # Última página probablemente parcial; cortamos.
            break
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    return items


def bootstrap(
    year_from: int,        # noqa: ARG001 (signature compat con dispatcher)
    month_from: int,       # noqa: ARG001
    year_to: int,          # noqa: ARG001
    month_to: int,         # noqa: ARG001
    session: requests.Session,
    sleep_seconds: float = 0.0,
    timeout: tuple[int, int] = (15, 45),
    min_score: int = 0,
    fetch_details: bool = False,  # noqa: ARG001 (no detail-fetch — el feed ya trae todo)
    types: tuple[str, ...] = FEED_TYPES,
    macro_filter: str = DEFAULT_MACRO_FILTER,
    max_pages: int = MAX_PAGES_PER_TYPE,
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Descarga las colecciones variant + box del MangaStore de SocialAnime.

    El rango año/mes se ignora — el feed no particiona por fecha; los
    macro_filter (best_of_all / next_from_now / default 8 meses) son el
    único control temporal y se setea con `macro_filter`. Lo aceptamos en
    la signature solo por compat con el dispatcher de manga_watch.py.
    """
    print(f"[socialanime] tipos: {types} | macro_filter={macro_filter}")
    candidates: list[Candidate] = []
    seen_urls: set[str] = set()
    for type_label in types:
        raw = fetch_feed_pages(
            session, type_label,
            macro_filter=macro_filter,
            timeout=timeout,
            max_pages=max_pages,
            sleep_seconds=sleep_seconds,
        )
        print(f"[socialanime] type={type_label}: {len(raw)} items raw")
        kept = 0
        type_kept: list[Candidate] = []
        for it in raw:
            cand = parse_feed_item(it, type_label)
            if cand is None:
                continue
            if min_score and cand.score < min_score:
                continue
            # Dedup local entre type=variant y type=box (un cofanetto que
            # también lleva variant cover puede aparecer en ambos feeds).
            if cand.url in seen_urls:
                continue
            seen_urls.add(cand.url)
            candidates.append(cand)
            type_kept.append(cand)
            kept += 1
        print(f"[socialanime] type={type_label}: {kept} candidates tras filtro")
        if flush_fn and type_kept:
            flush_fn(type_kept)
    print(f"[socialanime] terminado: {len(candidates)} candidates con score>={min_score}")
    return candidates


def iter_year_months(
    year_from: int, month_from: int,
    year_to: int, month_to: int,   # noqa: ARG001
) -> list[tuple[int, int]]:
    """SocialAnime no tiene calendario mensual; devolvemos un único batch.
    El dispatcher usa esto solo para el resumen 'sobre N meses'."""
    return [(year_from, month_from)]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--types", default="variant,box",
                        help="Lista de tipos coma-separados (variant,box).")
    parser.add_argument("--macro-filter", default=DEFAULT_MACRO_FILTER,
                        choices=["best_of_all", "next_from_now", ""],
                        help="best_of_all = todo el histórico; "
                             "next_from_now = upcoming; '' = últimos 8 meses.")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES_PER_TYPE)
    args = parser.parse_args()

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; manga-watch-socialanime)"
    types = tuple(t.strip() for t in args.types.split(",") if t.strip())
    cands = bootstrap(
        2024, 1, 2026, 12,
        session=s,
        sleep_seconds=0.0,
        min_score=0,
        types=types,
        macro_filter=args.macro_filter,
        max_pages=args.max_pages,
    )
    print(f"\nTotal: {len(cands)} candidates")
    for c in cands[:10]:
        print(f"  [{c.score}] {c.country} | {c.publisher} | {c.title[:80]}")
