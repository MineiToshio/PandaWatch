#!/usr/bin/env python3
"""build_web.py — refresca el índice de aliases y (opcional) embebe el catálogo.

Por DEFECTO **ya no embebe** el catálogo en web/index.html: deja el
<script id="manga-data"> vacío. El dashboard servido por serve.py usa el
fetch EN VIVO de data/items.jsonl (decisión #5), así que el embed sólo servía
de fallback para abrir el HTML con doble-click (file://) — y costaba ~30 MB
en una sola línea, que el navegador descargaba y parseaba en cada carga ADEMÁS
del fetch en vivo (trabajo doble). Con el embed vacío, index.html pesa ~130 KB.

Lo que SIEMPRE hace: exporta data/series_aliases.json (índice de búsqueda
multilingüe que consumen el dashboard y web-next).

Con --embed: además embebe data/items.jsonl (modelo 1-fila-por-producto con
sources[], agrupado por cluster_key vía manga_watch.consolidate_by_cluster) en
el <script id="manga-data">, para poder abrir web/index.html con doble-click
sin servidor. Más pesado; usar sólo si necesitás el fallback file://.

Uso:
    python scripts/build_web.py            # embed vacío + aliases (default)
    python scripts/build_web.py --embed    # + catálogo embebido (fallback file://)
    python scripts/build_web.py --clear     # sólo vacía el embed (sin tocar aliases)
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


def _mw():
    """Importa las primitivas de merge de manga_watch (fuente única de verdad).

    Standalone: `import manga_watch` (scripts/ en el path) trae el módulo
    completo. Bajo pytest, ese nombre resuelve al wrapper raíz (solo expone
    parse_args/run); en ese caso caemos a `scripts.manga_watch`.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import manga_watch as mw
    except ImportError:  # pragma: no cover
        from scripts import manga_watch as mw
    if not hasattr(mw, "merge_cluster"):  # wrapper raíz bajo pytest
        from scripts import manga_watch as mw
    return mw


def _source_entry(item: dict) -> dict:
    """Subconjunto por-source. Delega en manga_watch.source_entry (única impl.)."""
    return _mw().source_entry(item)


def _merged_canonical(group: list[dict], pick=None) -> dict:
    """Combina N items del mismo producto en uno con sources[].

    Delega en manga_watch.merge_cluster — la ÚNICA implementación del merge
    (la divergencia entre sitios de merge causó los bugs de fotos de
    2026-06-02). `pick` se ignora: merge_cluster elige la canónica internamente
    (aprobada > estandarizada > ISBN > imagen > precio).
    """
    return _mw().merge_cluster(group)


def _group_by_cluster_key(items: list[dict], pick=None) -> list[dict]:
    """Agrupa por cluster_key → 1 fila por producto con sources[].

    Delega en manga_watch.consolidate_by_cluster (única impl.).
    """
    return _mw().consolidate_by_cluster(items)


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
    parser.add_argument("--embed", action="store_true",
                        help="Embebe el catálogo completo en el HTML (fallback file://). "
                             "Por defecto el embed queda vacío y la página usa el fetch en vivo.")
    parser.add_argument("--clear", action="store_true",
                        help="Sólo vacía el embed (deja [] en el script) sin tocar los aliases.")
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

    # Vista de búsqueda de aliases (data/series_aliases.json) — la consumen
    # el dashboard y web-next para que la búsqueda resuelva nombres
    # multilingües de serie (el title es el nombre oficial, no se renombra).
    # SIEMPRE se exporta (con o sin --embed).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from export_series_aliases import export as export_aliases
    n_aliases = export_aliases()
    print(f"[INFO] {n_aliases} series en data/series_aliases.json")

    if not args.embed:
        # Default: embed vacío. La página usa el fetch en vivo de items.jsonl
        # (decisión #5); el HTML queda en ~130 KB en vez de ~30 MB.
        new_html = inject(html, [])
        output.write_text(new_html, encoding="utf-8")
        print(f"[OK] embed vacío en {output} (~{output.stat().st_size // 1024} KB). "
              f"La página usa el fetch en vivo de data/items.jsonl.")
        print("     Para embeber el catálogo (fallback file://) corré con --embed.")
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
        with_image = sum(1 for i in deduped if i.get("images"))
        print(f"[OK] embebidos {len(deduped)} items en {output}")
        print(f"     {len(countries)} países, {len(publishers)} editoriales")
        print(f"     {with_image} con imagen")
        print(f"     Tamaño final del HTML: {output.stat().st_size // 1024} KB")
    print()
    print(f"Abrí ahora: file://{output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
