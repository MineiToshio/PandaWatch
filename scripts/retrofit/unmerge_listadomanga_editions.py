#!/usr/bin/env python3
"""unmerge_listadomanga_editions.py — repara items de listadomanga que un
`consolidate` histórico FUSIONÓ entre colecciones distintas (= ediciones
distintas, gotcha #42) cuando compartían el mismo edition_key+volumen ERRÓNEO.

Cada `source[]` retiene su propia cover (image_url/image_local), precio y fecha,
así que podemos SEPARAR la fila fusionada en una fila por colección, atribuyendo
las imágenes del carrusel por archivo local / hash del disambiguador.

Uso:
  .venv/bin/python scripts/retrofit/unmerge_listadomanga_editions.py --dry-run
  .venv/bin/python scripts/retrofit/unmerge_listadomanga_editions.py
"""
from __future__ import annotations
import json, re, sys, argparse, shutil, copy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "wikis"))
import requests  # noqa: E402
import listadomanga_collections as lmc  # noqa: E402
from manga_watch import derive_cluster_key  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"
KIND_SLUG = {"especial": "special", "limitada": "limited", "alternativa": "variant",
             "pack": "boxset", "box": "boxset"}
TITLE_SIGNAL_SLUG = [("artbook", "artbook"), ("fanbook", "fanbook"), ("guidebook", "guidebook"),
                     ("kanzenban", "kanzenban"), ("omnibus", "integral"), ("deluxe", "deluxe"),
                     ("special_edition", "special"), ("variant_cover", "variant")]
SLUG_DISPLAY = {"regular": "", "artbook": "Artbook", "fanbook": "Fanbook", "guidebook": "Guidebook",
                "boxset": "Box Set", "kanzenban": "Kanzenban", "integral": "Edición Integral",
                "deluxe": "Deluxe", "special": "Edición Especial", "limited": "Edición Limitada",
                "variant": "Variant"}

_S = requests.Session(); _S.headers.update({"User-Agent": "Mozilla/5.0 (unmerge)"})
_title_cache: dict[str, str] = {}


def _coleccion(url: str) -> str | None:
    m = re.search(r"coleccion\.php\?id=(\d+)", url or "")
    return m.group(1) if m else None


def _kind_vol_hash(url: str):
    m = re.search(r"item=([a-z]+)-([^-&]+)(?:-([0-9a-f]+))?", url or "")
    return (m.group(1), m.group(2), m.group(3) or "") if m else ("regular", "", "")


def _fetch_title(cid: str) -> str:
    if cid in _title_cache:
        return _title_cache[cid]
    try:
        t = _S.get(f"https://www.listadomanga.es/coleccion.php?id={cid}", timeout=(10, 30)).text
        m = re.search(r"<h2[^>]*>([\s\S]*?)</h2>", t)
        title = re.sub("<[^>]+>", "", m.group(1)).strip() if m else ""
    except requests.RequestException:
        title = ""
    _title_cache[cid] = title
    return title


def _slug_for(kind: str, coleccion_title: str) -> str:
    if kind in KIND_SLUG:
        return KIND_SLUG[kind]
    sigs = set(lmc._detect_edition_title_signals(coleccion_title)) | \
        set(lmc._detect_collection_type_signals(coleccion_title))
    for sig, slug in TITLE_SIGNAL_SLUG:
        if sig in sigs:
            return slug
    return "regular"


