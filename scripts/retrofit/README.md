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
| `backfill_metadata.py` | Per-item HTTP fetch para rellenar campos vacíos (image_url, author, isbn, price, release_date) o el carrusel multi-imagen (`--only images`, popula `images[]` desde la galería del detail page). | Lento (network-bound). Cuando mejoraste `_extract_label_value_pairs`/`_extract_images_from_detail_soup` o agregaste extractor por fuente. La fase `[4e2]` de `scrape_full.sh` corre `--only images` automáticamente. |
| `backfill_cluster_key.py` | Pobla `cluster_key` en items históricos sin él. | Tras cambiar `derive_cluster_key` (raro). |
| `search_discovery.py` | NO es un retrofit puro — descubre items NUEVOS via Gemini/Tavily/DDG. Vive acá por proximidad. | 1×/semana o cuando querés ampliar el corpus sin esperar al overnight. |
| `wayback_recover.py` | Para items que dan 404/410, busca snapshot en archive.org y rescata cover/título/autor. | 1×/semana como mucho. Pesado (chequea miles de URLs). |
| `expand_whakoom_ediciones.py` | Convierte filas con URL Whakoom `/ediciones/<id>/<slug>` en N filas `/comics/<X>/<slug>/<vol>` (una por tomo). | Tras un search discovery que trajo `/ediciones/` desde Gemini. Idealmente: 0 filas `/ediciones/` residuales en el catálogo. Soporta one-shots via `/login?ReturnUrl=`. |
| `expand_index_pages.py` | Limpia páginas-índice guardadas como productos: Whakoom `/publisher/` (expande), Shopify multi-tomo variants (Dark Horse), `/blogs/news/` (elimina), `/collections/X` sin `/products/` (elimina). | Tras cada `search_discovery`. Idempotente. |
| `backfill_animeclick_details.py` | Para los items de AnimeClick ingestados sin `fetch_details=True` (release_date/price/description vacíos), fetcha directamente las páginas de detalle sin re-navegar el calendario AJAX. 4 workers, ~8 min para 1400 items. | 1× tras la ingesta inicial de AnimeClick o cuando aparezcan nuevos items sin fecha/precio. |
| `mirror_images.py` | Espejo local de portadas (Image storage Fase 1). Backfill: descarga a `data/images/` la portada de cada item con `image_url` y sin `image_local`. GC mark-and-sweep: saca de `data/images/` los archivos que ningún item referencia (a cuarentena `_orphans/`, o `--gc-delete`). | 1× para bajar el catálogo histórico (el scrape ya baja las portadas de items nuevos). Después, de vez en cuando para el GC. Idempotente. Ver "Image storage" en CLAUDE.md. |
| `generate_slugs.py` | Genera el campo `slug` en items.jsonl para la ruta `/item/[slug]` del app Next.js (`web-next/`). Prioridad: `isbn:{X}` cluster_key → `{edition_key}-{vol}` → `{edition_key}` solo → `isbn-{isbn}` → `item-{sha1(url)[:12]}` fallback. Resuelve colisiones con sufijos `-b`/`-c` (el más antiguo conserva el slug limpio). Idempotente: solo actualiza `slug` si está vacío o si `edition_key`/`volume` cambió. Flags: `--dry-run`, `--only-missing`, `--verbose`. | Como **último paso del skill `/standardize-catalog`** (después de escribir items.jsonl con sus campos canónicos). No corre automáticamente en el pipeline de scrape; solo cuando se estandarizan items nuevos. Ver docs/app/FRD-006-slug-generation.md. |
| `translate_descriptions.py` | Popula `description_es` y `extras[].description_es` con la traducción al español de los campos `description` / `extras[].description`. Primario: **Google Translate** (gratis, sin API key). Opcional: **DeepL** (mejor calidad si `DEEPL_API_KEY` está en `.env`; plan gratuito = crédito único de 1M chars, no se renueva). `description` original no se modifica. Idempotente: salta items que ya tienen `description_es` (salvo `--force`). Requiere `pip install deep-translator langdetect`. Opcional: `pip install deepl`. | Después de cada scrape grande que agregó items con descripción en idioma extranjero. Sin clave DeepL igualmente funciona. |

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
| "Quiero ser dueño de las portadas / limpiar imágenes viejas" | retrofit `mirror_images.py` |
| "Scrapée items nuevos y quiero que tengan URL `/item/[slug]` en el app" | retrofit `generate_slugs.py` |

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
.venv/bin/python scripts/retrofit/backfill_metadata.py --only images --limit 50  # carrusel multi-imagen

# Expansiones de páginas-índice (Whakoom, Shopify variants)
.venv/bin/python scripts/retrofit/expand_whakoom_ediciones.py --dry-run
.venv/bin/python scripts/retrofit/expand_index_pages.py --dry-run

# Espejo local de portadas (backfill + GC)
.venv/bin/python scripts/retrofit/mirror_images.py --dry-run
.venv/bin/python scripts/retrofit/mirror_images.py --limit 100   # probar
.venv/bin/python scripts/retrofit/mirror_images.py               # todo + GC

# Slugs para el app Next.js (web-next/)
.venv/bin/python scripts/retrofit/generate_slugs.py --dry-run    # preview sin escribir
.venv/bin/python scripts/retrofit/generate_slugs.py --only-missing  # solo items sin slug (normal)
.venv/bin/python scripts/retrofit/generate_slugs.py --verbose    # con log de cada asignación
```

Cada script crea un backup `.pre-*-bak` o `/tmp/items.jsonl.bak-*` antes
de sobrescribir `data/items.jsonl`. Un mal run es recuperable.

## Estado actual (última corrida — 2026-05-24)

- Total items: **~4400** (después de filtros, standardization, aliases).
- Cobertura post-Mangavariant integration:
  - image_url: ~100%
  - image_local (espejo local, Image storage Fase 1): ~98.6%
    (el resto: image_url mal extraída — data: URI, ícono — o 404
    muerto; no re-descargable, queda con image_url como fallback)
  - series_key: 100% (todos los items tienen serie canónica)
  - edition_key: 100%
  - volume: ~79% (vacío para artbooks/cover-only/one-shots)
  - isbn: ~30% (las bajas son items Mangavariant sin ISBN por diseño)
  - price: ~40% (Mangavariant no expone precio)
  - author: ~30%

Si la cobertura de un campo retroactiva-detectable empeora notablemente
después de un scrape grande, es señal de que conviene correr el retrofit
correspondiente.
