#!/usr/bin/env python3
"""Limpia la galería images[] alrededor de la portada (images[0]).

La portada es `images[0]` (única fuente de verdad, decisión 2026-06-09): no hay
campos top-level `image_url`/`image_local` que reconciliar. Lo que queda de este
retrofit es la limpieza de la galería:

  1. Si la portada (images[0]) es un placeholder/banner conocido (junk), la
     reemplaza por la primera imagen real de images[]; si no hay, la limpia
     (el dashboard muestra el placeholder 📚).
  2. Quita de images[] los duplicados exactos de la portada (misma imagen en
     otra resolución, dedup por URL normalizada / basename) y la basura conocida
     (banners de tienda, placeholders) vía IMAGE_URL_BAD_PATTERNS.
  3. Limpia refs basura en sources[] (otro layer, per-fuente).

Items aprobados (`approved_at`) se saltean por defecto (--include-approved
para forzar). Idempotente. Backup vía backup_and_rotate antes de escribir.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:  # import dual robusto (CLI directo vs wrapper raíz bajo pytest)
    from manga_watch import (  # noqa: E402
        IMAGE_URL_BAD_PATTERNS,
        _img_stem,
        backup_and_rotate,
        is_approved,
    )
except ImportError:  # pragma: no cover
    from scripts.manga_watch import (  # noqa: E402
        IMAGE_URL_BAD_PATTERNS,
        _img_stem,
        backup_and_rotate,
        is_approved,
    )
try:
    import image_store  # noqa: E402
    from image_store import normalize_image_url  # noqa: E402
except ImportError:  # pragma: no cover
    from scripts import image_store  # noqa: E402
    from scripts.image_store import normalize_image_url  # noqa: E402

DEFAULT_ITEMS = _SCRIPTS_DIR.parent / "data" / "items.jsonl"


def _basename(url: str) -> str:
    """Último segmento de path, sin query — para dedup de misma-imagen."""
    path = urlsplit(url).path.rstrip("/")
    return path.rsplit("/", 1)[-1].lower()


def _norm(url: str) -> str:
    """Clave de dedup para "misma imagen". Hallazgo #10 (2026-07-08): antes esto
    era un cuarto criterio propio (split query + normalize_image_url + lower),
    divergente de `manga_watch._img_stem` — la clave canónica que usa
    `merge_cluster` y que images.md documenta con "paridad de 3 lugares". Ahora
    compone AMBOS normalizadores: `image_store.normalize_image_url` (sufijo
    WordPress -NxM + query params de resize Magento — casos que _img_stem no
    cubre) seguido de `_img_stem` (sufijo CDN estilo Shopify _NxN/_grande/_small,
    query v/version/t/etc, esquema, minúsculas — la clave canónica del carrusel).
    """
    if not url:
        return ""
    return _img_stem(normalize_image_url(url))


def _is_junk(url: str) -> bool:
    low = (url or "").lower()
    return any(p in low for p in IMAGE_URL_BAD_PATTERNS)


# Set de archivos locales basura (placeholders/anuncios/píxeles), detectados por
# datos: 0 bytes, diminutos (<6KB = íconos/píxeles/garabatos), o el MISMO archivo
# compartido por muchas series distintas (bytes idénticos desde URLs distintas =
# placeholder reusado: banners, "now printing", pósters de eventos, etc.).
# Poblado por _compute_junk_local() antes del barrido. Validado visualmente.
_JUNK_LOCAL: set[str] = set()
_TINY_BYTES = 6000
_SHARED_SERIES_MIN = 4


def _compute_junk_local(items: list[dict], images_dir: Path) -> set[str]:
    from collections import defaultdict
    sizes: dict[str, int] = {}
    if images_dir.exists():
        for p in images_dir.iterdir():
            if p.is_file():
                try:
                    sizes[p.name] = p.stat().st_size
                except OSError:
                    pass
    # Para el criterio "compartido" usamos OBRAS DISTINTAS (prefijo de título),
    # no series_key: si una misma obra quedó fragmentada en varios series_key y
    # comparten su portada REAL, NO es basura. La basura (banners, placeholders,
    # pósters) aparece en muchas obras genuinamente distintas.
    def _work(it: dict) -> str:
        t = (it.get("series_display") or it.get("title") or "").lower().strip()
        return " ".join(t.split()[:3])  # prefijo: distingue obras, tolera volúmenes
    f2works: dict[str, set] = defaultdict(set)
    for it in items:
        w = _work(it)
        # La portada es images[0]; recorremos todas las entries de images[].
        locs = [im.get("local") for im in (it.get("images") or []) if isinstance(im, dict)]
        for f in locs:
            if f:
                f2works[f].add(w)
    junk = set()
    for f, works in f2works.items():
        # Hallazgo #2 (ALTA, 2026-07-08): "no existe en el espejo" y "existe con
        # 0 bytes" NO son lo mismo. Antes `sizes.get(f, 0)` los igualaba: si
        # `images_dir` no existe (o el archivo simplemente no se mirroreó
        # todavía), CADA local caía acá con sz==0 → se clasificaba TODO como
        # basura y `_fix_bad_cover` arrasaba portadas en masa. "No existe" es
        # un skip legítimo (borrado/nunca descargado); sólo "existe pero pesa
        # 0 bytes" es basura real (descarga corrupta/truncada).
        if f not in sizes:
            continue                                   # no existe en el espejo — NO es basura
        sz = sizes[f]
        if sz == 0:                                    # existe pero 0 bytes → corrupto
            junk.add(f)
        elif sz < _TINY_BYTES:                        # píxeles / íconos / garabatos
            junk.add(f)
        elif len(works) >= _SHARED_SERIES_MIN:        # placeholder reusado entre OBRAS distintas
            junk.add(f)
    return junk


def _img_is_junk(url: str, local: str = "") -> bool:
    """Junk por patrón de URL O por archivo local conocido (placeholder/píxel/ad)."""
    if local and local in _JUNK_LOCAL:
        return True
    return _is_junk(url)


# Galerías que son "productos relacionados", NUNCA fotos propias del producto
# (otros tomos / otras series del sidebar). En estas fuentes la única imagen
# válida es la portada (images[0]); el resto se descarta. Esto es la
# contrapartida-de-datos de gotcha #31 (el extractor ya filtra en scrape nuevo;
# acá limpiamos el corpus histórico).
#   - Star Comics: la ficha muestra una grilla de otros volúmenes en
#     /fumetti-cover/thumbnail/ (la portada vive en /fumetti-cover/<x> sin
#     thumbnail). Caso real: "Dragon Ball Guide" arrastraba Hellboy,
#     Detective Conan, My Hero Academia.
#   - Manga-Sanctuary: la página planning muestra otras novedades como
#     thumbs /objet/150/ (la portada es /objet/300/ o un CDN externo). Las
#     mismas 6 series se repetían en Orange / Takopi / Zelda.
def _is_related_product_thumb(url: str) -> bool:
    low = (url or "").lower()
    if "/fumetti-cover/thumbnail/" in low:        # Star Comics
        return True
    if "img.sanctuary.fr/objet/150/" in low:      # Manga-Sanctuary planning
        return True
    return False


def _same_image(a_url: str, b_url: str) -> bool:
    """True si dos URLs apuntan a la misma imagen (otra resolución/folder)."""
    if not a_url or not b_url:
        return False
    if _norm(a_url) == _norm(b_url):
        return True
    ba, bb = _basename(a_url), _basename(b_url)
    return bool(ba) and ba == bb


def _fix_bad_cover(item: dict) -> bool:
    """Si la portada (images[0]) es un placeholder/banner conocido (_is_junk),
    la reemplaza por la primera imagen real de la galería; si no hay, la limpia
    para que el dashboard muestre el placeholder 📚.

    Dispara SOLO con `_is_junk` (visuel_defaut, banner promo Panini, etc.) — NO
    con `_is_related_product_thumb`, porque la portada de muchos productos de
    Star Comics vive legítimamente en /thumbnail/ (no es basura, es la portada).

    Devuelve True si modificó la portada.
    """
    iu = image_store.cover_url(item)
    il = image_store.cover_local(item)
    # Portada basura: por patrón de URL (placeholder/banner) O por archivo local
    # conocido (píxel/ad/poster compartido). Si no es basura, no tocar.
    if not _img_is_junk(iu, il):
        return False
    imgs = item.get("images") or []
    # Busca la primera imagen REAL de GALERÍA del resto y la promueve a portada
    # (images[0]), descartando la portada basura. Hallazgo #8 (2026-07-08): sólo
    # `kind: "gallery"` es elegible — un "extra" (postal/shikishi) NUNCA debe
    # terminar de portada, es un bonus que viene CON el producto, no la ficha.
    for i, im in enumerate(imgs):
        if i == 0 or not isinstance(im, dict):
            continue
        if im.get("kind", "gallery") != "gallery":
            continue
        u = im.get("url") or ""
        loc = im.get("local") or ""
        if u and not _img_is_junk(u, loc) and not _is_related_product_thumb(u) and not _same_image(u, iu):
            # La buena pasa a portada (pos 0); el resto de la galería se conserva.
            item["images"] = [im] + [g for j, g in enumerate(imgs) if j not in (0, i)]
            return True
    # Sin reemplazo de galería válido: quitamos SOLO la portada basura (pos 0) y
    # conservamos el resto TAL CUAL (extras legítimas incluidas) — `_rebuild()`
    # se encarga de la limpieza de basura/dups en las posiciones restantes.
    # Hallazgo #8: antes esto hacía `item["images"] = []`, perdiendo postales/
    # shikishis que no eran basura junto con la portada mala.
    item["images"] = imgs[1:]
    return True


def _clean_sources_junk(item: dict) -> bool:
    """Limpia refs basura en sources[] (modelo 1-fila-por-producto).

    sources[].image_local apuntando a un archivo basura (píxel/placeholder/ad) o
    sources[].image_url a una URL basura → se vacían. Así esos archivos quedan
    huérfanos de verdad y el GC los puede borrar (si no, sources[] los mantendría
    'referenciados' para siempre). El array sources[] no muestra imagen (solo
    name/url/price), así que vaciar estos campos no afecta la UI.
    """
    changed = False
    for s in (item.get("sources") or []):
        if not isinstance(s, dict):
            continue
        loc = s.get("image_local") or ""
        if loc and loc in _JUNK_LOCAL:
            s["image_local"] = ""
            changed = True
        url = s.get("image_url") or ""
        if url and _is_junk(url):
            s["image_url"] = ""
            changed = True
    return changed


def _rebuild(item: dict) -> bool:
    """Limpia duplicados exactos / basura de la galería, preservando la portada.

    La portada es images[0] (única fuente de verdad). Solo limpiamos las
    posiciones >=1: dups exactos de una URL o de la portada, y basura conocida
    (banners, placeholders). NO toca la contaminación de "productos relacionados"
    de gotcha #31 (problema aparte).

    Devuelve True si modificó el item.
    """
    imgs = item.get("images") or []
    if not isinstance(imgs, list) or not imgs:
        return False
    if not isinstance(imgs[0], dict):
        return False

    first_url = imgs[0].get("url", "")
    if not first_url:
        return False

    # images[0] es la portada. Limpiamos dups exactos y basura de posiciones >=1,
    # preservando la portada y el resto tal cual.
    new_imgs = [imgs[0]]
    seen = {_norm(first_url)}
    for im in imgs[1:]:
        if not isinstance(im, dict):
            new_imgs.append(im)
            continue
        u = im.get("url") or ""
        if (u or im.get("local")) and (_img_is_junk(u, im.get("local") or "") or _is_related_product_thumb(u)):
            continue
        if u and _norm(u) in seen:
            continue
        if u:
            seen.add(_norm(u))
        new_imgs.append(im)

    if new_imgs == imgs:
        return False
    item["images"] = new_imgs
    return True


def run(items_path: Path, *, dry_run: bool, include_approved: bool) -> None:
    images_dir = items_path.parent / "images"
    # Hallazgo #2 (ALTA, 2026-07-08): si el espejo no existe, `_compute_junk_local`
    # no tiene forma de distinguir "archivo borrado/nunca mirroreado" de "archivo
    # corrupto de 0 bytes" — TODO local caería en la rama junk y `_fix_bad_cover`
    # arrasaría portadas en masa. Abortamos ANTES de tocar nada.
    if not images_dir.exists():
        print(f"[sync-cover-images] ABORT: {images_dir} no existe — nada que limpiar "
              f"(evita clasificar TODO el espejo local como basura).")
        return

    items = [json.loads(l) for l in items_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    # Detectar archivos locales basura (0 bytes / <6KB píxeles-íconos / placeholder
    # compartido por >=4 series) para removerlos como portada y de la galería.
    global _JUNK_LOCAL
    _JUNK_LOCAL = _compute_junk_local(items, images_dir)
    if _JUNK_LOCAL:
        print(f"Archivos locales basura detectados (placeholder/píxel/ad): {len(_JUNK_LOCAL)}")
    changed = skipped_approved = bad_covers = 0
    examples = []
    for it in items:
        if is_approved(it) and not include_approved:
            skipped_approved += 1
            continue
        before = len(it.get("images") or [])
        touched = False
        if _fix_bad_cover(it):
            bad_covers += 1
            touched = True
        if _rebuild(it):
            touched = True
        if _clean_sources_junk(it):
            touched = True
        if touched:
            changed += 1
            if len(examples) < 8:
                examples.append((it.get("title", ""), before, len(it.get("images") or [])))

    print(f"Items totales: {len(items)}")
    print(f"Items con imágenes corregidas: {changed}")
    if bad_covers:
        print(f"  · de ellos, con portada mala reemplazada/limpiada: {bad_covers}")
    if skipped_approved:
        print(f"Items aprobados saltados (usar --include-approved): {skipped_approved}")
    for title, b, a in examples:
        print(f"  • {title}: images {b} → {a}")

    if dry_run:
        print("\n[dry-run] No se escribió nada.")
        return
    if not changed:
        print("\nNada que escribir.")
        return

    backup_and_rotate(items_path, "sync-cover-images")
    with items_path.open("w", encoding="utf-8") as fh:
        for it in items:
            # Hallazgo #12: sort_keys=True — el resto de los escritores de
            # items.jsonl lo usa; sin esto, este era el único escritor cuya
            # serialización dependía del orden de inserción de cada dict.
            fh.write(json.dumps(it, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"\n✓ Escrito {items_path} ({changed} items modificados).")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-approved", action="store_true",
                    help="También re-sincroniza items aprobados (por defecto se saltean).")
    args = ap.parse_args()
    run(args.items, dry_run=args.dry_run, include_approved=args.include_approved)


if __name__ == "__main__":
    main()
