# Known gotchas

> Documento de referencia de PandaWatch, cargado **bajo demanda** desde
> [CLAUDE.md](../../CLAUDE.md). Leelo cuando vayas a trabajar en este tema.

## The 142 known gotchas

Cada gotcha es la regla durable + la referencia de código. El detalle histórico
(cómo se descubrió, conteos retroactivos, nombres de tests) está en git.

1. **Mojibake FR.** Glénat/Pika devuelven UTF-8 decodificado como cp1252.
   `clean_title()::_fix_mojibake()` lo repara PRIMERO; no metas regex-cleaning antes.
2. **Manga-Sanctuary URL drift.** Releases futuros redirigen a productos no
   relacionados. `manga_sanctuary.py::_title_matches_page()` valida — no lo desactives.
3. **Otaku Calendar: el mes va por PATH, no por query string (2026-07-07).** `?month=
   YYYY-M` se armaba como query string, pero el servidor lo IGNORA y sirve siempre el
   mes por defecto — bootstrapear un rango daba el mismo HTML repetido (duplicados).
   `fetch_calendar_month()` ahora arma la URL como path-segment (`/Calendar/{year}/
   {month}`), que el servidor SÍ honra (misma estructura de HTML: `div.dateListingContainer`
   + `/Release/<id>/<slug>`, el parser no cambió). El backfill histórico mes-a-mes es
   viable ahora — antes el parser sólo servía para chequeo del mes actual.
4. **Tiendanube vs Shopify.** Tiendanube: `[data-product-id]` + `/productos/`.
   Shopify: `li.grid__item`/`[data-product-card]` + `/products/`.
5. **Kamite** parece Shopify pero es Tiendanube (catálogo en `/productos/`).
6. **Placeholders de imagen son muchos.** Ver `IMAGE_URL_BAD_PATTERNS` (placeholders/,
   visuel_defaut, data:image, `/assets/images/common/`, cualquier `.svg`, etc.). El
   extractor devuelve `""` si todo es placeholder (deja backfill re-fetchear).
   Lazy `<img>`: portada real en `data-src`/`data-lazy-src`; `_img_to_url` saltea
   valores `data:` URI. `IMAGE_URL_GOOD_PATTERNS` puede llevar hosts (ej. e-hon.ne.jp).
7. **`source_purity` se propaga** a los hijos search-template vía `_expand_search_template()`.
8. **Wikis bypassean el source loop.** Se activan con `--bootstrap-wiki <name>`; hacen
   su propio `is_likely_manga()`. No leen config de `sources.yml`.
9. **Word-boundary, no substring, para signals.** `detect_signals`/`derive_product_type`
   usan `_phrase_pattern()` (boundary ASCII, substring CJK). "poster"≠"posters". Usalo
   para cualquier detector nuevo.
10. **`signal_types` salen SÓLO del item** (`title + description`). NUNCA metas source
    name/publisher/tags/keywords del search-template (contaminó todo con `box_set` una vez).
    El boost por source-class lo aplica `score_candidate` aparte.
11. **Comics blacklist con word-boundary + bypass "manga".** `is_comic_not_manga`:
    publisher Marvel/DC + franchise/format keywords; si el title contiene "manga" se
    bypassea entero (Batmanga sobrevive). Extender en `comics_blacklist.yml`; no agregar
    publishers que también publican manga.
12. **Playwright sync NO es thread-safe** → único thread `playwright-worker` + queue es
    la única ruta segura (un `js_lock` no alcanza: el greenlet queda bound al thread
    original). Los workers HTTP llaman `fetch_with_playwright()` que despacha a
    `_PLAYWRIGHT_QUEUE`. `close_playwright()` termina vía sentinel (idempotente, re-init OK).
13. **Wayback trata 403/429 como VIVO.** `wayback_recover.py` sólo recupera 404/410;
    403/429/5xx son anti-bot (la página vive). No relajes sin ver la distribución real (`--check`).
14. **Whakoom `/ediciones/` = colección, no tomo.** Nunca guardar una `/ediciones/` como
    item: expandir vía `expand_whakoom_edition()` → N `/comics/.../<vol>` (multi-vol usa
    `/todos`; one-shots vía `/login?ReturnUrl=`). Idem `/publisher/` →
    `expand_whakoom_publisher_url` (2 niveles). Retrofits: `expand_whakoom_ediciones.py`,
    `expand_index_pages.py`.
15. **Whakoom: `Accept-Encoding: gzip, deflate` SIN `br`.** `requests` no decodifica
    Brotli → `response.text` queda binario y el parser ve 0 tomos en silencio. Si re-agregás
    `br`, agregá `brotli` a requirements. (CF challenge markers reales: `cf-chl-bypass`,
    `__cf_chl_rt_tk`, `/cdn-cgi/challenge-platform/h/` — NO el script JSD legítimo.)
16. **Shopify variants multi-tomo: 1 producto = N SKUs.** Dark Horse Direct modela una
    serie como un `og:type=product` con `<select>` de N volúmenes. Hay que expandirlos.
    Helpers en `shopify_variants.py` (`extract_shopify_variants`, `is_volume_variants`,
    `build_variant_url`). Restringido a dominios conocidos (hoy `darkhorsedirect.com`).
17. **`url_is_useful` (search_discovery) blacklistea índices** que nunca son productos
    (`/lists/`, `/profile/`, `/blogs/news/`, `/collections/X` sin `/products/`, social,
    YouTube…). Whakoom `/publisher/` queda FUERA (sí se expande).
18. **Omnibus / "X en X" pelados NO califican** como coleccionables (decisión del owner).
    `omnibus` no está en `COLLECTIBLE_EDITION_SIGNAL_TYPES`; un omnibus premium pasa por
    otro qualifier (hardcover/deluxe/box_set/...). `_GENERIC_X_EDITION_PATTERN` excluye
    "Omnibus" para que no dispare `lore_edition`.
19. **Rakuten `?l-id=` = tracking de slot** (misma SKU, URLs distintas). `l-id`/`l_id` en
    `TRACKING_PARAMS` de `normalize_url_for_dedup`. Agregá ahí cualquier tracking param nuevo.
20. **Una obra tiene N nombres por mercado/idioma** → todos colapsan al canónico vía
    `data/series_aliases.yml` (`canonical_series_key()` en `candidate_to_json`). Match
    EXACTO sobre series_key/display normalizados (NO substring en title). Sin match → input
    intacto. Mantenimiento: scrape loguea series nuevas a `unmapped_series.jsonl`; el skill
    `/watch-enrich-series-aliases` cura el backlog (Anilist API). Al agregar a mano: Anilist →
    curar aliases (quitar transliteraciones no-target y synonyms ambiguos).
21. **Doble pasada: scraper asigna crudo, skill corrige.** Pasada 1 (`derive_series_metadata`
    en el scraper): heurístico regex → series_key/edition_key/volume; devuelve EMPTY si el
    resultado es dudoso (series_key <3 chars, todo dígitos, termina en `-N` sin volumen).
    Deja `standardized_at` ausente. Pasada 2 (`/watch-standardize-catalog`, manual): re-deriva desde
    cero con LLM, mueve non-manga a blacklist, dedupea, setea `standardized_at`. Items con el
    flag se saltean (`--force-all` para re-procesar todo). Tras un scrape: standardize →
    enrich-series-aliases.
22. **`title` = canónico internacional; `title_original` = el scrape (post-clean).** Card
    muestra `title`; modal muestra `title_original` si difiere. El search del dashboard indexa
    AMBOS + `series_display`. El dedup del pipeline es por keys `(series_key, edition_key,
    volume)`, no por texto. `title_original` se setea siempre en el scraper; el skill lo
    backupea antes de sobrescribir `title`.
23. **`append_jsonl` preserva campos curados** en items con `standardized_at`: hace MERGE
    (no replace), refrescando sólo los volátiles scrapeados. Lista en `_CURATED_FIELDS`. Para
    re-procesar tras cambiar reglas de estandarización: `--force-all` (re-scrapear no alcanza).
24. **`_GENERIC_X_EDITION_PATTERN` excluye genéricos en ES/IT/FR, no sólo EN.** "Nueva
    Edición" (= reimpresión) disparaba `lore_edition` y colaba tomos normales. La stoplist
    incluye `Nueva|Nuova|Nouvelle|Primera|...`. Nota: `signal_types` se deriva de
    `title_original` (estable), no se vuelve caduco al re-titular; sólo `rescore.py` lo
    refresca cuando cambia el código de detectores.
25. **El `local` de la portada es sticky en `append_jsonl`** vía el union-merge de `images[]`
    (dedup por `(kind, url)` que preserva primero el entry viejo): si la row nueva trae
    `images[0]` con la misma url pero sin `local`, conserva el `local` de la existente.
    Protege el espejo de un re-scrape con `--skip-image-download` o fallo de red. (Antes esto
    era un bloque aparte sobre el campo top-level `image_local`, eliminado el 2026-06-09 al
    pasar la portada a `images[0]`; ver docs/reference/images.md.)
26. **Amazon affiliate canonicalization** (extiende #19): query params (`tag`, `linkCode`,
    `th`, `psc`, `ascsubtag`, `smid`, `pf_rd_*`, `content-id`) en `TRACKING_PARAMS`; + el path
    token `/ref=...` que `normalize_url_for_dedup` strippea SÓLO cuando el host es `amazon.*`.
27. **URLs sintéticas por-entry: usar query param, NO fragment.** `normalize_url_for_dedup`
    strippea fragments → entries colapsan. Wikis que emiten N items desde una URL base usan un
    query param custom que no está en `TRACKING_PARAMS` (`?bbm-entry=`, `?item=`).
28. **booksprivilege: decodificar `errors='replace'`.** El body es UTF-8 limpio pero los
    banners ad (A8.net) inyectan bytes cp932 crudos que rompen `decode('utf-8', strict)`. Usar
    `resp.content.decode('utf-8', errors='replace')`. Mismo patrón para JP/CN con mojibake mixto.
29. **listadomanga `Formato: ... en cofre` → UN box-level item, descartar tomos numerados.**
    `_is_box_format()` detecta `\ben\s+(?:cofre|estuche)\b`. Emite 1 Candidate
    `"<título> — Cofre"` (sufijo necesario para que `detect_signals` capte `box_set`), URL
    sintética `?item=box-0-<hash>`, `images[]` = [cover del cofre, cada tomo interno como
    kind=extra "Tomo N"]. Layout B extras se appendean al mismo carrusel.
30. **sumikko: el `type-tag` describe el EXTRA, no el producto** → NO filtrar por tipo
    (`accept_types=frozenset()` = aceptar todo; el catálogo `/limited-item/` está curado a
    mano, todo es manga limitado). Items BL/R18 usan `<img class="touch18">`; el parser busca
    cualquier `<img>` y prefiere `data-src`.
31. **Multi-imagen: acotar al scope del producto + filtro de directorio padre EXACTO — y,
    cuando eso no alcanza, detección ESTRUCTURAL de grilla de relacionados (2026-07-07).**
    `_find_product_scope(soup)` restringe los selectores de gallery al subtree del producto;
    luego se descartan las URLs gallery cuyo **directorio padre no es exactamente igual** al
    de la cover (≥2 outliers = contaminación real). Comparación por dir exacto, NO substring
    (Star Comics sirve "otros volúmenes" en un subdirectorio del folder de la cover). Cap 6
    imágenes. Wikis con URLs sintéticas (`?item=`, `?bbm-entry=`) los SKIPEA
    `backfill_metadata.py --only images` (set `SYNTHETIC_URL_MARKERS`) porque re-fetchear
    devuelve la página compartida. **El filtro de directorio NO alcanza cuando la cover
    PROPIA del producto también vive en el mismo subdir que los relacionados** (Star Comics:
    tanto la cover real como los thumbnails de "ti potrebbe interessare" cuelgan de
    `/files/immagini/fumetti-cover/thumbnail/`) — no queda señal de path que los separe. Fix:
    `_related_grid_card_ids()` detecta la grilla por FORMA, no por ruta — ≥3 product-cards
    dentro del scope que enlazan (`<a href>`) a ≥3 páginas de producto DISTINTAS (excluyendo
    anclas a archivos de imagen, que son lightbox/zoom de la propia galería) se marcan como
    grilla de relacionados y `_node_in_grid()` las excluye del harvest de galería. Una galería
    legítima (front/back/lomo del mismo producto) no enlaza a N páginas de producto distintas,
    así que nunca dispara el detector. El purge de este bug limpió 29 entradas contaminadas
    del corpus (ver gotcha #112 y `docs/reference/images.md` → Purga). **False-positive
    INVERSO (M6, Fable 2026-07-08):** cuando la cover vive en OTRO directorio que la galería
    (Shopify moderno sirve la cover en `/s/products/` y las vistas en `/s/files/`), el filtro
    de dir-exacto descartaba TODA la galería legítima porque ninguna compartía dir con la
    cover. Fix en el paso 6 de `_extract_images_from_detail_soup`: si NINGUNA gallery comparte
    dir con la cover pero hay un dir MAYORITARIO entre las gallery (≥2 imgs y ≥2/3), se usa ESE
    como ancla en vez de la cover. Ver gotcha #136.
32. **`flush_source_candidates()` = escritura incremental** tras CADA fuente (no acumular todo
    para un único write final → kill mid-run perdía todo). Aplica el gate, no actualiza
    `state` (eso lo hace `process_state()` al final). Idempotente con el write final enriquecido.
    Usa key `"url:<normalized_url>"` (mismo formato que `candidate_key()`).
33. **Shell: timeouts portables en subprocesos de wiki** (`_run_timed <secs> <cmd>` en
    scrape_delta/full: `timeout` → `gtimeout` → sin timeout). Un wiki colgado bloqueaba todo.
    Timeouts per-wiki definidos en cada script (livianos ~300s, AnimeClick full hasta 4h).
    Timeout → exit 124, el pipeline sigue; lo escrito por #32 se preserva.
34. **`serve.py` es threaded → toda escritura a `items.jsonl` bajo `@_serialized`** (lock
    global). Los 6 endpoints mutadores hacen read-modify-write del archivo entero; sin
    serializar la sección load→modify→write completa, requests concurrentes se pisan. REGLA:
    endpoint nuevo que reescriba items.jsonl → decoralo `@_serialized` (no funciones que se
    llamen entre sí: Lock no reentrante).
35. **Productos DIGITALES se filtran** (PandaWatch cataloga ediciones FÍSICAS).
    `is_digital_only_url()` chequea `_DIGITAL_ONLY_URL_PATTERNS` (hoy `honto.jp/ebook/`) por
    host+path, no por substring. Otro retailer que mezcle digital → agregar su patrón.
36. **"画集付き"/"イラスト集付き特装版" = artbook INCLUIDO como bonus, NO el producto** (el item
    es el tomo). Fix en DOS funciones que deben coincidir: `detect_signals` demuele
    artbook→`bonus` si sólo se detectó por adjunto (`_ARTBOOK_BONUS_ATTACH_RE`: 画集/イラスト集
    seguido en ≤8 chars de 付/つき/同梱/付属) y las frases ⊆ `_ARTBOOK_BOOKLET_PHRASES`;
    `derive_product_type` saltea ptype `artbook`. Un artbook genuino (画集 standalone sin 付き)
    NO se demuele. Mismo criterio para fanbook-tomo.
37. **Prefijos de botón "leer más" en `description`.** Fuentes como FR - Meian incluyen
    el label del CTA ("EN SAVOIR PLUS", "MÁS INFORMACIÓN", "APRENDE MÁS"…) en el campo
    `description` del JSON-LD porque el nodo que el scraper captura engloba el wrapper
    completo del producto. Fix en DOS sitios: `extract_schema_org_product()` aplica
    `clean_description()` al asignar `result["description"]`; `_candidate_from_card()`
    aplica `clean_description()` al texto de la card. `DESCRIPTION_JUNK_PREFIXES` en
    `manga_watch.py` lista todos los patrones conocidos (FR, ES, EN, DE, IT). Retrofit
    `scripts/retrofit/clean_descriptions.py` limpia items existentes.
38. **listadomanga: la edición premium suele estar en el TÍTULO o en "en preparación", no en el Formato.**
    Tres misses reales arreglados (P0, 2026-06-06) en `listadomanga_collections.py`:
    (a) **Edición por título** — `EDITION_TITLE_RULES` / `_detect_edition_title_signals()` fuerzan
    captura de TODOS los tomos cuando el título trae `Edición Integral|Coleccionista|Kanzenban|
    Maximum|Master/Eternal/Black Edition|Deluxe|de Lujo|Aniversario` aunque el Formato sea rústica
    (caso AoT Integral id=5639: rústica 177×266 → daba 0, ahora 34). Conservador: `Nueva Edición`/
    `New Edition` NO cuentan (re-impresión estándar). (b) **"Números en preparación (Ediciones
    Especiales/Limitadas/Portadas alternativas)"** ya NO se descarta: se clasifica igual que su
    contraparte "editados" y el item lleva tag `status:upcoming` (descubrimiento temprano; el
    `cluster_key` no cambia → upsert cuando pasa a "editados", no duplica). El "en preparación"
    regular sigue gateado por premium (Berserk Master Edition id=6325: tomos cartoné en preparación
    → daba 0, ahora 3). (c) **Extras huérfanos** — `_merge_extras_into_items` ahora crea item
    destino también para `especial/limitada/alternativa` (no solo `regular`) cuando el tomo no está
    en Layout A. "Números no editados" / "Edición Revisada" siguen en DISCARD.
39. **listadomanga: portadas capadas a ~150 px de alto — NO existe alta resolución on-site.**
    Verificado en colecciones de 2012 a 2026 (todas ≈100×150). `static.listadomanga.com` guarda
    UN solo archivo por imagen (namespace plano `/<md5>.jpg|png`), sin sufijos de tamaño, sin
    `srcset`, sin og:image, sin página por-volumen. La única vía a alta resolución es externa
    (skill `watch-search-covers`, Yandex reverse-image). No reimplementar búsqueda on-site.
    **Dedup del thumbnail vs la cover hi-res**: cuando un item junta el thumbnail ~96×150 de
    listadomanga + la portada full (de otra fuente / search-covers), el aHash del thumb degradado
    difiere 7–14 bits de la full (>6, el umbral estricto) → `dedup_carousel_images.py` NO lo
    pescaba (caso real cole=52, hamming 7). Fix: umbral Hamming relajado a ≤14 SOLO para pares
    thumbnail↔full (uno ≤170px, el otro ≥2× más grande, aspect ratio ±6%) — inequívocamente la
    misma foto reescalada. Pares de tamaño comparable mantienen el umbral estricto ≤6 (no unir
    front/back de cofres ni variantes).
40. **listadomanga: la censura de portadas adultas es 100% client-side → el scraper recibe la URL real.**
    Mecanismo: cookie `CookieNSFW` + variable JS `imagenPortadaCensurada` (placeholder
    `08a02c…png`). El HTML del servidor SIEMPRE trae el hash real de la portada (verificado en
    títulos eróticos: el placeholder nunca aparece en `<img src>`, solo en la var JS). El scraper
    requests/BS4 (sin JS) no se ve afectado. **MATIZ (2026-06-07): la censura NO siempre es
    client-side.** Para ALGUNAS ediciones adultas/sin cover real, listadomanga sirve el placeholder
    `08a02c…png` directo en el `<img class="portada" src>` server-side (sin la cookie `CookieNSFW`),
    y setear la cookie NO lo revela (probado). El parser detecta ese hash (`CENSORED_COVER_HASH`) y
    vacía `image_url` — el item se captura igual (es válido) pero sin portada → entra al worklist de
    search-covers. (Eran 86 items que un retrofit de limpieza había dejado sin imagen.)
