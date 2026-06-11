# Known gotchas

> Documento de referencia de PandaWatch, cargado **bajo demanda** desde
> [CLAUDE.md](../../CLAUDE.md). Leelo cuando vayas a trabajar en este tema.

## The 68 known gotchas

Cada gotcha es la regla durable + la referencia de código. El detalle histórico
(cómo se descubrió, conteos retroactivos, nombres de tests) está en git.

1. **Mojibake FR.** Glénat/Pika devuelven UTF-8 decodificado como cp1252.
   `clean_title()::_fix_mojibake()` lo repara PRIMERO; no metas regex-cleaning antes.
2. **Manga-Sanctuary URL drift.** Releases futuros redirigen a productos no
   relacionados. `manga_sanctuary.py::_title_matches_page()` valida — no lo desactives.
3. **Otaku Calendar = sólo mes actual.** El `?month=YYYY-M` se ignora; bootstrapear
   un rango da duplicados. Parser para chequeo mensual, no backfill histórico.
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
31. **Multi-imagen: acotar al scope del producto + filtro de directorio padre EXACTO.**
    `_find_product_scope(soup)` restringe los selectores de gallery al subtree del producto;
    luego se descartan las URLs gallery cuyo **directorio padre no es exactamente igual** al
    de la cover (≥2 outliers = contaminación real). Comparación por dir exacto, NO substring
    (Star Comics sirve "otros volúmenes" en un subdirectorio del folder de la cover). Cap 6
    imágenes. Wikis con URLs sintéticas (`?item=`, `?bbm-entry=`) los SKIPEA
    `backfill_metadata.py --only images` (set `SYNTHETIC_URL_MARKERS`) porque re-fetchear
    devuelve la página compartida.
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
    retiene su propia cover/precio/fecha, y las imágenes del carrusel se atribuyen por archivo local /
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
    tocan (la "no"/"N" es parte real del nombre; el marcador es `nº`/`n°`, no la palabra suelta). El
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

55. **cluster_key STALE = la raíz de la "auditoría que siempre encuentra algo" (2026-06-07).** El bug más importante y el menos visible. `standardize` (o un retrofit) renombra el `edition_key` de un item (alias de serie, `boxset`→`cofanetto`, `deluxe`→`ultimate`, `fanbook`→`artbook`, `deluxe-2`→`deluxe`) PERO el `cluster_key` guardado conserva el `edition_key` VIEJO. El enforcer consolidaba por el `cluster_key` viejo → nunca fusionaba los duplicados que el nuevo `edition_key` implica, y en la siguiente ingesta `derive_cluster_key` producía la clave nueva → re-split/re-merge → "apareció algo nuevo". Eran **741 items** con `cluster_key` ≠ `derive_cluster_key(item)` (→ 82 productos duplicados ocultos). Fix: `backfill_cluster_key.py` (re-deriva TODOS los cluster_key) se agregó al enforcer (paso 3b2, ANTES de consolidate). **Invariante CLKEY** (validador): `it['cluster_key'] == derive_cluster_key(it)` para todo item — si falla, el pipeline NO es un punto fijo. Lección de proceso: auditar UNA dimensión a la vez con un instrumento que comparte el punto ciego de los datos da "0 falso". La verificación correcta es (a) `validate_corpus.py` — TODAS las invariantes estructurales en una pasada (SLUG, CLKEY, DUPCL, DUPSYN, LMCKIND, TITLE, ONECOLE, COLED, PAIS), y (b) **prueba de idempotencia**: correr el enforcer 2× debe dar items.jsonl byte-idéntico. Ambas corren en el pipeline (scrape_*.sh paso [5]). **Warnings COLED/PAIS resueltos (2026-06-08)**: COLED (una /coleccion con >1 edition_key) venía de fichas de TIENDA cross-source no unificadas + el slug stale `panini-es` — fix: `unify_coleccion_edition` ahora agrupa fichas de tienda vía `sources[]`, y `fix_edition_key_anomalies` (enforcer 2b) normaliza `panini-es`→`panini` y `xx`→país inferido de editorial mono-país. PAIS bajó 226→7; los 7 restantes son editoriales multi-país (panini/kodansha) o `unknown` → `xx` es honesto (no se inventa país). OJO con el validador: su derivación de kind (para TITLE) debe igualar a la del fixer (`fix_lmc_display_titles._kind`): cluster lmc → kind de la fuente sintética `item=` → slug del edition_key (una metalizada cross-source que mergeó con `especial-21` lleva "Edición Especial" legítimo aunque su edition-slug sea `maximum`).

