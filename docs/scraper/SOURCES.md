# SOURCES.md — Adding and maintaining sources

How to add new manga sources without breaking the filter logic.

## Anatomy of an entry in `sources.yml`

Minimum:
```yaml
- name: "XX - Source Name"
  country: "Country Name"
  language: "Language Name"
  publisher: "Publisher Name"
  source_class: "official | retailer | trusted_media | social"
  kind: "html | rss | js | bluesky | wiki"
  url: "https://example.com/manga/"
  enabled: true
  tags: ["manga", "official", "store"]
```

The five live `kind`s, in rough order of how often you'll add one:
- **`html`** — most retailer catalogs. Listing-page parsing via
  `extract_listing_candidates` with `item_selector` from
  `selectors:` (or auto-detected).
- **`rss`** — publisher/blog feeds. Parsed via `feedparser`.
- **`bluesky`** — publisher Bluesky profiles. URL must be
  `https://bsky.app/profile/<handle>`. Uses the public XRPC API
  `public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed` — no auth,
  no API key. One request returns up to ~30 recent posts.
- **`js`** — pages that need a real browser. Requires `--enable-js`
  at runtime + `pip install playwright && playwright install chromium`.
  Under `--workers > 1` these sources dispatch to a dedicated
  `playwright-worker` thread via `_PLAYWRIGHT_QUEUE` (Playwright's
  greenlets are not thread-safe — see gotcha #12 in CLAUDE.md).
- **`wiki`** — NOT a runtime kind. Documents that the source is
  handled by a dedicated parser in `scripts/wikis/` and activated via
  `--bootstrap-wiki <name>`. Add the entry anyway so the source shows
  up in `--list-sources` and in the web filters.

Optional:
```yaml
  purity: "manga_only" | "mixed"      # default manga_only
  selectors:
    item_selector: "li.product"        # CSS selector for cards
    title_selector: "a"                # selector inside the card
    description_selector: ".desc"      # optional
  max_pages: 5                         # 0 = use global default
  notes: "free-text"
  # For search-template entries:
  search_template: "https://example.com/search?q={query}"
  keywords:
    - "edicion coleccionista"
    - "deluxe"
    - "kanzenban"
```

## Recipe: add a new HTML retailer

1. **Inspect the site** with curl + BeautifulSoup. Find:
   - The container that wraps each product card.
   - The anchor with the product URL.
   - Where the title text lives (often inside that anchor).

   Common patterns:
   - **Shopify**: `li.grid__item` or `.product-card`, links to `/products/<handle>`.
   - **Tiendanube**: `[data-product-id]`, links to `/productos/<handle>`.
   - **Magento**: `li.product-item` or `.product`, links containing `/p/` o `.html` (Pipoca & Nanquim, Panini BR usan rewrites planos sin `/p/`).
   - **WooCommerce**: `li.product`, links to `/product/<handle>` (o `/producto/` con locale ES).
   - **Loja Integrada (Brasil)**: ecommerce muy común en editoriales BR pequeñas (NewPOP), URLs planas `/<slug>-<id>`. Auto-detección suele bastar.
   - **OpenCart**: `.product-thumb` o `.product-layout`, URLs amigables o `?route=product/product&product_id=X`.

2. **Add to sources.yml** with selectors:
   ```yaml
   - name: "AR - Example Editorial"
     country: "Argentina"
     language: "Español"
     publisher: "Example Editorial"
     source_class: "official"
     kind: "html"
     url: "https://example.com/manga"
     enabled: true
     tags: ["manga", "official", "store", "new-source"]
     selectors:
       item_selector: "[data-product-id]"
       title_selector: "a[href*='/productos/']"
     max_pages: 5
   ```

3. **Test selectively** without scraping everything:
   ```bash
   python scripts/manga_watch.py --only-tags new-source --dry-run
   ```

4. **Check the output** in `reports/YYYY-MM-DD.md`. If the candidates
   list looks right, drop `--dry-run`.

5. **Remove the `"new-source"` tag** once you're confident it's stable
   (or keep it for selective re-runs).

### Tip: si `/collections/all` no captura todo, agregá la sub-colección

Algunos Shopify (ej. mangadreams.it) tienen `/collections/all` paginado
pero la paginación se queda corta o el sitio no expone todos los
productos ahí — sub-colecciones temáticas pueden tener items que
`/collections/all` no surfacea. Si auditás un sitio y ves productos en
`/collections/<x>` que no llegan vía la fuente "all", agregalo como
fuente hermana con el mismo selector. Ejemplo: `IT - Manga Dreams
(variants europeas)` apunta a `/collections/edizioni-europee-manga-variant-limited`
porque la fuente `/collections/all` solo capturaba ~6 de los 43
productos de esa sub-colección. Dedup automático por `(series_key,
edition_key, volume)` evita duplicar lo que sí se solapa.

## Recipe: add a Bluesky publisher source

Publishers (Norma, Ki-oon, Kodansha USA, Yen Press, VIZ, …) often
announce their special editions on Bluesky before any catalog page
exists. We poll their profiles via the public XRPC API — no auth.

```yaml
- name: "SOCIAL - VIZ Media Bluesky"
  country: "Estados Unidos"
  language: "Inglés"
  publisher: "VIZ Media"
  source_class: "social"
  kind: "bluesky"
  url: "https://bsky.app/profile/viz.com"
  enabled: true
  tags: ["social", "news", "manga", "us", "publisher"]
  notes: "Handle viz.com — NO vizmedia.bsky.social (stale desde nov-2024)."
```

**The URL is the source of truth for the handle.** `bluesky_handle_from_url`
parses `bsky.app/profile/<handle>` — supports both
`username.bsky.social` and custom domains (`viz.com`, `kodansha.us`,
`darkhorse.com`). Verify the handle still exists by opening the URL in
a browser before adding.

**Posts are NOT products.** A post from a publisher might be:
- A real announcement of a special edition (target case).
- A general news post.
- A re-share or unrelated content.

The same filter cascade (`is_likely_manga` → `is_pure_novel` →
`is_comic_not_manga` → score → `is_collectible_edition`) applies, so
non-product posts get dropped automatically. But `source_class:
"social"` gets a -5 score penalty in `score_candidate`, so use a
relatively low `--min-score` if you want social signals to surface
(default 20-30 is fine).

**15 Bluesky sources defined; all currently disabled** (0 items in corpus
— publisher posts are announcement/news, not product listings with
collectible signals; the 2026-05-25 audit disabled all 15). Re-enable
individually if a publisher starts posting edition-detail content.
Adding more: confirm the handle is live (don't add stale accounts that
haven't posted in 12+ months — verified empirically), set `enabled: true`,
run `python scripts/manga_watch.py --only-source "SOCIAL - X Bluesky"`
to smoke-test.

## Recipe: add a search-template entry

For retailers that don't have a clean "all manga" page but do have a
search that we can query for specific keywords.

```yaml
- name: "ES - Some Retailer (search)"
  country: "España"
  language: "Español"
  publisher: "Some Publisher"
  source_class: "retailer"
  kind: "html"
  enabled: true
  tags: ["manga", "retailer"]
  search_template: "https://some-retailer.com/search?q={query}"
  keywords:
    - "edicion coleccionista"
    - "deluxe"
    - "kanzenban"
    - "boxset"
```

`{query}` gets URL-encoded and substituted. Each keyword generates a
"virtual source" with name like `"ES - Some Retailer (search) [search: deluxe]"`.

**Watch out for mixed catalogs.** If the search returns non-manga
products (Hot Wheels, Marvel comics, sports cards, etc.), set
`purity: "mixed"` (see below).

## Recipe: when to use `purity: "mixed"`

A source is "mixed" if its catalog or feed includes things other than
manga. Behavior change:
- Pack-extras like "Collector's Edition" alone do NOT rescue an item.
- The default decision flips from "keep" to "discard". So you need a
  STRONG hint (manga / vol N / kanzenban / Deluxe Hardcover / Library
  Edition / etc.) to pass.

Examples already flagged:
- `US - Dark Horse Direct` (sells manga + comics + figures + statues +
  art prints + bookends).
- `MX - Panini Manga México` and its search variants (also sells trading
  cards, Hot Wheels, sports collectibles).
- `ES - Panini España (search)` (Marvel/DC comics, LIGA ESTE cromos).
- `ES - Norma (search)` (returns podcast episodes too).
- `US - Anime News Network News RSS` (news, not products).
- `US - ComicBook.com Anime` (blog).
- `US - Kodansha USA News` (blog with contests/announcements).
- `JP - Rakuten Books (search)` (encyclopedias, magazines, idol boxes).

**Test:** add the source, see if it lets through a non-manga item with
a pack-extras-only rescue (typical: a statue / figure / mug "Collector's
Edition"). If yes → mark mixed.

## Recipe: add a wiki parser

Wikis are sources that need custom Python parsing because their HTML
doesn't fit `extract_listing_candidates`. Examples: ListadoManga
(month-based calendar), Manga-Sanctuary (Unix timestamp planning),
Otaku Calendar, Manga México.

1. **Create the parser file** at `scripts/wikis/<name>.py`. Use
   `listadomanga.py` as the template. Implement the public API:
   ```python
   def parse_calendar_page(html_text, source_url) -> list[Candidate]
   def fetch_calendar_month(year, month, session, timeout) -> list[Candidate]
   def iter_year_months(yf, mf, yt, mt) -> list[tuple[int, int]]
   def bootstrap(yf, mf, yt, mt, session, sleep_seconds, timeout,
                 min_score, fetch_details) -> list[Candidate]
   ```

2. **Inside the parser:**
   - Each Candidate must be created via `candidate_from_source(source,
     title, url, description)` so the standard fields are populated.
   - Call `is_likely_manga(cand.title, cand.description, tags=cand.tags)`
     to filter out non-manga before adding to the result.
   - Call `score_candidate(cand)` to populate score / signals.
   - If items don't have unique URLs (e.g. a catalog wiki where all
     items share the catalog page URL), fabricate unique URLs with a
     query param like `?manga=publisher-slug`. Otherwise the
     URL-based dedup will collapse them.

3. **Register in `_run_wiki_bootstrap()`** (`scripts/manga_watch.py`):
   ```python
   elif args.bootstrap_wiki == "<name>":
       from wikis.<name> import bootstrap as wiki_bootstrap, iter_year_months
   ```
   Also add `"<name>"` to the `choices=` list of the
   `--bootstrap-wiki` argparse argument.

4. **Add a documental entry to `sources.yml`** so the source shows up in
   `--list-sources` and in the web filters. Marks `kind: "html"` (not
   `wiki`, since `wiki` is not a runtime kind) and `tags: ["wiki",
   "calendar", ...]`.

5. **Add tests** in `tests/test_extraction.py` covering at least:
   - Parsing happy path with a small realistic HTML.
   - Date parsing edge cases (if applicable).
   - URL uniqueness (if you fabricated synthetic URLs).

## Recipe: add a new metadata label

If a source uses a label that `_extract_label_value_pairs` doesn't
recognize (e.g. a new JP label, or a new way of saying "publisher"):

1. **Inspect the HTML** to confirm the label appears in a recognized
   structure (`<li><span>label</span>value</li>`, `<dt>/<dd>`,
   `<tr><th/td>label</th/td><td>value</td></tr>`).

2. **Add the label to `_FIELD_LABELS`** in `manga_watch.py`. It's a
   dict mapping field name to a tuple of label variants:
   ```python
   _FIELD_LABELS: dict[str, tuple[str, ...]] = {
       "author": (
           "dessinateur", "scénariste", "scenariste", "auteur", "auteurs",
           "autor", "autores", "author", "authors", "autore", "autori",
           "mangaka", "writer", "creator",
           "著者", "作者", "原作", "漫画",
           # ADD HERE
       ),
       ...
   }
   ```

3. **Add a test** in `tests/test_extraction.py` with the exact HTML
   snippet:
   ```python
   def test_extract_label_value_pairs_new_label():
       html = '<ul><li><span>NEW_LABEL</span>VALUE</li></ul>'
       soup = BeautifulSoup(html, "html.parser")
       pairs = mw._extract_label_value_pairs(soup)
       assert pairs.get("author") == "VALUE"
   ```

4. **Retrofit existing items** so the label gets applied historically:
   ```bash
   python scripts/retrofit/backfill_metadata.py --only author \
       --skip-source X --skip-source Y
   ```
   (Restrict to the source(s) you expect to benefit so the run is fast.)

## Recipe: bootstrap-wiki for historical archives

Some sources expose both a **recent feed** (RSS, current month, latest
posts) and a **historical archive** (months/years back). The differential
flow (RSS/HTML scrape in each regular run) covers the recent feed. To
backfill the historical archive there's a separate one-shot wiki bootstrap.

Example: listadomanga.es has BOTH:
- Blog RSS feed (`/blog/feed/`) — last ~10 posts. Covered by source
  `ES - Listado Manga Blog RSS` (kind:rss).
- Monthly archive (`/blog/YYYY/MM/page/N/`) — every post since 2009-11.
  Covered by:
  ```bash
  python scripts/manga_watch.py --bootstrap-wiki listadomanga-blog \
      --wiki-from 2009-11 --wiki-to 2026-05
  ```
  One-shot, ~30-60 min. Items get upserted into items.jsonl just like the
  regular flow — dedup-by-URL handles overlaps with the RSS run.

When to use which:
- **Daily/weekly runs** → RSS in normal scrape. Captures novedades del día.
- **First-time bootstrap** → run blog historical once. Recupera anuncios
  pre-fecha-de-instalación.
- **Forensic recovery** → cuando se descubre que un item de hace meses
  no está en items.jsonl, basta correr el bootstrap acotado al rango
  del lanzamiento sospechoso.

Mismo patrón aplica a otras wikis con archivo histórico — añadir su
parser en `scripts/wikis/<name>.py` siguiendo `listadomanga_blog.py`.

### Sitemap-driven bootstrap (Mangavariant pattern)

Cuando la wiki no tiene calendario mensual pero sí publica sitemaps XML
limpios, el patrón es distinto al de listadomanga.py:

1. Enumerá las URLs desde el(los) `<wiki>-sitemap*.xml` (Yoast / WP típico).
2. Procesá cada detail page en paralelo (`ThreadPoolExecutor`).
3. `iter_year_months()` devuelve `[(yf, mf)]` (un único batch) solo para
   que el dispatcher cuente "1 mes" en el resumen.
4. El rango `--wiki-from` / `--wiki-to` se acepta por compat con
   `_run_wiki_bootstrap` pero **se ignora** — la base de datos no está
   particionada por fecha.

Ejemplo concreto: `scripts/wikis/mangavariant.py` baja `variant-sitemap.xml`,
`variant-sitemap2.xml`, `variant-sitemap3.xml`, filtra a URLs con shape
`/variant/<manga>/<edicion>/`, y procesa los ~2700 detail pages con 4
workers. Una corrida = todo el catálogo. La fuente queda registrada
también en `sources.yml` con `max_pages: 1` para captar novedades en cada
overnight sin re-bajar el sitemap.

Cuándo aplicar este patrón:
- La fuente tiene sitemap XML público en `robots.txt` (sanctioned crawl).
- El catálogo es enumerable (no paginado infinito ni search-only).
- Las detail pages contienen toda la metadata necesaria (no hace falta
  un segundo crawl).

### JSON-feed wiki (SocialAnime pattern)

Algunas wikis renderizan items en cliente vía AJAX. La página HTML
inicial es vacía (selectores BS4 devuelven 0 items), pero el frontend
hace requests XHR a un endpoint interno que devuelve JSON limpio.
Si encontrás uno así:

1. **Descubrí el endpoint** abriendo DevTools → Network → XHR mientras
   cargás la página, o leyendo el JS que tira las requests
   (en SocialAnime fue `store/store.js` y la función
   `get_endless_manga_data` que hace `GET store/backend/flow_mangafeed.php`).
2. **Probá el endpoint con `curl` directamente** con `Referer` y
   `X-Requested-With: XMLHttpRequest` headers para validar que devuelve
   JSON sin auth.
3. **Identificá los parámetros relevantes**: tipo de colección, paginación,
   filtro temporal. En SocialAnime: `type={variant|box}`, `group_no={0,1…}`
   (25 items por página), `macro_filter={best_of_all|next_from_now|''}`.
4. **El parser baja JSON puro** y mapea cada entry del array a un Candidate.
   Mucho más simple que parsear HTML — sin BeautifulSoup, sin selectores
   frágiles. La fragilidad se traslada al schema del JSON.
5. **Iterá páginas hasta recibir array vacío** (o página parcial). Capá
   con `max_pages` defensivo (p.ej. 40) por si el server entra en loop.
6. **Tratá los links como sus dueños te los dan**: SocialAnime emite
   URLs Amazon affiliate (`amazon.it/dp/<ASIN>?tag=socianim0c-21`).
   Canonicalizalas en `normalize_url_for_dedup` para que distintos
   affiliates del mismo ASIN colapsen al canónico. Para SocialAnime
   añadimos `linkCode/th/psc/ascsubtag/smid` + path-token stripping
   `/ref=...` (ver gotcha #26 en CLAUDE.md).

Ejemplo concreto: `scripts/wikis/socialanime.py` cubre las colecciones
variant + cofanetti del MangaStore de socialanime.it (~840 items raw,
~640 después de filtros). Una corrida toma ~30-60 segundos porque son
30-40 GETs JSON, no parsing HTML.

Cuándo aplicar este patrón:
- La página tira AJAX para llenar contenido (selectores HTML devuelven 0).
- Inspeccionando el JS encontrás un endpoint que devuelve JSON sin auth.
- El endpoint pagina deterministicamente y existe un parámetro que baja
  el "todo histórico" (no solo trending del día).

Trade-off: el endpoint es interno (no documentado), si lo cambian se
rompe sin aviso. Lo mismo pasa con cualquier scraping no oficial; el
`source_health.py` audit lo detecta cuando un wiki deja de aportar items.

### Curated-guide-post (BBM pattern)

Algunos blogs comunitarios mantienen **posts-guía únicos curados
continuamente** que enumeran items con metadata estructurada (imagen,
editorial, fecha, precio, descripción del extra). El blog actualiza el
MISMO post con cada nueva entrada notable; no archiva en posts nuevos.
Para estos casos:

1. **Identificá los posts relevantes**. Suelen estar enlazados desde
   una categoría o tag (`/category/capas-variantes/`, `/tag/edicao-especial/`).
2. **Inspeccioná la estructura HTML del post**. WP themes típicos
   meten cada entry como una secuencia de gallery + título + prose +
   `<hr>` (Layout A) o `<hr>` + título + `<hr>` + prose + figures
   (Layout B). Casos extremos: chunks tardíos que agrupan VARIOS entries
   sin `<hr>` entre ellos (`scripts/wikis/blogbbm.py` lo cubre con un
   buffer `pending_imgs` que se atan al próximo título).
3. **Heurística title-driven, no `<hr>`-driven**. Detectar el `<p>`
   que es el título de cada entry (combinación de: parens-date al final,
   ficha link cubriendo el texto, volume marker, `<strong>` envolvente).
   Aplicar rejects por prefijos narrativos largos ("Em janeiro",
   "A editora", "O volume #") para no agarrar prose como título.
   Cuidado con prefijos cortos ambiguos como "no " — rompen títulos
   legítimos como "No Game No Life".
4. **URL sintética por-entry**. Usá un **query param custom**, NO
   fragment. `normalize_url_for_dedup` strippea fragments siempre →
   todos los entries de la misma ficha colapsarían a una sola fila.
   El param debe NO estar en `TRACKING_PARAMS`. Ej:
   `?bbm-entry=vol-N-<image-stem>` (ver gotcha #27 en CLAUDE.md).
5. **`signal_inject`**: como el post entero está dedicado a un tipo de
   edición (capas variantes / extras), inyectá el keyword equivalente
   en la descripción de TODOS los items del post para que
   `detect_signals` levante el signal_type correcto. Esto evita
   depender del título de cada entry para detectar el signal.

Ejemplo concreto: `scripts/wikis/blogbbm.py` parsea dos posts de
blogbbm.com (capas variantes + volúmenes especiais) con la misma
función `parse_post(html, post_meta)`. Los `BBM_POSTS` listan
`url`/`source_suffix`/`tag`/`signal_inject` por post. Agregar un post
nuevo cuesta una línea.

Cuándo aplicar este patrón:
- La fuente es un blog con curación humana (no auto-publicado de un
  retailer feed).
- El contenido está concentrado en 1-3 posts URLs que se actualizan
  continuamente.
- Cada item del post tiene metadata estructurada (al menos imagen +
  título + prose corta).

### Per-collection page (listadomanga `coleccion.php?id=N` pattern)

Algunas wikis publican **una página HTML por colección** (= una edición
concreta de una obra), con todos sus tomos y extras enumerados dentro,
en lugar de un calendario mensual o un feed JSON. Listadomanga.es es el
caso paradigmático: `coleccion.php?id=1606` es Norma Editorial Ataque a
los Titanes, `coleccion.php?id=6242` es Witch Hat Atelier Edición
Grimorio, etc. Hay ~6500 colecciones distintas.

Estructura típica del HTML:

```html
<h2>Norma Editorial</h2>
<h2>Números editados</h2>
  <table class="ventana_id1" style="width: 184px;">
    <tr><td class="cen">
      <img class="portada" src="..." alt="Berserk nº37"/>
      Berserk nº37<br/>
      224 páginas en B/N<br/>
      10,00 €<br/>
      <a href="novedades.php?mes=6&ano=2017">Junio 2017</a>
    </td></tr>
  </table>
<h2>Números editados (Ediciones Especiales)</h2>
  <table class="ventana_id1">...</table>
<h2>Números editados (Portadas alternativas)</h2>
  ...
<h2><strong>Cofres de regalo con las primeras ediciones de Berserk</strong></h2>
  <table width="920" border="0" align="center">
    <tr>
      <td width="150" style="text-align: center;">
        <img src="..."/><br/><br/>
        Berserk nº17<br/>(1ª Edición)<br/>Cofre para tomos 8 a 17<br/>fecha
      </td>
      <td width="150">...</td>
    </tr>
  </table>
<h2>Extras de Berserk (Panini)</h2>
  ...
```

**Dos layouts mutuamente excluyentes**:
- **Layout A** (productos comprables, `Números editados` y sus
  paréntesis-variantes): `table.ventana_id1` + `img.portada` con `alt` =
  título canónico.
- **Layout B** (extras/cofres/regalos): `table[width="920"]` con
  `td[width="150"]` y texto separado por `<br/>` — la primera línea es
  `<Serie> nº<N>`, la segunda es marker de edición (`(1ª Edición)` /
  `Edición Especial Limitada` / `Portada Alternativa`), el resto es
  descripción y fecha.

**Detección de página entera = edición premium**: en la cabecera hay
`<b>Formato:</b> <valor>` (NO `<strong>`). Tokens premium a matchear:
`cartoné`, `tapa dura`, `A5` (148x210 / 150x210), `Tomo doble`,
`doble sobrecubierta`, `Libro de ilustraciones`, `Kanzenban`. Cuando
matchea, los items regulares de "Números editados" reciben el signal
correspondiente sin requerir sección de extras dedicada.

**URL sintética por item**: una URL `coleccion.php?id=N` cubre N tomos
distintos. Para que `append_jsonl` no los pise, cada item genera
`coleccion.php?id=N&item=<edition_slug>-<vol>` donde `edition_slug` es
`regular` / `especial` / `alternativa` / `pack` / `grimorio` / etc.
**Determinístico** (mismo input → mismo URL) para idempotencia en
re-scrapes. El param `item` NO está en `TRACKING_PARAMS` → sobrevive
normalización (gotcha #27 generalizada).

**Vinculación extra→tomo (Fase 2 del parser)**: la sección "Extras de X"
contiene celdas Layout B que SIEMPRE empiezan con `<Serie> nº<N>` y un
marker de edición. El parser pre-construye un dict
`{(edition_kind, vol_n): item}` con los items Layout A, y para cada
celda Layout B:
1. Identifica `target_vol` y `target_edition` por el texto estructurado.
2. Si el target existe → upsert con imagen en `images[]` (carrusel,
   nuevo campo `images: [{url, local, kind}]`).
3. Si NO existe (el extra es de un tomo regular que no se listó por ser
   tomo sin qualifier) → crea el tomo nuevo con la imagen del extra y
   signal `bonus` — ahora pasa el gate `is_collectible_edition`.

Esto es lo que "abre la puerta" a tomos regulares de 1ª edición que
trajeron marcapáginas/postales/cofres y que el catálogo no captura hoy.

Ejemplo concreto: `scripts/wikis/listadomanga_collections.py`. Fase 1
implementa Layout A + Formato premium; Fase 2 (futura) agrega Layout B
y el merge extra→tomo + schema `images[]` aditivo (`image_url` /
`image_local` quedan como alias del primer cover para no romper
consumidores). Discovery por enumeración secuencial id=1..~6500.

Cuándo aplicar este patrón:
- La fuente tiene **una URL por colección** con todos los tomos y
  variantes dentro.
- Las secciones se distinguen por `<h2>` headers consistentes.
- El total de colecciones es enumerable (rango de ids conocido).
- Cada tomo tiene una identidad propia que necesita URL única
  (volumen + edición), aunque vivan todos dentro del mismo HTML.

## Recipe: Whakoom spider

Whakoom (whakoom.com) tiene **descubrimiento limitado sin login** pero
suficiente para un spider de 3 niveles:

```
/newtitles  (~415 últimas novedades, kind:html source en sources.yml)
    ↓ extract anchors /comics/{shortcode}
/comics/{X}
    ↓ extract /ediciones/{id} (la edición principal del volumen)
/ediciones/{id}
    ↓ extract OG metadata + OTRAS /ediciones/{id'} (variantes hermanas:
      portada alternativa, deluxe, exclusiva retailer)
```

Modos:
- **DIFERENCIAL** (en cada scrape regular): la source
  `ES/LatAm - Whakoom Novedades` (kind:html) procesa solo nivel 1 →
  ~1-5 items reportables nuevos por run, lightweight.
- **BOOTSTRAP/SPIDER** (one-shot):
  ```bash
  python scripts/manga_watch.py --bootstrap-wiki whakoom
  ```
  Recorre los 3 niveles BFS — ~1500 HTTP requests, ~25-40 min.
  Descubre **variantes y portadas alternativas** que `/newtitles` solo
  no expone (ej. "Spy x Family 1 Portada Alternativa Ivrea Argentina"
  se descubre vía la edición regular de Spy x Family 1).

**Rate limit (importante)**: Whakoom usa Cloudflare con bloqueo agresivo.
El módulo tiene 4 capas de protección:

1. **Headers browser-like** (Chrome 120 UA, Accept-Language es-ES, Referer)
   para parecer tráfico humano y reducir falsos positivos de Cloudflare.
2. **Sleep default 2.0s** entre requests. Subir a 3.0 si ves 429s.
3. **Backoff en 429**: 10s → 20s → 40s, max 3 retries por URL.
4. **Detección de Cloudflare challenge** (página "Just a moment...",
   `cf-chl-bypass`, etc.). Si se detecta, el spider **aborta inmediatamente**
   con `WhakoomBlocked`. Seguir presionando empeoraría el bloqueo a nivel
   de IP (afecta TODOS los dispositivos en tu red — verificado).
5. **Throttle local**: `~/.cache/manga-watch/whakoom_lastrun` impide runs
   <6h del último bootstrap. Pasá `ignore_throttle=True` (CLI: TBD)
   para saltarlo si cambió tu IP.

**Si tu IP queda bloqueada por Cloudflare**:
- Verificá abriendo `whakoom.com` en un navegador desde tu red.
- Esperá **1-2h** para que se libere.
- Si urgente, cambia de red (datos móviles) o usá una VPN distinta.

### Whakoom URL semantics — `/ediciones/` vs `/comics/` vs `/publisher/`

Whakoom modela su catálogo en tres tipos de URL, y solo UNA representa
un tomo individual. Confundirlos genera items basura.

| URL pattern | Qué representa | Cómo procesar |
|---|---|---|
| `/comics/<shortcode>/<slug>/<vol>` | UN tomo individual (Berserk Deluxe #1) | Guardar tal cual |
| `/ediciones/<id>/<slug>` | Una EDICIÓN completa (Berserk Deluxe = 14 tomos) | Expandir a N items, uno por tomo |
| `/publisher/<id>/<slug>` | Página del editor (lista sus /ediciones/) | Expandir a /ediciones/ → tomos (2 niveles) |

Las funciones de expansión están en `scripts/wikis/whakoom.py`:
- `expand_whakoom_edition(url)` → N candidates (uno por /comics/ vol).
  Maneja **multi-vol** (lee `/todos` para volúmenes 12+) y **one-shot**
  (extrae el comic_url enmascarado en `/login?ReturnUrl=`).
- `expand_whakoom_publisher_url(url)` → llama `extract_ediciones_urls`
  + `expand_whakoom_edition` por cada edición.

Tres puntos de ingesta están protegidos contra `/ediciones/` y
`/publisher/` accidentales:
1. **`search_discovery.py`**: intercepta ambas y las expande antes de
   guardarlas.
2. **`wikis/whakoom.py` spider Fase 3**: cada `/ediciones/` descubierto
   se expande inmediatamente.
3. **Fuente regular `Whakoom Novedades`** en sources.yml: su
   `item_selector: "a[href^='/comics/']"` ya emite solo URLs de tomo —
   sin riesgo.

Para limpiar legacy en items.jsonl:
```bash
.venv/bin/python scripts/retrofit/expand_whakoom_ediciones.py --dry-run
.venv/bin/python scripts/retrofit/expand_whakoom_ediciones.py        # apply
```

### Whakoom requiere `Accept-Encoding: gzip, deflate` SIN `br`

Whakoom sirve Brotli si lo aceptás, y `requests` no decodifica Brotli
nativamente (sin la lib `brotli` instalada) — el body llega como bytes
binarios. El `_ua_session()` de `wikis/whakoom.py` **excluye `br`
explícitamente**. Si volvés a agregarlo, también agregá `brotli` a
`requirements.txt`.

Detección de Cloudflare challenge: usar markers específicos
(`cf-chl-bypass`, `__cf_chl_rt_tk`, path `/cdn-cgi/challenge-platform/h/`).
NO usar `challenge-platform` solo — matchea el JSD bot-detection script
que CF inyecta en TODAS las páginas protegidas, generando falsos
positivos en respuestas legítimas.

## Recipe: Shopify variants multi-tomo

Algunos sitios Shopify (Dark Horse Direct es el caso conocido) modelan
una serie completa como UN solo producto Shopify con un `<select>` de
variants — "Volume 1 / Volume 2 / Volume 3 / ...". Cada variant tiene
su propio `variant_id`, `sku`, `price` y deep-link via `?variant=<id>`.

Estructuralmente equivalente a Whakoom `/ediciones/`: el catálogo es
por tomo, así que estos productos hay que **expandirlos** en N items.

Parser: `scripts/shopify_variants.py`:
- `extract_shopify_variants(html)`: extrae variants desde JSON embebido
  o `<select data-variant-id>`.
- `is_volume_variants(variants)`: heurística — requiere al menos un
  variant con keyword de volumen ("Volume N", "Tome N", "#N", "第N巻",
  etc.). Single-variant ("Default Title") devuelve False.
- `build_variant_url(parent, id)`: construye `?variant=<id>` y limpia
  tracking de Shopify (`_pos`, `_sid`, `_ss`).

Retrofit: `scripts/retrofit/expand_index_pages.py` aplica la lógica
a Dark Horse Direct + cualquier futuro Shopify multi-tomo. La detección
se restringe a dominios conocidos (hoy solo `darkhorsedirect.com`) —
otros Shopify (mangadreams.it, milkyway, funside.it) no usan variants
para volúmenes y NO se chequean.

## Recipe: source de referencia (Mangavariant pattern)

**Mangavariant** (`mangavariant.com`) es una **base de datos curada**
de manga variants en 13 países. Aporta ~2700 items (~50% del corpus
actual) con metadata muy rica (serie, país, publisher, año, rarity,
tags, cover) **pero SIN precio ni URL de tienda** — son URLs de
referencia, no listings de retailer.

Este tipo de fuente define una categoría aparte: **"sources de
referencia"**. Reglas que se derivan:

1. **Mangavariant SIEMPRE pasa `is_manga=true`**. Política del owner:
   "todo lo que venga de mangavariant tomalo como válido siempre".
   El skill `/standardize-catalog` respeta esta regla — nunca mueve
   items Mangavariant a la blacklist.
2. **NO filtrar por falta de price / stock_type**. Una card sin precio
   es válida; el dashboard la muestra igual.
3. **NO eliminar wikis/bases de referencia "para limpiar" el corpus**.
   Son fuentes de primera clase.
4. **Cuando un item de referencia matchea cluster_key con uno de
   retailer**, se consolidan automáticamente; el de referencia suele
   quedar como card canónica y los retailers aparecen como "dónde
   comprar".
5. **Enrichment**, si se implementa en el futuro, es una pasada
   separada (`scripts/retrofit/enrich_references.py` — diferido).
   NO un filtro upstream que descarte items de referencia.

Patrón técnico (`scripts/wikis/mangavariant.py`):
- Sitemap Yoast → URLs de variants → detail parser por cada URL.
- Es un bootstrap único (~2700 requests, ~15-30 min). No corre en cada
  scrape regular — la source en sources.yml tiene `max_pages: 1` para
  el delta diario.

Otros candidates futuros para "source de referencia":
- Wikis de fandom (MyAnimeList, AniList, BakaUpdates).
- Catálogos editoriales sin e-commerce (editorial homepages).

## Recipe: search discovery (Gemini API + DuckDuckGo)

`scripts/retrofit/search_discovery.py` cubre el gap de discovery que
ningún source directo cubre: items en sitios que bloquean scraping
directo (Fnac → 403), items que sólo Google indexa profundo
(Whakoom `/ediciones/{N}`), y anuncios en social.

### Setup Gemini API (free, sin tarjeta)

El viejo Custom Search JSON API quedó cerrado a nuevos clientes en 2025.
Google lo reemplazó por la tool "Grounding with Google Search" del
Gemini API — misma calidad de resultados (index de Google directo),
free tier mayor (500 RPD), sin tarjeta.

1. Andate a https://aistudio.google.com — NO Google Cloud Console.
2. Click **"Get API key"** arriba a la derecha.
3. **"Create API key in new project"** → te devuelve algo tipo `AIzaSy...`.
4. Pegala en `.env`:
   ```bash
   GEMINI_API_KEY=AIzaSy...
   ```

Quota free tier 2026: Gemini 2.5 Flash con grounding incluido,
500 RPD compartido + 15 RPM. Eso son ~10 corridas del script al día
(con 50 queries cada una). Más que suficiente para uso personal.

Si te quedás corto, podés cambiar al modelo Gemini 3.x (más quota:
5,000 prompts/mes free) editando `GEMINI_MODEL` en `.env`.

### Setup Tavily (fallback recommended, free)

Cuando Gemini agota su quota (típico ~10-15 prompts/día), Tavily entra
como fallback automático. Free tier: 1,000 búsquedas/mes, sin tarjeta.

1. Andate a https://tavily.com → Sign up.
2. Dashboard → API key tipo `tvly-...`.
3. Pegala en `.env`:
   ```bash
   TAVILY_API_KEY=tvly-...
   ```

Tavily usa un index propio (no Google), por lo que NO ve Whakoom
profundo. Pero cubre Reddit, Fnac, Casa del Libro, blogs, etc.
Ideal para queries `site:reddit.com`, `site:fnac.es`, lore-words.

### Setup DuckDuckGo (no requiere API)

Funciona out-of-the-box. Solo necesita conexión. NO sirve para
whakoom (DDG usa Bing+propio y ninguno indexa /ediciones/ profundo).
Útil como último fallback para Reddit, FB público, blogs.

### Cómo correr

```bash
# Run completo (todas las queries de data/search_queries.yml)
.venv/bin/python scripts/retrofit/search_discovery.py

# Solo DDG (si Gemini no está configurado o quota agotada)
.venv/bin/python scripts/retrofit/search_discovery.py --engines ddg

# Solo Gemini (forzar; alias "google" también acepta por compat)
.venv/bin/python scripts/retrofit/search_discovery.py --engines gemini

# Dry-run: lista queries sin ejecutar
.venv/bin/python scripts/retrofit/search_discovery.py --dry-run

# Limitar a las primeras N queries (test)
.venv/bin/python scripts/retrofit/search_discovery.py --limit 5
```

### Cómo añadir queries

Editar `data/search_queries.yml`:

```yaml
queries:
  # Sólo Gemini (sitios que DDG no indexa bien)
  - q: 'whakoom "tu serie favorita" "edición coleccionista"'
    engines: [gemini]
  # Gemini preferred, DDG fallback
  - q: 'site:fnac.es "edición limitada" "tu serie"'
    engines: [gemini, ddg]
  # DDG preferred (Reddit/social)
  - q: 'site:reddit.com/r/manga "limited edition" 2026'
    engines: [ddg, gemini]
```

NOTA: el script acepta `google` como alias de `gemini` (yamls viejos
siguen funcionando).

### Rate limits y costes

- **Gemini 2.5 Flash**: 500 RPD (compartido) + 15 RPM en free tier 2026.
  Eso son ~10 corridas/día con 50 queries cada una. Sleep default 4.5s
  entre llamadas para respetar el RPM. Sin tarjeta de crédito.
- **DDG**: ~10-50 queries/min. Si saturás, devuelve HTTP 202 (soft rate-limit)
  y esperás ~1h. El script registra el error claramente.
- **Por query**: ~5-15 URLs candidatas (Gemini decide cuánto buscar) →
  ~3-5 nuevas tras dedup+gates → ~30-80 items reales por run completo.

## Recipe: when a source starts producing garbage

If after a re-scrape you see lots of new junk from one specific source:

1. **Look at 5-10 example titles** to spot the pattern. Use
   `grep -i "<source-name>" data/items.jsonl | head` or run
   `python scripts/retrofit/filter_non_manga.py --dry-run` and read the
   sample.

2. **Decide:** is the pattern site-wide non-manga (then mark `purity:
   mixed`) or is it a specific kind of product (then add a HARD/SOFT
   regex)?

3. **For new HARD/SOFT patterns:**
   - Add the regex to `_NON_MANGA_HARD` or `_NON_MANGA_SOFT` in
     `manga_watch.py`.
   - Write a unit test with the exact title.
   - Run `pytest` (should be green).
   - Run `scripts/retrofit/filter_non_manga.py` to clean historic data.

4. **For new STRONG patterns** (book formats that we want to KEEP in
   mixed sources):
   - Add to `_STRONG_MANGA_PATTERNS`.
   - Add a test with a borderline case (e.g. a Hellsing Deluxe Hardcover
     that should pass in Dark Horse Direct mixed source).
   - Run `pytest` and `filter_non_manga.py --dry-run` to ensure you
     didn't accidentally re-include too much.

## Recipe: extend the comics blacklist

`data/comics_blacklist.yml` rejects items that are clearly Western
comics (Marvel/DC franchises, BD franco-belga, graphic novels) — but
**only** in sources flagged `purity: "mixed"` (Panini ES/MX, Dark Horse
Direct). Sources that are 100% manga (Norma, Ivrea, Glénat manga) ignore
the blacklist completely, so manga series can never be falsely rejected.

Three fields, each optional:

```yaml
publishers:               # exact match against item.publisher
  - "Marvel"
  - "DC Comics"
franchise_keywords:       # case-insensitive substring match in title
  - "Spider-Man"
  - "Batman"
  - "Asterix"
format_keywords:          # word-boundary match (case-insensitive)
  - "graphic novel"
  - "novela gráfica"
  - "Facsímil"
```

When to extend:
- A new mixed source starts leaking specific cómic series → add to
  `franchise_keywords`.
- A publisher that *only* publishes Western comics shows up in a mixed
  source → add to `publishers` (Marvel/DC are the safe defaults; do NOT
  add Panini/Norma/Planeta — they publish both).
- A new cómic-exclusive format keyword surfaces → add to
  `format_keywords`. Don't add "comic" or "manga"-related words.

Edits to this file take effect at the next run (loaded lazily, cached
per-process).

## What NOT to add as a source

- **Aggregators that only link out without product metadata** (e.g.
  manganews.com news index — useful for spotting new products but
  produces shallow Candidates).
- **Marketplaces with too much noise** (general Amazon, eBay). Most
  results are imports / used books / non-manga.
- **Social media feeds without API access** (Twitter announcements,
  Instagram posts). Hard to scrape and don't add reliable structured
  data.

## Country / language labels

Stick to existing values for consistency in the web UI filters:

| Country (Spanish) | Language (Spanish) |
|---|---|
| Argentina | Español |
| España | Español |
| México | Español |
| España / LatAm | Español |
| Francia | Francés |
| Italia | Italiano |
| Japón | Japonés |
| Japón / Global | Japonés |
| Estados Unidos | Inglés |

If you genuinely need a new country, add it but mention in
`docs/SOURCES.md` and update the documentation table here.
