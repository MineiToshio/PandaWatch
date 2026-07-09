#!/bin/bash
# Lanza el servidor local de Manga Watch.
# http://localhost:PORT/ redirige a /web/ (ver scripts/serve.py).
set -e

cd "$(dirname "$0")/.."

# S6 (auditoría 2026-07-08): usar el venv del proyecto, NO el python3 del
# sistema. serve.py importa manga_watch en try/except (merge_cluster/
# consolidate_by_cluster/derive_cluster_key quedan None si falla) — con el
# python3 del sistema (sin bs4/requests) esas primitivas no importan y
# /api/curation/merge cae en silencio a un fallback que descarta una fila
# entera por score (pierde sources[]). serve.py no loguea WARNING cuando esto
# pasa (otro paquete de la auditoría lo revisa); usar el venv correcto evita
# el escenario de raíz.
VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    echo "❌ No encuentro $VENV_PY. Activá el venv o instalá primero:"
    echo "   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

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

exec "$VENV_PY" scripts/serve.py --port "$PORT"
