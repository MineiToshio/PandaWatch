#!/usr/bin/env bash
#
# overnight_run.sh — DEPRECATED, alias de scrape_delta.sh
#
# Este script existe por retrocompatibilidad con cron jobs / Panel de
# Control que referencian la ruta vieja. El comportamiento se movió a:
#
#   scripts/scrape_delta.sh   — scraping incremental ("delta", diario/semanal)
#   scripts/scrape_full.sh    — scraping completo (mensual/trimestral)
#
# Decisión 2026-05-23: simplificar a 2 scripts top-level canónicos.
# El overnight_run.sh equivalente es el "delta" (no recorre las ~3432
# colecciones de lista.php, solo agarra novedades del calendario y mes
# actual). Para el full, usar scrape_full.sh explícitamente.
#
# Todas las variables de entorno (INCLUDE_WHAKOOM_SPIDER, SKIP_*, etc.)
# se respetan igual — solo se delega la ejecución.

cd "$(dirname "$0")/.."
echo "[DEPRECATED] overnight_run.sh es alias de scrape_delta.sh."
echo "             Usar directamente: ./scripts/scrape_delta.sh"
echo
exec ./scripts/scrape_delta.sh "$@"
