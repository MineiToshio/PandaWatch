#!/usr/bin/env bash
#
# overnight_run.sh — corrida nocturna END-TO-END.
#
# Encadena TODAS las estrategias en orden:
#   1. Scrape principal (195 sources, --enable-js --fetch-details)
#   2. Wiki bootstraps (listadomanga calendario, blog histórico, manga-sanctuary,
#      otaku-calendar, manga-mexico)
#   3. Search discovery (Gemini + DDG, 32 queries)
#   4. Cleanup retrofits (rescore → filter_non_manga → filter_collectible →
#      clean_titles → backfill_metadata)
#   5. Build web final
#
# Tiempo estimado: 2-4 horas. Pensado para correr de noche.
#
# Cada fase escribe sus propios logs. Si una falla, las siguientes igual corren
# (set +e). Cada fase hace backup automático de items.jsonl antes de modificar.
#
# Uso:
#   ./scripts/overnight_run.sh
#
# Variables opcionales:
#   INCLUDE_WHAKOOM_SPIDER=1     # añade --bootstrap-wiki whakoom (riesgo Cloudflare ban; default OFF)
#   LISTADO_BLOG_FROM=2009-11    # default 2009-11
#   LISTADO_BLOG_TO=2026-05      # default mes actual
#   SKIP_SCRAPE=1                # saltar fase 1 (útil si solo querés wikis+search)
#   SKIP_WIKIS=1                 # saltar fase 2
#   SKIP_SEARCH=1                # saltar fase 3
#   SKIP_CLEANUP=1               # saltar fase 4
#   SKIP_BUILD=1                 # saltar fase 5
#   GEMINI_SLEEP=4.5             # sleep entre queries Gemini (default 4.5 = 15 RPM safe)
#   INCLUDE_WAYBACK_RECOVERY=1   # añade fase 4f: recupera items 404 vía Wayback (default OFF;
#                                #   pesado: ~3000 HEAD requests + Wayback queries. Correr 1x/semana)

set +e  # NO fallar si una fase rompe — seguir con las siguientes
set -u

cd "$(dirname "$0")/.."

VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    echo "❌ No encuentro $VENV_PY. Activa venv o instala primero."
    exit 1
fi

TIMESTAMP=$(date '+%Y-%m-%d-%H%M%S')
LOG_DIR="logs/overnight-${TIMESTAMP}"
mkdir -p "$LOG_DIR"

GLOBAL_LOG="$LOG_DIR/overnight.log"

# Re-direct todo stdout/stderr al log global pero TAMBIÉN a la consola
exec > >(tee -a "$GLOBAL_LOG") 2>&1

INCLUDE_WHAKOOM_SPIDER="${INCLUDE_WHAKOOM_SPIDER:-0}"
LISTADO_BLOG_FROM="${LISTADO_BLOG_FROM:-2009-11}"
LISTADO_BLOG_TO="${LISTADO_BLOG_TO:-$(date '+%Y-%m')}"
SKIP_SCRAPE="${SKIP_SCRAPE:-0}"
SKIP_WIKIS="${SKIP_WIKIS:-0}"
SKIP_SEARCH="${SKIP_SEARCH:-0}"
SKIP_CLEANUP="${SKIP_CLEANUP:-0}"
SKIP_BUILD="${SKIP_BUILD:-0}"
GEMINI_SLEEP="${GEMINI_SLEEP:-4.5}"
INCLUDE_WAYBACK_RECOVERY="${INCLUDE_WAYBACK_RECOVERY:-0}"

GLOBAL_START=$(date +%s)

echo "========================================================"
echo " MANGA WATCH — OVERNIGHT RUN"
echo " Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo " Log dir: $LOG_DIR"
echo "========================================================"
echo
echo "Config:"
echo "  INCLUDE_WHAKOOM_SPIDER=$INCLUDE_WHAKOOM_SPIDER"
echo "  LISTADO_BLOG range:    $LISTADO_BLOG_FROM → $LISTADO_BLOG_TO"
echo "  GEMINI_SLEEP=${GEMINI_SLEEP}s"
echo "  Skips: scrape=$SKIP_SCRAPE wikis=$SKIP_WIKIS search=$SKIP_SEARCH cleanup=$SKIP_CLEANUP build=$SKIP_BUILD"
echo

BEFORE_COUNT=$(wc -l < data/items.jsonl 2>/dev/null | tr -d ' ' || echo 0)
echo "items.jsonl antes: $BEFORE_COUNT líneas"
echo

