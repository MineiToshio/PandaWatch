"""shopify_variants.py — parser genérico de variants Shopify.

Muchos sitios Shopify (Dark Horse Direct, etc.) modelan una "serie de
tomos" como UN solo producto con N `variants` — un dropdown "Volume 1 /
Volume 2 / Volume 3" donde cada variant es un SKU real con su propio
precio, stock e ID. Para nuestro catálogo (que es por tomo) eso es
estructuralmente equivalente a la URL `/ediciones/` de Whakoom: hay
que expandir el producto-padre en N items, uno por variant.

Este módulo provee:
- `extract_shopify_variants(html)` → lista de dicts con `{id, title, sku, price}`.
- `is_volume_variants(variants)` → heurística que decide si los variants
  representan tomos de una serie (vs. talles, colores u otros opciones
  no relacionadas con volumen).
- `build_variant_url(parent_url, variant_id)` → URL deep-linkeada
  (`?variant=<id>`) para un variant dado. La expansión completa
  (producto-padre → N Candidates) vive en
  `scripts/retrofit/expand_index_pages.py::expand_shopify_variants_item`
  (hallazgo #7, 2026-07-08: este módulo antes documentaba una función
  `expand_shopify_variant_page` que nunca existió acá — quedó como
  aspiracional de una refactor que no se completó).

Diseño:
- Shopify embebe los variants en JSON dentro del HTML, normalmente en
  un script tipo `var meta = {"product": {"variants": [...]}}` o en
  `window.ShopifyAnalytics.meta.product.variants`. Hay variaciones por
  theme, así que el parser busca múltiples patrones, en orden de
  anclaje (hallazgo #11, 2026-07-08 — ver `extract_shopify_variants`).
- Fallback al `<select>` del formulario de "Add to Cart" cuando no
  encontramos JSON.
- Detección de "variants de tomo" requiere palabras clave en el
  `public_title`: "Volume", "Vol", "Tome", "Tomo", "Tankōbon", "巻", etc.
  Si no hay match, asumimos que son variants de otra cosa (color, talle)
  y NO expandimos.
"""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup


# Variants JSON suele estar embebido en uno de estos patrones, en orden de
# anclaje AL PRODUCTO ACTUAL (hallazgo #11, 2026-07-08 — antes se tomaba el
# PRIMER `"variants":` del documento sin más criterio, riesgo teórico si un
# theme serializa un widget de "productos relacionados"/recomendaciones ANTES
# que el bloque del producto principal en el HTML):
#
#   1. `"product":{...,"variants":[...]}` — el patrón real verificado (Dark
#      Horse Direct: `var meta = {"product": {"variants": [...]}, "page": {...}}`,
#      equivalente a `window.ShopifyAnalytics.meta.product.variants`).
#      `_PRODUCT_SCOPED_VARIANTS_PATTERN` exige que "variants" esté DENTRO
#      del mismo objeto "product" — sin otro `{`/`}` de por medio — así que
#      no puede "saltar" al variants de un objeto ajeno más adelante/atrás.
#   2. `"variants":[...]` suelto — fallback SIN anclaje garantizado. No se ha
#      visto un caso real en el corpus donde esto matchee lo incorrecto (los
#      themes Shopify auditados siempre traen el bloque del producto primero
#      o exclusivamente), pero queda documentado como el hueco conocido: un
#      theme que serialice un widget ajeno con su propio "variants" ANTES del
#      producto principal le ganaría a este patrón.
#   3. `variants = [...]` (asignación JS) — patrón legacy de themes viejos.
_PRODUCT_SCOPED_VARIANTS_PATTERN = re.compile(
    r'"product"\s*:\s*\{(?:(?![{}]).)*?"variants"\s*:\s*(\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\])',
    re.DOTALL,
)
_VARIANTS_JSON_PATTERNS: tuple[re.Pattern[str], ...] = (
    _PRODUCT_SCOPED_VARIANTS_PATTERN,
    re.compile(r'"variants"\s*:\s*(\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\])'),
    re.compile(r'variants\s*=\s*(\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\])\s*;'),
)


