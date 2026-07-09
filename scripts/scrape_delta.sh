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
# Mangavariant corre en AMBOS modos pero distinto: el full baja las ~2700 URLs
# del sitemap; el delta baja los sitemaps y fetchea SOLO las variantes cuya URL
# no está ya en el corpus (diff incremental, tope MANGAVARIANT_MAX_NEW, orden por
# lastmod desc). El resto de fuentes (SocialAnime, BBM, Manga-Sanctuary, Whakoom,
# retailers Shopify/Tiendanube, etc.) se comportan igual entre delta y full por
# ahora — la otra diferencia grande es el método de discovery de listadomanga.
#
# Encadena las fases:
#   1. Scrape principal (sources del YAML, --max-pages 5, --enable-js)
#   2. Wiki bootstraps DELTA (listadomanga-collections modo calendar,
#      manga-sanctuary, otaku-calendar, manga-mexico, socialanime, blogbbm,
#      booksprivilege, sumikko, mangapassion DE, animeclick IT,
#      prhcomics US/CA, kinokuniya US, yenpress US,
#      mangavariant incremental)
#   3. Cleanup retrofits (rescore → clean_titles → normalize_release_dates →
#      filter_non_manga → filter_collectible → backfill_metadata)
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
# Marker de aborto (Ctrl+C/SIGTERM a mitad de run, ver S4 auditoría 2026-07-08):
# el trap de INT/TERM lo escribe ANTES de salir; el trap EXIT lo consulta para
# decidir si es seguro liberar el lock. Nunca se borra "gate" solo — si esto
# existe, un corpus a mitad de pasos pudo quedar inválido y nadie corrió
# validate_corpus sobre él.
ABORT_MARKER="data/.run-aborted"
CURRENT_PHASE="init (pre-lock)"

_release_lock_on_exit() {
    if [ -f "$ABORT_MARKER" ]; then
        echo
        echo "⚠️  Salida por señal (INT/TERM) — el lock $LOCK_DIR NO se libera automáticamente."
        echo "    Marker: $ABORT_MARKER. Antes de volver a correr un scrape:"
        echo "      1) revisar el corpus:  .venv/bin/python scripts/validate_corpus.py"
        echo "      2) si está OK, borrar el marker y el lock a mano: rm -f \"$ABORT_MARKER\"; rm -rf \"$LOCK_DIR\""
        return
    fi
    rm -rf "$LOCK_DIR"
}

_on_abort_signal() {
    local sig=$1
    mkdir -p data
    printf '{"signal":"%s","phase":"%s","at":"%s","pid":%s}\n' \
        "$sig" "$CURRENT_PHASE" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$$" > "$ABORT_MARKER"
    echo
    echo "⚠️  Señal $sig recibida durante: $CURRENT_PHASE — abortando."
    echo "    Marker escrito en $ABORT_MARKER (el lock queda tomado a propósito)."
    exit 130
}
trap '_on_abort_signal INT' INT
trap '_on_abort_signal TERM' TERM

acquire_lock() {
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        echo $$ > "$LOCK_DIR/pid"
        trap '_release_lock_on_exit' EXIT
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
    # Carrera (S2, auditoría 2026-07-08): si dos procesos detectan el lock stale
    # a la vez, sólo uno gana el mkdir de abajo. Antes el perdedor seguía sin
    # lock (mkdir && echo no aborta si mkdir falla) y su trap EXIT heredado
    # borraba el lock del ganador al salir. Ahora el perdedor ABORTA.
    if ! mkdir "$LOCK_DIR" 2>/dev/null; then
        echo "❌ Perdí la carrera por el lock stale (otro proceso lo tomó primero). Abortando."
        exit 1
    fi
    echo $$ > "$LOCK_DIR/pid"
    trap '_release_lock_on_exit' EXIT
}
acquire_lock

TIMESTAMP=$(date '+%Y-%m-%d-%H%M%S')
LOG_DIR="logs/scrape-delta-${TIMESTAMP}"
mkdir -p "$LOG_DIR"

# Rotación de logs (B16, 2026-07-08): logs/scrape-* crece 1 directorio por
# corrida sin límite. Podamos a los últimos 14 (ordenados por mtime; el recién
# creado arriba ya cuenta como el más nuevo). data/metrics.jsonl NO se rota
# acá — lo consume source_health.py (histórico de baseline), otro paquete lo toca.
_prune_old_logs() {
    local keep=14
    ls -1dt logs/scrape-* 2>/dev/null | tail -n +$((keep + 1)) | while IFS= read -r old_dir; do
        rm -rf "$old_dir"
    done
}
_prune_old_logs

