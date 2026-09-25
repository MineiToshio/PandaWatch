# Fuente: Panini Manga España

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-09-23 (Queue-it #208: las 16 searches saltadas; #199 las oculta
> tras una fila fantasma en el reporte de salud).

Fuente **SIMPLE** (entradas en `sources.yml`, sin parser propio). Cubre **dos
entradas** del mismo sitio (`panini.es`): el catálogo de novedades y el buscador
expandido por keywords.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Panini Manga España |
| **URL base** | `https://www.panini.es/shp_esp_es/` |
| **Índice / punto de entrada** | `novedades-panini-comics-marvel-manga` (catálogo) · `catalogsearch/result/?q={query}` (buscador) |
| **Tipo de fuente** | Editorial oficial (tienda Magento de Panini España) |
| **`kind` en sources.yml** | `html` (ambas entradas) |
| **`source_class`** | `official` |
| **País** | España (`es`) — fuente mono-país |
| **Idioma** | Español (ES) |
| **Cobertura** | Manga publicado por Panini en España: novedades + ediciones especiales/limitadas/deluxe que aparecen en el buscador |
| **Aporte al corpus** | ~14 items (al último conteo) |
| **Parser / módulo** | Sin parser propio: 2 entradas en `sources.yml` vía extractor genérico Magento |

**Editoriales que abarca** (del corpus real): Panini Manga España (14/14 items).

**Por qué importa / qué aporta de único**: es la voz **oficial** de Panini para el
mercado español — capta novedades y ediciones premium (Master/Ultimate Edition,
deluxe, cofres, tapa dura, variantes) directo de la editorial, sin pasar por
intermediarios.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: tienda **Magento**. El catálogo de novedades
  pagina (`max_pages: 15`). El buscador usa `catalogsearch/result/?q={query}`,
  que en el pipeline se expande en fuentes virtuales (una por keyword).
- **Estructura del HTML**: layout Magento estándar. Selectores de la entrada
  (search): `item_selector: "li.product-item"`, `title_selector:
  "a.product-item-link"`. El catálogo de novedades usa el extractor genérico
  (sin selectores explícitos en el YAML).
- **Identificador de producto**: URL canónica del producto Magento.
- **Anti-bot / quirks**: catálogo **mixto** — el buscador devuelve también cromos
  (LIGA ESTE, Eurocopa), corbatas y otros no-manga; por eso la entrada (search)
  declara `purity: "mixed"` (ver §8).
- **Calidad de imágenes**: {{pendiente: no verificada en esta revisión}}.

---

## 5. Proceso de ingestión — técnico

Sin parser dedicado. Las dos entradas se ingieren en **FASE 1** (`manga_watch.py`,
scrape de las fuentes del YAML) vía el **extractor genérico** de Magento.

- **`ES - Panini Manga España`** (`sources.yml:479`): entrada `html` con
  `url` al catálogo de novedades y `max_pages: 15`. Tags `["manga", "official"]`.
  El extractor genérico recorre la paginación y toma cada producto del listado.

