#!/usr/bin/env python3
"""enforce_listadomanga_rules.py — aplica DETERMINÍSTICAMENTE las reglas de
agrupación/edición de listadomanga, sobreescribiendo lo que haya dejado el LLM
del skill `/watch-standardize-catalog`.

MOTIVO (decisión 2026-06-07): el skill re-deriva edition_key/series/title/display
vía LLM. El LLM NO debe ser la autoridad sobre la AGRUPACIÓN — sus reglas son
duras y determinísticas. Este enforcer es la ÚNICA fuente de verdad de:
  - **#49 edition_display = nombre oficial** (título de la /coleccion, sin traducir).
    Se recupera del `description` (el parser lo guarda como primer segmento
    `collection_title · …`) → NO re-fetchea. Inmune a que el LLM lo traduzca.
  - **#48 una /coleccion = UNA edición** (unify_coleccion_edition).
  - **#46 país = edición** (fix_edition_country: sufijo de país en edition_key).
  - **#69 slug de TIPO de edición por término** (canonicalize_edition_slugs:
    限定版→limited, 特装版→special… — aplica a TODAS las fuentes no-lmc).
  - **#70 series_key sin variantes mecánicas** (merge_duplicate_series) +
    publisher unificado por edición (normalize_edition_publishers).
  - cluster_key tier-0 lmc, consolidate, dedup de portadas, slugs.

Corré esto SIEMPRE DESPUÉS del skill de standardize (y el pipeline lo corre solo).
Idempotente.

Uso:
  .venv/bin/python scripts/retrofit/enforce_listadomanga_rules.py
"""
from __future__ import annotations
import json, sys, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = str(ROOT / ".venv" / "bin" / "python")
ITEMS = ROOT / "data" / "items.jsonl"
RETRO = ROOT / "scripts" / "retrofit"


def _recover_edition_display() -> int:
    """edition_display = título oficial de la coleccion, recuperado del
    `description` (`collection_title · edition · …`). Determinístico, sin red."""
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]
    n = 0
    for it in items:
        if "coleccion.php" not in (it.get("url", "") or ""):
            continue
        desc = it.get("description", "") or ""
        official = desc.split(" · ")[0].strip()
        # sólo si parece un título real (no vacío, no un slug) y difiere
        if official and len(official) > 1 and it.get("edition_display") != official:
            it["edition_display"] = official
            n += 1
    if n:
        tmp = ITEMS.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        tmp.replace(ITEMS)
    return n


def _run(script: str, *args: str) -> None:
    print(f">>> {script} {' '.join(args)}")
    subprocess.run([PY, str(RETRO / script), *args], cwd=str(ROOT), check=False)


def main() -> int:
    print("[enforce] 1) edition_display oficial (desde description, sin red)")
    n = _recover_edition_display()
    print(f"    edition_display recuperados: {n}")
    print("[enforce] 2) país = edición")
    _run("fix_edition_country.py")
    print("[enforce] 2b) anomalías de edition_key (panini-es→panini, xx→país inferido)")
    _run("fix_edition_key_anomalies.py")
    print("[enforce] 3) una /coleccion = una edición (incl. fichas de tienda cross-source)")
    _run("unify_coleccion_edition.py")
    print("[enforce] 3-0) coleccion distinta = edición distinta (desambiguar -cNNNN, #57)")
    _run("disambiguate_coleccion_editions.py")
    print("[enforce] 3-1) colapsar filas base-url phantom en su tomo sintético (#56)")
    _run("collapse_baseurl_tomos.py")
    print("[enforce] 3-2) fusionar fichas cross-source (tienda) en su tomo lmc (#56)")
    _run("merge_crosssource_into_lmc.py")
    print("[enforce] 3a) normalizar títulos (nº + marcador de kind + des-contaminar)")
    _run("fix_lmc_display_titles.py")
    print("[enforce] 3a2) orden de Edición Especial: '{serie} {vol} Edición Especial'")
    _run("fix_especial_title_order.py")
    print("[enforce] 3b) desambiguar títulos de display que colisionan")
    _run("fix_listadomanga_title_collisions.py")
    print("[enforce] 3c1) slug de TIPO de edición por término del título (#69, no-lmc)")
    _run("canonicalize_edition_slugs.py")
    print("[enforce] 3c2) fusionar series_keys mecánicamente duplicadas (#70)")
    _run("merge_duplicate_series.py")
    print("[enforce] 3c3) unificar publisher dentro de cada edición")
    _run("normalize_edition_publishers.py")
    print("[enforce] 3c4) re-alinear prefijo del edition_key con el series_key")
    _run("fix_edition_key_prefix.py")
    print("[enforce] 3c5) títulos: palabra de edición duplicada + 'Regular' sobrante")
    _run("fix_title_edition_words.py")
    print("[enforce] 3b2) re-derivar cluster_key (edition_key cambió en standardize → "
          "el cluster viejo queda stale; sin esto consolidate no fusiona)")
    _run("backfill_cluster_key.py")
    print("[enforce] 3c) dedup por fuente sintética compartida (gotcha #54)")
    _run("dedup_synthetic_source.py")
    print("[enforce] 4) consolidar (1 fila/producto)")
    _run("consolidate_sources.py")
    print("[enforce] 4b) re-normalizar títulos lmc POST-consolidate (el merge de filas "
          "puede revivir un título contaminado que el fixer ya había limpiado — "
          "sin esto el enforcer necesitaba 2 pasadas para converger)")
    _run("fix_lmc_display_titles.py")
    _run("fix_especial_title_order.py")
    print("[enforce] 5) dedup de portadas del carrusel")
    _run("dedup_carousel_images.py", "--all")
    print("[enforce] 6) slugs")
    _run("generate_slugs.py")
    print("[enforce] LISTO — reglas de agrupación re-aplicadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
