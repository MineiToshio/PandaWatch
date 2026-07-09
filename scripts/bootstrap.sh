#!/usr/bin/env bash
#
# bootstrap.sh — scraping profundo one-shot para construir el catálogo inicial.
#
# A diferencia de scrape_delta.sh/scrape_full.sh (los 2 scripts canónicos),
# este script:
#   - Paginación AGRESIVA: hasta 50 páginas por fuente (vs 5 default; ni
#     siquiera scrape_full.sh expone --max-pages como env var)
#   - Sleep alto (1.5s) para evitar rate-limiting durante el run largo
#   - Todos los modos activados: JS, fuzzy, fetch-details, diagnostic
#   - Snapshot del items.jsonl pre-bootstrap para poder revertir si algo se rompe
#   - SOLO scrapea sources.yml (NO corre wikis, cleanup retrofits, gate
#     validate_corpus ni build_web — encadená eso vos con scrape_delta/full).
#
# Pensado para correr UNA vez (o cada 6-12 meses) cuando hace falta paginación
# mucho más profunda que la del pipeline canónico. Para el uso diario/semanal
# normal usá ./scripts/scrape_delta.sh (o ./scripts/scrape_full.sh 1x/mes).
# (referencia corregida 2026-07-08 — antes apuntaba al deprecated full_run.sh)
#
# Tiempo estimado: 1-2 horas
# Requests estimados: ~1500-3000 HTTP (depende de profundidad real de catálogos)
#
# Uso:
#   ./scripts/bootstrap.sh
#
# Variables opcionales:
#   MAX_PAGES=100      # más profundo (default 50)
#   SLEEP=2.0          # más conservador (default 1.5)
#   SKIP_CONFIRM=1     # salta el prompt de confirmación

set -uo pipefail

cd "$(dirname "$0")/.."

MAX_PAGES="${MAX_PAGES:-50}"
SLEEP="${SLEEP:-1.5}"
MIN_SCORE="${MIN_SCORE:-30}"

VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    echo "❌ No encuentro $VENV_PY"
    exit 1
fi

# ── Lock global compartido con scrape_delta.sh/scrape_full.sh (mismo archivo,
# data/.scrape.lock): bootstrap.sh también escribe items.jsonl vía
# manga_watch.py — correrlo a la vez que un delta/full corrompería el corpus
# igual que dos scrapes simultáneos. Antes bootstrap.sh no tomaba lock alguno
# (auditoría S8, 2026-07-08). Se adquiere ANTES del prompt de confirmación
# para fallar rápido si ya hay un scrape corriendo.
LOCK_DIR="data/.scrape.lock"
acquire_lock() {
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        echo $$ > "$LOCK_DIR/pid"
        trap 'rm -rf "$LOCK_DIR"' EXIT
        return 0
    fi
    local old_pid
    old_pid=$(cat "$LOCK_DIR/pid" 2>/dev/null || echo "")
    if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
        echo "❌ Ya hay un scrape corriendo (PID $old_pid, lock $LOCK_DIR). Abortando."
        exit 1
    fi
    echo "⚠️  Lock stale (PID $old_pid ya no existe) — lo tomo."
    rm -rf "$LOCK_DIR"
    if ! mkdir "$LOCK_DIR" 2>/dev/null; then
        echo "❌ Perdí la carrera por el lock stale (otro proceso lo tomó primero). Abortando."
        exit 1
    fi
    echo $$ > "$LOCK_DIR/pid"
    trap 'rm -rf "$LOCK_DIR"' EXIT
}
acquire_lock

# ============================================================
# Aviso inicial + confirmación
# ============================================================
cat <<EOF

╔═══════════════════════════════════════════════════════════════╗
║              MANGA WATCH — BOOTSTRAP (one-shot)               ║
╠═══════════════════════════════════════════════════════════════╣
║                                                                ║
║  Este script hace scraping PROFUNDO de todas las fuentes:     ║
║                                                                ║
║   • Paginación: hasta ${MAX_PAGES} páginas por fuente                    ║
║   • Sleep:      ${SLEEP}s entre fuentes (anti-rate-limit)             ║
║   • Modos:     --enable-js --fuzzy-keywords --fetch-details   ║
║                                                                ║
║  Tiempo estimado: 1-2 horas                                   ║
║  Requests estimados: 1500-3000 HTTP                           ║
║                                                                ║
║  ⚠️  Esto NO es para el run diario.                            ║
║  Para updates incrementales rápidos usá:                       ║
║     ./scripts/scrape_delta.sh                                  ║
║                                                                ║
╚═══════════════════════════════════════════════════════════════╝

