#!/usr/bin/env python3
"""normalize_isbn.py — normaliza y VALIDA el campo `isbn` de items.jsonl.

Aplica manga_watch.normalize_isbn() (fuente única) a cada item. Desde el
2026-07-08 (Fable) el normalizador es REAL: tokeniza el crudo (descartando
prefijos "： " fullwidth y sufijos como "Deluxe"), valida checksum ISBN-13
(prefijo GS1 978/979) e ISBN-10 (mod-11), y CONVIERTE los ISBN-10 válidos a
ISBN-13 (una sola forma canónica). Si ningún token valida, conserva el más
ISBN-like y loguea ISBN_ANOMALY (fail-safe, gotcha #108). Por eso el dry-run
ahora reporta también las conversiones 10→13, no sólo el strip de basura.

El scraper ya normaliza en cada ingreso nuevo (candidate_to_json +
fetch_metadata_from_detail); este retrofit limpia el corpus histórico.

Es compute-only (sin red) → un único write al final con backup (convención de
retrofits, docs/reference/conventions.md).

Uso:
    python scripts/retrofit/normalize_isbn.py --dry-run   # solo cuenta, no escribe
    python scripts/retrofit/normalize_isbn.py             # aplica con backup
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import normalize_isbn, backup_and_rotate, is_approved  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/items.jsonl")
    parser.add_argument("--output", default="data/items.jsonl")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe el archivo; solo cuenta cuántos ISBN cambiarían.")
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
    sample_changes: list[tuple[str, str]] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            out_lines.append(line)
            continue

        # Golden records: el owner aprobó esta card; no la re-tocamos por defecto.
        if is_approved(item) and not args.include_approved:
            skipped_approved += 1
            out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            continue

        original = item.get("isbn", "")
        if original:
            new = normalize_isbn(original, source=item.get("source", ""))
            if new != original:
                changed += 1
                if len(sample_changes) < 10:
                    sample_changes.append((original, new))
                item["isbn"] = new
        out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))

    print(f"[INFO] {len(lines)} líneas totales, {changed} ISBN cambiarían.")
    if skipped_approved:
        print(f"[INFO] {skipped_approved} aprobados saltados (usa --include-approved para incluirlos)")
    if sample_changes:
        print("\nMuestra de cambios:")
        for old, new in sample_changes:
            print(f"  ANTES: {old!r}")
            print(f"  AHORA: {new!r}")
            print()

    if args.dry_run:
        print("[DRY-RUN] No se escribió ningún archivo.")
        return 0

    if changed == 0:
        print("[OK] Nada que normalizar.")
        return 0

    if dst.exists():
        backup = backup_and_rotate(dst, "isbn")
        print(f"[OK] Backup guardado en {backup}")

    dst.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"[OK] Escribí {dst} con {changed} ISBN normalizados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
