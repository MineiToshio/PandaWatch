#!/usr/bin/env python3
"""reconcile_lista_stale.py — quita del corpus los items de listadomanga que el
parser ACTUAL ya NO genera como coleccionables (data vieja de parsers buggy, ej.
omnibus/regular capturados por el viejo "doble sobrecubierta → premium_format").

Para cada coleccion: re-fetchea, calcula el set de (kind, vol) que el parser actual
considera coleccionable (score≥30 + gate), y quita los items de la DB (con synthetic
URL `item=`) cuyo (kind, vol) NO está en ese set. Conservador:
  - sólo toca items con synthetic URL (comparables); old-format sin item= se conserva.
  - sólo quita si la coleccion fetcheó OK (si falla el fetch, NO toca nada).
  - respeta `approved_at`.

Uso:
  .venv/bin/python scripts/retrofit/reconcile_lista_stale.py --dry-run
  .venv/bin/python scripts/retrofit/reconcile_lista_stale.py
"""
from __future__ import annotations
import json, re, sys, argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import requests
import wikis.listadomanga_collections as L
import manga_watch as mw

ITEMS = ROOT / "data" / "items.jsonl"
_ITEM = re.compile(r"item=([a-z]+)-([^-&]+)")
_COLE = re.compile(r"coleccion\.php\?id=(\d+)")
_CANON = {"especial": "special", "alternativa": "variant", "limitada": "limited"}


def _kv(url):
    m = _ITEM.search(url or "")
    return (_CANON.get(m.group(1), m.group(1)), m.group(2)) if m else None


def _item_kv(it):
    """(kind,vol) del synthetic de la fila: primaria O sources[] (tras el dedup
    cross-source, gotcha #54, la primaria puede ser base/tienda y el synthetic
    vivir como source)."""
    kv = _kv(it.get("url", ""))
    if kv:
        return kv
    for s in it.get("sources", []) or []:
        kv = _kv(s.get("url", "") or "")
        if kv:
            return kv
    return None


def _expected(cid, session):
    try:
        cands = L.fetch_collection(int(cid), session)
    except Exception:
        return None  # fetch falló → no tocar
    exp = set()
    for c in cands:
        if c.score < 30:
            continue
        ok, _ = mw.is_collectible_edition(
            c.title, getattr(c, "description", "") or "", getattr(c, "signal_types", None) or [],
            getattr(c, "product_type", "") or "", isbn=getattr(c, "isbn", "") or "", url=c.url)
        if ok and _kv(c.url):
            exp.add(_kv(c.url))
    return exp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]
    coles = sorted({_COLE.search(it.get("url", "")).group(1)
                    for it in items if _COLE.search(it.get("url", "") or "")})
    print(f"[reconcile] colecciones a verificar: {len(coles)}", flush=True)
    s = requests.Session(); s.headers["User-Agent"] = "manga-watch/0.2 (+reconcile)"
    exp_by_cole = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        for cid, exp in zip(coles, ex.map(lambda c: _expected(c, s), coles)):
            exp_by_cole[cid] = exp

    keep, remove = [], []
    for it in items:
        m = _COLE.search(it.get("url", "") or "")
        if not m:
            keep.append(it); continue
        cid = m.group(1)
        exp = exp_by_cole.get(cid)
        kv = _item_kv(it)
        if exp is None or kv is None or it.get("approved_at"):
            keep.append(it); continue  # fetch falló / old-format / aprobado → conservar
        if kv in exp:
            keep.append(it)
        else:
            remove.append(it)

    print(f"[reconcile] items SOBRANTES a quitar (parser ya no los genera): {len(remove)}", flush=True)
    by = {}
    for it in remove:
        by.setdefault(it.get("edition_key", ""), 0)
        by[it.get("edition_key", "")] += 1
    for ek, n in sorted(by.items(), key=lambda x: -x[1])[:30]:
        print(f"    {n:3}x  {ek}", flush=True)
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return
    if remove:
        mw.backup_and_rotate(ITEMS, "reconcile")
        mw.write_items_atomic(ITEMS, keep)
        print(f"[reconcile] escrito {ITEMS}: {len(items)} → {len(keep)}.", flush=True)


if __name__ == "__main__":
    main()
