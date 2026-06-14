#!/usr/bin/env python3
"""remove_phantom_calendar_editions.py — borra ediciones especiales/artbook
FANTASMA creadas a partir de items de `ListadoManga (calendario)` y arregla
portadas que son, en realidad, el BONUS (extra/regalo de 1ª edición) de OTRO tomo.

Contexto (gotcha #99). El módulo plano del calendario (`scripts/wikis/listadomanga.py`)
sólo conoce el texto del enlace del día (p. ej. "Edens Zero nº23"); NO conoce
ediciones. Cuando esos items pasaron por la estandarización (LLM), algunos se
"derivaron" como una Edición Especial / Artbook que NO existe en la página real, y
se les pegó como foto la imagen de un extra (cofre, posavasos, miniartbook…) que
pertenece a OTRO volumen. El parser de colecciones (`listadomanga_collections.py`)
es la AUTORIDAD de cada `/coleccion?id=N`: si ahí no hay tal especial, era un fantasma.

Caso semilla: `coleccion.php?id=3094` (Edens Zero). El tomo 23 es REGULAR; no hay
especial del 23. El item "Edens Zero Especial 23 Edición Especial" (artbook) tenía
como foto el "Posavasos imantado" que es el regalo de 1ª edición de los tomos 2 y 3.

IMPORTANTE — cada slug de las listas fue VERIFICADO a mano contra la página viva de
ListadoManga (no se borra por heurística; el cruce calendario-vs-colecciones tiene
falsos positivos: hay especiales REALES que el parser de colecciones se perdió, p.ej.
orange nº7, "El chico que me gusta no es un chico" nº3, Hosaka nº1). Por eso las
listas son explícitas, no derivadas.

Comportamiento:
  - DELETE_SLUGS: borra la fila completa. Guarda de seguridad: sólo borra si la fila
    es de fuente ÚNICA "ListadoManga (calendario)" y no está aprobada (golden record).
  - FIX_SLUGS: quita de `images[]` toda foto cuya URL sea un `extra`/`bonus` de OTRA
    fila (la foto "robada"); re-marca `images[0]`. Si queda sin fotos, la UI cae al 📚
    (mejor placeholder que portada equivocada — misma filosofía que gotcha #28/#... ).

Uso:
  .venv/bin/python scripts/retrofit/remove_phantom_calendar_editions.py --dry-run
  .venv/bin/python scripts/retrofit/remove_phantom_calendar_editions.py
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path

ITEMS = Path(__file__).resolve().parent.parent.parent / "data" / "items.jsonl"

# Fantasmas verificados contra la página viva — NO existe tal edición en la fuente.
DELETE_SLUGS = {
    "edens-zero-norma-special-c3094-es-23",                     # id 3094: tomo 23 es regular; foto = posavasos de tomos 2/3
    "four-knights-of-apocalypse-norma-artbook-es-17",           # id 4468: serie regular, no artbook; tomo 17 normal
    "yo-kai-watch-norma-special-es-11",                         # id 2337: tomo 11 normal; sólo el tomo 1 tuvo regalo
    "go-with-the-clouds-north-by-northwest-norma-artbook-es-2", # id 3293: serie regular, no artbook; tomo 2 normal
    "metamorphose-no-engawa-norma-kanzenban-es-2",              # id 3487: edición normal (no kanzenban); tomo 2 normal
}

# Items REALES cuya portada es la foto de un bonus de OTRO tomo → quitar esa foto.
FIX_SLUGS = {
    "seraph-of-the-end-norma-regular-es-27",        # id 2268: tomo 27 normal; su foto era el cofre del tomo 1
    "magic-knight-rayearth-norma-special-c322-es-3",# id 322: su images[0] era el cofre (extra de col. 245), no su portada
}


def _primary_idx(images: list) -> int:
    return 0 if images else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="no escribe nada, sólo reporta")
    args = ap.parse_args()

    items = [json.loads(l) for l in ITEMS.open(encoding="utf-8") if l.strip()]

    # Mapa: url -> set(slugs) donde esa url es un extra/bonus.
    extra_owner: dict[str, set[str]] = defaultdict(set)
    for it in items:
        for img in (it.get("images") or []):
            if isinstance(img, dict) and img.get("kind") in ("extra", "bonus") and img.get("url"):
                extra_owner[img["url"]].add(it.get("slug"))

    out: list[dict] = []
    deleted, skipped, fixed = [], [], []

    for it in items:
        slug = it.get("slug")

        if slug in DELETE_SLUGS:
            srcs = {s.get("name") for s in (it.get("sources") or [])}
            if it.get("approved_at") or srcs != {"ListadoManga (calendario)"}:
                # Guarda: no es el fantasma esperado (multi-fuente o aprobado) → conservar.
                skipped.append((slug, sorted(srcs), bool(it.get("approved_at"))))
                out.append(it)
                continue
            deleted.append(slug)
            continue  # no se re-agrega → borrado

        if slug in FIX_SLUGS:
            imgs = it.get("images") or []
            kept, removed = [], []
            for img in imgs:
                url = img.get("url") if isinstance(img, dict) else None
                owners = extra_owner.get(url, set()) - {slug}
                if url and owners:
                    removed.append((img.get("kind"), url, sorted(owners)))
                else:
                    kept.append(img)
            if removed:
                it["images"] = kept
                fixed.append((slug, removed, len(kept)))

        out.append(it)

    # ---- Reporte ----
    print("=== remove_phantom_calendar_editions ===\n")
    print(f"DELETE fantasmas ({len(deleted)}):")
    for s in deleted:
        print(f"  ✗ {s}")
    if skipped:
        print(f"\nSALTADOS por guarda ({len(skipped)}) — no eran el fantasma esperado:")
        for s, srcs, appr in skipped:
            print(f"  · {s}  sources={srcs} approved={appr}")
    print(f"\nFIX foto robada ({len(fixed)}):")
    for s, removed, n in fixed:
        for kind, url, owners in removed:
            print(f"  ↻ {s}: quita {kind} {url[-28:]} (extra de {owners}) → quedan {n} foto(s)")

    if args.dry_run:
        print("\n[dry-run] no se escribió nada.")
        return 0

    backup = ITEMS.with_suffix(".jsonl.pre-phantom-calendar-bak")
    shutil.copy(ITEMS, backup)
    tmp = ITEMS.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for it in out:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(ITEMS)
    print(f"\n[ok] escrito {ITEMS} ({len(out)} filas). Backup: {backup.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
