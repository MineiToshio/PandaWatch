#!/usr/bin/env python3
"""backfill_cluster_key.py — añade cluster_key a items.jsonl existentes.

Sprint 3.8: introdujimos `cluster_key` para agrupar items que representan
el mismo producto físico (ISBN compartido, o fuzzy match
lang+serie+vol+variantes+publisher). El scraper la calcula desde ahora,
pero las ~3000 entradas históricas no la tienen. Este script las rellena.

Uso:
    python scripts/retrofit/backfill_cluster_key.py            # full
    python scripts/retrofit/backfill_cluster_key.py --dry-run  # solo cuenta
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import (  # type: ignore
    derive_cluster_key, backup_and_rotate, write_lines_atomic,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", default="data/items.jsonl")
    p.add_argument("--output", default="data/items.jsonl")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    items: list[dict] = []
    raws: list[str] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
            raws.append("")
        except json.JSONDecodeError:
            items.append({"_raw": line})
            raws.append(line)

    print(f"[INFO] {len(items)} items en {src}")

    added = 0
    refreshed = 0
    kind_counter: Counter[str] = Counter()
    for it in items:
        if "_raw" in it:
            continue
        prev = it.get("cluster_key", "")
        new = derive_cluster_key(it)
        if new != prev:
            if prev:
                refreshed += 1
            else:
                added += 1
            it["cluster_key"] = new
        # estadística por tipo de clave
        kind = new.split(":", 1)[0] if ":" in new else "other"
        kind_counter[kind] += 1

    print(f"[INFO] cluster_key añadidas: {added}, refrescadas: {refreshed}")
    print(f"[INFO] Distribución de cluster_key por tipo:")
    for kind, n in kind_counter.most_common():
        print(f"  {kind:8s}: {n}")

    # Cuántos grupos > 1 produciría
    keys_seen: Counter[str] = Counter()
    for it in items:
        if "_raw" not in it:
            keys_seen[it.get("cluster_key", "")] += 1
    grouped = {k: n for k, n in keys_seen.items() if n > 1}
    if grouped:
        merged_items = sum(grouped.values())
        print(f"[INFO] Items que se consolidarán: {merged_items} en {len(grouped)} grupos "
              f"(ahorro: {merged_items - len(grouped)} cards en el dashboard)")
        # top 10 grupos más grandes
        top = sorted(grouped.items(), key=lambda x: -x[1])[:10]
        print(f"[INFO] Top 10 grupos más grandes:")
        for k, n in top:
            print(f"  [{n}] {k[:100]}")

    if args.dry_run:
        print("[DRY-RUN] No se escribió.")
        return 0

    dst = Path(args.output)
    if dst == src and src.exists():
        backup = backup_and_rotate(src, "cluster")
        print(f"[OK] Backup: {backup}")

    out_lines: list[str] = []
    for it, raw in zip(items, raws):
        if "_raw" in it:
            out_lines.append(raw)
        else:
            out_lines.append(json.dumps(it, ensure_ascii=False, sort_keys=True))
    write_lines_atomic(dst, out_lines)
    print(f"[OK] Escrito {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
