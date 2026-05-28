"""Parser de mangavariant.com — base global de variantes/ediciones especiales (EN).

Mangavariant es una base de datos curada por la comunidad que cataloga
~2700 variantes de manga de 13 países. NO es un retailer — no expone
precio ni botón de compra; las URLs son páginas-referencia ("este variant
existe, así se ve, salió en este año, lo publicó esta editorial").

Encaja con PandaWatch como **fuente de descubrimiento**: nos dice qué
variantes/ediciones especiales existen en el mundo, y otro paso del pipeline
(enrichment, próximo sprint) se encarga de buscar dónde comprarlas. Ver el
"URL-as-reference is OK" en CLAUDE.md.

Estructura del sitio (WordPress + Yoast):

    /sitemap_index.xml
      → variant-sitemap.xml      (1000 URLs)
      → variant-sitemap2.xml     (1000 URLs)
      → variant-sitemap3.xml     (~679 URLs)

Cada URL es /variant/<manga-slug>/<variant-slug>/ y la detail page tiene
un bloque `<div class="variant_info_block">` con:

  - <strong>Published by:</strong>  → publisher (texto plano)
  - <strong>Country:</strong>       → /variant?country=<slug>
  - <strong>Manga:</strong>         → /manga/<series-slug>  ← serie real
  - <strong>Where:</strong>         → /where/<slug>         (Comiket, Steelbox…)
  - <strong>Release:</strong>       → año (4 dígitos)
  - <strong>Tags:</strong>          → N · /variant?tags=<slug>
  - <a class="v_rarity_icon" href="/variant?rarity=<tier>">
  - <div class="vInfo notes">       → descripción libre

El **título visible** de la página es solo el nombre de la edición
(p.ej. "Vol.34 - Crunchyroll variant", "10th anniversary - Natsucomi variant").
La serie va aparte en el tag Manga — la concatenamos con el título para
que el item.title tenga forma "<Serie> — <Edición>" y los filtros / cluster_key
/ búsqueda del dashboard funcionen como en cualquier otra fuente.

API pública (paralela a otaku_calendar.py / whakoom.py):
    parse_variant_detail(html_text, url) -> Candidate | None
    fetch_variant_urls(session, timeout) -> list[str]
    bootstrap(yf, mf, yt, mt, session, ...) -> list[Candidate]
    iter_year_months(yf, mf, yt, mt) -> [(yf, mf)]  (single batch; no calendar)
"""

from __future__ import annotations

import concurrent.futures as cf
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree as ET

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


BASE_URL = "https://mangavariant.com"
VARIANT_SITEMAPS = (
    f"{BASE_URL}/variant-sitemap.xml",
    f"{BASE_URL}/variant-sitemap2.xml",
    f"{BASE_URL}/variant-sitemap3.xml",
)

# Mapping de slugs de país de mangavariant → (nombre_es, idioma_es).
# Slugs cubiertos hoy (13): ar br fr de it jp mexico es tw th uk us vn.
# Nota: "mexico" es el slug, NO "mx" — Yoast usa el nombre largo para MX.
COUNTRY_MAP: dict[str, tuple[str, str]] = {
    "ar": ("Argentina", "Español"),
    "br": ("Brasil", "Portugués"),
    "fr": ("Francia", "Francés"),
    "de": ("Alemania", "Alemán"),
    "it": ("Italia", "Italiano"),
    "jp": ("Japón", "Japonés"),
    "mexico": ("México", "Español"),
    "es": ("España", "Español"),
    "tw": ("Taiwán", "Chino"),
    "th": ("Tailandia", "Tailandés"),
    "uk": ("Reino Unido", "Inglés"),
    "us": ("Estados Unidos", "Inglés"),
    "vn": ("Vietnam", "Vietnamita"),
}


# Title suffix added by Yoast a TODOS los og:title del sitio.
_OG_TITLE_SUFFIX_RE = re.compile(r"\s*-\s*mangavariant\.com\s*$", re.IGNORECASE)

# Variantes de fecha-publicación dentro del JSON-LD (article:modified_time
# es backup). Pero release year viene del campo "Release" del bloque vInfo,
# no de la fecha del post.
_DATE_PUBLISHED_RE = re.compile(r'"datePublished":"([^"]+)"')
_OG_TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]+)"')
_OG_IMAGE_RE = re.compile(r'<meta property="og:image" content="([^"]+)"')
_OG_TYPE_RE = re.compile(r'<meta property="og:type" content="([^"]+)"')


