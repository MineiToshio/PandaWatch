#!/usr/bin/env python3
"""collapse_baseurl_tomos.py — fusiona la fila "representante base-url" old-format
en su tomo SINTÉTICO del mismo (coleccion, volumen) (gotcha #56).

Síntoma: en la vista de edición un tomo aparece DOS veces con el MISMO título —
una fila con primaria `coleccion.php?id=N` (sin `item=`, kind del edition_slug, ej.
`kanzenban:2`) y otra con synthetic `item=regular-2` (kind del parser). Son el
MISMO tomo capturado en dos formatos (viejo sin synthetic vs nuevo). El dedup por
fuente sintética NO las une (no comparten `item=`), y DUPVOL las marca.

Fix: para cada coleccion, una fila base-url CON volumen se fusiona (merge_cluster)
en la fila sintética del mismo volumen — preferentemente la `regular` (el tomo
numerado); si no hay regular, la primera sintética. El resultado conserva el
cluster_key SINTÉTICO (autoritativo) y une sources/imágenes. Si no hay hermana
sintética para ese volumen, la fila base-url se conserva (es un representante
legítimo: artbook/boxset de 1 item). Idempotente. Respeta `approved_at`.

Uso:
  .venv/bin/python scripts/retrofit/collapse_baseurl_tomos.py --dry-run
  .venv/bin/python scripts/retrofit/collapse_baseurl_tomos.py
"""
from __future__ import annotations
import json, re, sys, argparse, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from manga_watch import (  # noqa: E402
        merge_cluster, derive_cluster_key, backup_and_rotate, write_items_atomic,
    )
except ImportError:
    from scripts.manga_watch import (  # noqa: E402
        merge_cluster, derive_cluster_key, backup_and_rotate, write_items_atomic,
    )

ITEMS = ROOT / "data" / "items.jsonl"
_COLE = re.compile(r"coleccion\.php\?id=(\d+)")
_BASEURL = re.compile(r"listadomanga\.es/coleccion\.php\?id=\d+$")  # sin &item=
_LMC = re.compile(r"^lmc:(\d+):([a-z]+):(.*)$")


def _is_baseurl(it):
    return bool(_BASEURL.search(it.get("url", "") or ""))


def _has_syn(it):
    if "item=" in (it.get("url", "") or ""):
        return True
    return any("item=" in (s.get("url", "") or "") for s in (it.get("sources") or []))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    # index por (cole, vol) de filas SINTÉTICAS
    by_cv_syn = collections.defaultdict(list)
    for it in items:
        m = _COLE.search(it.get("url", "") or "")
        if not m or not _has_syn(it):
            continue
        vol = (it.get("volume") or "").strip()
        by_cv_syn[(m.group(1), vol)].append(it)

    drop_idx = set()
    merges = []  # (baseurl_it, target_it)
    for i, it in enumerate(items):
        # SÓLO phantoms puros: primaria base-url Y SIN fuente sintética propia. Una
        # fila base-url que SÍ tiene su `item=` en sources (ej. Seven Deadly Sins
        # regular:41, Promised regular:13) es un PRODUCTO real (regular que coexiste
        # con el especial del mismo vol) — NO se debe fusionar al especial.
        if not _is_baseurl(it) or _has_syn(it) or it.get("approved_at"):
            continue
        m = _COLE.search(it.get("url", "") or "")
        vol = (it.get("volume") or "").strip()
        if not m or not vol:
            continue
        sibs = [s for s in by_cv_syn.get((m.group(1), vol), []) if s is not it]
        if not sibs:
            continue

        def _kind(s):
            mm = _LMC.match(s.get("cluster_key", "") or "")
            return mm.group(2) if mm else ""
        # preferir hermana regular (el tomo numerado); si no, la primera
        target = next((s for s in sibs if _kind(s) == "regular"), None) or sibs[0]
        merges.append((it, target))
        drop_idx.add(i)

    # aplicar merges: agrupar por target
    by_target = collections.defaultdict(list)
    tgt_id = {id(t): t for _, t in merges}
    for src, t in merges:
        by_target[id(t)].append(src)

    print(f"[collapse-baseurl] filas base-url a fusionar en su tomo sintético: {len(merges)}")
    for src, t in merges[:25]:
        print(f"    {src.get('cluster_key')} → {t.get('cluster_key')}  | {t.get('title')!r}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if not merges:
        return 0

    # construir salida: para cada target, merge_cluster([target]+sources); drop base-urls
    out = []
    for i, it in enumerate(items):
        if i in drop_idx:
            continue
        if id(it) in by_target:
            group = [it] + by_target[id(it)]
            keep_ck = it.get("cluster_key")
            merged = merge_cluster(group)
            merged["url"] = it.get("url")            # mantener la primaria sintética
            merged["cluster_key"] = keep_ck          # autoritativo (sintético)
            out.append(merged)
        else:
            out.append(it)

    backup_and_rotate(ITEMS, "collapsebaseurl")
    write_items_atomic(ITEMS, out)
    print(f"[collapse-baseurl] escrito {ITEMS}: {len(items)} → {len(out)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