56. **"El tomo 13 aparece dos veces" — 4 raíces del DUPLICADO de tomo en una edición (2026-06-08).** El owner reportó The Promised Neverland 13 duplicado. La **invariante DUPVOL** (validador): dentro de un `edition_key`, dos items con el MISMO volumen y (mismo kind O mismo título exacto) = duplicado visible. Encontró 30, en 4 patrones:
    - **base-url phantom**: una fila con primaria `coleccion.php?id=N` (sin `item=`) y kind del edition_slug (`kanzenban:2`) duplica al tomo sintético `regular-2` (mismo título). Old-format vs new-format del mismo tomo. Fix: `collapse_baseurl_tomos.py` (enforcer 3-1) la fusiona en el sintético del mismo (cole, vol). CRÍTICO: sólo phantoms PUROS (base-url SIN `item=` propio en sources) — una base-url que SÍ tiene su synthetic es un producto real (regular que coexiste con el especial, NO fusionar). Verificado contra el parser: en estos casos el parser emite UN producto por vol.
    - **dup cross-source tier-0/tier-1**: la ficha de tienda (`edition:`) y el tomo de listadomanga (`lmc:`) NO se fusionan (cluster_key difiere por tier) aunque sean el mismo producto (Fruits Basket Collector 3 de Casa del Libro + listadomanga). Fix: `merge_crosssource_into_lmc.py` (enforcer 3-2) los fusiona por (edition_key, vol, MISMO título); el lmc es canónico y absorbe la URL de tienda como source.
    - **título contaminado**: un tomo REGULAR arrastra el nombre de la edición especial del mismo vol embebido en el título ("The Promised Neverland **Edición Especial Artbook** 13"). Fix: `fix_lmc_display_titles` (sólo edición regular) quita los qualifiers contaminantes (`Edición Especial Limitada|Artbook|Coleccionista`); `normalize_display_title` quita "Edición Especial" en CUALQUIER posición y, si el kind es especial, lo re-apenda UNA vez al final.
    - **falta marcador de kind**: regular + variant (o + limited) del mismo vol con título IDÉNTICO ("Devilman Omnibus 1" ×2). Fix: `normalize_display_title` apenda marcador por kind (variant→"Variant", limited→"Edición Limitada", especial→"Edición Especial") para distinguirlos. El validador pasa el kind REAL a normalize (no sólo especial/regular) y des-contamina igual que el fixer, o reporta falsos.

57. **coleccion distinta = edición distinta: colisión de edition_key entre /coleccion (2026-06-08).** `standardize` asignaba el MISMO `edition_key` a colecciones REALMENTE distintas (Biomega "Ultimate" cole 2572 vs "Master" cole 4501; Magic Knight Rayearth cole 245 vs Rayearth **2** cole 322; regular vs especial en páginas separadas) → sus tomos del mismo vol aparecían duplicados (mismo edition_key+vol). El `cluster_key` lmc sí difiere (lleva el cole), por eso DUPCL no lo veía. Viola la regla dura del owner ([[feedback_coleccion_is_edition]]). Fix: `disambiguate_coleccion_editions.py` (enforcer 3-0) — si un `edition_key` abarca >1 colección, inserta `-c{cole}` antes del país en CADA item (cada cole = su edición; coleccion=edición se mantiene). Idempotente. 124 items en la pasada inicial.

58. **Box set = edición APARTE, no parte de la edición de los tomos (2026-06-08).** Regla del owner: dentro de una /coleccion, un **pack / edición especial / portada alternativa conviven en la MISMA edición** (registros aparte del mismo `edition_key`), pero un **box set es una edición distinta**. `unify_coleccion_edition` colapsaba TODO a un solo `edition_key` → el box set y los tomos quedaban en la misma edición (o el tomo deluxe heredaba slug `boxset`, o el box heredaba `regular`). Fix: unify ahora calcula el base con los NO-box y asigna a los box-set su propio `edition_key` con slug `boxset` (`_is_box`: cluster kind `boxset`, o `pack`/otros con volumen-rango/vacío o título "Box Set/Cofre/Estuche"; un `pack:42` tomo-suelto NO es box). El cluster kind ya distinguía box; sólo el `edition_key` se corrompía. **El validador lo sabe**: COLED (una /coleccion con >1 edition_key) NO dispara si la 2da edición es un box set (slug `boxset`) — sólo flag si hay >1 edición NO-box. 34 items / 12 colecciones en la pasada inicial.

