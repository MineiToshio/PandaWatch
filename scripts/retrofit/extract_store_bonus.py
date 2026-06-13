#!/usr/bin/env python3
"""extract_store_bonus.py — separa el BONUS DE TIENDA (店舗特典) del `title` al
campo `store_bonus` (gotcha #93).

MOTIVO (decisión owner 2026-06-12): el `title` es el nombre OFICIAL del
producto, pero los retailers japoneses le pegan su perk de compra entre
brackets — "(…ポストカード)【楽天ブックス限定特典】" = "si compras en Rakuten te
llevas una postal". Eso NO es el nombre del producto y NO debe ocupar el título
en el grid; pertenece al detalle ("incluye estos bonus"). El nombre oficial de
la EDICIÓN (特装版/限定版/初回限定…) NO se toca.

Qué hace (sólo items con 特典 en el title; alta precisión):
  - `title` = título sin el bracket 【…特典…】 (y su descripción adjacente).
  - `store_bonus` = el texto del bonus extraído (para el detalle).
  - `title_original` queda INTACTO (conserva el nombre oficial completo).
  - Re-deriva cluster_key de lo tocado y consolida.

Usa `mw.split_store_bonus` (fuente única, misma que el scraper). Idempotente
(re-aplicar no cambia nada). Respeta `approved_at`.

Uso:
  .venv/bin/python scripts/retrofit/extract_store_bonus.py --dry-run
  .venv/bin/python scripts/retrofit/extract_store_bonus.py
"""
from __future__ import annotations

import argparse
import json
import shutil
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
    changed, ex = 0, []
    for it in items:
        if it.get("approved_at"):
            continue
        old = it.get("title", "") or ""
        new, bonus = mw.split_store_bonus(old)
        if new != old:
            if len(ex) < 25:
                ex.append((old, new, bonus))
            if not args.dry_run:
                it["title"] = new
                if bonus:
                    it["store_bonus"] = bonus
                it["cluster_key"] = mw.derive_cluster_key(it)
            changed += 1
    print(f"[store-bonus] títulos separados: {changed}")
    for o, n, b in ex:
        print(f"    {o!r}\n      → title={n!r}  bonus={b!r}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if changed:
        before = len(items)
        items = mw.consolidate_by_cluster(items)
        print(f"[store-bonus] consolidate: {before} → {len(items)}")
        shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-storebonus-bak"))
        tmp = ITEMS.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        tmp.replace(ITEMS)
        print(f"[store-bonus] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
