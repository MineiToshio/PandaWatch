#!/usr/bin/env python3
"""sc_plan.py — planificador determinista (0 tokens LLM) del skill
`/watch-search-covers`, Step 1.

Compila a código el bloque Python embebido más grande que quedaba en el skill
(auditoría Fable 2026-07-08, hallazgo F9, ~300 líneas): identifica qué
imágenes necesitan búsqueda (portada de baja calidad / ausente, o galería con
`--include-gallery`/`--gallery-only`), arma la lista ORDENADA de variantes de
query por target (whakoom/yandex/texto, orden por idioma), aplica los guards
de exclusión (ya adjudicado en `cover_preview.json`, memoria de intentos de 30
días, referencia degenerada `< MIN_REF_PX`), y persiste el plan para el loop
interactivo de Chrome (Step 3 del skill).

Es 100% determinista — el mismo perfil de tarea que ya tenían
`sc_validate.py`/`sc_flush.py` (permanentes, con tests, tras 3 incidentes de
drift documentados cuando esta lógica se regeneraba a mano en cada corrida).
El SKILL.md invoca este script; no vuelve a embeber el algoritmo.

Escribe:
  - `.tmp_sc_plan.json`  — lista de targets (consumida por el Step 3 loop)
  - `.tmp_sc_acc.json`   — reset del acumulador self-healing de esta corrida

Uso:
    sc_plan.py                                   # todas las imágenes pendientes
    sc_plan.py --limit 20
    sc_plan.py --slug berserk-darkhorse-deluxe-1
    sc_plan.py --gallery-only
    sc_plan.py --include-gallery --query-extra "portada oficial"
    sc_plan.py --retry-failed
"""
from __future__ import annotations

import argparse
import datetime
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

SKIP_SIGNALS = frozenset({"variant_cover", "retailer_exclusive"})

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


def get_pixels_local(local_fname: str, images_dir: Path) -> int:
    if not local_fname:
        return 0
    p = images_dir / local_fname
    if not p.exists():
        return 0
    try:
        from PIL import Image
        with Image.open(p) as img:
            return img.width * img.height
    except Exception:
        return 0


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

    # Dedup conservando orden (variantes de TEXTO → Google udm=2)
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for label, q in variants:
        if q and q.lower() not in seen:
            seen.add(q.lower())
            out.append({"label": label, "query": q, "kind": "text",
                        "url": f"https://www.google.com/search?q={urllib.parse.quote(q)}&udm=2"})

    # Variante WHAKOOM (texto, Google udm=2) — va PRIMERO para ítems en Español.
    # Evidencia: whakoom produjo el 100% de los matches ES en la corrida piloto
    # (8/8); yandex-reverse 0 (los thumbnails de listadomanga no están indexados
    # por Yandex). Su CDN (i1.whakoom.com/small/) tiene upgrade automático a
    # /large/ en sc_validate.py.
    if lang == "Español":
        wk_q = " ".join(p for p in [series or title, volume] if p).strip()
        if wk_q:
            wk_query = f"site:whakoom.com {wk_q}"
            wk_url = f"https://www.google.com/search?q={urllib.parse.quote(wk_query)}&udm=2"
            out.insert(0, {"label": "whakoom", "query": wk_query, "kind": "text", "url": wk_url})

    # Variante REVERSE-IMAGE (Yandex) — segundo para ES, primero para otros idiomas.
    # Solo si hay URL http usable. Va detrás de whakoom para ES. EXCEPCIÓN: si la
    # referencia ES un thumbnail de listadomanga, se OMITE (Yandex no la indexa).
    old_url = (ref_url or "").strip()
    if old_url.startswith("http") and "static.listadomanga.com" not in old_url:
        yx = f"https://yandex.com/images/search?rpt=imageview&url={urllib.parse.quote(old_url, safe='')}"
        yandex_pos = 1 if (lang == "Español" and out and out[0].get("label") == "whakoom") else 0
        out.insert(yandex_pos, {"label": "yandex-reverse", "query": f"[reverse] {series or title}",
                                "kind": "reverse", "url": yx})

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
    include_gallery: bool = False,
    query_extra: str = "",
) -> list[dict[str, Any]]:
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
            px = get_pixels_local(local, images_dir)

            if img_idx == 0:
                if gallery_only:
                    continue
                if px < MIN_REF_PX:
                    if not include_no_image:
                        continue
                    local = ""
                    ref_url = ""
                    px = 0
                elif px >= LOW_QUALITY_PX:
                    continue
            else:
                if not gallery_only and not include_gallery:
                    continue
                if px < MIN_REF_PX or px >= LOW_QUALITY_PX:
                    continue

            action = "replace_cover" if img_idx == 0 else "replace_image"
            target_url = "" if img_idx == 0 else ref_url
            skip_key = (slug, action, target_url)
            if skip_key in already_in_preview or skip_key in recently_failed:
                continue

            targets.append({
                "slug": slug,
                "pixels": px,
                "img_idx": img_idx,
                "image_ref_local": local,
                "image_ref_url": ref_url,
                "candidate_action": action,
                "candidate_target": target_url,
                "target_label": "portada" if img_idx == 0 else f"galería {img_idx}",
                "variants": build_variants(item, ref_url=ref_url, query_extra=query_extra),
            })

    targets.sort(key=lambda x: (x["pixels"] > 0, x["pixels"]))
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
    ap.add_argument("--include-gallery", action="store_true",
                    help="Procesa portadas Y galería (sin esto, solo portadas).")
    ap.add_argument("--retry-failed", action="store_true",
                    help="Ignora la exclusión de 30 días de intentos fallidos.")
    ap.add_argument("--query-extra", default="",
                    help="Texto adicional al final de cada variante de query en Google.")
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

    targets = build_plan(
        items,
        images_dir=images_dir,
        already_in_preview=already_in_preview,
        recently_failed=recently_failed,
        limit=args.limit,
        slug_filter=args.slug,
        include_no_image=args.include_no_image,
        gallery_only=args.gallery_only,
        include_gallery=args.include_gallery,
        query_extra=args.query_extra,
    )

    args.out.write_text(json.dumps(targets, ensure_ascii=False), encoding="utf-8")
    args.acc_out.write_text("{}", encoding="utf-8")

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
