#!/bin/bash
# Lanza el servidor local de Manga Watch.
# http://localhost:PORT/ redirige a /web/ (ver scripts/serve.py).
set -e

cd "$(dirname "$0")/.."

PORT="${PORT:-8000}"
URL="http://localhost:${PORT}/"

echo "==> Manga Watch Browser"
echo "    Raíz:   $(pwd)"
echo "    Server: ${URL}"
echo ""

if [ ! -f "data/items.jsonl" ]; then
    echo "⚠️  data/items.jsonl no existe."
    echo "    Corré primero:"
    echo "    .venv/bin/python scripts/manga_watch.py"
    echo ""
fi

# Abrir en el browser después de 1 segundo (cross-platform)
( sleep 1 && (open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || true) ) &

exec python3 scripts/serve.py --port "$PORT"