GLOBAL_LOG="$LOG_DIR/scrape-delta.log"
exec > >(tee -a "$GLOBAL_LOG") 2>&1

if [ -f "$ABORT_MARKER" ]; then
    echo "⚠️  Se encontró $ABORT_MARKER de una corrida anterior interrumpida (INT/TERM)."
    echo "    Detalle: $(cat "$ABORT_MARKER" 2>/dev/null)"
    echo "    Se borra tras el backup pre-scrape de ESTA corrida (ver abajo)."
    echo
fi

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

# Para el delta el calendario de listadomanga toma una VENTANA centrada en hoy:
#  - FROM: últimos 3 meses (mes actual + 2 anteriores) → novedades recientes.
#  - TO:   próximos 3 meses → "en preparación" / preventas ya anunciadas.
# calendario.php sirve meses futuros poblados; sin --wiki-to la ventana quedaba
# [hoy-2m..hoy] y se perdían los anuncios futuros (P1).
LISTADO_CAL_FROM="${LISTADO_CAL_FROM:-$(date -v-2m '+%Y-%m' 2>/dev/null || date -d '2 months ago' '+%Y-%m' 2>/dev/null || date '+%Y-%m')}"
LISTADO_CAL_TO="${LISTADO_CAL_TO:-$(date -v+3m '+%Y-%m' 2>/dev/null || date -d '3 months' '+%Y-%m' 2>/dev/null || date '+%Y-%m')}"

GLOBAL_START=$(date +%s)

echo "========================================================"
echo " MANGA WATCH — SCRAPE DELTA (incremental)"
echo " Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo " Log dir: $LOG_DIR"
echo "========================================================"
echo
echo "Config:"
echo "  Listadomanga calendar: $LISTADO_CAL_FROM → $LISTADO_CAL_TO"
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
    CURRENT_PHASE="PHASE $phase: $title"
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

# Acumulador de pasos que crashean (exit≠0). Con `set +e` un retrofit o wiki
# bootstrap que muere es invisible; record_step lo captura para el FINAL SUMMARY.
FAILED_STEPS=()
record_step() {
    # record_step <nombre> <returncode>
    local name=$1 rc=$2
    if [ "$rc" -ne 0 ]; then
        FAILED_STEPS+=("$name (rc=$rc)")
        echo "    ⚠ STEP FALLÓ: $name (rc=$rc)"
    fi
}

# ── Backup pre-scrape de items.jsonl (convención backup_and_rotate del repo:
# escribe en data/backups/items.jsonl/, rota máx 3). Un snapshot ANTES de que
# el run toque nada permite restaurar si algo corrompe el corpus.
# Capturamos el PATH del backup (no solo lo logueamos): PHASE 4 lo usa para
# restaurar automáticamente si el corpus post-run queda inválido.
PRESCRAPE_BACKUP=""
CURRENT_PHASE="backup pre-scrape"
if [ -s data/items.jsonl ]; then
    echo ">>> Backup pre-scrape de data/items.jsonl"
    PRESCRAPE_BACKUP=$(env PYTHONUNBUFFERED=1 "$VENV_PY" -u -c \
        "import sys; sys.path.insert(0,'scripts'); from pathlib import Path; from manga_watch import backup_and_rotate; print(backup_and_rotate(Path('data/items.jsonl'), 'scrape-delta'))")
    if [ -n "$PRESCRAPE_BACKUP" ] && [ -f "$PRESCRAPE_BACKUP" ]; then
        echo "    backup → $PRESCRAPE_BACKUP"
    else
        echo "    ⚠ backup pre-scrape falló (continúa)"
        PRESCRAPE_BACKUP=""
    fi
    echo
fi

# Marker de una corrida anterior abortada por señal (S4): una vez que ESTA
# corrida ya tiene su propio backup pre-scrape fresco, el marker viejo perdió
# su utilidad informativa — se borra para no confundir la próxima corrida.
if [ -f "$ABORT_MARKER" ]; then
    rm -f "$ABORT_MARKER"
