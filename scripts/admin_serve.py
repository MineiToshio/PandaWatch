#!/usr/bin/env python3
"""admin_serve.py — server LOCAL del Panel de Control.

Sirve `admin/index.html` y la API de ejecución de scripts. Por seguridad
bindea por default a 127.0.0.1, así que solo procesos de esta máquina
pueden ejecutar scripts.

Este server NO se despliega. Lo corrés a mano cuando querés usar el
panel de control. Para el catálogo público (que sí se despliega) está
`scripts/serve.py`.

Endpoints:
    GET  /                       → admin/index.html
    GET  /api/scripts            → JSON del registry
    POST /api/run                → lanza un script. Body:
                                   {"script_id": "...", "flags": {"--x": True}}
    GET  /api/jobs               → lista jobs (running + recientes)
    GET  /api/jobs/<id>          → detalle de un job
    GET  /api/jobs/<id>/stream   → SSE: stdout/stderr en vivo + 'end' al terminar
    POST /api/jobs/<id>/stop     → SIGTERM al proceso
    GET  /api/health             → liveness probe

Uso:
    python scripts/admin_serve.py             # 127.0.0.1:8001
    python scripts/admin_serve.py --port 9001
    python scripts/admin_serve.py --bind 0.0.0.0   # ⚠️ EXPONE A LA RED LOCAL
"""

from __future__ import annotations

import argparse
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

# Permite importar script_registry como módulo top-level.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from script_registry import SCRIPTS, get_script, known_flags  # type: ignore


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

# Cuántas líneas de stdout/stderr retener por job para que un cliente nuevo
# que se conecte tarde a /stream pueda ver el inicio.
MAX_BUFFERED_LINES = 5000

# Cuántos jobs ya terminados mantener en memoria para inspección.
MAX_FINISHED_JOBS = 30

# Raíz del repo (parent de scripts/) — desde acá se ejecutan los scripts y
# desde acá se sirve admin/.
ROOT = Path(__file__).resolve().parent.parent
ADMIN_DIR = ROOT / "admin"


