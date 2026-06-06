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
import argparse, json, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from manga_watch import IMAGE_URL_BAD_PATTERNS  # noqa: E402

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

# Metadatos de presentación por categoría. `target` decide a dónde linkea cada
# item de la worklist en el dashboard:
#   "image"  → image-manager.html (arreglar la foto)
#   "detail" → index.html#/volume/<url> (arreglar metadata / estructura)
CATEGORY_META = {
    # estructura
    "multi_cluster":      ("Clusters con >1 fila (deberían colapsar)", "estructura", "error",  "detail"),
    "std_no_keys":        ("Estandarizados sin series_key/edition_key", "estructura", "error", "detail"),
    "no_slug":            ("Items sin slug",                            "estructura", "error",  "detail"),
    # procedencia
    "no_sources":         ("Items sin sources[]",                      "procedencia", "error", "detail"),
    "src_no_url":         ("Alguna source sin url",                    "procedencia", "warn",  "detail"),
    # imágenes
    "sin_imagen":         ("Sin imagen (muestran 📚)",                 "imagenes", "warn",  "image"),
    "portada_url_basura": ("Portada con URL basura (banner/placeholder/estrella)", "imagenes", "error", "image"),
    "ref_local_rota":     ("Ref a archivo local inexistente",         "imagenes", "error", "image"),
    "archivo_tiny":       ("Archivo local <6KB (píxel/ícono/garabato)", "imagenes", "warn", "image"),
    "archivo_compartido": ("Archivo compartido por ≥4 obras (placeholder reusado)", "imagenes", "warn", "image"),
    "pixelada":           ("Imagen pequeña/pixelada",                  "imagenes", "warn",  "image"),
    "card_ne_carrusel":   ("Card != primera del carrusel (mismatch)",  "imagenes", "warn",  "image"),
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

    # multi-cluster: una entrada por cluster (la primera fila), con N filas
    multi_entries = [_entry(v[0], detail=f"{len(v)} filas · {k}")
                     for k, v in multi.items()]

    raw = {
        "multi_cluster": multi_entries,
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
    }

    categories = []
    for cid, entries in raw.items():
        label, group, severity, target = CATEGORY_META[cid]
        categories.append({
            "id": cid,
            "label": label,
            "group": group,
            "severity": severity,
            "target": target,
            "count": len(entries),
            "items": entries[:MAX_ITEMS_PER_CATEGORY],
        })

    coverage = {}
    for f in ("isbn", "price", "author", "volume", "release_date",
              "description_es", "rarity", "image_local"):
        c = sum(1 for it in items if it.get(f))
        coverage[f] = {"count": c, "pct": round(100 * c / n, 1) if n else 0}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": n,
        "pillow": HAVE_PIL and measure,
        "px_threshold": px,
        "categories": categories,
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
    for it in items:
        cluster_counts[it.get("cluster_key", "")] += 1
        work = (it.get("series_key") or (it.get("title") or "")[:24]).lower()
        if it.get("image_local"):
            file_to_works[it["image_local"]].add(work)
        for im in (it.get("images") or []):
            if im.get("local"):
                file_to_works[im["local"]].add(work)
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
