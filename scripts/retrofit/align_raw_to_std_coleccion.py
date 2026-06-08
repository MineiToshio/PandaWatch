#!/usr/bin/env python3
"""align_raw_to_std_coleccion.py — alinea items RAW a la edición ESTANDARIZADA
de su misma `/coleccion` (regla dura coleccion = edición, gotcha #42/#43).

Problema: re-scrapear una colección que YA tiene items estandarizados en el
corpus genera duplicados raw-vs-std que NO consolidan, porque el item viejo
tiene `cluster_key` tier-1 (`edition:…`) derivado de su `edition_key` ya
asignado por el LLM, y el item raw nuevo tiene tier-2.5 (`lmc:{coleccion}:…`).
Nunca coinciden → la misma colección (= misma edición física) aparece dos veces
con títulos/edition_key distintos (ej. cole 1555: "Bastard!! Deluxe N"
estandarizado vs "Bastard!! nº N" raw).

Fix determinístico (NO espera al LLM): en cada colección que tenga ≥1 item
estandarizado, los items RAW heredan series_key/series_display/edition_key/
edition_display del item estandarizado (el más frecuente si hay varios) y se
recomputa su cluster_key. Luego `consolidate_by_cluster` fusiona los raw cuyo
volumen ya existe estandarizado (el representante estandarizado gana título e
info; el raw aporta su fuente/imágenes si suman). Los raw de volúmenes SIN
contraparte estandarizada quedan raw pero ya con la identidad correcta de la
edición → el skill los procesará consistentes.

NO toca `title` de los raw (lo resuelve el merge) NI `standardized_at`.
Idempotente: si ya están alineados, no cambia nada.

Uso:
  .venv/bin/python scripts/retrofit/align_raw_to_std_coleccion.py --dry-run
  .venv/bin/python scripts/retrofit/align_raw_to_std_coleccion.py
"""
from __future__ import annotations
import json, re, sys, argparse, shutil, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import manga_watch as mw  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"
_COLE_RE = re.compile(r"coleccion\.php\?id=(\d+)")


def _cole(url: str) -> str | None:
    m = _COLE_RE.search(url or "")
    return m.group(1) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    # Agrupar por coleccion; identificar el item estandarizado autoritativo.
    by_cole: dict[str, list[dict]] = collections.defaultdict(list)
    for it in items:
        c = _cole(it.get("url", ""))
        if c:
            by_cole[c].append(it)

    # El KIND del item raw (de su synthetic URL `item=<kind>-<vol>-<hash>`) mapea
    # a un edition_slug. Una colección puede tener VARIAS ediciones (regular +
    # especial + collector); hay que alinear cada raw a la std de SU MISMO tipo,
    # NO a la más frecuente (si no, el especial-34 caía en `regular`).
    _KIND_SLUG = {"regular": "regular", "especial": "special", "limitada": "limited",
                  "alternativa": "variant", "pack": "boxset"}

    def _raw_kind(it):
        m = re.search(r"item=([a-z]+)-", it.get("url", "") or "")
        return m.group(1) if m else ""

    def _std_has_slug(std_it, slug):
        ek = std_it.get("edition_key") or ""
        return f"-{slug}-" in ek or ek.endswith(f"-{slug}")

    changed, diffs = 0, []
    for c, grp in by_cole.items():
        std = [it for it in grp if it.get("standardized_at") and it.get("edition_key")]
        raw = [it for it in grp if not it.get("standardized_at")]
        if not std or not raw:
            continue
        std_slugs = {(it.get("series_key"), it.get("edition_key")): it for it in std}
        single_std = len(std_slugs) == 1  # colección mono-edición (caso cole 52)
        for it in raw:
            kind = _raw_kind(it)
            expected = _KIND_SLUG.get(kind)
            # elegir la std cuyo edition_slug coincide con el kind del raw
            ref = next((s for s in std if expected and _std_has_slug(s, expected)), None)
            if ref is None and single_std:
                # colección con UNA sola edición → alinear sin ambigüedad
                ref = std[0]
            if ref is None:
                continue  # no hay std del mismo tipo → dejar el raw con su identidad
            if it.get("series_key") == ref.get("series_key") and \
               it.get("edition_key") == ref.get("edition_key"):
                continue  # ya alineado
            if len(diffs) < 30:
                diffs.append((c, it.get("edition_key"), ref.get("edition_key"), it.get("title")))
            if not args.dry_run:
                it["series_key"] = ref.get("series_key")
                it["series_display"] = ref.get("series_display", "")
                it["edition_key"] = ref.get("edition_key")
                it["edition_display"] = ref.get("edition_display", "")
                it["cluster_key"] = mw.derive_cluster_key(it)
            changed += 1

    print(f"[align-raw] items raw alineados a su edición estandarizada: {changed}")
    for c, oek, nek, t in diffs:
        print(f"    cole {c}: {oek!r} → {nek!r}   ({t!r})")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if changed:
        from manga_watch import consolidate_by_cluster
        before = len(items)
        items = consolidate_by_cluster(items)
        print(f"[align-raw] consolidate: {before} → {len(items)} ({before - len(items)} fusionados)")
        shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-alignraw-bak"))
        tmp = ITEMS.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        tmp.replace(ITEMS)
        print(f"[align-raw] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
