#!/usr/bin/env python3
"""Auditoría de calidad de datos sobre data/items.jsonl (SOLO LECTURA).

Levanta alertas, no modifica nada. Categorías:
  - Imágenes: sin imagen, ref local rota, archivo basura (píxel/banner/placeholder),
    portada con URL basura, imagen pequeña/pixelada (<px), card != carrusel,
    archivo compartido entre muchas obras (placeholder reusado).
  - Procedencia: items sin sources[], source sin url.
  - Metadata: campos clave faltantes en items estandarizados.
  - Estructura: clusters con >1 fila, items estandarizados sin keys, slug faltante.

Además del reporte humano por stdout, escribe un **reporte JSON estructurado**
(`data/quality_report.json` por default) que consume el Panel de Calidad del
dashboard (web/quality.html) — cada alerta trae la lista de items afectados con
su URL para hacer worklists clickeables (deep-link al detalle o al gestor de
imágenes). Ver CLAUDE.md → "Panel de Calidad".

Uso: .venv/bin/python scripts/audit/data_quality.py [--px 90000] [--examples 8]
                                                     [--no-measure] [--no-json]
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "retrofit"))
from manga_watch import IMAGE_URL_BAD_PATTERNS, _cluster_completeness  # noqa: E402
# Reusamos la MISMA derivación de slug que el retrofit (fuente única de verdad)
# para detectar slugs "desincronizados" sin reimplementar la lógica.
import generate_slugs as _slugs  # noqa: E402

try:
    from PIL import Image
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

IMAGES = ROOT / "data" / "images"
DEFAULT_JSON_OUT = ROOT / "data" / "quality_report.json"

# Cap de items por categoría en el JSON: suficiente para una worklist completa
# sin inflar el archivo si una categoría se dispara por un bug.
MAX_ITEMS_PER_CATEGORY = 3000

# Prompts de fix copiables: para categorías que necesitan JUICIO (no hay script
# mecánico seguro). El usuario copia el prompt y lo pega en Claude, que lo
# resuelve. Son self-contained (el Claude que los recibe no tiene contexto).
_FIX_PROMPT_DUP = (
    "En el repo manga-watch, revisá posibles PRODUCTOS DUPLICADOS en "
    "data/items.jsonl: filas con cluster_key DISTINTO que comparten el mismo "
    "ISBN, o la misma combinación (series_key, edition_key, volume). Por cada "
    "grupo, decidí si son realmente el mismo producto. Si lo son, fusionalos en "
    "UNA fila con manga_watch.consolidate_by_cluster (uniendo sources[], "
    "imágenes con la portada canónica primera, y extras) y recalculá cluster_key "
    "con derive_cluster_key. Si son ediciones realmente distintas, dejalos. Hacé "
    "backup con backup_and_rotate antes de escribir. Reportá qué fusionaste."
)
_FIX_PROMPT_REF_ROTA = (
    "En el repo manga-watch, en data/items.jsonl hay items cuyo campo "
    "image_local apunta a un archivo que YA NO EXISTE en data/images/. Por cada "
    "uno: si image_url sigue vivo, re-descargá la portada al espejo local "
    "(scripts/image_store.py / mirror_candidate_images) y actualizá image_local + "
    "images[0]; si image_url está muerto, limpiá image_local para que caiga al "
    "fallback. Hacé backup antes. Reportá cuántos arreglaste."
)
_FIX_PROMPT_NO_SOURCES = (
    "En el repo manga-watch, en data/items.jsonl hay items sin sources[]. "
    "Reconstruí el array sources[] desde sus campos (url, source, price, country, "
    "stock_type, image_url) usando manga_watch.source_entry; si el item es basura "
    "o no es un producto, movelo fuera del catálogo. Backup antes. Reportá."
)
_FIX_PROMPT_SRC_NO_URL = (
    "En el repo manga-watch, hay items donde alguna entrada de sources[] no tiene "
    "url. Revisá cada uno y completá el url faltante de esa tienda, o quitá esa "
    "source si es inválida. Backup con backup_and_rotate antes de escribir."
)

# Metadatos de presentación + ARREGLO por categoría.
#   target: a dónde linkea cada item de la worklist ("image"→image-manager,
#           "detail"→index.html#/volume/<url>).
#   desc:   explicación EN CRISTIANO (para alguien que nunca vio la app).
#   fix:    cómo se arregla la categoría. kind ∈
#           "script" (botón ▶ que corre un retrofit del registry, con backup),
#           "skill"  (un skill LLM: se copia el comando y se corre en Claude),
#           "prompt" (prompt copiable que Claude ejecuta — para casos con juicio),
#           "manual" (se revisa a mano, sin acción automática).
def _fix(kind, *, script_id="", skill="", prompt="", hint=""):
    return {"kind": kind, "script_id": script_id, "skill": skill,
            "prompt": prompt, "hint": hint}

CATEGORY_META = {
    # estructura
    "multi_cluster": {
        "label": "Productos partidos en varias fichas", "group": "estructura",
        "severity": "error", "target": "detail",
        "desc": "El mismo producto quedó como varias filas separadas en vez de una sola ficha. Deberían unirse en una con todas sus tiendas.",
        "fix": _fix("script", script_id="consolidate_sources",
                    hint="Une las filas del mismo producto en una sola ficha (juntando sus tiendas). Seguro: hace backup y no borra datos."),
    },
    "dup_product": {
        "label": "Posibles productos duplicados", "group": "estructura",
        "severity": "warn", "target": "detail",
        "desc": "Dos o más fichas distintas que parecen el MISMO producto (mismo ISBN, o misma serie+edición+volumen). Probablemente deberían ser una sola.",
        "fix": _fix("prompt", prompt=_FIX_PROMPT_DUP,
                    hint="Necesita criterio (¿son el mismo o ediciones distintas?). Copiá el prompt y Claude las revisa y fusiona las que correspondan."),
    },
    "std_no_keys": {
        "label": "Procesados pero sin serie/edición", "group": "estructura",
        "severity": "error", "target": "detail",
        "desc": "Items marcados como ya procesados a los que les falta saber a qué serie o edición pertenecen. Quedó una inconsistencia.",
        "fix": _fix("skill", skill="/watch-standardize-catalog",
                    hint="El asistente de estandarización les reasigna serie/edición/volumen."),
    },
    "no_slug": {
        "label": "Sin dirección web propia (slug)", "group": "estructura",
        "severity": "error", "target": "detail",
        "desc": "Les falta el identificador de URL (ej. /item/berserk-deluxe-1). Sin esto no tienen página propia en la web nueva.",
        "fix": _fix("script", script_id="generate_slugs",
                    hint="Genera el slug que falta. Seguro: hace backup."),
    },
    # procedencia
    "no_sources": {
        "label": "Sin ninguna tienda/fuente", "group": "procedencia",
        "severity": "error", "target": "detail",
        "desc": "No tienen asociada ninguna tienda ni fuente: no se sabe de dónde salió el producto.",
        "fix": _fix("prompt", prompt=_FIX_PROMPT_NO_SOURCES,
                    hint="Copiá el prompt y Claude reconstruye sources[] o quita el item si es basura."),
    },
    "src_no_url": {
        "label": "Tienda sin enlace", "group": "procedencia",
        "severity": "warn", "target": "detail",
        "desc": "Una de las tiendas del producto no tiene link. No se puede hacer clic para ir a verlo/comprarlo.",
        "fix": _fix("prompt", prompt=_FIX_PROMPT_SRC_NO_URL,
                    hint="Copiá el prompt y Claude completa el link faltante o quita la tienda inválida."),
    },
    # imágenes
    "sin_imagen": {
        "label": "Sin foto de portada", "group": "imagenes",
        "severity": "warn", "target": "image",
        "desc": "No tienen imagen de portada. En el catálogo se ven con un ícono de libro genérico (📚).",
        "fix": _fix("skill", skill="/watch-search-covers",
                    hint="El asistente busca portadas en internet (las deja para que vos las apruebes)."),
    },
    "portada_url_basura": {
        "label": "Portada que es un banner/ícono, no la tapa", "group": "imagenes",
        "severity": "error", "target": "image",
        "desc": "Lo que se ve como portada en realidad es un banner, placeholder o ícono, no la tapa real del manga.",
        "fix": _fix("script", script_id="sync_cover_images",
                    hint="Limpia las portadas-basura y promueve una foto real si la hay. Seguro: hace backup."),
    },
    "ref_local_rota": {
        "label": "Foto guardada que ya no existe", "group": "imagenes",
        "severity": "error", "target": "image",
        "desc": "El item apunta a un archivo de imagen que ya no está en el disco: la foto quedó rota.",
        "fix": _fix("prompt", prompt=_FIX_PROMPT_REF_ROTA,
                    hint="Copiá el prompt y Claude re-descarga la portada o limpia la referencia rota."),
    },
    "archivo_tiny": {
        "label": "Imagen diminuta (no es una portada)", "group": "imagenes",
        "severity": "warn", "target": "image",
        "desc": "La imagen guardada pesa menos de 6KB: es un ícono o un puntito, no una portada de verdad.",
        "fix": _fix("script", script_id="fetch_better_covers",
                    hint="Busca una portada de mejor resolución por ISBN / web. Seguro: hace backup."),
    },
    "archivo_compartido": {
        "label": "Misma foto reusada en muchas obras", "group": "imagenes",
        "severity": "warn", "target": "image",
        "desc": "El mismo archivo de imagen lo usan 4+ obras distintas: señal de que es un placeholder reusado, no la portada real de cada una.",
        "fix": _fix("script", script_id="sync_cover_images",
                    hint="Detecta el placeholder reusado y limpia las portadas falsas. Seguro: hace backup."),
    },
    "pixelada": {
        "label": "Portada de baja resolución (borrosa)", "group": "imagenes",
        "severity": "warn", "target": "image",
        "desc": "La portada tiene muy pocos píxeles y se ve borrosa al ampliarla. Candidata a buscar una versión mejor.",
        "fix": _fix("script", script_id="fetch_better_covers",
                    hint="Busca una versión en alta resolución por ISBN / web. Seguro: hace backup."),
    },
    "card_ne_carrusel": {
        "label": "La foto de la tarjeta no es la del detalle", "group": "imagenes",
        "severity": "warn", "target": "image",
        "desc": "La foto que se ve en la tarjeta del catálogo no coincide con la primera del carrusel al abrir el detalle. Quedaron descoordinadas.",
        "fix": _fix("script", script_id="sync_cover_images",
                    hint="Re-sincroniza la portada de la tarjeta con la del carrusel. Seguro: hace backup."),
    },
    "carrusel_dup": {
        "label": "Foto repetida en el carrusel", "group": "imagenes",
        "severity": "warn", "target": "image",
        "desc": "En el carrusel del detalle aparece la MISMA foto dos o más veces (archivo o enlace idéntico). Conviene dejar una sola.",
        "fix": _fix("script", script_id="sync_cover_images",
                    hint="Quita las fotos repetidas del carrusel. Seguro: hace backup."),
    },
}


def is_junk_url(url: str) -> bool:
    if not url:
        return False
    low = url.lower()
    return any(p in low for p in IMAGE_URL_BAD_PATTERNS)


def norm(url: str) -> str:
    """Normaliza URL para comparar (sin esquema ni query)."""
    if not url:
        return ""
    u = url.split("?", 1)[0].split("#", 1)[0]
    u = u.replace("https://", "").replace("http://", "")
    return u.rstrip("/")


def _entry(it: dict, detail: str = "") -> dict:
    """Item de worklist serializable para el JSON."""
    return {
        "url": it.get("url", ""),
        "title": (it.get("title") or "")[:120],
        "source": it.get("source", ""),
        "image_url": it.get("image_url", ""),
        "image_local": it.get("image_local", ""),
        "detail": detail,
    }


def _dup_member(it: dict) -> dict:
    """Ficha (miembro) de un grupo de posibles duplicados — todos los campos que
    el panel muestra lado a lado para comparar."""
    return {
        "url": it.get("url", ""),
        "title": (it.get("title") or "")[:140],
        "source": it.get("source", ""),
        "publisher": it.get("publisher", ""),
        "country": it.get("country", ""),
        "language": it.get("language", ""),
        "price": it.get("price", ""),
        "volume": it.get("volume", ""),
        "edition_display": it.get("edition_display", ""),
        "isbn": it.get("isbn", ""),
        "image_url": it.get("image_url", ""),
        "image_local": it.get("image_local", ""),
    }


def _load_dup_decisions() -> set:
    """Signatures de grupos de duplicados YA decididos (distinct/merged) —
    el panel no los vuelve a mostrar. Viven en data/dup_decisions.jsonl,
    escrito por los endpoints /api/dup/decide y /api/dup/merge de serve.py."""
    out: set = set()
    p = ROOT / "data" / "dup_decisions.jsonl"
    try:
        for ln in open(p, encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = json.loads(ln)
                sig = d.get("signature")
                if sig and d.get("decision") in ("distinct", "merged"):
                    out.add(sig)
            except Exception:
                pass
    except Exception:
        pass
    return out


# Pasos del ciclo de vida del dato que se completan DESPUÉS del scrape (manuales
# o semi-manuales). Ver docs/scraper/PIPELINE-WALKTHROUGH.md. Cada paso reporta
# `pending` (items que aún no pasaron por el paso) y, donde aplica, `stale`
# (items donde el paso ya corrió pero quedó DESACTUALIZADO — p. ej. el slug se
# generó bien pero después cambió la edición y ya no coincide).
#   kind="script" → tiene un script mecánico en el registry → botón "▶ Arreglar"
#                   en el Panel de Calidad (corre vía /api/run con streaming).
#   kind="skill"  → es un skill LLM de Claude → NO se puede automatizar desde la
#                   UI; el panel muestra el conteo + el nombre del skill a tipear.
#   kind="link"   → requiere acción humana en otra página (aprobación manual).
def _compute_readiness(items: list[dict], *, multi_clusters: int,
                       card_ne_carrusel: int) -> list[dict]:
    DATA = ROOT / "data"

    def _count_lines(path: Path) -> int:
        try:
            return sum(1 for ln in open(path, encoding="utf-8") if ln.strip())
        except Exception:
            return 0

    # --- Estandarización: items sin standardized_at (excluye golden records) ---
    std_pending = sum(1 for it in items
                      if not it.get("standardized_at") and not it.get("approved_at"))

    # --- Slugs: pendientes (sin slug) + desincronizados (slug != recalculado) ---
    slug_pending = sum(1 for it in items if not it.get("slug"))
    slug_stale = 0
    try:
        clusters: dict[str, list] = defaultdict(list)
        for it in items:
            ck = it.get("cluster_key") or ""
            if ck:
                clusters[ck].append(it)
        for ck, grp in clusters.items():
            rep = _slugs._best_representative(grp)
            base = _slugs._derive_base_slug(rep)
            stored = ""
            for it in grp:
                s = (it.get("slug") or "").strip()
                if s:
                    stored = s
                    break
            # stale si hay slug guardado y el base recalculado ya no lo respalda
            # (ni exacto ni como prefijo de un sufijo de colisión -b/-c).
            if stored and base and stored != base and not stored.startswith(base + "-"):
                slug_stale += len(grp)
    except Exception:
        slug_stale = 0

    # --- Traducción: misma condición que translate_descriptions (KEY ausente,
    # no string vacío — un item ya procesado tiene description_es="" para ES). ---
    trans_pending = 0
    for it in items:
        if it.get("approved_at"):
            continue
        if (it.get("description") or "") and "description_es" not in it:
            trans_pending += 1
            continue
        for ex in (it.get("extras") or []):
            if (ex.get("description") or "") and "description_es" not in ex:
                trans_pending += 1
                break

    # --- Aliases de series: series_key distintos en la cola unmapped ---
    unmapped: set[str] = set()
    try:
        for ln in open(DATA / "unmapped_series.jsonl", encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            try:
                sk = json.loads(ln).get("series_key", "")
                if sk:
                    unmapped.add(sk)
            except Exception:
                pass
    except Exception:
        pass

    # --- Rareza: asignar (sin campo) + verificar ambiguas (boxset/artbook rare) ---
    rarity_assign = sum(1 for it in items if not it.get("rarity"))
    rarity_verify = sum(1 for it in items
                        if it.get("rarity") == "rare"
                        and not it.get("rarity_verified_at")
                        and it.get("product_type") in ("boxset", "artbook"))

    # --- Feedback y portadas candidatas ---
    feedback_pending = _count_lines(DATA / "feedback.jsonl")
    cover_pending = 0
    try:
        cp = json.load(open(DATA / "cover_preview.json", encoding="utf-8"))

        def _walk(o) -> int:
            c = 0
            if isinstance(o, dict):
                if o.get("status") == "pending":
                    c += 1
                for v in o.values():
                    c += _walk(v)
            elif isinstance(o, list):
                for v in o:
                    c += _walk(v)
            return c
        cover_pending = _walk(cp)
    except Exception:
        cover_pending = 0

    return [
        {"id": "standardize", "label": "Estandarización", "pending": std_pending,
         "stale": 0, "kind": "skill", "skill": "/watch-standardize-catalog",
         "script_id": "", "flags": {}, "link": "", "severity": "warn",
         "hint": "Items nuevos sin serie/edición/volumen. Corré el skill en Claude."},
        {"id": "aliases", "label": "Aliases de series", "pending": len(unmapped),
         "stale": 0, "kind": "skill", "skill": "/watch-enrich-series-aliases",
         "script_id": "", "flags": {}, "link": "", "severity": "warn",
         "hint": "Series sin canónico en series_aliases.yml. Corré el skill en Claude."},
        {"id": "slugs", "label": "Slugs (URLs del catálogo)", "pending": slug_pending,
         "stale": slug_stale, "kind": "script", "skill": "",
         "script_id": "generate_slugs", "flags": {}, "link": "", "severity": "error",
         "hint": "Pendientes = sin slug. Desincronizados = cambió la edición y el slug viejo no coincide. El botón regenera todo."},
        {"id": "translate", "label": "Traducción al español", "pending": trans_pending,
         "stale": 0, "kind": "script", "skill": "",
         "script_id": "translate_descriptions", "flags": {}, "link": "", "severity": "warn",
         "hint": "Items con descripción extranjera y sin description_es."},
        {"id": "rarity", "label": "Rareza — asignar", "pending": rarity_assign,
         "stale": 0, "kind": "script", "skill": "", "script_id": "set_rarity",
         "flags": {}, "link": "", "severity": "warn",
         "hint": "Items sin campo rarity. Asignación mecánica determinística."},
        {"id": "rarity_verify", "label": "Rareza — verificar ambiguas (opcional)",
         "pending": rarity_verify, "stale": 0, "kind": "skill",
         "skill": "/watch-validate-rarity", "script_id": "", "flags": {}, "link": "",
         "severity": "info",
         "hint": "Boxsets/artbooks 'rare' de publishers grandes — confirmar stock real. Opcional."},
        {"id": "consolidate", "label": "Unir fichas del mismo producto",
         "pending": multi_clusters, "stale": 0, "kind": "script", "skill": "",
         "script_id": "consolidate_sources", "flags": {}, "link": "", "severity": "error",
         "hint": "La app guarda 1 ficha por producto, con la lista de todas las tiendas donde está. A veces el mismo producto quedó como varias fichas sueltas: este paso las une en una sola (juntando sus tiendas). Es seguro: hace backup y no borra datos."},
        {"id": "card_carrusel", "label": "Imágenes — card ≠ carrusel",
         "pending": 0, "stale": card_ne_carrusel, "kind": "script", "skill": "",
         "script_id": "sync_cover_images", "flags": {}, "link": "", "severity": "warn",
         "hint": "La portada de la card no coincide con la 1ª del carrusel. Saneo mecánico."},
        {"id": "feedback", "label": "Feedback del dashboard (👎)",
         "pending": feedback_pending, "stale": 0, "kind": "skill",
         "skill": "/watch-review-feedback", "script_id": "", "flags": {}, "link": "",
         "severity": "info", "hint": "Reportes del botón 👎 por procesar."},
        {"id": "covers", "label": "Portadas candidatas por aprobar",
         "pending": cover_pending, "stale": 0, "kind": "link", "skill": "",
         "script_id": "", "flags": {}, "link": "cover-preview.html", "severity": "info",
         "hint": "Candidatas de /watch-search-covers esperando aprobación manual."},
    ]


def audit_items(items: list[dict], px: int = 90000, measure: bool = True) -> dict:
    """Audita el corpus y devuelve un reporte estructurado (sin tocar nada).

    Returns {generated_at, total, pillow, px_threshold, categories[], coverage{}}.
    Cada categoría: {id, label, group, severity, target, count, items[]}.
    `count` es el total real; `items` viene capeado a MAX_ITEMS_PER_CATEGORY.
    """
    n = len(items)

    # --- Estructura ---
    by_cluster: dict[str, list] = defaultdict(list)
    for it in items:
        by_cluster[it.get("cluster_key", "")].append(it)
    multi = {k: v for k, v in by_cluster.items()
             if k and not k.startswith("url:") and len(v) > 1}

    std_no_keys = [it for it in items
                   if it.get("standardized_at")
                   and (not it.get("series_key") or not it.get("edition_key"))]
    no_slug = [it for it in items if not it.get("slug")]

    # --- Procedencia ---
    no_sources = [it for it in items if not it.get("sources")]
    src_no_url = [it for it in items
                  if any(not s.get("url") for s in (it.get("sources") or []))]

    # --- Imágenes: archivos locales compartidos entre obras distintas ---
    file_to_works: dict[str, set] = defaultdict(set)
    for it in items:
        work = (it.get("series_key") or (it.get("title") or "")[:24]).lower()
        il = it.get("image_local")
        if il:
            file_to_works[il].add(work)
        for im in (it.get("images") or []):
            loc = im.get("local")
            if loc:
                file_to_works[loc].add(work)
    shared_files = {f for f, w in file_to_works.items() if len(w) >= 4}

    dim_cache: dict[str, int | None] = {}

    def dims(local: str) -> int | None:
        if not local or not HAVE_PIL or not measure:
            return None
        if local in dim_cache:
            return dim_cache[local]
        p = IMAGES / local
        try:
            with Image.open(p) as im:
                d = im.size[0] * im.size[1]
        except Exception:
            d = None
        dim_cache[local] = d
        return d

    cat: dict[str, list] = defaultdict(list)
    for it in items:
        iu = it.get("image_url") or ""
        il = it.get("image_local") or ""
        imgs = it.get("images") or []

        if not iu and not il and not imgs:
            cat["sin_imagen"].append(_entry(it))
            continue

        il_path = IMAGES / il if il else None
        il_exists = bool(il) and il_path.exists()
        il_size = il_path.stat().st_size if il_exists else 0
        il_healthy = il_exists and il_size >= 6 * 1024

        # Portada basura: solo si la imagen QUE SE VE es basura. El dashboard
        # muestra `image_local` cuando existe; si hay una copia local sana, un
        # patrón "basura" en `image_url` es solo la URL de origen y NO afecta lo
        # que se ve — falso positivo (p. ej. Shueisha sirve portadas reales bajo
        # `/icon/`). Recién cuando no hay copia local sana, la card cae al
        # `image_url` basura y la alerta es real.
        if is_junk_url(iu) and not il_healthy:
            cat["portada_url_basura"].append(_entry(it, detail=iu[:80]))
        if il and not il_exists:
            cat["ref_local_rota"].append(_entry(it, detail=il))
        if il in shared_files:
            cat["archivo_compartido"].append(_entry(it, detail=il))
        if il_exists:
            if il_size < 6 * 1024:
                cat["archivo_tiny"].append(_entry(it, detail=f"{il_size} bytes"))
            elif measure:
                d = dims(il)
                if d is not None and d < px:
                    cat["pixelada"].append(_entry(it, detail=f"{d} px"))
        # Card != primera del carrusel: comparar la imagen QUE SE VE, no la URL
        # de origen. La card muestra `image_local` (si existe); el carrusel[0]
        # muestra `images[0].local`. Si ambas resuelven al MISMO archivo local,
        # son la misma foto aunque sus URLs difieran (p. ej. KADOKAWA sirve
        # cover_b vs cover_500 de la misma portada → mismo archivo descargado).
        # Solo es mismatch real si los archivos locales difieren, o —cuando no
        # hay locales— si las URLs difieren.
        if imgs:
            fl = imgs[0].get("local") or ""
            fu = imgs[0].get("url") or ""
            if il and fl:
                mismatch = il != fl
            else:
                mismatch = bool(iu and fu and norm(iu) != norm(fu))
            if mismatch:
                cat["card_ne_carrusel"].append(_entry(it))
        # Foto repetida en el carrusel: el MISMO archivo local o el MISMO url
        # (normalizado) aparece 2+ veces en images[]. Dup exacto, barato de ver.
        if len(imgs) >= 2:
            seen_loc: set[str] = set()
            seen_u: set[str] = set()
            for im in imgs:
                loc = im.get("local") or ""
                u = norm(im.get("url") or "")
                if (loc and loc in seen_loc) or (u and u in seen_u):
                    cat["carrusel_dup"].append(_entry(it, detail=f"{len(imgs)} fotos"))
                    break
                if loc:
                    seen_loc.add(loc)
                if u:
                    seen_u.add(u)

    # --- Posibles productos duplicados: mismo ISBN o misma (serie,edición,vol)
    # en cluster_keys DISTINTOS → el mismo producto quedó como 2+ fichas. Se
    # AGRUPAN (no fila por fila) para comparar lado a lado en el panel. Los
    # grupos ya decididos (data/dup_decisions.jsonl) NO se vuelven a mostrar. ---
    decided = _load_dup_decisions()
    isbn_groups: dict[str, list] = defaultdict(list)
    trip_groups: dict[tuple, list] = defaultdict(list)
    for it in items:
        isbn = (it.get("isbn") or "").strip()
        if isbn:
            isbn_groups[isbn].append(it)
        sk = it.get("series_key") or ""
        ek = it.get("edition_key") or ""
        if sk and ek:
            trip_groups[(sk, ek, it.get("volume") or "")].append(it)

    dup_product: list[dict] = []
    _seen_sets: set[frozenset] = set()

    def _emit_dup_group(members: list[dict], reason: str, display_key: str,
                        match: str, common_isbn: str = "") -> None:
        # Solo es duplicado si los miembros caen en cluster_keys DISTINTOS
        # (si comparten cluster_key ya son la misma ficha consolidada).
        cks = {(m.get("cluster_key") or "") for m in members}
        if len(cks) < 2:
            return
        urls = sorted(m.get("url", "") for m in members)
        sig = display_key + "|" + hashlib.sha1("\n".join(urls).encode("utf-8")).hexdigest()[:12]
        if sig in decided:
            return
        fs = frozenset(urls)
        if fs in _seen_sets:   # mismo conjunto ya emitido (isbn y triple coinciden)
            return
        _seen_sets.add(fs)
        # Ficha sugerida para conservar la INFO (título/editorial/edición) al unir:
        # la más "completa" (la MISMA métrica que usa merge_cluster como canónica).
        suggested = max(members, key=_cluster_completeness)
        dup_product.append({
            "signature": sig,
            "dup_key": display_key,
            "reason": reason,
            "match": match,                 # "isbn" (alta confianza) | "triple"
            "common_isbn": common_isbn,     # ISBN compartido (para colorear verde/rojo)
            "suggested_keep": suggested.get("url", ""),
            "members": [_dup_member(m) for m in members],
            # compat con _print_human / rendering genérico:
            "url": members[0].get("url", ""),
            "title": f"{reason} — {len(members)} fichas",
            "source": "(grupo)",
        })

    for isbn, members in isbn_groups.items():
        _emit_dup_group(members, "Mismo ISBN", f"ISBN {isbn}",
                        match="isbn", common_isbn=isbn)
    for (sk, ek, vol), members in trip_groups.items():
        _emit_dup_group(members, "Misma serie + edición + volumen",
                        f"{ek} · vol {vol or '—'}", match="triple")

    # multi-cluster: una entrada por cluster (la primera fila), con N filas
    multi_entries = [_entry(v[0], detail=f"{len(v)} filas · {k}")
                     for k, v in multi.items()]

    raw = {
        "multi_cluster": multi_entries,
        "dup_product": dup_product,
        "std_no_keys": [_entry(it) for it in std_no_keys],
        "no_slug": [_entry(it) for it in no_slug],
        "no_sources": [_entry(it) for it in no_sources],
        "src_no_url": [_entry(it) for it in src_no_url],
        "sin_imagen": cat["sin_imagen"],
        "portada_url_basura": cat["portada_url_basura"],
        "ref_local_rota": cat["ref_local_rota"],
        "archivo_tiny": cat["archivo_tiny"],
        "archivo_compartido": cat["archivo_compartido"],
        "pixelada": cat["pixelada"],
        "card_ne_carrusel": cat["card_ne_carrusel"],
        "carrusel_dup": cat["carrusel_dup"],
    }

    categories = []
    for cid, entries in raw.items():
        meta = CATEGORY_META[cid]
        categories.append({
            "id": cid,
            "label": meta["label"],
            "group": meta["group"],
            "severity": meta["severity"],
            "target": meta["target"],
            "desc": meta["desc"],
            "fix": meta["fix"],
            "count": len(entries),
            "items": entries[:MAX_ITEMS_PER_CATEGORY],
        })

    coverage = {}
    for f in ("isbn", "price", "author", "volume", "release_date",
              "description_es", "rarity", "image_local"):
        c = sum(1 for it in items if it.get(f))
        coverage[f] = {"count": c, "pct": round(100 * c / n, 1) if n else 0}

    readiness = _compute_readiness(
        items,
        multi_clusters=len(multi),
        card_ne_carrusel=len(cat["card_ne_carrusel"]),
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": n,
        "pillow": HAVE_PIL and measure,
        "px_threshold": px,
        "categories": categories,
        "readiness": readiness,
        "coverage": coverage,
    }


def check_urls(urls, items=None, px: int = 90000) -> dict:
    """Re-evalúa SOLO los items con esas `urls` y devuelve {url: [cat_ids]}.

    Para el live-update del Panel de Calidad: tras arreglar un item, en vez de
    re-auditar las 10K+ filas, se re-chequea SOLO el item tocado. Usa el corpus
    completo para el contexto barato (shared_files, cluster_counts) pero solo
    mide píxeles de los items pedidos (1 Pillow open c/u). Las condiciones DEBEN
    coincidir con `audit_items` — si cambiás una allá, cambiala acá."""
    if items is None:
        items = [json.loads(l) for l in open(ROOT / "data/items.jsonl") if l.strip()]
    targets = set(urls or [])
    if not targets:
        return {}

    file_to_works: dict[str, set] = defaultdict(set)
    cluster_counts: dict[str, int] = defaultdict(int)
    isbn_ck: dict[str, set] = defaultdict(set)
    trip_ck: dict[tuple, set] = defaultdict(set)
    for it in items:
        cluster_counts[it.get("cluster_key", "")] += 1
        work = (it.get("series_key") or (it.get("title") or "")[:24]).lower()
        if it.get("image_local"):
            file_to_works[it["image_local"]].add(work)
        for im in (it.get("images") or []):
            if im.get("local"):
                file_to_works[im["local"]].add(work)
        _ck = it.get("cluster_key") or ""
        _isbn = (it.get("isbn") or "").strip()
        if _isbn:
            isbn_ck[_isbn].add(_ck)
        _sk = it.get("series_key") or ""
        _ek = it.get("edition_key") or ""
        if _sk and _ek:
            trip_ck[(_sk, _ek, it.get("volume") or "")].add(_ck)
    shared_files = {f for f, w in file_to_works.items() if len(w) >= 4}

    result: dict[str, list] = {}
    for it in items:
        u = it.get("url", "")
        if u not in targets:
            continue
        cats: set[str] = set()
        # estructura / procedencia
        ck = it.get("cluster_key", "")
        if ck and not ck.startswith("url:") and cluster_counts[ck] > 1:
            cats.add("multi_cluster")
        if it.get("standardized_at") and (not it.get("series_key") or not it.get("edition_key")):
            cats.add("std_no_keys")
        if not it.get("slug"):
            cats.add("no_slug")
        if not it.get("sources"):
            cats.add("no_sources")
        if any(not s.get("url") for s in (it.get("sources") or [])):
            cats.add("src_no_url")
        _isbn = (it.get("isbn") or "").strip()
        if _isbn and len(isbn_ck.get(_isbn, ())) > 1:
            cats.add("dup_product")
        _sk = it.get("series_key") or ""
        _ek = it.get("edition_key") or ""
        if _sk and _ek and len(trip_ck.get((_sk, _ek, it.get("volume") or ""), ())) > 1:
            cats.add("dup_product")
        # imágenes
        iu = it.get("image_url") or ""
        il = it.get("image_local") or ""
        imgs = it.get("images") or []
        if not iu and not il and not imgs:
            cats.add("sin_imagen")
        else:
            il_path = IMAGES / il if il else None
            il_exists = bool(il) and il_path.exists()
            il_size = il_path.stat().st_size if il_exists else 0
            il_healthy = il_exists and il_size >= 6 * 1024
            if is_junk_url(iu) and not il_healthy:
                cats.add("portada_url_basura")
            if il and not il_exists:
                cats.add("ref_local_rota")
            if il in shared_files:
                cats.add("archivo_compartido")
            if il_exists:
                if il_size < 6 * 1024:
                    cats.add("archivo_tiny")
                elif HAVE_PIL:
                    try:
                        with Image.open(il_path) as im:
                            d = im.size[0] * im.size[1]
                        if d < px:
                            cats.add("pixelada")
                    except Exception:
                        pass
            if imgs:
                fl = imgs[0].get("local") or ""
                fu = imgs[0].get("url") or ""
                mismatch = (il != fl) if (il and fl) else bool(iu and fu and norm(iu) != norm(fu))
                if mismatch:
                    cats.add("card_ne_carrusel")
            if len(imgs) >= 2:
                _sl: set[str] = set()
                _su: set[str] = set()
                for im in imgs:
                    _loc = im.get("local") or ""
                    _u = norm(im.get("url") or "")
                    if (_loc and _loc in _sl) or (_u and _u in _su):
                        cats.add("carrusel_dup")
                        break
                    if _loc:
                        _sl.add(_loc)
                    if _u:
                        _su.add(_u)
        result[u] = sorted(cats)
    return result


def _print_human(report: dict, examples: int) -> None:
    n = report["total"]
    print(f"# Auditoría de calidad — {n} items\n")
    by_group: dict[str, list] = defaultdict(list)
    for c in report["categories"]:
        by_group[c["group"]].append(c)
    titles = {"estructura": "ESTRUCTURA", "procedencia": "PROCEDENCIA", "imagenes": "IMÁGENES"}
    for group in ("estructura", "procedencia", "imagenes"):
        print(f"## {titles[group]}")
        if group == "imagenes":
            print(f"- Pillow disponible (medición de píxeles): {report['pillow']}")
        for c in by_group.get(group, []):
            print(f"- {c['label']}: {c['count']}")
            for e in c["items"][:examples]:
                extra = f" [{e['detail']}]" if e.get("detail") else ""
                print("    - " + " | ".join(
                    str(e.get(f, ""))[:60] for f in ("title", "source", "url")) + extra)
        print()
    if report.get("readiness"):
        print("## PREPARACIÓN DEL DATO (qué falta correr)")
        for s in report["readiness"]:
            work = (s.get("pending", 0) or 0) + (s.get("stale", 0) or 0)
            if not work:
                continue
            bits = []
            if s.get("pending"):
                bits.append(f"{s['pending']} pend.")
            if s.get("stale"):
                bits.append(f"{s['stale']} desinc.")
            how = s.get("skill") or (s.get("script_id") and f"script {s['script_id']}") or s.get("link", "")
            print(f"- {s['label']}: {', '.join(bits)}  → {how}")
        print()

    print("## COBERTURA")
    for f, cov in report["coverage"].items():
        print(f"- {f}: {cov['count']} ({cov['pct']}%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--px", type=int, default=90000, help="umbral de píxeles para 'pequeña'")
    ap.add_argument("--examples", type=int, default=6)
    ap.add_argument("--no-measure", action="store_true",
                    help="saltea la medición de píxeles con Pillow (más rápido)")
    ap.add_argument("--no-json", action="store_true",
                    help="no escribe el reporte JSON")
    ap.add_argument("--json-out", default=str(DEFAULT_JSON_OUT),
                    help="ruta del reporte JSON estructurado")
    args = ap.parse_args()

    items = [json.loads(l) for l in open(ROOT / "data/items.jsonl") if l.strip()]
    report = audit_items(items, px=args.px, measure=not args.no_measure)

    _print_human(report, args.examples)

    if not args.no_json:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        total_alerts = sum(c["count"] for c in report["categories"])
        print(f"\n[OK] reporte JSON → {out}  ({total_alerts} alertas en {len(report['categories'])} categorías)")


if __name__ == "__main__":
    main()
