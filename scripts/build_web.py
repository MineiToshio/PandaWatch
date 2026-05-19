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

    by_url: dict[str, dict] = {}
    for item in items:
        url = item.get("url") or ""
        if not url:
            continue
        key = normalize_url_for_dedup(url)
        existing = by_url.get(key)
        if existing is None:
            by_url[key] = item
            continue
        new_score = item.get("score") or 0
        old_score = existing.get("score") or 0
        if new_score > old_score:
            by_url[key] = item
        elif new_score == old_score and (item.get("detected_at") or "") > (existing.get("detected_at") or ""):
            by_url[key] = item
    return list(by_url.values())


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
