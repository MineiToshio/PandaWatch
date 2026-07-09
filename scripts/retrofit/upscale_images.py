#!/usr/bin/env python3
"""upscale_images.py — AI upscaling de portadas pixeladas (Option C).

Para imágenes en `data/images/` que tienen menos de `--max-pixels` píxeles
(default 200 000 ≈ 450×445 px), aplica un upscaler de IA para mejorar la
resolución. Diseñado para portadas de fuentes que no exponen imágenes en
alta resolución (sumikko, booksprivilege, Rakuten JP, animeclick, etc.).

Upscalers soportados (se detectan automáticamente en orden de preferencia):
  1. waifu2x-ncnn-vulkan  (Vulkan; mejor para anime/manga, el preferido)
  2. realesrgan-ncnn-vulkan (Vulkan; más general, también bueno para manga)

Instalación (macOS, Homebrew):
  brew install waifu2x-ncnn-vulkan
  brew install realesrgan-ncnn-vulkan   # alternativa si no tenés el primero

Comportamiento:
  - Escala ×2 por default (--scale 2). Imágenes de ~150×220 → ~300×440.
  - El upscaler produce un PNG lossless, pero NO se guarda crudo: pasa por
    `image_store.normalize_image` (fuente única, P27 2026-07-07) antes de
    escribirse al espejo — mismo tratamiento (AVIF Q60, lado largo ≤1600px)
    que cualquier otra imagen que entra al corpus, así una portada upscaleada
    no pesa órdenes de magnitud más que sus pares. El nombre de archivo es
    content-addressed (sha256 de los bytes normalizados), igual que
    fetch_better_covers/image_store.download_image.
  - Marca cada entry de `images[]` afectada con `upscaled: true` — permite a
    scripts downstream (ej. fetch_better_covers) distinguir un upscale de IA
    de una foto hi-res real y preferir reemplazarla si aparece una mejor.
  - Idempotente: una entry con `upscaled: true` se saltea SIEMPRE (no se
    re-upscalea un upscale — degradaría más la imagen); es la señal primaria
    de idempotencia, más robusta que inferir por tamaño de archivo.
  - Items aprobados (`approved_at`, golden records) se saltean por defecto
    (`--include-approved` para forzar): upscalear reemplaza el archivo
    referenciado por `images[i].local` sin cola de revisión.
  - Procesa los archivos en serie (el upscaler ya paraleliza internamente
    en GPU).
  - GC-friendly: el archivo original (.jpg) queda en su lugar y se elimina
    sólo si el reemplazo normalizado se escribió exitosamente. Si algo falla,
    el original sigue disponible.

Uso:
    # Instalar primero: brew install waifu2x-ncnn-vulkan
    python scripts/retrofit/upscale_images.py --dry-run   # cuántas hay
    python scripts/retrofit/upscale_images.py --limit 20  # probar
    python scripts/retrofit/upscale_images.py             # todo

    # Opciones avanzadas
    python scripts/retrofit/upscale_images.py --max-pixels 100000 --scale 2
    python scripts/retrofit/upscale_images.py --no-delete-original  # conservar jpg
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import image_store  # type: ignore
try:  # import dual robusto (CLI directo vs wrapper raíz bajo pytest)
    from manga_watch import (  # type: ignore  # noqa: E402
        backup_and_rotate, is_approved, write_lines_atomic,
    )
except ImportError:  # pragma: no cover
    from scripts.manga_watch import (  # type: ignore  # noqa: E402
        backup_and_rotate, is_approved, write_lines_atomic,
    )


# ── Upscaler detection ────────────────────────────────────────────────────────

def _find_upscaler() -> tuple[str, str] | None:
    """Devuelve (binary_path, kind) del primer upscaler disponible."""
    candidates = [
        ("waifu2x-ncnn-vulkan", "waifu2x"),
        ("realesrgan-ncnn-vulkan", "realesrgan"),
    ]
    for name, kind in candidates:
        path = shutil.which(name)
        if path:
            return path, kind
    return None


def _upscale_file(
    upscaler_path: str,
    upscaler_kind: str,
    src: Path,
    dst: Path,
    scale: int,
    denoise: int,
) -> bool:
    """Upscalea `src` → `dst` con el binario dado. Devuelve True si éxito."""
    if upscaler_kind == "waifu2x":
        cmd = [
            upscaler_path,
            "-i", str(src),
            "-o", str(dst),
            "-s", str(scale),
            "-n", str(denoise),
            "-f", "png",
        ]
    else:  # realesrgan
        # realesrgan soporta scale 2 y 4; model realesrgan-x4plus-anime para manga
        model = "realesrgan-x4plus-anime" if scale >= 4 else "realesrnet-x2plus"
        cmd = [
            upscaler_path,
            "-i", str(src),
            "-o", str(dst),
            "-s", str(scale),
            "-n", model,
            "-f", "png",
        ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=120,
        )
        return result.returncode == 0 and dst.exists() and dst.stat().st_size > 0
    except (subprocess.TimeoutExpired, OSError):
        return False


# ── Image dimensions ──────────────────────────────────────────────────────────

def _pixels_from_bytes(data: bytes) -> int | None:
    """Cuenta píxeles totales de una imagen ya en memoria."""
    if len(data) < 24:
        return None

    if data[:8] == b"\x89PNG\r\n\x1a\n":
        try:
            w, h = struct.unpack(">II", data[16:24])
            return w * h
        except struct.error:
            return None

    if data[:6] in (b"GIF87a", b"GIF89a"):
        try:
            w, h = struct.unpack("<HH", data[6:10])
            return w * h
        except struct.error:
            return None

    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        if data[12:16] == b"VP8 " and len(data) >= 30:
            try:
                w = (struct.unpack_from("<H", data, 26)[0] & 0x3FFF) + 1
                h = (struct.unpack_from("<H", data, 28)[0] & 0x3FFF) + 1
                return w * h
            except struct.error:
                pass
        return None

    if data[:3] == b"\xff\xd8\xff":
        i = 2
        while i + 4 < len(data):
            if data[i] != 0xFF:
                break
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                if i + 9 < len(data):
                    h, w = struct.unpack(">HH", data[i + 5: i + 9])
                    return w * h
                break
            if i + 4 > len(data):
                break
            length = struct.unpack(">H", data[i + 2: i + 4])[0]
            i += 2 + length
        return None

    # AVIF (y cualquier otro formato que el parser de bytes no cubre): fallback
    # a PIL — sin esto, la salida normalizada (P27, siempre AVIF) medía por
    # tamaño de archivo (proxy), que para AVIF comprimido es sistemáticamente
    # MENOR que los píxeles reales y el gate de ganancia rechazaba TODO upscale.
    try:
        import io

        from PIL import Image  # noqa: PLC0415

        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
            if w > 0 and h > 0:
                return w * h
    except Exception:
        pass

    # Fallback final: file size as rough proxy
    return len(data)


def _pixels(path: Path) -> int | None:
    """Cuenta píxeles totales de una imagen sin dependencias externas."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return _pixels_from_bytes(data)