59. **Layout B: extra de "Edición Especial" mal clasificado como tomo regular cuando el nombre de serie se envuelve en 2 líneas (2026-06-08).** En la sección "Regalos/Cofres con las primeras ediciones", una celda Layout B cuyo nombre de serie viene partido por un `<br>` ("The Promised" / "Neverland nº13") hacía que `_parse_layout_b_cell` viera el `nº13` en la línea 2 y disparara el fallback Grimorio → `target_edition_kind = regular`. Pero el item era en realidad la EDICIÓN ESPECIAL (artbook): "Edición Especial con Escape - Libro de ilustraciones de 64 páginas". Resultado: un tomo `regular-13` FANTASMA (sin cofre propio) que duplicaba visualmente al `especial-13` real (lo reportó el owner en Promised Neverland). Fix: si CUALQUIER línea de la celda (más allá de la 1) contiene "Edición Especial/Limitada", el kind es `especial` (se fusiona con el especial del mismo vol), ANTES del fallback Grimorio. Sólo 3 items con el bug exacto (Promised Neverland 13, A Miyoshi 2, Twilight Out of Focus 2). OJO al diferenciar: un cofre legítimo de 1ª edición ("(1ª Edición) Cofre para tomos X a Y") SÍ es del tomo regular (#53); el discriminante es el texto "Edición Especial/Limitada".

59b. **El workflow `watch-standardize-catalog` perdía resultados y agotaba la sesión en force-runs grandes (2026-06-08).** Dos bugs encontrados al re-estandarizar ~10k items (force-run masivo). (a) **`args.limit` no llegaba** al workflow nombrado → `limit=0` (sin cap) → intentaba procesar TODO el pending de una sola corrida y agotaba el session limit del account a mitad del merge (subagentes "completed without calling StructuredOutput" en masa = signature de rate/session limit). Fix: default `limit=2000` (`args.limit !== undefined ? … : 2000`) — bound por corrida; el diseño es incremental, el resto se toma en la próxima. (b) **El merge transcribía inline un array gigante**: el merge-agent recibía `${JSON.stringify(allLlmResults)}` (hasta ~2000 objetos) en el prompt y debía escribirlo VERBATIM a `llm_results.json` con la Write tool → arriba de ~500 objetos el agente NO lo transcribía completo y escribía sólo unos pocos (un run mergeó 5 de 2000). Fix: cada subagente tier2/tier3 escribe su PROPIO `result_t{2,3}_NN.jsonl` (chunk chico, confiable) y el merge los lee por glob — cero transcripción central. Items cuyo chunk no produjo archivo quedan PENDING y se reintentan. **Recuperación**: si un run muere antes del merge, los veredictos VIVEN en los transcripts de los subagentes (`subagents/workflows/<runId>/agent-*.jsonl`, tool_use `StructuredOutput` con `{items:[…]}`) — se pueden extraer y mergear determinísticamente (lo que salvó ~3000 verdicts en este episodio). Sincronizado con `.claude/workflows/watch-standardize-catalog.js`.

61. **Lavado de señales post-estandarización: NO correr rescore blanket sobre items con `standardized_at` (2026-06-10).** Cualquier retrofit que recompute `signal_types` desde `title+description` destruye las señales de items estandarizados — la estandarización reescribe título/desc a etiquetas limpias ("Yawara! Ultimate 18") donde `detect_signals` no encuentra nada. Caso real 2026-06-10: `filter_collectible` habría rechazado 226 items estandarizados válidos como `regular_tomo` (Ultimate de Panini IT, Limited JP de Rakuten, Anniversary de Mangavariant, One Piece curados). Fix: `filter_collectible` tiene guard — items con `standardized_at` solo pasan gates duros (junk de título, umbrella_magazine), bucket `kept_standardized`. COROLARIO: `rescore.py` NO debe correrse blanket sobre corpus estandarizado (dry-run del 2026-06-10: cambiaría `signal_types` de 1393 items, con transiciones de pérdida 87 special→manga, 19 boxset→manga). La verdad post-estandarización vive en la etiqueta de edición derivada, no en el texto crudo.

62. **Colisión de título estandarizado en el gate `umbrella_magazine`: usar URL, no título (2026-06-10).** La revista de prensa FR "ATOM" (Manga-Sanctuary) quedó mapeada a la serie astro-boy y estandarizada como "Astro Boy | Mighty Atom Deluxe N" — EXACTAMENTE el mismo título que los tomos deluxe reales de Planeta ES (`astro-boy-planeta-deluxe-es-1..7`). Un patrón de título habría borrado los 7 legítimos. Fix: el gate ATOM discrimina por URL (`manga-sanctuary.com/magazine-atom-`) vía `_UMBRELLA_MAGAZINE_URL_PATTERN` en `is_collectible_edition` paso 0b; removidas las alternativas de título "Atom Hardcover|Mighty Atom (Magazine|Deluxe|Hardcover)". Quedan por título solo nombres inequívocos (Animeland, Otaku USA, Coyote Mag, antologías JP). Se removieron 21 items de la revista del corpus. REGLA GENERAL: cuando el título de la revista coincide o puede coincidir con el de una obra manga real, el discriminante debe ser la URL (fuente), nunca el título.

63. **Manga reales con palabras de franquicia occidental en el título: lista `title_exceptions` en `comics_blacklist.yml` (2026-06-10).** `franchise_keywords` rechazaba manga legítimos: "Shugo Chara! Jewel Joker" (Joker), "Hungry Joker", "Deadpool: Samurai" (Jump+), "Batman Ninja", "Cell of Empireo", "Batman: El Hijo de los Sueños" (Kia Asamiya), "Assassin's Creed: Blade of Shao Jun", "Eagle: The Making of an Asian-American President" (este último por el patrón hard `\bThe Making of\b`). Fix: lista `title_exceptions` en `data/comics_blacklist.yml` que neutraliza tanto `franchise_keywords` como los patrones hard non-manga (implementado en `is_comic_not_manga` + el flujo hard de `manga_watch.py`). También: `\bstandees?\b` refinado para no matchear "standee" como accesorio/extra del producto ("con/with/avec/mit/inkl./+ standee").

64. **Wrapper `manga_watch.py` de la raíz sombrea `scripts/manga_watch.py` en pytest (2026-06-10).** El wrapper en la raíz del repo (solo re-exporta `parse_args`/`run`) puede quedar cacheado en `sys.modules` como `'manga_watch'` durante la colección de la suite completa → `ImportError` en módulos que hacen `from manga_watch import <símbolo>`. Fix patrón: import con fallback `try/except` a `scripts.manga_watch` (como ya hacía `sync_cover_images.py`; aplicado a `fetch_better_covers.py`). Si agregás un retrofit nuevo que importa de `manga_watch`, aplicar el mismo patrón.

60. **`volume` vacío en ediciones especiales/limitadas/variantes — ordenamiento roto (2026-06-09).** REGLA GLOBAL (todas las fuentes): los tomos de una edición SIEMPRE se ordenan (a) por volumen ascendente; (b) desempate por kind-rank cuando el mismo volumen tiene >1 item: `regular(0) → variant(1) → special/limited(2) → deluxe/kanzenban(3) → artbook(4) → boxset(5)`. Dos bugs encontrados: (1) el parser LMC extraía el volumen del `alt` ("nº13") y construía correctamente la URL sintética `item=especial-13-HASH`, pero NO lo propagaba al `Candidate.volume` → `_extract_volume` fallaba en "Title 13 Edición Especial" (patrón trailing no captura números en medio del título) → `volume: ""` → item aparecía al final de la edición. Fix: `cand.volume = parsed["volume"]` en `listadomanga_collections.py` + nuevo patrón `\s(\d{1,3})\s+(?:Edición Especial|Variant|Limited|…)` en `_VOLUME_EXTRACT_PATTERNS`. (2) Para items existentes: `backfill_volume_from_cluster.py` lee el vol-segment del `cluster_key` lmc (ignorando "0" = placeholder). Afectó 9 items: Promised Neverland 13, Berserk 21/41/42 Variant, Seven Deadly Sins 41, Twilight Outfocus 1/2, A Miyoshi 1/2. Implementación del sort: `web/index.html` (`_kindRank` + sort en `currentEdition`) y `web-next/lib/data.ts` (`kindRank` + sort en `loadEditionClusters`). Tests: `test_edition_sort_*` en `tests/test_extraction.py`.

65. **Re-scrape sobre filas estandarizadas LAS DEGRADA: el upsert resetea `slug`/`cluster_key`/`detected_at`/`score`/`signals`/`status` (2026-06-10).** Al re-scrapear una fuente cuyos productos YA están en el corpus estandarizado (caso real: re-ingest de Manga-Sanctuary histórico + Panini IT), el upsert del flush matchea la fila existente por URL/ISBN y la refresca con el candidate crudo: conserva `standardized_at` y el título estandarizado, pero deja `slug=None`, baja `cluster_key` al tier `isbn:`/`url:` (perdiendo el `edition:` derivado), resetea `detected_at` a hoy y recomputa `score`/`signals` desde el texto crudo (pérdida tipo gotcha #61). Efecto: validate_corpus pasa de verde a cientos de violaciones SLUG/CLKEY/DUPCL. **Reparación post-scrape (en este orden)**: `backfill_cluster_key.py` (re-deriva claves → vuelve al tier edition) → `generate_slugs.py --only-missing` → `consolidate_sources.py` (fusiona las filas nuevas raw con sus clusters existentes). Verificado 2026-06-10: 1272 violaciones duras → 0. **FIXED de raíz (2026-06-10), en dos capas**: (a) en `append_jsonl` — `_CURATED_FIELDS` ahora incluye `slug`/`detected_at`/`score`/`signals`/`signal_types` (la verdad post-estandarización vive en la etiqueta de edición, no en el texto del re-scrape, gotcha #61), el merge re-deriva `cluster_key` con los campos curados ya restaurados (mantiene la invariante CLKEY en tier `edition:`), y `slug` es sticky para TODOS los items (el scraper nunca lo trae); además `candidate_to_json` deriva `cluster_key` DESPUÉS de escribir el edition_key heurístico (antes toda fila fresca entraba en tier `isbn:`/`url:` con stored != derived). (b) Safety-net en el pipeline: `scrape_delta.sh`/`scrape_full.sh` corren `backfill_cluster_key.py` [4f5] + `generate_slugs.py --only-missing` [4f6] antes de `consolidate_sources` [4g]. Verificado: re-scrape de Panini IT sobre corpus estandarizado (state limpiado para forzar el upsert) → `validate_corpus.py` 0 violaciones duras sin reparación manual.

67. **`srcset` lista entradas de menor a mayor: tomar la ÚLTIMA/mayor, no la primera (2026-06-11).** `_img_to_url` procesaba `srcset` con `val.split(",")[0]` → devolvía el thumbnail de menor resolución. Los `srcset` listan entradas de menor a mayor (convención HTML: `480w, 720w, 1200w` — el browser elige la adecuada según viewport). Fix: parsear todas las entradas; si tienen descriptor `<N>w` o `<N>x`, elegir el de mayor N; si no hay descriptores, tomar la ÚLTIMA entrada. Aplica a `srcset` y `data-srcset`. Tests: `test_img_to_url_srcset_picks_largest_w_descriptor`, `test_img_to_url_srcset_picks_last_when_no_descriptor`.

68. **Patrón Magento/Fotorama/PrestaShop/LightGallery: `<a href="full.jpg"><img src="thumb.jpg">` — el href es la full-res (2026-06-11).** Muchos storefronts envuelven el `<img>` del carrusel con un `<a>` cuyo `href` apunta a la imagen full-res (para lightbox). `_img_to_url` solo lee el `src`/`data-src` del `<img>` → devuelve el thumbnail. Fix: `_img_anchor_full_url()` — cuando un `<img>` tiene padre o abuelo `<a>` con `href` que termina en extensión de imagen (`.jpg/.jpeg/.png/.webp/.avif`, sin query string) y el href es del mismo dominio (gotcha #31), preferir ese href. Tests: `test_extract_images_anchor_href_wins_over_src`, `test_extract_images_anchor_non_image_href_falls_back_to_src`.

66. **Keywords de rareza con orden de palabras fijo pierden el caso real — usar patrones cuando la frase varía (2026-06-10).** El keyword `"japan expo exclusive"` no matcheaba "available **exclusively at Japan Expo** 2025"; `"lucca comics"` no matcheaba "Variant **Lucca** 2015" ni "punti vendita campfire di **Lucca Changes**"; y `_PRINT_RUN_RE` solo cubría la preposición de cada idioma en UNA forma ("limitata **a** N copie" pero no "tiratura limitata **di** 1200 copie", "in sole N copie", "limitiert auf 777 **Exemplare**" — el viejo `exempla[ir]res?` solo matcheaba la forma francesa —, "limited to 200 **numbered** copies"). Auditoría 2026-06-10: 368 items con evidencia textual de escasez quedaron en `common` por estos gaps (la mayor clase: 232 variantes furoku "appendix of the magazine X" de Mangavariant, inobtenibles fuera de segunda mano). Fix: `_SINGLE_RUN_PATTERNS` (regex con orden libre: Lucca word-boundary, evento/festival, furoku, retailer-exclusive en texto, out-of-print multilingual) + `_PRINT_RUN_RE` extendido. REGLA: para señales de rareza nuevas, si la frase real puede variar en orden o declinación, va como regex en `_SINGLE_RUN_PATTERNS`/`_ULTRA_RARE_PATTERNS`, no como substring. Tests por cada forma real encontrada en el corpus.