def _virtual_source() -> Source:
    """Source sintética. Los campos country/language se sobreescriben por item."""
    return Source(
        name="Global - Mangavariant",
        url=BASE_URL,
        country="",         # sobreescrito en parse_variant_detail
        language="",        # sobreescrito en parse_variant_detail
        publisher="",       # sobreescrito en parse_variant_detail
        source_class="trusted_media",
        kind="wiki",
        enabled=True,
        tags=["wiki", "mangavariant", "reference", "variant-catalog"],
        notes="mangavariant.com — base global comunitaria de variants/ediciones",
        selectors={},
        max_pages=0,
        purity="manga_only",
    )


def _strip_og_suffix(og_title: str) -> str:
    """Quita ' - mangavariant.com' del final del og:title."""
    return _OG_TITLE_SUFFIX_RE.sub("", og_title or "").strip()


def _extract_vib_field(vib_html: str, label: str) -> tuple[list[str], list[str]]:
    """Extrae (values, hrefs) de un <div class="vInfo"><strong>label:</strong>…</div>.

    Devuelve listas vacías si el label no aparece.
    """
    label_escaped = re.escape(label)
    pat = re.compile(
        rf'<div\s+class="vInfo[^"]*"[^>]*>\s*<strong>\s*{label_escaped}\s*:?\s*</strong>'
        r'(.*?)</div>',
        re.S | re.IGNORECASE,
    )
    m = pat.search(vib_html)
    if not m:
        return [], []
    body = m.group(1)
    values: list[str] = []
    # <li>...</li> → uno por linea
    for li in re.finditer(r'<li[^>]*>(.*?)</li>', body, re.S):
        txt = clean_text(li.group(1))
        if txt:
            values.append(txt)
    # Sin <li>: <ul>plain text</ul>
    if not values:
        m_ul = re.search(r'<ul[^>]*>(.*?)</ul>', body, re.S)
        if m_ul:
            txt = clean_text(m_ul.group(1))
            if txt:
                values.append(txt)
    # Country: texto plano fuera de <ul> ("(Japan)")
    if not values:
        txt = clean_text(body)
        if txt:
            values.append(txt)
    hrefs = re.findall(r'href="([^"]+)"', body)
    return values, hrefs


def _parse_country_slug(hrefs: list[str]) -> str:
    """De ['/variant?country=jp', …] devuelve 'jp'."""
    for href in hrefs:
        m = re.search(r'[?&]country=([a-z-]+)', href)
        if m:
            return m.group(1).lower()
    return ""


def _parse_release_year(values: list[str], hrefs: list[str]) -> str:
    """Devuelve año YYYY o ''. Mangavariant solo expone año, no día/mes."""
    for href in hrefs:
        m = re.search(r'[?&]release-date=(\d{4})', href)
        if m:
            return m.group(1)
    for v in values:
        m = re.search(r'\b(19|20)\d{2}\b', v)
        if m:
            return m.group(0)
    return ""


def _parse_rarity(vib_html: str) -> str:
    m = re.search(
        r'class="v_rarity_icon"\s+href="[^"]*?rarity=([a-z-]+)',
        vib_html, re.IGNORECASE,
    )
    return m.group(1).lower() if m else ""


def _parse_notes(vib_html: str) -> str:
    m = re.search(
        r'<div\s+class="vInfo notes"[^>]*>(.*?)</div>',
        vib_html, re.S | re.IGNORECASE,
    )
    if not m:
        return ""
    txt = clean_text(m.group(1))
    return txt[:1500]


