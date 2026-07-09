#!/usr/bin/env python3
"""remove_free_preview_editions.py — borra de items.jsonl los folletos
promocionales GRATUITOS de ListadoManga que se colaron como "edición especial".

Contexto (gotcha #103, caso owner Edens Zero id=3112 2026-06-14). ListadoManga
titula "(Especial)" a ciertos números que en realidad son material de marketing
que la editorial REGALA: el preview del primer capítulo de una obra, un
mini-artbook de regalo, un avance bundleado con un videojuego, etc. No son
ediciones comprables ni coleccionables. La señal estructural en la página viva
es la línea de PRECIO: donde un tomo de pago muestra "9,98 €", el folleto
gratuito muestra "Número Gratuito".

La prevención vive en el parser (`listadomanga_collections.py`
`FREE_PRICE_PATTERN`): delta y full comparten ese parser, así que un re-scrape
ya nunca los reingiere. Este retrofit limpia los que YA estaban en el corpus.

Dos reglas (ambas verificadas contra la página viva el 2026-06-14):
  A. ESTRUCTURAL — la `description` contiene "Número Gratuito". Es lo que el
     parser de colecciones escribió al capturar la línea de precio. Cubre los
     items de `ListadoManga (colecciones)`.
  B. POR COLECCIÓN VERIFICADA — items legacy de `ListadoManga (calendario)`
     (parser plano viejo, fuera del pipeline canónico) cuya `description` quedó
     malformada y NO contiene "Número Gratuito", pero cuya colección SÍ es un
     free preview (precio "Número Gratuito" confirmado por fetch). Sólo se
     borran si su precio está vacío (los free no tienen precio) para no tocar
     un eventual número de pago de la misma colección.

Guarda de seguridad (igual que remove_phantom_calendar_editions.py): nunca se
borra una fila aprobada (golden record).

Uso:
  .venv/bin/python scripts/retrofit/remove_free_preview_editions.py --dry-run
  .venv/bin/python scripts/retrofit/remove_free_preview_editions.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import backup_and_rotate, write_items_atomic  # type: ignore

ITEMS = _SCRIPTS.parent / "data" / "items.jsonl"

# Colecciones de ListadoManga cuyo número es "Número Gratuito" (free preview /
# regalo promocional), verificadas una a una contra la página viva el 2026-06-14
# (categoría editorial "Previews" id=332 + promos sueltas de Game / mini-artbooks).
# Se usan para la Regla B (legacy calendario con description malformada).
FREE_PREVIEW_COLLECTIONS = {
    2534, 2581, 2709, 2790, 2908, 2940, 3011, 3015, 3079, 3112, 3243, 3372,
    3574, 3616, 3978, 4001, 4023, 4303, 4318, 4617, 4874, 4887, 4911, 5594, 5751,
}

_FREE_DESC = re.compile(r"n[úu]mero\s+gratuito", re.IGNORECASE)
_COLE_ID = re.compile(r"coleccion\.php\?id=(\d+)")


def _is_listadomanga(it: dict) -> bool:
    return "listadomanga" in (it.get("source") or "").lower()


def _cole_id(it: dict) -> int | None:
    m = _COLE_ID.search(it.get("url") or "")
    return int(m.group(1)) if m else None


def _is_free_preview(it: dict) -> tuple[bool, str]:
    """(es_free_preview, razón). Sólo aplica a items de ListadoManga."""
    if not _is_listadomanga(it):
        return False, ""
    desc = it.get("description") or ""
    if _FREE_DESC.search(desc):
        return True, "A: description='Número Gratuito'"
    cid = _cole_id(it)
    if cid in FREE_PREVIEW_COLLECTIONS and not (it.get("price") or "").strip():
        return True, f"B: colección free-preview verificada (id={cid}), sin precio"
    return False, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="no escribe nada, sólo reporta")
    args = ap.parse_args()

    items = [json.loads(l) for l in ITEMS.open(encoding="utf-8") if l.strip()]

    out: list[dict] = []
    deleted, skipped = [], []
    for it in items:
        free, reason = _is_free_preview(it)
        if free:
            if it.get("approved_at"):
                skipped.append((it.get("slug"), "aprobado (golden record)"))
                out.append(it)
                continue
            deleted.append((it.get("slug"), it.get("source"), reason))
            continue  # no se re-agrega → borrado
        out.append(it)

    print("=== remove_free_preview_editions ===\n")
    print(f"DELETE folletos gratuitos ({len(deleted)}):")
    for slug, src, reason in sorted(deleted):
        print(f"  ✗ {slug}  [{src}]  ← {reason}")
    if skipped:
        print(f"\nSALTADOS por guarda ({len(skipped)}):")
        for slug, why in skipped:
            print(f"  · {slug}  ({why})")

    if args.dry_run:
        print("\n[dry-run] no se escribió nada.")
        return 0
    if not deleted:
        print("\n[ok] nada que borrar (idempotente).")
        return 0

    backup = backup_and_rotate(ITEMS, "freepreview")
    write_items_atomic(ITEMS, out)
    print(f"\n[ok] escrito {ITEMS} ({len(out)} filas, -{len(deleted)}). Backup: {backup.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
