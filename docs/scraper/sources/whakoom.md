# Fuente: Whakoom

> ⚠️ **PODA 2026-06-12 (poda de fuentes muertas)** — `ES/LatAm - Whakoom Novedades`: Novedades deshabilitada (kind js/Playwright → 1 item neto histórico). El spider whakoom opt-in sigue disponible (INCLUDE_WHAKOOM_SPIDER=1).
> Registro completo: [descartadas/README.md](descartadas/README.md).

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-09-02 (§6 — CIERRE de la vía: las 18 candidatas de tanda 3
> curadas 18/18 aprobadas y aplicadas, deuda de sync de tanda 2 podada (131→76 entries),
> 167 portadas whakoom aplicadas en total entre las 3 tandas; techo medido de la vía: 158
> items ES con tomo >11 que exigen cuenta. Ver `docs/reference/images.md` § "Cierre vía
> whakoom (2026-09-02)").
> Revisión previa 2026-09-02 (§6 — tanda 3 del skill `/watch-whakoom-covers`: retries
> priorizados sobre los 4 endurecimientos post-tanda-2 (metadata remota, Trigun Maximum,
> `sibling_urls`) + 41 targets nunca intentados. 134 targets únicos, 18 candidatas nuevas
> encoladas (`verified: true`), Trigun Maximum confirmado 5/5 destrabado con datos reales,
> `sibling_urls` sin un caso real que lo ejercite todavía, hallazgo nuevo de
> `series_display` en inglés sin indexación en Whakoom. Ver `docs/reference/images.md` §
> "Whakoom tanda 3" para el desglose completo).
> Revisión previa 2026-09-02 (§6 — tanda 2: ventana real 170/179 targets intentados
> (15:17-15:52 UTC, ver `data/cover_search_attempts.jsonl`), 55 candidatas encoladas,
> todas `verified: true` — corrección 2026-09-02 de un conteo previo que sumaba de más la
> actividad de tanda 1; 2 hallazgos nuevos en §6 — plantilla "hub" de portadas
> alternativas y `publisher_matches()` sensible al orden de tokens en imprints
> co-editados).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Whakoom |
| **URL base** | `https://www.whakoom.com` |
| **Índice / punto de entrada** | `https://www.whakoom.com/newtitles` (~415 novedades editoriales recientes) |
| **Página de un tomo** | `https://www.whakoom.com/comics/{shortcode}/{slug}/{vol}` |
| **Página de una edición** | `https://www.whakoom.com/ediciones/{id}/{slug}` (colección, NO un tomo — #14) |
| **Tipo de fuente** | Catálogo comunitario / tracker de coleccionistas (no es tienda) |
| **`kind` en sources.yml** | `html` (la fila /newtitles); el spider profundo es un módulo wiki (`--bootstrap-wiki`) |
| **`source_class`** | `trusted_media` |
| **País(es)** | España / LatAm — Argentina, México, España; el spider también captura ediciones en otros países (ver §1 corpus) |
| **Idioma(s)** | Español (principal); el spider detecta también Inglés, Italiano, etc. del HTML de la edición |
| **Cobertura** | Indexa exhaustivamente cómics y manga publicados en España y LatAm; expone novedades + variantes/portadas alternativas sin login |
| **Aporte al corpus** | ~26 items |
| **Parser / módulo** | Fila YAML `ES/LatAm - Whakoom Novedades` + spider `scripts/wikis/whakoom.py` |

**Editoriales / países que abarca** (del corpus real, ver snippet en §10):

- **Editoriales** (con volumen aprox. en el corpus): Seven Seas Entertainment (≈9) ·
  Editorial Ivrea (≈6) · Varias editoriales (≈5, items del spider sin publisher resuelto) ·
  Viz Media (≈2) · Panini Manga México (≈1).
- **Países**: Estados Unidos (≈11) · Argentina (≈6) · España / LatAm (≈5, el default de la
  fuente) · México (≈1).

Recuerda: `publisher` = editorial real (Ivrea, Seven Seas…), nunca "Whakoom" (#44).

**Por qué importa / qué aporta de único**: Whakoom es el mejor catálogo del **mercado
español y latinoamericano de manga** (Argentina, México, España), un mercado que pocas
fuentes del catálogo cubren. Su diferencial frente a otras fuentes es que expone
**variantes y portadas alternativas** (ej. "Spy x Family #1 Portada Alternativa, Ivrea
Argentina") que no aparecen en un listado plano de novedades: cada tomo lista sus
ediciones específicas, y desde una edición se descubren sus hermanas (deluxe, cofre,
portada alternativa). El acceso es sin login.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**:
  - `/newtitles` → ~415 últimas novedades editoriales públicas (el radar). Cada novedad es
    un `<a href="/comics/{shortcode}/...">` al volumen.
  - `/comics/{shortcode}/{slug}/{vol}` → página de un tomo individual; lista las
    `/ediciones/N` específicas de ese volumen.
  - `/ediciones/{id}/{slug}` → metadata completa de UNA edición (OG tags) + lista de tomos
    + lista de ediciones hermanas (variantes). **Una `/ediciones/` es una colección, no un
    tomo** (#14): se expande a N tomos `/comics/...`, nunca se guarda como un solo item.
  - `/publisher/{id}/{slug}` → índice puro de ediciones de un editor (no productos;
    `is_whakoom_publisher_url`).
  - `/autores/{id}/{slug}` → discovery por autor (accesible sin login; mencionado en las
    notas del YAML, no recorrido por el spider canónico).
- **Estructura del HTML / selectores clave**:
  - `/newtitles`: `a[href^='/comics/']` (selector de la fila YAML, e
    `extract_comics_urls_from_newtitles` en el spider).
  - Página de edición: OG tags (`og:title`, `og:description`, `og:image`, `og:url`); el
    publisher sale del paréntesis final del `og:title` (`"… (Ivrea Argentina)"`) o de
    `.publisher`; idioma/país de `ul.info-summary > li .value.flag` + `.title`
    (`_detect_language_from_edition_html`); autores de `h3.autores + p`; tipo de edición de
    `p.edition-type`.
  - Tomos dentro de una edición: `li[id^='comic'] a[href^='/comics/']`
    (`parse_volume_links`). Whakoom muestra sólo ~11 tomos en la página principal; el resto
    está en `<edition_url>/todos` (`edition_todos_url`).
  - One-shots: la URL `/comics/` canónica viene enmascarada en `/login?ReturnUrl=…`
    (`_extract_oneshot_comic_url`).
- **Identificador de producto**: la URL canónica del tomo (`/comics/{shortcode}/…/{vol}`).
  La `/ediciones/N` se usa sólo como agrupador/origen, nunca como identidad del item (#14).
- **Anti-bot / quirks**:
  - **Cloudflare agresivo** (#15): es la razón por la que el spider profundo es **opt-in**.
    El spider usa headers "browser-like" completos (no sólo User-Agent) para reducir
    challenges/429, detecta la página de challenge (`WhakoomBlocked`) y **aborta el batch
    entero** si la IP entra en cuarentena. Markers reales: `cf-chl-bypass`,
    `__cf_chl_rt_tk`, `/cdn-cgi/challenge-platform/h/` (NO el script JSD legítimo).
    **Refactor 2026-07-07 (sin cambio de comportamiento)**: la detección ya NO vive en
    `wikis/whakoom.py` — delega en la función compartida `detect_challenge()` de
    `scripts/manga_watch.py`, que es ahora la fuente ÚNICA de esos markers (la reutiliza
    también Mangavariant para su challenge sgcaptcha). `whakoom.py` sólo llama
    `detect_challenge(html_text) is not None`; los mismos markers, la misma lógica.
  - **Brotli** (#15): el header **NO** debe pedir `br` — `requests` no lo decodifica nativo
    y `response.text` quedaría binario (parser ve 0 tomos en silencio). Se usa
    `Accept-Encoding: gzip, deflate`. Si re-agregás `br`, agregá `brotli` a requirements.
  - **429 / rate-limit**: backoff exponencial (10s → 20s → 40s) en `fetch_url`. Si ves
    muchos `[WHAKOOM] 429`, subí `--sleep-seconds` a 3.0.
  - **Throttle local**: lockfile en `~/.cache/manga-watch/whakoom_lastrun` impide correr el
    bootstrap completo más de 1× cada 6h (protege la IP). `--ignore-throttle` lo salta.
- **Calidad de imágenes**: las portadas salen del `og:image` de la edición y del cover del
  tomo individual (`img` dentro del `<a>`); puede venir thumbnail (`small/`).

---

## 3. Proceso de ingestión — vista de producto

> Whakoom tiene dos caminos: la fila /newtitles (ligera, default) y el spider profundo
> (opt-in). Lo que sigue describe el spider, que es donde está la lógica de captura.

1. **Tomar el radar** (`/newtitles`): la lista de ~415 novedades recientes → URLs de
   volúmenes (`/comics/{X}`).
2. **Por cada volumen**, abrir su página y listar las **ediciones** (`/ediciones/N`) que lo
   publican (regular, deluxe, cofre, portada alternativa…).
3. **Por cada edición**, expandirla: una edición es una **colección de tomos** (#14), así
   que se produce **un item por tomo** (`/comics/.../{vol}`), heredando de la edición su
   publisher, autor, idioma, país, tipo de edición y descripción. Las ediciones hermanas
   descubiertas en esa página se agregan a la cola (BFS) para capturar variantes que el
   listado plano no expone.
4. **Decidir qué entra**: de cada tomo expandido sólo se conserva el que parece manga
   (`is_likely_manga` con `source_purity="mixed"`) y supera el umbral de score.
5. **Repetir** hasta agotar la cola o tocar el cap de ediciones (`max_editions=1500`).

**Reglas de producto que nunca se rompen:**
- Una `/ediciones/N` NUNCA se guarda como item; siempre se expande a tomos `/comics/…`
  (#14).
- El país de la edición es el de la edición (editorial/idioma), no el de la tienda (#46);
  el spider lo infiere por publisher/flag (Argentina, México, España, etc.).
- `publisher` = editorial real, nunca "Whakoom" (#44).
- En una fuente `mixed` sólo pasa lo que tiene hint fuerte de manga; la comics blacklist
  (Marvel/DC/Astérix/etc.) aplica siempre (#11, decisión de diseño #3).

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

Whakoom tiene **dos caminos** que se comportan distinto en el pipeline:

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| **Fila /newtitles** (default, kind:html) | corre en la **fase 1** (scrape de fuentes del YAML) | idéntica — corre en la **fase 1** |
| **Spider profundo** (opt-in) | paso **2q**, sólo si `INCLUDE_WHAKOOM_SPIDER=1` | paso **2p**, sólo si `INCLUDE_WHAKOOM_SPIDER=1` |
| Invocación spider | `--bootstrap-wiki whakoom --sleep-seconds 2.0 --min-score 20` | idéntica |
| Discovery | `/newtitles` → BFS de 3 niveles (comics → ediciones → tomos + hermanas) | idéntico (Whakoom no indexa por mes) |
| Default | **OFF** (riesgo Cloudflare) | **OFF** |

- **Camino default (sin spider)**: la fila `ES/LatAm - Whakoom Novedades` lee sólo
  `/newtitles` (`max_pages: 1`, ~415 novedades) usando el selector `a[href^='/comics/']`.
  Es ligera, sin riesgo de ban, y corre en cada scrape (full y delta) sin intervención.
  Captura el delta diario al **nivel 1** (novedad → volumen), sin variantes.
- **Camino opt-in (spider)**: `--bootstrap-wiki whakoom` corre el BFS completo de 3
  niveles, que descubre **todas las variantes y portadas alternativas** relacionadas a las
  novedades. Pesado (~1500 ediciones, ~60-70 min con `sleep=2.0`) y con riesgo de Cloudflare
  ban — por eso está detrás de `INCLUDE_WHAKOOM_SPIDER=1` (default OFF en ambos scripts).
- El módulo ignora `year_from`/`month_to` (Whakoom no es por mes); los mantiene por
  compatibilidad con la interfaz de wikis.
- **Nota del propio módulo**: para discovery regular se recomienda
  `scripts/retrofit/search_discovery.py` (Gemini + Grounding) en lugar del spider — cubre
  histórico, sin riesgo de ban y más rápido. El spider queda para bootstrap inicial de
  volumen o recovery forense puntual.

---

## 5. Proceso de ingestión — técnico

Parser/spider: [`scripts/wikis/whakoom.py`](../../../scripts/wikis/whakoom.py).
La fila /newtitles es una entrada estándar de `sources.yml` (`kind: html`) que recorre el
loop genérico de fuentes; el spider se activa con `--bootstrap-wiki whakoom`, que bypassea
ese loop (#8).

### 5.1 Modelo de datos / claves
- País de la edición (#46): el spider lo infiere por publisher conocido (`"argentina"` →
  Argentina, `"méxico"`/`"mexico"` → México, `"ivrea españa"`/`"planeta"`/`"norma"`/
  `"panini españa"` → España) y por el flag/`.title` de `ul.info-summary`
  (`_detect_language_from_edition_html`, que también mapea Estados Unidos, Italia, etc.).
  El default de la `_virtual_source()` es país="España / LatAm", idioma="Español".
- Identidad del producto = URL del tomo `/comics/…`. La `/ediciones/N` es un agrupador
  (#14): se expande, nunca se persiste como item.
- `source_class="trusted_media"`, `kind="html"`, `purity="mixed"` (tanto en la fila YAML
  como en la `_virtual_source()` del spider).

### 5.2 Qué captura el parser (mapea el §3 al código)
- `extract_comics_urls_from_newtitles()` — nivel 1: `/newtitles` → URLs `/comics/{X}`.
- `extract_ediciones_urls_from_html()` — nivel 2: `/comics/{X}` → pares `(id, /ediciones/N)`,
  deduplicados por id.
- `expand_whakoom_edition()` — nivel 3: expande una `/ediciones/N` en N `Candidate`s (uno
  por tomo). Lee la página principal (`parse_edition_metadata` + `parse_volume_links`) y,
  si hay >~11 tomos, `<url>/todos`. Merge por URL (`_merge_volume_dicts`). Fallback
  one-shot vía `_extract_oneshot_comic_url` cuando la edición no lista tomos.
- `expand_whakoom_publisher_url()` — expande una `/publisher/` a sus ediciones (no en el
  flujo BFS canónico).
- **Gate de entrada**: por cada tomo, `is_likely_manga(..., source_purity="mixed",
  publisher=…)` (#11/#3) y luego `score_candidate`; al final se conservan los de
  `score ≥ --min-score` (20 en el pipeline).
- `signal_types`/`product_type` se derivan aguas abajo del `title + description` (#10), no
  los setea el spider.

### 5.3 Flujo end-to-end
- **Fila /newtitles**: fase 1 de `scrape_full.sh` y `scrape_delta.sh` (scrape de fuentes del
  YAML), sin flags especiales.
- **Spider**: paso **2q** en `scrape_full.sh` y paso **2p** en `scrape_delta.sh`, sólo si
  `INCLUDE_WHAKOOM_SPIDER=1`. Comando:
  ```
  manga_watch.py --bootstrap-wiki whakoom --sleep-seconds 2.0 --min-score 20
  ```
- Escribe a `data/items.jsonl` incrementalmente vía `flush_fn` (por edición). Luego pasa por
  las fases comunes (cleanup retrofits → build → validate). No tiene retrofits dedicados.
- Tras el scrape, items.jsonl queda **raw** (sin `standardized_at`). NO correr
  `/watch-standardize-catalog` automáticamente.

---

## 6. Resolución por página de edición para portadas ES (skill `/watch-whakoom-covers`)

> Vía APROBADA por el owner (2026-09-02), separada del spider de ingestión (§2-§5
> de arriba). No agrega items nuevos al corpus — sólo mejora `images[0]` de items
> ES ya existentes. Implementación: `scripts/retrofit/we_plan.py` +
> `scripts/retrofit/we_resolve.py` + skill
> [`watch-whakoom-covers`](../../../.claude/skills/watch-whakoom-covers/SKILL.md).
> Motivación: la vía genérica de `/watch-search-covers` (Bing texto + Yandex
> reverse-image) sólo acertó **1% real** sobre el pool ES (gotcha #173) — Bing sí
> encuentra la página/serie correcta en Whakoom, pero una búsqueda de imagen
> suelta no sabe distinguir la edición ES exacta (regular/kanzenban/deluxe,
> logo/crop/color distintos) de sus hermanas. Esta vía resuelve la **página de
> edición** primero (editorial + idioma + total de tomos), y sólo DESPUÉS busca
> la imagen del tomo — reduce el problema a "¿es esta la edición correcta?" en
> vez de "¿es esta imagen la portada correcta?".

**Límites públicos verificados en vivo (reconocimiento 2026-09-02)**:

- `/ediciones/<id>/<slug>` es pública (sin login) y expone: editorial (link
  `/publisher/`), idioma + país (`"Spanish (Spain)"`, etc.), formato
  (`"Rústica con sobrecubierta"`, `"Cartoné 122 pp"`…), total de tomos, estado,
  y los **primeros ~11 tomos** como `<a href="/comics/<hash>/<slug>/<n>">` con
  su cover. Sección "Other Editions" lista ediciones hermanas (idioma · formato
  · editorial · nº de tomos). `og:image` = la `large` del tomo 1. Sin JSON-LD.
- **Tomos > 11**: viven en `<edición>/todos` o en `/comics/<hash>/…` — AMBAS
  exigen cuenta Whakoom. **Fuera de alcance de este skill** (regla dura, nunca
  se navega ahí — además `/comics/` está en `Disallow:` de `robots.txt`).
- **Sin ISBN, sin buscador público**: no hay endpoint de búsqueda por texto en
  el sitio — la única vía de descubrimiento es indexación externa (Bing con
  `site:whakoom.com`, igual que hace el spider/skill de ingestión).
- **Tamaños de imagen del CDN** (`i1.whakoom.com/<size>/<2hex>/<2hex>/<32hex>.jpg`):
  `small` 263×400, `medium` 277×397, `large` — **NO es un tamaño fijo** (corrección
  2026-09-02: la revisión anterior asumía 489×700 como máximo constante). Whakoom sirve
  en `/large/` la imagen que el usuario subió, redimensionada a lo sumo a ese tier —
  medido sobre las 149 candidatas aplicadas de las tandas 1-2: rango real **345×500 a
  718×1000** (área 172 500 a 718 000 px, mediana ~300 000 px). `original`/`xlarge` →
  404. El upgrade `/small|thumb|medium/ → /large/` ya existe en
  `sc_validate.py`/`upgrade_image_resolution.py` — se reutiliza sin cambios.
- **Cloudflare bloquea requests sin JS** (403) — el acceso es SOLO vía navegador
  real (Browser pane de Claude Code, `mcp__Claude_Browser__*`; Chrome del owner
  como fallback). **Nunca** se intenta resolver un captcha/challenge — si
  aparece, se abandona el target. Rate limit conservador: **2-3s** entre cargas
  de página.

**Algoritmo** (determinista, sin LLM — código en `we_plan.py`/`we_resolve.py`):

1. `we_plan.py` selecciona items ES (`country == "España"`) sin imagen o con
   portada chica (`--target-rule area`, default acá — la mayoría son thumbnails
   `static.listadomanga.com` ~210×300 px, gotcha #39) con `volume <= 11` o
   vacío/oneshot. Calcula `total_tomos` — **REMOTO por defecto desde tanda 3**
   (2026-09-02): si `data/listadomanga_collection_meta.jsonl` ya tiene una fila
   para el `coleccion_id` del item (poblada por `scripts/retrofit/listadomanga_meta.py`,
   Step 1b del skill, ver Runbook), usa el `total_tomos` REAL que reporta
   `listadomanga.es/coleccion.php?id=N`; si no, cae al heurístico LOCAL de
   siempre (conteo de items del corpus que comparten `edition_key` — sin red,
   puede infra-contar series en curso con tomos aún no ingestados). Cada
   target trae `listado.source` (`"listadomanga_remota"` / `"local_count"`) y
   `listado.ongoing` (True si listadomanga tiene tomos anunciados aún sin
   editar) y arma la query `site:whakoom.com "<serie>" <editorial>`.
2. El skill busca en Bing (máx 3 candidatas), abre cada `/ediciones/` en el
   Browser pane y extrae un JSON compacto (editorial, idioma, formato, total de
   tomos, ediciones hermanas con su URL propia, lista de tomos con cover) —
   nunca el DOM completo.
3. `we_resolve.py` acepta una edición sólo si:
   - idioma == `"Spanish (Spain)"` ∧
   - editorial coincide con el item por **conjunto de tokens normalizados**
     (`publisher_matches`, endurecido tanda 3 — ya no es contención de
     substring, tolera un imprint co-editado con el orden de tokens
     invertido) ∧
   - total de tomos coincide con `listado.total_tomos` — **igualdad estricta**,
     salvo que `listado.ongoing` o la propia edición whakoom se declaren en
     curso, en cuyo caso se acepta `cand.total_tomos >= listado.total_tomos`
     (endurecido tanda 3 — whakoom también puede llevar su contador
     desactualizado en ediciones "Ongoing", ver bullet más abajo). Si
     `listado.total_tomos` es desconocido, se exige en cambio que ninguna
     edición hermana sea también ES del mismo publisher ∧
   - **guard de reedición** (endurecido tanda 3): si la edición es oneshot
     (`total_tomos == 1`) o tiene una hermana ES del mismo publisher con el
     MISMO `total_tomos`, el formato+páginas embebidos en el slug de whakoom
     (`"<título>-rustica_240_pp"`) deben ser consistentes con
     `listado.formato`/`listado.paginas` (remoto) — si no hay datos
     suficientes para comparar Y existe esa hermana, no resuelve
     (`ambiguous_sibling_same_publisher`).

   Más de una candidata pasando el filtro ⇒ **ambiguo, no resuelve** (precisión
   > recall, igual que el resto del pipeline de imágenes). Si NINGUNA candidata
   resuelve por `language_mismatch`, el resultado trae `sibling_urls` — URLs de
   hermanas ES-España del mismo publisher que alguna candidata abierta listaba
   en "Otras ediciones" (endurecido tanda 3, ver bullet de idioma más abajo).
4. La imagen resuelta pasa por el MISMO validador permanente que
   `/watch-search-covers` (`sc_validate.py` — `_same_cover` + `_is_soft_image` +
   `candidate_metadata_conflict`) y se encola con `sc_flush.py`, marcada
   `via: "whakoom_edicion"`. **Nunca auto-aplica.**

**Caché append-only**: `data/whakoom_edition_map.jsonl` — una fila por intento de
resolución (éxito o no), `{series_key, series_display, publisher, country,
listado_coleccion_id, total_tomos, formato, whakoom_edition_id,
whakoom_edition_url, resolved_at, method}`. La escribe `we_resolve.py`; `we_plan.py`
sólo la lee (reutiliza `edition_url` ya resuelta, evita repetir la búsqueda Bing).

**Caché hermano (tanda 3)**: `data/listadomanga_collection_meta.jsonl` — una fila
por `coleccion_id` fetcheado, `{coleccion_id, total_tomos, ongoing, formato,
paginas, editorial, fetched_at}`. La escribe `scripts/retrofit/listadomanga_meta.py`
(mismo módulo hace el fetch — GET a `coleccion.php?id=N`, reusa el parser canónico
`listadomanga_collections.parse_collection_page`, nunca reimplementa el HTML
parsing); `we_plan.py` sólo la LEE (no hace red, mismo perfil que `sc_plan.py`). El
Step 1b del skill corre `listadomanga_meta.py --from-plan .tmp_we_plan.json` ANTES
de la corrida final de `we_plan.py` que arma el plan que consume el loop (ver
Runbook).

**Universo real (reconocimiento 2026-09-02, sobre el corpus del momento)**: 670
items ES con imagen ausente o chica por área (182 sin imagen + 488 portada
chica), de los cuales **508 son resolubles** (`volume <= 11` o vacío: 139 sin
imagen + 369 portada chica) y **162 quedan fuera de alcance** (`volume > 11`,
requiere login: 43 sin imagen + 119 portada chica). Con `--target-rule scale`
(criterio de `sc_plan.py`, factor de reescalado en card) el pool ES cae a sólo
12 portadas (10 resolubles) — la mayoría de las portadas ES chicas por área NO
se ven mal en la card real (gotcha #172/#173), por eso `we_plan.py` usa `area`
como default en vez de `scale`.

**Limitaciones conocidas**:

- Tomos `> 11` (162 items del pool, ver arriba) permanecen fuera de alcance sin
  una cuenta Whakoom del owner — decisión pendiente (ver Runbook).
- **Ediciones-hermanas casi idénticas y sin campo que las distinga** (hallazgo tanda 1):
  varios oneshots (p.ej. "Regreso al mar", "El muerto enfermo de amor", "Seraphim") tienen
  2-3 entradas en Whakoom con el MISMO publisher/idioma/`total_tomos` y sin ninguna
  diferencia visible en la metadata extraída (ni siquiera en `formato`) — probablemente
  duplicados de catálogo o reediciones idénticas. `we_resolve.py` correctamente no elige
  entre ellas (`ambiguous_multiple_editions`); no hay forma determinista de desambiguar sin
  abrir cada una y comparar visualmente la portada.
- **Tercera plantilla de página no documentada: "hub" de portadas alternativas** (hallazgo
  tanda 2, 2026-09-02): `/ediciones/589206` (`spy_x_family_portada_alternativa`) no es ni la
  plantilla "cómics" (`p.publisher`) ni la "libro/artbook" (línea `Idioma · Editorial`) — es
  un selector de "elige tu portada alternativa" sin la metadata de edición habitual. La
  extracción del skill devuelve `publisher`/`language`/`total_tomos` vacíos para esta página;
  `we_resolve.py` la descarta por `language_mismatch` (resultado correcto por accidente, el
  motivo reportado no es el real). Sin guard para detectarla de antemano — sigue pendiente.
- **`estado`/"Ongoing" de la propia edición whakoom NO se extrae todavía** (tanda 3): el
  JSON compacto del Step 3 no captura el badge de estado de la página (mencionado como
  posible en el reconocimiento pero sin selector CSS verificado en vivo); `cand.ongoing`
  queda `false` por defecto salvo que un futuro piloto confirme el selector real y lo
  agregue a la extracción — mientras tanto, la relajación `>=` de la condición 3 del
  algoritmo depende sobre todo de `listado.ongoing` (lado listadomanga, sí verificado). Ver
  SKILL.md Step 3 para el TODO de extracción.

### Resueltos en tanda 3 (endurecimientos, 2026-09-02)

Los siguientes 4 hallazgos de las tandas 1-2 (arriba) se cerraron con código + tests
(`tests/test_we_plan.py`, `tests/test_we_resolve.py`, `tests/test_listadomanga_meta.py`):

- **`total_tomos` local infra-contaba series en curso** → endurecimiento #1: nuevo
  módulo `scripts/retrofit/listadomanga_meta.py` fetchea el `total_tomos` REAL de
  `listadomanga.es/coleccion.php?id=N` (reusando el parser canónico
  `listadomanga_collections.parse_collection_page`) y lo cachea en
  `data/listadomanga_collection_meta.jsonl`; `we_plan.py` lo prefiere sobre el
  heurístico local (`listado.source`). Además, `listado.ongoing`/`cand.ongoing`
  relajan la condición 3 de `we_resolve.py` a `>=` en vez de `==` estricto — cubre
  tanto el caso "listadomanga no editó aún lo que whakoom ya cuenta" como el
  contador de whakoom desactualizado (bullet "Ongoing" de tanda 1, arriba).
  **Simulación offline** (sobre `data/whakoom_edition_map.jsonl`, 326 filas de la
  corrida real): 63 filas `total_tomos_mismatch` colapsan en **13 `coleccion_id`
  distintos** a re-consultar en una tanda 3 real (Bleach 3000, Attack on Titan 5060,
  Radiant 2325, One Piece 2570, Shangri-La Frontier 4290, Yuuna and the Haunted Hot
  Springs 3346, Erio to Ningyou 5823, Ranma 1/2 4782, Berserk 4945, The Summer
  Hikaru Died 4560, F.COMPO 3720, Inuyasha 4753, Witch Hat Atelier 3020) — no se
  pudo re-ejecutar `we_resolve.py` extremo a extremo sobre esos 63 casos porque el
  JSON compacto de candidatas (formato/idioma/`other_editions`/`volumes` que
  extrae el Step 3 del skill) no quedó persistido en ningún lado tras esas
  corridas; sólo el resumen agregado sobrevive en la caché
  `whakoom_edition_map.jsonl` (no guarda el lado whakoom de la comparación).
- **Reediciones del mismo sello con mismo `total_tomos` pero formato distinto**
  (caso `sensor-ecc-deluxe-es`, único error de la curación tanda 1) →
  endurecimiento #2: `we_resolve._reedition_guard_ok` compara el formato+páginas
  embebidos en el slug de whakoom contra `listado.formato`/`listado.paginas`
  (remoto) cuando la edición es oneshot o tiene una hermana con el mismo
  `total_tomos`; sin datos suficientes para comparar y con esa hermana presente,
  no resuelve (`ambiguous_sibling_same_publisher`).
- **`publisher_matches()` por substring, no por conjunto de tokens** (`task_07e139d6`,
  4 targets Trigun Maximum) → endurecimiento #3: `we_resolve.publisher_matches`
  ahora compara CONJUNTOS de tokens normalizados (subset en cualquier sentido,
  intersección no vacía) — verificado directamente contra el caso real: `"EDT
  Editores de Tebeos / Ediciones Glénat"` (tokens `{edt, editores, de, tebeos,
  glenat}`) vs `"Glénat España - Editores de Tebeos"` (tokens `{glenat, editores,
  de, tebeos}`) → el segundo conjunto es subconjunto del primero → **match**.
  `task_07e139d6` cerrada.
- **33 `language_mismatch` por indexación LatAm de Bing** → endurecimiento #4: el
  Step 3 ahora captura `edition_url` de cada entrada de `other_editions[]`, y
  `we_resolve._collect_sibling_urls` devuelve las URLs de hermanas ES-España del
  mismo publisher cuando NINGUNA candidata resuelve por idioma, para que el skill
  las abra sin repetir la búsqueda Bing (SKILL.md Step 4). No se pudo verificar
  contra datos reales de la tanda 2 (mismo motivo que endurecimiento #1: el JSON
  compacto de las candidatas no quedó persistido) — cubierto por tests
  sintéticos, pendiente de confirmar el hit rate real en una tanda 3.

### Tanda 3 — corrida real (2026-09-02): resultado de los 4 endurecimientos

Corrida real (skill + Browser pane) sobre el corpus post-delta-diario (universo
recalculado desde cero: 359 targets pendientes, no 508 — el corpus cambia entre
tandas). Step 1b corrió sobre las 226 `coleccion_id` del plan (0 errores; 228
targets salieron con `total_tomos` REMOTO). Detalle completo con desglose por serie
en `docs/reference/images.md` § "Whakoom tanda 3". Resumen del veredicto de cada
endurecimiento:

1. **Total remoto + relajación `ongoing`**: de los 12 `coleccion_id` de
   `total_tomos_mismatch` reverificables (de los 13 originales, uno salió del plan
   por drift del corpus), **5 destrabaron la edición** (Berserk, The Summer Hikaru
   Died, Witch Hat Atelier, Radiant, One Piece) pero sólo 1 (Witch Hat Atelier)
   aportó una candidata válida — los otros 4 son casos donde la edición correcta
   resolvió pero la imagen no calzaba (portada de otro tomo, o el caso de ambigüedad
   de tipo de producto ya documentado — Radiant resolvió contra la variante en vez de
   la regular, One Piece contra el especial de 113 tomos en vez del 1 tomo target).
   Los 7 restantes (incluido Shangri-La Frontier) siguen sin resolver — el conteo
   remoto de `listadomanga.es` en varios casos es el total de la obra japonesa
   completa, mayor al de la edición española real que Whakoom cuenta; la relajación
   `>=` no cubre ese caso inverso (estructural).
2. **Guard de reedición**: no se observó ningún `ambiguous_sibling_same_publisher`
   nuevo en esta tanda (0 casos) — sin evidencia adicional más allá de la tanda 1.
3. **`publisher_matches()` por tokens (Trigun Maximum)**: **CONFIRMADO con datos
   reales** — 5/5 targets Trigun Maximum resolvieron la edición (Glénat España -
   Editores de Tebeos ↔ EDT Editores de Tebeos / Ediciones Glénat) y 4/5 quedaron
   encolados. `task_07e139d6` cerrada con evidencia real.
4. **`sibling_urls`**: de los 33 `language_mismatch` reintentados, 15 destrabaron —
   pero **NINGUNO vía el mecanismo `sibling_urls`** (en todos los casos donde se
   abrió la edición LatAm original, "Otras ediciones" no listaba una hermana
   ES-España). Los 15 resolvieron porque la búsqueda Bing de esta corrida trajo
   directamente la edición española entre sus 3 candidatas — sin necesidad del
   fallback. El mecanismo sigue sin un caso real que lo ejercite.

**Hallazgo nuevo de esta tanda**: `series_display` en inglés no encuentra ediciones
que Whakoom indexa por su título de publicación en español — ver gotcha nueva en
`docs/reference/gotchas.md` (caso real: "A Man and His Cat" vs. la edición indexada
como "El hombre y el gato", Norma Editorial, verificado en vivo).

**Resultado agregado**: 134 targets únicos, 18 candidatas nuevas encoladas (todas
`verified: true`), 0 `verified: false`. Cola total de `whakoom_edicion` pendientes:
73 (55 de tanda 2 + 18 de tanda 3). Cachés: `whakoom_edition_map.jsonl` 326→461
filas, `listadomanga_collection_meta.jsonl` 0→226 filas (poblado por primera vez).

### Cierre de la vía whakoom (2026-09-02): curación + aplicación de las 3 tandas

Turno de cierre (JUDGE), único escritor de `items.jsonl`/`cover_preview.json`. No
volvió a scrapear Whakoom — sólo curó, podó y aplicó lo que las tandas 1-3 dejaron
en cola. Detalle completo y balance en `docs/reference/images.md` § "Cierre vía
whakoom (2026-09-02)".

- **Curación de las 18 candidatas de tanda 3: 18/18 aprobadas, 0 rechazadas.**
  Hoja de contacto a ~520×700 px por cara (no la miniatura de 210×300, que esconde
  sello y número de tomo). En las 18 la candidata es la misma ilustración del mismo
  tomo y la misma edición en mayor resolución; sello/imprint coincidente con el
  `publisher` del item en todos los casos. Ninguna cayó en el patrón de reedición
  del mismo sello que motivó el guard `_reedition_guard_ok`.
- **Deuda de sync de tanda 2 cerrada.** Las ~110 operaciones que
  `sync_cover_preview.py --dry-run` reportaba eran 55 candidatas cuyo `new_url` ya
  era la portada del item (aplicadas el 09-01/02, nunca podadas) + las 55 entries
  que quedan vacías al podarlas. No podaba nada pendiente; el sync real corrió y
  dejó la cola en 131 → 76 entries.
- **Aplicación**: 18 reemplazos de portada, 0 `no_gain_at_apply` (gotcha #182), 0
  duplicados en `images[]` en todo el corpus, 60 candidatas pendientes de otras
  acciones intactas, ledger sin cambios (333 filas).
- **Balance de la vía**: entre tandas 1-3, las candidatas whakoom aplicadas a
  `items.jsonl` suman **167** (149 de tandas 1-2 + 18 de tanda 3). Cachés al cierre:
  `whakoom_edition_map.jsonl` 461 filas, `listadomanga_collection_meta.jsonl` 226.
- **Verificación**: `pytest` 2585 verdes, `validate_corpus.py` 0 violaciones duras,
  `filter_non_manga.py --dry-run` 0 rechazos, `sync_cover_preview.py --dry-run`
  final en 0 operaciones, `quality_report.json` regenerado (784 alertas).

**Techo de la vía, medido al cierre**: quedan **158 items ES con `volume > 11` y
portada mala** (25 sin ninguna imagen + 133 con portada < 90 000 px) que esta vía
**no puede** cubrir — Whakoom muestra a lo sumo ~11 tomos por edición sin login, y
`/todos` + `/comics/` exigen cuenta (`/comics/` además está en `Disallow:` del
`robots.txt`, regla dura §6). Sobre el universo ES completo `we_plan.py` los
reporta como "no resolubles (vol>11, requiere login): 452". Los otros dos frenos
conocidos son las 7 colecciones con `total_tomos` remoto mayor que la edición
española real (Shangri-La Frontier, Ranma 1/2, F.COMPO, Inuyasha, Attack on
Titan-Norma, Yuuna, Erio to Ningyou) y el gap de descubrimiento por
`series_display` en inglés (gotcha #186).

---

## 7. Validación

- **`scripts/validate_corpus.py`** — gate estructural del pipeline (aplica a TODO el corpus,
  sin red). Es la verificación principal para esta fuente.
- No hay auditoría de red dedicada ni enforcer/idempotencia propios (a diferencia de
  ListadoManga).
- Sanity manual: verificar que NO existan items cuya URL sea una `/ediciones/N` (deberían
  ser todas `/comics/…`; #14).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#14 (`/ediciones/` = colección, no tomo)**: una `/ediciones/N` lista varios tomos; si se
  guardara como un solo item, una serie entera quedaría como un registro. ✅ Se expande a un
  `Candidate` por tomo (`expand_whakoom_edition`); la `/ediciones/` sólo sirve de agrupador
  y para descubrir hermanas.
- **#15 (Brotli + Cloudflare challenge)**: pedir `br` en `Accept-Encoding` deja
  `response.text` binario → 0 tomos en silencio; y Cloudflare puede challengear la IP entera.
  ✅ Header sin `br`; detección de challenge (`WhakoomBlocked`) aborta el batch; throttle
  local de 6h. El spider llegó a **quemar la IP** una vez — por eso es opt-in.
- **#11 / #3 (purity mixed + comics blacklist)**: Whakoom mezcla manga + cómic occidental +
  BD. ✅ Sólo entra lo que pasa `is_likely_manga` con hint fuerte de manga; Marvel/DC/
  Astérix/etc. los filtra la comics blacklist (que aplica siempre).
- **#6 (placeholders de imagen)**: covers pueden venir como thumbnail/placeholder; el
  backfill aguas abajo re-fetchea cuando aplica.
- **Decisiones (lo que NO se hace)**: no se guarda ninguna `/ediciones/` ni `/publisher/`
  como producto (son índices/colecciones); no se mergea cross-país (#46); para discovery
  regular se prefiere `search_discovery.py` (Gemini) sobre el spider.

---

## 9. Pendientes / limitaciones conocidas

- **Spider opt-in por riesgo de ban**: el camino que captura variantes/portadas alternativas
  NO corre por default. Sin `INCLUDE_WHAKOOM_SPIDER=1`, sólo se captura el nivel 1 de
  /newtitles (novedad → volumen), sin variantes.
- **Cobertura sesgada a lo reciente**: tanto /newtitles como el spider parten del radar de
  novedades; los items históricos no se cubren por esta vía (de ahí la recomendación de usar
  `search_discovery.py`).
- **País/idioma heurísticos**: el país se infiere por publisher/flag; ediciones con publisher
  no mapeado caen al default "España / LatAm" (de ahí los ≈5 items con publisher "Varias
  editoriales" / país genérico en el corpus).
- **`/autores/{id}/{slug}`**: mencionado como vía de discovery por autor en las notas del
  YAML, pero el spider canónico NO lo recorre. {{pendiente: confirmar si existe un camino de
  discovery por autor implementado o si es sólo una nota.}}
- {{pendiente: confirmar el número de gotcha exacto del placeholder de imagen citado como #6
  arriba (verificado contra el heading de gotchas.md, pero conviene revalidarlo si se
  renumeran).}}

---

## 10. Runbook / comandos útiles

```bash
# Camino default (ligero, /newtitles): corre solo en fase 1 del scrape, vía la fila YAML.
# No requiere comando dedicado; es parte de scrape_full.sh / scrape_delta.sh.

# Spider profundo (OPT-IN, riesgo Cloudflare — deja items raw):
.venv/bin/python scripts/manga_watch.py \
    --bootstrap-wiki whakoom --sleep-seconds 2.0 --min-score 20

# En el pipeline, activar el spider (default OFF):
INCLUDE_WHAKOOM_SPIDER=1 scripts/scrape_delta.sh   # paso 2p
INCLUDE_WHAKOOM_SPIDER=1 scripts/scrape_full.sh    # paso 2q

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "whakoom"
def hit(it):
    blobs=[it.get('url','') or '']+[ (s.get('url','') or '') for s in it.get('sources',[]) ]
    return any(NEEDLE in b for b in blobs)
items=[json.loads(l) for l in open("data/items.jsonl") if l.strip()]
sel=[it for it in items if hit(it)]
print("items:", len(sel))
print("países:", Counter((it.get('country') or '') for it in sel if it.get('country')))
print("editoriales:", Counter((it.get('publisher') or '') for it in sel if it.get('publisher')).most_common(20))
PY

# --- §6: resolución de portadas ES por página de edición -------------------

# Ver el universo ES (sin lanzar el skill ni tocar disco):
.venv/bin/python scripts/retrofit/we_plan.py --dry-run

# Plan real (escribe .tmp_we_plan.json, lo consume el skill /watch-whakoom-covers):
.venv/bin/python scripts/retrofit/we_plan.py --limit 30

# Step 1b (tanda 3, opt-in, hace RED): completa el caché de total_tomos REMOTO
# para los coleccion_id del plan que todavía no lo tienen — correr ANTES de la
# corrida final de we_plan.py que arma el .tmp_we_plan.json que consume el skill,
# así los targets salen con listado.source == "listadomanga_remota" en vez de
# "local_count". Throttle 2s por default entre fetches.
.venv/bin/python scripts/retrofit/listadomanga_meta.py --from-plan .tmp_we_plan.json
.venv/bin/python scripts/retrofit/we_plan.py --limit 30   # re-generar con el caché ya poblado

# Invocar el skill completo (agente + Browser pane):
#   /watch-whakoom-covers --limit 30

# Inspeccionar el caché de ediciones resueltas:
cat data/whakoom_edition_map.jsonl | .venv/bin/python -c "
import json, sys
from collections import Counter
rows = [json.loads(l) for l in sys.stdin if l.strip()]
print('filas:', len(rows))
print(Counter(r.get('method') for r in rows))
"

# Inspeccionar el caché de metadata remota de listadomanga (tanda 3):
cat data/listadomanga_collection_meta.jsonl | .venv/bin/python -c "
import json, sys
rows = [json.loads(l) for l in sys.stdin if l.strip()]
print('filas:', len(rows), '— ongoing:', sum(1 for r in rows if r.get('ongoing')))
"
```

**Antes de cerrar cualquier cambio en Whakoom**: validar (`validate_corpus`, 0 duras) →
tests (`pytest tests/test_extraction.py tests/test_we_plan.py tests/test_we_resolve.py
tests/test_we_integration.py tests/test_listadomanga_meta.py`) → build. Si tocaste algo meaningful, actualiza esta
ficha.
