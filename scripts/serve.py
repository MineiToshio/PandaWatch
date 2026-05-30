#!/usr/bin/env python3
"""serve.py — HTTP server PÚBLICO para el browser de Manga Watch.

Sirve el catálogo desde la raíz del proyecto y expone únicamente:
- `GET /`          → 302 a `/web/`
- archivos estáticos en `/web/`, `/data/`, `/reports/`
- `POST /api/feedback` → registra el feedback en data/feedback.jsonl
  sin modificar items.jsonl (el ítem sigue visible en el catálogo).

Este server NO ejecuta scripts — para eso está `scripts/admin_serve.py`,
que bindea solo a 127.0.0.1 y se mantiene fuera del deploy.

Uso:
    python scripts/serve.py             # puerto 8000 (default), 0.0.0.0
    python scripts/serve.py --port 9000
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import socketserver
import sys
from datetime import datetime, timezone
from pathlib import Path


ITEMS_PATH = Path("data/items.jsonl")
FEEDBACK_PATH = Path("data/feedback.jsonl")


def _log_feedback(url: str, reason: str) -> None:
    """Append a feedback entry to data/feedback.jsonl.

    Looks up the full item from items.jsonl by URL and writes its complete
    data plus 'reason' and 'submitted_at'. The item is NOT removed from
    items.jsonl — feedback is informational only.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Look up full item data from items.jsonl
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

    entry = {**item, "reason": reason, "submitted_at": now}
    # Fallback: if item not found in jsonl, at least store the url
    if not item:
        entry["url"] = url

    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FEEDBACK_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


class MangaWatchHandler(http.server.SimpleHTTPRequestHandler):
    """Sirve la raíz del proyecto. `/` (y `/index.html`) redirige a `/web/`."""

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html", ""):
            self.send_response(302)
            self.send_header("Location", "/web/")
            self.end_headers()
            return
        return super().do_GET()

    def do_POST(self) -> None:
        if self.path != "/api/feedback":
            self.send_error(404, "Not Found")
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 100_000:
            self.send_error(400, "Empty or oversized body")
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self.send_error(400, f"Invalid JSON: {e}")
            return

        title = (payload.get("title") or "").strip()
        url = (payload.get("url") or "").strip()
        reason = (payload.get("reason") or "").strip()

        if not title or not url or not reason:
            self.send_error(400, "Missing 'title', 'url' or 'reason'")
            return

        # Log feedback (item stays in catalog)
        _log_feedback(url, reason)

        body = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--bind", default="0.0.0.0")
    args = parser.parse_args()

    # Servir desde la raíz del proyecto (parent de scripts/).
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)

    print(f"==> Manga Watch Browser (público)")
    print(f"    Raíz:    {root}")
    print(f"    Server:  http://localhost:{args.port}/")
    print(f"    (redirige a /web/ — los datos están en /data/items.jsonl)")
    print()

    # Permite reusar el puerto rápido tras Ctrl+C (evita 'Address already in use').
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((args.bind, args.port), MangaWatchHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[OK] server detenido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
