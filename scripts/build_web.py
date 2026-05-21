#!/usr/bin/env python3
"""build_web.py — embebe data/items.jsonl dentro de web/index.html.

Lee data/items.jsonl, deduplica por url (queda la entrada más reciente),
y reemplaza el contenido del <script id="manga-data"> en web/index.html
con un array JSON inline. Después de correrlo, podés abrir
web/index.html directamente con doble-click sin necesidad de servidor.

Uso:
    python scripts/build_web.py
    python scripts/build_web.py --input data/items.jsonl --output web/index.html
    python scripts/build_web.py --clear   # vacía la data embebida
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SCRIPT_TAG_REGEX = re.compile(
    r'(<script id="manga-data" type="application/json">).*?(</script>)',
    re.DOTALL,
)


def load_items(path: Path) -> list[dict]:
    if not path.exists():
        return []
    items: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"[WARN] línea inválida ignorada: {exc}", file=sys.stderr)
    return items


def dedupe_by_url(items: list[dict]) -> list[dict]:
    """Mantiene la entrada con mayor score por URL normalizada.

    Importa scripts.manga_watch.normalize_url_for_dedup para colapsar:
    - Params de tracking (Shopify _pos/_sid/_ss, UTM, etc.)
    - Shopify /collections/X/products/Y → /products/Y
    - Trailing slash, case del host

    Empate de score: usar el más reciente.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from manga_watch import normalize_url_for_dedup

    def pick(a, b):
        if a is None:
            return b
        if b is None:
            return a
        sa = a.get("score") or 0
        sb = b.get("score") or 0
        if sb > sa:
            return b
        if sb < sa:
            return a
        return b if (b.get("detected_at") or "") > (a.get("detected_at") or "") else a

    # Pase 1: por URL normalizada.
    by_url: dict[str, dict] = {}
    for item in items:
        url = item.get("url") or ""
        if not url:
            continue
        key = normalize_url_for_dedup(url)
        by_url[key] = pick(by_url.get(key), item)

    # Pase 2: agrupar por cluster_key (mismo libro en distintos retailers).
    # cluster_key es ISBN cuando existe; cuando no, una clave fuzzy
    # (idioma|serie|volumen|variantes|publisher). Preservamos los hits
    # como sources[] dentro del item canónico.
    return _group_by_cluster_key(list(by_url.values()), pick)


def _source_entry(item: dict) -> dict:
    """Subconjunto del item que tiene sentido por-source (cada tienda
    tiene su precio, URL, imagen, stock, etc.)."""
    return {
        "name":         item.get("source", ""),
        "source_class": item.get("source_class", ""),
        "country":      item.get("country", ""),
        "publisher":    item.get("publisher", ""),
        "language":     item.get("language", ""),
        "url":          item.get("url", ""),
        "price":        item.get("price", ""),
        "image_url":    item.get("image_url", ""),
        "stock_type":   item.get("stock_type", ""),
        "detected_at":  item.get("detected_at", ""),
        "release_date": item.get("release_date", ""),
        "score":        item.get("score", 0),
    }


def _merged_canonical(group: list[dict], pick) -> dict:
    """Combina N items con el mismo ISBN en una sola entrada.

    - El item con mayor score gana como base ("canonical")
    - Si al canónico le falta algún campo (cover, autor, precio, fecha,
      ISBN, descripción), se completa desde cualquier source del grupo
      que sí lo tenga (best-of merge).
    - sources[] preserva la entrada por-source (precio, URL, país, etc.).
    """
    canonical = group[0]
    for item in group[1:]:
        canonical = pick(canonical, item)
    merged = dict(canonical)
    completable = ("image_url", "author", "price", "release_date",
                   "description", "isbn", "publisher")
    for field in completable:
        if not merged.get(field):
            for item in group:
                if item.get(field):
                    merged[field] = item[field]
                    break
    # Score máximo del grupo (mejor representa el "interés combinado").
    merged["score"] = max((i.get("score") or 0) for i in group)
    # Lista de sources, ordenada: la canónica primero, después por país.
    sources = [_source_entry(i) for i in group]
    sources.sort(key=lambda s: (
        s["url"] != canonical.get("url", ""),  # canónica primero
        s.get("country", ""),
        s.get("name", ""),
    ))
    merged["sources"] = sources
    return merged


def _group_by_cluster_key(items: list[dict], pick) -> list[dict]:
    """Agrupa items con mismo cluster_key fusionándolos en uno solo.

    cluster_key viene precalculada en items.jsonl por candidate_to_json
    (manga_watch.derive_cluster_key). Fallback para items legacy sin la
    clave: ISBN si existe, sino URL (standalone). Claves "url:..." nunca
    se agrupan con nada porque cada item tiene URL única.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from manga_watch import derive_cluster_key

    groups: dict[str, list[dict]] = {}
    for item in items:
        key = item.get("cluster_key") or derive_cluster_key(item)
        groups.setdefault(key, []).append(item)

    final: list[dict] = []
    for key, group in groups.items():
        if len(group) == 1:
            merged = dict(group[0])
            merged["sources"] = [_source_entry(group[0])]
            final.append(merged)
        else:
            final.append(_merged_canonical(group, pick))
    return final


def inject(html: str, items: list[dict]) -> str:
    if not SCRIPT_TAG_REGEX.search(html):
        raise SystemExit(
            "No encuentro el tag <script id=\"manga-data\"> en el HTML. "
            "Asegurate de tener la versión del template que lo incluye."
        )
    payload = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    return SCRIPT_TAG_REGEX.sub(
        lambda m: f"{m.group(1)}{payload}{m.group(2)}",
        html,
        count=1,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/items.jsonl", help="JSONL fuente (default: data/items.jsonl)")
    parser.add_argument("--output", default="web/index.html", help="HTML target (default: web/index.html)")
    parser.add_argument("--clear", action="store_true", help="Vacía la data embebida (deja [] en el script)")
    args = parser.parse_args()

    output = Path(args.output)
    if not output.exists():
        print(f"[ERROR] no existe {output}", file=sys.stderr)
        return 1

    html = output.read_text(encoding="utf-8")

    if args.clear:
        new_html = inject(html, [])
        output.write_text(new_html, encoding="utf-8")
        print(f"[OK] data embebida limpiada en {output}")
        return 0

    input_path = Path(args.input)
    items = load_items(input_path)
    deduped = dedupe_by_url(items)

    if not items:
        print(f"[WARN] {input_path} está vacío o no existe. La página mostrará 'sin items'.")
    else:
        print(f"[INFO] {len(items)} líneas en {input_path}, {len(deduped)} items únicos tras dedup.")

    new_html = inject(html, deduped)
    output.write_text(new_html, encoding="utf-8")

    # Stats útiles
    if deduped:
        countries = {i.get("country") for i in deduped if i.get("country")}
        publishers = {i.get("publisher") for i in deduped if i.get("publisher")}
        with_image = sum(1 for i in deduped if i.get("image_url"))
        with_price = sum(1 for i in deduped if i.get("price"))
        print(f"[OK] embebidos {len(deduped)} items en {output}")
        print(f"     {len(countries)} países, {len(publishers)} editoriales")
        print(f"     {with_image} con imagen, {with_price} con precio")
        print(f"     Tamaño final del HTML: {output.stat().st_size // 1024} KB")
    print()
    print(f"Abrí ahora: file://{output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
