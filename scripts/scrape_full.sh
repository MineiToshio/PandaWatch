#!/usr/bin/env bash
#
# scrape_full.sh — scraping COMPLETO del catálogo.
#
# Recorre TODO el catálogo histórico, no solo lo reciente. Pensado para
# correr **una vez al mes / trimestre** o cuando se quiere refrescar el
# corpus desde cero.
#
# Para listadomanga.es usa **`lista.php`** como índice (3432 colecciones
# activas, en orden alfabético del catálogo oficial). En cada colección
# busca ediciones especiales / portadas alternativas / cofres / extras
# de primera edición / formato premium — el discovery completo del
# parser `listadomanga_collections`.
#
# Para descubrir SOLO novedades recientes (mes actual) sin recorrer las
# 3432 colecciones, usar `scrape_delta.sh` (más rápido, ~30-60 min).
#
# El resto de fuentes (Mangavariant, SocialAnime, BBM, Manga-Sanctuary,
# Whakoom, retailers Shopify/Tiendanube, etc.) corren igual que en
# scrape_delta por ahora — la diferencia principal entre full y delta
# es solo el método de discovery de listadomanga.
#
# Encadena las fases:
#   1. Scrape principal (sources del YAML, --max-pages 5, --enable-js)
#   2. Wiki bootstraps FULL:
#      2a. listadomanga-collections via lista.php (~3432 colecciones)
#      2b. manga-sanctuary (FR)
#      2c. otaku-calendar (EN/US)
#      2d. manga-mexico
#      2e. mangavariant (~2700 entries, todo el sitemap)
#      2f. socialanime (IT)
#      2g. blogbbm (BR)
#      2h. booksprivilege (JP — 店舗特典 desde 2020)
#      2i. sumikko (JP — 限定版/特装版 catálogo completo)
#      2j. mangapassion (DE — Sonderausgaben + Variant-Covers)
#      2k. animeclick (IT — edizioni speciali desde 2015)
#      2l. prhcomics (EN/US — catálogo completo)
#      2m. kinokuniya (EN/US — exclusivos Kinokuniya USA)
#      2n. yenpress (EN/US — calendario histórico desde 2013)
#      2o (opt-in). whakoom spider profundo
#   3. Cleanup retrofits + (opt-in) wayback recovery
#   4. Build web final
#
# Tiempo estimado: 1.5-3 horas (vs 30-60 min del delta).
# NOTE: listadomanga-blog histórico REMOVED del pipeline canónico
# (decisión 2026-05-23). Son posts de noticias, no productos — el gate
# is_collectible_edition los rechaza al 99%+. Ver wiki module
# wikis/listadomanga_blog.py para invocación manual si vuelve a hacer falta.
#
# Uso:
#   ./scripts/scrape_full.sh
#
# Variables opcionales:
#   INCLUDE_WHAKOOM_SPIDER=1     # añade whakoom (riesgo Cloudflare; default OFF)
#   INCLUDE_WAYBACK_RECOVERY=1   # añade fase 3f (pesado; default OFF)
#   SKIP_SCRAPE=1 / SKIP_WIKIS=1 / SKIP_CLEANUP=1 / SKIP_BUILD=1
#   SCRAPE_WORKERS=8             # default 8
#   PER_HOST_LIMIT=2             # default 2
#   COLECCION_SLEEP=0.3          # sleep entre requests al recorrer las 3432
#                                #   colecciones de lista.php (default 0.3s)

set +e
set -u

cd "$(dirname "$0")/.."

VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    echo "❌ No encuentro $VENV_PY. Activa venv o instala primero."
    exit 1
fi

TIMESTAMP=$(date '+%Y-%m-%d-%H%M%S')
LOG_DIR="logs/scrape-full-${TIMESTAMP}"
mkdir -p "$LOG_DIR"

GLOBAL_LOG="$LOG_DIR/scrape-full.log"
exec > >(tee -a "$GLOBAL_LOG") 2>&1

INCLUDE_WHAKOOM_SPIDER="${INCLUDE_WHAKOOM_SPIDER:-0}"
INCLUDE_WAYBACK_RECOVERY="${INCLUDE_WAYBACK_RECOVERY:-0}"
SKIP_SCRAPE="${SKIP_SCRAPE:-0}"
SKIP_WIKIS="${SKIP_WIKIS:-0}"
SKIP_CLEANUP="${SKIP_CLEANUP:-0}"
SKIP_BUILD="${SKIP_BUILD:-0}"
SCRAPE_WORKERS="${SCRAPE_WORKERS:-8}"
PER_HOST_LIMIT="${PER_HOST_LIMIT:-2}"
COLECCION_SLEEP="${COLECCION_SLEEP:-0.3}"

