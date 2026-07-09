#!/usr/bin/env python3
"""fix_item_fields.py — mini-helper genérico para corregir campos puntuales
de UN item de `data/items.jsonl`, identificado por su `url` (o `slug`).

Reemplaza los snippets K/M embebidos del skill `/watch-review-feedback`
(auditoría Fable 2026-07-08, hallazgo F12) — antes esos snippets reescribían
`items.jsonl` a mano (tmp + replace inline) SIN `backup_and_rotate` ni guard
`approved_at`, y el snippet M incluía la línea

    row["title"] = "<correct_standardized_title>"

que contradice la política de títulos (gotcha #92, 2026-06-12): el `title` es
el nombre OFICIAL con que la editorial publica el producto — NUNCA se
traduce/renombra/decora a mano. Este script bloquea `title` por default y
sólo lo permite con `--allow-title` explícito (imprimiendo el warning de la
política en cada uso, para que quede constancia en el log del skill).

Qué hace:
  - Allowlist de campos editables (`ALLOWED_FIELDS`) — cualquier otro campo
    (y `title` sin `--allow-title`) aborta con exit 2 antes de tocar nada.
  - Guard `approved_at` (golden records, patrón homogéneo de
    docs/reference/conventions.md): salta el item salvo `--include-approved`.
  - `backup_and_rotate(items_path, "fix-item-fields")` antes de escribir.
  - Escritura atómica (tmp + os.replace), nunca `open(path, 'w')` directo
    sobre el archivo real (gotcha #133).
  - Re-deriva `cluster_key` con `manga_watch.derive_cluster_key(item)` si el
    `--set` tocó alguno de sus insumos (`edition_key`, `volume`, `country`,
    `publisher`, `title`, `url` — gotcha #55: "cluster_key stale es la raíz
    de la auditoría que siempre encuentra algo").
  - Validación liviana de los enums conocidos (`rarity`, `product_type`) para
    no dejar pasar un typo silencioso.
  - `--set cover_url=<url>` es un campo SINTÉTICO (categoría K, wrong_image):
    delega en `image_store.set_cover(item, url, local="")` — la MISMA función
    del resto del pipeline, con `local=""` para forzar el re-download de
    `mirror_images.py` — en vez de tocar `images[0]` a mano.

Uso:
    fix_item_fields.py --url "https://..." --set series_key=berserk --set series_display=Berserk
    fix_item_fields.py --url "https://..." --set edition_key=berserk-darkhorse-deluxe --dry-run
    fix_item_fields.py --url "https://..." --set cover_url=https://cdn.example.com/hires.jpg
    fix_item_fields.py --slug berserk-darkhorse-deluxe-1 --set volume=1
    fix_item_fields.py --url "https://..." --set title="Nuevo título" --allow-title
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# El wrapper manga_watch.py de la RAÍZ puede estar ya cacheado en sys.modules
# bajo pytest (no expone estos símbolos) → fallback al módulo real (mismo
# patrón que fetch_better_covers.py / backfill_series_aliases.py).
try:
    from manga_watch import backup_and_rotate, derive_cluster_key, is_approved  # type: ignore
except ImportError:  # pragma: no cover
    from scripts.manga_watch import backup_and_rotate, derive_cluster_key, is_approved  # type: ignore

try:
    from standardize_apply import VALID_PRODUCT_TYPES  # type: ignore
except ImportError:  # pragma: no cover — el enum es opcional para validar
    try:
        from scripts.standardize_apply import VALID_PRODUCT_TYPES  # type: ignore
    except ImportError:
        VALID_PRODUCT_TYPES = None  # type: ignore

import image_store  # type: ignore

# Campos editables — deliberadamente NO incluye 'title' (bloqueado salvo
# --allow-title) ni campos derivados/estructurales que otros scripts ya
# gestionan (cluster_key se re-deriva acá mismo, slug via generate_slugs.py,
# approved_at/approved_by via el dashboard).
ALLOWED_FIELDS = frozenset({
    "series_key", "series_display",
    "edition_key", "edition_display",
    "volume", "product_type", "rarity",
    "country", "publisher", "language", "isbn",
    "stock_status", "description",
})

# 'cover_url' es un campo SINTÉTICO (no vive como tal en el item — la portada
# es images[0], única fuente de verdad). --set cover_url=<url> reemplaza la
# categoría K (wrong_image) del skill /watch-review-feedback: delega en
# image_store.set_cover(item, url, local="") — la MISMA función que usa el
# resto del pipeline — con local="" para forzar el re-download de
# mirror_images.py. No participa de _CLUSTER_KEY_INSUMOS (la imagen no afecta
# cluster_key).
_SYNTHETIC_FIELDS = frozenset({"cover_url"})

# Insumos de derive_cluster_key() (ver su docstring): si el --set tocó
# cualquiera de estos, el cluster_key queda stale y hay que re-derivarlo.
_CLUSTER_KEY_INSUMOS = frozenset({"edition_key", "volume", "country", "publisher", "title", "url"})

RARITY_TIERS = frozenset({"common", "rare", "super_rare", "ultra_rare"})

_TITLE_POLICY_WARNING = (
    "ADVERTENCIA: estás editando 'title' con --allow-title. La política de "
    "títulos (gotcha #92, 2026-06-12) dice que el title es el nombre OFICIAL "
    "con que la editorial publica el producto — NUNCA se traduce, NUNCA se "
    "renombra a la serie canónica, NUNCA se le inyecta el tipo de edición. "
    "Si estás 'corrigiendo' un title porque no coincide con la serie/edición "
    "esperada, lo correcto es editar series_key/series_display/edition_key, "
    "NO el title. Usá --allow-title solo para basura real de scraping "
    "(prefijo de botón, truncado) — para eso preferí clean_titles.py."
)


def _default_items_path() -> Path:
    import os

    data_dir = os.environ.get("MANGA_WATCH_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "items.jsonl"
    return _SCRIPTS.parent / "data" / "items.jsonl"


def parse_sets(raw: list[str]) -> dict[str, str]:
    """Parsea ['field=value', ...] a {'field': 'value'}. Aborta si el
    formato es inválido o el campo no es editable."""
    out: dict[str, str] = {}
    for spec in raw:
        if "=" not in spec:
            print(f"[ERROR] --set {spec!r} inválido — formato esperado field=value",
                  file=sys.stderr)
            raise SystemExit(2)
        field, _, value = spec.partition("=")
        field = field.strip()
        out[field] = value
    return out


def validate_fields(sets: dict[str, str], *, allow_title: bool) -> None:
    for field in sets:
        if field == "title":
            if not allow_title:
                print(
                    "[ABORTA] --set title=... requiere --allow-title explícito. "
                    "Ver la política de títulos (gotcha #92) — el title es el "
                    "nombre OFICIAL, no se renombra a mano salvo basura real de "
                    "scraping.",
                    file=sys.stderr,
                )
                raise SystemExit(2)
            print(f"[WARN] {_TITLE_POLICY_WARNING}", file=sys.stderr)
            continue
        if field in _SYNTHETIC_FIELDS:
            continue
        if field not in ALLOWED_FIELDS:
            print(
                f"[ABORTA] campo {field!r} no está en la allowlist editable. "
                f"Campos permitidos: {', '.join(sorted(ALLOWED_FIELDS | _SYNTHETIC_FIELDS))} "
                f"(o 'title' con --allow-title).",
                file=sys.stderr,
            )
            raise SystemExit(2)

    if "rarity" in sets and sets["rarity"] not in RARITY_TIERS:
        print(
            f"[ABORTA] rarity={sets['rarity']!r} no es un tier válido "
            f"({', '.join(sorted(RARITY_TIERS))}).",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if "product_type" in sets and VALID_PRODUCT_TYPES is not None \
            and sets["product_type"] not in VALID_PRODUCT_TYPES:
        print(
            f"[ABORTA] product_type={sets['product_type']!r} no está en "
            f"VALID_PRODUCT_TYPES ({', '.join(sorted(VALID_PRODUCT_TYPES))}).",
            file=sys.stderr,
        )
        raise SystemExit(2)


def find_item(items: list[dict[str, Any]], *, url: str, slug: str) -> dict[str, Any] | None:
    for it in items:
        if url and it.get("url") == url:
            return it
        if slug and not url and it.get("slug") == slug:
            return it
    return None


def apply_fix(
    item: dict[str, Any], sets: dict[str, str],
) -> tuple[dict[str, tuple[Any, Any]], bool]:
    """Aplica los sets in-place. Devuelve ({field: (old, new)}, cluster_key_stale)."""
    changed: dict[str, tuple[Any, Any]] = {}
    for field, value in sets.items():
        if field == "cover_url":
            old = image_store.cover_url(item)
            if old == value:
                continue
            # local="" fuerza el re-download de mirror_images.py — misma
            # función que usa el resto del pipeline (fuente única).
            image_store.set_cover(item, value, "")
            changed[field] = (old, value)
            continue
        old = item.get(field)
        if old == value:
            continue
        item[field] = value
        changed[field] = (old, value)
    cluster_key_stale = bool(set(changed) & _CLUSTER_KEY_INSUMOS)
    return changed, cluster_key_stale


def run(
    items_path: Path,
    *,
    url: str,
    slug: str,
    sets: dict[str, str],
    include_approved: bool,
    dry_run: bool,
) -> int:
    if not items_path.exists():
        print(f"[ERROR] no existe {items_path}", file=sys.stderr)
        return 1

    items = [json.loads(l) for l in items_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    item = find_item(items, url=url, slug=slug)
    if item is None:
        print(f"[ERROR] no encontré item con url={url!r} slug={slug!r}", file=sys.stderr)
        return 1

    if is_approved(item) and not include_approved:
        print(
            f"[SKIP] item aprobado (approved_at={item.get('approved_at')}) — "
            f"golden record, no se edita salvo --include-approved. "
            f"slug={item.get('slug')!r}",
            file=sys.stderr,
        )
        return 0

    changed, cluster_key_stale = apply_fix(item, sets)
    if not changed:
        print("[OK] Sin cambios — los valores pedidos ya eran los actuales.")
        return 0

    for field, (old, new) in changed.items():
        print(f"  {field}: {old!r} → {new!r}")

    old_cluster_key = item.get("cluster_key", "")
    new_cluster_key = old_cluster_key
    if cluster_key_stale:
        new_cluster_key = derive_cluster_key(item)
        if new_cluster_key != old_cluster_key:
            print(f"  cluster_key: {old_cluster_key!r} → {new_cluster_key!r} (re-derivado)")

    if dry_run:
        print(f"[DRY-RUN] {len(changed)} campo(s) cambiarían. No se escribió nada.")
        return 0

    if cluster_key_stale:
        item["cluster_key"] = new_cluster_key

    if "cover_url" in changed:
        print("[INFO] cover_url cambió — corré mirror_images.py --no-gc para "
              "descargar la nueva portada.")

    backup = backup_and_rotate(items_path, "fix-item-fields")
    print(f"[OK] Backup: {backup}")
    tmp = items_path.with_suffix(items_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(items_path)
    print(f"[OK] Escrito {items_path} — slug={item.get('slug')!r}, {len(changed)} campo(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=None,
                    help="items.jsonl a leer/escribir (default: data/items.jsonl / "
                         "MANGA_WATCH_DATA_DIR).")
    ap.add_argument("--url", default="", help="URL exacta del item a editar.")
    ap.add_argument("--slug", default="", help="slug exacto del item a editar "
                                                "(alternativa a --url).")
    ap.add_argument("--set", dest="sets", action="append", default=[],
                    metavar="field=value",
                    help="Campo a setear, formato field=value. Repetible.")
    ap.add_argument("--allow-title", action="store_true",
                    help="Permite --set title=... (bloqueado por default, "
                         "política de títulos gotcha #92).")
    ap.add_argument("--include-approved", action="store_true",
                    help="También edita items aprobados (golden records). Por "
                         "defecto se saltean.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Muestra qué cambiaría sin escribir.")
    args = ap.parse_args(argv)

    if not args.url and not args.slug:
        print("[ABORTA] Falta --url o --slug para identificar el item.", file=sys.stderr)
        return 2
    if not args.sets:
        print("[ABORTA] Falta al menos un --set field=value.", file=sys.stderr)
        return 2

    try:
        sets = parse_sets(args.sets)
        validate_fields(sets, allow_title=args.allow_title)
    except SystemExit as exc:
        # parse_sets/validate_fields usan SystemExit para abortar temprano
        # (también invocables directo por tests) — acá se traduce a return
        # code para que main() sea llamable in-process sin tirar la excepción.
        return exc.code if isinstance(exc.code, int) else 2

    items_path = args.input if args.input is not None else _default_items_path()
    return run(
        items_path,
        url=args.url,
        slug=args.slug,
        sets=sets,
        include_approved=args.include_approved,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
