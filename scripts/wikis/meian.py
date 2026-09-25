"""Parser de Meian (FR) — ingesta por API JSON en vez de scraping HTML.

**Por qué existe este módulo.** `meian-editions.fr` es una app Angular que NO
renderiza nada sin JavaScript: el HTML servido pesa 64 KB (CSS crítico inlineado
más preloads) pero el texto útil del `<body>` son 60 caracteres —"Please enable
JavaScript to continue using this application."— y CERO enlaces. Tampoco hay
sitemap: cualquier ruta (`/meian/sitemap.xml` incluida) devuelve el mismo shell,
porque la app es catch-all. La fuente estuvo declarada `kind: js` y aun así
rindió 0 candidatos durante 4 corridas seguidas (2026-08-30 → 09-07).

**La API.** La app se alimenta de un API JSON en OTRO host, descubierto
capturando el tráfico de red del navegador el 2026-09-07 (no es deducible del
bundle: `main-EDWVHENJ.js`, 447 KB, sólo expone rutas de UI):

    GET https://www.anime-store.fr/api-meian/v5/licences/?cat=0&q=
    GET https://www.anime-store.fr/api-meian/v5/produits/licence/?id_serie=<id>&ref=0

Dos detalles que hacen fallar el acceso ingenuo:

1. **Exige el header `Origin: https://www.meian-editions.fr`.** Sin él responde
   `403 {"success":false,"message":"Access Forbidden"}`. Un `Referer` NO alcanza.
2. **La respuesta lleva prefijo anti-XSSI** `)]}',\n` antes del JSON. Hay que
   quitar la primera línea antes de parsear, o `json.loads` revienta.

El host es `www.anime-store.fr` **con `www.`**: sin el prefijo da 403/404 y
parece que la API no existiera.

**Qué aporta.** El catálogo son ~168 licencias (series); el endpoint de
productos lista cada volumen y — lo que le interesa al tracker — los **Coffrets
Collector**: en las 3 series más largas ya aparecen 15 cajas
("Kingdom - Partie 1 - Coffret Collector (tomes 01 à 10)"). El listing no trae
ISBN, precio ni fecha de salida: eso queda para el fetch de detalle del pipeline.

API pública (misma firma que los demás wiki parsers)::

    fetch_licences(session)                 -> list[dict]
    fetch_products(session, id_serie)       -> list[dict]
    parse_product(product, licence)         -> Candidate | None  (sin red)
    bootstrap(yf, mf, yt, mt, ...)          -> list[Candidate]
    iter_year_months(yf, mf, yt, mt)        -> [(yf, mf)]         (batch único)
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

import requests
try:
    from .health import report_issue
except ImportError:  # direct script execution
    from health import report_issue

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

SITE = "https://www.meian-editions.fr"
API_BASE = "https://www.anime-store.fr/api-meian/v5"
API_LICENCES = f"{API_BASE}/licences/"
API_PRODUCTS = f"{API_BASE}/produits/licence/"

# El `Origin` NO es cosmético: sin él la API responde 403 (ver docstring).
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Origin": SITE,
}

# Prefijo anti-XSSI que la API antepone al JSON.
_XSSI_PREFIX = ")]}'"

# Términos de edición especial en el catálogo francés de Meian.
SPECIAL_RE = re.compile(
    r"coffret|collector|[ée]dition\s+(?:limit[ée]e|sp[ée]ciale|deluxe|collector)"
    r"|deluxe|artbook|art\s*book|int[ée]grale|box\s*set|fourreau",
    re.IGNORECASE,
)


def _virtual_source() -> Source:
    return Source(
        name="FR - Meian (API)",
        url=f"{SITE}/meian/catalogue-meian",
        country="Francia",
        language="Francés",
        publisher="Meian",
        source_class="official",
        kind="wiki",
        purity="manga_only",
        tags=["manga", "wiki", "meian", "official", "france"],
    )


def _get_json(session: requests.Session, url: str, params: dict[str, Any],
              timeout: tuple[int, int]) -> dict:
    """GET + limpieza del prefijo anti-XSSI. Devuelve {} ante cualquier fallo."""
    try:
        resp = session.get(url, params=params, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        report_issue(session, f"meian {url} {params}: {exc}")
        return {}
    text = resp.text
    if text.startswith(_XSSI_PREFIX):
        _, _, text = text.partition("\n")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        report_issue(session, f"meian non-JSON response {url}: {exc}")
        return {}
    return data if isinstance(data, dict) else {}


def fetch_licences(session: requests.Session,
                   timeout: tuple[int, int] = (15, 45)) -> list[dict]:
    """Catálogo completo de licencias (series). Un solo request."""
    data = _get_json(session, API_LICENCES, {"cat": 0, "q": ""}, timeout)
    licences = data.get("licences") or []
    return [x for x in licences if isinstance(x, dict)]


def fetch_products(session: requests.Session, id_serie: Any,
                   timeout: tuple[int, int] = (15, 45)) -> list[dict]:
    """Productos (volúmenes y coffrets) de una licencia."""
    data = _get_json(session, API_PRODUCTS,
                     {"id_serie": id_serie, "ref": 0}, timeout)
    products = data.get("produits") or []
    return [x for x in products if isinstance(x, dict)]


def is_special_title(title: str) -> bool:
    return bool(SPECIAL_RE.search(title or ""))


def product_url(product: dict) -> str:
    """URL pública de la ficha en meian-editions.fr."""
    seo = (product.get("seo") or "").strip()
    ref = str(product.get("ref") or "").strip()
    if not seo or not ref:
        return ""
    return f"{SITE}/meian/produit/{seo}/{ref}"


def parse_product(product: dict, licence: dict | None = None) -> Candidate | None:
    """Producto del API → Candidate (sin red). None si no es edición especial."""
    if not isinstance(product, dict):
        return None
    title = clean_text(product.get("titre") or "")
    url = product_url(product)
    if not title or not url:
        return None
    if not is_special_title(title):
        return None

    bits = [title]
    author = clean_text(product.get("auteur") or "")
    if author:
        bits.append(author)
    if licence:
        serie = clean_text(licence.get("titre") or "")
        if serie and serie != title:
            bits.append(f"Série : {serie}")
    bits.append("Meian")
    description = clean_text(" · ".join(bits))[:1200]

    cand = candidate_from_source(
        _virtual_source(),
        title=title,
        url=url,
        description=description,
    )
    if author:
        cand.author = author
    image = (product.get("url_img_200") or product.get("url_img") or "").strip()
    if image:
        cand.image_url = image
    score_candidate(cand)
    return cand


API_PRODUCT = f"{API_BASE}/produit/"


def _first(value: Any) -> str:
    """El API devuelve listas para varios campos (autor, imágenes)."""
    if isinstance(value, list):
        return str(value[0]).strip() if value else ""
    return str(value or "").strip()


def _iso_date(raw: str) -> str:
    """`28-11-2025` → `2025-11-28`. Devuelve "" si no matchea el formato."""
    m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", (raw or "").strip())
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def enrich_candidate(session: requests.Session, cand: Candidate, ref: Any,
                     timeout: tuple[int, int] = (15, 45)) -> None:
    """Completa el candidate con la ficha del API (ISBN, fecha, portada, texto).

    La página pública es Angular, así que el fetch-details HTML del pipeline no
    puede leer nada: este endpoint es el único camino. **El precio NO se
    captura** (decisión del owner 2026-06-11).
    """
    data = _get_json(session, API_PRODUCT, {"ref": ref}, timeout)
    product = data.get("produit")
    if not isinstance(product, dict):
        return

    isbn = clean_text(product.get("isbn") or product.get("ean") or "")
    if isbn:
        cand.isbn = isbn.replace("-", "")
    release = _iso_date(product.get("date_parution") or "")
    if release:
        cand.release_date = release
    author = _first(product.get("auteur"))
    if author:
        cand.author = author
    image = _first(product.get("url_img_big")) or _first(product.get("url_img_h_345"))
    if image:
        cand.image_url = image

    # `description` e `info_sup` vienen con HTML; `info_sup` es el que enumera
    # el CONTENIDO de la caja (ex-libris, poster, fourreau…), que es
    # exactamente la señal de edición especial que busca el scoring.
    parts = []
    for field in ("description", "info_sup"):
        raw = product.get(field) or ""
        text = clean_text(re.sub(r"<[^>]+>", " ", raw))
        if text:
            parts.append(text)
    if parts:
        cand.description = clean_text(" · ".join([cand.description or ""] + parts))[:1200]
    score_candidate(cand)


def bootstrap(
    year_from: int,      # noqa: ARG001
    month_from: int,     # noqa: ARG001
    year_to: int,        # noqa: ARG001
    month_to: int,       # noqa: ARG001
    session: requests.Session,
    sleep_seconds: float = 0.3,
    timeout: tuple[int, int] = (15, 45),
    min_score: int = 0,
    fetch_details: bool = True,
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Recorre el catálogo por API y emite las ediciones especiales.

    El API no expone fecha de publicación por producto, así que NO hay modo
    delta real: siempre se recorre el catálogo completo (168 licencias). Es
    barato — 1 request de listado + 1 por licencia — y el dedup por
    `cluster_key` del pipeline absorbe lo ya conocido.
    """
    licences = fetch_licences(session, timeout=timeout)
    print(f"[meian] {len(licences)} licencias en el catálogo")
    if not licences:
        print("[meian] catálogo vacío — ¿cambió el header Origin o la ruta del API?")
        return []

    candidates: list[Candidate] = []
    seen_urls: set[str] = set()
    pending_flush: list[Candidate] = []

    for index, licence in enumerate(licences, 1):
        products = fetch_products(session, licence.get("id"), timeout=timeout)
        for product in products:
            cand = parse_product(product, licence)
            if cand is None:
                continue
            if cand.url in seen_urls:
                continue
            if min_score and (cand.score or 0) < min_score:
                continue
            seen_urls.add(cand.url)
            if fetch_details:
                enrich_candidate(session, cand, product.get("ref"), timeout=timeout)
            candidates.append(cand)
            pending_flush.append(cand)
        if flush_fn and pending_flush:
            flush_fn(pending_flush)
            pending_flush = []
        if index % 25 == 0:
            print(f"[meian] {index}/{len(licences)} licencias — "
                  f"{len(candidates)} ediciones especiales")
        if sleep_seconds:
            time.sleep(sleep_seconds)

    if flush_fn and pending_flush:
        flush_fn(pending_flush)
    print(f"[meian] terminado: {len(candidates)} ediciones especiales")
    return candidates


def iter_year_months(
    year_from: int, month_from: int,
    year_to: int, month_to: int,    # noqa: ARG001
) -> list[tuple[int, int]]:
    """El API no particiona por fecha; un único batch."""
    return [(year_from, month_from)]