# Wrapper portable para ejecutar un comando con timeout.
# Prueba: macOS nativo 'timeout', luego GNU 'gtimeout' (brew coreutils).
# Si ninguno está disponible, corre sin timeout (mejor que fallar).
_run_timed() {
    local secs=$1; shift
    if command -v timeout &>/dev/null 2>&1; then
        timeout "$secs" "$@"
        return $?
    elif command -v gtimeout &>/dev/null 2>&1; then
        gtimeout "$secs" "$@"
        return $?
    else
        echo "    [WARN] timeout/gtimeout no disponible — corriendo sin límite de tiempo"
        "$@"
        return $?
    fi
}

GLOBAL_START=$(date +%s)

echo "========================================================"
echo " MANGA WATCH — SCRAPE FULL (catálogo completo)"
echo " Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo " Log dir: $LOG_DIR"
echo "========================================================"
echo
echo "Config:"
echo "  Listadomanga lista.php discovery: ~3432 colecciones, sleep ${COLECCION_SLEEP}s"
echo "  INCLUDE_WHAKOOM_SPIDER=$INCLUDE_WHAKOOM_SPIDER"
echo "  INCLUDE_WAYBACK_RECOVERY=$INCLUDE_WAYBACK_RECOVERY"
echo "  SCRAPE_WORKERS=$SCRAPE_WORKERS (per-host limit=$PER_HOST_LIMIT)"
echo "  Skips: scrape=$SKIP_SCRAPE wikis=$SKIP_WIKIS cleanup=$SKIP_CLEANUP build=$SKIP_BUILD"
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
# PHASE 2: Wiki bootstraps FULL
# ============================================================
if [ "$SKIP_WIKIS" != "1" ]; then
    phase_header 2 "Wiki bootstraps (FULL — discovery completo)"

    # 2a. listadomanga-collections via lista.php (CORE del FULL).
    # Recorre las ~3432 colecciones activas del catálogo, buscando
    # ediciones especiales / portadas alternativas / cofres / extras.
    # Tiempo estimado: 30-60 min con sleep 0.3s.
    echo ">>> [2a] listadomanga-collections via lista.php (~3432 colecciones)"
    P2A_START=$(date +%s)
    _run_timed 5400 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki listadomanga-collections \
        --coleccion-mode lista \
        --sleep-seconds "$COLECCION_SLEEP" \
        --min-score 30 \
        > "$LOG_DIR/02a-listadomanga-collections.log" 2>&1
    echo "    duración: $(($(date +%s) - P2A_START))s — items: $(count_lines)"

    # NOTE: listadomanga calendario REMOVED del scrape_full (decisión
    # 2026-05-23). Razones:
    # - lista.php (2a) cubre todo el catálogo de colecciones activas
    #   (~3432 ids). Las colecciones "exclusivas" del calendar eran
    #   FALSOS NEGATIVOS del parser de collections (headers
    #   "Planeta DeAgostini Cómics" descartados por error) — fix aplicado
    #   en SECTION_RULES, ya no se necesita el calendar como complemento.
    # - El calendar SÍ tiene sentido para SCRAPE_DELTA: forma rápida de
    #   detectar releases muy recientes que aún no entraron a lista.php.
    # - Modelo final: full = lista.php, delta = calendar. Sin overlap.

    # NOTE: listadomanga-blog histórico REMOVED del pipeline canónico
    # (decisión 2026-05-23). Razones:
    # - Son posts de noticias (anuncios de licencias, "Novedades de X"),
    #   NO productos físicos. is_collectible_edition los rechaza al 99%+.
    # - Costo: ~30-60 min por corrida (~190 meses × 5-15 páginas × 0.5s)
    #   para 0 items netos al catálogo.
    # - lista.php ya cubre todo el catálogo de productos.
    # El módulo wikis/listadomanga_blog.py sigue disponible para invocación
    # manual si en el futuro se le da otro uso (ej. input para search_discovery).

    # 2b. manga-sanctuary
    echo ">>> [2b] manga-sanctuary (FR)"
    P2B_START=$(date +%s)
    _run_timed 600 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki manga-sanctuary \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02b-manga-sanctuary.log" 2>&1
    echo "    duración: $(($(date +%s) - P2B_START))s — items: $(count_lines)"

    # 2c. otaku-calendar
    echo ">>> [2c] otaku-calendar (EN/US)"
    P2C_START=$(date +%s)
    _run_timed 300 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki otaku-calendar \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02c-otaku-calendar.log" 2>&1
    echo "    duración: $(($(date +%s) - P2C_START))s — items: $(count_lines)"

    # 2d. manga-mexico
    echo ">>> [2d] manga-mexico (catálogo)"
    P2D_START=$(date +%s)
    _run_timed 300 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki manga-mexico \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02d-manga-mexico.log" 2>&1
    echo "    duración: $(($(date +%s) - P2D_START))s — items: $(count_lines)"

    # 2e. mangavariant (sitemap completo — solo FULL, no delta)
    echo ">>> [2e] mangavariant (~2700 entries del sitemap completo)"
    P2E_START=$(date +%s)
    _run_timed 1800 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki mangavariant \
        --sleep-seconds 0.3 \
        --min-score 20 \
        > "$LOG_DIR/02e-mangavariant.log" 2>&1
    echo "    duración: $(($(date +%s) - P2E_START))s — items: $(count_lines)"

    # 2f. socialanime
    echo ">>> [2f] socialanime (IT — variant + cofanetti)"
    P2F_START=$(date +%s)
    _run_timed 600 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki socialanime \
        --sleep-seconds 0.3 \
        --min-score 20 \
        > "$LOG_DIR/02f-socialanime.log" 2>&1
    echo "    duración: $(($(date +%s) - P2F_START))s — items: $(count_lines)"

    # 2g. blogbbm
    echo ">>> [2g] blogbbm (BR — capas variantes + volúmenes especiais)"
    P2G_START=$(date +%s)
    _run_timed 300 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki blogbbm \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02g-blogbbm.log" 2>&1
    echo "    duración: $(($(date +%s) - P2G_START))s — items: $(count_lines)"

    # 2h. booksprivilege — DESHABILITADO (2026-05-26)
    # Ver comentario en scrape_delta.sh [2g]. Misma razón.
    # echo ">>> [2h] booksprivilege — DESHABILITADO"

    # 2i. sumikko (JP — 限定版・特装版). El catálogo completo se recorre
    # en ~30 páginas (~30s con sleep 0.3). Idéntico a delta — el sitio
    # no expone filtro por fecha.
    echo ">>> [2i] sumikko (JP — 限定版/特装版 catálogo completo)"
    P2I_START=$(date +%s)
    _run_timed 600 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki sumikko \
        --sleep-seconds 0.3 \
        --min-score 20 \
        > "$LOG_DIR/02i-sumikko.log" 2>&1
    echo "    duración: $(($(date +%s) - P2I_START))s — items: $(count_lines)"

    # 2j. mangapassion (DE — catálogo completo histórico). En modo FULL
    # no aplicamos filtro de fecha (year_from=2000 < 2010 → descarga todo).
    echo ">>> [2j] mangapassion (DE — Sonderausgaben + Variant-Covers catálogo completo)"
    P2J_START=$(date +%s)
    _run_timed 1800 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki mangapassion \
        --wiki-from 2000-01 \
        --sleep-seconds 0.3 \
        --min-score 20 \
        > "$LOG_DIR/02j-mangapassion.log" 2>&1
    echo "    duración: $(($(date +%s) - P2J_START))s — items: $(count_lines)"

    # 2k. animeclick (IT — catálogo histórico desde 2015).
    # Navega el calendario semanal hacia atrás. ~500 semanas × detalle
    # por ~20% de items = potencialmente miles de HTTP fetches.
    echo ">>> [2k] animeclick (IT — edizioni speciali desde 2015)"
    P2K_START=$(date +%s)
    _run_timed 14400 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki animeclick \
        --wiki-from 2015-01 \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02k-animeclick.log" 2>&1
    echo "    duración: $(($(date +%s) - P2K_START))s — items: $(count_lines)"

    # 2l. prhcomics (EN/US — catálogo completo de ediciones especiales inglesas).
    # Una sola request, timeout muy corto.
    echo ">>> [2l] prhcomics (US/CA — hardcovers + box sets EN, catálogo completo)"
    P2L_START=$(date +%s)
    _run_timed 120 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki prhcomics \
        --wiki-from 2010-01 \
        --min-score 20 \
        > "$LOG_DIR/02l-prhcomics.log" 2>&1
    echo "    duración: $(($(date +%s) - P2L_START))s — items: $(count_lines)"

    # 2m. kinokuniya (EN/US — exclusivos Kinokuniya USA). Una sola request.
    echo ">>> [2m] kinokuniya (US — exclusivos Kinokuniya: variant covers + extras)"
    P2M_START=$(date +%s)
    _run_timed 120 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki kinokuniya \
        --min-score 20 \
        > "$LOG_DIR/02m-kinokuniya.log" 2>&1
    echo "    duración: $(($(date +%s) - P2M_START))s — items: $(count_lines)"

    # 2n. yenpress (EN/US — calendario histórico Yen Press, ediciones especiales).
    # Catálogo desde 2013-01 (lanzamiento de Yen Press como sello independiente).
    # ~140 meses × 0.5s sleep = ~70s. Timeout 600s.
    echo ">>> [2n] yenpress calendar (US — catálogo histórico collector's/deluxe/box set)"
    P2N_START=$(date +%s)
    _run_timed 600 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki yenpress \
        --wiki-from 2013-01 \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02n-yenpress.log" 2>&1
    echo "    duración: $(($(date +%s) - P2N_START))s — items: $(count_lines)"

    # 2o (OPT-IN). Whakoom spider (Cloudflare risk)
    if [ "$INCLUDE_WHAKOOM_SPIDER" = "1" ]; then
        echo ">>> [2o] whakoom spider (OPT-IN, riesgo Cloudflare)"
        P2O_START=$(date +%s)
        _run_timed 3600 "$VENV_PY" scripts/manga_watch.py \
            --bootstrap-wiki whakoom \
            --sleep-seconds 2.0 \
            --min-score 20 \
            > "$LOG_DIR/02o-whakoom.log" 2>&1
        echo "    duración: $(($(date +%s) - P2O_START))s — items: $(count_lines)"
    else
        echo "    [SKIP] whakoom spider profundo (INCLUDE_WHAKOOM_SPIDER=0)"
    fi

    echo " ✓ PHASE 2 wikis FULL done"
