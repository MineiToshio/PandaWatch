#!/usr/bin/env python3
"""expand_whakoom_ediciones.py — convierte items con URL /ediciones/ a N tomos.

Una URL Whakoom `/ediciones/<id>/<slug>` representa una colección entera
(p.ej. "Berserk Deluxe Edition" = 14 tomos), no un volumen individual.
Nuestro catálogo es por tomo, así que tener una sola fila por edición
es un bug: pierde el detalle por volumen y rompe la agrupación por
`cluster_key`.

Este retrofit recorre items.jsonl, identifica filas con URL `/ediciones/`,
fetchea cada una via `expand_whakoom_edition`, y reemplaza la fila padre
por N hijos (uno por `/comics/<X>/<slug>/<vol>`). Aplica los mismos
filtros que la ingestión normal (is_likely_manga + is_collectible_edition).

Uso:
    python scripts/retrofit/expand_whakoom_ediciones.py --dry-run
    python scripts/retrofit/expand_whakoom_ediciones.py            # aplica

Flags útiles:
    --sleep 2.0            (entre requests; default 1.5)
    --max 50               (cap de ediciones a procesar; útil para tests)
    --ignore-throttle      (saltea el throttle del spider — no aplica aquí
                           porque no usamos _check_throttle; flag por
                           consistencia con whakoom.py)

Si Cloudflare devuelve challenge a media corrida, el script aborta
limpiamente sin escribir cambios parciales: la IP está en cuarentena y
no tiene sentido seguir presionando.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import (  # type: ignore
    backup_and_rotate,
    candidate_to_json,
    derive_cluster_key,
    is_approved,
    is_collectible_edition,
    is_likely_manga,
    normalize_url_for_dedup,
    score_candidate,
)
from wikis.whakoom import (  # type: ignore
    WhakoomBlocked,
    _ua_session,
    expand_whakoom_edition,
    is_whakoom_edition_url,
)


def _load_items(path: Path) -> list[dict]:
    items: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            # Mantener líneas no-JSON intactas: las preservaremos al
            # escribir de vuelta para no perder data en caso de bug.
            items.append({"_raw": line})
    return items


def _write_items(path: Path, items: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for it in items:
            if "_raw" in it:
                fh.write(it["_raw"] + "\n")
            else:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="data/items.jsonl")
    ap.add_argument("--output", default="data/items.jsonl")
    ap.add_argument("--dry-run", action="store_true",
                    help="Reporta qué pasaría sin escribir items.jsonl")
    ap.add_argument("--sleep", type=float, default=1.5,
                    help="Segundos entre HTTP requests (default 1.5)")
    ap.add_argument("--max", type=int, default=0,
                    help="Máximo de ediciones a procesar (0 = sin límite)")
    ap.add_argument("--timeout-connect", type=int, default=10)
    ap.add_argument("--timeout-read", type=int, default=30)
    args = ap.parse_args()

    # Ingesta real (descubre items/series nuevas): habilitar el logging de la
    # cola de unmapped, salvo en dry-run (Fable 2026-07-08, punto 5 — el efecto
    # está apagado por default en series_aliases).
    try:
        from series_aliases import set_unmapped_logging
        set_unmapped_logging(not args.dry_run)
    except ImportError:
        pass

    src = Path(args.input)
    out = Path(args.output)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    items = _load_items(src)
    print(f"[INFO] {len(items)} filas leídas de {src}")

    # Identificar filas con URL /ediciones/ de Whakoom.
    edition_indices: list[int] = []
    skipped_approved = 0
    for idx, it in enumerate(items):
        if "_raw" in it:
            continue
        # Golden records aprobados: NUNCA expandir (se borraría el parent al
        # reemplazarlo por sus hijos).
        if is_approved(it):
            skipped_approved += 1
            continue
        if is_whakoom_edition_url(it.get("url", "")):
            edition_indices.append(idx)
    if skipped_approved:
        print(f"[INFO] {skipped_approved} items aprobados saltados (no se tocan)")
    print(f"[INFO] {len(edition_indices)} filas con URL /ediciones/ de Whakoom")
    if not edition_indices:
        print("[OK] Nada que expandir.")
        return 0

    if args.max > 0 and len(edition_indices) > args.max:
        print(f"[INFO] limitando a {args.max} ediciones (de {len(edition_indices)})")
        edition_indices = edition_indices[: args.max]

    # URLs ya conocidas (para no duplicar candidates expandidos contra
    # items.jsonl existente).
    known_urls: set[str] = set()
    for it in items:
        if "_raw" in it:
            continue
        url = it.get("url", "")
        if url:
            known_urls.add(normalize_url_for_dedup(url))

    session = _ua_session(requests.Session())
    timeout = (args.timeout_connect, args.timeout_read)
    timeout_t = (timeout[0], timeout[1])

    to_remove: set[int] = set()
    new_rows: list[dict] = []
    stats = {
        "expanded": 0,
        "no_volumes": 0,
        "blocked": 0,
        "filtered_non_manga": 0,
        "filtered_non_collectible": 0,
        "duplicates": 0,
        "kept_total": 0,
    }
    aborted = False
    for n, idx in enumerate(edition_indices, start=1):
        parent = items[idx]
        ed_url = parent.get("url", "")
        title_preview = parent.get("title", "")[:50]
        print(f"\n[{n}/{len(edition_indices)}] {ed_url}")
        print(f"   parent: {title_preview!r}")
        try:
            expanded = expand_whakoom_edition(
                ed_url, session,
                timeout=timeout_t,
                sleep_seconds=args.sleep,
            )
        except WhakoomBlocked as exc:
            print(f"   [BLOCKED] {exc}")
            print(f"   Cloudflare en cuarentena — abortando sin escribir cambios.")
            stats["blocked"] += 1
            aborted = True
            break

        if not expanded:
            print(f"   [WARN] expansión devolvió 0 candidates — dejamos la fila padre intacta")
            stats["no_volumes"] += 1
            continue

        # Aplicar filtros equivalentes a la ingestión normal.
        kept_this_edition: list[dict] = []
        for cand in expanded:
            is_m, _ = is_likely_manga(
                cand.title, cand.description, tags=cand.tags,
                source_purity="mixed", publisher=cand.publisher,
                url=cand.url,
            )
            if not is_m:
                stats["filtered_non_manga"] += 1
                continue
            score_candidate(cand)
            is_c, _ = is_collectible_edition(
                cand.title, cand.description, cand.signal_types, cand.product_type,
                tags=cand.tags, isbn=cand.isbn, url=cand.url,
            )
            if not is_c:
                stats["filtered_non_collectible"] += 1
                continue
            norm = normalize_url_for_dedup(cand.url)
            if norm in known_urls:
                stats["duplicates"] += 1
                continue
            row = candidate_to_json(cand)
            # cluster_key ya viene calculado por candidate_to_json.
            known_urls.add(norm)
            kept_this_edition.append(row)

        print(f"   → {len(expanded)} tomos expandidos, {len(kept_this_edition)} sobreviven filtros")
        # La fila padre se elimina cuando la expansión funcionó (volúmenes > 0),
        # aunque los hijos resulten todos duplicados con items.jsonl. Esto
        # cubre el caso de ediciones que vimos por subdominios distintos
        # (en.whakoom.com vs www.whakoom.com) — el primero genera los /comics/,
        # el segundo solo aporta la fila padre redundante.
        if expanded:
            stats["expanded"] += 1
            stats["kept_total"] += len(kept_this_edition)
            to_remove.add(idx)
            new_rows.extend(kept_this_edition)
        else:
            # Si la expansión devolvió 0 volúmenes ni siquiera como one-shot,
            # algo raro pasa: preservamos el padre para revisión manual.
            print(f"   [WARN] expansión vacía — preservando fila padre")

        # Throttle entre ediciones (además del que mete expand_whakoom_edition
        # entre la página principal y /todos).
        if args.sleep > 0 and n < len(edition_indices):
            time.sleep(args.sleep)

    print(f"\n{'=' * 60}")
    print(f"[STATS] ediciones expandidas: {stats['expanded']}")
    print(f"[STATS] tomos nuevos a agregar: {stats['kept_total']}")
    print(f"[STATS] filas padre a eliminar: {len(to_remove)}")
    print(f"[STATS] expansiones vacías: {stats['no_volumes']}")
    print(f"[STATS] tomos filtrados (no manga): {stats['filtered_non_manga']}")
    print(f"[STATS] tomos filtrados (no coleccionable): {stats['filtered_non_collectible']}")
    print(f"[STATS] duplicados con items.jsonl: {stats['duplicates']}")
    if aborted:
        print(f"[STATS] ABORTADO por Cloudflare challenge")

    if args.dry_run or aborted:
        if aborted:
            print(f"\n[ABORT] No se escribió {out} (corrida abortada).")
        else:
            print(f"\n[DRY-RUN] No se escribió {out}. Quitá --dry-run para aplicar.")
        return 0

    # Backup antes de sobrescribir (este script ELIMINA filas padre).
    if out.exists():
        backup_and_rotate(out, "expand-whakoom")
    # Build new items list: drop parents marked for removal, append new rows.
    final_items = [it for i, it in enumerate(items) if i not in to_remove]
    final_items.extend(new_rows)
    _write_items(out, final_items)
    print(f"\n[OK] {out} actualizado:")
    print(f"     filas antes: {len(items)}")
    print(f"     filas después: {len(final_items)}")
    print(f"     delta: {len(final_items) - len(items):+d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
