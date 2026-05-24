#!/usr/bin/env bash
#
# scrape_delta.sh — scraping INCREMENTAL ("delta").
#
# Detecta novedades RECIENTES. Pensado para correr **diario / semanal**.
# Es rápido (~30-60 min) y barato (pocos requests).
#
# Para listadomanga.es usa **`calendario.php`** (mes actual + recientes)
# en vez de `lista.php`. Eso cubre solo lanzamientos del mes — no
# recorre las ~3432 colecciones del catálogo.
#
# Para descubrir TODAS las colecciones del catálogo (incluyendo ediciones
# especiales / extras / portadas alternativas históricas), usar
# `scrape_full.sh` en su lugar (correr 1x/mes o 1x/trimestre).
#
# El resto de fuentes (Mangavariant, SocialAnime, BBM, Manga-Sanctuary,
# Whakoom, retailers Shopify/Tiendanube, etc.) se comportan igual entre
# delta y full por ahora — la diferencia es solo el método de discovery
# de listadomanga.
#
# Encadena las fases:
#   1. Scrape principal (sources del YAML, --max-pages 5, --enable-js)
#   2. Wiki bootstraps DELTA (listadomanga calendario mes actual,
#      manga-sanctuary, otaku-calendar, manga-mexico, socialanime, blogbbm)
#   3. Search discovery (Gemini + DDG, 32 queries)
#   4. Cleanup retrofits (rescore → filter_non_manga → filter_collectible →
#      clean_titles → backfill_metadata)
#   5. Build web final
#
# Tiempo estimado: 30-60 min (vs 2-4 horas del full).
#
# Cada fase escribe sus propios logs. Si una falla, las siguientes igual corren
# (set +e). Cada fase hace backup automático de items.jsonl antes de modificar.
#
# Uso:
#   ./scripts/scrape_delta.sh
#
# Variables opcionales:
#   INCLUDE_WHAKOOM_SPIDER=1     # añade --bootstrap-wiki whakoom (riesgo Cloudflare ban; default OFF)
#   SKIP_SCRAPE=1                # saltar fase 1
#   SKIP_WIKIS=1                 # saltar fase 2
#   SKIP_SEARCH=1                # saltar fase 3
#   SKIP_CLEANUP=1               # saltar fase 4
#   SKIP_BUILD=1                 # saltar fase 5
#   GEMINI_SLEEP=4.5             # sleep entre queries Gemini (default 4.5 = 15 RPM safe)
#   INCLUDE_WAYBACK_RECOVERY=1   # añade fase 4f (default OFF; pesado)
#   SCRAPE_WORKERS=8             # paralelismo Phase 1. Default 8.
#   PER_HOST_LIMIT=2             # requests concurrentes al mismo dominio

set +e
set -u

cd "$(dirname "$0")/.."

VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    echo "❌ No encuentro $VENV_PY. Activa venv o instala primero."
    exit 1
fi

TIMESTAMP=$(date '+%Y-%m-%d-%H%M%S')
LOG_DIR="logs/scrape-delta-${TIMESTAMP}"
mkdir -p "$LOG_DIR"

GLOBAL_LOG="$LOG_DIR/scrape-delta.log"
exec > >(tee -a "$GLOBAL_LOG") 2>&1

INCLUDE_WHAKOOM_SPIDER="${INCLUDE_WHAKOOM_SPIDER:-0}"
SKIP_SCRAPE="${SKIP_SCRAPE:-0}"
SKIP_WIKIS="${SKIP_WIKIS:-0}"
SKIP_SEARCH="${SKIP_SEARCH:-0}"
SKIP_CLEANUP="${SKIP_CLEANUP:-0}"
SKIP_BUILD="${SKIP_BUILD:-0}"
GEMINI_SLEEP="${GEMINI_SLEEP:-4.5}"
INCLUDE_WAYBACK_RECOVERY="${INCLUDE_WAYBACK_RECOVERY:-0}"
SCRAPE_WORKERS="${SCRAPE_WORKERS:-8}"
PER_HOST_LIMIT="${PER_HOST_LIMIT:-2}"

# Para el delta el calendario de listadomanga toma solo los últimos meses.
# Default: últimos 3 meses (mes actual + 2 anteriores).
LISTADO_CAL_FROM="${LISTADO_CAL_FROM:-$(date -v-2m '+%Y-%m' 2>/dev/null || date -d '2 months ago' '+%Y-%m' 2>/dev/null || date '+%Y-%m')}"

GLOBAL_START=$(date +%s)

echo "========================================================"
echo " MANGA WATCH — SCRAPE DELTA (incremental)"
echo " Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo " Log dir: $LOG_DIR"
echo "========================================================"
echo
echo "Config:"
echo "  Listadomanga calendar: $LISTADO_CAL_FROM → mes actual"
echo "  INCLUDE_WHAKOOM_SPIDER=$INCLUDE_WHAKOOM_SPIDER"
echo "  INCLUDE_WAYBACK_RECOVERY=$INCLUDE_WAYBACK_RECOVERY"
echo "  GEMINI_SLEEP=${GEMINI_SLEEP}s"
echo "  SCRAPE_WORKERS=$SCRAPE_WORKERS (per-host limit=$PER_HOST_LIMIT)"
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
# PHASE 1: Scrape principal (sources del YAML)
# ============================================================
if [ "$SKIP_SCRAPE" != "1" ]; then
    phase_header 1 "Scrape principal (sources YAML, JS+fetch-details, workers=${SCRAPE_WORKERS})"
    P1_START=$(date +%s)
    PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --enable-js \
        --fuzzy-keywords \
        --max-pages 5 \
        --fetch-details \
        --diagnostic \
        --workers "$SCRAPE_WORKERS" \
        --per-host-limit "$PER_HOST_LIMIT" \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/01-scrape.log" 2>&1
    P1_END=$(date +%s)
    phase_done 1 $((P1_END - P1_START)) "$(count_lines)"
