#!/usr/bin/env python3
"""merge_crosssource_into_lmc.py — fusiona una ficha cross-source (tienda/búsqueda,
cluster `edition:`/`url:`) en su tomo de listadomanga (`lmc:`) cuando son el MISMO
producto: mismo edition_key + mismo volumen + MISMO título (gotcha #56).

Síntoma: un tomo aparece dos veces en la edición — la fila de listadomanga (lmc,
tier-0) y la ficha de tienda (edition:, tier-1) NO se fusionan porque su cluster_key
difiere por tier, aunque sean el mismo tomo (ej. Fruits Basket Collector 3 de Casa
del Libro + de listadomanga). La de listadomanga es canónica (tier-0); absorbe la
URL de tienda como SOURCE (gana un link de compra). Conservador: exige título
idéntico (case-insensitive) para no fusionar variantes distintas. Respeta
`approved_at`. Idempotente.

Uso:
  .venv/bin/python scripts/retrofit/merge_crosssource_into_lmc.py --dry-run
  .venv/bin/python scripts/retrofit/merge_crosssource_into_lmc.py
"""
from __future__ import annotations
import json, re, sys, argparse, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from manga_watch import merge_cluster, backup_and_rotate, write_items_atomic  # noqa: E402
except ImportError:
    from scripts.manga_watch import merge_cluster, backup_and_rotate, write_items_atomic  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"
_LMC = re.compile(r"^lmc:")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    by_ev = collections.defaultdict(list)
    for it in items:
        ek = it.get("edition_key") or ""
        vol = (it.get("volume") or "").strip()
        if ek and vol:
            by_ev[(ek, vol)].append(it)

    drop = set()
    absorb = collections.defaultdict(list)  # id(lmc_row) -> [crosssource rows]
    lmc_by_id = {}
    ex = []
    for (ek, vol), grp in by_ev.items():
        lmcs = [it for it in grp if _LMC.match(it.get("cluster_key", "") or "")]
        others = [it for it in grp if not _LMC.match(it.get("cluster_key", "") or "")]
        if len(lmcs) != 1 or not others:
            continue
        lmc = lmcs[0]
        ltitle = (lmc.get("title") or "").strip().lower()
        for o in others:
            if o.get("approved_at"):
                continue
            if (o.get("title") or "").strip().lower() == ltitle:
                absorb[id(lmc)].append(o)
                lmc_by_id[id(lmc)] = lmc
                drop.add(id(o))
                if len(ex) < 25:
                    ex.append((o.get("cluster_key"), lmc.get("cluster_key"), lmc.get("title")))

    print(f"[merge-xsrc] fichas cross-source fusionadas en su tomo lmc: {len(drop)}")
    for oc, lc, t in ex:
        print(f"    {oc} → {lc}  | {t!r}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if not drop:
        return 0
    out = []
    for it in items:
        if id(it) in drop:
            continue
        if id(it) in absorb:
            keep_ck = it.get("cluster_key")
            keep_url = it.get("url")
            merged = merge_cluster([it] + absorb[id(it)])
            merged["cluster_key"] = keep_ck   # lmc canónico
            merged["url"] = keep_url
            out.append(merged)
        else:
            out.append(it)
    backup_and_rotate(ITEMS, "mergexsrc")
    write_items_atomic(ITEMS, out)
    print(f"[merge-xsrc] escrito {ITEMS}: {len(items)} → {len(out)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
