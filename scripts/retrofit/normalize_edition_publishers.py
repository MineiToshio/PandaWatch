#!/usr/bin/env python3
"""normalize_edition_publishers.py — unifica el campo `publisher` dentro de
cada edición (auditoría 2026-06-11: 40 ediciones con publishers mezclados).

PROBLEMA: filas de la MISMA edition_key con strings de editorial distintos
("Panini Comics" / "Planet Manga" / "Panini / Planet Manga"; "Glenat" /
"glénat manga"; typos como "Ichijinshha"; kanji vs romaji). No siempre rompe
la agrupación (la key ya está unificada) pero ensucia el dato y, en el tier
fuzzy del cluster_key, puede partir clusters.

FIX determinístico por mayoría: dentro de cada edition_key con >1 string de
publisher, todas las filas (nunca las approved) toman el string GANADOR:
el más común cuyo `_publisher_slug()` coincide con la editorial embebida en
el edition_key; si ninguno coincide, el más común a secas. Re-deriva
cluster_key de las filas tocadas y consolida.

Uso:
  .venv/bin/python scripts/retrofit/normalize_edition_publishers.py --dry-run
  .venv/bin/python scripts/retrofit/normalize_edition_publishers.py
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import manga_watch as mw  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"


def _key_pub_slug(ek: str) -> str:
    parts = (ek or "").split("-")
    return parts[-3] if len(parts) >= 4 else ""


def winning_publisher(group: list[dict]) -> str:
    """String de publisher ganador para un grupo de filas de la misma edición."""
    counts = Counter((it.get("publisher") or "").strip() for it in group)
    counts.pop("", None)
    if len(counts) < 2:
        return ""
    key_slug = _key_pub_slug(group[0].get("edition_key", ""))
    matching = Counter({p: n for p, n in counts.items()
                        if key_slug and mw._publisher_slug(p) == key_slug})
    pool = matching or counts
    # más común; empate → el string más corto (suele ser el nombre limpio)
    return sorted(pool.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0][0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    by_ek: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        ek = it.get("edition_key", "") or ""
        if ek:
            by_ek[ek].append(it)

    changed, editions, ex = 0, 0, []
    for ek, group in by_ek.items():
        winner = winning_publisher(group)
        if not winner:
            continue
        touched = False
        for it in group:
            if it.get("approved_at"):
                continue
            old = (it.get("publisher") or "").strip()
            if old and old != winner:
                if len(ex) < 20:
                    ex.append((ek, old, winner))
                it["publisher"] = winner
                it["cluster_key"] = mw.derive_cluster_key(it)
                changed += 1
                touched = True
        if touched:
            editions += 1
    print(f"[pub-mix] ediciones unificadas: {editions}, filas reescritas: {changed}")
    for ek, old, new in ex:
        print(f"    {ek}: {old!r} → {new!r}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if changed:
        before = len(items)
        items = mw.consolidate_by_cluster(items)
        print(f"[pub-mix] consolidate: {before} → {len(items)}")
        mw.backup_and_rotate(ITEMS, "pubmix")
        mw.write_items_atomic(ITEMS, items)
        print(f"[pub-mix] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
