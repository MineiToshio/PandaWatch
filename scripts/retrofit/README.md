# scripts/retrofit/

Utilitarios de **retrofit** — herramientas para aplicar mejoras del pipeline
de forma retroactiva sobre `data/items.jsonl` cuando el corpus histórico
no se beneficia automáticamente.

> **Estos scripts NO contienen lógica propia.** Solo importan funciones de
> `scripts/manga_watch.py` y las aplican a items ya guardados. Las mismas
> funciones ya corren automáticamente durante cualquier scrape nuevo
> (`bootstrap.sh`, `full_run.sh`).

## Cuadro completo de retrofits

| Script | Qué hace | Cuándo correrlo |
|---|---|---|
| `clean_titles.py` | Re-aplica `clean_title()` a títulos guardados (mojibake, prefijos junk). | Tras agregar pattern nuevo a `TITLE_JUNK_PATTERNS` en manga_watch.py. |
| `filter_non_manga.py` | Re-aplica `is_likely_manga` + `is_pure_novel` + `is_comic_not_manga`. Mueve los rechazados fuera de items.jsonl. | Tras agregar pattern a `_NON_MANGA_HARD`/`_SOFT` o `data/comics_blacklist.yml`. |
| `filter_collectible.py` | Re-aplica `is_collectible_edition` (segundo gate). Mueve tomos regulares fuera. | Tras cambios a `COLLECTIBLE_EDITION_SIGNAL_TYPES` o `is_collectible_edition`. ⚠️ Cuidado: este filtro rechaza items de referencia Mangavariant que SIEMPRE deben mantenerse — el skill `/standardize-catalog` los preserva pero este retrofit los puede quitar erróneamente. |
| `rescore.py` | Recalcula `score` + `signal_types` + `product_type` para cada item. | Tras cambiar `detect_signals`, `score_candidate`, o un peso en `signal_score_table`. |
| `backfill_metadata.py` | Per-item HTTP fetch para rellenar campos vacíos (image_url, author, isbn, price, release_date). | Lento (network-bound). Cuando mejoraste `_extract_label_value_pairs` o agregaste extractor por fuente. |
| `backfill_cluster_key.py` | Pobla `cluster_key` en items históricos sin él. | Tras cambiar `derive_cluster_key` (raro). |
| `search_discovery.py` | NO es un retrofit puro — descubre items NUEVOS via Gemini/Tavily/DDG. Vive acá por proximidad. | 1×/semana o cuando querés ampliar el corpus sin esperar al overnight. |
| `wayback_recover.py` | Para items que dan 404/410, busca snapshot en archive.org y rescata cover/título/autor. | 1×/semana como mucho. Pesado (chequea miles de URLs). |
| `expand_whakoom_ediciones.py` | Convierte filas con URL Whakoom `/ediciones/<id>/<slug>` en N filas `/comics/<X>/<slug>/<vol>` (una por tomo). | Tras un search discovery que trajo `/ediciones/` desde Gemini. Idealmente: 0 filas `/ediciones/` residuales en el catálogo. Soporta one-shots via `/login?ReturnUrl=`. |
| `expand_index_pages.py` | Limpia páginas-índice guardadas como productos: Whakoom `/publisher/` (expande), Shopify multi-tomo variants (Dark Horse), `/blogs/news/` (elimina), `/collections/X` sin `/products/` (elimina). | Tras cada `search_discovery`. Idempotente. |

## Cuándo NO los necesitás

- **Scrape nuevo de una fuente que ya existe**: el pipeline ya aplica todo.
- **Nunca tocaste las reglas**: no hay nada nuevo que aplicar a items viejos.
- **Curación general post-scrape**: para eso están los **skills** (ver más
  abajo), no los retrofits.

## Retrofits vs Skills — cuándo cada uno

Los retrofits son **mecánicos** (regex/function-based) y rápidos.
Los skills (`.claude/skills/*.md`) son **LLM-driven**, más sofisticados,
y se usan para curación que requiere juicio (asignar series, decidir
si algo es manga, consolidar nombres multilingües).

| Tarea | Herramienta |
|---|---|
| "Quité un patrón mojibake del título" | retrofit `clean_titles.py` |
| "Agregué pattern non-manga ej. 'puzzle XL'" | retrofit `filter_non_manga.py` |
| "Aparecieron items con series_key vacío o crudo" | skill `/standardize-catalog` |
| "Hay 5 series_keys distintos que son la misma obra en diferentes idiomas" | skill `/enrich-series-aliases` |
| "Un manga apareció con título 'Spider-Man' por error de scrape" | feedback en dashboard + skill `/standardize-catalog` |

## Uso típico

```bash
# Backup automático antes de tocar (los scripts lo hacen, pero por las dudas)
cp data/items.jsonl /tmp/items.jsonl.bak-$(date +%Y%m%d)

# Cleanup mecánico
.venv/bin/python scripts/retrofit/clean_titles.py --dry-run    # preview
.venv/bin/python scripts/retrofit/clean_titles.py              # aplicar

.venv/bin/python scripts/retrofit/filter_non_manga.py --dry-run
.venv/bin/python scripts/retrofit/filter_non_manga.py

# Backfill HTTP-bound (lento)
.venv/bin/python scripts/retrofit/backfill_metadata.py --sleep 0.2
.venv/bin/python scripts/retrofit/backfill_metadata.py --only image_url --limit 50

# Expansiones de páginas-índice (Whakoom, Shopify variants)
.venv/bin/python scripts/retrofit/expand_whakoom_ediciones.py --dry-run
.venv/bin/python scripts/retrofit/expand_index_pages.py --dry-run
```

Cada script crea un backup `.pre-*-bak` o `/tmp/items.jsonl.bak-*` antes
de sobrescribir `data/items.jsonl`. Un mal run es recuperable.

## Estado actual (última corrida — 2026-05-24)

- Total items: **~4400** (después de filtros, standardization, aliases).
- Cobertura post-Mangavariant integration:
  - image_url: ~100%
  - series_key: 100% (todos los items tienen serie canónica)
  - edition_key: 100%
  - volume: ~79% (vacío para artbooks/cover-only/one-shots)
  - isbn: ~30% (las bajas son items Mangavariant sin ISBN por diseño)
  - price: ~40% (Mangavariant no expone precio)
  - author: ~30%

Si la cobertura de un campo retroactiva-detectable empeora notablemente
después de un scrape grande, es señal de que conviene correr el retrofit
correspondiente.
