#!/usr/bin/env python3
"""promote_hires_cover.py — promueve la portada hi-res desde la galería a images[0].

Caso: ~13 items de listadomanga tienen su portada en baja resolución en images[0]
(thumbnail de static.listadomanga.com, <90 000 px) pero LA MISMA portada en alta
resolución ya aparece en images[1+] (vino de otra fuente del cluster, ej. Panini,
Norma, Whakoom). Este script intercambia images[0] ↔ images[k] para que la
hi-res quede como portada.

Verificación de identidad — criterio "thumbnail↔full" (igual que dedup_carousel_images.py,
caso documentado gotcha #39):

  El thumbnail de listadomanga (~100×150 px) degrada tanto el aHash que la distancia
  con su portada full supera el umbral estricto de _same_cover (6/64 bits). Por eso
  usamos el mismo criterio relajado de dedup_carousel_images.py:

  - Si la portada actual es un thumbnail (lado menor ≤ THUMB_MAX_SIDE) y la candidata
    es ≥ 2× más grande en su lado menor → par thumbnail↔full → aHash ≤ THUMB_HAMMING
    (14/64 bits) + aspect ratio ≤ THUMB_ASPECT_TOL (12%).
  - Si no es un par thumbnail↔full → usamos _same_cover (AND-gate estricto).

  El thumbnail NO se elimina: queda en la galería; dedup_carousel_images.py
  puede quitarlo después si lo decide.

Uso:
    .venv/bin/python scripts/retrofit/promote_hires_cover.py --dry-run
    .venv/bin/python scripts/retrofit/promote_hires_cover.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# fetch_better_covers vive en scripts/retrofit/; agréguémoslo también.
_RETROFIT = Path(__file__).resolve().parent
if str(_RETROFIT) not in sys.path:
    sys.path.insert(0, str(_RETROFIT))

import fetch_better_covers as fbc  # noqa: E402
from manga_watch import backup_and_rotate  # type: ignore  # noqa: E402

ITEMS = Path(__file__).resolve().parents[2] / "data" / "items.jsonl"
IMAGES = Path(__file__).resolve().parents[2] / "data" / "images"

# Umbral de px bajo el cual la portada actual se considera "baja calidad".
LOW_PX_THRESHOLD = 90_000

# Criterio thumbnail↔full (mismo que dedup_carousel_images.py, gotcha #39):
# el thumbnail de listadomanga degrada tanto el aHash que supera el umbral
# estricto de _same_cover. Usamos un umbral relajado para este par específico.
THUMB_MAX_SIDE = 170    # lado menor que delata un thumbnail
THUMB_HAMMING = 14      # umbral relajado para par thumbnail↔full
THUMB_ASPECT_TOL = 0.12  # aspect ratio ±12% (mismo que dedup, normal tolerance)


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_items(path: Path) -> list[dict]:
    items: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            items.append({"_raw": line})
    return items


def _write_items(dst: Path, items: list[dict]) -> None:
    lines = [
        it["_raw"] if "_raw" in it else json.dumps(it, ensure_ascii=False, sort_keys=True)
        for it in items
    ]
    tmp = dst.with_suffix(".jsonl.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(dst)


def _px(local: str) -> int:
    """Devuelve w*h de una imagen local, o 0 si no se puede leer."""
    if not local:
        return 0
    path = IMAGES / local
    if not path.exists():
        return 0
    try:
        data = path.read_bytes()
    except OSError:
        return 0
    w, h = fbc._get_dims_from_bytes(data)
    return w * h


def _read_local(local: str) -> bytes:
    if not local:
        return b""
    path = IMAGES / local
    if not path.exists():
        return b""
    try:
        return path.read_bytes()
    except OSError:
        return b""


# ── core ──────────────────────────────────────────────────────────────────────

def _is_same_cover(bytes0: bytes, bytes_k: bytes) -> bool:
    """
    Verifica si bytes_k es la misma portada que bytes0.

    Caso thumbnail↔full (gotcha #39 — igual que dedup_carousel_images.py):
    Si bytes0 es un thumbnail pequeño (lado menor ≤ THUMB_MAX_SIDE) y bytes_k
    es ≥2× más grande, el aHash se degrada demasiado para pasar _same_cover
    (distancia 8-14 vs umbral 6). Usamos el criterio relajado de dedup.

    Caso general: delegamos en fbc._same_cover (AND-gate multi-hash + NCC).
    """
    w0, h0 = fbc._get_dims_from_bytes(bytes0)
    wk, hk = fbc._get_dims_from_bytes(bytes_k)
    if w0 <= 0 or h0 <= 0 or wk <= 0 or hk <= 0:
        return False

    side0 = min(w0, h0)
    sidk = min(wk, hk)
    small, big = (side0, sidk) if side0 <= sidk else (sidk, side0)

    r0 = w0 / h0 if h0 else 0
    rk = wk / hk if hk else 0
    aspect_diff = abs(r0 - rk) / r0 if r0 else 1.0

    is_thumb_pair = (
        small <= THUMB_MAX_SIDE
        and big >= 2 * small
        and aspect_diff <= THUMB_ASPECT_TOL
    )

    if is_thumb_pair:
        # Criterio relajado: solo aHash + aspect ratio (igual que dedup_carousel)
        h_a0 = fbc._ahash(bytes0)
        h_ak = fbc._ahash(bytes_k)
        if h_a0 is None or h_ak is None:
            return False
        return fbc._hamming(h_a0, h_ak) <= THUMB_HAMMING
    else:
        return fbc._same_cover(bytes0, bytes_k)


def _best_hires_idx(item: dict) -> tuple[int, int] | None:
    """
    Busca el índice k≥1 con local existente, px≥LOW_PX_THRESHOLD,
    y que sea la misma portada que images[0]. Devuelve (k, px_del_k)
    del mejor candidato (mayor px), o None si no hay.
    """
    imgs = item.get("images") or []
    if len(imgs) < 2:
        return None

    cover = imgs[0]
    cover_local = cover.get("local") or ""
    cover_px = _px(cover_local)
    if cover_px <= 0 or cover_px >= LOW_PX_THRESHOLD:
        return None  # portada ya aceptable (o sin local)

    cover_bytes = _read_local(cover_local)
    if not cover_bytes:
        return None

    best_k: int | None = None
    best_px: int = 0

    for k, im in enumerate(imgs[1:], start=1):
        local_k = im.get("local") or ""
        if not local_k:
            continue
        px_k = _px(local_k)
        if px_k < LOW_PX_THRESHOLD:
            continue
        if px_k <= best_px:
            continue  # ya hay una mejor
        # Verificar identidad
        bytes_k = _read_local(local_k)
        if not bytes_k:
            continue
        if not _is_same_cover(cover_bytes, bytes_k):
            continue
        best_k = k
        best_px = px_k

    if best_k is None:
        return None
    return best_k, best_px


def run(items_path: Path, dry_run: bool) -> None:
    items = _load_items(items_path)
    promoted = 0
    examined = 0

    for it in items:
        if "_raw" in it:
            continue
        imgs = it.get("images") or []
        if len(imgs) < 2:
            continue
        cover_local = (imgs[0].get("local") or "")
        cover_px = _px(cover_local)
        if cover_px <= 0 or cover_px >= LOW_PX_THRESHOLD:
            continue  # portada ya grande o sin local → omitir
        examined += 1

        result = _best_hires_idx(it)
        if result is None:
            continue

        k, new_px = result
        title = it.get("title", "")[:50]
        print(f"  → promueve images[{k}]  {cover_px:>7} px → {new_px:>7} px  {title}")

        if not dry_run:
            # Intercambio en lugar (el thumb NO se elimina; queda en la galería).
            imgs[0], imgs[k] = imgs[k], imgs[0]
            it["images"] = imgs
        promoted += 1

    slug_str = f"  ({examined} con portada <{LOW_PX_THRESHOLD // 1000}k px examinadas)"
    print(f"\n[promote_hires_cover] items examinados: {examined}{slug_str}")
    print(f"[promote_hires_cover] promovidos:       {promoted}")

    if dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return

    if promoted == 0:
        print("[promote_hires_cover] nada que hacer.")
        return

    backup_and_rotate(items_path, "promote-hires-cover")
    _write_items(items_path, items)
    print(f"[promote_hires_cover] escrito {items_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Promueve portadas hi-res desde la galería a images[0]."
    )
    p.add_argument("--items", default="data/items.jsonl",
                   help="Ruta a items.jsonl (default: data/items.jsonl)")
    p.add_argument("--dry-run", action="store_true",
                   help="Muestra los cambios sin escribir.")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    root = Path(__file__).resolve().parents[2]
    run(
        items_path=root / args.items,
        dry_run=args.dry_run,
    )