phase_header() {
    local phase=$1
    local title=$2
    local started
    started=$(date '+%Y-%m-%d %H:%M:%S')
    echo
    echo "════════════════════════════════════════════════════════"
    echo " PHASE $phase: $title"
    echo " Started: $started"
    echo "════════════════════════════════════════════════════════"
}

phase_done() {
    local phase=$1
    local seconds=$2
    local count=$3
    echo
    echo " ✓ PHASE $phase done in $((seconds/60))m $((seconds%60))s"
    echo "   items.jsonl ahora: $count líneas"
}

count_lines() {
    wc -l < data/items.jsonl 2>/dev/null | tr -d ' ' || echo 0
}

# ============================================================
# PHASE 1: Scrape principal
# ============================================================
if [ "$SKIP_SCRAPE" != "1" ]; then
    phase_header 1 "Scrape principal (195 sources, JS+fetch-details)"
    P1_START=$(date +%s)
    PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --enable-js \
        --fuzzy-keywords \
        --max-pages 5 \
        --fetch-details \
        --diagnostic \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/01-scrape.log" 2>&1
    P1_END=$(date +%s)
    phase_done 1 $((P1_END - P1_START)) "$(count_lines)"
else
    echo "[SKIP] PHASE 1 (scrape) saltada por SKIP_SCRAPE=1"
fi

# ============================================================
# PHASE 2: Wiki bootstraps
# ============================================================
if [ "$SKIP_WIKIS" != "1" ]; then
    phase_header 2 "Wiki bootstraps"

    # 2a. listadomanga calendario (mes actual)
    echo ">>> [2a] listadomanga (calendario)"
    P2A_START=$(date +%s)
    "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki listadomanga \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02a-listadomanga.log" 2>&1
    echo "    duración: $(($(date +%s) - P2A_START))s — items: $(count_lines)"

    # 2b. listadomanga BLOG histórico completo (2009-11 → mes actual)
    echo ">>> [2b] listadomanga-blog (histórico ${LISTADO_BLOG_FROM} → ${LISTADO_BLOG_TO})"
    P2B_START=$(date +%s)
    "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki listadomanga-blog \
        --wiki-from "$LISTADO_BLOG_FROM" --wiki-to "$LISTADO_BLOG_TO" \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02b-listadomanga-blog.log" 2>&1
    echo "    duración: $(($(date +%s) - P2B_START))s — items: $(count_lines)"

    # 2c. manga-sanctuary (FR planning)
    echo ">>> [2c] manga-sanctuary (FR)"
    P2C_START=$(date +%s)
    "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki manga-sanctuary \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02c-manga-sanctuary.log" 2>&1
    echo "    duración: $(($(date +%s) - P2C_START))s — items: $(count_lines)"

    # 2d. otaku-calendar (EN/US)
    echo ">>> [2d] otaku-calendar (EN/US)"
    P2D_START=$(date +%s)
    "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki otaku-calendar \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02d-otaku-calendar.log" 2>&1
    echo "    duración: $(($(date +%s) - P2D_START))s — items: $(count_lines)"

    # 2e. manga-mexico
    echo ">>> [2e] manga-mexico (catálogo)"
    P2E_START=$(date +%s)
    "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki manga-mexico \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02e-manga-mexico.log" 2>&1
    echo "    duración: $(($(date +%s) - P2E_START))s — items: $(count_lines)"

    # 2f (OPT-IN). Whakoom spider profundo (RIESGO Cloudflare ban)
    if [ "$INCLUDE_WHAKOOM_SPIDER" = "1" ]; then
        echo ">>> [2f] whakoom spider (OPT-IN, riesgo Cloudflare)"
        P2F_START=$(date +%s)
        "$VENV_PY" scripts/manga_watch.py \
            --bootstrap-wiki whakoom \
            --sleep-seconds 2.0 \
            --min-score 20 \
            > "$LOG_DIR/02f-whakoom.log" 2>&1
        echo "    duración: $(($(date +%s) - P2F_START))s — items: $(count_lines)"
    else
        echo "    [SKIP] whakoom spider profundo (INCLUDE_WHAKOOM_SPIDER=0)"
    fi

    echo " ✓ PHASE 2 wikis done"
else
    echo "[SKIP] PHASE 2 (wikis) saltada por SKIP_WIKIS=1"
fi

