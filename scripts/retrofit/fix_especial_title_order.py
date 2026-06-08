#!/usr/bin/env python3
"""fix_especial_title_order.py — normaliza el título de las EDICIONES ESPECIALES a
"{serie} {vol} Edición Especial" (gotcha #52): el volumen ANTES del calificador, sin
paréntesis. Cubre TODAS las fuentes (no sólo listadomanga), ej. el item de la tienda
Milky Way "Witch Hat Atelier Edición Especial 5" → "Witch Hat Atelier 5 Edición Especial".

Usa `mw.format_especial_title` (sólo cambia títulos con el patrón especial; un regular
queda intacto). Idempotente. Respeta `approved_at`.

Uso:
  .venv/bin/python scripts/retrofit/fix_especial_title_order.py --dry-run
  .venv/bin/python scripts/retrofit/fix_especial_title_order.py
"""
from __future__ import annotations
import json, sys, argparse, shutil
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
        new = mw.format_especial_title(old)
        if new != old:
            if len(ex) < 30:
                ex.append((old, new))
            if not args.dry_run:
                it["title"] = new
                if it.get("title_standardized") == old:
                    it["title_standardized"] = new
            changed += 1
    print(f"[especial-order] títulos reordenados: {changed}")
    for o, n in ex:
        print(f"    {o!r}  →  {n!r}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if changed:
        shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-especialorder-bak"))
        tmp = ITEMS.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        tmp.replace(ITEMS)
        print(f"[especial-order] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