fi

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
    P1_RC=$?
    P1_END=$(date +%s)
    phase_done 1 $((P1_END - P1_START)) "$(count_lines)"
    # S1 (auditoría 2026-07-08): antes un crash/timeout de la Fase 1 era
    # invisible en FAILED_STEPS/SUMMARY porque no pasaba por record_step.
    if [ "$P1_RC" -eq 124 ]; then
        echo "    ⚠ Fase 1 alcanzó el TIMEOUT (90 min, rc=124) — se preservó lo ya flusheado por fuente."
    fi
    record_step "scrape-principal" "$P1_RC"
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
    _run_timed 1800 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki listadomanga-collections \
        --coleccion-mode calendar \
        --wiki-from "$LISTADO_CAL_FROM" \
        --wiki-to "$LISTADO_CAL_TO" \
        --sleep-seconds 0.3 \
        --min-score 20 \
        > "$LOG_DIR/02a-listadomanga-collections-calendar.log" 2>&1
    record_step "listadomanga-collections" $?
    echo "    duración: $(($(date +%s) - P2A_START))s — items: $(count_lines)"

    # 2b. manga-sanctuary (FR planning)
    echo ">>> [2b] manga-sanctuary (FR)"
    P2B_START=$(date +%s)
    _run_timed 600 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki manga-sanctuary \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02b-manga-sanctuary.log" 2>&1
    record_step "manga-sanctuary" $?
    echo "    duración: $(($(date +%s) - P2B_START))s — items: $(count_lines)"

    # 2c. otaku-calendar (EN/US). VENTANA ACOTADA estilo listadomanga: sin
    # --wiki-from/--wiki-to el dispatcher usa su default (2024-01 → mes actual =
    # ~31 meses). Desde el fix por-path (2026-07-07) cada mes es UNA página REAL
    # (antes las 31 iteraciones bajaban la misma página), así que el delta diario
    # backfillearía 31 meses distintos cada vez — lento e innecesario para un
    # delta. Reusamos la ventana del calendario (LISTADO_CAL_FROM..TO = hoy-2m →
    # hoy+3m = 6 meses): novedades recientes + preventas anunciadas (el sitio SÍ
    # sirve meses futuros poblados; verificado 2026-07-07). Costo medido: 1
    # request/mes (sin detail fetch), ~0.6s/mes → 6 meses ≈ 10s. Timeout 120s =
    # holgado (~12× lo esperado) pero bounded para no colgar el run diario.
    echo ">>> [2c] otaku-calendar (EN/US — ventana ${LISTADO_CAL_FROM} → ${LISTADO_CAL_TO})"
    P2C_START=$(date +%s)
    _run_timed 120 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki otaku-calendar \
        --wiki-from "$LISTADO_CAL_FROM" \
        --wiki-to "$LISTADO_CAL_TO" \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02c-otaku-calendar.log" 2>&1
    record_step "otaku-calendar" $?
    echo "    duración: $(($(date +%s) - P2C_START))s — items: $(count_lines)"

    # 2d. manga-mexico
    echo ">>> [2d] manga-mexico (catálogo)"
    P2D_START=$(date +%s)
    _run_timed 300 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki manga-mexico \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02d-manga-mexico.log" 2>&1
    record_step "manga-mexico" $?
    echo "    duración: $(($(date +%s) - P2D_START))s — items: $(count_lines)"

    # 2e. socialanime (IT)
    echo ">>> [2e] socialanime (IT — variant + cofanetti)"
    P2E_START=$(date +%s)
    _run_timed 600 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki socialanime \
        --sleep-seconds 0.3 \
        --min-score 20 \
        > "$LOG_DIR/02e-socialanime.log" 2>&1
    record_step "socialanime" $?
    echo "    duración: $(($(date +%s) - P2E_START))s — items: $(count_lines)"

    # 2f. blogbbm (BR)
    echo ">>> [2f] blogbbm (BR — capas variantes + volúmenes especiais)"
    P2F_START=$(date +%s)
    _run_timed 300 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki blogbbm \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02f-blogbbm.log" 2>&1
    record_step "blogbbm" $?
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
    _run_timed 600 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki sumikko \
        --sleep-seconds 0.3 \
        --min-score 20 \
        > "$LOG_DIR/02h-sumikko.log" 2>&1
    record_step "sumikko" $?
    echo "    duración: $(($(date +%s) - P2H_START))s — items: $(count_lines)"

    # 2i. mangapassion (DE — Sonderausgaben + Variant-Covers). Modo delta:
    # date[after] = LISTADO_CAL_FROM (últimos 3 meses). La API es pública,
    # sin auth, sin anti-bot — no requiere Playwright.
    echo ">>> [2i] mangapassion (DE — Sonderausgaben + Variant-Covers últimos 3 meses)"
    P2I_START=$(date +%s)
    _run_timed 600 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki mangapassion \
        --wiki-from "$LISTADO_CAL_FROM" \
        --sleep-seconds 0.3 \
        --min-score 20 \
        > "$LOG_DIR/02i-mangapassion.log" 2>&1
    record_step "mangapassion" $?
    echo "    duración: $(($(date +%s) - P2I_START))s — items: $(count_lines)"

    # 2j. animeclick (IT — variant/limitata/cofanetto últimos 3 meses).
    # Cubre Star Comics, Panini Comics, J-POP, MangaYo! y otros publishers
    # IT que SocialAnime no tiene. Sin ISBN pero con precio y fecha.
    # Timeout generoso (2700s = 45min) porque fetcha detail pages por cada item.
    echo ">>> [2j] animeclick (IT — edizioni speciali últimos 3 meses)"
    P2J_START=$(date +%s)
    _run_timed 2700 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki animeclick \
        --wiki-from "$LISTADO_CAL_FROM" \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02j-animeclick.log" 2>&1
    record_step "animeclick" $?
    echo "    duración: $(($(date +%s) - P2J_START))s — items: $(count_lines)"

    # 2k. prhcomics (EN/US — catálogo de ediciones especiales inglesas de PRH).
    # Una sola request HTTP estática, timeout corto.
    echo ">>> [2k] prhcomics (US/CA — hardcovers + box sets EN)"
    P2K_START=$(date +%s)
    _run_timed 120 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki prhcomics \
        --wiki-from "$LISTADO_CAL_FROM" \
        --min-score 20 \
        > "$LOG_DIR/02k-prhcomics.log" 2>&1
    record_step "prhcomics" $?
    echo "    duración: $(($(date +%s) - P2K_START))s — items: $(count_lines)"

    # 2l. kinokuniya (EN/US — exclusivos Kinokuniya USA: variant covers, dust
    # jackets, shikishi, ID cards, sticker packs). Una sola request, timeout corto.
    echo ">>> [2l] kinokuniya (US — exclusivos Kinokuniya: variant covers + extras)"
    P2L_START=$(date +%s)
    _run_timed 120 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki kinokuniya \
        --min-score 20 \
        > "$LOG_DIR/02l-kinokuniya.log" 2>&1
    record_step "kinokuniya" $?
    echo "    duración: $(($(date +%s) - P2L_START))s — items: $(count_lines)"

    # 2m. yenpress (EN/US — calendario mensual Yen Press, ediciones especiales).
    # Itera los últimos 3 meses del calendario; timeout 300s.
    echo ">>> [2m] yenpress calendar (US — collector's, deluxe, box set, hardcover)"
    P2M_START=$(date +%s)
    _run_timed 300 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki yenpress \
        --wiki-from "$LISTADO_CAL_FROM" \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02m-yenpress.log" 2>&1
    record_step "yenpress" $?
    echo "    duración: $(($(date +%s) - P2M_START))s — items: $(count_lines)"

    # 2n. shueisha (JP — artbooks, magazines, databooks nuevos).
    # Modo delta: --wiki-from con YYYY-MM reciente (year_from >= 2020 activa
    # el modo delta interno del parser, que sólo trae volúmenes nuevos).
    echo ">>> [2n] shueisha books (JP — delta: new Magazine/Color Walk volumes)"
    P2N_START=$(date +%s)
    _run_timed 600 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki shueisha \
        --wiki-from "$LISTADO_CAL_FROM" \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02n-shueisha.log" 2>&1
    record_step "shueisha" $?
    echo "    duración: $(($(date +%s) - P2N_START))s — items: $(count_lines)"

    # 2o. viz artbooks (US — small catalog, quick).
    echo ">>> [2o] viz artbooks (US — Color Walk Compendium, companion books)"
    P2O_START=$(date +%s)
    _run_timed 300 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki viz \
        --wiki-from "$LISTADO_CAL_FROM" \
        --sleep-seconds 1.0 \
        --min-score 20 \
        > "$LOG_DIR/02o-viz.log" 2>&1
    record_step "viz" $?
    echo "    duración: $(($(date +%s) - P2O_START))s — items: $(count_lines)"

    # 2p. sevenseas (US — deluxe/box sets/collector vía WordPress API).
    # Modo delta: after=LISTADO_CAL_FROM (posts nuevos = anuncios nuevos).
    # Enrich por item (ISBN/portada/fecha) — el dispatcher fuerza fetch_details.
    echo ">>> [2p] sevenseas (US — deluxe hardcovers + box sets, últimos 3 meses)"
    P2P_START=$(date +%s)
    _run_timed 900 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki sevenseas \
        --wiki-from "$LISTADO_CAL_FROM" \
        --sleep-seconds 0.3 \
        --min-score 20 \
        > "$LOG_DIR/02p-sevenseas.log" 2>&1
    record_step "sevenseas" $?
    echo "    duración: $(($(date +%s) - P2P_START))s — items: $(count_lines)"

    # 2r. kodansha-us (US — deluxe/omnibus/collector vía API kodansha.us).
    # Modo delta: solo volúmenes con datePublished >= LISTADO_CAL_FROM.
    echo ">>> [2r] kodansha-us (US — deluxe + omnibus + collector, últimos 3 meses)"
    P2R_START=$(date +%s)
    _run_timed 600 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki kodansha-us \
        --wiki-from "$LISTADO_CAL_FROM" \
        --sleep-seconds 0.5 \
        --min-score 20 \
        > "$LOG_DIR/02r-kodansha-us.log" 2>&1
    record_step "kodansha-us" $?
    echo "    duración: $(($(date +%s) - P2R_START))s — items: $(count_lines)"

    # 2s. storefronts API (HK/TW/VN/TH — catálogos completos, son chicos y
    # el upsert es idempotente; storefront_json.py, 2026-06-12).
    echo ">>> [2s] storefronts API (jd-intl HK · spp-tw · kimdong/ipm VN · yaakz TH)"
    P2S_START=$(date +%s)
    for SF in jd-intl spp-tw kimdong ipm yaakz; do
        _run_timed 900 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
            --bootstrap-wiki "$SF" \
            --sleep-seconds 0.3 \
            --min-score 20 \
            > "$LOG_DIR/02s-$SF.log" 2>&1
        record_step "storefront:$SF" $?
    done
    echo "    duración: $(($(date +%s) - P2S_START))s — items: $(count_lines)"

    # 2t. mangavariant INCREMENTAL (variantes/ediciones nuevas del catálogo global).
    # A diferencia del full (que baja las ~2700 URLs del sitemap), el delta baja
    # los sitemaps (costo fijo: sitemaps + 1 resolución del challenge sgcaptcha) y
    # fetchea SOLO las variantes cuya URL NO está ya en data/items.jsonl (diff
    # contra el corpus), ordenadas por lastmod desc (las más recientes primero) y
    # acotadas por MANGAVARIANT_MAX_NEW (tope de seguridad; si se topa, LOGuea).
    # Así las ediciones variantes nuevas entran en el delta diario en vez de
    # esperar hasta el próximo full (antes: hasta ~3 meses de lag).
    # Requiere Playwright para el challenge; sin él degrada con WARN e importa 0.
    # Timeout 1200s: challenge (~5-8s, one-shot) + 3 sitemaps + hasta 400 detail
    # pages (workers=4 default × ~1.5s ÷ 4 ≈ 150s) + mirror de portadas nuevas.
    # ≈ 4-8× lo esperado, pero bounded para no colgar el run diario.
    echo ">>> [2t] mangavariant incremental (variantes nuevas vs corpus, tope 400)"
    P2T_START=$(date +%s)
    _run_timed 1200 env MANGAVARIANT_INCREMENTAL=1 MANGAVARIANT_MAX_NEW=400 \
        PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
        --bootstrap-wiki mangavariant \
        --sleep-seconds 0.3 \
        --min-score 20 \
        > "$LOG_DIR/02t-mangavariant-incremental.log" 2>&1
    record_step "mangavariant-incremental" $?
    echo "    duración: $(($(date +%s) - P2T_START))s — items: $(count_lines)"

    # 2q (OPT-IN). Whakoom spider (Cloudflare risk)
    if [ "$INCLUDE_WHAKOOM_SPIDER" = "1" ]; then
        echo ">>> [2q] whakoom spider (OPT-IN, riesgo Cloudflare)"
        P2N_START=$(date +%s)
        _run_timed 3600 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/manga_watch.py \
            --bootstrap-wiki whakoom \
            --sleep-seconds 2.0 \
            --min-score 20 \
            > "$LOG_DIR/02q-whakoom.log" 2>&1
        record_step "whakoom" $?
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
    record_step "rescore" $?
    echo "    items: $(count_lines)"

    # [4b] clean_titles ANTES de los filtros (P2): los gates filter_non_manga /
    # filter_collectible deben evaluar el TÍTULO LIMPIO, no el crudo — si no, un
    # título que sólo pasa/rechaza tras limpiarse produce no-idempotencia.
    echo ">>> [4b] clean_titles (antes de los filtros)"
    "$VENV_PY" scripts/retrofit/clean_titles.py > "$LOG_DIR/04b-clean-titles.log" 2>&1
    record_step "clean_titles" $?
    echo "    items: $(count_lines)"

    # [4b2] normalize_release_dates: barato (compute-only, sin red) y no-op
    # cuando el corpus ya está normalizado — se corre acá porque
    # `normalize_release_date()` ya es la guardia universal en el sink del
    # scraper (candidate_to_json), así que items NUEVOS entran limpios; este
    # paso solo re-normaliza legacy que sobrevivió (backups restaurados,
    # merges de fuentes con formato crudo). `--all-formats` (no solo
    # DD/MM/YYYY) porque la auditoría DATEISO real (113 filas) es casi toda
    # datetime de tienda JP (`YYYY/MM/DD hh:mm:ss`) — sin el flag el paso
    # queda no-op y el backlog nunca converge. Antes de los filtros por el
    # mismo motivo que 4b: no debería afectarlos, pero mantiene el orden
    # estable.
    echo ">>> [4b2] normalize_release_dates --all-formats"
    _run_timed 120 env PYTHONUNBUFFERED=1 "$VENV_PY" -u scripts/retrofit/normalize_release_dates.py \
        --all-formats \
        > "$LOG_DIR/04b2-normalize-release-dates.log" 2>&1
    record_step "normalize_release_dates" $?
    echo "    items: $(count_lines)"

    echo ">>> [4c] filter_non_manga"
    "$VENV_PY" scripts/retrofit/filter_non_manga.py > "$LOG_DIR/04c-filter-non-manga.log" 2>&1
    record_step "filter_non_manga" $?
    echo "    items: $(count_lines)"

    echo ">>> [4d] filter_collectible"
    "$VENV_PY" scripts/retrofit/filter_collectible.py > "$LOG_DIR/04d-filter-collectible.log" 2>&1
    record_step "filter_collectible" $?
    echo "    items: $(count_lines)"

    # [4e] backfill_metadata --only image_url hace 1 request HTTP por item
    # pendiente de portada — sin _run_timed antes (regresión de gotcha #33, S3
    # auditoría 2026-07-08): un host colgado bloqueaba el run entero y
    # mantenía el lock global tomado por horas.
    echo ">>> [4e] backfill_metadata --only image_url"
    P4E_START=$(date +%s)
    _run_timed 1800 "$VENV_PY" scripts/retrofit/backfill_metadata.py --only image_url --sleep 0.5 \
        > "$LOG_DIR/04e-backfill-images.log" 2>&1
    record_step "backfill_metadata:image_url" $?
    echo "    duración: $(($(date +%s) - P4E_START))s — items: $(count_lines)"

    if [ "$INCLUDE_WAYBACK_RECOVERY" = "1" ]; then
        echo ">>> [4f] wayback_recover (OPT-IN)"
        P4F_START=$(date +%s)
        _run_timed 3600 "$VENV_PY" -u scripts/retrofit/wayback_recover.py --sleep 1.0 \
            > "$LOG_DIR/04f-wayback-recover.log" 2>&1
        record_step "wayback_recover" $?
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
    record_step "align_raw_to_std_coleccion" $?
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
    record_step "enforce_listadomanga_rules" $?
    echo "    duración: $(($(date +%s) - P4F3_START))s — items: $(count_lines)"

    # [4h] dedup de portada en el carrusel: consolidate_sources UNE imágenes de
    # fuentes hermanas → puede quedar la MISMA portada en dos resoluciones. Quita
    # la de menor resolución (hash perceptual). Network-bound (descarga thumbs).
    echo ">>> [4h] dedup_carousel_images (misma portada en 2 resoluciones)"
    P4H_START=$(date +%s)
    _run_timed 1200 "$VENV_PY" scripts/retrofit/dedup_carousel_images.py \
        > "$LOG_DIR/04h-dedup-carousel.log" 2>&1
    record_step "dedup_carousel_images" $?
    echo "    duración: $(($(date +%s) - P4H_START))s — items: $(count_lines)"

    # [4i] purga de placeholders: algunas fuentes sirven una imagen genérica
    # ("no disponible"/"coming soon"), un pixel 1×1 o un blanco cuando no tienen
    # portada. Se quitan de images[] para que la card caiga al 📚 (no a un
    # placeholder remoto). Sin red — lee el espejo local. Idempotente.
    echo ">>> [4i] purge_placeholder_images (1×1 / blancos / 'no disponible')"
    "$VENV_PY" scripts/retrofit/purge_placeholder_images.py \
        > "$LOG_DIR/04i-purge-placeholders.log" 2>&1
    record_step "purge_placeholder_images" $?
    echo "    items: $(count_lines)"

    # [4j] GC rutinario del espejo: manda a cuarentena (data/images/_orphans/) los
    # archivos que ningún item referencia — portadas reemplazadas por el skill/scripts,
    # masters viejos, etc. Reversible (no toca _originals/). Evita que el espejo crezca
    # con archivos muertos. Vaciar _orphans/ periódicamente (o --gc-delete) para reclamar.
    echo ">>> [4j] mirror_images --gc-only (cuarentena de huérfanos del espejo)"
    "$VENV_PY" scripts/retrofit/mirror_images.py --gc-only \
        > "$LOG_DIR/04j-gc.log" 2>&1 || echo "    (GC no crítico, continúa)"

    echo " ✓ PHASE 3 cleanup done"
