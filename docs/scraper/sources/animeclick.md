# Fuente: AnimeClick

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | AnimeClick |
| **URL base** | `https://www.animeclick.it` |
| **Índice / punto de entrada** | `https://www.animeclick.it/calendario-manga` (calendario semanal de salidas) |
| **Página de un producto** | `https://www.animeclick.it/edizione/<id>/<slug>` |
| **Tipo de fuente** | Catálogo comunitario / base de datos italiana de manga-anime (no es tienda) |
| **`kind`** | `wiki` (módulo propio, NO tiene entrada en `sources.yml`) |
| **`source_class`** | `trusted_media` |
| **País** | Italia (`Italia`) — fuente mono-país |
| **Idioma** | Italiano |
| **Cobertura** | Ediciones especiales (variant / limitata / cofanetto / artbook / box set) del mercado italiano, vía calendario semanal de salidas en librería |
| **Aporte al corpus** | ~1035 items |
| **Parser / módulo** | `scripts/wikis/animeclick.py` |

**Editoriales que abarca** (entre paréntesis, volumen aproximado de items en el corpus):

Panini Comics (≈356) · JPOP (≈113) · Star Comics (≈79) · 001 Edizioni (≈68) ·
Dynit (≈68) · Mangasenpai (≈62) · Goen (≈40) · Coconino Press (≈32) · Magic Press
(≈31) · Panini / Planet Manga (≈28) · Jundo (≈28) · Ishi Publishing (≈23) ·
Saldapress (≈15) · MangaYo! (≈10) · Bao Publishing (≈9) · Editoriale Cosmo (≈8) ·
Musubi Edizioni · Nippon Shock Edizioni · Toshokan · Dokusho Edizioni, entre otras.

