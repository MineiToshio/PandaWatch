#!/usr/bin/env bash
#
# scrape_delta.sh — scraping INCREMENTAL ("delta").
#
# Detecta novedades RECIENTES. Pensado para correr **diario / semanal**.
# Es rápido (~30-60 min) y barato (pocos requests).
#
# Para listadomanga.es usa **`listadomanga-collections --coleccion-mode
# calendar`**: descubre los ids de colección con actividad en `calendario.php`
# en los últimos meses y parsea SOLO esas colecciones completas. Da la misma
# riqueza que el full (ediciones especiales / cofres / portadas alternativas /
# en preparación) pero acotado a lo reciente (~500-600 colecciones vs 3432).
#
# Para recorrer TODO el catálogo (~3432 colecciones vía lista.php), usar
# `scrape_full.sh` en su lugar (correr 1x/mes o 1x/trimestre).
#
# El resto de fuentes (Mangavariant, SocialAnime, BBM, Manga-Sanctuary,
# Whakoom, retailers Shopify/Tiendanube, etc.) se comportan igual entre
# delta y full por ahora — la diferencia es solo el método de discovery
# de listadomanga.
#
# Encadena las fases:
#   1. Scrape principal (sources del YAML, --max-pages 5, --enable-js)
#   2. Wiki bootstraps DELTA (listadomanga-collections modo calendar,
#      manga-sanctuary, otaku-calendar, manga-mexico, socialanime, blogbbm,
#      booksprivilege, sumikko, mangapassion DE, animeclick IT,
#      prhcomics US/CA, kinokuniya US, yenpress US)
#   3. Cleanup retrofits (rescore → filter_non_manga → filter_collectible →
#      clean_titles → backfill_metadata)
#   4. Build web final
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
#   SKIP_CLEANUP=1               # saltar fase 3
#   SKIP_BUILD=1                 # saltar fase 4
#   INCLUDE_WAYBACK_RECOVERY=1   # añade fase 3f (default OFF; pesado)
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

# ── Lock global: dos corridas simultáneas (delta o full) corromperían
# items.jsonl (escrituras concurrentes del flush). mkdir es atómico; el lock
# se considera stale si el PID que lo creó ya no existe.
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
    mkdir "$LOCK_DIR" && echo $$ > "$LOCK_DIR/pid"
    trap 'rm -rf "$LOCK_DIR"' EXIT
}
acquire_lock

TIMESTAMP=$(date '+%Y-%m-%d-%H%M%S')
LOG_DIR="logs/scrape-delta-${TIMESTAMP}"
mkdir -p "$LOG_DIR"

GLOBAL_LOG="$LOG_DIR/scrape-delta.log"
exec > >(tee -a "$GLOBAL_LOG") 2>&1

