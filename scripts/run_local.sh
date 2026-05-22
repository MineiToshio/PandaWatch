#!/usr/bin/env bash
#
# run_local.sh — lanza los dos servers locales en paralelo:
#   - Catálogo (público, deployable):  http://localhost:8000/
#   - Panel de control (LOCAL, admin): http://localhost:8001/
#
# Ctrl+C detiene ambos.
#
# Variables opcionales:
#   PUBLIC_PORT=8000
#   ADMIN_PORT=8001
#   ADMIN_BIND=127.0.0.1   # ⚠️ Solo cambialo a 0.0.0.0 si sabés qué hacés
#                          # — cualquiera en tu red podría ejecutar scripts.

set -u
cd "$(dirname "$0")/.."

VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    echo "❌ No encuentro $VENV_PY. Activa venv o instala primero."
    exit 1
fi

PUBLIC_PORT="${PUBLIC_PORT:-8000}"
ADMIN_PORT="${ADMIN_PORT:-8001}"
ADMIN_BIND="${ADMIN_BIND:-127.0.0.1}"

echo "==> Lanzando server público (catálogo)   en http://localhost:${PUBLIC_PORT}/"
"$VENV_PY" scripts/serve.py --port "$PUBLIC_PORT" &
PID_PUBLIC=$!

echo "==> Lanzando server admin (panel local)  en http://localhost:${ADMIN_PORT}/  [bind=${ADMIN_BIND}]"
"$VENV_PY" scripts/admin_serve.py --port "$ADMIN_PORT" --bind "$ADMIN_BIND" &
PID_ADMIN=$!

echo
echo "    Catálogo:    http://localhost:${PUBLIC_PORT}/"
echo "    Admin:       http://localhost:${ADMIN_PORT}/"
echo
echo "    Ctrl+C para detener ambos."
echo

# Cleanup on exit
trap 'echo; echo "[run_local] deteniendo servers..."; kill "$PID_PUBLIC" "$PID_ADMIN" 2>/dev/null; wait 2>/dev/null; exit 0' INT TERM

wait
