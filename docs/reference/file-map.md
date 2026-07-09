# File map — qué vive dónde

> Documento de referencia de PandaWatch, cargado **bajo demanda** desde
> [CLAUDE.md](../../CLAUDE.md). Leelo cuando vayas a trabajar en este tema.

## File map (what lives where)

Detalle por-archivo abajo es deliberadamente conciso; las particularidades
de cada parser/retrofit están en "known gotchas" (referenciadas por #N) y en
`docs/`. Códigos: gitignored = (gi).

```
sources.yml                  — 138 source defs (67 enabled). kind: html/rss/js/
                               bluesky/wiki. purity: manga_only|mixed (17 mixed).
data/  (todo gi salvo los .yml versionados)
  comics_blacklist.yml       — Marvel/DC publishers + franchise/format keywords.
                               Aplica siempre; bypass si el title contiene "manga".
  search_queries.yml         — queries de search discovery (engine priority).
  series_aliases.yml         — canonical series + aliases multilingüe (ver #20).
  items.jsonl                — tabla principal. 1 fila por PRODUCTO (cluster) con
                               sources[]. Cada fila: cluster_key + slug. Ver decisión #1.
                               original_title (opcional, solo listadomanga): título en
                               idioma original del header "Título original:", semilla
                               para aliases — NO confundir con title_original (gotcha #22).
  state.json                 — cache de URLs vistas (detección incremental).
  feedback.jsonl             — cola del botón 👎. Item completo + reason + action
                               (feedback|move|merge|remove). Skill /watch-review-feedback.
  approvals.jsonl            — log append-only de aprobaciones (👍). Replay vía
                               retrofit/apply_approvals.py. Ver "Aprobación humana".
  dup_decisions.jsonl        — log append-only de decisiones sobre "posibles
                               duplicados" del Panel de Calidad (merged|distinct,
                               por signature). data_quality.py no re-sugiere los
                               ya decididos — tanto `audit_items` (auditoría completa)
                               como `check_urls` (live-update tras arreglar un item,
                               desde 2026-07-08) recomputan la firma del grupo y la
                               respetan. Endpoints /api/dup/{merge,decide}.
  edits.jsonl                — log append-only de ediciones inline (auditoría).
  quality_report.json        — output de audit/data_quality.py; lo lee quality.html.
  cover_preview.json         — candidatas de portada pendientes de aprobación.
  wayback_negative_cache.json — {url: checked_at_iso} de URLs SIN snapshot
                               confirmado en Wayback (TTL 90d). Escrito por
                               wayback_recover.py; sólo cachea negativos
                               DEFINITIVOS (200 + JSON válido sin snapshot) —
                               nunca 429/timeout. Gotcha #133.
  non_manga_blacklist.jsonl  — items movidos fuera por /watch-standardize-catalog.
  unmapped_series.jsonl      — FUENTE ÚNICA para flagear cualquier registro
                               incierto (serie/edición/publisher). NUNCA crear
                               archivos paralelos uncertain_X/review_X. Schema:
                               series_key (req) + contexto + flagged_by
                               (pipeline|audit:<n>|human) + opcionales libres.
                               Lo vacía /watch-enrich-series-aliases; el pipeline lo repuebla.
  images/                    — espejo local de portadas estandarizadas (AVIF Q60 ≤1600px):
                               <sha256(url)[:16]>.avif. El JSONL referencia el filename en
                               images[].local. _originals/ = originales pre-AVIF archivados.
  backups/<archivo>/         — backups rotativos (máx 3) vía backup_and_rotate().
                               NUNCA a mano ni en /tmp.
  diagnostics/               — outputs de debug de los filtros (se sobreescriben).
logs/  (gi)
  metrics.jsonl               — NUEVO (2026-07-07): 1 línea por fuente/run, appendeada por
                               source_health.py --metrics-file (idempotente por (run,source)).
                               Historial para --baseline-alert (mediana por modo delta/full).
                               Append-forever, ~21 MB a 2026-07-08 (B16) — NO se rota desde
                               scrape_delta/full.sh a propósito (source_health.py lo consume
                               como serie histórica completa; rotarlo rompería el baseline).
  scrape-{delta,full}-<TS>/    — logs por fase de cada corrida canónica (ver PIPELINE-WALKTHROUGH.md).
                               Podados a los últimos 14 directorios al arrancar cada corrida
                               (B16, 2026-07-08) — antes crecían sin límite.
scripts/
  manga_watch.py             — módulo principal (~7k líneas): filtros, scoring, IO,
                               loop paralelo, dispatchers Bluesky/Playwright/HTTP,
                               derive_cluster_key, merge_cluster/consolidate_by_cluster.
  build_web.py               — exporta series_aliases.json y deja el embed VACÍO por
                               default (fetch live; ~139 KB). --embed para poblarlo
                               (fallback file://). --clear sólo vacía el embed.
  serve.py                   — SERVIDOR ÚNICO (threaded). Sirve web/ + data/ + todos
                               los /api/*. Bind 127.0.0.1:8000. Ver gotcha #34 (@_serialized).
                               /api/run: build_command/resolve_preset_env/mutates_items
                               importados de script_registry.py (4.1, 2026-07-08 — antes
                               duplicado con admin_serve.py). 409 si ya hay un job
                               "running" que muta items.jsonl (S10) — check + registro
                               atómicos en JobManager.start(block_if_mutator=True). Origin/
                               Host validados en /api/run (S7, defensa CSRF/DNS-rebinding).
  gen_html_favicon.py        — genera web/favicon.ico + web/apple-touch-icon.png desde
                               web-next/app/icon.png (panda sobre fondo rosa de acento).
  admin_serve.py             — DEPRECATED (absorbido por serve.py); se mantiene sincronizado
                               (importa build_command/resolve_preset_env/mutates_items de
                               script_registry.py, mismo 409/Origin que serve.py). Sin CORS
                               abierto (`Access-Control-Allow-Origin: *` quitado, S7 —
                               era CSRF hacia /api/run).
  script_registry.py         — fuente única del Panel de Control (scripts, flags, presets)
                               Y de build_command/resolve_preset_env/mutates_items (4.1,
                               2026-07-08 — antes duplicados en serve.py/admin_serve.py).
                               Agregás un script acá, aparece en la UI. Valida su propio
                               schema al importar (asserts, 4.2) — ids únicos, presets con
                               values/id/desc, tipos de flag conocidos (bool/int/float/str/
                               choice/csv/csv_multi), paths de script existentes. Sincronía
                               con los argparse reales la prueba
                               tests/test_script_registry.py (AST, 4.3).
  run_local.sh / serve.sh    — lanzan serve.py en :8000, ambos vía `.venv/bin/python`
                               (serve.sh usaba `python3` del sistema hasta 2026-07-08 —
                               S6: si el sistema no tiene bs4/requests, serve.py degrada
                               en silencio y el merge de curación pierde `sources[]`).
  scrape_delta.sh            — ⭐ CANÓNICO INCREMENTAL (~30-60 min, diaria/semanal). Lock
                               global (con recuperación de carrera en lock stale, S2) +
                               marker `data/.run-aborted` en INT/TERM que retiene el lock
                               hasta validar (S4) + rotación de `logs/scrape-*` a 14 (B16)
                               + [4g2] merge ISBN + PHASE 6 source_health.
  com.pandawatch.scrape-delta.plist — LaunchAgent macOS para delta diario 3:30 AM (instrucciones dentro; NO instalado por defecto).
  scrape_full.sh             — ⭐ CANÓNICO FULL (~2-4 h, mensual/trimestral). Mismas
                               protecciones de lock/abort-marker/rotación que scrape_delta.sh.
  overnight_run.sh           — DEPRECATED (alias de scrape_delta.sh).
  full_run.sh                — DEPRECATED (alias de scrape_full.sh, 2026-07-08 — S8; antes
                               no tenía lock ni gate validate_corpus y sus stats leían
                               campos eliminados del schema).
  bootstrap.sh                — scraping profundo one-shot (paginación hasta 50, sólo
                               sources.yml — no wikis/cleanup/gate/build). Ahora toma el
                               mismo lock global que scrape_delta/full (S8, 2026-07-08).
                               Uso raro (construir/refrescar catálogo desde cero); para el
                               día a día usar scrape_delta.sh/scrape_full.sh.
  retry_failed.sh            — DEPRECATED (S9, 2026-07-08): reintentaba un set de fuentes
                               HARDCODEADO de un incidente de mayo 2026 con el cleanup en
                               el orden VIEJO (pre gotcha #110), sin lock/gate. Para
                               reintentar una fuente rota: `source_health.py` para
                               identificarla + `manga_watch.py --only-source <fuente>`.
  series_aliases.py          — canonical_series_key() + log_unmapped_series(). Ver #20.
  image_store.py             — primitivas del espejo local (hash, magic-bytes, idempotencia)
                               + normalize_image() (estandariza a AVIF Q60 ≤1600px al ingresar,
                               fuente única; fija VIPS_CONCURRENCY=1) + placeholder_reason().
  shopify_variants.py        — parser de variants multi-tomo Shopify (ver #16).
  standardize_audit.py       — AUDIT de /watch-standardize-catalog (fuente única
                               skill+workflow, anti-drift): tiering + proyecciones
                               tier{1,2,3}.json con proposed_*, existing_edition_key,
                               known_edition_keys (#69), MÁS summary.json (contrato
                               de conteos {total,pending,tier1,tier2,tier3,exhausted},
                               auditoría 2026-07-08 hallazgo F6 — reemplaza el parseo
                               por regex del reporte de un subagente). Flags
                               --limit/--force-all/--base. Run dir default
                               `data/standardize-run/` (persistente; antes
                               `/tmp/manga-standardize-run`, volátil ante reboot —
                               hallazgo F3).
  standardize_apply.py       — APPLY de /watch-standardize-catalog (fuente única):
                               subcomandos tier1 y merge. El merge PRESERVA el
                               edition_key existente; sin keys usables → PENDIENTE.
                               Su propio DEFAULT_BASE sigue en /tmp (no tocado en el
                               movimiento de F3) — todo invocador pasa `--base
                               data/standardize-run` explícito para que coincida con
                               standardize_audit.py.
  wikis/                     — parsers dedicados. País + scope; detalles en gotchas/docs:
    listadomanga.py            ES — calendario mensual (delta).
    listadomanga_collections.py ES — coleccion.php?id=N (full vía lista.php). URLs
                                 sintéticas ?item= (#27). Box "en cofre" → #29.
                                 `--coleccion-ids-file` procesa ids explícitos (chunks, #50).
  ingest_listadomanga_full.py  — driver de ingesta COMPLETA por chunks resumibles: recorre
                                 lista.php en orden alfabético, checkpoint en
                                 data/listadomanga_full_progress.json (#50). Reanudable.
  review_lista_chunk.py        — auditoría INDEPENDIENTE de un chunk: re-fetchea cada coleccion
                                 y verifica que todo lo esperado (score≥30 + gate) esté en la DB.
    listadomanga_blog.py       ES — blog histórico (disponible, fuera del pipeline).
    manga_sanctuary.py         FR — planning. Valida title vs página (#2). visuel_defaut (#6).
    otaku_calendar.py          EN — releases por mes vía path /Calendar/{y}/{m} (backfill
                               histórico viable desde 2026-07-07, ver #3).
    manga_mexico.py            MX — catálogo alfabético por editorial.
    whakoom.py                 ES/LatAm — spider 3-niveles, opt-in (#14, #15).
    mangavariant.py            Global — base de variants 13 países (~2700). URL-referencia.
    socialanime.py             IT — MangaStore JSON. Amazon afiliados → /dp/<ASIN> (#26).
    blogbbm.py                 BR — 3 posts curados. Dispatch layout AB/C. ?bbm-entry= (#27).
    booksprivilege.py          JP — 店舗特典 por tienda. Decode utf-8 errors=replace (#28).
    sumikko.py                 JP — 限定版/特装版 (~3178). type-tag = extra, no filtrar (#30).
    mangapassion.py            DE — API REST. type[]=3 Sonderausgaben + variant-covers.
    prhcomics.py               US/CA — hardcovers + box sets EN (Penguin RH). ISBN-13 determinístico.
    kinokuniya.py              US — exclusivos Kinokuniya. Parser URL-based (Squarespace).
    yenpress_calendar.py       US — calendario mensual collector's/box/hardcover EN.
    animeclick.py              IT — edizioni speciali (AJAX semanal). Complementa socialanime.
    shueisha_books.py          JP — One Piece artbooks/databooks. Fetcher HARDCODEADO por seeds.
    viz_artbooks.py            US — ediciones especiales EN VIZ. Discovery por calendario.
    sevenseas.py               wiki US Seven Seas: listing API WP (books) + enrich por item (media?parent + ISBN/fecha del HTML). Filtro is_special_title (sin omnibus a secas ni Mature Hardcover).
    kodansha_us.py             wiki US Kodansha: API /wp-json/kodansha/v1/search-series → series page (volume list) → volume page (JSON-LD: ISBN/fecha/portada). Filtro is_special_series.
    storefront_json.py         5 storefronts API en UN módulo con perfiles: jd-intl (HK, WooCommerce), spp-tw (91APP), kimdong/ipm (VN, products.json), yaakz (TH, Laravel). Filtros de título por idioma.
  retrofit/                  — utilidades sobre data histórica. README.md + reglas
                               de backup/flush/nohup en "Conventions" abajo.
    rescore.py                 refresca score/signal_types/product_type (tras cambiar detectores). Salta approved y standardized (gotcha #61) salvo --include-*.
    clean_titles.py            re-limpia títulos.
    recover_lost_jp_titles.py  recupera nombres oficiales de items JP cuyo
                               title_original fue pisado (openBD por ISBN +
                               re-fetch Playwright de mangavariant). One-shot.
    extract_store_bonus.py     separa el bonus de TIENDA (店舗特典) del title al
                               campo store_bonus (gotcha #93). mw.split_store_bonus.
    restore_official_titles.py migración one-shot por item (2026-06-12, gotcha #92):
                               title = clean_title(title_original) — nombre OFICIAL,
                               sin traducir ni renombrar — y retira title_standardized.
                               Marca title_restored_at; re-corridas son no-op.
    normalize_release_dates.py normaliza release_date legacy a ISO (DD/MM/YYYY → YYYY-MM-DD; --all-formats para 年月日/datetime/textual). Automático [4b2] con --all-formats. Gotcha #80.
    fix_product_types.py       re-deriva product_type fuera del enum (special/deluxe/variant →
                               manga_watch.derive_product_type; fallback "manga"). Invariante PTYPE_ENUM.
    normalize_languages.py     normaliza language al canon español (14 idiomas) vía mapa de
                               sinónimos explícito (Deutsch/English/ja/en/…). Invariante LANG_ENUM.
    queue_regular_shielded.py  encola a unmapped_series.jsonl (reason regular_shielded_review) tomos
                               regulares estandarizados sin señal de bonus. Reusa
                               standardize_apply.append_unmapped_from_item. Default = lista; --apply escribe.
    normalize_isbn.py          normaliza+VALIDA el campo isbn del corpus histórico vía
                               mw.normalize_isbn() (checksum 10/13, GS1 978/979, convierte 10→13,
                               fail-safe con ISBN_ANOMALY). Compute-only, salta approved salvo
                               --include-approved. Registrado en script_registry.py. Gotcha #108.
    prune_state.py             housekeeping OPT-IN de data/state.json: poda entradas con
                               last_seen_at > N meses (default 12). --dry-run por defecto, backup
                               antes de escribir (--apply). NUNCA en el pipeline canónico (last_seen
                               viejo también es señal de mercado). No toca items.jsonl. Gotcha #138.
    filter_non_manga.py        re-filtra (is_likely_manga / is_comic_not_manga / is_pure_novel).
    filter_collectible.py      2º gate: descarta tomos regulares.
    backfill_metadata.py       re-fetch cover/author/ISBN (--only X). --only images = carrusel.
    backfill_cluster_key.py    backfill cluster_key tras cambiar derive_cluster_key.
    backfill_series_aliases.py remapea series_key/display por series_aliases.yml (fuente única
                               canonical_series_key), re-deriva cluster_key + consolida vía
                               consolidate_by_cluster. --only-keys REQUERIDO (scope acotado;
                               --all exige --yes-i-know-collateral). Reemplaza el snippet
                               embebido del skill /watch-enrich-series-aliases (Step 4).
                               Registrado en script_registry.py (--all/--yes-i-know-collateral
                               NO expuestos en el panel — footgun deliberadamente solo-CLI).
    consolidate_sources.py     colapsa filas del mismo cluster en 1 con sources[] (paso [4g]).
    search_discovery.py        discovery multi-engine (Gemini + Tavily + DDG). Escritura vía
                               backup_and_rotate + append_jsonl con flush cada --flush-every
                               queries (default 8, no write único al final); dedup intra-run por
                               URL normalizada; engines agotados (DDG 202 / Gemini 429) se
                               desactivan para el resto de la corrida. Gotcha #133.
    wayback_recover.py         recupera items 404/410 vía archive.org (no 403/429, ver #13).
                               Guard `approved_at` (--include-approved), flush atómico
                               (tmp+fsync+os.replace), mapea metadata `name`→`title` (nunca
                               escribe `name`), caché negativa persistente en
                               `data/wayback_negative_cache.json` (TTL 90d, --no-negative-cache
                               para ignorarla; sólo cachea "sin snapshot" CONFIRMADO, nunca
                               429/timeout). Gotcha #133.
    expand_whakoom_ediciones.py / expand_index_pages.py  expanden páginas-índice (#14, #16, #17).
    strip_legacy_cover_fields.py  migración one-shot (2026-06-09): elimina image_url/
                               image_local top-level del item; portada = images[0].
    mirror_images.py           backfill espejo local (todas las images[]) + GC mark-and-sweep.
    purge_placeholder_images.py  quita de images[] las fotos placeholder (1×1, blanco,
                               "no disponible"), via image_store.placeholder_reason() +
                               data/placeholder_signatures.json. Paso [4i] del pipeline (#97).
    upgrade_image_resolution.py / promote_hires_cover.py / backfill_prh_covers.py /
    upscale_images.py / fetch_better_covers.py / sync_cover_preview.py
    optimize_images.py         backfill genérico: estandariza el espejo histórico a AVIF
                               (resize+encode, archiva originales a _originals/).
    migrate_images_to_avif.py  migración WebP→AVIF re-derivando desde _originals/ + dedup por
                               contenido + commit incremental (RESUMIBLE; un crash no rehace).
                               — mejora de portadas (CDN full-res, hi-res intra-cluster,
                               PRH, AI upscale, búsqueda, sincronización de cola).
                               fetch_better_covers: SEGURO POR DEFECTO (preview, no auto-aplica
                               baja confianza). --apply (alta confianza) / --apply-preview.
                               sync_cover_preview.py: poda candidatas pending cuya premisa ya
                               no existe; invocado automáticamente por GET /api/cover-preview.
    revalidate_cover_preview.py  re-valida OFFLINE candidatas pending viejas (match_dist null, del
                               skill drifteado) contra el gate endurecido reusando _same_cover/
                               _is_soft_image + sync_preview (moot). PASA→verified+match_dist;
                               FALLA→rejected(auto_revalidation); sin-ref→verified:false. No escribe
                               el ledger. Idempotente. --dry-run/--apply. Tests: test_revalidate_cover_preview.py.
                               fetch_better_covers: además de --limit, acepta --slugs slug1,slug2
                               (coma-sep y/o repetible) para acotar la corrida a slugs exactos; los
                               pedidos que no son candidatos se reportan y se saltean.
    scripts/eval/              harness de EVALUACIÓN reproducible (offline, sin red, determinístico).
      eval_cover_gate.py       mide el gate de identidad de portadas (old aspect-only ±0.30 vs new
                               _same_cover+_is_soft_image, delegación pura) sobre una muestra
                               etiquetada + trampas sintéticas PIL; reporta matriz FP/FN por
                               categoría de la taxonomía. --json/--synthetic-only. Ver images.md.
      cover_gate_sample.json   manifest de la muestra (10 positivos + 12 negativos reales,
                               paths a data/images/; las sintéticas se generan al vuelo).
                               Test: test_eval_cover_gate.py.
    sync_cover_images.py       saneamiento integral de imágenes (#31): portada mala, images[0]
                               sync, basura UI, productos relacionados.
    translate_descriptions.py  description → description_es (Google Translate + DeepL opcional).
    generate_slugs.py          genera slug (último paso de /watch-standardize-catalog).
    set_rarity.py              aplica rarity vía derive_rarity_tier().
    apply_rarity_verdicts.py   aplica veredictos web (data/diagnostics/rarity_validation_results.json)
                               del skill /watch-validate-rarity: stock_status como evidencia +
                               re-deriva rarity con derive_rarity_tier(). Re-selecciona candidatos
                               con audit/rarity_candidates.rarity_uncertainty_reason (fuente única).
                               Guard approved + backup_and_rotate + log a
                               data/diagnostics/rarity_validation_log.jsonl. Reemplaza el Step 3
                               embebido del skill (auditoría Fable 2026-07-08, hallazgo F5).
    fix_item_fields.py         mini-helper --url/--slug X --set campo=valor (multi --set) para
                               correcciones puntuales de items.jsonl. Allowlist de campos + campo
                               sintético cover_url (delega en image_store.set_cover). title
                               BLOQUEADO salvo --allow-title (política de títulos, gotcha #92).
                               Re-deriva cluster_key si tocó sus insumos (gotcha #55). Guard
                               approved + backup_and_rotate. Reemplaza los snippets K/M embebidos
                               del skill /watch-review-feedback (hallazgo F12).
    sc_plan.py                 planificador determinista (Step 1) del skill /watch-search-covers:
                               identifica targets de baja calidad/ausentes, arma variantes de query
                               por idioma (whakoom/yandex/texto), aplica guards de skip (cola,
                               memoria de intentos 30d, referencia degenerada). Escribe
                               .tmp_sc_plan.json/.tmp_sc_acc.json — NUNCA items.jsonl. Reemplaza
                               las ~300 líneas embebidas del skill (hallazgo F9).
    apply_approvals.py         re-materializa approvals.jsonl tras reconstruir el catálogo.
    fix_edition_key_anomalies.py  normaliza edition_key: panini-es→panini + xx→país (tier: source country → grupo ISBN → editorial mono-país → hermano de la misma edición). Enforcer 2b.
    disambiguate_coleccion_editions.py  coleccion distinta=edición distinta: -c{cole} si edition_key colisiona (#57). Enforcer 3-0.
    collapse_baseurl_tomos.py     fusiona fila base-url phantom en su tomo sintético del mismo (cole,vol) (#56). Enforcer 3-1.
    merge_crosssource_into_lmc.py fusiona ficha de tienda (edition:) en su tomo lmc por edition_key+vol+título (#56). Enforcer 3-2.
    canonicalize_edition_slugs.py re-aplica la tabla término→slug de tipo de edición post-LLM (no-lmc) + absorbe hermanas confundibles (#69). Enforcer 3c1.
    merge_duplicate_series.py     fusiona series_keys/canónicas del YAML partidas por variantes mecánicas del slug (#70). Enforcer 3c2.
    merge_isbn_duplicates.py   fusiona filas que comparten ISBN-13 (mismo producto físico partido por drift de edition_key o volumen vacío); ganador por approved>publisher-real>evidencia-serie-en-URL>popularidad-ek. Salta lmc/conflicto país/volumen. Invariante ISBNDUP.
    normalize_edition_publishers.py unifica por mayoría el publisher dentro de cada edition_key. Enforcer 3c3.
    fix_edition_key_prefix.py     re-alinea el prefijo de serie del edition_key con el series_key
                               vía rebuild_edition_key_prefix() (#71). Enforcer 3c4.
    fix_title_edition_words.py    colapsa palabra de edición duplicada en el título + quita
                               "Regular" sobrante en ediciones regulares (#72). Enforcer 3c5.
    remove_phantom_calendar_editions.py  borra ediciones especiales/artbook FANTASMA del
                               calendario+estandarización (no existen en la página real) y quita
                               portadas que son el bonus de otro tomo (#99). Listas explícitas
                               verificadas a mano. Guarda durable: invariante STOLENIMG. One-shot.
    remove_free_preview_editions.py  borra folletos promocionales GRATUITOS de ListadoManga
                               ("Número Gratuito", preview del 1er cap/mini-artbook) colados como
                               edición especial (#103). Prevención durable: FREE_PRICE_PATTERN en
                               listadomanga_collections.py (delta+full). One-shot (13 borrados).
  export_series_aliases.py     series_aliases.yml → data/series_aliases.json (vista de
                               búsqueda por alias para ambas UIs; lo invoca build_web.py).
  validate_corpus.py           VALIDADOR ESTRUCTURAL (sin red, gate de salud del pipeline, paso [5]
                               de scrape_*.sh). Chequea en UNA pasada TODAS las invariantes duras:
                               SLUG, CLKEY (cluster_key auto-consistente), DUPCL, DUPSYN (#54),
                               LMCKIND, TITLE, ONECOLE, DUPVOL (tomo duplicado en una edición, #56/#57)
                               + warnings COLED/PAIS/EDSLUG (#69)/SERIESDUP (#70)/EKPREFIX (#71)/PUBMIX/
                               STOLENIMG (portada de tomo normal = extra de otra fila, #99).
                               Exit≠0 si hay violación dura.
  audit_lista_full_bidir.py    auditoría de RED bidireccional: re-fetchea las 3436 colecciones de
                               lista.php y compara (kind,vol) parser vs DB → FALTANTES + SOBRANTES.
  audit/
    source_health.py           clasifica fuentes desde N logs recientes. Desde 2026-07-07 también
                               acumula logs/metrics.jsonl (--metrics-file) y alerta regresiones de
                               yield vs. mediana histórica del mismo modo (--baseline-alert --mode
                               delta|full, warm-up ≥3 runs). Auditoría 2026-07-08 (paquete
                               B-observabilidad): parsea categorías SKIP con guion (no-links/js-shell),
                               `[CHALLENGE_DETECTED]` como categoría propia `broken_challenge` (antes
                               una fuente bloqueada por anti-bot salía "healthy", gotcha #107), nombres
                               de search-template con ':' adentro sin truncar, siembra `unseen` con las
                               fuentes enabled de sources.yml + los 26 wikis (`wiki:<id>`, parseados
                               desde el log `[BOOTSTRAP-WIKI]`/`[RESUMEN BOOTSTRAP-WIKI]` de cada uno —
                               antes 100% invisibles), y excluye runs con error de la mediana de yield
                               (evita que ceros falsos apaguen la detección de regresión para siempre).
    staleness_report.py        NUEVO — read-only, sin red. Cuenta por fuente cuántas URLs de
                               data/state.json llevan >N días (default 90) sin verse. No propone
                               borrar nada, siempre exit 0. Invocado al final de scrape_delta/full.sh.
    unmapped_series.py         series_keys sin alias, fuzzy-matched. Lo lee enrich-series-aliases.
    rarity_candidates.py       selecciona/agrupa/prioriza (Step 0/1) los rarity='rare' por
                               INCERTIDUMBRE del skill /watch-validate-rarity. rarity_uncertainty_
                               reason() es la ÚNICA implementación del tracer (antes duplicado 2x en
                               el SKILL.md); test de coherencia por-rama contra derive_rarity_tier()
                               en tests/test_rarity_candidates.py. Escribe
                               data/diagnostics/rarity_validation_candidates.json. Solo lectura.
                               Reemplaza el Step 0/1 embebido del skill (hallazgo F5).
    data_quality.py            audit SOLO LECTURA → quality_report.json + check_urls(). Ver quality.html.
                               Auditoría 2026-07-08: "archivo_tiny"/"pixelada" (y check_urls, el
                               live-update del panel) juzgan por PÍXELES vía `image_store.
                               placeholder_reason()` (fuente única: broken/tiny:WxH/solid:STD/
                               signature:LABEL), NO por bytes<6KB — el espejo es 100% AVIF y comprime
                               tan bien que portadas reales de ~600x900 pesan <6KB (~1060 falsos
                               positivos medidos, corregido a 0 sobre el corpus real); fallback a
                               bytes<6KB sólo sin Pillow/--no-measure. `check_urls` ahora también
                               respeta `data/dup_decisions.jsonl` (antes sólo `audit_items`).
.claude/skills/              — skills MANUALES (solo bajo pedido explícito, ver política arriba):
  feature-spec/                Vía C: entrevista + exploración → spec en docs/specs/. No implementa.
  ship-check/                  gate pre-commit: checks por área tocada + auditoría docs-sync.
  product-pulse/               post-launch: PostHog + feedback.jsonl → backlog priorizado.
  standardize-catalog/         items sin standardized_at → asigna keys, mueve non-manga, dedup (#21).
    prompt-rules.md             FUENTE ÚNICA de las reglas de negocio del prompt LLM
                                 (edition_key, publisher/país/tipo de edición, 画集付き,
                                 coleccion=edición, allowlists) — SKILL.md y
                                 .claude/workflows/watch-standardize-catalog.js la leen,
                                 ninguno la copia (auditoría 2026-07-08, hallazgo F7: la
                                 regla 画集付き vivía solo en SKILL.md, drift confirmado).
  enrich-series-aliases/       cola unmapped → series_aliases.yml vía Anilist (#20).
  evaluate-sources/            evalúa fuentes candidatas antes de implementar.
  review-feedback/             procesa feedback.jsonl (14 categorías A–N). Fixes K/M/N puntuales vía
                               scripts/retrofit/fix_item_fields.py (hallazgo F12; title bloqueado
                               salvo --allow-title, política de títulos gotcha #92).
  validate-rarity/             verifica vía web los rare por incertidumbre (retailer_exclusive sin
                               stock / fuente de referencia). Step 0/1 → scripts/audit/
                               rarity_candidates.py; Step 3 (apply) → scripts/retrofit/
                               apply_rarity_verdicts.py (hallazgo F5, tracer fuente única).
  search-covers/               busca portadas hi-res para items con imagen pequeña (<min-pixels)
                               o ausente. Usa Serper API (preferido) o Chrome (fallback). Escribe
                               candidatas a cover_preview.json. NUNCA toca items.jsonl. Step 1 (plan
                               de queries) compilado a scripts/retrofit/sc_plan.py (hallazgo F9).
web/  (dashboard HTML público + paneles)
  index.html                 — dashboard Alpine.js. Filtros, detalle, feedback 👎,
                               aprobación 👍, edición inline ✏️, selección batch,
                               curación rápida (atajos A/U/R/E/S/J/K), lightbox.
  quality.html               — Panel de Calidad (live-update vía BroadcastChannel + recheck).
  cover-preview.html         — aprobación visual de portadas (multi-candidato).
  image-manager.html         — gestor de imágenes (cluster-level). Deep-link ?item=&return=.
                               "🔍 Buscar portada en Google" (abre Google Imágenes).
  panel.html                 — Panel de Control (lee script_registry.py).
  favicon.ico / apple-touch-icon.png — favicon de la app HTML (panda sobre fondo rosa
                               de acento; diferencia de la app pública Next.js). Generados
                               por scripts/gen_html_favicon.py. serve.py los sirve en raíz.
admin/index.html             — redirect → web/panel.html.
web-next/                    — app Next.js 16 + Tailwind v4 (reemplazo del dashboard).
  app/                         App Router. Rutas: / /series/[k] /edition/[k] /item/[slug]
                               (detalle = SSG puro, dynamicParams=false) + robots/sitemap/manifest.
  components/{modules,catalog,series,edition,item,seo}/  — ver docs/web-next
                               (core/ eliminado 2026-06-12: código muerto sin consumidores).
  lib/{types,data,filters,format,images,seo,jsonld,descriptions,styles}.ts
                               — data: cache por mtime + índices Map + helpers de sitemap;
                               format: fechas multi-formato; images: dedup único;
                               seo: paths encoded + decodeRouteParam + og.
  public/images → ../../data/images/  — symlink al espejo local.
tests/test_extraction.py     — pytest suite (~645 tests, <5s).
docs/                        — README.md índice + scraper/ (ARCHITECTURE, SOURCES, PRD,
                               PIPELINE-WALKTHROUGH = runbook completo del ciclo de vida del dato)
                               + web-html/PRD + admin/README + web-next/ (FRDs, blueprints, WOs)
                               + process/AI-WORKFLOW.md (flujo de implementación con IA: vías
                               A/B/C, verificación, eficiencia de tokens) + specs/ (SPEC-* de
                               /feature-spec, uno por épica).
```