# Palabras que indican "variant por volumen" (no por color/talle).
# Cada subpatrón maneja su propio borde de palabra: `\b` para los que
# arrancan con letra, sin `\b` para los que arrancan con `#` o caracteres
# no-word (donde `\b` no matchearía al inicio del título).
_VOLUME_VARIANT_WORDS = re.compile(
    r'('
    r'\bvol(?:ume|umen)?\.?\s*\d+|'
    r'\bvolume\s+[ivxlc]+\b|'                  # Volume I, Volume II
    r'\btome\s*\d+|'
    r'\btomo\s*\d+|'
    r'\bbook\s*\d+|'
    r'\blibro\s*\d+|'
    r'\blibro\s*[ivxlc]+\b|'
    r'\bpart\s*\d+|'
    r'\bparte\s*\d+|'
    r'#\s*\d+|'
    r'\b\d+(?:st|nd|rd|th)?\s+volume\b|'
    r'第\s*\d+\s*巻|'                          # JP "第N巻"
    r'\bn[º°]\s*\d+'                           # nº 1, n° 1
    r')',
    re.IGNORECASE,
)


def _normalize_raw_variants(raw: list) -> list[dict]:
    """Filtra entries vacías/sin id y normaliza al schema de salida."""
    variants = []
    for v in raw:
        if not isinstance(v, dict):
            continue
        vid = v.get("id")
        if vid is None:
            continue
        variants.append({
            "id": str(vid),
            "title": (v.get("public_title") or v.get("title") or "").strip(),
            "name": (v.get("name") or "").strip(),
            "sku": (v.get("sku") or "").strip(),
            "price": v.get("price"),     # cents (int) o string
            "available": v.get("available"),
        })
    return variants


def extract_shopify_variants(html_text: str) -> list[dict]:
    """Extrae variants de un HTML Shopify.

    Devuelve `[{id, title, sku, price, available}, ...]`. Campos vacíos
    cuando el HTML no los expone. Devuelve `[]` si no se encuentran
    variants o si la página parece tener un solo variant trivial (lo
    que indica "producto sin variants reales", típico de items
    individuales que no son multi-tomo).
    """
    if not html_text:
        return []

    # Estrategia 1: JSON embebido, probando los patrones en orden de anclaje
    # (ver comentario de _VARIANTS_JSON_PATTERNS arriba, hallazgo #11).
    for pat in _VARIANTS_JSON_PATTERNS:
        m = pat.search(html_text)
        if not m:
            continue
        try:
            raw = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, list) or not raw:
            continue
        variants = _normalize_raw_variants(raw)
        if variants:
            return variants

    # Estrategia 2: `<select>` con `<option data-variant-id=...>`.
    soup = BeautifulSoup(html_text, "html.parser")
    variants = []
    for sel in soup.find_all("select"):
        opts = sel.find_all("option")
        # Buscar el select que tiene `data-variant-id` en sus options.
        if not any(o.get("data-variant-id") for o in opts):
            continue
        for o in opts:
            vid = o.get("data-variant-id") or ""
            if not vid:
                continue
            title = o.get_text(" ", strip=True)
            variants.append({
                "id": str(vid),
                "title": title,
                "name": title,
                "sku": "",
                "price": None,
                "available": None,
            })
        if variants:
            return variants
    return []


def is_volume_variants(variants: list[dict]) -> bool:
    """Heurística: ¿estos variants representan tomos (vs talles/colores)?

    Si AL MENOS UN variant tiene un patrón de volumen claro
    ("Volume 1", "Tome 3", "巻", "Vol. 2", etc.) en su title, asumimos
    que toda la serie son variants-por-volumen. Esto evita expandir
    erróneamente productos con variants por color o talle.

    Un single-variant ("Default Title", "Default") NO es multi-tomo;
    devolvemos False en ese caso.
    """
    if len(variants) < 2:
        return False
    titles = [v.get("title", "") for v in variants if v.get("title")]
    if not titles:
        return False
    # "Default Title" es el variant placeholder de Shopify cuando un
    # producto NO tiene variants reales.
    if all(t.lower() in ("default title", "default", "") for t in titles):
        return False
    # Al menos un variant con keyword de volumen.
    return any(_VOLUME_VARIANT_WORDS.search(t) for t in titles)


def build_variant_url(parent_url: str, variant_id: str) -> str:
    """Construye la URL deep-linkeada al variant: `<base>?variant=<id>`.

    Preserva el path y query existente, agregando/reemplazando solo el
    parámetro `variant=`. URLs Shopify típicas usan `?variant=12345`.
    """
    from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse
    p = urlparse(parent_url)
    qs = dict(parse_qsl(p.query, keep_blank_values=True))
    qs["variant"] = str(variant_id)
    # Limpiamos parámetros de tracking típicos (Shopify pos/sid/ss) que
    # ensucian la URL canónica.
    for trash in ("_pos", "_sid", "_ss"):
        qs.pop(trash, None)
    new_query = urlencode(qs)
    return urlunparse((p.scheme, p.netloc, p.path, p.params, new_query, ""))
