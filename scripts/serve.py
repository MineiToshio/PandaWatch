#!/usr/bin/env python3
"""serve.py — HTTP server local para el browser de Manga Watch.

Sirve desde la raíz del proyecto y redirige `/` → `/web/` para que
http://localhost:8000 abra el browser directamente, sin necesidad de
escribir `/web/`. Los paths `/data/...`, `/web/...`, `/reports/...`
siguen siendo accesibles como recursos normales.

Uso:
    python scripts/serve.py             # puerto 8000 (default)
    python scripts/serve.py --port 9000
"""

from __future__ import annotations

import argparse
import http.server
import os
import socketserver
import sys
from pathlib import Path


class MangaWatchHandler(http.server.SimpleHTTPRequestHandler):
    """Sirve la raíz del proyecto. `/` (y `/index.html`) redirige a `/web/`."""

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html", ""):
            self.send_response(302)
            self.send_header("Location", "/web/")
            self.end_headers()
            return
        return super().do_GET()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--bind", default="0.0.0.0")
    args = parser.parse_args()

    # Servir desde la raíz del proyecto (parent de scripts/).
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)

    print(f"==> Manga Watch Browser")
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
