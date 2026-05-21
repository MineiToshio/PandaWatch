#!/usr/bin/env python3
"""filter_collectible.py — aplica el gate `is_collectible_edition` a items existentes.

El producto del proyecto son SOLO ediciones especiales, variantes, coleccionistas,
artbooks, fanbooks, magazines de serie y tomos con extras de primera edición.
Este script revisa items.jsonl y mueve los "tomos regulares sin nada especial"
a un archivo separado para revisión.

Uso:
    python scripts/retrofit/filter_collectible.py                   # ejecuta
    python scripts/retrofit/filter_collectible.py --dry-run         # solo cuenta
    python scripts/retrofit/filter_collectible.py --input X --kept-output Y --rejected-output Z

Por defecto:
    - keeps items en data/items.jsonl
    - rejected items en data/items.non_collectible.jsonl (para revisar)
    - backup en data/items.jsonl.pre-collectible-bak
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

from manga_watch import (  # type: ignore
    is_collectible_edition,
    derive_product_type,
    detect_signals,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/items.jsonl")
    parser.add_argument("--kept-output", default="data/items.jsonl")
    parser.add_argument("--rejected-output", default="data/items.non_collectible.jsonl")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe nada; solo reporta cuántos se filtrarían.")
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    lines = src.read_text(encoding="utf-8").splitlines()
    kept_lines: list[str] = []
    rejected_lines: list[str] = []
    reason_counter: Counter[str] = Counter()
    sample_rejected: list[tuple[str, str, str]] = []
    sample_kept: list[tuple[str, str, str]] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            kept_lines.append(line)
            continue
        title = item.get("title", "")
        description = item.get("description", "")
        tags = item.get("tags", []) or []
        # Re-computamos signal_types y product_type desde title+description
        # porque los valores persistidos en items.jsonl pueden venir de runs
        # previos con bugs de contaminación (source name → box_set, etc.).
        _, _, fresh_signal_types = detect_signals(f"{title}\n{description}")
        fresh_product_type = derive_product_type(title, description, fresh_signal_types)
        is_coll, reason = is_collectible_edition(
            title, description, fresh_signal_types, fresh_product_type,
            tags=tags, isbn=item.get("isbn", "") or "",
            url=item.get("url", "") or "",
        )
        if is_coll:
            kept_lines.append(line)
            # bucket = parte antes del primer ':'
            bucket = reason.split(":", 1)[0]
            if len(sample_kept) < 8:
                sample_kept.append((reason, title[:90], item.get("source", "")))
        else:
            rejected_lines.append(line)
            bucket = reason.split(":", 1)[0]
            reason_counter[bucket] += 1
            if len(sample_rejected) < 15:
                sample_rejected.append((reason, title[:90], item.get("source", "")))

    total = len(kept_lines) + len(rejected_lines)
    print(f"[INFO] {total} items totales")
    print(f"[INFO] {len(kept_lines)} coleccionables (kept)  {len(kept_lines)*100//max(total,1)}%")
    print(f"[INFO] {len(rejected_lines)} tomos regulares (rejected)  {len(rejected_lines)*100//max(total,1)}%")
    print(f"\nMotivos de descarte:")
    for bucket, n in reason_counter.most_common():
        print(f"  {bucket:25s}  {n}")

    if sample_kept:
        print(f"\nMuestra de KEPT (coleccionables):")
        for reason, title, source in sample_kept:
            print(f"  [{reason}]")
            print(f"    {title}")
            print(f"    ← {source}")

    if sample_rejected:
        print(f"\nMuestra de REJECTED (tomos regulares):")
        for reason, title, source in sample_rejected:
            print(f"  [{reason}]")
            print(f"    {title}")
            print(f"    ← {source}")

    if args.dry_run:
        print("\n[DRY-RUN] No se escribió ningún archivo.")
        return 0

    if not rejected_lines:
        print("\n[OK] Nada que filtrar.")
        return 0

    kept_path = Path(args.kept_output)
    rejected_path = Path(args.rejected_output)
    if kept_path.exists() and kept_path == src:
        backup = kept_path.with_suffix(kept_path.suffix + ".pre-collectible-bak")
        backup.write_text(kept_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"\n[OK] Backup guardado en {backup}")

    kept_path.write_text("\n".join(kept_lines) + "\n", encoding="utf-8")
    print(f"[OK] Escribí {kept_path} con {len(kept_lines)} coleccionables.")

    rejected_path.write_text("\n".join(rejected_lines) + "\n", encoding="utf-8")
    print(f"[OK] Escribí {rejected_path} con {len(rejected_lines)} no-coleccionables.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
