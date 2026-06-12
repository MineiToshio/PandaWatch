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
  state.json                 — cache de URLs vistas (detección incremental).
  feedback.jsonl             — cola del botón 👎. Item completo + reason + action
                               (feedback|move|merge|remove). Skill /watch-review-feedback.
  approvals.jsonl            — log append-only de aprobaciones (👍). Replay vía
                               retrofit/apply_approvals.py. Ver "Aprobación humana".
  dup_decisions.jsonl        — log append-only de decisiones sobre "posibles
                               duplicados" del Panel de Calidad (merged|distinct,
                               por signature). data_quality.py no re-sugiere los
                               ya decididos. Endpoints /api/dup/{merge,decide}.
  edits.jsonl                — log append-only de ediciones inline (auditoría).
  quality_report.json        — output de audit/data_quality.py; lo lee quality.html.
  cover_preview.json         — candidatas de portada pendientes de aprobación.
  non_manga_blacklist.jsonl  — items movidos fuera por /watch-standardize-catalog.
  unmapped_series.jsonl      — FUENTE ÚNICA para flagear cualquier registro
                               incierto (serie/edición/publisher). NUNCA crear
                               archivos paralelos uncertain_X/review_X. Schema:
                               series_key (req) + contexto + flagged_by
                               (pipeline|audit:<n>|human) + opcionales libres.
                               Lo vacía /watch-enrich-series-aliases; el pipeline lo repuebla.
  images/                    — espejo local de portadas: <sha256(url)[:16]>.<ext>.
                               El JSONL referencia el filename en image_local.
  backups/<archivo>/         — backups rotativos (máx 3) vía backup_and_rotate().
                               NUNCA a mano ni en /tmp.
  diagnostics/               — outputs de debug de los filtros (se sobreescriben).
