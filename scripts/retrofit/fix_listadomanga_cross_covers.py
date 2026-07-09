#!/usr/bin/env python3
"""fix_listadomanga_cross_covers.py — corrige portadas CRUZADAS entre ediciones
distintas: un retrofit de cover-search (cuando los títulos eran idénticos) asignó
la MISMA imagen hi-res a items de COLECCIONES distintas (síntoma: mismo
`image_local` en items de colecciones distintas). Caso real: Ranma ½ Kanzenban
(EDT/Glénat 1553 vs Planeta 1978), Issak (3372 vs 2990).

Fix: a cada item afectado le devuelve SU propia portada de listadomanga (la del
parser para su coleccion+volumen). Pierde la hi-res cruzada pero queda CORRECTA;
search-covers puede re-mejorarla ahora que los títulos son distintos.

Uso:
  .venv/bin/python scripts/retrofit/fix_listadomanga_cross_covers.py --dry-run
  .venv/bin/python scripts/retrofit/fix_listadomanga_cross_covers.py
"""
from __future__ import annotations
import json, re, sys, argparse
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "wikis"))
import requests  # noqa: E402
import image_store  # noqa: E402
import listadomanga_collections as lmc  # noqa: E402
from manga_watch import backup_and_rotate, write_items_atomic  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"
_S = requests.Session(); _S.headers.update({"User-Agent": "Mozilla/5.0 (xcover)"})
_cache: dict[str, dict] = {}


def _cole(u: str):
    m = re.search(r"id=(\d+)", u or ""); return m.group(1) if m else None


def _key(u: str):
    m = re.search(r"item=([a-z]+)-([^-&]+)", u or "")
    return (m.group(1), m.group(2)) if m else None


def _real_portada(cid: str, kind: str, vol: str):
    if cid not in _cache:
        try:
            cands = lmc.fetch_collection(int(cid), _S)
        except Exception:
            cands = []
        m = {}
        byvol = {}
        for c in cands:
            k = _key(c.url)
            if k:
                m[k] = c.image_url
                byvol.setdefault(k[1], c.image_url)
        _cache[cid] = {"exact": m, "byvol": byvol}
    c = _cache[cid]
    # exacto (kind, vol); fallback por volumen (el edition-kind pudo cambiar
    # entre el parse viejo y el actual, ej. Issak especial→regular).
    return c["exact"].get((kind, vol)) or c["byvol"].get(vol, "")


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    byloc = defaultdict(list)
    for it in items:
        if "coleccion.php" not in (it.get("url", "") or ""):
            continue
        il = image_store.cover_local(it)
        if il:
            byloc[il].append(it)
    # cross-cover = mismo image_local en items de COLECCIONES distintas
    affected = []
    for il, g in byloc.items():
        if len({_cole(i.get("url", "")) for i in g}) > 1:
            affected.extend(g)

    changed, diffs = 0, []
    for it in affected:
        cid = _cole(it.get("url", "")); k = _key(it.get("url", ""))
        if not cid or not k:
            continue
        real = _real_portada(cid, k[0], k[1])
        # Resetear SIEMPRE (el local cruzado de la portada es lo que se ve, aunque
        # la url ya sea correcta). Solo saltamos si ya está limpio (portada = real
        # sin local, ya en images[0]).
        if not real or (image_store.cover_url(it) == real
                        and not image_store.cover_local(it)):
            continue
        if len(diffs) < 40:
            diffs.append((it.get("title", "")[:30], cid,
                          (image_store.cover_local(it) or "")[:14],
                          real.split("/")[-1][:16]))
        if not args.dry_run:
            # se re-espeja luego; la portada cruzada (local) era incorrecta
            it["images"] = [{"url": real, "local": "", "kind": "gallery", "description": ""}]
        changed += 1

    print(f"[xcover] items con portada cruzada corregidos: {changed}")
    for t, c, oldl, newp in diffs:
        print(f"    {t!r:32} col={c} local_cruzado={oldl} → portada_propia={newp}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    backup_and_rotate(ITEMS, "xcover")
    write_items_atomic(ITEMS, items)
    print(f"[xcover] escrito {ITEMS} ({changed}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
