# Convenciones para cambios de código

> Documento de referencia de PandaWatch, cargado **bajo demanda** desde
> [CLAUDE.md](../../CLAUDE.md). Leelo cuando vayas a trabajar en este tema.

## Conventions for code changes

### Filtros (cambiar o agregar un pattern)

Cuatro familias de filtro, en este orden: (1) `is_likely_manga` (cascada 4-reglas,
decisión #2), (2) `is_pure_novel` (rechaza light novels por URL hints + indicator
words; bypass para adaptaciones manga y artbooks), (3) `is_comic_not_manga` (comics
blacklist, SIEMPRE, bypass si el title contiene "manga"), (4) `is_collectible_edition`
(2º gate: sólo special/variant/deluxe/limited/box/artbook/fanbook/magazine; rechaza
tomos regulares).

Workflow al cambiar cualquiera: (1) buscá un ejemplo real en items.jsonl; (2) agregá
un test en `tests/test_extraction.py` con el string exacto reportado; (3) `pytest -q`
verde; (4) retrofiteá el corpus con el script correcto:
`is_likely_manga`/`is_comic_not_manga`/`is_pure_novel` → `filter_non_manga.py`;
`is_collectible_edition` → `filter_collectible.py`; `detect_signals`/`signal_types`/
`score` → `rescore.py`; `clean_title` → `clean_titles.py`; extractores → `backfill_metadata.py`;
`derive_cluster_key` → `backfill_cluster_key.py`. (5) verificá que el ejemplo desapareció.

### Fuentes nuevas / wikis

Receta completa en `docs/scraper/SOURCES.md`. `kind: html|rss|bluesky|js` (js requiere
Playwright via `--enable-js`), `selectors:` si la auto-detección falla, `purity: mixed`
si no es manga-only (la comics blacklist aplica igual). Tag `"new-source"` para
`--only-tags`. Wiki parser nuevo: seguir el API público de `listadomanga.py`
(`parse_calendar_page`, `fetch_calendar_month`, `iter_year_months`, `bootstrap`) + wirear
en `_run_wiki_bootstrap()` + agregar a `choices=` del argparse + a scrape_delta/full + registry.

### Scripts shell del pipeline (lock / timeout / abort marker)

`scrape_delta.sh`/`scrape_full.sh` son la referencia; cualquier script shell nuevo (o
`bootstrap.sh`) que mute `items.jsonl` debe seguir el mismo patrón (endurecido
2026-07-08, auditoría S1-S4/B16):

