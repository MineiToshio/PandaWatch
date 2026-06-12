#!/usr/bin/env python3
"""standardize_apply.py — pasos de APPLY del skill /watch-standardize-catalog.

Fuente ÚNICA de la lógica de aplicación que antes vivía COPIADA (y
desincronizada) en SKILL.md y en el workflow. Dos subcomandos:

  tier1   Aplica determinísticamente las propuestas de `tier1.json`
          (0 tokens LLM) y marca `standardized_at`.

  merge   Lee los veredictos LLM por chunk (`result_*.jsonl` en el dir de
          trabajo), los aplica con estas garantías:
            - PRESERVA el edition_key/edition_display YA asignados (el LLM no
              re-agrupa — decisión owner 2026-06-07); solo asigna edición a
              items que NO tienen una.
            - Fallback a la propuesta heurística (tier{2,3}.json) si el LLM
              devolvió keys vacías; sin keys usables → el item queda PENDIENTE
              (se reintenta en la próxima corrida, nunca huérfanos).
            - is_manga=false → data/non_manga_blacklist.jsonl (dedup por url).
            - Re-chequeo canónico de serie (canonical_series_key) + outliers
              de serie dentro de una misma /coleccion.
            - Recomputa cluster_key y consolida (merge_cluster, fuente única).
          Después de `merge` correr SIEMPRE el enforcer
          (scripts/retrofit/enforce_listadomanga_rules.py — Step 6b del skill).

Uso:
  .venv/bin/python scripts/standardize_apply.py tier1 [--force-all]
  .venv/bin/python scripts/standardize_apply.py merge [--force-all]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manga_watch import (  # noqa: E402
    consolidate_by_cluster,
    derive_cluster_key,
    rebuild_edition_key_prefix,
    sanitize_key_ascii,
)
from series_aliases import (  # noqa: E402
    _build_aggressive_lookup,
    _build_lookup,
    canonical_series_key,
)

ITEMS = ROOT / "data" / "items.jsonl"
BLACKLIST = ROOT / "data" / "non_manga_blacklist.jsonl"
DEFAULT_BASE = Path("/tmp/manga-standardize-run")


def _load_items() -> list[dict]:
    return [json.loads(l) for l in ITEMS.open() if l.strip()]


def _write_items(items: list[dict]) -> None:
    tmp = ITEMS.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(ITEMS)


def cmd_tier1(base: Path, force_all: bool) -> int:
    tier1_file = base / "tier1.json"
    if not tier1_file.exists():
        print("tier1.json no existe — correr standardize_audit.py primero.")
        return 1
    tier1 = json.load(tier1_file.open())
    url_to_md = {p["url"]: p for p in tier1 if p.get("url")}

    items = _load_items()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    applied = 0
    for it in items:
        if it.get("approved_at"):
            continue
        if it.get("standardized_at") and not force_all:
            continue
        md = url_to_md.get(it.get("url", ""))
        if not md:
            continue
        if not it.get("title_original"):
            it["title_original"] = it.get("title", "")
        it["series_key"] = sanitize_key_ascii(md.get("proposed_series_key", ""))
        it["series_display"] = md.get("proposed_series_display", "")
        it["edition_key"] = sanitize_key_ascii(md.get("proposed_edition_key", ""))
        it["edition_display"] = md.get("proposed_edition_display", "")
        it["volume"] = md.get("proposed_volume", "")
        # title intacto: es el nombre OFICIAL scrapeado, nunca se renombra
        # ni traduce (política de títulos 2026-06-12).
        it["standardized_at"] = now_iso
        applied += 1
    _write_items(items)
    print(f"Tier 1 auto-standardized: {applied} items (0 tokens LLM)")
    return 0


def cmd_merge(base: Path, force_all: bool) -> int:
    # Caches de aliases pueden estar stale si el YAML cambió en esta sesión.
    _build_lookup.cache_clear()
    _build_aggressive_lookup.cache_clear()

    # 1) Veredictos LLM por chunk (cubre result_NN.jsonl y result_t{2,3}_NN.jsonl).
    results: dict[str, dict] = {}
    for f in sorted(base.glob("result_*.jsonl")):
        for line in f.open():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("url"):
                results[r["url"]] = r
    print(f"Veredictos leídos de archivos de chunk: {len(results)}")

    # 2) Propuestas heurísticas (fallback para keys vacías del LLM).
    proposals: dict[str, dict] = {}
    for name in ("tier2.json", "tier3.json"):
        p = base / name
        if p.exists():
            try:
                for proj in json.load(p.open()):
                    proposals[proj.get("url", "")] = proj
            except Exception:
                pass

    items = _load_items()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    pending_before = sum(1 for it in items if not it.get("standardized_at"))
    left_pending = 0

    non_manga: list[dict] = []
    final: list[dict] = []
    for it in items:
        if it.get("approved_at"):
            final.append(it)
            continue
        if it.get("standardized_at") and not force_all:
            final.append(it)
            continue
        r = results.get(it.get("url", ""))
        if not r:
            final.append(it)
            continue
        if not r.get("is_manga", True):
            non_manga.append({
                "url": it.get("url", ""), "title": it.get("title", ""),
                "source": it.get("source", ""), "publisher": it.get("publisher", ""),
                "reason": r.get("non_manga_reason", "flagged_by_review"),
                "reviewed_at": now_iso,
            })
            continue
        prop = proposals.get(it.get("url", ""), {})
        sk = (r.get("series_key", "") or "").strip() or prop.get("proposed_series_key", "")
        # Claves acuñadas por el LLM: forzar ASCII kebab (gotcha #81). Si la
        # sanitización la vacía (clave íntegramente CJK), queda pending.
        sk = sanitize_key_ascii(sk)
        if not sk:
            left_pending += 1
            final.append(it)
            continue
        it["series_key"] = sk
        it["series_display"] = ((r.get("series_display", "") or "").strip()
                                or prop.get("proposed_series_display", ""))
        # PRESERVAR la edición ya asignada determinísticamente (el parser aplicó
        # las reglas duras): el LLM solo asigna edición a items SIN edition_key.
        if (it.get("edition_key") or "").strip():
            it["volume"] = it.get("volume", "") or (r.get("volume", "") or "").strip()
        else:
            ek = (r.get("edition_key", "") or "").strip() or prop.get("proposed_edition_key", "")
            ek = sanitize_key_ascii(ek)
            if not ek:
                left_pending += 1
                final.append(it)
                continue
            it["edition_key"] = ek
            it["edition_display"] = ((r.get("edition_display", "") or "").strip()
                                     or prop.get("proposed_edition_display", ""))
            it["volume"] = ((r.get("volume", "") or "").strip()
                            or prop.get("proposed_volume", ""))
        # title intacto: es el nombre OFICIAL scrapeado, nunca se renombra ni
        # traduce (política de títulos 2026-06-12). Cualquier
        # `title_standardized` que devuelva el LLM se IGNORA.
        if not it.get("title_original"):
            it["title_original"] = it.get("title", "")
        new_sk, new_sd = canonical_series_key(it["title"], it["series_key"],
                                              it["series_display"])
        # La canónica del YAML también puede traer no-ASCII (gotcha #81).
        new_sk = sanitize_key_ascii(new_sk) or new_sk
        if new_sk != it["series_key"]:
            old_sk = it["series_key"]
            it["series_key"] = new_sk
            it["series_display"] = new_sd
            if (it.get("edition_key") or "").startswith(old_sk + "-"):
                it["edition_key"] = new_sk + it["edition_key"][len(old_sk):]
        elif new_sd != it["series_display"]:
            it["series_display"] = new_sd
        # Si la key vino con la serie truncada/stale (no empieza con el
        # series_key actual), re-armar el prefijo parseando la cola
        # {pub}-{slug}-{pais} (invariante de formato; mismo helper que el
        # retrofit fix_edition_key_prefix.py).
        rebuilt = rebuild_edition_key_prefix(it.get("edition_key", ""),
                                             it["series_key"])
        if rebuilt:
            it["edition_key"] = rebuilt
        it["standardized_at"] = now_iso
        final.append(it)

    # 3) Outliers de serie dentro de una misma /coleccion (consistencia).
    groups = defaultdict(list)
    for it in final:
        if not it.get("standardized_at"):
            continue
        m = re.search(r"listadomanga\.es/coleccion\.php\?id=(\d+)",
                      it.get("url", "") or "")
        if m:
            groups[m.group(1)].append(it)
    outliers = 0
    for grp in groups.values():
        if len(grp) < 4:
            continue
        dom_sk, dom_n = Counter(it.get("series_key", "") for it in grp).most_common(1)[0]
        if dom_n < 3:
            continue
        dom_sd = next((x.get("series_display", "") for x in grp
                       if x.get("series_key") == dom_sk), "")
        for it in grp:
            if it.get("series_key", "") and it["series_key"] != dom_sk:
                old_ek = it.get("edition_key", "")
                if old_ek.startswith(it["series_key"] + "-"):
                    it["edition_key"] = dom_sk + old_ek[len(it["series_key"]):]
                it["series_key"] = dom_sk
                if dom_sd:
                    it["series_display"] = dom_sd
                outliers += 1

    # 4) Recomputar cluster_key + consolidar (merge_cluster, fuente única).
    for it in final:
        it["cluster_key"] = derive_cluster_key(it)
    before = len(final)
    deduped = consolidate_by_cluster(final)

    _write_items(deduped)

    # 5) Blacklist de non-manga (dedup por url).
    existing_bl = set()
    if BLACKLIST.exists():
        for line in BLACKLIST.open():
            try:
                existing_bl.add(json.loads(line).get("url", ""))
            except Exception:
                pass
    new_bl = [nm for nm in non_manga if nm["url"] not in existing_bl]
    with BLACKLIST.open("a", encoding="utf-8") as fh:
        for nm in new_bl:
            fh.write(json.dumps(nm, ensure_ascii=False) + "\n")

    still_pending = sum(1 for it in deduped if not it.get("standardized_at"))
    orphans = sum(1 for it in deduped
                  if it.get("standardized_at")
                  and not (it.get("series_key") and it.get("edition_key")))
    print(f"Items: {len(items)} -> {len(deduped)}")
    print(f"Non-manga: {len(new_bl)}")
    print(f"Deduped: {before - len(deduped)}")
    print(f"Outliers de serie corregidos: {outliers}")
    print(f"INTEGRITY: pending_before={pending_before} "
          f"left_pending(sin keys usables)={left_pending} "
          f"still_pending_after={still_pending}")
    if orphans:
        print(f"WARNING: {orphans} items estandarizados con keys VACÍAS (huérfanos).")
        return 1
    print("INTEGRITY OK: 0 items estandarizados con keys vacías.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["tier1", "merge"])
    ap.add_argument("--force-all", action="store_true")
    ap.add_argument("--base", type=Path, default=DEFAULT_BASE)
    args = ap.parse_args()
    if args.command == "tier1":
        return cmd_tier1(args.base, args.force_all)
    return cmd_merge(args.base, args.force_all)


if __name__ == "__main__":
    raise SystemExit(main())
