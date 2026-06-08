#!/usr/bin/env python3
"""fix_doble_sobrecubierta_falsepos.py — quita del corpus los items de listadomanga
que entraron por el FALSO POSITIVO "doble sobrecubierta → kanzenban" (gotcha #51).

Una doble sobrecubierta es cosmética (común en ediciones REGULARES), NO una Kanzenban.
El parser ya está arreglado (se removió la regla). Este retrofit reconcilia el corpus:
re-parsea cada coleccion afectada con el parser ACTUAL y, por item, quita los que ya
NO califican (score>=30 + gate). Los que siguen calificando por OTRA señal real
(ej. "Master Edition"/"Ultimate Edition" en el título) se conservan.

NO toca items aprobados (`approved_at`) — respeta curación manual.

Uso:
  .venv/bin/python scripts/retrofit/fix_doble_sobrecubierta_falsepos.py --dry-run
  .venv/bin/python scripts/retrofit/fix_doble_sobrecubierta_falsepos.py
"""
from __future__ import annotations
import json, re, sys, argparse, shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import requests
import wikis.listadomanga_collections as L
import manga_watch as mw

ITEMS = ROOT / "data" / "items.jsonl"
_COLE = re.compile(r"coleccion\.php\?id=(\d+)")
_ITEM = re.compile(r"item=([a-z]+)-([^-&]+)")


def _valid_clusters(cid: str, session) -> set[str]:
    """Clusters lmc que el parser ACTUAL considera válidos para esta coleccion."""
    try:
        cands = L.fetch_collection(int(cid), session)
    except Exception:
        return None  # error de fetch → no tocar esta coleccion (conservador)
    out = set()
    for c in cands:
        if c.score < 30:
            continue
        ok, _ = mw.is_collectible_edition(
            c.title, getattr(c, "description", "") or "", getattr(c, "signal_types", None) or [],
            getattr(c, "product_type", "") or "", isbn=getattr(c, "isbn", "") or "", url=c.url)
        if not ok:
            continue
        m = _ITEM.search(c.url)
        if m:
            out.add(m.group(2))  # volumen válido (cualquier kind)
    return out  # set de VOLÚMENES que el parser arreglado sigue considerando coleccionables


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    # colecciones a reconciliar: las que tienen algún item con edition kanzenban
    # (la regla removida sólo producía kanzenban).
    coles = set()
    for it in items:
        m = _COLE.search(it.get("url", "") or "")
        if m and "kanzenban" in (it.get("edition_key") or ""):
            coles.add(m.group(1))
    print(f"[falsepos] colecciones kanzenban a reconciliar: {len(coles)}")

    s = requests.Session(); s.headers["User-Agent"] = "manga-watch/0.2 (+falsepos)"
    valid: dict[str, set] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for cid, vc in zip(sorted(coles), ex.map(lambda c: _valid_clusters(c, s), sorted(coles))):
            valid[cid] = vc

    remove, keep = [], []
    for it in items:
        m = _COLE.search(it.get("url", "") or "")
        if not m or m.group(1) not in coles:
            keep.append(it); continue
        cid = m.group(1)
        vc = valid.get(cid)
        if vc is None:  # error de fetch → conservar
            keep.append(it); continue
        if it.get("approved_at"):  # curación manual → conservar
            keep.append(it); continue
        # quitar SÓLO si el VOLUMEN del item ya no es coleccionable según el parser
        # arreglado (conservador: un kanzenban genuino mantiene sus vols; un dup
        # viejo de formato distinto pero mismo vol NO se toca acá).
        m2 = _ITEM.search(it.get("url", "") or "")
        vol = m2.group(2) if m2 else None
        if vol is not None and vol not in vc:
            remove.append(it)  # falso positivo (vol ya no califica) → quitar
        else:
            keep.append(it)

    print(f"[falsepos] items a QUITAR (ya no califican): {len(remove)}")
    by_ek = {}
    for it in remove:
        by_ek.setdefault(it.get("edition_key", ""), 0)
        by_ek[it.get("edition_key", "")] += 1
    for ek, n in sorted(by_ek.items(), key=lambda x: -x[1])[:30]:
        print(f"    {n:3}x  {ek}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if remove:
        shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-falsepos-bak"))
        tmp = ITEMS.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for it in keep:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        tmp.replace(ITEMS)
        print(f"[falsepos] escrito {ITEMS}: {len(items)} → {len(keep)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
