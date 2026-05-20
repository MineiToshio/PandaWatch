#!/usr/bin/env python3
"""clean_titles.py — aplica clean_title() a items existentes en items.jsonl.

Útil después de mejorar la lógica de limpieza para retroactivamente arreglar
títulos guardados con basura de e-commerce.

Uso:
    python scripts/clean_titles.py
    python scripts/clean_titles.py --dry-run        # solo cuenta, no escribe
    python scripts/clean_titles.py --input X --output Y
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import clean_title  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/items.jsonl")
    parser.add_argument("--output", default="data/items.jsonl")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe el archivo; solo cuenta cuántos se limpiarían.")
    args = parser.parse_args()

    src = Path(args.input)
    dst = Path(args.output)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    lines = src.read_text(encoding="utf-8").splitlines()
    cleaned_lines: list[str] = []
    changed = 0
    sample_changes: list[tuple[str, str]] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            cleaned_lines.append(line)
            continue
        original = item.get("title", "")
        new = clean_title(original)
        if new != original:
            changed += 1
            if len(sample_changes) < 8:
                sample_changes.append((original[:80], new[:80]))
            item["title"] = new
        cleaned_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))

    print(f"[INFO] {len(lines)} líneas totales, {changed} títulos cambiarían.")
    if sample_changes:
        print("\nMuestra de cambios:")
        for old, new in sample_changes:
            print(f"  ANTES: {old}")
            print(f"  AHORA: {new}")
            print()

    if args.dry_run:
        print("[DRY-RUN] No se escribió ningún archivo.")
        return 0

    if changed == 0:
        print("[OK] Nada que limpiar.")
        return 0

    # Backup defensivo
    backup = dst.with_suffix(dst.suffix + ".pre-clean-bak")
    if dst.exists():
        backup.write_text(dst.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"[OK] Backup guardado en {backup}")

    dst.write_text("\n".join(cleaned_lines) + "\n", encoding="utf-8")
    print(f"[OK] Escribí {dst} con {changed} títulos limpiados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
