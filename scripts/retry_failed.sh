#!/usr/bin/env bash
#
# retry_failed.sh — DEPRECATED (auditoría S9, 2026-07-08).
#
# Reintentaba un set de fuentes HARDCODEADO de un incidente puntual de mayo
# 2026 (Dark Horse Direct + Manga Dreams + Whakoom vía --include-tags
# new-source/dark-horse) y corría el cleanup en el orden VIEJO
# (filter_non_manga → filter_collectible → clean_titles) — la gotcha #110
# corrigió ese orden (clean_titles debe ir ANTES de los filtros, si no un
# título que sólo pasa/rechaza tras limpiarse produce no-idempotencia). Sin
# lock global, sin backup, sin gate validate_corpus, build_web incondicional:
# puede publicar un corpus roto. No sirve como "reintentar lo que falló" en
# general — el set hardcodeado no cubre ninguna fuente que falle hoy.
#
# file-map.md decía que reintenta "las fuentes que erraron en el último log"
# — nunca fue así (no lee logs ni source_health.py); corregido en el mismo
# commit que esta deprecación.
#
# Vía correcta para reintentar fuentes rotas:
#   1. Identificar qué falló:      .venv/bin/python scripts/audit/source_health.py
#   2. Reintentar SOLO esa fuente: .venv/bin/python scripts/manga_watch.py \
#        --only-source "<nombre exacto de la fuente>"
#   3. Cleanup + gate + build:     ./scripts/scrape_delta.sh (o scrape_full.sh)

cd "$(dirname "$0")/.."
echo "[DEPRECATED] retry_failed.sh está deprecated."
echo "             Reintentaba un set de fuentes HARDCODEADO (incidente de mayo 2026)"
echo "             y corría el cleanup en el orden viejo (gotcha #110). Sin lock, sin"
echo "             backup, sin gate validate_corpus — puede publicar un corpus roto."
echo
echo "Para reintentar fuentes rotas:"
echo "  1. .venv/bin/python scripts/audit/source_health.py          # identificar qué falló"
echo "  2. .venv/bin/python scripts/manga_watch.py --only-source \"<fuente>\"  # reintentar esa fuente"
echo "  3. ./scripts/scrape_delta.sh                                 # cleanup + gate + build completo"
echo
exit 1
