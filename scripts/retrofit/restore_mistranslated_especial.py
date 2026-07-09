#!/usr/bin/env python3
"""restore_mistranslated_especial.py — deshace la TRADUCCIÓN de "Special Edition"
(EN) → "Edición Especial" (ES) que el viejo `format_especial_title` aplicaba sobre
títulos NO españoles (gotcha #94).

SÍNTOMA: títulos mezclados — un nombre japonés/italiano/inglés terminando con la
marca española ("葬送のフリーレン 15 Edición Especial", "Demon Slayer 22 Edición
Especial" en items de Mangavariant/Sanyodo/AnimeClick…).

CAUSA: `format_especial_title` (usado por `fix_especial_title_order.py`, paso del
enforcer) matcheaba el inglés "Special Edition"/"Special" y SIEMPRE emitía la forma
española "Edición Especial" → traducción, prohibida por la política de títulos
(`docs/reference/title-policy.md`). El mecanismo ya se arregló: la regex sólo
normaliza frases en español.

ESTE RETROFIT (limpieza de datos legacy): restaura `title` = `clean_title(
title_original)` para los items cuyo `title` ganó "Edición Especial" por traducción
(la marca española NO está en `title_original`). `title_original` es, por política, el
nombre oficial tal como vino de la fuente — la red de seguridad correcta.

EXCLUYE:
  - items de listadomanga (coleccion.php): su `title_original` quedó corrompido por
    el skill viejo y se reconstruye aparte desde `description`
    (`fix_corrupted_lm_special_titles.py`). Restaurar desde su title_original
    REVIVIRÍA la corrupción ("…no Special Edition").
  - items con la firma de corrupción "no Special/Fanbook/…" en title_original.
  - items aprobados (`approved_at`).

Idempotente (tras correrlo, `title` ya no difiere de su title_original por la marca
ES). Re-deriva cluster_key y consolida.

Uso:
  .venv/bin/python scripts/retrofit/restore_mistranslated_especial.py --dry-run
  .venv/bin/python scripts/retrofit/restore_mistranslated_especial.py
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

ITEMS = ROOT / "data" / "items.jsonl"

_ESPECIAL_ES = re.compile(r"Especial", re.IGNORECASE)
_LM_CORRUPTION = re.compile(r"\bno\s+(?:Special|Limited|Collector|Deluxe|Fanbook|"
                            r"Artbook|Guidebook|Box|Coffret|Bonus)\b", re.IGNORECASE)


def _is_lm_collection(it: dict) -> bool:
    urls = [it.get("url", "") or ""] + [
        s.get("url", "") or "" for s in (it.get("sources") or [])
    ]
    return any("coleccion.php" in u for u in urls)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]
    changed, ex = 0, []
    for it in items:
        if it.get("approved_at"):
            continue
        title = it.get("title", "") or ""
        orig = (it.get("title_original") or "").strip()
        if "Edición Especial" not in title:
            continue
        # La marca ES debe estar AUSENTE del original (se inyectó por traducción).
        if not orig or _ESPECIAL_ES.search(orig):
            continue
        if _is_lm_collection(it) or _LM_CORRUPTION.search(orig):
            continue
        new = mw.clean_title(orig)
        if new and new != title:
            if len(ex) < 30:
                ex.append((title, new))
            it["title"] = new
            it["cluster_key"] = mw.derive_cluster_key(it)
            changed += 1
    print(f"[mistranslated-especial] títulos restaurados: {changed}")
    for o, n in ex:
        print(f"    {o!r}  →  {n!r}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if changed:
        before = len(items)
        items = mw.consolidate_by_cluster(items)
        print(f"[mistranslated-especial] consolidate: {before} → {len(items)}")
        backup = mw.backup_and_rotate(ITEMS, "mistransesp")
        print(f"[mistranslated-especial] backup: {backup}")
        mw.write_items_atomic(ITEMS, items)
        print(f"[mistranslated-especial] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
