#!/usr/bin/env python3
"""Repara los títulos de IT - Dynit pisados por el badge de descuento.

El `title_selector` de la fuente era una lista separada por comas
(".woocommerce-loop-product__title, h2, h3, a"). CSS matchea por orden en el
DOCUMENTO, no por el orden de la lista, y el <span class="onsale">Sconto N%</span>
vive dentro de un <a> que aparece ANTES del <h2> — así que el título capturado
quedó siendo el badge. Mismo bug que Funside 2026-08-24
(`fix_funside_frozen_titles_20260824.py`).

El selector ya está corregido en sources.yml; este retrofit arregla los items
YA congelados (con `standardized_at`), que el scrape no vuelve a tocar.

Uso:
    .venv/bin/python scripts/retrofit/fix_dynit_badge_titles_20260902.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from manga_watch import backup_and_rotate, write_items_atomic  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"

# Títulos que son en realidad badges de la tarjeta, no nombres de producto.
BADGE_TITLE_RE = re.compile(r"^\s*(?:sconto\s*\d+\s*%|uscita\s*:.*)\s*$", re.IGNORECASE)

# Títulos reales verificados contra la página de producto en vivo (2026-09-02).
KNOWN_TITLES = {
    "https://www.dynit.it/prodotto/makoto-shinkai-your-name-artbook-libri/":
        "Makoto Shinkai – Your Name – Artbook",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    items = [json.loads(line) for line in ITEMS.read_text().splitlines() if line.strip()]
    fixed = 0
    unresolved: list[str] = []

    for it in items:
        title = it.get("title") or ""
        if not BADGE_TITLE_RE.match(title):
            continue
        urls = [s.get("url") for s in (it.get("sources") or []) if s.get("url")]
        new = next((KNOWN_TITLES[u] for u in urls if u in KNOWN_TITLES), None)
        if not new:
            unresolved.append(f"{it.get('slug')} | {title!r} | {urls[:1]}")
            continue
        print(f"  {it.get('slug')}: {title!r} → {new!r}")
        it["title"] = new
        fixed += 1

    print(f"\nItems con título-badge reparados: {fixed}")
    if unresolved:
        print(f"Sin título conocido ({len(unresolved)}) — revisar a mano:")
        for u in unresolved:
            print(f"  {u}")

    if args.dry_run:
        print("[DRY-RUN] No se escribió nada.")
        return 0
    if fixed:
        backup_and_rotate(ITEMS, "dynit-badge-titles")
        write_items_atomic(ITEMS, items)
        print("items.jsonl actualizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
