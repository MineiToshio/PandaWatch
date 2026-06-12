#!/usr/bin/env python3
"""fix_title_edition_words.py — limpia dos defectos de título que deja el
generador/LLM de standardize (verificación 2026-06-11):

  (A) **Palabra de EDICIÓN duplicada consecutiva**: "5 Elementos Artbook
      Artbook", "Trigun Maximum Maximum 2" (la serie ya termina con la palabra
      y el generador la vuelve a agregar). SOLO se colapsa el vocabulario de
      ediciones — nunca palabras arbitrarias ("Dead Dead Demon's
      Dededededestruction" es un título legítimo y no se toca).

  (B) **"Regular" como palabra en el título de una edición regular**
      ("Noragami Regular 27" → "Noragami 27"): el formato canónico omite el
      calificador en las regulares.

Re-deriva cluster_key de lo tocado y consolida. Respeta approved_at.
Idempotente.

Uso:
  .venv/bin/python scripts/retrofit/fix_title_edition_words.py --dry-run
  .venv/bin/python scripts/retrofit/fix_title_edition_words.py
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import manga_watch as mw  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"

# Vocabulario de ediciones en títulos display (subset de _KNOWN_EDITION_SLUGS
# con sus formas display; "Box Set"/"Edición Especial" no se duplican en la
# práctica — el caso real es la palabra simple).
_ED_WORDS = (
    "Artbook|Fanbook|Guidebook|Kanzenban|Deluxe|Maximum|Perfect|Ultimate|"
    "Master|Library|Integral|Collector|Coffret|Cofanetto|Omnibus|Limited|"
    "Special|Variant|Prestige|Grimorio|Grimoire|Steelbox|Slipcase"
)
_DUP_RE = re.compile(rf"\b({_ED_WORDS})(?:\s+\1)+\b", re.IGNORECASE)
_REGULAR_RE = re.compile(r"\s*\bRegular\b\s*", re.IGNORECASE)


def _edition_slug(ek: str) -> str:
    parts = (ek or "").split("-")
    if parts and re.fullmatch(r"c\d+", parts[-1]):
        parts = parts[:-1]
    return parts[-2] if len(parts) >= 2 else ""


def fix_title(title: str, edition_slug: str) -> str:
    """Devuelve el título corregido (igual si no hay nada que tocar)."""
    t = title or ""
    t = _DUP_RE.sub(r"\1", t)
    if edition_slug == "regular":
        t = _REGULAR_RE.sub(" ", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]
    changed, ex = 0, []
    for it in items:
        if it.get("approved_at"):
            continue
        old = it.get("title", "") or ""
        new = fix_title(old, _edition_slug(it.get("edition_key", "")))
        if new and new != old:
            if len(ex) < 25:
                ex.append((old, new))
            it["title"] = new
            if it.get("title_standardized"):
                it["title_standardized"] = new
            it["cluster_key"] = mw.derive_cluster_key(it)
            changed += 1
    print(f"[title-edwords] títulos corregidos: {changed}")
    for o, n in ex:
        print(f"    {o!r}  →  {n!r}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if changed:
        before = len(items)
        items = mw.consolidate_by_cluster(items)
        print(f"[title-edwords] consolidate: {before} → {len(items)}")
        shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-titleedw-bak"))
        tmp = ITEMS.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        tmp.replace(ITEMS)
        print(f"[title-edwords] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
