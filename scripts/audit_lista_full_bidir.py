#!/usr/bin/env python3
"""audit_lista_full_bidir.py — auditoría INDEPENDIENTE y BIDIRECCIONAL de TODA la
ingesta de listadomanga. Re-fetchea cada coleccion de lista.php y compara, por
(kind, vol), lo que el parser ACTUAL considera coleccionable contra lo que está en
la DB:
  - FALTANTES: el parser lo emite (score≥30 + gate) pero NO está en la DB.
  - SOBRANTES: está en la DB (con synthetic URL item=) pero el parser ACTUAL ya
    NO lo emite → posible falso positivo / data vieja del parser buggy.

Cobertura: confirma que las 3436 colecciones de lista.php se fetchean OK.
"""
from __future__ import annotations
import json, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import requests
import wikis.listadomanga_collections as L
import manga_watch as mw

PROG = ROOT / "data" / "listadomanga_full_progress.json"
ITEMS = ROOT / "data" / "items.jsonl"
_ITEM = re.compile(r"item=([a-z]+)-([^-&]+)")
_CANON = {"especial": "special", "alternativa": "variant", "limitada": "limited"}


def _kv(url):
    m = _ITEM.search(url or "")
    if not m:
        return None
    return (_CANON.get(m.group(1), m.group(1)), m.group(2))


def _db_by_cole():
    """{cid: set((kind,vol))} para items de la DB con synthetic URL. Escanea la
    URL primaria Y las `sources[]` — tras el dedup cross-source (gotcha #54) la
    primaria puede ser una tienda y el synthetic de listadomanga vive como source."""
    db = {}
    for l in ITEMS.open():
        if not l.strip():
            continue
        it = json.loads(l)
        urls = [it.get("url", "") or ""]
        urls += [s.get("url", "") or "" for s in (it.get("sources") or [])]
        for u in urls:
            m = re.search(r"coleccion\.php\?id=(\d+)", u)
            kv = _kv(u)
            if m and kv:
                db.setdefault(m.group(1), set()).add(kv)
    return db


def _expected(cid, session):
    try:
        cands = L.fetch_collection(int(cid), session)
    except Exception as e:
        return cid, None, str(e)[:40]
    exp = set()
    for c in cands:
        if c.score < 30:
            continue
        ok, _ = mw.is_collectible_edition(
            c.title, getattr(c, "description", "") or "", getattr(c, "signal_types", None) or [],
            getattr(c, "product_type", "") or "", isbn=getattr(c, "isbn", "") or "", url=c.url)
        if not ok:
            continue
        kv = _kv(c.url)
        if kv:
            exp.add(kv)
    return cid, exp, None


def main():
    state = json.loads(PROG.read_text())
    ids = [str(i) for i in state["lista_ids"]]
    print(f"=== AUDITORÍA BIDIRECCIONAL ({len(ids)} colecciones de lista.php) ===", flush=True)
    db = _db_by_cole()
    s = requests.Session(); s.headers["User-Agent"] = "manga-watch/0.2 (+bidir-audit)"
    fetch_err = []
    missing = []   # (cid, kind, vol)
    extra = []     # (cid, kind, vol)
    n_ok = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        for cid, exp, err in ex.map(lambda c: _expected(c, s), ids):
            if err is not None:
                fetch_err.append((cid, err)); continue
            n_ok += 1
            have = db.get(cid, set())
            for kv in exp - have:
                missing.append((cid, kv[0], kv[1]))
            for kv in have - exp:
                extra.append((cid, kv[0], kv[1]))
    print(f"colecciones fetch OK: {n_ok}/{len(ids)} | errores fetch: {len(fetch_err)}", flush=True)
    print(f"FALTANTES (parser sí, DB no): {len(missing)}", flush=True)
    for cid, k, v in missing[:40]:
        print(f"    cole {cid} {k}-{v}", flush=True)
    print(f"SOBRANTES (DB sí, parser actual no): {len(extra)}", flush=True)
    bycole = {}
    for cid, k, v in extra:
        bycole.setdefault(cid, []).append(f"{k}-{v}")
    for cid in list(bycole)[:40]:
        print(f"    cole {cid}: {bycole[cid][:6]}", flush=True)
    if fetch_err:
        print(f"errores fetch (revisar): {fetch_err[:10]}", flush=True)
    print("AUDIT DONE", flush=True)


if __name__ == "__main__":
    main()
