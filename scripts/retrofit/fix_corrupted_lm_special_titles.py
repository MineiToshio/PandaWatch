#!/usr/bin/env python3
"""fix_corrupted_lm_special_titles.py — reconstruye el TÍTULO de los tomos de
listadomanga cuyo `title` quedó corrompido por el skill VIEJO de standardize
(gotcha #93).

SÍNTOMA (reportado por el owner 2026-06-13): "Pájaro que trina no vuela no
Special Edition Edición Especial" — sin el número de volumen y con el tipo de
edición DUPLICADO en inglés + español.

CAUSA: el skill viejo de standardize (pre-política de títulos 2026-06-12)
reescribía `title` traduciendo la edición a inglés ("Edición Especial" →
"Special Edition") y destruyendo el marcador de volumen ("nº9" → "no", perdiendo
el 9). Ese título mangleado quedó guardado como `title_original`, y
`restore_official_titles.py` lo propagó de vuelta a `title`. Después el enforcer
(`fix_lmc_display_titles` → `normalize_display_title`) re-apendaba "Edición
Especial" en español SIN remover el "Special Edition" inglés → duplicación.

FIX DE MECANISMO (durable, ya aplicado): `normalize_display_title` ahora también
remueve "Special Edition" (EN) antes de re-apendar el marcador español, así no se
vuelve a duplicar desde ninguna fuente.

ESTE RETROFIT (one-shot, limpieza de datos legacy): para cada tomo de
listadomanga cuyo `title` todavía arrastra un qualifier de edición en inglés,
reconstruye el título desde la FUENTE CONFIABLE — el `description`, que preserva
el `collection_title` scrapeado tal cual ("Serie nº9 (de 9 y abierta) - Edición
Especial + extras") — reusando `normalize_display_title` (única fuente de verdad
del título de display de listadomanga). Restaura el volumen y deja UN solo
marcador en español.

Idempotente (tras correrlo, el título ya no contiene el qualifier inglés → no
re-matchea). Respeta `approved_at`. Re-deriva cluster_key y consolida.

Uso:
  .venv/bin/python scripts/retrofit/fix_corrupted_lm_special_titles.py --dry-run
  .venv/bin/python scripts/retrofit/fix_corrupted_lm_special_titles.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import manga_watch as mw  # noqa: E402
from wikis.listadomanga_collections import (  # noqa: E402
    VOLUME_PATTERN,
    normalize_display_title,
)

ITEMS = ROOT / "data" / "items.jsonl"

# Firma de corrupción: el título arrastra un qualifier de edición en INGLÉS
# (el skill viejo tradujo la edición). Los títulos limpios de listadomanga llevan
# el marcador en español ("Edición Especial"/"Edición Limitada"), nunca en inglés.
_EN_EDITION_RESIDUE = re.compile(
    r"\b(?:Special|Limited|Collector'?s|Deluxe)\s+Edition\b", re.IGNORECASE)
# Mangle de la partícula de volumen: el skill viejo dejó "nº10" como "no" pegado
# al tipo de edición traducido ("…amor no Fanbook"). Firma de alta precisión.
_NO_PARTICLE_MANGLE = re.compile(
    r"\bno\s+(?:Special|Limited|Collector|Deluxe|Fanbook|Artbook|Guidebook|"
    r"Box|Coffret|Bonus)\b", re.IGNORECASE)
_CL_KIND = re.compile(r"^lmc:\d+:([a-z]+):")
_CL_COLE = re.compile(r"^(lmc:\d+):")
# Cortes para aislar la serie cuando el collection_title no trae volumen.
_SERIES_CUT = re.compile(r"\s*[-(]|\bedici[oó]n\b|\bspecial\b|\blimited\b", re.IGNORECASE)
# Título de display de un tomo limpio que termina en su volumen ("Fruits Basket 3").
_TRAILING_VOL = re.compile(r"\s+(\d+)\s*$")


def _cole(it: dict) -> str:
    m = _CL_COLE.match(it.get("cluster_key", "") or "")
    return m.group(1) if m else ""


def _is_lm_collection(it: dict) -> bool:
    urls = [it.get("url", "") or ""] + [
        s.get("url", "") or "" for s in (it.get("sources") or [])
    ]
    return any("coleccion.php" in u for u in urls)


def _kind(it: dict) -> str:
    m = _CL_KIND.match(it.get("cluster_key", "") or "")
    if m:
        return m.group(1)
    return (it.get("lm_kind") or "regular")


def _collection_title(desc: str) -> str:
    """El segmento `collection_title` del description (`{pub} · {cat} ·
    {collection_title} · {autor?}`): el primero —saltando la editorial— que trae
    un nº o un qualifier de edición."""
    parts = [p.strip() for p in (desc or "").split(" · ") if p.strip()]
    for p in parts[1:]:
        if VOLUME_PATTERN.search(p) or re.search(r"edici[oó]n|edition", p, re.I):
            return p
    return ""


def rebuild_title(desc: str, kind: str) -> str:
    """Reconstruye el título de display desde el collection_title scrapeado."""
    ct = _collection_title(desc)
    if not ct:
        return ""
    m = VOLUME_PATTERN.search(ct)
    if m:
        series = ct[: m.start()].strip()
        raw = f"{series} nº{m.group(1)}"
    else:
        series = _SERIES_CUT.split(ct, maxsplit=1)[0].strip()
        raw = series
    if not series:
        return ""
    return normalize_display_title(raw, kind)


def _sibling_stem(cole_items: list[dict]) -> str:
    """Stem de serie tomado de un tomo HERMANO limpio de la misma colección (su
    nombre scrapeado, no el canónico): el primer título sin residuo de edición en
    inglés que termina en su volumen ("Fruits Basket 3" → "Fruits Basket"). Sirve
    de fallback cuando el `description` quedó contaminado (ej. metadata de tienda
    de un merge cross-source) y no da un collection_title reconstruible."""
    for sib in cole_items:
        st = (sib.get("title") or "").strip()
        if not st or _EN_EDITION_RESIDUE.search(st):
            continue
        m = _TRAILING_VOL.search(st)
        if m:
            return st[: m.start()].strip()
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]
    by_cole: dict[str, list[dict]] = {}
    for it in items:
        c = _cole(it)
        if c:
            by_cole.setdefault(c, []).append(it)
    changed, skipped_norebuild, ex = 0, 0, []
    for it in items:
        if it.get("approved_at"):
            continue
        old = it.get("title", "") or ""
        if not (_EN_EDITION_RESIDUE.search(old) or _NO_PARTICLE_MANGLE.search(old)):
            continue
        if not _is_lm_collection(it):
            continue
        kind = _kind(it)
        new = rebuild_title(it.get("description", ""), kind)
        if not new:
            # Fallback: el description está contaminado (metadata de tienda). Tomar
            # el stem de un hermano limpio de la misma colección + el volumen propio.
            stem = _sibling_stem(by_cole.get(_cole(it), []))
            vol = (it.get("volume") or "").strip()
            if stem:
                raw = f"{stem} nº{vol}" if vol else stem
                new = normalize_display_title(raw, kind)
        if not new:
            skipped_norebuild += 1
            continue
        if new != old:
            if len(ex) < 30:
                ex.append((old, new))
            it["title"] = new
            it["cluster_key"] = mw.derive_cluster_key(it)
            changed += 1
    print(f"[lm-corrupt-titles] títulos reconstruidos: {changed}")
    if skipped_norebuild:
        print(f"[lm-corrupt-titles] sin collection_title reconstruible: {skipped_norebuild}")
    for o, n in ex:
        print(f"    {o!r}  →  {n!r}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if changed:
        before = len(items)
        items = mw.consolidate_by_cluster(items)
        print(f"[lm-corrupt-titles] consolidate: {before} → {len(items)}")
        mw.backup_and_rotate(ITEMS, "lmcorrupt")
        mw.write_items_atomic(ITEMS, items)
        print(f"[lm-corrupt-titles] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
