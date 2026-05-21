#!/usr/bin/env bash
#
# retry_failed.sh — re-corre los sources que fallaron en el overnight previo
# + verifica el flow Tavily recién integrado.
#
# Fases:
#   1. Re-scrape de Dark Horse Direct (8 entries) + Manga Dreams + Whakoom
#      (los que fallaron por 403 rate-limit; deberían funcionar ahora)
#   2. Search discovery completo (18 queries, prueba fallback Tavily)
#   3. Cleanup retrofits (filter_non_manga + filter_collectible + clean_titles)
#   4. Build web final
#
# Tiempo estimado: ~10-15 min total (mucho menos que overnight completo).
#
# Uso: ./scripts/retry_failed.sh

set +e
set -u
cd "$(dirname "$0")/.."

VENV_PY=".venv/bin/python"
TIMESTAMP=$(date '+%Y-%m-%d-%H%M%S')
LOG_DIR="logs/retry-${TIMESTAMP}"
mkdir -p "$LOG_DIR"

GLOBAL_LOG="$LOG_DIR/retry.log"
exec > >(tee -a "$GLOBAL_LOG") 2>&1

GLOBAL_START=$(date +%s)
echo "========================================================"
echo " RETRY FAILED SOURCES"
echo " Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo " Log dir: $LOG_DIR"
echo "========================================================"
BEFORE=$(wc -l < data/items.jsonl 2>/dev/null | tr -d ' ' || echo 0)
echo "items.jsonl antes: $BEFORE"
echo

# ============================================================
# PHASE 1: Re-scrape de los sources que fallaron
# Filtramos por nombre usando --include-tags en combinación con un
# helper Python que arma una lista temporal de sources habilitadas.
# Más simple: --include-tags new-source incluye Manga Dreams + Whakoom.
# Para Dark Horse Direct usamos un run separado con --include-tags expansion.
# ============================================================

echo "════════════════════════════════════════════════════════"
echo " PHASE 1a — Re-scrape Manga Dreams + Whakoom (new-source)"
echo "════════════════════════════════════════════════════════"
P1A_START=$(date +%s)
PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
    --include-tags new-source \
    --enable-js \
    --fetch-details \
    --sleep-seconds 1.0 \
    --min-score 20 \
    > "$LOG_DIR/01a-new-source.log" 2>&1
P1A_END=$(date +%s)
echo "   duración: $((P1A_END - P1A_START))s | items: $(wc -l < data/items.jsonl | tr -d ' ')"

echo
echo "════════════════════════════════════════════════════════"
echo " PHASE 1b — Re-scrape Dark Horse Direct (8 entries via expansion+new-source)"
echo "════════════════════════════════════════════════════════"
# Filtra a Dark Horse Direct específicamente vía python helper
P1B_START=$(date +%s)
"$VENV_PY" - <<'PYEOF' > "$LOG_DIR/01b-darkhorse.log" 2>&1
import sys, subprocess
sys.path.insert(0, 'scripts')
from pathlib import Path
from manga_watch import load_sources

sources = load_sources(Path('sources.yml'))
dh = [s for s in sources if s.enabled and 'Dark Horse Direct' in s.name]
print(f"Dark Horse Direct entries: {len(dh)}")
for s in dh:
    print(f"  [{s.kind}] {s.name}")

# Llamamos al scraper con --include-tags que matchee solo Dark Horse.
# Dark Horse search entries tienen tags ["manga","retailer","store","expansion","search:X"].
# Pero "expansion" trae muchas otras también. Mejor: solo el primer source
# (no search), que tiene tag distintivo.
# Hack: pasar como --include-tags un tag muy específico que solo Dark Horse use.
# Inspeccionemos:
for s in dh:
    print(f"  tags: {s.tags}")
PYEOF
cat "$LOG_DIR/01b-darkhorse.log"
echo
echo "   Lanzando re-scrape Dark Horse específico..."
PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
    --include-tags "dark-horse" \
    --sleep-seconds 1.5 \
    --min-score 20 \
    >> "$LOG_DIR/01b-darkhorse.log" 2>&1
P1B_END=$(date +%s)
echo "   duración: $((P1B_END - P1B_START))s | items: $(wc -l < data/items.jsonl | tr -d ' ')"

# ============================================================
# PHASE 2: Search discovery completo (18 queries, prueba Tavily fallback)
# ============================================================
echo
echo "════════════════════════════════════════════════════════"
echo " PHASE 2 — Search discovery (18 queries, Gemini+Tavily+DDG)"
echo "════════════════════════════════════════════════════════"
P2_START=$(date +%s)
"$VENV_PY" scripts/retrofit/search_discovery.py \
    --max-results 10 \
    > "$LOG_DIR/02-search-discovery.log" 2>&1
P2_END=$(date +%s)
echo "   duración: $((P2_END - P2_START))s | items: $(wc -l < data/items.jsonl | tr -d ' ')"

# ============================================================
# PHASE 3: Cleanup
# ============================================================
echo
echo "════════════════════════════════════════════════════════"
echo " PHASE 3 — Cleanup retrofits"
echo "════════════════════════════════════════════════════════"
echo ">>> filter_non_manga"
"$VENV_PY" scripts/retrofit/filter_non_manga.py > "$LOG_DIR/03a-filter-non-manga.log" 2>&1
echo "   items: $(wc -l < data/items.jsonl | tr -d ' ')"

echo ">>> filter_collectible"
"$VENV_PY" scripts/retrofit/filter_collectible.py > "$LOG_DIR/03b-filter-collectible.log" 2>&1
echo "   items: $(wc -l < data/items.jsonl | tr -d ' ')"

echo ">>> clean_titles"
"$VENV_PY" scripts/retrofit/clean_titles.py > "$LOG_DIR/03c-clean-titles.log" 2>&1
echo "   items: $(wc -l < data/items.jsonl | tr -d ' ')"

# ============================================================
# PHASE 4: Build web
# ============================================================
echo
echo "════════════════════════════════════════════════════════"
echo " PHASE 4 — Build web"
echo "════════════════════════════════════════════════════════"
"$VENV_PY" scripts/build_web.py > "$LOG_DIR/04-build-web.log" 2>&1
tail -5 "$LOG_DIR/04-build-web.log"

# ============================================================
# SUMMARY
# ============================================================
GLOBAL_END=$(date +%s)
TOTAL=$((GLOBAL_END - GLOBAL_START))
AFTER=$(wc -l < data/items.jsonl 2>/dev/null | tr -d ' ' || echo 0)

echo
echo "========================================================"
echo " RETRY FAILED COMPLETO"
echo " Duración: $((TOTAL / 60))m $((TOTAL % 60))s"
echo "========================================================"
echo " items antes:   $BEFORE"
echo " items después: $AFTER"
echo " delta:         $((AFTER - BEFORE))"
echo
echo " Logs: $LOG_DIR/"
ls -la "$LOG_DIR/"