def parse_variant_detail(html_text: str, url: str) -> Candidate | None:
    """Parsea una variant detail page de mangavariant.

    Devuelve None si el HTML no parece una variant page válida (p.ej. 404,
    redirect a home, página de manga en lugar de variant).
    """
    if not html_text or len(html_text) < 1000:
        return None
    # Reject if not a variant og:type
    m_type = _OG_TYPE_RE.search(html_text)
    if m_type and m_type.group(1).lower() not in {"article", "website"}:
        return None
    # Tiene que tener el bloque variant_info_block
    if 'class="variant_info_block"' not in html_text:
        return None

    # og:title → edition_name
    m_t = _OG_TITLE_RE.search(html_text)
    if not m_t:
        return None
    edition_name = _strip_og_suffix(m_t.group(1))
    if not edition_name:
        return None

    m_img = _OG_IMAGE_RE.search(html_text)
    image_url = m_img.group(1) if m_img else ""

    # Aislamos el bloque para evitar matchear vInfo de otras secciones
    m_vib = re.search(
        r'class="variant_info_block".+?(?=<div class="wp-block-group|</article>|</main>)',
        html_text, re.S,
    )
    vib = m_vib.group(0) if m_vib else html_text

    pub_values, _ = _extract_vib_field(vib, "Published by")
    publisher = pub_values[0] if pub_values else ""

    _, country_hrefs = _extract_vib_field(vib, "Country")
    country_slug = _parse_country_slug(country_hrefs)

    manga_values, manga_hrefs = _extract_vib_field(vib, "Manga")
    series = manga_values[0] if manga_values else ""
    series_slug = ""
    for href in manga_hrefs:
        m = re.search(r'/manga/([^/?"#]+)', href)
        if m:
            series_slug = m.group(1)
            break

    where_values, _ = _extract_vib_field(vib, "Where")
    where = where_values[0] if where_values else ""

    rel_values, rel_hrefs = _extract_vib_field(vib, "Release")
    release_year = _parse_release_year(rel_values, rel_hrefs)

    tag_values, _ = _extract_vib_field(vib, "Tags")
    variant_tags = [t for t in tag_values if t]

    rarity = _parse_rarity(vib)
    notes = _parse_notes(vib)

    # Skip si no hay serie — sin serie el item no tiene utilidad downstream.
    if not series:
        return None

    # Combinamos serie + edición en el title (la edición sola NO tiene la
    # serie; el filtro by-title del dashboard se rompería).
    title = f"{series} — {edition_name}"

    # Descripción: notes + año + where para que detect_signals y el scorer
    # tengan contexto.
    descr_parts = [notes] if notes else []
    if where:
        descr_parts.append(f"Disponible en: {where}.")
    if release_year:
        descr_parts.append(f"Año de lanzamiento: {release_year}.")
    if variant_tags:
        descr_parts.append("Tags: " + ", ".join(variant_tags) + ".")
    description = " ".join(descr_parts).strip()

    source = _virtual_source()
    country_name, language_name = COUNTRY_MAP.get(country_slug, ("", ""))
    if publisher:
        source.publisher = publisher
    if country_name:
        source.country = country_name
    if language_name:
        source.language = language_name

    cand = candidate_from_source(
        source,
        title=title,
        url=url,
        description=description,
        published_at=release_year,  # solo año; release_date lleva lo mismo
    )
    cand.release_date = release_year
    cand.image_url = image_url
    # Multi-imagen: las detail pages de mangavariant a veces traen una
    # mini-galería en `.entry-content img` además de la cover principal
    # (og:image). Reparsear el HTML con BS4 para usar el extractor común.
    try:
        gallery = _extract_images_from_detail_soup(
            BeautifulSoup(html_text, "html.parser"), url,
        )
    except Exception:
        gallery = []
    if len(gallery) > 1:
        cand.images = gallery
    # Tags: combinamos las del source con discriminantes de mangavariant.
    extra_tags: list[str] = []
    if country_slug:
        extra_tags.append(f"country:{country_slug}")
    if rarity:
        extra_tags.append(f"rarity:{rarity}")
    if where:
        extra_tags.append(f"where:{re.sub(r'[^a-z0-9]+', '-', where.lower()).strip('-')}")
    if series_slug:
        extra_tags.append(f"mv-series:{series_slug}")
    for t in variant_tags:
        slug = re.sub(r'[^a-z0-9]+', '-', t.lower()).strip('-')
        if slug:
            extra_tags.append(f"mv-tag:{slug}")
    cand.tags = list(source.tags) + extra_tags

    # Mangavariant es 100% curado: cada entry ES un variant/edición especial
    # por definición. NO pasamos por is_likely_manga ni is_collectible_edition —
    # el scorer general (que mira signal_types extraídos del título/notes)
    # alcanza para puntuarlo.
    score_candidate(cand)
    return cand


