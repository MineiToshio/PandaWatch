#!/usr/bin/env python3
"""admin_serve.py — server LOCAL del Panel de Control.

⚠ DEPRECATED: absorbido por serve.py; usar scripts/serve.py. Este módulo se
mantiene sincronizado (mismos endpoints) pero es legacy standalone — el
flujo normal ya sirve el Panel de Control desde `scripts/serve.py`
(ver docs/admin/README.md y docs/reference/file-map.md).

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
import socketserver
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Permite importar script_registry como módulo top-level.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from job_manager import Job, JobManager
from script_registry import (  # type: ignore
    SCRIPTS,
    build_command,
    get_script,
    known_flags,
    mutates_items,
    resolve_preset_env,
)


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
# Job/JobManager viven en scripts/job_manager.py (Fable audit B17, 2026-07-08)
# — antes estaban duplicadas byte-a-byte acá y en serve.py. log_prefix=
# "admin_serve" reproduce el prefijo que ya tenían los mensajes de este server
# ("[admin_serve] PID ...").

JOBS = JobManager(
    log_prefix="admin_serve",
    max_buffered_lines=MAX_BUFFERED_LINES,
    max_finished_jobs=MAX_FINISHED_JOBS,
    mutates_items=mutates_items,
)

# build_command vive en script_registry.py (4.1, 2026-07-08) — fuente única,
# importado arriba junto con resolve_preset_env/mutates_items. Ya no se
# duplica acá (había divergido de la copia de serve.py: sólo ésta sabía
# validar "choice", causa de que sync/desync se filtrara sin que un test lo
# atrapara — ver tests/test_script_registry.py).


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class AdminHandler(http.server.SimpleHTTPRequestHandler):
    """Sirve admin/ como root + endpoints /api/*."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ADMIN_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        sys.stderr.write("[admin] " + (format % args) + "\n")

    # ---------- CORS (S7, 2026-07-08) ----------
    # ANTES: `Access-Control-Allow-Origin: *` en toda respuesta. Aunque el
    # bind por default es 127.0.0.1, ese header permite que CUALQUIER página
    # abierta en el navegador del owner (o un dominio público con
    # DNS-rebinding a 127.0.0.1) haga fetch() a /api/run y ejecute scripts —
    # CSRF puro. No se necesita CORS: la UI (web/panel.html) consume /api/*
    # del MISMO origen (ADMIN_API=""), no cross-origin. Sin el header, el
    # navegador bloquea cualquier fetch() cross-origin por su cuenta.
    def do_OPTIONS(self) -> None:
        self.send_response(204)
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

    def _origin_allowed(self) -> bool:
        """Ídem serve.py._origin_allowed (S7, 2026-07-08): si el request trae
        Origin (cross-origin fetch), su host debe matchear el Host local."""
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        origin_host = origin.split("://", 1)[-1].rstrip("/")
        return bool(host) and origin_host == host

    def _handle_run(self) -> None:
        if not self._origin_allowed():
            self._json(403, {"error": "origin no permitido"})
            return
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
        preset_id = payload.get("preset_id")
        if preset_id is not None and not isinstance(preset_id, str):
            self._json(400, {"error": "'preset_id' debe ser string"})
            return

        cmd, label = build_command(script_id, flags)
        if cmd is None:
            self._json(400, {"error": label})  # label es msg de error
            return

        # El env NUNCA viene del cliente — se resuelve server-side desde el
        # preset_id, validado contra la allowlist (1.2/S5, 2026-07-08).
        env = resolve_preset_env(script_id, preset_id)

        # Resolver path absoluto al python del venv si existe.
        if cmd and cmd[0] == ".venv/bin/python":
            candidate = ROOT / ".venv" / "bin" / "python"
            cmd[0] = str(candidate) if candidate.exists() else sys.executable

        # S10: check + registro ATÓMICOS bajo el mismo lock (ver serve.py).
        job, blocker = JOBS.start(
            script_id, cmd, label, cwd=ROOT, env=env or None,
            block_if_mutator=mutates_items(script_id),
        )
        if job is None:
            assert blocker is not None
            self._json(409, {
                "error": (
                    f"ya hay un job mutador corriendo ({blocker.script_id}, "
                    f"job {blocker.id}) — esperá a que termine"
                ),
                "job_id": blocker.id,
                "script_id": blocker.script_id,
            })
            return
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

    print(
        "[DEPRECATED] admin_serve.py está deprecated — absorbido por "
        "scripts/serve.py (mismos endpoints, flujo normal). Usar: "
        "python scripts/serve.py",
        file=sys.stderr,
    )

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
