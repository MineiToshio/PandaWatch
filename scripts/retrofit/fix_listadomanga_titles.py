#!/usr/bin/env python3
"""fix_listadomanga_titles.py — repara títulos de listadomanga a los que el
parser viejo les DROPEÓ el subtítulo (título en 2 líneas sin número, ej.
"CLAMP Art-book" + "North Side" → quedaba solo "CLAMP Art-book"). Gotcha #41(g).

Re-parsea cada colección con el parser ACTUAL (ya arreglado, alt-aware) y, si el
título nuevo es una versión MÁS COMPLETA del `title_original` guardado (mismo
prefijo, más largo), actualiza title / title_standardized / title_original.

Conservador: SOLO toca items donde el título nuevo empieza con el viejo y es más
largo (firma del subtítulo dropeado). No re-titula nada más.

Uso:
  .venv/bin/python scripts/retrofit/fix_listadomanga_titles.py --dry-run
  .venv/bin/python scripts/retrofit/fix_listadomanga_titles.py
"""
from __future__ import annotations
import json, re, sys, argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "wikis"))
import requests  # noqa: E402
import listadomanga_collections as lmc  # noqa: E402
from manga_watch import backup_and_rotate, write_items_atomic  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"
_S = requests.Session(); _S.headers.update({"User-Agent": "Mozilla/5.0 (titlefix)"})


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _key_from_url(url: str):
    m = re.search(r"coleccion\.php\?id=(\d+)&item=([a-z]+)-([^-&]+)", url or "")
    return (m.group(1), m.group(2), m.group(3)) if m else None


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    # Colecciones a re-parsear (las que tienen items lmc).
    by_cole: dict[str, list] = {}
    for it in items:
        k = _key_from_url(it.get("url", ""))
        if k:
            by_cole.setdefault(k[0], []).append(it)

    print(f"[titles] colecciones lmc a re-parsear: {len(by_cole)}")
    changed = 0
    diffs = []
    for n, (cid, group) in enumerate(sorted(by_cole.items(), key=lambda x: int(x[0])), 1):
        try:
            cands = lmc.fetch_collection(int(cid), _S)
        except Exception:
            continue
        # mapa (kind, vol) → título nuevo del parser
        newt = {}
        for c in cands:
            k = _key_from_url(c.url)
            if k:
                newt[(k[1], k[2])] = c.title
        for it in group:
            k = _key_from_url(it.get("url", ""))
            cand_title = newt.get((k[1], k[2])) if k else None
            if not cand_title:
                continue
            old = it.get("title_original") or it.get("title") or ""
            # firma del subtítulo dropeado: el nuevo EMPIEZA con el viejo y es más largo
            if (_norm(cand_title) != _norm(old)
                    and _norm(cand_title).startswith(_norm(old))
                    and len(cand_title) > len(old) + 2):
                if len(diffs) < 90:
                    diffs.append((old, it.get("title", ""), cand_title))
                if not args.dry_run:
                    it["title"] = cand_title
                    it["title_original"] = cand_title
                changed += 1
        if n % 200 == 0:
            print(f"   … {n}/{len(by_cole)} colecciones, {changed} títulos corregidos")

    print(f"\n[titles] títulos corregidos: {changed}")
    print("  (title_original viejo → title_display viejo → título NUEVO completo):")
    for old, disp, new in diffs[:90]:
        print(f"    {old[:24]!r:26} | {disp[:24]!r:26} → {new!r}")
    if args.dry_run:
        print("\n[DRY-RUN] no se escribió nada.")
        return 0
    bak = backup_and_rotate(ITEMS, "titlefix")
    write_items_atomic(ITEMS, items)
    print(f"[titles] escrito {ITEMS} ({changed}). Backup: {bak}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
