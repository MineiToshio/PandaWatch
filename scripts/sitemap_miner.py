"""sitemap_miner.py — descubre URLs de producto vía /sitemap.xml.

Fase 3 del PRD-catalog. Many sites expose all their product URLs in
/sitemap.xml (or via robots.txt directives). Una sola request te
puede dar miles de URLs vs paginar 50+ páginas del catálogo.

API pública:
    discover_sitemap_urls(base_url, session) -> list[str]
        Devuelve URLs candidatas de sitemap (probando varios paths).

    parse_sitemap_xml(xml_text) -> tuple[list[str], list[str]]
        Devuelve (urls_planas, sitemaps_anidados).

    fetch_all_sitemap_urls(base_url, session, max_depth=3) -> list[str]
        Descubre + parsea recursivamente. Devuelve todas las URLs en la
        red de sitemaps.

    filter_product_urls(urls, include_patterns, exclude_patterns) -> list[str]
        Filtra por substring de path. Útil para retener solo
        /producto/..., /manga/..., /products/..., etc.
"""

from __future__ import annotations

import gzip
import html
import re
import sys
import time
from typing import Any
from urllib.parse import urlparse

import requests


SITEMAP_CANDIDATE_PATHS = (
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/sitemap1.xml",
    "/sitemaps/sitemap.xml",
    "/sitemap_products.xml",
    "/product-sitemap.xml",
    "/wp-sitemap.xml",  # WordPress nativo
    "/wp-sitemap-posts-product-1.xml",
)


# 429 → UN reintento con backoff (Retry-After si el server lo manda, si no un
# default fijo) — mismo espíritu que la política 403 del scraper principal
# (docs/reference/conventions.md § anti-bot): un reintento, NUNCA un loop.
_MAX_429_RETRIES = 1
_DEFAULT_429_WAIT_SECONDS = 2.0


def _retry_after_seconds(response: requests.Response, default: float = _DEFAULT_429_WAIT_SECONDS) -> float:
    header = response.headers.get("Retry-After")
    if header:
        try:
            return max(0.0, float(header))
        except ValueError:
            pass
    return default


def _fetch_text(url: str, session: requests.Session, timeout: tuple[int, int] = (10, 30)) -> str:
    """Fetch URL devolviendo texto (descomprime .gz si hace falta). Vacío si falla.

    Hallazgos #10/#13 (2026-07-08): 429 se reintenta UNA vez con backoff (antes
    no se manejaba — un sitio rate-limiteado devolvía "" igual que cualquier
    otro fallo, indistinguible en el log); y las excepciones ya no se tragan en
    silencio — se loguean a stderr antes de degradar a "" (el caller trata ""
    como "no hay sitemap acá", comportamiento sin cambios).
    """
    for attempt in range(_MAX_429_RETRIES + 1):
        try:
            response = session.get(url, timeout=timeout)
        except requests.RequestException as exc:
            print(f"[sitemap_miner] WARN fetch failed {url}: {exc}", file=sys.stderr)
            return ""
        if response.status_code == 429 and attempt < _MAX_429_RETRIES:
            time.sleep(_retry_after_seconds(response))
            continue
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"[sitemap_miner] WARN {url}: {exc}", file=sys.stderr)
            return ""
        # Algunos sitemaps vienen gzipped pero el servidor responde con .xml.gz
        if url.endswith(".gz") or response.headers.get("Content-Encoding") == "gzip" or response.content[:2] == b"\x1f\x8b":
            try:
                return gzip.decompress(response.content).decode("utf-8", errors="replace")
            except (OSError, ValueError) as exc:
                print(f"[sitemap_miner] WARN gzip decode failed {url}: {exc}", file=sys.stderr)
                return ""
        if not response.encoding:
            response.encoding = response.apparent_encoding or "utf-8"
        return response.text
    return ""


