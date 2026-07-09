#!/usr/bin/env python3
"""fix_listadomanga_edition_display.py — el `edition_display` de un item de
listadomanga debe ser el NOMBRE OFICIAL de la edición (el título de la /coleccion),
SIN traducir (gotcha #49). NO el slug genérico traducido "Special (Norma Editorial)".

Sólo el nombre del TOMO (`title`) se traduce; el de la EDICIÓN no. Caso real:
Attack on Titan cole 1606 mostraba "Special (Norma Editorial)" cuando la edición se
llama oficialmente "Ataque a los Titanes".

Re-fetchea cada coleccion única del corpus, extrae el collection_title con el parser
y lo asigna como `edition_display` a TODOS sus items. El motor (parser) ya lo hace
para items nuevos; esto repara el histórico.

Uso:
  .venv/bin/python scripts/retrofit/fix_listadomanga_edition_display.py --dry-run
  .venv/bin/python scripts/retrofit/fix_listadomanga_edition_display.py
"""
from __future__ import annotations
import json, re, sys, argparse, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from wikis.listadomanga_collections import _extract_collection_title  # noqa: E402
from manga_watch import backup_and_rotate, write_items_atomic  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"
_COLE_RE = re.compile(r"listadomanga\.es/coleccion\.php\?id=(\d+)")


def _cole(u: str) -> str | None:
    m = _COLE_RE.search(u or "")
    return m.group(1) if m else None


def _fetch_title(cid: str, session: requests.Session) -> tuple[str, str]:
    try:
        html = session.get(f"https://www.listadomanga.es/coleccion.php?id={cid}", timeout=20).text
        return cid, _extract_collection_title(BeautifulSoup(html, "html.parser")) or ""
    except Exception:
        return cid, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    coles = sorted({_cole(it.get("url", "")) for it in items if _cole(it.get("url", ""))})
    print(f"[edition-display] colecciones únicas a re-titular: {len(coles)}")

    s = requests.Session()
    s.headers["User-Agent"] = "manga-watch/0.2 (+edition-display-retrofit)"
    titles: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for cid, ct in ex.map(lambda c: _fetch_title(c, s), coles):
            if ct:
                titles[cid] = ct

    print(f"[edition-display] títulos oficiales obtenidos: {len(titles)}")
    changed, diffs = 0, []
    for it in items:
        c = _cole(it.get("url", ""))
        ct = titles.get(c)
        if not ct or it.get("edition_display") == ct:
            continue
        if len(diffs) < 30:
            diffs.append((it.get("edition_display"), ct))
        if not args.dry_run:
            it["edition_display"] = ct
        changed += 1

    print(f"[edition-display] items con edition_display corregido: {changed}")
    for old, new in diffs[:30]:
        print(f"    {old!r}  →  {new!r}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    backup_and_rotate(ITEMS, "editiondisplay")
    write_items_atomic(ITEMS, items)
    print(f"[edition-display] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
