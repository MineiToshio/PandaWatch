#!/usr/bin/env python3
"""filter_non_manga.py — descarta items que no son mangas/artbooks/light novels.

Usa is_likely_manga() de manga_watch.py para clasificar los items existentes
en items.jsonl y mover los no-mangas a un archivo separado para revisión.

Uso:
    python scripts/filter_non_manga.py                    # ejecuta y escribe
    python scripts/filter_non_manga.py --dry-run          # solo cuenta
    python scripts/filter_non_manga.py --input X --kept-output Y --rejected-output Z

Por defecto:
    - keeps items en data/items.jsonl
    - rejected items en data/items.non_manga.jsonl (para revisar)
    - backup en data/items.jsonl.pre-filter-bak
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import is_likely_manga  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/items.jsonl")
    parser.add_argument("--kept-output", default="data/items.jsonl")
    parser.add_argument("--rejected-output", default="data/items.non_manga.jsonl")
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
        is_manga, reason = is_likely_manga(title, description)
        if is_manga:
            kept_lines.append(line)
        else:
            rejected_lines.append(line)
            # Tomamos el "bucket" del reason (ej. "non_manga_hard")
            bucket = reason.split(":", 1)[0]
            reason_counter[bucket] += 1
            if len(sample_rejected) < 15:
                sample_rejected.append((reason, title[:90], item.get("source", "")))

    total = len(kept_lines) + len(rejected_lines)
    print(f"[INFO] {total} items totales")
    print(f"[INFO] {len(kept_lines)} mangas (kept)")
    print(f"[INFO] {len(rejected_lines)} non-manga (rejected)")
    print(f"\nMotivos de descarte:")
    for bucket, n in reason_counter.most_common():
        print(f"  {bucket:25s}  {n}")

    if sample_rejected:
        print(f"\nMuestra de descartes:")
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

    # Backup defensivo del input
    kept_path = Path(args.kept_output)
    rejected_path = Path(args.rejected_output)
    if kept_path.exists() and kept_path == src:
        backup = kept_path.with_suffix(kept_path.suffix + ".pre-filter-bak")
        backup.write_text(kept_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"\n[OK] Backup guardado en {backup}")

    kept_path.write_text("\n".join(kept_lines) + "\n", encoding="utf-8")
    print(f"[OK] Escribí {kept_path} con {len(kept_lines)} mangas.")

    rejected_path.write_text("\n".join(rejected_lines) + "\n", encoding="utf-8")
    print(f"[OK] Escribí {rejected_path} con {len(rejected_lines)} non-manga (para revisión).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