else
    echo "[SKIP] PHASE 1 (scrape) saltada por SKIP_SCRAPE=1"
fi

# ============================================================
# PHASE 2: Wiki bootstraps DELTA (solo lo reciente)
# ============================================================
if [ "$SKIP_WIKIS" != "1" ]; then
    phase_header 2 "Wiki bootstraps (delta — mes actual / recientes)"

    # 2a. listadomanga CALENDARIO (últimos 3 meses → mes actual)
    # NO usamos listadomanga-collections aquí — eso es para scrape_full.sh.
    echo ">>> [2a] listadomanga (calendario delta: ${LISTADO_CAL_FROM} → mes actual)"
    P2A_START=$(date +%s)
    "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki listadomanga \
        --wiki-from "$LISTADO_CAL_FROM" \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02a-listadomanga-calendar.log" 2>&1
    echo "    duración: $(($(date +%s) - P2A_START))s — items: $(count_lines)"

    # 2b. manga-sanctuary (FR planning)
    echo ">>> [2b] manga-sanctuary (FR)"
    P2B_START=$(date +%s)
    "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki manga-sanctuary \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02b-manga-sanctuary.log" 2>&1
    echo "    duración: $(($(date +%s) - P2B_START))s — items: $(count_lines)"

    # 2c. otaku-calendar (EN/US)
    echo ">>> [2c] otaku-calendar (EN/US)"
    P2C_START=$(date +%s)
    "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki otaku-calendar \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02c-otaku-calendar.log" 2>&1
    echo "    duración: $(($(date +%s) - P2C_START))s — items: $(count_lines)"

    # 2d. manga-mexico
    echo ">>> [2d] manga-mexico (catálogo)"
    P2D_START=$(date +%s)
    "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki manga-mexico \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02d-manga-mexico.log" 2>&1
    echo "    duración: $(($(date +%s) - P2D_START))s — items: $(count_lines)"

    # 2e. socialanime (IT)
    echo ">>> [2e] socialanime (IT — variant + cofanetti)"
    P2E_START=$(date +%s)
    "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki socialanime \
        --sleep-seconds 0.3 \
        --min-score 20 \
        > "$LOG_DIR/02e-socialanime.log" 2>&1
    echo "    duración: $(($(date +%s) - P2E_START))s — items: $(count_lines)"

    # 2f. blogbbm (BR)
    echo ">>> [2f] blogbbm (BR — capas variantes + volúmenes especiais)"
    P2F_START=$(date +%s)
    "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki blogbbm \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02f-blogbbm.log" 2>&1
    echo "    duración: $(($(date +%s) - P2F_START))s — items: $(count_lines)"

    # 2g (OPT-IN). Whakoom spider (Cloudflare risk)
    if [ "$INCLUDE_WHAKOOM_SPIDER" = "1" ]; then
        echo ">>> [2g] whakoom spider (OPT-IN, riesgo Cloudflare)"
        P2G_START=$(date +%s)
        "$VENV_PY" scripts/manga_watch.py \
            --bootstrap-wiki whakoom \
            --sleep-seconds 2.0 \
            --min-score 20 \
            > "$LOG_DIR/02g-whakoom.log" 2>&1
        echo "    duración: $(($(date +%s) - P2G_START))s — items: $(count_lines)"
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
    phase_header 3 "Search discovery (Gemini + DDG)"
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

    echo ">>> [4a] rescore"
    "$VENV_PY" scripts/retrofit/rescore.py > "$LOG_DIR/04a-rescore.log" 2>&1
    echo "    items: $(count_lines)"

    echo ">>> [4b] filter_non_manga"
    "$VENV_PY" scripts/retrofit/filter_non_manga.py > "$LOG_DIR/04b-filter-non-manga.log" 2>&1
    echo "    items: $(count_lines)"

    echo ">>> [4c] filter_collectible"
    "$VENV_PY" scripts/retrofit/filter_collectible.py > "$LOG_DIR/04c-filter-collectible.log" 2>&1
    echo "    items: $(count_lines)"

    echo ">>> [4d] clean_titles"
    "$VENV_PY" scripts/retrofit/clean_titles.py > "$LOG_DIR/04d-clean-titles.log" 2>&1
    echo "    items: $(count_lines)"

    echo ">>> [4e] backfill_metadata --only image_url"
    "$VENV_PY" scripts/retrofit/backfill_metadata.py --only image_url --sleep 0.5 \
        > "$LOG_DIR/04e-backfill-images.log" 2>&1
    echo "    items: $(count_lines)"

    if [ "$INCLUDE_WAYBACK_RECOVERY" = "1" ]; then
        echo ">>> [4f] wayback_recover (OPT-IN)"
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
echo " SCRAPE DELTA COMPLETO"
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
echo "Recordatorio:"
echo "  - Este es el scrape DELTA (incremental, últimos meses)."
echo "  - Para recorrer el catálogo COMPLETO de listadomanga (~3432"
echo "    colecciones via lista.php), usar: ./scripts/scrape_full.sh"
echo "  - Frecuencia recomendada: delta semanal, full mensual/trimestral."
echo
