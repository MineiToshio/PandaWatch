#!/usr/bin/env python3
"""wayback_recover.py — recupera metadata de items 404 vía Wayback Machine.

Caso de uso típico: una edición especial existió en el sitio del retailer
(ej. starcomics.com/fumetto/one-piece-100-celebration-edition) pero la
descatalogaron y ahora da 404. Wayback Machine tiene un snapshot del HTML
original. Este script:

1. Identifica items con URLs que actualmente dan 404 (o status no-200).
2. Para cada URL, consulta Wayback Machine Availability API.
3. Si hay snapshot, descarga el HTML cacheado de archive.org.
4. Extrae metadata (OG title, image, description) del snapshot.
5. Actualiza el item en items.jsonl con la metadata recuperada + marca
   `recovered_from_wayback: true` y `wayback_snapshot_url`.

Modos:
- --check: solo identifica URLs 404 (no consulta Wayback).
- --dry-run: identifica + consulta Wayback, no escribe.
- (default): full run, escribe items.jsonl con backup.

Uso:
    python scripts/retrofit/wayback_recover.py --check
    python scripts/retrofit/wayback_recover.py --dry-run --limit 10
    python scripts/retrofit/wayback_recover.py
    python scripts/retrofit/wayback_recover.py --urls url1,url2  # recovery puntual
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

try:
    from scripts.manga_watch import (  # type: ignore
        backup_and_rotate,
        fetch_metadata_from_detail,
        is_approved,
        make_session,
        write_lines_atomic,
    )
    from scripts import image_store  # type: ignore
except ImportError:
    from manga_watch import (  # type: ignore
        backup_and_rotate,
        fetch_metadata_from_detail,
        is_approved,
        make_session,
        write_lines_atomic,
    )
    import image_store  # type: ignore


# Caché negativa persistente (hallazgo #13, auditoría 2026-07-08): sin esto,
# cada corrida re-consulta Wayback para TODO el corpus de items 404 (~70 min),
# incluidos los miles que ya sabemos que no tienen snapshot. TTL 90 días: un
# sitio puede llegar a tener snapshot nuevo con el tiempo, así que no es
# indefinido.
DEFAULT_NEGATIVE_CACHE = Path("data/wayback_negative_cache.json")
NEGATIVE_CACHE_TTL_DAYS = 90


WAYBACK_API = "http://archive.org/wayback/available"


def check_url_status(url: str, session: requests.Session, timeout: int = 10) -> int:
    """Devuelve HTTP status code (0 si conexión falla)."""
    try:
        # HEAD primero (más liviano); si no soporta, GET.
        r = session.head(url, allow_redirects=True, timeout=timeout)
        if r.status_code == 405:  # Method not allowed
            r = session.get(url, allow_redirects=True, timeout=timeout, stream=True)
            r.close()
        return r.status_code
    except requests.RequestException:
        return 0


def find_wayback_snapshot(
    url: str, session: requests.Session, timeout: int = 15,
) -> tuple[dict | None, bool]:
    """Consulta Wayback Availability API.

    Response format:
      {"available": True, "url": "http://web.archive.org/web/.../<orig>",
       "timestamp": "20230501123456", "status": "200"}

    Devuelve (snapshot, definitive):
      - `snapshot`: dict del closest si hay uno disponible, None si no.
      - `definitive`: True cuando la API RESPONDIÓ (200 + JSON válido) y
        confirmó que no hay snapshot — recién ahí es seguro cachear como
        negativo. False ante timeout/error de red/status≠200/JSON roto: un
        429 o un timeout NO significa "no hay snapshot", así que nunca se
        cachea (hallazgo #13, auditoría 2026-07-08 — antes ambos casos eran
        indistinguibles, un rate-limit se leía igual que "sin snapshot").
    """
    try:
        r = session.get(
            WAYBACK_API, params={"url": url}, timeout=timeout,
        )
    except requests.RequestException:
        return None, False
    if r.status_code != 200:
        return None, False
    try:
        data = r.json()
    except (ValueError, KeyError):
        return None, False
    snapshots = data.get("archived_snapshots") or {}
    closest = snapshots.get("closest")
    if not closest or not closest.get("available"):
        return None, True
    return closest, True


def load_negative_cache(path: Path) -> dict[str, str]:
    """Carga la caché negativa `{url: checked_at_iso}`. Tolerante a archivo
    ausente/corrupto (devuelve {} en vez de romper el run)."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_negative_cache(path: Path, cache: dict[str, str]) -> None:
    """Escritura atómica (tmp + fsync + os.replace) — mismo patrón que
    `_flush_wayback`, no es un archivo de items pero igual queremos que un
    crash a mitad de escritura no lo deje truncado."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    content = json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True)
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def negative_cache_is_fresh(checked_at: str, ttl_days: int = NEGATIVE_CACHE_TTL_DAYS) -> bool:
    """True si `checked_at` (ISO) está dentro del TTL — no hace falta re-chequear."""
    if not checked_at:
        return False
    try:
        checked = dt.datetime.fromisoformat(checked_at)
    except ValueError:
        return False
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=dt.timezone.utc)
    now = dt.datetime.now(dt.timezone.utc)
    return (now - checked).days < ttl_days


def recover_from_snapshot(
    snapshot: dict, item: dict, session: requests.Session, timeout: tuple[int, int],
) -> dict:
    """Hace GET al snapshot URL y extrae metadata.

    Devuelve dict con campos actualizados; vacío si no se pudo enriquecer.
    """
    snap_url = snapshot.get("url", "")
    if not snap_url:
        return {}
    # Wayback URLs tienen formato /web/<timestamp>/<original-url>.
    # Usamos /web/<timestamp>if_/<original-url> para obtener el HTML "raw"
    # (sin las inyecciones del banner de Wayback Machine). El sufijo `if_`
    # significa "iframe", limpio sin chrome.
    m = re.match(r"^(https?://web\.archive\.org/web/\d+)/(.+)$", snap_url)
    if m:
        prefix, original = m.group(1), m.group(2)
        clean_url = f"{prefix}if_/{original}"
    else:
        clean_url = snap_url

    md = fetch_metadata_from_detail(clean_url, session, timeout=timeout)
    if not md.get("name") and not md.get("image_url"):
        # Wayback no devolvió nada útil
        return {}

    # fetch_metadata_from_detail devuelve metadata GENÉRICA con la key `name`
    # para el nombre del producto, pero el schema de items.jsonl usa `title`
    # (nunca `name` — hallazgo #6, auditoría 2026-07-08: escribir `name`
    # tal cual metía un campo espurio que el resto del pipeline ignora).
    _MD_TO_ITEM_FIELD = {
        "name": "title",
        "author": "author",
        "isbn": "isbn",
        "release_date": "release_date",
        "publisher": "publisher",
        "description": "description",
    }
    recovered: dict = {}
    for md_field, item_field in _MD_TO_ITEM_FIELD.items():
        if md.get(md_field) and not item.get(item_field):
            recovered[item_field] = md[md_field]
    # Portada = images[0]: si el item no tiene portada, sembrarla desde wayback
    # (no como campo top-level, que ya no existe).
    if md.get("image_url") and not image_store.cover_url(item):
        tmp = {"images": [dict(im) for im in (item.get("images") or [])]}
        image_store.set_cover(tmp, md["image_url"])
        recovered["images"] = tmp["images"]
    if recovered:
        recovered["recovered_from_wayback"] = True
        recovered["wayback_snapshot_url"] = snap_url
        recovered["wayback_timestamp"] = snapshot.get("timestamp", "")
    return recovered


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", default="data/items.jsonl")
    p.add_argument("--output", default="data/items.jsonl")
    p.add_argument("--check", action="store_true",
                   help="Solo identifica URLs 404, no consulta Wayback.")
    p.add_argument("--dry-run", action="store_true",
                   help="Consulta Wayback pero NO escribe items.jsonl.")
    p.add_argument("--limit", type=int, default=0,
                   help="Procesar solo primeros N items 404 (default: todos).")
    p.add_argument("--sleep", type=float, default=1.0,
                   help="Segundos entre requests a Wayback (default: 1.0).")
    p.add_argument("--urls", default="",
                   help="Lista de URLs separadas por coma para recovery puntual.")
    p.add_argument("--check-timeout", type=int, default=8)
    p.add_argument("--fetch-timeout", type=int, default=20)
    p.add_argument(
        "--include-approved", action="store_true",
        help="No saltear items con approved_at (golden records). Por defecto "
             "se excluyen: son metadata confirmada manualmente por el owner, "
             "wayback no debe pisarla (guard homogéneo, ver conventions.md).",
    )
    p.add_argument(
        "--negative-cache-file", default=str(DEFAULT_NEGATIVE_CACHE),
        help=f"Caché de URLs sin snapshot confirmado (default: {DEFAULT_NEGATIVE_CACHE}). "
             f"TTL {NEGATIVE_CACHE_TTL_DAYS} días.",
    )
    p.add_argument(
        "--no-negative-cache", action="store_true",
        help="Ignora y no actualiza la caché negativa (re-consulta todo).",
    )
    args = p.parse_args()

    src = Path(args.input)
    if not src.exists() and not args.urls:
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    session = make_session("Mozilla/5.0 (compatible; manga-watch-wayback/1.0)")

    # Caso A: URLs explícitas
    if args.urls:
        target_urls = [u.strip() for u in args.urls.split(",") if u.strip()]
        print(f"[INFO] Recovery puntual de {len(target_urls)} URLs")
        for u in target_urls:
            snap, _definitive = find_wayback_snapshot(u, session)
            if snap:
                print(f"  ✓ {u[:80]}")
                print(f"    snapshot: {snap.get('timestamp','')} → {snap.get('url','')[:80]}")
                md = recover_from_snapshot(snap, {}, session, (5, args.fetch_timeout))
                for k, v in md.items():
                    print(f"      {k}: {str(v)[:80]}")
            else:
                print(f"  ✗ {u[:80]} — sin snapshot")
            time.sleep(args.sleep)
        return 0

    # Caso B: scan items.jsonl
    items: list[dict] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            items.append({"_raw": line})

    print(f"[INFO] {len(items)} items totales en {src}")

    # Identificar candidatos: URL no-empty, no es ya wayback recovered, no es
    # URL canónica de social, no está aprobado (golden record — guard
    # homogéneo `approved_at`, hallazgo #5 auditoría 2026-07-08).
    skipped_approved = 0
    candidates = []
    for it in items:
        if "_raw" in it:
            continue
        url = it.get("url", "")
        if not url:
            continue
        if it.get("recovered_from_wayback"):
            continue  # ya fue procesado
        if is_approved(it) and not args.include_approved:
            skipped_approved += 1
            continue
        # Saltar URLs de social que no soporten Wayback bien
        if any(d in url for d in ("bsky.app/profile/", "facebook.com/", "instagram.com/")):
            continue
        candidates.append(it)

    print(f"[INFO] {len(candidates)} candidatos a verificar (excluidos: social, "
          f"ya recovered, {skipped_approved} aprobados — usar --include-approved)")

    if args.limit > 0:
        candidates = candidates[: args.limit]
        print(f"[INFO] Limitando a {args.limit}")

    # Phase 1: identificar URLs muertas.
    # - 200/301/302/304: vivas
    # - 404/410: realmente muertas → candidatas a Wayback
    # - 403/429/5xx/0: bloqueadas o caídas temporales → reportar pero NO recovery
    #   (la página puede estar viva; sería desperdiciar cuota de Wayback)
    print(f"\n[PHASE 1] Chequeando status HTTP...")
    dead_items: list[tuple[dict, int]] = []   # realmente muertas (404/410)
    blocked_items: list[tuple[dict, int]] = []  # bloqueadas (403/429/5xx)
    for idx, it in enumerate(candidates, 1):
        status = check_url_status(it["url"], session, timeout=args.check_timeout)
        if status in (200, 301, 302, 304):
            pass
        elif status in (404, 410):
            dead_items.append((it, status))
        else:
            blocked_items.append((it, status))
        if idx % 50 == 0:
            print(f"  [{idx}/{len(candidates)}] dead={len(dead_items)} blocked={len(blocked_items)}")
        time.sleep(args.sleep / 3)  # check es más liviano

    print(f"[PHASE 1] {len(dead_items)} URL muertas (404/410), "
          f"{len(blocked_items)} bloqueadas (403/429/5xx/conn)")

    if args.check:
        from collections import Counter
        all_codes = Counter(s for _, s in dead_items) + Counter(s for _, s in blocked_items)
        print(f"\n=== Distribución de status ===")
        for code, n in sorted(all_codes.items(), key=lambda x: -x[1]):
            label = {404: "Not Found", 410: "Gone", 403: "Forbidden",
                     429: "Too Many Requests", 0: "Conn failed"}.get(code, "")
            print(f"  [{code}] {label}: {n}")
        print(f"\n=== URLs muertas — recoverable via Wayback (todas) ===")
        for it, status in dead_items:
            print(f"  [{status}] {it.get('title','')[:60]}")
            print(f"          {it.get('url','')[:90]}")
        if blocked_items:
            print(f"\n=== Bloqueadas (no se intentará Wayback, muestra de 10) ===")
            for it, status in blocked_items[:10]:
                print(f"  [{status}] {it.get('title','')[:60]}")
                print(f"          {it.get('url','')[:90]}")
        return 0

    if not dead_items:
        print("[OK] Nada que recuperar.")
        return 0

    # Phase 2: consultar Wayback para cada uno
    print(f"\n[PHASE 2] Consultando Wayback Machine...")
    recovered_count = 0
    dst = Path(args.output)

    # Backup antes del loop: los flushes incrementales necesitan un punto de
    # retorno seguro. Aplica siempre que `dst` YA tenga contenido que
    # estamos por pisar — antes sólo corría si dst == src (por igualdad de
    # Path), así que un --output distinto (p.ej. absoluto) se saltaba el
    # backup y lo pisaba igual (hallazgo #3, auditoría 2026-07-08).
    if not args.dry_run and dst.exists():
        backup = backup_and_rotate(dst, "wayback")
        print(f"[OK] Backup: {backup}")

    def _flush_wayback() -> None:
        """Serializa items al destino ATÓMICAMENTE vía `write_lines_atomic`
        (tmp + flush + fsync + os.replace, bajo `items_write_lock` — helper
        único de manga_watch.py, A7/A12). Preserva `_raw` para las líneas que
        no se pudieron parsear al leer (patrón B11 raw-preserve): antes usaba
        `write_text` (abre en modo "w", trunca in-place) — un crash a mitad de
        la escritura dejaba items.jsonl truncado/corrupto, pese al docstring
        que decía "atómicamente" (hallazgo #3, auditoría 2026-07-08).
        """
        out_lines: list[str] = []
        for it in items:
            if "_raw" in it:
                out_lines.append(it["_raw"])
            else:
                out_lines.append(json.dumps(it, ensure_ascii=False))
        write_lines_atomic(dst, out_lines)

    # Caché negativa: URLs ya consultadas sin snapshot confirmado. Evita
    # re-golpear Wayback para los miles de items que ya sabemos que no
    # tienen snapshot (hallazgo #13). --no-negative-cache la ignora del todo
    # (ni lee ni escribe) para forzar un re-scan completo.
    use_cache = not args.no_negative_cache
    neg_cache_path = Path(args.negative_cache_file)
    neg_cache = load_negative_cache(neg_cache_path) if use_cache else {}
    if use_cache:
        print(f"[INFO] Caché negativa: {len(neg_cache)} URLs conocidas sin snapshot "
              f"(TTL {NEGATIVE_CACHE_TTL_DAYS}d) en {neg_cache_path}")
    cache_hits = 0
    cache_new_negatives = 0

    _FLUSH_EVERY = 10  # flush cada N recuperaciones
    _CACHE_SAVE_EVERY = 25  # persistir la caché cada N items chequeados
    for idx, (it, status) in enumerate(dead_items, 1):
        url = it["url"]
        cached_checked_at = neg_cache.get(url) if use_cache else None
        if cached_checked_at and negative_cache_is_fresh(cached_checked_at):
            cache_hits += 1
            continue  # ya confirmado "sin snapshot" hace menos del TTL

        snap, definitive = find_wayback_snapshot(url, session)
        if not snap:
            if use_cache and definitive:
                neg_cache[url] = dt.datetime.now(dt.timezone.utc).isoformat()
                cache_new_negatives += 1
            # `definitive=False` (429/timeout/error) NUNCA se cachea — no
            # sabemos si hay snapshot o no, sólo que esta consulta falló.
            time.sleep(args.sleep)
            if use_cache and idx % _CACHE_SAVE_EVERY == 0 and not args.dry_run:
                save_negative_cache(neg_cache_path, neg_cache)
            continue

        md = recover_from_snapshot(snap, it, session, (5, args.fetch_timeout))
        if md:
            recovered_count += 1
            print(f"  [{idx}/{len(dead_items)}] ✓ recovered: {it.get('title','')[:55]}", flush=True)
            print(f"      snapshot {snap.get('timestamp','')[:8]}", flush=True)
            if not args.dry_run:
                it.update(md)
                # Flush periódico: no pérdida si se cancela mid-run
                if recovered_count % _FLUSH_EVERY == 0:
                    _flush_wayback()
                    print(f"  → flush parcial ({recovered_count} recuperados)", flush=True)
        time.sleep(args.sleep)
        if use_cache and idx % _CACHE_SAVE_EVERY == 0 and not args.dry_run:
            save_negative_cache(neg_cache_path, neg_cache)

    print(f"\n[PHASE 2] {recovered_count} items recuperados con metadata de Wayback")
    if use_cache:
        print(f"[PHASE 2] Caché negativa: {cache_hits} hits (saltados sin red), "
              f"{cache_new_negatives} nuevos negativos confirmados")

    if not args.dry_run and use_cache:
        save_negative_cache(neg_cache_path, neg_cache)

    if args.dry_run:
        print("[DRY-RUN] No se escribió items.jsonl")
        return 0
    if recovered_count == 0:
        print("[OK] Nada que escribir.")
        return 0

    # Flush final (incluye el último bloque < FLUSH_EVERY)
    _flush_wayback()
    print(f"[OK] Escrito {dst} ({recovered_count} items enriquecidos vía Wayback)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
