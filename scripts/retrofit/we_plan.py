#!/usr/bin/env python3
"""we_plan.py — planificador determinista (0 tokens LLM) del skill
`/watch-whakoom-covers`, Step 1.

Selecciona items ES (España) candidatos a mejora de portada por la vía
"whakoom por página de edición" (owner, 2026-09-02): sin imagen, o portada de
baja calidad (`--target-rule area|scale`, default `area` — ver nota abajo),
con `volume <= 11` o vacío/oneshot (Whakoom sólo lista los primeros ~11 tomos
de una edición sin login; `/todos` y `/comics/` requieren login → esos items
NO son resolubles por esta vía, ver docs/scraper/sources/whakoom.md).

Por cada target arma:
- la query Bing `site:whakoom.com "<series_display>" <publisher>` para que el
  agente (Chrome del skill) localice la página `/ediciones/<id>/<slug>`;
- `listado.total_tomos` — **REMOTO por defecto (endurecimiento #1, tanda 3,
  2026-09-02)**: si `data/listadomanga_collection_meta.jsonl` (caché poblado
  por `listadomanga_meta.py`, ver ese módulo) ya tiene una fila para el
  `coleccion_id` del item, se usa el `total_tomos` REAL que reporta
  `listadomanga.es/coleccion.php?id=N` (`listado.source = "listadomanga_remota"`).
  Si NO hay fila cacheada, cae al heurístico LOCAL de siempre (cuántos items
  del corpus comparten el mismo `edition_key`; `listado.source = "local_count"`,
  menor confianza — puede infra-contar series en curso con volúmenes aún no
  ingestados). `we_plan.py` en sí NO hace red (mismo perfil que `sc_plan.py`);
  el fetch real lo dispara `listadomanga_meta.py --from-plan` como Step 1b del
  skill (ver SKILL.md) ANTES de la corrida final de `we_plan.py` que arma
  `.tmp_we_plan.json`. `listado.ongoing` viaja también (True si la colección
  remota tiene tomos anunciados aún sin editar) — `we_resolve.py` lo usa para
  aceptar `total_tomos` de whakoom `>=` en vez de `==` exacto en series en
  curso (whakoom también puede llevar su contador desactualizado, ver
  whakoom.md § 6).
- `listado.formato` / `listado.paginas` / `listado.editorial` — del caché
  remoto si está disponible; si no, `formato` cae al caché legado de
  `whakoom_edition_map.jsonl` (poblado por `we_resolve.py` en corridas
  previas) y `paginas`/`editorial` quedan vacíos. Usados por el guard de
  reedición de `we_resolve.py` (oneshots / ediciones hermanas del mismo
  publisher, ver whakoom.md § 6).
- `edition_url` — si el caché ya tiene una resolución PREVIA de esta serie+
  editorial+país (`method == "whakoom_edicion_page"`), se reutiliza sin
  volver a buscar en Bing.

Por qué `--target-rule area` es el DEFAULT acá (a diferencia de `sc_plan.py`,
que desde 2026-09-02 usa `scale` por default, gotcha #172/#175): sobre el
corpus real ES, `scale` deja sólo 12 portadas candidatas (10 resolubles
≤11 tomos) — insuficiente para operar la vía a escala. `area` (< 90 000 px,
`fetch_better_covers.LOW_QUALITY_PX`) da 488 (369 resolubles) — es el pool
que efectivamente motivó esta vía (portadas `static.listadomanga.com` a
~210×300 px). `--target-rule scale` sigue disponible para acotar a las que
además se ESTIRAN mal en la card real.

Caché append-only: `data/whakoom_edition_map.jsonl`, una fila por resolución
intentada (exitosa o no) — `{series_key, series_display, publisher, country,
listado_coleccion_id, total_tomos, formato, whakoom_edition_id,
whakoom_edition_url, resolved_at, method}`. La escribe `we_resolve.py`, no
este script. `we_plan.py` sólo LEE el caché (última fila por
`listado_coleccion_id` gana).

Escribe `.tmp_we_plan.json` (lista de targets, consumida por el loop del
Step 3 del skill). Con `--dry-run` no escribe el archivo — sólo imprime el
resumen (útil para inspeccionar el universo sin tocar disco).

Uso:
    we_plan.py                              # todos los targets ES pendientes
    we_plan.py --limit 20
    we_plan.py --slugs slug1,slug2
    we_plan.py --dry-run
    we_plan.py --target-rule scale          # criterio de sc_plan (más estricto)
    we_plan.py --include-approved
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any

_SCRIPTS_RETROFIT = Path(__file__).resolve().parent
if str(_SCRIPTS_RETROFIT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_RETROFIT))

import fetch_better_covers as fbc  # type: ignore
import listadomanga_meta  # type: ignore — caché de metadata remota (endurecimiento #1, tanda 3)
import sc_plan  # type: ignore — reusa get_dims_local/reference_placeholder_reason/reference_sha256 (fuente única, evita drift)

# Umbrales importados de fbc — SIEMPRE los mismos que sc_plan.py / producción,
# nunca redefinidos acá (fuente única).
MIN_REF_PX = fbc.MIN_REF_PX
LOW_QUALITY_PX = fbc.LOW_QUALITY_PX
UPSCALE_TARGET_MIN = fbc.UPSCALE_TARGET_MIN

DEFAULT_TARGET_RULE = "area"  # ver docstring — distinto del default de sc_plan.py

_COLECCION_ID_RE = re.compile(r"listadomanga\.es/coleccion\.php\?id=(\d+)")

# Volumen máximo público sin login (Whakoom muestra ~11 tomos en la página
# principal de una edición; el resto vive en /todos, que en la práctica está
# detrás de captcha/rate-limit agresivo — tratado como no resoluble, ver
# HECHOS del reconocimiento en la ficha de fuente).
MAX_PUBLIC_VOLUME = 11


def _default_data_path(name: str) -> Path:
    data_dir = os.environ.get("MANGA_WATCH_DATA_DIR")
    base = Path(data_dir) if data_dir else _SCRIPTS_RETROFIT.parent.parent / "data"
    return base / name


def volume_resolvable(item: dict[str, Any]) -> bool:
    """True si el volumen del item es resoluble sin login (<=11 o vacío/oneshot)."""
    v = str(item.get("volume") or "").strip()
    if not v:
        return True
    try:
        return int(v) <= MAX_PUBLIC_VOLUME
    except ValueError:
        # Volumen no numérico ("1-4", "Especial"...) — no podemos comparar
        # contra el límite público; conservador, se trata como no resoluble.
        return False


def extract_coleccion_id(item: dict[str, Any]) -> int | None:
    """Id de `listadomanga.es/coleccion.php?id=N` del item, si tiene uno.

    Busca en `url` (top-level) y en cada `sources[].url` — el mismo patrón
    que usa el resto del pipeline para reconocer un item de ListadoManga."""
    blobs = [item.get("url", "")] + [s.get("url", "") for s in (item.get("sources") or [])]
    for b in blobs:
        m = _COLECCION_ID_RE.search(b or "")
        if m:
            return int(m.group(1))
    return None


def _load_cache(cache_path: Path) -> dict[int, dict[str, Any]]:
    """Última fila por `listado_coleccion_id` (append-only, última gana)."""
    cache: dict[int, dict[str, Any]] = {}
    if not cache_path.exists():
        return cache
    for line in cache_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        cid = row.get("listado_coleccion_id")
        if isinstance(cid, int):
            cache[cid] = row
    return cache


def _load_already_in_preview(preview_path: Path) -> set[tuple[str, str, str]]:
    """(slug, action, target) ya adjudicados por ESTE skill (candidata con
    `via == "whakoom_edicion"`), en cualquier estado."""
    already: set[tuple[str, str, str]] = set()
    if not preview_path.exists():
        return already
    try:
        for e in json.loads(preview_path.read_text(encoding="utf-8")):
            for c in e.get("candidates", []):
                if c.get("via") == "whakoom_edicion":
                    already.add((e.get("slug", ""), c.get("action", "replace_cover"), c.get("target", "")))
    except (ValueError, OSError):
        pass
    return already


def _bing_search_url(query: str) -> str:
    """Bing IMÁGENES (no Bing web) — verificado en vivo (piloto real, 2026-09-02):
    `bing.com/search` (web) devolvió un challenge/captcha ("Resuelve el desafío
    siguiente para continuar") de forma consistente para queries `site:`, incluso
    en una sesión de Chrome autenticada del owner — NUNCA se intenta resolver
    (regla dura). `bing.com/images/search` con la MISMA query NO fue challengeada
    (mismo endpoint que ya usa `sc_plan.py` a escala, 366 fetches sin bloqueos,
    2026-07-11) — cada resultado trae `purl` (page URL) en su atributo `m`, que
    es la página `/ediciones/` real, aunque sea una búsqueda de imágenes. Ver
    docs/scraper/sources/whakoom.md § 6 y gotcha nueva sobre el hallazgo.

    OJO: a diferencia de Bing web, Bing Imágenes NO parece honrar estrictamente
    la frase exacta entre comillas — puede devolver ediciones de Whakoom sin
    relación con la serie buscada. El skill filtra client-side por token de la
    serie ANTES de abrir una candidata (ver SKILL.md Step 2b) — `we_resolve.py`
    igual la rechazaría por editorial/idioma/total de tomos, pero el filtro
    evita gastar navegaciones en candidatas obviamente no relacionadas."""
    return f"https://www.bing.com/images/search?q={urllib.parse.quote(query)}&first=1"


def build_query(item: dict[str, Any]) -> str:
    series = (item.get("series_display") or item.get("title") or "").strip()
    pub = fbc._simplify_publisher(item.get("publisher", "") or "")
    parts = [f'site:whakoom.com "{series}"'] if series else ["site:whakoom.com"]
    if pub:
        parts.append(pub)
    return " ".join(parts)


def build_plan(
    items: list[dict[str, Any]],
    *,
    images_dir: Path,
    cache_by_coleccion: dict[int, dict[str, Any]],
    already_in_preview: set[tuple[str, str, str]],
    limit: int = 0,
    slugs: list[str] | None = None,
    include_approved: bool = False,
    target_rule: str = DEFAULT_TARGET_RULE,
    remote_meta_by_coleccion: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    edition_counts: Counter[str] = Counter(
        it.get("edition_key") for it in items if it.get("edition_key")
    )
    slugs_filter = set(slugs) if slugs else None
    remote_meta_by_coleccion = remote_meta_by_coleccion or {}

    targets: list[dict[str, Any]] = []
    for item in items:
        if (item.get("country") or "") != "España":
            continue
        if slugs_filter and item.get("slug") not in slugs_filter:
            continue
        if item.get("approved_at") and not include_approved:
            continue
        if not volume_resolvable(item):
            continue

        slug = item.get("slug", "")
        imgs = item.get("images") or []
        local = imgs[0].get("local", "") if imgs else ""
        ref_url = imgs[0].get("url", "") if imgs else ""
        w, h = sc_plan.get_dims_local(local, images_dir)
        px = w * h

        placeholder_why = sc_plan.reference_placeholder_reason(local, ref_url, images_dir)
        if not local or px < MIN_REF_PX or placeholder_why:
            reference_kind = "none" if not placeholder_why else "placeholder"
            local = ""
            ref_url = ""
            px = 0
        else:
            if target_rule == "scale":
                if fbc.cover_upscale_factor(w, h) < UPSCALE_TARGET_MIN:
                    continue
            else:  # "area" — default acá, ver docstring
                if px >= LOW_QUALITY_PX:
                    continue
            reference_kind = "real"

        skip_key = (slug, "replace_cover", "")
        if skip_key in already_in_preview:
            continue

        coleccion_id = extract_coleccion_id(item)
        cache_row = cache_by_coleccion.get(coleccion_id) if coleccion_id is not None else None
        cached_edition_url = ""
        if cache_row and cache_row.get("method") == "whakoom_edicion_page":
            cached_edition_url = cache_row.get("whakoom_edition_url", "") or ""

        edition_key = item.get("edition_key", "")
        local_total_tomos = edition_counts.get(edition_key) if edition_key else None

        # Endurecimiento #1 (tanda 3, 2026-09-02): preferir el total_tomos
        # REMOTO (listadomanga.es real) sobre el heurístico local — ver
        # docstring del módulo. `remote_meta` es None si el caché de
        # `listadomanga_meta.py` todavía no tiene fila para este coleccion_id
        # (Step 1b del skill no corrió, o esta colección no se fetcheó aún).
        remote_meta = remote_meta_by_coleccion.get(coleccion_id) if coleccion_id is not None else None
        if remote_meta and remote_meta.get("total_tomos") is not None:
            listado_total_tomos = remote_meta["total_tomos"]
            listado_source = "listadomanga_remota"
            listado_ongoing = bool(remote_meta.get("ongoing"))
            formato = remote_meta.get("formato", "") or (cache_row or {}).get("formato", "") or ""
            paginas = remote_meta.get("paginas", "") or ""
            editorial = remote_meta.get("editorial", "") or ""
        else:
            listado_total_tomos = local_total_tomos
            listado_source = "local_count"
            listado_ongoing = False
            formato = (cache_row or {}).get("formato", "") or ""
            paginas = ""
            editorial = ""

        query = build_query(item)
        targets.append({
            "slug": slug,
            "title": item.get("title", ""),
            "series_display": item.get("series_display", ""),
            "series_key": item.get("series_key", ""),
            "publisher": item.get("publisher", ""),
            "country": item.get("country", ""),
            "volume": str(item.get("volume") or ""),
            "pixels": px,
            "width": w,
            "height": h,
            "reference_kind": reference_kind,
            "image_ref_local": local,
            "image_ref_url": ref_url,
            "reference_sha256": sc_plan.reference_sha256(local, images_dir) if reference_kind == "real" else "",
            "listado": {
                "coleccion_id": coleccion_id,
                "total_tomos": listado_total_tomos,
                "formato": formato,
                "paginas": paginas,
                "editorial": editorial,
                "ongoing": listado_ongoing,
                "source": listado_source,
                "local_total_tomos": local_total_tomos,
            },
            "query": query,
            "bing_url": _bing_search_url(query),
            "edition_url": cached_edition_url,
            "candidate_action": "replace_cover",
            "candidate_target": "",
            "target_label": "portada",
        })

    # Peor primero: sin imagen antes que con imagen chica; dentro de "con
    # imagen", menor resolución primero (mismo criterio que sc_plan --target-rule area).
    targets.sort(key=lambda t: (0 if t["pixels"] == 0 else 1, t["pixels"]))
    if slugs_filter is not None:
        return targets  # filtro por identidad exacta — --limit no aplica
    return targets[:limit] if limit else targets


def compute_universe_stats(items: list[dict[str, Any]]) -> dict[str, int]:
    """Conteo del universo ES completo (sin los guards de "ya en preview"/caché
    — es el panorama crudo para el reporte al owner), partido por resoluble
    (`volume <= 11` o vacío) vs no-resoluble (>11, requiere login)."""
    es = [it for it in items if (it.get("country") or "") == "España"]
    stats = {
        "es_total": len(es),
        "no_image_total": 0, "no_image_resolvable": 0,
        "low_area_total": 0, "low_area_resolvable": 0,
        "resolvable_total": 0, "not_resolvable_total": 0,
    }
    for it in es:
        resolvable = volume_resolvable(it)
        if resolvable:
            stats["resolvable_total"] += 1
        else:
            stats["not_resolvable_total"] += 1
        imgs = it.get("images") or []
        has_local = bool(imgs and imgs[0].get("local"))
        if not has_local:
            stats["no_image_total"] += 1
            if resolvable:
                stats["no_image_resolvable"] += 1
            continue
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=0, help="Máximo de targets. 0 = TODOS (default).")
    ap.add_argument("--slugs", default="", help="CSV de slugs exactos a procesar (ignora --limit).")
    ap.add_argument("--dry-run", action="store_true", help="No escribe --out; sólo imprime el resumen.")
    ap.add_argument("--include-approved", action="store_true",
                    help="Incluye items con approved_at (golden records). Por defecto se excluyen.")
    ap.add_argument("--target-rule", choices=["area", "scale"], default=DEFAULT_TARGET_RULE,
                    help="Criterio de 'baja calidad' de portada. 'area' (default acá, "
                         "distinto de sc_plan.py): píxeles < 90 000. 'scale': factor de "
                         "reescalado en card >= 1.6 (mismo default que sc_plan.py).")
    ap.add_argument("--items", type=Path, default=None)
    ap.add_argument("--preview", type=Path, default=None)
    ap.add_argument("--cache", type=Path, default=None)
    ap.add_argument("--meta-cache", type=Path, default=None,
                     help="Caché de listadomanga_meta.py (data/listadomanga_collection_meta.jsonl "
                          "por defecto). Sólo se LEE acá — nunca se fetchea.")
    ap.add_argument("--images-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path(".tmp_we_plan.json"))
    args = ap.parse_args(argv)

    items_path = args.items if args.items is not None else _default_data_path("items.jsonl")
    preview_path = args.preview if args.preview is not None else _default_data_path("cover_preview.json")
    cache_path = args.cache if args.cache is not None else _default_data_path("whakoom_edition_map.jsonl")
    meta_cache_path = args.meta_cache if args.meta_cache is not None else _default_data_path("listadomanga_collection_meta.jsonl")
    images_dir = args.images_dir if args.images_dir is not None else _default_data_path("images")

    if not items_path.exists():
        print(f"[ERROR] no existe {items_path}", file=sys.stderr)
        return 1

    items = [json.loads(l) for l in items_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    cache = _load_cache(cache_path)
    remote_meta = listadomanga_meta.load_meta_cache(meta_cache_path)
    already = _load_already_in_preview(preview_path)
    slugs = [s.strip() for s in args.slugs.split(",") if s.strip()] if args.slugs else None

    universe = compute_universe_stats(items)
    targets = build_plan(
        items,
        images_dir=images_dir,
        cache_by_coleccion=cache,
        already_in_preview=already,
        remote_meta_by_coleccion=remote_meta,
        limit=args.limit,
        slugs=slugs,
        include_approved=args.include_approved,
        target_rule=args.target_rule,
    )

    if not args.dry_run:
        args.out.write_text(json.dumps(targets, ensure_ascii=False), encoding="utf-8")

    print(f"Universo ES: {universe['es_total']} items — resolubles (vol<=11/vacío): "
          f"{universe['resolvable_total']} · no resolubles (vol>11, requiere login): "
          f"{universe['not_resolvable_total']}")
    print(f"  Sin imagen: {universe['no_image_total']} total, "
          f"{universe['no_image_resolvable']} resolubles")
    if not targets:
        print("No hay targets pendientes (ya en preview / filtros). Nada que hacer.")
        return 0

    n_no_img = sum(1 for t in targets if t["pixels"] == 0)
    n_low = len(targets) - n_no_img
    n_cached = sum(1 for t in targets if t["edition_url"])
    n_remote = sum(1 for t in targets if t["listado"]["source"] == "listadomanga_remota")
    n_local = len(targets) - n_remote
    n_distinct_coleccion_missing_remote = len({
        t["listado"]["coleccion_id"] for t in targets
        if t["listado"]["source"] == "local_count" and t["listado"]["coleccion_id"] is not None
    })
    print(f"\nTargets a procesar: {len(targets)} (sin imagen: {n_no_img}, portada chica: {n_low}); "
          f"{n_cached} con edición whakoom ya en caché.")
    print(f"  total_tomos: {n_remote} con referencia REMOTA (listadomanga_meta), "
          f"{n_local} con heurístico LOCAL de fallback "
          f"({n_distinct_coleccion_missing_remote} coleccion_id distintos sin meta cacheada — "
          f"correr listadomanga_meta.py --from-plan {args.out} antes de re-generar el plan "
          f"para maximizar la cobertura remota).")
    for t in targets[: args.limit or 20]:
        px_str = f"{t['pixels']:,} px" if t["pixels"] > 0 else "sin imagen"
        cached = " [cached]" if t["edition_url"] else ""
        print(f"  • {t['title'][:45]}  ({t['publisher']}) vol={t['volume'] or '-'} — {px_str}{cached}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