# ── Protección de refs adicionales antes de borrar el original (hallazgo #3) ──
# `_collect_targets` agrupa refs SOLO vía `images[].local` (portada + galería) —
# `--delete-original` (default ON) borraba el archivo VIEJO en cuanto reemplazaba
# esas refs, sin chequear que ninguna OTRA estructura siguiera apuntando al mismo
# filename: `sources[i].image_local` (ref legacy per-fuente, este script no la
# actualiza) y `data/cover_preview.json` (old_image / candidates[].new_image /
# current_images[].local — la cola de revisión de portadas referencia archivos
# por nombre). Mismo set que protege el GC de `mirror_images.py`.

def _sources_image_locals(items: list[dict]) -> set[str]:
    """`sources[].image_local` de TODOS los items — ref per-fuente que este
    script no actualiza cuando reemplaza `images[].local`."""
    out: set[str] = set()
    for it in items:
        if "_raw" in it:
            continue
        for s in (it.get("sources") or []):
            if isinstance(s, dict) and s.get("image_local"):
                out.add(s["image_local"])
    return out


def _cover_preview_locals(preview_path: Path) -> set[str]:
    """Filenames referenciados por `data/cover_preview.json`: `old_image`,
    `candidates[].new_image`, `current_images[].local` — el panel de revisión
    de portadas (`cover-preview.html`) queda con fotos rotas si se los borra."""
    refs: set[str] = set()
    if not preview_path.exists():
        return refs
    try:
        data = json.loads(preview_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return refs
    entries = data if isinstance(data, list) else data.get("items", data.get("entries", []))
    for e in entries or []:
        v = e.get("old_image")
        if v and v != "[dry-run]":
            refs.add(v)
        for c in (e.get("candidates") or []):
            v = c.get("new_image")
            if v and v != "[dry-run]":
                refs.add(v)
        for ci in (e.get("current_images") or []):
            v = ci.get("local") if isinstance(ci, dict) else None
            if v:
                refs.add(v)
    return refs


def _protected_locals(items: list[dict], preview_path: Path) -> set[str]:
    """Unión de refs adicionales (fuera de `images[].local`) que
    `--delete-original` debe respetar antes de borrar el archivo viejo."""
    return _sources_image_locals(items) | _cover_preview_locals(preview_path)


# ── IO ────────────────────────────────────────────────────────────────────────

def _load_items(src: Path) -> list[dict]:
    items: list[dict] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                items.append({"_raw": line})
    return items


def _write_items(dst: Path, items: list[dict]) -> None:
    lines = []
    for it in items:
        lines.append(it["_raw"] if "_raw" in it
                     else json.dumps(it, ensure_ascii=False, sort_keys=True))
    write_lines_atomic(dst, lines)


# ── Main logic ────────────────────────────────────────────────────────────────

def _collect_targets(
    items: list[dict],
    images_dir: Path,
    max_pixels: int,
    *,
    include_approved: bool = False,
) -> tuple[list[tuple[str, Path, list[dict]]], int, int]:
    """Agrupa por `image_local` los items que tienen imágenes pequeñas.

    Devuelve ([(local, path, [items_that_reference_it]), ...], skipped_already_upscaled,
    skipped_approved) sólo para archivos que existen y tienen píxeles < max_pixels.

    Agrupa por cada `local` de images[] (la portada es images[0], el resto
    galería). Un mismo archivo lo pueden referenciar varios items (cross-source).

    Dos guards, ambos a nivel de ARCHIVO (no de item — un mismo `local` puede
    ser compartido por varios items y no queremos actualizar unos sí y otros no,
    dejando una referencia colgando si el original se borra):
      - `upscaled: true` en cualquier entry que apunte a este `local` → ya es un
        upscale de IA, no se re-procesa (idempotencia, P27).
      - cualquier item referenciando este `local` está aprobado (`approved_at`)
        y no se pasó `--include-approved` → se saltea el archivo COMPLETO (no
        solo ese item), para no reemplazar un archivo que un golden record
        todavía necesita.
    """
    local_to_items: dict[str, list[dict]] = {}
    local_upscaled: set[str] = set()
    for it in items:
        if "_raw" in it:
            continue
        seen_locals: set[str] = set()
        for im in (it.get("images") or []):
            if not isinstance(im, dict):
                continue
            local = im.get("local") or ""
            if not local:
                continue
            if im.get("upscaled"):
                local_upscaled.add(local)
            if local not in seen_locals:
                seen_locals.add(local)
                local_to_items.setdefault(local, []).append(it)

    targets = []
    skipped_already_upscaled = 0
    skipped_approved = 0
    for local, refs in local_to_items.items():
        if local in local_upscaled:
            skipped_already_upscaled += 1
            continue
        if any(is_approved(it) for it in refs) and not include_approved:
            skipped_approved += 1
            continue
        path = images_dir / local
        if not path.is_file():
            continue
        px = _pixels(path)
        if px is None or px >= max_pixels:
            continue
        targets.append((local, path, refs))

    return targets, skipped_already_upscaled, skipped_approved


def run(
    items_path: Path,
    images_dir: Path,
    *,
    max_pixels: int,
    scale: int,
    denoise: int,
    limit: int,
    dry_run: bool,
    delete_original: bool,
    include_approved: bool = False,
    preview_path: Path | None = None,
) -> None:
    upscaler = _find_upscaler()
    if upscaler is None:
        print(
            "ERROR: No se encontró ningún upscaler.\n"
            "Instalá uno de estos con Homebrew:\n"
            "  brew install waifu2x-ncnn-vulkan\n"
            "  brew install realesrgan-ncnn-vulkan"
        )
        sys.exit(1)

    upscaler_path, upscaler_kind = upscaler
    print(f"Upscaler: {upscaler_kind} ({upscaler_path})")

    items = _load_items(items_path)
    targets, skipped_already_upscaled, skipped_approved = _collect_targets(
        items, images_dir, max_pixels, include_approved=include_approved,
    )

    if limit > 0:
        targets = targets[:limit]

    total = len(targets)
    print(f"Imágenes candidatas (< {max_pixels:,} px): {total}")
    if skipped_already_upscaled:
        print(f"  ya upscaleadas (marcadas `upscaled: true`, no se re-procesan): "
              f"{skipped_already_upscaled}")
    if skipped_approved:
        print(f"  archivos de items aprobados saltados (usar --include-approved): "
              f"{skipped_approved}")

    if dry_run:
        print("[DRY-RUN] No se harán cambios.")
        for local, path, refs in targets[:20]:
            px = _pixels(path) or 0
            print(f"  {local}  ({px:,} px)  → ×{scale}  [{len(refs)} items]")
        if total > 20:
            print(f"  ... y {total - 20} más.")
        return

    if total == 0:
        print("Nada que upscalear.")
        return

    backup_and_rotate(items_path, "upscale")
    counter: Counter = Counter()
    counter["already_done"] = skipped_already_upscaled
    items_changed = False

    # Hallazgo #3 (2026-07-08): refs adicionales que `--delete-original` debe
    # respetar antes de borrar el archivo viejo (ver docstring arriba). Se
    # computa UNA vez sobre el estado inicial — ninguna de las dos fuentes
    # (sources[].image_local, cover_preview.json) la muta este script.
    preview_path = preview_path or (items_path.parent / "cover_preview.json")
    protected_locals = _protected_locals(items, preview_path) if delete_original else set()

    for i, (local, src_path, refs) in enumerate(targets, 1):
        print(f"  [{i}/{total}] {local} ({_pixels(src_path) or 0:,} px) → ×{scale}…", end=" ", flush=True)

        # Upscalear a un .tmp primero para atomicidad
        with tempfile.NamedTemporaryFile(
            suffix=".png", dir=images_dir, delete=False
        ) as tf:
            tmp_path = Path(tf.name)

        ok = _upscale_file(upscaler_path, upscaler_kind, src_path, tmp_path, scale, denoise)
        if not ok:
            tmp_path.unlink(missing_ok=True)
            print("FALLÓ")
            counter["errors"] += 1
            continue

        raw_data = tmp_path.read_bytes()
        tmp_path.unlink(missing_ok=True)

        # P27: pasa por normalize_image (fuente única en image_store) en vez de
        # escribir el PNG lossless crudo del upscaler al espejo — mismo formato/
        # tamaño (AVIF Q60, lado largo ≤1600px) que el resto del corpus.
        norm_data, norm_ext = image_store.normalize_image(raw_data)
        new_px = _pixels_from_bytes(norm_data) or 0
        old_px = _pixels(src_path) or 0
        if new_px <= old_px:
            print(f"sin ganancia ({new_px:,} px)")
            counter["no_gain"] += 1
            continue

        # Nombre content-addressed (misma convención que download_image/_save_image):
        # la imagen normalizada reusa archivo si dos upscales dan el mismo resultado.
        new_local = hashlib.sha256(norm_data).hexdigest()[:16] + norm_ext
        dst_path = images_dir / new_local
        if not dst_path.exists():
            tmp2 = dst_path.with_name(f"{dst_path.name}.{uuid.uuid4().hex}.tmp")
            tmp2.write_bytes(norm_data)
            tmp2.replace(dst_path)
        print(f"{old_px:,} → {new_px:,} px ✓")
        counter["upscaled"] += 1

        # Actualizar el `local` (y marcar `upscaled: true`, P27) en cada entry de
        # images[] que apunte al archivo viejo (la portada es images[0]).
        for it in refs:
            imgs = it.get("images") or []
            for img in imgs:
                if isinstance(img, dict) and img.get("local") == local:
                    img["local"] = new_local
                    img["upscaled"] = True
        items_changed = True

        # Eliminar original si se pidió — SOLO si ninguna ref adicional (fuera
        # de images[].local, ya actualizada arriba) sigue apuntando al archivo
        # viejo (hallazgo #3): sources[].image_local o cover_preview.json.
        if delete_original and src_path != dst_path:
            if local in protected_locals:
                counter["kept_protected"] += 1
                print(f"    (original conservado: referenciado por sources[]/"
                      f"cover_preview.json)")
            else:
                src_path.unlink(missing_ok=True)

        # Flush inmediato tras cada upscale exitoso: no pérdida si se cancela
        if not dry_run:
            _write_items(items_path, items)

    # Flush final (garantiza que el último bloque está guardado)
    if not dry_run and items_changed:
        _write_items(items_path, items)

    print(
        f"\n✓ Resultado:"
        f"\n  Upscaleadas:    {counter['upscaled']:>4}"
        f"\n  Sin ganancia:   {counter['no_gain']:>4}"
        f"\n  Ya procesadas:  {counter['already_done']:>4}"
        f"\n  Errores:        {counter['errors']:>4}"
    )
    if counter["kept_protected"]:
        print(f"  Originales conservados (sources[]/cover_preview.json aún los "
              f"referencian): {counter['kept_protected']:>4}")
    if counter["upscaled"] > 0 and items_changed:
        print("\nitems.jsonl actualizado con los nuevos `image_local`.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "AI upscaling de portadas pixeladas usando waifu2x-ncnn-vulkan "
            "o realesrgan-ncnn-vulkan. Instalar primero: brew install waifu2x-ncnn-vulkan"
        )
    )
    p.add_argument("--items", default="data/items.jsonl")
    p.add_argument("--images-dir", default="data/images")
    p.add_argument(
        "--max-pixels", type=int, default=200_000,
        help="Solo procesa imágenes con menos de N píxeles (default 200 000 ≈ 450×445)",
    )
    p.add_argument(
        "--scale", type=int, default=2, choices=[2, 4],
        help="Factor de escala (default 2; waifu2x soporta 1-4, realesrgan 2 o 4)",
    )
    p.add_argument(
        "--denoise", type=int, default=1,
        help="Nivel de denoise 0-3 (solo waifu2x, default 1 = leve)",
    )
    p.add_argument("--limit", type=int, default=0, help="Limitar a los primeros N archivos")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--no-delete-original", action="store_true",
        help="No borrar el .jpg original cuando se guarda el reemplazo normalizado",
    )
    p.add_argument(
        "--include-approved", action="store_true",
        help="También upscalea archivos referenciados por items aprobados (golden "
             "records). Por defecto se saltea el archivo ENTERO si alguno de sus "
             "referenciantes está aprobado (`approved_at`), para no reemplazar una "
             "imagen que un golden record todavía necesita.",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    root = Path(__file__).resolve().parent.parent.parent
    run(
        items_path=root / args.items,
        images_dir=root / args.images_dir,
        max_pixels=args.max_pixels,
        scale=args.scale,
        denoise=args.denoise,
        limit=args.limit,
        dry_run=args.dry_run,
        delete_original=not args.no_delete_original,
        include_approved=args.include_approved,
    )
