#!/usr/bin/env python3
"""purge_false_artbook_residuals.py — desblinda residuos del bug de "category"
inyectada (GRUPO 2 de la auditoría post-scrape, 2026-07-07).

Contexto (causa raíz verificada). El módulo legacy del calendario
(`scripts/wikis/listadomanga.py`, pre-2026-05-23) inyectaba la `category` del
día ("Artbook", "Cofre"...) directamente en la `description` de CADA item
cercano en el HTML — aunque la `<u>` perteneciera a otro contexto (autor,
sección adyacente, item vecino). `detect_signals` la interpretaba como señal
premium real y marcaba tomos REGULARES como `product_type="artbook"` /
`signal_types=["artbook"]`. Casos reales detectados 2026-05-19: Chainsaw Man
1, Black Butler 27, Fire Force 9, Tokyo Ghoul:re 14. El bug upstream ya está
arreglado (`_extract_items_from_table` en `listadomanga.py` ya NO inyecta la
categoría en la description — ver el comentario ahí), pero los residuos que
ya habían entrado al corpus ANTES del fix quedaron BLINDADOS por
`standardized_at` (gotcha #61: `filter_collectible`/`rescore` saltean items
estandarizados, así que la mala clasificación nunca se corrige sola).

Blast radius (acotado a propósito, NO todo item artbook/boxset):
  - `product_type` ∈ {artbook, boxset}
  - `standardized_at` truthy (si no, ya lo agarran los filtros normales)
  - `edition_key` contiene `-regular-` O `edition_display == "Regular"` — el
    tomo YA fue clasificado como regular por la estandarización; el
    product_type=artbook es contradictorio con esa propia clasificación.
  - `signal_types == ["artbook"]` EXACTAMENTE — un item con más señales
    (ej. `["artbook", "bonus"]`) puede tener evidencia real adicional; fuera
    de alcance acá.
  - El título NO contiene ninguna keyword real de artbook (illustrations,
    art book, artbook, ilustraciones, libro de ilustraciones, sketchbook,
    fanbook, guidebook, databook) — un artbook legítimo SÍ lo dice en su
    título/nombre oficial.

Acción: NO reclasifica (regla del owner: la expulsión la hace el mecanismo, no
el retrofit puntual). Hace DOS cosas mínimas y deterministas sobre cada
candidato:
  1. Remueve `standardized_at` → desblinda (gotcha #61).
  2. Limpia el RESIDUO del bug de la `description`: quita el token de categoría
     inyectado (` · {category} · `, justo entre publisher y título) que el
     parser legacy había metido. Sin esto, `rescore` VUELVE a leer "Artbook" en
     la description y re-deriva la misma señal falsa (la description NO estaba
     "ya limpia por la estandarización" como se asumió originalmente — el texto
     crudo del calendario, con la categoría inyectada, sobrevivió a la
     estandarización). La categoría a quitar es el valor del tag
     `category:<X>`; se remueve determinísticamente por posición (el 2º segmento
     al hacer split por " · "), nunca por substring ciego.
Con la description ya limpia, la próxima corrida del pipeline canónico
(`rescore.py` re-deriva `signal_types` desde título+description SIN la palabra
de artbook → la señal se cae; luego `filter_collectible.py` los rechaza como
`regular_tomo`) los expulsa del catálogo de forma determinista.

Idempotente (un item sin `standardized_at` ya no matchea el gate `standardized_at
truthy`). Guard `approved_at` (golden records) + `--include-approved`. Backup
vía `backup_and_rotate` antes de escribir. Escritura atómica (tmp + rename).

Uso:
  .venv/bin/python scripts/retrofit/purge_false_artbook_residuals.py --dry-run
  .venv/bin/python scripts/retrofit/purge_false_artbook_residuals.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import backup_and_rotate, is_approved  # type: ignore

ITEMS = _SCRIPTS.parent / "data" / "items.jsonl"

# Keywords que SÍ indican un artbook legítimo en el título/nombre oficial.
ARTBOOK_KEYWORDS = (
    "illustrations", "art book", "artbook", "ilustraciones",
    "libro de ilustraciones", "sketchbook", "fanbook", "guidebook", "databook",
)

_FALSE_PRODUCT_TYPES = {"artbook", "boxset"}


def _looks_like_regular(item: dict) -> bool:
    ek = item.get("edition_key") or ""
    ed = item.get("edition_display") or ""
    return "-regular-" in ek or ed == "Regular"


def _has_real_artbook_keyword(title: str) -> bool:
    t = (title or "").lower()
    return any(kw in t for kw in ARTBOOK_KEYWORDS)


def _injected_category(item: dict) -> str:
    """Valor de la categoría inyectada por el parser legacy (tag `category:<X>`)."""
    for tag in item.get("tags") or []:
        if isinstance(tag, str) and tag.startswith("category:"):
            return tag.split(":", 1)[1].strip()
    return ""


def strip_injected_category(item: dict) -> str | None:
    """Devuelve la description SIN el token de categoría inyectado, o None si no
    hay nada que limpiar.

    El parser legacy inyectaba la categoría como 2º segmento de la description
    (`{publisher} · {category} · {título}...`). Se remueve por POSICIÓN — el 2º
    elemento tras split por ' · ' — sólo si coincide exactamente con el valor
    del tag `category:<X>`. Determinista; no toca ocurrencias del mismo texto en
    otra posición (p.ej. dentro del título).
    """
    category = _injected_category(item)
    if not category:
        return None
    description = item.get("description") or ""
    parts = description.split(" · ")
    if len(parts) >= 2 and parts[1].strip() == category:
        del parts[1]
        return " · ".join(parts)
    return None


def is_false_artbook_residual(item: dict) -> bool:
    """True si el item matchea el blast radius del GRUPO 2 (ver docstring)."""
    if item.get("product_type") not in _FALSE_PRODUCT_TYPES:
        return False
    if not item.get("standardized_at"):
        return False
    if not _looks_like_regular(item):
        return False
    if list(item.get("signal_types") or []) != ["artbook"]:
        return False
    if _has_real_artbook_keyword(item.get("title") or ""):
        return False
    return True


def find_candidates(items: list[dict], *, include_approved: bool) -> tuple[list[dict], int]:
    """Devuelve (candidatos, aprobados_saltados)."""
    candidates: list[dict] = []
    skipped_approved = 0
    for item in items:
        if not is_false_artbook_residual(item):
            continue
        if is_approved(item) and not include_approved:
            skipped_approved += 1
            continue
        candidates.append(item)
    return candidates, skipped_approved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(ITEMS))
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe nada, sólo reporta (default: escribe).")
    parser.add_argument("--include-approved", action="store_true",
                        help="Desblindar también items aprobados (golden records). "
                             "Por defecto se saltean.")
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    items: list[dict] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    candidates, skipped_approved = find_candidates(items, include_approved=args.include_approved)

    print(f"[INFO] {len(items)} items totales, {len(candidates)} residuos de "
          f"artbook/boxset falso (product_type∈{{artbook,boxset}} + standardized_at + "
          f"pinta de regular + signal_types==['artbook'] + sin keyword real).")
    if skipped_approved:
        print(f"[INFO] {skipped_approved} aprobados saltados (usa --include-approved para incluirlos)")

    if not candidates:
        print("[OK] Nada para desblindar.")
        return 0

    sample = candidates[:10]
    print("\nMuestra de candidatos:")
    for it in sample:
        print(f"  {it.get('slug') or it.get('url', '')[:60]}: title={it.get('title')!r} "
              f"product_type={it.get('product_type')!r} signal_types={it.get('signal_types')!r}")
    if len(candidates) > 10:
        print(f"  ... y {len(candidates) - 10} más")

    if args.dry_run:
        print("\n[DRY-RUN] No se escribió nada.")
        return 0

    backup_and_rotate(src, "purge-false-artbook-residuals")

    ids = {id(it) for it in candidates}
    cleaned_desc = 0
    out: list[dict] = []
    for it in items:
        if id(it) in ids:
            it = dict(it)
            it.pop("standardized_at", None)
            new_desc = strip_injected_category(it)
            if new_desc is not None:
                it["description"] = new_desc
                cleaned_desc += 1
        out.append(it)

    tmp = src.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for it in out:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(src)

    print(f"\n[OK] Desblindados {len(candidates)} items (standardized_at removido; "
          f"{cleaned_desc} con categoría inyectada limpiada de la description) en {src}. "
          f"Correr rescore.py + filter_collectible.py después para completar la expulsión.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