def _read_robots_sitemaps(base_url: str, session: requests.Session) -> list[str]:
    """Lee /robots.txt y extrae las directivas 'Sitemap:'."""
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = session.get(robots_url, timeout=(10, 20))
        if response.status_code != 200:
            return []
        text = response.text
    except requests.RequestException as exc:
        print(f"[sitemap_miner] WARN robots.txt fetch failed {robots_url}: {exc}", file=sys.stderr)
        return []
    urls: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("sitemap:"):
            url = line.split(":", 1)[1].strip()
            if url and url not in urls:
                urls.append(url)
    return urls


def discover_sitemap_urls(base_url: str, session: requests.Session) -> list[str]:
    """Devuelve una lista de URLs candidatas de sitemap a probar.

    Estrategia:
    1. Leer /robots.txt y extraer 'Sitemap:' directives (más confiable).
    2. Si no hay, probar paths comunes (/sitemap.xml, etc.).
    """
    discovered: list[str] = []

    # 1) Robots.txt
    robots_sitemaps = _read_robots_sitemaps(base_url, session)
    for url in robots_sitemaps:
        if url not in discovered:
            discovered.append(url)

    # 2) Paths comunes
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    for path in SITEMAP_CANDIDATE_PATHS:
        candidate = origin + path
        if candidate not in discovered:
            discovered.append(candidate)

    return discovered


# Regex para extraer <loc>...</loc> sin necesidad de namespace XML parsing.
# Hallazgo #9 (2026-07-08): soporta tanto texto plano como `<![CDATA[...]]>`
# (algunos generadores de sitemap envuelven la URL en CDATA — el patrón viejo
# solo matcheaba texto plano y esas URLs se perdían sin ningún aviso).
LOC_PATTERN = re.compile(
    r"<loc>\s*(?:<!\[CDATA\[(?P<cdata>.*?)\]\]>|(?P<plain>[^<>\s]+))\s*</loc>",
    re.IGNORECASE | re.DOTALL,
)
SITEMAPINDEX_PATTERN = re.compile(r"<sitemapindex\b", re.IGNORECASE)


def _extract_loc(m: re.Match) -> str:
    """Valor de un match de LOC_PATTERN, des-escapado de entidades XML.

    Hallazgo #9: `&amp;amp;` en el XML crudo (una URL con `&` re-escapada por
    el generador del sitemap) rompía la URL si no se hacía `html.unescape()`
    ANTES de usarla — quedaba con `&amp;` literal en vez de `&`.
    """
    raw = m.group("cdata") if m.group("cdata") is not None else m.group("plain")
    return html.unescape((raw or "").strip())


def parse_sitemap_xml(xml_text: str) -> tuple[list[str], list[str]]:
    """Parsea un sitemap XML y devuelve (urls_de_producto, sitemaps_anidados).

    - Si el documento es un <sitemapindex>, las <loc> son sitemaps anidados.
    - Si es un <urlset>, las <loc> son URLs finales (productos, posts, etc.).
    """
    if not xml_text or len(xml_text) < 50:
        return [], []
    locs = [_extract_loc(m) for m in LOC_PATTERN.finditer(xml_text)]
    locs = [loc for loc in locs if loc]
    is_index = bool(SITEMAPINDEX_PATTERN.search(xml_text))
    if is_index:
        return [], locs
    return locs, []


