#!/usr/bin/env python3
"""fix_publisher_unknown_edition_key.py — reemplaza el segmento `-unknown-` del
`edition_key` por el slug REAL de la editorial cuando el item SÍ tiene el campo
`publisher` poblado (gotcha #45).

Causa: el `edition_key` (`{series}-{publisher_slug}-{edition}`) se generó cuando
la editorial no estaba en `_PUBLISHER_SLUG_MAP` (o antes de poblar `publisher`),
quedando `…-unknown-…` aunque la editorial es conocida (Norma, Planeta, Astiberri,
Ponent Mon, Ediciones B, etc.). Efecto: ediciones de editoriales distintas
colapsaban bajo el mismo slug `unknown`.

Fix determinístico: recomputa `mw._publisher_slug(publisher)`; si ya no es
'unknown', reemplaza la (única) ocurrencia de `-unknown-` en el edition_key y
recomputa cluster_key. NO toca series ni edition. Idempotente. Tras correr,
consolida (dos items que estaban separados por error podrían fusionar; o al revés
quedan bien separados por editorial).

Uso:
  .venv/bin/python scripts/retrofit/fix_publisher_unknown_edition_key.py --dry-run
  .venv/bin/python scripts/retrofit/fix_publisher_unknown_edition_key.py
"""
from __future__ import annotations
import json, sys, argparse, shutil
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

    changed, diffs = 0, []
    for it in items:
        ek = it.get("edition_key") or ""
        if "-unknown-" not in ek:
            continue
        pub = it.get("publisher") or ""
        slug = mw._publisher_slug(pub)
        if slug == "unknown":
            continue  # editorial sigue sin mapear → no tocar
        new_ek = ek.replace("-unknown-", f"-{slug}-", 1)
        if new_ek == ek:
            continue
        if len(diffs) < 40:
            diffs.append((pub, ek, new_ek))
        if not args.dry_run:
            it["edition_key"] = new_ek
            if it.get("edition_display"):
                pass  # display no incluye el slug; se conserva
            it["cluster_key"] = mw.derive_cluster_key(it)
        changed += 1

    print(f"[pub-unknown] edition_key con publisher real recomputado: {changed}")
    for pub, oek, nek in diffs[:40]:
        print(f"    {pub!r}: {oek}  →  {nek}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if changed:
        from manga_watch import consolidate_by_cluster
        before = len(items)
        items = consolidate_by_cluster(items)
        print(f"[pub-unknown] consolidate: {before} → {len(items)} ({before - len(items)} fusionados)")
        shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-pubunknown-bak"))
        tmp = ITEMS.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        tmp.replace(ITEMS)
        print(f"[pub-unknown] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
