#!/usr/bin/env python3
"""fix_product_types.py — re-deriva `product_type` fuera del enum en items.jsonl.

La invariante WARN `PTYPE_ENUM` de `scripts/validate_corpus.py` detecta items
cuyo `product_type` no pertenece al enum de `derive_product_type()` (manga /
artbook / fanbook / guidebook / boxset / novel / magazine / audiobook). Hoy
son 105 filas con un edition-kind (`special`/`deluxe`/`variant`…) que la
estandarización VIEJA escribió en `product_type` en vez de en `edition_key`
(gotcha: el LLM del skill /watch-standardize-catalog ya NO hace esto desde
que `standardize_apply.py` valida contra `VALID_PRODUCT_TYPES` — ver
"El LLM propone, el determinismo dispone" en docs/reference/conventions.md).

Re-deriva con `manga_watch.derive_product_type(title, description,
signal_types)` (fuente única, NUNCA reimplementada); si el resultado también
cae fuera del enum (no debería pasar — es la misma función que define el
enum), cae a "manga" (el producto es casi siempre un tomo).

Uso:
    python scripts/retrofit/fix_product_types.py --dry-run
    python scripts/retrofit/fix_product_types.py
    python scripts/retrofit/fix_product_types.py --include-approved
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import backup_and_rotate, derive_product_type, is_approved  # type: ignore

# Mismo enum que valida `standardize_apply.VALID_PRODUCT_TYPES` y que
# documenta la invariante PTYPE_ENUM de validate_corpus.py — fuente única
# real es `derive_product_type()`; este set solo sirve para el chequeo
# defensivo post-derivación (nunca debería dispararse).
_PTYPE_ENUM = frozenset({
    "manga", "artbook", "fanbook", "guidebook", "boxset", "novel", "magazine",
    "audiobook",
})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/items.jsonl")
    parser.add_argument("--output", default="data/items.jsonl")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe el archivo; solo cuenta cuántos se arreglarían.")
    parser.add_argument("--include-approved", action="store_true",
                        help="Procesar también items aprobados (golden records). Por "
                             "defecto se saltean para no pisar metadata aprobada.")
    args = parser.parse_args()

    src = Path(args.input)
    dst = Path(args.output)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    lines = src.read_text(encoding="utf-8").splitlines()
    out_lines: list[str] = []
    changed = 0
    skipped_approved = 0
    approved_unfixed: list[str] = []  # slugs/urls de aprobados que quedan fuera del enum
    fallback_manga = 0
    still_invalid: Counter[str] = Counter()  # no debería ocurrir; reportado si pasa
    sample_changes: list[tuple[str, str, str]] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            out_lines.append(line)
            continue

        ptype = (item.get("product_type") or "").strip()
        needs_fix = bool(ptype) and ptype not in _PTYPE_ENUM

        if needs_fix and is_approved(item) and not args.include_approved:
            skipped_approved += 1
            approved_unfixed.append(item.get("slug") or item.get("url", "")[:60])
            out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            continue

        if needs_fix:
            new = derive_product_type(
                item.get("title", ""),
                item.get("description", ""),
                item.get("signal_types") or [],
            )
            if new not in _PTYPE_ENUM:
                still_invalid[new or "(vacío)"] += 1
                new = "manga"
                fallback_manga += 1
            changed += 1
            if len(sample_changes) < 10:
                sample_changes.append((item.get("slug") or item.get("url", "")[:60], ptype, new))
            item["product_type"] = new

        out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))

    print(f"[INFO] {len(lines)} líneas totales, {changed} product_type se re-derivarían.")
    if skipped_approved:
        print(f"[INFO] {skipped_approved} aprobados saltados fuera del enum "
              f"(usa --include-approved para incluirlos):")
        for s in approved_unfixed[:10]:
            print(f"  - {s}")
        if len(approved_unfixed) > 10:
            print(f"  ... y {len(approved_unfixed) - 10} más")
    if fallback_manga:
        print(f"[INFO] {fallback_manga} cayeron a fallback 'manga' (derive_product_type "
              f"devolvió algo fuera del enum — no debería pasar).")
        for val, cnt in still_invalid.most_common():
            print(f"  {val!r} ×{cnt}")
    if sample_changes:
        print("\nMuestra de cambios:")
        for slug, old, new in sample_changes:
            print(f"  {slug}: {old!r} → {new!r}")

    if args.dry_run:
        print("\n[DRY-RUN] No se escribió ningún archivo.")
        return 0

    if changed == 0:
        print("[OK] Nada que arreglar.")
        return 0

    if dst.exists():
        backup = backup_and_rotate(dst, "ptype")
        print(f"[OK] Backup guardado en {backup}")

    dst.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"[OK] Escribí {dst} con {changed} product_type re-derivados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
