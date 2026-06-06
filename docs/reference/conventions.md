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

### Escritura de datos — reglas duras

- **JSONL**: NUNCA `open(path,'a')`. Usá `append_jsonl(path, rows)` (upsert + atomic rename).
- **Backups**: todo script que modifique un archivo de datos usa `backup_and_rotate(path,
  label)` importada de `manga_watch.py`, UNA vez ANTES del loop. Escribe en
  `data/backups/<filename>/` (rota, máx 3). NUNCA `cp ... /tmp/`, NUNCA path propio (un
  path mal calculado crea `backups/` en la raíz, sin rotación, en git status).
- **Flush incremental**: todo loop de red/subprocess (HTTP por ítem, Tavily, waifu2x,
  Wayback) escribe items.jsonl incremental (por mejora o cada N; `--flush-every` donde
  exista, default 50, bajar a 5-10 para llamadas lentas). Un write único al final pierde
  todo si el proceso muere. El backup va antes del loop; el flush es `_write_items` directo
  (sin backup). Scripts compute-only (rescore, clean_titles, filter_*, backfill_cluster_key,
  generate_slugs) terminan en segundos → write único OK.
- **nohup**: todo script >~2 min se lanza con `nohup .venv/bin/python -u scripts/... >
  logs/<x>.log 2>&1 &` + `echo $!` (sobrevive cierres de terminal y compactaciones de
  contexto de Claude). NO `tee` (buffering). Claude programa un `ScheduleWakeup` (~20 min)
  para revisar el log, ya que nohup desacopla el proceso.

### Flagear un registro incierto

SIEMPRE a `data/unmapped_series.jsonl` (única fuente). NUNCA archivos paralelos
(uncertain_X/review_X). Contexto extra vía campos opcionales del schema (`flagged_by`,
`reason`, `notes`, `proposed_canonical_*`). Para flags automáticos desde el pipeline usá
`log_unmapped_series()` en `series_aliases.py`. Schema completo en el File map.

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