scripts/
  manga_watch.py             — módulo principal (~7k líneas): filtros, scoring, IO,
                               loop paralelo, dispatchers Bluesky/Playwright/HTTP,
                               derive_cluster_key, merge_cluster/consolidate_by_cluster.
  build_web.py               — lee items.jsonl, agrupa por cluster_key, embebe en
                               web/index.html (o deja [] → fetch live).
  serve.py                   — SERVIDOR ÚNICO (threaded). Sirve web/ + data/ + todos
                               los /api/*. Bind 0.0.0.0:8000. Ver gotcha #34 (@_serialized).
  admin_serve.py             — DEPRECATED (absorbido por serve.py).
  script_registry.py         — fuente única del Panel de Control. Agregás un script
                               acá, aparece en la UI.
  run_local.sh / serve.sh    — lanzan serve.py en :8000.
  scrape_delta.sh            — ⭐ CANÓNICO INCREMENTAL (~30-60 min, diaria/semanal). Lock global + [4g2] merge ISBN + PHASE 6 source_health.
  com.pandawatch.scrape-delta.plist — LaunchAgent macOS para delta diario 3:30 AM (instrucciones dentro; NO instalado por defecto).
  scrape_full.sh             — ⭐ CANÓNICO FULL (~2-4 h, mensual/trimestral).
  overnight_run.sh           — DEPRECATED (alias de scrape_delta.sh).
  retry_failed.sh            — re-corre solo las fuentes que erraron en el último log.
  series_aliases.py          — canonical_series_key() + log_unmapped_series(). Ver #20.
  image_store.py             — primitivas del espejo local (hash, magic-bytes, idempotencia).
  shopify_variants.py        — parser de variants multi-tomo Shopify (ver #16).
  standardize_audit.py       — AUDIT de /watch-standardize-catalog (fuente única
                               skill+workflow, anti-drift): tiering + proyecciones
                               tier{1,2,3}.json con proposed_*, existing_edition_key,
                               known_edition_keys (#69). Flags --limit/--force-all.
  standardize_apply.py       — APPLY de /watch-standardize-catalog (fuente única):
                               subcomandos tier1 y merge. El merge PRESERVA el
                               edition_key existente; sin keys usables → PENDIENTE.
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
    otaku_calendar.py          EN — releases del mes actual (sólo, ver #3).
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
    restore_official_titles.py migración one-shot por item (2026-06-12, gotcha #92):
                               title = clean_title(title_original) — nombre OFICIAL,
                               sin traducir ni renombrar — y retira title_standardized.
                               Marca title_restored_at; re-corridas son no-op.
    normalize_release_dates.py normaliza release_date legacy a ISO (DD/MM/YYYY → YYYY-MM-DD; --all-formats para 年月日/datetime/textual). Gotcha #80.
    filter_non_manga.py        re-filtra (is_likely_manga / is_comic_not_manga / is_pure_novel).
    filter_collectible.py      2º gate: descarta tomos regulares.
    backfill_metadata.py       re-fetch cover/author/ISBN (--only X). --only images = carrusel.
    backfill_cluster_key.py    backfill cluster_key tras cambiar derive_cluster_key.
    consolidate_sources.py     colapsa filas del mismo cluster en 1 con sources[] (paso [4g]).
    search_discovery.py        discovery multi-engine (Gemini + Tavily + DDG).
    wayback_recover.py         recupera items 404/410 vía archive.org (no 403/429, ver #13).
    expand_whakoom_ediciones.py / expand_index_pages.py  expanden páginas-índice (#14, #16, #17).
    strip_legacy_cover_fields.py  migración one-shot (2026-06-09): elimina image_url/
                               image_local top-level del item; portada = images[0].
    mirror_images.py           backfill espejo local (todas las images[]) + GC mark-and-sweep.
    upgrade_image_resolution.py / promote_hires_cover.py / backfill_prh_covers.py /
    upscale_images.py / fetch_better_covers.py / sync_cover_preview.py
                               — mejora de portadas (CDN full-res, hi-res intra-cluster,
                               PRH, AI upscale, búsqueda, sincronización de cola).
                               fetch_better_covers: SEGURO POR DEFECTO (preview, no auto-aplica
                               baja confianza). --apply (alta confianza) / --apply-preview.
                               sync_cover_preview.py: poda candidatas pending cuya premisa ya
                               no existe; invocado automáticamente por GET /api/cover-preview.
    sync_cover_images.py       saneamiento integral de imágenes (#31): portada mala, images[0]
                               sync, basura UI, productos relacionados.
    translate_descriptions.py  description → description_es (Google Translate + DeepL opcional).
    generate_slugs.py          genera slug (último paso de /watch-standardize-catalog).
    set_rarity.py              aplica rarity vía derive_rarity_tier().
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
  export_series_aliases.py     series_aliases.yml → data/series_aliases.json (vista de
                               búsqueda por alias para ambas UIs; lo invoca build_web.py).
  validate_corpus.py           VALIDADOR ESTRUCTURAL (sin red, gate de salud del pipeline, paso [5]
                               de scrape_*.sh). Chequea en UNA pasada TODAS las invariantes duras:
                               SLUG, CLKEY (cluster_key auto-consistente), DUPCL, DUPSYN (#54),
                               LMCKIND, TITLE, ONECOLE, DUPVOL (tomo duplicado en una edición, #56/#57)
                               + warnings COLED/PAIS/EDSLUG (#69)/SERIESDUP (#70)/EKPREFIX (#71)/PUBMIX.
                               Exit≠0 si hay violación dura.
  audit_lista_full_bidir.py    auditoría de RED bidireccional: re-fetchea las 3436 colecciones de
                               lista.php y compara (kind,vol) parser vs DB → FALTANTES + SOBRANTES.
  audit/
    source_health.py           clasifica fuentes desde N logs recientes.
    unmapped_series.py         series_keys sin alias, fuzzy-matched. Lo lee enrich-series-aliases.
    data_quality.py            audit SOLO LECTURA → quality_report.json + check_urls(). Ver quality.html.
.claude/skills/              — skills MANUALES (solo bajo pedido explícito, ver política arriba):
  feature-spec/                Vía C: entrevista + exploración → spec en docs/specs/. No implementa.
  ship-check/                  gate pre-commit: checks por área tocada + auditoría docs-sync.
  product-pulse/               post-launch: PostHog + feedback.jsonl → backlog priorizado.
  standardize-catalog/         items sin standardized_at → asigna keys, mueve non-manga, dedup (#21).
  enrich-series-aliases/       cola unmapped → series_aliases.yml vía Anilist (#20).
  evaluate-sources/            evalúa fuentes candidatas antes de implementar.
  review-feedback/             procesa feedback.jsonl (14 categorías A–N).
  search-covers/               busca portadas hi-res para items con imagen pequeña (<min-pixels)
                               o ausente. Usa Serper API (preferido) o Chrome (fallback). Escribe
                               candidatas a cover_preview.json. NUNCA toca items.jsonl.
web/  (dashboard HTML público + paneles)
  index.html                 — dashboard Alpine.js. Filtros, detalle, feedback 👎,
                               aprobación 👍, edición inline ✏️, selección batch,
                               curación rápida (atajos A/U/R/E/S/J/K), lightbox.
  quality.html               — Panel de Calidad (live-update vía BroadcastChannel + recheck).
  cover-preview.html         — aprobación visual de portadas (multi-candidato).
  image-manager.html         — gestor de imágenes (cluster-level). Deep-link ?item=&return=.
                               "🔍 Buscar portada en Google" (abre Google Imágenes).
  panel.html                 — Panel de Control (lee script_registry.py).
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