else
    echo "[SKIP] PHASE 3 (cleanup) saltada por SKIP_CLEANUP=1"
fi

# ============================================================
# PHASE 4: Validación estructural del corpus (GATE pre-build)
# ============================================================
# Corre ANTES del build: si hay violaciones DURAS (invariantes corruptoras —
# duplicados de volumen/slug/title/cluster), NO se construye la web y se conserva
# el build anterior intacto. exit 2 = duras, exit 0 = válido, exit ≠0/≠2 = error
# del validador (también bloquea por precaución). Ver validate_corpus.py.
phase_header 4 "Validación estructural del corpus (gate pre-build)"
echo ">>> [4] validate_corpus (invariantes estructurales — gotcha #54)"
CORPUS_INVALID=0
"$VENV_PY" scripts/validate_corpus.py | tee "$LOG_DIR/04-validate-corpus.log"
# Sin `set -o pipefail`, $? sería el de `tee` (siempre 0). El exit real de
# validate_corpus está en PIPESTATUS[0] (bash).
VAL_RC=${PIPESTATUS[0]}
if [ "$VAL_RC" -eq 2 ]; then
    CORPUS_INVALID=1
    FAILED_STEPS+=("validate_corpus (violaciones DURAS)")
    echo " ✗ validate_corpus: violaciones DURAS — se OMITE el build (build anterior intacto). Ver $LOG_DIR/04-validate-corpus.log"
