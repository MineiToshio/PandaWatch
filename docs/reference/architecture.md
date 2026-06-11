# Arquitectura — pipeline, storage, las 7 decisiones de diseño

> Documento de referencia de PandaWatch, cargado **bajo demanda** desde
> [CLAUDE.md](../../CLAUDE.md). Leelo cuando vayas a trabajar en este tema.

## High-level pipeline

```
sources.yml  (138 entries, ~67 enabled)
    │
    ▼
manga_watch.py (scraper)  ←─── ThreadPoolExecutor(--workers N)
  • fetch HTML / RSS / Bluesky API / sitemap per source
  • extract_listing_candidates() / extract_rss() /
    extract_bluesky_posts() / sitemap miner
  • score_candidate() — assigns 0-300 score by signal detection
  • is_likely_manga() — 4-rule cascade (figures, comics, news, etc.)
  • is_pure_novel() — rejects pure light novels (URL hints + words)
  • is_comic_not_manga() — comics blacklist with "manga" bypass
  • clean_title() — strips e-commerce junk, mojibake, news prefixes
  • fetch_metadata_from_detail() — opt-in HTTP per item for cover/
    author/price/ISBN via JSON-LD + label/value pairs (also
    parallelized in the --fetch-details stage)
  • mirror_candidate_images() — descarga la portada de cada item
    nuevo/cambiado a data/images/ (espejo local, campo image_local).
    On by default; --skip-image-download para saltearlo.
    │
    ▼
data/items.jsonl  ← 1 fila por PRODUCTO (cluster_key) con sources[].
                    append_jsonl: upsert por URL + consolidación por
                    cluster_key. Un producto re-encontrado suma su fuente
                    a sources[], no agrega fila. Ver decisión #1.
data/images/      ← espejo local de portadas (image_local apunta acá)
data/state.json   ← cache of seen URLs (for incremental detection)
    │
    ▼
build_web.py  ← reads JSONL, groups by cluster_key (ISBN or fuzzy
                lang+series+vol+variants+publisher), embeds in HTML
web/index.html ← Alpine.js dashboard (filters incl. signal_types
                 chip filter, search, multi-source modal)
    │
    ▼
http://localhost:8000/ (via scripts/serve.py — servidor ÚNICO)
  + POST /api/feedback, /api/curation/*, /api/item/update,
    /api/approve(-edition), /api/batch/{approve,move},
    /api/quality/check (re-verificación por ítem), POST
    /api/save-cover-preview + /api/apply-cover-preview
    (aplica aprobadas del revisor al catálogo) (catálogo)
  + GET /api/scripts, POST /api/run, GET+SSE /api/jobs/* (panel)
  web/panel.html → Panel de Control. Lee scripts/script_registry.py
  y permite ejecutar scripts con toggles + presets + logs en vivo (SSE).
  web/quality.html → Panel de Calidad. Lee data/quality_report.json
  (lo genera scripts/audit/data_quality.py) y lo muestra como worklists
  clickeables. Detalle en docs/admin/README.md.

Orchestration: scrape_delta.sh / scrape_full.sh (decisión #7) encadenan
  scrape (parallel) → wiki bootstraps →
  cleanup retrofits (rescore, filter_non_manga, filter_collectible,
  clean_titles, backfill_metadata, [wayback_recover]) →
  consolidate_sources → build_web.

Observability: scripts/audit/source_health.py parses N recent overnight
  logs and classifies sources (broken_http / selector_dead / declining
  / healthy / unseen).
```


## Current corpus state

Baseline para sanity-check (medido 2026-06-10 tras auditoría/fixes). Si un retrofit
tira la image coverage de 99% a 60%, algo se rompió. Números aproximados; se vuelven
stale — re-medí con un snippet sobre items.jsonl si necesitás precisión.