def _publisher_slug(edition_key: str, series_key: str) -> str:
    if edition_key.startswith(series_key + "-"):
        rem = edition_key[len(series_key) + 1:]
        if "-" in rem:
            return rem.rsplit("-", 1)[0]
    return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    out = []
    split_count = 0
    for it in items:
        srcs = it.get("sources") or []
        cids = {_coleccion(s.get("url", "")) for s in srcs}
        cids.discard(None)
        cids.add(_coleccion(it.get("url", "")))
        cids.discard(None)
        if "coleccion.php" not in (it.get("url", "") or "") or len(cids) < 2:
            out.append(it); continue

        # FUSIÓN entre colecciones → split por source.
        sk = it.get("series_key", ""); sd = it.get("series_display", "")
        pub = _publisher_slug(it.get("edition_key", ""), sk)
        imgs = it.get("images") or []
        extras = it.get("extras") or []
        # Pre-calcular el edition_key de cada source para detectar colisiones:
        # si 2 colecciones distintas mapean al MISMO edition_key, hay que
        # desambiguar por coleccion (-cN), sino re-mergean en el próximo
        # consolidate (bug: Candy Candy 190/191, Magic Knight Rayearth 245/322).
        _ek_for = {}
        for s in srcs:
            cid_s = _coleccion(s.get("url", ""))
            kind_s, _, _ = _kind_vol_hash(s.get("url", ""))
            _ek_for.setdefault(f"{sk}-{pub}-{_slug_for(kind_s, _fetch_title(cid_s))}", set()).add(cid_s)
        _ek_collide = {ek for ek, cids in _ek_for.items() if len(cids) > 1}
        for s in srcs:
            s_url = s.get("url", "")
            cid = _coleccion(s_url)
            if not cid:
                continue
            kind, vol, h = _kind_vol_hash(s_url)
            ct = _fetch_title(cid)
            slug = _slug_for(kind, ct)
            new = copy.deepcopy(it)
            new["url"] = s_url
            new["sources"] = [s]
            for k in ("image_url", "image_local", "release_date", "score"):
                if k in s:
                    new[k] = s[k]
            new["volume"] = vol if vol.isdigit() else new.get("volume", "")
            _ek_base = f"{sk}-{pub}-{slug}"
            # Si este edition_key colisiona con otra coleccion del mismo item,
            # desambiguar por coleccion para que NO re-mergeen (coleccion=edicion).
            new["edition_key"] = (f"{_ek_base}-c{cid}" if _ek_base in _ek_collide else _ek_base) if sk else new.get("edition_key", "")
            suffix = SLUG_DISPLAY.get(slug, "")
            if sd:
                # Best-effort: sources[] no guarda el título oficial por-fuente,
                # así que al separar se reconstruye un título distinguible.
                # (Única excepción tolerada a la política de títulos 2026-06-12;
                # herramienta de reparación manual, fuera del pipeline canónico.)
                new["title"] = " ".join(x for x in [sd, suffix, new.get("volume", "")] if x).strip()
            new["edition_display"] = suffix
            # Atribuir imágenes: las que matchean el cover local del source, o cuyo
            # hash matchea el disambiguador del source url, o extras de este source.
            s_local = s.get("image_local", "")
            s_imgurl = s.get("image_url", "")
            mine = []
            for im in imgs:
                iu = im.get("url", ""); il = im.get("local", "")
                if (il and il == s_local) or (s_imgurl and iu == s_imgurl) or (h and h[:16] in iu):
                    mine.append(im)
            if not mine and s_imgurl:
                mine = [{"url": s_imgurl, "local": s_local, "kind": "gallery", "description": ""}]
            new["images"] = mine
            # extras de este source: los cuyo hash matchea el disambiguador.
            new["extras"] = [e for e in extras if (h and any(h[:16] in (im.get("url", "") or "")
                             for im in mine if im.get("kind") == "extra"))] if kind == "regular" else []
            new["cluster_key"] = derive_cluster_key(new)  # recomputar (deepcopy traía el viejo)
            out.append(new)
            split_count += 1
        print(f"  SPLIT {it.get('title','')[:34]!r} ({len(srcs)} colecciones {sorted(cids)})")

    print(f"\n[unmerge] items fusionados detectados: "
          f"{sum(1 for _ in items) - sum(1 for x in out if True) + split_count} "
          f"→ {split_count} items separados")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-unmerge-bak"))
    tmp = ITEMS.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for it in out:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(ITEMS)
    print(f"[unmerge] escrito {ITEMS}. Backup: {ITEMS.with_suffix('.jsonl.pre-unmerge-bak')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
