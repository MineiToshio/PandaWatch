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

La portada se determina por **posición**, no por kind: `images[0]` = siempre la portada
(sincronizada con image_url/image_local); `images[1+]` = galería/extras/vistas.

**El carrusel es a nivel CLUSTER.** Un producto puede tener N filas (una por fuente),
cada una con su `images[]`. El carrusel muestra la UNION dedupeada por URL de todas las
filas. **Invariante crítico**: la portada de la fila canónica (`merged.image_url`, la que
muestra la card) va SIEMPRE primera en la union — si no, el carrusel discrepa de la card.
Este merge vive en TRES lugares que DEBEN coincidir: `web/index.html` (`dedupByUrl`),
`build_web.py` (`_merged_canonical`), `web-next/.../ItemHero.tsx`. Tocás uno → tocá los
tres. El gestor de imágenes opera igual a nivel cluster (`_update_item_images` propaga el
set editado a todas las filas del cluster).

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

**Fase 1 — espejo local `data/images/` (IMPLEMENTADA).** El scrape descarga la portada de
cada item nuevo/cambiado a `data/images/<sha256(image_url)[:16]>.<ext>` y guarda el
**filename** (no la URL) en `image_local`. Características:
- **Multi-imagen**: el extractor `_extract_images_from_detail_soup(soup, url, limit=6)` trae
  todo el carrusel del producto a `images[]` (JSON-LD + og/twitter + selectores de galería
  Shopify/Tiendanube/WooCommerce/Magento + genéricos), acotado al scope del producto y
  filtrando "productos relacionados" (gotcha #31). Un solo `<img>` → lista de 1.
- `image_url` queda como provenance + fallback (espejo falla → image_url remoto → 📚).
- On por defecto en todo scrape; `--skip-image-download` lo desactiva. Primitivas en
  `image_store.py`; orquestado por `mirror_candidate_images()`.
- **Idempotente** (nombre determinístico). **Validación magic bytes** (descarta HTML de
  error servido como imagen; la extensión sale de los bytes). `image_local` sticky (gotcha #25).
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
(`mcp__Claude_in_Chrome__*`):

1. Verifica que Chrome esté conectado (`list_connected_browsers`).
2. Filtra `items.jsonl`: imagen < `--min-pixels` px (default 100 000), saltando slugs
   que ya tienen candidatas `pending` en `cover_preview.json`.
3. Para cada item, navega `https://www.google.com/search?tbm=isch&q={query}` con
   `mcp__Claude_in_Chrome__navigate`. Query = `{title_original} {publisher_short} portada`.
4. Extrae hasta 10 URLs full-res con `mcp__Claude_in_Chrome__javascript_tool` (campo
   `"ou":"..."` de los `<script>` embebidos por Google).
5. Valida cada URL con `_sc_validate.py` (script temporal en `scripts/retrofit/`):
   - Píxeles: `new_px ≥ max(curr_px × 1.5, 30 000)` (si sin imagen actual: ≥ 10 000)
   - Aspect ratio: `|new_w/h − curr_w/h| / (curr_w/h) ≤ 0.25`
   - Identidad: aHash Hamming > 3 (≤ 3 = misma imagen → descartar)
   - Dominio no es red social / baja calidad (pinterest, instagram, twitter, reddit…)
6. Guarda imágenes válidas en `data/images/` (`_save_image`, nombre sha256).
7. Flush atómico a `data/cover_preview.json` después de cada item.

**Invariantes**:
- Candidatas: `confidence: "low"`, `status: "pending"` — sin excepción.
- Máximo 10 candidatas por item.
- `_sc_validate.py` es temporal — se borra al finalizar el skill.
- **NUNCA** modifica `items.jsonl`. La aprobación es manual vía `cover-preview.html`.