# ============================================================
# PHASE 3: Search discovery (Gemini + DDG)
# ============================================================
if [ "$SKIP_SEARCH" != "1" ]; then
    phase_header 3 "Search discovery (Gemini + DDG, 32 queries)"
    P3_START=$(date +%s)
    "$VENV_PY" scripts/retrofit/search_discovery.py \
        --sleep-google "$GEMINI_SLEEP" \
        --sleep-ddg 3.0 \
        --max-results 10 \
        > "$LOG_DIR/03-search-discovery.log" 2>&1
    P3_END=$(date +%s)
    phase_done 3 $((P3_END - P3_START)) "$(count_lines)"
else
    echo "[SKIP] PHASE 3 (search) saltada por SKIP_SEARCH=1"
fi

# ============================================================
# PHASE 4: Cleanup retrofits
# ============================================================
if [ "$SKIP_CLEANUP" != "1" ]; then
    phase_header 4 "Cleanup retrofits"

    echo ">>> [4a] rescore (refresca signal_types + product_type)"
    "$VENV_PY" scripts/retrofit/rescore.py > "$LOG_DIR/04a-rescore.log" 2>&1
    echo "    items: $(count_lines)"

    echo ">>> [4b] filter_non_manga (aplica comics blacklist)"
    "$VENV_PY" scripts/retrofit/filter_non_manga.py > "$LOG_DIR/04b-filter-non-manga.log" 2>&1
    echo "    items: $(count_lines)"

    echo ">>> [4c] filter_collectible (gate de coleccionable)"
    "$VENV_PY" scripts/retrofit/filter_collectible.py > "$LOG_DIR/04c-filter-collectible.log" 2>&1
    echo "    items: $(count_lines)"

    echo ">>> [4d] clean_titles (junky prefixes)"
    "$VENV_PY" scripts/retrofit/clean_titles.py > "$LOG_DIR/04d-clean-titles.log" 2>&1
    echo "    items: $(count_lines)"

    echo ">>> [4e] backfill_metadata --only image_url (rellena imágenes faltantes)"
    "$VENV_PY" scripts/retrofit/backfill_metadata.py --only image_url --sleep 0.5 \
        > "$LOG_DIR/04e-backfill-images.log" 2>&1
    echo "    items: $(count_lines)"

    # 4f (OPT-IN). Wayback recovery — recupera items 404 desde archive.org
    if [ "$INCLUDE_WAYBACK_RECOVERY" = "1" ]; then
        echo ">>> [4f] wayback_recover (OPT-IN, lento ~30-60min)"
        P4F_START=$(date +%s)
        "$VENV_PY" -u scripts/retrofit/wayback_recover.py --sleep 1.0 \
            > "$LOG_DIR/04f-wayback-recover.log" 2>&1
        echo "    duración: $(($(date +%s) - P4F_START))s — items: $(count_lines)"
    else
        echo "    [SKIP] wayback recovery (INCLUDE_WAYBACK_RECOVERY=0)"
    fi

    echo " ✓ PHASE 4 cleanup done"
else
    echo "[SKIP] PHASE 4 (cleanup) saltada por SKIP_CLEANUP=1"
fi

# ============================================================
# PHASE 5: Build web
# ============================================================
if [ "$SKIP_BUILD" != "1" ]; then
    phase_header 5 "Build web"
    "$VENV_PY" scripts/build_web.py > "$LOG_DIR/05-build-web.log" 2>&1
    tail -10 "$LOG_DIR/05-build-web.log"
    echo " ✓ PHASE 5 build done"
else
    echo "[SKIP] PHASE 5 (build) saltada por SKIP_BUILD=1"
fi

# ============================================================
# FINAL SUMMARY
# ============================================================
GLOBAL_END=$(date +%s)
TOTAL=$((GLOBAL_END - GLOBAL_START))
AFTER_COUNT=$(count_lines)

echo
echo "========================================================"
echo " OVERNIGHT RUN COMPLETO"
echo " Finished: $(date '+%Y-%m-%d %H:%M:%S')"
echo " Duración: $((TOTAL / 3600))h $(((TOTAL % 3600) / 60))m $((TOTAL % 60))s"
echo "========================================================"
echo
printf " %-30s %s\n" "items.jsonl antes:"   "$BEFORE_COUNT"
printf " %-30s %s\n" "items.jsonl después:" "$AFTER_COUNT"
printf " %-30s %s\n" "delta:" "$((AFTER_COUNT - BEFORE_COUNT))"
echo
echo "Logs por fase: $LOG_DIR/"
ls -la "$LOG_DIR/"
echo
echo "Próximos pasos:"
echo "  - Revisar: open web/index.html"
echo "  - Log global: less $GLOBAL_LOG"
echo