else
    echo "[SKIP] PHASE 2 (wikis) saltada por SKIP_WIKIS=1"
fi

# ============================================================
# PHASE 3: Cleanup retrofits
# ============================================================
if [ "$SKIP_CLEANUP" != "1" ]; then
    phase_header 3 "Cleanup retrofits"

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

    echo ">>> [4e2] backfill_metadata --only images (carrusel multi-imagen)"
    "$VENV_PY" scripts/retrofit/backfill_metadata.py --only images --sleep 0.5 \
        > "$LOG_DIR/04e2-backfill-galleries.log" 2>&1
    echo "    items: $(count_lines)"

    echo ">>> [4e3] mirror_images --no-gc (descarga gallery images al espejo local)"
    "$VENV_PY" scripts/retrofit/mirror_images.py --no-gc --workers 8 \
        > "$LOG_DIR/04e3-mirror-galleries.log" 2>&1
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

    echo " ✓ PHASE 3 cleanup done"
else
    echo "[SKIP] PHASE 3 (cleanup) saltada por SKIP_CLEANUP=1"
fi

# ============================================================
# PHASE 4: Build web
# ============================================================
if [ "$SKIP_BUILD" != "1" ]; then
    phase_header 4 "Build web"
    "$VENV_PY" scripts/build_web.py > "$LOG_DIR/04-build-web.log" 2>&1
    tail -10 "$LOG_DIR/04-build-web.log"
    echo " ✓ PHASE 4 build done"
else
    echo "[SKIP] PHASE 4 (build) saltada por SKIP_BUILD=1"
fi

# ============================================================
# FINAL SUMMARY
# ============================================================
GLOBAL_END=$(date +%s)
TOTAL=$((GLOBAL_END - GLOBAL_START))
AFTER_COUNT=$(count_lines)

echo
echo "========================================================"
echo " SCRAPE FULL COMPLETO"
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
echo "  - Este es el scrape FULL (recorrido del catálogo completo)."
echo "  - Frecuencia recomendada: 1x/mes o 1x/trimestre."
echo "  - Para deltas diarios/semanales (más rápido): ./scripts/scrape_delta.sh"
echo "  - Siguiente paso recomendado: correr /standardize-catalog si llegaron"
echo "    items nuevos sin standardized_at (chequear con el snippet del skill)."
echo