- **Lock**: `mkdir "data/.scrape.lock" 2>/dev/null` (atómico). Si falla, chequeá
  `kill -0 <pid-guardado>`; si sigue vivo, abortá; si está muerto (stale), `rm -rf` y
  reintentá el `mkdir` — pero el reintento debe **abortar explícitamente si también
  falla** (carrera con otro proceso que lo tomó primero): `if ! mkdir "$LOCK_DIR"
  2>/dev/null; then exit 1; fi`. Nunca `mkdir ... && echo ...` suelto (el `&&` no aborta
  si `mkdir` falla, sólo saltea el segundo comando — bug real, ver gotcha #135).
- **Trap EXIT** libera el lock (`rm -rf "$LOCK_DIR"`) SÓLO si no hay un marker de aborto
  activo (ver abajo). Se instala DESPUÉS de adquirir el lock, nunca antes.
- **Traps INT/TERM**: escriben `data/.run-aborted` (señal + fase actual + timestamp +
  PID) y salen con un rc distinto de 0 ANTES de que corra el trap EXIT — así el corpus
  a mitad de pasos no queda servido sin que quede rastro. El marker se borra recién
  después del backup pre-scrape de la SIGUIENTE corrida (avisando en el log primero).
- **`_run_timed <segundos> <comando>`**: cualquier paso que haga HTTP (scrape, wiki
  bootstrap, retrofit de imagen/red) va envuelto — un host colgado no debe bloquear el
  resto del pipeline ni mantener el lock tomado indefinidamente. `backfill_metadata`,
  `mirror_images`, `wayback_recover` y similares NO son excepción.
- **`record_step "<nombre>" $?`**: TODO paso relevante de la corrida (incluida la Fase
  1 de scrape principal, no sólo los retrofits/wikis) — con `set +e` un paso que
  crashea a mitad de la cadena es invisible sin esto.
- **Rotación de logs**: al crear el `LOG_DIR` de la corrida, podar `logs/scrape-*`
  viejos (quedarse con los últimos ~14). `data/metrics.jsonl` es la excepción — es
  histórico append-only que consume `source_health.py`, no se rota desde acá.

### Anti-bot (challenge detection + política 403)

- **`detect_challenge(html, status)` en `manga_watch.py` es la FUENTE ÚNICA** para
  decidir si una respuesta HTTP 200 es en realidad un challenge de Cloudflare/WAF (no
  contenido real). La usan el path HTTP plano (`_scrape_one`), el path Playwright
  (`_fetch_with_playwright_impl`) y el spider de whakoom (`_looks_like_cf_challenge`
  delega acá) — **no reimplementar markers en otro lado** (divergió antes; gotcha
  #107). Un challenge detectado cuenta como fallo de fuente (categoría `challenge`,
  log `CHALLENGE_DETECTED`), no como "0 items".
- **403 → UN reintento con UA browser-like alternativo + backoff, NUNCA loop.** Decisión
  consciente de red team: agregar 403 al `Retry` de `urllib3` reintentaría con el MISMO
  UA y escalaría el bloqueo en vez de resolverlo. Si el reintento también da 403, se
  loguea `BLOCKED_403` y se abandona la fuente en ese run (`Blocked403Error`).
- **UA por-fuente**: `sources.yml` acepta `user_agent:` opcional (`Source.user_agent`)
  para fuentes con anti-bot agresivo que necesitan un UA browser-like permanente. Se
  aplica por-request (`fetch_with_metadata(..., user_agent=...)`), nunca mutando la
  sesión compartida entre threads.
- **`throttle_group:` para infraestructura compartida (2026-07-07, gotcha #114)**:
  `--per-host-limit` agrupa la concurrencia por HOSTNAME — no protege cuando varios
  dominios distintos resuelven al mismo borde/CDN compartido (ej. varias tiendas
  Shopify tras `23.227.38.0/24`) y ese borde aplica un rate-limit único: cada fuente
  cree tener su propio cupo y entre todas saturan el límite real (evidencia real:
  US - Dark Horse Direct (search), IT - Funside Variant e IT - Manga Dreams 429'earon
  el mismo día). Usar `throttle_group: "<nombre>"` en `sources.yml` cuando agregues o
  detectes fuentes que comparten CDN/borde/infra de hosting: todas las que compartan el
  mismo valor pasan a compartir UN semáforo (limit 1) + un delay mínimo configurable
  entre requests del grupo (`--throttle-group-delay`, default 2s) en vez de serializarse
  solo por host. Vacío (default) = comportamiento de siempre, agrupado por hostname.
- **`--respect-robots` es opt-in a propósito, y los scripts canónicos NUNCA lo pasan**
  (decisión de producto consciente, no un olvido). PandaWatch es single-user / uso
  personal de baja frecuencia (un delta diario, un full mensual/trimestral) — el
  costo de ignorar `robots.txt` en ese volumen es marginal frente al de perder
  cobertura de fuentes que lo bloquean sin razón real de carga. Si una fuente puntual
  necesita respetar robots.txt, se invoca `manga_watch.py --respect-robots` manualmente
  (`RobotsCache` ya existe); no se agrega a los scripts canónicos por defecto.
  **`RobotsCache` (M10, Fable 2026-07-08)**: fetchea `robots.txt` con la `session` del
  proyecto (`fetch_text`, mismo timeout/retry que cualquier otro fetch del pipeline) +
  `parser.parse(text.splitlines())`, en vez de `RobotFileParser.read()` (`urlopen` SIN
  timeout — el único fetch del pipeline sin límite, podía colgar el worker para siempre
  ante un host que no responde). El dict `cache` está protegido por lock (se muta desde
  N threads en el path paralelo); un fetch duplicado ante una carrera es benigno, sólo el
  hang era el problema real.

### Escritura de datos — reglas duras

- **JSONL**: NUNCA `open(path,'a')`. Usá `append_jsonl(path, rows)` (upsert + atomic rename).
  Antes del rename atómico hace `file.flush()` + `os.fsync(file.fileno())` (2026-07-07):
  sin eso, un corte de energía justo tras escribir el `.tmp` podía dejarlo en el page
  cache pero no en disco.
- **Lock inter-proceso de items.jsonl (A12/S10, Fable 2026-07-08)**: TODO writer de
  `items.jsonl` corre bajo `items_write_lock(path)` (fcntl.flock sobre
  `<path>.lock`) para cubrir el read→modify→write completo contra otros PROCESOS
  (scraper vs dashboard vs retrofit del Panel). `append_jsonl`/`write_items_atomic`/
  `write_lines_atomic` lo toman solos (reentrante en el mismo hilo, así
  `append_jsonl`→`write_items_atomic` no se auto-bloquea) → los retrofits lo heredan
  gratis. `serve.py` lo toma en `_serialized` con su propio helper sobre el MISMO
  archivo de lock (flock es sobre el archivo, interopera). **Orden de locks
  SIEMPRE:** primero el lock in-proceso (RLock / `_ITEMS_LOCK`), después el flock
  cross-proceso — mismo orden en todos lados o hay deadlock. Timeout 30 s →
  `TimeoutError` (los writes son sub-segundo; no colgar esperando un proceso trabado).
- **Flush por SPOOL, no append per-fuente (A10, Fable 2026-07-08)**: en el scraper,
  `flush_source_candidates(..., spool=True)` (default) escribe a
  `data/items.jsonl.spool` (append-only + fsync, O(filas)) en vez de un
  `append_jsonl` O(corpus) por-fuente (~60/run). El `append_jsonl` FINAL del run
  absorbe el spool (chaining idéntico al upsert per-fuente) y lo borra. Todo camino
  que use `spool=True` DEBE cerrar con un `append_jsonl(items_path, ...)` que lo
  absorba (`run()`, `_run_wiki_bootstrap`, `_run_sitemap_mining` ya lo hacen). Un
  spool huérfano (crash) lo absorbe el próximo `append_jsonl`. `spool=False`
  conserva el append inmediato para callers sin append final.
- **Dump-completo de JSONL (no upsert)**: usá `write_items_atomic(path, rows)` (dicts) o
  `write_lines_atomic(path, lines)` (strings ya serializadas — para preservar texto crudo
  de una línea corrupta, patrón `_raw`, o cuando un writer mezcla dicts y raw lines) — las
  dos, importadas de `manga_watch.py`, es el patrón OFICIAL desde A7 (Fable 2026-07-08).
  Mismo tmp+flush+fsync+`os.replace` que `append_jsonl`; `write_items_atomic` serializa con
  `sort_keys=True` (mismo formato que `append_jsonl`, necesario para diffs limpios y para
  que la prueba de idempotencia byte-a-byte entre scripts distintos sea válida — si un
  writer serializa con orden de claves distinto al de otro, dos pasadas que no cambiaron
  NADA de contenido igual difieren en bytes). **TODO** script que hace dump-completo de
  `items.jsonl` usa uno de estos dos helpers — sin excepción (regla UNIVERSAL desde la
  migración del 2026-07-09: los ~60 writers del repo, no solo los del pipeline canónico,
  pasan por acá; verificable con `grep -L 'write_items_atomic\|write_lines_atomic\|append_jsonl'`
  sobre los scripts que escriben items.jsonl → debe dar vacío). `serve.py` es el único
  writer que NO importa el helper a propósito (modo degradado, gotcha S6): sus writers de
  items.jsonl tienen fsync propio y toman el MISMO `data/items.jsonl.lock` vía `_items_flock`
  bajo `@_serialized`, así que interoperan con `items_write_lock` por archivo. **No confundir**
  con los writers de `data/cover_preview.json` (`sync_cover_preview`, `prune_soft_cover_candidates`,
  `revalidate_cover_preview`, `sc_flush`): ese es OTRO archivo, con su propio `_write_atomic`
  local — el helper de items NO aplica ahí. La regla A7 nació el 2026-07-08 cubriendo la lista
  del pipeline canónico (`filter_non_manga`, `filter_collectible`, `rescore`, `clean_titles`,
  `backfill_cluster_key`, `consolidate_sources`, `apply_approvals`, `generate_slugs`, `set_rarity`,
  `merge_isbn_duplicates`, `unify_coleccion_edition`, `align_raw_to_std_coleccion`,
  `fix_edition_key_anomalies`, `canonicalize_edition_slugs`, `enforce_listadomanga_rules`) y se
  completó al universo entero el 2026-07-09. Antes muchos hacían `write_text`/tmp-sin-fsync
  directo (un kill a mitad TRUNCABA el archivo; dos —`backfill_volume_from_cluster`,
  `strip_legacy_cover_fields`— ni siquiera usaban archivo temporal) y la serialización de
  claves era inconsistente entre scripts.
  **Filtros** (`filter_non_manga`/`filter_collectible`): escribir el archivo de
  `rejected` ANTES que el de `kept` — un crash entre ambos writes no deja los rechazados
  fuera de AMBOS archivos.
- **Backups**: todo script que modifique un archivo de datos usa `backup_and_rotate(path,
  label)` importada de `manga_watch.py`, UNA vez ANTES del loop. Escribe en
  `data/backups/<filename>/` (rota, máx 3). NUNCA `cp ... /tmp/`, NUNCA path propio (un
  path mal calculado crea `backups/` en la raíz, sin rotación, en git status; A13, Fable
  2026-07-08: 5 retrofits hacían `shutil.copy` a un path propio sin rotar — 38 siblings /
  1.1 GB sueltos, migrados a `backup_and_rotate` y borrados).
  **Backup pre-scrape (2026-07-07)**: `scrape_delta.sh`/`scrape_full.sh` corren
  `backup_and_rotate(items.jsonl, "scrape-{delta,full}")` al inicio del run, ANTES de
  tocar nada — antes el primer backup recién ocurría dentro de retrofits puntuales de
  la Fase 3; ahora un snapshot cubre también la Fase 1/2 (scrape + wikis). Mismo patrón
  en `enforce_listadomanga_rules.py` (backup al inicio de su cadena de 20+ pasos).
  **Rotación por-label (A6, Fable 2026-07-08)**: el slot fijo (`timestamped=False`,
  default) poda SÓLO el propio glob `<filename>.pre-<label>-bak` de ESE label — antes
  ordenaba TODA la carpeta `backups_dir` por mtime y podaba a `max_keep` GLOBAL, así que
  una cadena de 3+ llamadas con labels distintos (la del enforcer encadena 20+) evictaba
  el snapshot pre-run inicial y los backups `timestamped=True` de otros pasos, justo lo
  que "restaurar si la cadena aborta" necesita. Los snapshots de NIVEL-RUN (el backup
  pre-scrape del shell y el snapshot inicial del enforcer) usan `timestamped=True` —
  se conservan entre corridas en vez de pisarse.
- **Flush incremental**: todo loop de red/subprocess (HTTP por ítem, Tavily, waifu2x,
  Wayback) escribe items.jsonl incremental (por mejora o cada N; `--flush-every` donde
  exista, default 50, bajar a 5-10 para llamadas lentas). Un write único al final pierde
  todo si el proceso muere. El backup va antes del loop; el flush es `_write_items` directo
  (sin backup). Scripts compute-only (rescore, clean_titles, filter_*, backfill_cluster_key,
  generate_slugs) terminan en segundos → write único OK.
- **Orden save_state / append_jsonl (A3, Fable 2026-07-08)**: `save_state` SIEMPRE corre
  DESPUÉS de que las filas lleguen a items.jsonl (`append_jsonl`/`mirror_candidate_images`),
  nunca antes — en `run()`, `_run_wiki_bootstrap()` y `_run_sitemap_mining()`. Si se
  persiste el state ANTES (como era antes de este fix), un crash entre medio deja el
  enriquecimiento (author/isbn/imágenes del detail-fetch) perdido para siempre: el próximo
  run ve el `content_hash` ya "al día" en state y nunca re-escribe ni re-hace el
  detail-fetch.
- **Trabajo parcial ante un error a mitad de loop (M7/M8, Fable 2026-07-08)**: un loop
  paralelo (`ThreadPoolExecutor`+`as_completed`) SIEMPRE envuelve `fut.result()` en
  try/except por-future (contar como failed, seguir) — nunca dejar que una excepción de UN
  future aborte todo el batch (patrón ya usado por el loop de detail-fetch; `mirror_candidate_images`
  lo adoptó). Un loop de PAGINACIÓN (fuente con "página siguiente") que falla en la página N
  debe scorear y devolver lo acumulado de las páginas 1..N-1 en los handlers de excepción
  (`_finalize_partial_pages()` en `_scrape_one`), no descartarlo — el problema/error se
  registra igual, sólo se recupera el trabajo ya hecho.
- **nohup**: todo script >~2 min se lanza con `nohup .venv/bin/python -u scripts/... >
  logs/<x>.log 2>&1 &` + `echo $!` (sobrevive cierres de terminal y compactaciones de
  contexto de Claude). NO `tee` (buffering). Claude programa un `ScheduleWakeup` (~20 min)
  para revisar el log, ya que nohup desacopla el proceso.

### Guard `approved_at` homogéneo + test anti-drift (2026-07-07)

Los 13 retrofits de imagen/agrupación de listadomanga (`mirror_images` [aditivo,
excepción — ver docs/reference/images.md], `dedup_carousel_images`,
`purge_placeholder_images`, `upgrade_image_resolution`, `backfill_prh_covers`,
`fetch_better_covers` [sólo paths que MUTAN, no la generación de candidatas hacia
`cover_preview.json`], `upscale_images` [guard a nivel de ARCHIVO compartido —
si CUALQUIER item que referencia el `local` está aprobado, se saltea el archivo
entero], `promote_hires_cover`, `align_raw_to_std_coleccion`, `fix_edition_country`,
`unify_coleccion_edition`, `fix_listadomanga_title_collisions`, y
`_recover_edition_display` dentro de `enforce_listadomanga_rules.py`) siguen el MISMO
patrón: `if is_approved(it) and not args.include_approved: skip`. Un script NUEVO que
reescribe metadata descriptiva/agrupación debe seguir el mismo patrón desde el día 1
(no agregarlo después como parche).

**Test estructural anti-drift**: en vez de confiar en que cada unit test cubra el
guard, un test dedicado (`tests/test_audit_wo_d.py`) verifica MECÁNICAMENTE que los 13
scripts del dominio mencionen `approved`/`is_approved` en su código y expongan el flag
`--include-approved` en su `argparse` — si alguien agrega un script nuevo al dominio
(o le rompe el guard existente a uno viejo) sin el patrón, el test lo detecta sin
depender de qué tan exhaustivos sean los tests unitarios de ese script en particular.
Extendé la lista del test si agregás un script nuevo a este dominio.

**Por qué importa (gotcha #121)**: si un paso saltea la fila aprobada pero re-deriva sus
HERMANAS (misma edición, sin aprobar), la fila aprobada queda con un `edition_key`/
`cluster_key` VIEJO mientras sus hermanas migran al esquema nuevo — el mismo producto
se fragmenta en 2 cards. El paso 7 nuevo del enforcer (`apply_approvals.py` al FINAL de
la cadena de `enforce_listadomanga_rules.py`) es la red de seguridad: re-materializa
`data/approvals.jsonl` matcheando por `cluster_key` con fallback a `url`, así el
`approved_at` termina siempre en la fila que HOY representa ese producto (best-effort —
no vuelve a fusionar filas ya fragmentadas, eso requeriría re-clusterizar).

### El LLM propone, el determinismo dispone (backstops de standardize, 2026-07-07)

El LLM del skill `/watch-standardize-catalog` NUNCA es la autoridad final sobre nada
estructural — sólo propone, y un backstop determinista en `standardize_apply.py`/
`standardize_audit.py` valida o corrige antes de persistir:

- **`is_manga`**: el LLM YA NO expulsa items a `non_manga_blacklist.jsonl` por su
  propio veredicto (gotcha #122). Un `is_manga=false` deja el item PENDIENTE +
  registrado en `data/unmapped_series.jsonl` (reason `llm_non_manga`) para que los
  gates deterministas (`filter_non_manga`/`filter_collectible`) decidan en la próxima
  corrida. Excepción dura: Mangavariant nunca se expulsa (el veredicto se ignora, WARN).
- **`product_type`**: se valida contra un enum cerrado (`VALID_PRODUCT_TYPES` en
  `standardize_apply.py` — manga/artbook/fanbook/guidebook/boxset/novel/magazine/
  audiobook). Si el LLM devuelve un edition-kind (special/deluxe/variant/limited/
  collector — esos van en `edition_key`, no en `product_type`), se descarta y se
  re-deriva con `derive_product_type()` (fuente única, importada de `manga_watch.py`,
  nunca reimplementada).
- **Escalado de retry**: `standardize_attempts` cuenta cada vez que el merge deja un
  item pendiente por keys inusables (sanitización vacía); al llegar a
  `MAX_STANDARDIZE_ATTEMPTS=3`, el audit lo excluye de las proyecciones Tier 2/3 y lo
  manda a curación manual (`unmapped_series.jsonl`, reason `standardize_exhausted`) en
  vez de reintentarlo para siempre.

Regla general al agregar un campo nuevo que el LLM del skill pueda emitir: si el campo
tiene un enum/regla estructural conocida, el backstop determinista SIEMPRE va en
`standardize_apply.py`/`standardize_audit.py` (fuente única) — nunca confiar en que el
prompt del LLM sea suficiente.

### Flagear un registro incierto

SIEMPRE a `data/unmapped_series.jsonl` (única fuente). NUNCA archivos paralelos
(uncertain_X/review_X). Contexto extra vía campos opcionales del schema (`flagged_by`,
`reason`, `notes`, `proposed_canonical_*`). Para flags automáticos desde el pipeline usá
`log_unmapped_series()` en `series_aliases.py`. Para flags de CURACIÓN post-hoc con `reason`
+ dedup cross-run por `(series_key, reason)`/`(sample_url, reason)` (retrofits, el merge del
skill de standardize) usá `append_unmapped_from_item(item, reason, note=...)` en
`standardize_apply.py` (fuente única — no reimplementar el writer/dedup; ver
`queue_regular_shielded.py` para un ejemplo de retrofit que la reusa). Schema completo en el
File map.

**El efecto de `log_unmapped_series` está GATEADO (Fable 2026-07-08 — separar
derivación de efecto).** `candidate_to_json` (el builder de filas, "Paso D") llama
`log_unmapped_series` al DERIVAR una fila, pero esa derivación la ejecutan también
rescore/backfill_metadata/dry-runs, que NO ingieren series nuevas — sólo re-derivan
filas del corpus. Antes appendeaban a la cola aunque no fueran a escribir (git
dirty + ruido). Ahora el logging está **apagado por default**
(`series_aliases._UNMAPPED_LOGGING_ENABLED = False`) y sólo lo encienden los
entrypoints de INGESTIÓN real vía `set_unmapped_logging(not dry_run)`: el scraper
`run()` (cubre bootstrap-wiki + sitemap) y los 3 retrofits de descubrimiento
(`search_discovery`, `expand_index_pages`, `expand_whakoom_ediciones`). Regla
general: **una función de derivación pura no debe tener efectos de escritura por
default** — el CALLER que ingiere los habilita, no se apagan con un `if dry_run`
esparcido por N scripts. Los tests que ejercitan el logging lo encienden explícito;
`conftest.py` lo resetea a False por test (además del aislamiento de DATA_DIR).

### Script nuevo (o flag nuevo) en el Panel de Control

El Panel lee `scripts/script_registry.py` (única fuente). Agregá un dict a `SCRIPTS`
(id/category/icon/name/tagline/what/when/command/presets/flags) o un `_flag(...)`. El
`type`/`default` de cada flag DEBE coincidir con el argparse (bool=store_true, choice=choices…);
si divergen, el panel devuelve 400. `advanced=True` para flags poco usados. Help en español
plano (de ahí salen los tooltips). Ver `docs/admin/README.md` (API, seguridad, deploy).


## When the user reports "this item shouldn't be here"

1. Look up the item in `data/items.jsonl` to see its actual source,
   URL, signals, and what rule(s) it passed.
2. Categorize:
   - **Non-manga merchandise** (figures, bookends, prints, statues) →
     add to `_NON_MANGA_HARD` or `_NON_MANGA_SOFT`.
   - **Trading cards / sticker albums** (Panini Hot Wheels, FIFA, etc.) →
     HARD pattern.
   - **News / blog post** ("X Reveals", "Gives Y a tribute", "Win this!")
     → HARD pattern in the news family.
   - **Source-level problem** (whole feed is news, or whole search trail
     returns mixed crap) → flag the source `purity: mixed`.
   - **Menu junk** ("BD arrow_forward", "rss", category page) → HARD
     pattern matching the literal title.
3. Add a unit test with the exact title.
4. Run `pytest`, then `filter_non_manga.py`.

## When the user reports "this item is missing X field"

Almost always means the extractor didn't pick it up. Workflow:
1. `curl` the item's URL and inspect the HTML.
2. Look for the field in:
   - JSON-LD `<script type="application/ld+json">`
   - `<meta>` tags (`og:image`, `twitter:image`, `book:author`)
   - Definition lists / tables (`<li><span>label</span>value</li>` is
     the common pattern handled by `_extract_label_value_pairs`)
3. If a new label needs handling, add it to `_FIELD_LABELS` (e.g. JP
   labels like 著者, 価格, 発売日 already covered).
4. Run `backfill_metadata.py` (or `--only image_url` etc.) over the
   corpus.

