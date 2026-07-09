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
`web-next/lib/images.ts` (`dedupeImages`/`imageKey` — desde 2026-06-12 es la fuente
ÚNICA dentro de web-next: ItemHero e ImageCarousel la importan; antes cada uno tenía
su copia con criterio distinto y una URL http vs https pasaba un dedup pero no el otro).
Tocás uno → tocá los tres. El gestor de imágenes opera igual
a nivel cluster (`_update_item_images` propaga el set editado a todas las filas del cluster).

### Clave de dedup de imágenes — paridad de 3 lugares (2026-07-07)

La CLAVE que decide "son la misma foto" para el dedup del carrusel debe tener la
MISMA semántica en los tres lugares de arriba — si diverge, la misma imagen en dos
tamaños distintos pasa el dedup en un lugar pero no en otro (thumb y full quedan
ambas en la galería). Referencia canónica: `manga_watch._img_stem`, que delega en
`manga_watch._gallery_url_normalize` — la usa `merge_cluster` para unir `images[]`
cross-fuente. `web/index.html` (`imgKey`) y `web-next/lib/images.ts` (`imageKey`)
replican la MISMA regex:

- Strippea el esquema (`http://`/`https://`), query string y fragment.
- Lowercase.
- **Strippea sufijos de tamaño de CDN con GUION BAJO** (estilo Shopify:
  `_600x600.jpg`, `_grande.jpg`, `_small.jpg`, `_master.jpg`, etc. — lista completa
  en el regex `IMG_KEY_SUFFIX_RE`/`_img_stem`) para que un thumb dedupee contra la
  imagen full del mismo producto.

