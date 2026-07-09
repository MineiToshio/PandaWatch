#!/usr/bin/env python3
"""fix_edition_key_prefix.py — repara edition_keys cuyo prefijo no es el
series_key del item (invariante de formato: `{series_key}-{pub}-{slug}-{pais}`).

PROBLEMA (verificación 2026-06-11): 175 items con prefijo stale. Causa: cuando
`canonical_series_key()` re-canonicaliza el series_key DESPUÉS de acuñada la
key (o la key vino con la serie truncada a 35 chars, ej. "saint-seiya-les-
chevaliers-du-…"), el reemplazo por startswith del merge no matchea y el
prefijo queda viejo. Eso desalinea la edición de su serie (agrupación rota en
la UI y en el clustering).

FIX: `manga_watch.rebuild_edition_key_prefix()` (fuente única, también la usa
el merge de standardize_apply) parsea la cola `-{pub}-{slug}-{pais}[-cN]`
desde la derecha (slug del allowlist; publishers de dos tokens tipo
"ivrea-ar" probados primero) y re-arma la key con el series_key actual.
Re-deriva cluster_key y consolida. Respeta approved_at. Idempotente.

Uso:
  .venv/bin/python scripts/retrofit/fix_edition_key_prefix.py --dry-run
  .venv/bin/python scripts/retrofit/fix_edition_key_prefix.py
"""
from __future__ import annotations

import argparse
import json
import sys
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
    changed, unparsable, ex = 0, 0, []
    for it in items:
        if it.get("approved_at"):
            continue
        ek, sk = it.get("edition_key", "") or "", it.get("series_key", "") or ""
        if not ek or not sk:
            continue
        new = mw.rebuild_edition_key_prefix(ek, sk)
        if not new:
            # None = ya alineada O no parseable; solo es problema lo segundo.
            if not ek.startswith(sk + "-"):
                unparsable += 1
            continue
        if len(ex) < 25:
            ex.append((ek, new))
        it["edition_key"] = new
        it["cluster_key"] = mw.derive_cluster_key(it)
        changed += 1
    print(f"[ek-prefix] edition_key re-alineados con su series_key: {changed} "
          f"(no parseables: {unparsable})")
    for o, n in ex:
        print(f"    {o}  →  {n}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if changed:
        before = len(items)
        items = mw.consolidate_by_cluster(items)
        print(f"[ek-prefix] consolidate: {before} → {len(items)}")
        mw.backup_and_rotate(ITEMS, "ekprefix")
        mw.write_items_atomic(ITEMS, items)
        print(f"[ek-prefix] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
