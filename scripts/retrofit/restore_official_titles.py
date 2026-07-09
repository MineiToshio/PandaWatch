#!/usr/bin/env python3
"""restore_official_titles.py — restaura el TÍTULO OFICIAL en todo el corpus
(política de títulos 2026-06-12).

MOTIVO (decisión owner 2026-06-12): el skill /watch-standardize-catalog
reescribía `title` como "{serie canónica} {edición} {vol}" — traducía y
renombraba la obra ("Guardianes de la Noche nº8" → "Demon Slayer 8") y le
inyectaba tipos de edición que no son parte del nombre oficial ("20th Century
Boys Kanzenban"). El título ES un dato: el nombre oficial con que la editorial
publica el producto. El nombre reconocible vive en `series_display` (canónico)
y la búsqueda resuelve aliases multilingües (data/series_aliases.json).

Qué hace:
  1. `title` = clean_title(title_original) — el título scrapeado, limpio de
     basura de e-commerce (clean_title es idempotente). Sólo si difiere.
  2. Elimina el campo `title_standardized` (retirado del schema).
  3. Re-deriva cluster_key de lo tocado (el tier fuzzy usa el título) y
     consolida.

MIGRACIÓN ONE-SHOT POR ITEM: marca cada item procesado con
`title_restored_at` y NUNCA re-procesa items marcados. Sin el marcador, cada
re-corrida desharía las normalizaciones COSMÉTICAS del enforcer ("nº8"→"8",
orden de Edición Especial, tags de colisión) y el par restore+enforcer no
convergería. Sólo evalúa items con `standardized_at` (los únicos que el skill
viejo pudo haber renombrado).

Respeta `approved_at` (golden records intactos, incluido su
title_standardized residual). Idempotente (vía marcador). Después de
correrlo, correr el enforcer (normaliza "nº", orden de Edición Especial,
colisiones):

  .venv/bin/python scripts/retrofit/restore_official_titles.py --dry-run
  .venv/bin/python scripts/retrofit/restore_official_titles.py
  .venv/bin/python scripts/retrofit/enforce_listadomanga_rules.py --fast
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import manga_watch as mw  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    restored, stripped, marked, ex = 0, 0, 0, []
    for it in items:
        if it.get("approved_at"):
            continue
        if it.pop("title_standardized", None) is not None:
            stripped += 1
        if it.get("title_restored_at") or not it.get("standardized_at"):
            continue
        if not args.dry_run:
            it["title_restored_at"] = now_iso
        marked += 1
        orig = (it.get("title_original") or "").strip()
        if not orig:
            continue
        new = mw.clean_title(orig)
        old = it.get("title", "") or ""
        if new and new != old:
            if len(ex) < 25:
                ex.append((old, new))
            it["title"] = new
            it["cluster_key"] = mw.derive_cluster_key(it)
            restored += 1
    print(f"[official-titles] items marcados (one-shot): {marked}")
    print(f"[official-titles] títulos restaurados: {restored}")
    print(f"[official-titles] title_standardized eliminados: {stripped}")
    for o, n in ex:
        print(f"    {o!r}  →  {n!r}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if restored or stripped or marked:
        before = len(items)
        items = mw.consolidate_by_cluster(items)
        print(f"[official-titles] consolidate: {before} → {len(items)}")
        backup = mw.backup_and_rotate(ITEMS, "officialtitles")
        print(f"[official-titles] backup: {backup}")
        mw.write_items_atomic(ITEMS, items)
        print(f"[official-titles] escrito {ITEMS}.")
        print("[official-titles] ahora corré: "
              ".venv/bin/python scripts/retrofit/enforce_listadomanga_rules.py --fast")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
