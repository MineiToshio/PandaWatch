#!/bin/bash
# Lanza un servidor HTTP local desde la raíz del proyecto y abre la UI.
set -e

cd "$(dirname "$0")/.."

PORT="${PORT:-8000}"
URL="http://localhost:${PORT}/web/"

echo "==> Manga Watch Browser"
echo "    Raíz:   $(pwd)"
echo "    Server: ${URL}"
echo ""

if [ ! -f "data/items.jsonl" ]; then
    echo "⚠️  data/items.jsonl no existe."
    echo "    Corré primero:"
    echo "    .venv/bin/python manga_watch.py --enable-js --fuzzy-keywords"
    echo ""
fi

# Abrir en el browser después de 1 segundo (cross-platform)
( sleep 1 && (open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || true) ) &

python3 -m http.server "$PORT"
