#!/usr/bin/env python3
"""Vacía los `author` que son CROMO de la plantilla del sitio, no un autor.

Gotcha #193: el último recurso de `fetch_metadata_from_detail()` leía los
primeros 3000 caracteres del `<body>` ENTERO. En una plantilla con mega-menú
(Funside) esos caracteres son la NAVEGACIÓN, y el regex `di <X>` de
`AUTHOR_BY_PATTERN` engancha ahí: las 174 fichas fetcheadas en la corrida del
2026-09-07 devolvieron la MISMA cadena, `"Batman ELDEN RING ARTBOOK"`, leída del
`div.mega-menu__promotions`.

El mecanismo ya está arreglado en `manga_watch.py` (región del producto sin
nav/breadcrumb + guard de forma de nombre propio, verificado en vivo: 8/8 fichas
de Funside devuelven autor vacío, y el `Autori: Tsutomu Nihei` de Panini IT se
sigue extrayendo). Este retrofit limpia lo YA ingresado, que el scrape no vuelve
a tocar en items congelados.

DENYLIST EXPLÍCITA, no heurística. Una heurística de "valor repetido" no sirve:
un autor real se repite mucho más (Kentaro Miura, 88 items) y los valores
multi-autor legítimos ("Buronson / Shō Fumimura", "Posuka DEMIZU / Kaiu SHIRAI")
tienen exactamente la misma forma que el ruido. Sólo se limpia lo verificado
contra la página en vivo.

Se deja `author` vacío en vez de adivinar: `backfill_metadata` lo repuebla bien
con el extractor ya corregido.

Uso:
    .venv/bin/python scripts/retrofit/fix_chrome_authors_20260907.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from manga_watch import backup_and_rotate, write_items_atomic  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"

# (host, valor exacto de author) verificados EN VIVO como texto de plantilla.
# funside.it: texto de `div.mega-menu__promotions` ("… Comics di Batman …
# ELDEN RING ARTBOOK - (VOL.1-2) …"), reproducido el 2026-09-07 sobre
# funside.it/products/non-tormentarmi-nagatoro-1-variant-games-academy-funside.
CHROME_AUTHORS: set[tuple[str, str]] = {
    ("funside.it", "Batman ELDEN RING ARTBOOK"),
}


def hosts_of(item: dict) -> set[str]:
    hosts = set()
    for source in item.get("sources") or []:
        netloc = urlsplit(source.get("url") or "").netloc.lower()
        if netloc:
            hosts.add(netloc)
            if netloc.startswith("www."):
                hosts.add(netloc[4:])
    return hosts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    items = [json.loads(line) for line in ITEMS.read_text().splitlines() if line.strip()]

    cleared = 0
    for it in items:
        author = (it.get("author") or "").strip()
        if not author:
            continue
        if any((host, author) in CHROME_AUTHORS for host in hosts_of(it)):
            it["author"] = ""
            cleared += 1

    print(f"Items con author-cromo vaciado: {cleared}")
    if args.dry_run:
        print("[DRY-RUN] No se escribió nada.")
        return 0
    if cleared:
        backup_and_rotate(ITEMS, "chrome-authors")
        write_items_atomic(ITEMS, items)
        print("items.jsonl actualizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
