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
  - Salida en PNG (lossless). Si el archivo original era .jpg y la salida
    es .png, actualiza `image_local` en items.jsonl. La función
    `existing_local_image()` de image_store hace glob `<stem>.*`, así que
    futuros scrapes del mismo URL usan el PNG sin re-descargar.
  - Procesa los archivos en serie (el upscaler ya paraleliza internamente
    en GPU). --workers controla cuántos ítems del JSONL se actualizan en
    lotes pero no lanza upscalers en paralelo (evita contención de GPU).
  - Idempotente: si el archivo ya fue upscaleado (píxeles ≥ threshold ×
    scale²), lo saltea.
  - GC-friendly: el archivo original (.jpg) queda en su lugar y se elimina
    sólo si el PNG nuevo reemplazó exitosamente. Si algo falla, el original
    sigue disponible.

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
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import image_store  # type: ignore
from manga_watch import backup_and_rotate  # type: ignore


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

def _pixels(path: Path) -> int | None:
    """Cuenta píxeles totales de una imagen sin dependencias externas."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
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

    # Fallback: file size as rough proxy
    return len(data)


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
    dst.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Main logic ────────────────────────────────────────────────────────────────

def _collect_targets(
    items: list[dict],
    images_dir: Path,
    max_pixels: int,
) -> list[tuple[str, Path, list[dict]]]:
    """Agrupa por `image_local` los items que tienen imágenes pequeñas.

    Devuelve [(image_local, path, [items_that_reference_it]), ...] sólo
    para archivos que existen y tienen píxeles < max_pixels.
    """
    local_to_items: dict[str, list[dict]] = {}
    for it in items:
        if "_raw" in it:
            continue
        local = it.get("image_local") or ""
        if not local:
            continue
        local_to_items.setdefault(local, []).append(it)

    targets = []
    for local, refs in local_to_items.items():
        path = images_dir / local
        if not path.is_file():
            continue
        px = _pixels(path)
        if px is None or px >= max_pixels:
            continue
        targets.append((local, path, refs))

    return targets


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
    targets = _collect_targets(items, images_dir, max_pixels)

    if limit > 0:
        targets = targets[:limit]

    total = len(targets)
    print(f"Imágenes candidatas (< {max_pixels:,} px): {total}")

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
    items_changed = False

    for i, (local, src_path, refs) in enumerate(targets, 1):
        stem = src_path.stem
        dst_path = images_dir / (stem + ".png")

        # Si ya existe un PNG (upscaleo previo) y tiene más píxeles, saltar.
        if dst_path.exists() and dst_path != src_path:
            existing_px = _pixels(dst_path) or 0
            src_px = _pixels(src_path) or 0
            if existing_px >= src_px * (scale ** 2) * 0.5:
                counter["already_done"] += 1
                continue

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

        new_px = _pixels(tmp_path) or 0
        old_px = _pixels(src_path) or 0
        if new_px <= old_px:
            tmp_path.unlink(missing_ok=True)
            print(f"sin ganancia ({new_px:,} px)")
            counter["no_gain"] += 1
            continue

        # Reemplazar: mover tmp → dst_path
        tmp_path.replace(dst_path)
        print(f"{old_px:,} → {new_px:,} px ✓")
        counter["upscaled"] += 1

        # Si el extension cambió (jpg → png), actualizar image_local en items
        new_local = dst_path.name
        if new_local != local:
            for it in refs:
                it["image_local"] = new_local
                # Sincronizar también dentro de images[0] si apunta al mismo archivo
                imgs = it.get("images") or []
                for img in imgs:
                    if isinstance(img, dict) and img.get("local") == local:
                        img["local"] = new_local
            items_changed = True

        # Eliminar original si se pidió
        if delete_original and src_path != dst_path:
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
        help="No borrar el .jpg original cuando se guarda el .png upscaleado",
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
    )
