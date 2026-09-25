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
  - **`normalize_image_url` preserva params de IDENTIDAD, solo filtra los de resize
    (2026-07-08, hallazgo #2, ALTA, gotcha #137)**: el patrón 1 (Magento-style query
    params: `?width=300&height=300&quality=80…`) borraba la query COMPLETA en vez de
    filtrar solo `_CDN_RESIZE_PARAMS`. Dos imágenes DISTINTAS con un param de identidad
    (`?id=123&width=300` vs `?id=456&width=300`) colapsaban al mismo `image_stem` →
    `existing_local_image` devolvía la portada del PRIMER item para el segundo
    (cross-cover silencioso). Fix: reconstruye la query quedándose sólo con los pares
    que NO están en `_CDN_RESIZE_PARAMS` (idempotente: una 2ª pasada ya no tiene esos
    keys, así que el `if` de detección da False). Análisis de impacto sobre el corpus
    real (2026-07-08): de 19 688 URLs únicas en `images[].url`, 164 matcheaban el
    patrón 1, 151 cambian de stem con el fix, y **67 ya tenían un archivo en disco bajo
    el stem VIEJO** — por encima del umbral de "impacto material" (>50), así que
    `existing_local_image` prueba el stem correcto primero y cae al stem LEGACY
    (`_legacy_image_stem`, replica el comportamiento pre-fix) si no encuentra nada — los
    67 archivos existentes se siguen sirviendo sin re-descarga; sólo las descargas
    NUEVAS usan el stem corregido.
- La `url` remota de cada entry queda como provenance + fallback (espejo falla → url remota → 📚).
- On por defecto en todo scrape; `--skip-image-download` lo desactiva. Primitivas en
  `image_store.py` (incluye los helpers `cover_url`/`cover_local`/`set_cover`); orquestado
  por `mirror_candidate_images()`.
