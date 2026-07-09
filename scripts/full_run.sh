#!/usr/bin/env bash
#
# full_run.sh — DEPRECATED, alias de scrape_full.sh
#
# Este script era el run "completo" legacy (pre scrape_delta/scrape_full):
# sin lock global (dos corridas simultáneas podían corromper items.jsonl), sin
# gate `validate_corpus.py` (publicaba web sin validar el corpus), y sus
# estadísticas finales leían campos eliminados del schema (`price`,
# `image_url` top-level — ver decisión #1/refactor "portada → images[0]"), así
# que reportaban 0% siempre. Auditoría S8, 2026-07-08.
#
# El equivalente canónico es:
#
#   scripts/scrape_delta.sh   — scraping incremental (diario/semanal)
#   scripts/scrape_full.sh    — scraping completo (mensual/trimestral, esto)
#
# full_run.sh hacía lo que scrape_full.sh hace hoy (recorrido completo del
# catálogo YAML), así que el alias delega ahí. Las variables de entorno viejas
# (SLEEP, MIN_SCORE, MAX_PAGES, SKIP_DETAILS) NO se traducen — la interfaz de
# scrape_full.sh es distinta (SCRAPE_WORKERS, PER_HOST_LIMIT, COLECCION_SLEEP,
# SKIP_SCRAPE/SKIP_WIKIS/SKIP_CLEANUP/SKIP_BUILD). Ver su --help/comentarios.

cd "$(dirname "$0")/.."
echo "[DEPRECATED] full_run.sh está deprecated (sin lock, sin gate validate_corpus,"
echo "             estadísticas rotas — auditoría S8, 2026-07-08)."
echo "             Usar directamente: ./scripts/scrape_full.sh"
echo "             (variables de entorno viejas SLEEP/MIN_SCORE/MAX_PAGES/SKIP_DETAILS"
echo "             no se trasladan — la interfaz de scrape_full.sh es distinta)."
echo
exec ./scripts/scrape_full.sh
