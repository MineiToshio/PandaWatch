#!/usr/bin/env python3
"""sc_plan.py — planificador determinista (0 tokens LLM) del skill
`/watch-search-covers`, Step 1.

Compila a código el bloque Python embebido más grande que quedaba en el skill
(auditoría Fable 2026-07-08, hallazgo F9, ~300 líneas): identifica qué
imágenes necesitan búsqueda (por defecto portada Y galería de baja calidad /
ausentes; acotable con `--only-covers`/`--gallery-only`), arma la lista ORDENADA de variantes de
query por target (whakoom/yandex/texto, orden por idioma), aplica los guards
de exclusión (ya adjudicado en `cover_preview.json`, memoria de intentos de 30
días, referencia degenerada `< MIN_REF_PX`), y persiste el plan para el loop
interactivo de Chrome (Step 3 del skill).

El target de PORTADA usa por defecto `--target-rule scale` (factor de
reescalado en card >= `fbc.UPSCALE_TARGET_MIN`, apaisadas primero — Etapa 1
de triage de imágenes, 2026-09-02, gotcha #172): el ÁREA sola (criterio viejo,
disponible con `--target-rule area`) marca 579 portadas como "baja calidad" en
el corpus real de las que el 91% se ven BIEN en la card del catálogo. La
galería (img_idx >= 1) sigue usando el criterio de área siempre — la Etapa 1
sólo evaluó portadas.

Es 100% determinista — el mismo perfil de tarea que ya tenían
`sc_validate.py`/`sc_flush.py` (permanentes, con tests, tras 3 incidentes de
drift documentados cuando esta lógica se regeneraba a mano en cada corrida).
El SKILL.md invoca este script; no vuelve a embeber el algoritmo.

Escribe:
  - `.tmp_sc_plan.json`  — lista de targets (consumida por el Step 3 loop)
  - `.tmp_sc_acc.json`   — reset del acumulador self-healing de esta corrida

Uso:
    sc_plan.py                                   # todas: portadas + galería
    sc_plan.py --limit 20
    sc_plan.py --slug berserk-darkhorse-deluxe-1
    sc_plan.py --only-covers                     # solo portadas (img_idx 0)
    sc_plan.py --gallery-only --query-extra "portada oficial"
    sc_plan.py --retry-failed
    sc_plan.py --target-rule area                # criterio viejo (compatibilidad)
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
import urllib.parse
from pathlib import Path
from typing import Any

_SCRIPTS_RETROFIT = Path(__file__).resolve().parent
if str(_SCRIPTS_RETROFIT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_RETROFIT))

import fetch_better_covers as fbc  # type: ignore

# Umbral de "baja calidad": SIEMPRE el mismo que fetch_better_covers.LOW_QUALITY_PX
# (constante única del motor, 90 000). Se importa de fbc en vez de hardcodear el
# número para que NUNCA pueda driftear (antes había un DEFAULT_MIN_PIXELS de
# 100 000 separado que generaba churn entre motor y skill; unificado 2026-07-08).
LOW_QUALITY_PX = fbc.LOW_QUALITY_PX

# Umbral de "referencia NO degenerada": por debajo de esto la imagen actual es un
# placeholder roto (típico: GIF de 1×1 px de Amazon "imagen no disponible") y NO
# sirve como referencia para _same_cover — el gate de aspect ratio y los hashes
# rechazarían toda candidata (0 matches garantizados). Estos targets se tratan
# como "sin imagen": se saltan salvo --include-no-image (y ahí van verified:false,
# sin variante reverse, porque no hay con qué hacer búsqueda por foto). Sin este
# guard los ~46 placeholders de 1px copan el --limit en cada corrida y nunca se
# llega a las portadas reales de baja resolución (causa estructural, 2026-06-12).
#
# SE IMPORTA de fbc (fuente única, SC-9): antes era un literal 2 500 acá y el motor
# tenía su propio literal 10 000 (SAME_COVER_MIN_REF_PX) sin nombre — dos umbrales
# de referencia DISTINTOS pero pelados, con riesgo de drift bajo --serper-fallback.
# fbc.MIN_REF_PX (2 500) = piso de placeholder degenerado (lo que usa el plan);
# fbc.SAME_COVER_MIN_REF_PX (10 000) = piso para _same_cover fiable (lo usa el motor).
MIN_REF_PX = fbc.MIN_REF_PX

# Criterio de selección de targets de PORTADA (img_idx 0). Default "scale" desde
# 2026-09-02 (Etapa 1 de triage de imágenes, gotcha #172): factor de reescalado
# en card >= fbc.UPSCALE_TARGET_MIN (1.6), apaisadas primero — ver
# `fbc.cover_upscale_factor`. "area" es el criterio viejo (píxeles < LOW_QUALITY_PX),
# conservado tras `--target-rule area` por compatibilidad; la galería (img_idx >= 1)
# SIEMPRE usa el criterio de área, independiente de este flag (no evaluado en
# la Etapa 1, que sólo cubrió portadas).
DEFAULT_TARGET_RULE = "scale"

SKIP_SIGNALS = frozenset({"variant_cover", "retailer_exclusive"})


# Motor de TEXTO primario = Bing image search (decisión 2026-07-11, investigación web +
# red team; ver docs/reference/gotchas.md). Razón principal NO es velocidad sino RIESGO DE
# CUENTA: scrapear Google con las cookies del owner (credentials:include) ata el 429/`/sorry`
# a su cuenta Google real y puede escalar a suspensión (Gmail/Ads colaterales). Bing es el
# motor más tolerante al scraping de los tres grandes, con patrón `murl` estable, y —crítico—
# HONRA el operador `site:` (verificado en vivo: devolvió covers de whakoom con
# site:whakoom.com), así que la vía whakoom se conserva. Google udm=2 queda como FALLBACK de
# emergencia documentado en el SKILL (no se emite en el plan). El reverse-by-photo sigue
# siendo Yandex (gratis) → Serper Lens (Step 5, server-side, sin cookies del owner).
def _text_search_url(query: str) -> str:
    return f"https://www.bing.com/images/search?q={urllib.parse.quote(query)}&first=1"


# Términos de edición que NO cubre fbc._EDITION_HINT, por idioma.
EXTRA_EDITION_HINT = {
    "special": {"Español": "edición especial", "Inglés": "special edition",
                "Italiano": "edizione speciale", "Francés": "édition spéciale",
                "Portugués": "edição especial", "default": "special edition"},
}


def _default_data_path(name: str) -> Path:
    data_dir = os.environ.get("MANGA_WATCH_DATA_DIR")
    base = Path(data_dir) if data_dir else _SCRIPTS_RETROFIT.parent.parent / "data"
    return base / name


def get_dims_local(local_fname: str, images_dir: Path) -> tuple[int, int]:
    """(width, height) del archivo local, vía la fuente única de dimensiones
    (`fbc._get_dims_from_bytes` — parsing de JPEG/PNG/WebP + fallback PIL para
    AVIF/GIF/WebP lossless, ya usada por el motor para candidatas). `(0, 0)` si
    no hay `local_fname`, el archivo no existe, o no se puede leer/decodificar."""
    if not local_fname:
        return 0, 0
    p = images_dir / local_fname
    if not p.exists():
        return 0, 0
    try:
        data = p.read_bytes()
    except OSError:
        return 0, 0
    return fbc._get_dims_from_bytes(data)


def get_pixels_local(local_fname: str, images_dir: Path) -> int:
    w, h = get_dims_local(local_fname, images_dir)
    return w * h


# ── Guard de referencia placeholder (gotcha #17x, 2026-09-02) ──────────────────
# Hallazgo del juez sobre la Etapa 2: 9/9 candidatas de Yandex reverse-image que
# usaron como CONSULTA una referencia placeholder (la "tarjeta de título" .gif de
# Rakuten — texto negro quemado sobre fondo pálido, gotcha #171) fueron basura
# sistemática (slides, cabeceras de blog, logos): reverse-image de un placeholder
# encuentra imágenes visualmente parecidas AL PLACEHOLDER, no a la portada real
# que reemplaza. El guard MIN_REF_PX (arriba) sólo atrapa referencias DEGENERADAS
# por TAMAÑO (1×1); la tarjeta de Rakuten tiene tamaño de canvas real (hasta
# 1004×1172 px) y lo pasa de largo. Se detecta por las DOS fuentes únicas de
# `image_store` (fbc.image_store — el motor ya las importa, no se reimplementan
# acá): `known_placeholder_url_reason(url)` (por URL — stem/fragmento/regla
# host+extensión de Rakuten `.gif`, sin tocar disco) y `placeholder_reason(bytes)`
# (por contenido del archivo local — estructural + firma sha1 de
# `data/placeholder_signatures.json`).
def reference_placeholder_reason(local_fname: str, ref_url: str, images_dir: Path) -> str:
    """"" si la referencia (portada o foto de galería) actual NO es un
    placeholder conocido; si lo es, el motivo (`known:...`/`tiny:...`/
    `solid:...`/`signature:...`, tal cual lo devuelven las fuentes únicas).
    Se consulta la URL primero (no toca disco) y sólo si no matchea se leen
    los bytes del archivo local, si existe."""
    reason = fbc.image_store.known_placeholder_url_reason(ref_url) if ref_url else ""
    if reason:
        return reason
    if not local_fname:
        return ""
    p = images_dir / local_fname
    if not p.exists():
        return ""
    try:
        data = p.read_bytes()
    except OSError:
        return ""
    return fbc.image_store.placeholder_reason(data)


def reference_sha256(local_fname: str, images_dir: Path) -> str:
    """sha256 hex del archivo local de referencia, o "" si no es legible.

    Se persiste en el target del plan (campo `reference_sha256`) como guard
    ANTI-DRIFT (gotcha #178, 2026-09-02): el loop de Chrome del Step 3 tarda
    decenas de minutos, y en esa ventana otra sesión puede purgar/reemplazar
    la imagen de referencia (p.ej. la purga de placeholders `.gif` de Rakuten
    de gotcha #176a corriendo en paralelo). `sc_validate.py`
    (`reference_drift_reason`) recalcula este hash contra el archivo actual
    ANTES de correr `_same_cover` — si cambió, el target se omite en vez de
    generar candidatas `verified:false` sobre una referencia que ya no es la
    portada real del item (el caso medido: 8 items con 1-2 candidatas de
    dudosa relación, `docs/reference/images.md` § "Etapa 2, tanda 2")."""
    if not local_fname:
        return ""
    p = images_dir / local_fname
    if not p.exists():
        return ""
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return ""


def edition_term(item: dict[str, Any]) -> str:
    """Tipo de edición en el idioma del item (kanzenban, boxset, edición especial...)."""
    lang = item.get("language", "")
    slug = fbc._edition_slug(item.get("edition_key", ""))
    if not slug:
        return ""
    hint = fbc._EDITION_HINT.get(slug, {})
    if hint:
        return hint.get(lang, hint.get("default", ""))
    extra = EXTRA_EDITION_HINT.get(slug, {})
    return extra.get(lang, extra.get("default", ""))


def build_variants(
    item: dict[str, Any], ref_url: str = "", query_extra: str = "",
) -> list[dict[str, str]]:
    """Lista ORDENADA de variantes de query — de la más específica a la más
    amplia. El loop del Step 3 las prueba en orden e itera hasta juntar
    suficientes matches. `ref_url`: URL de la imagen de referencia para Yandex
    reverse (la portada = images[0].url, o la foto de galería en proceso)."""
    title = (item.get("title") or "").strip()
    title_orig = (item.get("title_original") or "").strip()
    series = (item.get("series_display") or "").strip()
    volume = str(item.get("volume") or "").strip()
    lang = item.get("language", "")
    cover_term = fbc._COVER_TERM.get(lang, "cover")
    pub_short = fbc._simplify_publisher(item.get("publisher", ""))
    ed_term = edition_term(item)

    def clean(q: str) -> str:
        q = " ".join(q.split())
        return f"{q} {query_extra}".strip() if query_extra else q

    variants: list[tuple[str, str]] = []
    # 1. La más específica: serie + volumen + edición + editorial + portada
    if series:
        variants.append(("serie+vol+ed", clean(f"{series} {volume} {ed_term} {pub_short} {cover_term}")))
    # 2. title_original (lo que indexan los retailers locales) + editorial + portada
    if title_orig and title_orig != title:
        variants.append(("title_original", clean(f"{title_orig} {pub_short} {cover_term}")))
    # 3. title (en inglés/canónico) + editorial + portada
    if title:
        variants.append(("title", clean(f"{title} {pub_short} {cover_term}")))
    # 4. amplia: serie + volumen + edición + editorial (sin término portada)
    if series:
        variants.append(("amplia", clean(f"{series} {volume} {ed_term} {pub_short}")))

    # Dedup conservando orden (variantes de TEXTO → Bing image search, motor primario)
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for label, q in variants:
        if q and q.lower() not in seen:
            seen.add(q.lower())
            out.append({"label": label, "query": q, "kind": "text",
                        "engine": "bing", "url": _text_search_url(q)})

    # Variante WHAKOOM (texto, Bing image search) — va PRIMERO para ítems en Español.
    # Evidencia: whakoom produjo el 100% de los matches ES en la corrida piloto
    # (8/8); yandex-reverse 0 (los thumbnails de listadomanga no están indexados
    # por Yandex). Su CDN (i1.whakoom.com/small/) tiene upgrade automático a
    # /large/ en sc_validate.py. Bing HONRA `site:` (verificado en vivo 2026-07-11:
    # site:whakoom.com devolvió covers de whakoom /large/), así que la vía whakoom se
    # conserva al ser Bing el motor de texto primario.
    if lang == "Español":
        wk_q = " ".join(p for p in [series or title, volume] if p).strip()
        if wk_q:
            wk_query = f"site:whakoom.com {wk_q}"
            out.insert(0, {"label": "whakoom", "query": wk_query, "kind": "text",
                           "engine": "bing", "url": _text_search_url(wk_query)})

    # Variante REVERSE-IMAGE (Yandex) — segundo para ES, primero para otros idiomas.
    # Solo si hay URL http usable. Va detrás de whakoom para ES. EXCEPCIÓN: si la
    # referencia ES un thumbnail de listadomanga, se OMITE (Yandex no la indexa).
    old_url = (ref_url or "").strip()
    if old_url.startswith("http") and "static.listadomanga.com" not in old_url:
        yx = f"https://yandex.com/images/search?rpt=imageview&url={urllib.parse.quote(old_url, safe='')}"
        yandex_pos = 1 if (lang == "Español" and out and out[0].get("label") == "whakoom") else 0
        out.insert(yandex_pos, {"label": "yandex-reverse", "query": f"[reverse] {series or title}",
                                "kind": "reverse", "engine": "yandex", "url": yx})

    return out


def _load_already_in_preview(preview_path: Path) -> set[tuple[str, str, str]]:
    """(slug, action, target) ya adjudicados por ESTE skill (candidata con
    'match_dist'), en cualquier estado — pending/approved/rejected."""
    already: set[tuple[str, str, str]] = set()
    if not preview_path.exists():
        return already
    try:
        for e in json.loads(preview_path.read_text(encoding="utf-8")):
            for c in e.get("candidates", []):
                if "match_dist" in c:
                    already.add((e.get("slug", ""), c.get("action", "replace_cover"), c.get("target", "")))
    except (ValueError, OSError):
        pass
    return already


def _load_recently_failed(attempts_path: Path, retry_failed: bool) -> set[tuple[str, str, str]]:
    """(slug, action, target) con 0 matches en el último intento, hace <30 días."""
    recently_failed: set[tuple[str, str, str]] = set()
    if retry_failed or not attempts_path.exists():
        return recently_failed
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    last_attempt: dict[tuple[str, str, str], dict[str, Any]] = {}
    try:
        for line in attempts_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            a = json.loads(line)
            key = (a.get("slug", ""), a.get("action", ""), a.get("target", ""))
            prev = last_attempt.get(key)
            if prev is None or a.get("attempted_at", "") > prev.get("attempted_at", ""):
                last_attempt[key] = a
    except (ValueError, OSError):
        pass
    for key, a in last_attempt.items():
        if a.get("matches", 1) == 0:
            try:
                ts = datetime.datetime.fromisoformat(a["attempted_at"].replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=datetime.timezone.utc)
                if ts >= cutoff:
                    recently_failed.add(key)
            except (KeyError, ValueError):
                pass
    return recently_failed


def _target_sort_key(t: dict[str, Any], target_rule: str) -> tuple:
    """Orden de procesamiento de la lista final de targets (peor primero).

    - `pixels == 0` ("sin imagen", sólo con `--include-no-image`): siempre
      primero, igual que antes de esta tarea.
    - Portada (`img_idx == 0`) con `target_rule == "scale"`: apaisadas
      (`width > height`, recorte destruido — p.ej. `cover150/` de Aladin)
      primero, y dentro de cada grupo por factor de reescalado DESCENDENTE
      (peor = más estirada, primero). Recomendación del juez de visión de la
      Etapa 1 (gotcha #172 / docs/reference/images.md § "Etapa 1 — resultados").
    - Todo lo demás (galería, o portada con `target_rule == "area"` de
      compatibilidad): criterio viejo, por píxeles ASCENDENTE (peor = más
      chico, primero).
    """
    if t["pixels"] == 0:
        return (0, 0, 0.0)
    if target_rule == "scale" and t["img_idx"] == 0:
        is_landscape = t.get("width", 0) > t.get("height", 0)
        return (1, 0 if is_landscape else 1, -(t.get("scale") or 0.0))
    return (1, 2, float(t["pixels"]))


def build_plan(
    items: list[dict[str, Any]],
    *,
    images_dir: Path,
    already_in_preview: set[tuple[str, str, str]],
    recently_failed: set[tuple[str, str, str]],
    limit: int = 0,
    slug_filter: str = "",
    include_no_image: bool = False,
    gallery_only: bool = False,
    only_covers: bool = False,
    query_extra: str = "",
    target_rule: str = DEFAULT_TARGET_RULE,
    skip_counts: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """`skip_counts` (opcional, mutado in-place): contador de motivos de skip
    DURO que no quedan implícitos en el largo de `targets` — hoy sólo
    `placeholder_reference` (referencia actual detectada como placeholder
    conocido, ver `reference_placeholder_reason`). Puramente aditivo/opcional:
    no cambia el valor de retorno ni requiere que el caller lo pase."""
    targets: list[dict[str, Any]] = []
    for item in items:
        if slug_filter and item.get("slug") != slug_filter:
            continue
        if item.get("approved_at"):
            continue
        if SKIP_SIGNALS & set(item.get("signal_types", [])):
            continue
        slug = item.get("slug", "")

        # La portada es images[0] (única fuente de verdad). Si el item no tiene
        # images[], igual lo procesamos con un entry vacío para que la búsqueda
        # por TEXTO corra (sin Yandex reverse) — útil con --include-no-image.
        imgs = item.get("images") or []
        if not imgs:
            imgs = [{"url": "", "local": "", "kind": "gallery"}]

        for img_idx, img in enumerate(imgs):
            local = img.get("local", "")
            ref_url = img.get("url", "")
            # `orig_ref_url` NUNCA se pisa: para galería es la identidad del
            # slot (`candidate_target` — QUÉ foto se reemplaza), independiente
            # de si sirve o no como referencia de búsqueda/verificación.
            orig_ref_url = ref_url
            w, h = get_dims_local(local, images_dir)
            px = w * h

            # Guard de referencia placeholder (gotcha #171/#176a/#178, 2026-09-02):
            # una referencia puede tener tamaño de canvas real (no cae en el guard
            # MIN_REF_PX de abajo) y seguir siendo inservible como consulta —
            # p.ej. la "tarjeta de título" .gif de Rakuten. Reverse-image sobre un
            # placeholder devuelve basura sistemática (hallazgo del juez: 9/9).
            # Se detecta ANTES de aplicar el criterio de calidad (scale/area) —
            # un placeholder nunca es una referencia válida sin importar su tamaño.
            placeholder_why = reference_placeholder_reason(local, ref_url, images_dir)
            reference_kind = "real"

            if img_idx == 0:
                if gallery_only:
                    continue
                if px < MIN_REF_PX or placeholder_why:
                    if not include_no_image:
                        if placeholder_why and skip_counts is not None:
                            skip_counts["placeholder_reference"] = (
                                skip_counts.get("placeholder_reference", 0) + 1
                            )
                        continue
                    local = ""
                    ref_url = ""
                    px = 0
                    w = h = 0
                    reference_kind = "placeholder" if placeholder_why else "none"
                elif target_rule == "scale":
                    # Etapa 1 (2026-09-02): el ÁREA no predice si se ve mal —
                    # el factor de reescalado en card sí. Ver gotcha #172 y
                    # fbc.cover_upscale_factor.
                    if fbc.cover_upscale_factor(w, h) < fbc.UPSCALE_TARGET_MIN:
                        continue
                else:  # target_rule == "area" — criterio viejo, compatibilidad
                    if px >= LOW_QUALITY_PX:
                        continue
            else:
                # Galería (img_idx >= 1): se procesa POR DEFECTO, SIEMPRE con el
                # criterio de área (la Etapa 1 sólo evaluó portadas). Se salta
                # solo si se pidió --only-covers explícitamente.
                if only_covers:
                    continue
                if placeholder_why:
                    if not include_no_image:
                        if skip_counts is not None:
                            skip_counts["placeholder_reference"] = (
                                skip_counts.get("placeholder_reference", 0) + 1
                            )
                        continue
                    # El SLOT (candidate_target = orig_ref_url) se conserva —
                    # sigue identificando QUÉ foto de galería se reemplaza. Sólo
                    # se blanquea la referencia de BÚSQUEDA/verificación.
                    local = ""
                    ref_url = ""
                    px = 0
                    reference_kind = "placeholder"
                elif px < MIN_REF_PX or px >= LOW_QUALITY_PX:
                    continue

            action = "replace_cover" if img_idx == 0 else "replace_image"
            target_url = "" if img_idx == 0 else orig_ref_url
            skip_key = (slug, action, target_url)
            if skip_key in already_in_preview or skip_key in recently_failed:
                continue

            targets.append({
                "slug": slug,
                "pixels": px,
                "img_idx": img_idx,
                "width": w,
                "height": h,
                # None (no `inf`, no serializable en JSON estándar) cuando no hay
                # dimensiones utilizables — el mismo caso "sin imagen" de arriba.
                "scale": fbc.cover_upscale_factor(w, h) if (w > 0 and h > 0) else None,
                "image_ref_local": local,
                "image_ref_url": ref_url,
                # "real" (referencia utilizable) / "placeholder" (detectada por
                # image_store, blanqueada) / "none" (degenerada por tamaño, sin
                # placeholder conocido). El Step 3 del skill la lee para decidir
                # la vía de búsqueda — aunque ya es estructural: sin referencia
                # real no hay URL para armar la variante yandex-reverse (ver
                # build_variants), así que "placeholder"/"none" nunca la generan.
                "reference_kind": reference_kind,
                # sha256 del archivo de referencia AL MOMENTO DEL PLAN — sólo con
                # referencia real (si no hay archivo o no es "real" no hay nada
                # que proteger). Guard anti-drift (gotcha #178): sc_validate.py lo
                # recalcula contra el archivo actual antes de correr _same_cover.
                "reference_sha256": reference_sha256(local, images_dir) if reference_kind == "real" else "",
                "candidate_action": action,
                "candidate_target": target_url,
                "target_label": "portada" if img_idx == 0 else f"galería {img_idx}",
                "variants": build_variants(item, ref_url=ref_url, query_extra=query_extra),
            })

    targets.sort(key=lambda t: _target_sort_key(t, target_rule))
    return targets[:limit] if limit else targets


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=0,
                    help="Máximo de targets (imágenes) a procesar. 0 = TODAS (default).")
    ap.add_argument("--slug", default="", help="Procesa solo el item con ese slug exacto.")
    ap.add_argument("--include-no-image", action="store_true",
                    help="Incluye items sin imagen actual (candidatas quedan verified:false).")
    ap.add_argument("--gallery-only", action="store_true",
                    help="Salta portadas (img_idx 0); procesa solo galería (img_idx >= 1).")
    ap.add_argument("--only-covers", action="store_true",
                    help="Salta galería (img_idx >= 1); procesa solo portadas (img_idx 0).")
    ap.add_argument("--include-gallery", action="store_true",
                    help="DEPRECADO / no-op: la galería ya se procesa por defecto. "
                         "Se mantiene para no romper invocaciones viejas.")
    ap.add_argument("--retry-failed", action="store_true",
                    help="Ignora la exclusión de 30 días de intentos fallidos.")
    ap.add_argument("--query-extra", default="",
                    help="Texto adicional al final de cada variante de query en Google.")
    ap.add_argument("--target-rule", choices=["scale", "area"], default=DEFAULT_TARGET_RULE,
                    help="Criterio de selección de PORTADAS de baja calidad (img_idx 0; "
                         "la galería SIEMPRE usa área). 'scale' (default, 2026-09-02): "
                         "factor de reescalado en card (fbc.cover_upscale_factor) >= "
                         "fbc.UPSCALE_TARGET_MIN (1.6), apaisadas primero — gotcha #172. "
                         "'area' (criterio viejo, compatibilidad): píxeles < LOW_QUALITY_PX "
                         "(90 000).")
    ap.add_argument("--items", type=Path, default=None,
                    help="items.jsonl a leer (default: data/items.jsonl / MANGA_WATCH_DATA_DIR).")
    ap.add_argument("--preview", type=Path, default=None,
                    help="cover_preview.json (default: data/cover_preview.json).")
    ap.add_argument("--attempts", type=Path, default=None,
                    help="cover_search_attempts.jsonl (default: data/cover_search_attempts.jsonl).")
    ap.add_argument("--images-dir", type=Path, default=None,
                    help="Directorio del espejo local (default: data/images).")
    ap.add_argument("--out", type=Path, default=Path(".tmp_sc_plan.json"),
                    help="Ruta de salida del plan (default: .tmp_sc_plan.json).")
    ap.add_argument("--acc-out", type=Path, default=Path(".tmp_sc_acc.json"),
                    help="Ruta del acumulador a resetear (default: .tmp_sc_acc.json).")
    args = ap.parse_args(argv)

    items_path = args.items if args.items is not None else _default_data_path("items.jsonl")
    preview_path = args.preview if args.preview is not None else _default_data_path("cover_preview.json")
    attempts_path = args.attempts if args.attempts is not None else _default_data_path("cover_search_attempts.jsonl")
    images_dir = args.images_dir if args.images_dir is not None else _default_data_path("images")

    if not items_path.exists():
        print(f"[ERROR] no existe {items_path}", file=sys.stderr)
        return 1

    items = [json.loads(l) for l in items_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    already_in_preview = _load_already_in_preview(preview_path)
    recently_failed = _load_recently_failed(attempts_path, args.retry_failed)

    skip_counts: dict[str, int] = {}
    targets = build_plan(
        items,
        images_dir=images_dir,
        already_in_preview=already_in_preview,
        recently_failed=recently_failed,
        limit=args.limit,
        slug_filter=args.slug,
        include_no_image=args.include_no_image,
        gallery_only=args.gallery_only,
        only_covers=args.only_covers,
        query_extra=args.query_extra,
        target_rule=args.target_rule,
        skip_counts=skip_counts,
    )

    args.out.write_text(json.dumps(targets, ensure_ascii=False), encoding="utf-8")
    args.acc_out.write_text("{}", encoding="utf-8")

    n_placeholder_skipped = skip_counts.get("placeholder_reference", 0)
    if n_placeholder_skipped:
        print(f"Saltados DURO por referencia placeholder (known_placeholder_url_reason / "
              f"placeholder_reason — gotcha #171/#176a): {n_placeholder_skipped}. "
              f"Con --include-no-image entran como 'sin imagen' (reference_kind != 'real', "
              f"sólo búsqueda por texto, nunca Yandex reverse con esa referencia).")

    if not targets:
        print("No hay imágenes que necesiten búsqueda. Nada que hacer.")
        return 0

    by_slug = {it.get("slug"): it for it in items}
    n_items = len({t["slug"] for t in targets})
    print(f"Targets a procesar: {len(targets)} imágenes en {n_items} item(s)")
    for t in targets:
        it = by_slug.get(t["slug"], {})
        px_str = f"{t['pixels']:,} px" if t["pixels"] > 0 else "sin imagen"
        lbl = t["target_label"]
        print(f"  • {it.get('title', '')[:45]}  ({it.get('publisher', '')}) [{lbl}] — {px_str}  "
              f"· {len(t['variants'])} queries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