INCLUDE_WHAKOOM_SPIDER="${INCLUDE_WHAKOOM_SPIDER:-0}"
SKIP_SCRAPE="${SKIP_SCRAPE:-0}"
SKIP_WIKIS="${SKIP_WIKIS:-0}"
SKIP_CLEANUP="${SKIP_CLEANUP:-0}"
SKIP_BUILD="${SKIP_BUILD:-0}"
INCLUDE_WAYBACK_RECOVERY="${INCLUDE_WAYBACK_RECOVERY:-0}"
SCRAPE_WORKERS="${SCRAPE_WORKERS:-8}"
PER_HOST_LIMIT="${PER_HOST_LIMIT:-2}"

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
    # Fase 1 envuelta en timeout (90 min): una fuente HTTP colgada NO debe
    # bloquear el resto del pipeline. La escritura incremental por fuente
    # (flush_source_candidates) preserva lo ya scrapeado si el timeout dispara.
    _run_timed 5400 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
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

    # 2a. listadomanga-collections en modo CALENDAR (paridad con el full).
    # Descubre los ids con actividad en calendario.php (últimos 3 meses) y
    # parsea esas colecciones completas con el parser de colecciones — captura
    # ediciones especiales / cofres / variantes / en preparación, no solo el
    # entry del calendario. (El módulo de calendario plano `--bootstrap-wiki
    # listadomanga` sigue disponible pero ya no se usa en el pipeline canónico:
    # collections-calendar es estrictamente más rico sobre los mismos ids.)
    echo ">>> [2a] listadomanga-collections (calendar delta: actividad ${LISTADO_CAL_FROM} → mes actual)"
    P2A_START=$(date +%s)
    _run_timed 1800 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki listadomanga-collections \
        --coleccion-mode calendar \
        --wiki-from "$LISTADO_CAL_FROM" \
        --sleep-seconds 0.3 \
        --min-score 20 \
        > "$LOG_DIR/02a-listadomanga-collections-calendar.log" 2>&1
    echo "    duración: $(($(date +%s) - P2A_START))s — items: $(count_lines)"

    # 2b. manga-sanctuary (FR planning)
    echo ">>> [2b] manga-sanctuary (FR)"
    P2B_START=$(date +%s)
    _run_timed 600 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki manga-sanctuary \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02b-manga-sanctuary.log" 2>&1
    echo "    duración: $(($(date +%s) - P2B_START))s — items: $(count_lines)"

    # 2c. otaku-calendar (EN/US)
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

    # 2e. socialanime (IT)
    echo ">>> [2e] socialanime (IT — variant + cofanetti)"
    P2E_START=$(date +%s)
    _run_timed 600 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki socialanime \
        --sleep-seconds 0.3 \
        --min-score 20 \
        > "$LOG_DIR/02e-socialanime.log" 2>&1
    echo "    duración: $(($(date +%s) - P2E_START))s — items: $(count_lines)"

    # 2f. blogbbm (BR)
    echo ">>> [2f] blogbbm (BR — capas variantes + volúmenes especiais)"
    P2F_START=$(date +%s)
    _run_timed 300 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki blogbbm \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02f-blogbbm.log" 2>&1
    echo "    duración: $(($(date +%s) - P2F_START))s — items: $(count_lines)"

    # 2g. booksprivilege — DESHABILITADO (2026-05-26)
    # BooksPrivilege cubre 店舗特典 (bonuses de tienda para tomos regulares).
    # El 99.7% de sus items son tomos normales que solo se ven especiales por
    # el bonus de tienda, sin foto del extra y con descripción en japonés.
    # Confunde al usuario público que espera ver ediciones especiales reales.
    # Los 32 items realmente especiales (完全版/限定版/BOX) se conservaron en
    # el corpus; el resto fue limpiado. No re-correr esta fuente.
    # echo ">>> [2g] booksprivilege — DESHABILITADO"

    # 2h. sumikko (JP — 限定版・特装版). El sitio no tiene filtro por
    # fecha; siempre se recorre el catálogo entero (~30 páginas, ~30s)
    # ordenado por release_date desc. El upsert por URL deja sólo lo nuevo.
    echo ">>> [2h] sumikko (JP — 限定版/特装版 catálogo completo)"
    P2H_START=$(date +%s)
    _run_timed 600 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki sumikko \
        --sleep-seconds 0.3 \
        --min-score 20 \
        > "$LOG_DIR/02h-sumikko.log" 2>&1
    echo "    duración: $(($(date +%s) - P2H_START))s — items: $(count_lines)"

    # 2i. mangapassion (DE — Sonderausgaben + Variant-Covers). Modo delta:
    # date[after] = LISTADO_CAL_FROM (últimos 3 meses). La API es pública,
    # sin auth, sin anti-bot — no requiere Playwright.
    echo ">>> [2i] mangapassion (DE — Sonderausgaben + Variant-Covers últimos 3 meses)"
    P2I_START=$(date +%s)
    _run_timed 600 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki mangapassion \
        --wiki-from "$LISTADO_CAL_FROM" \
        --sleep-seconds 0.3 \
        --min-score 20 \
        > "$LOG_DIR/02i-mangapassion.log" 2>&1
    echo "    duración: $(($(date +%s) - P2I_START))s — items: $(count_lines)"

    # 2j. animeclick (IT — variant/limitata/cofanetto últimos 3 meses).
    # Cubre Star Comics, Panini Comics, J-POP, MangaYo! y otros publishers
    # IT que SocialAnime no tiene. Sin ISBN pero con precio y fecha.
    # Timeout generoso (2700s = 45min) porque fetcha detail pages por cada item.
    echo ">>> [2j] animeclick (IT — edizioni speciali últimos 3 meses)"
    P2J_START=$(date +%s)
    _run_timed 2700 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki animeclick \
        --wiki-from "$LISTADO_CAL_FROM" \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02j-animeclick.log" 2>&1
    echo "    duración: $(($(date +%s) - P2J_START))s — items: $(count_lines)"

    # 2k. prhcomics (EN/US — catálogo de ediciones especiales inglesas de PRH).
    # Una sola request HTTP estática, timeout corto.
    echo ">>> [2k] prhcomics (US/CA — hardcovers + box sets EN)"
    P2K_START=$(date +%s)
    _run_timed 120 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki prhcomics \
        --wiki-from "$LISTADO_CAL_FROM" \
        --min-score 20 \
        > "$LOG_DIR/02k-prhcomics.log" 2>&1
    echo "    duración: $(($(date +%s) - P2K_START))s — items: $(count_lines)"

    # 2l. kinokuniya (EN/US — exclusivos Kinokuniya USA: variant covers, dust
    # jackets, shikishi, ID cards, sticker packs). Una sola request, timeout corto.
    echo ">>> [2l] kinokuniya (US — exclusivos Kinokuniya: variant covers + extras)"
    P2L_START=$(date +%s)
    _run_timed 120 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki kinokuniya \
        --min-score 20 \
        > "$LOG_DIR/02l-kinokuniya.log" 2>&1
    echo "    duración: $(($(date +%s) - P2L_START))s — items: $(count_lines)"

    # 2m. yenpress (EN/US — calendario mensual Yen Press, ediciones especiales).
    # Itera los últimos 3 meses del calendario; timeout 300s.
    echo ">>> [2m] yenpress calendar (US — collector's, deluxe, box set, hardcover)"
    P2M_START=$(date +%s)
    _run_timed 300 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki yenpress \
        --wiki-from "$LISTADO_CAL_FROM" \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02m-yenpress.log" 2>&1
    echo "    duración: $(($(date +%s) - P2M_START))s — items: $(count_lines)"

    # 2n. shueisha (JP — artbooks, magazines, databooks nuevos).
    # Modo delta: --wiki-from con YYYY-MM reciente (year_from >= 2020 activa
    # el modo delta interno del parser, que sólo trae volúmenes nuevos).
    echo ">>> [2n] shueisha books (JP — delta: new Magazine/Color Walk volumes)"
    P2N_START=$(date +%s)
    _run_timed 600 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki shueisha \
        --wiki-from "$LISTADO_CAL_FROM" \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02n-shueisha.log" 2>&1
    echo "    duración: $(($(date +%s) - P2N_START))s — items: $(count_lines)"

    # 2o. viz artbooks (US — small catalog, quick).
    echo ">>> [2o] viz artbooks (US — Color Walk Compendium, companion books)"
    P2O_START=$(date +%s)
    _run_timed 300 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki viz \
        --wiki-from "$LISTADO_CAL_FROM" \
        --sleep-seconds 1.0 \
        --min-score 20 \
        > "$LOG_DIR/02o-viz.log" 2>&1
    echo "    duración: $(($(date +%s) - P2O_START))s — items: $(count_lines)"

    # 2p. sevenseas (US — deluxe/box sets/collector vía WordPress API).
    # Modo delta: after=LISTADO_CAL_FROM (posts nuevos = anuncios nuevos).
    # Enrich por item (ISBN/portada/fecha) — el dispatcher fuerza fetch_details.
    echo ">>> [2p] sevenseas (US — deluxe hardcovers + box sets, últimos 3 meses)"
    P2P_START=$(date +%s)
    _run_timed 900 "$VENV_PY" scripts/manga_watch.py \
        --bootstrap-wiki sevenseas \
        --wiki-from "$LISTADO_CAL_FROM" \
        --sleep-seconds 0.3 \
        --min-score 20 \
        > "$LOG_DIR/02p-sevenseas.log" 2>&1
    echo "    duración: $(($(date +%s) - P2P_START))s — items: $(count_lines)"

    # 2q (OPT-IN). Whakoom spider (Cloudflare risk)
    if [ "$INCLUDE_WHAKOOM_SPIDER" = "1" ]; then
        echo ">>> [2q] whakoom spider (OPT-IN, riesgo Cloudflare)"
        P2N_START=$(date +%s)
        _run_timed 3600 "$VENV_PY" scripts/manga_watch.py \
            --bootstrap-wiki whakoom \
            --sleep-seconds 2.0 \
            --min-score 20 \
            > "$LOG_DIR/02q-whakoom.log" 2>&1
        echo "    duración: $(($(date +%s) - P2N_START))s — items: $(count_lines)"
    else
        echo "    [SKIP] whakoom spider profundo (INCLUDE_WHAKOOM_SPIDER=0)"
    fi

    echo " ✓ PHASE 2 wikis done"
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

    if [ "$INCLUDE_WAYBACK_RECOVERY" = "1" ]; then
        echo ">>> [4f] wayback_recover (OPT-IN)"
        P4F_START=$(date +%s)
        "$VENV_PY" -u scripts/retrofit/wayback_recover.py --sleep 1.0 \
            > "$LOG_DIR/04f-wayback-recover.log" 2>&1
        echo "    duración: $(($(date +%s) - P4F_START))s — items: $(count_lines)"
    else
        echo "    [SKIP] wayback recovery (INCLUDE_WAYBACK_RECOVERY=0)"
    fi

    # [4f2] alinea items raw a la edición estandarizada de su MISMA coleccion
    # (regla coleccion=edición). Re-scrapear una coleccion ya estandarizada deja
    # el item raw nuevo con edition_key/cluster_key distinto del viejo → no
    # consolidan (dup raw-vs-std, ej. "Bastard!! nº1" vs "Bastard!! Deluxe 1").
    # Debe correr ANTES de consolidate_sources para que el merge los fusione.
    echo ">>> [4f2] align_raw_to_std_coleccion (dedup raw-vs-estandarizado)"
    "$VENV_PY" scripts/retrofit/align_raw_to_std_coleccion.py \
        > "$LOG_DIR/04f2-align-raw-std.log" 2>&1
    echo "    items: $(count_lines)"

    # [4f3] ENFORCER de reglas listadomanga (--fast: sin dedup de carrusel, que
    # corre aparte en [4h]). Reemplaza a los pasos sueltos fix_edition_country /
    # unify_coleccion / backfill_cluster_key / slugs / consolidate: el re-scrape
    # del calendario sobre colecciones YA estandarizadas deja duplicados
    # raw-vs-std (DUPSYN/DUPVOL/TITLE) que solo la cadena completa del enforcer
    # repara (verificado 2026-06-12: delta real dejaba 53 violaciones duras sin
    # esto; con el enforcer → 0). Idempotente.
    echo ">>> [4f3] enforce_listadomanga_rules --fast (cadena completa de agrupación)"
    P4F3_START=$(date +%s)
    "$VENV_PY" scripts/retrofit/enforce_listadomanga_rules.py --fast \
        > "$LOG_DIR/04f3-enforce-lmc.log" 2>&1
    echo "    duración: $(($(date +%s) - P4F3_START))s — items: $(count_lines)"

    # [4h] dedup de portada en el carrusel: consolidate_sources UNE imágenes de
    # fuentes hermanas → puede quedar la MISMA portada en dos resoluciones. Quita
    # la de menor resolución (hash perceptual). Network-bound (descarga thumbs).
    echo ">>> [4h] dedup_carousel_images (misma portada en 2 resoluciones)"
    P4H_START=$(date +%s)
    _run_timed 1200 "$VENV_PY" scripts/retrofit/dedup_carousel_images.py \
        > "$LOG_DIR/04h-dedup-carousel.log" 2>&1
    echo "    duración: $(($(date +%s) - P4H_START))s — items: $(count_lines)"

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
# PHASE 5: Validación estructural del corpus (gate de salud)
# ============================================================
echo
echo ">>> [5] validate_corpus (invariantes estructurales — gotcha #54)"
"$VENV_PY" scripts/validate_corpus.py | tee "$LOG_DIR/05-validate-corpus.log" || \
    echo " ⚠ validate_corpus reportó violaciones DURAS — revisar $LOG_DIR/05-validate-corpus.log"

# ============================================================
# PHASE 6: Salud de fuentes de ESTE run (observabilidad)
# ============================================================
echo
echo ">>> [6] source_health (fuentes con errores / 0 candidatos en este run)"
"$VENV_PY" scripts/audit/source_health.py --last-n 1 --output md \
    --output-file "$LOG_DIR/06-source-health.md" 2>/dev/null \
    && grep -E "^## |^\| " "$LOG_DIR/06-source-health.md" | head -40 \
    || echo " ⚠ source_health falló (no bloquea)"

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
