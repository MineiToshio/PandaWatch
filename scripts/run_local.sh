#!/usr/bin/env bash
#
# run_local.sh — lanza el servidor unificado de Manga Watch.
#
#   Catálogo + Panel de control: http://localhost:8000/
#   Panel de control:            http://localhost:8000/web/panel.html
#
# Ctrl+C lo detiene.
#
# Variables opcionales:
#   PORT=8000

set -u
cd "$(dirname "$0")/.."

VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    echo "❌ No encuentro $VENV_PY. Activa venv o instala primero."
    exit 1
fi

PORT="${PORT:-8000}"

echo "==> Lanzando Manga Watch en http://localhost:${PORT}/"
echo "    Panel de control: http://localhost:${PORT}/web/panel.html"
echo
echo "    Ctrl+C para detener."
echo

exec "$VENV_PY" scripts/serve.py --port "$PORT"