EOF

if [ "${SKIP_CONFIRM:-0}" != "1" ]; then
    read -r -p "¿Continuar? [y/N] " confirm
    if [[ ! "$confirm" =~ ^[yY](es)?$ ]]; then
        echo "Cancelado."
        exit 0
    fi
fi

# ============================================================
# Snapshot del items.jsonl actual
# ============================================================
mkdir -p data/snapshots logs/runs

TIMESTAMP=$(date '+%Y-%m-%d-%H%M%S')
LOG_FILE="logs/runs/bootstrap-${TIMESTAMP}.log"

BEFORE_COUNT=0
if [ -f data/items.jsonl ]; then
    BEFORE_COUNT=$(wc -l < data/items.jsonl | tr -d ' ')
    SNAPSHOT="data/snapshots/items.jsonl.pre-bootstrap-${TIMESTAMP}"
    cp data/items.jsonl "$SNAPSHOT"
    echo "==> Snapshot guardado en $SNAPSHOT ($BEFORE_COUNT líneas)"
fi

# Pre-flight Playwright
if ! "$VENV_PY" -c "import playwright" 2>/dev/null; then
    echo
    echo "⚠️  Playwright no está instalado en el venv."
    echo "    Instalalo antes de bootstrap:"
    echo "      $VENV_PY -m pip install -r requirements-playwright.txt"
    echo "      $VENV_PY -m playwright install chromium"
    exit 1
fi

# ============================================================
# Run profundo
# ============================================================
echo
echo "==> Lanzando bootstrap profundo"
echo "    Log: $LOG_FILE"
echo

START_TS=$(date +%s)

PYTHONUNBUFFERED=1 "$VENV_PY" -u manga_watch.py \
    --enable-js \
    --fuzzy-keywords \
    --fetch-details \
    --diagnostic \
    --max-pages "$MAX_PAGES" \
    --sleep-seconds "$SLEEP" \
    --min-score "$MIN_SCORE" \
    2>&1 | tee "$LOG_FILE"

END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))

echo
echo "==> Bootstrap completado en $((DURATION / 60))m $((DURATION % 60))s"
echo

# ============================================================
# Embed en HTML + stats
# ============================================================
"$VENV_PY" scripts/build_web.py

AFTER_COUNT=0
if [ -f data/items.jsonl ]; then
    AFTER_COUNT=$(wc -l < data/items.jsonl | tr -d ' ')
fi
DELTA=$((AFTER_COUNT - BEFORE_COUNT))

echo
echo "==> Bootstrap final"
printf "    %-25s %s\n" "items.jsonl antes:"  "$BEFORE_COUNT líneas"
printf "    %-25s %s\n" "items.jsonl después:" "$AFTER_COUNT líneas"
printf "    %-25s %s\n" "delta:" "+$DELTA"
echo

# Stats por fuente (cuántas páginas paginó cada una)
LATEST_DIAG=$(ls -t logs/diagnostic-*.json 2>/dev/null | head -1 || true)
if [ -n "$LATEST_DIAG" ]; then
    echo "==> Top 15 fuentes por profundidad de paginación"
    "$VENV_PY" - <<EOF
import json
data = json.load(open("$LATEST_DIAG"))
sources = data.get("sources", [])
# Sort by pages_visited descending
by_pages = sorted(
    [s for s in sources if s.get("pages_visited", 1) > 1],
    key=lambda s: -s.get("pages_visited", 0)
)[:15]
print(f"{'pages':>6s}  {'cands':>6s}  fuente")
for s in by_pages:
    print(f"  {s.get('pages_visited', 0):4d}  {s.get('candidates_after_scoring', 0):6d}  {s['name']}")
EOF
fi

echo
echo "==> Listo. Próximos pasos:"
echo "    1. Abrir web:    open web/index.html"
echo "    2. Log completo: less $LOG_FILE"
echo "    3. Para updates incrementales:  ./scripts/scrape_delta.sh (diario/semanal)"
echo "                                     o ./scripts/scrape_full.sh (mensual/trimestral)"
echo
echo "    Si algo salió mal, rollback con:"
if [ -n "${SNAPSHOT:-}" ]; then
    echo "       cp $SNAPSHOT data/items.jsonl"
    echo "       $VENV_PY scripts/build_web.py"
fi