def fetch_variant_urls(
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
    sitemaps: tuple[str, ...] = VARIANT_SITEMAPS,
) -> list[str]:
    """Descarga los 3 sitemaps de variants y devuelve la lista de URLs únicas."""
    urls: list[str] = []
    seen: set[str] = set()
    for sm_url in sitemaps:
        try:
            resp = session.get(sm_url, timeout=timeout)
            resp.raise_for_status()
            xml_text = resp.text
        except requests.RequestException as exc:
            print(f"[WARN] No pude bajar {sm_url}: {exc}")
            continue
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            print(f"[WARN] XML malformado en {sm_url}: {exc}")
            continue
        # Yoast sitemap namespace
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        for url_el in root.findall("sm:url/sm:loc", ns):
            loc = (url_el.text or "").strip()
            if not loc or loc in seen:
                continue
            # Solo /variant/<manga>/<variant>/, no la home /variant/
            if not re.search(r"/variant/[^/]+/[^/]+/?$", loc):
                continue
            seen.add(loc)
            urls.append(loc)
    return urls


def _fetch_one(
    url: str, session: requests.Session, timeout: tuple[int, int],
) -> Candidate | None:
    try:
        resp = session.get(url, timeout=timeout)
        if resp.status_code != 200:
            return None
        if not resp.encoding:
            resp.encoding = resp.apparent_encoding or "utf-8"
        return parse_variant_detail(resp.text, url)
    except requests.RequestException:
        return None


def bootstrap(
    year_from: int,
    month_from: int,
    year_to: int,
    month_to: int,
    session: requests.Session,
    sleep_seconds: float = 0.0,
    timeout: tuple[int, int] = (15, 45),
    min_score: int = 0,
    fetch_details: bool = False,  # noqa: ARG001 (signature compat)
    workers: int = 4,
    max_items: int = 0,
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Descarga el catálogo completo de mangavariant.com.

    El rango año/mes se ignora — mangavariant no particiona por fecha, los
    sitemaps cubren todo. Lo aceptamos solo por compat con el dispatcher.
    `max_items` es para pruebas (0 = todo).
    """
    print(f"[mangavariant] descargando sitemaps de variants…")
    urls = fetch_variant_urls(session, timeout=timeout)
    print(f"[mangavariant] {len(urls)} URLs de variants en los sitemaps")
    if max_items and max_items > 0:
        urls = urls[:max_items]
        print(f"[mangavariant] limitado a {len(urls)} (--max-items)")

    results: list[Candidate] = []
    done = 0
    lock = threading.Lock()

    def task(u: str) -> Candidate | None:
        nonlocal done
        cand = _fetch_one(u, session, timeout)
        with lock:
            done += 1
            if done % 100 == 0:
                print(f"[mangavariant] {done}/{len(urls)} procesados — "
                      f"{len(results)} candidates")
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        return cand

    _flush_batch: list[Candidate] = []
    with cf.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for cand in pool.map(task, urls):
            if cand is None:
                continue
            if min_score and cand.score < min_score:
                continue
            results.append(cand)
            if flush_fn:
                _flush_batch.append(cand)
                if len(_flush_batch) >= 100:
                    flush_fn(_flush_batch)
                    _flush_batch.clear()
    if flush_fn and _flush_batch:
        flush_fn(_flush_batch)

    print(f"[mangavariant] terminado: {len(results)}/{len(urls)} candidates con "
          f"score>={min_score}")
    return results


def iter_year_months(
    year_from: int, month_from: int,
    year_to: int, month_to: int,  # noqa: ARG001 (signature compat)
) -> list[tuple[int, int]]:
    """Mangavariant no tiene calendario mensual; devolvemos un único batch.

    El dispatcher de manga_watch.py usa esto solo para mostrar
    'sobre N meses' en el resumen.
    """
    return [(year_from, month_from)]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--max-items", type=int, default=20,
                        help="Para pruebas locales. 0 = todo.")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; manga-watch-mangavariant)"
    cands = bootstrap(
        2024, 1, 2026, 12,
        session=s,
        sleep_seconds=0.0,
        min_score=0,
        workers=args.workers,
        max_items=args.max_items,
    )
    print(f"\nTotal: {len(cands)} candidates")
    for c in cands[:10]:
        print(f"  [{c.score}] {c.country} | {c.title[:80]}")
