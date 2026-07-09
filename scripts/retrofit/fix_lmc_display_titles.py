#!/usr/bin/env python3
"""fix_lmc_display_titles.py — normaliza el título de display de los tomos de
listadomanga (gotcha #52):
  (a) quita el marcador de volumen "nº" ("Atelier of Witch Hat nº5" → "… 5");
  (b) edición ESPECIAL → apenda "(Edición Especial)" para distinguirla del tomo
      regular del MISMO volumen (que conviven en la misma edición y se veían como
      duplicados). Siempre para especial, salvo que ya diga especial/special.

El edition_kind sale del synthetic URL `item=<kind>-<vol>` o del campo `lm_kind`.
Idempotente (re-aplicar no cambia nada). NO toca items aprobados (`approved_at`).

Uso:
  .venv/bin/python scripts/retrofit/fix_lmc_display_titles.py --dry-run
  .venv/bin/python scripts/retrofit/fix_lmc_display_titles.py
"""
from __future__ import annotations
import json, re, sys, argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from wikis.listadomanga_collections import normalize_display_title  # noqa: E402
from manga_watch import backup_and_rotate, write_items_atomic  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"
_ITEM = re.compile(r"[?&]item=([a-z]+)-")
_CL = re.compile(r"^lmc:\d+:([a-z]+):")
# Qualifiers de EDICIÓN que NO van en el título de un tomo de una edición REGULAR
# (contaminación stale: el tomo regular arrastra el nombre de la edición especial
# del mismo volumen → se ve como duplicado, gotcha #56). NO toca "Edición Especial"
# a secas (eso lo maneja normalize_display_title según el kind).
_CONTAM = re.compile(
    r"\s*\b(?:Edici[oó]n\s+Especial\s+Limitada|Edici[oó]n\s+Limitada|"
    r"Edici[oó]n\s+Coleccionista|Artbook|Coleccionista)\b\s*", re.IGNORECASE)
_VALID_COUNTRY = ("es", "it", "fr", "us", "jp", "mx", "br", "de", "xx", "vn",
                  "th", "tw", "gb", "kr", "pt", "ar", "pe", "cl", "eslatam", "latam")


def _edition_slug(ek: str) -> str:
    parts = (ek or "").split("-")
    parts = parts[:-1] if parts and parts[-1] in _VALID_COUNTRY else parts
    if parts and re.fullmatch(r"c\d+", parts[-1]):
        parts = parts[:-1]
    return parts[-1] if parts else ""


def _kind(it: dict) -> str:
    """kind del tomo. Prioridad: cluster_key `lmc:cole:kind:vol` (fiable también
    para la fila base sin `item=`) → URL primaria → URLs de sources → lm_kind."""
    m = _CL.match(it.get("cluster_key", "") or "")
    if m:
        return m.group(1)
    m = _ITEM.search(it.get("url", "") or "")
    if m:
        return m.group(1)
    for s in it.get("sources", []) or []:
        m = _ITEM.search(s.get("url", "") or "")
        if m:
            return m.group(1)
    return (it.get("lm_kind") or "regular")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]
    changed, ex = 0, []
    for it in items:
        # procesar filas de listadomanga: primaria coleccion.php O fuente lista-
        # manga en sources[] (fichas cross-source de tienda que mergearon, #56).
        urls = [it.get("url", "") or ""] + [s.get("url", "") or "" for s in (it.get("sources") or [])]
        if not any("coleccion.php" in u for u in urls):
            continue
        if it.get("approved_at"):
            continue
        kind = _kind(it)
        old = it.get("title", "") or ""
        base = old
        # Pre-strip: en ediciones REGULARES, quitar qualifiers de edición embebidos
        # que contaminan el título del tomo (gotcha #56).
        if _edition_slug(it.get("edition_key", "")) == "regular":
            base = re.sub(r"\s{2,}", " ", _CONTAM.sub(" ", old)).strip()
        new = normalize_display_title(base, kind)
        if new != old:
            if len(ex) < 25:
                ex.append((old, new))
            if not args.dry_run:
                it["title"] = new
            changed += 1
    print(f"[lmc-titles] títulos normalizados: {changed}")
    for o, n in ex:
        print(f"    {o!r}  →  {n!r}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if changed:
        backup_and_rotate(ITEMS, "lmctitles")
        write_items_atomic(ITEMS, items)
        print(f"[lmc-titles] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
