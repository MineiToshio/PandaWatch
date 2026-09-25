#!/usr/bin/env python3
"""Poda `data/unmapped_series.jsonl` conservando la cola de CURACIÓN.

El archivo es DOS colas en un mismo fichero (gotcha #155):

  1. **Series sin mapear** (filas sin `reason`): las consume
     `/watch-enrich-series-aliases`, y una vez procesadas son descartables — el
     próximo scrape las vuelve a generar si siguen sin mapear.
  2. **Curación manual** (`reason` = `llm_non_manga`, `standardize_exhausted`…):
     items que un humano tiene que revisar uno por uno. NO son regenerables por
     el scrape: se pierden para siempre si se truncan sin mirarlas.

El Step 5 del skill de aliases hacía `: > data/unmapped_series.jsonl`, que
borra LAS DOS. Por eso la rutina diaria lleva 7 corridas seguidas saltándose el
skill: correrlo destruía la cola de curación sin revisarla. Este script es el
reemplazo — sólo poda la cola (1).

Además DEDUPLICA (gotcha #157): el appender no deduplica entre corridas, así
que el 82-92% del archivo son `series_key` repetidas. Eso rompía la condición
"¿creció la cola?" que usa el PASO 4 de la rutina diaria, que se disparaba
siempre por duplicación y no por descubrimiento.

Uso:
    .venv/bin/python scripts/prune_unmapped_queue.py [--dry-run]
    .venv/bin/python scripts/prune_unmapped_queue.py --dedupe-only  # no poda, sólo dedup
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manga_watch import backup_and_rotate  # noqa: E402

QUEUE = ROOT / "data" / "unmapped_series.jsonl"

# Filas con estos `reason` son COLA DE CURACIÓN: nunca se podan
# automáticamente. Sólo un humano (o un retrofit de curación explícito) las
# saca. Una fila con un `reason` desconocido también se conserva: ante la duda,
# no se borra dato que el scrape no sabe regenerar.
REGENERABLE_REASONS = {"", None}


def is_curation_row(row: dict) -> bool:
    return (row.get("reason") or "") not in REGENERABLE_REASONS


def dedupe_key(row: dict) -> tuple:
    return (row.get("series_key") or "", row.get("reason") or "", row.get("sample_url") or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dedupe-only", action="store_true",
                    help="sólo deduplica; conserva también las filas de series sin mapear")
    args = ap.parse_args()

    if not QUEUE.exists():
        print(f"{QUEUE} no existe — nada que hacer.")
        return 0

    rows: list[dict] = []
    unreadable = 0
    for line in QUEUE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            unreadable += 1

    total = len(rows)
    curation = [r for r in rows if is_curation_row(r)]
    regenerable = [r for r in rows if not is_curation_row(r)]

    keep_source = rows if args.dedupe_only else curation
    seen: set[tuple] = set()
    kept: list[dict] = []
    for row in keep_source:
        key = dedupe_key(row)
        if key in seen:
            continue
        seen.add(key)
        kept.append(row)

    print(f"Filas leídas:                    {total}"
          + (f"  ({unreadable} ilegibles descartadas)" if unreadable else ""))
    print(f"  series sin mapear (podables):  {len(regenerable)}")
    print(f"  curación (SIEMPRE se conserva):{len(curation)}")
    for reason in sorted({(r.get('reason') or '') for r in curation}):
        n = sum(1 for r in curation if (r.get("reason") or "") == reason)
        print(f"      {n:5d}  {reason}")
    print(f"Filas que quedan:                {len(kept)}"
          f"   (dedup quitó {len(keep_source) - len(kept)})")

    if args.dry_run:
        print("[DRY-RUN] No se escribió nada.")
        return 0

    backup_and_rotate(QUEUE, "prune-unmapped")
    tmp = QUEUE.with_suffix(QUEUE.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in kept:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        import os
        os.fsync(fh.fileno())
    tmp.replace(QUEUE)
    print(f"{QUEUE.name} actualizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