elif [ "$VAL_RC" -ne 0 ]; then
    CORPUS_INVALID=1
    FAILED_STEPS+=("validate_corpus (error rc=$VAL_RC)")
    echo " ⚠ validate_corpus falló con rc=$VAL_RC (error del validador) — se OMITE el build por precaución."
fi

# ── Corpus inválido: cuarentena + restore automático desde el backup pre-scrape.
# "Se omite el build" NO alcanza: serve.py hace fetch() EN VIVO de data/items.jsonl
# (decisión #5) — un corpus corrupto quedaría SERVIDO igual aunque no se reconstruya
# el HTML. Por eso hay que sacarlo de items.jsonl (cuarentena) y, si el backup
# pre-scrape resulta válido, restaurarlo — así el dashboard vuelve a servir el
# último corpus bueno conocido en vez del corrupto.
RESTORE_STATUS=""
if [ "$CORPUS_INVALID" -ne 0 ]; then
    mkdir -p data/quarantine
    QUARANTINE_PATH="data/quarantine/items-${TIMESTAMP}.jsonl"
    if [ -f data/items.jsonl ]; then
        mv data/items.jsonl "$QUARANTINE_PATH"
        echo " ⚠ corpus inválido → cuarentena: $QUARANTINE_PATH"
        if [ -n "$PRESCRAPE_BACKUP" ] && [ -f "$PRESCRAPE_BACKUP" ]; then
            echo ">>> Validando backup pre-scrape antes de restaurar: $PRESCRAPE_BACKUP"
            if "$VENV_PY" scripts/validate_corpus.py --file "$PRESCRAPE_BACKUP" \
                > "$LOG_DIR/04b-validate-backup.log" 2>&1; then
                cp "$PRESCRAPE_BACKUP" data/items.jsonl
                echo " ✓ backup válido — RESTAURADO a data/items.jsonl"
                # Las aprobaciones hechas en vivo (dashboard) durante esta misma
                # corrida viven en data/approvals.jsonl (log durable); el restore
                # pisó items.jsonl con el backup pre-scrape, que no las tiene
                # todavía — re-aplicarlas las recupera.
                echo ">>> Re-aplicando aprobaciones en vivo (data/approvals.jsonl) sobre el corpus restaurado"
                "$VENV_PY" scripts/retrofit/apply_approvals.py \
                    > "$LOG_DIR/04c-reapply-approvals.log" 2>&1
                record_step "apply_approvals (post-restore)" $?
                RESTORE_STATUS="restaurado"
            else
                echo " ✗ el backup pre-scrape TAMBIÉN es inválido (ver $LOG_DIR/04b-validate-backup.log)"
                echo " ⚠⚠⚠ NO se restaura — corpus previo NO disponible. Revisar manualmente:"
                echo "     cuarentena: $QUARANTINE_PATH"
                echo "     backup:     $PRESCRAPE_BACKUP"
                RESTORE_STATUS="backup_invalido"
            fi
        else
            echo " ⚠ no hay backup pre-scrape disponible (primera corrida o el backup falló)"
            echo " ⚠⚠⚠ NO se puede restaurar — corpus previo NO disponible. Revisar cuarentena:"
            echo "     $QUARANTINE_PATH"
            RESTORE_STATUS="sin_backup"
        fi
    else
        echo " ⚠ data/items.jsonl no existe — nada que mover a cuarentena."
        RESTORE_STATUS="sin_corpus"
    fi
