#!/usr/bin/env python3
"""revalidate_cover_preview.py — re-valida OFFLINE la cola de portadas
(data/cover_preview.json) contra el gate endurecido del motor.

Motivo (2026-07-08): la mayoría de las candidatas PENDING vienen de una versión
VIEJA del skill watch-search-covers (la copia embebida que drifteó, causa de los
falsos positivos pre-2026-06-11). Esas entries traen `match_dist: null` y NUNCA
pasaron por el gate `_same_cover` / `_is_soft_image` endurecido. Como referencia
(`old_image`) y candidata (`new_image`) ya están espejadas en `data/images/`,
la re-validación se hace SIN red, reusando las funciones REALES del motor.

Política (delegación pura, cero lógica copiada):
  - Moot: si sync_cover_preview.py podaría la candidata (item borrado, portada
    vigente ya buena, target ausente/ok, ya-es-portada) → se DELEGA a sync; acá
    se detecta con `sync_preview()` y se deja intacta (sync la limpia después).
  - Referencia utilizable = `old_image` en disco Y px ≥ 10 000 (mismo umbral que
    el motor). Sin referencia utilizable → NO se auto-rechaza: solo `verified:
    false` (queda flageada para review humano). Ídem si falta el archivo de la
    candidata.
  - Re-validación (`_same_cover` + `_is_soft_image` sobre la candidata):
      PASA  → puebla `match_dist` (aHash Hamming, igual que sc_validate),
              `ref_pixels`, `verified: true`; queda PENDING (decide el owner).
      FALLA → `status: "rejected"` + `reject_reason: "auto_revalidation"`. El
              ledger NO se escribe acá (lo escribe apply_preview/sync al aplicar
              — escritor único; evita doble escritura).

Idempotencia: una candidata con status ≠ pending, o pending que ya tiene la clave
`verified` (procesada por una corrida previa o por el skill nuevo), NO se
reprocesa → correr 2× produce un JSON byte-idéntico.

Uso:
    .venv/bin/python scripts/retrofit/revalidate_cover_preview.py --dry-run
    .venv/bin/python scripts/retrofit/revalidate_cover_preview.py --apply
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
ITEMS_PATH = ROOT / "data" / "items.jsonl"
PREVIEW_PATH = ROOT / "data" / "cover_preview.json"
IMAGES_DIR = ROOT / "data" / "images"

sys.path.insert(0, str(ROOT / "scripts" / "retrofit"))
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_better_covers as fbc  # noqa: E402  (fuente única del gate)
from sync_cover_preview import (  # noqa: E402  (fuente única de la lógica de poda)
    _get_local_pixels,
    _load_items_by_slug,
    _write_atomic,
    sync_preview,
)

try:
    from manga_watch import backup_and_rotate  # noqa: E402
except ImportError:  # pragma: no cover - fallback de import
    from scripts.manga_watch import backup_and_rotate  # noqa: E402

# Umbral mínimo de referencia utilizable — el MISMO que aplica el motor/skill
# (sc_validate descarta candidatas < 10 000 px; la referencia se mide igual).
REF_MIN_PIXELS = 10_000
# Motivo de rechazo cuando la re-validación falla el gate de identidad/detalle.
# Está en fbc._IDENTITY_REJECT_REASONS, así el ledger puede vetar por hash.
REVALIDATION_REASON = "auto_revalidation"


def _candidate_key(slug: str, cand: dict) -> tuple[str, str, str, str]:
    """Identidad estable de una candidata (para diffear contra sync)."""
    return (
        slug,
        cand.get("action", "replace_cover"),
        cand.get("new_url", ""),
        cand.get("target", ""),
    )


def _surviving_candidate_keys(
    preview: list[dict],
    items_by_slug: dict[str, dict],
    images_dir: Path,
) -> set[tuple[str, str, str, str]]:
    """Candidatas que sync_preview() CONSERVARÍA (todo lo demás es moot). Se
    delega en la función real de sync (sobre una copia; write_ledger=False para
    no tocar la denylist durante la detección)."""
    synced, _ = sync_preview(
        copy.deepcopy(preview), items_by_slug, images_dir, write_ledger=False
    )
    keys: set[tuple[str, str, str, str]] = set()
    for entry in synced:
        slug = entry.get("slug", "")
        for cand in entry.get("candidates", []):
            keys.add(_candidate_key(slug, cand))
    return keys


def _pixels_on_disk(local: str | None, images_dir: Path) -> int:
    """Píxeles del archivo local vía PIL (0 si no existe / ilegible / sin PIL).

    Se reusa `_get_local_pixels` de sync (fuente única, PIL). Nota (hallazgo #11,
    2026-07-08): el comentario anterior decía que `fbc._get_pixels_from_bytes`
    NO cubre AVIF — eso ya no es cierto, el gate #132 le agregó fallback PIL vía
    `_get_dims_from_bytes` y SÍ mide AVIF correctamente. Igual delegamos acá en
    `_get_local_pixels` porque partimos de un Path (no de bytes ya leídos) y así
    evitamos una lectura+decode redundante del archivo."""
    return _get_local_pixels(local, images_dir)


def revalidate_preview(
    preview: list[dict],
    items_by_slug: dict[str, dict],
    images_dir: Path,
) -> tuple[list[dict], dict[str, Any]]:
    """Re-valida las candidatas PENDING de la cola. Función PURA: no escribe
    archivos ni el ledger; devuelve (preview_nuevo, stats).

    stats incluye:
      - passed:              candidatas que pasaron el gate (match_dist poblado).
      - match_dist_hist:     Counter de match_dist de las que pasaron.
      - rejected_same_cover: rechazadas porque no son la MISMA portada.
      - rejected_soft:       rechazadas por imagen blanda (_is_soft_image).
      - no_ref:              sin referencia utilizable (old_image ausente/chica).
      - no_candidate:        el archivo de la candidata no está en disco.
      - moot:                sync las podaría → se dejan intactas para sync.
      - already_verified:    pending ya procesadas (tienen `verified`) → intactas.
      - decided:             candidatas approved/rejected → intactas.
    """
    stats: dict[str, Any] = {
        "passed": 0,
        "match_dist_hist": Counter(),
        "rejected_same_cover": 0,
        "rejected_soft": 0,
        "no_ref": 0,
        "no_candidate": 0,
        "moot": 0,
        "already_verified": 0,
        "decided": 0,
    }

    surviving = _surviving_candidate_keys(preview, items_by_slug, images_dir)

    result: list[dict] = []
    for entry in preview:
        slug = entry.get("slug", "")
        old_image = entry.get("old_image", "")
        # Referencia (portada congelada de la entry) — se lee una vez por entry.
        ref_px = _pixels_on_disk(old_image, images_dir)
        ref_bytes: bytes | None = None
        ref_usable = bool(old_image) and old_image != "[dry-run]" and ref_px >= REF_MIN_PIXELS
        if ref_usable:
            try:
                ref_bytes = (images_dir / old_image).read_bytes()
            except OSError:
                ref_usable = False
                ref_bytes = None

        new_entry = dict(entry)
        new_cands: list[dict] = []
        for cand in entry.get("candidates", []):
            status = cand.get("status", "pending")
            # Idempotencia / decisiones del owner: no se tocan.
            if status != "pending":
                stats["decided"] += 1
                new_cands.append(cand)
                continue
            # Pending ya procesada (por una corrida previa o por el skill nuevo,
            # que ya escribe `verified`) → no reprocesar (idempotencia).
            if "verified" in cand:
                stats["already_verified"] += 1
                new_cands.append(cand)
                continue
            # Moot: lo que sync podaría se deja intacto (sync lo limpia después).
            if _candidate_key(slug, cand) not in surviving:
                stats["moot"] += 1
                new_cands.append(cand)
                continue

            # Sin referencia utilizable → NO auto-rechazar; flag para humano.
            if not ref_usable or ref_bytes is None:
                stats["no_ref"] += 1
                new_cands.append({**cand, "verified": False})
                continue

            # Archivo de la candidata ausente → tampoco se puede validar/aplicar.
            new_local = cand.get("new_image", "")
            new_path = images_dir / new_local if new_local else None
            if not new_local or new_local == "[dry-run]" or new_path is None or not new_path.exists():
                stats["no_candidate"] += 1
                new_cands.append({**cand, "verified": False})
                continue

            try:
                cand_bytes = new_path.read_bytes()
            except OSError:
                stats["no_candidate"] += 1
                new_cands.append({**cand, "verified": False})
                continue

            # ── Gate REAL del motor (delegación pura) ──
            # Identidad primero (falla dominante), luego detalle (blandura).
            if not fbc._same_cover(ref_bytes, cand_bytes, fbc.DEFAULT_MAX_HASH_DIST):
                stats["rejected_same_cover"] += 1
                new_cands.append({
                    **cand,
                    "status": "rejected",
                    "reject_reason": REVALIDATION_REASON,
                })
                continue
            if fbc._is_soft_image(cand_bytes):
                stats["rejected_soft"] += 1
                new_cands.append({
                    **cand,
                    "status": "rejected",
                    "reject_reason": REVALIDATION_REASON,
                })
                continue

            # PASA: puebla match_dist (aHash Hamming, igual que sc_validate),
            # ref_pixels y verified; queda pending (lo decide el owner).
            h1 = fbc._ahash(ref_bytes)
            h2 = fbc._ahash(cand_bytes)
            match_dist = fbc._hamming(h1, h2) if (h1 is not None and h2 is not None) else None
            stats["passed"] += 1
            stats["match_dist_hist"][match_dist] += 1
            new_cands.append({
                **cand,
                "match_dist": match_dist,
                "ref_pixels": ref_px,
                "verified": True,
            })

        new_entry["candidates"] = new_cands
        result.append(new_entry)

    return result, stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_report(stats: dict[str, Any]) -> None:
    print()
    print("=== Re-validación de la cola de portadas ===")
    print(f"  Pasan (verificadas)        : {stats['passed']}")
    if stats["passed"]:
        hist = stats["match_dist_hist"]
        dist_str = ", ".join(
            f"{('null' if k is None else k)}→{v}"
            for k, v in sorted(hist.items(), key=lambda kv: (kv[0] is None, kv[0]))
        )
        print(f"    distribución match_dist  : {dist_str}")
    print(f"  Auto-rechazadas (no misma) : {stats['rejected_same_cover']}  [gate _same_cover]")
    print(f"  Auto-rechazadas (blanda)   : {stats['rejected_soft']}  [gate _is_soft_image]")
    print(f"  Sin referencia utilizable  : {stats['no_ref']}  (verified=false)")
    print(f"  Sin archivo de candidata   : {stats['no_candidate']}  (verified=false)")
    print(f"  Moot (las poda sync)       : {stats['moot']}")
    print(f"  Ya procesadas (verified)   : {stats['already_verified']}")
    print(f"  Decididas (approved/reject): {stats['decided']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-valida OFFLINE cover_preview.json contra el gate endurecido del motor."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True,
                       help="(default) reporta qué haría, sin escribir.")
    group.add_argument("--apply", action="store_true",
                       help="escribe los cambios en cover_preview.json (backup + atomic).")
    args = parser.parse_args(argv)
    apply = args.apply
    dry_run = not apply

    if not PREVIEW_PATH.exists():
        print("cover_preview.json no existe — nada que re-validar.")
        return 0

    preview: list[dict] = json.loads(PREVIEW_PATH.read_text(encoding="utf-8"))
    items_by_slug, malformed = _load_items_by_slug(ITEMS_PATH)
    print(f"Entries: {len(preview)} | items en catálogo: {len(items_by_slug)}"
          + (f" ({malformed} línea(s) corrupta(s) ignoradas)" if malformed else ""))

    new_preview, stats = revalidate_preview(preview, items_by_slug, IMAGES_DIR)
    _print_report(stats)

    changed = new_preview != preview
    if dry_run:
        print("\n[dry-run] No se escribió ningún archivo"
              f" ({'habría cambios' if changed else 'sin cambios'}).")
        return 0

    if not changed:
        print("\nCola ya re-validada — sin cambios.")
        return 0

    backup_and_rotate(PREVIEW_PATH, "revalidate-preview")
    _write_atomic(PREVIEW_PATH, new_preview)
    print(f"\n✓ cover_preview.json re-validado ({len(new_preview)} entries).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
