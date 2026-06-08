#!/usr/bin/env python3
"""fix_listadomanga_title_collisions.py — desambigua TÍTULOS de display que
colisionan entre EDICIONES distintas de la misma obra (gotcha #42): dos
ediciones (publishers/idiomas distintos) con el mismo `title` se ven idénticas
en el volume-view aunque su `edition_key` las distinga.

Caso real: "Saint Seiya Integral 1" en EDT/Glénat y en Planeta; "Rurouni Kenshin
Integral N" en Glénat y Panini. standardize no metió la editorial en el título.

Disambiguador por prioridad (lo que realmente las diferencia):
  1. editorial (si difieren) → "Título (Planeta)"
  2. idioma (misma editorial, distinto idioma) → "Título (Català)"
  3. año de publicación (misma editorial e idioma, distinto año) → "Título (2013)"
  4. coleccion id (último recurso) → "Título (col. 248)"

Uso:
  .venv/bin/python scripts/retrofit/fix_listadomanga_title_collisions.py --dry-run
  .venv/bin/python scripts/retrofit/fix_listadomanga_title_collisions.py
"""
from __future__ import annotations
import json, re, sys, argparse, shutil
from pathlib import Path
from collections import defaultdict

ITEMS = Path(__file__).resolve().parents[2] / "data" / "items.jsonl"

# Etiqueta corta de editorial a partir del campo `publisher`.
PUB_LABEL = [
    (re.compile(r"planeta", re.I), "Planeta"), (re.compile(r"norma", re.I), "Norma"),
    (re.compile(r"panini", re.I), "Panini"), (re.compile(r"ivrea", re.I), "Ivrea"),
    (re.compile(r"gl[ée]nat", re.I), "Glénat"), (re.compile(r"\bedt\b", re.I), "EDT"),
    (re.compile(r"milky", re.I), "Milky Way"), (re.compile(r"\becc\b", re.I), "ECC"),
    (re.compile(r"distrito", re.I), "Distrito"), (re.compile(r"tomodomo", re.I), "Tomodomo"),
    (re.compile(r"kitsune", re.I), "Kitsune"), (re.compile(r"arechi", re.I), "Arechi"),
    (re.compile(r"mangaline", re.I), "MangaLine"), (re.compile(r"fandogamia", re.I), "Fandogamia"),
]


def pub_label(publisher: str) -> str:
    for rx, lab in PUB_LABEL:
        if rx.search(publisher or ""):
            return lab
    return (publisher or "").split()[0] if publisher else ""


def coleccion(url: str) -> str:
    m = re.search(r"coleccion\.php\?id=(\d+)", url or "")
    return m.group(1) if m else "?"


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    groups = defaultdict(list)
    for it in items:
        if "coleccion.php" not in (it.get("url", "") or "") or not it.get("edition_key"):
            continue
        key = (it.get("series_key", ""), re.sub(r"\s+", " ", (it.get("title", "") or "")).strip().lower())
        groups[key].append(it)

    changed = 0
    diffs = []
    for (sk, _), g in groups.items():
        if len({i.get("edition_key") for i in g}) < 2:
            continue  # no es colisión entre ediciones distintas
        def year(it):
            return (it.get("release_date", "") or "")[:4]
        def tag_for(it, mode):
            if mode == "pub":
                return pub_label(it.get("publisher", ""))
            if mode == "lang":
                return (it.get("language") or "").strip()
            if mode == "year":
                return year(it)
            return f"col. {coleccion(it.get('url',''))}"
        # Elegir el PRIMER modo cuyo tag haga ÚNICOS a TODOS los items del grupo
        # (no basta con que haya ≥2 valores distintos: dos items con el mismo
        # publisher no se separan con el publisher → caer a coleccion, que SIEMPRE
        # distingue porque cada edición es una /coleccion distinta).
        mode = "cole"
        for cand in ("pub", "lang", "year", "cole"):
            tags = [tag_for(it, cand) for it in g]
            if all(tags) and len(set(tags)) == len(g):
                mode = cand
                break
        for it in g:
            tag = tag_for(it, mode)
            if not tag:
                continue
            t = it.get("title", "") or ""
            if f"({tag})" in t:
                continue
            new = f"{t} ({tag})"
            if len(diffs) < 60:
                diffs.append((t, new))
            if not args.dry_run:
                it["title"] = new
                it["title_standardized"] = new
            changed += 1

    print(f"[collisions] títulos desambiguados: {changed}")
    for old, new in diffs[:60]:
        print(f"    {old!r} → {new!r}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-collisionfix-bak"))
    tmp = ITEMS.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(ITEMS)
    print(f"[collisions] escrito {ITEMS} ({changed}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