| Métrica | Valor aprox. |
|---|---|
| Total items (1 fila por producto) | **10 645** |
| Movidos a non_manga_blacklist.jsonl (acum.) | ~591 (+17 audit 2026-06-10 incl. Sorayama artbook bajo "Venom") |
| Removidos por umbrella URL-gate (ATOM FR) | 21 (revista Manga-Sanctuary; ver gotcha #62) |
| Removidos quirúrgicamente (junk confirmado) | 5 (respaldados en `data/diagnostics/items.audit_fp_removed-20260610.jsonl`) |
| series_aliases.yml | ~2844 canónicos (~32% con aliases multilingüe) |
| Sources en YAML / enabled | 138 / 67 (17 mixed, 15 bluesky todas off) |
| Wikis (`--bootstrap-wiki`) | 19 |
| Top sources | Sumikko ~2717, Mangavariant ~1606, AnimeClick IT ~1037, ListadoManga colecciones ~987, Manga-Sanctuary ~926, Manga-Passion DE ~793 |
| Image / image_local coverage | ~99.9% / ~99.8% |
| series_key / edition_key / standardized_at | ~99% / ~99% / ~99.6% |
| slug | 100% |
| volume / release_date / ISBN / price / author | ~84% / ~91% / ~48% / ~51% / ~56% |
| cluster_key populado | 100% |
| carrusel real (images.length > 1) | ~2623 (26%) |
| Países | 13 (top: Japón ~3758, Italia ~2182, Francia ~1295, España ~1279, Alemania ~841, EEUU ~309) |
| validate_corpus | 0 violaciones duras; 7 warnings PAIS (editoriales multi-país / `unknown`) |

ISBN/price/author bajos NO son regresión: muchas filas curadas (Mangavariant,
wikis) catalogan "qué variant existe", no "dónde comprarlo" (ver "URL como referencia").


## Modelo de rareza — `derive_rarity_tier()` en `set_rarity.py`

Rediseño 2026-06-10: **default-common** (antes default-rare con 54% de precisión medida).

### Tiers (de mayor a menor)

| Tier | Criterio |
|---|---|
| `ultra_rare` | Numerado/firmado A MANO (`_has_hand_signed` con guard de firma impresa), lotería-evento, o print run ≤ 500 |
| `super_rare` | Print run ≤ 2500, o `retailer_exclusive` + `out_of_stock` |
| `rare` | Print run > 2500 y confirmado agotado; o `retailer_exclusive` sin verificar (con `in_stock` VERIFICADO sigue la cascada → normalmente common; decisión owner, caso Ichi the Witch); o tokuten; o keyword de no-reimpresión (`_SINGLE_RUN_KEYWORDS`: incluye 限定版, 特装版 y similares; se removió la familia genérica "limited edition" para evitar FP); o patrón de tirada única (`_SINGLE_RUN_PATTERNS`); o **fallback de fuente de referencia** (ver abajo) |
| `common` | **Default** — sin evidencia de escasez |

### Fallback de fuentes de referencia (2026-06-10, decisión owner)

Si un item proviene ÚNICAMENTE de fuentes de `_REFERENCE_ONLY_SOURCES` (Mangavariant,
Sumikko, BooksPrivilege, BlogBBM — catalogan SOLO coleccionables, no catálogo de
tienda) y **ninguna regla de evidencia lo clasificó** (caería al default common), la
incertidumbre se resuelve a `rare`: que esté documentado en una DB de coleccionismo y
en ninguna tienda ES la señal. NO aplica si: (a) alguna regla de evidencia ya decidió
(esas ganan), (b) el item también tiene una fuente no-referencia (una tienda lo vende),
o (c) `stock_status == "in_stock"`. `derive_rarity_tier` recibe `sources=[...]` (todas
las fuentes del item) desde `set_rarity.py`; en scrape-time la fila es mono-fuente y
basta el param `source`.

### Cobertura multilingual (2026-06-10, investigación por mercado)

- `_PRINT_RUN_RE` cubre además de "limited to N copies": "tiratura limitata **di** N copie",
  "**in sole/soli** N copie/esemplari/**pezzi**" (IT), "limitiert auf N **Exemplare**" (DE),
  "limitada a N **ejemplares**" (ES), "limited to N **numbered** copies" (EN).
- `_SINGLE_RUN_PATTERNS` (nueva, tier rare): Lucca word-boundary; exclusivas de
  evento/festival con orden de palabras libre ("sold exclusively at Napoli Comicon");
  variantes furoku/appendix de revista JP (inobtenibles fuera de segunda mano);
  exclusiva de retailer en texto ("exclusive to Kinokuniya bookstores"); out-of-print
  multilingual (esaurito/descatalogado/vergriffen/épuisé/絶版/out of print).
- `_SINGLE_RUN_KEYWORDS` suma: "édition/coffret collector" FR (política oficial Pika:
  las ediciones collector NO se reimprimen — misma convención que 限定版 JP),
  "no habrá reimpresiones"/"no se reimprime" ES, y exclusivas de tienda JP
  (アニメイト限定/とらのあな限定/ゲーマーズ限定/店舗限定/完全生産限定/数量限定).
- `_ULTRA_RARE_KEYWORDS` suma: "nummeriert" DE, "autografato/a" IT ("firmato" sigue
  excluido — significa "de autoría"), "convention exclusive", 会場限定/イベント限定 JP.
- `set_rarity.py` NUNCA recalcula items con `rarity_verified_at` (ground truth de la
  skill watch-validate-rarity), ni siquiera con `--force`; override: `--include-verified`.

### Campo `stock_status`
`''` | `'in_stock'` | `'out_of_stock'` (+ `stock_checked_at` ISO UTC). Hoy lo escribe
la skill `/watch-validate-rarity` (verificación web manual de los rares por
incertidumbre, con log en `data/diagnostics/rarity_validation_log.jsonl`); el retrofit
`check_stock.py` (PENDIENTE — no escrito) llenará la misma interfaz desde las páginas
fuente. `set_rarity` lo lee pero no lo escribe.

### Distribución del corpus (2026-06-10, post cobertura multilingual, `--force`)

| Tier | Items | % |
|---|---|---|
| `common` | 6 183 | 57% |
| `rare` | 4 479 | 41% |
| `super_rare` | 72 | <1% |
| `ultra_rare` | 117 | ~1% |

Antes del rediseño: ~81% `rare` con ~54% de precisión medida. La mejora viene de que
"sin evidencia" ya no implica escasez. La pasada multilingual movió 368 items
(361 common→rare, 7 →ultra_rare) con evidencia textual que el código no capturaba;
el fallback de fuentes de referencia movió otros 996 (Mangavariant-only sin evidencia).
El piloto de `/watch-validate-rarity` (2026-06-11) verificó 12 ediciones italianas:
6 exclusivas agotadas promovidas a super_rare, 1 democión a common, 5 rare confirmados.


## The 7 design decisions you MUST understand

### 1. Storage = JSONL, UNA fila por PRODUCTO con `sources[]` (no por URL)

`items.jsonl` guarda **una línea por PRODUCTO físico** (cluster), no por URL. Cada
fila lleva `sources[]` con todas las fuentes donde se encontró (cada entrada:
name/url/price/country/stock_type/image_url… vía `source_entry()`). Cuando el
scraper re-encuentra un producto existente, suma la fuente a `sources[]` en vez de
agregar fila. `append_jsonl()`: (1) upsert por URL normalizada; (2) `sources[]`
sticky+merge (un re-scrape de una fuente no borra las hermanas); (3) consolidación
final por `cluster_key` vía `consolidate_by_cluster()`. Para filas con
`standardized_at`, `_CURATED_FIELDS` preserva además `slug`/`detected_at`/`score`/
`signals`/`signal_types` y el merge re-deriva `cluster_key` (tier `edition:`) —
un re-scrape NO degrada filas estandarizadas (gotcha #65). `slug` es sticky para
TODOS los items.

**`merge_cluster()` / `consolidate_by_cluster()` / `source_entry()` en
`manga_watch.py` son la FUENTE ÚNICA del merge.** Las usan `append_jsonl`,
`build_web` y `consolidate_sources.py`. NUNCA reimplementar el merge en otro lado
(la divergencia causó bugs de fotos). `merge_cluster` elige la canónica
(aprobada > estandarizada > ISBN > imagen > precio), rellena faltantes, une
`sources[]` (dedup por URL), une `images[]` con **portada canónica primera**
(carrusel[0] == card) y une `extras[]`.

`cluster_key` no es estable hasta estandarizar (el heurístico a veces deja
`edition_key` vacío → `cluster_key=url:`; `/watch-standardize-catalog` le asigna el real).
Por eso `consolidate_sources.py` corre como paso final del pipeline (`[4g]`),
DESPUÉS de la estandarización. Idempotente.

History NO se preserva (antes append-only, 2.5x bloat). Price history futura = event
log separado. NO migramos a SQLite todavía (decisión del owner: JSONL mientras se
itera filtros; SQLite con multi-user/deploy — triggers en ARCHITECTURE.md).

### 2. `is_likely_manga()` is a 4-rule cascade, in order

```
0. _NON_MANGA_HARD        → False (figure, DVD, Funko, statue, art print, ...)
1. _STRONG_MANGA_PATTERNS → True  (manga, kanzenban, vol N, "Deluxe Hardcover", ...)
2. _MANGA_WITH_EXTRAS     → True  (edición especial + figura, cofanetto, ...)
                            EXCEPT purity='mixed' → requiere STRONG hint, no pack-extras.
3. _NON_MANGA_SOFT        → False (statue, plush, puzzle, mug, ...)
4. Default                → True si purity='manga_only', False si 'mixed'
```

EL ORDEN IMPORTA: HARD antes que STRONG porque algunos títulos non-manga contienen
"manga"/"vol N" (ej. "Kodansha Reveals New Print Manga Licenses" = noticia). Pattern
nuevo: ¿debe overridear el rescate strong-manga? sí → HARD; sólo si no hay rescate → SOFT.

### 3. Source purity ("manga_only" vs "mixed")

Algunas fuentes tienen catálogo mixto (Dark Horse Direct = manga + statues + prints;
Panini search = trading cards + Hot Wheels; ANN = blog). `purity: "mixed"` en
sources.yml: (a) desactiva el rescate pack-extras; (b) default = False (descartar).
Sólo items con STRONG manga hint pasan. Lista actual de mixed sources en sources.yml
(grep `purity: mixed`). NOTA: la comics blacklist se aplica SIEMPRE, no sólo en mixed.

### 4. Multi-source grouping by `cluster_key` (tier-based)

`derive_cluster_key(item)` se computa por fila y se guarda en el JSONL; lo consume
build_web (`_group_by_cluster_key`) y el JS `dedupByUrl()`. La agregación se
materializa al ingestar (decisión #1) pero la presentación igual agrupa por
cluster_key como red de seguridad y une los `sources[]` guardados.

Cuatro shapes, en orden de prioridad:
1. **`edition:<edition_key>|<volume>`** — mismo edition_key + volume = mismo producto
   físico. **Prioritario sobre ISBN**: si una fuente tiene ISBN (PRH) y otra no (Dark
   Horse), mergean igual. El edition_key ya codifica publisher/market en su slug
   (`gon-norma-collector`). Crucial para boxes/artbooks sin volumen.
2. **`isbn:<X>`** — fallback para items sin edition_key (legacy).
3. **`fuzzy:<lang>|<series>|<vol>|<variant_tier>|<publisher>`** — sin ISBN ni
   edition_key. Los 5 componentes deben ser significativos (series ≥3 chars, lang
   non-empty, volume detectado); si no → standalone.
4. **`url:<url>`** — standalone, nunca agrupa (mejor 1 card por fuente que mergear cosas no relacionadas).

**Variant tier**: distintas fuentes detectan signal_types ligeramente distintos para
el mismo producto, así que el set completo no serviría como discriminante.
`_variant_tier(signal_types)` elige el **primer tier que matchee** (más → menos específico):
`artbook > omnibus > box_set > kanzenban > lore_edition > variant_cover > deluxe >
limited > special > "" (tomo regular)`. Mismo tier → mergean; distinto tier → no
(OP100 Deluxe ≠ OP100 Celebration).

Al compartir cluster_key: el de mayor score es canónico, faltantes se completan
best-of, todos van a `sources[]`. **Si cambiás la derivación, corré
`backfill_cluster_key.py`.** `_extract_volume` soporta vol/tomo/tome/n./#/巻 +
parénesis full-width `（15）`; `_normalize_series_name` strippea keywords/markers pero
preserva kanji/kana/acentos (discriminantes non-Latin).

### 5. Live-fetch mode, not embedded data

`web/index.html` lee `data/items.jsonl` vía `fetch()` por defecto (el `<script
id="manga-data">` está vacío en el repo). **Siempre correr `serve.py`** para ver el
dashboard (`./web/serve.sh` lo hace + abre el browser); abrir `file://` falla por
CORS. Para embeber offline: `build_web.py` (revertir: `--clear`).

### 6. Concurrency via ThreadPoolExecutor, NOT asyncio

El scrape loop usa `ThreadPoolExecutor` con `--workers N` (default 1, recomendado 8).
Rails: **`--per-host-limit N`** (default 2, `threading.Semaphore` por dominio) +
**Playwright worker thread dedicado** (gotcha #12). `DiagnosticRecorder` es
thread-safe (cada `record_*` toma `entry` explícito; `self.entries.append` bajo
`_entries_lock`). No asyncio porque tocaría cientos de call sites; threads dan ~6-8×
en workload I/O-bound con ~250 LOC.

### 7. Pipeline canónico + observabilidad

Los scripts canónicos (`scrape_delta.sh` / `scrape_full.sh`, ver arriba) encadenan
scrape → wikis → cleanup retrofits (rescore → filter_non_manga → filter_collectible →
clean_titles → backfill_metadata → [wayback_recover opt-in]) → consolidate → build_web,
cada fase en su log bajo `logs/`. Skips vía `SKIP_*`, opt-ins vía `INCLUDE_*`.
`audit/source_health.py` clasifica fuentes desde los logs recientes (broken/declining/
healthy/unseen). `retry_failed.sh` re-corre sólo lo que erró en el último log.

**Ordenamiento de tomos dentro de una edición (regla global, gotcha #60):** aplica a
TODAS las fuentes y TODAS las UIs (app HTML + Next.js). Dos reglas duras:
1. **Orden por volumen ascendente** — los tomos de una edición se ordenan de menor a mayor
   número de volumen. Items sin volumen (artbooks standalone, box sets sin número) van al
   final.
2. **Desempate por kind-rank** cuando el mismo volumen tiene >1 item (regular + variant +
   especial del mismo tomo): `regular(0) → variant(1) → special/limited(2) → deluxe/
   kanzenban(3) → artbook(4) → boxset(5) → desconocido(10)`. El kind se extrae por prioridad:
   (a) cluster_key lmc (`lmc:N:kind:vol`) → (b) penúltimo segmento del `edition_key` →
   (c) `signal_types`. Implementado en `web/index.html` (`_kindRank`) y
   `web-next/lib/data.ts` (`kindRank`).
   El `volume` del item DEBE estar populado para que el ordenamiento funcione. Para LMC,
   si `_extract_volume` falla en el título (número antes de calificador de edición),
   el parser lo propaga vía `cand.volume = parsed["volume"]`. Retrofit de corrección:
   `scripts/retrofit/backfill_volume_from_cluster.py`.

**Paridad delta/full para listadomanga** (P1, 2026-06-06): ambos scripts corren el MISMO
parser de colecciones (`listadomanga_collections.py`); difieren solo en el discovery
(`--coleccion-mode`): `full = lista` (~3432 colecciones), `delta = calendar` (ids con
actividad en `calendario.php` en la ventana reciente → ~500-600 colecciones, parseadas
completas). Antes el delta usaba el calendario plano (`--bootstrap-wiki listadomanga`) que
no parseaba ediciones especiales/cofres/variantes; ahora el delta captura la misma riqueza
que el full, acotado a lo reciente. El dedup (synthetic URL + cluster_key, decisión #4)
absorbe el overlap entre corridas.

