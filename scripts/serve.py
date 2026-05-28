#!/usr/bin/env python3
"""serve.py — HTTP server PÚBLICO para el browser de Manga Watch.

Sirve el catálogo desde la raíz del proyecto y expone únicamente:
- `GET /`          → 302 a `/web/`
- archivos estáticos en `/web/`, `/data/`, `/reports/`
- `POST /api/feedback` → elimina el item de items.jsonl y lo mueve a
  data/user_rejected.jsonl con el motivo.

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
USER_REJECTED_PATH = Path("data/user_rejected.jsonl")


def _remove_from_catalog(url: str, reason: str) -> int:
    """Remove item(s) from items.jsonl matching url (and same cluster_key).

    Appends every removed row to user_rejected.jsonl with the rejection_reason
    and rejected_at timestamp.  Returns the number of rows removed.
    """
    if not ITEMS_PATH.exists():
        return 0

    now = datetime.now(timezone.utc).isoformat()

    # Read everything
    parsed: list[tuple[dict, str]] = []
    unparseable: list[str] = []
    with ITEMS_PATH.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.rstrip("\n")
            if not raw:
                continue
            try:
                parsed.append((json.loads(raw), raw))
            except json.JSONDecodeError:
                unparseable.append(raw)

    # Find the cluster_key for this URL (skip url: keys — those are standalone)
    target_ck: str | None = None
    for row, _ in parsed:
        if row.get("url") == url:
            ck = row.get("cluster_key", "")
            if ck and not ck.startswith("url:"):
                target_ck = ck
            break

    # Partition: remove items that are the target URL or same real cluster
    kept: list[str] = list(unparseable)
    removed: list[dict] = []
    for row, raw in parsed:
        is_match = row.get("url") == url or (
            target_ck and row.get("cluster_key") == target_ck
        )
        if is_match:
            removed.append(row)
        else:
            kept.append(raw)

    if not removed:
        return 0

    # Atomic rewrite of items.jsonl
    tmp = ITEMS_PATH.with_name("items.jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for raw in kept:
            fh.write(raw + "\n")
    tmp.replace(ITEMS_PATH)

    # Append each removed row to user_rejected.jsonl
    USER_REJECTED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with USER_REJECTED_PATH.open("a", encoding="utf-8") as fh:
        for row in removed:
            entry = {**row, "rejection_reason": reason, "rejected_at": now}
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return len(removed)


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

        # Remove from catalog (atomic) and move to user_rejected.jsonl
        n_removed = _remove_from_catalog(url, reason)

        body = json.dumps({"ok": True, "removed": n_removed}).encode("utf-8")
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
