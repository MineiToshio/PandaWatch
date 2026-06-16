#!/usr/bin/env python3
"""migrate_images_to_avif.py — migración one-shot: re-deriva el espejo a AVIF.

Convierte los masters actuales (WebP) a **AVIF Q60 re-derivando desde los originales**
archivados en `data/images/_originals/` (sin doble compresión: la calidad sale de la
fuente, no del WebP intermedio). Además:
  - **Dedup por contenido**: dos imágenes pixel-idénticas tras normalizar colapsan a UN
    solo archivo (las refs apuntan al mismo), recuperando los duplicados cross-source.
  - Reescribe `images[].local` / `sources[].image_local` en items.jsonl y las refs de
    `cover_preview.json`.
  - **Borra los WebP reemplazados** (redundantes; el original sigue en `_originals/`).

Para un master sin original archivado (los ~900 que ya eran WebP de origen) re-deriva
desde el propio WebP (una compresión extra mínima). Placeholders (.gif/.jpg/.png que NO
son portadas) quedan intactos. Crash-safe (escribe .avif → actualiza refs → borra WebP)
y **RESUMIBLE**: items.jsonl no se toca hasta el final, así que un crash lo deja intacto
(la web sigue mostrando WebP); al re-correr, los .avif ya escritos por la corrida previa se
COMMITEAN sin re-derivar (continúa donde quedó, no rehace). Con backup de items/cover_preview.

Uso:
    .venv/bin/python scripts/retrofit/migrate_images_to_avif.py --dry-run --limit 500
    .venv/bin/python scripts/retrofit/migrate_images_to_avif.py --workers 8

⚠️ Cerrá el panel de cover-preview antes (reescribe cover_preview.json).
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import image_store  # type: ignore  # noqa: E402
import optimize_images as oi  # type: ignore  # noqa: E402  (helpers de refs/IO reusados)

_ROOT = _SCRIPTS.parent
_IMAGES_DIR = _ROOT / "data" / "images"
_ORIGINALS = _IMAGES_DIR / "_originals"
_ITEMS_PATH = _ROOT / "data" / "items.jsonl"
_PREVIEW_PATH = _ROOT / "data" / "cover_preview.json"


def _current_masters(images_dir: Path) -> dict[str, str]:
    """{stem: filename} del master actual. Si un stem tiene un master no-AVIF (p.ej.
    .webp) Y un .avif (una corrida previa interrumpida escribió el .avif pero no llegó a
    borrar el .webp), devuelve el NO-avif (el master a reemplazar); _process detecta el
    .avif ya hecho y lo commitea SIN re-derivar (resume). Un stem SOLO con .avif ya está
    hecho → se saltea."""
    non_avif: dict[str, str] = {}
    avif_only: dict[str, str] = {}
    for p in images_dir.iterdir():
        if p.is_dir() or p.name.endswith(".tmp") or not p.is_file():
            continue
        if p.suffix == ".avif":
            avif_only.setdefault(p.stem, p.name)
        else:
            non_avif[p.stem] = p.name
    out = dict(non_avif)
    for stem, name in avif_only.items():
        out.setdefault(stem, name)
    return out


def _process(stem: str, current_name: str, images_dir: Path, originals: Path,
             dry_run: bool, max_long_side: int, quality: int,
             seen: dict, lock: threading.Lock) -> dict:
    current = images_dir / current_name

    # Idempotencia: si el master ya es AVIF, nada que migrar.
    if current_name.endswith(".avif"):
        return {"action": "skip", "before": current.stat().st_size if current.exists()
                else 0, "after": 0, "rename": None, "delete": None}

    # RESUME: si el .avif del stem YA existe (una corrida previa interrumpida lo escribió;
    # los writes son atómicos → completo y correcto), lo COMMITEAMOS sin re-derivar. Así un
    # crash a mitad CONTINÚA desde donde quedó en vez de rehacer las ya hechas.
    target_name = stem + ".avif"
    target = images_dir / target_name
    if target.is_file() and current_name != target_name:
        return {"action": "resumed",
                "before": current.stat().st_size if current.exists() else 0,
                "after": target.stat().st_size,
                "rename": (current_name, target_name), "delete": current_name}

    # Fuente: original archivado (mejor calidad) o, si no hay, el master actual.
    src = None
    for cand in sorted(originals.glob(stem + ".*")):
        if cand.is_file():
            src = cand
            break
    src = src or current
    try:
        body = src.read_bytes()
        before = current.stat().st_size if current.exists() else len(body)
    except OSError:
        return {"action": "error", "before": 0, "after": 0, "rename": None, "delete": None}

    try:
        avif, ext = image_store.normalize_image(
            body, max_long_side=max_long_side, quality=quality
        )
    except Exception:
        return {"action": "error", "before": before, "after": before,
                "rename": None, "delete": None}

    if ext != ".avif":
        # placeholder / no-imagen → dejar el master como está
        return {"action": "skip", "before": before, "after": before,
                "rename": None, "delete": None}

    target_name = stem + ".avif"
    digest = hashlib.sha256(avif).hexdigest()
    with lock:
        canonical = seen.get(digest)
        if canonical is None:
            seen[digest] = target_name

    if canonical is not None:
        # Dedup: el ref del master actual apunta al canónico; el WebP actual se borra.
        return {"action": "deduped", "before": before, "after": 0,
                "rename": (current_name, canonical),
                "delete": current_name if current_name != canonical else None}

    if not dry_run:
        oi._atomic_write_bytes(images_dir / target_name, avif)
    return {"action": "converted", "before": before, "after": len(avif),
            "rename": (current_name, target_name) if current_name != target_name else None,
            "delete": current_name if current_name != target_name else None}


def run(images_dir: Path, originals: Path, items_path: Path, preview_path: Path, *,
        workers: int, limit: int, dry_run: bool, max_long_side: int, quality: int,
        batch: int = 2000) -> dict:
    masters = _current_masters(images_dir)
    stems = sorted(masters)
    if limit > 0:
        stems = stems[:limit]
    total = len(stems)
    print(f"Masters a re-derivar: {total:,}  (origen _originals/ con fallback; "
          f"AVIF Q{quality}, máx {max_long_side}px, workers {workers})")
    if dry_run:
        print("[DRY-RUN] No se escribe nada.")

    seen: dict[str, str] = {}
    lock = threading.Lock()
    counter: Counter = Counter()
    before_tot = after_tot = 0
    pending_rename: dict[str, str] = {}
    pending_delete: list[str] = []
    totals = {"renamed": 0, "deleted": 0}

    def _flush() -> None:
        """COMMIT INCREMENTAL: persiste el lote acumulado a items.jsonl + cover_preview y
        borra sus WebP. Hace el progreso DURABLE — si el proceso muere, lo ya commiteado
        queda hecho y un re-run continúa desde ahí (no se pierde ni se rehace el lote)."""
        if not pending_rename and not pending_delete:
            return
        if pending_rename:
            oi._apply_renames_to_items(items_path, pending_rename)
            oi._apply_renames_to_preview(preview_path, pending_rename)
            totals["renamed"] += len(pending_rename)
        for name in pending_delete:
            p = images_dir / name
            if p.is_file():
                p.unlink(missing_ok=True)
                totals["deleted"] += 1
        pending_rename.clear()
        pending_delete.clear()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(_process, s, masters[s], images_dir, originals, dry_run,
                      max_long_side, quality, seen, lock): s
            for s in stems
        }
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            counter[r["action"]] += 1
            before_tot += r["before"]
            after_tot += r["after"]
            if r["rename"]:
                pending_rename[r["rename"][0]] = r["rename"][1]
            if r["delete"]:
                pending_delete.append(r["delete"])
            if not dry_run and i % batch == 0:
                _flush()
                print(f"  {i:,}/{total:,} (commit incremental ✓)…", flush=True)
            elif i % 1000 == 0:
                print(f"  {i:,}/{total:,}…", flush=True)
    if not dry_run:
        _flush()  # lote final

    print(f"\nResumen: {dict(counter)}")
    print(f"Resumidas de corrida previa (sin re-derivar): {counter.get('resumed', 0):,}")
    print(f"Dedup por contenido: {counter.get('deduped', 0):,} colapsadas")
    print(f"Masters: {before_tot / 1e9:.2f} GB (WebP) -> {after_tot / 1e9:.2f} GB (AVIF)")
    if not dry_run:
        print(f"Commit: items.jsonl {totals['renamed']:,} refs actualizadas · "
              f"WebP borrados {totals['deleted']:,} (el original queda en _originals/)")

    return {"counter": dict(counter), "renames": totals["renamed"],
            "deleted": totals["deleted"], "deduped": counter.get("deduped", 0)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=0, help="hilos (default: núcleos/2)")
    ap.add_argument("--max-long-side", type=int, default=image_store.NORMALIZE_MAX_LONG_SIDE)
    ap.add_argument("--quality", type=int, default=image_store.NORMALIZE_QUALITY)
    ap.add_argument("--images-dir", type=Path, default=_IMAGES_DIR)
    ap.add_argument("--originals", type=Path, default=_ORIGINALS)
    ap.add_argument("--items", type=Path, default=_ITEMS_PATH)
    ap.add_argument("--preview", type=Path, default=_PREVIEW_PATH)
    args = ap.parse_args()

    import os
    workers = args.workers if args.workers > 0 else max(1, (os.cpu_count() or 2) // 2)
    if not args.images_dir.exists():
        print(f"ERROR: no existe {args.images_dir}")
        sys.exit(1)

    run(args.images_dir, args.originals, args.items, args.preview,
        workers=workers, limit=args.limit, dry_run=args.dry_run,
        max_long_side=args.max_long_side, quality=args.quality)


if __name__ == "__main__":
    main()
