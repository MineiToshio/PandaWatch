#!/usr/bin/env python3
"""backfill_prh_covers.py — portadas EN vía CDN de Penguin Random House.

Para items EN con ISBN-13 (prefijos 978-0 / 978-1), prueba la URL
determinística del CDN de PRH:

    https://images.penguinrandomhouse.com/cover/{isbn13}

PRH distribuye manga en inglés de: Dark Horse Manga, Kodansha Comics,
Seven Seas, Square Enix, TOKYOPOP, Titan, Vertical, Inklore, Yen Press
(Hachette) y más.  Para ISBNs fuera del catálogo PRH el CDN devuelve 404
(el magic-bytes validator de download_image lo descarta), así que el script
es seguro sobre cualquier item con ISBN-13 de prefijo anglófono.

Uso:
    python scripts/retrofit/backfill_prh_covers.py --dry-run
    python scripts/retrofit/backfill_prh_covers.py --limit 20
    python scripts/retrofit/backfill_prh_covers.py --workers 8
    python scripts/retrofit/backfill_prh_covers.py --min-gain 0  # acepta siempre
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import image_store  # type: ignore
try:  # import dual robusto (CLI directo vs wrapper raíz bajo pytest)
    from manga_watch import backup_and_rotate, make_session, is_approved  # type: ignore  # noqa: E402
except ImportError:  # pragma: no cover
    from scripts.manga_watch import backup_and_rotate, make_session, is_approved  # type: ignore  # noqa: E402

DEFAULT_USER_AGENT = "manga-watch-personal/0.2 (+personal-use)"

PRH_CDN_BASE = "https://images.penguinrandomhouse.com/cover/"

# Prefijos ISBN-13 asignados al mundo anglófono (US, UK, AU, CA…)
_EN_ISBN_PREFIXES = ("9780", "9781")

# Mínimo de píxeles para considerar que la imagen PRH es "real" (descarta
# placeholders de tipo "cover not available" que son thumbnails <5 KB).
_MIN_PRH_PIXELS = 80_000  # ~300×270 mínimo razonable para una portada


# ── ISBN ──────────────────────────────────────────────────────────────────────

def isbn_to_13(raw: str) -> str | None:
    """Normaliza cualquier ISBN (10 ó 13, con o sin guiones) a 13 dígitos."""
    digits = re.sub(r"[^0-9X]", "", raw.upper())
    if len(digits) == 13 and digits[:3] in ("978", "979"):
        return digits
    if len(digits) == 10:
        base = "978" + digits[:9]
        total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(base))
        check = (10 - (total % 10)) % 10
        return base + str(check)
    return None


# ── Pixel count ───────────────────────────────────────────────────────────────

def _dims_from_bytes(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        try:
            return struct.unpack(">II", data[16:24])
        except struct.error:
            return None
    if data[:6] in (b"GIF87a", b"GIF89a"):
        try:
            return struct.unpack("<HH", data[6:10])
        except struct.error:
            return None
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        if data[12:16] == b"VP8 " and len(data) >= 30:
            try:
                w = (struct.unpack_from("<H", data, 26)[0] & 0x3FFF) + 1
                h = (struct.unpack_from("<H", data, 28)[0] & 0x3FFF) + 1
                return w, h
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
                    h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                    return w, h
                break
            if i + 4 > len(data):
                break
            length = struct.unpack(">H", data[i + 2 : i + 4])[0]
            i += 2 + length
        return None
    return None


def _pixels(path: Path) -> int | None:
    try:
        data = path.read_bytes()
        dims = _dims_from_bytes(data)
        return dims[0] * dims[1] if dims else len(data)
    except OSError:
        return None


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


# ── Target collection ─────────────────────────────────────────────────────────

def _collect_targets(
    items: list[dict], *, include_approved: bool = False,
) -> tuple[list[tuple[dict, str]], int]:
    """Devuelve ([(item, isbn13), …], skipped_approved) para items EN con ISBN
    y sin PRH CDN. Items aprobados (`approved_at`) se saltean por defecto: este
    script reemplaza la portada auto-máticamente (sin cola de revisión) si la
    candidata PRH gana en píxeles — no debe pisar un golden record."""
    out: list[tuple[dict, str]] = []
    skipped_approved = 0
    for it in items:
        if "_raw" in it:
            continue
        if is_approved(it) and not include_approved:
            skipped_approved += 1
            continue
        raw_isbn = it.get("isbn") or ""
        if not raw_isbn:
            continue
        isbn13 = isbn_to_13(raw_isbn)
        if not isbn13:
            continue
        if not any(isbn13.startswith(p) for p in _EN_ISBN_PREFIXES):
            continue
        # Si ya usa PRH CDN, no hay nada que hacer.
        cur_url = image_store.normalize_image_url(image_store.cover_url(it))
        if cur_url == PRH_CDN_BASE + isbn13:
            continue
        out.append((it, isbn13))
    return out, skipped_approved


# ── Upgrade logic ─────────────────────────────────────────────────────────────

def _try_prh(
    item: dict,
    isbn13: str,
    images_dir: Path,
    session,
    timeout: tuple[int, int],
    min_gain: float,
) -> tuple[str, str] | None:
    """Descarga la portada PRH y devuelve (new_url, new_local) si mejora."""
    candidate_url = PRH_CDN_BASE + isbn13
    new_local = image_store.download_image(
        candidate_url, images_dir, session=session, timeout=timeout,
    )
    if not new_local:
        return None  # 404 o no imagen válida

    new_path = images_dir / new_local
    new_px = _pixels(new_path)

    # Descarta placeholders de tipo "cover not available" (pocas dimensiones).
    if new_px and new_px < _MIN_PRH_PIXELS:
        return None

    # Compara contra la imagen actual si existe.
    old_local = image_store.cover_local(item)
    old_path = images_dir / old_local if old_local else None
    if old_path and old_path.exists():
        old_px = _pixels(old_path)
        if old_px and new_px and new_px < old_px * (1 + min_gain):
            return None  # No hay mejora suficiente

    return candidate_url, new_local


def _apply(item: dict, new_url: str, new_local: str) -> None:
    image_store.set_cover(item, new_url, new_local)


# ── Runner ────────────────────────────────────────────────────────────────────

def run(
    items_path: Path,
    images_dir: Path,
    *,
    workers: int,
    timeout: tuple[int, int],
    limit: int,
    min_gain: float,
    dry_run: bool,
    user_agent: str,
    include_approved: bool = False,
) -> None:
    items = _load_items(items_path)
    targets, skipped_approved = _collect_targets(items, include_approved=include_approved)
    if limit > 0:
        targets = targets[:limit]

    total = len(targets)
    print(f"Items EN candidatos (ISBN sin PRH CDN): {total}")
    if skipped_approved:
        print(f"Items aprobados saltados (usar --include-approved): {skipped_approved}")

    if dry_run:
        print("[DRY-RUN] No se harán cambios.")
        for it, isbn13 in targets[:15]:
            cur_url = image_store.cover_url(it)[:55]
            print(f"  {isbn13}  →  {PRH_CDN_BASE}{isbn13}")
            print(f"           cur: {cur_url}")
        if total > 15:
            print(f"  ... y {total - 15} más.")
        return

    backup_and_rotate(items_path, "prh-covers")
    session = make_session(user_agent=user_agent)
    counter: Counter = Counter()

    # Dedup por ISBN: descargamos 1 vez, aplicamos a todos los items del cluster.
    isbn_to_items: dict[str, list[dict]] = {}
    for it, isbn13 in targets:
        isbn_to_items.setdefault(isbn13, []).append(it)

    unique_isbns = list(isbn_to_items.keys())
    print(f"ISBNs únicos a probar: {len(unique_isbns)}")

    def _process(isbn13: str) -> tuple[str, tuple[str, str] | None]:
        # Usa el item con portada local válida para la comparación de píxeles.
        sample = next(
            (it for it in isbn_to_items[isbn13]
             if image_store.cover_local(it)
             and (images_dir / image_store.cover_local(it)).exists()),
            isbn_to_items[isbn13][0],
        )
        return isbn13, _try_prh(sample, isbn13, images_dir, session, timeout, min_gain)

    completed = 0
    _FLUSH_EVERY = 20  # flush items.jsonl cada N ISBNs mejorados
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_process, isbn13): isbn13 for isbn13 in unique_isbns}
        for fut in as_completed(futures):
            isbn13 = futures[fut]
            completed += 1
            if completed % 50 == 0:
                print(f"  {completed}/{len(unique_isbns)} procesados…", flush=True)
            try:
                _, res = fut.result()
                if res is not None:
                    new_url, new_local = res
                    for it in isbn_to_items[isbn13]:
                        _apply(it, new_url, new_local)
                    counter["upgraded"] += 1
                    # Flush periódico: no pérdida de datos si se cancela
                    if not dry_run and counter["upgraded"] % _FLUSH_EVERY == 0:
                        _write_items(items_path, items)
                        print(f"  → flush parcial ({counter['upgraded']} mejoradas)", flush=True)
                else:
                    counter["no_gain"] += 1
            except Exception:
                counter["no_gain"] += 1
                counter["errors"] += 1

    # Flush final (incluye mejoras del último bloque < FLUSH_EVERY)
    if not dry_run:
        _write_items(items_path, items)

    print(
        f"\n✓ Resultado:"
        f"\n  Mejoradas:    {counter['upgraded']:>4}"
        f"\n  Sin mejora:   {counter['no_gain']:>4}  (PRH no tiene o misma resolución)"
        f"\n  Errores:      {counter['errors']:>4}"
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill portadas EN usando el CDN de Penguin Random House por ISBN-13."
    )
    p.add_argument("--items", default="data/items.jsonl")
    p.add_argument("--images-dir", default="data/images")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--timeout", type=int, default=20)
    p.add_argument(
        "--min-gain", type=float, default=0.10,
        help="Mejora mínima en píxeles para reemplazar la imagen actual (default 0.10 = 10%%)",
    )
    p.add_argument("--limit", type=int, default=0, help="Limitar a los primeros N targets")
    p.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    p.add_argument("--include-approved", action="store_true",
                    help="También reemplaza la portada de items aprobados (golden records). "
                         "Por defecto se saltean: este script auto-aplica la mejora sin cola "
                         "de revisión.")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    root = Path(__file__).resolve().parent.parent.parent
    run(
        items_path=root / args.items,
        images_dir=root / args.images_dir,
        workers=args.workers,
        timeout=(10, args.timeout),
        limit=args.limit,
        min_gain=args.min_gain,
        dry_run=args.dry_run,
        user_agent=args.user_agent,
        include_approved=args.include_approved,
    )
