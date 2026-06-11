# Imágenes — convención images[], espejo local, URL-como-referencia

> Documento de referencia de PandaWatch, cargado **bajo demanda** desde
> [CLAUDE.md](../../CLAUDE.md). Leelo cuando vayas a trabajar en este tema.

## URL como referencia (no de tienda) — política

PandaWatch acepta items cuya `url` NO lleva a una tienda. Wikis, bases comunitarias
y directorios son fuentes de primera clase: la meta es **descubrir qué variantes /
ediciones especiales existen en el mundo**, no sólo "dónde se venden hoy". Ejemplos:
Mangavariant (serie/país/publisher/año/rarity, sin precio), ListadoManga preventa,
Manga-Sanctuary planning, Whakoom. Reglas: NO filtrar por falta de price/stock_type;
NO eliminar wikis/referencia para "limpiar"; el enrichment (si llega) es una pasada
SEPARADA que busca la URL de tienda, no un filtro upstream. (Memoria:
`feedback_url_as_reference.md` — el owner lo flageó varias veces.)

## Convención `images[]` — portada por posición, kind simplificado

La portada se determina por **posición**, no por kind: `images[0]` = la portada;
`images[1+]` = galería/extras/vistas.

**`images[0]` es la ÚNICA fuente de verdad de la portada (migración COMPLETADA 2026-06-09).**
Antes había DOS fuentes paralelas a nivel fila —`image_url`/`image_local` top-level vs
`images[0]`— que driftearon en producción (810 filas con `images[0].local` vacío pero
`image_local` con archivo; 575 con URL distinta). Se unificó todo hacia `images[0]`; los
campos top-level `image_url`/`image_local` del item **fueron eliminados del JSONL**:

- **Paso 1 — frontend (HECHO).** Todo el display lee la portada de `images[0]` vía un
  helper `coverImage(item)`. Está en `web/index.html`, `web/quality.html`,
  `web/cover-preview.html`, `web/image-manager.html` y, en web-next, `coverImage()`
  exportado desde `lib/data.ts` (cards, `ItemHero`, `jsonld`, series-cover, páginas OG).
- **Paso 2 — pipeline + datos (HECHO).** El lado Python ya NO escribe `image_url`/
  `image_local` top-level. Helpers canónicos en `image_store.py`: `cover_image`,
  `cover_url`, `cover_local`, `set_cover`, `clear_cover` (operan sobre el dict del row).
  `candidate_to_json` convierte el `image_url`/`image_local` del `Candidate` runtime (input
  del scraper + output del mirror) en `images[0]` al serializar. El merge
  (`merge_cluster`/`_cluster_completeness`) y todos los retrofits leen/escriben vía
  `images[0]`. La migración one-shot fue `retrofit/strip_legacy_cover_fields.py` (rescató
  810 `local` drifteados que existían en disco, sembró `images[0]` donde faltaba, y borró
  los campos top-level; con backup). Las entradas de `sources[]` conservan su propio
  `image_url`/`image_local` per-fuente (no llevan `images[]`): ése es otro layer, intacto.

**El carrusel es a nivel CLUSTER.** Un producto puede tener N filas (una por fuente),
cada una con su `images[]`. El carrusel muestra la UNION dedupeada por URL de todas las
filas. **Invariante crítico**: la portada de la fila canónica (`canonical.images[0]`, la
que muestra la card) va SIEMPRE primera en la union — si no, el carrusel discrepa de la
card. Este merge vive en TRES lugares que DEBEN coincidir: `web/index.html` (`dedupByUrl`),
`build_web.py` (`_merged_canonical`, delega en `manga_watch.merge_cluster`),
`web-next/.../ItemHero.tsx`. Tocás uno → tocá los tres. El gestor de imágenes opera igual
a nivel cluster (`_update_item_images` propaga el set editado a todas las filas del cluster).

**`kind` sólo tiene 2 valores**: `gallery` (foto del producto: portada, contraportada,
lomo, interior, variant cover) y `extra` (bonus/regalo que viene CON el producto: postal,
shikishi, acrylic stand). ELIMINADOS, NO reintroducir: `cover` (→ usar posición 0),
`variant_cover`, `back_cover`. Anti-patterns: `kind: "cover"`, `if img.kind === "cover"`
(usar `idx === 0`), agregar valores de kind sin necesidad demostrada con datos. Aplica en
items.jsonl + manga_watch.py + todos los wikis/retrofits + image-manager.html + index.html
+ ImageCarousel.tsx.

## Image storage — espejo local de portadas

**Por qué**: para deploy multi-usuario hay que **ser dueños de los bytes** (si la fuente
muere/cambia URLs/agrega anti-hotlink, las cards se rompen). Dos cosas separadas: ser dueño
de los bytes (Fase 1, hecha) vs dónde se sirven (Fase 2, planeada).