fi

# ============================================================
# PHASE 5: Build web (sólo si el corpus es válido)
# ============================================================
if [ "$SKIP_BUILD" = "1" ]; then
    echo "[SKIP] PHASE 5 (build) saltada por SKIP_BUILD=1"
elif [ "$CORPUS_INVALID" -ne 0 ]; then
    echo "[SKIP] PHASE 5 (build) OMITIDA — corpus inválido (ver PHASE 4). Build anterior intacto."
else
    phase_header 5 "Build web"
    "$VENV_PY" scripts/build_web.py > "$LOG_DIR/05-build-web.log" 2>&1
    record_step "build_web" $?
    tail -10 "$LOG_DIR/05-build-web.log"
    echo " ✓ PHASE 5 build done"
fi

# ============================================================
# PHASE 6: Salud de fuentes de ESTE run (métricas + baseline alert)
# ============================================================
echo
echo ">>> [6] source_health (métricas + baseline alert, modo delta)"
"$VENV_PY" scripts/audit/source_health.py \
    --last-n 1 \
    --metrics-file logs/metrics.jsonl \
    --baseline-alert \
    --mode delta \
    --output md \
    --output-file "$LOG_DIR/06-source-health.md" \
    > "$LOG_DIR/06-source-health.stdout.log" 2>&1 \
    || echo " ⚠ source_health falló (no bloquea) — ¿interfaz --metrics-file/--baseline-alert/--mode aún no disponible?"

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
if [ "${CORPUS_INVALID:-0}" -ne 0 ]; then
    case "${RESTORE_STATUS:-}" in
        restaurado)
            printf " %-30s %s\n" "corpus:" "⚠ INVÁLIDO → cuarentena + RESTAURADO desde backup (aprobaciones re-aplicadas)"
            ;;
        backup_invalido)
            printf " %-30s %s\n" "corpus:" "⚠ INVÁLIDO → cuarentena, backup TAMBIÉN inválido, corpus previo NO disponible"
            ;;
        sin_backup)
            printf " %-30s %s\n" "corpus:" "⚠ INVÁLIDO → cuarentena, sin backup pre-scrape, corpus previo NO disponible"
            ;;
        sin_corpus)
            printf " %-30s %s\n" "corpus:" "⚠ INVÁLIDO — data/items.jsonl no existía, nada que restaurar"
            ;;
        *)
            printf " %-30s %s\n" "corpus:" "⚠ INVÁLIDO — violaciones DURAS (ver $LOG_DIR/04-validate-corpus.log) · build OMITIDO"
            ;;
    esac
