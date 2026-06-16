#!/usr/bin/env python3
"""optimize_images.py — backfill: estandariza el espejo histórico data/images/.

Aplica ``image_store.normalize_image`` a CADA archivo del espejo: redimensiona a
≤ NORMALIZE_MAX_LONG_SIDE px de lado largo + re-encodea a WebP q80 + strip de
metadata. Reduce data/images/ ~80% (clave para Cloudflare R2 y velocidad web). Es la
pasada one-shot que pone al día las ~24k imágenes ya descargadas; los ingresos NUEVOS
ya entran normalizados por ``image_store.download_image`` y ``_save_image`` (los
cuellos de botella, fuente única) — no hace falta re-correr esto salvo backlog viejo.

Comportamiento:
  - Idempotente: una imagen ya WebP y ≤ máx se saltea (cero pérdida generacional). Un
    WebP > máx se redimensiona in situ (mismo nombre, sin tocar items.jsonl).
  - Placeholders (1×1, sólidos, firmas) NO se tocan (``normalize_image`` los devuelve
    crudos) → ``purge_placeholder_images`` los sigue detectando por firma sha1.
  - Cambio de extensión (.jpg/.png/.gif/.avif → .webp): reescribe ``images[].local`` y
    ``sources[].image_local`` en items.jsonl, y las referencias de cover_preview.json.
  - Originales: por defecto se ARCHIVAN a data/images/_originals/ (reversible; GC luego
    con ``mirror_images.py`` o borrando esa carpeta). ``--originals delete`` los borra;
    ``--originals keep`` los deja en su sitio (quedan huérfanos para el GC).
  - Crash-safe: escribe los .webp nuevos → actualiza referencias → recién después
    archiva los originales. Si se corta a mitad, items.jsonl sigue apuntando a archivos
    que existen; re-correr es idempotente. Atómico (tmp + replace) y con backup.

Uso:
    .venv/bin/python scripts/retrofit/optimize_images.py --dry-run --limit 800  # estimar
    .venv/bin/python scripts/retrofit/optimize_images.py --limit 500            # probar
    .venv/bin/python scripts/retrofit/optimize_images.py --workers 4            # todo

⚠️ Cerrá el panel de cover-preview antes de correrlo (reescribe cover_preview.json;
si el panel guarda encima, el guard de mtime lo fuerza a recargar — no se pierde nada).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import image_store  # type: ignore  # noqa: E402
from manga_watch import backup_and_rotate  # type: ignore  # noqa: E402

_ROOT = _SCRIPTS.parent
_IMAGES_DIR = _ROOT / "data" / "images"
_ITEMS_PATH = _ROOT / "data" / "items.jsonl"
_PREVIEW_PATH = _ROOT / "data" / "cover_preview.json"
_SKIP_DIRS = {"_orphans", "_originals"}


# ── IO de items.jsonl (preserva orden de claves → diff mínimo) ──────────────────

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
    lines = [
        it["_raw"] if "_raw" in it else json.dumps(it, ensure_ascii=False)
        for it in items
    ]
    tmp = dst.with_name(f"{dst.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(dst)


def _atomic_write_bytes(dest: Path, data: bytes) -> None:
    tmp = dest.with_name(f"{dest.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_bytes(data)
        tmp.replace(dest)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


# ── Procesamiento por archivo (fase 1: NO toca originales) ──────────────────────

def _process_file(path: Path, images_dir: Path, dry_run: bool,
                  max_long_side: int, quality: int) -> dict:
    """Normaliza un archivo y escribe el target .webp (sin archivar el original).

    Devuelve {action, before, after, rename}. action ∈ skip|resized|converted|
    deduped|error. rename = (old_name, new_name) sólo si cambió la extensión.
    """
    try:
        body = path.read_bytes()
    except OSError:
        return {"action": "error", "before": 0, "after": 0, "rename": None}
    before = len(body)
    try:
        new_bytes, ext = image_store.normalize_image(
            body, max_long_side=max_long_side, quality=quality
        )
    except Exception:
        return {"action": "error", "before": before, "after": before, "rename": None}
    after = len(new_bytes)
    target = images_dir / (path.stem + ext)

    # Sin cambio real y mismo nombre (ya webp ≤máx / placeholder / fallback) → skip.
    if target == path and new_bytes == body:
        return {"action": "skip", "before": before, "after": before, "rename": None}

    # WebP > máx: redimensionado in situ (mismo nombre) → overwrite, sin rename.
    if target == path:
        if not dry_run:
            _atomic_write_bytes(target, new_bytes)
        return {"action": "resized", "before": before, "after": after, "rename": None}

    # Cambio de extensión → .webp
    existed = target.exists()
    if not existed and not dry_run:
        _atomic_write_bytes(target, new_bytes)
    return {
        "action": "deduped" if existed else "converted",
        "before": before,
        "after": after,
        "rename": (path.name, target.name),
    }


# ── Fase 2: actualizar referencias ───────────────────────────────────────────────

def _apply_renames_to_items(items_path: Path, rename: dict[str, str]) -> int:
    items = _load_items(items_path)
    changed = 0
    for it in items:
        if "_raw" in it:
            continue
        for im in (it.get("images") or []):
            if isinstance(im, dict) and im.get("local") in rename:
                im["local"] = rename[im["local"]]
                changed += 1
        for sc in (it.get("sources") or []):
            if isinstance(sc, dict) and sc.get("image_local") in rename:
                sc["image_local"] = rename[sc["image_local"]]
                changed += 1
    if changed:
        backup_and_rotate(items_path, "optimize")
        _write_items(items_path, items)
    return changed


def _apply_renames_to_preview(preview_path: Path, rename: dict[str, str]) -> int:
    if not preview_path.exists() or not rename:
        return 0
    try:
        data = json.loads(preview_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    n = [0]

    def walk(o):
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(x) for x in o]
        if isinstance(o, str) and o in rename:
            n[0] += 1
            return rename[o]
        return o

    new = walk(data)
    if n[0]:
        backup_and_rotate(preview_path, "optimize")
        tmp = preview_path.with_name(f"{preview_path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(preview_path)
    return n[0]


# ── Fase 3: archivar/borrar originales ───────────────────────────────────────────

def _retire_original(images_dir: Path, old_name: str, mode: str) -> None:
    src = images_dir / old_name
    if not src.is_file():
        return
    if mode == "delete":
        src.unlink(missing_ok=True)
    elif mode == "keep":
        return
    else:  # archive
        dest_dir = images_dir / "_originals"
        dest_dir.mkdir(exist_ok=True)
        dest = dest_dir / old_name
        if dest.exists():
            src.unlink(missing_ok=True)  # ya archivado en un run previo
        else:
            shutil.move(str(src), str(dest))


# ── Orquestación ─────────────────────────────────────────────────────────────────

def _iter_files(images_dir: Path):
    for p in sorted(images_dir.iterdir()):
        if p.is_dir() or p.name.endswith(".tmp"):
            continue
        if p.is_file():
            yield p


def run(images_dir: Path, items_path: Path, preview_path: Path, *,
        workers: int, limit: int, dry_run: bool, originals_mode: str,
        max_long_side: int, quality: int) -> dict:
    files = list(_iter_files(images_dir))
    if limit > 0:
        files = files[:limit]
    total = len(files)
    print(f"Archivos a evaluar: {total:,}  (máx {max_long_side}px, WebP q{quality}, "
          f"workers {workers})")
    if dry_run:
        print("[DRY-RUN] Se normaliza para medir, pero NO se escribe nada.")

    rename: dict[str, str] = {}
    counter: Counter = Counter()
    freed = 0

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(_process_file, p, images_dir, dry_run, max_long_side, quality): p
            for p in files
        }
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            counter[r["action"]] += 1
            if r["action"] in ("resized", "converted"):
                freed += max(0, r["before"] - r["after"])
            elif r["action"] == "deduped":
                freed += r["before"]
            if r["rename"]:
                rename[r["rename"][0]] = r["rename"][1]
            if i % 1000 == 0:
                print(f"  {i:,}/{total:,}…", flush=True)

    print(f"\nResumen: {dict(counter)}")
    print(f"Reducción estimada: {freed / 1e9:.2f} GB")

    if dry_run:
        for old, new in list(rename.items())[:10]:
            print(f"  {old} → {new}")
        if len(rename) > 10:
            print(f"  ... y {len(rename) - 10:,} renames más.")
        return {"counter": dict(counter), "freed": freed, "renames": len(rename)}

    if rename:
        ic = _apply_renames_to_items(items_path, rename)
        pc = _apply_renames_to_preview(preview_path, rename)
        print(f"Referencias: items.jsonl {ic:,} · cover_preview.json {pc:,}")
        for old in rename:
            _retire_original(images_dir, old, originals_mode)
        verb = {"archive": "archivados en _originals/", "delete": "borrados",
                "keep": "dejados en su sitio (huérfanos)"}[originals_mode]
        print(f"Originales ({len(rename):,}): {verb}")

    return {"counter": dict(counter), "freed": freed, "renames": len(rename)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="no escribe nada; estima")
    ap.add_argument("--limit", type=int, default=0, help="procesar sólo N archivos")
    ap.add_argument("--workers", type=int, default=0,
                    help="hilos (default: núcleos/2)")
    ap.add_argument("--originals", choices=["archive", "delete", "keep"],
                    default="archive", help="qué hacer con el original tras convertir")
    ap.add_argument("--max-long-side", type=int,
                    default=image_store.NORMALIZE_MAX_LONG_SIDE)
    ap.add_argument("--quality", type=int, default=image_store.NORMALIZE_QUALITY)
    ap.add_argument("--images-dir", type=Path, default=_IMAGES_DIR)
    ap.add_argument("--items", type=Path, default=_ITEMS_PATH)
    ap.add_argument("--preview", type=Path, default=_PREVIEW_PATH)
    args = ap.parse_args()

    workers = args.workers if args.workers > 0 else max(1, (os_cpu() // 2))
    if not args.images_dir.exists():
        print(f"ERROR: no existe {args.images_dir}")
        sys.exit(1)

    run(args.images_dir, args.items, args.preview,
        workers=workers, limit=args.limit, dry_run=args.dry_run,
        originals_mode=args.originals, max_long_side=args.max_long_side,
        quality=args.quality)


def os_cpu() -> int:
    import os
    return os.cpu_count() or 2


if __name__ == "__main__":
    main()
