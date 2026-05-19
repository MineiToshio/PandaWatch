#!/usr/bin/env bash
#
# full_run.sh — run completo de Manga Watch con todas las funcionalidades.
#
# Hace:
#   1. Snapshot del items.jsonl actual (para comparar antes/después)
#   2. Corre el scraper con --enable-js --fuzzy-keywords --fetch-details --diagnostic
#      → todas las 76 fuentes canónicas + 66 búsquedas dirigidas
#   3. Embebe los datos nuevos en web/index.html
#   4. Imprime estadísticas comparativas
#
# Tiempo estimado: 25-40 minutos con paginación (~3 págs por fuente)
#
# Uso:
#   ./scripts/full_run.sh
#
# Variables opcionales:
#   SLEEP=0.5          # sleep entre fuentes (default 0.5)
#   MIN_SCORE=30       # score mínimo para reportar (default 30)
#   SKIP_DETAILS=1     # saltea --fetch-details para ir más rápido
#   MAX_PAGES=5        # paginación profunda (default 3)

set -uo pipefail  # set -e desactivado para que veas errores aunque algo falle

cd "$(dirname "$0")/.."

SLEEP="${SLEEP:-0.5}"
MIN_SCORE="${MIN_SCORE:-30}"
SKIP_DETAILS="${SKIP_DETAILS:-0}"
MAX_PAGES="${MAX_PAGES:-3}"

VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    echo "❌ No encuentro $VENV_PY"
    echo "   Activá el venv o instalá:"
    echo "   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

mkdir -p logs/runs

TIMESTAMP=$(date '+%Y-%m-%d-%H%M%S')
LOG_FILE="logs/runs/full-${TIMESTAMP}.log"

# ============================================================
# 1. Snapshot inicial
# ============================================================
echo "==> Pre-flight"
echo

BEFORE_COUNT=0
if [ -f data/items.jsonl ]; then
    BEFORE_COUNT=$(wc -l < data/items.jsonl | tr -d ' ')
    echo "    items.jsonl actual: $BEFORE_COUNT líneas"
else
    echo "    items.jsonl no existe — primer run."
fi

if [ ! -d ".venv/lib/python3.14/site-packages/playwright" ]; then
    echo "    ⚠️  Playwright no parece estar instalado. Si querés --enable-js:"
    echo "       .venv/bin/pip install -r requirements-playwright.txt"
    echo "       .venv/bin/python -m playwright install chromium"
fi

echo
echo "==> Run completo"
echo "    Log:        $LOG_FILE"
echo "    Sleep:      ${SLEEP}s entre fuentes"
echo "    Min score:  $MIN_SCORE"
echo "    Max pages:  $MAX_PAGES por fuente (paginación automática)"
echo "    JS render:  on (--enable-js)"
echo "    Fuzzy:      on (--fuzzy-keywords)"
if [ "$SKIP_DETAILS" = "1" ]; then
    echo "    Detail-fetch: OFF (SKIP_DETAILS=1)"
    DETAIL_FLAG=""
else
    echo "    Detail-fetch: on (--fetch-details, score>=70)"
    DETAIL_FLAG="--fetch-details"
fi
echo

# ============================================================
# 2. Run del scraper
# ============================================================
START_TS=$(date +%s)

PYTHONUNBUFFERED=1 "$VENV_PY" -u manga_watch.py \
    --enable-js \
    --fuzzy-keywords \
    --max-pages "$MAX_PAGES" \
    $DETAIL_FLAG \
    --diagnostic \
    --sleep-seconds "$SLEEP" \
    --min-score "$MIN_SCORE" \
    2>&1 | tee "$LOG_FILE"

END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))

echo
echo "==> Run completado en $((DURATION / 60))m $((DURATION % 60))s"
echo

# ============================================================
# 3. Build web (embed JSONL en HTML)
# ============================================================
echo "==> Embebiendo data en web/index.html"
"$VENV_PY" scripts/build_web.py
echo