else
    printf " %-30s %s\n" "corpus:" "✓ válido"
fi
if [ "${#FAILED_STEPS[@]}" -gt 0 ]; then
    printf " %-30s %s\n" "pasos con error:" "⚠ ${#FAILED_STEPS[@]}"
    for step in "${FAILED_STEPS[@]}"; do
        printf "   %-28s %s\n" "" "✗ $step"
    done
else
    printf " %-30s %s\n" "pasos con error:" "✓ ninguno"
fi
echo
echo "Salud de fuentes (source_health --baseline-alert):"
if [ -f "$LOG_DIR/06-source-health.md" ]; then
    grep -E "^## |^\| |ALERT|baseline|⚠|✗" "$LOG_DIR/06-source-health.md" | head -40 \
        || echo "  (sin alertas destacadas — ver $LOG_DIR/06-source-health.md)"
else
    echo "  (source_health no produjo salida — ver $LOG_DIR/06-source-health.stdout.log)"
fi
echo
echo "Logs por fase: $LOG_DIR/"
ls -la "$LOG_DIR/"
echo

# ── Reporte de staleness (fuentes sin novedades hace tiempo). Interfaz pactada;
# la crea otro agente. No bloquea el run.
echo ">>> staleness_report (fuentes sin novedades en 90 días)"
"$VENV_PY" scripts/audit/staleness_report.py --days 90 || true
echo

echo "Recordatorio:"
echo "  - Este es el scrape DELTA (incremental, últimos meses)."
echo "  - Para recorrer el catálogo COMPLETO de listadomanga (~3432"
echo "    colecciones via lista.php), usar: ./scripts/scrape_full.sh"
echo "  - Frecuencia recomendada: delta semanal, full mensual/trimestral."
echo
