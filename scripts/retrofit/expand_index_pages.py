#!/usr/bin/env python3
"""expand_index_pages.py — limpia páginas-índice guardadas como productos.

Auditoría descubrió varias URLs en items.jsonl que NO son tomos individuales
sino páginas-índice / catálogo. Cada tipo necesita un tratamiento distinto:

1. **Whakoom `/publisher/<id>/`** — página del editor que lista sus
   ediciones. Se expande extrayendo `/ediciones/...` y luego cada una
   en sus tomos `/comics/...`.

2. **Shopify variants multi-tomo** (ej. Dark Horse Direct
   `products/berserk-deluxe-hardcover-volumes`) — un solo producto
   con un `<select>` de variants ("Volume 1 / 2 / 3"). Cada variant
   es un SKU. Se expande generando N items con URL `?variant=<id>`.

3. **Páginas `/blogs/news/` o `/blog/news/`** — anuncios editoriales,
   no productos. Se eliminan sin reemplazo (los productos mencionados
   aparecerán en su fuente regular cuando estén disponibles).

4. **Páginas `/collections/X` Shopify (sin /products/)** — catálogo
   completo. Se eliminan, y si vale la pena se agrega la fuente a
   `sources.yml` para que el scraper regular la procese (caso funside.it).

Uso:
    python scripts/retrofit/expand_index_pages.py --dry-run
    python scripts/retrofit/expand_index_pages.py            # aplica

Idempotente: si volvés a correrlo no toca filas ya limpias.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import (  # type: ignore
    Source,
    backup_and_rotate,
    candidate_from_source,
    candidate_to_json,
    is_approved,
    is_collectible_edition,
    is_likely_manga,
    normalize_url_for_dedup,
    score_candidate,
    write_lines_atomic,
)
import image_store  # type: ignore
from shopify_variants import (  # type: ignore
    build_variant_url,
    extract_shopify_variants,
    is_volume_variants,
)
from wikis.whakoom import (  # type: ignore
    WhakoomBlocked,
    _ua_session,
    expand_whakoom_publisher_url,
    fetch_url,
    is_whakoom_publisher_url,
)


# -----------------------------------------------------------------------------
# Clasificación de URLs
# -----------------------------------------------------------------------------

_BLOG_NEWS_RE = re.compile(
    r"/(blogs?/news/|/blog/news/|/news/[a-z0-9_-]+/|/noticias/[a-z0-9_-]+/)",
    re.IGNORECASE,
)
_SHOPIFY_COLLECTION_ONLY_RE = re.compile(
    r"^https?://[^/]+/collections/[^/?#]+/?(?:[?#]|$)",
    re.IGNORECASE,
)


def classify_url(url: str) -> str:
    """Devuelve la categoría de "índice" o "" si no lo es.

    Categorías:
    - "whakoom_publisher" — `/publisher/<id>/<slug>` en Whakoom.
    - "shopify_variants_candidate" — producto Shopify; hay que fetchear
       para confirmar si tiene variants multi-tomo.
    - "blog_news" — post de blog/news editorial.
    - "shopify_collection" — `/collections/X` sin `/products/Y` después.
    - "" — no es índice.
    """
    if not url:
        return ""
    if is_whakoom_publisher_url(url):
        return "whakoom_publisher"
    if _BLOG_NEWS_RE.search(url):
        return "blog_news"
    # Shopify variants candidate — chequeamos solo Dark Horse Direct ahora,
    # ya que el resto de Shopify-sources que tenemos no parecen modelar
    # series como variants (mangadreams.it, milkyway, etc. tienen 1 tomo
    # por URL).
    if "darkhorsedirect.com" in url and "/products/" in url:
        return "shopify_variants_candidate"
    # /collections/X sin /products/Y después
    if "/products/" not in url and _SHOPIFY_COLLECTION_ONLY_RE.match(url):
        return "shopify_collection"
    return ""


# -----------------------------------------------------------------------------
# Expanders
# -----------------------------------------------------------------------------


def _virtual_shopify_variant_source(parent_url: str, parent_item: dict) -> Source:
    """Construye un Source virtual para los items expandidos de Shopify variants.

    Hereda country/language/publisher del item padre cuando los tiene.
    """
    domain = urlparse(parent_url).netloc.replace("www.", "")
    return Source(
        name=f"Shopify variants ({domain})",
        country=parent_item.get("country", ""),
        language=parent_item.get("language", ""),
        publisher=parent_item.get("publisher", ""),
        source_class=parent_item.get("source_class", "trusted_media"),
        kind="html",
        url=parent_url,
        tags=parent_item.get("tags", []) + ["shopify-variant"],
        purity="mixed",
    )


def expand_shopify_variants_item(
    parent_item: dict,
    session: requests.Session,
    timeout: tuple[int, int],
) -> tuple[list, str]:
    """Expande un item Shopify multi-tomo en N candidates.

    Devuelve `(candidates, status)` donde status es:
    - "expanded"      — N candidates generados, parent se debe eliminar.
    - "no_variants"   — la página no tiene variants relevantes (single
                       product). Parent se mantiene como está.
    - "not_volumes"   — los variants existen pero no son por volumen
                       (probablemente color/talle). Parent se mantiene.
    - "fetch_error"   — fetch falló. Parent se mantiene.
    """
    parent_url = parent_item.get("url", "")
    if not parent_url:
        return [], "fetch_error"
    try:
        r = session.get(parent_url, timeout=timeout, allow_redirects=True)
    except requests.RequestException:
        return [], "fetch_error"
    if r.status_code != 200:
        return [], "fetch_error"
    if not r.encoding:
        r.encoding = r.apparent_encoding
    html = r.text
    variants = extract_shopify_variants(html)
    if len(variants) < 2:
        return [], "no_variants"
    if not is_volume_variants(variants):
        return [], "not_volumes"
    source = _virtual_shopify_variant_source(parent_url, parent_item)
    parent_title = parent_item.get("title", "")
    # Estética: el title del producto Shopify suele ser plural ("Volumes",
    # "Hardcovers"). Limpiamos para que el child quede como "Hellsing
    # Deluxe Hardcover - Volume 1" en lugar de "Hellsing Deluxe Hardcover
    # Volumes - Volume 1".
    base_title = re.sub(
        r"\s+(Volumes?|Hardcovers?|Books?|Sets?|Multi[-\s]Volume)\s*$",
        "",
        parent_title,
        flags=re.IGNORECASE,
    ).strip()
    candidates = []
    for v in variants:
        vid = v["id"]
        vtitle = v["title"] or v["name"] or f"Variant {vid}"
        full_title = f"{base_title} - {vtitle}" if base_title else vtitle
        url = build_variant_url(parent_url, vid)
        cand = candidate_from_source(
            source, full_title, url, parent_item.get("description", ""),
        )
        if v.get("sku"):
            cand.isbn = ""  # SKU != ISBN; lo dejamos vacío.
        # Image del padre: lo más probable es que sea la portada
        # representativa de la serie. Mejor que vacío. Portada = images[0].
        parent_cover = image_store.cover_url(parent_item)
        if parent_cover:
            cand.image_url = parent_cover
        candidates.append(cand)
    return candidates, "expanded"


# -----------------------------------------------------------------------------
# Main retrofit loop
# -----------------------------------------------------------------------------


def _load_items(path: Path) -> list[dict]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            items.append({"_raw": line})
    return items


def _write_items(path: Path, items: list[dict]) -> None:
    lines = [
        it["_raw"] if "_raw" in it else json.dumps(it, ensure_ascii=False)
        for it in items
    ]
    write_lines_atomic(path, lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="data/items.jsonl")
    ap.add_argument("--output", default="data/items.jsonl")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sleep", type=float, default=1.5)
    ap.add_argument("--timeout-connect", type=int, default=10)
    ap.add_argument("--timeout-read", type=int, default=30)
    args = ap.parse_args()

    # Ingesta real (descubre items/series nuevas): habilitar el logging de la
    # cola de unmapped, salvo en dry-run (Fable 2026-07-08, punto 5 — el efecto
    # está apagado por default en series_aliases).
    try:
        from series_aliases import set_unmapped_logging
        set_unmapped_logging(not args.dry_run)
    except ImportError:
        pass

    src = Path(args.input)
    out = Path(args.output)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    items = _load_items(src)
    print(f"[INFO] {len(items)} filas leídas de {src}")

    # Clasificar.
    buckets: dict[str, list[int]] = {
        "whakoom_publisher": [],
        "shopify_variants_candidate": [],
        "blog_news": [],
        "shopify_collection": [],
    }
    skipped_approved = 0
    for idx, it in enumerate(items):
        if "_raw" in it:
            continue
        # Golden records aprobados: NUNCA expandir ni eliminar. Sin este guard,
        # un parent aprobado se perdía al expandirlo (se borra + se reemplaza) o
        # al caer en blog_news/shopify_collection (se borra sin reemplazo).
        if is_approved(it):
            skipped_approved += 1
            continue
        category = classify_url(it.get("url", ""))
        if category in buckets:
            buckets[category].append(idx)

    print()
    if skipped_approved:
        print(f"[INFO] {skipped_approved} items aprobados saltados (no se tocan)")
    print(f"### Clasificación de items sospechosos:")
    for cat, idxs in buckets.items():
        print(f"  {cat:35s} {len(idxs)} items")

    known_urls: set[str] = set()
    for it in items:
        if "_raw" in it:
            continue
        u = it.get("url", "")
        if u:
            known_urls.add(normalize_url_for_dedup(u))

    session = _ua_session(requests.Session())
    timeout = (args.timeout_connect, args.timeout_read)

    to_remove: set[int] = set()
    new_rows: list[dict] = []
    stats = {
        "whakoom_publisher_expanded": 0,
        "whakoom_publisher_failed": 0,
        "shopify_variants_expanded": 0,
        "shopify_variants_skipped": 0,
        "shopify_variants_failed": 0,
        "blog_news_removed": 0,
        "shopify_collection_removed": 0,
        "tomos_nuevos": 0,
        "duplicates": 0,
    }
    aborted = False

    def _filter_and_keep(cand) -> dict | None:
        """Aplica los mismos filtros que la ingestión normal."""
        is_m, _ = is_likely_manga(
            cand.title, cand.description, tags=cand.tags,
            source_purity="mixed", publisher=cand.publisher,
            url=cand.url,
        )
        if not is_m:
            return None
        score_candidate(cand)
        is_c, _ = is_collectible_edition(
            cand.title, cand.description, cand.signal_types, cand.product_type,
            tags=cand.tags, isbn=cand.isbn, url=cand.url,
        )
        if not is_c:
            return None
        norm = normalize_url_for_dedup(cand.url)
        if norm in known_urls:
            stats["duplicates"] += 1
            return None
        known_urls.add(norm)
        return candidate_to_json(cand)

    # ---- 1) Whakoom /publisher/
    for idx in buckets["whakoom_publisher"]:
        it = items[idx]
        url = it.get("url", "")
        print(f"\n[whakoom_publisher] {url}")
        try:
            expanded = expand_whakoom_publisher_url(
                url, session, timeout=timeout, sleep_seconds=args.sleep,
            )
        except WhakoomBlocked as exc:
            print(f"   [BLOCKED] {exc}")
            aborted = True
            break
        if not expanded:
            print(f"   [WARN] 0 tomos descubiertos")
            stats["whakoom_publisher_failed"] += 1
            continue
        kept = [_filter_and_keep(c) for c in expanded]
        kept = [k for k in kept if k]
        print(f"   → {len(expanded)} expandidos / {len(kept)} sobreviven filtros")
        if expanded:
            stats["whakoom_publisher_expanded"] += 1
            stats["tomos_nuevos"] += len(kept)
            new_rows.extend(kept)
            to_remove.add(idx)
        if args.sleep > 0:
            time.sleep(args.sleep)

    # ---- 2) Shopify variants
    if not aborted:
        for idx in buckets["shopify_variants_candidate"]:
            it = items[idx]
            url = it.get("url", "")
            print(f"\n[shopify_variants] {url}")
            cands, status = expand_shopify_variants_item(it, session, timeout)
            if status == "expanded":
                kept = [_filter_and_keep(c) for c in cands]
                kept = [k for k in kept if k]
                print(f"   → {len(cands)} variants / {len(kept)} sobreviven filtros")
                stats["shopify_variants_expanded"] += 1
                stats["tomos_nuevos"] += len(kept)
                new_rows.extend(kept)
                to_remove.add(idx)
            elif status in ("no_variants", "not_volumes"):
                print(f"   [skip] {status} — fila padre intacta (es un single-product)")
                stats["shopify_variants_skipped"] += 1
            else:
                print(f"   [fail] {status}")
                stats["shopify_variants_failed"] += 1
            if args.sleep > 0:
                time.sleep(args.sleep)

    # ---- 3) Blog/news posts — eliminar sin reemplazo
    if not aborted:
        for idx in buckets["blog_news"]:
            it = items[idx]
            print(f"\n[blog_news] eliminando: {it.get('title','')[:60]}")
            print(f"   {it.get('url','')}")
            to_remove.add(idx)
            stats["blog_news_removed"] += 1

    # ---- 4) Shopify collections /collections/X (sin /products/) — eliminar
    if not aborted:
        for idx in buckets["shopify_collection"]:
            it = items[idx]
            print(f"\n[shopify_collection] eliminando: {it.get('title','')[:60]}")
            print(f"   {it.get('url','')}")
            to_remove.add(idx)
            stats["shopify_collection_removed"] += 1

    print("\n" + "=" * 60)
    for k, v in stats.items():
        print(f"  {k:35s} {v}")
    print(f"  filas a eliminar: {len(to_remove)}")
    print(f"  filas nuevas a agregar: {len(new_rows)}")

    if args.dry_run or aborted:
        if aborted:
            print(f"\n[ABORT] No se escribió {out} (Cloudflare).")
        else:
            print(f"\n[DRY-RUN] No se escribió {out}. Quitá --dry-run para aplicar.")
        return 0

    if out.exists():
        backup_and_rotate(out, "expand-index")
    final = [it for i, it in enumerate(items) if i not in to_remove]
    final.extend(new_rows)
    _write_items(out, final)
    print(f"\n[OK] {out} actualizado:")
    print(f"     filas antes: {len(items)}")
    print(f"     filas después: {len(final)}")
    print(f"     delta: {len(final) - len(items):+d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
