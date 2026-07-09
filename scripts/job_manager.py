"""job_manager.py — Job/JobManager compartidos por scripts/serve.py y
scripts/admin_serve.py (Fable audit B17, 2026-07-08).

Antes de este módulo, `Job` y `JobManager` estaban duplicadas BYTE A BYTE en
ambos servers (~scripts/serve.py:180 y ~scripts/admin_serve.py:83). La parte
grave de esa duplicación — `build_command`/`resolve_preset_env`/`mutates_items`
divergentes — ya se había unificado en `scripts/script_registry.py` (4.1,
2026-07-08); este módulo cierra el resto: la clase que corre subprocesos y
reparte sus logs vía SSE.

Diff real entre las dos copias (verificado con `diff` antes de extraer, no
solo lectura): NINGUNA diferencia de comportamiento. Lo único que divergía
legítimamente era el PREFIJO de las líneas de log que cada server inyecta en
el buffer del job ("[serve] PID ..." vs "[admin_serve] PID ...") — acá es el
parámetro `log_prefix` de `JobManager`. Todo lo demás (docstrings, un `if`
partido en dos líneas en `stop()`, un dict con/sin anotación de tipo) era
cosmético.

`mutates_items` se recibe INYECTADO (no se importa `script_registry` acá) a
propósito: serve.py resuelve `mutates_items` con un fallback stub (`lambda
sid: False`) cuando `script_registry` no está disponible (ver el try/except
de su import), y admin_serve.py lo importa sin fallback. Si este módulo
importara `script_registry` directamente perderíamos ese fallback y
acoplaríamos job_manager.py a un módulo que no necesita conocer.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# Ambos servers usaban los mismos valores (5000 líneas bufferizadas por job,
# 30 jobs terminados retenidos en memoria para inspección) — quedan acá como
# default y overrideables por instancia de JobManager si algún server
# necesita otra cosa en el futuro.
DEFAULT_MAX_BUFFERED_LINES = 5000
DEFAULT_MAX_FINISHED_JOBS = 30


class Job:
    """Un proceso en ejecución (o terminado) con sus logs y suscriptores SSE."""

    __slots__ = (
        "id", "script_id", "label", "command", "status", "started_at",
        "ended_at", "exit_code", "process", "lines", "lock", "cv", "version",
    )

    def __init__(self, script_id: str, label: str, command: list[str],
                 *, max_buffered_lines: int = DEFAULT_MAX_BUFFERED_LINES) -> None:
        self.id: str = uuid.uuid4().hex[:12]
        self.script_id: str = script_id
        self.label: str = label
        self.command: list[str] = command
        self.status: str = "running"  # running | exited | error | killed
        self.started_at: str = datetime.now(timezone.utc).isoformat()
        self.ended_at: str | None = None
        self.exit_code: int | None = None
        self.process: subprocess.Popen[bytes] | None = None
        self.lines: deque[str] = deque(maxlen=max_buffered_lines)
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
    def __init__(
        self,
        *,
        log_prefix: str = "job",
        max_buffered_lines: int = DEFAULT_MAX_BUFFERED_LINES,
        max_finished_jobs: int = DEFAULT_MAX_FINISHED_JOBS,
        mutates_items: Callable[[str], bool] | None = None,
    ) -> None:
        """log_prefix identifica quién escribió cada línea de log inyectada
        por el manager (PID/errores/SIGTERM) — "serve" o "admin_serve" en los
        dos usos actuales. mutates_items es inyectado por el caller (ver
        docstring del módulo) para no acoplar este módulo a script_registry."""
        self.jobs: dict[str, Job] = {}
        self.order: deque[str] = deque()
        self.lock = threading.Lock()
        self._log_prefix = log_prefix
        self._max_buffered_lines = max_buffered_lines
        self._max_finished_jobs = max_finished_jobs
        self._mutates_items = mutates_items or (lambda script_id: False)

    def start(self, script_id: str, command: list[str], label: str,
              cwd: Path, env: dict[str, str] | None = None,
              *, block_if_mutator: bool = False) -> tuple[Job | None, Job | None]:
        """Registra y lanza un job. Devuelve (job, None) o (None, blocker).

        block_if_mutator=True hace el chequeo "¿hay un mutador corriendo?" +
        el registro del job nuevo bajo el MISMO lock (S10, 2026-07-08): dos
        POST /api/run casi simultáneos para scripts mutadores NO pueden
        colarse los dos — antes el check (running_mutator()) y el registro
        pasaban por locks separados, dejando una ventana TOCTOU donde ambos
        requests veían "nada corriendo todavía" y arrancaban igual."""
        with self.lock:
            if block_if_mutator:
                for jid in self.order:
                    j = self.jobs.get(jid)
                    if j and j.status == "running" and self._mutates_items(j.script_id):
                        return None, j
            job = Job(script_id, label, command,
                      max_buffered_lines=self._max_buffered_lines)
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
                job.append(f"[{self._log_prefix}][ERROR reader] {e}")
                job.mark_done("error", -1)

        try:
            full_env = os.environ.copy()
            full_env["PYTHONUNBUFFERED"] = "1"
            if env:
                full_env.update(env)
            proc = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=full_env,
                bufsize=1,
            )
            job.process = proc
            job.append(f"[{self._log_prefix}] PID {proc.pid} — {shlex.join(command)}")
            threading.Thread(target=reader, args=(proc,), daemon=True).start()
        except Exception as e:
            job.append(f"[{self._log_prefix}][ERROR spawn] {e}")
            job.mark_done("error", -1)
        return job, None

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
            job.append(f"[{self._log_prefix}] SIGTERM enviado por el usuario")
            return True
        except Exception as e:
            job.append(f"[{self._log_prefix}][ERROR stop] {e}")
            return False

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def list(self) -> list[Job]:
        return [self.jobs[jid] for jid in self.order if jid in self.jobs]

    def running_mutator(self) -> Job | None:
        """Un job "running" cuyo script muta items.jsonl, si hay alguno (S10,
        2026-07-08). Los retrofits lanzados desde el Panel no toman lock de
        archivo entre sí (a diferencia de scrape-vs-scrape, .scrape.lock) —
        dos mutadores corriendo a la vez se pisan en un read-modify-write.

        Sólo para INSPECCIÓN (ej. mostrar un aviso en la UI antes de
        intentar). El chequeo que realmente bloquea un `/api/run` concurrente
        es el de `start(block_if_mutator=True)`, que es atómico con el
        registro del job — este método por sí solo tiene una ventana TOCTOU."""
        with self.lock:
            jobs = [self.jobs[jid] for jid in self.order if jid in self.jobs]
        for job in jobs:
            if job.status == "running" and self._mutates_items(job.script_id):
                return job
        return None

    def _trim(self) -> None:
        finished = [
            jid for jid in self.order
            if jid in self.jobs and self.jobs[jid].status != "running"
        ]
        while len(finished) > self._max_finished_jobs:
            old = finished.pop(0)
            self.jobs.pop(old, None)
            try:
                self.order.remove(old)
            except ValueError:
                pass
