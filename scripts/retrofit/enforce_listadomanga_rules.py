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
    publisher unificado por edición (normalize_edition_publishers) +
    un ISBN-13 = un producto (merge_isbn_duplicates, invariante ISBNDUP).
  - cluster_key tier-0 lmc, consolidate, dedup de portadas, slugs.

Corré esto SIEMPRE DESPUÉS del skill de standardize (y el pipeline lo corre solo).
Idempotente.

Items aprobados y el paso 7 (WO-D, 2026-07-07): varios pasos de esta cadena
(edition_display, fix_edition_country, unify_coleccion_edition,
fix_listadomanga_title_collisions, dedup_carousel_images — ver `is_approved` en
cada uno) SALTEAN las filas con `approved_at` (golden records) para no pisar
metadata que el owner confirmó a mano. Riesgo: si esos pasos saltean la fila
aprobada pero re-derivan sus HERMANAS (misma edición, sin aprobar), la fila
aprobada puede terminar con un `edition_key`/`cluster_key` viejo mientras sus
hermanas migran al nuevo esquema — el cluster se fragmenta en 2 cards para la
misma edición, y un delta futuro que llegue con la identidad NUEVA ya no
consolida contra la fila aprobada. El paso 7 (`apply_approvals.py`, fuente
única — se invoca, no se copia su lógica) re-materializa el log durable de
aprobaciones (`data/approvals.jsonl`) al FINAL de la cadena: matchea primero
por `cluster_key` y, si cambió, hace fallback por `url` — así el flag
`approved_at` siempre termina en la fila que HOY representa ese producto,
aunque el cluster_key haya derivado durante la cadena. Es best-effort (no
vuelve a FUSIONAR dos filas ya fragmentadas — eso requeriría re-clusterizar),
pero evita que la aprobación quede huérfana en una fila stale. Idempotente
(confirmado en apply_approvals.py: last-wins por clave, no-op si el estado ya
coincide).

Uso:
  .venv/bin/python scripts/retrofit/enforce_listadomanga_rules.py
"""
from __future__ import annotations
import argparse, json, sys, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = str(ROOT / ".venv" / "bin" / "python")
ITEMS = ROOT / "data" / "items.jsonl"
RETRO = ROOT / "scripts" / "retrofit"

sys.path.insert(0, str(ROOT / "scripts"))
try:  # import dual robusto (CLI directo vs wrapper raíz bajo pytest)
    from manga_watch import backup_and_rotate, is_approved  # noqa: E402
except ImportError:  # pragma: no cover
    from scripts.manga_watch import backup_and_rotate, is_approved  # noqa: E402


def _recover_edition_display(include_approved: bool = False) -> tuple[int, int]:
    """edition_display = título oficial de la coleccion, recuperado del
    `description` (`collection_title · edition · …`). Determinístico, sin red.

    Items aprobados (`approved_at`) se saltean por defecto (WO-D 2026-07-07):
    devuelve (n_recuperados, n_aprobados_saltados)."""
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]
    n = 0
    skipped_approved = 0
    for it in items:
        if "coleccion.php" not in (it.get("url", "") or ""):
            continue
        if is_approved(it) and not include_approved:
            skipped_approved += 1
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
    return n, skipped_approved


def _run(script: str, *args: str) -> None:
    """Corre un retrofit de la cadena. Antes tragaba fallos (check=False):
    un crash a mitad de la cadena de 20+ pasos dejaba el corpus a medias sin
    señal. Ahora captura el returncode y ABORTA la cadena al primer fallo con
    SystemExit(rc) — el pipeline (shell) lo recoge en FAILED_STEPS."""
    print(f">>> {script} {' '.join(args)}")
    r = subprocess.run([PY, str(RETRO / script), *args], cwd=str(ROOT))
    if r.returncode != 0:
        print(f"[enforce] ✗ FALLÓ {script} (rc={r.returncode}) — abortando la cadena.",
              file=sys.stderr)
        raise SystemExit(r.returncode)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true",
                    help="Salta el dedup de portadas del carrusel (network-heavy). "
                         "Para el pipeline delta/full, que ya corre su propio "
                         "dedup_carousel_images en [4h].")
    ap.add_argument("--include-approved", action="store_true",
                    help="También re-deriva items aprobados (golden records) en los pasos "
                         "de esta cadena que lo soportan (edition_display, país=edición, "
                         "coleccion=edición, colisiones de título, dedup de portadas). Por "
                         "defecto se saltean. Ver WO-D (2026-07-07) y el paso final "
                         "'apply_approvals' más abajo.")
    args = ap.parse_args()
    # Flag propagado a los pasos de ESTA cadena que ya soportan el guard is_approved
    # (WO-D 2026-07-07). Los pasos que no son dominio de WO-D (fix_edition_key_anomalies,
    # disambiguate_coleccion_editions, etc.) no lo reciben — su propio guard, si lo
    # tienen, es responsabilidad de la ronda que los toque.
    _approved_flag = ("--include-approved",) if args.include_approved else ()
    # Backup pre-enforce (convención del repo: data/backups/items.jsonl/, rota máx 3).
    # El enforcer reescribe items.jsonl vía su cadena de retrofits; un snapshot al
    # inicio permite restaurar si la cadena aborta a media pasada.
    if ITEMS.exists() and ITEMS.stat().st_size > 0:
        bak = backup_and_rotate(ITEMS, "enforce-lmc")
        print(f"[enforce] 0) backup → {bak}")
    print("[enforce] 1) edition_display oficial (desde description, sin red)")
    n, skipped = _recover_edition_display(include_approved=args.include_approved)
    print(f"    edition_display recuperados: {n}" + (f" (aprobados saltados: {skipped})" if skipped else ""))
    print("[enforce] 2) país = edición")
    _run("fix_edition_country.py", *_approved_flag)
    print("[enforce] 2b) anomalías de edition_key (panini-es→panini, xx→país inferido)")
    _run("fix_edition_key_anomalies.py")
    print("[enforce] 3) una /coleccion = una edición (incl. fichas de tienda cross-source)")
    _run("unify_coleccion_edition.py", *_approved_flag)
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
    _run("fix_listadomanga_title_collisions.py", *_approved_flag)
    print("[enforce] 3c1) slug de TIPO de edición por término del título (#69, no-lmc)")
    _run("canonicalize_edition_slugs.py")
    print("[enforce] 3c2) fusionar series_keys mecánicamente duplicadas (#70)")
    _run("merge_duplicate_series.py")
    print("[enforce] 3c2b) fusionar filas que comparten ISBN-13 (mismo producto)")
    _run("merge_isbn_duplicates.py")
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
    if args.fast:
        print("[enforce] 5) dedup de portadas del carrusel — SALTADO (--fast)")
    else:
        print("[enforce] 5) dedup de portadas del carrusel")
        _run("dedup_carousel_images.py", "--all", *_approved_flag)
    print("[enforce] 6) slugs")
    _run("generate_slugs.py")
    print("[enforce] 7) re-aplicar aprobaciones (anti-fragmentación)")
    _run("apply_approvals.py")
    print("[enforce] LISTO — reglas de agrupación re-aplicadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
