#!/usr/bin/env python3
"""Repara los títulos de KR - Aladin con el CROMO de la lista pegado adelante.

La fuente declaraba `item_selector: div.ss_book_box` y NINGÚN `title_selector`,
así que el título salía del texto del contenedor entero: número de puesto,
banner promocional, "크게보기", la etiqueta de categoría `[국내도서]` y recién
después el nombre real del producto.

Ejemplo real (2026-09-07):
    "2단 아크릴 스탠드/ 키보드 덮개(대상도서 구매 시) [국내도서] 고깔모자의 아틀리에 16 (한정판)"
    →                                              "고깔모자의 아틀리에 16 (한정판)"

El selector ya está corregido en `sources.yml` (`title_selector: "a.bo3"`,
verificado en vivo dentro de cada `div.ss_book_box`). Este retrofit arregla los
items YA ingresados, que el scrape no vuelve a tocar cuando están congelados.

El corte es DETERMINISTA y seguro: el título real es siempre lo que está a la
derecha del último `[국내도서]`. No se inventa nada — si el marcador no está, el
item no se toca.

Viola la política dura de títulos tenerlos así (`docs/reference/title-policy.md`):
el `title` es el nombre OFICIAL del producto.

Uso:
    .venv/bin/python scripts/retrofit/fix_aladin_list_chrome_titles_20260907.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from manga_watch import backup_and_rotate, clean_text, write_items_atomic  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"

# Etiqueta de categoría de Aladin: todo lo que va ANTES es cromo de la lista.
CATEGORY_TAG = "[국내도서]"
# Sufijo de "extras" que la caja concatena tras el título con " - ".
EXTRAS_SEP = re.compile(r"\s+-\s+")


def is_aladin(item: dict) -> bool:
    return any(
        "aladin.co.kr" in (s.get("url") or "")
        for s in (item.get("sources") or [])
    )


def repair(title: str) -> str | None:
    """Devuelve el título limpio, o None si no hay nada que hacer."""
    if CATEGORY_TAG not in title:
        return None
    tail = clean_text(title.rsplit(CATEGORY_TAG, 1)[1])
    if not tail:
        return None
    return tail if tail != title else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show", type=int, default=12, help="cuántos cambios listar")
    args = ap.parse_args()

    items = [json.loads(line) for line in ITEMS.read_text().splitlines() if line.strip()]

    fixed = 0
    shown = 0
    for it in items:
        if not is_aladin(it):
            continue
        title = it.get("title") or ""
        new = repair(title)
        if not new:
            continue
        if shown < args.show:
            print(f"  {title[:78]!r}\n    → {new[:78]!r}")
            shown += 1
        it["title"] = new
        fixed += 1

    print(f"\nTítulos de Aladin reparados: {fixed}")
    if args.dry_run:
        print("[DRY-RUN] No se escribió nada.")
        return 0
    if fixed:
        backup_and_rotate(ITEMS, "aladin-list-chrome-titles")
        write_items_atomic(ITEMS, items)
        print("items.jsonl actualizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
