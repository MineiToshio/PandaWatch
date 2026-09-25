# Fuente: Aladin (Corea del Sur)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-12 (alta de la fuente).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | KR - Aladin (만화 한정판) |
| **URL base** | `https://www.aladin.co.kr` |
| **Punto de entrada** | `/search/wsearchresult.aspx?SearchTarget=Book&SearchWord=만화+한정판&page=1` (~428 resultados, 18 págs) |
| **Tipo de fuente** | Librería online multi-editorial (retailer) |
| **`kind`** | `html` |
| **`source_class`** | `retailer` |
| **País / idioma** | Corea del Sur / Coreano |
| **`publisher`** | **VACÍO** (gotcha #44) — el real (학산문화사/Haksan, 대원씨아이/Daewon, 디앤씨웹툰비즈/D&C…) sale de la ficha |
| **Cobertura** | 한정판 (ediciones limitadas) de manga japonés licenciado + webtoons coreanos en print |
| **Aporte al corpus** | ~390 reportables (primera fuente de Corea; el país estaba en 0) |
| **Parser** | Entrada en `sources.yml` con selector `div.ss_book_box` |

**Por qué importa**: abre Corea de 0. Las 한정판 coreanas son **ediciones limitadas
DE FÁBRICA** con ISBN y precio propios (2-3× el tomo regular) — estructuralmente
distintas del patrón BooksPrivilege (tomo regular + regalo de tienda), por eso la
fuente pasó la evaluación aunque no haya foto del extra. Cubre además ediciones
print de webtoons coreanos (Solo Leveling/나 혼자만 레벨업, 화산귀환) que NO existen
en ninguna otra fuente del corpus.

---

## 2. Descripción técnica

- HTML server-rendered (~296KB por página), sin anti-bot, paginación `&page=N`.
- **La paginación del sitio es JS** (`Javascript:Page_Set('2')`) — el paginador
  genérico la sigue gracias a: (1) `&page=1` explícito en la URL fuente y
  (2) la extensión 2026-06-12 de `find_next_page_url` estrategia 4 que acepta
  evidencia de página siguiente en llamadas JS de paginación.
- Detalle (`/shop/wproduct.aspx?ItemId=N`): ISBN-13 coreano (979-11-…), fecha
  exacta, editorial, precio KRW.
- Señales en coreano (alta 2026-06-12 en `KEYWORD_RULES`): 한정판 (limited, 50),
  특별판/특장판 (special), 박스 세트 (box), 아트웍스/화집 (artbook), 포토카드/아크릴 (bonus).

## 5. Proceso de ingestión

- FASE 1 (fuente YAML). `max_pages: 18`. Dry-run de alta: 428 candidatos / 389
  reportables.

## 8. Problemas conocidos

- **Sin foto del extra** (solo portada del tomo; los extras se listan como texto).
- **Títulos en coreano**: la serie requiere aliases KO en `series_aliases.yml`
  (장송의 프리렌 → frieren, 스파이 패밀리 → spy-x-family…). Hasta correr
  `/watch-enrich-series-aliases`, muchos items quedarán en unmapped_series.
- **El selector de título capturaba la tarjeta ENTERA** (gotcha #94, 2026-06-13):
  `title` quedaba como "{título} {vol} (한정판) - {bonus} {autor}(지은이) |
  {editorial}(만화) | {fecha} {precio} → {oferta} (할인), 마일리지 … 세일즈포인트"
  (367 items). El nombre oficial termina en el marcador de edición "(…한정판)" /
  "한정판 [박스] [세트]". Fix: `clean_title` ahora corta la cola de tienda coreana
  (`_strip_korean_retailer_tail`, sólo si hay Hangul) — aplica a items nuevos y se
  limpió el histórico con `clean_titles.py`. **Pendiente**: afinar el
  `title_selector` del YAML para capturar sólo el link del producto (evitar la
  tarjeta entera) — hoy el saneo depende de `clean_title`.
- **Curación LLM non-manga 2026-08-23**: 3 items expulsados — una figura de
  열혈강호 (한비광) y dos cómics Marvel en coreano (블랙팬서 히든 젬 패키지, 시빌 워 2
  스페셜 에디션); se agregaron "시빌 워" y "블랙팬서" a `data/comics_blacklist.yml`.

## 9. Pendientes

- **Aladin OpenAPI (TTB key gratuita)** como upgrade futuro: más estable que
  HTML, devuelve ISBN/portada en JSON. Evaluar si la fuente escala.
- Poblar aliases KO (queue en `data/unmapped_series.jsonl` tras la primera ingesta).

## 10. Runbook

```bash
.venv/bin/python scripts/manga_watch.py --only-source "KR - Aladin (만화 한정판)" --dry-run
```

## 2026-08-28 — la búsqueda `만화 한정판` trae figuras, no libros

Delta diario (`logs/scrape-delta-2026-08-28-160959/`). Dos items marcados
`is_manga=false` por el LLM del skill de estandarización, pendientes en
`data/unmapped_series.jsonl` (reason `llm_non_manga`):

- `열혈강호 피규어 한비광 한정판` (Ruler of the Land — figura de Han Bi-Kwang, ed. limitada)
- `열혈강호 피규어 합본 한정판` (Ruler of the Land — pack de figuras, ed. limitada)

Causa: la query `만화 한정판` ("manhwa/manga edición limitada") matchea también el
**merchandising** de una serie de manhwa. `피규어` = *figure*. Son productos de una obra
del catálogo, pero no son material impreso.

**Para el owner (no aplicado):** excluir `피규어` (figure) del parser o de la blacklist
para esta fuente. Retorno: barato y de bajo riesgo — el término es inequívoco y corta
la re-ingesta diaria.

## 2026-09-01 — un item tenía un ÍCONO DE UI como `images[0].url` (no una portada)

OLA 1 de depuración de imágenes (auditoría de portadas sin espejo local, gotcha #158).
Uno de los 5 items de Aladin pendientes de espejo local tenía
`image.aladin.co.kr/img/search/icon_arrow.jpg` como URL de portada — no un JPEG de
producto: es una flecha de UI de **8×9 px** (`image_store.placeholder_reason()` la
clasifica `tiny:8x9`, la misma regla estructural que ya cubre tracking pixels de otras
fuentes, sin necesidad de fichar una firma nueva).

El backfill de `mirror_images.py` la descargó (200, `image/jpeg`, 367 bytes), la
detectó como placeholder DESPUÉS de la descarga (chequeo nuevo del punto 2 del
encargo — ver gotcha #158) y **no la asignó como `local`** — el item queda sin
portada mirroreada en vez de con un ícono de flecha como "cover", que es el
comportamiento correcto. Pero el bug real está más arriba: el parser HTML de esta
fuente (búsqueda `만화 한정판`) extrajo esa URL como portada del producto para
empezar — probablemente un ícono de "siguiente resultado" de la página de búsqueda
capturado por un selector de imagen demasiado laxo.

**Para el owner (no aplicado):** esta fuente NO tiene módulo propio — es `kind: html`
genérico en `sources.yml` (sólo `selectors.item_selector: "div.ss_book_box"`, sin
`selectors` de imagen dedicados), así que el extractor genérico de imágenes
(`manga_watch.py::_extract_images_from_detail_soup`) es el que está capturando
`icon_arrow.jpg`. Habría que revisar qué selector/heurística genérica lo atrapa (¿un
`<img>` suelto dentro del scope del item que no es la portada real?) y excluir rutas
`/img/search/` o íconos <10px de forma genérica (no sólo para Aladin — el mismo
extractor lo comparten ~150 fuentes). Bajo riesgo: un único item detectado en esta
auditoría, no una regresión masiva.

## 2026-09-02 — `cover150/` no es "baja resolución", es recorte destruido

Hallazgo de la Etapa 1 de triage de imágenes (`docs/reference/images.md` § "Etapa 1 —
resultados"). Aladin sirve `image.aladin.co.kr/product/.../cover150/...` con el **ancho fijo
en 150 px y el alto sin normalizar**, y cuando el producto es una foto de caja/pack apaisada
el resultado es una banda inutilizable: `150×76` (`frieren-unknown-limited-kr-10`), `150×83`
(`d-gray-man-unknown-limited-kr-6`), `150×100` (`return-of-the-mount-hua-sect-unknown-
limited-kr-21`), `150×136` (`hayate-no-gotoku-unknown-limited-kr-1`). No es un problema de
resolución que un upscaler pueda arreglar: **ya no queda portada en la imagen**. Son las 4
primeras de la lista de prioridad para búsqueda web (Etapa 2), por delante de cualquier
portada simplemente blanda.

**Pendiente (no aplicado)**: verificar si Aladin expone una variante de mayor tamaño en la
misma ruta (p. ej. `cover500/`, `letslook/`) para reemplazar `cover150/` en la ingesta —
sería un fix de mecanismo y no de síntoma, y evitaría reencolar estos ítems en cada tanda.

También salieron de esta fuente 2 `imagen_equivocada`: `katekyo-hitman-reborn-
haksanmunhwasa-limited-kr-16` (escaneo de una página en blanco / el lomo con el código de
barras) y `debut-or-die-unknown-limited-kr-2` (collage de merch en vez de la portada).

## 2026-09-02 — CONFIRMADO: `cover500/` existe en la misma ruta y es la MISMA imagen en
## mucha mejor resolución (cierra el "pendiente" de arriba)

Verificado con requests reales (Etapa 2, tanda 2, `/watch-search-covers`): la ruta de imagen
de Aladin es `image.aladin.co.kr/product/<id>/<subcarpeta>/<tamaño>/<archivo>`, y **el mismo
`<id>/<subcarpeta>/<archivo>` existe con `<tamaño>` = `cover500` además de `cover150`** — no
es una variante distinta, es el MISMO archivo servido en otra resolución por el CDN de
Aladin. Confirmado en 2 productos reales del corpus:

| Item | `cover150` (actual, apaisado destruido) | `cover500` (mismo archivo, HTTP 200) |
|---|---|---|
| `return-of-the-mount-hua-sect-unknown-limited-kr-21` | `150×100` (15 000 px), 6 998 bytes | **`600×400`** (240 000 px), 63 061 bytes — portada real de las 2 tapas del box set, confirmado visualmente |
| `d-gray-man-unknown-limited-kr-6` | `150×83`, 4 522 bytes | `cover500` HTTP 200 pero sólo 6 819 bytes (el contenido en sí es chico — ver nota abajo) |

**16× más píxeles** para `return-of-the-mount-hua-sect` con una simple sustitución de
carpeta en la URL — sin necesitar `_same_cover` (es el mismo archivo, no una candidata
externa) ni búsqueda web. `letslook/` con el mismo nombre de archivo dio 404 (no es un
tamaño válido para ese producto; `cover500` sí lo fue en ambos casos probados).

**No lo consume el skill todavía** (footgun descubierto en la misma tanda): la vía de
búsqueda web SÍ encontró estas URLs `cover500` para 2 items vía Bing texto (misma serie,
resultado orgánico), pero `sc_validate.py` las **rechazó** — no por `_same_cover` (que dio
`True`, distancia 0) sino por `candidate_metadata_conflict()`, que interpreta el sufijo
`_1`/`_2` del NOMBRE DE ARCHIVO (`k622831461_1.jpg`, `8925290057_1.jpg` — el índice de
foto de Aladin: portada=`_1`, contratapa=`_2`, etc.) como si fuera un MARCADOR DE VOLUMEN
(`_VOL_BARE_RE`), y lo compara contra `item.volume` (21, 6…) — conflicto falso, hard-reject.
Detalle del mecanismo y fix propuesto: gotcha #177.

**Recomendación de mecanismo** (aplicada, ver sección siguiente): agregar al motor de
portadas (`fetch_better_covers.py`) un intento CDN determinístico específico de Aladin —
igual que ya existe para ISBN/Amazon/PRH/OpenLibrary/GoogleBooks — que pruebe
`cover500`/`cover800`/etc. en la MISMA ruta antes de ir a búsqueda web. Es más barato,
más preciso (0% falsos positivos posibles — es el mismo archivo) y evita el problema del
gotcha #177 por completo para esta fuente.

## 2026-09-02 — Upgrade determinista aplicado (cierra gotcha #177) + fix del heurístico de volumen

Dos fixes de mecanismo, ambos en la fuente única:

**1. `candidate_metadata_conflict`/`_extract_candidate_volumes` (`fetch_better_covers.py`)
ya no confunde el índice de foto Aladin (`_1`/`_2`) con el tomo.** Regla general (no
hardcodeada a este host): un sufijo bare `_N` sólo se ignora como volumen cuando queda
INMEDIATAMENTE antes de la extensión Y el token que lo precede es un ID de catálogo
numérico largo (≥6 dígitos, a lo sumo 1 letra de prefijo — `k622831461`, `8925290057`).
Detalle y tests en gotcha #177.

**2. Upgrade determinista** (`upgrade_image_resolution.py`, patrón nuevo): `cover<N>/` con
`N<500` → `cover500/` en la misma ruta, con guard de no-downgrade y `--min-gain 0.10`.
Corrida real sobre el corpus completo (`--host aladin.co.kr`, backup
`items.jsonl.pre-aladin-upgrade-bak`):

| Métrica | Valor |
|---|---|
| URLs candidatas (`cover150`×90 + `cover200`×281, portada+galería) | 371 (351 únicas) |
| Mejoradas | **297** |
| Sin mejora real | 54 |
| Errores | 0 |
| Ganancia de píxeles — mediana | **×6.25** |
| Ganancia de píxeles — rango | ×1.77 – ×16.04 |

De las 54 "sin mejora": una parte ya estaba en el techo real del CDN (`cover150`/`cover200`
devuelven el mismo archivo que `cover500` cuando el escaneo original es chico — confirmado
con requests reales, mismas dimensiones exactas), y otra parte tenía la portada local
previamente pasada por `upscale_images.py` (`upscaled: true`, más píxeles SINTÉTICOS que el
`cover500` real) — el gate `--min-gain` correctamente no reemplaza detalle interpolado por
menos píxeles reales, aunque más fieles. Segunda corrida real (idempotencia, gotcha
#159/#163): **0 mejoradas adicionales**.

**De los 4 items con recorte apaisado destruido** (tabla de la sección "cover150/ no es
baja resolución" arriba): **2 quedaron resueltos** por el upgrade —
`return-of-the-mount-hua-sect-unknown-limited-kr-21` (15 000→240 000 px, ×16, ya sobre el
piso de 90 000 px de `LOW_QUALITY_PX`) y `frieren-unknown-limited-kr-10` (11 400→182 400 px,
×16) — y **2 siguen bajo el piso** porque Aladin no tiene más detalle real que ofrecer:
`hayate-no-gotoku-unknown-limited-kr-1` (20 400→36 200 px) y `d-gray-man-unknown-limited-kr-6`
(12 450→29 440 px, confirma la nota de arriba: "el contenido en sí es chico").

**Nota**: el candidate `approved` en `data/cover_preview.json` para
`return-of-the-mount-hua-sect-unknown-limited-kr-21` (URL externa `ae04.alicdn.com`, mismos
240 000 px) quedó redundante contra la portada nativa de Aladin ya aplicada —
`sync_cover_preview.py --dry-run` no lo poda porque las candidatas `approved` son
intocables por diseño. Decisión del owner si aplicarlo igual (mismo contenido) o
descartarlo; no se tocó `cover_preview.json` en este cierre.

Suite completa verde (2432 tests, +11 de este cambio), `validate_corpus.py` 0 violaciones
duras. Detalle del fix de `candidate_metadata_conflict` en gotcha #177;
`upgrade_image_resolution.py` en `docs/reference/images.md` § "Upgrade de resolución" y
`scripts/retrofit/README.md`.

## 2026-09-02 — Reparación de imagen duplicada en `images[]` (gotcha #181)

El upgrade `cover150`/`cover200`→`cover500` de arriba dejó **151 items KR-Aladin** con la
MISMA foto duplicada dentro de `images[]`: la portada (`images[0]`) ya estaba en `cover500/`
por otro camino (JSON-LD/og:image) mientras una entry de galería apuntaba al mismo archivo
bajo `cover150/`/`cover200/` — URLs distintas hasta que el upgrade normalizó ambas a la misma
`cover500/`. Causa raíz, fix de mecanismo (`dedupe_item_images()` en
`upgrade_image_resolution.py`) y la reparación completa (156 items/161 entradas en TODO el
corpus, no sólo Aladin) están en `docs/reference/gotchas.md` #181 y
`docs/reference/images.md` § "Cierre de los 2 hallazgos 'no corregidos acá'". Ningún item de
esta fuente perdió portada; 0 items `approved_at` de Aladin tocados.

## 2026-09-07 — 130 títulos (30 % de la fuente) llevan el CROMO de la lista pegado adelante

**Hallazgo nuevo, verificado en vivo. Viola la política dura de títulos** (`title` = nombre
oficial del producto; ver `docs/reference/title-policy.md`).

### Síntoma

El item nuevo de hoy entró con este título:

```
2단 아크릴 스탠드/ 키보드 덮개(대상도서 구매 시) [국내도서] 고깔모자의 아틀리에 16 (한정판)
```

El producto real es `고깔모자의 아틀리에 16 (한정판)` (Witch Hat Atelier 16, edición
limitada). Todo lo anterior a `[국내도서]` es texto de la promoción de la lista
("soporte acrílico de 2 pisos / funda de teclado (al comprar el libro objetivo)").

### Alcance medido sobre el corpus

| Métrica | Valor |
|---|---|
| Items de la fuente | 438 |
| Con `[국내도서]` en el título | **130 (29.7 %)** |
| De esos, con basura ANTES del tag | **130 (100 %)** |
| Que arrancan con el número de puesto (`"NN. "`) | 111 |

Ejemplos del corpus (basura → título real):

| Prefijo capturado | Título real |
|---|---|
| `144.` | 뱀파이어 기사 한정판 박스 세트 |
| `220.` | 슬램덩크 완전판 프리미엄 한정판 박스 세트 |
| `이 만화가 대단하다! 역대 수상작 모음` | 타몬 군 지금 어느 쪽?! 6 (한정판) |
| `책과 함께 무료배송 - 함께 사기 좋은 특가 도서 · 저가 도서 총집합` | 블루 록 30 (한정판) |

El patrón es **regular**: el título real siempre empieza justo después de `[국내도서]`.

### Causa raíz (verificada en vivo)

La fuente declara `item_selector: "div.ss_book_box"` y **ningún `title_selector`**
(`sources.yml:2117-2118`), así que el título sale de la heurística genérica sobre el texto
del contenedor. Ese contenedor incluye, en este orden: el número de puesto, el banner
promocional del bloque, `크게보기`, la etiqueta de categoría `[국내도서]`, el título, la
lista de extras y el autor.

En la página de resultados **existe el elemento correcto**: `a.bo3` devuelve el título
limpio, ya verificado contra el sitio en vivo:

```
a.bo3 → "GACHIAKUTA 18 (한정판)"
a.bo3 → "손끝과 연연 13 (한정판)"
a.bo3 → "고깔모자의 아틀리에 16 (한정판)"
```

Es la misma familia de fallos que las gotchas #187/#188 y que el `author` de Funside
(#193): un selector demasiado ancho captura el **cromo de la plantilla** junto al dato.

### Impacto

- **130 fichas muestran un título equivocado en la UI** — y el título es el campo con
  política más dura del proyecto.
- Contamina aguas abajo: `series_display` se deriva del título, así que la serie también
  sale mal en esos items; y el ruido ("무료배송", "굿즈", números de puesto) es el tipo de
  término que descoloca a los filtros y al matching de aliases.
- **Se re-escribe en cada corrida** mientras el selector no cambie: limpiar los títulos
  ahora sin arreglar el selector es trabajo que el próximo delta deshace.

### Recomendación (NO aplicada — decisión del owner)

1. **Agregar `title_selector: "a.bo3"`** a la fuente en `sources.yml`. Es una línea, el
   elemento ya está verificado en vivo, y elimina la causa.
2. **Después** de (1), pasar `clean_titles.py` sobre los 130 items para reparar lo ya
   ingresado (el corte por `[국내도서]` es determinista y seguro: el título real siempre
   queda a la derecha del tag).

Cambiar `sources.yml` es configuración de fuente = decisión del owner; la rutina diaria
documenta y recomienda.

### 2026-09-07 (mismo día) — RESUELTO

**Aplicado**, las dos partes:

1. `sources.yml` ahora declara `title_selector: "a.bo3"` para esta fuente.
2. `scripts/retrofit/fix_aladin_list_chrome_titles_20260907.py` reparó los **130**
   títulos ya ingresados, cortando por el último `[국내도서]` (determinista: el
   título real siempre queda a la derecha del tag). Idempotente — segunda pasada:
   0 cambios.

Verificación posterior: 0 títulos de la fuente conservan la etiqueta de categoría.

## 2026-09-21 — Fallback de slug por ISBN se fosiliza (gotcha #213)

El item nuevo `메리 마블링 9~10 세트 - 전2권 (한정판)` (Merry Marbling, set limitado de 2
tomos, Haksan, rareza `rare`) quedó con `slug = isbn-9791141116118` aunque su
`edition_key` post-estandarización es el correcto: `merry-marbling-haksan-limited-kr`.

Causa: con el título 100% en coreano la derivación CRUDA no saca serie y cae al fallback
de ISBN para el slug; después el LLM resuelve la serie bien, pero `generate_slugs.py`
corre `--only-missing` y no lo reescribe. Es la gotcha **#213** (mecanismo general,
medición y fix propuesto allá) y Aladin es la fuente donde más probable es que ocurra,
porque es la que más títulos sin romanización aporta.

**Nada aplicado (decisión del owner).**

### Auditoría full — 2026-09-24

El extractor reconoce `16 (한정판)` y conserva rangos `9~10 세트` como `9-10`;
no confunde la cantidad total de libros `전2권` con el número de volumen. Se
verificaron 18 páginas y 441 candidatos antes de filtros finales en staging.

### Reparación de referencias históricas — 2026-09-24

Se quitaron 9 referencias de `www.aladin.co.kr` asociadas a otra fila con ISBN
válido diferente del producto cuya URL primaria es esa misma referencia. Se
conservan ambos productos y su URL primaria; no se fusionan por ISBN. Evidencia
por URL/ISBN en `reports/ingestion-audit-2026-09-24/closure/publication-2-manifest.json`.
