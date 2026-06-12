#!/usr/bin/env python3
"""normalize_release_dates.py — normaliza release_date legacy a ISO en items.jsonl.

El corpus arrastraba fechas en formato crudo de fuente (DD/MM/YYYY de fuentes
EU, "2023/09/27 10:00:00" de JSON-LD de tiendas JP, 年月日, mes textual FR…)
porque los extractores guardaban el match sin normalizar (gotcha #80, ya
arreglado upstream en normalize_release_date / extract_release_date).

Por defecto convierte SOLO la familia DD/MM/YYYY (también con `.` o `-` como
separador): día primero, rangos validados — una fecha imposible (32/05, 31/02)
se reporta y NO se toca. YYYY y YYYY-MM se dejan como están (granularidad
parcial legítima: nunca se inventa día ni mes). Cualquier otro formato se
reporta agrupado sin tocarlo; con --all-formats también se normalizan los que
normalize_release_date() reconozca (年月日, YYYY/MM/DD hh:mm:ss, mes textual).

Uso:
    python scripts/retrofit/normalize_release_dates.py --dry-run
    python scripts/retrofit/normalize_release_dates.py
    python scripts/retrofit/normalize_release_dates.py --all-formats
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# Gotcha #64: el wrapper de la raíz puede sombrear scripts/manga_watch.py.
try:
    from manga_watch import backup_and_rotate, is_approved, normalize_release_date  # type: ignore
except ImportError:
    from scripts.manga_watch import backup_and_rotate, is_approved, normalize_release_date  # type: ignore

_ISO_FULL = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_PARTIAL = re.compile(r"^\d{4}(?:-\d{2})?$")
_DMY_FAMILY = re.compile(r"^\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}$")


def _shape(value: str) -> str:
    """Firma del formato para agrupar el reporte ("2023/09/27 10:00:00" → "9999/99/99 99:99:99")."""
    return re.sub(r"[A-Za-zÀ-ÿ]", "a", re.sub(r"\d", "9", value))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/items.jsonl")
    parser.add_argument("--output", default="data/items.jsonl")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe el archivo; solo reporta qué cambiaría.")
    parser.add_argument("--all-formats", action="store_true",
                        help="Además de DD/MM/YYYY, normaliza todo formato que "
                             "normalize_release_date() reconozca (年月日, "
                             "YYYY/MM/DD hh:mm:ss, mes textual FR/ES/IT/EN).")
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
    untouched_partial = 0
    invalid_dmy: list[tuple[str, str]] = []
    other_formats: Counter[str] = Counter()
    other_samples: dict[str, str] = {}
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

        if is_approved(item) and not args.include_approved:
            skipped_approved += 1
            out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            continue

        raw = (item.get("release_date") or "").strip()
        if raw and not _ISO_FULL.match(raw):
            if _ISO_PARTIAL.match(raw):
                untouched_partial += 1  # YYYY / YYYY-MM: granularidad legítima
            elif _DMY_FAMILY.match(raw) or args.all_formats:
                new = normalize_release_date(raw)
                if new != raw:
                    changed += 1
                    if len(sample_changes) < 10:
                        sample_changes.append((item.get("slug") or item.get("url", "")[:60], raw, new))
                    item["release_date"] = new
                elif _DMY_FAMILY.match(raw):
                    invalid_dmy.append((item.get("slug", "?"), raw))
                else:
                    other_formats[_shape(raw)] += 1
                    other_samples.setdefault(_shape(raw), raw)
            else:
                other_formats[_shape(raw)] += 1
                other_samples.setdefault(_shape(raw), raw)
        out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))

    print(f"[INFO] {len(lines)} líneas totales, {changed} release_date se normalizarían.")
    print(f"[INFO] {untouched_partial} con granularidad parcial (YYYY / YYYY-MM) — sin tocar, por diseño.")
    if skipped_approved:
        print(f"[INFO] {skipped_approved} aprobados saltados (usa --include-approved para incluirlos)")
    if sample_changes:
        print("\nMuestra de cambios:")
        for slug, old, new in sample_changes:
            print(f"  {slug}: {old!r} → {new!r}")
    if invalid_dmy:
        print(f"\n[WARN] {len(invalid_dmy)} DD/MM/YYYY con rangos inválidos — SIN tocar, revisar a mano:")
        for slug, raw in invalid_dmy[:10]:
            print(f"  {slug}: {raw!r}")
    if other_formats:
        modo = "no reconocidos por normalize_release_date()" if args.all_formats else "fuera de scope (corré con --all-formats para normalizarlos)"
        print(f"\n[REPORT] Otros formatos {modo} — SIN tocar:")
        for shape, count in other_formats.most_common():
            print(f"  {count:5d}  {shape}   (ej: {other_samples[shape]!r})")

    if args.dry_run:
        print("\n[DRY-RUN] No se escribió ningún archivo.")
        return 0

    if changed == 0:
        print("[OK] Nada que normalizar.")
        return 0

    if dst.exists():
        backup = backup_and_rotate(dst, "normdates")
        print(f"[OK] Backup guardado en {backup}")

    dst.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"[OK] Escribí {dst} con {changed} fechas normalizadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
