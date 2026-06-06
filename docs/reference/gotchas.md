# Known gotchas

> Documento de referencia de PandaWatch, cargado **bajo demanda** desde
> [CLAUDE.md](../../CLAUDE.md). Leelo cuando vayas a trabajar en este tema.

## The 36 known gotchas

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
    `/enrich-series-aliases` cura el backlog (Anilist API). Al agregar a mano: Anilist →
    curar aliases (quitar transliteraciones no-target y synonyms ambiguos).
21. **Doble pasada: scraper asigna crudo, skill corrige.** Pasada 1 (`derive_series_metadata`
    en el scraper): heurístico regex → series_key/edition_key/volume; devuelve EMPTY si el
    resultado es dudoso (series_key <3 chars, todo dígitos, termina en `-N` sin volumen).
    Deja `standardized_at` ausente. Pasada 2 (`/standardize-catalog`, manual): re-deriva desde
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
25. **`image_local` es sticky en `append_jsonl`** (aunque NO está en `_CURATED_FIELDS`): si la
    row nueva no lo trae pero la existente sí, conserva el de la existente. Protege el espejo
    de un re-scrape con `--skip-image-download` o fallo de red puntual.
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

