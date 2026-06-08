#!/usr/bin/env python3
"""fix_raw_series_keys.py — re-deriva series_key/edition_key de los items RAW de
listadomanga (sin standardized_at) con el heurístico ARREGLADO (bug 2026-06-07:
`_normalize_series_name` dejaba el marcador "nº" → series_key "slam-dunk-no").

Efecto: (1) consistencia de series_key dentro de cada coleccion; (2) los items
raw pasan a tener el MISMO edition_key que sus contrapartes ya estandarizadas →
deduplican (consolidate los fusiona en vez de duplicar).

NO toca `title` (se conserva el título raw para no regresionar el display), NI
`standardized_at` (siguen raw → el skill LLM los procesa después).

Uso:
  .venv/bin/python scripts/retrofit/fix_raw_series_keys.py --dry-run
  .venv/bin/python scripts/retrofit/fix_raw_series_keys.py
"""
from __future__ import annotations
import json, sys, argparse, shutil
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import manga_watch as mw  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    changed, diffs = 0, []
    for it in items:
        if "coleccion.php" not in (it.get("url", "") or ""):
            continue
        if it.get("standardized_at"):
            continue  # solo raw; los estandarizados los maneja el skill
        cand = SimpleNamespace(
            title=it.get("title", ""), publisher=it.get("publisher", ""),
            language=it.get("language", ""), signal_types=it.get("signal_types") or [],
        )
        meta = mw.derive_series_metadata(cand)
        if not meta:
            continue
        new_sk = meta.get("series_key", "")
        new_ek = meta.get("edition_key", "")
        if not new_sk or (new_sk == it.get("series_key") and new_ek == it.get("edition_key")):
            continue
        if len(diffs) < 40:
            diffs.append((it.get("series_key"), new_sk, it.get("edition_key"), new_ek))
        if not args.dry_run:
            it["series_key"] = new_sk
            it["series_display"] = meta.get("series_display", "")
            it["edition_key"] = new_ek
            it["edition_display"] = meta.get("edition_display", "")
            it["cluster_key"] = mw.derive_cluster_key(it)
        changed += 1

    print(f"[raw-series] items raw con series_key/edition_key recomputado: {changed}")
    for osk, nsk, oek, nek in diffs[:30]:
        print(f"    sk {osk!r} → {nsk!r}   ek {oek!r} → {nek!r}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    # Consolidar: ahora los raw pueden tener el mismo cluster_key que los std → merge.
    from manga_watch import consolidate_by_cluster
    before = len(items)
    items = consolidate_by_cluster(items)
    print(f"[raw-series] consolidate: {before} → {len(items)} ({before - len(items)} fusionados)")
    shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-rawseries-bak"))
    tmp = ITEMS.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(ITEMS)
    print(f"[raw-series] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
