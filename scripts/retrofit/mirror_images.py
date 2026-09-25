#!/usr/bin/env python3
"""mirror_images.py — backfill + GC del espejo local de portadas.

Image storage Fase 1, pasos restantes (ver "Image storage" en CLAUDE.md):

1. BACKFILL — para cada item de items.jsonl, recorre TODAS las entries de
   `images[]` (idx 0 = portada, idx > 0 = galería): para cada una que tenga
   `url` pero le falte `local`, descarga la imagen a data/images/ y setea
   `images[i].local`. La portada es `images[0]` (única fuente de verdad); no
   hay campo top-level que mirar. El scrape
   (`manga_watch.py::mirror_candidate_images`) ya lo hace para items nuevos;
   este retrofit cubre el corpus histórico que recién recibió `images[]`
   poblado por `backfill_metadata.py --only images`.

2. GC mark-and-sweep — busca en data/images/ los archivos que NINGÚN
   item de items.jsonl referencia (orphans, típicamente de items que
   se quitaron del corpus) y los saca de la carpeta. El set de
   "referenciadas" incluye cada `images[i].local` (portada + galería) y
   cada `sources[i].image_local` (per-fuente) — si solo mirara la portada,
   los archivos de galería/fuente caerían como orphans. Por defecto los manda
   a una cuarentena (data/images/_orphans/) — reversible; `--gc-delete` los
   borra de verdad.

Idempotente: re-correrlo no re-descarga imágenes ya en disco (el nombre
de archivo es determinístico). Seguro de correr en el overnight.

Items aprobados (`approved_at`, golden records) — matiz WO-D (2026-07-07): el
BACKFILL de este script es ADITIVO (solo rellena un `local` faltante; nunca
quita, reordena ni reemplaza una entry existente), así que se aplica IGUAL a
items aprobados por defecto — un golden record necesita su espejo local tanto
como cualquier otro (si lo saltáramos, un item aprobado nunca conseguiría su
`local`). `--include-approved` se acepta por consistencia de CLI con el resto
de los retrofits de imagen, pero no cambia el comportamiento del backfill; el
summary igual reporta cuántas de las entries rellenadas eran de items
aprobados, a título informativo. El GC (mark-and-sweep de archivos huérfanos)
no muta `images[]` de ningún item — opera solo sobre archivos en disco — así
que tampoco necesita saltear aprobados.

Uso:
    python scripts/retrofit/mirror_images.py                # backfill + GC
    python scripts/retrofit/mirror_images.py --dry-run      # solo reporta
    python scripts/retrofit/mirror_images.py --no-gc        # solo backfill
    python scripts/retrofit/mirror_images.py --gc-only      # solo GC
    python scripts/retrofit/mirror_images.py --workers 8    # paralelismo
    python scripts/retrofit/mirror_images.py --limit 100    # primeros 100 (test)
    python scripts/retrofit/mirror_images.py --gc-delete    # GC borra (no cuarentena)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import image_store  # type: ignore
try:  # import dual robusto (CLI directo vs wrapper raíz bajo pytest)
    from manga_watch import (  # type: ignore  # noqa: E402
        make_session, backup_and_rotate, is_approved, write_lines_atomic,
        ThrottleRegistry,
    )
except ImportError:  # pragma: no cover
    from scripts.manga_watch import (  # type: ignore  # noqa: E402
        make_session, backup_and_rotate, is_approved, write_lines_atomic,
        ThrottleRegistry,
    )

# MISMO User-Agent que usa el scraper (`manga_watch.py --user-agent`).
# Algunas fuentes (Manga-Sanctuary, p.ej.) sirven 404 a UAs desconocidos
# pero 200 a este — el corpus entero se scrapeó con él, así que las
# imágenes hay que pedirlas con el mismo UA o fallan.
DEFAULT_USER_AGENT = "manga-watch-personal/0.2 (+personal-use)"

# Subdirectorio de cuarentena para orphans (dentro de data/images/, así
# que el GC lo ignora al escanear — solo mira archivos top-level).
QUARANTINE_DIRNAME = "_orphans"


def _load_items(src: Path) -> list[dict]:
    items: list[dict] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            items.append({"_raw": line})  # preserva la línea ininteligible
    return items


def _write_items(dst: Path, items: list[dict]) -> None:
    try:
        from scripts.manga_watch import items_write_lock, read_jsonl_strict, write_items_atomic
    except ImportError:
        from manga_watch import items_write_lock, read_jsonl_strict, write_items_atomic
    def identity(row):
        return row.get('url') or row.get('slug')
    with items_write_lock(dst):
        if not dst.exists():
            write_items_atomic(dst, items)
            return
        current = read_jsonl_strict(dst)
        patches = {identity(row): row for row in items if identity(row)}
        for row in current:
            patch = patches.get(identity(row))
            if not patch:
                continue
            images = {im.get('url'): im for im in patch.get('images', []) if im.get('url')}
            for im in row.get('images', []):
                if im.get('url') in images and (not im.get('local') or not (dst.parent / image_store.IMAGES_DIRNAME / im['local']).is_file()):
                    im['local'] = images[im['url']].get('local', '')
        write_items_atomic(dst, current)


def _normalize_missing_local_keys(items: list[dict], *, apply: bool) -> int:
    """Uniforma el esquema de `images[]`: toda entry con `url` debe tener la key
    `local` presente (canónica `""` cuando no hay espejo — ver
    `image_store.cover_local`/`set_cover`, que ya devuelven/escriben `""` por
    default). Auditoría 2026-08-31: 259 items del corpus tenían la key ausente
    en vez de `""` (`local:None` al leerla con `.get()`) mientras que las otras
    13598/13857 portadas con `url` ya tenían `local=""` explícito — inconsistencia
    de esquema, no de comportamiento (`not im.get("local")` trata ambos casos
    igual, por eso el backfill nunca lo notó). `apply=False` sólo cuenta (dry-run).
    Devuelve cuántas entries se normalizaron (o normalizarían)."""
    n = 0
    for it in items:
        if "_raw" in it:
            continue
        for im in (it.get("images") or []):
            if isinstance(im, dict) and im.get("url") and "local" not in im:
                n += 1
                if apply:
                    im["local"] = ""
    return n


def _pixels_of(data: bytes) -> int:
    """Área en píxeles de `data` (bytes de imagen ya descargados). Delega en
    `fetch_better_covers._get_pixels_from_bytes` (fuente única de dimensiones,
    gotcha #124/#132 — cubre AVIF vía fallback PIL) en vez de reimplementar un
    4º parser binario. 0 si no se puede determinar."""
    try:
        import fetch_better_covers as _fbc  # type: ignore  # noqa: PLC0415
        return _fbc._get_pixels_from_bytes(data) or 0
    except ImportError:  # pragma: no cover — dependencias opcionales (PIL/bs4)
        return 0


def _classify_failure(
    url: str, session: requests.Session, timeout: tuple[int, int], referer: str,
) -> str:
    """Best-effort: UN request de diagnóstico adicional (mismo session/UA que
    `download_image`) para bucketizar por qué falló, SOLO sobre URLs que ya
    fallaron — nunca agrega carga extra sobre las que sí funcionan.
    `download_image` en sí no expone la causa (por diseño: cualquier problema
    devuelve "" para degradar con gracia), así que esto es puramente para el
    reporte de esta corrida, no cambia ningún comportamiento del pipeline."""
    headers = {"Referer": referer} if referer else None
    try:
        resp = session.get(url, timeout=timeout, stream=True, headers=headers)
    except requests.Timeout:
        return "timeout"
    except requests.ConnectionError:
        return "connection_error"
    except (requests.RequestException, UnicodeError) as exc:
        return f"request_error:{type(exc).__name__}"
    try:
        if resp.status_code != 200:
            return f"http_{resp.status_code}"
        return "not_image_or_too_large"
    finally:
        resp.close()


def _run_backfill(
    items: list[dict],
    images_dir: Path,
    *,
    items_path: Path | None = None,
    workers: int,
    per_host_limit: int,
    timeout: tuple[int, int],
    limit: int,
    user_agent: str,
    dry_run: bool,
    skip_hosts: frozenset[str] = frozenset(),
    slugs: frozenset[str] = frozenset(),
) -> int:
    """Descarga el `local` faltante de CADA entry de images[]. Devuelve cuántos
    consumers (entries de images[]) se actualizaron.

    Target = cualquier `images[idx]` con `url` y sin `local` (idx 0 = portada,
    idx > 0 = galería). El owner quiere que TODAS las fotos tengan su espejo
    local, no solo la portada.

    Tres capas ANTES de tocar la red (2026-09-01, OLA 1 depuración de imágenes):
      1. `skip_hosts` — hosts que se saben bloqueados (ej. mangavariant.com,
         detrás de un challenge sgcaptcha que devuelve 202 incluso para las
         imágenes estáticas /wp-content/uploads/ — ver gotcha #158) se excluyen
         ANTES de contar targets, para no gastar tiempo/red en algo que se sabe
         que va a fallar 100% de las veces.
      2. `image_store.known_placeholder_url_reason(url)` — una URL ya fichada
         como placeholder conocido (logo, "imagen no disponible", etc.) NUNCA
         es una portada real: se saltea sin descargar.
      3. Tras descargar, `image_store.placeholder_reason(bytes)` sobre el
         archivo YA guardado por `download_image` — si el contenido resulta
         ser un placeholder estructural/por firma que no estaba fichado por
         URL, NO se asigna como `local` del consumer (el archivo queda huérfano
         en disco; el GC de este mismo script lo manda a cuarentena si corre a
         continuación) — así nunca "portada" == placeholder.

    `slugs` (opcional) acota los TARGETS a items puntuales (CLI `--slugs`),
    sin achicar `items` — el flush periódico y el flush final SIEMPRE escriben
    la lista `items` completa que se les pasó (el caller decide qué lista es
    esa); si acá filtráramos `items` en vez de sólo los targets, un flush a
    mitad de la descarga truncaría items.jsonl al subconjunto acotado.
    """
    try:
        from scripts.manga_watch import read_jsonl_strict, write_items_atomic
    except ImportError:
        from manga_watch import read_jsonl_strict, write_items_atomic
    attempts_path = images_dir.parent / 'image_mirror_attempts.jsonl'
    attempts = {row['url']: row for row in read_jsonl_strict(attempts_path)}
    def recent_failure(url):
        return time.time() - attempts.get(url, {}).get('at', 0) < 86400

    # Targets: (item, idx) por cada entry de images[] con url y sin local.
    img_targets: list[tuple[dict, int]] = []
    skipped_host_targets: list[tuple[dict, int]] = []
    for it in items:
        if "_raw" in it:
            continue
        if slugs and it.get("slug") not in slugs:
            continue
        imgs = it.get("images") or []
        for idx, im in enumerate(imgs):
            if not isinstance(im, dict):
                continue
            if im.get("url") and (not im.get("local") or not (images_dir / im["local"]).is_file()) and not recent_failure(im["url"]):
                host = urlparse(im["url"]).hostname or ""
                if host.lower() in skip_hosts:
                    skipped_host_targets.append((it, idx))
                else:
                    img_targets.append((it, idx))

    img_targets.sort(key=lambda entry: entry[1])  # Covers before galleries.
    if limit > 0:
        img_targets = img_targets[:limit]

    if skipped_host_targets:
        by_host = Counter(
            (urlparse(it["images"][idx]["url"]).hostname or "")
            for it, idx in skipped_host_targets
        )
        print(f"[BACKFILL] {len(skipped_host_targets)} imágenes en hosts excluidos "
              f"(--skip-hosts), sin tocar la red:")
        for host, n in by_host.most_common():
            print(f"  {n:5d}  {host}")

    # Pre-filtro: URLs ya fichadas como placeholder conocido (gotcha #112) —
    # nunca son la portada real, no vale la pena bajarlas.
    known_placeholder_targets: list[tuple[dict, int, str]] = []
    real_targets: list[tuple[dict, int]] = []
    for it, idx in img_targets:
        url = it["images"][idx]["url"]
        reason = image_store.known_placeholder_url_reason(url)
        if reason:
            known_placeholder_targets.append((it, idx, reason))
        else:
            real_targets.append((it, idx))

    if known_placeholder_targets:
        by_reason = Counter(r for _, _, r in known_placeholder_targets)
        print(f"[BACKFILL] {len(known_placeholder_targets)} imágenes son placeholder "
              f"conocido por URL (known_placeholder_url_reason) — no se descargan:")
        for reason, n in by_reason.most_common():
            print(f"  {n:5d}  {reason}")

    # Dedup por URL: muchos items comparten la misma imagen (tomos de una
    # edición, cross-source, portada repetida en galería). Bajamos cada URL
    # única una sola vez y mapeamos el filename a todos sus consumers.
    # consumers: list of (it, idx) sobre images[].
    by_url: dict[str, list[tuple[dict, int]]] = {}
    for it, idx in real_targets:
        url = it["images"][idx]["url"]
        by_url.setdefault(url, []).append((it, idx))

    n_targets = len(real_targets)
    n_covers = sum(1 for _, idx in real_targets if idx == 0)
    # Informativo, no gating (ver matiz WO-D en el docstring): cuántos targets
    # pertenecen a items aprobados — el fill se hace igual, es aditivo.
    n_approved = sum(1 for it, _ in real_targets if is_approved(it))
    print(f"[BACKFILL] {n_targets} imágenes sin local a intentar ({n_covers} portadas, "
          f"{n_targets - n_covers} galería) — {len(by_url)} URLs únicas.")
    if n_approved:
        print(f"[BACKFILL]   de ellas, {n_approved} en items aprobados (fill aditivo, "
              f"siempre permitido — ver docstring).")
    if not by_url:
        return 0
    if dry_run:
        cover_counter = Counter(it.get("source", "?") for it, idx in real_targets if idx == 0)
        if cover_counter:
            print("[BACKFILL] Top sources pendientes (portadas):")
            for source, n in cover_counter.most_common(10):
                print(f"  {n:5d}  {source}")
        gallery_counter = Counter(it.get("source", "?") for it, idx in real_targets if idx != 0)
        if gallery_counter:
            print("[BACKFILL] Top sources pendientes (galería):")
            for source, n in gallery_counter.most_common(10):
                print(f"  {n:5d}  {source}")
        print("[DRY-RUN] No se descargó nada.")
        return 0

    session = make_session(user_agent)
    # Images are independent optional assets: a blocked host must not stall
    # thousands of unrelated URLs behind Retry-After sleeps.
    from requests.adapters import HTTPAdapter
    session.mount('https://', HTTPAdapter(max_retries=0, pool_connections=32, pool_maxsize=32))
    session.mount('http://', HTTPAdapter(max_retries=0, pool_connections=32, pool_maxsize=32))
    blocked_hosts = set()

    # Cortesía por-host (conventions.md § anti-bot): 8 workers globales sin
    # límite por host saturarían un solo dominio chico (16 en manga-sanctuary,
    # 9 en media-amazon, etc.) — mismo semáforo `ThrottleRegistry` que usa el
    # scraper principal (`--per-host-limit`), sin grupos (no aplica acá).
    throttle = ThrottleRegistry(per_host_limit=per_host_limit)

    def _one(
        entry: tuple[str, list[tuple[dict, int]]],
    ) -> tuple[list[tuple[dict, int]], str, str, int]:
        """Devuelve (consumers, filename_o_"", reason_de_fallo_o_"placeholder:X", px)."""
        url, consumers = entry
        referer = consumers[0][0].get("url", "")
        host = urlparse(url).hostname
        if host in blocked_hosts:
            return consumers, "", "host_blocked", 0
        with throttle.acquire(url):
            if host in blocked_hosts:
                return consumers, "", "host_blocked", 0
            filename = image_store.download_image(
                url, images_dir, session=session,
                timeout=timeout, referer=referer,
            )
        if not filename:
            reason = getattr(session, '_image_download_failures', {}).get(image_store.normalize_image_url(url))
            reason = reason or _classify_failure(url, session, timeout, referer)
            if reason in {'http_403', 'http_429'}:
                blocked_hosts.add(host)
            return consumers, "", reason, 0
        # Descarga OK — pero puede ser un placeholder que NADIE fichó todavía
        # por URL (contenido genérico servido ad-hoc). No propagar eso como
        # portada real (item 2 del encargo). `normalize_image` (dentro de
        # download_image) ya deja los bytes de un placeholder SIN re-encodear,
        # así que placeholder_reason() sobre el archivo en disco sigue viendo
        # la misma firma/estructura que vería sobre el body crudo.
        try:
            data = (images_dir / filename).read_bytes()
        except OSError:
            return consumers, "", "read_after_download_failed", 0
        preason = image_store.placeholder_reason(data)
        if preason:
            # No se borra el archivo (mirror_images.py es aditivo — ver
            # docstring del módulo); queda huérfano en disco y el GC de esta
            # misma corrida lo manda a cuarentena si no se pasó --no-gc.
            return consumers, "", f"placeholder:{preason}", 0
        pixels = _pixels_of(data)
        if pixels <= 0:
            return consumers, "", "unreadable_image", 0
        return consumers, filename, "", pixels

    updated = 0
    failed_urls = 0
    placeholder_urls = 0
    failure_reasons: Counter[str] = Counter()
    px_ge_90k = 0
    px_lt_90k = 0
    done = 0
    total = len(by_url)
    # Convención dura (docs/reference/conventions.md § "Flush incremental"):
    # default 50, no 200 (hallazgo #15, 2026-07-08) — un write único más
    # espaciado deja más trabajo sin persistir si el proceso muere a mitad
    # de una corrida larga sobre miles de URLs.
    _FLUSH_EVERY = 50  # flush items.jsonl cada N URLs procesadas (no pérdida si se cancela)
    with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="mirror") as pool:
        # Round-robin hosts prevents all workers waiting on one semaphore.
        from itertools import zip_longest
        by_host = {}
        for e in by_url.items():
            by_host.setdefault(urlparse(e[0]).hostname, []).append(e)
        ordered = [e for batch in zip_longest(*by_host.values()) for e in batch if e is not None]
        for fut in as_completed(pool.submit(_one, e) for e in ordered):
            consumers, filename, reason, px = fut.result()
            done += 1
            attempted_url = consumers[0][0]['images'][consumers[0][1]]['url']
            if filename:
                attempts.pop(attempted_url, None)
            else:
                attempts[attempted_url] = {'url': attempted_url, 'at': time.time(), 'reason': reason}
            if filename:
                for it, idx in consumers:
                    it["images"][idx]["local"] = filename
                updated += len(consumers)
                if px >= 90_000:
                    px_ge_90k += 1
                else:
                    px_lt_90k += 1
            elif reason.startswith("placeholder:"):
                placeholder_urls += 1
            else:
                failed_urls += 1
                if reason:
                    failure_reasons[reason] += 1
            if done % _FLUSH_EVERY == 0:
                print(f"  [{done}/{total}] URLs procesadas, {updated} consumers atendidos", flush=True)
                # Flush periódico: no pérdida de datos si se cancela mid-run
                if items_path is not None and not dry_run:
                    _write_items(items_path, items)
                    write_items_atomic(attempts_path, list(attempts.values()))
                    print(f"  → flush parcial ({done} procesadas)", flush=True)

    if not dry_run:
        write_items_atomic(attempts_path, list(attempts.values()))
    print(f"[BACKFILL] {updated} consumers actualizados, {failed_urls} URLs "
          f"fallidas (esas entries quedan con images[].url como fallback), "
          f"{placeholder_urls} URLs descargaron un placeholder (no se asignó local).")
    if failure_reasons:
        print("[BACKFILL] Fallos por razón:")
        for reason, n in failure_reasons.most_common():
            print(f"  {n:5d}  {reason}")
    n_mirrored_urls = px_ge_90k + px_lt_90k
    print(f"[BACKFILL] De las {n_mirrored_urls} URLs únicas mirroreadas con éxito "
          f"({updated} consumers/entries de images[] actualizadas): "
          f"{px_ge_90k} con área >= 90 000 px, {px_lt_90k} por debajo del umbral "
          f"(mismo umbral que scripts/audit/data_quality.py).")
    return updated


def _run_gc(
    items: list[dict],
    images_dir: Path,
    *,
    delete: bool,
    dry_run: bool,
) -> int:
    """Saca de images_dir los archivos que ningún item referencia.

    Devuelve la cantidad de orphans encontrados."""
    if not images_dir.exists():
        print("[GC] data/images/ no existe todavía — nada que limpiar.")
        return 0

    # Referenciadas = portada + galería (`images[i].local`, idx 0 = portada) +
    # CADA fuente (`sources[i].image_local`, modelo 1-fila-por-producto). Sin
    # incluir sources[], el GC borraría fotos que una fuente sí usa (58 archivos
    # de ese tipo detectados el 2026-06-02).
    referenced: set[str] = set()
    for it in items:
        if "_raw" in it:
            continue
        for im in (it.get("images") or []):
            if isinstance(im, dict) and im.get("local"):
                referenced.add(im["local"])
        for s in (it.get("sources") or []):
            if isinstance(s, dict) and s.get("image_local"):
                referenced.add(s["image_local"])

    # Retain the original bytes needed to undo an automatic upgrade.
    for item in items:
        for change in item.get('cover_history', []):
            for field in ('old_local', 'new_local'):
                if change.get(field):
                    referenced.add(change[field])

    # cover_preview.json referencia archivos del espejo por `old_image`/
    # `new_image` (revisión de portadas mejoradas, web/cover-preview.html). NO
    # están en items.jsonl — si no se incluyen, el GC borra las originales y la
    # página de review queda con todas las fotos rotas (bug 2026-06-03).
    preview = images_dir.parent / "cover_preview.json"
    if preview.exists():
        try:
            for e in json.loads(preview.read_text(encoding="utf-8")):
                # old_image: portada vieja (referencia para el diff de review).
                v = e.get("old_image")
                if v and v != "[dry-run]":
                    referenced.add(v)
                # new_image: schema viejo (plano) o schema multi-candidato
                # (candidates[].new_image). Hay que cubrir ambos o el GC borra
                # las candidatas y la página de review queda con fotos rotas.
                v = e.get("new_image")
                if v and v != "[dry-run]":
                    referenced.add(v)
                for c in (e.get("candidates") or []):
                    v = c.get("new_image")
                    if v and v != "[dry-run]":
                        referenced.add(v)
        except (ValueError, OSError):
            pass

    on_disk = [p for p in images_dir.iterdir() if p.is_file()]
    orphans = [p for p in on_disk if p.name not in referenced]

    freed = sum(p.stat().st_size for p in orphans)
    print(f"[GC] {len(on_disk)} archivos en disco, {len(referenced)} referenciados, "
          f"{len(orphans)} orphans ({freed / 1024 / 1024:.1f} MB).")
    if not orphans:
        return 0
    if dry_run:
        for p in orphans[:10]:
            print(f"  orphan: {p.name}")
        if len(orphans) > 10:
            print(f"  … y {len(orphans) - 10} más.")
        print("[DRY-RUN] No se movió ni borró nada.")
        return len(orphans)

    if delete:
        for p in orphans:
            p.unlink()
        print(f"[GC] {len(orphans)} archivos borrados.")
    else:
        quarantine = images_dir / QUARANTINE_DIRNAME
        quarantine.mkdir(parents=True, exist_ok=True)
        for p in orphans:
            p.replace(quarantine / p.name)
        print(f"[GC] {len(orphans)} archivos movidos a cuarentena {quarantine}/ "
              f"(borralos a mano cuando estés seguro, o re-corré con --gc-delete).")
    return len(orphans)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default="data/items.jsonl")
    parser.add_argument("--output", default="data/items.jsonl")
    parser.add_argument("--workers", type=int, default=8,
                        help="Descargas en paralelo (default: 8).")
    parser.add_argument("--per-host-limit", type=int, default=2,
                        help="Descargas concurrentes por HOSTNAME (default: 2, mismo "
                             "default que manga_watch.py --per-host-limit) — cortesía "
                             "ante fuentes con pocas imágenes pendientes concentradas "
                             "en un solo host chico.")
    parser.add_argument("--skip-hosts", default="",
                        help="Hostnames separados por coma a EXCLUIR del backfill sin "
                             "tocar la red (ej. un host con anti-bot conocido que "
                             "bloquea todos los intentos). Vacío = ninguno.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Máximo de items a backfillear (0 = sin límite). Útil para probar.")
    parser.add_argument("--slugs", default="",
                        help="Slugs separados por coma — acota el BACKFILL a esos items "
                             "puntuales (el resto del corpus se re-escribe intacto; el GC, "
                             "si corre, sigue viendo el corpus completo). Vacío = todos. Útil "
                             "para reparaciones acotadas (p.ej. tras restaurar images[] de un "
                             "subconjunto de items que quedó con local=\"\" y necesita "
                             "re-descargarse) sin tocar la red del resto del corpus.")
    parser.add_argument("--no-gc", action="store_true",
                        help="Solo backfill, sin la pasada de garbage collection.")
    parser.add_argument("--gc-only", action="store_true",
                        help="Solo GC, sin descargar nada.")
    parser.add_argument("--gc-delete", action="store_true",
                        help="GC borra los orphans en vez de mandarlos a cuarentena.")
    parser.add_argument("--include-approved", action="store_true",
                        help="Aceptado por consistencia de CLI con el resto de los retrofits "
                             "de imagen; no cambia el comportamiento (el backfill de este "
                             "script es aditivo y ya se aplica a items aprobados — ver "
                             "docstring del módulo).")
    parser.add_argument("--connect-timeout", type=int, default=10)
    parser.add_argument("--read-timeout", type=int, default=30)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--dry-run", action="store_true",
                        help="No descarga, no mueve, no escribe — solo reporta.")
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    images_dir = src.parent / image_store.IMAGES_DIRNAME
    items = _load_items(src)
    print(f"[INFO] {len(items)} items en {src}")
    print(f"[INFO] espejo local: {images_dir}/")

    # --slugs acota los TARGETS del backfill a items puntuales (ver `slugs=`
    # en `_run_backfill`); `items` NUNCA se achica — el flush (parcial y
    # final) siempre escribe el corpus completo, sólo los targets se filtran.
    slugs = frozenset(s.strip() for s in args.slugs.split(",") if s.strip())
    if slugs:
        present = {it.get("slug") for it in items if "_raw" not in it and it.get("slug")}
        missing = slugs - present
        print(f"[SLUGS] {len(slugs & present)}/{len(slugs)} slugs encontrados en el corpus.")
        if missing:
            print(f"[SLUGS] {len(missing)} slugs NO encontrados (typo / no existen): "
                  f"{', '.join(sorted(missing)[:10])}" + (" …" if len(missing) > 10 else ""))
    print()

    dst = Path(args.output)

    # Backup antes del loop — así los flushes incrementales tienen un punto de retorno
    if not args.dry_run and not args.gc_only:
        if dst.exists():
            backup = backup_and_rotate(dst, "mirror")
            print(f"[OK] Backup en {backup}")

    normalized = 0
    updated = 0
    if not args.gc_only:
        # Paso 0 — normaliza esquema: toda entry con `url` debe tener la key
        # `local` presente (canónica "" si no hay espejo — ver docstring de la
        # función). Corre siempre antes del backfill, incluso en --dry-run
        # (donde sólo cuenta, no muta).
        normalized = _normalize_missing_local_keys(items, apply=not args.dry_run)
        verb = "normalizarían" if args.dry_run else "normalizaron"
        print(f"[NORMALIZE] {normalized} entries de images[] {verb} "
              f"(local ausente → local=\"\").")
        print()

        skip_hosts = frozenset(
            h.strip().lower() for h in args.skip_hosts.split(",") if h.strip()
        )
        updated = _run_backfill(
            items, images_dir,
            items_path=dst if not args.dry_run else None,
            workers=args.workers,
            per_host_limit=args.per_host_limit,
            timeout=(args.connect_timeout, args.read_timeout),
            limit=args.limit,
            user_agent=args.user_agent,
            dry_run=args.dry_run,
            skip_hosts=skip_hosts,
            slugs=slugs,
        )
        print()

    if not args.no_gc:
        _run_gc(items, images_dir, delete=args.gc_delete, dry_run=args.dry_run)
        print()

    if args.dry_run:
        print("[DRY-RUN] Nada se escribió a disco.")
        return 0

    if updated == 0 and normalized == 0:
        print("[OK] items.jsonl sin cambios (no hubo backfill ni normalización que escribir).")
        return 0

    # Flush final (cubre el último bloque, la normalización y cualquier cambio del GC)
    _write_items(dst, items)
    print(f"[OK] Escribí {dst} — {updated} entries de images[] con local nuevo, "
          f"{normalized} entries normalizadas (local ausente → \"\").")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