**Gap conocido (documentado, no arreglado)**: sufijos de tamaño estilo WordPress con
GUION MEDIO (`img-800x600.jpg`) **NO se strippean** en NINGUNO de los tres lugares —
el docstring viejo de la función Python mencionaba "WP -NxM" como aspiracional, pero
la regex nunca lo implementó. Si aparece un caso real de thumb/full WordPress sin
dedupear, hay que agregar el patrón a los TRES lugares a la vez (nunca a uno solo).
Tests: `tests/test_audit_wo_g.py` (Python) / `web-next/__tests__/images.test.ts`
(TypeScript) — comparten la misma tabla de fixtures URL→clave esperada; si agregás un
caso a un archivo, agregalo también al otro.

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
  - **Detección ESTRUCTURAL de grilla de relacionados (2026-07-07, gotcha #31 actualizada)**:
    el filtro de "mismo directorio padre" no alcanza cuando la cover PROPIA del producto
    también vive en el mismo subdirectorio que los relacionados (Star Comics: tanto la cover
    real como los thumbnails de "ti potrebbe interessare" cuelgan de
    `/files/immagini/fumetti-cover/thumbnail/`). `_related_grid_card_ids()` complementa el
    filtro de path con una señal de FORMA: ≥3 product-cards dentro del scope que enlazan
    (`<a href>`) a ≥3 páginas de producto DISTINTAS (no a archivos de imagen — eso es lightbox/
    zoom de la propia galería) se detectan como grilla de relacionados y se excluyen del
    harvest vía `_node_in_grid()`. Una galería legítima del propio producto no enlaza a N
    páginas de producto distintas, así que nunca la dispara. El purge de este bug limpió 29
    entradas contaminadas del corpus.
  - **`srcset` → mayor resolución**: `_img_to_url` parsea todas las entradas del `srcset` y
    elige la de mayor descriptor `<N>w`; sin descriptores, toma la última (gotcha #67).
  - **`<a href="full.jpg">` envolviendo `<img>`**: cuando el `<a>` apunta a imagen del mismo
    dominio, se prefiere el href (full-res) sobre el src del `<img>` (thumb — patrón
    Magento/Fotorama/LightGallery; gotcha #68).
  - **Placeholders de lazy-load como archivo real**: `src="/gfx/pol/loader.gif"` +
    portada en `data-src` (Mangarden). `_LAZY_PLACEHOLDER_RE` saltea nombres exactos
    de loader/blank/spinner para caer al data-src (gotcha #88).
  - **URLs no-ASCII** (slugs thai/chinos): `download_image` hace `requote_uri` de URL
    y referer; `UnicodeError` capturado para no matar el proceso (gotcha #89).
  - **El union-merge de `images[]` es sticky en AMBAS direcciones** (gotcha #87): en
    colisión (kind, url), el entry conservado rellena `local`/`description` vacíos con
    los del duplicado — cubre el flush-pre-mirror de los wikis Y el re-scrape sin descarga.
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
  → cuarentena `data/images/_orphans/` o `--gc-delete`). **Excepción al guard `approved_at`
  (2026-07-07)**: `mirror_images.py` es ADITIVO (sólo rellena un `local` faltante; nunca
  quita/reordena/reemplaza una entry existente), así que se aplica IGUAL a items aprobados
  por defecto — un golden record también necesita su espejo local. Acepta `--include-approved`
  por consistencia de CLI con el resto de retrofits de imagen, pero no cambia el
  comportamiento del backfill (sólo reporta a título informativo cuántas entries rellenadas
  eran de items aprobados). El GC (huérfanos) tampoco necesita el guard: opera sobre archivos
  en disco, no muta `images[]` de ningún item.

**Fase 2 — subir el espejo a Cloudflare R2 (PLANEADA).** Al desplegar, sincronizar
`data/images/ → R2` (boto3, S3-compatible). **Bucket R2 propio** (no un prefijo dentro del
bucket de PandaTrack): blast radius de credenciales + GC mark-and-sweep seguro. Serving por
dominio propio (no `r2.dev`, rate-limited). PandaTrack ya usa el patrón con `@aws-sdk/client-s3`
(env `ASSETS_STORAGE_*` / `ASSETS_PUBLIC_BASE_URL`). Decisión 2026-06-15 (verificada): R2 con
**masters pre-optimizados** + dominio + Cache Rule (`Cache-Control: public, max-age=31536000,
immutable`) ≈ **0 USD/mes** (los ~2-3 GB optimizados caben en el free tier de 10 GB; egress
gratis). Pre-optimizar es OBLIGATORIO: R2 no transforma imágenes. No hace falta Cloudflare
Images (~2-4 USD/mes) ni Polish (requiere plan Pro) para este caso.

## Normalización / estandarización al ingresar (2026-06-15)

**Toda imagen que entra al espejo se estandariza a un "master de display" único: AVIF
Q60, lado largo ≤ 1600 px, sin metadata (EXIF/ICC).** Antes el espejo guardaba los bytes
CRUDOS de la fuente (14.58 GB, 24 166 archivos; los PNG eran el 71% del peso a ~1.65 MB c/u).
Evolución del formato: crudo 14.58 GB → WebP q80 2.37 GB (1ª pasada) → **AVIF Q60 ~1.5 GB**
(2026-06-15). AVIF pesa ~27% menos que WebP a igual calidad visual; acota el crecimiento del
catálogo y entra holgado en el free tier de R2. **Tamaño/formato = decisión del owner (1600 px
/ AVIF Q60).**

**Soporte de navegador AVIF ~93%** (Chrome 85+/Firefox 93+/Edge 121+/Safari 16.4+ desde 2023).
El owner decidió **NO soportar el ~6-7% viejo** (Safari pre-2023): en web-next `next/image`
transcodifica solo a un formato que el navegador acepte; el dashboard estático cae a la URL
remota. (AVIF Q~50-63 ≈ WebP q80; encode más lento pero es batch/offline.)

**Fuente ÚNICA: `image_store.normalize_image(body) -> (bytes, ext)`** (nunca reimplementar la
lógica en otro lado). Reglas:
- Solo redimensiona **hacia abajo** (nunca agranda — el upscale AI es otro proceso, manual; ver
  `upscale_images.py`). Motor **pyvips** (`heifsave_buffer(Q, compression='av1', effort=4)`,
  ~2.6× más rápido y ~11× menos memoria que Pillow) con **fallback a Pillow** (`save(...,'AVIF')`,
  nativo desde 11.3). Dependencias: `brew install vips` + `pip install pyvips` + `Pillow>=11.3`.
  `image_store` fija **`VIPS_CONCURRENCY=1`** al importar: libvips usa TODOS los cores por imagen,
  lo que oversuscribe la CPU al paralelizar por archivo (scrape/backfills con ThreadPoolExecutor);
  single-thread por imagen + paralelismo por pool es ~3× más rápido en batch (medido).
- **Idempotente**: una imagen ya AVIF y ≤ 1600 px se devuelve sin re-encodear (cero pérdida
  generacional). Una AVIF > 1600 px se redimensiona.
- **NUNCA toca placeholders** (gotcha #100): si `placeholder_reason(body) != ""` devuelve los
  bytes CRUDOS sin tocar, para que la detección por FIRMA (sha1 del contenido) de
  `purge_placeholder_images` siga matcheando aguas abajo. Si re-encodeáramos, el sha1 cambiaría.
- **Degrada con gracia**: ante error de decode/encode (o sin pyvips/PIL) devuelve los bytes
  originales con su extensión — nunca rompe el scrape.

**Los 3 cuellos de botella de escritura** (todos llaman a `normalize_image`, cubren los ~11
entry points): `image_store.download_image()` (scrape, `mirror_images`, `upgrade_image_resolution`,
`backfill_prh_covers`, `wayback_recover`); `fetch_better_covers._save_image()` (skill
`/watch-search-covers` vía `sc_validate`, `apply_preview`, PRH); `serve.py._download_image_to_store()`
(gestor de imágenes). El stem del archivo no cambia (sigue `sha256(url)[:16]`), solo la extensión
pasa a `.avif`; `existing_local_image()` ya hace glob `<stem>.*` así que los re-scrapes reusan el
`.avif` sin re-descargar.

**Backfills (one-shot, históricos):**
- `optimize_images.py` — 1ª pasada (crudo → estandarizado): normaliza in situ, archiva los
  originales a `data/images/_originals/`. Flags: `--dry-run`, `--limit`, `--workers`,
  `--originals {archive,delete,keep}`.
- `migrate_images_to_avif.py` — **re-deriva los masters a AVIF DESDE `_originals/`** (sin doble
  compresión; calidad = la fuente), hace **dedup por contenido** (imágenes pixel-idénticas tras
  normalizar colapsan a un solo archivo) y **borra los WebP reemplazados** (el original queda en
  `_originals/`). Crash-safe, idempotente, con backup de items.jsonl/cover_preview.json.
  Tests: `tests/test_migrate_images_to_avif.py`.

⚠️ Cerrá el panel de cover-preview antes de correr cualquiera (reescriben `cover_preview.json`;
el guard de mtime lo recarga si intenta guardar encima). Tests del core:
`tests/test_normalize_image.py`, `tests/test_optimize_images.py`.

**GC rutinario (anti-explosión).** Cada scrape corre `[4j] mirror_images.py --gc-only` (delta y
full): manda a cuarentena `data/images/_orphans/` los archivos que ningún item referencia
(portadas reemplazadas por el skill/scripts, masters viejos). Reversible y NO toca `_originals/`
(el GC sólo escanea archivos top-level de `data/images/`). Vaciar `_orphans/` periódicamente (o
`--gc-delete`) para reclamar el disco. Esto evita el verdadero riesgo de crecimiento: los
archivos MUERTOS, no las fotos vivas (cada foto está acotada a ~110 KB por el cap AVIF/1600).

## Upgrade de resolución — `upgrade_image_resolution.py`

Re-descarga portadas en resolución completa eliminando parámetros/segmentos CDN de
resize. Corre como fase `[4g2]` de `scrape_full.sh` (después de `consolidate_sources`,
antes de `dedup_carousel`). NO corre en el delta.

**Patrones verificados empíricamente (2026-06-11)** — además de los 5 anteriores
(Magento query params, WordPress -NxM, Shopify _Nx, Amazon ._SY300_., Rakuten ?_ex=):
- **Buscalibre** (`images.cdnN.buscalibre.com`): quita segmento `fit-in/<W>x<H>/` → ganancia 2-22×.
- **Cultura** (`cdn.cultura.com`): quita segmento `cdn-cgi/image/width=<N>/` (Cloudflare Polish) → hasta 2×.
- **Whakoom** (`i1.whakoom.com`): `/small/` o `/thumb/` o `/medium/` → `/large/` → 3×.
- **Magento cache path** (`/media/catalog/product/cache/<hex>/`): quita el segmento → acceso a la imagen original. **⚠️ Requiere validación same_cover** (bdfugue y similares ~20% devuelven imagen distinta); el script la aplica automáticamente cuando está disponible PIL.

Patrones **no agregados** (verificados como no viables): Amazon (los modificadores no controlan resolución), Manga-Sanctuary `/objet/300/` (es el máximo del servidor), Rakuten (404 sin ?_ex).

El download pasa `referer=<url del item>` para evitar 403 de CDNs con anti-hotlink. La comparación de píxeles (umbral `--min-gain 0.10`) evita reemplazar por la misma imagen o peor.

**Guard `approved_at` (2026-07-07, gotcha #121)**: por defecto saltea items aprobados
(golden records) — el script reemplaza `url`/`local` de una entry existente sin cola
de revisión. `--include-approved` fuerza. Mismo guard homogéneo en los 13 scripts de
imagen/agrupación de listadomanga (ver `docs/reference/conventions.md`).

## Backfill de portadas externas en `scrape_full.sh` — `RUN_COVER_BACKFILL=1` (opt-in, 2026-07-07)

`backfill_prh_covers.py` (CDN determinístico de Penguin Random House, ISBN EN) y
`fetch_better_covers.py` (búsqueda web ISBN/Tavily/Serper) van MÁS ALLÁ de lo que
`upgrade_image_resolution.py` puede hacer (ese sólo re-pide la misma URL sin params de
resize, mismo dominio; estos buscan portadas hi-res en OTRAS fuentes). Pasos **[4g3]/
[4g4]** de `scrape_full.sh`, ubicados DESPUÉS de `[4g2]` (que ya agotó la mejora
"gratis" intra-dominio) y ANTES de `[4h]` `dedup_carousel_images` (que necesita ver el
estado FINAL de portadas). **Default OFF** — son network-heavy (`fetch_better_covers`
hace hasta 1 búsqueda web por item candidato) y `fetch_better_covers` necesita
`SERPER_API_KEY` o `TAVILY_API_KEY` en `.env` para buscar (sin key, sólo corre el
fallback CDN/ISBN, funciona igual pero acotado). Activar con `RUN_COVER_BACKFILL=1
./scripts/scrape_full.sh`. **Seguro por defecto**: `fetch_better_covers` sin `--apply`
no reemplaza nada — todo queda en `data/cover_preview.json` para aprobación manual
(ver "Búsqueda de portadas hi-res" abajo y `cover-preview.html`). NO está en
`scrape_delta.sh` (sólo full).

## Promoción de hi-res intra-cluster — `promote_hires_cover.py`

Caso: un item tiene su portada en `images[0]` como thumbnail de listadomanga (<90 000 px,
`static.listadomanga.com`) pero la MISMA portada en alta resolución ya está en `images[1+]`
porque el cluster tiene otra fuente (Panini, Norma, Whakoom, etc.). El script intercambia
`images[0] ↔ images[k]` para que la hi-res quede como portada. No hace ninguna petición de
red — trabaja con lo que ya está en el catálogo.

**Criterio de identidad thumbnail↔full** (mismo que `dedup_carousel_images.py`): el thumbnail
de listadomanga (~100×150 px) degrada el hash lo suficiente como para superar el umbral
estricto de `_same_cover`. Por eso usa un umbral relajado: si la portada actual tiene lado
menor ≤ 170 px y la candidata es ≥ 2× más grande → par thumbnail↔full → aHash ≤ 14/64 bits
+ aspect ratio ≤ 6%. Si no cumple ese par, se aplica `_same_cover` estricto (AND-gate).

**Drift corregido (2026-07-08, hallazgo #3)**: el aspect ratio del par thumbnail↔full estaba
en ±12% con el comentario "mismo que dedup", pero `dedup_carousel_images.THUMB_ASPECT_TOL`
es en realidad 0.06 — éste es el ÚNICO de los dos scripts que muta `images[0]` SIN cola de
revisión (dedup sólo decide qué queda en la galería), así que tener el umbral MÁS laxo era
al revés de lo que hace falta. Corregido a 0.06 para matchear de verdad. Los 3 umbrales
(`THUMB_MAX_SIDE`/`THUMB_HAMMING`/`THUMB_ASPECT_TOL`) siguen DUPLICADOS entre este script y
`dedup_carousel_images.py` — ninguno es hoy el lugar canónico; centralizarlos en una
constante compartida (candidato natural: `fetch_better_covers.py`, ya fuente única de
`LOW_QUALITY_PX`/`SOFT_GUARD_PX`/`DETAIL_RATIO_MIN`/`DEFAULT_MAX_HASH_DIST`) queda pendiente.

El thumbnail queda en la galería; ejecutar `dedup_carousel_images.py` después si se quiere
eliminarlo. Tests: `tests/test_promote_hires_cover.py`. Flags: `--dry-run`,
`--include-approved` (por defecto saltea aprobados — promover intercambia `images[0]`
sin cola de revisión).

Cuándo usarlo: después de `upgrade_image_resolution.py` (paso 3 del sub-pipeline de imágenes)
y antes de cualquier retrofit que necesite ir a la red, ya que resuelve el problema sin costo
de red cuando la hi-res ya está en el cluster. Lee cada archivo (portada + candidatas) UNA
sola vez (`_read_and_px`, hallazgo #13, 2026-07-08) — antes `_px`/`_read_local` releían el
mismo archivo por separado.

## AI upscale de portadas pixeladas — `upscale_images.py`

AI upscaling (waifu2x/realesrgan) ×2 para thumbnails JP pequeños (sumikko,
booksprivilege, Rakuten, animeclick — típicamente <200k px sin hi-res en origen).

**Pasa por `image_store.normalize_image` (fuente única, P27, 2026-07-07)** — antes
guardaba el PNG lossless crudo del upscaler directo al espejo, pesando órdenes de
magnitud más que sus pares; ahora el resultado se normaliza igual que cualquier otra
imagen que entra al corpus (AVIF Q60, lado largo ≤1600px). El nombre de archivo pasa a
ser content-addressed (`sha256(bytes normalizados)[:16]`), igual que
`fetch_better_covers`/`image_store.download_image`.

**Marca `upscaled: true`** en cada entry de `images[]` que reemplaza — permite a
scripts downstream (ej. `fetch_better_covers`) distinguir un upscale de IA de una foto
hi-res real y preferir reemplazarla si aparece una candidata mejor. Es también la señal
PRIMARIA de idempotencia: una entry con `upscaled: true` se saltea SIEMPRE (nunca se
re-upscalea un upscale — degradaría más la imagen), más robusta que inferir por tamaño
de archivo (el criterio viejo).

**Guard `approved_at`**: por defecto saltea el archivo ENTERO (no sólo el item) si
CUALQUIERA de los items que referencian ese `local` está aprobado — un mismo archivo
puede ser compartido por varios items y no se quiere actualizar unos sí y otros no.
`--include-approved` fuerza.

**Gotcha cerrada (P27, #124)**: el parser de píxeles por bytes no reconoce AVIF: caía
al fallback de tamaño de archivo, que es sistemáticamente MENOR que los píxeles reales
para una imagen comprimida — el gate de ganancia (`new_px <= old_px`) rechazaba TODO
upscale sobre el espejo ya normalizado. Fix: fallback a PIL (`Image.open(...).size`)
para AVIF y cualquier formato no cubierto por el parser binario, antes del proxy de
tamaño de archivo.

## Dedup de portada en el carrusel — `dedup_carousel_images.py`

Cuando un item termina con la MISMA portada en dos resoluciones en `images[]` (ej.
la cover hi-res del publisher + la misma como thumbnail de baja calidad de
listadomanga), `scripts/retrofit/dedup_carousel_images.py` la deduplica por hash
perceptual (aHash 8×8, Hamming ≤6 + aspect ±12%), conservando la de MAYOR
resolución. Solo toca `kind=gallery` (los `extra` —cofres/tomos del box— son
contenido curado y nunca se tocan) y exige dims válidas. Por defecto saltea items
aprobados (`--include-approved` fuerza) — el dedup puede reordenar `images[0]` (la
portada) de un golden record. Ver retrofit README.

## Limpieza de galería — `sync_cover_images.py`

Limpia `images[]` alrededor de la portada (`images[0]`, única fuente de verdad): si la
portada es un placeholder/banner conocido la reemplaza por la primera foto real de la
galería (o la limpia si no hay ninguna); quita duplicados exactos y basura conocida de
las posiciones ≥1; limpia refs basura en `sources[]`. Idempotente, guard `is_approved`,
backup vía `backup_and_rotate`.

- **Guard de espejo ausente (2026-07-08, hallazgo #2, ALTA)**: `run()` aborta si
  `not images_dir.exists()`. Antes, `_compute_junk_local` igualaba "el archivo no está en
  `data/images/`" con "el archivo pesa 0 bytes" (`sizes.get(f, 0)`) — si el espejo entero
  faltaba (o un archivo simplemente no se había mirroreado todavía), CADA `local`
  referenciado caía en la rama junk y `_fix_bad_cover` arrasaba portadas en masa. Ahora
  "no está en el espejo" es un skip legítimo; sólo "está pero pesa 0 bytes" es basura real.
- **`_fix_bad_cover` no promueve `extra` a portada (2026-07-08, hallazgo #8)**: sólo
  `kind: "gallery"` es elegible para reemplazar una portada basura — un `extra` (postal,
  shikishi) es un bonus que viene CON el producto, nunca la ficha del producto. Y cuando NO
  hay reemplazo de galería válido, ya no vacía `images[]` entero: conserva el resto
  (extras legítimas incluidas), sólo quita la portada basura de la posición 0.
- **Clave "misma imagen" alineada a `manga_watch._img_stem` (2026-07-08, hallazgo #10)**:
  `_norm()` era un cuarto criterio de dedup propio, divergente del canónico documentado
  arriba en "Clave de dedup de imágenes — paridad de 3 lugares". Ahora compone
  `image_store.normalize_image_url` (sufijo WordPress -NxM + query Magento) con `_img_stem`
  (sufijo Shopify + query genérico + esquema + minúsculas).
- **`is_approved()` + `sort_keys=True` (2026-07-08, hallazgo #12)**: usaba
  `it.get("approved_at")` directo en vez del helper de `manga_watch.py`, y era el único
  escritor de `items.jsonl` cuya serialización dependía del orden de inserción del dict.

## Purga de placeholders / 1×1 / rotas — `purge_placeholder_images.py`

Varias fuentes, cuando NO tienen la carátula de un producto, en vez de 404 sirven una
imagen genérica que el mirror baja como si fuera la portada (pasa el chequeo de magic
bytes: ES una imagen válida). Casos verificados (2026-06-13): Amazon devuelve un **GIF
1×1** para ISBN sin foto (`images-na.../P/<ISBN>...jpg`), listadomanga/otros CDNs un
**blanco**, Penguin Random House **"Cover Coming Soon"**, Funside **"Immagine non
disponibile"** (logo MD), SocialAnime **"Image coming soon"** (robot EPM). Resultado: la
card muestra el placeholder de la fuente en vez del 📚 por defecto.

**Detector por CONTENIDO — fuente ÚNICA `image_store.placeholder_reason(source)`** (úsalo, no
reimplementes). `source` = bytes o path; devuelve `""` (real) o la razón:
- `tiny:WxH` — algún lado ≤ 8 px (tracking pixel / 1×1).
- `solid:STD` — std global de luminancia < 3 ⇒ imagen casi de un solo color (el blanco
  "sin portada"). Una portada de manga real tiene std ≫ 20 — cero zona gris.
- `broken` — 0 bytes / no abre con PIL / truncado.
- `signature:LABEL` — el sha1 del CONTENIDO está en `data/placeholder_signatures.json`.
  Ahí van SOLO los placeholders **con texto/logo** (no caen por baja entropía). Para
  agregar uno: pegá su sha1 en ese JSON — **no toca código**.

**Detector por URL — fuente ÚNICA `image_store.known_placeholder_url_reason(url)`** (gotcha
#112). Complementa al de contenido para dos casos que éste NO puede ver: (1) placeholders que
**nunca se espejaron** (`local=""`, decide sólo por la URL — clave para el `08a02c…png`
"portada censurada" de listadomanga que llega con `local` vacío), y (2) assets de sitio
(logos, iconos de UI, "adulto") que SON imágenes válidas con textura. Registro en dos partes:
- `KNOWN_PLACEHOLDER_URL_STEMS` — stem exacto del basename (archivos con nombre hash del CDN):
  `08a02c…` = listadomanga censored-cover.
- `KNOWN_PLACEHOLDER_URL_FRAGMENTS` — substring de la URL (assets de sitio con nombre
  descriptivo): `TwitterFollow.png` (otakucalendar), `img/adulte.png` (manga-sanctuary),
  `funside-logo-light` (funside), `buste_protettiva_fumetti` (socialanime — accesorio).
  Sumar uno = una línea en el dict — **importable, sin copias** (el parser de listadomanga lo
  usa en Layout A y Layout B; ver gotcha #40/#112).

**⚠️ "Contenido idéntico repetido" NO es señal de placeholder.** La portada real de *BECK
16* aparecía idéntica en 3 items (eso es cross-cover, otro bug). El detector la deja
intacta (std 66) porque borra solo por reglas estructurales/firma, nunca por repetición.

**Retrofit `scripts/retrofit/purge_placeholder_images.py`** (sin red, lee el espejo local):
- Quita la ENTRY completa de `images[]` (no solo `local`: si quedara la `url` remota, la
  card cargaría el placeholder remoto igual) en TODAS las filas. Tres detecciones:
  1. **por CONTENIDO local** (`placeholder_reason` — estructural/firma) para las espejadas;
  2. **por URL conocida** (`known_placeholder_url_reason` — gotcha #112): purga aunque
     `local=""` y en cualquier posición (un placeholder conocido nunca es cover real);
  3. **genérica cross-series**: la MISMA URL en ≥ N series DISTINTAS (`--cross-series-min`,
     default 4) es sospechosa → se purga SOLO de galería (`idx>0`), **NUNCA de la portada
     (`images[0]`)**. Una foto puede ser el cover legítimo de UNA serie y contaminar el
     carrusel de otras (caso real: los thumbnails de búsqueda de Star Comics inyectados en
     ediciones "variant"); quitar la portada destruiría un cover real, quitar la copia de
     galería es siempre seguro. Se agrupa por SERIE (`series_display`, fallback título sin
     volumen), no por item, para no castigar box↔tomos de la misma serie que comparten foto.
- Preserva el **dueño legítimo** identificable: si una URL-placeholder la lleva UN solo item
  como `kind=extra`/`bonus` de su propia colección, ahí se conserva (y no se limpia su source).
- Limpia `sources[].image_local`/`image_url` que apunten al mismo archivo/URL.
- Re-marca la portada por posición (la primera foto que queda pasa a `images[0]`); un item
  sin fotos muestra el 📚.
- GC: los archivos que quedan huérfanos van a cuarentena `data/images/_orphans/`
  (reversible; protege los referenciados por `cover_preview.json`). `--keep-files` lo evita.
- Optimización: solo evalúa archivos ≤ 200 KB (un placeholder pesa pocos KB; una portada
  real > 200 KB jamás es casi-sólida ni matchea firma) → no decodifica los 14 GB de espejo.
- Idempotente. Flags: `--dry-run`, `--keep-files`, `--cross-series-min N`,
  `--include-approved` (por defecto saltea items aprobados; sus locals SIGUEN contando
  como "sobrevivientes" para el GC aunque no se toque la entry, para no mandarlos a
  cuarentena si otro item no-aprobado que comparte el mismo archivo lo pierde en su
  propia pasada). Tests: `tests/test_purge_placeholder_images.py`.

Corre como paso **[4i]** del pipeline canónico (delta y full), después de
`dedup_carousel_images` y antes de `build_web`, así un placeholder que reentre durante un
scrape no llega al build. Corrida inicial 2026-06-13: 165 entries quitadas (87 sólidos, 63
pixeles 1×1, 15 con firma), 138 items pasaron a mostrar el 📚.

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
3. **Motores, en orden** (verificado en vivo 2026-06-11): para items en **Español**:
   primero **whakoom** (`site:whakoom.com <serie> <vol>` vía Google `udm=2` — produjo el
   100% de los matches ES en la corrida 2026-06-11, 8/8; yandex-reverse 0 porque los
   thumbnails de listadomanga no están indexados por Yandex), después **Yandex reverse-image**
   (`rpt=imageview&url=<old_url>` — mejor búsqueda-por-foto gratis), después queries de
   texto con contexto en **Google Imágenes `udm=2`**. Para otros idiomas: Yandex reverse
   va primero. Las URLs full-res se extraen con regex sobre `innerHTML` (los `img.src` de
   `udm=2` son thumbnails base64; el patrón viejo `"ou":"..."` da vacío). Google Lens y
   Bing visual NO sirven (franquicia-level matching / bloqueado). Fallback a Bing texto si
   Google muestra consent wall.
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
4b. **Gate de calidad de display (gotcha #98)**: la identidad NO garantiza calidad — un
   escaneo blando o upscale de la MISMA portada pasa el AND-gate pero se ve pixelado. El
   px count engaña (la casadellibro 80k mala y una whakoom 637k buena miden el mismo
   `_detail_ratio` ≈ 0.10); lo que distingue es el TAMAÑO. Una candidata se rechaza si es
   **CHICA** (`< SOFT_GUARD_PX` = 150k px → se muestra agrandada, la blandura se nota) **Y
   BLANDA** (`fetch_better_covers._detail_ratio < DETAIL_RATIO_MIN` = 0.115 → poca energía
   en la octava superior medida a 384px). Las grandes-pero-blandas pasan (se muestran
   reducidas → nítidas). Mismo gate (`_is_soft_image`) en el script de producción
   (`fetch_better_covers._process_item`) y en `sc_validate.py` — fuente única. La cola ya
   armada se re-evalúa con `prune_soft_cover_candidates.py`: candidatas `pending` que dan
   blandas se marcan `status: "rejected"` + `reject_reason: "soft_image"` y se appendean al
   ledger de rechazos (2026-07-08, hallazgo #9 — antes las eliminaba en silencio SIN dejar
   rastro, política divergente de `revalidate_cover_preview.py` que sí marca rejected+ledger
   para el mismo gate; ahora ambos scripts comparten la misma política, reusando
   `sync_cover_preview._ledger_record_from_candidate`). Tests: `tests/test_detail_ratio.py`.
5. Guarda imágenes válidas en `data/images/` (nombre sha256) y flushea **atómico** a
   `data/cover_preview.json` después de cada item.

**Step 5 del skill (`--serper-fallback`, opcional, de pago, 2026-07-08):** tras terminar el loop
de Chrome (pasos 1-5 de arriba), invoca el MOTOR de producción (`fetch_better_covers.py`, con
`SERPER_API_KEY`) para reverse-image vía Google Lens, sólo sobre los targets que terminaron en 0
matches. Acotable a una lista exacta de slugs con `--slugs slug1,slug2` (repetible, agregado
2026-07-08) — `--limit` sigue siendo el corte por cantidad, `--slugs` es el filtro por identidad
exacta. Detalle completo (comando, costo, cuándo correrlo) en
`.claude/skills/watch-search-covers/SKILL.md` § "Step 5".

**Hallazgo del piloto e2e (2026-07-08, 10 items con 0 matches del Step 4):** Google Lens vía
Serper devolvió **0 candidatas** partiendo de thumbnails ORIGEN chicos (~10 000-16 000 px:
listadomanga, aladin, rakuten) — confirmado en `data/cover_search_attempts.jsonl` (`engines.lens`
en 0 en toda la corrida). Lens necesita una imagen de consulta con detalle suficiente para el
matching visual; una referencia diminuta no le da con qué. La vía efectiva para estos casos es
el **TEXT SEARCH localizado** (Step 3, queries con contexto en Google Imágenes `udm=2`), que
llega a los CDNs de las editoriales directamente por nombre/serie/tomo sin depender de la calidad
de la imagen de referencia — en el mismo piloto produjo matches donde Lens no encontró nada
(`engines.text` > 0 en varios slugs ES/KR). Conclusión: Lens no es palanca de mejora para
referencias diminutas; la "ficha de editorial" (pendiente, ver CLAUDE.md § "Next things on the
radar") es la vía de fondo para listadomanga.

**Re-validación del corpus de candidatas (2026-06-10):** 459 candidatas de 200 items →
154 `verified=true` / 305 `false`. Breakdown de causas de rechazo: `hash_dist` 92,
`aspect_ratio` 75, `ncc` 67, `dhash` 42, `phash` 21, `entropy` 8. 117 items con ≥1
candidata válida. Los falsos positivos conocidos del audit quedaron rechazados. El flujo
sigue siendo de aprobación manual (`cover_preview.json` nunca toca `items.jsonl`).
**2026-06-11**: las 305 `verified=false` se purgaron de la cola (status → `rejected`,
conservando `verify_reason`) — estaban `pending` y la UI no distingue `verified`, así que el
owner seguía viéndolas; el validador embebido del skill (Step 2 del SKILL.md) se re-sincronizó
con producción (aHash default 6 sin relax + llamada a `candidate_metadata_conflict()`).

**Mejoras 2026-06-11**:
- **Upgrade de URL antes de validar** (`sc_validate.py`): antes de intentar el fetch de cada
  candidata, `upgrade_url_variants(url)` prueba variantes hi-res derivadas de la URL original.
  Patrones verificados: whakoom `/small/` → `/large/` (3× px); buscalibre quita
  `fit-in/<W>x<H>/` (2-22× px); cultura quita `cdn-cgi/image/width=<N>/`; bdfugue (Magento)
  quita `cache/<hash>/`; WordPress genérico quita sufijo `-<W>x<H>` del nombre de archivo.
  `_same_cover` valida cada descarga, así que una reescritura incorrecta no contamina.
  `new_url` en el resultado refleja la variante que se usó efectivamente.
- **Default solo-portadas**: por defecto el skill solo procesa `img_idx == 0` (portadas). Las
  fotos de galería interior son irrecuperables en su mayoría (no existe copia externa); en la
  corrida real 12/25 targets eran galería con 0 matches. Usar `--include-gallery` para procesar
  ambas, o `--gallery-only` para exclusivamente galería.
- **Variante whakoom para Español** (va PRIMERO): en `build_variants`, items con
  `language == 'Español'` reciben una variante de texto `site:whakoom.com <serie> <vol>`
  (Google udm=2) insertada al inicio de la lista — antes de yandex-reverse. Motivo:
  whakoom produjo el 100% de los matches ES (8/8) y yandex-reverse 0 (thumbnails de
  listadomanga no indexados por Yandex). Su CDN (i1.whakoom.com/small/) tiene upgrade
  automático a /large/ en sc_validate.py.
- **Memoria de intentos** (`data/cover_search_attempts.jsonl`): una línea JSON por intento
  con `{slug, action, target, attempted_at (ISO), matches (int)}`. Targets cuyo último intento
  tuvo `matches == 0` hace menos de 30 días se omiten automáticamente. Flag `--retry-failed`
  para ignorar la exclusión. El archivo es local (`.gitignore`). El **motor** (`run()` de
  `fetch_better_covers.py`) ahora también escribe una fila por target procesado (mismo formato
  + campo extra `engines: {isbn,lens,text}`); UNA fila por `(slug,action,target)` para no
  romper el dedup del skill (ITEM 6).

### Motor de portadas — gates endurecidos + ledger de rechazos (2026-07-08)

Paquete de fixes al MOTOR (`fetch_better_covers.py`), post-auditoría + red team. Toda la
lógica de identidad/calidad vive en el motor (fuente única); `sc_validate.py` DELEGA.

- **Ledger de rechazos + denylist** (`data/cover_rejections.jsonl`, append-only, local): cada
  vez que `apply_preview()` marca una candidata `rejected`, se apendea `{slug, action, target,
  rejected_url, a_hash (hex del archivo o null si ya no existe), match_dist, ref_pixels,
  new_pixels, page_title, query, reason, rejected_at}` ANTES de borrar el archivo. `sync_cover_preview`
  también lo apendea cuando dropea una entry entera con candidatas rechazadas por slug
  desaparecido. `fetch_better_covers.is_rejected_candidate(slug, url, a_hash_hex, ledger)` es la
  fuente única de la denylist, consultada por `_process_item` (URL antes de descargar, hash
  después) y por `sc_validate` (delegando). **Política EXACTA del veto por hash** (decisión
  post-red-team): match por **URL exacta** (mismo slug + rejected_url) veta SIEMPRE; match por
  **hash** SÓLO si la entrada del ledger tiene un `reason` de **IDENTIDAD** (`otro_tomo`,
  `otra_edicion`, `no_es_la_obra`, `arte_sin_logo`, `auto_revalidation`) **y** aHash dist ≤ 2 —
  NUNCA se veta por hash con `reason` null o de calidad (`mala_calidad`/`otros`), porque toda
  candidata que pasó `_same_cover` comparte aHash con la referencia y ese veto tiraría la
  candidata correcta en mejor resolución. Ver gotcha #131. Tests:
  `tests/test_cover_rejection_ledger.py`.
- **Cierre de bypasses del gate** (`_process_item`): antes, la rama `via=="lens"` corría sólo
  aspect ±0.30 + page-content, y la rama `via=="text"` con `orig_px < 30k` sólo aspect ±0.25 —
  ninguna corría `_same_cover` (falsos positivos 2/3/4/5). Ahora, con **referencia utilizable**
  (bytes descargables + px ≥ 10 000, donde `_same_cover` es fiable): lens y text EXIGEN
  `_same_cover` (lens verificada queda `verified=True` pero `confidence` sigue `low` — no
  auto-aplica). **Sin referencia utilizable**: `verified=False` y se exige TODO — aspect ±0.25
  (unificado) + `candidate_metadata_conflict` sin conflicto + `_validate_page_content` en modo
  **FAIL-CLOSED** (`fail_open=False`: error/timeout/status≠200 ⇒ rechazo, con 1 reintento). El
  gate de blandura `_is_soft_image` corre para toda candidata aceptada (mismo criterio que
  `sc_validate`). La función muerta `_try_candidates` se eliminó. Tests:
  `tests/test_cover_engine_gates.py`.
- **Umbral único de baja calidad (F16)**: `LOW_QUALITY_PX = 90_000` es la constante única en
  `fetch_better_covers`; `DEFAULT_MIN_PIXELS` vale `LOW_QUALITY_PX` (90k, antes 100k) y
  `sync_cover_preview.LOW_QUALITY_PX` / `promote_hires_cover.LOW_PX_THRESHOLD` la IMPORTAN (no
  la redefinen). La banda 90k-100k generaba churn (el motor buscaba candidatas que `sync`
  podaba al instante). Candado en `test_cover_engine_gates.py::test_low_quality_threshold_locked`.
- **Merge anti-carrera en `_write_preview` (F19)**: `run()` reescribe `cover_preview.json`
  completo tras cada item; el mtime-guard de `serve.py` no aplica al motor, así que pisaba
  decisiones que la UI guardó durante la corrida. Ahora `_write_preview(entries, merge=True)`
  relee el disco y funde: (a) candidata en memoria decidida en disco → conserva status +
  reject_reason de disco (nunca la resucita como pending); (b) candidatas/entries de disco que
  el motor no tiene → se conservan. `apply_preview()` escribe con `merge=False` (ya es
  autoritativo sobre el estado final). Misma semántica de preservación que `sc_flush.py`.
- **Cobertura de idiomas (F11)**: `_COVER_TERM`, `_EDITION_HINT`, `_LANG_TO_GL`, el nuevo
  `_LANG_TO_HL` (código de IDIOMA para el `hl` de Serper: `ja/ko/zh-CN/pt-BR…`, distinto del
  `gl` de país) y `_MARKET_PREFERRED_DOMAINS` cubren los 14 idiomas (KO/ZH/TH/VI/PL/TR/CS
  agregados; dominios de mercado KR/PL/CZ/TR + JP ampliado).

### Motor de portadas — footguns cerrados (A3-fbc, auditoría Fable 2026-07-08)

Paquete de fixes de bajo riesgo sobre `fetch_better_covers.py`, posterior al overhaul de arriba.
Ningún cambio toca `_same_cover`, `_is_soft_image` ni los umbrales default (`DEFAULT_MAX_HASH_DIST`,
`LOW_QUALITY_PX`) — el harness `scripts/eval/eval_cover_gate.py` sigue en 0 FP tras el paquete.
Tests: `tests/test_fbc_footguns.py` (+ la suite existente de portadas, sin regresiones).

- **`--apply-preview --dry-run` es un dry-run REAL**: antes la CLI nunca pasaba `dry_run` a
  `apply_preview()` (el flag no tenía ningún efecto), y aun pasado, la implementación vieja
  sólo saltaba el ledger — igual escribía `items.jsonl` y borraba archivos con `unlink()`. Ahora
  `dry_run=True` no muta nada en disco (ni `items.jsonl`, ni imágenes, ni `cover_preview.json`,
  ni el ledger) pero el resumen impreso/retornado sí refleja lo que una corrida real aplicaría
  (mismos contadores `replaced`/`reverted`/`cleaned_old`/`cleaned_new`) — útil como reporte antes
  de aplicar de verdad.
- **Gate fail-closed sin referencia: cerrado el hueco vacuo (#4)**: `_validate_page_content("")`
  aceptaba SIEMPRE sin mirar `fail_open` (el chequeo "obligatorio" en modo fail-closed era en
  realidad un no-op para cualquier vía sin `link` — que era todas menos Lens, porque
  `_search_serper_for_cover` descartaba el campo `link` que Serper sí trae). Ahora: (a)
  `_search_serper_for_cover` captura `link`, así que la vía text también corre la validación real
  cuando la API lo provee; (b) `_validate_page_content("")` devuelve `fail_open` en vez de `True`
  fijo — sin página que validar, el modo fail-closed rechaza. La vía **CDN** (Amazon/PRH/
  OpenLibrary/Google Books) no tiene página que scrapear — su confianza es el match determinístico
  por ISBN — así que `_passes_no_ref_gate(..., require_page_validation=False)` la exceptúa
  explícitamente y conserva su comportamiento documentado sin cambios.
- **`_fetch` requotea URLs no-ASCII (#10)**: `requests.utils.requote_uri()` antes de cada
  descarga (URLs con caracteres thai/chino/etc. sin escapar) + catch de `UnicodeError` además del
  `requests.RequestException` existente. El self-heal de `apply_preview()` (re-descarga de
  archivo faltante) ahora corre dentro de un `try/except` propio.
- **`_validate_page_content` verifica el publisher como señal adicional NO bloqueante (#11)**:
  `pub_keywords` se computaba y nunca se usaba (promesa incumplida en el docstring). Ahora se
  compara contra el texto de la página y se reporta en `--verbose`; un miss NO rechaza (el nombre
  del publisher en la página varía mucho — imprint/sello local/nombre corto — así que no es una
  señal confiable por sí sola, a diferencia del match de serie que sí bloquea).
- **fsync antes del `replace()` atómico (#12)**: `_atomic_write` (items.jsonl) y `_write_preview`
  (cover_preview.json) ahora hacen `f.flush(); os.fsync(f.fileno())` antes del `tmp.replace()`,
  igual que la vía canónica `append_jsonl`. Sin esto, un crash justo después del write podía
  promover un tmp truncado/vacío.
- **Errores por item visibles sin `--verbose` (#15)**: `run()` imprime `⚠ WARN [slug]: Tipo: msg`
  por cada excepción de item SIEMPRE (antes: solo con `-v`, una corrida silenciosa podía terminar
  con "Errores: 40" sin ninguna pista). Con `--verbose` además imprime el traceback completo.
- **Código muerto eliminado (#16, grep-verificado)**: `_text_matches_item` (sin ningún caller);
  el cómputo local de `edition_hint`/`ed_slug`/`ed_hints` dentro de `_build_search_query` (se
  calculaba y nunca se usaba en el query — el título ya trae el tipo de edición cuando
  corresponde); la condición `f"{e}?" in path` en `_search_serper_lens` (`urlparse().path` NUNCA
  contiene `?`, la query queda en `.query` — condición imposible). **NO se tocaron** `_EDITION_HINT`
  ni `_edition_slug` como símbolos del módulo — el skill `watch-search-covers` los importa
  directo (`fbc._EDITION_HINT`, `fbc._edition_slug`) para su propio armado de queries.
- **Portada leída UNA vez por item (#17)**: antes `_get_current_pixels`/`_get_current_bytes`/
  `_is_upscaled` releían y re-parseaban el MISMO archivo de portada hasta 3-4 veces por item (en
  el filtro de candidatos de `run()`, y de nuevo en `_process_item`). Ahora `_get_current_pixels`
  y `_is_upscaled` aceptan un parámetro opcional `_bytes` con los bytes ya leídos; `_process_item`
  y el filtro `_is_candidate` de `run()` leen una sola vez y reusan.
- **`--limit` refleja el consumo real de API (#18)**: un item con `isbn` no-vacío pero de longitud
  inválida (ni 10 dígitos, ni 13 con prefijo 978/979) no produce NINGUNA candidata CDN — cae igual
  a Serper/Tavily (créditos reales) — pero antes `--limit` lo contaba como "gratis" (`bool(isbn)`
  alcanzaba). El nuevo helper `_isbn_len_ok()` (misma validación de longitud/prefijo que
  `_candidates_from_isbn*`, sin checksum) reemplaza el `bool(isbn)` en el contador de `--limit` y
  en el desglose `con ISBN / sin ISBN` del resumen.

**Invariantes**:
- Candidatas: `confidence: "low"`, `status: "pending"` — sin excepción.
- Dos scripts son **permanentes** (nunca borrar ni reimplementar inline):
  - `scripts/retrofit/sc_validate.py` (tests: `tests/test_sc_validate.py`) — validación de
    identidad de imagen; la copia embebida que había drifteó de producción y causó falsos
    positivos pre-2026-06-11.
  - `scripts/retrofit/sc_flush.py` (tests: `tests/test_sc_flush.py`) — flush self-healing al
    `cover_preview.json`; el código inline que lo reemplazó reconstruyó dicts a mano y perdió
    el campo `new_image` en 8 candidatas (2026-06-11). El script rechaza con exit 1 cualquier
    candidata sin `new_image` o `new_url` — guarda estructural contra esa regresión.
  Las candidatas se pasan EXACTAMENTE como las devolvió `sc_validate.py`, sin modificar nada.
- `cover-preview.html` muestra un badge **✓ verificada** (verde) cuando la candidata pasó
  `_same_cover` contra la imagen actual, o **⚠ sin verificar** (ámbar) cuando no fue posible
  verificar (p.ej. items sin imagen con `--include-no-image`). El badge aparece tanto en la
  card compacta como en el modal de comparación.
- **Chips de motivo de rechazo** (`otro_tomo`/`otra_edicion`/`arte_sin_logo`/`no_es_la_obra`/
  `mala_calidad`/`otros…`, opcionales, 1 clic tras rechazar): detalle completo en
  [dashboard.md § "Cover-preview — chips de motivo de rechazo"](dashboard.md#cover-preview--chips-de-motivo-de-rechazo-2026-07-08-sin-fricción).
  El motivo alimenta el veto por hash del ledger de rechazos (arriba, "Ledger de rechazos +
  denylist").
- **Badge "aprobadas SIN APLICAR" (P24, 2026-07-07)**: aprobar una candidata (👍) y
  aplicarla a `items.jsonl` son pasos DESACOPLADOS (guardar `status=approved` no toca el
  catálogo; sólo `POST /api/apply-cover-preview` lo hace). Si quedan candidatas
  `approved` sin aplicar, `cover-preview.html` muestra un banner verde prominente al
  cargar con el conteo y un botón "✓ Aplicar ahora" — el contador (`approved_unapplied`)
  es AUTORITATIVO server-side, viene en `GET /api/cover-preview`. Detalle en
  [dashboard.md](dashboard.md).
- **NUNCA** modifica `items.jsonl`. La aprobación es manual vía `cover-preview.html`.
- Flags: `--limit N`, `--slug SLUG`, `--gallery-only`, `--include-gallery`, `--include-no-image`,
  `--retry-failed`, `--query-extra "texto"`.
- **Guard de concurrencia (2026-06-11, endurecido 2026-06-12)**: el frontend envía
  `expected_mtime` (token STRING opaco — st_mtime_ns excede 2^53 y como Number daba 409
  espurio en cada save, gotcha #79) en cada save y en el apply; el servidor rechaza con 409
  si el archivo cambió desde la carga. Ya no es crítico cerrar la pestaña antes de correr el
  skill — si la pestaña intenta guardar encima, el 409 la fuerza a recargar la cola
  actualizada sin pisar los cambios del servidor. Detalle en
  [dashboard.md](dashboard.md) § "guard de concurrencia optimista".
- **apply_preview con archivo faltante**: si una candidata `approved` referencia un `new_image`
  que ya no existe en disco, `apply_preview` la omite (no toca `items.jsonl`), la conserva en el
  preview y reporta `skipped_missing_file` en el summary.
- **Sincronización al cargar (2026-06-11)**: `GET /api/cover-preview` llama
  `scripts/retrofit/sync_cover_preview.py::sync_preview()` antes de responder. Poda
  candidatas `pending` cuya premisa ya no existe (portada ya ≥ 90 000 px, foto de galería
  target desaparecida o ya ok, new_url igual a la portada actual) y elimina entries cuyo slug
  ya no existe en el catálogo o que quedaron sin candidatas. Las candidatas `approved`/`rejected`
  nunca se tocan. **Además recomputa `new_pixels` (y `old_pixels`) desde el archivo REAL en
  disco** (2026-06-16): como el ingreso normaliza a AVIF ≤1600px, el panel debe mostrar la
  resolución que QUEDA guardada, no la del original pre-resize (que inflaba el ratio xN). El
  skill (`sc_validate`) y el script (`fetch_better_covers`) ya registran el px del archivo
  normalizado al crear la candidata; el sync auto-corrige las que quedaron con valor viejo.
  La detección de "hubo cambios" compara `synced != preview` (2026-07-08, hallazgo #4 — antes
  sólo miraba counters de poda, así que un refresh de Regla 2 sin ninguna poda NUNCA se
  persistía). Si hubo cambios, persiste el JSON atómicamente (con `backup_and_rotate` antes de
  escribir, hallazgo #5) antes de responder. El CLI manual:
  `.venv/bin/python scripts/retrofit/sync_cover_preview.py [--dry-run]`.
- **Guard de catálogo sano (2026-07-08, hallazgo #1, ALTA)**: tanto el CLI como el GET (que
  persiste) corren `sync_cover_preview.catalog_is_sane(preview, items_by_slug,
  malformed_lines)` ANTES de sincronizar. Sin esto, un `items.jsonl` ausente/truncado/con
  líneas que no parsean hacía que CADA slug de la cola se viera como "item borrado" (Regla 1) —
  un solo GET podía vaciar `cover_preview.json` entero (~160 entries) en un momento
  equivocado. Aborta (CLI, exit 1) o degrada a solo-lectura sin persistir nada (GET: sirve la
  cola tal cual está en disco + loguea `[serve][WARN]`) si: `items_by_slug` sale vacío con la
  cola no vacía, >20% de los slugs de la cola no matchean ningún item, o
  `_load_items_by_slug` contó ≥1 línea con `JSONDecodeError` (antes se tragaban en silencio).
- **GC de candidatas huérfanas (2026-07-08, hallazgo #14)**: cuando `sync_preview()` poda una
  candidata o dropea una entry entera, el archivo `new_image` descargado queda huérfano en
  `data/images/` — nada más lo GC-eaba. Ahora se borra automáticamente SI (y sólo si) nada
  más lo referencia: ni `images[].local` **ni `sources[].image_local`** de ningún item real
  (la ref legacy per-fuente, ~5.9k items la tienen poblada — misma protección que el GC de
  mirror_images), ni ninguna otra entry/candidata sobreviviente (el espejo de candidatas
  comparte el MISMO directorio flat que el espejo de portadas de items, así que un borrado
  ciego por nombre podía arrancarle la portada a un item real). Gatea con el mismo flag que
  el ledger (`write_ledger`) — nunca corre en un probe puro (`revalidate_cover_preview.py`
  lo llama con `write_ledger=False`) ni en `--dry-run`.

### Re-validación OFFLINE de la cola (`revalidate_cover_preview.py`, 2026-07-08)

Retrofit puntual para re-validar candidatas `pending` que vienen de una versión VIEJA del
skill (la copia embebida que drifteó, causa de los falsos positivos pre-2026-06-11): traen
`match_dist: null` y NUNCA pasaron por el gate endurecido. Como la referencia (`old_image`) y
la candidata (`new_image`) ya están espejadas en `data/images/`, se re-validan **sin red**.

- **Delegación pura, cero lógica copiada**: la identidad se decide con `fetch_better_covers._same_cover`
  + `_is_soft_image` (fuente única); la detección de candidatas MOOT delega en
  `sync_cover_preview.sync_preview()` (item borrado, portada vigente ya buena, target ausente/ok,
  ya-es-portada) — esas se dejan intactas para que `sync` las limpie. `revalidate_preview()` es una
  función PURA importable (no escribe archivos ni el ledger).
- **Por candidata pending** (que no tenga ya la clave `verified`): (a) **sin referencia utilizable**
  (`old_image` ausente o < 10 000 px) → NO se auto-rechaza, sólo `verified: false` (queda para review
  humano); (b) **PASA** `_same_cover` ∧ ¬`_is_soft_image` → puebla `match_dist` (aHash Hamming, igual
  que `sc_validate`), `ref_pixels`, `verified: true`, sigue `pending`; (c) **FALLA** → `status: rejected`
  + `reject_reason: "auto_revalidation"` (motivo de IDENTIDAD → habilita veto por hash en el ledger).
- **El ledger NO se escribe acá** (escritor único = `apply_preview`/`sync`): la candidata rechazada se
  ledgerea cuando el owner la aplica. Idempotente: status ≠ pending o pending-con-`verified` no se
  reprocesan → correr 2× = JSON byte-idéntico. Backup + escritura atómica.
- **Píxeles de referencia vía PIL** (reusa `sync_cover_preview._get_local_pixels`). Nota
  (2026-07-08, hallazgo #11): un comentario viejo acá y en el código decía que el parser de
  bytes del motor (`_get_pixels_from_bytes`) NO cubre AVIF — eso dejó de ser cierto con el
  fix de la gotcha #132 (`_get_dims_from_bytes` ya tiene fallback PIL para AVIF/GIF/WebP
  lossless). Se sigue delegando en `_get_local_pixels` de todos modos porque acá partimos de
  un `Path`, no de bytes ya leídos — evita una lectura+decode redundante, no por la limitación
  de AVIF que ya no existe.
- CLI: `--dry-run` (default, reporta desglose por categoría + distribución de `match_dist`) / `--apply`.
  Tests: `tests/test_revalidate_cover_preview.py` (pasa/falla/sin-ref/moot/idempotencia/no-ledger).

### Harness de evaluación del gate (`scripts/eval/eval_cover_gate.py`, 2026-07-08)

Harness OFFLINE reproducible que mide el gate de identidad de portadas sobre una muestra
etiquetada y reporta la matriz de errores (FP/FN) por categoría de la taxonomía de fallas del
owner (2 otro tomo · 3 otra edición/editorial · 4 foto random · 5 parecida al tomo 1/plantilla ·
6 ilustración sin trade dress). Sirve de **candado de regresión**: si alguien relaja
`_same_cover`/`_is_soft_image`, el eval lo detecta.

- **Qué mide**: dos políticas sobre cada par (referencia, candidata):
  - `old_policy` — aspect-ratio-only (±0.30): lo que hacía el path lens/text ANTES del hardening
    2026-07-08 (sin verificación de identidad; causa raíz #1 de fotos equivocadas).
  - `new_policy` — **delegación pura** al motor: `_same_cover` completo + `_is_soft_image`
    (cero lógica copiada; importa las funciones reales de `fetch_better_covers`). Referencia
    < 10 000 px → `no_reference` (modela `usable_ref` de `_process_item`; el px se cuenta vía
    `_get_dims_from_bytes` con fallback PIL porque `_get_pixels_from_bytes` no cubre AVIF).
- **Muestra**: `scripts/eval/cover_gate_sample.json` (manifest chico versionable; las imágenes
  reales referencian `data/images/` por path, NO se copian binarios) — 10 positivos reales
  (verified, misma portada mejor resolución, `match_dist` 0-5) + 12 negativos reales
  (auto-rechazados en la re-validación, clasificados en la taxonomía) — MÁS 6 trampas
  **sintéticas** generadas con PIL al vuelo en un tmpdir (deterministas, seed fijo).
- **`expected_fail`** = limitación conocida y ACEPTADA, no cuenta como falla del harness:
  (a) *arte-sin-logo* (cat 6) — candidata = ilustración sin trade dress; la ilustración domina,
  los hashes colisionan y el gate la ACEPTA (el red team rechazó gates automáticos para este
  caso → cubierto por review humano + denylist); (f) *crop ±3%* — el gate estricto la rechaza
  (NCC < 0.90), FN documentado (precisión > recall).
- **Resultado** (28 casos): `old_policy` acepta los 14 negativos (FP=14) — ESO era el bug;
  `new_policy` = **0 FP y 0 FN reales**, con los 2 únicos desvíos = los `expected_fail`
  sintéticos. Determinístico: correr 2× → JSON idéntico.
- CLI: `--json`, `--synthetic-only` (no requiere `data/images/`), `--no-synthetic`.
  Test: `tests/test_eval_cover_gate.py` (corre sólo las sintéticas; candado de regresión).

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

