#!/usr/bin/env python3
"""review_lista_chunk.py — auditoría INDEPENDIENTE de un chunk de la ingesta
lista.php. Re-fetchea cada coleccion del chunk, calcula qué items DEBERÍAN estar
en la DB (score>=30 + pasa is_collectible_edition, igual que el write-path), y
verifica que cada uno esté en items.jsonl. Reporta faltantes (= bug).

"Auditor de banco": verifica de forma independiente, no confía en los logs.

Uso:
  .venv/bin/python scripts/review_lista_chunk.py            # último chunk del checkpoint
  .venv/bin/python scripts/review_lista_chunk.py --from 0 --to 100
  .venv/bin/python scripts/review_lista_chunk.py --workers 6
"""
from __future__ import annotations
import json, sys, re, argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import requests
import wikis.listadomanga_collections as L
import manga_watch as mw

PROG = ROOT / "data" / "listadomanga_full_progress.json"
ITEMS = ROOT / "data" / "items.jsonl"
MIN_SCORE = 30


def _db_keys() -> set[str]:
    """cluster_keys lmc presentes en la DB (coleccion+kind+vol)."""
    keys = set()
    for l in ITEMS.open():
        if not l.strip():
            continue
        it = json.loads(l)
        u = it.get("url", "") or ""
        m = re.search(r"coleccion\.php\?id=(\d+)", u)
        if not m:
            for s in (it.get("sources") or []):
                m = re.search(r"coleccion\.php\?id=(\d+)", s.get("url", "") or "")
                if m:
                    break
        if m:
            keys.add(it.get("cluster_key", ""))
    return keys


def _expected(cid: int, session) -> dict:
    """Items que DEBERÍAN entrar de esta coleccion (replica el write-path)."""
    try:
        cands = L.fetch_collection(cid, session)
    except Exception as e:
        return {"cid": cid, "error": str(e)[:60], "expected": []}
    exp = []
    for c in cands:
        if c.score < MIN_SCORE:
            continue
        ok, _ = mw.is_collectible_edition(
            c.title, getattr(c, "description", "") or "", getattr(c, "signal_types", None) or [],
            getattr(c, "product_type", "") or "", isbn=getattr(c, "isbn", "") or "", url=c.url,
        )
        if not ok:
            continue
        m = re.search(r"item=([a-z]+)-([^-&]+)", c.url)
        kind, vol = (m.group(1), m.group(2)) if m else ("regular", "")
        exp.append({"cluster": f"lmc:{cid}:{kind}:{vol}", "kind": kind, "vol": vol, "title": c.title})
    return {"cid": cid, "expected": exp, "n_cands": len(cands)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", type=int, default=-1)
    ap.add_argument("--to", type=int, default=-1)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    state = json.loads(PROG.read_text())
    ids = state["lista_ids"]
    if args.frm >= 0 and args.to >= 0:
        frm, to = args.frm, args.to
    else:
        last = state["history"][-1]
        frm, to = last["from"], last["to"]
    chunk = ids[frm:to]
    print(f"=== AUDITORÍA chunk posiciones {frm}..{to} ({len(chunk)} colecciones) ===")

    s = requests.Session()
    s.headers["User-Agent"] = "manga-watch/0.2 (+chunk-audit)"
    db = _db_keys()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(lambda c: _expected(c, s), chunk))

    errors = [r for r in results if r.get("error")]
    total_expected = sum(len(r["expected"]) for r in results)
    missing = []
    coles_con_items = 0
    coles_vacias = []
    for r in results:
        if r.get("error"):
            continue
        if r["expected"]:
            coles_con_items += 1
        else:
            coles_vacias.append(r["cid"])
        for e in r["expected"]:
            if e["cluster"] not in db:
                missing.append((r["cid"], e["kind"], e["vol"], e["title"][:36]))

    print(f"  colecciones fetch OK: {len(results)-len(errors)}/{len(chunk)} | errores fetch: {len(errors)}")
    print(f"  colecciones con items coleccionables: {coles_con_items}")
    print(f"  colecciones SIN items (sin ed. especial/cofre): {len(coles_vacias)}")
    print(f"  items esperados en DB: {total_expected}")
    print(f"  items FALTANTES (esperados pero NO en DB): {len(missing)}")
    for cid, kind, vol, title in missing[:40]:
        print(f"      cole {cid} {kind}-{vol} | {title}")
    if errors:
        print(f"  errores de fetch (revisar): {[(r['cid'], r['error']) for r in errors[:10]]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
