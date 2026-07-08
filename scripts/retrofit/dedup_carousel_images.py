#!/usr/bin/env python3
"""dedup_carousel_images.py — quita del carrusel (`images[]`) las imágenes que
son LA MISMA portada en otra resolución, conservando la de MAYOR resolución.

Caso real: artbooks/items de listadomanga que tienen la portada hi-res del
publisher (normaeditorial) + la MISMA portada como thumbnail de baja calidad de
static.listadomanga.com. El usuario ve la foto duplicada en alta y baja.

Seguridad: usa hash perceptual (aHash 8×8) con umbral Hamming ESTRICTO +
chequeo de aspect ratio para NO confundir fotos distintas (cofres, variantes,
páginas de artbook) con duplicados. Nunca deja un item sin imágenes.

Uso:
  .venv/bin/python scripts/retrofit/dedup_carousel_images.py --dry-run
  .venv/bin/python scripts/retrofit/dedup_carousel_images.py [--all]
"""
from __future__ import annotations
import json, sys, argparse, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "retrofit"))
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_better_covers as fbc  # noqa: E402  (reusa _ahash/_hamming/_get_dims_from_bytes)
import requests  # noqa: E402
try:  # import dual robusto (CLI directo vs wrapper raíz bajo pytest)
    from manga_watch import is_approved  # noqa: E402
except ImportError:  # pragma: no cover
    from scripts.manga_watch import is_approved  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"
IMAGES = ROOT / "data" / "images"
MAX_HAMMING = 6        # ≤6/64 bits = misma foto (diff resolución sube ~3-5 bits)
ASPECT_TOL = 0.12      # ratios deben coincidir ±12%
# Caso thumbnail: una versión DIMINUTA (ej. el thumb ~96×150 de listadomanga,
# gotcha #39) de la misma portada pierde tanto detalle que su aHash sube por
# encima de 6 (caso real cole=52: hamming 7). Si una imagen es un thumbnail
# chico, la otra es ≥2× más grande y el aspect ratio es CASI idéntico (±5%),
# es inequívocamente la misma foto reescalada → umbral hamming relajado.
THUMB_MAX_SIDE = 170   # lado menor que delata un thumbnail
THUMB_HAMMING = 14     # umbral relajado SOLO para el par thumbnail↔full (un thumb
                       # ~100px degrada el aHash hasta ~14 bits vs su full)
THUMB_ASPECT_TOL = 0.06

_S = requests.Session(); _S.headers.update({"User-Agent": "Mozilla/5.0 (dedup)"})
_bytes_cache: dict[str, bytes] = {}


def _img_bytes(im: dict) -> bytes:
    local = im.get("local") or ""
    if local:
        p = IMAGES / local
        if p.exists():
            return p.read_bytes()
    url = im.get("url") or ""
    if not url:
        return b""
    if url in _bytes_cache:
        return _bytes_cache[url]
    try:
        data = _S.get(url, timeout=(10, 30)).content
    except requests.RequestException:
        data = b""
    _bytes_cache[url] = data
    return data


def _fingerprint(im: dict):
    """(ahash, pixels, w, h) o None si no se pudo leer."""
    data = _img_bytes(im)
    if not data:
        return None
    h = fbc._ahash(data)
    if h is None:
        return None
    w, ht = fbc._get_dims_from_bytes(data)
    return (h, w * ht, w, ht)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true",
                    help="todos los items (default: solo los que tienen una imagen de listadomanga)")
    ap.add_argument("--include-approved", action="store_true",
                    help="También dedupea items aprobados (golden records). Por defecto se "
                         "saltean: dedup puede REORDENAR images[0] (la portada) de un item "
                         "aprobado si la portada actual cae como duplicado de menor resolución.")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    removed_total = 0
    items_changed = 0
    skipped_approved = 0
    examples = []
    for it in items:
        if is_approved(it) and not args.include_approved:
            skipped_approved += 1
            continue
        imgs = it.get("images") or []
        if len(imgs) < 2:
            continue
        if not args.all and not any("listadomanga.com" in (im.get("url") or "") for im in imgs):
            continue
        fps = [_fingerprint(im) for im in imgs]
        # SOLO deduplicamos imágenes kind=gallery con dims válidas. Los `extra`
        # (cofres, tomos del box, bonuses) son contenido curado del carrusel —
        # NUNCA se tocan aunque se parezcan a la cover. Y sin dims (px=0) no
        # podemos elegir la de mayor resolución → no arriesgamos.
        def _dedupable(idx):
            return (imgs[idx].get("kind", "gallery") == "gallery"
                    and fps[idx] is not None and fps[idx][1] > 0)
        keep = [True] * len(imgs)
        # comparar pares; si son la misma foto, descartar la de MENOS píxeles.
        for i in range(len(imgs)):
            if not keep[i] or not _dedupable(i):
                continue
            for j in range(i + 1, len(imgs)):
                if not keep[j] or not _dedupable(j):
                    continue
                (h1, px1, w1, ht1), (h2, px2, w2, ht2) = fps[i], fps[j]
                hamm = fbc._hamming(h1, h2)
                r1 = (w1 / ht1) if ht1 else 0
                r2 = (w2 / ht2) if ht2 else 0
                aspect_diff = abs(r1 - r2) / r1 if r1 else 1.0
                # ¿par thumbnail↔full? (una diminuta, la otra ≥2× su lado menor)
                side1, side2 = min(w1, ht1), min(w2, ht2)
                small, big = (side1, side2) if side1 <= side2 else (side2, side1)
                is_thumb_pair = (small <= THUMB_MAX_SIDE and big >= 2 * small
                                 and aspect_diff <= THUMB_ASPECT_TOL)
                if is_thumb_pair:
                    # misma foto reescalada a thumbnail → umbral relajado
                    if hamm > THUMB_HAMMING:
                        continue
                else:
                    if hamm > MAX_HAMMING:
                        continue
                    if r1 and r2 and aspect_diff > ASPECT_TOL:
                        continue
                # misma foto → descartar la de menos píxeles (j si px2<=px1, sino i)
                drop = j if px2 <= px1 else i
                keep[drop] = False
                if drop == i:
                    break  # i descartado, no seguir comparándolo
        if all(keep):
            continue
        new_imgs = [im for k, im in zip(keep, imgs) if k]
        if not new_imgs:
            continue  # nunca dejar sin imágenes
        dropped = [im for k, im in zip(keep, imgs) if not k]
        # La portada es images[0]: si la portada (imgs[0]) cayó como duplicado de
        # menor resolución, new_imgs[0] (el hi-res que quedó) pasa a ser la portada
        # automáticamente al reescribir images[]. No hace falta repuntar nada aparte.
        if not args.dry_run:
            it["images"] = new_imgs
        removed_total += len(dropped)
        items_changed += 1
        if len(examples) < 25:
            examples.append((it.get("title", "")[:34],
                             [(d.get("kind"), (d.get("url", "") or "").split("/")[-1][:18]) for d in dropped]))

    print(f"[dedup] items con duplicados de portada: {items_changed} | imágenes quitadas: {removed_total}")
    if skipped_approved:
        print(f"[dedup] items aprobados saltados (usar --include-approved): {skipped_approved}")
    for t, dr in examples:
        print(f"   {t:34} drop={dr}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-dedup-bak"))
    tmp = ITEMS.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(ITEMS)
    print(f"[dedup] escrito {ITEMS}. Backup: {ITEMS.with_suffix('.jsonl.pre-dedup-bak')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