- **`ES - Panini España (search)`** (`sources.yml:1493`): entrada `html` con
  `search_template`. En el pipeline, `_expand_search_template()` la **expande en
  fuentes virtuales por keyword** (una query por cada keyword del bloque
  `keywords`) — tag de procesamiento "expansion". Cada query se ejecuta contra
  `catalogsearch/result/?q={query}` y se parsea con los `selectors` declarados
  (`li.product-item` / `a.product-item-link`). `purity: "mixed"` se **propaga a
  todas las fuentes hijas** generadas por la expansión (#7). Tags
  `["manga", "official", "store"]`.

  Keywords (verbatim del YAML): `edicion limitada`, `edicion especial`,
  `edicion coleccionista`, `deluxe`, `cofre`, `kanzenban`, `tapa dura`,
  `variante`, `portada variante`, `master edition` (rescata Berserk Master
  Edition; "Beherit" cae aquí), `ultimate edition`, `tarot`, `celebration`,
  `anniversary`, `tribute`, `aniversario`.

  Nota del YAML: keywords validadas a mano; se eliminaron `gran formato`,
  `perfect edition` y `beherit` (esta última sólo aparece en la descripción, no
  en el título, así que el buscador no la indexa).

**Flujo end-to-end**: ambas entran en **FASE 1** del pipeline canónico
(`scrape_full.sh` / `scrape_delta.sh`). No tienen discovery especial: se scrapean
igual en full y en delta. Luego pasan por los cleanup retrofits genéricos de la
FASE 3 (rescore → `filter_non_manga` → `filter_collectible` → clean_titles →
backfill_metadata).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **`purity: mixed` (decisión #3)**: el buscador de Panini ES devuelve cromos
  (LIGA ESTE, Eurocopa), corbatas y merch no-manga. En `mixed`, sólo pasa lo que
  trae un **STRONG manga hint** (la comics blacklist aplica siempre). Por eso la
  entrada (search) está marcada `mixed` y NO `manga_only`.
- **#7: `source_purity` se propaga a las fuentes hijas** de la expansión del
  `search_template`. El `mixed` de la entrada padre cubre automáticamente cada
  query-por-keyword; no hay que marcarlo por hijo.
- **Tienda ≠ editorial (#44)**: NO aplica como contaminación acá — Panini España
  **es** la editorial real, así que `publisher: "Panini Manga España"` es
  correcto (la entrada es `source_class: official`, no un retailer multi-editorial).
- **Curación LLM non-manga 2026-08-23**: 2 items expulsados — "Marvel Treasury
  Edition" y "Marvel Now! Deluxe. Secret Wars: Integral"; se agregaron "Marvel
  Treasury" y "Secret Wars" a `data/comics_blacklist.yml`.

---

## 9. Pendientes / limitaciones conocidas

- **Aporte chico** (~14 items): la cobertura depende de que las ediciones traigan
  alguna de las keywords en el **título** indexado por el buscador (las que sólo
  aparecen en descripción no se capturan — caso "beherit"). Ampliar keywords
  podría subir recall, pero sube también el ruido (catálogo mixto).
- **Calidad de imágenes**: {{pendiente: no verificada}}.
- **Diferencia full vs delta**: hoy ninguna — ambas entradas se scrapean igual en
  los dos modos.
- **Watchlist benigna (2026-08-24)**: `ES - Panini España (search) [search:
  portada variante]` y `[search: ultimate edition]` dieron 0 candidatos en las
  3 últimas corridas medidas (2026-07-07, 2026-08-22, 2026-08-24 —
  `logs/metrics.jsonl`). Decisión del owner: **NO podar** — 0 items en 3
  corridas puede significar simplemente que no hubo productos nuevos que
  matcheen esa keyword en esa ventana, no que la búsqueda esté rota (`status:
  healthy`, `errors: 0` en las 3). Validar selectores recién si llegan a 0 con
  un corpus shift visible o pasan >3 meses sin ningún candidato.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo estas fuentes (ajustar al nombre exacto del YAML):
.venv/bin/python scripts/manga_watch.py --only-source "ES - Panini Manga España"
.venv/bin/python scripts/manga_watch.py --only-source "ES - Panini España (search)"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "panini.es"
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

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`,
0 duras) → tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo
meaningful, actualiza esta ficha.

## 2026-09-02 — 3 cajas de merchandising de Harry Potter, en italiano, atribuidas a España

Delta diario (`logs/scrape-delta-2026-09-02-110142/`). La fuente aportó como items nuevos
`COFANETTO TREASURE BOX ONLINE HARRY POTTER`, `… HERMIONE GRANGER` y `… RON WEASLEY`,
los tres `product_type: boxset`, `country: España`, `publisher: Panini Manga España`, y
los tres re-flageados `llm_non_manga` con nota `merchandise`.

Dos problemas distintos en el mismo dato:

1. **Fuera de alcance**: no son manga ni libro — son cajas de coleccionismo de Harry
   Potter (merchandising). Ninguno de los gates deterministas los ve porque la fuente es
   `manga_only` y el título no dispara ningún patrón non-manga.
2. **País/idioma incoherentes**: el título es italiano (`COFANETTO`, no `ESTUCHE`/`CAJA`),
   pero el item quedó etiquetado España. Señal de que el search de esta fuente está
   alcanzando catálogo de Panini Italia y heredando el país de la fuente en vez del de la
   edición — choca con la regla dura "país = edición, no país de la tienda".

Además el LLM les acuñó `series_display` a partir del propio título de producto
(`Treasure Box Online Ron Weasley` como si fuera una serie), lo que ensucia el índice de
series.

Nada aplicado: acotar el search o corregir la derivación de país de esta fuente es
decisión del owner. El punto 2 conviene revisarlo aunque se descarte el 1 — si el search
trae catálogo italiano, hay riesgo de más items con país equivocado que sí son manga.

### RESUELTO parcialmente el mismo día (2026-09-02) — el owner pidió arreglar las fuentes

**Punto 1 (fuera de alcance) — CERRADO.** Las 3 cajas quedaron EXPULSADAS por un
mecanismo nuevo: `_NON_MANGA_URL_PATTERNS` ahora incluye `trading[-_]cards?`. El tipo de
producto ya estaba en `_NON_MANGA_HARD` (`\bTrading\s+Cards?\b`) pero sólo se evaluaba
contra el TÍTULO, y estos títulos no dicen de qué es la caja — la evidencia vivía
únicamente en la URL (`harry-potter-always-trading-card-treasure-box-panini-…`). Es la
misma regla, aplicada al blob donde el dato realmente está.

**Punto 2 (país/idioma incoherentes) — SIGUE ABIERTO, y conviene no perderlo de vista.**
Los 3 items ya no están, así que el síntoma desapareció, pero la CAUSA no se tocó: el
search de esta fuente alcanza catálogo de Panini Italia y hereda `country: España` de la
fuente en vez de derivarlo de la edición. Hay un discriminador limpio y verificado: el
sufijo de mercado del SKU en la URL. Medido sobre el corpus, `panini.es` tenía 26 items —
**23 con sufijo `-es…` (legítimos) y exactamente 3 con `-it`** (los tres infractores). O
sea `-it.html` en un storefront `.es` predice el problema con precisión perfecta en la
muestra disponible.

No se implementó porque con los 3 items expulsados la muestra quedó en cero y no hay
forma de validar la regla contra un caso vivo — implementarla ahora sería escribir un
filtro que no se puede probar. **Recomendación**: si vuelve a aparecer un `panini.es`
con sufijo de mercado extranjero (sobre todo si ES manga real), ahí sí conviene derivar
el país del SKU en vez de la fuente. Choca con la regla dura "país = edición, no país de
la tienda", así que un manga italiano entrando como España sería un error de agrupación,
no sólo ruido.

## 2026-09-05 — flag de yield descartado como fluctuación normal

`source_health --baseline-alert` marcó `ES - Panini Manga España | 5 | mediana 11 | 45%`.
Revisado en el log del run (`logs/scrape-delta-2026-09-05-113236/01-scrape.log`):

```
[13/141] ES - Panini Manga España :: .../novedades-panini-comics-marvel-manga
    [ES - Panini Manga España] candidatos con señales: 5 (2 págs)
```

**0 errores, 0 challenges, paginación recorrida completa (2 págs).** Es una página de
*novedades*: su yield depende de cuántos lanzamientos anunció la editorial esa semana, así
que oscilar entre 5 y 11 es el comportamiento esperado, no una regresión. Queda anotado
para no volver a diagnosticarlo: **el umbral de `source_health` es demasiado sensible para
las fuentes de tipo "novedades"**, del mismo modo que lo es para las de forma de calendario
(gotcha #190). Nada aplicado.

## 2026-09-16 — las 16 searches caen en una sala de espera Queue-it (gotcha #208)

Corrida `logs/scrape-delta-2026-09-16-110158`. **Las 16 entradas
`ES - Panini España (search)` se saltaron enteras**, todas con el mismo mensaje:

```
[SKIP-empty] ES - Panini España (search) [search: deluxe]: HTML muy corto (2327 chars).
             Probablemente JS-rendered o vacío.
```

El diagnóstico del mensaje es equivocado. Verificado en vivo el mismo día:

```
curl -sL "https://www.panini.es/shp_esp_es/catalogsearch/result/?q=deluxe"
→ 302 → https://panini.queue-it.net/?c=panini&e=paninies&ver=v3-php-3.7.4
        &t=https%3A%2F%2Fwww.panini.es%2F…%2Fresult%2F%3Fq%3Ddeluxe
  size = 2332 chars
```

Esos ~2.3 KB son la **página de la sala de espera virtual de Queue-it**, no un shell
de Angular/React. Reproducido 5/5 con UA de navegador. Consecuencia práctica:
`--enable-js` NO lo arregla (Playwright aterrizaría en la misma cola).

**La avería es parcial y por-request.** En la MISMA corrida:

| Fuente | Resultado |
|---|---|
| ES - Panini Manga España (novedades) | 9 candidatos ✓ |
| ES - Panini España (search) × 16 | 0, todas skip ✗ |

Es decir, el host respondía; lo que disparó la cola fueron las 16 peticiones
consecutivas a `catalogsearch` (per-host-limit=2). Al momento de la verificación
(unas 2 h después del run) la cola ya cubría también `novedades` y el dominio `.it`.

**No afecta a `tiendapanini.com.mx`** (otro dominio, 35 y 7 candidatos en la misma
corrida).

**Ruido en el reporte de salud (gotcha #199, aún sin resolver):** las 16 searches
aparecen en 🟢 Healthy con `Runs 0`, y el único skip se le atribuye a una fila
fantasma `ES - Panini España (search) [search`. Sin leer `01-scrape.log` la corrida
parece sana.

**Recomendaciones (decisión del owner, nada aplicado):**

1. **Mecanismo, prioritario**: clasificar el redirect a `queue-it.net` como
   `challenge`/anti-bot en vez de `empty`. Hoy el mensaje induce al fix equivocado y
   `source_health` no lo cuenta en la columna Challenge.
2. Espaciar las searches de `panini.es` (o bajar el per-host-limit para ese host) —
   la evidencia apunta a que la ráfaga de 16 es lo que dispara la cola.
3. Mientras la cola esté activa, las searches no aportan nada: 16 slots por corrida
   gastados en 0 items.

## 2026-09-17 — Queue-it sigue activa: los mismos 17 skips, segundo día

Corrida `logs/scrape-delta-2026-09-17-110139`. Las **16 searches de `panini.es` volvieron
a saltarse con `[SKIP-empty]`** (~2330 chars cada una), exactamente el mismo conjunto que
ayer. Verificado en vivo el mismo día:

```
curl -sL "https://www.panini.es/shp_esp_es/catalogsearch/result/?q=deluxe"
→ https://panini.queue-it.net/?c=panini&e=paninies&…  (2332 chars)
```

No es intermitencia: **la cola de `panini.es` (`e=paninies`) lleva 2 corridas seguidas
bloqueando el 100% de las searches.** La fuente está efectivamente caída para el pipeline
desde el 2026-09-16, aunque el sitio esté sano para un humano que espera en la cola.

**Gotcha #199 lo volvió a tapar.** El reporte de salud mostró sólo 2 filas en 🟠 Broken:

```
| ES - Panini España (search) [search  | ? | ✓ | 1 | ... | `empty: aniversario]: HTML muy corto…`
```

El nombre quedó cortado en el primer `:` y las 16 searches se colapsaron en **una fila
fantasma** con `Enabled ?`. En el log crudo (`01-scrape.log`) los skips son **17** —16 de
`.es` + 1 de `.it`—. Sigue siendo obligatorio leer `01-scrape.log` y no el reporte para
contar skips de fuentes con `[search: …]` en el nombre.

**Recomendación (sin cambios respecto a ayer, decisión del owner):** clasificar
`queue-it.net` en la URL final como *challenge*, no como `empty`. `--enable-js` no sirve:
Playwright aterriza en la misma sala de espera.

## 2026-09-18 — Queue-it, tercer día: los mismos 16 skips

Las 16 searches de `panini.es` volvieron a responder ~2.3 KB (`HTML muy corto`, la página
de la cola Queue-it, gotcha #208). El reporte de salud vuelve a colapsarlas en una fila
fantasma `ES - Panini España (search) [search` (gotcha #199). Sin cambios de diagnóstico;
la fuente lleva 3 corridas sin ingesta por búsquedas.

## 2026-09-19 — Queue-it, cuarto día: 17 skips (16 searches + novedades)

Delta `logs/scrape-delta-2026-09-19-110115/`: 17 `SKIP-empty` de ~2.3 KB (página de la
cola, #208) en `panini.es`. El reporte de salud otra vez colapsó las 16 searches en UNA fila
fantasma `ES - Panini España (search) [search` (gotcha #199). Sin cambios de config.

## 2026-09-20 — Queue-it, 5º día consecutivo (gotcha #208)

Una search de `panini.es` volvió a saltarse con `empty: aniversario]: HTML muy corto
(2332 chars). Probablemente JS-rendered` — los ~2.3 KB son la página de la cola de
Queue-it, no un shell JS (ver #208).

Nota de lectura del reporte: la fila aparece como `ES - Panini España (search) [search`
con `Enabled ?` — es la fuente FANTASMA de la gotcha **#199** (el regex corta el nombre
en el primer `:`, y las searches se llaman `<fuente> [search: <keyword>]`). El nombre
real de la search saltada sólo se recupera del mensaje de skip (`aniversario`), no de la
columna Source.

Nada aplicado.

## 2026-09-21 — Queue-it, 6º día: la cola alcanzó el LISTADO PRINCIPAL (gotcha #208)

Delta `logs/scrape-delta-2026-09-21-110220/`: **19 `SKIP-empty`** de ~2.3 KB en `panini.es`
— las 16 searches (ya conocido) **más el listado principal `ES - Panini Manga España`**
(`manga.html`, 2317 chars). Es la primera corrida en que la cola se come el listado
principal de ES, no sólo las búsquedas.

Verificado en vivo hoy, no es un shell JS:

```
curl -s -o /dev/null -D - "https://www.panini.es/shp_esp_es/manga.html"
→ HTTP/2 302
  location: https://panini.queue-it.net/?c=panini&e=paninies&ver=v3-php-3.7.4
            &cver=28&man=Panini%20Spain%20-%20Production%20-%20Server
            &kupver=magento2_1.3.5
```

El `e=paninies` identifica la cola de la tienda española y `kupver=magento2_1.3.5` el
conector Queue-it del Magento — o sea está configurada a nivel plataforma, no es un
incidente de red. `--enable-js` NO sirve: Playwright aterrizaría en la misma cola.

Sigue siendo por-request (ver la ficha de Planet Manga: en la MISMA corrida el listado
principal IT rindió 79 candidatos mientras sus dos sublistados y todo ES cayeron), y el
reporte de salud sigue colapsando las 16 searches en la fila fantasma
`ES - Panini España (search) [search` de la gotcha **#199**.

**Nada aplicado (decisión del owner).**

## Seguimiento Queue-it (#208) — 2026-09-23

Las **16 searches** de `panini.es` se saltaron íntegras (`[SKIP-empty] … HTML muy corto
(~2 330 chars)`), o sea la sala de espera Queue-it devolvió su página a todas. Es el 7º
día del incidente. El listado principal `ES - Panini Manga España` sí rindió (10
candidatos), lo que vuelve a confirmar el carácter **por-request** de la cola: no es la
fuente la que está caída, es cada request el que puede caer en la sala de espera.

**Cuidado al leer el reporte de salud (gotcha #199)**: las 16 searches aparecen con
`Runs 0` y sin incidencias, y el skip se le atribuye a una fila **fantasma** llamada
`ES - Panini España (search) [search` — el regex de `source_health.py` corta el nombre
de fuente en el primer `:`, y estas fuentes se llaman `<fuente> [search: <keyword>]`.
En este delta el reporte mostró 3 skips de Panini; los reales fueron 18.

**Nada aplicado (decisión del owner).**


## Revisión de ingestión — 2026-09-24

Queue-it se identifica como challenge por la URL final; los SKIP de búsquedas conservan search: término sin crear fuentes fantasma. El bloqueo externo sigue siendo intermitente; no se declara cobertura restaurada.

Evidencia y alcance: [auditoría integral](../audits/2026-09-24-ingestion.md).

### Queue-it resuelto por navegador — 2026-09-24

Con `--enable-js` (activo en full y delta), una respuesta Queue-it ahora abre
el URL original con Chromium. Si la página carga, las siguientes páginas de esa
fuente usan el navegador; si continúa bloqueada, se reporta fallo. Verificación
real: Panini IT variantes 4 páginas/81 candidatos; cofanetti 9 páginas/209;
Panini ES búsqueda deluxe 1 página/12. Las tres finalizaron sin errores, con
179 reportables tras gates. Esto no afirma cobertura completa de todas las
búsquedas españolas: prueba el mecanismo y esas tres entradas.

### Corrección de catálogo — 2026-09-24

La entrada principal apuntaba a una página promocional de novedades mixta, cuyo
bloque actual devuelve cero manga elegible. Se sustituye por el enlace oficial
`/shp_esp_es/comics/manga.html?skip_default_filters=true`. El catálogo predeterminado
mostraba 1113 productos y el filtro `A la venta: Sí`: se quita para conservar la
cobertura de agotados. El mismo parámetro se agrega al buscador. La categoría
sigue siendo manga; el buscador mantiene `purity: mixed`. Full recorre hasta
agotar paginación; delta conserva sus topes configurados.

El navegador conserva una sesión efímera por host de Panini durante la corrida,
reutilizando cookies/caché de navegación entre páginas; se elimina al cerrar el
browser del scraper y no usa el perfil personal. La categoría IT de variantes
verificó 8 páginas/168 candidatos con esta sesión (0 errores). Los demás hosts
conservan contextos independientes por render como antes.

Cierre 2026-09-25: se incorporaron 7 referencias adicionales de esta fuente
a productos ya existentes, recuperadas del resultado del upsert en staging.
Cada URL tenía un único propietario propuesto y no existía aún en ninguna
ficha publicada; se conserva el producto canónico. Manifest: `publication-3-manifest.json`.

### Cierre del recorrido completo — 2026-09-25

Catálogo general: páginas 1–25 persistidas y reanudación 24–119 (96 páginas),
173 candidatos en esta última, sin errores. Todas las búsquedas españolas
configuradas finalizaron entre el primer proceso y la reanudación. La suma
reanudada IT+ES cerró con 660 candidatos, 448 reportables y cero errores.
El proceso inicial interrumpido se conserva como tal en la evidencia.
