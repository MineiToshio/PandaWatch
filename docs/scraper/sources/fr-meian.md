# Fuente: Meian

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-09-01.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Meian |
| **URL base** | `https://www.meian-editions.fr` |
| **Índice / punto de entrada** | `https://www.meian-editions.fr/meian/accueil-meian` |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `js` (requiere render con Playwright) |
| **`source_class`** | `official` |
| **País(es)** | Francia (`Francia`) — el país va al edition_key |
| **Idioma(s)** | FR (francés) |
| **Cobertura** | Catálogo de la editorial francesa Meian (manga publicado en Francia) |
| **Aporte al corpus** | ~16 items, todos `publisher=Meian` / `country=Francia` |
| **Parser / módulo** | Entrada en `sources.yml` (`FR - Meian`); sin parser propio |

**Por qué importa / qué aporta de único**: cubre el catálogo oficial de **Meian**, una
editorial francesa de manga, aportando ediciones del mercado francés (FR) que no
aparecen en las fuentes españolas/japonesas.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: índice en `meian-editions.fr/meian/accueil-meian`;
  páginas de producto del sitio de la editorial.
- **Identificador de producto**: URL canónica del producto en el dominio
  `meian-editions.fr`.
- **Anti-bot / quirks**: sitio **JS-rendered** (`kind: js`) → se renderiza con Playwright
  (#12). Posible **mojibake FR** (#1) por la codificación del HTML francés.
- **Calidad de imágenes**: {{pendiente: resolución real de las portadas de Meian}}.

---

## 5. Proceso de ingestión — técnico

> ⚠️ **Obsoleto desde 2026-09-07** (igual que la tabla de §1): la entrada HTML de abajo
> quedó `enabled: false` y la fuente pasó al módulo wiki `scripts/wikis/meian.py` (API
> JSON, `FR - Meian (API)`, ~116 items). Ver "2026-09-07 — RESUELTO" más abajo. Y ojo:
> ese wiki **todavía no está cableado a los scripts canónicos** (entrada 2026-09-13,
> gotcha #205). Se conserva el texto original como historia.

- **Entrada en `sources.yml`**: bloque `FR - Meian` (`kind: js`, `source_class: official`,
  `country: Francia`, `publisher: Meian`). Se scrapea como una fuente simple del YAML.
- **FASE 1 del pipeline** (`scrape_full.sh` / `scrape_delta.sh`): la fuente entra en el
  paso de scrape de sources del YAML (`manga_watch.py --workers 8`). **No tiene parser
  propio** ni discovery dedicado.
- **Render JS (#12)**: por ser `kind: js`, las páginas se rinden con Playwright. Playwright
  sync NO es thread-safe → el render se serializa en el único thread `playwright-worker`
  vía `_PLAYWRIGHT_QUEUE`; los workers HTTP despachan a esa cola con
  `fetch_with_playwright()`. Requiere `--enable-js` (Playwright es opt-in).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#12 (JS/Playwright)**: el sitio es JS-rendered; el scrape exige `--enable-js` y el
  render se serializa en el worker dedicado. Sin Playwright la página no entrega productos.
- **#1 (mojibake FR)**: riesgo de codificación cp1252 sobre UTF-8 en HTML francés;
  `clean_title()::_fix_mojibake()` lo repara primero (no meter regex-cleaning antes).
- **Banner genérico de homepage colado como foto de galería — CONFIRMADO y
  PURGADO (2026-09-01).** Descubierto en la OLA 3 de depuración de imágenes
  (gotcha #160) como grupo sha≥5 SIN validar: 7 items de TRES series distintas
  (`hanma-baki-meian-perfect-fr-13..16`, `the-breaker-new-waves-meian-
  ultimate-fr-1-5`/`6-10`, `baki-gaiden-scarface-integrale-meian-coffret-fr`)
  compartían byte-a-byte la MISMA imagen en `images[1]` — el banner OG por
  defecto del sitio (`meian-editions.fr/meian/assets/images/facebook/
  default_fb.jpg`, 1200×630, sha1 `1bff44a55de9e0afc37ba5bf6763b32de19cb7bd`),
  destacando "Egregor Tome 1" (obra sin relación con ninguno de los 7 items) —
  el extractor de galería capturó un elemento del layout de la página en vez
  de sólo las fotos del producto. Al cierre de la tanda de imágenes
  (2026-09-01) el owner confirmó visualmente el hallazgo: firma sha1 agregada
  a `data/placeholder_signatures.json`, purgado con
  `purge_placeholder_images.py --only-reasons signature` — **7 entries
  quitadas de 7 items**, los 7 conservaron su `images[0]` real, 0 items
  quedaron sin imagen. Detalle completo en `docs/reference/images.md` §
  "Cierre de la tanda de depuración de imágenes". **Pendiente real (no
  aplicado)**: el bug de EXTRACCIÓN sigue vivo — si Meian vuelve a
  scrapearse, el extractor de galería puede volver a traer este banner (o
  cualquier otro elemento de layout) a `images[]`. El fix de fondo es acotar
  el extractor al contenedor del producto (mismo patrón que la "detección
  estructural de grilla de relacionados" de otras fuentes); la firma sha1
  sólo cubre esta imagen puntual, no la causa raíz.

---

## 9. Pendientes / limitaciones conocidas

- **Costo de Playwright**: al ser `kind: js`, cada fetch pasa por el worker serializado de
  Playwright (más lento y caro que HTML plano).
- **`FR - Meian Plus Boutique`** (`meian-plus.fr`, mismo `publisher: Meian`) está
  **`enabled: false`** (deshabilitada 2026-06-01: 0 items en corpus, fuente JS cara, sin
  yield). Queda fuera del pipeline; reactivar sólo si justifica el costo de Playwright.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente (requiere Playwright por ser kind: js):
.venv/bin/python scripts/manga_watch.py --only-source "FR - Meian" --enable-js

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "meian-editions"
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

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`, 0 duras)
→ tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful, actualiza
esta ficha.

### Verificación 2026-06-12 — falsa alarma del run de mayo

- El "0 candidatos / error" del run 2026-05-24 fue el fallo transitorio de greenlet
  (`Cannot switch to a different thread`) del worker Playwright compartido (gotcha #12)
  — NO un cambio del sitio. Verificado en vivo: 14 cards, 9 candidatos (coffrets
  intégrale: Madoka Magica, Lodoss, Higurashi Gô…), 5 tomos regulares bien skippeados.
  Regla: si Meian da 0 en un run full con muchas fuentes js, sospechar del worker
  Playwright antes que del sitio.
- **Hallazgo técnico**: el sitio es una SPA Angular que consume la API JSON
  `https://www.anime-store.fr/api-meian/v5/` (exige header `Referer:
  https://www.meian-editions.fr/`, si no → 403). Endpoints útiles:
  `/v5/produits/news/` (los ~14 recientes), `/v5/licences/?cat=0&q=` (catálogo
  completo, 161 series), `/v5/planning/` (lanzamientos futuros). Hoy Playwright
  resuelve todo; si algún día se quiere bajar el costo de JS o ampliar cobertura
  (la homepage solo muestra ~14 recientes), migrar a la API con ese Referer es el
  camino — sin Playwright.
- Selectores confirmados del DOM renderizado (no necesarios hoy, el método clusters
  funciona): item `div.swiper-news`, title `h3`, link `a[href*='/produit/']`.

### 2026-08-30 — 0 candidatos otra vez, pero SIN error de greenlet (SPA sin hidratar)

Delta diario (`logs/scrape-delta-2026-08-30-111729/`). `source_health --baseline-alert`
la marcó como **la única regresión de yield del run**: `FR - Meian | 0 | mediana 8 | 0%`
(7 corridas históricas).

Diferencia con el falso positivo del 2026-05-24: **esta vez NO hay error de greenlet
ni de Playwright en el log** (`grep -iE "greenlet|playwright" 01-scrape.log` → 0 hits),
y el scrape corrió con `--enable-js` (lo pasa `scrape_delta.sh:293`). El HTML crudo
capturado (`logs/raw/fr-meian.html`, 159 KB) es el **shell de Angular sin hidratar**:

- 0 ocurrencias de `/produit/` (los links de producto que espera el parser),
- las 2 ocurrencias de `swiper-news` son sólo reglas CSS (`article[_ngcontent-ng-c…]`),
  no nodos del DOM renderizado.

O sea: Playwright trajo la página pero el bundle de Angular no terminó de montar los
componentes antes del snapshot — no es que el sitio haya cambiado sus selectores. El
runbook del 2026-06-12 sigue valiendo ("si Meian da 0, sospechar del render antes que
del sitio"), pero se refina: **la falla ya no se anuncia con una excepción**, así que
un 0 silencioso es indistinguible de "no hubo novedades" salvo mirando el HTML crudo.

También: `logs/raw/fr-meian-plus-boutique.html` quedó en **0 bytes** (la fuente
`FR - Meian Plus Boutique` está `enabled: false`, así que es esperable).

**Para el owner (no aplicado — cambio de configuración):** migrar la fuente a la API
JSON ya documentada arriba (`https://www.anime-store.fr/api-meian/v5/produits/news/`
con header `Referer: https://www.meian-editions.fr/`) y bajarla de `kind: js` a una
fuente de API. Retorno: elimina la dependencia de Playwright (la más cara y la más
frágil del pipeline, #12), vuelve determinista un yield que hoy oscila entre 0 y ~9,
y de paso amplía la cobertura — la homepage sólo expone ~14 recientes mientras que
`/v5/licences/?cat=0&q=` lista las 161 series del catálogo.

### 2026-09-05 — 2ª ocurrencia del SPA sin hidratar (idéntica al 2026-08-30)

Delta diario (`logs/scrape-delta-2026-09-05-113236/`). `source_health --baseline-alert`
la vuelve a marcar: `FR - Meian | 0 | mediana 8 | 0%` (13 corridas históricas).

Verificado que es **el mismo modo de fallo**, no uno nuevo:

- `logs/raw/fr-meian.html` (159 414 bytes, del run de hoy) → **0 ocurrencias de
  `/produit/`**: shell de Angular sin montar, exactamente como el 2026-08-30.
- `grep -icE "greenlet|playwright" 01-scrape.log` → **0**: sigue sin anunciarse con
  excepción.

Conclusión operativa: el 0 silencioso de Meian ya es **recurrente y no diagnosticable
desde el reporte de salud** — hay que abrir el HTML crudo para distinguir "no hubo
novedades" de "el render no terminó". La recomendación del 2026-08-30 (migrar a la API
JSON `anime-store.fr/api-meian/v5/…` y bajarla de `kind: js`) sube de prioridad: es la
única de las 5 regresiones de yield de hoy que corresponde a una avería real y
reproducible, y el fix elimina la causa en vez de monitorearla. Nada aplicado (cambio de
configuración = decisión del owner).

### 2026-09-06 — 3ª ocurrencia consecutiva del SPA sin hidratar

Tercera corrida seguida con `candidatos con señales: 0` y **sin error** en el log
(`[25/141] FR - Meian :: .../accueil-meian` → 0). Idéntica al 2026-08-30 y al 2026-09-05:
el reporte de salud la marca 🔴 (0 vs mediana 8, 14 runs históricos) mientras la tabla
"Healthy" del mismo reporte la lista como sana con 0 errores — la contradicción ya
documentada.

Tres corridas seguidas descartan la lectura de "no hubo novedades": es avería
reproducible, no ruido. De las 5 regresiones de yield de hoy, sigue siendo **la única que
corresponde a una falla real** (las otras 4 son las ya diagnosticadas: JBC forma de
calendario, Panini España página de novedades, Dark Horse `slipcase` con mediana 1,
Mangavariant recuperándose del challenge de ayer).

La recomendación del 2026-08-30 —migrar a la API JSON `anime-store.fr/api-meian/v5/…` y
bajar la fuente de `kind: js`— sube otro escalón de prioridad: es el único de los
pendientes abiertos que **elimina** la causa en lugar de monitorearla, y ya lleva 3
corridas de evidencia acumulada. Nada aplicado (cambio de configuración = decisión del
owner).

### 2026-09-07 — 4ª ocurrencia + verificación en vivo: no es "sin hidratar", es JS-only estructural

Cuarta corrida seguida con `candidatos con señales: 0` y sin error
(`[25/141] FR - Meian :: .../accueil-meian` → 0).

Hoy se verificó **en vivo** contra el sitio, lo que refina el diagnóstico de las tres
corridas anteriores. El HTML servido a un cliente sin JS:

- **`HTTP 200`, 64 914 bytes** — el peso engaña: es CSS crítico inlineado
  (`data-beasties-container`, el inliner de Angular SSR) más preloads.
- **Texto útil del `<body>`: 60 caracteres**, literalmente
  `"Please enable JavaScript to continue using this application."`
- **0 enlaces `<a>` en toda la página.**
- Sin `<app-root>` ni `ng-version`, así que la heurística habitual para reconocer un SPA
  de Angular tampoco lo delata.

Es decir: **no hay contenido que un parser HTML pueda fallar en encontrar**. La lectura de
"el render no terminó de hidratar" queda descartada — el servidor nunca manda producto,
en ninguna corrida. Que la fuente ya esté declarada `kind: js` y aun así rinda 0 significa
que el problema está en el camino de render, no en los selectores.

**Vías de escape probadas hoy, las dos cerradas:**

| Vía | Resultado |
|---|---|
| `sitemap.xml` | `404`. `/meian/sitemap.xml` devuelve **el shell** (`200`, 64 914 bytes) — la app es catch-all: cualquier ruta responde lo mismo. No hay sitemap utilizable. |
| API JSON `anime-store.fr/api-meian/v5/…` (la recomendación abierta desde 2026-08-30) | El host **existe y responde**: `/v5/` da `403` (gateado, no inexistente) y las rutas hijas probadas dan `404`. La ruta exacta **no es deducible por análisis estático** del bundle (`main-EDWVHENJ.js`, 447 KB) — sólo aparecen rutas de UI (`/catalogue-meian`, `/vendre-nos-mangas`). Hay que capturarla del tráfico de red con el navegador. |

**Dato adicional**: la URL configurada apunta a `accueil-meian`, la **home**. La ruta de
catálogo del propio bundle es `/meian/catalogue-meian`. Aunque no arregla el problema de
fondo (la home tampoco renderiza), es la URL correcta a usar cuando la fuente vuelva a
rendir.

**Recomendación (NO aplicada — decisión del owner)**, en orden de retorno:

1. Abrir `meian-editions.fr/meian/catalogue-meian` en el navegador con el panel de red
   abierto y **capturar la llamada real de la API**; con esa ruta, la fuente baja de
   `kind: js` a un fetch JSON barato y determinista. Es el único fix que **elimina** la
   causa; ya lleva 4 corridas de evidencia.
2. Mientras tanto, cambiar la URL a la ruta de catálogo.

Sigue siendo la única de las regresiones de yield del reporte que corresponde a una avería
real y reproducible.

---

## 2026-09-07 — RESUELTO: la fuente pasa a ingesta por API JSON

**Aplicado.** Se capturó la ruta real del API con el navegador (panel de red del
Browser pane sobre `meian-editions.fr/meian/catalogue-meian`) y la fuente se
reimplementó como módulo wiki.

### Por qué el HTML no tenía arreglo

Ver la entrada del mismo día más arriba: 64 KB de shell, 60 caracteres de texto
útil, 0 enlaces, sin sitemap, `kind: js` rindiendo 0 durante 4 corridas. No hay
selector que pueda salvar eso.

### El API (los tres endpoints)

```
GET https://www.anime-store.fr/api-meian/v5/licences/?cat=0&q=              → 168 licencias (series)
GET https://www.anime-store.fr/api-meian/v5/produits/licence/?id_serie=<id>&ref=0  → productos de la serie
GET https://www.anime-store.fr/api-meian/v5/produit/?ref=<ref>             → ficha completa
```

**Dos trampas que hacen fallar el acceso ingenuo** (las dos costaron un 403
antes de dar con ellas):

1. **Exige el header `Origin: https://www.meian-editions.fr`.** Sin él responde
   `403 {"success":false,"message":"Access Forbidden","code":1}`. Un `Referer`
   solo NO alcanza — probado.
2. **La respuesta lleva prefijo anti-XSSI `)]}',\n`** antes del JSON. Hay que
   descartar la primera línea o `json.loads` revienta.

Y el host es `www.anime-store.fr` **con `www.`**: sin el prefijo devuelve
403/404 y parece que el API no existiera (fue exactamente el motivo por el que
la sonda del 2026-09-07 por la mañana concluyó "ruta no deducible").

### Qué aporta

La ficha de detalle trae **todo lo que el pipeline necesita**, y son datos que
la fuente NUNCA había entregado:

| Campo | Ejemplo |
|---|---|
| `titre` | Kingdom - Partie 1 - Coffret Collector (tomes 01 à 10) |
| `isbn` / `ean` | 978-2-38658-742-9 / 9782386587429 |
| `date_parution` | `28-11-2025` (se normaliza a ISO) |
| `auteur` | Yasuhisa Hara |
| `info_sup` | "Contenu du coffret : 10 tomes, 10 ex-libris, 1 poster, coffret rigide…" |
| `url_img_big` | webp a resolución grande |

`info_sup` es especialmente valioso: enumera el CONTENIDO de la caja, que es
justo la señal que el scoring busca. El candidato de prueba puntuó **300**.

**El precio (`prix_public`) NO se captura** — decisión del owner 2026-06-11.

### Implementación

- Módulo nuevo: `scripts/wikis/meian.py` (misma firma que los demás wikis:
  `bootstrap()` / `iter_year_months()` / `parse_product()` / `enrich_candidate()`).
- Registrado en `WIKI_BOOTSTRAP_IDS` → `--bootstrap-wiki meian`.
- Filtro local `SPECIAL_RE`: coffret / collector / édition limitée·spéciale·deluxe /
  artbook / intégrale / box set / fourreau. El catálogo es mayormente tomos
  regulares; sólo se emiten las ediciones especiales.
- **No hay modo delta**: el API no expone fecha de alta por producto, así que se
  recorre el catálogo completo (1 request de listado + 1 por licencia + 1 por
  edición especial). Es barato y el dedup por `cluster_key` absorbe lo conocido.
- La entrada HTML de `sources.yml` quedó `enabled: false` con la explicación.
  **Conteo de fuentes habilitadas: 57 → 56; wikis: 26 → 27.**

#### Nota de implementación: `fetch_details` es OBLIGATORIO para esta fuente

El listing (`/produits/licence/`) sólo trae título, autor, `ref` y una portada
chica. **ISBN, fecha de salida, descripción y el contenido de la caja viven
únicamente en `/produit/?ref=N`.** Y a diferencia de otras fuentes, acá el
fetch-details HTML genérico del pipeline NO puede suplirlo: la página pública es
Angular y no devuelve nada sin JS.

Por eso `manga_watch.py` fuerza `fetch_details=True` para
`--bootstrap-wiki meian`, igual que hace con `kodansha-us` y `animeclick`. La
primera corrida (2026-09-07) se hizo sin ese fuerce y los 118 items entraron sin
ISBN ni `release_date`; se reingestó con el enriquecimiento activo (el merge por
`cluster_key` es idempotente y completa los campos faltantes).

---

## 2026-09-13 — el wiki API NO está cableado a los scripts canónicos (gotcha #205)

Delta diario (`logs/scrape-delta-2026-09-13-110143/06-source-health.md`): `wiki:meian`
aparece en **⚪ Not seen in recent runs**. Verificado en el código:

- `meian` está en `WIKI_BOOTSTRAP_IDS` (`manga_watch.py`) y tiene su rama
  `--bootstrap-wiki meian` con `fetch_details` forzado.
- Pero `grep -n meian scripts/scrape_delta.sh scripts/scrape_full.sh` → **0 coincidencias**.
  Ningún paso del pipeline canónico lo invoca.
- Los 116 items con fuente `FR - Meian (API)` salen de la corrida manual del 2026-09-07.
  Desde entonces la fuente **no se refrescó** (6 deltas sin ella).

Como la entrada HTML quedó `enabled: false` ese mismo día, **hoy Meian no tiene ninguna
vía de ingesta automática**: un coffret nuevo de Meian no entraría al catálogo. La nota del
09-07 ("wikis: 26 → 27") lo daba por integrado; el registro del id sólo habilita el flag,
no agrega el paso a los scripts.

**Para el owner (no aplicado — cambio de pipeline):** agregar un paso
`--bootstrap-wiki meian` a `scrape_delta.sh` y a `scrape_full.sh`. El módulo no tiene modo
delta, pero recorrer el catálogo completo es barato (1 listado + ~168 licencias + 1 request
por edición especial) y el merge por `cluster_key` absorbe lo conocido. Retorno: la fuente
vuelve a estar viva, con ISBN y fecha.


## Revisión de ingestión — 2026-09-24

El importador API se agregó a full y delta. Reingesta viva: 168 licencias, 118 candidatos especiales; dos productos ausentes detectados en copia de trabajo. Los errores HTTP/JSON se notifican como corrida parcial.

Evidencia y alcance: [auditoría integral](../audits/2026-09-24-ingestion.md).


Publicados dos coffrets The One recuperados. `best-seller` era un falso indicador de novela en la descripción: por sí solo ya no rechaza el producto. Conserva filtros literarios explícitos.
