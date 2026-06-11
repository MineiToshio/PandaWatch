#!/usr/bin/env python3
"""serve.py — servidor único de Manga Watch.

Sirve el catálogo, el panel de control y la API de ejecución de scripts.
Todos los endpoints conviven en un solo proceso (port 8000, 0.0.0.0).

Endpoints:
    GET  /                          → 302 a /web/
    archivos estáticos en /web/, /data/, /reports/
    POST /api/feedback              → registra feedback en data/feedback.jsonl
    POST /api/curation/move         → mover item a otra edición (inmediato)
    POST /api/curation/merge        → fusionar items duplicados (inmediato)
    POST /api/curation/remove       → sacar item de su edición (inmediato)
    POST /api/item/update           → editar metadata del item (detalle, inmediato)
    POST /api/approve               → aprobar/desaprobar una card (golden record)
    POST /api/approve-edition       → aprobar/desaprobar todos los tomos de una edición
    POST /api/batch/approve         → aprobar/desaprobar N cards/ediciones a la vez
    POST /api/batch/move            → mover N items a una edición a la vez
    POST /api/quality/check         → re-evalúa N items (live-update del Panel de Calidad)
    GET  /api/editions/search?q=    → buscar ediciones por nombre (autocomplete)
    POST /api/save-cover-preview    → guarda data/cover_preview.json
    GET  /api/health                → liveness probe
    GET  /api/scripts               → JSON del script registry (panel)
    POST /api/run                   → lanza un script (panel)
    GET  /api/jobs                  → lista jobs (panel)
    GET  /api/jobs/<id>             → detalle de un job (panel)
    GET  /api/jobs/<id>/stream      → SSE stdout/stderr en vivo (panel)
    POST /api/jobs/<id>/stop        → SIGTERM al proceso (panel)
    GET  /api/image-file-sizes      → {filename: bytes} del espejo local
    POST /api/image-manager/save    → guarda images[] de un item
    POST /api/image-manager/download → descarga imagen por URL al espejo
    POST /api/image-manager/scrape  → extrae <img> URLs de una página
    POST /api/image-search          → busca portadas candidatas (ISBN + Tavily)

Uso:
    python scripts/serve.py             # port 8000 (default), 0.0.0.0
    python scripts/serve.py --port 9000
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import shlex
import socketserver
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
ITEMS_PATH     = ROOT / "data" / "items.jsonl"
FEEDBACK_PATH  = ROOT / "data" / "feedback.jsonl"
APPROVALS_PATH = ROOT / "data" / "approvals.jsonl"
EDITS_PATH     = ROOT / "data" / "edits.jsonl"
DUP_DECISIONS_PATH = ROOT / "data" / "dup_decisions.jsonl"
IMAGES_DIR     = ROOT / "data" / "images"

MAX_BUFFERED_LINES = 5000
MAX_FINISHED_JOBS  = 30

# Permite importar script_registry como módulo top-level desde scripts/.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    from script_registry import SCRIPTS, get_script, known_flags  # type: ignore
    _REGISTRY_OK = True
except ImportError:
    SCRIPTS: list = []
    _REGISTRY_OK = False

    def get_script(sid: str) -> None:  # type: ignore[misc]
        return None

    def known_flags(sid: str) -> set:  # type: ignore[misc]
        return set()

# Primitivas del modelo 1-fila-por-producto (fuente única de verdad del merge).
# Las usan los endpoints de curación que escriben items.jsonl para no romper el
# invariante "1 fila por cluster_key con sources[]". Ver CLAUDE.md decisión #1.
try:
    import manga_watch as _mw_mod  # type: ignore
    if not hasattr(_mw_mod, "merge_cluster"):  # wrapper raíz bajo pytest
        from scripts import manga_watch as _mw_mod  # type: ignore
    merge_cluster = _mw_mod.merge_cluster
    consolidate_by_cluster = _mw_mod.consolidate_by_cluster
    derive_cluster_key = _mw_mod.derive_cluster_key
    backup_and_rotate = _mw_mod.backup_and_rotate
except Exception:  # pragma: no cover
    merge_cluster = None  # type: ignore
    consolidate_by_cluster = None  # type: ignore
    derive_cluster_key = None  # type: ignore
    backup_and_rotate = None  # type: ignore


# ---------------------------------------------------------------------------
# Job manager — corre subprocesos y reparte sus logs via SSE
# ---------------------------------------------------------------------------

class Job:
    """Un proceso en ejecución (o terminado) con sus logs y suscriptores SSE."""

    __slots__ = (
        "id", "script_id", "label", "command", "status", "started_at",
        "ended_at", "exit_code", "process", "lines", "lock", "cv", "version",
    )

    def __init__(self, script_id: str, label: str, command: list[str]) -> None:
        self.id: str = uuid.uuid4().hex[:12]
        self.script_id: str = script_id
        self.label: str = label
        self.command: list[str] = command
        self.status: str = "running"  # running | exited | error | killed
        self.started_at: str = datetime.now(timezone.utc).isoformat()
        self.ended_at: str | None = None
        self.exit_code: int | None = None
        self.process: subprocess.Popen[bytes] | None = None
        self.lines: deque[str] = deque(maxlen=MAX_BUFFERED_LINES)
        self.lock: threading.Lock = threading.Lock()
        self.cv: threading.Condition = threading.Condition(self.lock)
        self.version: int = 0

    def append(self, line: str) -> None:
        with self.cv:
            self.lines.append(line)
            self.version += 1
            self.cv.notify_all()

    def mark_done(self, status: str, exit_code: int | None) -> None:
        with self.cv:
            self.status = status
            self.exit_code = exit_code
            self.ended_at = datetime.now(timezone.utc).isoformat()
            self.version += 1
            self.cv.notify_all()

    def to_dict(self, include_lines: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "script_id": self.script_id,
            "label": self.label,
            "command": self.command,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "exit_code": self.exit_code,
            "lines_count": len(self.lines),
        }
        if include_lines:
            out["lines"] = list(self.lines)
        return out


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.order: deque[str] = deque()
        self.lock = threading.Lock()

    def start(self, script_id: str, command: list[str], label: str,
              cwd: Path) -> Job:
        job = Job(script_id, label, command)
        with self.lock:
            self.jobs[job.id] = job
            self.order.append(job.id)
            self._trim()

        def reader(proc: subprocess.Popen[bytes]) -> None:
            try:
                assert proc.stdout is not None
                for raw in iter(proc.stdout.readline, b""):
                    try:
                        text = raw.decode("utf-8", errors="replace").rstrip("\n")
                    except Exception:
                        text = repr(raw)
                    job.append(text)
                proc.stdout.close()
                rc = proc.wait()
                job.mark_done("exited" if rc == 0 else "error", rc)
            except Exception as e:
                job.append(f"[serve][ERROR reader] {e}")
                job.mark_done("error", -1)

        try:
            full_env = os.environ.copy()
            full_env["PYTHONUNBUFFERED"] = "1"
            proc = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=full_env,
                bufsize=1,
            )
            job.process = proc
            job.append(f"[serve] PID {proc.pid} — {shlex.join(command)}")
            threading.Thread(target=reader, args=(proc,), daemon=True).start()
        except Exception as e:
            job.append(f"[serve][ERROR spawn] {e}")
            job.mark_done("error", -1)
        return job

    def stop(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or not job.process or job.status != "running":
            return False
        try:
            job.process.terminate()

            def _killer(p: subprocess.Popen[bytes]) -> None:
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()

            threading.Thread(target=_killer, args=(job.process,), daemon=True).start()
            job.append("[serve] SIGTERM enviado por el usuario")
            return True
        except Exception as e:
            job.append(f"[serve][ERROR stop] {e}")
            return False

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def list(self) -> list[Job]:
        return [self.jobs[jid] for jid in self.order if jid in self.jobs]

    def _trim(self) -> None:
        finished = [
            jid for jid in self.order
            if jid in self.jobs and self.jobs[jid].status != "running"
        ]
        while len(finished) > MAX_FINISHED_JOBS:
            old = finished.pop(0)
            self.jobs.pop(old, None)
            try:
                self.order.remove(old)
            except ValueError:
                pass


JOBS = JobManager()


# ---------------------------------------------------------------------------
# Construcción del comando desde flags
# ---------------------------------------------------------------------------

def build_command(
    script_id: str, flag_values: dict[str, Any]
) -> tuple[list[str], str] | tuple[None, str]:
    """Valida flags y devuelve (argv, label) o (None, mensaje_error)."""
    spec = get_script(script_id)
    if not spec:
        return None, f"script_id desconocido: {script_id}"

    valid = known_flags(script_id)
    cmd = list(spec["command"])
    used_labels: list[str] = []
    by_arg = {f["arg"]: f for f in spec["flags"]}

    for arg, value in flag_values.items():
        if arg not in valid:
            return None, f"flag desconocido para {script_id}: {arg}"
        f = by_arg[arg]
        t = f["type"]

        if t == "bool":
            if bool(value):
                cmd.append(arg)
                used_labels.append(arg)
        elif t == "int":
            if value in (None, "", "null"):
                continue
            try:
                ival = int(value)
            except (TypeError, ValueError):
                return None, f"valor int inválido para {arg}: {value!r}"
            cmd.extend([arg, str(ival)])
            used_labels.append(f"{arg}={ival}")
        elif t == "float":
            if value in (None, "", "null"):
                continue
            try:
                fval = float(value)
            except (TypeError, ValueError):
                return None, f"valor float inválido para {arg}: {value!r}"
            cmd.extend([arg, str(fval)])
            used_labels.append(f"{arg}={fval}")
        elif t in ("str", "csv"):
            sval = "" if value is None else str(value).strip()
            if not sval:
                continue
            cmd.extend([arg, sval])
            used_labels.append(f"{arg}={sval}")
        elif t == "choice":
            sval = "" if value is None else str(value).strip()
            if not sval:
                continue
            if f.get("choices") and sval not in f["choices"]:
                return None, f"choice inválido para {arg}: {sval!r}"
            cmd.extend([arg, sval])
            used_labels.append(f"{arg}={sval}")
        else:
            return None, f"tipo de flag no soportado: {t}"

    label = spec["name"]
    if used_labels:
        label += "  ·  " + " ".join(used_labels)
    return cmd, label


# ---------------------------------------------------------------------------
# Feedback / curation helpers
# ---------------------------------------------------------------------------

# El servidor es threaded (ThreadedTCPServer). Todos los endpoints que
# modifican items.jsonl hacen read-modify-write del archivo ENTERO. Sin
# serializar, dos requests concurrentes (clics rápidos: aprobar varios, o
# aprobar + curar) se pisan — ambos leen el estado viejo y el último write
# gana, perdiendo los cambios del otro (p. ej. aprobaciones que "desaparecen").
# Este lock serializa la sección crítica load→modify→write de cada operación.
# OJO: NO decorar funciones que se llamen entre sí (deadlock — Lock no
# reentrante). _log_feedback queda SIN lock a propósito (sólo lee items.jsonl
# para snapshot + appendea a feedback.jsonl; lo llaman funciones ya bajo lock).
_ITEMS_LOCK = threading.Lock()


def _serialized(fn):
    """Serializa la ejecución de la función con _ITEMS_LOCK (read-modify-write
    atómico sobre items.jsonl)."""
    @functools.wraps(fn)
    def _wrapper(*args, **kwargs):
        with _ITEMS_LOCK:
            return fn(*args, **kwargs)
    return _wrapper


def _load_items() -> list[dict]:
    items: list[dict] = []
    if not ITEMS_PATH.exists():
        return items
    with ITEMS_PATH.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                items.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
    return items


def _write_items(items: list[dict]) -> None:
    tmp = ITEMS_PATH.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(ITEMS_PATH)


def _find_item_by_url(items: list[dict], url: str) -> dict | None:
    for it in items:
        if it.get("url") == url:
            return it
    return None


def _log_feedback(url: str, reason: str, action: str = "feedback",
                  extra: dict | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    item: dict = {}
    if ITEMS_PATH.exists():
        with ITEMS_PATH.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                    if row.get("url") == url:
                        item = row
                        break
                except json.JSONDecodeError:
                    pass

    entry = {**item, "action": action, "reason": reason, "submitted_at": now}
    if not item:
        entry["url"] = url
    if extra:
        entry.update(extra)

    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FEEDBACK_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _search_editions(query: str, limit: int = 15) -> list[dict]:
    """Search edition_keys by series/edition display name."""
    if not query or len(query) < 2:
        return []
    q = query.lower()
    items = _load_items()
    seen: dict[str, dict] = {}
    for it in items:
        ek = it.get("edition_key", "")
        if not ek or ek in seen:
            continue
        sd = (it.get("series_display") or "").lower()
        ed = (it.get("edition_display") or "").lower()
        sk = (it.get("series_key") or "").lower()
        if q in sd or q in ed or q in sk or q in ek:
            vol_count = sum(1 for i in items if i.get("edition_key") == ek)
            seen[ek] = {
                "edition_key": ek,
                "series_display": it.get("series_display", ""),
                "edition_display": it.get("edition_display", ""),
                "publisher": it.get("publisher", ""),
                "country": it.get("country", ""),
                "volume_count": vol_count,
            }
        if len(seen) >= limit:
            break
    return list(seen.values())


@_serialized
def _apply_move(item_url: str, to_edition_key: str, reason: str) -> str:
    """Move item to a different edition. Returns status message."""
    items = _load_items()
    item = _find_item_by_url(items, item_url)
    if not item:
        return "Item no encontrado"

    old_ek = item.get("edition_key", "")

    target_items = [i for i in items if i.get("edition_key") == to_edition_key]
    if not target_items:
        return f"Edición destino '{to_edition_key}' no existe"

    ref = target_items[0]
    item["edition_key"] = to_edition_key
    item["edition_display"] = ref.get("edition_display", "")
    item["series_key"] = ref.get("series_key", item.get("series_key", ""))
    item["series_display"] = ref.get("series_display", item.get("series_display", ""))
    vol = (item.get("volume") or "").strip()
    item["cluster_key"] = f"edition:{to_edition_key}|{vol}"

    # Modelo 1-fila-por-producto: si la edición destino ya tiene ESTE tomo,
    # mover crearía 2 filas con el mismo cluster_key. Consolidamos para que se
    # fusionen en una sola con sources[] unido. Idempotente.
    if consolidate_by_cluster is not None:
        items = consolidate_by_cluster(items)

    _write_items(items)
    _log_feedback(item_url, reason, action="move",
                  extra={"from_edition": old_ek, "to_edition": to_edition_key})
    return "ok"


@_serialized
def _apply_merge_items(item_url: str, duplicate_of_url: str,
                       reason: str) -> str:
    """Merge two duplicate items: keep the better one, remove the other."""
    items = _load_items()
    item_a = _find_item_by_url(items, item_url)
    item_b = _find_item_by_url(items, duplicate_of_url)
    if not item_a:
        return "Item origen no encontrado"
    if not item_b:
        return "Item destino no encontrado"

    url_a, url_b = item_a.get("url"), item_b.get("url")

    # Modelo 1-fila-por-producto: el usuario marca estos dos como el MISMO
    # producto (suelen tener cluster_key distinto, por eso aparecían como 2
    # cards). Los fusionamos en UNA fila con merge_cluster — une sources[],
    # imágenes (portada canónica primera) y extras, eligiendo la más completa
    # como canónica. NO borramos una perdiendo su fuente (bug del modelo viejo).
    if merge_cluster is not None:
        merged = merge_cluster([item_a, item_b])
    else:  # pragma: no cover — fallback degradado
        merged = item_a if item_a.get("score", 0) >= item_b.get("score", 0) else item_b
    kept_url = merged.get("url")
    dropped_url = url_b if kept_url == url_a else url_a

    items = [i for i in items if i.get("url") not in (url_a, url_b)]
    items.append(merged)
    _write_items(items)
    _log_feedback(item_url, reason, action="merge",
                  extra={"duplicate_of": duplicate_of_url,
                         "kept_url": kept_url,
                         "dropped_url": dropped_url})
    return "ok"


@_serialized
def _apply_remove(item_url: str, reason: str) -> str:
    """Remove item from its edition (set standalone edition_key)."""
    items = _load_items()
    item = _find_item_by_url(items, item_url)
    if not item:
        return "Item no encontrado"

    old_ek = item.get("edition_key", "")
    item["edition_key"] = ""
    item["edition_display"] = ""
    item["cluster_key"] = f"url:{item_url}"

    _write_items(items)
    _log_feedback(item_url, reason, action="remove",
                  extra={"from_edition": old_ek})
    return "ok"


@_serialized
def _apply_approve(item_url: str, approved: bool, reason: str = "") -> str:
    """Aprobar/desaprobar una card (golden record).

    Aprobar marca `approved_at` + `approved_by` en TODAS las filas que
    comparten el `cluster_key` del item clickeado (una card = un cluster).
    Para clusters standalone (`url:...`) toca sólo esa fila. Desaprobar
    limpia ambos campos. Además appendea un registro al log durable
    data/approvals.jsonl para poder re-aplicar tras una reconstrucción
    del catálogo (ver scripts/retrofit/apply_approvals.py).
    """
    items = _load_items()
    item = _find_item_by_url(items, item_url)
    if not item:
        return "Item no encontrado"

    cluster = item.get("cluster_key") or f"url:{item_url}"
    now = datetime.now(timezone.utc).isoformat()

    targets = [
        it for it in items
        if (it.get("cluster_key") or f"url:{it.get('url','')}") == cluster
    ]
    if not targets:
        targets = [item]

    for it in targets:
        if approved:
            it["approved_at"] = now
            it["approved_by"] = "owner"
        else:
            it["approved_at"] = ""
            it["approved_by"] = ""

    _write_items(items)

    entry = {
        "cluster_key": cluster,
        "url": item_url,
        "action": "approve" if approved else "unapprove",
        "approved_at": now if approved else "",
        "approved_by": "owner" if approved else "",
        "reason": reason,
        "submitted_at": now,
        # snapshot de campos congelados para auditoría / replay
        "series_key": item.get("series_key", ""),
        "edition_key": item.get("edition_key", ""),
        "title": item.get("title", ""),
        "volume": item.get("volume", ""),
    }
    APPROVALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with APPROVALS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return "ok"


def _log_dup_decision(signature: str, dup_key: str, decision: str,
                      urls: list[str]) -> None:
    """Registra una decisión sobre un grupo de 'posibles duplicados' en el log
    durable data/dup_decisions.jsonl. data_quality.py lo lee y NO vuelve a
    mostrar los grupos ya decididos (mismo `signature`). decision ∈
    'distinct' (son productos distintos, mantener separados) | 'merged'."""
    now = datetime.now(timezone.utc).isoformat()
    DUP_DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DUP_DECISIONS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "signature": signature,
            "dup_key": dup_key,
            "decision": decision,
            "urls": urls,
            "submitted_at": now,
        }, ensure_ascii=False) + "\n")


@_serialized
def _apply_dup_decide(signature: str, dup_key: str, urls: list[str]) -> str:
    """Marca un grupo de posibles duplicados como PRODUCTOS DISTINTOS: no toca
    items.jsonl, solo registra la decisión para no volver a sugerirlo."""
    _log_dup_decision(signature, dup_key, "distinct", urls)
    return "ok"


# Campos de IDENTIDAD que definen "de qué edición/producto se trata". Al unir
# duplicados, las fotos y tiendas se juntan SIEMPRE, pero estos campos se toman
# de UNA sola ficha (la elegida por el usuario, o la canónica por defecto) para
# no mezclar "Special" con "Special Edition" ni la editorial-tienda con la real.
_DUP_IDENTITY_FIELDS = (
    "title", "title_original", "series_key", "series_display",
    "edition_key", "edition_display", "volume", "publisher",
)


@_serialized
def _apply_dup_merge(signature: str, dup_key: str, urls: list[str],
                     keep_url: str = "") -> str:
    """Fusiona las filas del grupo (mismo producto en fichas distintas) en UNA
    sola con sources[] e imágenes unidas, vía merge_cluster (la primitiva
    canónica). La INFO de identidad (título/editorial/edición) se toma de
    `keep_url` si se indicó; si no, de la canónica que elige merge_cluster.
    Hace backup, recomputa cluster_key, y registra la decisión."""
    if merge_cluster is None:
        return "merge_cluster no disponible"
    urlset = {u for u in (urls or []) if u}
    if len(urlset) < 2:
        return "Necesito al menos 2 fichas para fusionar"
    items = _load_items()
    members = [it for it in items if it.get("url") in urlset]
    if len(members) < 2:
        return "No encontré las fichas a fusionar"
    merged = merge_cluster(members)
    # Override de identidad con la ficha elegida (fotos/tiendas ya están unidas).
    chosen = next((m for m in members if m.get("url") == keep_url), None) if keep_url else None
    if chosen:
        _ek_before = merged.get("edition_key", "")
        for f in _DUP_IDENTITY_FIELDS:
            v = chosen.get(f)
            if v not in (None, ""):
                merged[f] = v
        # Si cambió el edition_key, el slug viejo queda desincronizado: lo
        # limpiamos para que generate_slugs lo regenere (el panel ya lo flagea).
        if merged.get("edition_key", "") != _ek_before:
            merged.pop("slug", None)
    if derive_cluster_key is not None:
        merged["cluster_key"] = derive_cluster_key(merged)
    rest = [it for it in items if it.get("url") not in urlset]
    rest.append(merged)
    if backup_and_rotate is not None:
        backup_and_rotate(ITEMS_PATH, "dup-merge")
    _write_items(rest)
    _log_dup_decision(signature, dup_key, "merged", sorted(urlset))
    return "ok"


@_serialized
def _apply_approve_edition(edition_key: str, approved: bool, reason: str = "") -> tuple[str, int]:
    """Aprobar/desaprobar TODOS los tomos de una edición de una sola vez.

    Marca `approved_at`/`approved_by` en todas las filas con ese `edition_key`
    en una única reescritura atómica de items.jsonl (más eficiente que N
    requests). Loguea una entrada por cluster_key afectado a approvals.jsonl
    para que `apply_approvals.py` pueda re-materializarlas. Devuelve
    (status, n_filas_afectadas).
    """
    if not edition_key or edition_key.startswith("__solo__"):
        return "edition_key inválido", 0
    items = _load_items()
    now = datetime.now(timezone.utc).isoformat()
    affected = [it for it in items if it.get("edition_key") == edition_key]
    if not affected:
        return "Edición no encontrada", 0

    for it in affected:
        if approved:
            it["approved_at"] = now
            it["approved_by"] = "owner"
        else:
            it["approved_at"] = ""
            it["approved_by"] = ""

    _write_items(items)

    APPROVALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    seen_clusters: set[str] = set()
    with APPROVALS_PATH.open("a", encoding="utf-8") as fh:
        for it in affected:
            cluster = it.get("cluster_key") or f"url:{it.get('url','')}"
            if cluster in seen_clusters:
                continue
            seen_clusters.add(cluster)
            fh.write(json.dumps({
                "cluster_key": cluster,
                "url": it.get("url", ""),
                "action": "approve" if approved else "unapprove",
                "approved_at": now if approved else "",
                "approved_by": "owner" if approved else "",
                "reason": reason or f"bulk edition: {edition_key}",
                "submitted_at": now,
                "series_key": it.get("series_key", ""),
                "edition_key": edition_key,
                "title": it.get("title", ""),
                "volume": it.get("volume", ""),
            }, ensure_ascii=False) + "\n")

    return "ok", len(affected)


@_serialized
def _apply_batch_approve(item_urls: list[str], edition_keys: list[str],
                         approved: bool, reason: str = "") -> tuple[str, int]:
    """Aprobar/desaprobar muchas cards a la vez en UNA sola reescritura atómica.

    `item_urls` aporta clusters (cada url → todas las filas de su cluster_key);
    `edition_keys` aporta ediciones enteras (todas las filas con ese edition_key).
    Marca approved_at/by en la unión, escribe una vez, y loguea una entrada por
    cluster afectado a approvals.jsonl. Devuelve (status, n_filas).
    """
    items = _load_items()
    now = datetime.now(timezone.utc).isoformat()

    url_set = set(item_urls or [])
    ek_set = set(k for k in (edition_keys or []) if k and not k.startswith("__solo__"))

    # Clusters seleccionados vía item_urls (una card = un cluster).
    sel_clusters: set[str] = set()
    for it in items:
        if it.get("url") in url_set:
            sel_clusters.add(it.get("cluster_key") or f"url:{it.get('url','')}")

    affected: list[dict] = []
    for it in items:
        cl = it.get("cluster_key") or f"url:{it.get('url','')}"
        if cl in sel_clusters or it.get("edition_key") in ek_set:
            affected.append(it)
            if approved:
                it["approved_at"] = now
                it["approved_by"] = "owner"
            else:
                it["approved_at"] = ""
                it["approved_by"] = ""
    if not affected:
        return "Nada que aprobar", 0

    _write_items(items)

    APPROVALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    with APPROVALS_PATH.open("a", encoding="utf-8") as fh:
        for it in affected:
            cluster = it.get("cluster_key") or f"url:{it.get('url','')}"
            if cluster in seen:
                continue
            seen.add(cluster)
            fh.write(json.dumps({
                "cluster_key": cluster,
                "url": it.get("url", ""),
                "action": "approve" if approved else "unapprove",
                "approved_at": now if approved else "",
                "approved_by": "owner" if approved else "",
                "reason": reason or "batch via UI",
                "submitted_at": now,
                "series_key": it.get("series_key", ""),
                "edition_key": it.get("edition_key", ""),
                "title": it.get("title", ""),
                "volume": it.get("volume", ""),
            }, ensure_ascii=False) + "\n")

    return "ok", len(affected)


@_serialized
def _apply_batch_move(item_urls: list[str], to_edition_key: str,
                      reason: str = "") -> tuple[str, int]:
    """Mover muchos items a una edición destino en UNA sola reescritura.

    Reasigna edition/series + cluster_key de cada url y consolida UNA vez al
    final (modelo 1-fila-por-producto). Loguea cada move a feedback.jsonl.
    Devuelve (status, n_movidos).
    """
    if not to_edition_key:
        return "Falta to_edition", 0
    items = _load_items()
    target = [i for i in items if i.get("edition_key") == to_edition_key]
    if not target:
        return f"Edición destino '{to_edition_key}' no existe", 0
    ref = target[0]

    url_set = set(item_urls or [])
    moved: list[tuple[str, str]] = []  # (url, old_edition)
    for it in items:
        if it.get("url") in url_set and it.get("edition_key") != to_edition_key:
            old_ek = it.get("edition_key", "")
            it["edition_key"] = to_edition_key
            it["edition_display"] = ref.get("edition_display", "")
            it["series_key"] = ref.get("series_key", it.get("series_key", ""))
            it["series_display"] = ref.get("series_display", it.get("series_display", ""))
            vol = (it.get("volume") or "").strip()
            it["cluster_key"] = f"edition:{to_edition_key}|{vol}"
            moved.append((it.get("url", ""), old_ek))
    if not moved:
        return "Nada que mover", 0

    if consolidate_by_cluster is not None:
        items = consolidate_by_cluster(items)
    _write_items(items)

    for url, old_ek in moved:
        _log_feedback(url, reason or "batch move via UI", action="move",
                      extra={"from_edition": old_ek, "to_edition": to_edition_key})
    return "ok", len(moved)


# El editor inline del detalle permite editar CUALQUIER atributo del item,
# EXCEPTO estos dos grupos:
#
# 1. _PROTECTED_ITEM_FIELDS — las imágenes tienen su propio gestor
#    (image-manager.html / endpoint /api/image-manager/save). Editarlas desde
#    acá rompería la convención images[] (portada por posición = images[0],
#    única fuente de verdad). image_url/image_local son campos legacy ELIMINADOS
#    del row; se dejan acá por si llega un payload viejo con esas keys (se ignora).
_PROTECTED_ITEM_FIELDS = frozenset({
    "image_url", "image_local", "images", "images_backfilled_at",
})
# 2. _ROW_LOCAL_FIELDS — campos de IDENTIDAD/estructura de la FILA. Se aplican
#    SOLO a la fila abierta, nunca a las hermanas del cluster: son per-fila (la
#    url es la clave de upsert; cluster_key/slug identifican la fila; sources[]
#    es la lista de fuentes de esa fila concreta). El resto de campos (metadata
#    de PRODUCTO: title/author/price/…) sí se propaga a todas las filas del
#    cluster, como el gestor de imágenes, para que el dato editado no reaparezca
#    desde una fila hermana al re-mergear el detalle.
_ROW_LOCAL_FIELDS = frozenset({
    "url", "slug", "cluster_key", "content_hash", "source_url", "sources",
})


@_serialized
def _apply_item_update(item_url: str, fields: dict) -> tuple[bool, dict]:
    """Edición manual de metadata desde el detalle del dashboard.

    Acepta CUALQUIER campo salvo _PROTECTED_ITEM_FIELDS (imágenes). Preserva el
    tipo de cada valor tal como lo manda el cliente (str/int/float/list/dict),
    no lo coacciona a str. Los campos de _ROW_LOCAL_FIELDS se escriben SOLO a la
    fila abierta; el resto se propaga a todas las filas del cluster. Loguea el
    cambio a data/edits.jsonl (auditoría). Devuelve (ok, campos_aplicados).

    NO recomputa cluster_key automáticamente: la reagrupación estructural por
    arrastre tiene su propio flujo (`/api/curation/move`). Si el owner edita
    cluster_key/edition_key/etc. a mano desde el editor avanzado, es a propósito.
    """
    clean = {k: v for k, v in (fields or {}).items()
             if k not in _PROTECTED_ITEM_FIELDS}
    if not clean:
        return False, {}

    items = _load_items()
    item = _find_item_by_url(items, item_url)
    if not item:
        return False, {}

    cluster = item.get("cluster_key") or ""
    # Campos de producto (se propagan al cluster) vs de fila (solo la abierta).
    cluster_fields = {k: v for k, v in clean.items() if k not in _ROW_LOCAL_FIELDS}

    def _is_sibling(row: dict) -> bool:
        # Hermanas = misma fila de cluster real (no standalone url:).
        if row is item:
            return False
        if cluster and not cluster.startswith("url:"):
            return (row.get("cluster_key") or "") == cluster
        return False

    n = 0
    for row in items:
        if row is item:
            row.update(clean)            # la fila abierta recibe TODO
            n += 1
        elif _is_sibling(row) and cluster_fields:
            row.update(cluster_fields)   # las hermanas, solo metadata de producto
            n += 1

    _write_items(items)

    now = datetime.now(timezone.utc).isoformat()
    EDITS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EDITS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "url": item_url,
            "cluster_key": cluster,
            "rows_updated": n,
            "fields": clean,
            "submitted_at": now,
        }, ensure_ascii=False) + "\n")
    return True, clean


# ---------------------------------------------------------------------------
# Image manager helpers
# ---------------------------------------------------------------------------

def _image_file_sizes() -> dict[str, int]:
    """Return {filename: size_bytes} for all files in data/images/."""
    sizes: dict[str, int] = {}
    if not IMAGES_DIR.exists():
        return sizes
    for p in IMAGES_DIR.iterdir():
        if p.is_file() and not p.name.startswith(".") and not p.name.endswith(".tmp"):
            sizes[p.name] = p.stat().st_size
    return sizes


@_serialized
def _update_item_images(item_url: str, images: list[dict]) -> tuple[bool, list[str]]:
    """Rewrite item's images[] in items.jsonl.

    Returns (success, deleted_files) — deleted_files lists local filenames
    that were in the old images but not in the new ones AND are not referenced
    by any other item. Those files are deleted from disk.
    """
    if not ITEMS_PATH.exists():
        return False, []
    lines = ITEMS_PATH.read_text(encoding="utf-8").splitlines()

    # El gestor opera a nivel CLUSTER: el set de imágenes editado se aplica a
    # TODAS las filas del cluster (mismo cluster_key), no solo a la fila abierta.
    # Así el detalle (que hace union del cluster) y el gestor muestran siempre lo
    # mismo, y borrar una foto no reaparece desde una fila hermana. Para clusters
    # `url:` (standalone) o sin cluster_key, solo se toca la fila por su url.
    target_cluster = ""
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if row.get("url") == item_url:
            ck = row.get("cluster_key") or ""
            if ck and not ck.startswith("url:"):
                target_cluster = ck
            break

    def _is_target(row: dict) -> bool:
        if target_cluster:
            return (row.get("cluster_key") or "") == target_cluster
        return row.get("url") == item_url

    found = False
    old_locals: set[str] = set()
    new_locals: set[str] = {img.get("local", "") for img in images} - {""}
    new_lines = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            new_lines.append(raw)
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError:
            new_lines.append(raw)
            continue
        if _is_target(row):
            found = True
            for img in row.get("images", []):
                loc = img.get("local", "")
                if loc:
                    old_locals.add(loc)
            # images[0] es la portada (única fuente de verdad). Ya no hay campos
            # top-level image_url/image_local que sincronizar.
            row["images"] = [dict(im) for im in images]
            new_lines.append(json.dumps(row, ensure_ascii=False))
        else:
            new_lines.append(raw)
    if not found:
        return False, []
    tmp = ITEMS_PATH.with_suffix(".tmp")
    tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    tmp.replace(ITEMS_PATH)

    removed_locals = old_locals - new_locals
    deleted_files: list[str] = []
    if removed_locals:
        all_referenced: set[str] = set()
        for raw in tmp.parent.joinpath("items.jsonl").read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            for img in row.get("images", []):
                loc = img.get("local", "")
                if loc:
                    all_referenced.add(loc)
            # sources[] per-fuente conserva su propio image_local: contarlo evita
            # borrar un archivo todavía referenciado por una entrada de fuente.
            for s in (row.get("sources") or []):
                if isinstance(s, dict) and s.get("image_local"):
                    all_referenced.add(s["image_local"])
        # cover_preview.json también referencia archivos del espejo (old_image /
        # new_image / candidates[].new_image) — mismo set que el GC de
        # mirror_images.py. Sin esto, borrar una foto de galería que además es
        # referencia de una candidata pendiente deja el panel de review roto.
        preview_path = ROOT / "data" / "cover_preview.json"
        if preview_path.exists():
            try:
                for e in json.loads(preview_path.read_text(encoding="utf-8")):
                    for v in (e.get("old_image"), e.get("new_image")):
                        if v and v != "[dry-run]":
                            all_referenced.add(v)
                    for c in (e.get("candidates") or []):
                        v = c.get("new_image")
                        if v and v != "[dry-run]":
                            all_referenced.add(v)
            except (ValueError, OSError):
                pass
        for orphan in removed_locals:
            if orphan not in all_referenced:
                p = IMAGES_DIR / orphan
                if p.exists():
                    p.unlink()
                    deleted_files.append(orphan)
    return True, deleted_files


def _download_image_to_store(image_url: str) -> tuple[str, str]:
    """Download image to data/images/. Returns (filename, '') on success or ('', error_msg) on failure."""
    import hashlib
    import urllib.request

    if not image_url or not image_url.strip().startswith(("http://", "https://")):
        return "", "URL invalida"
    image_url = image_url.strip()

    _MAGIC = {
        b"\xff\xd8\xff": ".jpg",
        b"\x89PNG\r\n\x1a\n": ".png",
        b"GIF87a": ".gif", b"GIF89a": ".gif",
    }

    def _ext(body: bytes) -> str:
        for sig, ext in _MAGIC.items():
            if body[:len(sig)] == sig:
                return ext
        if len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP":
            return ".webp"
        if len(body) >= 12 and body[4:12] in (b"ftypavif", b"ftypavis"):
            return ".avif"
        return ""

    stem = hashlib.sha256(image_url.encode("utf-8")).hexdigest()[:16]
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    for existing in sorted(IMAGES_DIR.glob(stem + ".*")):
        if existing.is_file() and not existing.name.endswith(".tmp"):
            return existing.name, ""

    try:
        req = urllib.request.Request(image_url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read(12 * 1024 * 1024)
    except Exception as e:
        return "", f"Error descargando: {e}"

    ext = _ext(body)
    if not ext:
        return "", "El archivo descargado no es una imagen valida (HTML de error o formato desconocido)"

    filename = stem + ext
    dest = IMAGES_DIR / filename
    tmp = dest.with_name(f"{dest.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_bytes(body)
        tmp.replace(dest)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        return "", f"Error escribiendo archivo: {e}"
    return filename, ""


def _scrape_images_from_page(page_url: str) -> list[dict]:
    """Fetch a page and extract image URLs."""
    import re
    import urllib.request
    try:
        req = urllib.request.Request(page_url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return []
    from urllib.parse import urljoin
    results: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(r'<img[^>]+>', html, re.I):
        tag = m.group(0)
        url = ""
        alt = ""
        for attr in ("data-src", "data-lazy-src", "data-large_image", "data-zoom-image", "src"):
            am = re.search(rf'{attr}\s*=\s*["\']([^"\']+)["\']', tag, re.I)
            if am:
                u = am.group(1).strip()
                if u and not u.startswith("data:") and u.lower().startswith(("http", "//")):
                    url = urljoin(page_url, u)
                    break
        am = re.search(r'alt\s*=\s*["\']([^"\']*)["\']', tag, re.I)
        if am:
            alt = am.group(1).strip()
        if url and url not in seen:
            ext = url.rsplit(".", 1)[-1].lower().split("?")[0]
            if ext in ("jpg", "jpeg", "png", "webp", "gif", "avif"):
                seen.add(url)
                results.append({"url": url, "alt": alt})
    return results


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class MangaWatchHandler(http.server.SimpleHTTPRequestHandler):
    """Sirve la raíz del proyecto + todos los endpoints /api/*."""

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A002
        sys.stderr.write("[serve] " + (fmt % args) + "\n")

    # ---------- helpers ----------

    def _serve_file(self, filepath: Path) -> None:
        """Sirve un archivo directamente con el content-type correcto."""
        import mimetypes
        if not filepath.exists():
            self.send_error(404, "Not Found")
            return
        ctype, _ = mimetypes.guess_type(str(filepath))
        content = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        try:
            self.wfile.write(content)
        except BrokenPipeError:
            pass

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _read_json(self, max_bytes: int = 5_000_000) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > max_bytes:
            raise ValueError("body vacío u oversized")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    # ---------- GET ----------

    def do_GET(self) -> None:
        # Páginas HTML accesibles directamente en la raíz (sin /web/ en la URL)
        _HTML_ALIASES = {
            "/":                  ROOT / "web" / "index.html",
            "/index.html":        ROOT / "web" / "index.html",
            "/panel.html":        ROOT / "web" / "panel.html",
            "/cover-preview.html": ROOT / "web" / "cover-preview.html",
            "/image-manager.html": ROOT / "web" / "image-manager.html",
            "/quality.html":      ROOT / "web" / "quality.html",
        }
        # Comparar sin el query string: /image-manager.html?item=... debe
        # matchear el alias /image-manager.html (el query lo lee el JS del
        # cliente vía window.location.search, no afecta qué archivo servir).
        _path_only = self.path.split("?", 1)[0]
        if _path_only in _HTML_ALIASES:
            self._serve_file(_HTML_ALIASES[_path_only])
            return

        # Curation API (GET)
        if self.path.startswith("/api/editions/search?"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            q = (qs.get("q") or [""])[0]
            results = _search_editions(q)
            self._json(200, {"results": results})
            return

        # Panel API
        if self.path == "/api/health":
            self._json(200, {"ok": True, "ts": datetime.now(timezone.utc).isoformat()})
            return
        if self.path == "/api/image-file-sizes":
            self._json(200, _image_file_sizes())
            return
        if self.path == "/api/scripts":
            self._json(200, {"scripts": SCRIPTS})
            return
        if self.path == "/api/jobs":
            self._json(200, {"jobs": [j.to_dict() for j in JOBS.list()]})
            return
        if self.path.startswith("/api/jobs/"):
            rest = self.path[len("/api/jobs/"):]
            parts = rest.split("/", 1)
            jid = parts[0]
            sub = parts[1] if len(parts) > 1 else ""
            job = JOBS.get(jid)
            if not job:
                self._json(404, {"error": "job not found"})
                return
            if sub == "":
                self._json(200, job.to_dict(include_lines=True))
                return
            if sub == "stream":
                self._stream_job(job)
                return
            self._json(404, {"error": "endpoint desconocido"})
            return

        # Archivos estáticos (web/, data/, reports/, etc.)
        return super().do_GET()

    # ---------- POST ----------

    def do_POST(self) -> None:
        # Panel API
        if self.path == "/api/run":
            self._handle_run()
            return
        if self.path.startswith("/api/jobs/") and self.path.endswith("/stop"):
            jid = self.path[len("/api/jobs/"):-len("/stop")]
            ok = JOBS.stop(jid)
            self._json(200 if ok else 400, {"ok": ok})
            return

        # Catalog API
        if self.path == "/api/feedback":
            self._handle_feedback()
            return
        if self.path == "/api/curation/move":
            self._handle_curation_move()
            return
        if self.path == "/api/curation/merge":
            self._handle_curation_merge()
            return
        if self.path == "/api/curation/remove":
            self._handle_curation_remove()
            return
        if self.path == "/api/item/update":
            self._handle_item_update()
            return
        if self.path == "/api/approve":
            self._handle_approve()
            return
        if self.path == "/api/approve-edition":
            self._handle_approve_edition()
            return
        if self.path == "/api/batch/approve":
            self._handle_batch_approve()
            return
        if self.path == "/api/batch/move":
            self._handle_batch_move()
            return
        if self.path == "/api/quality/check":
            self._handle_quality_check()
            return
        if self.path == "/api/dup/decide":
            self._handle_dup_decide()
            return
        if self.path == "/api/dup/merge":
            self._handle_dup_merge()
            return
        if self.path == "/api/save-cover-preview":
            self._handle_save_cover_preview()
            return
        if self.path == "/api/apply-cover-preview":
            self._handle_apply_cover_preview()
            return

        # Image manager API
        if self.path == "/api/image-manager/save":
            self._handle_image_save()
            return
        if self.path == "/api/image-search":
            self._handle_image_search()
            return
        if self.path == "/api/image-manager/download":
            self._handle_image_download()
            return
        if self.path == "/api/image-manager/scrape":
            self._handle_image_scrape()
            return

        self.send_error(404, "Not Found")

    # ---------- Panel: run + SSE ----------

    def _handle_run(self) -> None:
        try:
            payload = self._read_json(max_bytes=200_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"Invalid body: {e}"})
            return

        script_id = (payload.get("script_id") or "").strip()
        flags = payload.get("flags") or {}
        if not isinstance(flags, dict):
            self._json(400, {"error": "'flags' debe ser dict"})
            return

        cmd, label = build_command(script_id, flags)
        if cmd is None:
            self._json(400, {"error": label})
            return

        # Resolver python del venv si existe.
        if cmd and cmd[0] == ".venv/bin/python":
            candidate = ROOT / ".venv" / "bin" / "python"
            cmd[0] = str(candidate) if candidate.exists() else sys.executable

        job = JOBS.start(script_id, cmd, label, cwd=ROOT)
        self._json(200, {"job_id": job.id, "label": label, "command": cmd})

    def _stream_job(self, job: Job) -> None:
        """Server-Sent Events stream del stdout del job."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()

        sent = 0
        last_keepalive = time.monotonic()
        try:
            while True:
                with job.cv:
                    while len(job.lines) <= sent and job.status == "running":
                        job.cv.wait(timeout=15)
                    snapshot = list(job.lines)[sent:]
                    finished = job.status != "running"

                for line in snapshot:
                    data = json.dumps({"line": line}, ensure_ascii=False)
                    self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                sent += len(snapshot)

                now = time.monotonic()
                if not snapshot and not finished and (now - last_keepalive) > 14:
                    self.wfile.write(b": keepalive\n\n")
                    last_keepalive = now
                elif snapshot:
                    last_keepalive = now

                self.wfile.flush()

                if finished:
                    end_data = json.dumps({
                        "status": job.status,
                        "exit_code": job.exit_code,
                        "ended_at": job.ended_at,
                    }, ensure_ascii=False)
                    self.wfile.write(b"event: end\n")
                    self.wfile.write(f"data: {end_data}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    return
        except (BrokenPipeError, ConnectionResetError):
            return

    # ---------- Catalog handlers ----------

    def _handle_feedback(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 100_000:
            self.send_error(400, "Empty or oversized body")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self.send_error(400, f"Invalid JSON: {e}")
            return

        title  = (payload.get("title") or "").strip()
        url    = (payload.get("url") or "").strip()
        reason = (payload.get("reason") or "").strip()

        if not title or not url or not reason:
            self.send_error(400, "Missing 'title', 'url' or 'reason'")
            return

        _log_feedback(url, reason, action="feedback")
        self._json(200, {"ok": True})

    def _handle_curation_move(self) -> None:
        try:
            payload = self._read_json(max_bytes=100_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"Invalid body: {e}"})
            return
        url = (payload.get("url") or "").strip()
        to_edition = (payload.get("to_edition") or "").strip()
        reason = (payload.get("reason") or "").strip()
        if not url or not to_edition:
            self._json(400, {"error": "Missing 'url' or 'to_edition'"})
            return
        result = _apply_move(url, to_edition, reason or "moved via UI")
        if result == "ok":
            self._json(200, {"ok": True})
        else:
            self._json(400, {"error": result})

    def _handle_curation_merge(self) -> None:
        try:
            payload = self._read_json(max_bytes=100_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"Invalid body: {e}"})
            return
        url = (payload.get("url") or "").strip()
        duplicate_of = (payload.get("duplicate_of") or "").strip()
        reason = (payload.get("reason") or "").strip()
        if not url or not duplicate_of:
            self._json(400, {"error": "Missing 'url' or 'duplicate_of'"})
            return
        result = _apply_merge_items(url, duplicate_of, reason or "merged via UI")
        if result == "ok":
            self._json(200, {"ok": True})
        else:
            self._json(400, {"error": result})

    def _handle_curation_remove(self) -> None:
        try:
            payload = self._read_json(max_bytes=100_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"Invalid body: {e}"})
            return
        url = (payload.get("url") or "").strip()
        reason = (payload.get("reason") or "").strip()
        if not url:
            self._json(400, {"error": "Missing 'url'"})
            return
        result = _apply_remove(url, reason or "removed via UI")
        if result == "ok":
            self._json(200, {"ok": True})
        else:
            self._json(400, {"error": result})

    def _handle_item_update(self) -> None:
        try:
            payload = self._read_json(max_bytes=200_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"Invalid body: {e}"})
            return
        url = (payload.get("url") or "").strip()
        fields = payload.get("fields")
        if not url or not isinstance(fields, dict):
            self._json(400, {"error": "Missing 'url' or 'fields'"})
            return
        ok, applied = _apply_item_update(url, fields)
        if ok:
            self._json(200, {"ok": True, "fields": applied})
        else:
            self._json(400, {"error": "Item no encontrado o sin campos válidos"})

    def _handle_approve(self) -> None:
        try:
            payload = self._read_json(max_bytes=100_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"Invalid body: {e}"})
            return
        url = (payload.get("url") or "").strip()
        approved = bool(payload.get("approved", True))
        reason = (payload.get("reason") or "").strip()
        if not url:
            self._json(400, {"error": "Missing 'url'"})
            return
        result = _apply_approve(url, approved, reason or "approved via UI")
        if result == "ok":
            self._json(200, {"ok": True, "approved": approved})
        else:
            self._json(400, {"error": result})

    def _handle_approve_edition(self) -> None:
        try:
            payload = self._read_json(max_bytes=100_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"Invalid body: {e}"})
            return
        edition_key = (payload.get("edition_key") or "").strip()
        approved = bool(payload.get("approved", True))
        reason = (payload.get("reason") or "").strip()
        if not edition_key:
            self._json(400, {"error": "Missing 'edition_key'"})
            return
        result, n = _apply_approve_edition(edition_key, approved, reason or "approved edition via UI")
        if result == "ok":
            self._json(200, {"ok": True, "approved": approved, "count": n})
        else:
            self._json(400, {"error": result})

    def _handle_batch_approve(self) -> None:
        try:
            payload = self._read_json(max_bytes=2_000_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"Invalid body: {e}"})
            return
        urls = payload.get("urls") or []
        edition_keys = payload.get("edition_keys") or []
        approved = bool(payload.get("approved", True))
        reason = (payload.get("reason") or "").strip()
        if not isinstance(urls, list) or not isinstance(edition_keys, list):
            self._json(400, {"error": "'urls'/'edition_keys' deben ser listas"})
            return
        if not urls and not edition_keys:
            self._json(400, {"error": "Selección vacía"})
            return
        result, n = _apply_batch_approve(urls, edition_keys, approved, reason)
        if result == "ok":
            self._json(200, {"ok": True, "approved": approved, "count": n})
        else:
            self._json(400, {"error": result})

    def _handle_batch_move(self) -> None:
        try:
            payload = self._read_json(max_bytes=2_000_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"Invalid body: {e}"})
            return
        urls = payload.get("urls") or []
        to_edition = (payload.get("to_edition") or "").strip()
        reason = (payload.get("reason") or "").strip()
        if not isinstance(urls, list) or not urls:
            self._json(400, {"error": "Selección vacía"})
            return
        if not to_edition:
            self._json(400, {"error": "Falta 'to_edition'"})
            return
        result, n = _apply_batch_move(urls, to_edition, reason)
        if result == "ok":
            self._json(200, {"ok": True, "count": n})
        else:
            self._json(400, {"error": result})

    def _handle_quality_check(self) -> None:
        """Re-evalúa SOLO los items pedidos (live-update del Panel de Calidad).

        Devuelve {results: {url: [cat_ids que aún dispara]}}. Es de SOLO LECTURA
        (no toca items.jsonl), por eso no necesita @_serialized."""
        try:
            payload = self._read_json(max_bytes=200_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"Invalid body: {e}"})
            return
        urls = payload.get("urls") or []
        if not isinstance(urls, list) or not urls:
            self._json(400, {"error": "Falta 'urls' (lista)"})
            return
        audit_dir = str(ROOT / "scripts" / "audit")
        if audit_dir not in sys.path:
            sys.path.insert(0, audit_dir)
        try:
            import data_quality as _dq  # type: ignore
            items = _load_items()
            results = _dq.check_urls(urls[:500], items=items)
        except Exception as e:  # pragma: no cover
            self._json(500, {"error": f"recheck falló: {e}"})
            return
        self._json(200, {"results": results})

    def _handle_dup_decide(self) -> None:
        """Marca un grupo de posibles duplicados como productos DISTINTOS
        (no se vuelve a sugerir). Body: {signature, dup_key, urls}."""
        try:
            payload = self._read_json(max_bytes=200_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"Invalid body: {e}"})
            return
        sig = (payload.get("signature") or "").strip()
        dup_key = (payload.get("dup_key") or "").strip()
        urls = [u for u in (payload.get("urls") or []) if u]
        if not sig or not urls:
            self._json(400, {"error": "Falta 'signature' o 'urls'"})
            return
        result = _apply_dup_decide(sig, dup_key, urls)
        if result == "ok":
            self._json(200, {"ok": True})
        else:
            self._json(400, {"error": result})

    def _handle_dup_merge(self) -> None:
        """Fusiona las fichas de un grupo de duplicados en una sola.
        Body: {signature, dup_key, urls}."""
        try:
            payload = self._read_json(max_bytes=200_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"Invalid body: {e}"})
            return
        sig = (payload.get("signature") or "").strip()
        dup_key = (payload.get("dup_key") or "").strip()
        urls = [u for u in (payload.get("urls") or []) if u]
        keep_url = (payload.get("keep_url") or "").strip()
        if not sig or len(urls) < 2:
            self._json(400, {"error": "Faltan 'signature' / al menos 2 'urls'"})
            return
        result = _apply_dup_merge(sig, dup_key, urls, keep_url)
        if result == "ok":
            self._json(200, {"ok": True})
        else:
            self._json(400, {"error": result})

    @_serialized
    def _handle_save_cover_preview(self) -> None:
        """Persiste la cola de candidatas. Va bajo @_serialized para no pisar
        un apply concurrente (gotcha #34), y escribe atómico (tmp + replace)
        para no dejar JSON truncado si el proceso muere a mitad del write."""
        try:
            entries = self._read_json(max_bytes=5_000_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self.send_error(400, f"Invalid body: {e}")
            return
        if not isinstance(entries, list):
            self.send_error(400, "Expected JSON array")
            return
        dst = ROOT / "data" / "cover_preview.json"
        tmp = dst.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(dst)
        self._json(200, {"ok": True, "saved": len(entries)})

    @_serialized
    def _handle_apply_cover_preview(self) -> None:
        """Aplica al catálogo las candidatas APROBADAS del cover_preview.json y
        quita del JSON las decididas (aprobadas + rechazadas), dejando solo las
        pendientes. Reusa apply_preview() de fetch_better_covers. Muta items.jsonl
        + borra archivos huérfanos → va bajo @_serialized (gotcha #34)."""
        retro_dir = str(ROOT / "scripts" / "retrofit")
        if retro_dir not in sys.path:
            sys.path.insert(0, retro_dir)
        try:
            import fetch_better_covers as _fbc  # type: ignore
            # apply_preview lee su _PREVIEW_PATH global; lo apuntamos al archivo real.
            _fbc._PREVIEW_PATH = ROOT / "data" / "cover_preview.json"
            summary = _fbc.apply_preview(ITEMS_PATH, IMAGES_DIR)
        except Exception as e:  # noqa: BLE001
            self._json(500, {"ok": False, "error": str(e)})
            return
        self._json(200, summary or {"ok": True, "applied": 0})

    # ---------- Image manager handlers ----------

    def _handle_image_save(self) -> None:
        try:
            payload = self._read_json(max_bytes=1_000_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"Invalid body: {e}"})
            return
        item_url = (payload.get("item_url") or "").strip()
        images = payload.get("images")
        if not item_url or not isinstance(images, list):
            self._json(400, {"error": "Missing 'item_url' or 'images'"})
            return
        ok, deleted = _update_item_images(item_url, images)
        if ok:
            self._json(200, {"ok": True, "deleted_files": deleted})
        else:
            self._json(404, {"error": "Item not found"})

    def _handle_image_download(self) -> None:
        try:
            payload = self._read_json(max_bytes=100_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"Invalid body: {e}"})
            return
        image_url = (payload.get("image_url") or "").strip()
        if not image_url:
            self._json(400, {"error": "Missing 'image_url'"})
            return
        local, err = _download_image_to_store(image_url)
        if local:
            file_size = 0
            try:
                file_size = (IMAGES_DIR / local).stat().st_size
            except OSError:
                pass
            self._json(200, {"ok": True, "local": local, "url": image_url, "file_size": file_size})
        else:
            self._json(422, {"error": err or "Failed to download image"})

    def _handle_image_search(self) -> None:
        """Busca portadas candidatas para un item (búsqueda integrada del gestor).

        Reúsa la infra de scripts/retrofit/fetch_better_covers.py:
          - por ISBN → Amazon CDN + PRH CDN + OpenLibrary + Google Books (gratis)
          - por texto → Tavily Search API con include_images (TAVILY_API_KEY en .env)
        Devuelve solo las URLs candidatas; el frontend las muestra y, al elegir
        una, la baja con /api/image-manager/download. Solo lectura."""
        try:
            payload = self._read_json(max_bytes=100_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"Invalid body: {e}"})
            return
        query = (payload.get("query") or "").strip()
        isbn = (payload.get("isbn") or "").strip()
        if not query and not isbn:
            self._json(400, {"error": "Falta 'query' o 'isbn'"})
            return

        retro_dir = str(ROOT / "scripts" / "retrofit")
        if retro_dir not in sys.path:
            sys.path.insert(0, retro_dir)
        try:
            import fetch_better_covers as _fbc  # type: ignore
            import requests  # type: ignore
            _fbc._load_dotenv()
            session = requests.Session()
            session.headers.update({"User-Agent": "manga-watch-personal/0.2"})
            urls: list[str] = []
            if isbn:
                for fn in ("_candidates_from_isbn",
                           "_candidates_from_isbn_openlibrary",
                           "_candidates_from_isbn_google_books"):
                    try:
                        urls += list(getattr(_fbc, fn)(isbn, session) or [])
                    except Exception:
                        pass
            serper_key = os.environ.get("SERPER_API_KEY", "")
            tavily_key = os.environ.get("TAVILY_API_KEY", "")
            serper_hits: list[str] = []
            if query and serper_key:
                try:
                    # _search_serper_for_cover devuelve dicts con campo "url"
                    for hit in (_fbc._search_serper_for_cover(query, serper_key, session) or []):
                        u = hit.get("url") if isinstance(hit, dict) else hit
                        if u:
                            serper_hits.append(u)
                except Exception:
                    pass
            urls += serper_hits
            # Tavily como fallback: solo si Serper no dio resultados o no hay key
            if query and tavily_key and not serper_hits:
                try:
                    urls += list(_fbc._search_tavily_for_cover(query, tavily_key, session) or [])
                except Exception:
                    pass
            seen: set[str] = set()
            out: list[str] = []
            for u in urls:
                if u and u not in seen:
                    seen.add(u)
                    out.append(u)
            self._json(200, {
                "results": out,
                "serper": bool(serper_key),
                "tavily": bool(tavily_key),
                "isbn_used": bool(isbn),
            })
        except Exception as e:  # pragma: no cover
            self._json(500, {"error": f"búsqueda falló: {e}"})

    def _handle_image_scrape(self) -> None:
        try:
            payload = self._read_json(max_bytes=100_000)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            self._json(400, {"error": f"Invalid body: {e}"})
            return
        page_url = (payload.get("page_url") or "").strip()
        if not page_url:
            self._json(400, {"error": "Missing 'page_url'"})
            return
        images = _scrape_images_from_page(page_url)
        self._json(200, {"images": images, "count": len(images)})


# ---------------------------------------------------------------------------
# Server — threaded para soportar SSE + peticiones concurrentes
# ---------------------------------------------------------------------------

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--bind", default="0.0.0.0")
    args = parser.parse_args()

    os.chdir(ROOT)

    print("==> Manga Watch")
    print(f"    Raíz:    {ROOT}")
    print(f"    URL:     http://localhost:{args.port}/")
    print(f"    Panel:   http://localhost:{args.port}/web/panel.html")
    if not _REGISTRY_OK:
        print("    ⚠️  script_registry no encontrado — /api/run deshabilitado")
    print()

    with ThreadedTCPServer((args.bind, args.port), MangaWatchHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[OK] server detenido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