# ---------------------------------------------------------------------------
# Job manager: corre subprocesos y reparte sus logs via SSE.
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
        self.status: str = "running"   # running | exited | killed | error
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
        out = {
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
              cwd: Path, env: dict[str, str] | None = None) -> Job:
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
                job.append(f"[admin_serve][ERROR reader] {e}")
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
            job.append(f"[admin_serve] PID {proc.pid} — {shlex.join(command)}")
            threading.Thread(target=reader, args=(proc,), daemon=True).start()
        except Exception as e:
            job.append(f"[admin_serve][ERROR spawn] {e}")
            job.mark_done("error", -1)
        return job

    def stop(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or not job.process:
            return False
        if job.status != "running":
            return False
        try:
            job.process.terminate()
            def _killer(p: subprocess.Popen[bytes]) -> None:
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()
            threading.Thread(target=_killer, args=(job.process,), daemon=True).start()
            job.append("[admin_serve] SIGTERM enviado por el usuario")
            return True
        except Exception as e:
            job.append(f"[admin_serve][ERROR stop] {e}")
            return False

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def list(self) -> list[Job]:
        return [self.jobs[jid] for jid in self.order if jid in self.jobs]

    def _trim(self) -> None:
        finished_ids = [jid for jid in self.order
                        if jid in self.jobs and self.jobs[jid].status != "running"]
        while len(finished_ids) > MAX_FINISHED_JOBS:
            old = finished_ids.pop(0)
            self.jobs.pop(old, None)
            try:
                self.order.remove(old)
            except ValueError:
                pass


JOBS = JobManager()


# ---------------------------------------------------------------------------
# Construcción del comando desde flags
# ---------------------------------------------------------------------------

def build_command(script_id: str, flag_values: dict[str, Any]) -> tuple[list[str], str] | tuple[None, str]:
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
            if value is None or value == "" or value == "null":
                continue
            try:
                ival = int(value)
            except (TypeError, ValueError):
                return None, f"valor int inválido para {arg}: {value!r}"
            cmd.extend([arg, str(ival)])
            used_labels.append(f"{arg}={ival}")
        elif t == "float":
            if value is None or value == "" or value == "null":
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
# HTTP handler
# ---------------------------------------------------------------------------

class AdminHandler(http.server.SimpleHTTPRequestHandler):
    """Sirve admin/ como root + endpoints /api/*."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ADMIN_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        sys.stderr.write("[admin] " + (format % args) + "\n")

    # ---------- CORS para que la UI consuma su propia API ----------
    def end_headers(self) -> None:
        # Mismo origen siempre que el front venga del mismo server, pero
        # dejamos abierto para que un dev pueda apuntar el panel desde otro
        # origen local si lo necesita.
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ---------- GET ----------
    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._json(200, {"ok": True, "ts": datetime.now(timezone.utc).isoformat()})
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
        # Estáticos desde admin/
        return super().do_GET()

    # ---------- POST ----------
    def do_POST(self) -> None:
        if self.path == "/api/run":
            return self._handle_run()
        if self.path.startswith("/api/jobs/") and self.path.endswith("/stop"):
            jid = self.path[len("/api/jobs/"):-len("/stop")]
            ok = JOBS.stop(jid)
            self._json(200 if ok else 400, {"ok": ok})
            return
        self.send_error(404, "Not Found")

    # ---------- helpers ----------
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

    def _read_json_body(self, max_bytes: int = 200_000) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > max_bytes:
            raise ValueError("body vacío u oversized")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _handle_run(self) -> None:
        try:
            payload = self._read_json_body()
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
            self._json(400, {"error": label})  # label es msg de error
            return

        # Resolver path absoluto al python del venv si existe.
        if cmd and cmd[0] == ".venv/bin/python":
            candidate = ROOT / ".venv" / "bin" / "python"
            cmd[0] = str(candidate) if candidate.exists() else sys.executable

        job = JOBS.start(script_id, cmd, label, cwd=ROOT)
        self._json(200, {"job_id": job.id, "label": label, "command": cmd})

    # ---------- SSE ----------
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
                        break
                    snapshot = list(job.lines)[sent:]
                    finished = job.status != "running"

                for line in snapshot:
                    payload = json.dumps({"line": line}, ensure_ascii=False)
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                sent += len(snapshot)

                now = time.monotonic()
                if not snapshot and not finished and (now - last_keepalive) > 14:
                    self.wfile.write(b": keepalive\n\n")
                    last_keepalive = now
                elif snapshot:
                    last_keepalive = now

                self.wfile.flush()

                if finished:
                    end_payload = json.dumps({
                        "status": job.status,
                        "exit_code": job.exit_code,
                        "ended_at": job.ended_at,
                    }, ensure_ascii=False)
                    self.wfile.write(b"event: end\n")
                    self.wfile.write(f"data: {end_payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    return
        except (BrokenPipeError, ConnectionResetError):
            return


# ---------------------------------------------------------------------------
# Server: threaded para soportar múltiples SSE en paralelo
# ---------------------------------------------------------------------------

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=int(os.environ.get("ADMIN_PORT", "8001")))
    parser.add_argument(
        "--bind",
        default=os.environ.get("ADMIN_BIND", "127.0.0.1"),
        help=("Interface a la que bindear. Default: 127.0.0.1 (solo localhost). "
              "Usá 0.0.0.0 solo si entendés que cualquiera en tu red puede "
              "ejecutar tus scripts."),
    )
    args = parser.parse_args()

    if not ADMIN_DIR.exists():
        print(f"[ERROR] no existe {ADMIN_DIR}", file=sys.stderr)
        return 1

    # Servimos archivos estáticos desde admin/ pero ejecutamos comandos
    # desde ROOT (donde están los scripts y data/).
    os.chdir(ROOT)

    bind = args.bind
    warn = ""
    if bind not in ("127.0.0.1", "localhost", "::1"):
        warn = "  ⚠️  Bindeado a una interface PÚBLICA — cualquiera en tu red puede ejecutar scripts."

    print(f"==> Manga Watch — Panel de Control (ADMIN, NO desplegar)")
    print(f"    Admin dir:  {ADMIN_DIR}")
    print(f"    URL:        http://localhost:{args.port}/")
    print(f"    Bind:       {bind}:{args.port}{warn}")
    print()

    with ThreadedTCPServer((bind, args.port), AdminHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[OK] admin server detenido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
