#!/usr/bin/env python3
"""clean_descriptions.py — strip prefijos de botón "leer más" de description y description_es.

Aplica `clean_description()` de manga_watch a los campos `description` y
`description_es` de todos los items en items.jsonl (gotcha #37).

Afecta principalmente items de "FR - Meian" donde el wrapper del card incluye
el CTA "EN SAVOIR PLUS" y el JSON-LD lo embebe en el campo description.

Uso:
    python scripts/retrofit/clean_descriptions.py --dry-run
    python scripts/retrofit/clean_descriptions.py
    python scripts/retrofit/clean_descriptions.py --input X --output Y
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import clean_description, backup_and_rotate, is_approved  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/items.jsonl")
    parser.add_argument("--output", default="data/items.jsonl")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe el archivo; solo muestra cuántos cambiarían.")
    parser.add_argument("--include-approved", action="store_true",
                        help="Procesar también items aprobados (golden records). "
                             "Por defecto se saltean para no pisar metadata aprobada.")
    args = parser.parse_args()

    src = Path(args.input)
    dst = Path(args.output)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    lines = src.read_text(encoding="utf-8").splitlines()
    cleaned_lines: list[str] = []
    changed = 0
    skipped_approved = 0
    sample_changes: list[tuple[str, str, str]] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            cleaned_lines.append(line)
            continue

        if is_approved(item) and not args.include_approved:
            skipped_approved += 1
            cleaned_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            continue

        item_changed = False

        for field in ("description", "description_es"):
            original = item.get(field, "")
            if not original:
                continue
            new = clean_description(original)
            if new != original:
                item_changed = True
                if len(sample_changes) < 8:
                    sample_changes.append((field, original[:100], new[:100]))
                item[field] = new

        if item_changed:
            changed += 1

        cleaned_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))

    print(f"[INFO] {len(lines)} líneas totales, {changed} items cambiarían.")
    if skipped_approved:
        print(f"[INFO] {skipped_approved} aprobados saltados (usa --include-approved para incluirlos)")
    if sample_changes:
        print("\nMuestra de cambios:")
        for field, old, new in sample_changes:
            print(f"  [{field}]")
            print(f"    ANTES: {old}")
            print(f"    DESPUÉS: {new}")

    if args.dry_run:
        print("\n[DRY-RUN] No se escribió nada.")
        return 0

    if not changed:
        print("[OK] Nada que limpiar.")
        return 0

    if dst.exists():
        backup = backup_and_rotate(dst, "clean-descriptions")
        print(f"[OK] Backup guardado en {backup}")

    tmp = dst.with_suffix(".jsonl.cleandesc-tmp")
    tmp.write_text("\n".join(cleaned_lines) + "\n", encoding="utf-8")
    tmp.replace(dst)
    print(f"[OK] Escrito {dst} ({len(cleaned_lines)} líneas, {changed} items modificados).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