41. **listadomanga-collections: idempotencia y observabilidad del parser.** (a) **Volumen NO es
    campo de `Candidate`** — se deriva del título (`_extract_volume("Berserk nº1")=1`) al construir
    el `cluster_key` (decisión #4). No agregar `Candidate.volume`. (b) **Idempotencia ante re-subida
    de portada**: el `item=<edition>-<vol>-<hash_img>` sintético cambia si listadomanga re-sube la
    portada (hash nuevo), PERO el fuzzy `cluster_key` (`lang|series|vol|tier|publisher`) fusiona el
    item viejo y el nuevo → sin duplicado visible. Residual conocido: items SIN volumen (box/packs)
    caen a clave `url:` y NO se fusionan ante re-subida (raro; no se cambió el esquema de URL para
    evitar churn del corpus). (c) **`ZERO_YIELD_LOG`** (P4): el parser registra colecciones con
    indicación premium (formato/título) o secciones de extras que emitieron 0 items → posibles
    misses (la señal que habría delatado Berserk Master pre-P0-B). Se vuelca al final del bootstrap
    y a `logs/listadomanga_zero_yield.txt`, junto a `UNKNOWN_H2_LOG`. (d) **Las tablas de item usan
    `ventana_id<N>`, NO solo `ventana_id1`** — el número es un skin CSS por tipo: id1 = manga
    japonés B/N, id3 = manhwa a color (Sweet Home, Lector Omnisciente), id9 = packs/especiales
    (His Little Amber). El parser matchea cualquier `ventana_id\d+` a width 184px
    (`ITEM_TABLE_CLASS_RE`); antes solo id1 → manhwa y varias especiales daban 0 items (detectado
    por ZERO_YIELD en el dry-run). (e) **NO existe rule "A5-tamaño → kanzenban"** (se eliminó 2026-06-06,
    decisión del owner): el formato A5 (148x210) es el ESTÁNDAR de muchas series clásicas en España
    (Detective Conan, Monster, Dr. Slump, Rumiko Takahashi…), no señal de kanzenban. El run real
    sobre ids 1-100 capturaba 254/266 tomos estándar como falso `premium_format`. El kanzenban
    GENUINO se detecta por título "(Kanzenban)" (P0-A), formato "doble sobrecubierta" o literal
    "kanzenban". Las ediciones A5 estándar (incl. Vinland) NO se capturan — no son especiales.
    (f) **La sección regular ("Números editados") solo emite `ventana_id1`** salvo que la colección
    sea premium por TÍTULO/tipo (`title_premium`: Integral/Maximum/Kanzenban/fanbook/…). Así las
    ediciones regionales premium en otros layouts (Berserk Maximum / Ranma Kanzenban en catalán,
    `ventana_id2`) se capturan, pero el manga/manhwa/revista regular en id2/id3/id12 no inunda. Las
    secciones ESPECIALES aceptan cualquier layout siempre.
    (g) **Título en DOS líneas sin número** (`_parse_item_table`): artbooks cuyo nombre va en 2
    líneas sin nº ("CLAMP Art-book" + "North Side") perdían el subtítulo (el parser tomaba solo la
    1ª línea). Dos colecciones distintas (North/South Side) quedaban con título idéntico → la cover
    search las confundía y ponía la portada cruzada. Fix: la 2da línea se une al título si aparece en
    el `alt` canónico de la `img.portada` (que sí trae el título completo). Una descripción real
    ("Edición Especial con logo dorado") NO está en el alt → sigue siendo description.
42. **listadomanga: cada `/coleccion?id=N` es UNA edición — REGLA DURA del owner (2026-06-06).**
    La MISMA obra en `/coleccion` distintos = ediciones DISTINTAS → NUNCA el mismo `edition_key`
    (una obra tiene varias ediciones: tankobon, kanzenban, integral, artbook…). El standardize (LLM)
    las fusionaba: ej. FMA `edition_key=fullmetal-alchemist-norma-special` mezclaba cole=50 (tomos
    regulares con cofre de 1ª ed.) + cole=524 (Libro de Ilustraciones). Enforcement DETERMINÍSTICO en
    DOS sitios que deben coincidir: el post-paso del skill `watch-standardize-catalog` y el retrofit
    `scripts/retrofit/fix_listadomanga_editions.py`. Reglas: (a) si un `edition_key` abarca >1 id de
    colección → split por id (`…-c{id}`). (b) tomos `regular` con `from_extras`/cofre mal slugueados
    como special/limited → `regular` (el cofre es bonus, NO una edición). (c) colección cuyo TÍTULO es
    un artbook (Libro de Ilustraciones / "The Art of" / Illustrations) → `artbook` aunque esté
    numerada. Conservador: NO re-derivar a ciegas (product_type y títulos son ruidosos) — solo
    corregir estos patrones, el resto del slug se conserva.
    **Enforcement también en el `cluster_key`** (`derive_cluster_key`, tier 2.5): items RAW de
    listadomanga (sin edition_key) se clavean `lmc:{coleccion}:{kind}:{vol}` — NO fuzzy — para que
    el dedup NUNCA fusione colecciones distintas (el fuzzy las uniría por mismo series+vol+tier).
    Como bonus, ignora el hash del `item=` → idempotente ante re-subida de portada. **Un-merge:** los
    items que un consolidate histórico ya fusionó entre colecciones (cuando compartían el edition_key
    erróneo) se separan con `scripts/retrofit/unmerge_listadomanga_editions.py` — cada `source[]`
    retiene su propia cover/fecha, y las imágenes del carrusel se atribuyen por archivo local /
    hash del disambiguador (el cofre de 1ª ed. vuelve a su tomo regular, el artbook queda limpio).
    **Colisión de título de display**: dos ediciones distintas (publishers/idiomas/años distintos) de
    la misma obra pueden quedar con el MISMO `title` aunque su `edition_key` las separe (ej. "Saint
    Seiya Integral 1" en Glénat y Planeta; "Death Note Black Edition 3" 2013 y 2024). Se desambigua
    apendando editorial → idioma → año → coleccion (`fix_listadomanga_title_collisions.py` + el
    post-paso del skill). No afecta el grouping (es solo display).

43. **`_normalize_series_name` dejaba el marcador `nº`/`n°` como residuo `-no` en el series_key
    (2026-06-07).** La función removía el DÍGITO de volumen ("Slam Dunk nº1" → quitaba "1") pero
    el marcador `nº` quedaba → `series_key` malformado `slam-dunk-no` (y `monster-no`, `i-s-no`,
    `rg-veda-no`, `soy-un-angel-no`). Efecto: items raw de una misma serie no agrupaban entre sí ni
    con su contraparte ya estandarizada. Fix: tras `_SERIES_STRIP_RE`, una pasada extra
    `re.sub(r"(?:n[º°]|＃|#|第)\s*\d*\s*巻?", " ", text, flags=I)` limpia el marcador (y sus variantes
    JP ＃/#/第…巻) junto al número. OJO: "Kaiju No. 8", "Denjin N", "Make wa Tada **no** Mahou" NO se
    tocan (la "no"/"N" es parte real del nombre; el marcador es `nº`/`n°`, no la palabra suelta).
    **A2 (Fable 2026-07-08): el fix de arriba NO estaba completo — `_SERIES_STRIP_TOKENS` seguía
    incluyendo `"no"`/`"no."` como stopword, así que la palabra "no" líder/interna SÍ se borraba
    ("No Longer Human" → "longer human", "No Soy un Ángel" → "soy un ángel" — que NO matchea la
    canónica `no-soy-un-angel`/`im-not-an-angel`, "No Guns Life" → "guns life", "Kaiju No. 8" →
    "kaiju 8" ≠ `kaiju-no-8`). Fix real: quitar `"no"`/`"no."` de `_SERIES_STRIP_TOKENS` (los
    markers reales `nº`/`n°`/`n.` quedan). Verificado: `backfill_cluster_key --dry-run` = 0 churn
    (el corpus estandarizado agrupa por tier edition/lmc, no por la heurística de serie).** El
    corpus existente se reparó con `scripts/retrofit/fix_raw_series_keys.py` (re-deriva series/edition
    de los items raw y consolida). **Raw vs. estandarizado en una misma coleccion**: si una `/coleccion`
    ya tiene un item estandarizado y entran items raw de la misma página (misma obra, otro idioma p.ej.
    "No soy un ángel" vs el std "I'm Not an Angel"), los raw heredan series/edition del std (coleccion =
    edición) — alineación determinística, no se espera al LLM.
    **A escala (re-scrape de colecciones conocidas):** re-scrapear una `/coleccion` que YA estaba
    estandarizada deja el item raw nuevo con `edition_key`/`cluster_key` distinto del viejo (el viejo
    tiene tier-1 `edition:…`, el raw tier-2.5 `lmc:…`) → NO consolidan y la colección aparece dos veces
    (ej. cole 1555: 9× "Bastard!! nº N" raw + 9× "Bastard!! Deluxe N" estandarizado). El fix es
    `scripts/retrofit/align_raw_to_std_coleccion.py`, **wireado como paso `[4f2]` de
    `scrape_delta.sh`/`scrape_full.sh` (antes de `consolidate_sources`)** → idempotente, no recurre.

44. **La TIENDA no es la EDITORIAL (2026-06-07).** Las fuentes retailer generales —que
    revenden ediciones estándar de muchas editoriales— NO deben setear `publisher` al nombre
    de la tienda. Tres lo hacían: `JP - Sanyodo Comic Limited Editions` (`Sanyodo`),
    `JP - Rakuten Books (search)` (`Rakuten Books / 楽天ブックス`) y `US - Kinokuniya Exclusives`
    (`Kinokuniya USA`, hardcodeado en `wikis/kinokuniya.py::_virtual_source`). El nombre de
    tienda se sembraba como `publisher` (`candidate_from_source` → `source.publisher`) y luego
    `_publisher_slug` lo metía en el `edition_key` o quedaba `…-unknown-…`. Efecto: el MISMO
    libro (mismo ISBN) scrapeado desde la editorial oficial quedaba en otro `cluster_key` →
    "posibles productos duplicados" en el Panel de Calidad. En Kinokuniya además el `edition_key`
    YA traía la editorial real (`vagabond-viz-deluxe`, `attack-on-titan-kodansha-us-deluxe`) —
    solo el campo `publisher` quedaba con la tienda. **Regla:** en fuentes retailer
    multi-editorial, NO pongas `publisher` (mejor `""` que erróneo — el merge por ISBN o el skill
    lo completa) y NUNCA mapees un nombre de tienda en `_PUBLISHER_SLUG_MAP`. **Excepción:**
    tiendas *mono-editorial* (La Comiquería→Ivrea AR) o *labels que SON el editor de la variante*
    (Funside, Manga Dreams, MangaYo) SÍ llevan publisher/slug a propósito. **Kinokuniya NO es
    excepción** (decisión 2026-06-07): es una librería; la editorial real es Viz/Kodansha/Seven
    Seas/TOKYOPOP y va en el campo `publisher` (la exclusividad de la variante la captura el
    signal `retailer_exclusive`, no el publisher). Fix de fuente: se removió el `publisher` de
    las tres fuentes y el `"rakuten"` del slug map. Corpus existente: retrofit
    `scripts/retrofit/fix_store_publisher.py` (`_STORE_EXACT`/`_STORE_PREFIX` cubren sanyodo,
    rakuten books, kinokuniya): limpia el campo `publisher` top-level y dentro de `sources[]`,
    recupera la editorial real por slug del edition_key o por hermano-ISBN, y colapsa los dups
    de mismo-ISBN+mismo-series cuyo único conflicto era el slug de publisher. Las divergencias
    de romanización del `series_key` NO se tocan (son trabajo del skill).

45. **Editoriales REALES ausentes en `_PUBLISHER_SLUG_MAP` → `edition_key` con `…-unknown-…`
    (2026-06-07).** Distinto de #44 (ahí la tienda contaminaba el publisher); acá el `publisher`
    es correcto pero la editorial no estaba en el map, así que `_publisher_slug` devolvía
    `unknown` y se horneaba en el `edition_key` (`look-back-unknown-integral` con publisher
    "Norma Editorial"). Efecto: ediciones de editoriales DISTINTAS colapsaban bajo el mismo slug
    `unknown` (mismo `cluster_key`) → merges erróneos / dups. Faltaban ~22 editoriales (varias ES
    indie/medianas: Astiberri, Ponent Mon, Ediciones B, Bruguera, La Cúpula, LetraBlanka, Héroes
    de Papel, Ooso, Nowevolution; + Akita, noeve, ISAN…). Fix: se agregaron al map (futuros
    standardize ya resuelven). Corpus existente: retrofit
    `scripts/retrofit/fix_publisher_unknown_edition_key.py` reemplaza el segmento `-unknown-` por
    el slug real cuando `publisher` está poblado y recomputa cluster_key (703 items en la pasada
    inicial; quedó 1 borde legítimo, "Derek Padula", autor-editor). **Al sumar una fuente con
    editoriales nuevas, agregalas al map** o reaparecerá el `unknown`.

46. **REGLA DE NEGOCIO DURA: país distinto = edición distinta, SIEMPRE (2026-06-07).** Dos
    mercados NUNCA comparten edición aunque coincidan series+editorial+edición. El `edition_key`
    TERMINA con el código de país de la EDICIÓN: `{series}-{publisher}-{edition}-{country_slug}`
    (`_country_slug`, ej. `hunter-x-hunter-panini-variant-es` vs `…-it`). Antes "Panini" colapsaba
    IT+ES+MX+BR al mismo slug → la vista de edición (agrupa por `edition_key`) mostraba tomos de
    países distintos como UNA edición (53 edition_keys mezclaban países). El cluster_key tier-1
    (`edition:{edition_key}|{vol}`) hereda el país → el dedup tampoco fusiona cross-mercado.
    **El país es el de la EDICIÓN (`item.country`, derivado de editorial/idioma), NO el de la
    tienda**: una tienda IT puede revender la edición FR (Manga Dreams) y sigue siendo UNA edición
    — por eso NO se escinde `sources[]` por país (las sources son la misma edición en varias
    tiendas). Motor: `derive_series_metadata` hornea el país; el skill `/watch-standardize-catalog`
    igual (su allowlist de country_slug). Corpus existente: retrofit
    `scripts/retrofit/fix_edition_country.py` (sufija país + recomputa cluster_key + consolida;
    10323 items). Las fusiones cross-país REALES (misma editorial matriz en 2 mercados, ej. Panini
    Comics IT + Panini Manga ES bajo un edition_key) se separan a mano / las previene el motor.

47. **`is_collectible_edition` regla-2 (`bonus`/`finish`) usaba `\b\d+\b`, que NO reconoce "nºN"
    (2026-06-07).** Los tomos con cofre de 1ª edición de listadomanga tienen título "Ataque a los
    Titanes **nº1**" y sólo signal `bonus`. La regla 2 exigía un número en el título con
    `re.search(r"\b\d+\b", title)`, pero la "º" de "nº" es word-char Unicode → NO hay word-boundary
    antes del dígito → el match fallaba y TODOS esos cofres caían como `regular_tomo` (el gate los
    descartaba pese a que el parser los crea adrede). Caso real Attack on Titan cole 1606:
    regular-1/17/27 (cofres por rangos 1-7, 8-17, 18-27) desaparecían; sólo sobrevivía el
    `especial-34`. Fix: `re.search(r"\b\d+\b|n[º°]\s*\d+", title)` — acepta número suelto ("Naruto
    12 con marcapáginas") Y pegado a nº ("…nº1"); sigue rechazando posts sin número. Afecta a TODO
    el catálogo (cualquier serie con cofres de 1ª ed.); recuperar el corpus requiere re-scrape.
    Relacionado con #43 (el mismo "nº" rompía `_normalize_series_name`).

48. **Una `/coleccion` = UNA página de edición: TODOS sus tomos comparten edition_key (2026-06-07).**
    Complemento de #42 (esa dice: colecciones DISTINTAS nunca comparten edition_key; ésta dice el
    inverso: dentro de UNA coleccion NO se separa). El owner: "de una misma /coleccion se agrupan
    TODOS esos tomos en una misma página de edición". Antes el parser/skill separaba dentro de una
    coleccion `…-regular` vs `…-special-c{id}` → la edición especial (ej. Attack on Titan especial-34,
    cole 1606) caía en otra página que los regulares 1/17/27. Fix: el `edition_key` se UNIFICA por
    coleccion al de su edición BASE (`regular` si existe; si no, la predominante — Berserk cole 2689
    → `maximum`). La distinción de variantes del MISMO volumen (regular-34 vs especial-34) ya NO la
    da el edition_key (común) sino el **`cluster_key` tier-0 de listadomanga**:
    `lmc:{coleccion}:{kind}:{vol}`, evaluado ANTES del edition_key en `derive_cluster_key`. El kind
    sale del synthetic URL `&item=<kind>-<vol>` o, para old-format sin item=, del campo `lm_kind`
    (edition_slug viejo). Seguro: los items de listadomanga NUNCA se fusionan cross-fuente (0 sources
    externas), así que usar lmc en vez de edition_key no rompe merges. Motor: el skill genera el
    edition_key base; post-paso `unify_coleccion_edition.py` ([4f3] del pipeline) lo fuerza en el
    corpus (46 colecciones tenían split interno). 46 colecciones unificadas en la pasada inicial.

49. **`edition_display` = NOMBRE OFICIAL de la edición, SIN traducir (2026-06-07).** NO un slug
    genérico traducido ("Special (Norma Editorial)", "Regular", "Box Set"). Sólo el `title` (nombre
    del TOMO) se traduce; el nombre de la EDICIÓN va tal cual en su idioma. Para listadomanga = el
    título de la /coleccion (`_extract_collection_title`): "Ataque a los Titanes", "Guardianes de la
    Noche (Kimetsu no Yaiba)", "Berserk (Maximum) (Castellano)", "Fruits Basket (Edición
    Coleccionista)". El parser lo inyecta (`cand.edition_display = collection_title`) y
    `candidate_to_json` lo respeta (`ed = ed or derived...`); el skill NO lo regenera (gotcha #49 en
    SKILL.md + el post-paso _LMC ya no pisa edition_display). Corpus existente: retrofit
    `fix_listadomanga_edition_display.py` re-fetchea el título de cada coleccion (507 colecciones,
    1303 items). Antes el display salía de `_EDITION_NAME_MAP` (slug→"Special") + publisher.

50. **El FULL recorre lista.php (alfabético), NO ids numéricos; y 3 fugas de captura (2026-06-07).**
    `lista.php` lista ~3436 colecciones ACTIVAS en orden ALFABÉTICO (ids NO secuenciales —
    Azumanga id=542 está en posición 251). El FULL debe recorrerlo item por item
    (`--coleccion-mode lista`, o el driver `ingest_listadomanga_full.py` por chunks resumibles
    con checkpoint `data/listadomanga_full_progress.json`). NO usar `range` (ids 1..N) para
    "los primeros N" — son sets distintos. Tres bugs que tumbaban premium/cofres aun visitando
    la coleccion: (a) **`kanzenban` puntuaba 25 < min_score 30** → colecciones Kanzenban enteras
    (20th Century Boys, Monster…) caían; subido a 35 (= perfect/master edition); `coleccionista`/
    `collector` 28→32. (b) **Score floor por título premium**: si el TÍTULO de la coleccion indica
    edición premium (`title_premium`: Kanzenban/Integral/Deluxe/Coleccionista), sus tomos reciben
    score≥31 aunque el signal puntúe bajo. (c) **Gate proof-of-product**: una edición premium de 1
    tomo sin número en el título ("21st Century Boys" Kanzenban) caía como `regular_tomo` porque el
    signal venía del título de la coleccion (en description); la URL sintética
    `coleccion.php?id=N&item=` ahora cuenta como prueba-de-producto. Relacionado con #47 (gate +
    cofres "nº"). Reparar el corpus = re-correr el FULL (re-walk = retrofix).

51. **"doble sobrecubierta" NO es Kanzenban (2026-06-07).** La regla
    `PREMIUM_FORMAT_RULES` mapeaba `doble sobrecubierta → kanzenban`, pero una doble
    sobrecubierta (dust jacket doble/reversible) es COSMÉTICA y común en ediciones
    REGULARES → marcaba colecciones enteras como kanzenban premium y las capturaba (caso
    real Zetman Ivrea cole 1648: "Tomo (133x185) rústica con doble sobrecubierta", una
    edición regular). Fix: se removió la regla; el kanzenban GENUINO se detecta sólo por el
    título "(Kanzenban)" (P0-A) o el literal "kanzenban" en el formato. Corpus: retrofit
    `fix_doble_sobrecubierta_falsepos.py` re-parsea las colecciones kanzenban y quita los
    items cuyo volumen ya no califica (conservador: NO toca los kanzenban genuinos como Slam
    Dunk / 20th Century Boys / Inuyasha; 105 falsos positivos removidos — Zetman, Hikaru no
    Go, Princess Jellyfish, Blue Giant…). Relacionado #41 (heurístico A5 ya removido antes).

52. **Título de tomo: quitar "nº" + marcar Edición Especial (2026-06-07).** (a) El display
    quita el marcador de volumen "nº" ("Atelier of Witch Hat nº5" → "… 5"). (b) Cuando un tomo
    es EDICIÓN ESPECIAL, su título es "{serie} {vol} Edición Especial" (vol ANTES del
    calificador, SIN paréntesis; helper `mw.format_especial_title`) para distinguirlo del tomo REGULAR
    del MISMO volumen — ambos conviven en la misma edición (gotcha #48) y se veían como
    duplicados (caso real Atelier of Witch Hat: regular nº5 + especial nº5). Helper
    `normalize_display_title(title, kind)` (parser lo aplica al emitir; retrofit
    `fix_lmc_display_titles.py` para el corpus; paso 3a del enforcer). **Kind del cluster
    canonicalizado**: el synthetic URL usa español (especial/alternativa/limitada) y el lm_kind
    viejo el slug inglés (special/variant/limited) → `derive_cluster_key` los mapea a un
    vocabulario (especial→special, etc.) para que old-format std y new raw del MISMO producto
    deduplicen. **Dup cross-fuente**: un especial de listadomanga (cluster lmc) y su gemelo de
    otra fuente (ej. la tienda Milky Way, cluster edition:) NO fusionaban; se re-clusterizó el
    especial de listadomanga al cluster de edición (19 fusionados) — la regular sigue separada por
    su cluster lmc.

53. **Cofre de 1ª edición común no se capturaba: target_edition_kind vacío (2026-06-07).**
    `_parse_layout_b_cell` determina el tomo destino del cofre. Cuando la línea 1 es "Serie nºN"
    (volumen) y la línea 2 es "Cofre para tomos X a Y" (descriptor de cofre, SIN marker de edición
    especial), `target_edition_kind` quedaba VACÍO → `_merge_extras_into_items` lo saltaba
    (`if not target_kind: continue`) → la coleccion rendía 0 (caso real Medaka Box cole 1576, Aoha
    Ride, Cells at Work, Cutie Honey…). Attack on Titan funcionaba porque su cofre traía el marker
    "1ª Edición". Fix: si hay `target_volume` y la línea 2 contiene un descriptor de COFRE/EXTRA
    (cofre|regalo|postal|marcapáginas|lámina|brinde|extra|póster|tarjeta) → `target_edition_kind =
    "regular"` (es el cofre de 1ª ed. del tomo regular N). OJO: un marker de edición DESCONOCIDO
    ("(Edición Aniversario 30)") NO defaultea a regular — se sigue saltando (no inventamos edición).
    Afecta a TODO el catálogo (cofres comunes); recuperar requiere re-scrape.

54. **Dups por fuente sintética compartida + título "Edición Especial" stale + hash NO único por cole (2026-06-07).** Tres facetas de un mismo enredo en listadomanga, encontradas en la auditoría bidireccional:
    - **Dup cross-source**: un tomo de listadomanga (`item=especial-41`) se fusiona con su ficha de tienda (Panini) bajo `edition:`+vol, pero la fila `lmc:`-only original queda viva → 2 filas comparten el mismo synthetic. El upsert keyea por `cluster_key` (`edition:` vs `lmc:`), que difiere, así que NO deduplica y el dup VUELVE cada scrape. También pasa con el representante base-url (`coleccion.php?id=N` sin `item=`) que arrastra una copia de un synthetic (AoT `regular:34` dup de `special:34`). Fix: `dedup_synthetic_source.py` (en el enforcer, paso 3c) fusiona filas que comparten EXACTAMENTE 1 token sintético; re-fija primaria+cluster (externa→`edition:`, sólo-listadomanga→`lmc:` con la URL `item=`, NUNCA la base sin `item=`). Multi-hash (packs especial+variant, filas sobre-mergeadas) se SALTAN y loguean para revisión manual.
    - **El hash del `item=` NO es único entre colecciones**: el disambiguator sale del stem del filename de la portada (`_make_synthetic_url` line ~1395), y listadomanga reusa un placeholder → `regular-1-08a02c268a6d6b23` aparece IDÉNTICO en obras distintas (NGE 4288, Bastard!! 1555, Tokyo Revengers 3996…). El `id=N` de la URL las disambigua (cluster `lmc:cole:kind:vol` es seguro), pero CUALQUIER dedup por `item=` pelado fusiona obras totalmente distintas. Regla: la identidad sintética SIEMPRE se cualifica por cole (`{cole}|{item}`). No se tocó el generador (cambiarlo rompería idempotencia con el corpus); el cluster ya está cole-scoped.
    - **Título "Edición Especial" stale en tomos regular**: tras reclasificar cofres especial→regular (#53), los tomos arrastraban el qualifier viejo (AoT/Platinum End `1,2,3,14`). `normalize_display_title` ahora es AUTORITATIVO: añade "Edición Especial" si kind∈{especial,special}, lo QUITA si no. `fix_lmc_display_titles._kind` deriva del `cluster_key` (`lmc:cole:kind:vol`, fiable para la fila base sin `item=`).
    - **Bundling de tienda multi-kind**: una fila de TIENDA (Berserk Pack/Metalizada) agrupaba sintéticos de KINDS distintos del mismo (cole,vol) — especial-41 + alternativa-41 — porque antes del tier-0 clusterizaban por `edition:edition_key|vol` (sin kind). `dedup_synthetic_source._debundle_store_rows` conserva el sintético que matchea el edition-slug de la fila y quita el ajeno SÓLO si otra fila ya lo tiene.

55. **cluster_key STALE = la raíz de la "auditoría que siempre encuentra algo" (2026-06-07).** El bug más importante y el menos visible. `standardize` (o un retrofit) renombra el `edition_key` de un item (alias de serie, `boxset`→`cofanetto`, `deluxe`→`ultimate`, `fanbook`→`artbook`, `deluxe-2`→`deluxe`) PERO el `cluster_key` guardado conserva el `edition_key` VIEJO. El enforcer consolidaba por el `cluster_key` viejo → nunca fusionaba los duplicados que el nuevo `edition_key` implica, y en la siguiente ingesta `derive_cluster_key` producía la clave nueva → re-split/re-merge → "apareció algo nuevo". Eran **741 items** con `cluster_key` ≠ `derive_cluster_key(item)` (→ 82 productos duplicados ocultos). Fix: `backfill_cluster_key.py` (re-deriva TODOS los cluster_key) se agregó al enforcer (paso 3b2, ANTES de consolidate). **Invariante CLKEY** (validador): `it['cluster_key'] == derive_cluster_key(it)` para todo item — si falla, el pipeline NO es un punto fijo. Lección de proceso: auditar UNA dimensión a la vez con un instrumento que comparte el punto ciego de los datos da "0 falso". La verificación correcta es (a) `validate_corpus.py` — TODAS las invariantes estructurales en una pasada (SLUG, CLKEY, DUPCL, DUPSYN, LMCKIND, TITLE, ONECOLE, COLED, PAIS), y (b) **prueba de idempotencia**: correr el enforcer 2× debe dar items.jsonl byte-idéntico. Ambas corren en el pipeline (scrape_*.sh paso [5]). **Warnings COLED/PAIS resueltos (2026-06-08)**: COLED (una /coleccion con >1 edition_key) venía de fichas de TIENDA cross-source no unificadas + el slug stale `panini-es` — fix: `unify_coleccion_edition` ahora agrupa fichas de tienda vía `sources[]`, y `fix_edition_key_anomalies` (enforcer 2b) normaliza `panini-es`→`panini` y `xx`→país inferido de editorial mono-país. PAIS bajó 226→7; y 7→1 (2026-06-11) al agregar el tier **grupo de registro ISBN→país** (978-84=es, 978-3=de, 607=mx, 978-612=pe; anglófonos 0/1 NO se mapean por ambigüedad US/UK) + herencia de país entre hermanos del mismo edition_key (coleccion=edición ⇒ mismo país). El 1 restante no tiene evidencia (eBay sin ISBN) → `xx` es honesto (no se inventa país). OJO con el validador: su derivación de kind (para TITLE) debe igualar a la del fixer (`fix_lmc_display_titles._kind`): cluster lmc → kind de la fuente sintética `item=` → slug del edition_key (una metalizada cross-source que mergeó con `especial-21` lleva "Edición Especial" legítimo aunque su edition-slug sea `maximum`).

56. **"El tomo 13 aparece dos veces" — 4 raíces del DUPLICADO de tomo en una edición (2026-06-08).** El owner reportó The Promised Neverland 13 duplicado. La **invariante DUPVOL** (validador): dentro de un `edition_key`, dos items con el MISMO volumen y (mismo kind O mismo título exacto) = duplicado visible. Encontró 30, en 4 patrones:
    - **base-url phantom**: una fila con primaria `coleccion.php?id=N` (sin `item=`) y kind del edition_slug (`kanzenban:2`) duplica al tomo sintético `regular-2` (mismo título). Old-format vs new-format del mismo tomo. Fix: `collapse_baseurl_tomos.py` (enforcer 3-1) la fusiona en el sintético del mismo (cole, vol). CRÍTICO: sólo phantoms PUROS (base-url SIN `item=` propio en sources) — una base-url que SÍ tiene su synthetic es un producto real (regular que coexiste con el especial, NO fusionar). Verificado contra el parser: en estos casos el parser emite UN producto por vol.
    - **dup cross-source tier-0/tier-1**: la ficha de tienda (`edition:`) y el tomo de listadomanga (`lmc:`) NO se fusionan (cluster_key difiere por tier) aunque sean el mismo producto (Fruits Basket Collector 3 de Casa del Libro + listadomanga). Fix: `merge_crosssource_into_lmc.py` (enforcer 3-2) los fusiona por (edition_key, vol, MISMO título); el lmc es canónico y absorbe la URL de tienda como source.
    - **título contaminado**: un tomo REGULAR arrastra el nombre de la edición especial del mismo vol embebido en el título ("The Promised Neverland **Edición Especial Artbook** 13"). Fix: `fix_lmc_display_titles` (sólo edición regular) quita los qualifiers contaminantes (`Edición Especial Limitada|Artbook|Coleccionista`); `normalize_display_title` quita "Edición Especial" en CUALQUIER posición y, si el kind es especial, lo re-apenda UNA vez al final.
    - **falta marcador de kind**: regular + variant (o + limited) del mismo vol con título IDÉNTICO ("Devilman Omnibus 1" ×2). Fix: `normalize_display_title` apenda marcador por kind (variant→"Variant", limited→"Edición Limitada", especial→"Edición Especial") para distinguirlos. El validador pasa el kind REAL a normalize (no sólo especial/regular) y des-contamina igual que el fixer, o reporta falsos.

57. **coleccion distinta = edición distinta: colisión de edition_key entre /coleccion (2026-06-08).** `standardize` asignaba el MISMO `edition_key` a colecciones REALMENTE distintas (Biomega "Ultimate" cole 2572 vs "Master" cole 4501; Magic Knight Rayearth cole 245 vs Rayearth **2** cole 322; regular vs especial en páginas separadas) → sus tomos del mismo vol aparecían duplicados (mismo edition_key+vol). El `cluster_key` lmc sí difiere (lleva el cole), por eso DUPCL no lo veía. Viola la regla dura del owner ([[feedback_coleccion_is_edition]]). Fix: `disambiguate_coleccion_editions.py` (enforcer 3-0) — si un `edition_key` abarca >1 colección, inserta `-c{cole}` antes del país en CADA item (cada cole = su edición; coleccion=edición se mantiene). Idempotente. 124 items en la pasada inicial.

58. **Box set = edición APARTE, no parte de la edición de los tomos (2026-06-08).** Regla del owner: dentro de una /coleccion, un **pack / edición especial / portada alternativa conviven en la MISMA edición** (registros aparte del mismo `edition_key`), pero un **box set es una edición distinta**. `unify_coleccion_edition` colapsaba TODO a un solo `edition_key` → el box set y los tomos quedaban en la misma edición (o el tomo deluxe heredaba slug `boxset`, o el box heredaba `regular`). Fix: unify ahora calcula el base con los NO-box y asigna a los box-set su propio `edition_key` con slug `boxset` (`_is_box`: cluster kind `boxset`, o `pack`/otros con volumen-rango/vacío o título "Box Set/Cofre/Estuche"; un `pack:42` tomo-suelto NO es box). El cluster kind ya distinguía box; sólo el `edition_key` se corrompía. **El validador lo sabe**: COLED (una /coleccion con >1 edition_key) NO dispara si la 2da edición es un box set (slug `boxset`) — sólo flag si hay >1 edición NO-box. 34 items / 12 colecciones en la pasada inicial.

59. **Layout B: extra de "Edición Especial" mal clasificado como tomo regular cuando el nombre de serie se envuelve en 2 líneas (2026-06-08).** En la sección "Regalos/Cofres con las primeras ediciones", una celda Layout B cuyo nombre de serie viene partido por un `<br>` ("The Promised" / "Neverland nº13") hacía que `_parse_layout_b_cell` viera el `nº13` en la línea 2 y disparara el fallback Grimorio → `target_edition_kind = regular`. Pero el item era en realidad la EDICIÓN ESPECIAL (artbook): "Edición Especial con Escape - Libro de ilustraciones de 64 páginas". Resultado: un tomo `regular-13` FANTASMA (sin cofre propio) que duplicaba visualmente al `especial-13` real (lo reportó el owner en Promised Neverland). Fix: si CUALQUIER línea de la celda (más allá de la 1) contiene "Edición Especial/Limitada", el kind es `especial` (se fusiona con el especial del mismo vol), ANTES del fallback Grimorio. Sólo 3 items con el bug exacto (Promised Neverland 13, A Miyoshi 2, Twilight Out of Focus 2). OJO al diferenciar: un cofre legítimo de 1ª edición ("(1ª Edición) Cofre para tomos X a Y") SÍ es del tomo regular (#53); el discriminante es el texto "Edición Especial/Limitada".

59b. **El workflow `watch-standardize-catalog` perdía resultados y agotaba la sesión en force-runs grandes (2026-06-08).** Dos bugs encontrados al re-estandarizar ~10k items (force-run masivo). (a) **`args.limit` no llegaba** al workflow nombrado → `limit=0` (sin cap) → intentaba procesar TODO el pending de una sola corrida y agotaba el session limit del account a mitad del merge (subagentes "completed without calling StructuredOutput" en masa = signature de rate/session limit). Fix: default `limit=2000` (`args.limit !== undefined ? … : 2000`) — bound por corrida; el diseño es incremental, el resto se toma en la próxima. (b) **El merge transcribía inline un array gigante**: el merge-agent recibía `${JSON.stringify(allLlmResults)}` (hasta ~2000 objetos) en el prompt y debía escribirlo VERBATIM a `llm_results.json` con la Write tool → arriba de ~500 objetos el agente NO lo transcribía completo y escribía sólo unos pocos (un run mergeó 5 de 2000). Fix: cada subagente tier2/tier3 escribe su PROPIO `result_t{2,3}_NN.jsonl` (chunk chico, confiable) y el merge los lee por glob — cero transcripción central. Items cuyo chunk no produjo archivo quedan PENDING y se reintentan. **Recuperación**: si un run muere antes del merge, los veredictos VIVEN en los transcripts de los subagentes (`subagents/workflows/<runId>/agent-*.jsonl`, tool_use `StructuredOutput` con `{items:[…]}`) — se pueden extraer y mergear determinísticamente (lo que salvó ~3000 verdicts en este episodio). Sincronizado con `.claude/workflows/watch-standardize-catalog.js`.

61. **Lavado de señales post-estandarización: NO correr rescore blanket sobre items con `standardized_at` (2026-06-10).** Cualquier retrofit que recompute `signal_types` desde `title+description` destruye las señales de items estandarizados — la estandarización reescribe título/desc a etiquetas limpias ("Yawara! Ultimate 18") donde `detect_signals` no encuentra nada. Caso real 2026-06-10: `filter_collectible` habría rechazado 226 items estandarizados válidos como `regular_tomo` (Ultimate de Panini IT, Limited JP de Rakuten, Anniversary de Mangavariant, One Piece curados). Fix: `filter_collectible` tiene guard — items con `standardized_at` solo pasan gates duros (junk de título, umbrella_magazine), bucket `kept_standardized`. COROLARIO (cerrado 2026-06-11): `rescore.py` ahora tiene el MISMO guard estructural — los items con `standardized_at` se saltean por defecto (`--include-standardized` para override puntual), así el paso [4a] del pipeline canónico es seguro por construcción. Antes NO debía correrse blanket sobre corpus estandarizado (dry-run del 2026-06-10: cambiaría `signal_types` de 1393 items, con transiciones de pérdida 87 special→manga, 19 boxset→manga). La verdad post-estandarización vive en la etiqueta de edición derivada, no en el texto crudo.

62. **Colisión de título estandarizado en el gate `umbrella_magazine`: usar URL, no título (2026-06-10).** La revista de prensa FR "ATOM" (Manga-Sanctuary) quedó mapeada a la serie astro-boy y estandarizada como "Astro Boy | Mighty Atom Deluxe N" — EXACTAMENTE el mismo título que los tomos deluxe reales de Planeta ES (`astro-boy-planeta-deluxe-es-1..7`). Un patrón de título habría borrado los 7 legítimos. Fix: el gate ATOM discrimina por URL (`manga-sanctuary.com/magazine-atom-`) vía `_UMBRELLA_MAGAZINE_URL_PATTERN` en `is_collectible_edition` paso 0b; removidas las alternativas de título "Atom Hardcover|Mighty Atom (Magazine|Deluxe|Hardcover)". Quedan por título solo nombres inequívocos (Animeland, Otaku USA, Coyote Mag, antologías JP). Se removieron 21 items de la revista del corpus. REGLA GENERAL: cuando el título de la revista coincide o puede coincidir con el de una obra manga real, el discriminante debe ser la URL (fuente), nunca el título.

63. **Manga reales con palabras de franquicia occidental en el título: lista `title_exceptions` en `comics_blacklist.yml` (2026-06-10).** `franchise_keywords` rechazaba manga legítimos: "Shugo Chara! Jewel Joker" (Joker), "Hungry Joker", "Deadpool: Samurai" (Jump+), "Batman Ninja", "Cell of Empireo", "Batman: El Hijo de los Sueños" (Kia Asamiya), "Assassin's Creed: Blade of Shao Jun", "Eagle: The Making of an Asian-American President" (este último por el patrón hard `\bThe Making of\b`). Fix: lista `title_exceptions` en `data/comics_blacklist.yml` que neutraliza tanto `franchise_keywords` como los patrones hard non-manga (implementado en `is_comic_not_manga` + el flujo hard de `manga_watch.py`). También: `\bstandees?\b` refinado para no matchear "standee" como accesorio/extra del producto ("con/with/avec/mit/inkl./+ standee").

64. **Wrapper `manga_watch.py` de la raíz sombrea `scripts/manga_watch.py` en pytest (2026-06-10).** El wrapper en la raíz del repo (solo re-exporta `parse_args`/`run`) puede quedar cacheado en `sys.modules` como `'manga_watch'` durante la colección de la suite completa → `ImportError` en módulos que hacen `from manga_watch import <símbolo>`. Fix patrón: import con fallback `try/except` a `scripts.manga_watch` (como ya hacía `sync_cover_images.py`; aplicado a `fetch_better_covers.py`). Si agregás un retrofit nuevo que importa de `manga_watch`, aplicar el mismo patrón.

60. **`volume` vacío en ediciones especiales/limitadas/variantes — ordenamiento roto (2026-06-09).** REGLA GLOBAL (todas las fuentes): los tomos de una edición SIEMPRE se ordenan (a) por volumen ascendente; (b) desempate por kind-rank cuando el mismo volumen tiene >1 item: `regular(0) → variant(1) → special/limited(2) → deluxe/kanzenban(3) → artbook(4) → boxset(5)`. Dos bugs encontrados: (1) el parser LMC extraía el volumen del `alt` ("nº13") y construía correctamente la URL sintética `item=especial-13-HASH`, pero NO lo propagaba al `Candidate.volume` → `_extract_volume` fallaba en "Title 13 Edición Especial" (patrón trailing no captura números en medio del título) → `volume: ""` → item aparecía al final de la edición. Fix: `cand.volume = parsed["volume"]` en `listadomanga_collections.py` + nuevo patrón `\s(\d{1,3})\s+(?:Edición Especial|Variant|Limited|…)` en `_VOLUME_EXTRACT_PATTERNS`. (2) Para items existentes: `backfill_volume_from_cluster.py` lee el vol-segment del `cluster_key` lmc (ignorando "0" = placeholder). Afectó 9 items: Promised Neverland 13, Berserk 21/41/42 Variant, Seven Deadly Sins 41, Twilight Outfocus 1/2, A Miyoshi 1/2. Implementación del sort: `web/index.html` (`_kindRank` + sort en `currentEdition`) y `web-next/lib/data.ts` (`kindRank` + sort en `loadEditionClusters`). Tests: `test_edition_sort_*` en `tests/test_extraction.py`.

65. **Re-scrape sobre filas estandarizadas LAS DEGRADA: el upsert resetea `slug`/`cluster_key`/`detected_at`/`score`/`signals`/`status` (2026-06-10).** Al re-scrapear una fuente cuyos productos YA están en el corpus estandarizado (caso real: re-ingest de Manga-Sanctuary histórico + Panini IT), el upsert del flush matchea la fila existente por URL/ISBN y la refresca con el candidate crudo: conserva `standardized_at` y el título estandarizado, pero deja `slug=None`, baja `cluster_key` al tier `isbn:`/`url:` (perdiendo el `edition:` derivado), resetea `detected_at` a hoy y recomputa `score`/`signals` desde el texto crudo (pérdida tipo gotcha #61). Efecto: validate_corpus pasa de verde a cientos de violaciones SLUG/CLKEY/DUPCL. **Reparación post-scrape (en este orden)**: `backfill_cluster_key.py` (re-deriva claves → vuelve al tier edition) → `generate_slugs.py --only-missing` → `consolidate_sources.py` (fusiona las filas nuevas raw con sus clusters existentes). Verificado 2026-06-10: 1272 violaciones duras → 0. **FIXED de raíz (2026-06-10), en dos capas**: (a) en `append_jsonl` — `_CURATED_FIELDS` ahora incluye `slug`/`detected_at`/`score`/`signals`/`signal_types` (la verdad post-estandarización vive en la etiqueta de edición, no en el texto del re-scrape, gotcha #61), el merge re-deriva `cluster_key` con los campos curados ya restaurados (mantiene la invariante CLKEY en tier `edition:`), y `slug` es sticky para TODOS los items (el scraper nunca lo trae); además `candidate_to_json` deriva `cluster_key` DESPUÉS de escribir el edition_key heurístico (antes toda fila fresca entraba en tier `isbn:`/`url:` con stored != derived). (b) Safety-net en el pipeline: `scrape_delta.sh`/`scrape_full.sh` corren `backfill_cluster_key.py` [4f5] + `generate_slugs.py --only-missing` [4f6] antes de `consolidate_sources` [4g]. Verificado: re-scrape de Panini IT sobre corpus estandarizado (state limpiado para forzar el upsert) → `validate_corpus.py` 0 violaciones duras sin reparación manual.

67. **`srcset` lista entradas de menor a mayor: tomar la ÚLTIMA/mayor, no la primera (2026-06-11).** `_img_to_url` procesaba `srcset` con `val.split(",")[0]` → devolvía el thumbnail de menor resolución. Los `srcset` listan entradas de menor a mayor (convención HTML: `480w, 720w, 1200w` — el browser elige la adecuada según viewport). Fix: parsear todas las entradas; si tienen descriptor `<N>w` o `<N>x`, elegir el de mayor N; si no hay descriptores, tomar la ÚLTIMA entrada. Aplica a `srcset` y `data-srcset`. Tests: `test_img_to_url_srcset_picks_largest_w_descriptor`, `test_img_to_url_srcset_picks_last_when_no_descriptor`.

68. **Patrón Magento/Fotorama/PrestaShop/LightGallery: `<a href="full.jpg"><img src="thumb.jpg">` — el href es la full-res (2026-06-11).** Muchos storefronts envuelven el `<img>` del carrusel con un `<a>` cuyo `href` apunta a la imagen full-res (para lightbox). `_img_to_url` solo lee el `src`/`data-src` del `<img>` → devuelve el thumbnail. Fix: `_img_anchor_full_url()` — cuando un `<img>` tiene padre o abuelo `<a>` con `href` que termina en extensión de imagen (`.jpg/.jpeg/.png/.webp/.avif`, sin query string) y el href es del mismo dominio (gotcha #31), preferir ese href. Tests: `test_extract_images_anchor_href_wins_over_src`, `test_extract_images_anchor_non_image_href_falls_back_to_src`.

66. **Keywords de rareza con orden de palabras fijo pierden el caso real — usar patrones cuando la frase varía (2026-06-10).** El keyword `"japan expo exclusive"` no matcheaba "available **exclusively at Japan Expo** 2025"; `"lucca comics"` no matcheaba "Variant **Lucca** 2015" ni "punti vendita campfire di **Lucca Changes**"; y `_PRINT_RUN_RE` solo cubría la preposición de cada idioma en UNA forma ("limitata **a** N copie" pero no "tiratura limitata **di** 1200 copie", "in sole N copie", "limitiert auf 777 **Exemplare**" — el viejo `exempla[ir]res?` solo matcheaba la forma francesa —, "limited to 200 **numbered** copies"). Auditoría 2026-06-10: 368 items con evidencia textual de escasez quedaron en `common` por estos gaps (la mayor clase: 232 variantes furoku "appendix of the magazine X" de Mangavariant, inobtenibles fuera de segunda mano). Fix: `_SINGLE_RUN_PATTERNS` (regex con orden libre: Lucca word-boundary, evento/festival, furoku, retailer-exclusive en texto, out-of-print multilingual) + `_PRINT_RUN_RE` extendido. REGLA: para señales de rareza nuevas, si la frase real puede variar en orden o declinación, va como regex en `_SINGLE_RUN_PATTERNS`/`_ULTRA_RARE_PATTERNS`, no como substring. Tests por cada forma real encontrada en el corpus.

69. **El LLM elegía el slug de TIPO de edición de forma inconsistente — la MISMA edición partida en edition_keys hermanos (2026-06-11).** El skill `watch-standardize-catalog` traducía 限定版 a veces como "limited" y a veces como "special" entre corridas → la misma edición quedaba partida en dos `edition_key` que solo diferían en ese slug. Auditoría 2026-06-11: 206 grupos serie+editorial+país con keys que diferían solo en special/limited/collector/deluxe; 38 con los MISMOS tomos en ambas. Fix (mecanismo, 4 capas): (1) tabla determinística término→slug `edition_slug_from_text()` en `scripts/manga_watch.py` (限定版→limited; 特装版/同梱版→special; 愛蔵版→deluxe; 完全版→kanzenban; "edición limitada"/"edizione limitata"/"édition limitée"/"limited edition"→limited; deluxe→deluxe; las ediciones NOMBRADAS — Maximum/Perfect/Ultimate/etc. — ganan sobre el tipo); el heurístico `_refine_edition_slug` la consulta PRIMERO y manda aun sin signal_types. (2) Los prompts del skill/workflow enuncian la misma tabla + regla de REUSO: el audit adjunta `known_edition_keys` (keys existentes en el corpus para esa serie) para que el LLM REUSE en vez de acuñar variantes. (3) Retrofit `canonicalize_edition_slugs.py` (enforcer paso 3c1) re-aplica la tabla post-LLM sobre fuentes no-listadomanga (los lmc los gobierna coleccion=edición, #48) y además absorbe "hermanas" confundibles minoritarias SIN evidencia textual dentro de la key evidenciada del grupo cuando los tomos se solapan. (4) Invariante EDSLUG (warning) en `validate_corpus.py`. Corpus: 345 keys re-canonicalizadas + 7 absorbidas; pares con tomos solapados 38→27; EDSLUG=0.

70. **series_key partidas por variantes mecánicas del slug (2026-06-11).** La misma obra con 2-3 `series_key`: artículo "The" ("the-apothecary-diaries" vs "apothecary-diaries", 32 items partidos), apóstrofes ("hell-s-paradise" vs "hells-paradise"), romanización de vocales largas ("kumichou" vs "kumicho"). CAUSA RAÍZ: entradas canónicas DUPLICADAS en `data/series_aliases.yml` (el enrich skill creó ambas en corridas distintas) — el corpus solo reflejaba eso. Fix: (1) `aggressive_series_norm()` en `scripts/series_aliases.py` (colapsa "the-" inicial, apóstrofes, separadores, vocales largas ou/uu/oo; NO es fuzzy) + fallback agresivo en `canonical_series_key()` con un índice que descarta colisiones ambiguas entre canónicas; (2) retrofit `merge_duplicate_series.py` (enforcer paso 3c2): fusiona los duplicados del YAML cuando los displays también colapsan (gana la key con más items; la perdedora pasa a alias), reescribe items (series_key, prefijo de edition_key, cluster_key) y encola los grupos SIN canónica a `data/unmapped_series.jsonl` con campo `merged_from`; (3) invariante SERIESDUP (warning) en `validate_corpus.py`. Resultado: 25 grupos fusionados (20 del YAML; quedan 3395 canónicas); 15 grupos ambiguos quedan como warning para curación.

71. **edition_key con prefijo de serie stale (2026-06-11).** El formato es `{series_key}-{pub}-{slug}-{país}[-cN]`, pero 175 items tenían el segmento de serie del `edition_key` desalineado del `series_key`: serie truncada a 35 chars, alias/traducción vieja ("pokemon-sol-luna" vs series_key "pokemon-sun-moon"), o tokens duplicados ("shugo-chara-jewel-joker-jewel-joker"). Fix: `manga_watch.rebuild_edition_key_prefix()` — parsea la COLA desde la derecha (slug de edición del allowlist `_KNOWN_EDITION_SLUGS`; publisher OBLIGATORIAMENTE reconocido en `_PUBLISHER_SLUG_MAP` — si no lo reconoce NO toca la key, para no mutilar publishers fuera del mapa como "nxb-tre"→"tre") y compara el SEGMENTO de serie EXACTO contra el series_key (no startswith). Regla conservadora para keys MÁS específicas que el series_key: solo repara si el extra es repetición mecánica del final del series_key o equivalente bajo `aggressive_series_norm` — un distinguidor LEGÍTIMO ("danganronpa-1-2-reload", "sword-art-online-aincrad": obras distintas de la franquicia sin volumen) NO se toca, porque fusionarlo mezclaría productos. Lo usan: el merge de `standardize_apply.py` (re-alineación inline) y el retrofit `fix_edition_key_prefix.py` (enforcer paso 3c4). **Invariante EKPREFIX** (warning) en `validate_corpus.py`, espejo exacto del fixer + startswith. Resultado: 164+34 keys reparadas en dos pasadas; quedan 11 no-parseables visibles como warning (keys legacy con slug fuera del allowlist, ej. "the-book-of-wind-panini-taniguchi-it" — curación manual).

72. **Títulos con palabra de edición duplicada / "Regular" sobrante (2026-06-11).** El generador/LLM de standardize producía "5 Elementos Artbook Artbook", "Trigun Maximum Maximum 2" (la serie ya termina con la palabra de edición) y "Noragami Regular 27" (las ediciones regulares no llevan calificador en el título). Fix: retrofit `fix_title_edition_words.py` (enforcer paso 3c5) — colapsa SOLO el vocabulario de ediciones duplicado consecutivo (NUNCA palabras arbitrarias: "Dead Dead Demon's Dededededestruction" es legítimo) y quita "Regular" cuando el slug de la edición es regular. 91 títulos corregidos en la pasada inicial. Además los prompts del skill/workflow ganaron dos reglas: GUARD de nombre de serie (si la palabra tipo-edición es parte del NOMBRE de la serie, no es edición ni se repite en el título) y "regular → título sin palabra de edición".

73. **SECTION_RULES no reconocía "Números en preparación (Packs)" (2026-06-11).** Listadomanga usa el header `Números en preparación (Packs)` para packs ANUNCIADOS aún no a la venta (caso real id=5584, detectado en `logs/listadomanga_unknown_h2.txt`). SECTION_RULES cubría `Números editados (Packs)` y las variantes "en preparación" de Especiales/Limitadas/Alternativas + el base, pero NO `(Packs)` en preparación → la sección caía a unknown-h2 y los packs anunciados se perdían en silencio (exactamente la novedad próxima que el modo delta existe para capturar). Fix: nueva regla en SECTION_RULES (`scripts/wikis/listadomanga_collections.py`), ANTES del entry base "en preparación", con el mismo tratamiento que editados: kind `pack` + filtro `PACK_EXTRAS_KEYWORDS` (un pack sin keywords de extras, ej. "Pack tomos 4 y 5" pelado, se sigue descartando) y `status:upcoming` vía `EN_PREPARACION_PATTERN` (prefijo). No toca enforcer ni validador (sólo clasificación upstream).

74. **Volumen contaminado por número embebido en el NOMBRE de la serie (2026-06-11).** `VOLUME_PATTERN` (`n[º°.]?\s*\d+`) tomaba el PRIMER match del alt/título — en series cuyo nombre incluye un número con marcador ("Kaiju Nº8"), ese primer match es el de la serie, no el del tomo: "Kaiju Nº8 nº16" daba vol 8 (la limitada del tomo 16 quedaba con key `limitada-8`), y el pack cuyo alt es SOLO el nombre de la serie heredaba un vol 8 fantasma (`pack-8` para un cofre de tomos 1-3). Detectado en la prueba en vivo de la cole 4139. Fix: `_strip_series_prefix()` en `_parse_item_table` — antes de buscar el volumen se quita el prefijo del título de la colección (probando también la forma sin sufijo parentético, "InuYasha (Kanzenban)" → "InuYasha"); lo que queda es el nº del tomo o nada. Las keys sintéticas stale del corpus (2 items Kaiju) se repararon + `backfill_cluster_key` (la invariante CLKEY del validador las detectó al instante — el cluster_key lmc se deriva de la URL). **M1 (Fable 2026-07-08): el mismo bug vivía en el helper GENÉRICO `_extract_volume` de `manga_watch.py`** (usado por `derive_series_metadata` y el tier fuzzy), que sólo tenía el fix en `listadomanga_collections.py`. `_extract_volume("Kaiju Nº8 nº16")` daba `8`. Fix generalizado: el helper prefiere el ÚLTIMO match de cada patrón (el volumen va DESPUÉS del nombre) — `pat.findall(title)[-1]` en vez de `pat.search`. Ver gotcha #136.

75. **Cofres listados INLINE dentro de "Números editados" (2026-06-11).** El gate "sección regular sin premium → descartar entera" se tragaba cofres que listadomanga lista como un item más de la sección regular ("Cofre de 2 tomos", caso real Boichi cole 6240 — el boxset solo existía en el corpus porque el calendario plano legacy lo había capturado; el parser de colecciones daba 0 items). Fix: antes de descartar la sección, se buscan items cuyo `description_extra` matchee `INLINE_BOX_RE` (`\bcofres?\b`); si los hay, se emiten SOLO esos (kind `box`, título enriquecido con el desc_extra como los packs, hint "Box Set") y el resto de tomos regulares se sigue descartando. No confundir con el formato "en cofre" de página entera (emisión box-level, gotcha #41) ni con la sección "Cofres de regalo".

76. **Label de "autor" horneado en el VALOR del campo (`"Autori: Kentaro Miura"`) — `clean_author()` en los puntos de serialización (2026-06-12).** Algunas fuentes (Panini IT, JSON-LD sucio) repiten el label dentro del valor del campo author. Fix de mecanismo: `clean_author()` en manga_watch.py quita prefijos `Autori:/Autor:/Author:/By:/著者：…` (sólo CON dos puntos — "Byron"/"Diana" no se tocan) y se aplica en los 3 puntos donde un Candidate se serializa a JSON (content_hash payload, fila del flush, candidate_to_json). 196 items legacy limpiados in-place. Test: `test_clean_author_strips_baked_labels`.

77. **`list.sort(key=…)` en CPython VACÍA la lista durante el sort — un `key` que itera la misma lista ve `[]` (2026-06-12).** Caso real: el scoring de `merge_isbn_duplicates` calculaba `_evidence(serie, group)` dentro del `key=` de `group.sort()` → la evidencia era siempre 0 → ganaba el candidato equivocado en silencio ("Rave" sobre "Marco Polo"). Patrón obligatorio: PRECOMPUTAR los scores en un dict `{id(item): score}` ANTES del sort y usar `key=lambda it: scores[id(it)]`. Sin error ni warning: CPython solo tira ValueError si MUTÁS la lista, leerla devuelve la lista vacía.

78. **Sitios Next.js App Router (RSC): el catálogo vive en `__next_f`, NO en el DOM — extractor dedicado por dominio (2026-06-12).** Caso Square Enix Manga US (release-calendar): el DOM solo renderiza ~10 items del mes visible, pero el payload `self.__next_f.push([1,"…"])` embebido en `<script>` trae el catálogo COMPLETO (~488 productos). `extract_generic_html` decompone los `<script>` antes de buscar productos → 0 cards para siempre; `kind: js` tampoco ayuda (Playwright también ve solo el mes visible) y `selectors:` capturaría solo ~10. Patrón de fix: extractor dedicado registrado en `_SITE_EXTRACTORS` (manga_watch.py) — hook por substring de dominio que corre sobre el HTML CRUDO antes del flujo genérico, con falla silenciosa a `[]` (cae al genérico). Si otra fuente da "0 cards con html_size grande", revisar si es una app RSC ANTES de intentar selectores. Test del caso: `test_extract_squareenix_rsc_payload`.

79. **`st_mtime_ns` como Number rompe el guard optimista de cover-preview — 409 espurio en CADA save (2026-06-12).** El guard anti-race de `cover_preview.json` (introducido 2026-06-11) enviaba el `st_mtime_ns` (~1.8e18) como entero JSON; JavaScript redondea todo entero > 2^53 (~9.0e15) al double más cercano (spacing ~256 ns en esa magnitud), así que el `expected_mtime` que el frontend devolvía casi nunca coincidía con el del disco → "La cola cambió en el servidor (otro proceso la actualizó)" al aprobar/rechazar cualquier candidata, sin que existiera concurrencia real. Fix de mecanismo: el token viaja como STRING opaco end-to-end (`_mtime_token()`/`_mtime_matches()` en serve.py; el frontend lo guarda y lo devuelve tal cual, sin parsearlo). Compat: si un cliente viejo manda un Number, se compara en espacio double (`float(expected) == float(current)`). REGLA: nunca mandar `st_mtime_ns` (ni cualquier entero > 2^53: ids de snowflake, nanotimestamps) como Number JSON hacia un navegador — siempre string. Tests: `tests/test_cover_preview_mtime_guard.py`.

80. **`release_date` se guardaba con el formato CRUDO de la fuente — `normalize_release_date()` en los puntos de asignación (2026-06-12).** `extract_release_date()` devolvía el match textual sin normalizar y el JSON-LD (`datePublished`) se copiaba tal cual, así que al corpus entraban DD/MM/YYYY (label-pairs de fuentes EU: Star Comics IT, Pika FR, Dynit IT, Glénat FR, Ramen Para Dos ES, Manga Dreams IT — 131 items), `2023/09/27 10:00:00` (JSON-LD de tiendas JP, hora = inicio de venta en tienda), `2026年04月08日`, `DD.MM.YYYY` y mes textual FR ("2 juillet 2025"). Fix de mecanismo: `normalize_release_date()` en `scripts/manga_watch.py` — normaliza a ISO respetando granularidad parcial (YYYY / YYYY-MM se quedan: NUNCA inventar día/mes), valida rangos vía `datetime.date` (32/05 o 31/02 → se devuelve SIN tocar, nunca destruye información), día-primero para `D/M/YYYY` con swap solo si el segundo componente >12 (US inequívoco). Aplicada en: `extract_release_date()` (todos los matches), `fetch_metadata_from_detail()` (DESPUÉS de la excepción del componente horario, que necesita ver la hora cruda), las 2 asignaciones card-level desde `extract_schema_org_product`, el fallback RSS `published_at` y el meta de AnimeClick. OJO: `extract_schema_org_product` sigue devolviendo el valor CRUDO a propósito (la excepción tienda-vs-発売日 lo necesita); normalizar ahí rompería esa lógica. Corpus legacy: retrofit `normalize_release_dates.py` (131 DMY convertidos; `--all-formats` para 年月日/datetime/textual que siguen reportados sin tocar). Tests: `test_normalize_release_date_*` en `tests/test_extraction.py`.

81. **Claves de agrupación con no-ASCII: homoglifo cirílico y CJK crudo en `series_key`/`edition_key` (2026-06-12).** Dos canónicas acuñadas por el LLM del enrich skill entraron al corpus con caracteres no-ASCII: `taihо-to-stamp` (la "о" es CIRÍLICA U+043E, visualmente indistinguible) y `maku-ga-oriru-to-bokura-wa-番` (CJK crudo). `_slugify_kebab` no era el origen (su regex ya descarta no-ASCII) pero PERDÍA letras con homoglifos — NFKD no descompone cirílico, así que "Taihо" daba "taih" — y nada sanitizaba las claves que NO derivan de él: las canónicas de `series_aliases.yml` (inyectadas vía `canonical_series_key`) y las propuestas por el LLM del standardize. Fix (mecanismo, 3 capas): (1) `_slugify_kebab` mapea homoglifos cirílicos/griegos → ASCII (`_HOMOGLYPH_TO_ASCII`, antes de NFKD); el CJK se descarta de forma controlada (actúa como separador, strip de bordes — "Maku ga Oriru to Bokura wa 番" → "maku-ga-oriru-to-bokura-wa"). (2) `sanitize_key_ascii()` (público, idempotente sobre claves limpias) se aplica en las DOS fronteras de claves no-derivadas: la resolución del YAML en `derive_series_metadata` (paso 3b de manga_watch.py) y las claves del LLM en `standardize_apply.py` (tier1 + merge; una clave que se vacía al sanitizar queda pending — el caller decide). (3) Datos: las 2 canónicas del YAML renombradas a ASCII (la clave vieja quedó como alias) y los 2 items reparados (series_key/edition_key/cluster_key/slug), con backup. Verificación: `backfill_cluster_key --dry-run` 0 refrescos, `validate_corpus` verde. Los `cluster_key` de tier `fuzzy:` siguen embebiendo título crudo japonés — eso es BY DESIGN (no son slugs). Tests: `test_slugify_kebab_homoglyphs_and_cjk_discard`, `test_sanitize_key_ascii_grouping_keys`.
82. **Dígitos full-width JP (０-９) en títulos → `volume`/`cluster_key` contaminados (2026-06-12).**
    `\d` en regex unicode de Python MATCHEA los dígitos full-width U+FF10-FF19, así que los
    patterns de `_extract_volume` capturaban el dígito crudo: "学園アイドルマスター ＧＯＬＤ ＲＵＳＨ
    特装版 ７" (JP - Sanyodo) quedaba con `volume: "７"` y `cluster_key`
    `edition:…-special-jp|７` — el MISMO producto con "7" ASCII de otra fuente nunca fusionaría.
    Fix de mecanismo: `FULLWIDTH_DIGITS_TABLE` en `manga_watch.py` es la FUENTE ÚNICA de la
    tabla ０-９→0-9 (`generate_slugs.py` la importa en vez de duplicarla), aplicada en 4 puntos:
    (1) `_extract_volume` traduce el título antes de matchear; (2) `_normalize_series_name`
    también (sin esto el strip del volumen ASCII no matchea el "７" del texto); (3)
    `derive_cluster_key` traduce el campo `volume` del item en los tiers `edition:` y `lmc:`
    (el campo puede venir de un parser de fuente o del LLM del standardize, no solo de
    `_extract_volume`); (4) `candidate_to_json` traduce `vol` antes de escribir el row (frontera
    que cubre `candidate.volume` de los wikis). Corpus: 2 items reparados (volume +
    `backfill_cluster_key.py`), `validate_corpus` verde. Tests:
    `test_extract_volume_fullwidth_digits`, `test_derive_cluster_key_fullwidth_volume_normalized`.

83. **`http.client` aborta con ">100 headers" en sitios con decenas de Set-Cookie (2026-06-12).**
    `egmont-shop.de` responde con más de 100 headers HTTP y el límite default de
    `http.client._MAXHEADERS` (100) hacía fallar la fuente con
    `ProtocolError('Connection aborted.', HTTPException('got more than 100 headers'))`.
    Fix global en manga_watch.py (tras los imports): `http.client._MAXHEADERS = 200`.
    Inocuo para el resto de fuentes. Si otra fuente da este error exacto, NO es el sitio
    caído — es este límite.

84. **Paginación JS (`Javascript:Page_Set('2')`) invisible para la estrategia 4 del paginador (2026-06-12).**
    `find_next_page_url` estrategia 4 (incrementar `?page=N`) exigía que `page=N+1`
    apareciera en el href de algún anchor — los sitios ASP.NET/osCommerce (Aladin KR)
    paginan con `Javascript:Page_Set('2')` y nunca cumplen esa evidencia, así que solo
    se scrapeaba la página 1 (25 de 428 resultados). Fix: la evidencia aceptada ahora
    incluye hrefs `javascript:` de paginación con el número N+1 como argumento (regex
    `^javascript:[\w.]*pag\w*[_.]?\w*\(['"]?N\+1['"]?\)`). Requisito: la URL fuente debe
    llevar `&page=1` explícito para activar la estrategia 4. El sitio debe aceptar
    `?page=N` por GET aunque sus links usen JS (verificado en Aladin).

85. **El extractor genérico de clusters puede TRUNCAR el título y el gate rechaza todo (2026-06-12).**
    En mangastore.pl el cluster extractor capturaba "Atelier spiczastych kapeluszy" sin
    el sufijo "(twarda okładka)" — la señal hardcover se detectaba por otro campo pero el
    GATE evalúa el TÍTULO → 59/63 candidatos rechazados como regular_tomo. Con selectores
    explícitos (`div.Okno.OknoRwd` + `a[href*='-p-']:not(.Zoom)`) → 63 reportables.
    REGLA: si una fuente da "candidatos con señales" altos pero el gate descarta >80%,
    sospechar título truncado ANTES que señales débiles — comparar el título del
    diagnostic JSON con el real del sitio.

86. **`--only-source` era single-valued: repetirlo pisaba en silencio los anteriores (2026-06-12).**
    Una ingesta dirigida con 10 flags `--only-source` solo corrió la ÚLTIMA fuente
    (argparse default: last-wins). Fix: `action="append"` + matching por set con error
    explícito si algún nombre no existe. Síntoma histórico: el log muestra `[1/1]` cuando
    esperabas N fuentes.

87. **El union-merge de `images[]` descartaba el `local` del upsert post-mirror (2026-06-12).**
    El dedup por (kind, url) preservaba ÍNTEGRO el entry viejo — diseñado para que un
    re-scrape sin descarga no borre el `local` existente, pero el caso inverso rompía: los
    wikis con flush incremental escriben la fila ANTES del mirror (local=""), y el upsert
    final post-mirror (local="sha.jpg") se descartaba como duplicado → ~1700 items con la
    imagen EN DISCO pero la fila sin referencia (parecían "sin foto" en el dashboard).
    Fix: en colisión de clave, el entry conservado RELLENA sus campos vacíos (local,
    description) con los del duplicado — sticky en ambas direcciones. Reparación del
    corpus: `mirror_images.py --no-gc` (religa por nombre determinístico sha256(url)[:16]).
    Test: `test_append_jsonl_images_merge_backfills_local`.
    **ACTUALIZADO (Fable 2026-07-08, hallazgo A9):** el arreglo original vivía SÓLO en
    `append_jsonl`; `merge_cluster` tenía su propia union de `images[]` que dedupeaba por
    `_img_stem` (sin kind), NO rellenaba `local`/`description` y aliaseaba el dict del
    miembro — y como `consolidate_by_cluster` corre en CADA `append_jsonl`, el bug seguía
    vivo en el camino de cluster. Ahora AMBOS sitios delegan en la primitiva única
    `_union_merge_images()` (dedup por `(kind, _img_stem(url))`, fill bidireccional de
    `local`/`description`, `dict(im)` sin aliasing). Regla: NUNCA reimplementar la union
    de imágenes; usar `_union_merge_images`. Tests:
    `tests/test_merge_fixes_20260708.py::test_a9_*`.

88. **Placeholders de lazy-load como ARCHIVO real (no data-URI) → el loader entraba como portada (2026-06-12).**
    `_img_to_url` prueba `src` primero y solo salteaba `data:` URIs. Mangarden sirve
    `src="/gfx/pol/loader.gif"` (archivo real) con la portada en `data-src` → 167/215
    items PL "con portada" = el loader, que `_score_image`/el mirror terminaban
    descartando → sin foto. Fix: `_LAZY_PLACEHOLDER_RE` saltea nombres EXACTOS de
    placeholder (loader/loading/blank/placeholder/spacer/spinner/transparent/pixel/
    dummy/no-image/default + sufijo numérico opcional) para caer al data-src. OJO: sin
    wildcard tras el nombre — "lazy.jpg" o "grey-edition.jpg" pueden ser imágenes
    reales. Test: `test_extract_image_url_skips_lazy_placeholder_file`.

89. **URLs/referers con no-ASCII rompían el descargador de imágenes con UnicodeEncodeError (2026-06-12).**
    `http.client` codifica la request line y headers en latin-1; las URLs de yaakz
    (slugs thai) y jd-intl (paths chinos) crasheaban `download_image` — y como
    `UnicodeEncodeError` no es `RequestException`, el except no la capturaba y MATABA
    el proceso entero de mirror_images.py a mitad de corrida. Fix: `requote_uri` sobre
    URL y referer (el referer se omite si sigue no-latin-1) + `except (RequestException,
    UnicodeError)`. Relacionado: el API de yaakz devuelve `images` como STRING (una URL),
    no lista — `imgs[0]` tomaba el primer CARÁCTER ("h") como URL; fix en el mapper
    (`storefront_json._yaakz_map`).

90. **Placeholders "no cover" de cada tienda entraban como portada real (2026-06-12).**
    Crew CZ sirve `src=/static/crew/img/ph/komiks.png` (ph = placeholder) con la portada
    real en `data-src`; Aladin KR usa `19book_150cover.jpg` como default; Shopify IT
    `img-non-disponibile`; Star Comics `no_cover_2021.jpg`; Amazon el píxel transparente.
    ~53 items del corpus tenían estos placeholders COMO portada (el dashboard los mostraba
    "sin foto" o con la imagen genérica). Fix doble: (1) `data-src`/`data-original` se
    prueban ANTES que `src` en `_img_to_url` — cuando coexisten, data-* es la imagen real
    por definición del patrón lazy; (2) los nombres de placeholder nuevos se agregaron a
    `IMAGE_URL_BAD_PATTERNS`. Señal de diagnóstico: la MISMA url de portada repetida en
    ≥3 items de una fuente = placeholder casi seguro (sweep:
    `Counter(images[0].url)` sobre el corpus). Reparación: null + `backfill_metadata
    --only image_url` (las páginas de detalle traen la cover real) + mirror.

91. **Países fuera de `_COUNTRY_SLUG_MAP` → sufijo fallback NO idempotente en edition_key (2026-06-12).**
    `_country_slug()` cae a "primeras 4 letras" para países desconocidos (cheq/turq/core/
    polo/hong tras la expansión de países), pero `_has_country_suffix()` de
    fix_edition_country validaba el tail SOLO contra los valores del mapa → no reconocía
    el fallback y cada corrida del enforcer apendeaba OTRO sufijo:
    "…-cheq-cheq-cheq" tras 3 corridas (503 keys afectadas: core ×253, polo ×233…).
    Fix doble: (1) mapa completado (corea del sur→kr, polonia→pl, chequia→cz, turquía→tr,
    hong kong→hk, china→cn, indonesia→id); (2) `_has_country_suffix(ek, country_slug)`
    acepta además el código COMPUTADO del país del item — idempotente aunque el país no
    esté en el mapa. REGLA: al abrir un país nuevo, agregalo al mapa EN EL MISMO TURN.
    Reparación: strip de sufijos fallback repetidos + re-sufijo correcto +
    backfill_cluster_key + slugs (enforcer); verificado idempotente (2× → byte-idéntico).

92. **Política de títulos: title = nombre OFICIAL → re-expone keywords de bonus en filtros (2026-06-12).**
    Decisión de producto: el `title` es el nombre oficial con que la editorial publica el
    producto — NUNCA se traduce, NUNCA se renombra a la serie canónica y NUNCA se le inyecta
    el tipo de edición. El nombre reconocible vive en `series_display` (canónico) y la
    búsqueda resuelve aliases multilingües (`data/series_aliases.json`, exportado por
    `export_series_aliases.py` en cada build_web). El skill standardize y `standardize_apply.py`
    ya no escriben `title` (el campo `title_standardized` quedó RETIRADO del schema; migración:
    `restore_official_titles.py`, one-shot por item vía `title_restored_at`).
    **Consecuencia en filtros**: los títulos oficiales JP/IT nombran el BONUS de la edición
    ("夏目友人帳 フィギュアストラップ付き特装版", "テラフォーマーズ(21)特装版 DVD LIMITED EDITION",
    "Ediz. variant. Con acrylic standee") y los patterns HARD de figura/DVD/standee/bundle
    los mataban. Fix: tier `_NON_MANGA_HARD_UNLESS_BONUS` + `_bonus_context_near()` — el
    match NO descarta si hay marcador de inclusión PEGADO al match (付/同梱 hasta 12 chars
    después; con/with/avec/mit/+ en ventana corta; 特装版/同梱版 en cualquier parte — NO 限定版
    a secas, que también lo usan los Blu-ray BOX de anime). El marcador debe ser posicional:
    "神の庭付き楠木邸 Blu-ray BOX" tiene 付き en el NOMBRE de la obra y sigue siendo anime.
    También: `図鑑(?!未掲載)` (図鑑未掲載 describe el bonus) y `(?<!限定版)プレミアムBOX`
    (限定版プレミアムBOX es un manga premium box, no idol box). Tests:
    `test_is_likely_manga_bonus_context_*`. Una limitación conocida de la migración: algunos
    `title_original` viejos fueron pisados por retrofits históricos (`fix_listadomanga_titles.py`
    escribía title_original), así que esos items conservan el mejor título disponible, no
    necesariamente el oficial original. Complemento: `recover_lost_jp_titles.py`
    recuperó los nombres reales de los items JP con título "generado" (openBD por ISBN +
    re-fetch Playwright de mangavariant — el sitio quedó tras sgcaptcha, ver su ficha);
    marcadores agregados tras esa pasada: `w/` (= with, listings EN) y excepción
    "Gangan Joker" en comics_blacklist (revista, contiene "Joker").

95. **Título de edición DUPLICADO en dos idiomas + volumen perdido (skill viejo de standardize, 2026-06-13).** _(renumerado de #93 → #95 el 2026-06-13: colisionaba con el #93 de store_bonus, que es el referenciado en git/commits.)_
    Síntoma reportado por el owner: "Pájaro que trina no vuela no Special Edition Edición Especial"
    — sin el número de volumen y con el tipo de edición repetido en inglés y español.
    CAUSA (dos bugs encadenados): (a) el skill VIEJO de standardize (pre-política de títulos
    #92, 2026-06-12) reescribía `title` traduciendo la edición a inglés ("Edición Especial" →
    "Special Edition") y destruía el marcador de volumen ("nº9" → "no", perdiendo el 9); ese
    título mangleado quedó guardado como `title_original`, y `restore_official_titles.py` lo
    propagó de vuelta a `title`. (b) `normalize_display_title` (el normalizador de display de
    listadomanga) solo removía "Edición Especial" en ESPAÑOL antes de re-apendar el marcador,
    NO la frase en inglés → "…Special Edition" + "Edición Especial" = marcador duplicado.
    FIX DE MECANISMO (durable): `_ESP_ANY_RE` ahora también matchea "Special Edition" (EN), así
    el marcador nunca se duplica venga de donde venga; además se completó `_KIND_MARKER` con
    `collector` → "Edición Coleccionista". FIX DE DATOS LEGACY (one-shot):
    `fix_corrupted_lm_special_titles.py` reconstruye el título de los tomos de listadomanga
    cuyo `title` arrastra un qualifier de edición en inglés, leyéndolo de la fuente CONFIABLE
    — el `description`, que preserva el `collection_title` scrapeado con su `nº{vol}` y la
    edición en español — reusando `normalize_display_title` (única fuente de verdad). Restaura
    el volumen y deja un solo marcador. Estos títulos violaban la invariante DURA `TITLE` de
    `validate_corpus.py`. La duplicación EN+ES era una firma confiable porque los títulos
    limpios de listadomanga llevan el marcador en español, nunca en inglés. Tests:
    `test_lmc_normalize_display_title` (casos EN). FALLBACK por hermano: cuando el
    `description` quedó contaminado por un merge cross-source (metadata de tienda en vez del
    `collection_title`, caso "Fruits Basket Collector's Edition" — su `description` traía la
    paginación de fnac), el título se reconstruye tomando el STEM de un tomo HERMANO limpio de
    la misma colección (su nombre scrapeado, no el canónico) + el volumen propio →
    "Fruits Basket 1"/"Fruits Basket 3", consistente con los hermanos vol 2-12 (en esa
    colección TODOS los tomos son kind=regular: la edición coleccionista es la colección
    entera, no hay regular vs especial coexistiendo, así que el tomo NO lleva marcador). Total:
    18 items (16 desde description + 2 vía fallback).

93. **Bonus de TIENDA (店舗特典) embebido en el título oficial → campo `store_bonus` (2026-06-12).**
    Corolario de la política de títulos (#92): el `title` es el nombre OFICIAL, pero los
    retailers japoneses le pegan SU perk de compra entre brackets —
    "数学ゴールデン 2(描き下ろしイラストカード)【楽天ブックス限定特典】" = "si compras en Rakuten
    te llevas una postal". Eso NO es el nombre del producto (otro retailer da otro bonus);
    no debe ocupar el título en el GRID. Se separa al campo `store_bonus`, visible solo en
    el DETALLE ("🎁 Bonus de tienda"). Helper `mw.split_store_bonus(title) → (clean, bonus)`
    (fuente única: scraper en `candidate_to_json` + retrofit `extract_store_bonus.py`).
    Señal de ALTA precisión: el bracket japonés 【…特典…】 (特典 = "perk de compra"); 222 en
    el corpus, CERO con marcador de edición dentro. Guards: (a) NO tocar
    【…特装版/限定版/初回限定…】 (eso ES la edición, no un bonus — `_STORE_BONUS_EDITION_GUARD`);
    (b) el paréntesis adjacente sólo se consume si describe el bonus, NO si es el volumen
    ("年の差婚(3)【…特典】" conserva el "(3)" — `_VOLUME_PAREN_RE`). `title_original` conserva
    el nombre oficial COMPLETO (con el bonus). Idempotente. NO aplica a las colas de tienda
    en inglés de Mangavariant ("- Animate cover") que SÍ son la identidad de la variante.
    Tests: `test_split_store_bonus_*`.

94. **Selector genérico que captura la TARJETA entera → título con cola de e-commerce (2026-06-13).**
    Auditoría de calidad de títulos: 3 fuentes config-by-YAML (selector genérico) guardaban en
    `title` toda la tarjeta del producto, no sólo el nombre. **KR - Aladin** (367 items):
    "{título} {vol} (한정판) - {bonus} {autor}(지은이) | {editorial}(만화) | {fecha} {precio} →
    {oferta} (할인), 마일리지 … 세일즈포인트". **IT - Funside** (~58): "… - VARIANT Prezzo normale
    €X Prezzo di vendita €X … Aggiungi al carrello", a veces con prefijo "Aggiungi al carrello
    [Confrontare]" y sufijo de tienda "GAMES ACADEMY FUNSIDE / POPSTORE". **IT - Dynit** (2):
    "… #03 Disponibile dal: DD/MM/YYYY Dynit". Fix de mecanismo en `clean_title` (única fuente
    de verdad, beneficia scrape nuevo + retrofit): cortes IT (Prezzo/Disponibile dal/sufijo
    FUNSIDE) en `TITLE_JUNK_PATTERNS`, y `_strip_korean_retailer_tail` para la cola coreana
    (corta en el marcador de edición "(…한정판)"/"한정판 [박스] [세트]" o, si no hay, en el
    autor-rol/pipe-editorial/precio/세일즈포인트; sólo corre si hay Hangul). Limpieza del
    histórico: `clean_titles.py` (433 títulos). Tests: `test_clean_title_strips_korean_retailer_tail`,
    `test_clean_title_strips_italian_price_block`, `test_clean_title_strips_funside_cart_prefix`.
    Una segunda pasada de la auditoría sumó dos catches genéricos a `clean_title` (25 items):
    **entidades HTML sin decodificar** ("Collector&#039;s box", "Girls &amp; Weapons" →
    `html.unescape`) y **badges de estado de tienda TH** (IPM/Siam: "(PRE-ORDER)" como prefijo
    y "[NEW]" embebido — el `[NEW]` consume el espacio que lo precede para no pegar palabras).
    Tests: `test_clean_title_decodes_html_entities`, `test_clean_title_strips_thai_status_badges`.
    **Pendiente** (no bloqueante): afinar los `title_selector` del YAML para capturar sólo el
    link del producto — hoy el saneo depende de `clean_title` como red de seguridad.
    La misma auditoría destapó otros dos defectos de título, ambos arreglados de raíz:
    (b) **Traducción prohibida del tipo de edición**: `format_especial_title` (en
    `fix_especial_title_order.py`, paso del enforcer) matcheaba el inglés "Special Edition"/
    "Special" y SIEMPRE emitía la forma española "Edición Especial" → un título japonés/
    italiano/inglés terminaba mezclado ("葬送のフリーレン 15 Edición Especial"), violando la
    política de títulos (NO traducir). Fix: `_ESPECIAL_REORDER_RE` ahora sólo matchea español;
    el inglés se deja intacto. Limpieza del histórico: `restore_mistranslated_especial.py`
    restaura `title = clean_title(title_original)` para los 85 items traducidos (excluye
    listadomanga, cuyo title_original está corrupto — gotcha #95). (c) **Duplicación de frase
    de edición**: `fix_title_edition_words.py` ahora colapsa también frases de edición CJK
    repetidas verbatim ("特装版 特装版", "オリジナルバッジ付き限定版 ×2") gateadas por marcador de
    edición —para NO tocar nombres de obra con repetición legítima (デッドデッド…, Kuma Kuma
    Kuma Bear, New York New York)— y ordinales repetidos ("30TH 30th" → "30th"). Tests:
    `test_format_especial_title_order`, `test_fix_title_edition_words_collapses_real_dups`.

96. **Revista-paraguas como SUFIJO descriptivo → 9 productos legítimos borrados en el cleanup (2026-06-13).**
    Síntoma (auditoría): `filter_collectible.py` (fase cleanup del pipeline canónico) borraría
    9 items estandarizados — 8 portadas variantes de Mangavariant ("Sakamoto Days — The Order -
    Shonen Jump", "Silver Spoon — Vol.1 - Shonen Sunday", …) y 1 revista de UNA serie
    ("ONE PIECE magazine … 週刊少年ジャンプとONE PIECE 020"). CAUSA: `is_collectible_edition` hacía
    `_UMBRELLA_JP_MAGAZINE_PATTERN.search(title)` a secas (regla 0b, ANTES de mirar
    `signal_types`), así que el nombre de la revista como SUFIJO descriptivo daba
    `(False, "umbrella_magazine")`. Como `umbrella_magazine` es HARD_REASON en
    `filter_collectible.should_reject`, IGNORA `standardized_at` → destrucción de datos en el
    camino más frecuente. FIX DE MECANISMO (durable): nuevo helper
    `_is_umbrella_magazine_title(title, signal_types)` que distingue "ES la antología" de "la
    menciona": (a) si `variant_cover` ∈ signal_types ⇒ es portada variante de una serie, la
    revista es descriptiva ⇒ NO umbrella; (b) el match de la revista debe arrancar al INICIO
    del título (`m.start() <= 3`, con margen para prefijos "週刊"/"月刊") — la antología real
    lleva su nombre como sujeto inicial ("Weekly Shōnen Jump 2023 No.42", "週刊少年ジャンプ …"),
    los descriptores-sufijo tras "<Serie> — Vol.N - …" no. La defensa por URL
    (`_UMBRELLA_MAGAZINE_URL_PATTERN`, revista ATOM) queda intacta. Tras el fix, el dry-run de
    `filter_collectible` pasa de 10 a 1 rechazo (el residuo es el bug de Aladin KR `한정판`,
    aparte). Test: `test_is_collectible_edition_keeps_variant_cover_with_magazine_suffix` (los 9
    títulos reales + antología real que sigue rechazándose).

97. **Fuentes sirven un PLACEHOLDER cuando no tienen portada → se espeja como si fuera la cover (2026-06-13).**
    Síntoma: cards con un pixel 1×1, un cuadro blanco o una imagen "no disponible" en vez del 📚.
    CAUSA: cuando una fuente no tiene la carátula de un ISBN/producto, en vez de 404 devuelve una
    imagen genérica — Amazon un GIF 1×1 (`images-na.../P/<ISBN>...jpg`), listadomanga/otros CDNs un
    blanco, Penguin Random House "Cover Coming Soon", Funside "Immagine non disponibile", SocialAnime
    "Image coming soon". El mirror la baja igual (pasa el chequeo de magic bytes: ES una imagen
    válida) y queda como `images[0]`. Rechazarla solo en `download_image` NO alcanza: la `url` remota
    seguiría como fallback y la card cargaría el placeholder remoto igual. FIX: detector de fuente
    única `image_store.placeholder_reason()` — estructural (lado ≤ 8 px ⇒ `tiny`; std global de
    luminancia < 3 ⇒ `solid`; no-abre/0 bytes ⇒ `broken`) + firmas de contenido
    (`data/placeholder_signatures.json`, sha1) para los que llevan texto/logo y no caen por baja
    entropía. El retrofit `purge_placeholder_images.py` quita la ENTRY completa de `images[]` (y las
    refs en `sources[]`), re-marca la portada por posición y manda el archivo a cuarentena
    `_orphans/`. Corre como paso **[4i]** del pipeline (delta y full), así no reentra al build.
    SUTILEZA: "contenido idéntico repetido" NO es señal suficiente — la portada real de *BECK 16*
    aparecía idéntica en 3 items (cross-cover, otro bug); el detector la deja intacta (std 66 ≫ 3)
    porque solo borra por las reglas estructurales/firma, nunca por repetición. Para agregar un
    placeholder con texto nuevo: pegá su sha1 en `placeholder_signatures.json` (no toca código).
    Tests: `tests/test_purge_placeholder_images.py`.

98. **El px count sobreestima la calidad → se propone una portada CHICA y BLANDA que se ve pixelada (2026-06-13).**
    Síntoma: el panel de portadas propone reemplazar una portada chica pero limpia (ej. listadomanga
    14k px) por una candidata de "mejor resolución" (ej. casadellibro 80k px, ×5.7) que se ve FEA y
    pixelada. CAUSA: tanto el script (`fetch_better_covers._try_candidates`) como el skill
    (`sc_validate.py`) elegían "mejor" por ÁREA EN PÍXELES (más px = mejor) y validaban identidad con
    `_same_cover` (que confirma que es la MISMA portada, NO su calidad). Un escaneo sobre-comprimido o
    upscale de la misma portada tiene más px pero menos detalle real, pasa el AND-gate de identidad y
    gana por px. SUTILEZA CLAVE: la nitidez sola NO distingue el caso malo — la casadellibro 80k mala
    (`_detail_ratio` ≈ 0.10) y una whakoom 637k buena miden el MISMO ratio; hasta una planeta de 6M px
    puede medir ~0.10 (escaneo borroso). Lo que cambia es el TAMAÑO: la chica se muestra AGRANDADA
    (modal/tarjeta la upscalean) y ahí la blandura salta a la vista; la grande se muestra REDUCIDA y se
    ve nítida. FIX (fuente única, gate en `fetch_better_covers`, lo llaman los dos caminos): una
    candidata se rechaza si es CHICA (`< SOFT_GUARD_PX` = 150k px) **Y** BLANDA
    (`_detail_ratio < DETAIL_RATIO_MIN` = 0.115). `_detail_ratio` = fracción de energía en la octava
    superior, medida a un tamaño de display común (lado largo 384px): residual del roundtrip
    downscale½→upscale normalizado por la stddev de grises; una portada nítida concentra mucho detalle
    al reducir a 384, un escaneo blando casi nada. Un umbral de ratio aplicado a CUALQUIER tamaño daba
    falsos positivos en escaneos grandes legítimos (por eso el guard de px). Calibrado con casos reales:
    casadellibro 78-90k ratio 0.05-0.10 → rechazadas; whakoom/norma/buscalibre buenas ≥150k px o ratio
    ≥0.12 → pasan. Retrofit de limpieza de la cola ya armada: `prune_soft_cover_candidates.py`
    (re-aplica el MISMO gate a `cover_preview.json`, idempotente; quitó 56 candidatas chicas+blandas de
    569 entries). Tests: `tests/test_detail_ratio.py`.

99. **El calendario plano + estandarización inventaban una EDICIÓN ESPECIAL que no existe, con la foto del bonus de OTRO tomo (2026-06-14).**
    Síntoma (caso semilla): el item "Edens Zero Especial 23 Edición Especial" (artbook) — la página
    real `coleccion.php?id=3094` NO tiene especial del tomo 23 (es un tomo REGULAR), y la foto que
    arrastraba era el "Posavasos imantado" que es el regalo de 1ª edición de los tomos 2 y 3. Dos errores
    en un solo item: edición inventada + foto del bono de otro volumen. CAUSA: el módulo plano del
    calendario (`scripts/wikis/listadomanga.py`) sólo conoce el texto del enlace del día (era literal
    "Edens Zero nº23"); NO conoce ediciones — por eso su `fetch_detail_metadata` deja la imagen vacía en
    páginas multi-tomo (gotcha #28). Pero al pasar esos items legacy por la estandarización (LLM,
    `standardized_at`), algunos se "derivaron" como Edición Especial / Artbook inexistente y se les pegó
    la foto de un extra (cofre/posavasos/miniartbook) de otro tomo de la misma colección. El parser de
    colecciones (`listadomanga_collections.py`) es la AUTORIDAD de cada `/coleccion?id=N`: si ahí no hay
    tal especial, era fantasma. SUTILEZA CLAVE — el cruce calendario-vs-colecciones NO es autoridad para
    borrar: tiene **falsos positivos en ambos sentidos**. (a) Ediciones especiales REALES (orange nº7,
    "El chico que me gusta no es un chico" nº3, Hosaka nº1, Vanitas nº11…) — el item del calendario es
    correcto, NO se borra. (⚠️ Acá se creyó ver un bug aparte de "under-capture del parser de
    colecciones"; **era falsa alarma de medición** — el parser SÍ las captura y `consolidate` las fusiona
    con el item del calendario; ver gotcha #101.) (b) Artbooks/cofres/fanbooks standalone cuya portada ES legítimamente el
    bonus que regalan (Witch Hat ArtWorks/Illustrations, Promised Neverland Escape, Princess Jellyfish,
    Réquiem fanbook, Quintillizas mini-artbook) — mismo objeto físico, misma imagen, NO es robo. Por eso
    cada candidato se VERIFICÓ a mano contra la página viva antes de tocarlo. FIX: limpieza con
    `scripts/retrofit/remove_phantom_calendar_editions.py` (listas explícitas verificadas: 5 fantasmas
    borrados + 2 fotos robadas quitadas). GUARDA durable: invariante **STOLENIMG** en `validate_corpus.py`
    — warning si la portada (`images[0]`) de un tomo NORMAL es un `extra`/`bonus` de otra fila (excluye
    artbook/cofre standalone, que comparten foto legítimamente). Probada contra el backup pre-fix (marcaba
    los 2 casos) y en 0 post-fix.

100. **La búsqueda del grid ya NO es en vivo + el pipeline está MEMOIZADO → toda mutación in-place de
    `items[]` DEBE bumpear `_dataVersion` (2026-06-14).** El dashboard (`web/index.html`) cargaba ~13k items
    y filtraba en CADA tecla, recomputando `filtered→sorted→editions` (que Alpine, al no memoizar getters,
    corría varias veces por render — el template referencia `editions`/`sorted`/`totalPages` decenas de veces).
    Tipear era casi imposible. FIX en 3 partes: (a) **búsqueda por botón/Enter**: el input edita `searchInput`,
    sólo `applySearch()` commitea a `filters.search`; (b) **haystack precomputado** por item (`i._search`,
    `_indexSearch()`) en vez de armar la cadena en cada item en cada tecla; (c) **memoización** de
    `filtered/sorted/editions` (cache `_pipeCache` por firma de filtros+sort+`_dataVersion`) y de `unique/stats`
    (por `_dataVersion`), en caches **closure NO reactivos** (Alpine no los observa → sin loops). FOOTGUN: la
    cache se invalida por el contador `_dataVersion`; **cualquier código que reasigne o mute `items[]` in-place
    DEBE llamar `_bumpData()`** (y `_indexSearch()` si tocó campos de búsqueda), o el grid queda stale hasta el
    próximo cambio de filtro. Sitios que ya lo hacen: `loadItems`, `loadAliases`, las 3 aprobaciones in-place y
    `saveEdit`. Las acciones que recargan vía `loadItems()` (curación move/merge/remove) quedan cubiertas.
    Medido: pipeline completo ~11 ms (miss) vs ~0.1 ms (hit). Verificado en preview.

101. **"El parser de colecciones se PIERDE especiales" era FALSA ALARMA de medición — el especial está
    en `sources[]`, no en los tags (2026-06-14).** El §9 de la ficha de listadomanga (y el inciso (a) de
    la gotcha #99) reportaban un "under-capture": especiales reales (orange nº7 id=1970, "El chico que me
    gusta no es un chico" nº3 id=5641, A Miyoshi/Hosaka nº1 id=5050, Vanitas nº11) que supuestamente
    `listadomanga_collections.py` "sólo emitía como regular". MEDICIÓN CORRECTA: el parser SÍ los emite
    (reproducido con el debug de §10: id=5050→`especial-1`+`especial-2` en `ventana_id9`; id=5641→
    `especial-3` en `ventana_id14`; id=1970→`especial-7` vía Layout B), y los 3 YA ESTÁN en el corpus con
    DOS fuentes `['ListadoManga (calendario)', 'ListadoManga (colecciones)']` — el item del calendario y el
    especial del parser se FUSIONARON por `cluster_key` (mismo producto, correcto). CAUSA del falso
    positivo: el item fusionado conserva los **tags del calendario** (`category:Manga`), NO `edition:especial`
    ni `coleccion:N`, y su URL **primaria** es la del calendario (el synthetic `item=especial-N` vive en
    `sources[]`). Una consulta que filtra por tag o por la url primaria "no ve" el origen colecciones y
    concluye, falsamente, que el especial no se capturó. REGLA: para preguntar "¿esta /coleccion tiene su
    especial?" hay que escanear `sources[]` (las URLs sintéticas `item=<kind>-<vol>`), NUNCA los tags —
    exactamente como hace `scripts/audit_lista_full_bidir.py` (autoridad de faltantes globales, ya robusto).
    Aplicación del principio del owner: *medir la composición antes de "arreglar"* (cf. §7 de la ficha:
    PAIS marcaba 226 pero 203 eran válidos). NO hubo bug de parser ni se necesitó retrofit. Guarda durable:
    tests `test_lmc_especial_in_non_id1_ventana_is_captured` (#41: especiales en `ventana_id9`/`id14`) y
    `test_lmc_two_especiales_same_section_get_distinct_clusters` (#60: volumen propagado → cluster_keys
    distintos → consolidate NO los fusiona) lockean los mecanismos que SÍ causarían under-capture si
    regresaran.

102. **Edición especial CON cofre listada inline en "Números editados" → mal clasificada como `box` →
    edición box-set fantasma + DUPLICADO del especial (2026-06-14).** El gate de la sección regular no
    premium descarta los tomos sueltos pero deja pasar los cofres listados inline como `box` (gotcha #75,
    "Cofre de 2 tomos"). PROBLEMA: cuando el item inline trae un marcador de edición ADEMÁS del cofre
    ("orange nº7 -queridos amigos- **Edición Especial + Cofre** + Set 4 postales", id=1970), no es un box
    set — es la edición ESPECIAL que incluye un cofre. Clasificarlo como box (a) inventa una edición
    box-set que no existe y (b) DUPLICA el especial del MISMO vol que la sección "Regalos/Cofres"
    (Layout B) emite ("Cofre para tomos 1 a 7", marker "Edición Especial") → dos items (`box-7` +
    `especial-7`, cluster_keys distintos `lmc:N:box:7` vs `lmc:N:special:7` → consolidate NO los fusiona).
    No estalló en el corpus sólo porque orange se scrapeó ANTES de #75; el próximo full re-scrape habría
    metido el duplicado. FIX en la fuente: `_match_inline_edition()` — si la desc del item inline-cofre
    trae "Edición Especial/Limitada" o "Portada/Sobrecubierta Alternativa", se clasifica por ESA edición
    (no como box). Entonces el merge tomo↔extra fusiona el cofre de Layout B (mismo kind+vol) como imagen
    extra → UN solo `especial-N` con la portada de la especial + el cofre en el carrusel. El cofre inline
    SIN marcador de edición ("Cofre de N tomos") sigue siendo box (#75 intacto). Auditado: 0 box fantasma
    en el corpus actual (15 box, ninguno con marcador de edición). Test:
    `test_lmc_inline_edicion_especial_con_cofre_is_especial_not_box`.

103. **Folleto promocional GRATUITO de ListadoManga ("Número Gratuito") colado como edición especial
    (2026-06-14, caso owner Edens Zero id=3112).** ListadoManga titula "(Especial)" a números que en
    realidad son material de marketing que la editorial REGALA: el preview del primer capítulo de una obra
    (Nota: "Preview gratuito de … que incluye el primer capítulo"), un mini-artbook de regalo, un avance
    bundleado con un videojuego (id=2534 Dragon Quest). No son ediciones comprables ni coleccionables, pero
    el título "(Especial)" disparaba `special_edition` y entraban al catálogo. La señal estructural es la
    **línea de PRECIO**: donde un tomo de pago muestra "9,98 €", el folleto muestra "Número Gratuito"
    (univers­al — verificada contra TODA la categoría editorial "Previews" id=332 + promos sueltas: 25
    colecciones, todas con esa línea). El parser (`_parse_item_table`) no la reconocía como precio (sólo
    matcheaba `€|EUR`) y caía en `description_extra`. FIX en la fuente: `FREE_PRICE_PATTERN`
    (`^(?:n[úu]mero\s+)?gratuito$`) — si una línea del item la matchea, `_parse_item_table` devuelve `None`
    y el item se descarta (POR ITEM: una colección con un número gratuito Y números de pago conserva los de
    pago). Delta y full comparten el parser → prevención única. Limpieza del corpus (13 borrados):
    `scripts/retrofit/remove_free_preview_editions.py` (regla A: "Número Gratuito" en `description`; regla
    B: legacy `ListadoManga (calendario)` en colección free-preview verificada por fetch — su description
    quedó malformada y no trae la frase). Caveat: el módulo plano del calendario (`wikis/listadomanga.py`,
    fuera del pipeline canónico) sólo ve el texto del enlace del día, no la línea de precio; si se invoca a
    mano puede re-meter un free preview vía estandarización (mismo origen que gotcha #99). Tests:
    `test_lmc_free_preview_number_is_skipped`, `test_lmc_free_preview_skipped_but_paid_items_kept`.

100. **Estandarizar la imagen al ingresar NO debe tocar los placeholders, o se rompe la detección
    por FIRMA (2026-06-15).** Desde 2026-06-15 toda imagen que entra al espejo se normaliza a un
    "master de display" único (AVIF Q60, lado largo ≤1600px, resize-down + strip de metadata) en
    `image_store.normalize_image()`, llamado desde los 3 cuellos de escritura: `download_image`
    (scrape + retrofits que bajan red), `fetch_better_covers._save_image` (skill de portadas /
    apply / PRH) y `serve._download_image_to_store` (gestor). TRAMPA: `purge_placeholder_images`
    detecta los placeholders CON texto/logo ("Cover Coming Soon", "Immagine non disponibile", etc.)
    por **sha1 del CONTENIDO** (`data/placeholder_signatures.json`). Si normalizáramos un placeholder,
    su sha1 cambiaría y la firma dejaría de matchear → el placeholder sobreviviría como portada (los
    estructurales —1×1, solid— sí sobreviven el re-encode porque dims/std se preservan; los de FIRMA
    NO). FIX: `normalize_image` llama `placeholder_reason(body)` PRIMERO y, si es placeholder, devuelve
    los bytes CRUDOS sin tocar. Orden obligatorio: detectar placeholder → recién después normalizar.
    Reglas extra: solo achica (NUNCA agranda — el upscale AI es manual y aparte, `upscale_images.py`);
    idempotente (un WebP ≤max se devuelve igual, sin pérdida generacional); fallback a los bytes
    originales si pyvips/PIL fallan (nunca rompe el scrape). Backfill del histórico:
    `optimize_images.py` → `migrate_images_to_avif.py` (14.58 GB crudo → 2.37 GB WebP → ~1.5 GB
    AVIF). Decisión del owner: 1600px / **AVIF Q60** (no se soporta el ~6% de navegadores viejos;
    el fallback es next/image transcodificando o la url remota). Tests: `test_normalize_image.py`,
    `test_optimize_images.py`, `test_migrate_images_to_avif.py`.

105. **Los tests de `serve.py` escribían a los datos REALES — `data/feedback.jsonl` se llenó con 670
    filas fantasma (2026-06-21).** `test_serve_merge_items_*` y `test_serve_move_*` seteaban
    `serve.ITEMS_PATH` a un tmp pero **no** `FEEDBACK_PATH`; como `_apply_merge_items`/`_apply_move`
    loguean vía `_log_feedback`, cada corrida de la suite appendeaba 2 filas (urls `https://a`/`https://x`,
    reasons `dup`/`regroup`, todo lo demás en `None`) a la `data/feedback.jsonl` de producción. Tras
    ~335 corridas → 670 filas que parecían un doble-submit del dashboard pero eran **leak de tests**
    (no fue el owner). FIX estructural (fuente única de paths): `serve.py` deriva TODOS sus paths de
    escritura (items/feedback/approvals/edits/dup_decisions/images) de `MANGA_WATCH_DATA_DIR`
    (default `ROOT/data` → prod idéntico). Un fixture **autouse** en `tests/conftest.py`
    (`_isolate_serve_data_dir`) apunta esa env var a un tmp por test, así NINGÚN test puede tocar los
    datos reales (el `_load_serve()` interno re-importa serve y lee la env var). Regresión:
    `test_serve_tests_never_touch_real_data_dir` afirma que cada path arranca dentro del tmp.
    Relacionado: el guard de re-dislike (#106-style en dashboard.md) — `_handle_feedback` es ahora
    idempotente por URL (`_url_in_feedback`) y no escribe duplicados aunque el cliente reintente.
    Tests: `test_serve_tests_never_touch_real_data_dir`, `test_serve_feedback_dedup_guard`.

106. **Alpine `:disabled="obj[key]"` con clave AUSENTE (`undefined`) deja el botón
    DESHABILITADO → traga el click sin hacer nada (2026-06-21).** En `cover-preview.html` el
    botón 👎 Reportar usaba `:disabled="reportedSlugs[e.slug]"`. Cuando el slug NO estaba en el
    objeto, `reportedSlugs[e.slug]` es `undefined`, y esta versión de Alpine **no remueve** el
    atributo booleano con `undefined` (sí lo hace con `false` — por eso el botón "Excluir" de al
    lado, `:disabled="isSaving"`, sí funcionaba). Resultado: el botón quedaba `disabled` para SIEMPRE,
    y un botón deshabilitado **no dispara `@click`** → el síntoma fue "le doy click y no pasa nada"
    (no era el `prompt`). FIX: coercioná a booleano explícito — `:disabled="!!reportedSlugs[e.slug]"`.
    Regla: cualquier `:disabled`/`:checked`/`:readonly` (atributos booleanos) que lea una propiedad
    posiblemente `undefined` (acceso por clave dinámica, campo opcional) **debe** envolverse en `!!`.
    El `x-text` del mismo botón SÍ reaccionaba (texto cambiaba bien) — el bug era específico del
    binding de atributo booleano. **Bonus de la misma sesión**: el motivo del 👎 se pedía con
    `prompt()`, que varios navegadores **suprimen** (devuelve `null` → no se envía nada) → se
    reemplazó por un **editor de motivo inline** (input + Enviar/Cancelar). No uses `prompt()`/`confirm()`
    para capturar input en estas UIs; metés un campo inline. Verificado en browser (preview).

107. **Un 200 OK puede ser un challenge anti-bot — `detect_challenge()` es la FUENTE
    ÚNICA (2026-07-07).** Cloudflare/WAFs a veces responden HTTP 200 con una página de
    "verificando tu navegador" en vez de contenido: sin detectarlo, el scraper lo cuenta
    como "0 items" en vez de "fuente bloqueada", y confunde una fuente muerta con una
    sin novedades. `detect_challenge(html, status)` en `manga_watch.py` combina (a)
    markers ESTRUCTURALES inequívocos (`cf-chl-bypass`, `__cf_chl_rt_tk`,
    `/cdn-cgi/challenge-platform/h/` — OJO: NO `challenge-platform` a secas, aparece en
    el JSD de bot-detection de CUALQUIER página protegida) y (b) markers de
    título/texto ("just a moment", "checking your browser"…) sólo si la página es
    CORTA (≤50 000 chars — un challenge pesa 5-15KB; contenido real que mencione esas
    frases de pasada no debe dispararlo). La usan LOS TRES paths que pueden recibir un
    challenge: el HTTP plano (`_scrape_one`), Playwright (`_fetch_with_playwright_impl`,
    evalúa el título renderizado) y el spider de whakoom (`_looks_like_cf_challenge`
    delega acá — antes tenía su propia copia de markers, divergente). Un challenge
    detectado se loguea `CHALLENGE_DETECTED`, cuenta como fallo de fuente (categoría
    `challenge`) y NO se procesan candidatos de esa página. **Política 403** (decisión
    red team): ante un 403 se hace UN reintento único con UA browser-like alternativo
    (`_BROWSER_LIKE_UA`) + 4s de backoff (`_fetch_source_html`); si persiste, se loguea
    `BLOCKED_403`, se levanta `Blocked403Error` y se abandona la fuente en este run. **NO
    se agregó 403 al `Retry` de urllib3** — reintentar un 403 idéntico en loop escala el
    bloqueo (banea más agresivo), no lo resuelve. `sources.yml` acepta un `user_agent:`
    opcional por fuente (`Source.user_agent`) para las que necesitan un UA browser-like
    permanente; se aplica por-request (`fetch_with_metadata(..., user_agent=...)`) sin
    mutar la sesión compartida entre threads. El resumen del run ahora imprime el
    desglose de challenges/403 por fuente (antes invisible entre los "0 items").

108. **ISBN con prefijo fullwidth "： " en fuentes JP degradaba el dedup por ISBN
    (2026-07-07).** Cuando el ISBN sale de una ficha técnica `ISBN：978…` (label pairs),
    el split no strippeaba el carácter "：" (dos puntos FULLWIDTH, U+FF1A, distinto del
    ASCII ":"), así que el valor persistido quedaba `"： 9784091234567"` — dos filas del
    mismo libro con y sin ese prefijo caían en tiers `isbn:` DISTINTOS y no fusionaban
    (~30-40% de los ISBN de fuentes JP tenían el prefijo). Fix: `normalize_isbn(raw,
    source="")` en `manga_watch.py` — conserva SOLO dígitos y X (x→X), descarta
    cualquier basura alrededor. Si tras limpiar la longitud no es 10 ni 13 NO se
    descarta el valor (puede ser un identificador parcial útil) pero se loguea
    `ISBN_ANOMALY` para diagnóstico. Se aplica en TODOS los puntos de asignación
    (fuente única): `fetch_metadata_from_detail`, `extract_with_selectors`,
    `_candidate_from_card`, `extract_rss`, y de nuevo como guardia universal en
    `candidate_to_json` (antes de que `derive_cluster_key` use el tier `isbn:`) — ningún
    camino de ingesta (listadomanga, wikis, retailers) puede dejar un ISBN sucio.
    Retrofit `scripts/retrofit/normalize_isbn.py` limpia el corpus histórico (salta
    `approved_at` salvo `--include-approved`; idempotente).
    **ACTUALIZADO (Fable 2026-07-08, hallazgo cover-sync #6 + B7): `normalize_isbn` ya
    NO es un simple strip — es un normalizador REAL.** Antes conservaba dígitos+X sin
    validar, así que `…046 Deluxe` se guardaba corrupto como `…046X` (la `x` de "Deluxe")
    y un SKU de 10 dígitos entraba como ISBN. Ahora: (1) TOKENIZA el crudo en runs de
    dígitos/X (separadores internos guion/espacio ok) — el `： ` fullwidth y sufijos como
    "Deluxe" caen FUERA del token del número; (2) valida checksum ISBN-13 (con prefijo
    GS1 978/979) e ISBN-10 (mod-11, `X`=10 sólo como último dígito); (3) CONVIERTE los
    ISBN-10 válidos a ISBN-13 (`_isbn10_to_13`, prefijo 978, checksum recomputado); (4)
    multi-ISBN en un campo → el primero válido. Fail-safe (esta gotcha sigue vigente): si
    NINGÚN token valida, conserva el más ISBN-like + `ISBN_ANOMALY` a stderr — el valor
    puede ser un identificador parcial útil. Los extractores estructurados que aceptaban
    `len==10` a ciegas ahora exigen `_isbn10_check` (B7). **PROHIBIDO re-agregar el tier
    `isbn:`** a `derive_cluster_key` (decisión #4): el normalizador SÓLO limpia/valida el
    campo. Dry-run sobre el corpus: 3135 ISBN-10 se convertirían a ISBN-13 (0 anomalías);
    NO aplicado (la conversión cambia el slug Regla-4 de esos items — decisión del owner).
    Tests: `tests/test_merge_fixes_20260708.py` (13 válido/inválido, 10→13, X mal puesta,
    multi-ISBN, GS1 979, Deluxe-no-corrupto).

109. **`derive_cluster_key` tier fuzzy usaba LANGUAGE, no COUNTRY — violaba "país=edición"
    incluso pre-estandarización (2026-07-07).** El tier 3 (`fuzzy:<X>|<series>|<vol>|
    <variant_tier>|<publisher>`, para items sin ISBN ni edition_key) discriminaba por
    idioma: dos ediciones que comparten idioma pero son mercados distintos (ES-España vs
    ES-México) podían fusionarse en el mismo cluster ANTES de que el skill de
    estandarización les asigne edition_key — la regla dura #46 ("país distinto = edición
    distinta, SIEMPRE") no debería tener una ventana donde no aplica. Fix: el componente
    ahora es `item.country` (`fuzzy:<country>|<series>|<vol>|<variant_tier>|<publisher>`).
    **Guard de vacío**: si `country` está vacío, NO se genera clave fuzzy (evitaría que
    TODOS los items sin país detectado cayeran en el mismo bucket) — cae al tier
    `url:` (standalone). Corpus actual: 0 claves fuzzy en items.jsonl (todo lo existente
    ya tiene edition_key/ISBN), así que no hizo falta backfill; el fix protege scrapes
    futuros de fuentes nuevas antes de su primera pasada de estandarización.

110. **Orden clean_titles-antes-de-filtros: los gates evaluaban título SUCIO en el run N
    y LIMPIO en el N+1 → no-idempotencia (2026-07-07).** La FASE 3 de `scrape_delta.sh`/
    `scrape_full.sh` corría `rescore → filter_non_manga → filter_collectible →
    clean_titles` — un título cuyo veredicto de filtro depende de la versión limpia (ej.
    tras `_strip_korean_retailer_tail` un "한정판 <cola de tienda>" recortado a sólo
    "한정판" y rechazado por `title_too_short` en la corrida donde YA estaba limpio, pero
    sobreviviendo en la corrida anterior con el título sucio) daba un resultado DISTINTO
    según en qué run cayera — dos corridas seguidas sobre el mismo item podían divergir.
    Fix: el orden ahora es `rescore → clean_titles → filter_non_manga →
    filter_collectible → backfill_metadata` (etiquetas de paso reindexadas 4a-4e) — los
    gates SIEMPRE ven el título ya limpio, en la misma corrida. Relacionado: el guard
    nuevo en `_strip_korean_retailer_tail` (no recortar si el resultado queda ≤ el
    marcador "한정판" desnudo) ataca el mismo síntoma desde el extractor.

111. **`validate_corpus.py` exit 2 = violaciones DURAS; el build se OMITE, no se corre
    igual (2026-07-07).** Antes `validate_corpus` corría DESPUÉS del build (PHASE 5) — un
    corpus con violaciones duras (dedup roto, cluster_key inconsistente) ya se había
    publicado en `web/index.html` para cuando la alerta aparecía. Ahora: (a) el validador
    devuelve `2` específicamente para violaciones duras (antes `1`, ambiguo con errores
    del propio script — `1` queda reservado para excepciones no controladas del
    validador); (b) `validate_corpus` corre como PHASE 4, ANTES del build; (c) el build
    (PHASE 5) se OMITE por completo si `CORPUS_INVALID=1` (exit 2 o cualquier rc≠0),
    dejando el build anterior intacto en vez de sobreescribirlo con datos corruptos. Se
    complementa con `FAILED_STEPS` (array bash que acumula el `$?` de CADA bootstrap/
    retrofit/build de la corrida, no sólo el gate) impreso en el FINAL SUMMARY — con
    `set +e` un paso que crashea a mitad de la cadena era antes invisible.
112. **El placeholder de "portada censurada" de listadomanga (`08a02c…png`) se colaba por
    Layout B como imagen `kind=extra`/carrusel → STOLENIMG masivo (2026-07-07).** El guard
    de gotcha #40 (vaciar `image_url` cuando el `<img>` es el hash censurado) vivía SOLO en
    `_parse_item_table` (Layout A / portada). `_parse_layout_b_cell` (Cofres/Regalos/Extras)
    NO tenía guard → el mismo placeholder entraba como foto de extra del tomo destino, y si
    el tomo no estaba en Layout A, como cover de un item `from_extras` fantasma. Resultado:
    UNA sola foto placeholder terminó de "portada" (kind=gallery) en ~80 series completamente
    distintas (Bleach, Tokyo Revengers, Ayako, Bastard!!, JJK…) — el invariante **STOLENIMG**
    de `validate_corpus`. Fix mecanismo (no síntoma): el listado de placeholders conocidos por
    URL es **fuente ÚNICA** en `image_store.known_placeholder_url_reason()` (stems exactos +
    fragmentos de URL); tanto Layout A como Layout B lo importan (`CENSORED_COVER_HASH` queda
    como alias validado contra el registro). Consecuencia en `purge_placeholder_images.py`:
    (a) los placeholders CONOCIDOS por URL se purgan aunque `local=""` (nunca se espejaron) y
    en cualquier posición — nunca son cover real; (b) regla genérica cross-series: una MISMA
    URL en ≥4 SERIES distintas es sospechosa, pero SOLO se purga de galería (`idx>0`), NUNCA
    de la portada (`images[0]`), porque una foto puede ser el cover legítimo de UNA serie y
    contaminar el carrusel de otras (bug de scrape de búsqueda de Star Comics: los thumbnails
    `fumetti-cover/thumbnail/*` son covers reales de Blue Box/Dragon Ball/One Piece inyectados
    en los carruseles de ediciones "variant"). Agrupar por SERIE (no por item) evita el falso
    positivo box↔tomos de la misma serie. Ver `docs/reference/images.md` → Purga.
113. **El token "box" desnudo matcheaba NOMBRES PROPIOS latinos y disparaba `box_set` falso en
    tomos regulares (2026-07-07, primer delta real post-mejoras).** La editorial francesa
    "Black Box" y la serie "Blue Box" (Star Comics IT, Delcourt/Tonkam FR) tienen "box" en su
    propio nombre — el signal de `box_set` por el token suelto no distinguía "Blue Box 7" (un
    tomo regular de la serie) de "Complete Box"/"Box Set" (un producto de caja real). Evidencia:
    76 tomos regulares de Manga-Sanctuary con publisher "Black Box"/"Blue Box" en 6 países
    quedaban marcados `box_set`. Fix mecanismo, no lista de series (`_box_set_signal_present()`
    en `manga_watch.py`): (1) una CONSTRUCCIÓN de producto en latín (`box set/completo/deluxe/
    premium/edition/collector/…`, o `con/en/com box`) sí señala `box_set`; (2) el token "box"
    suelto SIN ese calificador y sin un bigrama latino "`<palabra> box`" inmediatamente antes
    (es decir, pegado a CJK/dígito/puntuación o al inicio del string) también señala `box_set`
    — preserva los boxes CJK (収納BOX, 特裝BOX, 全套收納BOX, 다용도BOX…) que no tienen otra keyword;
    (3) un bigrama latino "`<palabra> box`" SIN calificador de formato (Blue Box, Black Box) NO
    señala nada — es el nombre propio de la serie/editorial. Corrida real de rescore: 85
    señales `box_set` retiradas (84 items dejaron de calificar como coleccionable y se purgaron
    del corpus vía `filter_collectible`; un item retuvo `box_set` por otra keyword genuina).
    Tests: cobertura en `tests/test_extraction.py` para el bigrama latino vs la construcción real.
114. **`throttle_group` — el rate-limit puede ser de la INFRAESTRUCTURA COMPARTIDA, no de la
    fuente (2026-07-07).** US - Dark Horse Direct (search), IT - Funside Variant e IT - Manga
    Dreams (sus 2 entradas YAML) devolvieron HTTP 429 el mismo día — las 4 resuelven al MISMO
    borde Shopify `23.227.38.0/24` (confirmado por DNS: `.65`, `.65`, `.68`). `--per-host-limit`
    agrupa por HOSTNAME, así que dominios distintos (`darkhorsedirect.com`, `funside.it`,
    `mangadreams.it`) no se serializan entre sí aunque compartan el mismo edge y el mismo
    presupuesto de rate-limit remoto — cada uno cree que tiene su propio cupo de concurrencia
    y entre los tres saturan el límite real del borde. Fix: campo nuevo `throttle_group:` en
    `sources.yml` (`Source.throttle_group`, default vacío = comportamiento de siempre agrupado
    por host). Fuentes con el mismo `throttle_group` comparten UN semáforo (limit 1) + un delay
    mínimo configurable entre requests del grupo (`--throttle-group-delay`, default 2s), en vez
    de cada una tener su propio semáforo por host. `ES - Milky Way Próximamente` (mismo borde,
    `23.227.38.32`, aunque no dio 429 en esta corrida) se agrupó preventivamente por compartir
    la misma infraestructura; `ES - Milky Way (search)` comparte el mismo borde pero todavía no
    tiene el campo seteado. Ver `docs/reference/conventions.md` → Anti-bot.
115. **Badges de descuento capturados como título cuando el `title_selector` cae al primer
    match del DOM (2026-07-07).** IT - Dynit: el theme WooCommerce inserta un badge de oferta
    ("Sconto 10%", "Sconto 5%") ANTES del nombre del producto dentro de la card; el
    `title_selector` (`.woocommerce-loop-product__title, h2, h3, a`) tomaba el PRIMER elemento
    que matcheaba —el badge— en vez del título real, en 3 items. Fix:
    `_first_non_badge_title(card, title_selector)` en
    `manga_watch.py` itera TODOS los matches del selector dentro de la card y devuelve el
    primero cuyo texto NO sea un badge (`_is_sale_badge()` vía `_SALE_BADGE_RE`: patrones tipo
    "-10%", "Sconto N%", "Descuento N%", "Réduction N%", "Sale"/"Saldo"/"Offerta"/"Promo(zione)"/
    "Solde(s)" en ES/IT/FR/EN); si TODOS los matches son badges (caso raro), cae al primero
    (comportamiento viejo, nunca peor que antes). Los 3 items con título "Sconto N%" de Dynit se
    auto-curan en el próximo scrape vía upsert (no requiere retrofit dedicado). Nota aparte: el
    sitio de Dynit está detrás de Cloudflare (`server: cloudflare`, header `cf-mitigated`) para
    fetch plano — el fetch de hoy funcionó, pero es sensible a las heurísticas del WAF.
    **Extensión (2026-07-07, IT - Funside Variant):** aparecieron 7 items con `title`
    literalmente "Sconto" — el MISMO badge pero SIN porcentaje, que el regex (que exigía un
    `\d{1,3}` junto a "sconto") no cubría. Se agregó a `_SALE_BADGE_RE` la alternativa de
    palabra "desnuda" (`sconto`/`sale`/`offerta`/`descuento`/`rebaja`/`réduction` como texto
    COMPLETO vía `fullmatch`), que NO sobre-matchea títulos con la palabra en contexto
    ("Garage Sale Vol 1"). Regresión en `tests/test_ingestion_fixes.py`; los 7 títulos se
    auto-curan igual en el próximo scrape (ficha: `docs/scraper/sources/it-funside-variant.md`).
116. **Catálogos curados de artbook mueren en el gate de coleccionable (2026-07-07).**
    Una fuente cuyo catálogo ENTERO son artbooks (tag `artbook`, p.ej. `FR - Glénat Art
    Books`) tiene títulos que rara vez traen la keyword: "L'Art de Berserk", "One Piece Color
    Walk", "Rumiko Takahashi Colors". Doble falla: (a) `detect_signals` daba score=0 → morían
    en `if score <= 0: continue` (`extract_generic_html`); (b) aun con señal,
    `derive_product_type` caía en `manga` y `is_collectible_edition` los rechazaba como
    `regular_tomo`. Fix de mecanismo (NO parche por título): **bypass por tag `artbook`**
    análogo al de `variant-catalog` (Mangavariant), centralizado en
    `is_curated_collectible_source(candidate)` y usado por los TRES gates
    (`flush_source_candidates`, `process_state`, wiki flush). Para `artbook` además fuerza
    `product_type="artbook"` (si no es ya un tipo coleccionable) para que la fila quede bien
    tipada y pase por la regla 3 de `is_collectible_edition`. Complementariamente se agregó
    **vocabulario FR de artbook** a `KEYWORD_RULES` ("l'art de", "super art book", "color
    walk", "beaux livres") + señal `artbook` para "…Colors" **anclado a fin de texto**
    (`_COLORS_ARTBOOK_RE`) para no marcar tomos regulares con "colors" mid-title ("True Colors
    3"). **Guard de relevancia:** el bypass se aplica SIEMPRE después de `is_likely_manga`, así
    que los ítems no-manga de la misma página (BD occidental: Cromwell, Druillet — sin keyword
    → score=0 → mueren en el gate de señal) nunca llegan al bypass. Regresión en
    `tests/test_ingestion_fixes.py`. Riesgo residual: un artbook de BD titulado "L'Art de
    <autor-BD>" SÍ matchea el STRONG hint `\bL['’]?art\s+de\b` de `is_likely_manga` y colaría;
    si aparece, agregar esa franquicia a `data/comics_blacklist.yml` (ficha:
    `docs/scraper/sources/fr-glenat-artbooks.md`).
117. **Cupo de compra "por persona" simulaba tirada limitada (falso `ultra_rare`/`super_rare`,
    2026-07-07).** `_extract_print_run()` tomaba cualquier "limited to N copies" sin mirar el
    contexto — pero "limited to 2 copies **per person**" / "**par personne**" / お一人様2点限り
    (JP, el marcador va ANTES del número) es un límite de COMPRA, no evidencia de escasez de
    la EDICIÓN. Fix: ventana de contexto alrededor del match (`_PER_PERSON_QUOTA_RE` mira la
    cola en latín, `_JP_PER_PERSON_RE` mira antes del número en JP) descarta el match si hay
    marcador de cupo cerca. Piso adicional: print run < 10 se descarta (ninguna tirada retail
    real es de <10 ejemplares, casi siempre es un cupo/typo). Complementario: la keyword de
    no-reimpresión (`_SINGLE_RUN_KEYWORDS`, incluye 限定版/한정판/tirada limitada/sin
    reimpresión) YA NO fuerza `rare` si `stock_status == "in_stock"` VERIFICADO — si se puede
    comprar hoy, la convención "no se reimprime" no lo hace escaso. Tests: `test_audit_wo_a.py`.
118. **`description_es=""` no distinguía "ya está en español" de "la API de traducción
    falló" (2026-07-07).** `translate_descriptions.py` escribía `description_es=""` en ambos
    casos — el original ya en ES (skip legítimo) Y un fallo total de DeepL+Google (excepción o
    resultado vacío). Como la key queda "presente", el item se marcaba PROCESADO para siempre
    y la traducción real nunca se reintentaba (fallos de red silenciosos se perdían). Fix:
    `translate_to_es()` devuelve un `TranslationResult` tri-estado (`_ST_TRANSLATED` /
    `_ST_ALREADY_ES` / `_ST_FAILED`); un fallo NO escribe la key (reintento natural en la
    próxima corrida) + WARN por slug/servicio/error a stderr. Flag `--retry-empty` recupera los
    items que ya habían quedado mal marcados como "ya-ES" antes del fix (reprocesa sólo
    `description_es==""` cuya `description` NO detecta como español). Ver también gotcha #119
    (mismo script, bug de la cola de este mismo texto). Tests: `test_audit_wo_b.py`.
119. **Junk de tienda al INICIO de la description rompía la traducción — el regex asumía que
    el botón de carrito siempre iba de COLA (2026-07-07, IT - Funside Variant).** El regex
    viejo (`_IT_JUNK_SUFFIX`, ancla `$` + `.*` greedy con `re.DOTALL`) borraba desde el primer
    match de "Aggiungi al Carrello" hasta el final — asumía que el botón siempre aparece al
    FINAL del texto. Funside Variant antepone el botón al PRINCIPIO
    ("Sconto Aggiungi al carrello Confrontare {título} Prezzo…"), así que el regex se comía la
    description ENTERA y `description_es` quedaba como "Descuento" (o vacío). Fix:
    `_strip_it_cart_suffix()` sólo corta el match si (1) arranca dentro de los últimos
    `_IT_TAIL_WINDOW` (150) caracteres del texto Y (2) queda contenido sustancial
    (`_IT_MIN_BODY_BEFORE`, 40 chars) ANTES del match — si el botón aparece temprano, se deja
    intacto (no es cola real). Ficha: `docs/scraper/sources/it-funside-variant.md`. Tests:
    `test_audit_wo_b.py`.
120. **Canonicals DUPLICADAS en `series_aliases.yml` que colapsan a la MISMA forma normalizada
    quedan sombreadas para siempre (2026-07-07, variante de #70 con detección nueva).** El
    resolver (`series_aliases._build_lookup`) indexa cada canonical por su forma normalizada
    EXACTA; si dos entradas canónicas distintas (acuñadas en corridas separadas del skill de
    enrichment) normalizan idéntico, el lookup sólo puede mapear a la PRIMERA declarada — la
    segunda queda invisible para siempre (silent data loss, sin error ni warning). Fix:
    `unmapped_series.find_canonical_duplicates()` detecta los pares vía comparación EXACTA
    post-`_normalize` (NO substring — "gto" y "gto-paradise-lost" no colisionan) y los reporta
    en `unmapped_series.py --json` bajo `canonical_duplicates`; son insumo para un merge
    gateado manual (Lote B), no se auto-fusionan. Snapshot de regresión con los 30 pares
    conocidos del corpus real. Tests: `test_audit_wo_h.py`.
121. **Guard `approved_at` faltante en UN paso de la cadena de agrupación fragmenta el cluster
    de un golden record (2026-07-07).** Si un retrofit de la cadena de listadomanga (país=
    edición, coleccion=edición, colisiones de título, dedup de carrusel…) saltea la fila
    aprobada (correcto, no debe pisarla) pero re-deriva sus HERMANAS (misma edición, sin
    aprobar), la fila aprobada termina con un `edition_key`/`cluster_key` VIEJO mientras sus
    hermanas migran al esquema NUEVO — el mismo producto se fragmenta en 2 cards, y un delta
    futuro que llegue con la identidad NUEVA ya no consolida contra la fila aprobada (el
    `approved_at` queda huérfano en una fila stale). Fix: guard `is_approved()` homogéneo +
    flag `--include-approved` en los 13 scripts de imagen/agrupación de listadomanga
    (`mirror_images` es la única excepción real — su backfill es aditivo, nunca reordena/
    reemplaza, así que se aplica igual a aprobados) + test estructural anti-drift que verifica
    que los 13 mencionen `approved`/`is_approved` y expongan `--include-approved` + **paso 7
    nuevo del enforcer** (`apply_approvals.py` al FINAL de la cadena): re-materializa el log
    durable `data/approvals.jsonl` matcheando primero por `cluster_key` y, si cambió, fallback
    por `url` — así el `approved_at` siempre termina en la fila que HOY representa ese
    producto. Es best-effort (no vuelve a FUSIONAR dos filas ya fragmentadas — eso requeriría
    re-clusterizar), pero evita que la aprobación quede huérfana. Tests: `test_audit_wo_d.py`.
122. **El LLM de standardize expulsaba items a `non_manga_blacklist.jsonl` por su propio
    veredicto, sin pasar por los gates deterministas (2026-07-07).** Un `is_manga=false` del
    LLM (falso negativo en un título ambiguo/CJK) borraba el item del corpus directamente —
    sin que `filter_non_manga`/`is_likely_manga` (los gates deterministas y auditables) lo
    hubieran rechazado nunca. Fix: **el LLM ya NO expulsa** — `is_manga=false` deja el item
    PENDIENTE (sin `standardized_at`) y lo registra en `unmapped_series.jsonl` (reason
    `llm_non_manga`) para curación manual; son los gates deterministas del pipeline los que
    deciden la expulsión real en la próxima corrida. Excepción dura: un item con source
    Mangavariant NUNCA se expulsa — el veredicto se ignora (WARN) y sigue el flujo normal
    (regla ya existente, ahora también blindada acá). Complementario: `standardize_attempts`
    escala a curación manual (reason `standardize_exhausted`) tras
    `MAX_STANDARDIZE_ATTEMPTS=3` intentos sin key usable, para que un título irromanizable no
    gaste Tier 3 en loop infinito. Tests: `test_audit_wo_c.py`.
123. **`normalize_release_date()` existía pero no era guardia UNIVERSAL — fechas crudas
    seguían colándose por caminos nuevos (regresión de #80, 2026-07-07, 113 filas).** La
    normalización a ISO se aplicaba en varios puntos de asignación específicos, pero no como
    guardia en el SINK final de escritura (`candidate_to_json`) — cualquier fuente/wiki nueva
    (KADOKAWA, Rakuten, wikis JP) que asignara `release_date` por un camino no cubierto colaba
    una fecha cruda (`"2025/04/25 10:00:00"`, `"2026年04月08日"`) directo al campo persistido.
    Fix: `candidate_to_json` ahora envuelve INCONDICIONALMENTE `candidate.release_date` en
    `normalize_release_date()` — es idempotente (una fecha ya ISO no cambia) y no pisa la
    excepción tienda-vs-発売日 de `fetch_metadata_from_detail` (esa decide QUÉ fecha usar,
    viendo el componente horario crudo, ANTES de llegar acá; este guard sólo la lleva a ISO).
    Detectado por la invariante WARN nueva `DATEISO` de `validate_corpus.py`. Tests:
    `test_audit_wo_a.py`.
124. **`upscale_images.py` rechazaba TODO upscale sobre el espejo normalizado — el parser de
    píxeles caía a un proxy de TAMAÑO DE ARCHIVO para formatos que no reconoce (2026-07-07,
    P27).** Desde que el espejo normaliza toda imagen a AVIF Q60 (2026-06-15), la salida del
    upscaler (que ahora pasa por `image_store.normalize_image` antes de escribirse, en vez de
    guardar el PNG lossless crudo) es AVIF — un formato que el parser de píxeles por bytes NO
    sabe leer, así que caía al fallback final (`len(data)`, tamaño de archivo como proxy). Un
    AVIF comprimido pesa sistemáticamente MENOS bytes que sus píxeles reales, así que el gate
    de ganancia (`new_px <= old_px`) rechazaba el upscale SIEMPRE, aunque la imagen fuera
    objetivamente más grande. Fix: `_pixels_from_bytes()` agrega un fallback a PIL
    (`Image.open(io.BytesIO(data)).size`) para AVIF y cualquier otro formato no cubierto por
    el parser binario, ANTES de caer al proxy de tamaño de archivo. Cada entry upscaleada de
    `images[]` se marca `upscaled: true` (idempotencia: nunca se re-upscalea un upscale, señal
    primaria — más robusta que inferir por tamaño). Tests: `test_audit_wo_e.py`.
    **Cerrado el 3er (y último) sitio con esta misma clase de bug (2026-07-08, auditoría
    Fable de imágenes, hallazgo #1, ALTA)**: `upgrade_image_resolution.py._pixels` tenía
    su PROPIO parser binario duplicado (`_image_dimensions_from_bytes`) sin rama AVIF ni
    fallback PIL — el gate `--min-gain` de ese script caía al mismo proxy de tamaño de
    archivo. Fix: `_pixels()` delega en `fetch_better_covers._get_pixels_from_bytes`
    (fuente única, ya con el fallback PIL de la gotcha #132) — el parser binario
    duplicado se eliminó en vez de parchearlo por 3ª vez. Tests: `tests/test_images_pkg.py::TestPixelsDelegatesToFetchBetterCovers`.
125. **Serie resuelta desde un token LATINO MINORITARIO de un título CJK pasaba Tier 1 (0
    tokens LLM) con series_key potencialmente equivocada (2026-07-07).** Caso real: "冴えない
    彼女の育てかた 深崎暮人画集 上 Flat." resolvía `series_key='flat'` — el ÚNICO fragmento
    latino del título (4 caracteres) — y el resto del título es japonés puro; como la
    resolución "tenía éxito" (encontró algo en `series_aliases.yml`), `confidence_tier=1`
    mandaba el item directo a auto-standardize SIN revisión LLM, arriesgando una key
    incorrecta silenciosa. Fix: guard en `derive_series_metadata()` — si el título contiene
    CJK/Hangul/Kana (`_has_cjk()`) Y la key resuelta viene de un token latino MINORITARIO
    (`< 5 chars` o `< 30%` de la longitud del título en latín), degrada `confidence_tier` de 1
    a 2 para que el LLM la valide. NO degrada bilingües con match latino sustancial
    ("ワンピース ONE PIECE" → `one-piece` sigue Tier 1) — el owner paga tokens sólo con
    ambigüedad real. Tests: `test_audit_wo_a.py`.
126. **`series_aliases.py::log_unmapped_series` también escribía a `data/unmapped_series.jsonl`
    REAL desde los tests — mismo patrón que el gotcha #105 de `serve.py`, distinto archivo
    (2026-07-07).** Cualquier test que ejercite `candidate_to_json` (manga_watch.py) con un
    `series_key` NO canónico (ej. un `Candidate` de fixture con título "Some Manga 1") dispara
    `log_unmapped_series()`, y `_UNMAPPED_FILE` era una constante de módulo fija a
    `data/unmapped_series.jsonl` — sin override, cada corrida de la suite completa dejaba +1
    línea fantasma en el archivo real (confirmado: 2924→2925 líneas tras una sola corrida de
    `test_audit_wo_a.py`). Fix: `_unmapped_target()` en `series_aliases.py` resuelve el path
    en CADA llamada leyendo `MANGA_WATCH_DATA_DIR` — la MISMA env var que ya usa `serve.py`
    (#105) — en vez de una constante congelada al import; así el fixture autouse existente
    (`_isolate_serve_data_dir` en `tests/conftest.py`) aísla GRATIS también esta cola, sin
    necesitar `importlib.reload` (a diferencia de `serve.py`, que sí lo necesita porque su
    `_DATA_DIR` se congela al importar el módulo). Sin la env var, cae al `_UNMAPPED_FILE`
    default — un test también puede seguir monkeypatcheando ese atributo directamente para un
    path ad-hoc. Tests: `test_log_unmapped_series_appends_only_non_canonical` (test_extraction.py),
    `tests/test_audit_loteb_prep.py`.
127. **`unify_coleccion_edition` (coleccion=edición) plegaba las VARIANTES ESPECIALES al
    regular — se perdía el tipo del título (2026-07-08, WO-1).** El unify pliega TODOS los
    tomos no-box de una /coleccion al `edition_key` base `…-regular-…` (para agruparlos en
    una página), y el tipo sobrevivía SOLO en el cluster_key (`lmc:cole:special:N`). Las
    variantes que se venden APARTE con bonus físico (título "Edición Especial"/"Especial
    Limitada"/"Edición Limitada"/"Edición de Lujo") quedaban con edition_slug `regular` y el
    display de la serie — perdían su identidad de edición (~28 items). Agravante: la tabla
    `manga_watch._EDITION_TYPE_TERM_RULES` no tenía la frase "Edición Especial"/"Especial
    Limitada", así que `edition_slug_from_text` devolvía "". Fix en tres piezas: (a) la tabla
    ahora reconoce esas frases → special/limited (ancladas a la FRASE, NUNCA "especial"
    suelto: rozaría nombres de serie); (b) `unify_coleccion_edition` CARVA esas variantes en
    su propia edición (`_with_slug(base_ek, tipo)`) por EVIDENCIA FUERTE de título
    (`_carve_slug`), en vez de plegarlas al regular — **sin tocar el cluster_key** (el dedup
    sigue por cluster) y respetando dos reglas duras: **cofre 1ª ed = regular** (una palabra
    de bonus suelta —cofre/caja/lámina/chapas— NO dispara; sólo la frase de tipo) y **folleto
    promocional gratuito fuera** (guarda anti #103: `FREE_PRICE_PATTERN` importado del parser
    + "Edición Promocional" ≠ "Edición Especial"); (c) idempotencia: `_kind_of` lee el kind
    del cluster_key existente (no del edition_slug carvado) para que `lm_kind` no derive y
    mueva el cluster en la 2ª pasada. Dos colecciones de la misma serie+publisher carvadas al
    mismo tipo colisionarían en un edition_key (DUPVOL cross-coleccion, ej. Las Quintillizas
    cole 3406 vs "Mini libro" cole 5028) → el carve namespacea con `-c{cole}` SÓLO cuando el
    ek plano ya lo reclama OTRA coleccion (si no, se deja plano; no se churnea al resto del
    corpus). Invariante nueva `validate_corpus.SPECIALREG` marca el estado defectuoso (título
    de tipo fuerte ⇒ edition_slug regular). Tests: `tests/test_audit_wo1_grupo1.py`.
128. **La `category` inyectada por el calendario legacy sobrevivía a la estandarización y
    re-contaminaba `rescore` (2026-07-08, WO-2).** El parser legacy del calendario
    (`scripts/wikis/listadomanga.py`, pre-2026-05-23) inyectaba la categoría del día
    ("Artbook", "Cofre") como 2º segmento de la `description` (`{publisher} · {category} ·
    {título}…`). `detect_signals` la leía como señal premium real ⇒ tomos REGULARES marcados
    `product_type="artbook"` (17 residuos: Fire Force 9, Black Butler 27, Tokyo Ghoul:re 14…).
    El bug upstream ya estaba arreglado, pero los residuos quedaron **blindados** por
    `standardized_at` (#61). El retrofit `purge_false_artbook_residuals.py` los desblinda —
    pero desblindar NO alcanza: la `description` NUNCA se limpió en la estandarización (guarda
    el texto crudo del calendario), así que `rescore` VOLVÍA a leer "Artbook" y re-derivaba la
    misma señal. Fix del mecanismo: el retrofit **también** quita el token de categoría
    inyectado de la `description` (por POSICIÓN — el 2º segmento del split por " · " sólo si
    coincide con el tag `category:<X>`; nunca substring ciego); recién entonces `rescore`
    dropea la señal y `filter_collectible` los expulsa como `regular_tomo`. Tests:
    `tests/test_audit_wo2_grupos23.py`.
129. **El calendario legacy NO ve precio ⇒ los folletos promocionales gratuitos entraban como
    ítems; cobertura sólo parcial vía "Edición Promocional" (2026-07-08, WO-2).** A diferencia
    del parser de colecciones (`listadomanga_collections.py`, que descarta precio 0 con
    `FREE_PRICE_PATTERN`, #103), el módulo del calendario no extrae precio, así que no podía
    filtrar folletos gratis por señal de precio. La guarda que sí aplica es textual: se saltea
    el enlace cuyo título es "Edición Promocional" (≠ "Edición Especial"), reusando
    `FREE_PRICE_PATTERN` importado del parser de colecciones (fuente única, no redefinir). Es
    cobertura PARCIAL — un folleto gratis sin esa frase en el título aún puede colarse; la
    señal de precio sólo existe en la vía de colecciones. Tests:
    `tests/test_audit_wo2_grupos23.py`.
130. **Import manual one-shot de One Piece con ISBN mal resuelto arrastró ~11 series ajenas
    (2026-07-08, WO-2).** El import de publicaciones especiales/Jump Remix
    (`import_op_remix.py` / `fix_op_special_vols.py`) resolvía ISBNs de índices de antología
    Jump Remix/GIGA a "volúmenes de One Piece", metiendo series completamente ajenas (地獄楽,
    終末のハーレム, RURIDRAGON, 青の祓魔師, 遊☆戯☆王, 逃げ上手の若君…) bajo edition_keys
    `one-piece-*-special-jp`. Prevención estructural: `op_series_guard.is_one_piece_title()` —
    fuente ÚNICA reusada por los dos scripts de import (guard ANTES de escribir) y por el
    retrofit `purge_op_import_foreign.py` (detección de residuos). Un título es "de One Piece"
    sólo si contiene una keyword dura (`one piece`/`ワンピース`/`尾田`) o está en la
    allowlist de spin-offs oficiales (`ONE_PIECE_SPINOFF_ALLOWLIST`: "Shokugeki no Sanji",
    que como spin-off legítimo NO debe expulsarse — falso positivo del matcher corregido en el
    mecanismo, no relajando la regla genérica). Los residuos se desblindan + encolan a
    `data/unmapped_series.jsonl` (reason `op_import_foreign`), no se borran. Tests:
    `tests/test_audit_wo2_grupos23.py`.
131. **Los paths lens/text-small del motor de portadas NO corrían `_same_cover` (falsos
    positivos 2/3/4/5) + el rechazo se purgaba sin dejar rastro (2026-07-08).** En
    `fetch_better_covers._process_item`, la rama `via=="lens"` verificaba sólo aspect ±0.30 +
    `_validate_page_content` (fail-open), y la rama `via=="text"` con `orig_px < 30k` sólo
    aspect ±0.25 — ninguna corría el AND-gate de identidad `_same_cover`, así que se colaban
    portadas equivocadas de la misma serie/otro tomo. Además, cuando el owner rechazaba una
    candidata en el panel, `apply_preview` borraba el archivo y la quitaba de la cola SIN
    registrar nada: la misma candidata volvía a proponerse en la corrida siguiente. **Fix**:
    (1) lens y text ahora EXIGEN `_same_cover` cuando hay **referencia utilizable** (bytes +
    px ≥ 10 000, umbral donde `_same_cover` es fiable); sin ref utilizable el gate es
    FAIL-CLOSED (aspect ±0.25 + `candidate_metadata_conflict` + `_validate_page_content` con
    `fail_open=False`). (2) Ledger `data/cover_rejections.jsonl` (append-only) + denylist
    `is_rejected_candidate` consultada por el motor y por `sc_validate` (fuente única). **El
    veto por HASH aplica SÓLO con motivo de IDENTIDAD** (`otro_tomo`/`otra_edicion`/
    `no_es_la_obra`/`arte_sin_logo`/`auto_revalidation`) y aHash dist ≤ 2 — NUNCA con `reason`
    null o de calidad, porque toda candidata que pasó `_same_cover` comparte aHash con la
    referencia y ese veto tiraría la candidata correcta en mejor resolución (lo demostró el red
    team). El veto por URL exacta (slug + rejected_url) aplica siempre. Se eliminó la función
    muerta `_try_candidates`. Tests: `tests/test_cover_rejection_ledger.py`,
    `tests/test_cover_engine_gates.py`.
132. **`_get_pixels_from_bytes` medía 0 px en AVIF ⇒ anulaba el gate `_same_cover` de #131
    (2026-07-08).** El parser de bytes de `fetch_better_covers._get_pixels_from_bytes` sólo
    cubría JPEG/PNG/WebP-VP8; para AVIF (y GIF/VP8L) devolvía 0. Pero el espejo local
    `data/images/` está normalizado a AVIF (≈99.98% de los archivos), así que la REFERENCIA de
    CUALQUIER item medía `orig_px == 0`. En `_process_item`, `usable_ref = bool(orig_bytes) and
    orig_px >= 10_000` quedaba SIEMPRE False → TODAS las candidatas caían al gate degradado
    `_passes_no_ref_gate` (fail-closed por page-content) en vez de correr el AND-gate de
    identidad `_same_cover` — es decir, el fix de #131 estaba muerto en la práctica. Además el
    filtro de ganancia de píxeles (`orig_px > 0 and ...`) quedaba deshabilitado. **Fix de fuente
    única**: tras el parsing rápido, `_get_pixels_from_bytes` delega en `_get_dims_from_bytes`
    (que ya tenía fallback PIL para AVIF/GIF) y multiplica — una sola fuente de verdad para las
    dimensiones. Verificado en vivo: una ref AVIF 357×500 medía 0, ahora mide 178 500. Tests:
    `tests/test_cover_engine_gates.py::test_get_pixels_from_bytes_measures_avif` (+ fast-paths
    intactos).
133. **`search_discovery.py`/`wayback_recover.py`/`build_web.py` con footguns de escritura,
    dedup y observabilidad — auditoría Fable A2, 2026-07-08.** Varios:
    (a) `search_discovery.py` escribía items.jsonl con `open("a")` crudo al FINAL del run
    (sin `backup_and_rotate`, sin el upsert/merge de `append_jsonl`) — un crash a mitad de
    un run de ~1h de red quemaba todo el presupuesto de API sin persistir nada; ahora hace
    `backup_and_rotate` una vez antes del loop + `append_jsonl` cada `--flush-every` queries
    (default 8). (b) El dedup intra-run agregaba la URL CRUDA a un set de URLs
    NORMALIZADAS (`known_urls.add(cand.url)` en vez de `normalize_url_for_dedup(cand.url)`),
    así que la misma URL con OTRO tracking param se colaba como duplicado. (c) Los engines
    agotados (DDG HTTP 202 soft-ban, Gemini 429 quota) se seguían golpeando query tras query;
    ahora `SearchEngineExhaustedError` los desactiva (`dead_engines`) para el resto de la
    corrida (gemini/google comparten cupo, se desactivan juntos). (d) `wayback_recover.py`
    `_flush_wayback` decía "atómicamente" en el docstring pero usaba `write_text` (trunca
    in-place) — un crash a mitad de escritura dejaba items.jsonl corrupto; ahora es
    tmp+fsync+`os.replace`, y el backup previo aplica siempre que `--output` YA exista (antes
    sólo corría si `dst == src` por igualdad de Path, así que un `--output` distinto se lo
    saltaba). (e) No respetaba el guard homogéneo `approved_at` (ver gotcha #121/conventions.md)
    — un golden record podía perder su título/autor/publisher por una recuperación de
    Wayback; ahora salta items aprobados salvo `--include-approved`. (f) Escribía un campo
    `name` espurio (la metadata genérica de `fetch_metadata_from_detail` usa esa key, pero
    el schema de items.jsonl usa `title`) — se mapea `name`→`title` explícitamente, sin pisar
    un título ya existente. (g) Re-escaneaba TODO el corpus de items 404 contra Wayback en
    cada corrida (~70 min) sin caché — ahora `data/wayback_negative_cache.json` (TTL 90 días)
    recuerda las URLs con "sin snapshot" CONFIRMADO por la API (200 + JSON válido); un 429 o
    timeout nunca se cachea como negativo (`find_wayback_snapshot` devuelve
    `(snapshot, definitive)`, y sólo `definitive=True` es cacheable). (h) `build_web.py`
    escribía `index.html` con `write_text` (no atómico, mismo problema que (d)) — ahora usa
    `_atomic_write_text`. (i) `build_web --embed`: `json.dumps` no escapa `/`, así que un
    `</script>` literal en un título/descripción scrapeado cerraba el tag antes de tiempo y
    corrompía el HTML — se escapa `payload.replace("</", r"<\/")` (escape válido de JSON,
    cualquier parser lo interpreta igual que `/` sin escapar). Código muerto eliminado de
    paso: `_DDG_SNIPPET_RE` (search_discovery), `items_by_url` + `from datetime import
    datetime` sin uso (wayback_recover), `build_web._source_entry` (cero callers, ni en
    tests). Tests: `tests/test_discovery_wayback_buildweb.py`.
134. **Los scripts de cover-sync trataban "el catálogo no cargó" igual que "el catálogo
    cambió" — auditoría Fable A1, 2026-07-08.** `sync_cover_preview.py` (Regla 1: slug
    ausente de `items_by_slug` → entry eliminada) y `sync_cover_images.py`
    (`_compute_junk_local`: `sizes.get(f, 0)` igualaba "0 bytes" con "no existe") NO
    distinguían un catálogo vacío/corrupto de uno que de verdad cambió — un
    `items.jsonl` ausente/truncado/con líneas mal parseadas vaciaba la cola de
    aprobación entera (`cover_preview.json`, ~160 entries) en UN solo GET
    `/api/cover-preview` (que persiste), y un `data/images/` ausente hacía que
    `_fix_bad_cover` arrasara portadas en masa (TODO local caía en la rama junk).
    **Fix**: (a) `sync_cover_preview.catalog_is_sane(preview, items_by_slug,
    malformed_lines)` — aborta (CLI) o degrada a solo-lectura sin persistir (GET) si
    `items_by_slug` está vacío con cola no vacía, si >20% de los slugs no matchean, o
    si `_load_items_by_slug` contó líneas `JSONDecodeError`>0 (antes las tragaba en
    silencio, ahora las cuenta y las expone). (b) `sync_cover_images.run()` aborta si
    `not images_dir.exists()`; `_compute_junk_local` separa "no está en `sizes`" (skip,
    legítimo) de "está con 0 bytes" (junk real). Además, en el mismo paquete: (c)
    `_fix_bad_cover` ya no promueve `kind:"extra"` (postal/shikishi) a portada, y al no
    encontrar reemplazo de galería válido conserva el resto de `images[]` en vez de
    vaciarlo entero (antes perdía extras legítimas junto con la portada mala). (d)
    `prune_soft_cover_candidates.py` marcaba `_is_soft_image` como DROP silencioso
    (ninguna traza, la misma candidata podía re-proponerse); ahora marca
    `status: "rejected"` + ledger, igual que `revalidate_cover_preview.py` — misma
    condición, política unificada. (e) `promote_hires_cover.THUMB_ASPECT_TOL` decía
    "0.12, igual que dedup" pero `dedup_carousel_images.THUMB_ASPECT_TOL` es 0.06 — el
    único script que muta `images[0]` SIN cola de revisión tenía el umbral MÁS laxo,
    no el mismo; corregido a 0.06 (centralización real en una constante compartida
    queda pendiente — TODO en el docstring de `promote_hires_cover.py`, requiere tocar
    `fetch_better_covers.py`, fuera del alcance de este paquete). (f) GC de archivos de
    candidatas huérfanas: `sync_preview()` ahora borra el `new_image` de una candidata
    podada/dropeada SOLO si no lo referencia nada más (ni `items_by_slug`, que comparte
    el mismo `data/images/`, ni otra entry/candidata sobreviviente) — antes quedaban
    huérfanos para siempre (ningún GC leía `cover_preview.json`). Tests:
    `tests/test_cover_sync_guards.py`.
135. **El lock global del scrape tenía una ventana de carrera y el trap EXIT liberaba
    el lock aun con el corpus a mitad de pasos — auditoría Fable S2/S4, 2026-07-08.**
    `scrape_delta.sh`/`scrape_full.sh` (y desde este mismo fix, `bootstrap.sh`): (a)
    **S2** — si dos procesos detectaban `data/.scrape.lock` stale (PID muerto) al mismo
    tiempo, ambos hacían `rm -rf "$LOCK_DIR"` y el `mkdir "$LOCK_DIR" && echo $$ >
    "$LOCK_DIR/pid"` de la vieja `acquire_lock()` NO abortaba si el `mkdir` fallaba (el
    `&&` sólo salteaba el segundo comando) — el perdedor seguía el scrape completo SIN
    lock, y su `trap 'rm -rf "$LOCK_DIR"' EXIT` heredado borraba el lock del ganador al
    salir. Fix: `if ! mkdir "$LOCK_DIR" 2>/dev/null; then exit 1; fi` — el perdedor
    aborta explícitamente. (b) **S4** — un Ctrl+C/SIGTERM a mitad de Fase 2/3 saltea el
    gate `validate_corpus` (PHASE 4) por completo, pero el trap EXIT igual corría `rm
    -rf "$LOCK_DIR"` sin validar nada — un corpus inter-pasos corrupto podía quedar
    SERVIDO (serve.py hace `fetch()` en vivo, decisión #5) sin que el lock reflejara
    ningún problema. Fix: `trap '_on_abort_signal INT' INT` / `TERM` escribe
    `data/.run-aborted` (señal + fase actual + timestamp + PID) y sale con rc=130 ANTES
    de que el trap EXIT corra; el trap EXIT ahora chequea el marker — si existe, NO
    libera el lock (hay que correr `validate_corpus.py` a mano y borrar marker+lock).
    El marker de una corrida previa se avisa en el log y se borra recién después del
    backup pre-scrape de la corrida siguiente (no antes — necesitás el aviso en el log
    de ESA corrida). Verificado con un harness de sandbox (dos subshells compitiendo
    por un lock stale con la ventana ensanchada a propósito; SIGINT real con job
    control habilitado) — no hay test de pytest para esto (es mecánica de bash, no de
    Python). Además (S1) la Fase 1 (scrape principal) ahora pasa por `record_step` —
    antes un crash/timeout (rc=124) de esa fase no aparecía en `FAILED_STEPS`; y (S3)
    los retrofits de red de Fase 3 sin timeout (`backfill_metadata --only image_url/
    images`, `mirror_images --no-gc`, `wayback_recover`) quedaron envueltos en
    `_run_timed` (regresión de gotcha #33). Detalle operativo completo en
    `docs/scraper/PIPELINE-WALKTHROUGH.md` → "Convenciones de ambos scripts".

136. **Paquete D-parsing de la auditoría Fable (2026-07-08) — correctness silenciosa en el
    parsing de `manga_watch.py`.** Trece fixes con test de regresión en
    `tests/test_parsing_fixes_20260708.py`; ninguno cambió un cluster_key existente
    (`backfill_cluster_key --dry-run` = 0 churn). **A1 — JSON-LD por-card MUERTO en el listing:**
    `extract_generic_html` hacía `soup(["script",…]).decompose()` ANTES de que
    `extract_with_selectors`/`_candidate_from_card` llamaran a `extract_schema_org_product(card)`,
    que sólo lee `<script type='application/ld+json'>` — ya destruidos. El isbn/author/release_date/
    cover por card nunca se extraían en el listing (los tests pasaban porque construyen soup fresco).
    Fix: un **mapa `card→schema` (`_build_card_schema_map`) construido ANTES del decompose**,
    guardando el `script.parent` (sobrevive al decompose del `<script>`), atribuido a la card vía
    `_schema_for_card` (camina el ancestro hasta la card). Así el texto de la card NO se contamina
    con el JSON crudo y el JSON-LD se atribuye por card. La extracción de campos se factorizó en
    `_schema_product_result(items, url)` (fuente única, usada por el mapa y por
    `extract_schema_org_product`; los call sites de detail/soup-fresco quedan idénticos, `schema_map=None`).
    **A2** — ver gotcha #43 (strip de "no"). **M1** — ver gotcha #74 (último-match en `_extract_volume`).
    **M2 — año entre paréntesis como volumen:** "Berserk Official Guidebook (2016)" → vol 2016; el
    patrón de paréntesis descarta ahora `(19xx|20xx)` con un negative-lookahead. **M3 — autores en
    Hangul rechazados:** `_validate_author_candidate`/`_extract_author_from_links` usaban el rango
    U+3040–U+9FFF (sin Hangul) → autores KR (Aladin) perdidos; ahora reutilizan `_has_cjk()`/`_CJK_RE`
    (fuente única, ya incluye Hangul). **M4 — meses PT/DE sin normalizar:** "15 de junho de 2025" /
    "15. März 2026" se guardaban crudos; se agregaron los 12 meses PT y DE (con/sin acento) a
    `_MONTH_NAMES` y a `RELEASE_DATE_PATTERNS`, y un `\.?` tras el día en `_DATE_TEXT_DMY_RE` (el "15."
    alemán). **M5 — `_schema_item_is_product` matcheaba substring del `@type`:** `BookSeries`/
    `BookStore`/`ComicSeries` daban True (poblando name/publisher con la SERIE, no el tomo); ahora
    matchea por TOKEN excluyendo esos tres. Y `dateModified` (fecha de registro, no 発売日) salió de
    la cascada de release_date. **M6 — filtro de dir de galería INVERSO:** ver gotcha #31 (cover en
    `/s/products/`, galería en `/s/files/`). **B3 — `\bMagazine\b` case-sensitive:** "ONE PIECE
    magazine" (minúscula) no se tipaba magazine; ahora IGNORECASE pero ignorando lo que va entre
    paréntesis (para no disparar con "(sale magazine)" de marketing — el test histórico se preserva).
    **B4 — `_load_comics_blacklist` relativo al CWD, degradación SILENCIOSA a vacío:** ahora ancla a
    `Path(__file__)…/data/comics_blacklist.yml` (fallback al CWD) y WARN a stderr si falta o el YAML no
    parsea. **B5 — `normalize_isbn` logueaba `ISBN_ANOMALY` a stdout** (contaminaba salida parseable):
    a `sys.stderr`. **B6 — `series_display = raw.title()` rompía apóstrofes** ("hell's" → "Hell'S");
    ahora `" ".join(w.capitalize() …)`. **B14 — `normalize_release_date` default DD/MM ambiguo para
    fuentes US:** `06/07/2026` de una fuente US se leía 6-jul; nuevo param opcional `country` (y en
    `extract_release_date`/`fetch_metadata_from_detail`) → MM/DD para US/CA cuando el formato es
    AMBIGUO (ambos componentes ≤12); el resto sigue day-first (gotcha #80). Cableado en los call sites
    de parsing (card-level + detail-fetch); un componente >12 ya era inequívoco y no depende del país.
137. **`normalize_image_url` borraba la query COMPLETA en el patrón Magento-resize →
    colisión de `image_stem` entre imágenes DISTINTAS, cross-cover silencioso latente
    (2026-07-08, auditoría Fable de imágenes, hallazgo #2, ALTA).** El stem local
    (`data/images/<sha256(image_url)[:16]>.<ext>`) se deriva de la URL NORMALIZADA — el
    patrón 1 de `normalize_image_url` (params de resize tipo Magento:
    `?width=300&height=300&quality=80…`) hacía `parsed._replace(query="").geturl()`,
    borrando TODA la query, incluidos params de IDENTIDAD que algunas fuentes meten en
    el mismo query string (ej. `?id=123&width=300` vs `?id=456&width=300` → ambas
    normalizan a la misma URL sin query → mismo stem). Como `existing_local_image` hace
    glob por stem, la SEGUNDA imagen con ese stem "ya existía" y `download_image` la
    saltaba, dejando la portada del PRIMER item pisando al segundo — el mismo bug de
    fondo que el STOLENIMG de la gotcha #112, pero de una clase distinta (colisión de
    hash, no un placeholder compartido) y corriendo sobre CADA imagen de las 63 fuentes,
    no sólo listadomanga. Latente en el corpus real: 164 URLs matcheaban el patrón, 151
    cambiarían de stem con el fix, 67 ya tenían archivo en disco bajo el stem viejo.
    **Fix (fuente única, `image_store.normalize_image_url`)**: reconstruir la query
    filtrando SOLO los keys de `_CDN_RESIZE_PARAMS`, preservando cualquier otro param
    (identidad, cache-buster, etc.) — idempotente (una 2ª pasada ya no tiene esos keys,
    el `if` de detección da False). **Compat hacia atrás**: `existing_local_image`
    prueba el stem correcto primero y cae al stem LEGACY (`_legacy_image_stem`, replica
    exactamente el comportamiento pre-fix) si no encuentra nada, así los archivos ya
    espejados bajo el stem viejo se siguen sirviendo sin re-descarga — sólo las
    descargas NUEVAS usan el stem corregido. Regla general: cualquier función que derive
    un stem/hash de identidad a partir de una URL debe preservar TODO lo que distingue
    una imagen de otra — "limpiar la query" para des-parametrizar un CDN no es lo mismo
    que "vaciar la query", y confundir ambas cosas es el patrón exacto de este bug.
    Tests: `tests/test_images_pkg.py::TestNormalizeImageUrlIdentityParams`,
    `::TestExistingLocalImageLegacyCompat`.

138. **Paquete MERGE de la auditoría Fable (2026-07-08) — pérdida silenciosa en el
    corazón del merge/estado.** Cinco bugs del upsert/consolidación (`manga_watch.py`),
    todos con test de regresión en `tests/test_merge_fixes_20260708.py`:
    **(A4)** una `description` entrante VACÍA (re-scrape con drift de selector) borraba
    `description` Y descartaba la traducción pagada `description_es` — `_translation_is_stale`
    daba True para `sha1("")` y `description` no estaba en el fill-if-empty ni en
    `_CURATED_FIELDS`. Fix: description vacía = "no recapturada" → NO stale + fill-if-empty
    en las ramas raw y estandarizada. **(A5)** `process_state` tenía un 2º pase que
    colapsaba por ISBN pelado y DESCARTABA al perdedor — incoherente con la decisión #4
    (mismo ISBN entre productos distintos, ej. `9788419177629`) y, como el flush ya lo
    había escrito pero nunca entraba al state, lo re-flusheaba como "new" en cada run
    (churn eterno). Fix: ELIMINADO el 2º pase (la consolidación por `cluster_key` hace el
    merge legítimo). **(M11)** el sticky de `rarity` era incondicional → la rareza quedaba
    congelada en el primer ingest; evidencia estructural nueva (tirada numerada,
    "esaurito") nunca actualizaba una rareza no verificada. Fix: sticky SÓLO si la vieja
    tiene `rarity_verified_at`/`standardized_at`/`approved_at`; raw-sobre-raw deja ganar la
    derivación nueva. **(M13)** `detected_at` estaba en `_VOLATILE_FIELDS` → un aprobado
    re-scrapeado saltaba al final del archivo (orden por `detected_at`) como "recién
    detectado". Fix: quitado de volátiles (es la PRIMERA detección; `_CURATED_FIELDS` ya lo
    cubría para estandarizados). **(M9)** `_wiki_flush_fn` reimplementaba el flush SIN el
    check de state → un re-bootstrap reescribía TODO el batch aunque estuviera "seen". Fix:
    delega en `flush_source_candidates` (fuente única). Idempotencia del enforcer verificada
    2× byte-idéntica tras todos los cambios.
139. **Paquete E-standardize de la auditoría Fable (2026-07-08) — golden records +
    `aggressive_series_norm`.** (a) El paso de "outliers de serie" de `standardize_apply.py`
    reescribía `series_key`/`edition_key` de CUALQUIER item de la /coleccion que difiriera
    del dominante, SIN guard `approved_at` — un golden record curado a mano podía cambiar de
    serie por dominancia estadística de sus hermanas no curadas (misma clase que gotcha #121)
    y, si la serie dominante era `""`, los items sanos se volvían huérfanos. Fix: guard
    `approved_at` en el loop de rewrite + `if not dom_sk: continue`. (b)
    `aggressive_series_norm` (`series_aliases.py`, gotcha #70) colapsaba las vocales largas
    del romaji (`ou/oo→o`, `uu→u`) sobre la cadena YA concatenada → una `ou` formada en el
    LÍMITE entre dos tokens (`…o` + `u…`) fundía series distintas (`neko-udon`≡`neko-don`).
    Fix: colapso POR TOKEN, antes del join. Además el rango conservado descartaba Hangul: NFKD
    descompone las sílabas `가-힣` en jamo conjuntivos `U+1100-U+11FF` que el char-class no
    incluía → un título coreano se vaciaba. Fix: conservar también los jamo + recomponer a NFC.
    (c) `validate_corpus.py` gana 7 invariantes WARN (PAISKEY/URLDUP/IMGTOP/COVER0/APPROVED/
    TSISO/SRCFMT) y deja de crashear ante una entrada no-dict en `sources[]`. (d) enum
    `product_type` unificado a `manga_watch.PRODUCT_TYPE_ENUM` (ya no doble copia). Tests:
    `test_standardize_apply.py`, `test_validate_corpus.py`, `test_series_aliases.py`.
140. **Paquete F-escritura de la auditoría Fable (2026-07-08) — durabilidad, rotación y
    determinismo en los writers de items.jsonl.** Ver `tests/test_write_robustness_20260708.py`.
    **(A7)** la mitad de los retrofits hacían `write_text`/tmp-sin-fsync directo — un kill a
    mitad de la escritura truncaba/corrompía items.jsonl (gotcha #133, misma clase). Fix:
    helper único `write_items_atomic(path, rows)`/`write_lines_atomic(path, lines)` en
    `manga_watch.py` (tmp+flush+fsync+`os.replace`, `sort_keys=True` homogéneo con
    `append_jsonl`), adoptado por los 14 retrofits que hacen dump-completo + los 2 writers
    de items.jsonl de `serve.py`. Los filtros (`filter_non_manga`/`filter_collectible`)
    ahora escriben `rejected` ANTES que `kept`. **(A3)** `save_state` corría ANTES de
    `append_jsonl`/`mirror_candidate_images` en `run()`/`_run_wiki_bootstrap()`/
    `_run_sitemap_mining()` — un crash entre medio perdía el enriquecimiento del
    detail-fetch para siempre (state ya "al día", items.jsonl no). Fix: `save_state` SIEMPRE
    después de que las filas lleguen al JSONL. **(A6)** `backup_and_rotate` en su rama
    fixed-slot podaba TODA la carpeta de backups por mtime a `max_keep` GLOBAL — con ~20
    labels compartiendo la misma carpeta, una cadena de 3+ llamadas (el enforcer encadena
    20+) evictaba el snapshot pre-run y los `timestamped=True` de otros labels. Fix: podar
    SÓLO el glob del propio label; snapshots de nivel-run (pre-scrape, enforcer) pasan a
    `timestamped=True`. **(A8)** `generate_slugs` resolvía colisiones de slug ordenando por
    `cluster_key` sacado de iterar un `set` — con `PYTHONHASHSEED` aleatorio (default), el
    orden de empate entre clusters con la misma `detected_at` más vieja cambiaba entre
    procesos → sufijo `-b`/`-c` NO determinista (churn de URLs, idempotencia rota). Fix:
    tie-break `(detected_at, cluster_key)` + un `taken_slugs` global (antes sólo dedupeaba
    DENTRO de cada grupo de colisión, no ENTRE grupos en modo full) + iterar los grupos en
    orden alfabético de `base_slug` (no orden de inserción del set). **(A13)** 5 retrofits
    (`merge_isbn_duplicates`, `unify_coleccion_edition`, `align_raw_to_std_coleccion`,
    `fix_edition_key_anomalies`, `canonicalize_edition_slugs`) usaban `shutil.copy` a un
    path propio sin rotar (38 siblings / 1.1 GB sueltos) — migrados a `backup_and_rotate`;
    `unify_coleccion_edition` además escribía SIEMPRE aunque `changed==0` (no-op en cada
    delta), ahora hace early-return. **(M7/M8)** un `fut.result()` sin try/except en
    `mirror_candidate_images` podía abortar TODO el run ante un bug de `image_store`; un
    error de red en la página N de una fuente paginada descartaba las páginas 1..N-1 ya
    scrapeadas — ambos ahora recuperan el trabajo parcial (contar como failed/loguear el
    error, seguir con lo acumulado). **(M10)** `RobotsCache.allowed()` usaba
    `RobotFileParser.read()` (`urlopen` SIN timeout, el único fetch del pipeline sin
    límite) — un host colgado bloqueaba el worker para siempre; fix: fetch vía la `session`
    del proyecto (`fetch_text`, timeout+retry) + `parser.parse()`, dict cacheado bajo lock.
    **(B2/B8/B9/B10/B11/B12/B13, bajos)**: rama muerta `cluster_key="isbn:…"` en
    `generate_slugs` removida (tier eliminado 2026-07-07, 0 usos reales);
    `_recover_edition_display` exige el separador `" · "` + tope de longitud (si no, colaba
    la `description` entera como "título"); `align_raw_to_std_coleccion` matchea el
    edition_slug por POSICIÓN (`unify_coleccion_edition._edition_slug`, hoisteada a nivel de
    módulo) en vez de substring (un `…-variant-…` en el nombre de la serie ya no confundía
    al matcher); `fix_edition_key_anomalies._publisher_slug` saltea el token `-cNNNN` antes
    de indexar (con disambiguador, `parts[-3]` apuntaba al slug de edición, no al
    publisher) + `resolved_xx` se siembra desde ediciones YA resueltas en items.jsonl (antes
    sólo vivía en memoria de la corrida actual — un hermano `-xx` llegado en un scrape
    posterior no heredaba el país de una edición resuelta en una corrida previa); 9 scripts
    con `json.loads` sin try/except unificados al patrón `_raw`-preserve (una línea corrupta
    se cuenta/warnea y se reinyecta verbatim, no tumba el paso); los diagnósticos de
    rechazados de los filtros se ROTAN (`backup_and_rotate`) en vez de pisarse cada corrida;
    `rescore` incluye `content_hash` en su chequeo de drift (antes "nada cambió" si sólo el
    hash recomputado difería, dejando el item stale sin escribir).
    **Hallazgo NO introducido por este paquete** (pre-existente, fuera de scope): en una
    corrida FRESCA que aún tiene títulos pendientes de `clean_titles`, `rescore` corre ANTES
    (orden canónico del pipeline) y computa `content_hash` sobre el título SUCIO; recién en
    la corrida SIGUIENTE lo recalcula sobre el título ya limpio → 1 pasada de "retraso" antes
    de estabilizar (confirmado con prueba de idempotencia: pasada 2→3 da md5 IDÉNTICO). No es
    un bug de escritura — es orden de pipeline documentado; ahora VISIBLE gracias al fix de
    `rescore` de este mismo paquete (B13) en vez de quedar silenciosamente ignorado.

141. **Paquete G-performance/lock de la auditoría Fable (2026-07-08) — hot path del scraper
    + lock inter-proceso.** Ver `tests/test_perf_lock_20260708.py`.
    **(A10) `append_jsonl` era O(corpus) por flush.** El flush por-fuente lo invocaba
    ~60 veces/run, y cada llamada relee+parsea+consolida+reescribe las ~13 k filas / 33 MB
    COMPLETAS (~4 GB de I/O, en el MAIN thread bloqueando a los workers). Fix: el flush
    (`flush_source_candidates`, `spool=True` default) escribe sólo sus filas a un SPOOL
    append-only (`data/items.jsonl.spool`, O(filas) + fsync); la consolidación O(corpus)
    corre UNA vez en el `append_jsonl` final del run, que absorbe el spool (chaining idéntico
    al upsert per-fuente histórico) y lo borra. Medido: 60 flushes 22.85 s → 0.43 s (53×);
    byte-idéntico al append per-flush. Durabilidad preservada (un crash deja el corpus
    intacto+válido y lo flusheado en el spool, que el próximo `append_jsonl` absorbe —
    recuperación automática). **(A11)** `detect_signals` re-normalizaba (casefold+NFKD+regex)
    las 269 frases ESTÁTICAS de `KEYWORD_RULES` por candidato (~48 % de su CPU). Fix:
    `_COMPILED_RULES` a nivel módulo (phrase, pattern, score, type, tokens+patrones fuzzy) —
    743 → 345 µs/call (2.15×). Mismo tratamiento a `derive_product_type` con
    `_PRODUCT_TYPE_COMPILED` (106 → 76 µs/call). **(A12/S10) faltaba lock inter-proceso sobre
    items.jsonl.** El rename atómico no impide el last-writer-wins CROSS-proceso (una curación
    del dashboard entre el leer y el renombrar de un flush del scraper se pisaba). Fix:
    `items_write_lock` (fcntl.flock sobre `data/items.jsonl.lock`) tomado por
    `append_jsonl`/`write_items_atomic`/`write_lines_atomic` (reentrante mismo-hilo vía RLock
    + un fd mientras profundidad>0 → `append_jsonl`→`write_items_atomic` no se auto-bloquea) y
    por `serve._serialized` con su propio helper sobre el MISMO archivo (flock es sobre el
    archivo, interopera). Orden de locks SIEMPRE: in-proceso → flock; timeout 30 s. Verificado
    con 2 procesos reales (sin lock hay lost update, con lock no). **(B18) Playwright:** (a) el
    timeout del caller ahora escala por el backlog de la cola (`qsize()` × presupuesto por-job)
    — con ≥4 fuentes `js` un timeout fijo daba `queue.Empty` espurio aunque el job aún no
    corriera; (b) si `chromium.launch()` falla, el driver `sync_playwright().start()` se
    DETIENE antes de re-levantar (antes quedaba huérfano y cada job siguiente iniciaba otro);
    (c) `final_url` se lee MIENTRAS la page está abierta (antes se leía tras el `finally` que
    la cierra → `is_closed()` True → siempre caía a la URL original, nunca reflejaba el
    redirect). **(Punto 5, mecanismo no síntoma) el efecto de `log_unmapped_series` se
    separó de la derivación**: `candidate_to_json` lo llamaba incondicionalmente, así que
    rescore/backfill_metadata/dry-runs contaminaban `data/unmapped_series.jsonl` aunque no
    fueran a escribir. Ahora el logging está apagado por default y sólo lo encienden los
    entrypoints de ingestión real (`set_unmapped_logging`); verificado con un `rescore
    --dry-run` real (md5 de `unmapped_series.jsonl` intacto). **(B19, micro-opts)**:
    `is_comic_not_manga`/`is_pure_novel` guardan el match en vez de `.search()` dos veces;
    `_LMC_KIND_CANON` a constante de módulo (antes se recreaba el dict por llamada en el hot
    path de `derive_cluster_key`); `import math` y `urlparse` movidos fuera de los hot paths
    (ya estaban a nivel módulo); `candidate_from_source` copia `list(source.tags)` (antes
    aliaseaba la lista compartida de la fuente entre threads); `image_url`/`image_local`
    removidos de `_SOURCE_FIELDS` (siempre "" desde que la portada vive en `images[0]`;
    `SourceEntry` en `web-next/lib/types.ts` sincronizado); `host_to_group` se arma desde
    `sources_all` (no la lista filtrada — el comentario ya lo decía);
    `fetch_metadata_from_detail` captura sólo `requests.RequestException` (la tupla
    `(RequestException, Exception)` era redundante y tragaba bugs de parsing).
142. **La cola de portadas y el ledger de rechazos tienen DOS identidades: slug (primaria) +
    url canónica del item (secundaria, estable a re-slugs).** Un `generate_slugs` cambia el slug
    de un item; si la cola (`cover_preview.json`) y el ledger (`cover_rejections.jsonl`) se
    keyearan sólo por slug, un re-slug (a) perdería las decisiones del owner como "item borrado"
    y (b) neutralizaría el veto (la URL rechazada se re-ofrece bajo el slug nuevo). Cada entry de
    la cola y cada record del ledger guardan además `url` = campo top-level `url` del item.
    `sync_cover_preview.sync_preview` matchea por slug y, si falla, por `url` (migra el slug de la
    entry al nuevo en vez de podarla; backfillea `url` en entries legacy al matchear por slug);
    `catalog_is_sane` cuenta las rescatadas por url dentro del guard del 20%.
    `fetch_better_covers.is_rejected_candidate(slug, url, a_hash_hex, ledger, item_url=…)` matchea
    por slug O url canónica. Compat: records/entries sin `url` (legacy) matchean sólo por slug.
    NUNCA debilitar el ledger — la identidad secundaria lo FORTALECE. Ver `docs/reference/images.md`
    § "paquete R". Tests: `tests/test_remediacion_20260708.py`. **Lock del preview**: todo escritor
    de `cover_preview.json` (el motor `_write_preview`, y en serve el save + el persist del GET)
    toma `fetch_better_covers.preview_write_lock` (fcntl.flock sobre `cover_preview.json.lock`,
    reentrante mismo-hilo, timeout 10 s) sobre su intervalo read→modify→write — cierra el TOCTOU
    motor-vs-panel que perdía decisiones del owner.
