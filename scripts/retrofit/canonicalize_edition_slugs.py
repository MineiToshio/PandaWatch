#!/usr/bin/env python3
"""canonicalize_edition_slugs.py — re-aplica la tabla determinística
término→slug de edición sobre el edition_key (gotcha #69).

PROBLEMA: el LLM del skill standardize elegía el slug de TIPO de edición de
forma inconsistente entre corridas (限定版 a veces "limited", a veces
"special"; collector vs deluxe en FR/IT) y partía la MISMA edición en dos
edition_keys hermanos. Auditoría 2026-06-11: 206 grupos serie+editorial+país
con keys que difieren solo en ese slug; 38 con los mismos tomos en ambas.

FIX (mecanismo, no síntoma): `manga_watch.edition_slug_from_text()` es la
AUTORIDAD término→slug. Este retrofit la re-aplica post-LLM: si el
título original trae evidencia de un tipo confundible (special/limited/
collector/deluxe) y el edition_key tiene OTRO slug confundible, se reescribe
el slug del key. Las keys corregidas convergen y consolidate fusiona los
duplicados. Sin evidencia textual NO se toca nada (precisión > recall).

Excluidos: items aprobados (golden) y items de listadomanga (su edition_key
lo gobierna la regla coleccion=edición, no el término del título).

Uso:
  .venv/bin/python scripts/retrofit/canonicalize_edition_slugs.py --dry-run
  .venv/bin/python scripts/retrofit/canonicalize_edition_slugs.py
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import manga_watch as mw  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"

# Slugs de TIPO confundibles entre sí (los que el LLM mezclaba). Solo se
# corrige confundible→confundible; nunca se pisa una edición nombrada
# (maximum, kanzenban, …) ni se inventa tipo sin evidencia.
CONFUSABLE = {"special", "limited", "collector", "deluxe"}


def _is_lmc(it: dict) -> bool:
    urls = [it.get("url", "") or ""] + [s.get("url", "") or "" for s in (it.get("sources") or [])]
    return any("listadomanga.es/coleccion.php" in u for u in urls)


def canonical_confusable_slug(it: dict) -> str | None:
    """Devuelve el nuevo edition_key si el título contradice el slug, o None.

    Solo actúa cuando AMBOS (evidencia textual y slug actual) son tipos
    confundibles y difieren.
    """
    ek = it.get("edition_key", "") or ""
    parts = ek.split("-")
    if len(parts) < 4:
        return None
    slug = parts[-2]
    if slug not in CONFUSABLE:
        return None
    evidence = mw.edition_slug_from_text(it.get("title_original") or it.get("title") or "")
    if evidence not in CONFUSABLE or evidence == slug:
        return None
    parts[-2] = evidence
    return "-".join(parts)


def propagate_group_evidence(items: list[dict]) -> tuple[int, list[tuple[str, str]]]:
    """Fase 2 — propaga la evidencia DENTRO del grupo serie+editorial+país.

    Caso típico (auditoría 2026-06-11): una key dominante CON evidencia textual
    (`…-collector-fr`, 13 items con "collector" en el título) y una hermana
    confundible suelta SIN evidencia (`…-special-fr`, 1 item) con tomos
    solapados — la misma edición partida. Regla conservadora: la hermana se
    absorbe en la evidenciada SOLO si (a) hay UNA única slug evidenciada en el
    grupo y su evidencia coincide con su propia slug, (b) la hermana no tiene
    NINGUNA evidencia propia, (c) la hermana tiene MENOS items que la
    evidenciada (estrictamente: una hermana MÁS GRANDE que la evidenciada no
    se absorbe — caso hokuto 18-vs-3; el empate 1-vs-1 SÍ se absorbe — caso
    astro-royale collector/special), y (d) sus volúmenes se solapan. Si dos
    slugs del grupo tienen evidencia (ej. collector Y limited reales), no se
    toca nada.
    """
    groups: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for it in items:
        if it.get("approved_at") or _is_lmc(it):
            continue
        ek = it.get("edition_key", "") or ""
        parts = ek.split("-")
        if len(parts) < 4 or parts[-2] not in CONFUSABLE:
            continue
        groups[("-".join(parts[:-2]), parts[-1])][parts[-2]].append(it)

    moved, ex = 0, []
    for (prefix, country), slugs in groups.items():
        if len(slugs) < 2:
            continue
        ev = {
            s: {mw.edition_slug_from_text(i.get("title_original") or i.get("title") or "")
                for i in its} & CONFUSABLE
            for s, its in slugs.items()
        }
        evidenced = [s for s, e in ev.items() if e]
        if len(evidenced) != 1 or ev[evidenced[0]] != {evidenced[0]}:
            continue
        star = evidenced[0]
        star_vols = {i.get("volume") for i in slugs[star] if i.get("volume")}
        for s, its in slugs.items():
            if s == star or ev[s]:
                continue
            if len(its) > len(slugs[star]):
                continue
            vols = {i.get("volume") for i in its if i.get("volume")}
            if not (vols & star_vols):
                continue
            new_ek = f"{prefix}-{star}-{country}"
            for i in its:
                if len(ex) < 20:
                    ex.append((i.get("edition_key"), new_ek))
                i["edition_key"] = new_ek
                i["cluster_key"] = mw.derive_cluster_key(i)
                moved += 1
    return moved, ex


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]
    changed, ex = 0, []
    for it in items:
        if it.get("approved_at") or _is_lmc(it):
            continue
        new = canonical_confusable_slug(it)
        if new:
            if len(ex) < 30:
                ex.append((it.get("edition_key"), new, (it.get("title_original") or "")[:50]))
            it["edition_key"] = new
            it["cluster_key"] = mw.derive_cluster_key(it)
            changed += 1
    print(f"[edition-slugs] edition_key re-canonicalizados por término: {changed}")
    for o, n, t in ex:
        print(f"    {o}  →  {n}   ({t!r})")
    moved, ex2 = propagate_group_evidence(items)
    print(f"[edition-slugs] hermanas sin evidencia absorbidas por la key evidenciada: {moved}")
    for o, n in ex2:
        print(f"    {o}  →  {n}")
    changed += moved
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if changed:
        before = len(items)
        items = mw.consolidate_by_cluster(items)
        print(f"[edition-slugs] consolidate: {before} → {len(items)}")
        shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-edslug-bak"))
        tmp = ITEMS.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        tmp.replace(ITEMS)
        print(f"[edition-slugs] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
