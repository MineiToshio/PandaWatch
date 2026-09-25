#!/usr/bin/env python3
"""Corrige los `edition_key` de Ivrea que dicen `artbook` siendo tomos numerados.

Colateral de la gotcha #196: como las 19 URLs de la fuente apuntaban a un JPG en
vez de a la ficha, la derivación no tenía descripción real que leer y etiquetó
como `artbook` a tomos regulares numerados.

**Es una contradicción interna del propio item**: `product_type = manga` +
`volume` presente + `edition_key` terminado en `-artbook-ar`. La regla del repo
es explícita — un item con número de volumen nunca es `artbook`.

Verificado en vivo (2026-09-07) contra la ficha `/titulo/<slug>/` de cada uno: en
las cuatro páginas el único término de formato es "sobrecubierta"; no aparece
kanzenban, deluxe, wide ni artbook. Es la línea estándar de Ivrea (B6 con
sobrecubierta, páginas a color), que en el corpus ya se codifica como
`-regular-ar` para esta misma fuente (`dandadan-ivrea-ar-regular-ar`,
`grand-blue-dreaming-ivrea-ar-regular-ar`).

Matiz anotado, no resuelto acá: la Inuyasha de Ivrea son 30 tomos (la ficha dice
"ESTADO EN JAPÓN: COMPLETA – 30 TOMOS"), o sea que la obra base es la Wide
Edition japonesa, no el tankōbon de 56. Se codifica igual como `regular` porque
es la ÚNICA edición que publica Ivrea y es el patrón establecido de la fuente; si
alguna vez conviven dos líneas de la misma serie habrá que distinguirlas.

Correr `enforce_listadomanga_rules.py` después (re-deriva cluster_key y slug).

Uso:
    .venv/bin/python scripts/retrofit/fix_ivrea_artbook_keys_20260907.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from manga_watch import backup_and_rotate, write_items_atomic  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"

WRONG_SUFFIX = "-ivrea-ar-artbook-ar"
RIGHT_SUFFIX = "-ivrea-ar-regular-ar"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    items = [json.loads(line) for line in ITEMS.read_text().splitlines() if line.strip()]

    fixed = 0
    skipped: list[str] = []
    for it in items:
        ek = it.get("edition_key") or ""
        if not ek.endswith(WRONG_SUFFIX):
            continue
        # Guard: sólo se corrige lo que es DEMOSTRABLEMENTE un tomo, no un
        # artbook real que casualmente viva en esta fuente.
        if it.get("product_type") != "manga" or not str(it.get("volume") or "").strip():
            skipped.append(f"{it.get('slug')} (pt={it.get('product_type')}, vol={it.get('volume')!r})")
            continue
        new_ek = ek[: -len(WRONG_SUFFIX)] + RIGHT_SUFFIX
        print(f"  {it.get('slug'):42s} | {ek} → {new_ek}")
        it["edition_key"] = new_ek
        display = it.get("edition_display") or ""
        if display.lower().startswith("artbook"):
            it["edition_display"] = "Regular"
        fixed += 1

    print(f"\nEdition keys corregidas: {fixed}")
    if skipped:
        print(f"Saltados por no ser tomos numerados ({len(skipped)}):")
        for s in skipped:
            print(f"  {s}")

    if args.dry_run:
        print("[DRY-RUN] No se escribió nada.")
        return 0
    if fixed:
        backup_and_rotate(ITEMS, "ivrea-artbook-keys")
        write_items_atomic(ITEMS, items)
        print("items.jsonl actualizado. Correr enforce_listadomanga_rules.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