# ============================================================
# 4. Estadísticas comparativas
# ============================================================
AFTER_COUNT=0
if [ -f data/items.jsonl ]; then
    AFTER_COUNT=$(wc -l < data/items.jsonl | tr -d ' ')
fi

DELTA=$((AFTER_COUNT - BEFORE_COUNT))

echo "==> Resumen final"
echo
printf "    %-25s %s\n" "items.jsonl antes:"  "$BEFORE_COUNT líneas"
printf "    %-25s %s\n" "items.jsonl después:" "$AFTER_COUNT líneas"
printf "    %-25s %s\n" "delta:" "+$DELTA"
echo

# Stats del último diagnóstico (si existe)
LATEST_DIAG=$(ls -t logs/diagnostic-*.json 2>/dev/null | head -1 || true)
if [ -n "$LATEST_DIAG" ]; then
    echo "==> Cobertura por status (último diagnóstico)"
    "$VENV_PY" - <<EOF
import json, sys
data = json.load(open("$LATEST_DIAG"))
total = data["summary"]["total_sources"]
by_status = data["summary"]["by_status"]
print(f"    Total fuentes analizadas: {total}")
for status in ["ok", "no-candidates", "empty", "js-shell", "no-links", "http", "request", "robots", "other"]:
    n = by_status.get(status, 0)
    if n: print(f"      {status:18s} {n:4d}  ({100*n/total:4.1f}%)")
ok_sources = [s for s in data["sources"] if s["status"] == "ok"]
total_cands = sum(s.get("candidates_after_scoring", 0) for s in ok_sources)
print()
print(f"    Total candidatos con señales: {total_cands}")
print(f"    Top 10 fuentes:")
ok_sources.sort(key=lambda s: -s.get("candidates_after_scoring", 0))
for s in ok_sources[:10]:
    method = (s.get("extraction_method") or "?")[:12]
    print(f"      {s.get('candidates_after_scoring',0):4d}  {method:14s} {s['name']}")
EOF
fi

echo
echo "==> Distribución de campos en items.jsonl"
"$VENV_PY" - <<EOF
import json, collections
items = []
with open("data/items.jsonl") as f:
    for line in f:
        line = line.strip()
        if line:
            try: items.append(json.loads(line))
            except: pass
# Dedup by url
seen = {}
for i in items:
    u = i.get("url", "")
    if u and (u not in seen or (i.get("detected_at","") > seen[u].get("detected_at",""))):
        seen[u] = i
items = list(seen.values())

n = len(items)
def pct(c): return f"{c:4d}/{n} ({100*c/n if n else 0:4.0f}%)" if n else "—"

print(f"    Total items únicos: {n}")
print(f"    Con price:        {pct(sum(1 for i in items if i.get('price')))}")
print(f"    Con image_url:    {pct(sum(1 for i in items if i.get('image_url')))}")
print(f"    Con release_date: {pct(sum(1 for i in items if i.get('release_date')))}")
print(f"    Con author:       {pct(sum(1 for i in items if i.get('author')))}")
print(f"    Con stock=limited:{pct(sum(1 for i in items if i.get('stock_type')=='limited'))}")
print()
pt = collections.Counter(i.get("product_type","") for i in items)
print("    Distribución de product_type:")
for k, v in pt.most_common():
    print(f"      {(k or '(empty)'):14s} {v:4d}  ({100*v/n if n else 0:4.0f}%)")
print()
countries = collections.Counter(i.get("country","") for i in items)
print(f"    Países cubiertos: {len([c for c in countries if c])}")
for c, v in countries.most_common(10):
    if c: print(f"      {c:20s} {v:4d} items")
EOF

echo
echo "==> Listo. Próximos pasos:"
echo "    1. Abrir web:    open web/index.html"
echo "    2. Log completo: less $LOG_FILE"
echo "    3. Diagnóstico:  less $(ls -t logs/diagnostic-*.md 2>/dev/null | head -1 || echo 'N/A')"