def fetch_all_sitemap_urls(
    sitemap_url: str,
    session: requests.Session,
    max_depth: int = 3,
    max_urls: int = 50_000,
    timeout: tuple[int, int] = (10, 30),
    _preloaded: dict[str, str] | None = None,
) -> list[str]:
    """Descarga sitemap recursivamente y devuelve todas las URLs finales.

    Cap a max_urls para evitar runaway en sitios grandes.

    `_preloaded` (uso interno, hallazgo #10, 2026-07-08): mapa `{url: texto}`
    con sitemaps que el CALLER ya descargó (típicamente `discover_and_filter`,
    que fetchea el candidato una vez para validarlo antes de llamar acá) — evita
    una 2ª request idéntica al mismo servidor.
    """
    seen: set[str] = set()
    all_urls: list[str] = []
    queue: list[tuple[str, int]] = [(sitemap_url, 0)]
    visited_sitemaps: set[str] = set()
    preloaded = _preloaded or {}

    while queue and len(all_urls) < max_urls:
        url, depth = queue.pop(0)
        if url in visited_sitemaps or depth > max_depth:
            continue
        visited_sitemaps.add(url)

        text = preloaded.get(url) if url in preloaded else _fetch_text(url, session, timeout=timeout)
        if not text:
            continue
        urls, nested = parse_sitemap_xml(text)
        for u in urls:
            if u not in seen:
                seen.add(u)
                all_urls.append(u)
                if len(all_urls) >= max_urls:
                    break
        for n in nested:
            if n not in visited_sitemaps:
                queue.append((n, depth + 1))
    return all_urls


def filter_product_urls(
    urls: list[str],
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> list[str]:
    """Filtra URLs por substring de path.

    - include_patterns: si está, requiere que AL MENOS uno aparezca en la URL.
    - exclude_patterns: si está, descarta URLs que contengan AL MENOS uno.
    """
    incl = [p.lower() for p in (include_patterns or [])]
    excl = [p.lower() for p in (exclude_patterns or [])]
    out: list[str] = []
    for u in urls:
        lower = u.lower()
        if incl and not any(p in lower for p in incl):
            continue
        if excl and any(p in lower for p in excl):
            continue
        out.append(u)
    return out


# Heurísticas comunes para detectar URLs de producto cuando no se especifica.
DEFAULT_PRODUCT_INCLUDES = (
    "/product/", "/products/", "/producto/", "/productos/",
    "/manga/", "/comic/", "/comics/", "/livre/", "/libro/",
    "/ficha/", "/p/", "/shop/g/",
    "/article/", "/articles/",  # algunos sites llaman así
)

DEFAULT_PRODUCT_EXCLUDES = (
    "/category/", "/categories/", "/tag/", "/tags/",
    "/page/", "/pages/", "/blog/", "/news/",
    "/login", "/account", "/cart", "/checkout",
    ".css", ".js", ".jpg", ".png", ".gif", ".pdf",
    "/feed", "/rss", "/sitemap",
)


def discover_and_filter(
    base_url: str,
    session: requests.Session,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    max_urls: int = 50_000,
    timeout: tuple[int, int] = (10, 30),
) -> dict[str, Any]:
    """Pipeline completo: discover → fetch → parse recursivo → filter.

    Devuelve dict con:
      - sitemap_url: el sitemap raíz que funcionó (o "" si ninguno)
      - all_urls: todas las URLs del sitemap
      - product_urls: filtradas como probable producto
    """
    result = {"sitemap_url": "", "all_urls": [], "product_urls": []}

    candidates = discover_sitemap_urls(base_url, session)
    chosen_url = ""
    chosen_urls: list[str] = []
    for candidate in candidates:
        text = _fetch_text(candidate, session, timeout=timeout)
        if not text or len(text) < 50:
            continue
        # Hallazgo #10 (2026-07-08): el candidato ya se bajó arriba para
        # validarlo — se lo pasamos precargado a fetch_all_sitemap_urls en vez
        # de dejar que lo re-descargue (misma URL, mismo servidor, 2ª request
        # innecesaria en CADA candidato probado).
        urls = fetch_all_sitemap_urls(
            candidate, session, max_urls=max_urls, timeout=timeout,
            _preloaded={candidate: text},
        )
        if urls:
            chosen_url = candidate
            chosen_urls = urls
            break

    if not chosen_urls:
        return result

    product_urls = filter_product_urls(
        chosen_urls,
        include_patterns=include_patterns or list(DEFAULT_PRODUCT_INCLUDES),
        exclude_patterns=exclude_patterns or list(DEFAULT_PRODUCT_EXCLUDES),
    )
    result["sitemap_url"] = chosen_url
    result["all_urls"] = chosen_urls
    result["product_urls"] = product_urls
    return result