**Fase 1 — espejo local `data/images/` (IMPLEMENTADA).** El scrape descarga CADA imagen de
cada item nuevo/cambiado a `data/images/<sha256(url)[:16]>.<ext>` y guarda el **filename**
(no la URL) en el campo `local` del entry de `images[]` correspondiente. Características:
- **Multi-imagen**: el extractor `_extract_images_from_detail_soup(soup, url, limit=6)` trae
  todo el carrusel del producto a `images[]` (JSON-LD + og/twitter + selectores de galería
  Shopify/Tiendanube/WooCommerce/Magento + genéricos), acotado al scope del producto y
  filtrando "productos relacionados" (gotcha #31). Un solo `<img>` → lista de 1. La portada
  es `images[0]`; el mirror puebla `local` para TODAS las fotos, no solo la portada.
- La `url` remota de cada entry queda como provenance + fallback (espejo falla → url remota → 📚).
- On por defecto en todo scrape; `--skip-image-download` lo desactiva. Primitivas en
  `image_store.py` (incluye los helpers `cover_url`/`cover_local`/`set_cover`); orquestado
  por `mirror_candidate_images()`.
- **Idempotente** (nombre determinístico). **Validación magic bytes** (descarta HTML de
  error servido como imagen; la extensión sale de los bytes). El `local` de `images[0]` es
  sticky vía el union-merge de `images[]` en `append_jsonl` (gotcha #25).
- `data/images/` gitignored (entrada propia; `data/` no se ignora en bloque). Deploy-agnóstico:
  el JSONL guarda sólo el filename → cambia sólo la base de la URL (local hoy, R2 en Fase 2).
- Retrofits: `backfill_metadata.py --only images` (re-fetch carrusel de items con <2 imágenes,
  fase `[4e2]` del scrape_full); `mirror_images.py` (backfill del histórico + GC mark-and-sweep
  → cuarentena `data/images/_orphans/` o `--gc-delete`).

**Fase 2 — subir el espejo a Cloudflare R2 (PLANEADA).** Al desplegar, sincronizar
`data/images/ → R2` (boto3, S3-compatible). **Bucket R2 propio** (no un prefijo dentro del
bucket de PandaTrack): blast radius de credenciales + GC mark-and-sweep seguro. Serving por
dominio propio (no `r2.dev`, rate-limited). PandaTrack ya usa el patrón con `@aws-sdk/client-s3`
(env `ASSETS_STORAGE_*` / `ASSETS_PUBLIC_BASE_URL`).

## Dedup de portada en el carrusel — `dedup_carousel_images.py`

Cuando un item termina con la MISMA portada en dos resoluciones en `images[]` (ej.
la cover hi-res del publisher + la misma como thumbnail de baja calidad de
listadomanga), `scripts/retrofit/dedup_carousel_images.py` la deduplica por hash
perceptual (aHash 8×8, Hamming ≤6 + aspect ±12%), conservando la de MAYOR
resolución. Solo toca `kind=gallery` (los `extra` —cofres/tomos del box— son
contenido curado y nunca se tocan) y exige dims válidas. Ver retrofit README.

## Búsqueda de portadas hi-res — skill `/watch-search-covers`

> **listadomanga es la causa raíz de la mayoría de portadas de baja calidad.** Verificado
> (gotcha #39): `static.listadomanga.com` guarda las portadas capadas a ~150 px de alto
> (≈100×150), en colecciones de 2012 a 2026, sin versión grande on-site (namespace plano
> `/<md5>.jpg`, sin `srcset`/og:image/página por-volumen). NO hay forma de conseguir alta
> resolución dentro de listadomanga — la única vía es externa con esta skill. Los items
> sourced de listadomanga-collections quedan por debajo del umbral de calidad y son
> candidatos naturales a `/watch-search-covers`.

Skill manual (`.claude/skills/watch-search-covers/SKILL.md`) para encontrar portadas en mayor
resolución para items con imagen pequeña o ausente. Usa **Chrome exclusivamente**
(`mcp__Claude_in_Chrome__*`). El detalle operativo (steps, regex de extracción, flush)
vive en el SKILL.md; el gist:

1. Verifica que Chrome esté conectado (`list_connected_browsers`).
2. Filtra `items.jsonl`: imagen < **90 000 px** (mismo umbral que el panel de calidad,
   `scripts/audit/data_quality.py`; no configurable), saltando targets ya encolados en
   `cover_preview.json`.
3. **Motores, en orden** (verificado en vivo 2026-06-06, ver memoria
   `feedback_google_images_chrome`): primero **Yandex reverse-image**
   (`rpt=imageview&url=<old_url>` — la mejor búsqueda-por-foto gratis), después queries de
   texto con contexto en **Google Imágenes `udm=2`**. Las URLs full-res se extraen con regex
   sobre `innerHTML` (los `img.src` de `udm=2` son thumbnails base64; el patrón viejo
   `"ou":"..."` da vacío). Google Lens y Bing visual NO sirven (franquicia-level matching /
   bloqueado). Fallback a Bing texto si Google muestra consent wall.
4. **Validación de identidad (la regla de oro)**: una candidata SOLO se acepta si
   `fetch_better_covers._same_cover(actual, candidata, MAX_HASH_DIST)` da `True`.
   Umbral endurecido (2026-06-10): **AND de aHash ≤ 6 ∧ dHash ≤ 8 ∧ pHash(DCT) ≤ 8**
   + **NCC 64×64 ≥ 0.90** (correlación normalizada de parche central) + **gate de entropía**
   (std pixel gris en patch 32×32 < 20 ⇒ imagen casi sólida ⇒ rechazar) + eliminada la
   relajación +4 de umbral para originales chicas + formatos no parseables
   (GIF animado / AVIF / WebP-lossless sin dims detectables) ⇒ rechazar +
   `candidate_metadata_conflict()`: volumen o ISBN detectado en la URL del candidato que
   difiere del item ⇒ hard reject. Otro volumen / otra edición / arte distinto → descarta.
   Precisión > recall: mejor 0 candidatas que una no relacionada. (Imagen corrupta →
   hash no computable → rechazar.)
5. Guarda imágenes válidas en `data/images/` (nombre sha256) y flushea **atómico** a
   `data/cover_preview.json` después de cada item.

**Re-validación del corpus de candidatas (2026-06-10):** 459 candidatas de 200 items →
154 `verified=true` / 305 `false`. Breakdown de causas de rechazo: `hash_dist` 92,
`aspect_ratio` 75, `ncc` 67, `dhash` 42, `phash` 21, `entropy` 8. 117 items con ≥1
candidata válida. Los falsos positivos conocidos del audit quedaron rechazados. El flujo
sigue siendo de aprobación manual (`cover_preview.json` nunca toca `items.jsonl`).
**2026-06-11**: las 305 `verified=false` se purgaron de la cola (status → `rejected`,
conservando `verify_reason`) — estaban `pending` y la UI no distingue `verified`, así que el
owner seguía viéndolas; el validador embebido del skill (Step 2 del SKILL.md) se re-sincronizó
con producción (aHash default 6 sin relax + llamada a `candidate_metadata_conflict()`).

**Invariantes**:
- Candidatas: `confidence: "low"`, `status: "pending"` — sin excepción.
- `_sc_validate.py` (validador temporal en `scripts/retrofit/`) se borra al finalizar.
- **NUNCA** modifica `items.jsonl`. La aprobación es manual vía `cover-preview.html`.
- Flags: `--limit N`, `--slug SLUG`, `--gallery-only`, `--include-no-image`,
  `--query-extra "texto"`.

### Eliminar fotos de la galería actual (`cover-preview.html`)

Cada miniatura del bloque **"Galería actual"** del panel de revisión tiene un botón rojo
`×` (visible al pasar el mouse) que elimina esa foto del catálogo. Reusa el endpoint del
gestor de imágenes `POST /api/image-manager/save` (no inventa endpoint propio): parte de la
**unión `images[]` del cluster** (`_clusterImagesFor`, mismo dedup por URL/local que
`image-manager.html`), quita la foto elegida y reescribe `images[]` en **todas las filas del
cluster**; si el archivo local queda huérfano se borra del espejo (el chequeo de huérfanos
considera `images[].local` + `sources[].image_local` de todas las filas **y** las referencias
de `cover_preview.json` —`old_image`/`new_image`/`candidates[].new_image`, mismo set que el
GC de `mirror_images.py`— para no romper el panel de review, fix 2026-06-10). Tras eliminar,
re-marca la portada por posición (`images[0]`), actualiza `current_images` en memoria y
persiste `cover_preview.json` vía `/api/save-cover-preview` (endpoint serializado + escritura
atómica desde 2026-06-10; antes un save concurrente con un apply podía dejar el JSON
truncado). A diferencia de la aprobación de
candidatas, esta acción **sí modifica `items.jsonl`** de inmediato (es una edición directa de
galería, equivalente a borrar desde el gestor).

El **modal de zoom** (al hacer clic en una miniatura de la galería) también permite eliminar
y navegar: cuando el zoom se abre desde la galería actual (`zoomCtx`), muestra flechas
laterales ◀ ▶ + soporte de teclado ← → para recorrer las fotos del producto, un contador
`i / N`, y un botón **🗑 Eliminar** (`deleteFromZoom`, reusa `deleteGalleryImage` y reposiciona
el visor a la foto siguiente, o cierra si no queda ninguna) junto al de "usar como referencia".