Recuerda: `publisher` = editorial real, NO la tienda (#44). Acá la editorial sale
del propio detalle de la edición (campo "Editore:").

**Por qué importa / qué aporta de único**: es la cobertura **amplia del mercado
italiano de ediciones especiales**. Complementa a SocialAnime (que trae ISBN al
~95% pero sólo cubre ~7 editoriales menores): AnimeClick da cobertura mucho más
ancha (todas las editoriales IT grandes) **a cambio de no tener ISBN**, pero sí
fecha de salida. Es la vía principal para captar variant/limitata/
cofanetto de Panini, Star Comics, J-POP y MangaYo! en Italia.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**:
  - `calendario-manga` — calendario **semanal** de salidas en librería. El estado
    inicial (día/mes/año de la semana actual) se lee de `div#calendario-pagination-div`
    (atributos `data-current-day` / `-month` / `-year`). El contenido de la semana
    actual vive en `div#calendario-days-thumbs`.
  - Navegación hacia atrás vía **endpoint AJAX**:
    `GET /calendario-manga?paging=prev-week&month=MM&year=YYYY&day=DD&tipo[]=&inLista=false&nazioni[]=`
    con headers `X-Requested-With: XMLHttpRequest` y `Accept: application/json, */*`.
    Respuesta JSON: `{"ok": true, "data": {"html": "<div…>", "month": "...", "year": "...", "day": "..."}}`.
  - `edizione/<id>/<slug>` — página de detalle de UNA edición.
- **Estructura del HTML/feed**:
  - **Card del calendario** (`div.panel-evento-calendario`): link a `/edizione/<id>/…`,
    `h3` = título con qualifier (ej. "100 Metres - Hyakuemu Variant MangaYo! 1"),
    `h4.edizione` = publisher, `h5` = serie, `img.img-evento` con la portada en
    `data-original` (lazy; `src` es placeholder).
  - **Detalle** (schema.org `Book`): `h1[itemprop="name"]` (título),
    `img[itemprop="image"]` (portada), `p[itemprop="description"]` (sinopsis),
    `meta[itemprop="datePublished"]` (fecha de salida), y `<strong>` con etiquetas
    `Editore:` (editorial).
- **Identificador de producto**: el `id` de edición del path `/edizione/<id>/…`
  (regex `/edizione/(\d+)/`). Se usa para deduplicar entre semanas (`seen_ids`).
- **Anti-bot / quirks**:
  - Calendario **JS/AJAX**: el HTML semanal se sirve por endpoint AJAX, no como
    páginas estáticas paginadas. El parser lo consume directo con `requests` + los
    headers de XHR (no necesita Playwright).
  - **Sin ISBN** en todo el sitio: el modelo de datos de AnimeClick no lo expone.
  - Portadas con **lazy-load** (#6): la URL real está en `data-original`, no en `src`
    (placeholder). El parser prefiere `data-original` y descarta lo que no termine
    en `.jpg/.jpeg/.png/.webp`.
- **Calidad de imágenes**: la portada del detalle (`img[itemprop="image"]`,
  `/immagini/manga/.../edizione-ID.jpg`) suele ser mejor que la del thumbnail del
  calendario. El parser también intenta una galería multi-imagen del detalle
  (`_extract_images_from_detail_soup`) y la adjunta cuando hay más de una.

---

## 3. Proceso de ingestión — vista de producto

> Sólo entran las **ediciones especiales** (collector-grade). Una salida normal del
> calendario (un tomo regular sin qualifier) NO entra.

1. **Cargar el calendario semanal** (`/calendario-manga`) y leer el estado actual
   (día/mes/año de la semana en curso).
2. **Tomar la semana actual** y luego **navegar hacia atrás semana por semana** vía
   el endpoint AJAX, hasta cruzar el **cutoff** (`--wiki-from YYYY-MM`).
3. **Por cada card de cada semana**: si el **título trae un qualifier de edición
   especial** (variant, limitata/limited, special, deluxe, ultimate, cofanetto,
   collector, esclusiva, premium, artbook, kanzenban, completa/integrale, box set),
   el item **entra**; si no, se **descarta**.
4. **Abrir la página de detalle** del item que entró: de ahí salen fecha de
   salida, sinopsis, editorial y la portada de mejor calidad.
5. **Repetir** hasta agotar las semanas dentro del cutoff.

**Reglas de producto que nunca se rompen:**
- País = edición (#46): todas las ediciones son de Italia (es el país de la
  editorial/idioma, no el de una tienda).
- Sólo califica lo collector-grade: el filtro por keyword en el título es el gate
  de entrada; un tomo regular del calendario NO es coleccionable.

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

Ambos usan el mismo parser y el mismo discovery (calendario semanal hacia atrás);
sólo cambia **hasta dónde retroceden** (el cutoff `--wiki-from`) y el timeout:

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| Script / paso | `scripts/scrape_full.sh` — paso `2k` | `scripts/scrape_delta.sh` — paso `2j` |
| `--wiki-from` | `2015-01` (catálogo histórico) | `$LISTADO_CAL_FROM` (~últimos 3 meses) |
| Discovery | navega el calendario semanal hacia atrás hasta 2015 | igual, acotado a los últimos ~3 meses |
| Timeout | hasta **4 h** (`14400 s`) | **45 min** (`2700 s`) |
| Cuándo | refresh completo del catálogo | novedades recientes |

- El cutoff es una **fecha** (`YYYY-MM`, primer día del mes); el bootstrap retrocede
  mientras la semana mostrada sea ≥ cutoff. Hay un tope de seguridad `MAX_WEEKS=520`
  (~10 años).
- **Costo del FULL**: navegar ~500 semanas + un **fetch de detail page por cada item
  collector** que pasa el filtro puede ser miles de requests HTTP; por eso el timeout
  largo. Cada item que entra **siempre** hace fetch de su detalle (fecha/
  sinopsis/editorial/portada sólo viven ahí — ver §5.2). El delta lo acota a ~3 meses.
- Ambos pasos corren con `--sleep-seconds 0.5` y `--min-score 20`.

---

## 5. Proceso de ingestión — técnico

Parser: [`scripts/wikis/animeclick.py`](../../../scripts/wikis/animeclick.py). NO
tiene entrada en `sources.yml`; se invoca con `--bootstrap-wiki animeclick`
(despachado en `scripts/manga_watch.py`).

### 5.1 Modelo de datos / claves

- La fuente virtual la arma `_virtual_source()`: `name="IT - AnimeClick (edizioni
  speciali)"`, `country="Italia"`, `language="Italiano"`, `source_class="trusted_media"`,
  `kind="wiki"`, `purity="manga_only"`, tags `["wiki", "animeclick", "italia"]`.
  El `publisher` se sobreescribe con el de cada edición (campo "Editore:").
- **Sin ISBN**: el cluster_key NO puede usar tier `isbn:`; cae al tier que aplique
  (`edition:`/`fuzzy:`/`url:`). La identidad de producto es la URL de la edición
  (`/edizione/<id>/…`).
- País = Italia, va al edition_key como en el resto del corpus (#46).

### 5.2 Qué captura el parser (mapea el §3 al código)

- `parse_calendar_html(html)` — extrae las cards (`div.panel-evento-calendario`):
  título (`h3`), URL (`/edizione/…`), publisher (`h4.edizione`), imagen
  (`img.img-evento` → `data-original`).
- `is_collector_edition(title)` — gate por keyword (`_COLLECTOR_RE`: variant /
  limitata / limited / special / deluxe / ultimate / extreme / cofanetto /
  collector / esclusiva / exclusive / premium / artbook / kanzenban / completa /
  integrale / box set). Sólo pasa lo que matchea.
- `parse_detail_page(html, url)` — del detalle (schema.org `Book`): título,
  imagen, descripción, `release_date` (`datePublished`), `publisher` (parsea el
  texto tras "Editore:" y corta antes de la siguiente etiqueta, ej. "Nazionalità:")
  (el campo `price` de la página ya no se captura).
- `_inject_collector_hints(title, description)` — inyecta hints en la descripción
  ("Cofanetto Box Set", "Complete edition integral") para que `detect_signals`/
  `score_candidate` los reconozca como señal de coleccionable.
- `bootstrap(...)` — orquesta: navega semanas, deduplica por `edition_id`, aplica el
  filtro, fetcha detalles (`fetch_details=True` siempre, forzado en manga_watch.py),
  arma cada `Candidate`, le corre `score_candidate`, y filtra por `min_score`.
  Flushea cada `_FLUSH_EVERY=25` candidatos vía `flush_fn` (escritura incremental a
  items.jsonl para no perder datos si el proceso muere a mitad).

### 5.3 Flujo end-to-end

- **FULL**: `scrape_full.sh` paso `2k` (`--wiki-from 2015-01`, timeout 4 h).
- **DELTA**: `scrape_delta.sh` paso `2j` (`--wiki-from` ~3 meses, timeout 45 min).
- Tras el bootstrap, los items quedan en items.jsonl y pasan por los **cleanup
  retrofits** de la fase 3 (rescore → filtros → clean_titles → backfill metadata/
  imágenes → consolidate) como cualquier otra fuente, y luego build + validate.
- `fetch_details=True` se **fuerza** para animeclick en `manga_watch.py` (el
  calendario sólo da título + publisher + imagen; fecha/sinopsis/editorial/portada
  están sólo en el detail page). El flag CLI `--fetch-details` es para el source
  loop principal, otro propósito.

> ⚠️ Tras un scrape, items.jsonl queda **raw** (sin `standardized_at`). NO correr el
> skill `/watch-standardize-catalog` automáticamente (lo decide el owner).

---

## 7. Validación

- **`scripts/validate_corpus.py`** — gate estructural, aplica a TODO el corpus
  (incluye los items de animeclick).
- **Idempotencia**: animeclick NO tiene retrofits/enforcer propios; el bootstrap es
  re-ejecutable (`append_jsonl` idempotente: re-correr actualiza campos sin
  duplicar). La dedup por `edition_id` entre semanas evita repetidos dentro de una
  misma corrida.
- **Debug del parser** (sin escribir): ver §10.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Calendario AJAX (no estático)**: el contenido semanal se sirve por endpoint XHR
  (`paging=prev-week`), no como páginas paginadas. → ✅ se consume con `requests` +
  headers de XHR; no hizo falta Playwright (#12).
- **Lazy-load de portadas (#6)**: la URL real está en `data-original`, no en `src`
  (placeholder). → ✅ el parser prefiere `data-original` y descarta lo que no sea
  imagen real (sin extensión válida).
- **Editore + Nazionalità pegados**: el bloque "Editore:" puede venir seguido de
  "Nazionalità:" en el mismo nodo. → ✅ el parser corta el publisher antes de la
  siguiente etiqueta (palabra previa al siguiente ":").
- **Decisiones (lo que NO se hace)**:
  - **Sin ISBN**: no se intenta derivar/inventar ISBN; AnimeClick no lo expone. La
    cobertura ancha (todas las editoriales IT) es el trade-off frente a SocialAnime
    (que sí trae ISBN pero cubre menos editoriales).
  - **Sólo collector-grade**: un tomo regular del calendario NO entra (gate por
    keyword en el título); no se captura la edición normal completa.

---

## 9. Pendientes / limitaciones conocidas

- **Sin ISBN**: limita el matching `isbn:` de cluster_key con otras fuentes; el cruce
  con SocialAnime/listas IT depende de `edition:`/`fuzzy:`.
- **Filtro por keyword de título**: si una edición especial NO trae un qualifier
  reconocido en el título (`_COLLECTOR_RE`), no entra. Ediciones especiales con
  nombres atípicos podrían perderse (falso negativo). No medido sistemáticamente.
- **Costo del FULL**: navegar ~500 semanas + 1 fetch de detalle por item collector es
  caro (miles de requests, timeout de 4 h). El delta lo acota a ~3 meses.
- **Calidad de fecha**: depende del formato del detail page; si AnimeClick
  cambia la etiqueta "Editore:" o el schema.org, el parser deja esos
  campos vacíos en silencio.

---

## 10. Runbook / comandos útiles

```bash
# Ingesta DELTA (últimos ~3 meses):
.venv/bin/python scripts/manga_watch.py \
    --bootstrap-wiki animeclick --wiki-from 2026-03 \
    --sleep-seconds 0.5 --min-score 20

# Ingesta FULL (histórico desde 2015 — lento, miles de fetches):
.venv/bin/python scripts/manga_watch.py \
    --bootstrap-wiki animeclick --wiki-from 2015-01 \
    --sleep-seconds 0.5 --min-score 20

# Prueba directa del módulo (imprime hasta 20 candidates, no escribe):
.venv/bin/python scripts/wikis/animeclick.py --wiki-from 2026-03

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "animeclick"
def hit(it):
    blobs=[it.get('url','') or '']+[ (s.get('url','') or '') for s in it.get('sources',[]) ]
    return any(NEEDLE in b for b in blobs)
items=[json.loads(l) for l in open("data/items.jsonl") if l.strip()]
sel=[it for it in items if hit(it)]
print("items:", len(sel))
print("países:", Counter((it.get('country') or '') for it in sel if it.get('country')))
print("editoriales:", Counter((it.get('publisher') or '') for it in sel if it.get('publisher')).most_common(20))
PY
```

**Antes de cerrar cualquier cambio en AnimeClick**: validar (`validate_corpus`, 0
duras) → tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo
meaningful, actualiza esta ficha.

## 2026-06-12 — títulos oficiales IT con bonus/bundle (gotcha #92)

Con la política de títulos, los títulos oficiales italianos nombran el bonus o el
bundle: "Ediz. variant. Con acrylic standee", "Variant Bundle con Storia
Extra-Piccante", "Sakamoto Days Variant con T-shirt 3", "Yomi No Tsugai Variant +
FMA Variant Bundle 1". Los patterns de standee/Variant Bundle/T-shirt los mataban.
Fix genérico (gotcha #92): marcador "con/with/+" en ventana corta alrededor del match
rescata; "Io Sakisaka Variant Bundle" (sin marcador) va por `title_exceptions` de
`data/comics_blacklist.yml`.

## 2026-09-02 — placeholder "COPERTINA NON DISPONIBILE" (URL exacta, denylist trivial)

AnimeClick sirve `https://www.animeclick.it/bundles/accommon/images/non_disponibile.jpg`
(texto "COPERTINA NON DISPONIBILE" + mascota/logo del sitio) cuando no tiene portada. En el
corpus actual son **3 ítems compartiendo 1 solo archivo local** (`fb88ab0e8281fd87.avif`,
sha256 `fd6804dd…`): `finder-series-magicpress-deluxe-it-14`,
`ken-il-guerriero-le-origini-del-panini-lore-it-12` y
`takamine-rimettiti-le-mutandine-magicpress-variant-it-6`. Es el único caso de la tanda
donde la denylist por URL exacta o por hash es trivialmente segura (URL constante, no
parametrizada por título). Detectado en la Etapa 1 de triage
(`docs/reference/images.md` § "Etapa 1 — resultados").

**Aplicado (2026-09-02, cierre de la Etapa 1, gotcha #176)**: sha1
`140a4352062228eda4f55717be6dae33c2de5319` agregado a `data/placeholder_signatures.json`
(label "AnimeClick — 'COPERTINA NON DISPONIBILE' + logo"). `purge_placeholder_images.py
--only-reasons known,signature` quitó las 3 entries; los 3 items quedaron sin ninguna
foto (candidatos a `/watch-search-covers` o re-fetch).

Ojo con el sentido inverso: las fotos 3D de cofres/estuches sobre fondo blanco de esta misma
fuente (Berserk, L'Attacco dei Giganti, Death Note Black Edition, Jujutsu Kaisen, Samurai 8)
dispararon la heurística de placeholder tipográfico y **son portadas válidas** — 17 falsos
positivos en un solo chunk del triage. Gotcha #172.

### Integridad de ingestión — continuación 2026-09-24

Los fallos de transporte ahora registran `[WIKI-ISSUE]` en la sesión. El dispatcher
conserva los resultados parciales y termina con error; incluye el fallo en el
reporte. Una respuesta fallida no equivale a catálogo vacío. El watermark por
fuente solo avanza después de persistir corpus y estado, sin incidencias ni
límites alcanzados. Tras una interrupción, el calendario amplía su ventana hasta
el último inicio exitoso con siete días de solapamiento. Un import histórico
acotado, un chunk explícito o un dry-run no adelantan ese watermark.

### Auditoría de continuidad — 2026-09-24

El límite anterior de 520 semanas truncaba un full desde 2015 al ejecutarse en
2026 sin informar cobertura incompleta. Se amplía a 2000 y su agotamiento genera
incidencia (sin checkpoint). Fechas inválidas, JSON inesperado y semanas que no
retroceden detienen la paginación con error conservando lo adquirido. Se incluye
la semana que cruza el inicio del mes y se respeta el mes final al seleccionar
semanas. El rango se define por semanas: puede incluir días adyacentes.

La verificación viva posterior recorrió 614 semanas hasta 2015-01 y descubrió
1645 fichas de ediciones especiales para procesar. Esto confirma que el límite
de 520 semanas era insuficiente para el full configurado.


## Revalidación de calendarios y catálogos — 2026-09-24

El histórico 2015-01–2026-09 completó 614 semanas y 1587 candidatos finales,
1580 reportables, sin errores ni conflictos pendientes. El tope anterior de
520 semanas habría truncado 94 semanas. No se simula cobertura futura: esta
fuente navega hacia atrás desde la semana actual.

La revisión de asociaciones detectó `Kaiju No. 8 Limited Edition 1` interpretado
como volumen 8. El extractor excluye el 8 del nombre de esta serie antes de
buscar el tomo; se conserva la asociación existente al tomo 1 y se evita un alta
duplicada. Regresiones cubren título sin tomo, nº16 y tomo 8 real.

Cierre 2026-09-25: se incorporaron 105 referencias adicionales de esta fuente
a productos ya existentes, recuperadas del resultado del upsert en staging.
Cada URL tenía un único propietario propuesto y no existía aún en ninguna
ficha publicada; se conserva el producto canónico. Manifest: `publication-3-manifest.json`.