- **Idempotente** (nombre determinístico). **Validación magic bytes** (descarta HTML de
  error servido como imagen; la extensión sale de los bytes). El `local` de `images[0]` es
  sticky vía el union-merge de `images[]` en `append_jsonl` (gotcha #25).
- **Cota anti-decompression-bomb (2026-07-08, hallazgo #16)**: `image_store.
  MAX_IMAGE_PIXELS_CAP` (80 MP) reemplaza `Image.MAX_IMAGE_PIXELS = None` en los 3
  sitios donde el módulo abre bytes con PIL (`placeholder_reason`, `normalize_image`
  ×2) — `None` desactivaba por completo el guard de PIL contra un PNG/JPEG adversarial
  de pocos KB que decodifica a gigapíxeles. 80 MP cubre con margen cualquier escaneo/
  portada legítima del corpus.
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
  en disco, no muta `images[]` de ningún item. **Flush incremental cada 50** (no 200 —
  2026-07-08, hallazgo #15): alineado a la convención dura de `docs/reference/conventions.md`
  § "Flush incremental"; idempotente de todos modos, así que el cambio es de robustez ante
  cancelación, no de comportamiento.
- **OLA 1 de depuración de imágenes (2026-09-01, gotcha #158)**: `mirror_images.py` ganó
  cuatro capacidades nuevas, todas en el mismo script (nada reimplementado en paralelo):
  1. **Normaliza el esquema `local`** antes de backfillear
     (`_normalize_missing_local_keys`): toda entry de `images[]` con `url` pasa a tener
     la key `local` presente (`""` si no hay espejo), en vez de a veces faltar la key
     por completo — 1531 entries del corpus tenían la key ausente (`.get("local")` daba
     `None`), inconsistentes con el resto (`cover_local`/`set_cover` ya devuelven/escriben
     `""` por default). Corre siempre, incluso en `--dry-run` (sólo cuenta).
  2. **Cortesía por-host**: usa el mismo `manga_watch.ThrottleRegistry` que el scraper
     principal (`--per-host-limit`, default 2) para no saturar un host chico con pocas
     portadas pendientes concentradas (ej. 16 en manga-sanctuary) bajo `--workers` alto.
  3. **No propaga un placeholder como si fuera portada**: antes de descargar, saltea
     URLs ya fichadas por `image_store.known_placeholder_url_reason()`; después de
     descargar, corre `image_store.placeholder_reason()` sobre el archivo recién
     guardado — si es un placeholder (estructural o por firma) NO se asigna como
     `local` del consumer (el archivo queda huérfano; el GC de la misma corrida lo
     manda a cuarentena si no se pasó `--no-gc`). Detectó un caso real el 2026-09-01:
     un ícono de UI de 8×9 px extraído como portada por el parser genérico de Aladin
     (`tiny:8x9` — ver `docs/scraper/sources/kr-aladin.md`).
  4. **`--skip-hosts host1,host2`**: excluye hosts conocidos-bloqueados ANTES de tocar
     la red (no cuentan como "fallidos", se reportan aparte). Usado para excluir
     `mangavariant.com` (240/307 portadas pendientes del corpus, 78%) — el challenge
     sgcaptcha del sitio bloquea también sus imágenes self-hosteadas, no sólo las
     páginas HTML (extiende gotcha #152; detalle en
     `docs/scraper/sources/mangavariant.md`).
  El reporte final también bucketiza fallos por razón (`_classify_failure`: HTTP status,
  timeout, connection error) y mide el área en píxeles de cada portada mirroreada con
  éxito contra el umbral de 90 000 px (`fetch_better_covers._get_pixels_from_bytes`,
  fuente única — nada reimplementado). Corrida real de esta ola (excluyendo
  mangavariant): de 67 portadas + 439 galería intentadas (506 objetivos, 493 URLs
  únicas), 425 entries se mirrorearon con éxito (413 URLs únicas: 128 ≥ 90 000 px, 285
  por debajo), 77 URLs fallaron (44 `http_404`, 14 `not_image_or_too_large`, 11
  `http_500`, 6 `http_400`, 1 `http_403`, 1 `http_503`) y 3 URLs descargaron un
  placeholder. Idempotente: dos corridas posteriores sobre el mismo corpus con los
  mismos flags dejaron `items.jsonl` con hash `sha256` idéntico.

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
- **NUNCA toca placeholders** (gotcha #104): si `placeholder_reason(body) != ""` devuelve los
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
- **Buscalibre** (`images.cdnN.buscalibre.com`): reescribe el segmento `fit-in/<W>x<H>/` a
  `fit-in/1200x1200/` — **NO se quita el segmento entero** (gotcha #167, 2026-09-01, corregido
  tras la curación del 2026-09-01: quitarlo del todo NO devuelve el original en máxima
  resolución, el CDN sirve un tamaño "base" intermedio. Verificado con requests reales sobre la
  misma imagen: `fit-in/360x360/` → 256×360 = 92 160 px; segmento quitado → 384×540 = 207 360 px;
  `fit-in/1200x1200/` → 853×1200 = **1 023 600 px**, 5× más que quitar el segmento). No re-capa
  si el fit-in pedido ya es ≥1200 en ambas dimensiones (no downgrade).
- **Cultura** (`cdn.cultura.com`): quita segmento `cdn-cgi/image/width=<N>/` (Cloudflare Polish) → hasta 2×.
- **Whakoom** (`i1.whakoom.com`): `/small/` o `/thumb/` o `/medium/` → `/large/` → 3×.
- **Magento cache path** (`/media/catalog/product/cache/<hex>/`): quita el segmento → acceso a la imagen original. **⚠️ Requiere validación same_cover** (bdfugue y similares ~20% devuelven imagen distinta); el script la aplica automáticamente cuando está disponible PIL.
- **Aladin** (`image.aladin.co.kr`, gotcha #177, 2026-09-02): `cover<N>/<archivo>` con `N<500` → `cover500/<archivo>` (mismo archivo, carpeta de tamaño mayor en la misma ruta — no re-capa si ya es ≥500). Verificado en vivo antes de aplicar: `cover800`/`1000`/`1200` dan 404 (`cover500` es el techo real del CDN); `coversum`/`letslook` son variantes MÁS chicas o de archivo DISTINTO, no se usan como target. Corrida real sobre el corpus (`--host aladin.co.kr`): 371 URLs candidatas (`cover150`×90 + `cover200`×281) → **297 mejoradas** (mediana ×6.25 píxeles, rango ×1.77–×16), 54 sin mejora real (ya en el techo del CDN, o portada previamente algoritmo-upscaleada con más píxeles sintéticos que el `cover500` real — el gate no downgradea). Detalle y números completos en `docs/scraper/sources/kr-aladin.md` § "Upgrade determinista aplicado".
- **Rakuten Books familia r10s.jp** (`tshop.r10s.jp`/`shop.r10s.jp`, gotcha #180, 2026-09-02): `?downsize=<N>:*` (y `?fitin=…&composite-to=…`) → quita la query ENTERA, no un `downsize=N` más grande. Distinto del host `thumbnail.image.rakuten.co.jp` de arriba (`?_ex=`, mismo mecanismo, CDN separado de la misma tienda). Verificado en vivo: `downsize=130:*` → 130×184; `downsize=1000:*` → 844×1200 (= nativa, no upscala); sin query (sigue el 302 `tshop`→`shop`) → 844×1200; `downsize=9999:*` → HTTP 400 (el param SÍ tiene techo, evitado quitando la query entera). Guard anti-`.gif`: nunca reescribe la tarjeta de título placeholder de gotcha #171/#176 (`image_store.known_placeholder_url_reason()`). Corrida real (`--host r10s.jp`): 176 URLs candidatas (84 aprobados salteados) → **145 mejoradas** (mediana ×5.34, rango ×1.16–×85.21), 22 sin mejora — todas con espejo local ya mejor que la nativa de Rakuten (upgrade previo vía `watch-search-covers`), no un límite del patrón. Detalle en `docs/scraper/sources/jp-rakuten-books.md`.

Patrones **no agregados** (verificados como no viables): Amazon (los modificadores no controlan resolución), Manga-Sanctuary `/objet/300/` (es el máximo del servidor).

El download pasa `referer=<url del item>` para evitar 403 de CDNs con anti-hotlink. La comparación de píxeles (umbral `--min-gain 0.10`) evita reemplazar por la misma imagen o peor.

**`--host <substring>`** (2026-09-02, gotcha #177): acota los targets por substring de
netloc (case-insensitive) — ej. `--host aladin.co.kr` corre/mide sólo ese CDN sin tocar
los demás patrones/hosts soportados. Útil para aplicar un patrón nuevo de forma acotada
antes de confiar en él sobre todo el corpus.

**Guard `approved_at` (2026-07-07, gotcha #121)**: por defecto saltea items aprobados
(golden records) — el script reemplaza `url`/`local` de una entry existente sin cola
de revisión. `--include-approved` fuerza. Mismo guard homogéneo en los 13 scripts de
imagen/agrupación de listadomanga (ver `docs/reference/conventions.md`).

**Dedup post-upgrade de `images[]` (2026-09-02, gotcha #181).** Reescribir cada entry
de forma aislada puede colapsar dos entries del MISMO item a la MISMA url/local final
si, ANTES del upgrade, ya apuntaban al mismo archivo bajo dos tamaños de CDN distintos
(caso real: 151 items KR-Aladin con `images[0]` ya en `cover500/` por otra vía y una
entry de galería en `cover150/`/`cover200/` del MISMO archivo). `dedupe_item_images()`
corre por-item apenas `_apply_upgrade` toca una entry — clave canónica `_img_stem(url)`
(fuente única de `manga_watch`), con fallback a `local` idéntico y, si ninguno de los
dos decide, sha256 de los bytes del archivo `local` (mismo contenido bajo stem/local
distintos). Nunca reordena `images[0]` ni vacía `images[]`; el duplicado eliminado
dona `kind`/`description` al sobreviviente cuando éste no los tenía (mismo patrón
sticky que `_apply_improvement`, gotcha #164). Detalle completo, la reparación del
dato (156 items/161 entradas) y por qué no bastaba con `dedup_carousel_images.py
--redteam-auto` (detecta MÁS que esto — pares `dhash_rescale` ajenos al bug) en
gotcha #181.

**El gate de píxeles delega en la fuente única de dimensiones (2026-07-08, hallazgo #1,
ALTA, gotcha #124).** `_pixels()` tenía su PROPIO 3er parser binario de dimensiones
(`_image_dimensions_from_bytes`) sin rama AVIF ni fallback PIL — la misma clase de bug
ya cerrada en `upscale_images.py` y `fetch_better_covers.py`, pero no acá. Como el
espejo local está ~100% AVIF, el gate `--min-gain` caía SIEMPRE al proxy de tamaño de
ARCHIVO (`len(data)`), que para AVIF comprimido no guarda relación con los píxeles
reales: mejoras legítimas se rechazaban y reemplazos sin ganancia real se aceptaban.
Fix: `_pixels()` delega en `fetch_better_covers._get_pixels_from_bytes` (que a su vez
cae a `_get_dims_from_bytes` con fallback PIL para AVIF/GIF/WebP-lossless, gotcha
#132) — el 3er y último parser binario duplicado del repo queda eliminado; fallback a
`len(data)` sólo si ni siquiera PIL puede leer el archivo (comportamiento degradado
preexistente, sin cambios).

**`_try_upgrade` es fail-closed sin espejo local de referencia (2026-07-08, hallazgo
#4, gotcha #131).** El patrón Magento cache path (`needs_same_cover_validation`) exige
validar identidad porque ~20% de esos CDNs devuelven una imagen DISTINTA. Antes, si el
`old_local` de la entry estaba vacío (nunca se espejó localmente), el bloque entero de
validación se saltaba y el script aceptaba la nueva URL a ciegas; y si `fetch_better_
covers`/PIL no estaban disponibles, el `except (ImportError, Exception): pass` también
aceptaba a ciegas (fail-open, contradiciendo la política fail-closed de la gotcha
#131 — "cualquier capa incomputable ⇒ rechazo"). Ahora: sin referencia local utilizable
Y sin poder validar `_same_cover`, el resultado es rechazo, no aceptación.

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
al revés de lo que hace falta. Corregido a 0.06 para matchear de verdad.

**Centralización completada (2026-07-08, hallazgo #12)**: `THUMB_ASPECT_TOL` vive ahora en
`image_store.THUMB_ASPECT_TOL` (0.06) — fuente ÚNICA importada por este script y por
`dedup_carousel_images.py`, así que un futuro ajuste del umbral no puede volver a driftear
entre los dos. `THUMB_MAX_SIDE`/`THUMB_HAMMING` siguen duplicados (menos sensibles al drift:
sólo definen qué par se considera "thumbnail↔full" antes de aplicar el umbral ya
centralizado) — no forman parte de este paquete de fixes.

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

**`--delete-original` (default ON) protege refs fuera de `images[]` (2026-07-08,
hallazgo #3).** `_collect_targets` agrupa refs sólo vía `images[i].local` (que sí se
actualiza al `local` nuevo); pero `sources[].image_local` (ref legacy per-fuente, no
la actualiza este script) y `data/cover_preview.json` (`old_image`/
`candidates[].new_image`/`current_images[].local` — la cola de revisión de portadas)
pueden seguir apuntando al archivo VIEJO. Antes se borraba igual (`src_path.unlink()`
sin chequear estas dos fuentes) → refs colgantes. Fix: `_protected_locals(items,
preview_path)` (unión de `_sources_image_locals` + `_cover_preview_locals`) se computa
una vez antes del loop; si el `local` viejo está protegido, el archivo se CONSERVA (se
reporta como `kept_protected` en el resumen) en vez de borrarse. Tests:
`tests/test_images_pkg.py`.

**El binario externo NO acepta AVIF como input — 100% de fallo silencioso hasta el fix
(gotcha #146, 2026-08-23).** waifu2x-ncnn-vulkan/realesrgan-ncnn-vulkan sólo leen
`jpg/png/webp` (su propio `--help` lo dice); el script le pasaba el archivo del espejo
DIRECTO a `subprocess.run` como `-i`, y el espejo es 100% AVIF desde la estandarización
2026-06-15 — el binario no podía decodificar nada, devolvía returncode≠0 y
`_upscale_file` lo reportaba "FALLÓ" sin ninguna traza de la causa real. Se detectó en
la corrida post-scrape 2026-08-23 (3159/3159 candidatos fallando). Fix:
`_decodable_upscaler_input()` detecta por magic bytes si el archivo no es jpg/png/webp
y, de ser así, lo decodifica con PIL (mismo patrón lazy-import que `_pixels_from_bytes`)
a un PNG temporal en `images_dir`, que es lo que se le pasa al binario; el temporal se
borra tras cada intento. Re-corrida post-fix: 3145/3145 upscaleadas, 0 errores. Moraleja
para cualquier script nuevo que invoque un binario EXTERNO sobre un archivo del espejo:
verificar los formatos que acepta ANTES de asumir que el espejo sigue siendo JPEG/PNG
genérico — desde 2026-06-15 es AVIF por decisión de diseño.

## Dedup de portada en el carrusel — `dedup_carousel_images.py`

Cuando un item termina con la MISMA portada en dos resoluciones en `images[]` (ej.
la cover hi-res del publisher + la misma como thumbnail de baja calidad de
listadomanga), `scripts/retrofit/dedup_carousel_images.py` la deduplica por hash
perceptual (aHash 8×8, Hamming ≤6 + aspect ±12%), conservando la de MAYOR
resolución. Solo toca `kind=gallery` (los `extra` —cofres/tomos del box— son
contenido curado y nunca se tocan) y exige dims válidas. Por defecto saltea items
aprobados (`--include-approved` fuerza) — el dedup puede reordenar `images[0]` (la
portada) de un golden record. Ver retrofit README.

**Umbral thumbnail↔full centralizado (2026-07-08, hallazgo #12)**:
`THUMB_ASPECT_TOL` (0.06) se importa de `image_store.THUMB_ASPECT_TOL` — fuente
única compartida con `promote_hires_cover.py` (antes duplicado en los dos scripts,
sin drift entre ellos porque ya se habían alineado a mano, pero sin protección contra
un futuro drift).

**Un `extra` no puede ascender a portada cuando la portada cae como dup (2026-07-08,
hallazgo #12)**: cuando `images[0]` (la portada) cae como duplicado de menor
resolución, el código viejo asumía que `new_imgs[0]` (el primer sobreviviente en
orden original tras filtrar) era el hi-res que ganó la comparación — pero si un
`extra` (bonus que viene CON el producto: postal, shikishi) estaba ubicado ENTRE la
portada descartada y el hi-res sobreviviente, ese `extra` terminaba en `images[0]` por
puro accidente de posición (mismo error de clase que `sync_cover_images._fix_bad_cover`
promoviendo un extra, ver más abajo). Fix: si la portada cayó, se busca explícitamente
el primer sobreviviente `kind=="gallery"` y se lo mueve a la posición 0 — un `extra`
nunca es dedupable (ver `_dedupable`), así que si la portada cayó SIEMPRE hay otro
`gallery` que le ganó la comparación.

**Convenciones duras endurecidas (2026-07-08, hallazgo #5)**: (a) `backup_and_rotate`
en vez de un slot fijo `.pre-dedup-bak` (se pisaba en cada corrida — el script corre en
cada `scrape_full.sh`, fase `[4h]`); (b) flush incremental cada 50 items con cambios en
vez de un write único al final (el loop baja imágenes de red por cada par a comparar —
un crash a mitad de una corrida sobre `--all` perdía TODO); (c) `make_session` de
`manga_watch.py` (retry + headers consistentes) en vez de un UA propio
(`"Mozilla/5.0 (dedup)"` — fuentes como Manga-Sanctuary sirven 404 a UAs desconocidos,
así que el dedup se omitía en silencio para esas fotos); (d) `_bytes_cache` con cota
LRU (200 entradas) — sin tope, una corrida sobre `--all` podía acumular gigabytes en
memoria; (e) `json.dumps(..., sort_keys=True)` + `encoding="utf-8"` explícito en la
lectura (rompía la idempotencia byte-idéntica del corpus). Tests:
`tests/test_dedup_carousel_images.py`.

### `--redteam-auto` — regla de dedup validada por red-team visual (OLA 2, 2026-09-01)

La heurística histórica de arriba (aHash Hamming≤6, aspect±12%, más el relax
thumbnail↔full) sigue siendo la que corre en el pipeline canónico
(`scrape_full.sh` fase `[4h]`, sin cambios). Un red-team visual sobre 37 pares
reales encontró que ese margen es más ancho de lo seguro para un borrado
100% automático: el falso positivo típico son DOS FOTOS DISTINTAS del mismo
producto con dimensiones **exactamente iguales** (shikishi de colores
distintos, caja llena vs vacía) — la heurística vieja no exige que las
dimensiones sean distintas, así que un par así puede colar si el aHash cae
por casualidad dentro del margen.

`--redteam-auto` es un modo AISLADO del mismo script (mismo archivo, mismo
guard `approved_at`/backup/flush — no un script hermano, ver justificación
en el propio código) que implementa la regla validada, exactamente así, sin
relajarla:

- **AUTO** (se borra la de menor resolución) sólo si **(a)** SHA-256 de bytes
  idéntico, **o (b)** dHash Hamming ≤ 2 **y** dimensiones **DISTINTAS**
  **y** `|aspect1−aspect2|/aspect1 ≤ 2%`. La condición "dimensiones
  distintas" es DURA, no cosmética: dos fotos DISTINTAS del mismo producto
  casi siempre comparten resolución (misma cámara/escaneo); la MISMA foto en
  dos resoluciones, por definición, no.
- **DUDOSO** (se reporta, NUNCA se toca): pares dentro de la banda de interés
  (dHash ≤ 8, el mismo tope que usa `_same_cover` para identidad de
  portadas) que no cumplen (b) — típicamente dimensiones iguales, o dHash en
  la banda 3-8. Se evalúan sobre los SOBREVIVIENTES tras el paso AUTO (si una
  imagen ya se auto-eliminó, un dudoso que la involucraba deja de existir en
  la galería final).
- **pHash de la librería `imagehash`** (instalada como dependencia nueva,
  `requirements.txt`) se computa SOLO para los pares dudosos, como señal
  ADICIONAL informativa en el reporte — nunca decide el criterio auto.
- Reporta los pares dudosos en `data/diagnostics/dedup-wave2-dudosos.json`
  (gitignored, sólo evidencia — **no** es en sí misma una cola de aprobación:
  la resolución vive en `cover_preview.json` vía la acción `remove_image`, ver
  subsección siguiente). El owner decide qué hacer con cada par dudoso desde
  el dashboard.
- Escanea TODO el corpus (ignora el filtro `--all`/listadomanga de la
  heurística vieja) — la regla es genérica, no específica de una fuente.
  Label de backup propio: `wave2-dedup` (slot fijo `.pre-wave2-dedup-bak`,
  igual convención que el resto).
- Tests: `tests/test_dedup_carousel_images.py` (clasificador puro con
  fingerprints sintéticos + end-to-end con imágenes PIL reales: SHA-256
  idéntico, rescale 2× con re-promoción de portada, dudoso por dimensiones
  iguales, label de backup, idempotencia).

**Corrida real sobre el corpus (2026-09-01, post-ola-1, 14305 items, 3646 con
≥2 imágenes, 84 aprobados saltados)**: 321 items con auto-dup, **471 imágenes
auto-eliminadas** (mezcla de `sha256` exacto y `dhash_rescale`), **0
portadas** cayeron como duplicado de menor resolución (0 re-promociones —
los duplicados detectados por esta corrida estaban todos en `images[1+]`, no
en `images[0]`), y **327 pares dudosos** reportados sin tocar. Verificación:
`pytest` completo 2360 verdes, `filter_non_manga.py --dry-run` 0 rechazos,
`validate_corpus.py` sigue en 0 violaciones duras (mismos warns que la
baseline pre-ola-2, sólo `MIRRORREF` bajó su denominador de 22810→22339 refs
revisadas, consistente con las 471 imágenes menos), idempotencia
`sha256` byte-idéntica entre una 2ª corrida real y la 1ª.

**Gotcha del proceso de verificación (no del script)**: verificar
idempotencia con una 2ª corrida REAL (no `--dry-run`) sobre un retrofit que
usa `backup_and_rotate` en modo slot-fijo (el default en TODO el dominio de
imágenes, ver `docs/reference/conventions.md`) PISA el propio backup
pre-cambio con el estado YA aplicado — la 2ª corrida no cambia nada, pero
igual copia el `items.jsonl` actual (post-cambio) sobre el slot fijo antes
de procesar. Pasó en esta misma ola: `items.jsonl.pre-wave2-dedup-bak` quedó
idéntico al post-dedup en vez de conservar el pre-dedup. Para verificar
idempotencia sin perder el backup, correr la 2ª pasada con `--dry-run`
(reporta 0 cambios igual) o comparar el `sha256` ANTES de la 2ª corrida
real. Detalle en `docs/reference/gotchas.md` #159.

### Resolución de los pares dudosos — acción `remove_image` (2026-09-01)

Los 327 pares dudosos de arriba SÍ tienen ahora una vía de resolución: la
acción `remove_image` en `cover_preview.json`/`apply_preview()`
(`fetch_better_covers.py`) — la acción "eliminar sin reemplazo" que hasta
esta ola no existía. Diseño:

- **Esquema de la candidata**: reusa el schema multi-candidato existente en
  vez de agregar campos paralelos. `action: "remove_image"`, `target` = url de
  la imagen que se propone eliminar (igual que `replace_image`, que ya usa
  `target` para identificar CUÁL foto de la galería toca). `new_url`/
  `new_image` — que en el resto de las acciones son "la imagen nueva" — acá
  apuntan a la MISMA imagen que `target` (la que se propone eliminar): así
  `candSrc()` en el dashboard la muestra sin tocar código de rendering. Campos
  nuevos de CONTEXTO del par (para que el dashboard muestre "se va" vs "se
  queda" sin ir a buscarlo): `keep_url`/`keep_local` (la gemela que se
  conserva), `remove_dims`/`keep_dims` (`[w, h]` de cada una, leídas del
  espejo local al encolar), `same_dims` (bool, heredado del reporte de la
  ola 2). `match_dist` (campo genérico ya existente) se reusa para el dHash
  del par.
- **Regla dura — nunca sin portada**: si la imagen a remover es `images[0]`,
  la acción es inválida. Triple capa: (1) el encolador (abajo) nunca propone
  un `target` que sea la portada actual; (2) `sync_preview()` poda una
  candidata pending cuya `target` pasó a ser la portada mientras tanto
  (`pruned_remove_would_be_cover`); (3) `apply_preview()` es la red de
  seguridad final — si pese a (1)/(2) una candidata aprobada resuelve a
  `images[0]` (la galería cambió entre que se armó y se aprobó), NO la aplica:
  la devuelve a `pending` con `invalid_reason: "would_remove_cover"` en vez de
  reportar un "removed" fantasma o dejar el item sin portada.
- **`apply_preview()`**: aprobada → `_remove_gallery_image()` (ya existente,
  sólo opera sobre `images[1:]`) quita la entry; el archivo local se limpia
  como huérfano si ningún otro item lo referencia (mismo mecanismo de
  `old_to_drop`/`referenced` que las demás acciones). Rechazada → no se aplica
  nada (ambas imágenes se conservan tal cual); se registra en el ledger de
  rechazos como cualquier otra candidata (`data/cover_rejections.jsonl`), pero
  el self-heal de re-descarga (para candidatas con archivo local faltante) se
  saltea a propósito para esta acción — no hay nada que descargar, `new_url`
  es una foto que YA está en la galería del item.
- **`sync_preview()`**: tres podas para candidatas `pending` obsoletas —
  `pruned_remove_target_gone` (la imagen a eliminar ya no está en la
  galería, otra pasada la sacó), `pruned_remove_would_be_cover` (la regla
  dura de arriba) y `pruned_remove_keep_gone` (gotcha #168, 2026-09-01: la
  gemela que se CONSERVABA — `keep_url`, contexto del par — ya no está en
  `images[]`; sin ella la candidata queda huérfana para siempre, ninguna
  poda existente la alcanzaba porque `target` seguía presente). Se chequean
  ANTES que la poda genérica 3a (`pruned_already_current`), que de otro modo
  capturaría el mismo caso con un nombre que no describe la situación (acá
  no hay "reemplazo ya aplicado", hay una remoción que dejó de ser segura).
- **Dashboard (`web/cover-preview.html`)**: mínimo cambio sobre la UI
  existente — la card/modal compacta ya comparaban "actual" (panel izquierdo)
  vs "candidata" (panel derecho); para `remove_image`, `openCompare()`
  auto-navega el panel izquierdo a `keep_url` (la gemela que se conserva) y
  `candSrc()` ya resuelve el panel derecho a la imagen a eliminar sin cambios
  — así el modal existente compara el PAR sin agregar paneles nuevos. La
  card compacta agrega un segundo `.cand-thumb` chico con la gemela. Badge
  "🗑 a eliminar" / "✓ se conserva" en vez de la comparación de píxeles (que
  no aplica: no hay "ganancia" en una remoción). El dropdown de acción
  (`candidateOptions`) se oculta para esta acción — no tiene sentido
  redirigir una remoción a "agregar a galería" o similar. Aprobar/Rechazar
  reusan los mismos botones/atajos de teclado (A/R/1-5/N/P) sin cambios — el
  guard de portada corre server-side en `apply_preview()`, no en el cliente.
  `approved_unapplied` ya contaba genéricamente por `status`, así que incluye
  estas candidatas sin cambios.
- **Encolado inicial**: `scripts/retrofit/enqueue_wave2_dudosos_removal.py`
  lee `data/diagnostics/dedup-wave2-dudosos.json`, re-verifica CADA par contra
  el corpus vigente (el item sigue existiendo, ambas fotos del par siguen en
  `images[]`), determina keep/target (gana la de más píxeles; empate → gana
  la de índice menor en la galería), aplica la regla dura de portada, y
  escribe con `fetch_better_covers._write_preview(entries, merge=True)`
  (toma `preview_write_lock`, funde con lo que haya en disco — nunca
  reescritura total). Orden de encolado: primero los pares `same_dims=true`
  (más informativos — más probables de ser DOS FOTOS DISTINTAS, no una
  resolución vs otra), después el resto; dentro de cada grupo, dHash
  ascendente. Corrida real (2026-09-01, 705 entries totales en la cola tras
  el merge): de 327 pares, **280 candidatas `remove_image` encoladas en 260
  productos**; 44 saltados porque el target resolvía a `images[0]` (la
  imagen de MENOS píxeles del par resultó ser la portada vigente — señal de
  calidad real pero de otro dominio, `promote_hires_cover.py`/
  `upgrade_image_resolution.py`, no de esta acción) y 3 por `target`
  duplicado entre pares (dos pares distintos proponían eliminar la misma
  foto). 0 items habían perdido alguna de las dos fotos del par desde que
  corrió la ola 2. Verificación: `sync_cover_preview.py --dry-run` sobre la
  cola resultante da 0 podas (todas las candidatas encoladas son válidas
  contra el corpus), `pytest` completo 2370 verdes, `filter_non_manga.py
  --dry-run` 0 rechazos. `items.jsonl` NUNCA se tocó (sólo lectura) —
  `apply_preview()` no se corrió; las 280 candidatas quedan `pending` para
  que el owner las revise una por una desde `cover-preview.html`.
- Tests: `tests/test_remove_image_action.py` (normalización de defaults,
  apply aprobado/rechazado, guard de portada, dry-run, poda de `sync_preview`
  por target ausente y por target-pasó-a-ser-portada).

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
- **Criterio de basura ESTRUCTURAL, no por bytes crudos (2026-09-02, gotcha #185, fix de
  mecanismo).** `_compute_junk_local` clasificaba junk cualquier archivo local
  `< 6000 bytes` (`_TINY_BYTES`) sin mirar dimensión/contenido. Los thumbnails REALES de
  listadomanga (96-124×150-160px) comprimen en AVIF a 2.6-6KB y caían en esa clasificación
  — `_fix_bad_cover` terminaba vaciando `images[]` de ediciones sin galería de respaldo. La
  corrida real del 2026-08-23 21:31 afectó 111 items (todos ES) verificados: archivos
  2577-5992 bytes, dims tipo 208×300/234×320, 0/111 marcados placeholder por el detector
  estructural. Fix: `_compute_junk_local` ahora delega en `image_store.placeholder_reason()`
  (mismo detector que `purge_placeholder_images.py`: dims ≤8px, casi-sólido std<3, firma de
  contenido conocida, roto) para archivos ≤ `_EVAL_MAX_BYTES` (200 000, mismo bound que ese
  script); el tamaño en bytes DEJÓ de ser criterio de basura — sólo queda la señal
  independiente "compartido por ≥4 obras distintas". `_is_junk(url)` también gana
  `image_store.known_placeholder_url_reason()` (antes sólo miraba `IMAGE_URL_BAD_PATTERNS`,
  sustrings genéricos — un placeholder fichado por hash/fragmento/regla Rakuten sin esos
  sustrings pasaba como "no junk"). Tests en `tests/test_sync_cover_images.py` (16 casos:
  thumbnail chico-pero-real conservado, placeholder estructural purgado con/sin reemplazo,
  compartido-entre-obras purgado, archivo roto/firma/rakuten/known-url detectados, archivo
  grande nunca evaluado). **Reparación del dato** (separada del fix de mecanismo, mismo
  turno): `scripts/retrofit/restore_lm_thumbnails_20260902.py` — one-off, compara
  `items.jsonl` actual contra el backup pre-bug
  (`data/backups/items.jsonl/items.jsonl.pre-sync-cover-images-bak`, snapshot 2026-08-23
  21:31) y para cada item con `images == []` cuyo backup tenía una portada real de
  `static.listadomanga.com` (no un placeholder conocido), reconstruye `images[0]` — el
  archivo se recupera de `data/images/` directo o se MUEVE de vuelta desde la cuarentena
  `_orphans/` (re-verificado con `placeholder_reason` antes de mover), o si no aparece en
  ningún lado queda `local=""` para que `mirror_images.py --slugs` lo re-descargue. Corrida
  real: 111/111 restaurados vía `_orphans/`, 0 vía disco directo, 0 faltantes (no hizo falta
  re-descargar nada). Backup de items.jsonl con label `restore-lm-covers`. Tests en
  `tests/test_restore_lm_thumbnails.py` (9 casos: disco, orphans-con-move, missing-queda-url,
  nunca reintroduce placeholder conocido ni uno detectado recién al re-verificar, no toca
  items con portada ya presente, fuera de alcance si el backup no es de listadomanga,
  dry-run no mueve archivos, idempotente). De paso, `mirror_images.py` ganó `--slugs` (acota
  el BACKFILL a items puntuales sin restringir la lista completa que se flushea — filtrar
  la lista completa habría truncado `items.jsonl` a sólo esos slugs en cualquier flush
  parcial/final; el filtro vive DENTRO de `_run_backfill` sobre los targets, no sobre la
  lista de items pasada al caller). Tests en `tests/test_mirror_images_slugs.py`.

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
  propia pasada), `--only-reasons` (CSV de prefijos de razón — p.ej. `signature` o
  `signature,known` — para aplicar SOLO esas categorías esta corrida; lo detectado
  fuera de la lista se deja intacto, no cuenta como dropped ni entra al GC; default =
  todas las razones, comportamiento histórico. Agregado 2026-09-01, gotcha #161, para
  poder aplicar una denylist puntual sin arrastrar de paso un backlog `broken`/`known`
  preexistente que el script siempre re-detecta). Tests:
  `tests/test_purge_placeholder_images.py`.
- **`backup_and_rotate` + `sort_keys=True` (2026-07-08, hallazgo #6)**: el backup usaba
  un slot fijo propio (`.jsonl.pre-purge-placeholder-bak`, `shutil.copy`) en vez de la
  convención dura (rota, máx 3, `data/backups/<filename>/`); y la escritura no ordenaba
  las claves del dict (rompía la idempotencia byte-idéntica del corpus entre corridas).
  Corrida real de dry-run post-fix (2026-07-08): 0 items afectados, 0 huérfanos — el
  corpus ya estaba limpio desde la corrida inicial de abajo, confirmando que el cambio
  de backup/serialización no alteró ningún resultado.

Corre como paso **[4i]** del pipeline canónico (delta y full), después de
`dedup_carousel_images` y antes de `build_web`, así un placeholder que reentre durante un
scrape no llega al build. Corrida inicial 2026-06-13: 165 entries quitadas (87 sólidos, 63
pixeles 1×1, 15 con firma), 138 items pasaron a mostrar el 📚.

### OLA 3 de depuración de imágenes (2026-09-01) — firmas C3b + denylist iconos + cola de promoción local

Tercera ola del plan de depuración (ver ola 1 y ola 2 arriba), sobre el corpus YA
procesado por ambas: 14305 items, 3 grupos SHA-256 compartidos ≥5 items avalados
por el red-team en la auditoría previa (criterio C3b — ver gotcha #160 para el
detalle de por qué C3b NO generaliza a grupos nuevos sin validación).

**1. Purga de los 3 grupos validados.** Recalculado sobre el corpus actual (no se
confió en los conteos de la auditoría original): los 3 grupos reaparecieron
intactos — `68fe751d…` (15 items, Berserk Deluxe/Dark Horse Direct),
`981f9d0d…` (6 items, logo metálico "U" de Mangavariant), `f62d3e1f…` (6 items,
banner "Square Enix Manga & Books"). Confirmados visualmente de nuevo (conversión
AVIF→PNG + lectura) antes de tocar nada. Firmas sha1 agregadas a
`data/placeholder_signatures.json` (mismo mecanismo que las firmas de 2026-06-13,
ver arriba — el purge las consume vía `image_store.placeholder_reason()` sin
cambios de código):

| sha1 | label | dims |
|---|---|---|
| `7198af74883c98ebd0f6aeb20e9bf021b57f0943` | Dark Horse Direct — foto promocional genérica de Berserk Deluxe | 1600×1600 |
| `49e8419c2b0a631ecd198994a8ba2d3db1a367ae` | Mangavariant — logo metálico 'U' | 512×512 |
| `8fe710766d89bbb99d2ed50b53759b31f51f5005` | Square Enix Manga & Books — banner de editorial | 900×471 |

Corrida real (dry-run primero, backup `pre-wave3` + el propio
`.pre-purge-placeholder-bak` del script antes de aplicar): **27 entries
quitadas** (15+6+6, todas por firma, todas en posición `idx>0` — ninguna era la
portada `images[0]` de su item), **0 items quedaron sin ninguna imagen** (el
📚 no aumentó esta ola), 84 items aprobados salteados sin tocar, 3 archivos
huérfanos (el resto de los 24 archivos removidos sigue "vivo" porque otro item
no purgado lo referencia). Idempotencia verificada con una 2ª pasada
**`--dry-run`** (0 pendientes) — NO con una 2ª corrida real, por la gotcha #159
de la ola anterior (el slot fijo de backup se pisaría con el estado ya aplicado).

**Grupos NUEVOS al recalcular (NO purgados — ver gotcha #160):** aparecieron 3
grupos sha≥5 que el red-team nunca vio. 2 son FALSOS POSITIVOS del criterio —
portadas reales de tomos hermanos de un box de Mangarden.pl que se contaminan
entre sí por un bug de scope del extractor de galería, no un placeholder (ver
`docs/scraper/sources/pl-mangarden.md`). El 3ro (`81ba1b708afca6db…`, 7 items de
3 series: Hanma Baki, The Breaker New Waves, Baki Gaiden — todas de
meian-editions.fr) SÍ parece un banner genérico de homepage colado como foto de
galería, pero queda sin validar visualmente por el red-team ni purgado (ver
`docs/scraper/sources/fr-meian.md`). Ningún grupo nuevo se agregó a
`placeholder_signatures.json` ni se tocó en el corpus.

**2. Denylist de placeholders icónicos — revisión única (SIN aplicar).** El
red-team había detectado placeholders grandes CON contenido (ícono de libro
tachado de manga-passion.de, cámara tachada de livriz.com) que pasan todos los
filtros de tamaño/entropía porque no son ni diminutos ni casi-sólidos. Señal de
"planitud" recalculada sobre el corpus actual: `modal_frac` (fracción de
píxeles del bucket de color más repetido tras cuantizar a 64×64) ≥ 0.60 en la
PORTADA (`images[0]`) del item, cruzado con "el sha del archivo se repite en
≥2 items distintos" (una portada real casi nunca es byte-idéntica entre
productos distintos). Dio **28 candidatas** (vs. la estimación previa de ~29 —
consistente, el corpus cambió por las olas 1/2). Las 28 se leyeron una por una
(conversión AVIF→PNG + Read) y se clasificaron a mano:

| Familia (grupo de filas) | Host | Veredicto | Razón |
|---|---|---|---|
| `nightschool-yenpress-collector-us-{1,2}` | images.penguinrandomhouse.com | **placeholder** | "Cover Coming Soon" — variante nueva (1058×1600), sha1 distinto de la firma ya registrada (297×449) |
| `outlaw-tamer…`/`campfire-cooking…` (funside-variant-it) | funside.it | **placeholder** | Logo "MD — Immagine non disponibile" — variante nueva (500×500), sha1 distinto de las 2 firmas ya registradas |
| `oshiete-kudasai-fujishima-san…`/`oshiete-fujine-san…` | thumbnail.image.rakuten.co.jp | **placeholder** | Plantilla tipográfica genérica de Rakuten ("sin portada" con el propio título superpuesto) |
| `beck-distrito-kanzenban-ar-{3,5,8}` | cdn.livriz.com | **placeholder** | Ícono de cámara tachada "sin imagen" — 3 variantes de archivo, mismo diseño |
| `bang-dream-mygo…` | tshop.r10s.jp | portada legítima | Cover real chico (130×151), mismo archivo en 2 filas del mismo tomo |
| `asunaro-hakusho-part-1…` (×3) | img.91app.com | portada legítima | Cover real (chino tradicional), 3 ediciones/variantes del mismo libro |
| `captain-tsubasa-unknown-deluxe-pl-6{,-b}` | mangarden.pl | portada legítima | Mismo archivo, cover real de Kapitan Tsubasa |
| `cold-die-kreatur-altraverse-collector-de-5` | media.manga-passion.de | portada legítima | Foto real de slipcase |
| `silent-mobius-mangaline-omnibus-mx-1` | mangaline.com.mx | portada legítima | Foto real de 3 libros/box |
| `romantic-killer-panini-cofanetto-it` (×2) | www.panini.it | portada legítima | Foto real de cofanetto compartida entre 2 fichas del mismo box |
| `noblesse-panini-boxset-it-3`/`noblesse-1-3-panini-cofanetto-it-1` | www.panini.it | portada legítima | Mismo archivo, box real |
| `requiem-mit-schuber…`/`requiem-einzelband…` | media.manga-passion.de / altraverse.de | portada legítima | Foto real de slipcase (mismo diseño, 2 fuentes) |
| `billy-bat-panini-cofanetto-it` (×2) | www.panini.it | portada legítima | Foto real de cofanetto (mismo patrón que romantic-killer/noblesse) |
| `semantic-error-clines-boxset-de` (×2) | media.manga-passion.de | portada legítima | Foto real de boxset ("vorläufiges Cover" — mockup PROMOCIONAL oficial, no un placeholder genérico) |

**Resultado: 9 de 28 filas (4 familias visuales distintas) son placeholder;
19 de 28 son portadas legítimas** (mayormente fotos de boxset/cofanetto
compartidas entre fichas hermanas del mismo box — el mismo patrón legítimo que
ya protege la regla `cross-series` de `purge_placeholder_images.py`). Ninguna de
las 4 familias placeholder coincide en sha1 con las firmas ya registradas —
son variantes nuevas (otro tamaño/re-encode) de placeholders YA conocidos por
tipo, no placeholders nuevos de fuentes nuevas.

**Aplicación de la denylist (2026-09-01, aprobada por el owner).** Cada familia
resultó tener el MISMO sha1 (del espejo local AVIF) en sus 2-3 filas confirmadas
— la denylist por sha1 alcanza sin necesitar `KNOWN_PLACEHOLDER_URL_STEMS`/
`FRAGMENTS`: no hay un patrón de URL estable-y-exclusivo-de-placeholder en
ninguna de las 4 (el path de Rakuten/PRH/Funside/Livriz también sirve covers
reales, así que un fragmento de URL habría sido demasiado amplio). 4 firmas
nuevas a `data/placeholder_signatures.json`:

| sha1 | familia | dims | filas |
|---|---|---|---|
| `6a948548150f018bc3993b8fd8531d79b6f3f06c` | PRH "Cover Coming Soon" (variante 1058×1600) | 1058×1600 | `nightschool-yenpress-collector-us-{1,2}` |
| `51b45316ed9f6d8de41558d52e4eae5ec6b23b86` | Funside logo MD "Immagine non disponibile" (variante 500×500 nueva) | 500×500 | `outlaw-tamer-epic-rise-funside-variant-it-1`, `campfire-cooking-in-another-world-funside-variant-it-1` |
| `b10109774a879c1d8f484177fea3bafd6ffa46bf` | Rakuten Books — plantilla "sin portada" con el título superpuesto como texto | 1004×1172 | `oshiete-kudasai-fujishima-san-unknown-limited-jp-3`, `oshiete-fujine-san-bright-limited-jp-3` |
| `74527790152165b7db548ffb5ebfa09d426534c7` | Livriz — ícono de cámara tachada "sin imagen" | 1200×1500 | `beck-distrito-kanzenban-ar-{3,5,8}` |

Nota sobre Livriz: existe una 4ª fila con el mismo patrón de URL (`.../no-disp.png`,
`beck-distrito-kanzenban-ar-14`) pero con un archivo de OTRO tamaño (300×375, sha1
distinto) — visualmente es el mismo ícono, pero **no se agregó su firma ni se tocó
esta ola** porque no fue parte de las 28 filas que el owner revisó y aprobó (regla
dura de gotcha #160: cada instancia nueva necesita su propia validación explícita,
no alcanza con "mismo patrón de URL que una ya aprobada"). Queda anotado para una
futura ronda si el owner quiere extenderla.

**Corrida real** (`scripts/retrofit/purge_placeholder_images.py --only-reasons
signature`, gotcha #161 — el flag nuevo evita arrastrar el backlog `broken`/`known`
preexistente y no relacionado que el script siempre re-detecta): backup explícito
`items.jsonl.pre-denylist-icons-bak` + el propio `.pre-purge-placeholder-bak` del
script. **9 entries quitadas de 9 items** (exactamente las filas de la tabla), **9
items quedaron sin ninguna imagen** (los 9 tenían el placeholder como única foto,
sin galería — pasan al bucket de búsqueda web / 📚 en la UI), **9 archivos movidos a
cuarentena** `data/images/_orphans/`. Idempotencia verificada con una 2ª pasada
`--dry-run --only-reasons signature` (0 pendientes) — NUNCA con una 2ª corrida real
(gotcha #159, pisaría el propio backup pre-cambio con el estado ya aplicado).

Nota de proceso: con varios agentes corriendo en paralelo sobre el repo esta misma
sesión, la 1ª corrida real se aplicó correctamente pero un escritor concurrente
pisó `items.jsonl` con una copia tomada de antes de la purga minutos después —
las 9 filas volvieron a mostrar el placeholder. Se detectó con una verificación
directa (no sólo confiando en el resumen del script), se restauraron los 9
archivos desde `_orphans/` y se re-corrió la purga real; los números finales de
arriba son del estado confirmado después de ese 2º intento. Detalle completo del
mecanismo de la carrera (y por qué el 1er reintento reportó `0 items afectados`
en vez de volver a purgar) en gotcha #163.

**3. Cola de promoción local — SÍ soportada por la infraestructura existente,
sin tocar dashboard/serve.** Target: portada actual mala (`área<90 000 px` o
sin espejo local tras la ola 1) pero con otra imagen YA local y ≥90 000 px en
la propia `images[]` del item (idx≥1). Investigación: el schema multi-candidato
de `cover_preview.json` (`_normalize_preview_entry`/`apply_preview` en
`fetch_better_covers.py`) ya soporta una candidata cuya `new_image`/`new_url`
son un archivo/URL que YA vive en la galería del propio item — no exige que la
imagen venga de una búsqueda web. La acción `action="replace_cover_demote"` es
exactamente el caso de uso: promueve la candidata a portada y **conserva** la
portada mala actual en la galería como `kind="extra"` (no se pierde nada; el
owner decide en `cover-preview.html` como cualquier otra candidata). Se
encoló usando la infraestructura TAL CUAL —
`fetch_better_covers.preview_write_lock`/`_write_preview(merge=True)` (mismo
lock cross-proceso + merge anti-carrera que usa el motor real) + `backup_and_rotate`
sobre `cover_preview.json` antes de escribir — **cero líneas de código nuevas**
en `fetch_better_covers.py`, `serve.py` ni el dashboard.

Recálculo sobre el corpus actual (excluyendo items aprobados): de 1036 items con
portada mala, **40 tienen ≥1 alternativa local ≥90 000 px en su propia galería**.
Pre-filtro del red-team (fuertes primero, orden preservado en la lista — NO es
un campo persistido, es el ORDEN de las entries): fuerte = portada actual CON
espejo local (no "sin local") + `alt.kind != "extra"` + alt no `.gif` +
`alt.área != 90 000` exacto + aspect ratio del alt en `[0.60, 0.78]`. Resultado:
**7 fuertes, 33 débiles** — las 40 se agregaron a `cover_preview.json`
(413→446 entries; 7 slugs ya tenían una entry de `/watch-search-covers` y se
fusionaron ahí vía el merge existente). Nota para el owner: 4 de las 33 débiles
(`hanma-baki-meian-perfect-fr-{13..16}`) resuelven al MISMO banner genérico de
meian-editions.fr reportado como grupo sha nuevo sin validar en el punto 1 de
arriba — el pre-filtro ya las clasificó como "débiles" (aspect ratio 1.91, fuera
de 0.60-0.78) así que no aparecen primero en la cola, pero conviene
**rechazarlas** explícitamente en vez de aprobarlas. Diagnóstico completo
(clasificación fuerte/débil por slug, evidencia — NO una cola de aprobación
paralela) en `data/diagnostics/wave3-promotion-queue.json`.

**Segunda tanda (2026-09-01, mismo día) — los 44 excluidos de la ola 2
dudosos.** Fuente distinta a la de arriba: no son covers `<90 000 px`, son los
44 pares de `data/diagnostics/dedup-wave2-dudosos.json` que
`enqueue_wave2_dudosos_removal.py` NO pudo encolar como `remove_image` porque
la imagen de MENOR resolución del par era la portada vigente (`images[0]`) —
ver el comentario "Regla dura" en ese script. Eso no es un caso de "borrar
galería": es una mejora de portada con material que YA está en el item (la
gemela de mayor resolución del mismo par ya vive en `images[]`, idx≥1).
Reconstruido sobre el corpus actual con `scripts/retrofit/
enqueue_wave2_dudosos_promotion.py` (re-deriva keep/target con la misma
lógica que el script de remoción, filtrando sólo `target_idx==0`): **44
pares vigentes** (0 items desaparecidos, 51 pares con alguna imagen ya fuera
de la galería por otra pasada, 232 pares que no son caso de portada).
Mismo pre-filtro fuerte/débil que la ola 3 (kind≠extra + no `.gif` +
área≠90 000 exacto + aspect ratio en [0.60, 0.78]): **27 fuertes, 17
débiles** — el único motivo de "débil" en las 17 fue aspect ratio fuera de
rango (0 por `.gif`, 0 por área=90 000, 0 por `kind=extra`). Encoladas como
`replace_cover_demote` (fuertes primero) con la misma infraestructura de la
ola 3 — `fetch_better_covers.preview_write_lock`/`_write_preview(merge=True)`
+ `backup_and_rotate` (`cover_preview.json.pre-enqueue-44-demote-bak`) — cero
líneas nuevas en `fetch_better_covers.py`/`serve.py`/dashboard.
`cover_preview.json`: 459→501 entries (43 productos afectados; 1 slug —
`bleach-christmas-variant-panini-cofanetto-it-1` — con 2 candidatas, dos
gemelas distintas del mismo par de dudosos).

**Hallazgo al verificar con `sync_cover_preview.py --dry-run`**: reportó
**44/44 candidatas podadas** (`pruned_cover_ok`) y las 43 entries nuevas
vaciadas — a diferencia de la primera tanda (arriba), acá el 100% de las 44
portadas actuales YA estaban por encima del piso de 90 000 px (la premisa es
"misma foto, mejor resolución", no "portada por debajo del piso"), y la poda
3b de `sync_cover_preview.py` no distinguía el motivo. **Riesgo real**: una
corrida REAL (no dry-run) de `sync_cover_preview.py` — o simplemente abrir el
panel, que corre `sync_preview()` en cada `GET /api/cover-preview` y persiste
— borraba la cola completa antes de que el owner la viera. Quedó documentado
como gotcha #166.

**Fix de mecanismo (2026-09-01, mismo día — corregido)**: `sync_preview()` en
`scripts/retrofit/sync_cover_preview.py` ahora exime la poda 3b para
candidatas `replace_cover_demote` cuando, verificado EN VIVO contra `images[]`
del item (no contra el `new_pixels` congelado de la candidata), su `new_url`
sigue presente en la galería Y sus píxeles reales superan a los de la portada
actual — exactamente la premisa "gemela de mayor resolución ya en la galería".
Sin campo de premisa nuevo en el schema (`_normalize_preview_entry` intacto):
el criterio es 100% derivable de `action` + la galería actual + píxeles reales,
así que no hace falta re-encolar ni tocar `cover_preview.json`. Contador nuevo
`demote_upgrade_exempted` para observabilidad. `replace_cover`/`replace_and_add`
(motor de búsqueda web) no cambian de comportamiento — siguen podándose igual
que antes cuando la portada actual ya está por encima del piso. Si la "gemela"
deja de estar en la galería (otra pasada la sacó) o no es una mejora real
(píxeles iguales o menores), la excepción no aplica y se poda igual que antes
— precisión > recall. Tests nuevos en `tests/test_sync_cover_preview.py`
(`test_demote_gallery_upgrade_exempted_from_3b`,
`test_replace_cover_normal_still_pruned_when_cover_ok`,
`test_demote_no_real_upgrade_still_pruned`,
`test_demote_stale_gallery_membership_still_pruned`). Verificación real: un
`sync_cover_preview.py --dry-run` post-fix sobre las 501 entries actuales
reporta **0 podadas / 44 exentas / 0 cambios** (antes: 44 podadas / 43 entries
vaciadas / 87 operaciones) — **las 44 candidatas siguen en `cover_preview.json`
sin aplicar**, ahora ya no frágiles ante una corrida real de
`sync_cover_preview.py` ni ante abrir el panel, pendientes de revisión visual
del owner en `cover-preview.html`.

**Verificación de la ola completa**: `pytest` 2360 verdes, `filter_non_manga.py
--dry-run` 0 rechazos, `validate_corpus.py` 0 violaciones duras (los warns
preexistentes no cambiaron; `MIRRORREF` bajó su denominador de 22339→22312,
exactamente las 27 refs removidas por el purge), `sync_cover_preview.py
--dry-run` sobre las 446 entries reporta 0 podas/cambios (el schema nuevo es
válido para el resto del pipeline de revisión). Backups: `items.jsonl`
(`.pre-wave3-bak` explícito + `.pre-purge-placeholder-bak` del propio script) y
`cover_preview.json` (`.pre-wave3-promotion-bak`).

### Cierre de la tanda de depuración de imágenes (2026-09-01)

Cierre del ciclo iniciado por las olas 1-3 (ver arriba). Verificación de
integridad ANTES de tocar nada (read-only): denylist de 9 slugs/4 firmas
(ola 3) sin regresión, 10 items muestreados de la ola 2 (auto-eliminados)
sin reaparición, 10 items muestreados del espejo de la ola 1 con
`images[0].local` + archivo en disco confirmados, los 3 grupos sha de la
ola 3 (C3b) sin hits en todo el corpus — 0 regresiones encontradas.

**Purga del banner de Meian** (el grupo NUEVO reportado sin validar en la
ola 3, ver `docs/scraper/sources/fr-meian.md`): confirmado visualmente por
el owner. sha1 `1bff44a55de9e0afc37ba5bf6763b32de19cb7bd` (1200×630,
`meian-editions.fr/meian/assets/images/facebook/default_fb.jpg`, banner OG
por defecto del sitio) agregado a `data/placeholder_signatures.json`.
Corrida con `--only-reasons signature` (backup `items.jsonl.pre-meian-
banner-bak` + el propio `.pre-purge-placeholder-bak` del script): **7
entries quitadas de 7 items** (`hanma-baki-meian-perfect-fr-13..16`,
`the-breaker-new-waves-meian-ultimate-fr-1-5`/`6-10`,
`baki-gaiden-scarface-integrale-meian-coffret-fr`), los 7 conservaron su
`images[0]` real, 0 items quedaron sin imagen. El archivo no pasó a
`_orphans/` en esta corrida porque `cover_preview.json` todavía lo
referenciaba (4 candidatas `replace_cover_demote` rechazadas de la cola de
promoción local apuntaban al mismo banner) — se liberó al aplicar el
preview (siguiente punto).

**Aplicación de la cola de portadas** (`sync_cover_preview.py` real +
`fetch_better_covers.py --apply-preview` real, orden canónico): sync pasó
`catalog_is_sane` limpio, podó 37 entries vacías + 50 candidatas
`remove_image` con target ya desaparecido (705→668 entries) sin tocar
ninguna de las 9 candidatas aprobadas. `apply_preview` aplicó las **9
aprobadas** (3 `replace_cover` de corridas previas + **6 `replace_cover_demote`
de la cola de promoción local**, ver ola 3 punto 3): 9 reemplazos de portada,
6 agregados a galería (la portada vieja demovida a `extra`). **204
candidatas rechazadas** revertidas + ledgereadas en `data/cover_rejections.jsonl`
(6→210 filas), 180 imágenes nuevas huérfanas borradas — incluye las 4
candidatas del banner de Meian rechazadas explícitamente (ver gotcha #160).
Quedan **478 candidatas pendientes** en la cola tras el apply (230
`remove_image` de la ola 2 dudosos, 241 `replace_cover`, 4 `replace_image`,
3 `replace_cover_demote` — promociones débiles del juez aún sin decidir). Un
`sync_cover_preview.py` posterior (para limpiar 2 candidatas que quedaron
obsoletas por el fix de abajo) dejó la cola en **462 entries / 478
pendientes**, confirmado con un `--dry-run` final en 0 cambios.

**Bug encontrado y corregido al aplicar — `replace_cover_demote` duplica la
imagen promovida** (gotcha #164): las 6 candidatas de la cola de promoción
local reusan una foto que YA vivía en la propia `images[]` del item;
`_apply_improvement()` sólo escribía `images[0]` sin remover esa copia
preexistente de la galería, así que las 6 quedaron con la imagen dos veces
(`images[0]` y su posición original). Corregido AD HOC para esos 6 items
(quitada la copia redundante, portada intacta, backup
`items.jsonl.pre-fix-demote-dup-bak`).

**Fix de mecanismo cerrado (2026-09-01, turno posterior).** `_apply_improvement()`
(`scripts/retrofit/fetch_better_covers.py`) ahora dedupea de fondo: tras pisar
`images[0]`, busca en `images[1:]` una entry que matchee la promovida por la
MISMA clave canónica de dedup que usa el resto del pipeline
(`manga_watch._img_stem` sobre la url — robusto a sufijos de thumb CDN y query
params, no comparación de string pelada — con fallback a comparar `local` para
el candidato recién descargado). Si hay match, sus campos `kind`/`description`
se trasladan al entry sobreviviente en `images[0]` cuando éste no los tenía
(no se pierde metadata de la foto original al pisar la portada) y la copia
duplicada se elimina de la galería. El fix vive en UN solo lugar — cubre las
tres acciones que llaman a `_apply_improvement()` (`replace_cover`,
`replace_and_add`, `replace_cover_demote`) con el mismo mecanismo, no sólo
`replace_cover_demote`. Idempotente (una segunda pasada con los mismos
argumentos ya no encuentra duplicado). Tests en
`tests/test_replace_cover_demote_dedup.py` (dedup con/sin duplicado
preexistente, clave canónica vs. string pelado, idempotencia, regresión de
`replace_cover` plano). Suite completa: 2378 verdes.

**Verificación final**: `pytest` 2370 verdes, `filter_non_manga.py --dry-run`
0 rechazos, `validate_corpus.py` 0 violaciones duras (warns preexistentes sin
cambios de fondo; `MIRRORREF` con denominador 22418, consistente con el
backfill del delta diario corrido en paralelo esta misma sesión),
`sync_cover_preview.py --dry-run` final en 0 cambios, `data/quality_report.json`
regenerado (`scripts/audit/data_quality.py`, mismo comando que invoca el
Panel de Control).

**Balance de calidad de portadas, baseline auditoría 2026-08-31 → recálculo
2026-09-01** (mismo criterio ≥90 000 px que `data_quality.py`/el panel):

| Métrica | Baseline 2026-08-31 | Recálculo 2026-09-01 | Δ |
|---|---|---|---|
| Items totales | 14 305 | 14 353 | +48 (delta scrape del día, ajeno a esta tanda) |
| Portadas malas (total) | 1 061 | 1 042 | −19 |
| — portada < 90 000 px | 754 | 767 | +13 |
| — portada sin espejo local | 307 | 275 | −32 |
| Items sin ninguna imagen | 448 | 467 | +19 |
| Items con posible dup interno (dHash≤8) | 316 | 386 (273 con dHash≤4, umbral más estricto) | metodología de conteo puede no ser idéntica a la del baseline — no hay script de auditoría persistido de esa corrida |
| `cover_preview.json` — entries | 413 | 462 | +49 |
| `cover_preview.json` — candidatas pending | 245 | 476 | +231 (las olas 2/3 encolaron ~320 candidatas nuevas — remove_image + promoción local — de las cuales 9 se aprobaron/aplicaron y 204 ya estaban rechazadas de corridas previas al recalcular) |

Notas de lectura: el corpus no es estático entre ambas fechas (+48 items del
delta diario corrido en paralelo esta sesión), así que los deltas absolutos
mezclan el efecto de esta tanda con el crecimiento orgánico del catálogo. El
salto de portadas <90 000 px (+13) y sin imagen (+19) es consistente con
items NUEVOS del delta que todavía no pasaron por el backfill de imágenes —
no una regresión de esta tanda (las verificaciones de integridad del PASO 1
confirmaron 0 regresiones en lo que las olas 1-3 ya habían corregido). El
salto grande de `cover_preview.json` pending (+231) es la cola de trabajo
NUEVA que generaron las olas 2/3 (candidatas `remove_image` de los dudosos +
promoción local), no candidatas viejas sin atender. Script del recálculo:
`audit_images.py` (adaptado del usado en la auditoría original), en el
scratchpad de esta sesión — no persistido en el repo.

## Cierre final 2026-09-01 — aplicación de la cola + balance de la tanda completa

Cierre definitivo del ciclo de depuración de imágenes iniciado por las olas 1-3 y
continuado por el "cierre de la tanda" (sección anterior). Este turno es el ÚNICO
escritor de `items.jsonl`/`cover_preview.json` durante la corrida; usa los locks
canónicos (`items_write_lock`/`preview_write_lock`) heredados de los scripts, no
implementa nada nuevo.

**PASO 1 — integridad previa (read-only), 0 hallazgos**: `pytest` 2394 verdes,
`validate_corpus.py` 0 violaciones duras, `sync_cover_preview.py --dry-run` sobre
las 501 entries vigentes reportó exactamente **1 candidata podada** (`remove_image`
con gemela ausente, `vanquished-queens-unknown-limited-jp-3`, gotcha #168) y **44
exentas de la poda 3b** (gotcha #166) — el resultado esperado, sin regresiones.
Muestreo de 10 entries de `data/diagnostics/wave-mv-gallery-mirror.json` (gotcha
#169) confirmó `local` asignado + archivo `.avif` existente en disco para las 10, y
un cruce adicional contra `items.jsonl` confirmó que las 10 URLs de origen
matchean exactamente el `local` esperado en `images[]` (0 mismatches).

**PASO 2 — sync real**: `sync_cover_preview.py` (sin `--dry-run`), backup automático
del script en `data/backups/cover_preview.json/cover_preview.json.pre-sync-cover-
preview-bak`. Resultado idéntico al dry-run: 1 operación (la poda de la gemela
ausente), 501→501 entries (ninguna se vació). `catalog_is_sane` pasó limpio.

**PASO 3 — aplicación de la cola**: backup manual de `items.jsonl` (sufijo
`pre-apply-final`, `data/backups/items.jsonl/items.jsonl.pre-apply-final-bak`) +
backup automático del propio `fetch_better_covers.py` (label `apply-preview`),
luego `fetch_better_covers.py --apply-preview` en real (un `--dry-run` previo
confirmó el mismo resultado antes de tocar disco). Preview de entrada: 501
productos, 516 candidatas (431 aprobadas / 25 rechazadas / 60 pendientes).

| Acción | Resultado |
|---|---|
| Reemplazos de portada/galería (`replace_cover`/`replace_and_add`/`replace_image`) | **220 aplicados** (391 imágenes viejas huérfanas eliminadas del espejo) |
| Agregadas a galería (`add_gallery`/`add_extra`) | 0 |
| Revertidas (aprobadas antes, rechazadas en esta pasada) | 8 (7 imágenes nuevas huérfanas eliminadas) |
| Eliminadas sin reemplazo (`remove_image`) | **211 aplicadas** |
| Re-descargadas (self-heal, archivo faltante recuperado desde `new_url`) | 4 |
| Rechazadas al ledger (`data/cover_rejections.jsonl`) | 25 (210→235 filas) |
| Pendientes remanentes | 60 candidatas en 58 entries |

**Verificación post-apply, releyendo `items.jsonl` (gotcha #163, no confiar en el
resumen del script)**:
- **(a) Ninguna `remove_image` dejó un item sin portada**: comparación campo-a-campo
  contra el backup `pre-apply-final` de los 14353 items — 0 regresiones (0 items que
  tuvieran `images[0]` usable antes y no después).
- **(b) 10 `replace_cover` aplicados muestreados**: los 10 tienen `images[0].local`
  apuntando a un archivo `.avif` existente en `data/images/` (áreas entre 175 500 px
  y 1 713 600 px, todas ≥90 000 px — el piso mínimo del gate); la imagen vieja fue
  borrada del espejo en los 10 casos (comportamiento esperado, no una regresión).
- **(c) 0 candidatas `approved` sin aplicar**: recuento sobre `cover_preview.json`
  post-apply — 0 `approved`, 60 `pending`, 0 `rejected` (los 25 rechazos ya viven
  sólo en el ledger, no en la cola).
- **(d) 0 items con imagen duplicada en `images[]` (fix #164)**: barrido completo del
  corpus por `local` y por `url` dentro de cada `images[]` — 0 duplicados en ambos
  criterios.

**PASO 4 — verificación final**: `pytest` 2394 verdes (segunda corrida, post-apply),
`filter_non_manga.py --dry-run` 0 rechazos, `validate_corpus.py` 0 violaciones duras
(mismos warns preexistentes que el PASO 1, sin cambios de fondo), `sync_cover_
preview.py --dry-run` final en **0 cambios** (58 entries, 60 pendientes, 44 seguían
exentas), `data/quality_report.json` regenerado con `scripts/audit/data_quality.py`
(mismo comando que invoca el registry/Panel de Control, sin flags).

**Balance de calidad de portadas — baseline 2026-08-31 → recálculo intermedio
2026-09-01 → cierre final 2026-09-01** (mismo criterio ≥90 000 px que
`data_quality.py`/el panel; recálculo final vía `audit_images.py`, script read-only
copiado de la sesión anterior al scratchpad de ésta, ~10 min de corrida):

| Métrica | Baseline 08-31 | Intermedio 09-01 | Cierre final 09-01 | Δ vs. intermedio |
|---|---|---|---|---|
| Items totales | 14 305 | 14 353 | 14 353 | 0 (sin scrape en este turno) |
| Portadas malas (total) | 1 061 | 1 042 | **614** | −428 |
| — portada <90 000 px | 754 | 767 | **579** | −188 |
| — portada sin espejo local | 307 | 275 | **35** | −240 |
| Items sin ninguna imagen | 448 | 467 | **439** | −28 |
| Items con posible dup interno (dHash≤4) | 316 | n/d (metodología del recálculo intermedio no comparable, ver nota abajo) | **146** | — |
| `cover_preview.json` — entries | 413 | 462 | **58** | −404 |
| `cover_preview.json` — candidatas pending | 245 | 476 | **60** | −416 |
| Ledger `cover_rejections.jsonl` — filas | 6 | 210 | **235** | +25 |
| Refs de mangavariant.com sin `local` | (pendiente, ver gotcha #158/#169) | 0 (ola de galería cerrada el mismo día) | **0** | 0 |

Notas de lectura: la caída grande de "portadas malas" (−428) y de la cola
`cover_preview.json` (entries −404, pending −416) es el resultado DIRECTO de este
cierre — la aplicación real de las 220 mejoras + 211 remociones + el ledgereo de los
25 rechazos, no una corrida adicional de búsqueda. El ledger crece exactamente por
los 25 rechazos aplicados en el PASO 3 (210→235, sin otras escrituras). "Items sin
ninguna imagen" bajó (−28) porque parte de las 220 mejoras aplicadas eran de items
que antes tenían `images[0]` sin `local` utilizable y ahora tienen portada real
(no todas — la cola de búsqueda de portadas no cubre el 100% de los 439 restantes,
que siguen siendo candidatos para `/watch-search-covers`). La fila de dedup interno
(dHash≤4) usa el mismo script/umbral que la ola 2 original (146 items, dato limpio);
el valor "intermedio" no está en el doc previo con ese mismo criterio exacto, así
que no se compara directamente — evitar inferir una tendencia de esa fila sola.

**Script del recálculo**: `audit_images.py`, copiado sin modificar del scratchpad de
la sesión anterior (2026-08-31) al scratchpad de ésta — 100% read-only (nunca abre
`items.jsonl`/`data/images/` en modo escritura), no persistido en el repo.

## Etapa 1 — triage con IA de visión, preparación de manifiestos (2026-09-02)

Continuación del "Cierre final 2026-09-01": con el corpus en 579 portadas <90.000 px
(coincide exactamente con la fila "portada <90.000 px" de la tabla de balance de arriba,
buena señal de que el recálculo de esta sesión parte del mismo estado), el owner aprobó
correr la **Etapa 1** del plan de `informe_imagenes.md` — la IA de visión **no decide,
ordena**: prioriza qué portadas de baja resolución realmente se ven mal (para no gastar
tandas de `/watch-search-covers` en falsos problemas) y detecta sospechosos de
placeholder tipográfico entre TODAS las portadas del corpus.

**No se llamó a la API de Claude en esta sesión.** Se buscó credencial en `ANTHROPIC_
API_KEY` (env), `.env`/`.env.example` del repo, keychain (`security find-generic-
password`) y el CLI `ant` (no instalado, `ant auth status` no disponible) — 0 fuentes
con clave. Siguiendo la policy de la tarea, no se improvisó otra vía paga: se prepararon
los **manifiestos por chunks** para que el orquestador los reparta a subagentes de
visión, sin gastar en API desde este turno.

**Recálculo del corpus (read-only)**, reusando los caches de la sesión de imágenes
anterior (`wave3_full_cache.json` para área/sha, `wave3_cover_feats.json` para
`pale_frac`/`modal_frac`/`ncolors`) y recalculando sólo lo que faltaba (501 de 13.880
covers, los agregados/cambiados desde esos caches):

| Lote | Criterio | N | Chunks (40/chunk) |
|---|---|---|---|
| **A** | `images[0].area < 90.000 px` (mismo `LOW_QUALITY_PX` del panel) | **579** | `data/diagnostics/etapa1-manifests/lotA/` (15) |
| **B** | top 600 por `signal_score = modal_frac + pale_frac` sobre TODAS las portadas del corpus (no sólo lote A) | **600** | `data/diagnostics/etapa1-manifests/lotB/` (15) |
| Calibración | 8 casos con `known_verdict` del red-team (`informe_imagenes.md` §5) + 19 de diversidad sin verdad conocida | **27** | `data/diagnostics/etapa1-manifests/calibration/calibration_set.json` |

`data/diagnostics/etapa1-manifests/index.json` documenta metodología completa,
preguntas por lote, veredictos posibles y el schema de salida esperado
(`data/diagnostics/etapa1-triage.json`, no generado todavía — lo escribe quien corra el
juicio de visión).

**Nota de calibración**: el prompt original citaba "11 etiquetas C1 del red-team"; sólo
8 están nombradas explícitamente en `informe_imagenes.md`/CLAUDE.md — se usaron esas 8
tal cual, sin inventar las 3 restantes. Quien corra la calibración real debe tratar el
umbral de acierto (80%) sólo contra esas 8, no contra las 19 de diversidad.

### Spot-check manual (5 imágenes) — la señal de lote B tiene falsos positivos reales

Antes de cerrar, se verificaron a mano 5 portadas del top de lote B (convertidas de AVIF
a PNG en el scratchpad para poder verlas — el visor no renderiza AVIF crudo):

- **3 placeholders reales confirmados**: `goodnight-punpun-shogakukan-limited-jp-13`
  (Amazon JP, 1.852.800 px — sólo título en japonés sobre blanco), `rokujo-ichima-
  killtimec-special-jp-1` y `darwins-game-akita-limited-jp-21` (Rakuten Books, ambos
  exactamente 1.176.688 px / 1004×1172 — "tarjeta de título", sin arte de portada).
- **2 falsos positivos confirmados**: `asunaro-hakusho-part-2-sharppoint-deluxe-tw-3`
  (`img.91app.com`, el host más frecuente del top-600 con 91 casos) y `at-summers-end-
  dynit-cofanetto-it-1` (`m.media-amazon.com`) son portadas **legítimas** con diseño de
  fondo blanco/pálido — el `pale_frac` alto viene del diseño real, no de un placeholder.

Esto **confirma** lo que ya advertía `informe_imagenes.md` ("la señal es heurística, no
validada 1:1 en este corpus") y por qué el plan la usa sólo como generador de
candidatas para el triage de visión, nunca como gate automático. Detalle completo del
hallazgo de la familia Rakuten "tarjeta de título a canvas fijo" (que ni el área ≥90k ni
el dedup por SHA-256 de C3b detectan) en gotcha #170.

**Estado**: manifiestos listos, 0 juicios de visión corridos, US$0 gastados. Próximo
paso (fuera de esta sesión): el orquestador reparte los chunks de `lotA/` y `lotB/` a
subagentes de visión, empezando por la calibración de 27 casos.

## Etapa 1 — resultados del triage con visión (2026-09-02)

Continuación directa de la sección anterior. El orquestador repartió los 30 chunks a **15
subagentes baratos** (2 chunks c/u) y después un **subagente JUDGE** con visión re-verificó
todo lo que decidía algo (todos los `placeholder`, todos los `se_ve_mal`, todos los
`dudoso`) y juzgó lo que había quedado sin cubrir. Salida consolidada:
**`data/diagnostics/etapa1-triage.json`** (1179 objetos = un objeto por par *(lote, slug)*;
29 slugs caen en ambos lotes).

**Método de re-verificación** (reproducible): AVIF → PNG con Pillow del venv y **hojas de
contacto** donde cada portada se renderiza **al ancho real de la card (300 px, BICUBIC)**,
5 columnas × 3-4 filas, hoja ≤ 1500 px para que el visor no la reescale. Juzgar la miniatura
a tamaño nativo es lo que hace que un agente barato declare "nítida" una imagen de 130 px.

### Cobertura — lo que los 15 agentes dejaron sin hacer

| | lote A (579) | lote B (600) |
|---|---|---|
| Con veredicto de agente | 538 | 560 |
| **Sin veredicto** | **41** (`lotA_chunk_001` completo + 1 ítem de `lotA_chunk_009`) | **40** (`lotB_chunk_001` completo) |
| Duplicados | 19 (`lotA_chunk14.json` vs `lotA_chunk_014.json`) | 40 (`lotB_chunk14` vs `lotB_chunk_014`) |
| **Contradicciones entre duplicados** | **0** | **0** |

Los 81 huecos los juzgó el JUDGE mirando las imágenes. Los duplicados coincidieron al 100%,
así que no hubo nada que arbitrar — pero el **chunk 1 de ambos lotes se perdió entero**:
con nombres de archivo libres (`lotA_chunk02.json`, `lotA_chunk_000.json`,
`REPORTE_CHUNK06.txt`, y uno en otro directorio) no hay forma de detectar el hueco sin
reconciliar slug por slug contra los manifiestos. **Convención para la próxima tanda: el
nombre del archivo de resultados debe ser exactamente el del chunk de entrada**, y la
reconciliación slug→veredicto contra el manifiesto es obligatoria antes de consolidar.

### Matriz de re-verificación — el juicio barato falla por sesgo de fondo blanco

| Veredicto del agente | Confirmado por el JUDGE | Degradado |
|---|---|---|
| lote B `placeholder` (84) | **46 (55%)** | 34 → `no_placeholder`, 3 → `imagen_equivocada`, 1 → `dudoso` |
| lote B `dudoso` (22) | — | 21 → `no_placeholder`, 1 → `imagen_equivocada` |
| lote A `placeholder` (17) | **14 (82%)** | 3 → `se_ve_bien` |
| lote A `dudoso` (3) | — | 2 → `se_ve_bien`, 1 → `imagen_equivocada` |
| lote A `se_ve_bien` (518) | 490 | 25 → `se_ve_mal`, 3 → `placeholder` |

**El 45% de los `placeholder` del lote B eran falsos positivos, y casi todos del mismo tipo**:
**fotos del producto físico sobre fondo blanco** — cofres y estuches 3D (15 de un solo chunk:
Berserk, L'Attacco dei Giganti, Death Note Black Edition, Jujutsu Kaisen, My Dress-Up
Darling), renders 3D de tomos (西遊妖猿傳, 東京愛情故事), y **portadas minimalistas de diseño**
(las 12 de 三國志 典藏版 de Sharp Point — caligrafía + una figurita a línea sobre blanco —,
Fénix de Tezuka/Planeta, `blanc #1` de Asumiko Nakamura, el coffret de *Rumiko Takahashi ·
Histoires Courtes* de Delcourt). Todas son portadas válidas. Ver gotcha #172.

En el otro sentido, el juicio barato **no vio 25 portadas genuinamente blandas** del lote A
porque las miró a tamaño nativo en vez de a tamaño de card.

### Conclusión sobre el umbral de 90.000 px como criterio de encolado

**El área NO sirve como criterio de encolado; el ancho de origen sí.** El lote A entero está
por debajo de 90.000 px, pero el 84% son portadas de `static.listadomanga.com` de ~210×300 px:
en una card de 300×420 px (fit *contain*) eso se renderiza con un factor de **1.4×**, y se ve
perfectamente bien. La métrica que separa lo bueno de lo malo es el **factor de reescalado en
la card**, `escala = min(300/w, 420/h)`:

| escala en card | ítems del lote A | veredicto real |
|---|---|---|
| < 1.6× | **528 (91,2%)** | se ven bien — muestreo aleatorio de 15 + los 490 confirmados |
| ≥ 1.6× | **51 (8,8%)** | blandas de verdad (33 `se_ve_mal`) o directamente placeholder/imagen equivocada (18) |

La distribución es **bimodal**, no continua: 528 ítems ≤1.6× y 51 ítems ≥2.0×, con **2 ítems
en el medio**. O sea que el corte no es arbitrario, hay un hueco real.

**Recomendación para `sc_plan` del skill `/watch-search-covers`** (recomendación, no se tocó
código): reemplazar el target `area < LOW_QUALITY_PX (90.000)` por
`min(300/w, 420/h) >= 1.6`, y priorizar dentro de eso las **apaisadas** (`h < w`) primero.
Efecto sobre este corpus: la cola de búsqueda web baja de **579 a 33 ítems (−94%)**, y los
otros 18 del tramo malo se resuelven con denylist/purga, no con búsqueda. Las 6 apaisadas van
primero porque no son "baja resolución" sino **recorte destruido**: `image.aladin.co.kr`
sirve `cover150/` como una banda de 150×76 … 150×136 px donde ya no queda portada que
mejorar, y `tshop.r10s.jp` hace lo propio con `?downsize=130:*`.

### Placeholders confirmados — tabla de decisión de denylist (lote B, 58 ítems)

**Nada se purgó**: esto es material de decisión para el owner. Los hashes de cada archivo
(`sha1`, `sha256`) y cuántos ítems comparten cada archivo están en
`data/diagnostics/etapa1-triage.json` → `_meta.denylist_candidata_por_host`.

| Host | Ítems | Patrón | Denylist por hash sirve? |
|---|---|---|---|
| `tshop.r10s.jp` | 26 | `/book/cabinet/<n>/<ISBN>.gif?downsize=130:*` — tarjeta de título | **No** |
| `thumbnail.image.rakuten.co.jp` | 22 | `/@0_mall/book/cabinet/<n>/<ISBN>.gif` — misma familia | **No** |
| `images-na.ssl-images-amazon.com` | 4 | `/images/P/<ISBN>.09SCLZZZZZZZ_.jpg` con "電撃コミックス coming soon" / "FLOS COMIC coming soon" / "Now Printing" | **No** (la misma URL sirve portadas reales) |
| `www.animeclick.it` | 3 | `/bundles/accommon/images/non_disponibile.jpg` — "COPERTINA NON DISPONIBILE" + logo | **Sí** (URL exacta, 1 archivo, 3 ítems) |
| `shop.r10s.jp` | 1 | misma familia Rakuten | No |
| `mangavariant.com` | 1 | `/wp-content/uploads/2024/07/hunt1.jpg` — banner de evento 30º aniversario City Hunter | Sí (URL exacta) |
| `funside.it` | 1 | `/cdn/shop/files/cover_<uuid>.jpg` — "MQ · IMMAGINE NON DISPONIBILE" | Sí (URL exacta) |

**El hallazgo que decide la estrategia**: los 58 placeholders dan **55 SHA-256 distintos**.
Sólo 2 grupos repiten archivo (AnimeClick ×3, una tarjeta Rakuten ×2). La familia dominante
(49/58, el 84%, todo Rakuten/e-hon) **quema el título en la imagen**, así que cada archivo es
único y **ninguna denylist por hash la va a agarrar** — ni la de C3b (SHA compartido ≥5
ítems) ni ninguna otra. Hay que atacarla por patrón de URL. Ver gotcha #171: en los hosts
Rakuten, la **extensión `.gif`** discrimina con precisión perfecta en este corpus.

**Falsos positivos de la heurística `modal_frac + pale_frac`** (lote B): 535 `no_placeholder`
sobre 600 → **la señal tiene ~10% de precisión** y sirve sólo como generador de candidatas,
nunca como gate. Los hosts que más la disparan sin ser placeholder: `img.91app.com` (Sharp
Point TW, diseño editorial sobre blanco), `www.animeclick.it` (fotos 3D de cofres),
`img.sanctuary.fr` y `media.manga-passion.de`.

### Categorías nuevas que aparecieron en el triage

- **`imagen_equivocada`** (8 ítems, separada de `placeholder` a pedido del encargo): no es un
  placeholder de la tienda sino la foto/el escaneo **equivocado** del producto correcto.
  Casos: contraportada con sinopsis y código de barras
  (`sous-un-rayon-de-soleil-panini-coffret-fr-1`), escaneo de página en blanco / lomo
  (`katekyo-hitman-reborn-haksanmunhwasa-limited-kr-16`), collage de merch en vez de portada
  (`debut-or-die-unknown-limited-kr-2`, `kagurabachi-kana-special-fr-10`,
  `my-dress-up-darling-kana-coffret-fr-1`), y **mockup con marca de agua `SAMPLE`**
  (`the-heroic-legend-of-arslan-kobunsha-boxset-jp-1-16`). Estos NO se arreglan con denylist:
  necesitan re-fetch o búsqueda.
- **`portada_provisional`** (4 ítems, marcados en el JSON con el flag homónimo): las 4
  *Happy! Édition de Luxe* de Panini FR en `img.sanctuary.fr` llevan una banda
  **"COUVERTURE PROVISOIRE"** impresa sobre arte real. **No** son placeholder (el arte es del
  editor y es el de la obra), pero envejecen mal: candidatas a re-fetch cuando salga la
  portada definitiva, no a purga.
- **`dudoso` (2, sin resolver a propósito)**: `goodnight-punpun-shogakukan-limited-jp-13`
  (blanco con el título y el autor rotulados a mano, 1158×1600 — **corrige el spot-check de
  la sección anterior, que lo daba por placeholder confirmado**: el rotulado es caligrafía
  real de la edición Young Sunday Comics, así que lo más probable es que sea la portada sin
  sobrecubierta) y `aposimz-mangacult-limited-de-1` (emblema plateado de 4 puntas sin texto;
  la API de manga-passion lo registra como cover activo del volumen, apunta a diseño real del
  estuche). Ninguna de las dos se pudo cerrar por web; se dejan en `dudoso` a propósito —
  precisión > recall.

### Sospechosos de non-manga detectados de paso (para `filter_non_manga`)

Nueve ítems que la visión identificó como libros que no son manga y que hoy están en el
corpus: `item-f5b77311f6d7` y `item-c70208a5d8b7` (libros de adivinación *Getters Iida ·
五星三心占い* 2021 y 2026), `item-37e4a16256aa` (láminas de historia natural francesa,
博物画集), `neko-no-iru-ie-unknown-special-jp` (ensayo ilustrado sobre gatos),
`haru-han-kogi-daewon-limited-kr` (libro coreano de fotos de perros), `dr-stone-unknown-
limited-jp` (guía de viaje 地球の歩き方 — la marca "Dr.STONE" es el tema de la guía, no un
manga), y las dos ediciones de `gran-enciclopedia-de-las-videoconsolas-heroesdepapel-*`. Van
como candidatos, no como decisión: la curación es del owner.

## Etapa 1 — la recomendación se aplicó en `sc_plan.py` (2026-09-02)

Cerrando la Etapa 1: la recomendación de la sección anterior ("reemplazar el target `area <
LOW_QUALITY_PX` por `min(300/w, 420/h) >= 1.6`, apaisadas primero") se implementó en el
planificador determinista del skill `/watch-search-covers`.

**Código**: `scripts/retrofit/fetch_better_covers.py` gana una función pura
`cover_upscale_factor(w, h, card_w=300, card_h=420) -> float` (`min(card_w/w, card_h/h)`,
`inf` si `w`/`h` no son computables) y la constante `UPSCALE_TARGET_MIN = 1.6`, junto a
`LOW_QUALITY_PX` — que **no cambia de semántica**, sigue siendo el umbral de "pixelada" del
panel de calidad (`data_quality.py`) y de `sync_cover_preview.py`/`promote_hires_cover.py`.
`scripts/retrofit/sc_plan.py` gana `--target-rule {scale,area}` (default `scale`, 2026-09-02):

- **Portadas (`img_idx 0`)**: con `scale` (default), target si
  `cover_upscale_factor(w, h) >= UPSCALE_TARGET_MIN`; ordenadas apaisadas (`w > h`) primero,
  luego por factor descendente (peor primero). Con `area` (compatibilidad), vuelve al
  criterio viejo (`píxeles < LOW_QUALITY_PX`).
- **Galería (`img_idx >= 1`)**: SIEMPRE usa el criterio de área — la Etapa 1 sólo evaluó
  portadas.
- Las dimensiones se leen del archivo local vía `get_dims_local()` (nuevo), que delega en
  `fbc._get_dims_from_bytes` (la fuente única de dimensiones del motor) en vez de duplicar
  el parsing PIL que tenía antes `get_pixels_local` (ahora un wrapper de una línea sobre
  `get_dims_local`).

**Dry-run sobre el corpus real** (solo lectura — `--out`/`--acc-out` redirigidos al
scratchpad, `items.jsonl`/`cover_preview.json` nunca se tocan), comparando `--target-rule
scale` (default) contra `--target-rule area` (criterio viejo), ambos con `--retry-failed`
para no arrastrar el ruido de corridas concurrentes del mismo día:

| Criterio | Targets de PORTADA |
|---|---|
| `area` (viejo) | 546 |
| `scale` (nuevo, default) | **48** (−91,2%) |

**Cruce contra `data/diagnostics/etapa1-triage.json`** (33 slugs con veredicto `se_ve_mal`):
32/33 siguen en el corpus y son candidatos elegibles (el criterio nuevo con `--retry-failed`
los captura **32/32**, 100%); el slug 33 (`radiant-letrablanka-regular-es-10`) tiene la señal
`variant_cover`, que `sc_plan.py` salta SIEMPRE (antes de esta tarea, sin relación con el
criterio de calidad — "web search devuelve la portada regular, no la variante"). **0** de los
516 slugs con veredicto exclusivamente `se_ve_bien` terminaron como target bajo el criterio
nuevo (0 falsos positivos). El corpus real ya no tiene 579 portadas < 90 000 px como en la
sesión original de la Etapa 1 — bajó a 546 candidatas de área porque agentes concurrentes
purgaron/reemplazaron portadas el mismo día — pero la proporción de reducción (~91%) y la
captura 100% de los `se_ve_mal` conocidos confirman la recomendación.

**Tests**: `tests/test_cover_upscale_factor.py` (función pura: cuadrado, apaisado tipo
Aladin `cover150/` → 2.0× exacto, retrato listadomanga 210×300 → 1.4× exacto —confirma el
número citado en la sección anterior—, grande que ya entra sin estirarse, dims no
computables → `inf`, tamaño de card parametrizable) + 11 tests nuevos en
`tests/test_sc_plan.py` (selección `scale` vs `area`, la galería sigue en área siempre,
orden apaisadas-primero y luego por factor descendente, `get_dims_local` delegando en la
fuente única). Suite completa: 2413 tests verdes (baseline previo 2394).

Docs actualizados en el mismo turn: `.claude/skills/watch-search-covers/SKILL.md`
(descripción del target nuevo + `--target-rule` en la tabla de parámetros y el Step 1) y
gotcha #172 (nota de "aplicado en sc_plan").

## Etapa 1 — cierre: denylist aplicada + 7 non-manga expulsados (2026-09-02, gotcha #176)

El owner aprobó resolver lo que quedó "verificado, listo para aplicar" en las secciones
anteriores. Backup explícito `data/backups/items.jsonl/items.jsonl.pre-etapa1-denylist-bak`
antes de tocar nada.

**Placeholders/imágenes equivocadas — purga real.** Antes de purgar, cada regla se cruzó
contra `etapa1-triage.json` para confirmar que no atrapaba ninguna portada que el juez
hubiera dado por real:

- **Regla `.gif` de Rakuten** (gotcha #171) implementada en
  `image_store.known_placeholder_url_reason()`: host de la familia Rakuten
  (`tshop.r10s.jp`/`thumbnail.image.rakuten.co.jp`/`shop.r10s.jp`) Y `urlparse(url).path`
  (sin query) termina en `.gif`. Cruce: los 50 `.gif` de `images[0]` en todo el corpus dan
  **50/50 confirmados NO-portada** (49 `placeholder` + 1 `imagen_equivocada`), **0**
  `se_ve_bien`/`no_placeholder` — sin excepciones que reportar.
- **AnimeClick** (1 archivo compartido por 3 items), **Mangavariant** (banner del 30º
  aniversario de City Hunter) y **Funside** (4ª variante del placeholder "MQ · IMMAGINE NON
  DISPONIBILE") → sha1 exacto en `data/placeholder_signatures.json`.
- **Amazon** (4 items, tarjetas "coming soon"/"now printing" con ISBN distinto cada una) →
  sha1 exacto de cada archivo (la URL sirve portadas reales también, no discrimina).
- **6 `imagen_equivocada`** (contraportada, collage de merch, página en blanco/lomo, foto de
  display, mockup `SAMPLE`) → sha1 exacto con label `wrong_image:<slug>` para distinguirlas
  de un placeholder de tienda genuino.
- **Las 4 `portada_provisional`** (banda "COUVERTURE PROVISOIRE" de *Happy! Édition de
  Luxe*, Panini FR) y los **3 `dudoso`** (`goodnight-punpun-...`, `aposimz-...`,
  `haru-no-arashi-to-monster-...`) **no se tocaron** — son arte real, no placeholder.

`purge_placeholder_images.py --only-reasons known,signature` (gotcha #161, nunca sin
acotar): **68 items afectados, 68 entries quitadas** (`known: 53`, `signature: 15`). El
`known` da 53 y no 49 porque la regla `.gif` corre en CUALQUIER posición de `images[]`, no
sólo portada — 4 tarjetas coladas como foto de "galería" cayeron también; 3 más quedaron
protegidas porque el propio item las lista como `kind: extra` de su propia colección (el
guard de "dueño legítimo" de `url_owner` protege también razones `known:`, no sólo
`cross-series` — comportamiento existente y con test propio,
`test_purge_known_placeholder_url_keeps_owner`, no tocado). **56 items quedaron sin ninguna
foto** (candidatos a `/watch-search-covers` o re-fetch). `--dry-run` posterior con el mismo
`--only-reasons`: **0 pendientes**; archivo releído (gotcha #163) y verificado a mano contra
una muestra de slugs — cada uno con el estado esperado (purgado del todo, purgado
parcialmente conservando galería real, o intacto).

**7 non-manga expulsados.** La visión detectó de paso 9 sospechosos (7 slugs únicos, 2
repetidos entre lote A/B) mirando sólo portadas — cada uno se verificó contra
`items.jsonl` (título/descripción/publisher/fuente) antes de tocar nada, y 2 resultaron
FALSOS POSITIVOS del juez (que sólo ve la portada, no el contenido):

| Slug | Veredicto | Motivo |
|---|---|---|
| `item-f5b77311f6d7`, `item-c70208a5d8b7` | expulsado | almanaque de adivinación *Getters Iida · 五星三心占い* — la propia descripción de Rakuten dice "占い本特集" |
| `item-37e4a16256aa` | expulsado | artbook de historia natural francesa (`博物画集`), no artbook de manga |
| `neko-no-iru-ie-unknown-special-jp` | expulsado | recopilación de tanka + ensayo de 仁尾智/小泉さよ (辰巳出版) — verificado por búsqueda web: poesía corta + prosa, no viñetas |
| `dr-stone-unknown-limited-jp` | expulsado | guía de viaje real de la franquicia `地球の歩き方` (desde 1979); el título menciona "Dr.STONE" pero es la guía, no el manga |
| `gran-enciclopedia-de-las-videoconsolas-heroesdepapel-{deluxe,special}-es` | expulsado | enciclopedia de hardware de videoconsolas, colada desde listadomanga.es |
| `haru-han-kogi-daewon-limited-kr` | **conservado** | manhwa real publicado por Daewon C.I. (categoría `만화` en su propio catálogo) — verificado por búsqueda web |

Los 2 `dudoso` restantes del triage (`goodnight-punpun-...`, `aposimz-...`) no forman parte
de esta lista de 9 y tampoco se tocaron.

5 patrones nuevos a `_NON_MANGA_HARD` en `manga_watch.py` (no a
`data/comics_blacklist.yml`, que es específico de franquicias de cómic occidental vía
`is_comic_not_manga` — estos son libros generales sin relación al cómic):
`ゲッターズ飯田`, `博物画集`, `地球の歩き方`, `猫のいる家に`, `gran enciclopedia de las
videoconsolas`. Cada término se verificó contra el corpus completo ANTES de agregarlo
(gotcha #154 — un término mal elegido puede borrar manga real): conteos de 1-2 hits, sin
colisión. `filter_non_manga.py --dry-run` → `--dry-run` posterior confirmó **exactamente 7
rechazos**; aplicado (real run): **14353 → 14346 items**. Tests:
`test_is_likely_manga_rejects_non_manga_general_books_etapa1` (los 7 casos reales) +
`test_is_likely_manga_general_book_patterns_dont_overmatch` (画集 genérico y el corgi
manhwa siguen pasando).

**Verificación final**: pytest completo 2421 verdes (0 rojos), `validate_corpus.py` → 0
violaciones duras (14346 items), `sync_cover_preview.py --dry-run` → 0 operaciones (ninguna
candidata de la cola quedó huérfana por este cierre). Docs actualizados en el mismo turn:
esta sección, gotcha #176, y las fichas `jp-rakuten-books.md`, `animeclick.md`,
`it-funside-variant.md`, `mangavariant.md`.

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
3. **Motores, en orden** (motor de texto = **Bing** desde 2026-07-11 — gotcha #145): para
   items en **Español**: primero **whakoom** (`site:whakoom.com <serie> <vol>`, ahora vía
   **Bing** que honra `site:` — produjo el 100% de los matches ES del piloto; yandex-reverse 0
   porque los thumbnails de listadomanga no están indexados por Yandex), después **Yandex
   reverse-image** (`rpt=imageview&url=<old_url>` — mejor búsqueda-por-foto gratis), después
   queries de texto con contexto en **Bing Imágenes** (`&first=1`, extracción por `murl`). Para
   otros idiomas: Yandex reverse va primero. **Google udm=2 quedó como fallback de emergencia**
   (no primario): scrapear Google con las cookies del owner ata el 429 a su cuenta y puede
   escalar a suspensión; se usa solo si Bing se degrada, con throttle fuerte y stop-al-primer-
   `/sorry`. Google Lens y Bing visual NO sirven (franquicia-level matching / bloqueado). Cada
   variante lleva `engine` (`bing`/`yandex`), registrado en `cover_search_attempts.jsonl`.
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
   `sync_cover_preview._ledger_record_from_candidate`). **Guard por `action` (gotcha #167,
   2026-09-01)**: este gate sólo tiene sentido para candidatas con imagen NUEVA externa
   (`fetch_better_covers.NEW_EXTERNAL_IMAGE_ACTIONS`: replace_cover/replace_image/
   replace_and_add/add_gallery/add_extra) — `remove_image` (`new_image` es la imagen que se
   propone ELIMINAR) y `replace_cover_demote` (`new_image` suele ser una foto YA existente en
   la propia galería del item, cola de promoción local) se saltan intactas en AMBOS scripts
   (`prune_soft_cover_candidates.py` y `revalidate_cover_preview.py`). Tests:
   `tests/test_detail_ratio.py`, `tests/test_cover_sync_guards.py`,
   `tests/test_revalidate_cover_preview.py`.
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
  Patrones verificados: whakoom `/small/` → `/large/` (3× px); buscalibre reescribe
  `fit-in/<W>x<H>/` → `fit-in/1200x1200/` (gotcha #167, 2026-09-01 — NO se quita el segmento,
  ver § "Búsqueda de portadas hi-res — skill `/watch-search-covers`" y
  `docs/reference/gotchas.md` #167 para el detalle empírico; no re-capa si el fit-in pedido ya
  es ≥1200); cultura quita `cdn-cgi/image/width=<N>/`;
  bdfugue (Magento) quita `cache/<hash>/`; WordPress genérico quita sufijo `-<W>x<H>` del
  nombre de archivo. `_same_cover` valida cada descarga, así que una reescritura incorrecta
  no contamina. `new_url` en el resultado refleja la variante que se usó efectivamente.
- **Default portadas + galería**: por defecto el skill procesa `img_idx == 0` (portadas) Y
  `img_idx >= 1` (galería). Las fotos de galería interior son irrecuperables en su mayoría (no
  existe copia externa); en la corrida real 12/25 targets de galería dieron 0 matches, así que
  aportan poco pero se incluyen igual. Usar `--only-covers` para acotar a portadas, o
  `--gallery-only` para exclusivamente galería.
- **Variante whakoom para Español** (va PRIMERO): en `build_variants`, items con
  `language == 'Español'` reciben una variante de texto `site:whakoom.com <serie> <vol>`
  (ahora vía **Bing**, que honra `site:`) insertada al inicio de la lista — antes de
  yandex-reverse. Motivo: whakoom produjo el 100% de los matches ES (8/8) y yandex-reverse 0
  (thumbnails de listadomanga no indexados por Yandex). Su CDN (i1.whakoom.com/small/) tiene
  upgrade automático a /large/ en sc_validate.py.
- **Memoria de intentos** (`data/cover_search_attempts.jsonl`): una línea JSON por intento
  con `{slug, action, target, attempted_at (ISO), matches (int), engines (lista)}`. El campo
  `engines` (2026-07-11) registra qué motores se consultaron — sin él, un 0-match de un motor
  degradado cierra el reintento 30 días sin rastro. Targets cuyo último intento tuvo
  `matches == 0` hace menos de 30 días se omiten automáticamente. Flag `--retry-failed`
  para ignorar la exclusión. El archivo es local (`.gitignore`). El **motor** (`run()` de
  `fetch_better_covers.py`) ahora también escribe una fila por target procesado (mismo formato
  + campo extra `engines: {isbn,lens,text}`); UNA fila por `(slug,action,target)` para no
  romper el dedup del skill (ITEM 6).

### Etapa 2, tanda 1 — España/ListadoManga, 150 targets vía whakoom-por-Bing (2026-09-02)

Primera tanda real (no piloto) del plan "Etapa 2" aprobado por el owner: medir el hit rate
real de whakoom-vía-Bing sobre el catálogo ES completo antes de escalar. **Resultado: el
8/8 del piloto de 2026-07-11 NO generaliza** — sobre 150 targets reales el hit rate
gate-verificado fue **1%**, no ~100%. Detalle y causas abajo; no se tocó código, sólo se
corrió el skill y se documenta el hallazgo.

**Selección de targets**: `sc_plan.py` no filtra por país, así que se filtró
`items.jsonl` a los 1987 items `country == "España"` (100% sourced de "ListadoManga
(colecciones)") a un JSONL temporal y se invocó `sc_plan.py --items <temp> --only-covers`
(y variantes `--include-no-image`/`--retry-failed`) sobre ese subconjunto — mecanismo
soportado sin cambios de código (`--items` ya existía). Con los filtros por defecto (sin
`--retry-failed`) la población ES `--only-covers` daba sólo **101 targets** (14 portada
chica + 87 sin imagen), muy por debajo de los 150 pedidos: **553 de los ~654 targets ES
elegibles ya habían sido intentados hace ≤30 días con 0 matches**, mayormente en una
corrida masiva de `fetch_better_covers.py` (motor de producción, engines `isbn`/`lens`/
`text`) del **2026-08-24** con **869/870 (99,9%) 0-match** sobre ES — no documentada en
este archivo hasta ahora. Como el objetivo explícito de esta tanda era medir
**whakoom-vía-Bing**, un motor que esa corrida de 08-24 NO usó, se decidió correr con
`--retry-failed` para no bloquear la medición por el cooldown de un motor distinto — la
tanda final: **100 portadas chicas** (13.800–60.000 px, las de menor calidad primero) +
**50 items sin imagen**, mezclando `plan_covers_A[:100] + plan_covers_B[:50]` de dos
corridas del planificador.

**Ejecución**: sólo la variante `whakoom` (`site:whakoom.com <serie> <vol>` vía Bing) —
**no** se agotaron las hasta 4 variantes de texto por target ni se probó fallback cuando
whakoom no daba 0 matches (adaptación pragmática por volumen: 150 targets × hasta 4
variantes hubiera sido ~450+ navegaciones). `yandex-reverse` no aplicó a ningún target: los
150 tienen `image_ref_url` en `static.listadomanga.com`, que `sc_plan.py` ya excluye de
esa variante (gotcha #39). Extracción vía `fetch()` en lote desde una pestaña `bing.com`
(mismo origen — un intento inicial desde `static.listadomanga.com`/`i1.whakoom.com` dio 0
resultados por CORS, silenciosamente atrapado por el `try/catch`; hay que fetchear desde
una pestaña ya en `bing.com`), 350–600 ms + jitter entre requests, sin bloqueos ni
captchas en ningún momento. `--serper-fallback` NO se usó (indicado explícitamente).

**Resultado, desagregado por tipo de target** (única vía: whakoom-por-Bing):

| Segmento | n | Candidatas con `verified:true` (gate `_same_cover` real) | Candidatas `verified:false` (sin referencia, revisión estricta) |
|---|---|---|---|
| Portada chica (13.800–60.000 px, CON referencia) | 100 | **1 (1%)** | 0 |
| Sin imagen (SIN referencia) | 50 | 0 | **50 (100%)** |

**El 1% del segmento con referencia, no el "100%" del segmento sin referencia, es la
cifra comparable con el 8/8 del piloto** (ambos con `_same_cover` corriendo de verdad).
Muestreo manual de 3 rechazos confirmó que whakoom SÍ encuentra la página/serie correcta
(ej. Meaheim vol. 1 — mismo personaje, misma pose, mismo arte que la portada JP original)
pero `_same_cover` la rechaza por venir de una edición/logo distinto al de la portada ES
capada por listadomanga — el gate funciona como está diseñado (precisión > recall), pero
para portadas de baja resolución esa exigencia entierra casi todo. Combinado con el
hallazgo de "Etapa 1" (arriba, misma fecha): el 91,2% de los items con área <90.000 px
**se ven bien en la card real** (factor de reescalado <1,6×) — la métrica de "necesita
mejora" que alimenta `sc_plan.py` sobre-selecciona portadas que ya están bien, así que
gran parte de esta tanda buscó mejoras para portadas que no las necesitaban. Esto, más que
un mal desempeño de whakoom, explica el 1% frente al 8/8 del piloto (que probablemente
usó items curados a mano, no una muestra representativa del área<90k real).

**El "100%" del segmento sin imagen es una señal MUCHO más débil de lo que parece — no
tratarla como hit rate.** Sin referencia, `sc_validate.py` sólo exige aspect-ratio +
`candidate_metadata_conflict` + `_is_soft_image` (sin `_same_cover`, por diseño — no hay
con qué comparar) — así que casi cualquier imagen plausible de whakoom pasa. Cruzando las
94 candidatas de este segmento por `new_url`: **36 de los 50 items (72%) tienen al menos
una candidata cuya URL es idéntica a la de OTRO item de la misma serie con OTRO volumen**
(ej. la misma imagen propuesta para Bastard!! tomos 2, 4, 6, 7, 8 y 9; para Bleach tomos 5,
6, 8, 14, 16, 17 y 20; para Tokyo Revengers en 5 pares) — matemáticamente no pueden ser
todas correctas: whakoom-vía-Bing devuelve con frecuencia la miniatura de la SERIE o de
OTRO tomo cuando la query de un tomo específico no tiene página propia indexada, y sin
imagen de referencia no hay forma automática de detectarlo. **Recomendación fuerte: el
owner debería revisar estas 50 entries con más escepticismo que las `verified:true`
normales**, y las series con candidatas repetidas (Bastard!!, Bleach, Tokyo Revengers,
Shangri-La Frontier) son las de mayor riesgo. Ver gotcha #173.

**Cola**: `sync_cover_preview.py --dry-run` post-tanda → 0 operaciones inesperadas, las 58
entries/60 pendientes previas (cierre del 2026-09-01) intactas; 51 entries nuevas / 95
candidatas pending agregadas por esta tanda (109 entries / 155 pending en total). `pytest`
de `sc_plan`/`sc_validate`/`sc_flush` verde (40 tests). Tiempo total ~50 min (incluye
investigación del falso-cero inicial, ver gotcha #173).

**Recomendación numérica para tandas siguientes**: NO escalar ES completo con el criterio
actual tal cual. Antes: (1) aplicar el corte de "Etapa 1" (`min(300/w,420/h) >= 1,6` en vez
de área<90.000) para no re-buscar portadas que ya se ven bien — reduciría el universo de
"portada chica" en ~90%; (2) para el segmento sin imagen, considerar un guard adicional en
`sc_validate`/`sc_flush` que baje la confianza (o descarte) una candidata `verified:false`
cuya URL ya se propuso para OTRO slug de la misma tanda — barato de implementar, cierra el
72% de riesgo detectado arriba. `--serper-fallback` NO se recomienda todavía: el cuello de
botella no es la cobertura de búsqueda (whakoom SÍ encuentra las páginas) sino el gate de
identidad sin referencia — Serper Lens tiene el mismo problema estructural para el
segmento sin imagen y factura por búsqueda.

**Desenlace — curación humana de las 94 candidatas `verified:false` (2026-09-02, aplicado en
el cierre de Etapas 1-2)**: el owner revisó desde `cover-preview.html` las 94 candidatas del
segmento sin imagen. Resultado: **12 aprobadas (13%), 82 rechazadas (87%)**. Desglose real de
los 82 rechazos por motivo: **65 (79%) `otra_edicion`** — whakoom SÍ encontró la página/serie
correcta pero de una edición o país distinto al del item ES capado por listadomanga, el mismo
patrón que ya domina el segmento CON referencia; **12 (15%) `no_es_la_obra`**; y sólo **5 (6%)
`otro_tomo`** — el caso puntual que el guard de URL compartida (gotcha #174, abajo) apunta a
mitigar. Esto corrige la lectura original del hallazgo (ver gotcha #173, corrección agregada
el mismo día): **el riesgo dominante NO es la ambigüedad de tomo que delata compartir
`new_url` entre slugs — es la edición/país equivocado**, el mismo problema estructural que el
gate `_same_cover` no puede resolver sin referencia. **Whakoom SÍ tiene la portada correcta
para la inmensa mayoría de estos casos** — el problema no es cobertura, es la VÍA: la búsqueda
de texto `site:whakoom.com <serie> <vol>` vía Bing devuelve con frecuencia la ficha de la
serie o de un tomo vecino en vez de la ficha exacta del volumen+edición; **la vía correcta es
navegar la página de EDICIÓN de whakoom** (serie → edición correcta → tomo), no la búsqueda de
imágenes — recomendación para una futura vía determinística de whakoom, no implementada en
esta tanda. Las 12 aprobadas se aplicaron en el cierre del 2026-09-02 (ver § "Cierre Etapas
1-2" abajo) — las 12 del catálogo ES: Norma Tokyo Revengers ×7 (vols. 1, 2, 10, 11, 12, 15,
16), Panini Bleach ×4 (vols. 9, 12, 14, 15), Planeta Ayako ×1 (vol. 2).

### Validación sin referencia — guard de URL compartida (fix del hallazgo de arriba, 2026-09-02)

La "recomendación numérica" del cierre de la tanda de arriba (punto 2) se implementó el mismo
día. **Por qué en `sc_flush.py` y no en `sc_validate.py`**: `sc_validate.py` valida UN item a
la vez (input/output por llamada) y no tiene visibilidad de qué candidata se le propuso a
OTRO slug de la misma corrida — esa visibilidad cruzada sólo existe en `sc_flush.py`, que ya
acumula candidatas entre flushes en `.tmp_sc_acc.json`. `_apply_shared_url_guard(acc)`
(`scripts/retrofit/sc_flush.py`) corre en CADA flush sobre TODO el acumulador:

1. Agrupa las candidatas no-rechazadas de todos los slugs por la clave canónica de imagen
   (`fetch_better_covers._img_stem(new_url)` — la misma que usa `_union_merge_images` para
   dedupear `images[]`, así que variantes de tamaño/CDN de la misma imagen caen en el mismo
   grupo, no sólo URLs byte-idénticas).
2. Para cada grupo con ≥2 slugs distintos, reusa `fetch_better_covers._extract_candidate_volumes`
   (la misma función que ya usa `candidate_metadata_conflict` — sin duplicar el criterio de
   extracción de tomo) sobre `page_title + new_url` de cada candidata:
   - Si el marcador explícito de tomo coincide con el `volume` del item de **un solo** slug
     del grupo → esa candidata se conserva; las demás quedan `status="rejected"` +
     `reject_reason="otro_tomo"` (auditable en el preview, no desaparecen en silencio).
   - Si no hay forma de desambiguar (sin marcador de tomo en `page_title`/`new_url`, o el
     marcador no resuelve a un único slug) → TODAS quedan `pending` pero con `shared_with`
     (los otros slugs del grupo), `confidence="low"` y `needs_visual_review=True` — **nunca
     se auto-aprueban**.

Idempotente entre flushes de la misma corrida: las candidatas ya `rejected` se excluyen de la
re-agrupación, y si un 3er slug con la misma URL aparece en un flush posterior, `shared_with`
de los primeros dos crece para reflejarlo. El resumen por rama
(`shared_groups`/`kept_disambiguated`/`rejected_otro_tomo`/`unresolved_flagged`) se agrega al
stdout de `sc_flush.py` como `shared_url_guard`. `candidate_metadata_conflict` (ítem 2 del
mismo encargo) ya cubría el caso "item con `volume` conocido + candidata que declara
CLARAMENTE otro tomo" (vía URL o `page_title`) — no necesitó cambios, sólo tests nuevos para
el canal `page_title` (antes sólo probado vía URL). El guard de URL compartida cubre el caso
COMPLEMENTARIO: cuando la candidata NO declara ningún tomo (el caso dominante medido en la
tanda de arriba — los `page_title` de whakoom casi nunca lo llevan) pero se repite en varios
slugs de la misma serie.

**Simulación de sólo lectura sobre la cola real** (2026-09-02, `data/cover_preview.json`
cruzado con `volume` de `items.jsonl`, sin escribir nada): de 139 candidatas `verified:false`
`pending` en 93 slugs, **15 grupos** comparten `new_url` con ≥2 slugs — **0 se pudieron
desambiguar por tomo** (confirma que el caso dominante es el ambiguo, no el conflictivo: los
`page_title` de whakoom casi nunca declaran el tomo explícitamente), **42/139 (30%)** quedarían
marcadas `needs_visual_review`, 97 sin cambios (URL única). Tests:
`tests/test_sc_shared_url_guard.py` (6 casos: desambiguación por tomo, grupo sin desambiguar,
URL única sin tocar, grupo que crece entre flushes, y los 2 casos de `candidate_metadata_conflict`
reusada). Detalle narrativo en `docs/reference/gotchas.md` #173 (hallazgo) y #174 (fix).

### Etapa 2, tanda 2 — corpus completo (JP/KR/ES/MX/IT), 48 targets con el criterio `scale` (2026-09-02)

Primera corrida del skill sobre TODO el corpus (no acotado por país) con el criterio nuevo
de "Etapa 1" (`--target-rule scale`, default desde hoy — factor de reescalado ≥1.6× en vez
de área<90.000 px). `sc_plan.py --only-covers --retry-failed` dio **48 targets** (vs. los
546 que hubiera dado el criterio viejo — confirma la reducción del 91% medida en "Etapa 1 —
la recomendación se aplicó en `sc_plan.py`", arriba). Desglose por país:

| País | Targets | Fuente dominante |
|---|---|---|
| Japón | 25 | JP - Rakuten Books (search) — 19; JP - Sanyodo — 6 |
| España | 11 | ListadoManga (colecciones) — Planeta Cómic |
| Corea del Sur | 6 | KR - Aladin (만화 한정판) |
| México | 1 | MX - Panini México |
| Italia | 1 | IT - AnimeClick |

**Colisión operativa con una purga concurrente (gotcha #178)**: a mitad de la corrida, otra
sesión aplicó el cierre de la Etapa 1 (gotcha #176a) — la regla `.gif` de Rakuten purgó
`images[]` de 68 items del corpus, **15 de ellos eran targets de esta tanda** (más 4 items
expulsados del corpus por el cierre non-manga de gotcha #176b, y 1 con cover reemplazada).
`sc_plan.py` ya había tomado su snapshot, así que el loop de Chrome siguió trabajando sobre
referencias que dejaron de existir a mitad de camino. De los 20 targets afectados: **8 ya
habían sido tocados por el loop** cuando se detectó el drift (comparando el snapshot contra
una relectura de `items.jsonl`) — se cerraron con lo que tenían (candidatas `verified:false`
de baja confianza, ver abajo); los **12 restantes se saltearon sin gastar navegaciones**
(no tiene sentido buscar hi-res para una portada que el corpus ya no tiene). **36 targets
se buscaron con referencia real** (28 sin tocar por la purga + 8 afectados a medio camino).
Detalle del mecanismo en gotcha #178; recomendación de proceso: no correr este skill en
paralelo con `purge_placeholder_images.py`/`mirror_images.py --gc` sobre el mismo corpus.

**Resultado — hit rate `verified:true` (gate `_same_cover` real corrido) por país**,
sobre los 36 targets con referencia utilizable:

| País | Buscados | Hit `verified:true` | Hit rate |
|---|---|---|---|
| Japón | 19 | 4 | 21% |
| Corea del Sur | 5 | 1 | 20% |
| México | 1 | 1 | 100% (n=1) |
| España | 11 | 0 | 0% |
| **Total** | **36** | **6** | **17%** |

**17% real sobre el corpus completo** — muy por encima del 1% de la tanda 1 (España,
criterio viejo de área). Dos factores lo explican: (1) el criterio `scale` deja afuera las
~500 portadas ES que ya se veían bien (gotcha #172/#175) y que dominaban el universo viejo
con 0% de éxito estructural; (2) el universo nuevo es mayormente JP/KR con **referencia
real de baja resolución genuina** (recorte apaisado destruido de Aladin, `.gif` de Rakuten
pre-purga), donde Yandex reverse-image SÍ tiene con qué buscar.

**Vía que produjo cada hit `verified:true`** (de las 6 candidatas ganadoras, leyendo el
campo `query` real, no sólo `engines_used` acumulado — un item agota varias vías antes de
terminar): **5/6 via Yandex reverse-image** (`kowamoto-no-rinjin-ga-omega-ichijinsha-
limited-jp-3` ×3, `cute-aggression-unknown-artbook-jp` ×4, `return-of-the-mount-hua-sect-
unknown-limited-kr-21` ×1, `death-note-panini-boxset-mx` ×2, `travidebla-unknown-artbook-
jp` ×1) y **1/6 vía Bing texto** (`item-75cd876218b5`, query `title_original`, encontró
otra página de Rakuten del mismo producto). **Whakoom-vía-Bing: 0/11 en ES** (Planeta
Cómic/Panini España — mismo patrón que la tanda 1, gotcha #173: whakoom encuentra la
página pero es la edición regular/sin logo especial, `_same_cover` rechaza correctamente).
Confirma la lectura de la tanda 1: Yandex reverse es la vía productiva real cuando hay
referencia útil; whakoom-vía-Bing casi no aporta nada verificado en este corpus.

**Candidatas nuevas en la cola**: 14 entries nuevas / candidatas (109→123 en
`cover_preview.json`), **12 `verified:true`** (los 6 hits de arriba, hasta 3-4 candidatas
ordenadas por cada uno) + **9 `verified:false`** (los 8 items afectados por la purga
concurrente, gotcha #178 — confianza baja, recomendado revisión escéptica reforzada, NO
tratarlas como una vía nueva confiable). `sync_cover_preview.py --dry-run` post-tanda: **0
operaciones inesperadas**, 123 entries sanas.

**Causas de 0-match** (30 targets sin ninguna candidata, de los 36 con referencia real
buscada): mayormente `_same_cover` rechazando correctamente ediciones hermanas/regulares
sin el logo o crop de la especial (el patrón de "regla de oro" del skill funcionando como
está diseñado — precisión > recall), y **un hallazgo nuevo de mecanismo** (gotcha #177):
para 2 items de Aladin (`return-of-the-mount-hua-sect-...-kr-21` en su variante `title`,
`d-gray-man-unknown-limited-kr-6`), la búsqueda SÍ encontró la variante `cover500/` del
mismo producto en el propio CDN de Aladin — **el mismo archivo, 16× más píxeles,
`_same_cover` con distancia Hamming 0** — pero `candidate_metadata_conflict()` la
rechazó igual: interpreta el sufijo `_1`/`_2` del nombre de archivo de Aladin (índice de
foto: portada/contratapa) como si fuera el número de tomo, y como no coincide con
`item.volume`, hard-rechaza una candidata que en realidad es perfecta. Ver gotcha #177 y
`docs/scraper/sources/kr-aladin.md` § "CONFIRMADO: `cover500/`…" para el detalle y la
recomendación de mecanismo (CDN determinístico de Aladin en el motor, antes de pasar por
`candidate_metadata_conflict`).

> **Cerrado 2026-09-02**: ambos fixes de mecanismo aplicados — el heurístico de volumen ya
> no confunde el índice de foto de Aladin (fix en `candidate_metadata_conflict`) y el CDN
> determinístico de Aladin se agregó a `upgrade_image_resolution.py` (patrón `cover<N>/` →
> `cover500/`), evitando el problema de raíz para el pipeline batch. Ver gotcha #177 (cerrada)
> y § "Upgrade de resolución" arriba para los números de la corrida real.

**Recomendación numérica**:
- **`--serper-fallback`: NO todavía.** El cuello de botella medido no es cobertura de
  búsqueda (Yandex+Bing SÍ encuentran páginas relevantes en la mayoría de los 0-match) sino
  (a) el gate de identidad rechazando correctamente ediciones distintas, y (b) el bug de
  mecanismo de gotcha #177 en 2 casos puntuales de Aladin — ninguno de los dos lo resuelve
  Serper Lens (mismo problema de `candidate_metadata_conflict` si la URL viene del mismo
  CDN). Antes de pagar por Lens: (1) arreglar gotcha #177 (o agregar el CDN determinístico
  de Aladin), que probablemente cierra unos pocos más gratis; (2) medir cuántos 0-match
  reales quedan después de eso antes de decidir escalar a pago.
- **Tanda para items SIN imagen (`--include-no-image`)**: no se corrió en esta tanda
  (fuera de alcance, `--only-covers` explícito). La tanda 1 (gotcha #173) ya mostró que ese
  segmento es una señal débil (72% de candidatas compartidas entre tomos de la misma serie,
  sin forma de desambiguar) — el guard de URL compartida (gotcha #174) ya mitiga el riesgo
  de auto-aprobación, pero no lo recomendaría como prioridad sin antes medir si el guard
  reduce el ruido lo suficiente en una muestra chica.
- **Proceso**: coordinar con el owner que este skill y los scripts de purga/GC de
  `data/images/` no corran en paralelo (gotcha #178) — el próximo desperdicio de 12-20
  navegaciones es evitable con sólo secuenciar.

Tiempo total ~35 min (48 targets, loop de Chrome batcheado). Suite de tests de
`sc_plan`/`sc_validate`/`sc_flush` no re-corrida en esta tanda (sin cambios de código).

### Fix de mecanismo: guard de referencia placeholder + anti-drift por hash (2026-09-02, gotcha #179)

Cierre de código para dos hallazgos de la Etapa 2 que hasta acá sólo tenían mitigación
manual: el juez de visión midió **9/9 candidatas basura** cuando Yandex reverse-image usó
como consulta una referencia placeholder (la "tarjeta de título" `.gif` de Rakuten, gotcha
#171 — canvas de tamaño REAL, no cae en el guard `MIN_REF_PX` por tamaño), y la colisión
con una purga concurrente de gotcha #178 (15/48 targets con referencia invalidada a mitad
de la corrida de Chrome).

- **Guard de referencia placeholder** (`scripts/retrofit/sc_plan.py`,
  `reference_placeholder_reason`): reusa `image_store.known_placeholder_url_reason(url)` y
  `image_store.placeholder_reason(bytes)` (las DOS fuentes únicas, sin reimplementar) ANTES
  de aplicar el criterio de calidad (scale/área) — un placeholder nunca es referencia válida
  sin importar su tamaño. Por defecto: skip DURO con contador en el resumen impreso de
  `sc_plan.py` (`Saltados DURO por referencia placeholder: N`). Con `--include-no-image`:
  entra con el campo nuevo `reference_kind` (`"real"`/`"placeholder"`/`"none"`) en
  `"placeholder"` y la referencia de búsqueda blanqueada — para galería (`img_idx >= 1`)
  `candidate_target` (identidad del slot a reemplazar) se conserva intacto, sólo se
  blanquea la referencia de búsqueda/verificación. Como `build_variants()` sólo genera la
  variante `yandex-reverse` con un `ref_url` http utilizable, blanquear la referencia ya
  impide ESTRUCTURALMENTE el reverse contra el placeholder (el SKILL.md además filtra
  defensivamente por `reference_kind` en el Step 3, por si un plan viejo sin el campo llega
  al loop).
- **Guard anti-drift por hash** (`scripts/retrofit/sc_validate.py`,
  `reference_drift_reason`): `sc_plan.py` persiste `reference_sha256` (sha256 del archivo
  local de referencia AL MOMENTO DEL PLAN) en cada target con `reference_kind == "real"`.
  `sc_validate.py` lo recalcula contra el archivo actual — misma resolución que usa
  `validate()` para `curr_bytes`, factorizada a `_resolve_reference_bytes` (fuente única
  dentro del script) — ANTES de tocar la red: si el archivo ya no existe o cambió de
  contenido, `validate()` devuelve `[]` sin descargar ninguna candidata (`main()` reporta
  el motivo en `{"drift": "reference_missing"|"reference_changed"}`). Puramente aditivo:
  sin `reference_sha256` en el payload (plan viejo, o target sin referencia real) el guard
  es no-op. El Step 3 del skill corta el resto de las variantes de un target apenas detecta
  `drift` (no gasta más navegaciones para una referencia obsoleta) y lo registra en
  `cover_search_attempts.jsonl` con un campo `drift` propio, distinguible de un 0-match
  genuino en el log.
- **Dry-run de sólo lectura sobre el corpus real** (`sc_plan.py --retry-failed`, criterio
  `scale` default, portada+galería): **3 targets** saltados DURO por referencia placeholder
  de 569 candidatos totales. La mayoría de los ~50 `.gif` de Rakuten identificados en
  gotcha #171 ya habían sido purgados del corpus por el cierre de gotcha #176a antes de
  esta tarea (68 items, ver arriba) — estos 3 son casos nuevos/remanentes que entraron o
  quedaron sin purgar desde entonces.
- Tests: `tests/test_sc_plan.py` (skip por URL `.gif` de Rakuten, skip por firma de
  contenido, `reference_kind`/`reference_sha256` correctos para referencia real, galería
  preserva `candidate_target` pero blanquea la referencia de búsqueda) y
  `tests/test_sc_validate.py` (sin `reference_sha256` no bloquea, detecta
  `reference_changed`/`reference_missing`, `validate()` corta ANTES de la red con drift,
  camino feliz sin drift no se rompe). Suite completa verde (2443 tests) tras el cambio.
  Detalle completo en gotcha #179.

### Motor de portadas — gates endurecidos + ledger de rechazos (2026-07-08)

Paquete de fixes al MOTOR (`fetch_better_covers.py`), post-auditoría + red team. Toda la
lógica de identidad/calidad vive en el motor (fuente única); `sc_validate.py` DELEGA.

- **Ledger de rechazos + denylist** (`data/cover_rejections.jsonl`, append-only, local): cada
  vez que `apply_preview()` marca una candidata `rejected`, se apendea `{slug, action, target,
  rejected_url, a_hash (hex del archivo o null si ya no existe), match_dist, ref_pixels,
  new_pixels, page_title, query, reason, rejected_at}` ANTES de borrar el archivo. `sync_cover_preview`
  también lo apendea cuando dropea una entry entera con candidatas rechazadas por slug
  desaparecido. Los records incluyen `url` (identidad secundaria canónica del item, estable a
  re-slugs — ver "paquete R" abajo). `fetch_better_covers.is_rejected_candidate(slug, url,
  a_hash_hex, ledger, item_url=…)` es la fuente única de la denylist, consultada por
  `_process_item` (URL antes de descargar, hash después), por la búsqueda manual del gestor
  (`serve._handle_image_search`) y por `sc_validate` (delegando); matchea una entrada por **slug O
  url canónica** (`item_url`). **Política EXACTA del veto por hash** (decisión
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
  (bytes descargables + px ≥ `SAME_COVER_MIN_REF_PX` = 10 000, donde `_same_cover` es fiable): lens y text EXIGEN
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
  relee el disco y funde vía `_merge_preview_entries`: (a) candidata en memoria decidida en
  disco → conserva status + reviewed_at + reject_reason de disco (nunca la resucita como
  pending); (b) candidatas/entries de disco que el motor no tiene → se conservan.
  `apply_preview()` escribe con `merge=False` (ya es autoritativo sobre el estado final).
  **Clave de matching (gotcha #168, 2026-09-01)**: `_candidate_identity(c) = (action, target,
  new_url)`, NO `new_url` pelado — `new_url` significa cosas distintas según `action`
  (en `remove_image` es la imagen a ELIMINAR; en el resto, la imagen NUEVA propuesta), así
  que dos candidatas de acciones distintas pueden compartir el mismo `new_url` por
  coincidencia; matchear sólo por eso fundía ambas como "la misma" y perdía la de disco (caso
  real: `bleach-christmas-variant-panini-cofanetto-it-1`, ver gotcha #168 para el detalle
  completo y la reparación). `_dedupe_candidates()` colapsa candidatas con la misma identidad
  si un merge llegara a duplicarlas (gana la ya decidida sobre cualquier pending duplicada).
  **Paridad real con `sc_flush.py` (SC-7, 2026-07-11)**: el flush del skill NO tenía este
  mecanismo — no tomaba lock cross-proceso ni relee el disco en cada flush, y sólo rescataba
  las candidatas revisadas en el PRIMER flush de un slug, así que una aprobación del owner hecha
  DESPUÉS de ese primer flush se pisaba (last-writer-wins) el resto de la corrida. Ahora
  `sc_flush.py` IMPORTA y reutiliza `preview_write_lock` + `_merge_preview_entries` de
  `fetch_better_covers` (fuente única, no copia): mismo lock sobre `cover_preview.json.lock` y
  mismo merge que preserva status/reviewed_at/reject_reason de disco en CADA flush. La paridad
  que este doc afirmaba ahora existe de verdad.
- **Dos umbrales de referencia nombrados (SC-9, 2026-07-11)**: son conceptos DISTINTOS que antes
  vivían como literales pelados duplicados (`MIN_REF_PX = 2 500` en `sc_plan`, un `10 000` inline
  en `_process_item`), con riesgo de drift bajo `--serper-fallback`. Ahora ambos tienen nombre en
  `fetch_better_covers` (fuente única) y `sc_plan` importa el suyo: **`MIN_REF_PX` (2 500)** = piso
  de "referencia NO degenerada" (por debajo es un placeholder 1×1 roto → el plan saltea el target);
  **`SAME_COVER_MIN_REF_PX` (10 000)** = piso de "referencia utilizable para `_same_cover`" (por
  debajo, pero por encima de `MIN_REF_PX`, la referencia existe pero es muy chica para hashear con
  confianza → el motor la trata como "sin referencia" y cae al gate degradado). La banda 2 500–10 000
  px es justo donde difieren: usable como pista de búsqueda, insuficiente para `_same_cover` estricto.
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

### Motor de portadas — paquete R (remediación, auditoría Fable 2026-07-08)

Cinco hallazgos que el cross-check de cobertura confirmó FALTANTES. Tests:
`tests/test_remediacion_20260708.py` (+ suites de portadas sin regresiones).

- **Identidad secundaria de la cola y del ledger (url canónica, #7)** — la MÁS importante. Antes
  la cola (`cover_preview.json`) matcheaba las entries contra el catálogo **sólo por `slug`**, y el
  ledger de rechazos se keyeaba `(slug, rejected_url)`. Un **re-slug** (`generate_slugs` tras
  cambios de serie/edición) rompía ambas cosas: (a) las decisiones pendientes/aprobadas del owner
  se perdían como "item borrado" (Regla 1 de `sync_preview` las podaba), y (b) el veto del ledger
  se neutralizaba (la URL rechazada se re-ofrecía bajo el slug nuevo). **Fix**: cada entry de la
  cola guarda además `url` = **campo top-level `url` del item** (estable a re-slugs), seteado al
  crearse (`run()`), preservado por `_normalize_preview_entry`, y **backfilleado al vuelo** por
  `sync_preview` cuando el slug SÍ matchea (entries legacy). El matching de `sync_preview` intenta
  slug primero; si el slug ya no existe, busca por `url` en el índice `items_by_url` y, si la
  encuentra, **MIGRA el slug de la entry al nuevo** (logueado a stderr, `stats["slug_migrated"]`)
  en vez de podarla. El **guard del 20%** (`catalog_is_sane`) cuenta como "match" también las
  entries rescatadas por url. El **ledger**: los records nuevos (creados por `apply_preview` y por
  `sync_cover_preview._ledger_record_from_candidate`) guardan `url` canónica; `is_rejected_candidate(
  slug, url, a_hash_hex, ledger, item_url=…)` matchea una entrada cuando coincide el **slug O la
  url canónica** — el veto sobrevive el re-slug. **Compat hacia atrás**: records/entries viejos sin
  `url` siguen matcheando sólo por slug (comportamiento idéntico al previo). El ledger y la denylist
  NUNCA se debilitan — este cambio los FORTALECE ante re-slugs.
- **Lock cross-proceso del preview (TOCTOU, #14)** — `_write_preview(merge=True)` relee el disco,
  funde y renombra; entre el read y el replace, un save del owner desde el panel podía perderse. El
  `@_serialized` de serve sólo cubre request-vs-request dentro del proceso de serve, no el proceso
  separado del motor. **Fix**: `fetch_better_covers.preview_write_lock(path)` — un `fcntl.flock`
  EXCLUSIVO sobre `cover_preview.json.lock`, reentrante en el mismo hilo (RLock + un fd mientras la
  profundidad > 0), timeout 10 s, mismo patrón que `items_write_lock` de manga_watch. Lo toma
  `_write_preview` sobre TODO el intervalo read→merge→replace, y serve toma el MISMO archivo con su
  helper (`_preview_write_lock`) alrededor de sus escrituras del preview: el save del panel
  (`_handle_save_cover_preview`, guard de mtime incluido) y el persist del GET
  (`_handle_cover_preview_get`). Así una decisión del owner cae ENTERA antes o después del merge del
  motor, nunca en el medio. No-op cross-proceso si `fcntl` no existe (Windows) — el RLock igual
  serializa in-proceso.
- **`--include-upscaled` deja de ser no-op (#9)** — el flag marca como candidatos los PNG
  upscaleados por waifu2x (px ≥ 200k, look pastel) para buscarles el original real, PERO
  `_process_item` early-returnea con `curr_px >= min_pixels` ANTES de que la rama de relajación
  (`is_upscaled_item and cand_px >= 50_000 → effective_gain = 0`) se ejecutara → la condición
  `px≥200k Y px<90k` era imposible. **Fix**: `_process_item` recibe `include_upscaled` y el early
  return pasa a `curr_px >= min_pixels and not (include_upscaled and is_upscaled_item)`. El flag
  tiene caso de uso real (la maquinaria de `effective_gain=0` existe justo para esto), así que se
  ARREGLÓ, no se eliminó.
- **La búsqueda manual del gestor filtra contra el ledger (#19)** — `serve._handle_image_search`
  re-ofrecía URLs ya rechazadas por el owner. **Fix**: el panel manda `slug` + `item_url` (url
  canónica) del item que se está editando; el handler filtra los resultados con
  `is_rejected_candidate` (misma fuente única, match por URL exacta; slug O item_url → sobrevive
  re-slugs) y devuelve `hidden_by_ledger` (contador de ocultas, que el panel muestra en el toast
  "N ocultas por rechazos previos"). Fail-open de UI: ante cualquier error del ledger no oculta nada.
- **`normalize_release_dates._DMY_FAMILY` exige el mismo separador** — el patrón aceptaba
  separadores mixtos (`"12-05/2024"`) y disparaba un falso `[WARN] rango inválido`. **Fix**:
  backreference `^\d{1,2}([/.\-])\d{1,2}\1\d{4}$` — una fecha con separadores mixtos ya no es
  DD/MM/YYYY legítimo y cae al reporte de "otros formatos" sin tocarse.

**Invariantes**:
- Candidatas: `confidence: "low"`, `status: "pending"` — sin excepción.
- **Identidad de la cola/ledger**: `slug` (primaria) + `url` canónica top-level del item
  (secundaria, estable a re-slugs). El matching y el veto usan AMBAS; un re-slug migra la entry y
  preserva el veto, nunca los pierde.
- Dos scripts son **permanentes** (nunca borrar ni reimplementar inline):
  - `scripts/retrofit/sc_validate.py` (tests: `tests/test_sc_validate.py`) — validación de
    identidad de imagen; la copia embebida que había drifteó de producción y causó falsos
    positivos pre-2026-06-11.
  - `scripts/retrofit/sc_flush.py` (tests: `tests/test_sc_flush.py`) — flush self-healing al
    `cover_preview.json`; el código inline que lo reemplazó reconstruyó dicts a mano y perdió
    el campo `new_image` en 8 candidatas (2026-06-11). El script rechaza con exit 1 cualquier
    candidata sin `new_image`/`new_url`, cuyo `new_image` no exista en el espejo local
    (`--images-dir`), o a la que le falte un campo de proveniencia que `sc_validate` emite SIEMPRE
    (`new_pixels`/`verified`/`confidence`/`status`/`match_dist`) o lo traiga con el tipo
    equivocado (SC-2, 2026-07-11) — guarda estructural contra dicts reconstruidos o fabricados.
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
- Flags: `--limit N`, `--slug SLUG`, `--only-covers`, `--gallery-only`, `--include-no-image`,
  `--retry-failed`, `--query-extra "texto"` (`--include-gallery` sigue aceptado pero es no-op:
  la galería ya se procesa por defecto).
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
  ledgerea cuando el owner la aplica. Idempotente: status ≠ pending o pending-con-`verified` **y
  evidencia vigente** no se reprocesan → correr 2× = JSON byte-idéntico. Backup + escritura atómica.
- **Guard por `action` (gotcha #167, 2026-09-01)**: sólo candidatas cuya `action` traiga una imagen
  NUEVA externa (`fetch_better_covers.NEW_EXTERNAL_IMAGE_ACTIONS`) pasan por el gate de identidad/
  calidad — `remove_image`/`replace_cover_demote` quedan intactas (contador `skipped_by_action`),
  mismo criterio que `prune_soft_cover_candidates.py`.
- **Evidencia stale (gotcha #167, 2026-09-01)**: la referencia usada para `_same_cover` ya no es el
  `old_image` CONGELADO del preview de entrada — se resuelve vía `sync_preview()` contra la portada
  ACTUAL del item (`item.images[0]`, delegación pura, sin lógica nueva). Si una candidata `pending`
  ya tenía `verified`/`match_dist` calculados contra un `old_image` que se purgó del disco (ola de
  limpieza posterior) o que dejó de ser la portada del item (otra `action` la reemplazó), se limpian
  esos campos y se re-valida contra la portada ACTUAL (contador `stale_evidence_recomputed`) en vez
  de saltarse para siempre por la regla de idempotencia.
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

### Header de tarjeta — título arriba, controles abajo (`cover-preview.html`, 2026-08-26)

`.card-header` era una sola fila flex (título + badge + 4 botones). Con títulos largos sin
espacios (japonés/chino: p.ej. `月刊少女野崎くん（18）特装版 セレクト小冊子「堀と鹿島編」付き
（SEコミックスプレミアム）`), `min-width:0` en `.card-title` dejaba que el flex item se
comprimiera hasta ~1 carácter de ancho; sin `white-space:nowrap` el `text-overflow:ellipsis`
no aplicaba, y el line-breaking CJK (permite cortar entre cualquier par de caracteres) convertía
el título en una columna vertical ilegible que además estiraba la tarjeta. Fix: `.card-header`
pasó a `flex-direction:column` en dos filas — fila 1 = `.card-title` a ancho completo (ya no
flex item comprimible; `-webkit-line-clamp:3` + `overflow-wrap:break-word` en vez de
nowrap+ellipsis, así corta prolijo a 3 líneas con el `title` completo disponible en el hover del
`<a>`); fila 2 = `.card-header-controls` (badge + 👎 Reportar + Excluir + ✕ Rechazar pend. +
toggle ▾/▸, este último con `margin-left:auto` para quedar a la derecha). No cambió ningún
handler (`toggleReport`/`flagIrrelevant`/`rejectEntryPending`/`toggleCollapse`) ni el resto del
markup de la tarjeta.


## 2026-08-29 — el paso 4e (`backfill_metadata --only image_url`) NUNCA termina: rc=124 crónico

El paso 4e del delta (`backfill_metadata.py --only image_url`, "rellena portadas
faltantes") viene siendo **matado por su timeout de 1800s en 6 corridas consecutivas**:

| Corrida | rc |
|---|---|
| `scrape-delta-2026-08-24-183301` | 124 |
| `scrape-delta-2026-08-25-110223` | 124 |
| `scrape-delta-2026-08-26-110228` | 124 |
| `scrape-delta-2026-08-28-160959` | 124 |
| `scrape-delta-2026-08-29-110244` | 124 |
| `scrape-delta-2026-08-30-111729` | 124 |
| `scrape-delta-2026-08-31-110202` | 124 |

**Por qué importa más de lo que parece.** El paso hace **un HTTP por item** sobre todos
los que no tienen portada, y no hay evidencia de que procese la cola en un orden estable,
así que un kill a los 30 minutos no es "termina el 80%": es *se corta donde llegó*. Si el
orden es estable, además, **la cola de la lista nunca se toca** — habría items que jamás
van a recibir portada por este camino, corrida tras corrida. Eso es consistente con que
`data/cover_preview.json` se mantenga estancado en ~413 pendientes.

**Lo que NO se puede afirmar todavía**: cuántos items quedan sin procesar por corrida, ni
si el corte es determinístico. El log (`04e-backfill-images.log`) sólo deja las líneas
`[ISBN_ANOMALY]` y muere sin resumen — **no imprime cuántos items vio ni cuántos le
faltaron**, que es justo el dato que haría falta.

**Para el owner (no aplicado — es decisión suya).** Tres opciones, de menor a mayor
esfuerzo:
1. **Instrumentar primero** (barato y sin riesgo): que el paso emita progreso/resumen
   periódico, para saber si le faltan 50 items o 5000 antes de decidir nada.
2. **Subir el timeout** — es lo que se hizo con Mangavariant (1200s→1800s→3600s). Sirve
   sólo si la cola es finita y cabe; si crece con el corpus, patea el problema.
3. **Hacerlo resumible/incremental** (marcar los items ya intentados y arrancar por los
   no vistos), que es la única opción que sobrevive al crecimiento del corpus.

### Actualización 2026-08-30 — 6ª corrida, y la cola de portadas confirma el estancamiento

`scrape-delta-2026-08-30-111729`: rc=124 otra vez, mismos 1800s consumidos, mismo log sin
resumen (sólo líneas `[ISBN_ANOMALY]`). Dato nuevo que refuerza la hipótesis del corte
fijo: **`data/cover_preview.json` sigue en 413 pendientes**, exactamente el mismo número
que antes de la corrida — el paso corrió media hora y no movió la aguja en la cola de
portadas por aprobar.

En positivo, el espejo local sí trabajó: la FASE 1 descargó **4071 portadas nuevas**
(32 fallidas) por la vía normal del scrape. O sea que el problema está acotado al paso 4e
(relleno retroactivo de items viejos sin portada), no a la ingestión de portadas nuevas.

Las 3 opciones para el owner no cambian; la nº1 (instrumentar antes de decidir) sigue
siendo la más barata y ahora tiene 6 corridas de evidencia detrás.

### Actualización 2026-08-31 — 7ª corrida, cola de portadas clavada en 413 por 2º día

`scrape-delta-2026-08-31-110202`: rc=124 otra vez, mismos 1800s, mismo log sin resumen.
`data/cover_preview.json` sigue en **413 pendientes** — idéntico al 08-29 y al 08-30, o
sea que van **tres corridas seguidas (90 minutos de cómputo) sin mover un solo item** de
la cola de portadas por aprobar. Eso ya no es "lento": el paso no está produciendo salida
útil, sólo consumiendo el timeout.

Sigue en pie el contraste: la FASE 1 descarga portadas nuevas sin problema; lo que no
avanza es el relleno retroactivo del paso 4e.

Con 7 corridas de evidencia, la opción nº1 (instrumentar) dejó de ser la más informativa:
si la cola no se mueve en 3 corridas, la pregunta "¿le faltan 50 o 5000?" importa menos
que "¿está avanzando algo?" — y la respuesta observable es que no. La opción más barata
ahora es **sacar 4e del delta** (o bajarle drásticamente el timeout) y correrlo aparte
cuando el owner quiera, recuperando 30 min de cada corrida diaria. Decisión del owner.

### Actualización 2026-09-02 — el paso 4e TERMINÓ: rc=0 en 1742s, corta la racha de 7

`scrape-delta-2026-09-02-110142`: **`backfill_metadata --only image_url` terminó solo**,
con `rc=0` en **1742s** — 58 segundos por debajo del timeout de 1800s. Primera vez desde
el 2026-08-24; rompe la racha de 7 corridas consecutivas en rc=124.

Lo que esto dice y lo que NO dice:

- **Lo que dice**: la cola SÍ es finita y hoy entró en la ventana. La hipótesis "la cola
  crece sin techo con el corpus" queda debilitada; la hipótesis "está justo en el borde
  del timeout" queda reforzada.
- **Lo que NO dice**: que esté resuelto. Terminar con 3% de margen no es holgura — es
  suerte. Cualquier corrida con más items sin portada (un full, o un delta grande) vuelve
  a pasarse. El log sigue sin emitir progreso ni resumen, así que seguimos sin saber
  cuántos items procesa realmente.

**No cambia la recomendación al owner**: la opción 1 (instrumentar el progreso) sigue
siendo la barata y la que convierte esto en un dato en vez de una inferencia, y la
opción 3 (hacerlo resumible) sigue siendo la única que sobrevive al crecimiento del
corpus. Que una corrida haya entrado por 58s no es evidencia de que el mecanismo esté
sano.

### Actualización 2026-09-11 — el "borde del timeout" confirmado: alterna rc=0 / rc=124

Serie reciente del paso 4e: 09-02 rc=0 (1742s) · 09-07 rc=124 · **09-08 rc=0 (1646s)** ·
09-09 rc=124 · **09-11 rc=124** (1800s, `04e-backfill-images.log` vacío, 0 bytes). Con
deltas de tamaño parecido (+12 a +27 items netos) el paso termina un día y se corta al
siguiente, lo que confirma la lectura del 09-02: la cola es finita pero vive pegada al
timeout, y el resultado depende de la latencia de las fuentes ese día, no del tamaño del
lote. El log sigue sin emitir nada, así que todavía no se sabe cuántos items procesa. La
recomendación no cambia (instrumentar progreso primero, hacerlo resumible después).

## Cierre Etapas 1-2 (2026-09-02) — aplicación de la cola + balance

Cierre del ciclo de Etapa 1 (triage de visión, purga de denylist) + Etapa 2 (búsqueda con
`/watch-search-covers`, tandas 1 y 2) documentado arriba. Este turno es el ÚNICO escritor de
`items.jsonl`/`cover_preview.json` durante la corrida; usa los locks canónicos heredados de
los scripts, no implementa nada nuevo.

**PASO 1 — integridad previa (read-only)**: `pytest` 2451 verdes (igual a la baseline),
`validate_corpus.py` 0 violaciones duras (mismos warns preexistentes), `sync_cover_
preview.py --dry-run` sobre las 123 entries vigentes reportó exactamente **1 candidata
podada** (slug no existe: `item-75cd876218b5`, expulsado como non-manga en el cierre de la
Etapa 1, gotcha #176b) y **44 exentas de la poda 3b** (gotcha #166, sin cambios). De las 18
entries con candidata `approved`, una (`return-of-the-mount-hua-sect-unknown-limited-kr-21`)
ya se sabía redundante por la nota operativa de gotcha #177 — la portada nativa de Aladin ya
había sido mejorada a los mismos ~240 000 px por `upgrade_image_resolution.py` el mismo día,
antes de que esta candidata (`ae04.alicdn.com`) se aplicara. Por diseño, `sync_cover_
preview.py` no poda `approved` (son intocables) — se dejó que el apply la procesara igual, tal
como anticipaba la nota.

**PASO 2 — sync real**: `sync_cover_preview.py` sin `--dry-run`, backup automático en
`cover_preview.json.pre-sync-cover-preview-bak`. Resultado idéntico al dry-run: 1 poda (la
huérfana), 123→122 entries, 1 archivo huérfano del espejo (`d9df2327064906f4.avif`) borrado
por el propio GC del sync.

**PASO 3 — aplicación de la cola**: backup manual de `items.jsonl` (sufijo
`pre-apply-etapa2`) + backup automático del script (label `apply-preview`), luego
`fetch_better_covers.py --apply-preview` en real (un `--dry-run` previo confirmó el mismo
resultado). Preview de entrada: 122 productos, 175 candidatas (17 aprobadas / 97 rechazadas
sin ledgerear todavía / 61 pendientes).

| Acción | Resultado |
|---|---|
| Reemplazos de portada (`replace_cover`) | **17 aplicados** (5 imágenes viejas huérfanas eliminadas del espejo) |
| Agregadas a galería | 0 |
| Rechazadas al ledger (`data/cover_rejections.jsonl`) | 97 (235→332 filas; 69 imágenes candidatas huérfanas eliminadas del espejo) |
| Pendientes remanentes | 61 candidatas en 59 entries |

**Verificación post-apply, releyendo `items.jsonl` (gotcha #163)**:
- **(a) 0 regresiones de portada**: comparación campo-a-campo contra el backup
  `pre-apply-etapa2` de los 14 345 items — ningún item que tuviera `images[0].local`
  usable antes se quedó sin él después; 0 archivos referenciados por `images[0].local`
  faltantes en disco.
- **(b) Las 17 aplicadas, verificadas una por una (no sólo muestreadas)**: 16/17 mejoraron
  píxeles reales (12 items sin portada previa pasaron a tenerla; 4 con portada previa
  mejoraron — death-note-panini-boxset-mx 21 760→603 681 px, cute-aggression-unknown-
  artbook-jp 1 039 200→1 848 000 px, kowamoto-...-jp-3 460 000→739 328 px); **1 redundante
  sin cambio real** (`return-of-the-mount-hua-sect-...-kr-21`, 240 000→240 000 px — la
  nota operativa de gotcha #177 se confirmó exacta, aplicó por diseño sin downgrade); y
  **1 DOWNGRADE real detectado y revertido** (`travidebla-unknown-artbook-jp`, ver abajo).
- **(c) 0 candidatas `approved` sin aplicar**: post-apply, `cover_preview.json` quedó en
  0 `approved` / 61 `pending` / 0 `rejected` (los 97 rechazos ya sólo viven en el ledger).
- **(d) Imagen duplicada dentro de `images[]` introducida por este apply: 0** — se comparó
  el set de items con `local`/`url` duplicados dentro de `images[]` ANTES y DESPUÉS del
  apply: **idéntico (109 items, mismo set exacto)**, así que el apply de hoy no introdujo
  ninguna. Ese set de 109 SÍ es un hallazgo nuevo — ver "Bug encontrado (no corregido acá)"
  abajo.

**Bug encontrado: downgrade real por candidata redundante desactualizada
(`travidebla-unknown-artbook-jp`)**. La candidata aprobada (`animate.shop`, hallada por
Yandex reverse-image en la Etapa 2 tanda 2, `match_dist=0` — visualmente idéntica) reemplazó
una portada que, ENTRE el momento de la búsqueda/aprobación y este apply, ya había sido
mejorada por otro proceso del mismo día: el patrón #11 de `upgrade_image_resolution.py`
(gotcha #180, familia `r10s.jp` de Rakuten) había subido la portada nativa de
`tshop.r10s.jp` a **850×1200 = 1 020 000 px**. La candidata aprobada (misma imagen,
`match_dist=0`) traía sólo **600×847 = 508 200 px** — un downgrade real del 50%. El
`--apply-preview` no re-valida ganancia de píxeles al aplicar una candidata `approved` (el
gate de ganancia corre en `sc_validate`/aprobación, no en apply) — dos referencias
"correctas" en momentos distintos, ninguna re-chequeada contra la otra. **Acción tomada,
tal como indica el protocolo de esta tarea (no arreglar el mecanismo de fondo)**: se
revirtió sólo este item desde el backup `pre-apply-etapa2` (imagen vieja re-descargada con
`image_store.download_image()` — mismo stem `7870c3e3dcaefb2d.avif`, bytes idénticos
recuperados de la fuente remota ya que el archivo local había sido borrado por el propio
apply; la imagen nueva redundante se movió a `data/images/_orphans/`). **Recomendación de
mecanismo para el owner**: `apply_preview()` debería re-comparar píxeles del `local` actual
vs. la candidata al momento de aplicar (no sólo al momento de aprobar/validar), igual que ya
hace `upgrade_image_resolution.py` con su `--min-gain` — mismo patrón que
`_try_upgrade`/gotcha #131, pero en el motor de aprobación humana en vez del batch
determinista. No implementado en este cierre (fuera del alcance de la tarea asignada).

> **CERRADO (2026-09-02, gotcha #182).** `_no_gain_at_apply()` en
> `fetch_better_covers.py` re-lee la portada ACTUAL de disco al momento de aplicar
> (no el `old_pixels` congelado) para `replace_cover`/`replace_cover_demote`/
> `replace_and_add`; si no hay ganancia real, la candidata vuelve a `pending` con
> `invalid_reason="no_gain_at_apply"` en vez de aplicarse a ciegas — el caso
> `travidebla-unknown-artbook-jp` de arriba ya no puede volver a ocurrir. Detalle,
> excepción de placeholder y tests en gotcha #182.

**Bug encontrado (no corregido acá): 109 items / 151 entradas con imagen literalmente
duplicada dentro de `images[]`, 100% `KR - Aladin (만화 한정판)`.** Detectado al verificar (d)
arriba — pre-existente ANTES de este apply (idéntico en el backup `pre-apply-etapa2`), así
que no lo causó la aplicación de la cola. El patrón: la MISMA URL `cover500/…` (post-upgrade
del patrón #10 de `upgrade_image_resolution.py`, gotcha #177) aparece dos veces en el mismo
`images[]`, típicamente en la posición 0 y en la última — ej.
`fullmetal-alchemist-universe-limited-kr` tiene `[cover500/..._1.jpg, letslook/..._f.jpg,
letslook/..._b.jpg, cover500/..._1.jpg]` (índices 0 y 3 idénticos). Coincide en el tiempo con
la corrida de hoy `upgrade_image_resolution.py --host aladin.co.kr` (gotcha #177, 297
mejoradas) — hipótesis de mecanismo (no confirmada): el union-merge que reescribe la entry
`cover<N>/` a `cover500/` no dedupeó contra otra entry que YA apuntaba a la misma imagen
final (posible re-scrape/flush previo con la URL ya normalizada). También lo confirma el
panel: `data_quality.py` ya lo reporta como "Foto repetida en el carrusel: 151" en
`data/quality_report.json` regenerado en este cierre — no es invisible, sólo no se había
investigado su causa hasta ahora. **Fuera del alcance de esta tarea** (mecanismo de imágenes
de Aladin, no de la cola de portadas) — flaggeado como tarea aparte para el owner.

> **CERRADO (2026-09-02, gotcha #181).** Hipótesis CONFIRMADA con datos reales del
> backup `items.jsonl.pre-aladin-upgrade-bak`: `images[0]` (portada) ya estaba en
> `cover500/` por un camino previo (JSON-LD/og:image) mientras una entry de galería
> distinta apuntaba al MISMO archivo bajo `cover150/`/`cover200/` — URLs textualmente
> distintas hasta que el upgrade normalizó ambas al mismo `cover500/`. Fix de
> mecanismo: `dedupe_item_images()` en `upgrade_image_resolution.py`, corrida
> por-item apenas `_apply_upgrade` toca un item. Reparación del dato: **156 items /
> 161 entradas** (151 Aladin + 5 más fuera de Aladin que el mismo mecanismo general
> encontró por sha256 idéntico — Mangavariant/Star Comics/Rakuten — verificado que
> la verificación pedida, "0 duplicados por url y por sha en TODO el corpus",
> exigía cubrirlos también). El conteo verificado (151 Aladin) difiere del "109"
> estimado acá — ver detalle y la reconciliación en gotcha #181.

**PASO 4 — verificación final**: `pytest` 2451 verdes (segunda corrida, post-apply + post-
revert), `filter_non_manga.py --dry-run` 0 rechazos, `validate_corpus.py` 0 violaciones
duras (mismos warns), `sync_cover_preview.py --dry-run` final en **0 cambios** (59 entries,
61 pendientes), `data/quality_report.json` regenerado con `scripts/audit/data_quality.py`
(1181 alertas en 14 categorías, sin flags nuevos más allá de lo ya conocido).

**Balance — baseline 2026-08-31 → cierre 2026-09-01 → cierre 2026-09-02 (hoy)**:

| Métrica | Baseline 08-31 | Cierre 09-01 | Cierre 09-02 (hoy) | Δ vs. 09-01 |
|---|---|---|---|---|
| Items totales | 14 305 | 14 353 | **14 345** | −8 (expulsiones non-manga del cierre Etapa 1, gotcha #176b, y su sync) |
| Portada <90 000 px | 754 | 579 | **513** | −66 |
| Portada sin espejo local | 307 | 35 | **35** | 0 |
| Portadas malas (área o sin local) | 1 061 | 614 | **548** | −66 |
| **Portada con `cover_upscale_factor ≥ 1.6`** (criterio nuevo de Etapa 1) | n/d (criterio no existía) | n/d | **12** | — |
| Items sin ninguna imagen (`images: []`) | — | — | **482** | — |
| Items sin imagen usable (incl. sin local) | 448 | 439 | **517** | +78 (ver nota) |
| `cover_preview.json` — entries | 413 | 58 | **59** | +1 |
| `cover_preview.json` — candidatas pending | 245 | 60 | **61** | +1 |
| Ledger `cover_rejections.jsonl` — filas | 6 | 235 | **332** | +97 |

Nota de lectura — "items sin imagen usable" SUBIÓ (+78) pese a que este cierre sólo agregó
portadas: la cifra del 09-01 (439) y la de hoy (517=482+35) no son estrictamente comparables,
al no tener documentado el desglose exacto del cálculo del 09-01. Lo que SÍ es comparable
1:1 es "portada sin espejo local" (35→35, sin cambio) y "portada <90 000 px" (579→513,
−66, resultado directo de las 17 mejoras aplicadas hoy + descuento de los 8 items
expulsados). El criterio nuevo que más importa de acá en más es `cover_upscale_factor ≥
1.6` (12 portadas hoy) — reemplaza al área como target real de búsqueda desde la Etapa 1
(gotcha #175); "portada <90 000 px" se sigue reportando por continuidad histórica de esta
tabla, no porque siga siendo el criterio operativo.

**Targets restantes para una eventual tanda 3** — `sc_plan.py --retry-failed` (criterio
`scale` default, portada+galería, dry-run a scratchpad, sin tocar `.tmp_sc_plan.json` del
repo): **542 targets** (11 portada + 531 galería — el criterio de galería sigue siendo área,
sin cambios desde la Etapa 1). **Items sin ninguna imagen, top 8 por país**: España 182,
Estados Unidos 114, Japón 99, Italia 39, Francia 23, México 23, Corea del Sur 21, Alemania
11. **Top 8 por fuente**: ListadoManga (colecciones) 180, JP - Sumikko (限定版・特装版) 76, EN -
Otaku Calendar 36, US - Seven Seas (ediciones especiales) 34, Manga-Sanctuary (planning) 23,
MX - Manga México (Panini México) 22, KR - Aladin (만화 한정판) 21, US - Kinokuniya Exclusives
19. ListadoManga/España domina por volumen absoluto de catálogo, no por tasa de fallo — no
amerita una tanda 3 dedicada sin antes resolver la vía de whakoom-por-navegación sugerida en
la corrección de gotcha #173.

**Backups de este cierre**: `data/backups/cover_preview.json/cover_preview.json.pre-sync-
cover-preview-bak`, `data/backups/items.jsonl/items.jsonl.pre-apply-etapa2-bak` (manual) +
`items.jsonl.pre-apply-preview-bak` (automático del script, mismo contenido).

### Cierre de los 2 hallazgos "no corregidos acá" (gotchas #181/#182, 2026-09-02)

Turno posterior, dedicado a cerrar los dos mecanismos que "Cierre Etapas 1-2" arriba dejó
explícitamente sin arreglar. Único escritor de `items.jsonl` durante la corrida; no tocó
`data/cover_preview.json` salvo lectura.

**#181 — duplicado de foto en `images[]` (upgrade Aladin).** Diagnóstico con datos reales
del backup `items.jsonl.pre-aladin-upgrade-bak` confirmó la hipótesis de la nota original:
`images[0]` (portada) ya estaba en `cover500/` por un camino previo (JSON-LD/og:image, que
Aladin sirve directo en esa resolución) mientras una entry de galería más adelante en el
mismo `images[]` apuntaba al MISMO `<id>/<subcarpeta>/<archivo>` bajo `cover150/` o
`cover200/` — URLs textualmente distintas hasta que `upgrade_image_resolution.py` normalizó
ambas a `cover500/`, momento en que colapsaron a la misma url/local. Fix de mecanismo:
`dedupe_item_images()` (nueva, `upgrade_image_resolution.py`), corrida por-item apenas
`_apply_upgrade` toca una entry — clave canónica `_img_stem(url)` / `local` / sha256 de
contenido (fallback), nunca reordena `images[0]` ni vacía `images[]`, dona `kind`/
`description` al sobreviviente (mismo patrón sticky que `_apply_improvement`, gotcha #164).
Reparación del dato (backup `items.jsonl.pre-aladin-dedup-repair-bak`): **156 items / 161
entradas** duplicadas eliminadas — 151 KR-Aladin (el bug original) + 5 más fuera de Aladin
(3 Global-Mangavariant, 1 IT-Star Comics, 1 JP-Rakuten Books) que el mismo mecanismo general
encontró por sha256 idéntico bajo nombres de archivo totalmente distintos, verificados a
mano como duplicados reales — la verificación pedida ("0 por url canónica y por sha en TODO
el corpus") los cubre a propósito. 0 items `approved_at` tocados, 0 portadas perdidas. El
"109 items" del diagnóstico original no se pudo reconciliar con el conteo real (151 Aladin,
confirmado por el propio detector `carrusel_dup` de `data_quality.py`) — ver gotcha #181 para
el detalle completo, incluyendo por qué `dedup_carousel_images.py --redteam-auto` (que ya
cubre sha256) NO alcanzaba como herramienta de reparación sin tocar más de la cuenta (detecta
además pares `dhash_rescale` ajenos a este bug, 303 items vs. los 156 de este mecanismo).

**#182 — downgrade real al aplicar una candidata `approved` desactualizada.** El caso
`travidebla-unknown-artbook-jp` de arriba (candidata `approved` de 508 200 px pisando una
portada que mientras tanto había subido a 1 020 000 px vía el patrón r10s.jp de gotcha #180)
expuso que `apply_preview()` confiaba en el `old_pixels` congelado al momento de aprobar, no
en la portada ACTUAL al momento de aplicar. Fix de mecanismo: `_no_gain_at_apply()` (nueva,
`fetch_better_covers.py`) re-lee la portada ACTUAL de disco en el momento mismo de aplicar,
para las 3 acciones que pasan por `_apply_improvement` (`replace_cover`,
`replace_cover_demote`, `replace_and_add`). Sin ganancia real → la candidata vuelve a
`pending` con `invalid_reason="no_gain_at_apply"` (mismo patrón que `would_remove_cover` de
`remove_image`, gotcha #168), contado en el resumen (`skipped_no_gain_at_apply`). Excepción:
portada actual placeholder o ausente → aplica igual, cualquier imagen real es mejora.
`replace_image` (target puntual de galería, no necesariamente la portada) queda fuera del
alcance a propósito — no tiene una única "imagen actual" bien definida como sí la tiene
`images[0]`.

Tests: `tests/test_upgrade_image_resolution.py::TestDedupeItemImages` (7 casos) y
`tests/test_apply_gain_guard.py` (6 casos, cubre las 3 acciones + placeholder + sin portada
previa). Suite completa verde (2464 tests, +13 de este cierre). `validate_corpus.py` 0
violaciones duras (mismos warnings preexistentes). `sync_cover_preview.py --dry-run` en 0
cambios. `filter_non_manga.py --dry-run` 0 rechazos. Detalle completo en gotchas #181/#182.

---

## Búsqueda de portadas hi-res — skill `/watch-whakoom-covers` (2026-09-02)

> Vía APROBADA por el owner específicamente para el mercado **España**, alternativa a
> `/watch-search-covers` (§ arriba). Motivación directa: la tanda "Etapa 2, tanda 1" de
> arriba midió que la vía genérica (Bing texto + Yandex reverse) sólo acertó **1% real**
> sobre el pool ES (gotcha #173) — Bing SÍ encuentra la página/serie correcta en Whakoom,
> pero una búsqueda de imagen suelta no distingue la edición ES exacta de sus hermanas
> (regular/kanzenban/deluxe, logo/crop/color distintos). Esta vía invierte el orden:
> resuelve la **página de edición** primero (editorial + idioma + total de tomos) y
> recién después busca la imagen del tomo — reduce "¿es esta imagen la portada
> correcta?" (difícil, sin contexto) a "¿es esta la edición correcta?" (verificable con
> metadata estructurada).

**Implementación**: `scripts/retrofit/we_plan.py` (Step 1, determinista, sin red) +
`scripts/retrofit/we_resolve.py` (Step 2, determinista, decide editorial+idioma+total de
tomos y arma la URL del tomo) + skill
[`watch-whakoom-covers`](../../.claude/skills/watch-whakoom-covers/SKILL.md) (Browser pane
de Claude Code para el scraping interactivo) + los MISMOS `sc_validate.py`/`sc_flush.py`
permanentes que usa `/watch-search-covers` (identidad/calidad de imagen — no se
reimplementa ese criterio). Detalle de los límites públicos de Whakoom (11 tomos sin
login, sin ISBN, sin buscador, tamaños de CDN, rate limit, robots.txt) en
`docs/scraper/sources/whakoom.md` § 6.

**Diferencia de criterio de "baja calidad" vs `sc_plan.py`**: `we_plan.py` usa
`--target-rule area` (píxeles < `fetch_better_covers.LOW_QUALITY_PX`) como **default**,
no `scale` (el default de `sc_plan.py` desde el gotcha #175). Motivo: sobre el corpus ES,
`scale` deja sólo 12 portadas candidatas (10 con `volume <= 11`) — insuficiente para
operar esta vía a escala. `area` da 488 (369 resolubles) — es el pool real que motivó la
vía (portadas `static.listadomanga.com` ~210×300 px, gotcha #39). `--target-rule scale`
sigue disponible para acotar a las que además se ven mal en la card real.

**`total_tomos` es una heurística LOCAL, no una re-scrapeada de `listadomanga.es`**:
`we_plan.py` cuenta cuántos items del corpus comparten el mismo `edition_key` — evita que
el planificador dependa de red (mismo perfil que `sc_plan.py`), a costa de poder
infra-contar una serie en curso con tomos aún no ingestados (esa edición no resuelve hasta
que el corpus tenga todos sus tomos). `we_resolve.py` exige coincidencia EXACTA (±0) entre
ese valor y el `total_tomos` que la edición whakoom declara — es el criterio DURO de
desambiguación entre ediciones hermanas (regular/kanzenban/deluxe), junto con editorial +
idioma `"Spanish (Spain)"`. Si el corpus no tiene el dato (`total_tomos` local
desconocido), se exige en cambio que ninguna edición hermana sea también ES del mismo
publisher — si la hay, no resuelve (`ambiguous_no_total_tomos`).

**Caché append-only** `data/whakoom_edition_map.jsonl` — una fila por intento de
resolución (éxito o no, con el motivo como `method`), la escribe `we_resolve.py`;
`we_plan.py` sólo la lee para reutilizar una `edition_url` ya resuelta (evita repetir la
búsqueda Bing en corridas futuras para la misma serie+editorial).

**Universo real ES** (reconocimiento 2026-09-02): 670 items con imagen ausente o chica
por área (182 sin imagen + 488 chica), de los cuales 508 son resolubles por esta vía
(`volume <= 11` o vacío: 139 sin imagen + 369 chica) y 162 quedan fuera de alcance
(`volume > 11`, requiere cuenta Whakoom).

**Gotcha nueva**: #183 (ver `docs/reference/gotchas.md`) — el límite de 11 tomos sin
login y la exclusión dura de `/comics/`/`/todos` por robots.txt + requerimiento de cuenta.

### Whakoom tanda 1 — items ES sin imagen (2026-09-02)

Primera corrida real a escala del skill, acotada a los 139 items ES **sin imagen**
resolubles (`volume <= 11` o vacío; portada chica quedó fuera de esta tanda a propósito).
`we_plan.py` no tiene un flag `--include-no-image` dedicado — el filtro se aplicó
post-plan, quedándose sólo con los targets `pixels == 0` de la salida (137 de los 139;
2 ya estaban adjudicados en `cover_preview.json` de una corrida piloto previa).

**Resultado**: 137/137 targets intentados, **93 candidatas encoladas** (hit rate 67.9%),
todas `status: "pending"`, `confidence: "low"`, `via: "whakoom_edicion"` — pendientes de
revisión visual del owner en `http://localhost:8000/web/cover-preview.html`.

**Optimización clave**: los 137 targets no resolubles requieren 137 búsquedas Bing
individuales — pero muchos son volúmenes de la MISMA edición (mismo `listadomanga.es
coleccion_id`). Agrupando por `coleccion_id` antes de buscar, los 137 targets colapsaron
en **61 grupos** (búsqueda Bing una vez por grupo, candidatas de edición reutilizadas para
todos los volúmenes del grupo) — ~2.2 targets resueltos por búsqueda en promedio, con
casos de hasta 11 (Fist of the North Star) y 9 (Bastard!!, Eden, I's, Shangri-La Frontier,
Berserk kanzenban) targets resueltos de una sola búsqueda + apertura de candidatas.

**Desglose de los 44 no resueltos** (motivo tal como lo deja `we_resolve.py` en
`data/whakoom_edition_map.jsonl`):

| Motivo | Cant. | Detalle |
|---|---|---|
| `total_tomos_mismatch` | 11 | La única edición ES+editorial candidata declara un `total_tomos` distinto al heurístico local. Incluye el caso Shangri-La Frontier (9 targets): la edición "Expansion Pass" es visiblemente la correcta (título/editorial/idioma calzan) pero el heurístico local cuenta 27 tomos vs. los 11 que declara whakoom — probable artefacto del heurístico (cuenta por `edition_key` compartido entre variantes), no un error de edición. Quedó sin forzar (precisión > recall). |
| Rechazadas por gate (`sc_validate.py`, matches=0 con `resolved:true`) | 13 | La edición resolvió correcta (editorial+idioma+total_tomos calzan) pero la candidata de imagen no pasó el gate débil sin-referencia (denylist por hash, imagen blanda, o < 10 000 px tras el upgrade). Incluye el caso documentado de Hokuto no Ken (7 de 11 tomos): la portada real de Whakoom coincidía por hash con una candidata YA RECHAZADA en `data/cover_rejections.jsonl` de una revalidación automática previa — el denylist funcionando como se espera, no un bug. |
| `not_found` (0 candidatas relevantes en Bing, o ninguna edición ES del publisher correcto) | 14 | Incluye 2 casos donde Bing no indexó la obra en absoluto (All World, Sex Report) y varios donde sólo aparecieron ediciones de otros países (LatAm/México) o de otro publisher. |
| `ambiguous_multiple_editions` (ambigüedad entre ediciones hermanas) | 3 | Regreso al Mar y El Muerto Enfermo de Amor y Seraphim: Whakoom lista 2-3 entradas casi idénticas (mismo publisher/idioma/`total_tomos`, sin diferencia visible) — no hay forma determinista de elegir sin arriesgar la edición equivocada. |
| `volume_not_listed` (tomo no listado en la edición resuelta) | 3 | La edición resolvió pero el tomo pedido no aparece en su lista de volúmenes — incluye Berserk Beherit Limited (edición ES real, pero modelada por Whakoom como oneshot sin numeración mientras el corpus lo tiene como "volumen 1"). |

**Ambigüedad de tipo de producto (gotcha del piloto, confirmada en esta tanda)**: el
primer target de la corrida (`bloom-into-you-planeta-boxset-es`, el caso documentado en
el SKILL.md) casi resuelve contra "Astrolabio - Bloom Into You Illustration Works" (un
artbook, no el box set) — mismo publisher/idioma/`total_tomos == 1` por coincidencia. Se
detectó a mano ANTES de pasarlo a `we_resolve.py` (0 candidatas para ese target) porque no
hay guard determinista para esta clase de falso positivo — sigue como mejora pendiente.

**Ediciones nuevas en el caché** (`data/whakoom_edition_map.jsonl`): 147 filas totales al
cierre (18 pre-existentes de la sesión piloto + 129 nuevas de esta tanda), 110 resueltas
(`method: "whakoom_edicion_page"`). Corridas futuras de `we_plan.py` reutilizan estas
`edition_url` sin repetir la búsqueda Bing para la misma serie+editorial.

**Verificación de cierre**: `sync_cover_preview.py --dry-run` → 0 cambios (cola sana).
`validate_corpus.py` no se corrió (este skill nunca toca `items.jsonl`). Nada aplicado a
`items.jsonl` — sólo `data/cover_preview.json` (93 candidatas nuevas) y el caché de
ediciones. Pendiente: revisión visual del owner de las 93 candidatas, y decisión sobre si
correr una tanda 2 para las ~369 "portada chica" (excluidas a propósito de esta tanda).

### Whakoom tanda 2 — items ES "portada chica" (2026-09-02)

Segunda corrida a escala del skill, sobre el pool que la tanda 1 excluyó a propósito: los
369 targets "portada chica" (`volume <= 11` o vacío, área < 90 000 px) que `we_plan.py`
deja tras excluir los ya-adjudicados de tanda 1. A diferencia de tanda 1 (items sin
imagen), la mayoría de estos targets SÍ tienen una referencia real → `sc_validate.py`
corre el AND-gate completo (`_same_cover` + `_is_soft_image` + `candidate_metadata_conflict`),
no sólo el gate débil.

**Optimización por agrupación** (misma técnica que tanda 1, replicada): los 369 targets
colapsan en **206 grupos únicos** por `(coleccion_id, publisher)`; 24 de ellos (10 grupos)
ya tenían `edition_url` en caché desde tanda 1 y se resolvieron sin tocar Bing. De los 196
grupos restantes se procesaron **~50 grupos (294 targets únicos)** dentro del presupuesto
de esta corrida — priorizados de mayor a menor tamaño de grupo (los de 4-11 targets primero,
con hit rate más alto por ser series largas de una sola edición kanzenban/deluxe/omnibus;
luego una muestra de grupos de 2-3). Quedan **75 targets sin intentar** (grupos de 1-2
targets, cola larga) para una tercera corrida.

**Resultado real (corregido 2026-09-02, ver nota de corrección al final de esta sección)**:
la ventana real de tanda 2, aislada en `data/cover_search_attempts.jsonl` por
`engines: ["whakoom_edicion"]` con `attempted_at` entre **15:17:36 y 15:52:11 UTC**, tiene
**170 targets únicos intentados** (179 filas — 9 targets con 2 intentos). De esos, **55
candidatas encoladas** (hit rate **32.4%** sobre targets únicos, 30.7% sobre intentos) —
**todas `verified: true`** (referencia real, pasaron `_same_cover`); tanda 2 no aporta
candidatas `verified: false` propias (ver nota de corrección). Ganancia mediana de píxeles
sobre las 55: **+621 800 px** (factor ~11×) al reemplazar la portada `~55-65k px` de
`static.listadomanga.com` por el `/large/` de Whakoom — esta cifra ya era correcta en la
versión anterior de esta sección (se recalculó igual, confirma el número).

**Desglose de los 124 no resueltos/rechazados de la ventana real** (recontado desde
`data/cover_search_attempts.jsonl`, `matches: 0` con `engines: ["whakoom_edicion"]` en la
ventana 15:17-15:52 UTC):

| Motivo | Cant. | Detalle |
|---|---|---|
| `total_tomos_mismatch` | 48 | La edición ES+editorial candidata declara un `total_tomos` distinto al local. Incluye varios casos de "el contador de Whakoom va ADELANTADO" (series en curso donde Whakoom ya cuenta más tomos que el corpus local — Shangri-La Frontier 11 vs 27 heurístico, The Summer Hikaru Died 8 vs 6, InuYasha 23 vs 24, Witch Hat Atelier 15/4 vs 13) — mismatch legítimo por desfase temporal, no bug. |
| `language_mismatch` | 32 | La única edición encontrada es de otro país hispanohablante (Argentina/México) o de otro idioma — Bing indexa mejor las ediciones LatAm que las de España para varias series de Ivrea/Panini (Yu Yu Hakusho, Baki, Fushigi Yûgi, Spy x Family, D.N.Angel, Black Jack). |
| `sc_validate_rejected` (resolvió pero la imagen no pasó el gate) | 21 | Editorial+idioma+total_tomos calzan pero `_same_cover`/denylist rechazan la candidata. La mayoría coinciden por hash (`aHash` dist ≤2) con una candidata YA rechazada en `data/cover_rejections.jsonl` por una revalidación automática previa (`reason: auto_revalidation`, 2026-09-01) — el denylist funcionando correctamente sobre el mismo arte propuesto desde otra fuente, no un bug de este skill. |
| `not_found` / `no_candidates_found` | 9 + 9 | 0 candidatas relevantes tras el filtro de tokens, o ninguna edición ES del publisher correcto entre las candidatas abiertas (Attack on Titan/Salvat: Bing no indexó ninguna edición de Whakoom para esa combinación serie+editorial). |
| `publisher_mismatch` | 4 | Trigun Maximum (4 targets): el publisher local es el label co-editado `"EDT Editores de Tebeos / Ediciones Glénat"`, Whakoom lo declara como `"Glénat España - Editores de Tebeos"` — mismos tokens, orden distinto. `publisher_matches()` en `we_resolve.py` es un check de contención de substring, no de conjunto de tokens, así que un reordenamiento de imprint co-editado no matchea aunque sea la MISMA editorial. Hallazgo de esta tanda, ver spawn_task. |
| `volume_not_listed` | 1 | La edición resolvió pero el tomo pedido no aparece en `volumes[]` — incluye el caso "My Dress-Up Darling: Libro oficial" (oneshot real en Whakoom, pero el item local tiene `volume: "1"` en vez de vacío, así que `find_volume_image` no lo empareja). |
| `ambiguous_multiple_editions` | 0 en la ventana | Dos ediciones candidatas pasan el filtro editorial+idioma+total_tomos (p.ej. Shangri-La Frontier: "Expansion Pass" vs. edición regular, ambas 11 tomos Norma ES) — no se puede desambiguar sin arriesgar la edición equivocada. Los 3 casos vistos originalmente caen FUERA de la ventana real de tanda 2 (pertenecen a la actividad de tanda 1 antes de 15:17 UTC). |

**Quirk nuevo de plantilla — página "hub" de portadas alternativas**: `/ediciones/589206`
(`spy_x_family_portada_alternativa`) no sigue ninguna de las dos plantillas documentadas en
el SKILL.md ("cómics" con `p.publisher`, "libro/artbook" con la línea `Idioma · Editorial`)
— la extracción del skill devuelve `publisher`/`language`/`total_tomos` todos vacíos porque
esta página es un selector de "elige tu portada alternativa" sin la metadata de edición
habitual. No hay guard para detectar esto de antemano; el resultado es simplemente
`language_mismatch` (candidata descartada, correcto por accidente — no está mal, pero el
motivo reportado no es el real). Tercera plantilla a documentar si reaparece.

**Caché**: `data/whakoom_edition_map.jsonl` pasó de 147 a 326 filas (+179 nuevas). Tiempo
total de la corrida: ~1h50min (14:02–15:52 UTC). Bing Imágenes no challengeó ninguna
búsqueda en toda la corrida (a diferencia de Bing web).

**Verificación de cierre**: `sync_cover_preview.py --dry-run` → 208 entries cargadas al
cierre de la sesión completa (tanda 1 + tanda 2 acumuladas), **0 operaciones** salvo
backfill informativo del campo `url` en entries legacy — cola sana. Nada aplicado a
`items.jsonl` en este punto. El desglose "58 previas / 150 nuevas" de la versión original
de este párrafo describía el total acumulado de la sesión, no la contribución real de
tanda 2 sola — ver nota de corrección abajo. Pendiente entonces: revisión visual del owner
de las candidatas nuevas (208 total en cola), y una posible tanda 3 sobre los targets que
no llegaron a intentarse.

**Nota de corrección (2026-09-02, turno posterior de aplicación de la cola)**: al releer
`data/cover_search_attempts.jsonl` para verificar la cola antes de aplicarla, se encontró
que el párrafo de resultado y la tabla de rechazos de esta sección (arriba) sumaban las
candidatas y los intentos de tanda 1 (actividad 14:02:03–15:16:42 UTC, 155 filas, 95 con
`matches: 1`) junto con los de tanda 2 (actividad real 15:17:36–15:52:11 UTC, 179 filas,
55 con `matches: 1`) como si las 150 filas combinadas con `matches: 1` (95+55) fueran todas
"candidatas de tanda 2", y de ahí salió el "150 candidatas encoladas... 95 verified: false"
que aparecía antes en esta sección. Confirmado contra `data/cover_preview.json` (149
`approved` + 1 `rejected` con `via: "whakoom_edicion"` al momento de aplicar la cola,
`docs/reference/images.md` § "Cierre de la tanda de depuración de imágenes"): 94 de esos
149 aprobados tienen `ref_pixels: 0` (candidatas de tanda 1, sobre items sin imagen previa)
y 55 tienen `ref_pixels > 0` — exactamente los 55 `matches: 1` de la ventana real de tanda
2, todos `verified: true`. Los números corregidos (resultado, tabla de rechazos, hit rate)
ya están arriba en esta sección; el párrafo "Caché"/"Verificación de cierre" de arriba
queda con la nota de que sus cifras son totales de sesión completa, no de tanda 2 aislada.
Los conteos de "206 grupos" / "294 targets únicos" / "75 targets sin intentar" del párrafo
"Optimización por agrupación" (arriba) NO se pudieron re-verificar contra ningún log
persistido (esa bookkeeping de grupos vivía sólo en el estado de la sesión que corrió el
skill, no en un archivo) — quedan como estaban, sin corregir ni confirmar; tratarlos con
la misma cautela que el resto de esta nota. El análisis de `total_tomos_mismatch` (63
filas → 13 `coleccion_id`) y `publisher_mismatch` (4 filas → fix #3) en "Whakoom —
endurecimientos de código" (abajo) se hizo sobre las 326 filas acumuladas de
`whakoom_edition_map.jsonl` al cierre de sesión (caché de ediciones, no de intentos) — ese
archivo no distingue tanda 1 de tanda 2 por diseño (es un caché deduplicado por edición),
así que esa sección no hereda el bug de este párrafo y no requirió corrección.

### Whakoom — endurecimientos de código previos a tanda 3 (2026-09-02)

Antes de correr una tanda 3 de scraping real, se implementaron 4 endurecimientos de
código sobre `we_plan.py`/`we_resolve.py` a partir de los hallazgos de las tandas 1-2
de arriba — con tests, sin tocar `items.jsonl` ni `cover_preview.json`, sin invocar el
skill ni el Browser pane en esta pasada:

1. **Total de tomos REMOTO en vez de heurística LOCAL** — nuevo módulo
   `scripts/retrofit/listadomanga_meta.py`: fetchea `total_tomos`/`formato`/`paginas`/
   `editorial`/`ongoing` REALES de `listadomanga.es/coleccion.php?id=N` (reusa el
   parser canónico `wikis/listadomanga_collections.parse_collection_page`, nunca
   reimplementa el HTML parsing) y los cachea en
   `data/listadomanga_collection_meta.jsonl` (append-only). `we_plan.py` prefiere este
   dato sobre el conteo local por `edition_key` cuando está disponible
   (`listado.source: "listadomanga_remota"` vs `"local_count"`); el fetch es un Step 1b
   opt-in del skill (`listadomanga_meta.py --from-plan .tmp_we_plan.json`), `we_plan.py`
   en sí sigue sin red. `listado.ongoing`/`cand.ongoing` relajan la condición de
   `total_tomos` de `we_resolve.py` a `>=` en vez de `==` estricto para series en curso.
2. **Guard de reedición** — `we_resolve._reedition_guard_ok`: para oneshots
   (`total_tomos == 1`) o ediciones con una hermana ES del mismo publisher y mismo
   `total_tomos`, exige que el formato+páginas embebidos en el SLUG de whakoom
   (`"<título>-rustica_240_pp"`) sean consistentes con `listado.formato`/`listado.paginas`
   remotos — motivado por el único error de la curación tanda 1 (`sensor-ecc-deluxe-es`,
   una reedición del mismo sello con mismos tomos y páginas).
3. **Publisher por conjunto de tokens** — `we_resolve.publisher_matches` dejó de ser
   contención de substring (que no toleraba un imprint co-editado con el orden de
   tokens invertido, 4 targets Trigun Maximum) y ahora compara CONJUNTOS de tokens
   normalizados. Cierra `task_07e139d6`.
4. **`sibling_urls` desde "Otras ediciones"** — cuando ninguna candidata resuelve por
   `language_mismatch` (33 casos en tanda 2, típicamente Bing indexando mejor la
   hermana LatAm), `we_resolve.py` ahora devuelve las URLs de hermanas ES-España del
   mismo publisher que las candidatas abiertas listaban bajo "Otras ediciones" — el
   skill las abre como una pasada adicional del Step 3 sin repetir la búsqueda Bing
   (requirió agregar `edition_url` a la extracción JS de `other_editions[]` en
   SKILL.md, y un intento best-effort SIN verificar en vivo de extraer el estado
   "Ongoing" propio de whakoom).

**Simulación offline (sin red, sin Browser)**: se re-analizó `data/whakoom_edition_map.jsonl`
(326 filas de la corrida real de tanda 2) con el código nuevo. Resultados:

- **63 filas `total_tomos_mismatch` colapsan en 13 `coleccion_id` distintos**: Bleach
  (3000), Attack on Titan (5060), Radiant (2325), One Piece (2570), Shangri-La Frontier
  (4290), Yuuna and the Haunted Hot Springs (3346), Erio to Ningyou (5823), Ranma 1/2
  (4782), Berserk (4945), The Summer Hikaru Died (4560), F.COMPO (3720), Inuyasha
  (4753), Witch Hat Atelier (3020) — son los targets de una tanda 3 real de
  `listadomanga_meta.py --coleccion-ids 3000,5060,2325,2570,4290,3346,5823,4782,4945,4560,3720,4753,3020`
  para maximizar cuántos de estos 63 pasan a resolver con la referencia remota.
- **Las 4 filas `publisher_mismatch` (Trigun Maximum, `coleccion_id=693`) se verificaron
  RESUELTAS con el fix #3**: `publisher_matches("EDT Editores de Tebeos / Ediciones
  Glénat", "Glénat España - Editores de Tebeos")` ahora es `True` (antes `False`) — los
  conjuntos de tokens `{edt, editores, de, tebeos, glenat}` / `{glenat, editores, de,
  tebeos}` son subconjunto uno del otro.
- **No fue posible re-ejecutar `we_resolve.py` extremo a extremo sobre los 63/33 casos
  reales de `total_tomos_mismatch`/`language_mismatch`**: el JSON compacto de candidatas
  que extrae el Step 3 del skill (idioma/formato/`other_editions`/`volumes` por edición
  abierta) no quedó persistido en ningún archivo tras esas corridas — `data/whakoom_edition_map.jsonl`
  sólo guarda el resumen agregado (lado item + `method`), no el lado whakoom completo de
  la comparación. Los archivos `raw_whakoom_*.json` hallados en el scratchpad de sesión
  resultaron ser URLs de imagen sueltas (candidatas ya encoladas), no el JSON de entrada
  de `we_resolve.py`. Mejora de proceso para una tanda 3 real: persistir el `we_input`
  compacto de cada target (o al menos de los que fallan) en
  `data/diagnostics/whakoom_tanda3_inputs.jsonl` antes de invocar `we_resolve.py`, para
  poder re-simular fixes futuros sin re-scrapear.

**Verificación**: suite completa `pytest` verde (2557 tests, baseline reportado 2520).
Los 3 archivos de test de esta vía quedaron en 79 tests (`test_we_plan.py` 22,
`test_we_resolve.py` 41, `test_listadomanga_meta.py` 16 — este último nuevo). Nada
tocado en `items.jsonl`/`cover_preview.json`. `we_plan.py --dry-run` sigue reportando el
mismo universo (no cambia sin caché remoto poblado). Docs actualizadas en el mismo turn:
`docs/scraper/sources/whakoom.md` § 6 (algoritmo + subsección "Resueltos en tanda 3"),
`.claude/skills/watch-whakoom-covers/SKILL.md` (Step 1b nuevo, Step 3 JS con
`edition_url`/`ongoing`, Step 4 con los 6 criterios + manejo de `sibling_urls`),
`scripts/retrofit/README.md` (entrada `listadomanga_meta.py`), gotcha #184
(`Candidate.volume` dinámico, `docs/reference/gotchas.md`).

**Pendiente para una tanda 3 real** (con skill + Browser pane): correr Step 1b sobre los
13 `coleccion_id` de `total_tomos_mismatch` listados arriba; reintentar los 4 targets
Trigun Maximum (deberían resolver directo); reintentar los 33 `language_mismatch` para
medir el hit rate real de `sibling_urls`; y los 75 targets de tanda 2 que nunca se
intentaron (grupos de 1-2, cola larga).

### Whakoom tanda 3 — corrida real (2026-09-02)

Primera corrida real (skill + Browser pane) sobre los endurecimientos de la sección
anterior. El corpus creció entre tanda 2 y tanda 3 (delta diario), así que el universo
real de `we_plan.py` pasó de ~369+139 a **359 targets pendientes** (43 con edición ya
en caché) al recalcular desde cero — los "75 nunca intentados" de la nota anterior
quedaron obsoletos (226 grupos por `coleccion_id`, 223 targets tras los ya-resueltos).

**Step 1b real**: `listadomanga_meta.py --from-plan .tmp_we_plan.json` fetcheó las
**226 `coleccion_id`** distintas del plan (0 errores) — `we_plan.py` pasó de 0 a **228
targets con `listado.source == "listadomanga_remota"`** (131 quedaron en heurístico
LOCAL: colecciones cuya página de `listadomanga.es` no declara `total_tomos` explícito,
típicamente series largas en curso — Ranma 1/2, Berserk, Yu Yu Hakusho, Baki, Trigun
Maximum, D.N.Angel, Inuyasha, Fushigi Yûgi, One Piece entre ellas; el fetch fue exitoso
pero el campo vino `None`, no es un error del script).

**Retries priorizados** (93 targets, agrupados por `coleccion_id` en 21 grupos):

- **Los 13 `coleccion_id` de `total_tomos_mismatch`** (uno, `3000`/Bleach, ya había
  salido del plan por drift del corpus — no se pudo reverificar): de los 12 restantes,
  **5 se destrabaron a nivel EDICIÓN** gracias a la metadata remota + la relajación
  `ongoing` — Berserk (`4945`, Maximum Berserk 21 tomos vs. 19 heurístico, ongoing),
  The Summer Hikaru Died (`4560`, 8 vs. 6 remoto, ongoing), Witch Hat Atelier (`3020`,
  15 vs. 8 remoto, ongoing), Radiant (`2325`, 16 vs. 1 remoto+ongoing) y One Piece
  (`2570`, 113 vs. 1 remoto+ongoing) — pero SÓLO Witch Hat Atelier aportó una candidata
  nueva a la cola (1); las otras 4 resolvieron la EDICIÓN pero `sc_validate.py` rechazó
  la imagen con matches=0 — correcto: Berserk/Hikaru Died son portadas de tomo distintas
  a las ya existentes (denylist/`_same_cover`), y Radiant/One Piece resultaron ser el
  caso de ambigüedad de producto ya documentado (portada VARIANTE y edición ESPECIAL
  respectivamente, distintas de la edición numerada regular que sí calzó por conteo).
  Los 7 restantes (Shangri-La Frontier `4290`, Ranma 1/2 `4782`, F.COMPO `3720`,
  Inuyasha `4753`, Attack on Titan-Norma `5060`, Yuuna `3346`, Erio to Ningyou `5823`)
  siguen sin resolver — en varios casos (Shangri-La Frontier, Inuyasha) el conteo
  remoto de `listadomanga.es` es el total de la obra japonesa completa, mayor que lo
  que Whakoom cuenta para la edición española real (11 vs. 27, 23 vs. 24) — la
  relajación `ongoing` sólo cubre `cand >= listado`, no el caso inverso; estructural,
  no un bug.
- **Trigun Maximum** (`693`, 5 targets — creció de 4 a 5 por el delta diario):
  **5/5 resolvieron la edición Y 4/5 quedaron encoladas** (`verified: true`) —
  confirma en datos reales el fix #3 (`publisher_matches` por conjunto de tokens):
  `"EDT Editores de Tebeos / Ediciones Glénat"` vs. `"Glénat España - Editores de
  Tebeos"` matchea. `task_07e139d6` cerrada con evidencia real, no sólo simulación.
- **Los 33 `language_mismatch`** (8 series: My Dress-Up Darling, Yu Yu Hakusho, Baki,
  D.N.Angel, Fushigi Yûgi, Spy x Family, Black Jack, Dorohedoro): **15/33 se
  destrabaron** (Baki 6, Fushigi Yûgi 4, Spy x Family 3, Dorohedoro 2), de los cuales
  Baki + Fushigi Yûgi + Dorohedoro aportaron **6 candidatas nuevas** a la cola
  (Spy x Family resolvió la edición pero `sc_validate` rechazó la imagen). D.N.Angel
  (4) cambió de motivo a `total_tomos_mismatch` (se encontró la edición ES real —
  15 tomos Ivrea — pero no calza con el heurístico local de 10). Yu Yu Hakusho (9),
  Black Jack (3) y My Dress-Up Darling (2) siguen `language_mismatch` sin resolver.
  **Hallazgo importante**: en NINGÚN caso la resolución pasó por el mecanismo
  `sibling_urls` (endurecimiento #4) — en todos los casos donde se abrió la edición
  LatAm/México original, su lista "Otras ediciones" NO listaba una hermana
  ES-España (`sibling_urls` volvió vacío). Los 15 destrabados se resolvieron porque
  el candidato Bing de esta corrida (¡de nuevo `site:whakoom.com "<serie>"
  <editorial>`, sin cambios de query) incluyó directamente la edición de España entre
  las 3 URLs devueltas — algo que la corrida de tanda 2 aparentemente no vio (el
  ranking de Bing Imágenes no es determinista corrida a corrida, o esos targets son
  nuevos del delta diario y nunca se intentaron en tanda 2 bajo ese nombre). El
  mecanismo `sibling_urls` en sí sigue sin un caso real que lo ejercite — sólo
  cobertura por tests sintéticos.
- **Targets nunca intentados**: el "75" original de la nota de arriba ya no reflejaba
  el corpus (creció a 223 tras el delta diario). Se procesaron **41 targets en 14
  grupos** (de los 186 grupos/223 targets restantes, priorizando los de mayor tamaño):
  Attack on Titan-Salvat (9, `not_found` — Whakoom no indexa esa coedición), #DRCL
  Midnight Children (3, resolvió edición, 0 candidatas), Más Allá de las Palabras (3,
  `not_found`), re CERVIN (3, resolvió, **2 encoladas**), Historia de Amor (3,
  resolvió, **2 encoladas** — ver nota de título abajo), Los Inventos de Peace
  Electronics (3, `total_tomos_mismatch`), Devilman (3, resolvió, **1 encolada**),
  Cardcaptor Sakura Art-Book (2, resolvió, 0 candidatas), Medaka Box (2, `not_found`),
  A Man and His Cat (2, `not_found` — ver hallazgo de idioma abajo), Blissful Land (2,
  `total_tomos_mismatch`), Bakemonogatari (2, `total_tomos_mismatch`), Gestalt (2,
  resolvió, **1 encolada**), Saiyuki (2, 1 resolvió + **1 encolada**, 1
  `volume_not_listed`).

**Hallazgo nuevo — `series_display` en inglés no indexa contra el título en español de
Whakoom**: "A Man and His Cat" (`coleccion_id=3766`, editorial Norma) dio 0 candidatas
relevantes con la query documentada (`site:whakoom.com "A Man and His Cat" Norma`) — pero
Whakoom SÍ tiene la edición indexada bajo su título de publicación real,
`https://www.whakoom.com/ediciones/597708/el_hombre_y_el_gato-rustica_con_sobrecubierta`
("El hombre y el gato", Norma Editorial, Spanish (Spain), 12 tomos — verificado en vivo,
no se forzó la resolución por ir fuera del algoritmo documentado). El item local trae
`series_display` en inglés (nombre internacional de la obra) mientras Whakoom indexa por
el título de la edición española — un gap de descubrimiento que no se intentó resolver
acá (cambiar `query` a partir de `title_original`/título de tomo en vez de
`series_display` es una mejora de scope de `we_plan.py`, no de este skill). Ver gotcha
nueva abajo.

**Resultado agregado de la corrida** (134 targets únicos intentados —93 retries + 41
nunca-intentados—, ventana `cover_search_attempts.jsonl` 17:32–18:14 UTC del
2026-09-02, aislada de tanda 1/2 por timestamp):

| Categoría | Cant. |
|---|---|
| Candidatas nuevas encoladas (`verified: true`) | **18** |
| Candidatas nuevas encoladas (`verified: false`) | 0 |
| Edición resuelta, `sc_validate` rechazó (matches=0) | 41 |
| No resuelto — `total_tomos_mismatch` | 42 |
| No resuelto — `language_mismatch` | 16 |
| No resuelto — `not_found` (0 candidatas tras filtro de tokens) | 16 |
| No resuelto — `volume_not_listed` | 1 |
| **Total** | **134** |

De los 13 `coleccion_id` de `total_tomos_mismatch` de tanda 2: **5/12 destrabados a
nivel edición** (1 salió del plan por drift). De los 33 `language_mismatch`: **15/33
destrabados**, ninguno vía `sibling_urls`. Trigun Maximum: **5/5 destrabados, 4
encolados** (fix #3 confirmado con datos reales). Caché `whakoom_edition_map.jsonl`:
326 → 461 filas (+135). Caché `listadomanga_collection_meta.jsonl`: 0 → 226 filas
(nuevo, poblado 100% en este turno). Tiempo total: ~45 min (17:32–18:18 UTC).

**Cierre de cola**: `sync_cover_preview.py --dry-run` reporta **110 operaciones
pendientes** sobre las 131 entries cargadas — pero son TODAS deuda de tanda 2, no de
esta corrida: 55 candidatas cuyo `new_url` ya es la portada actual del item (`pruned_
already_current` — aplicadas a `items.jsonl` en el cierre de cola del 2026-09-01/02
pero nunca podadas de `cover_preview.json`) + 44 exentas por la regla #166 + 73
entries legacy con `url` backfilleada. Verificado explícitamente que los 18 candidatos
nuevos de esta tanda NO están entre las 55 ya-aplicadas (comparación `new_url` vs.
portada actual del item, 0 coincidencias). La cola real de candidatas
`whakoom_edicion` pendientes de revisión visual del owner queda en **73** (55 de
tanda 2 + 18 de tanda 3), todas `verified: true`, `status: pending`. La poda de las
55 stale es trabajo de sync pendiente, fuera del alcance de este skill (que nunca
corre `sync_cover_preview.py --apply`).

## Cierre vía whakoom (2026-09-02) — curación t3, poda de la deuda de sync, aplicación

Cierre del ciclo de las 3 tandas del skill `/watch-whakoom-covers` documentadas arriba.
Este turno fue el **único escritor** de `items.jsonl` y `cover_preview.json` (verificado con
`ps`: sin `scrape_delta`/`manga_watch.py`/retrofits vivos); usa los locks canónicos
(`fetch_better_covers.preview_write_lock`, `manga_watch.backup_and_rotate`), no implementa
mecanismo nuevo.

### PASO 1 — curación de las 18 candidatas de tanda 3: 18/18 aprobadas, 0 rechazos

Método: hoja de contacto **portada actual vs. candidata a ~520×700 px por cara** (no la
miniatura de 210×300 que esconde sello y número de tomo — la trampa documentada en la
curación de tanda 1). Las 18 salieron de `data/cover_preview.json` filtrando
`via == "whakoom_edicion"` ∧ `status == "pending"` ∧ `verified == true` y **descartando por
`(slug, new_url)` las que ya eran la portada del item** (ver PASO 2): 73 candidatas
whakoom en cola → 55 deuda de tanda 2 ya aplicada + **18 nuevas de tanda 3**.

Veredicto: **18 approved / 0 rejected / 0 pending**. En las 18 la candidata es la MISMA
ilustración del MISMO tomo y la MISMA edición, en resolución mayor — número de tomo legible
e idéntico en ambas caras, sello/imprint coincidente con el `publisher` del item
(Ivrea, Norma, Glénat/EDT, Milky Way, Tsubaki, MangaLine, Héroes de Papel, Distrito Manga),
y crop/proporción equivalentes. Ninguna cayó en el patrón de reedición del mismo sello que
motivó el guard `_reedition_guard_ok` en tanda 3.

| # | slug | vol | actual → candidata |
|---|---|---|---|
| 1-2 | `baki-ivrea-kanzenban-es-{2,4}` | 2, 4 | 212×300 → 505×719 / 400×568 |
| 3-4 | `fushigi-yugi-ivrea-kanzenban-es-{6,7}` | 6, 7 | ~213×300 → 400×564 |
| 5-6 | `dorohedoro-norma-omnibus-es-{1,2}` | 1, 2 | 212×300 → 618×876 / 433×612 |
| 7-10 | `trigun-maximum-glenat-maximum-es-{1,3,4,11}` | 1, 3, 4, 11 | ~213×300 → 337×500 |
| 11 | `witch-hat-atelier-milkyway-special-es-10` | 10 | 214×300 → 686×1000 |
| 12-13 | `re-cervin-milkyway-special-es-{4,6}` | 4, 6 | 206×300 → 391×570 / 439×640 |
| 14-15 | `historia-de-amor-unknown-special-es-{1,2}` | 1, 2 | ~213×300 → 717×1000 / 481×686 |
| 16 | `devilman-mangaline-omnibus-es-1` | 1 | 212×300 → 703×1000 |
| 17 | `gestalt-heroesdepapel-special-es-2` | 2 | 216×300 → 475×656 |
| 18 | `saiyuki-distrito-omnibus-es-2` | 2 | 218×300 → 723×1000 |

Sin regresiones del gate: las 18 ya venían `verified: true` de `sc_validate.py`, ningún
`new_url` se repite entre candidatas (no hay colisión tipo gotcha #179), y el ledger de
rechazos no se tocó (0 rechazos que ledgerear). Backup de la cola antes de escribir:
`data/backups/cover_preview.json/cover_preview.json.pre-judge-whakoom-t3-bak`.

### PASO 2 — las ~110 operaciones del sync eran deuda ya aplicada, no trabajo pendiente

`sync_cover_preview.py --dry-run` sobre las 131 entries reportaba **110 operaciones**. El
desglose confirma que **NO poda nada pendiente**: son 55 candidatas podadas por "ya es
portada" + las 55 entries que quedan vacías al podarlas (55 + 55 = 110). Verificado
independientemente leyendo `items.jsonl`: esas 55 candidatas tienen `new_url ==
images[0].url` del propio item — son las de **tanda 2, aplicadas en el cierre del
2026-09-01/02 pero nunca podadas de la cola**; ninguna de las 55 es la única candidata
compartida con otra entry (`stale slugs con >1 candidata: []`), por eso las 55 entries
quedan vacías 1:1. Las otras 60 candidatas pendientes (44 `replace_cover_demote` exentas
por gotcha #166, 15 `replace_cover`, 1 `remove_image`) quedan intactas, y los 73
"backfill de `url` en entries legacy" son relleno de un campo, no poda.

Con eso, el sync real corrió sin riesgo: **131 → 76 entries**, resultado idéntico al
dry-run, backup automático `cover_preview.json.pre-sync-cover-preview-bak`. Esto cierra la
deuda que la sección "Whakoom tanda 3" dejó marcada como "trabajo de sync pendiente".

### PASO 3 — aplicación y verificación

Backup manual `data/backups/items.jsonl/items.jsonl.pre-apply-whakoom-t3-bak` +
`fetch_better_covers.py --apply-preview`:

| Acción | Resultado |
|---|---|
| Reemplazos de portada | **18 aplicados** (18 imágenes viejas eliminadas del espejo) |
| `no_gain_at_apply` (gotcha #182) | **0** — ninguna candidata volvió a `pending` |
| Rechazadas al ledger | 0 (no había rechazos) |
| Pendientes remanentes | **60** candidatas en 58 entries — intactas |

Verificación releyendo `items.jsonl` (gotcha #163, no se confía en el stdout del script):
**18/18** con `images[0].url == new_url`, `local` asignado y archivo `.avif` presente en
disco, y la imagen vieja fuera de `images[]` en las 18; **0 items con duplicados en
`images[]`** en TODO el corpus (por `url` y por `local`); ledger `cover_rejections.jsonl`
sin cambios (333 → 333 filas).

### PASO 4 — verificación de cierre

- `pytest` completo: **2585 passed, 0 failed** (37,9 s). Las fallas preexistentes por items
  crudos sin slug que se anticipaban tras el delta **no se materializaron** — la suite está
  entera en verde; `data_quality.py` reporta 14 items pendientes de estandarizar, no 43.
- `validate_corpus.py`: **0 violaciones duras**, con los mismos warns preexistentes
  (LANG_ENUM 11, VOLRANGE 24, EKMALFORMED 1, URLDUP 155, ISBN dup 1) — MIRRORREF 0 de
  23 509 refs, IMGTOP/COVER0/APPROVED/SLUGUNIQ en 0.
- `filter_non_manga.py --dry-run`: **0 rechazos** sobre 14 366 items.
- `sync_cover_preview.py --dry-run` final: **0 operaciones** (58 entries, 60 pendientes).
- `data/quality_report.json` regenerado con `scripts/audit/data_quality.py`: 784 alertas en
  14 categorías (baja de 1181 en el cierre de la mañana), "Foto repetida en el carrusel: 0"
  y "Misma foto reusada en muchas obras: 0" — las reparaciones de gotchas #181/#182 siguen
  firmes.

### Balance — 08-31 → ahora

| Métrica | Baseline 08-31 | Cierre 09-01 | 09-02 mañana (Etapas 1-2) | **Ahora (cierre whakoom)** |
|---|---|---|---|---|
| Items totales | 14 305 | 14 353 | 14 345 | **14 366** |
| Portada ≥ 90 000 px | — | — | — | **13 496** |
| Portada < 90 000 px | 754 | 579 | 513 | **497** (−18 por este apply) |
| Portada sin espejo local (`images[0]` con `url` y sin `local`) | 307 | 35 | 35 | **121** (ver nota) |
| Portadas malas (área o sin local) | 1 061 | 614 | 548 | **618** |
| Portada con `cover_upscale_factor ≥ 1.6` | n/d | n/d | 12 | **14** |
| Items sin ninguna imagen (`images: []`) | — | — | 494 | **252** (España: **34**) |
| ES con portada < 90 000 px | — | — | — | **469** (de 1 988 items ES) |
| `cover_preview.json` — entries | 413 | 58 | 59 | **58** |
| `cover_preview.json` — candidatas pending | 245 | 60 | 61 | **60** |
| Ledger `cover_rejections.jsonl` — filas | 6 | 235 | 332 | **333** |
| Caché `whakoom_edition_map.jsonl` | — | — | 326 | **461** |
| Caché `listadomanga_collection_meta.jsonl` | — | — | 0 | **226** |
| Caché `cover_search_attempts.jsonl` | — | — | — | **3 549** |

**Nota de lectura — el salto 35 → 121 en "portada sin espejo local" NO es una regresión de
este cierre**: comparando estructuralmente `items.jsonl.pre-apply-etapa2-bak` (mañana)
contra el corpus de ahora, los items **sin ninguna imagen bajaron 494 → 252 (−242)** y los
que tienen `images[0]` con `url` pero sin `local` subieron **35 → 121 (+86)**. Es decir:
~242 items que no tenían NINGUNA imagen ganaron una `url` de portada hoy —consistente con
que el paso 4e (`backfill_metadata --only image_url`) por fin terminó en rc=0 tras 7
corridas muertas por timeout, ver § "Actualización 2026-09-02"— y ~86 de esas URLs todavía
no bajaron al espejo. El remedio es una corrida de `mirror_images.py`, no una curación. Las
121 se concentran en `JP - Sumikko` (47), `Manga-Sanctuary (planning)` (23), `IT -
SocialAnime Variant` (10) y `US - Yen Press Calendar` (9) — hosts con historial de bloqueo,
no un bug del apply.

### Qué queda abierto en la vía whakoom

1. **158 items ES con `volume > 11` y portada mala** (25 sin ninguna imagen + 133 con
   portada < 90 000 px) — **fuera de alcance estructural** del skill: Whakoom sólo muestra
   los ~11 primeros tomos de una edición sin login, y `/todos` + `/comics/` exigen cuenta
   (además `/comics/` está en `Disallow:` del `robots.txt`). No hay vía limpia sin
   credenciales; queda como límite conocido, no como backlog accionable. `we_plan.py` los
   reporta como "no resolubles (vol>11, requiere login): 452" sobre el universo ES completo.
2. **7 colecciones donde el `total_tomos` remoto de listadomanga es MAYOR que la edición
   española real que indexa Whakoom** — Shangri-La Frontier (`4290`), Ranma 1/2 (`4782`),
   F.COMPO (`3720`), Inuyasha (`4753`), Attack on Titan-Norma (`5060`), Yuuna (`3346`),
   Erio to Ningyou (`5823`). `listadomanga.es` reporta ahí el total de la obra japonesa
   completa (ej. 27 vs. los 11 que cuenta Whakoom para la edición ES), y la relajación
   `ongoing` de `we_resolve.py` sólo cubre el caso inverso (`cand >= listado`). Es
   estructural, no un bug: haría falta una señal de "total de la EDICIÓN española" que
   listadomanga no expone de forma fiable.
3. **Series cuyo `series_display` está en inglés no se descubren en Whakoom** (gotcha
   **#186**): la query `site:whakoom.com "<series_display>" <editorial>` falla cuando
   Whakoom indexa por el título de la edición española (caso verificado: "A Man and His
   Cat" vs. "El hombre y el gato", Norma, `coleccion_id=3766`). El gap es de
   DESCUBRIMIENTO, no de resolución. Mejora pendiente en `we_plan.py`: query alternativa
   con `title_original`/el título del tomo local antes de rendirse con `not_found`.
4. El mecanismo `sibling_urls` (endurecimiento #4 de tanda 3) **sigue sin un caso real que
   lo ejercite** — sólo cobertura por tests sintéticos.

## Backfill post-delta de portadas (2026-09-02, cierre del día)

Cierra el remedio anotado arriba ("El salto 35 → 121... El remedio es una corrida de
`mirror_images.py`, no una curación"). Corrida real (`--skip-hosts mangavariant.com`,
default workers/cortesía por-host), sobre las 121 portadas + 53 fotos de galería sin
espejo local que dejó el delta diario (174 objetivos, 162 URLs únicas):

- **44 entries de `images[]` mirroreadas con éxito** (33 URLs únicas; 27 ≥ 90 000 px, 17 <
  90 000 px, contado por entry/consumer). Top hosts que sí bajaron: `www.manga-sanctuary.com`
  (5/23), `www.yenpress.com` (4/4), `images-na.ssl-images-amazon.com` (5/50, portadas con
  token de tamaño Amazon válido), `m.media-amazon.com` (11/27, todas < 90 000 px).
- **83 URLs fallidas a nivel HTTP** (quedan con `url` remota de fallback, comportamiento
  normal): 46 `http_404` (18 Manga-Sanctuary "planning" — ver su ficha; 21 `altraverse.de`
  galería DE - altraverse Collectors Edition; 6 `squareenixmangaandbooks...` galería "Coming
  Soon"; 1 `tokyopop.de`), 16 `not_image_or_too_large` (incluye `img.shoplineapp.com`: el
  archivo real pesa 13.18 MB, por encima del cap `_MAX_IMAGE_BYTES` de 12 MB — no es basura,
  es una imagen legítima demasiado pesada), 13 `http_5xx` (12 `www.edizionibd.it` galería +
  5 `images.yenpress.com` portada — bug de `normalize_image_url` ya documentado en
  `yenpress.md` § 2026-09-01, mismos 5 items de siempre, no son nuevos del delta de hoy), 6
  `http_400` (`m.media-amazon.com`), 1 `http_403` (`socialanime.s3...`), 1 `http_503`
  (`production.image.azuki.co`).
- **46 URLs descargaron un placeholder estructural** (HTTP 200 pero `image_store.
  placeholder_reason()` las rechazó — no se les asignó `local`, el guard de OLA 1 /
  gotcha #158 funcionando como se diseñó): **44 son SKUs de Amazon muertos de `JP -
  Sumikko`** (`tiny:1×1`, hallazgo nuevo — detalle y verificación en
  `docs/scraper/sources/sumikko.md` § 2026-09-02), + 1 `tiny:1x1` de Rakuten Books y 1
  `signature:"Cover Coming Soon"` de PRH (`images.penguinrandomhouse.com`, mismo patrón que
  la denylist de ayer, ISBN distinto).
- Corrida repetida una 2ª vez con los mismos flags: **0 cambios** (idempotente, mismo
  resultado exacto) — confirma que las 130 imágenes restantes están genuinamente
  estancadas (fuente muerta o bug conocido), no es una falla transitoria de red.

**Verificación de cierre**: `validate_corpus.py` → 0 violaciones duras, `MIRRORREF`
0 (de 23 553 refs revisadas); `pytest tests/test_extraction.py` → 714 verdes;
`sync_cover_preview.py --dry-run` → 0 cambios (`cover_preview.json` NO tocado, hash
idéntico antes/después). Backup pre-corrida:
`data/items.jsonl.pre-mirror-postdelta.20260902-133239.bak`.

**Portadas (`images[0]`) sin espejo local — estado final**: 121 → **81** (−40, −33%; el
resto de las 44 entries mirroreadas eran de galería, `images[1+]`, que no entran en este
conteo). De las 81 restantes, 42 son Sumikko/Amazon (SKU muerto, sin remedio sin cambiar
de fuente), 18 son Manga-Sanctuary "planning" (404 recurrente, ver su ficha), 9
SocialAnime + 5 Yen Press + resto (bugs/hosts ya documentados o de bajo volumen). No
queda ningún caso nuevo sin diagnosticar: las 3 categorías (404 fuente muerta / 5xx bug
de proxy conocido / SKU Amazon muerto) cubren el 100% de lo pendiente.
