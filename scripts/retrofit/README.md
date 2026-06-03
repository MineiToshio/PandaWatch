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
| `upgrade_image_resolution.py` | Re-descarga portadas en resolución completa eliminando parámetros de redimensionado de CDN. Detecta 3 patrones: Magento (`?quality=80&width=222&height=222` → sin params), WordPress/WooCommerce (`image-300x300.jpg` → `image.jpg`), Shopify (`image_540x.jpg` → `image.jpg`). Compara píxeles antes de reemplazar (umbral `--min-gain 0.10` = 10%). Actualiza `image_url` e `images[]` en items.jsonl; archivos viejos quedan como huérfanos para el próximo GC de `mirror_images.py`. Idempotente: URLs ya limpias no se reprocesan. | 1× tras una ingesta grande con imágenes pixeladas (Mangavariant ~5500, Panini IT ~1100). Luego es idempotente. Correr `mirror_images.py --gc` después para limpiar las miniaturas huérfanas. |
| `backfill_prh_covers.py` | Para items EN con ISBN-13 de prefijo 978-0/978-1, prueba la URL determinística `images.penguinrandomhouse.com/cover/{isbn13}` del CDN de Penguin Random House. PRH distribuye manga EN de Dark Horse, Kodansha Comics, Seven Seas, Square Enix, TOKYOPOP, Titan, Inklore, Yen Press y más. 404 → descartado (magia-bytes). Valida ≥80 000 píxeles (descarta placeholders). Compara contra la imagen actual (umbral `--min-gain 0.10`). Deduplicado por ISBN: un solo download sirve a todos los items con ese ISBN. Actualiza `image_url`, `image_local` e `images[0]` en sincronía. Idempotente: items ya usando PRH CDN no se retocan. | Tras ingestas de fuentes EN con imágenes pequeñas (Yen Press Calendar, VIZ, Manga-Sanctuary EN). 18 items mejorados en la corrida inicial (2026-05-28). |
| `upscale_images.py` | AI upscaling de portadas pixeladas usando waifu2x-ncnn-vulkan o realesrgan-ncnn-vulkan (modelos optimizados para anime/manga). Para imágenes con menos de `--max-pixels` píxeles (default 200 000 ≈ 450×445 px), aplica el upscaler ×2 y guarda el resultado como PNG lossless. Actualiza `image_local` en items.jsonl si la extensión cambia de .jpg → .png. Idempotente: saltea archivos ya procesados. Requiere instalar: `brew install waifu2x-ncnn-vulkan`. | Después de ingestas de fuentes JP (sumikko, booksprivilege, Rakuten) o IT (animeclick) que sólo exponen miniaturas ~150×220 px sin versión hi-res disponible en el servidor. |
| `fetch_better_covers.py` | Para items con imagen pequeña (< `--min-pixels`, default 100 000 px), busca portadas en mayor resolución por dos estrategias: (1) ISBN → lookup determinístico en Amazon CDN (`m.media-amazon.com/images/P/{isbn10}.09.SCLZZZZZZZ.jpg`) y PRH CDN (EN only); (2) sin ISBN → **Tavily Search API** con `include_images=True` que devuelve URLs de imagen directas sin fetchar páginas individuales (requiere `TAVILY_API_KEY` en `.env`, 1 000 queries/mes gratis; auto-detectado). Verificación doble: aspect ratio (±25%) + perceptual hash aHash 8×8 con distancia Hamming ≤ `--max-hash-dist` (default 12/64 bits) para confirmar que la candidata es la misma portada. Items con `variant_cover` o `retailer_exclusive` se saltan (web search devolvería la portada regular). Requiere Pillow: `.venv/bin/python3 -m pip install Pillow`. | Después de `upgrade_image_resolution.py` (que ya limpió parámetros CDN). Cuando hay muchos items con imagen < 100 000 px sin versión hi-res en el servidor origen — típico en AnimeClick IT (~1 000) y ListadoManga colecciones (~1 200). Correr primero con `--dry-run` para ver cuántos mejorarían. |
| `generate_slugs.py` | Genera el campo `slug` en items.jsonl para la ruta `/item/[slug]` del app Next.js (`web-next/`). Prioridad: `isbn:{X}` cluster_key → `{edition_key}-{vol}` → `{edition_key}` solo → `isbn-{isbn}` → `item-{sha1(url)[:12]}` fallback. Resuelve colisiones con sufijos `-b`/`-c` (el más antiguo conserva el slug limpio). Idempotente: solo actualiza `slug` si está vacío o si `edition_key`/`volume` cambió. Flags: `--dry-run`, `--only-missing`, `--verbose`. | Como **último paso del skill `/standardize-catalog`** (después de escribir items.jsonl con sus campos canónicos). No corre automáticamente en el pipeline de scrape; solo cuando se estandarizan items nuevos. Ver docs/app/FRD-006-slug-generation.md. |
| `set_rarity.py` | Aplica el campo `rarity` (`common` / `rare` / `super_rare` / `ultra_rare`) a todos los items usando `derive_rarity_tier()` de manga_watch.py. Solo toca items sin valor asignado (o todos con `--force`). Respeta valores asignados por web-search (p. ej. `common` nunca se degrada). Flags: `--dry-run`, `--force`. | Después de un scrape grande que agregó items nuevos sin `rarity`, o cuando se modifican las reglas de `derive_rarity_tier()`. |
| `translate_descriptions.py` | Popula `description_es` y `extras[].description_es` con la traducción al español de los campos `description` / `extras[].description`. Primario: **Google Translate** (gratis, sin API key). Opcional: **DeepL** (mejor calidad si `DEEPL_API_KEY` está en `.env`; plan gratuito = crédito único de 1M chars, no se renueva). `description` original no se modifica. Idempotente: salta items que ya tienen `description_es` (salvo `--force`). Requiere `pip install deep-translator langdetect`. Opcional: `pip install deepl`. | Después de cada scrape grande que agregó items con descripción en idioma extranjero. Sin clave DeepL igualmente funciona. |
| `apply_approvals.py` | Re-materializa el log durable `data/approvals.jsonl` (las cards aprobadas desde el dashboard — golden records) sobre `items.jsonl`. Reduce el log al estado final por `cluster_key` (last-wins) y re-aplica `approved_at`/`approved_by` (match por cluster_key, fallback url). Idempotente. Flags: `--dry-run`, `--approvals`, `--items`. | Tras **reconstruir `items.jsonl` de cero** (re-scrape/import) cuando se perdieron los `approved_at`. Las aprobaciones viven también en el JSONL, este log es el respaldo durable. Registrado en Panel de Control. |
| `consolidate_sources.py` | Modelo **1-fila-por-producto**: agrupa por `cluster_key` y colapsa las filas duplicadas del mismo producto (misma edición encontrada en varias fuentes con URLs distintas) en UNA sola fila con `sources[]` (todas las fuentes), imágenes union (portada canónica primera) y extras union. Delega en `manga_watch.consolidate_by_cluster` (la misma primitiva que usa `append_jsonl` al ingestar). Idempotente. | Después de `/standardize-catalog` (reasigna edition_key → nuevos clusters), o si ves cards duplicadas del mismo producto. Corre como paso `[4g]` del pipeline. Registrado en Panel de Control. |
| `sync_cover_images.py` | Saneamiento integral de imágenes (contrapartida-de-datos del extractor, gotcha #31). Por item: **(1)** portada mala — si `image_url` es placeholder/banner (`visuel_defaut`, banner "Lista de Mangas" Panini MX) promueve la 1ª imagen real de `images[]` o la limpia (→ 📚); **(2)** `images[0]` == portada — re-sincroniza con `image_url`/`image_local` (bug 2026-06-02 Dark Horse: card y carrusel mostraban fotos distintas); **(3)** basura — elimina duplicados exactos (Panini `[cover,cover,cover]`), dups http/https, y BASURA por patrón de URL (KADOKAWA `top_bar_banner`/`bnr_*`, avatares AnimeClick `/bundles/accommon/`+`/avatar/`, íconos Funside `icona_lucchetto`, `nowprinting` e-hon, `adulte` manga-sanctuary, `/images/site/yomi/` otakucalendar, `img_star`) **O por ARCHIVO LOCAL** (`_compute_junk_local`: 0 bytes, <6KB píxeles/íconos, o el mismo archivo compartido por ≥4 OBRAS distintas = placeholder/banner reusado — con guard que NO marca portadas reales de obras fragmentadas en varios series_key); **(4)** productos relacionados — descarta galerías que son otros tomos/series (Star Comics `/fumetti-cover/thumbnail/`, Manga-Sanctuary `/objet/150/`), dejando solo la portada. Salta aprobados (`--include-approved`). Idempotente. Flags: `--dry-run`, `--include-approved`. | Cuando card y carrusel muestran fotos distintas, hay imágenes repetidas / banners / avatares, o carruseles con fotos de otras series. Registrado en Panel de Control. |

## ⚠️ Aprobaciones (golden records) — los retrofits las RESPETAN

Los items que el owner aprobó desde el dashboard llevan `approved_at` (ver
"Aprobación humana" en CLAUDE.md). **Todos los retrofits que reescriben campos
descriptivos** (`rescore`, `clean_titles`, `filter_non_manga`,
`filter_collectible`, `set_rarity`, `backfill_metadata`,
`translate_descriptions`) **saltean los items aprobados por defecto** — no los
re-derivan ni re-filtran. Los dos filtros (`filter_non_manga`,
`filter_collectible`) además SIEMPRE conservan un item aprobado (nunca lo
rechazan). Flag `--include-approved` para forzar el procesamiento de aprobados
cuando realmente lo querés. El guard usa `is_approved()` de `manga_watch.py`.
Si agregás un retrofit nuevo que reescribe metadata descriptiva, sumá el mismo
guard.

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
| "Cambié las reglas de rareza / hay items sin `rarity`" | retrofit `set_rarity.py` |

## Backups — dónde van y cómo funcionan

**Regla única: todos los backups se crean con `backup_and_rotate()` importada de `manga_watch.py`.
NUNCA con `cp ... /tmp/`, NUNCA con lógica propia en el script.**

```python
from manga_watch import backup_and_rotate

# Al inicio del script, ANTES del loop (una sola vez):
if not dry_run:
    backup_and_rotate(items_path, "nombre-del-script")
```

`backup_and_rotate(path, label, max_keep=3)` crea el backup en
`data/backups/<filename>/` (p. ej. `data/backups/items.jsonl/items.nombre-del-script-TIMESTAMP.bak`)
y elimina automáticamente los backups más viejos, conservando solo los 3 más recientes.

**¿Por qué importa?**
- `data/backups/` está en `.gitignore`. Si el backup va a otro lado (p. ej. raíz del repo),
  aparece en `git status` como untracked y no hay rotación automática.
- La lógica de rotación la tiene `backup_and_rotate()` — implementarla a mano en cada script
  garantiza que divergen (como pasó con `fetch_better_covers.py` que usaba `items_path.parent.parent / "backups"` → creaba `backups/` en la raíz del repo).

**Anti-patterns:**
- ❌ `cp data/items.jsonl /tmp/items.jsonl.bak-$(date)`
- ❌ `backup_dir = items_path.parent.parent / "backups" / ...` (hardcoded)
- ❌ Definir tu propia función `_backup_items()` en el script

Todos los retrofits existentes ya usan `backup_and_rotate()`. Si agregás uno nuevo, hacé lo mismo.

## Uso típico

```bash
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

# Upgrade de resolución (Mangavariant -300x300, Panini ?width=222, etc.)
.venv/bin/python scripts/retrofit/upgrade_image_resolution.py --dry-run   # cuántas hay
.venv/bin/python scripts/retrofit/upgrade_image_resolution.py --limit 100 # probar
.venv/bin/python scripts/retrofit/upgrade_image_resolution.py --workers 8 # todo
# Luego correr mirror_images --gc para limpiar las miniaturas huérfanas

# Portadas EN via PRH CDN (Yen Press, VIZ, Manga-Sanctuary EN, etc.)
.venv/bin/python scripts/retrofit/backfill_prh_covers.py --dry-run      # candidatos
.venv/bin/python scripts/retrofit/backfill_prh_covers.py --workers 8    # todo
.venv/bin/python scripts/retrofit/backfill_prh_covers.py --min-gain 0   # sin umbral de píxeles

# AI upscaling de portadas pixeladas (sumikko, booksprivilege, Rakuten JP, animeclick)
# Instalar primero: brew install waifu2x-ncnn-vulkan
.venv/bin/python scripts/retrofit/upscale_images.py --dry-run            # cuántas hay
.venv/bin/python scripts/retrofit/upscale_images.py --limit 20           # probar
.venv/bin/python scripts/retrofit/upscale_images.py                      # todo (< 200k px)
.venv/bin/python scripts/retrofit/upscale_images.py --max-pixels 100000  # solo las más pequeñas

# Buscar portadas en mayor resolución (AnimeClick IT, ListadoManga colecciones, etc.)
# Requiere: .venv/bin/python3 -m pip install Pillow
.venv/bin/python scripts/retrofit/fetch_better_covers.py --dry-run --limit 30 --verbose  # ver candidatos
.venv/bin/python scripts/retrofit/fetch_better_covers.py --no-search      # solo ISBN CDN (rápido, seguro)
.venv/bin/python scripts/retrofit/fetch_better_covers.py                  # todo (ISBN + Tavily search, requiere TAVILY_API_KEY en .env)

# Slugs para el app Next.js (web-next/)
.venv/bin/python scripts/retrofit/generate_slugs.py --dry-run    # preview sin escribir
.venv/bin/python scripts/retrofit/generate_slugs.py --only-missing  # solo items sin slug (normal)
.venv/bin/python scripts/retrofit/generate_slugs.py --verbose    # con log de cada asignación

# Re-aplicar aprobaciones (golden records) tras reconstruir items.jsonl
.venv/bin/python scripts/retrofit/apply_approvals.py --dry-run   # cuántas se re-aplicarían
.venv/bin/python scripts/retrofit/apply_approvals.py             # re-materializa desde approvals.jsonl
```

Cada script llama a `backup_and_rotate(items_path, "nombre-script")` antes
de sobrescribir `data/items.jsonl`. Los backups van siempre a `data/backups/items.jsonl/`
(max 3, rotación automática). Ver sección "Backups" arriba.

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
