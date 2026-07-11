---
name: watch-enrich-series-aliases
description: Process queue of unmapped manga series (data/unmapped_series.jsonl), group them under existing canonicals or create new entries in data/series_aliases.yml via Anilist API and web search. Trigger manually whenever new items appear without a known series canonical (e.g., after each scrape). Updates the YAML, runs the backfill on items.jsonl, and reports what was done.
argument-hint: "[--max-suggestions N] [--min-count N]"
---

# Enrich series aliases

> **Model tier (F10):** the per-candidate decision (Steps 1–3 — Anilist lookup +
> A/B/C classification) is bounded reasoning, not heavy synthesis. **Run this skill
> in `sonnet`** (or fix `model: 'sonnet'` on the decision phase if this is ever
> compiled to a workflow). Steps 1, 4, 5 are mechanical (scripts). Never opus.

You are processing the queue of manga series that the scraper discovered but couldn't map to a canonical entry in `data/series_aliases.yml`. Your job: review each candidate, decide whether it's an alias of an existing canonical or a new series, update the YAML, and apply the backfill so `items.jsonl` reflects the new mappings.

**Keep a list of every `series_key` you touch in Steps 2–3** (each candidate's
current, non-canonical `series_key`). You pass that exact list to the backfill in
Step 4 via `--only-keys` — the backfill is deliberately scoped to just those keys.

## Step 1 — Audit the queue

Run the audit script first. It reads `data/items.jsonl` + `data/unmapped_series.jsonl`, aggregates by `series_key`, and proposes fuzzy matches against existing canonicals.

```bash
.venv/bin/python scripts/audit/unmapped_series.py --min-count 1 --max-suggestions 50
```

**Cómo acotar el lote** (el argument-hint expone estos dos flags): `--max-suggestions N`
limita a las top-N candidatas por `item_count` (procesá las de más impacto primero);
`--min-count N` ignora las series con menos de N items (útil para saltar la cola larga
de one-shots/ruido de 1 item). Ej.: `--min-count 3 --max-suggestions 20` para una pasada
corta de alto impacto.

The output is markdown with one section per candidate, ordered by `item_count` DESC. For each candidate you see:

- `series_key` (current, non-canonical) and `primary_display`
- Best fuzzy guess of an existing canonical (🟢 confidence ≥ 0.8 / 🟡 0.6–0.8 / 🔴 < 0.6)
- Languages, publishers, sample titles, sample URL

If the file is empty / no candidates: report "no unmapped series" and stop.

## Step 2 — Classify each candidate

For each entry in the audit output, choose ONE of three actions:

### Action A: merge into existing canonical (alias)

When the candidate is clearly a translation, romanization, or spelling variant of a series already in `series_aliases.yml`:

- "🟢 best guess = `witch-hat-atelier` (confidence 0.85)" + candidate is `atelier-des-sorciers` → it's the French title.
- "🟢 best guess = `apothecary-diaries` (confidence 0.92)" + candidate is `apothicaire` → FR title.

Add the candidate's `series_key` and `primary_display` (and any extra synonyms you know) to the `aliases` list of the existing canonical entry in the YAML.

> **⚠️ Regla dura — merges de confianza media (🟡 ~0.6–0.8):** un falso merge es
> IRREVERSIBLE tras la siguiente corrida (backfill → `merge_cluster()` funde filas
> y descarta campos de las perdedoras; el backup de items.jsonl rota). Por eso un
> 🟡 **NO se mergea con el fuzzy score solo** — es un hint, no un veredicto. Antes de
> mergear un 🟡 exigí **evidencia estructural explícita** de que es la MISMA obra:
> coincidencia de **idioma + publisher + una muestra de títulos** que encaje (los
> tomos de la candidata y de la canónica pertenecen a la misma serie), **o** una
> búsqueda web que confirme que candidata y canónica son la misma obra (títulos
> internacionales/locales cruzados). **Si no reunís esa evidencia, NO mergees:** el
> default es crear una canónica nueva (Action B) o skip (Action C) — NUNCA merge a
> ciegas. Un 🟢 (≥0.8) con sample titles que confirman sigue el flujo normal.

### Action B: create a new canonical entry

When the candidate is a real new series not yet in the YAML (e.g., a recent release, a niche manga, a spin-off). Steps:

1. Query Anilist GraphQL to get the canonical international name + multilingual synonyms:

   ```bash
   curl -s -X POST https://graphql.anilist.co \
     -H "Content-Type: application/json" \
     -H "User-Agent: PandaWatch/1.0 (sminei10@gmail.com)" \
     -d '{"query":"query($s:String){Media(search:$s,type:MANGA){id title{romaji english native} synonyms}}","variables":{"s":"<SERIES_DISPLAY>"}}'
   ```

2. If Anilist returns a match:
   - Choose canonical key = slug of `title.english` (preferred) or `title.romaji`. Avoid subtitles ("Frieren: Beyond Journey's End" → just "frieren").
   - The canonical key MUST be pure ASCII kebab-case (`[a-z0-9-]` only) — never raw CJK
     and never Cyrillic/Greek homoglyphs copied from a source ("taihо-to-stamp" with
     Cyrillic о, "maku-ga-oriru-to-bokura-wa-番" — real bugs, gotcha #81). Transliterate
     to romaji instead. The pipeline now sanitizes keys with `sanitize_key_ascii()`, so a
     non-ASCII key will silently diverge from what items actually get — don't coin one.
   - Display = `title.english` cleaned, or romaji if no english.
   - Aliases = romaji, native, and synonyms — **filter out** synonyms in non-target alphabets (cyrillic, arabic, hebrew, hangul, thai) and single-word generic aliases that could collide ("Monster", "Real", "Blue Period" when those refer to other series).

3. If Anilist returns nothing (rare — doujinshi, very recent, or obscure):
   - Try a quick web search for the title to find its English/international name.
   - If still nothing: use the JP romaji (transliterate the title if needed) as canonical. Display = romaji form.

4. For Spanish (especially Latin American), French (Glénat/Pika), Italian (Star Comics/Panini) translations — check the publishers in the candidate's metadata and add the local title as an alias if it differs from canonical. The audit output lists languages and publishers you can use as hints.

### Action C: skip (low confidence, low priority, or wrong data)

Reasons to skip:
- `item_count` == 1 AND title looks like garbage (truncated, weird encoding).
- The candidate is actually a one-shot or doujinshi that won't get more items.
- The data is ambiguous and you'd rather wait for more items to accumulate before deciding.

For skips: just leave the entry unmapped. The audit will surface it again next time you run the skill.

## Step 3 — Update the YAML

**Antes de la PRIMERA edición**, dos preparativos obligatorios:

1. **Respaldá el YAML** (es de 344 KB y lo vas a editar a ciegas; un backup
   timestamped es el punto de restauración si algo sale mal):

```bash
.venv/bin/python -c "from scripts.manga_watch import backup_and_rotate; from pathlib import Path; print(backup_and_rotate(Path('data/series_aliases.yml'), 'enrich', timestamped=True))"
```

2. **Capturá el baseline de colisiones PRE-EXISTENTES** (el YAML real ya tiene
   colisiones históricas que esta corrida NO introdujo; el gate del Step 3.5 sólo
   debe abortar por colisiones NUEVAS — las tuyas):

```bash
.venv/bin/python scripts/audit/lint_series_aliases.py \
  --snapshot data/diagnostics/aliases_collisions_baseline.json
```

Si este comando sale con exit ≠ 0 el YAML ya tiene una **clave duplicada** de
entrada (corrupción real, no deuda histórica): frená y reportala al owner antes
de editar nada.

For each Action A or B, edit `data/series_aliases.yml` directly. Add entries in the same shape as existing ones:

```yaml
witch-hat-atelier:
  display: Witch Hat Atelier
  aliases:
    - Atelier of Witch Hat
    - L'Atelier des Sorciers
    - Tongari Boushi no Atelier
    - とんがり帽子のアトリエ
    # ← add new alias here
    - atelier-of-witch-hat
```

**Rules for editing the YAML:**
- Keep entries alphabetized by canonical key (the file is sorted that way).
- Within `aliases`, sorted alphabetically too (helps diff readability).
- One entry per line in the aliases array (YAML list).
- Preserve diacritics in display names ("Frieren", "L'Apothicaire") — the resolver normalizes them at match time.
- For JP-only manga that has no English title, use romaji as display (e.g., "Yawara!").
- Never add an alias that's a single short generic word ("Monster", "Real") — those collide with other series.
- If you're merging two existing canonicals into one (e.g., `detective-conan` + `case-closed`), pick the more globally-recognized one as canonical, move all aliases of the loser into the winner, then DELETE the loser entry from the YAML.

## Step 3.5 — Lint the YAML (gate — corré DESPUÉS de CADA edición)

Inmediatamente después de guardar cada tanda de ediciones al YAML, validá su
integridad **antes** de tocar `items.jsonl`, comparando contra el baseline que
capturaste en Step 3:

```bash
.venv/bin/python scripts/audit/lint_series_aliases.py \
  --baseline data/diagnostics/aliases_collisions_baseline.json
```

El lint atrapa dos fallos SILENCIOSOS que `yaml.safe_load` no reporta:

- **Clave canónica DUPLICADA** (siempre fatal): si re-agregaste una key que ya
  existía en el YAML, `safe_load` se quedaría con la ÚLTIMA y perdería la entrada
  original **y sus aliases** sin avisar — y el backfill escribiría `items.jsonl`
  con un mapeo mutilado. El lint LEVANTA error en vez de tragárselo.
- **Colisión de normalización NUEVA** entre dos canonicals distintas (gotcha #70,
  fatal sólo si NO está en el baseline): una quedaría sombreada para el resolver.
  Las colisiones **pre-existentes** (ya en el baseline) salen como warning ⚠ y NO
  bloquean — no las introdujiste vos; se le informan al owner en el reporte final.

**Si el lint sale con exit ≠ 0, ABORTÁ:** corregí el YAML (borrá el duplicado
conservando los aliases de ambas; renombrá/fusioná la canonical que colisiona con
una existente) y volvé a correr el lint hasta que quede en verde. **No pases a
Step 4 con el lint en rojo.**

## Step 4 — Apply the backfill

After saving the YAML, run the backfill retrofit **scoped to the exact `series_key`s
you processed** in Steps 2–3 (comma-separated, no spaces):

```bash
# Dry-run first to preview what changes (no write):
.venv/bin/python scripts/retrofit/backfill_series_aliases.py \
  --dry-run --only-keys key1,key2,key3

# Then apply:
.venv/bin/python scripts/retrofit/backfill_series_aliases.py \
  --only-keys key1,key2,key3
```

The script (FUENTE ÚNICA — no embedded logic here anymore):
- Remaps `series_key`/`series_display` of the in-scope items via
  `series_aliases.canonical_series_key` (the single alias resolver), re-aligns the
  `edition_key` prefix, and re-derives `cluster_key` with
  `manga_watch.derive_cluster_key`.
- **Delegates consolidation** to `manga_watch.consolidate_by_cluster` (the single
  merge primitive that ingest uses) — it never re-implements dedup.
- **Backs up `data/items.jsonl`** via `backup_and_rotate(..., timestamped=True)` antes
  de escribir (este es el archivo realmente en riesgo — ver Step 5). El backup es
  **timestamped** (un archivo por corrida, no un slot fijo): un falso merge es
  irreversible si el snapshot anterior se pisara, así que se conserva entre corridas.
- Skips `approved_at` golden records (guard homogéneo). Idempotent.

**⚠️ `--only-keys` is REQUIRED.** Do NOT run this over the whole corpus. Passing every
key you touched is the whole point: a new alias applied blanket-style can collapse
unrelated series across the entire base (regla dura, auditoría post-scrape
2026-07-07: *"backfill de aliases NUNCA sobre todo el corpus"*). The script aborts
without `--only-keys`; `--all --yes-i-know-collateral` exists only for the rare
deliberate full pass.

## Step 5 — Truncate the unmapped queue

**SOLO si el backfill de Step 4 devolvió exit 0.** Si el backfill abortó o falló
(exit ≠ 0), NO trunques la cola — arreglá lo que falló y re-corré Step 4 primero.
Truncar con el backfill en rojo perdería la cola sin haber aplicado los mapeos.

Una vez que el backfill aplicó limpio, limpiá la cola para que la próxima corrida
arranque fresca:

```bash
# Solo procede si el backfill anterior salió con exit 0:
if [ $? -eq 0 ]; then
  # Backup + truncate (usa backup_and_rotate para respetar la rotación max-3)
  .venv/bin/python -c "from scripts.manga_watch import backup_and_rotate; from pathlib import Path; backup_and_rotate(Path('data/unmapped_series.jsonl'), 'enrich')"
  : > data/unmapped_series.jsonl
fi
```

(Si corriste otros comandos entre el backfill y este paso, verificá el exit code
del **backfill** explícitamente en vez de confiar en `$?`.)

(The pipeline will repopulate it on the next scrape if any series remains unmapped.)

> **Note on backups:** the queue (`unmapped_series.jsonl`) is cheap and regenerable —
> the next scrape rebuilds it. The file actually at risk is `data/items.jsonl`, which
> Step 4's retrofit already backs up (`backup_and_rotate` label `series-aliases`,
> **timestamped** — un archivo por corrida, se conserva entre corridas) before its
> destructive rewrite. So the critical restore point lives with items.jsonl, not the
> queue; this queue backup is just a convenience.

## Step 6 — Verificación final (gates) + export + report

Corré **todos** estos gates; **cualquiera en rojo aborta el cierre** (arreglá y
re-corré antes de reportar "listo"):

**1. Lint del YAML contra el baseline** (sin claves duplicadas ni colisiones
NUEVAS; las pre-existentes del baseline salen como warning ⚠ y no bloquean —
anotalas para el reporte final):

```bash
.venv/bin/python scripts/audit/lint_series_aliases.py \
  --baseline data/diagnostics/aliases_collisions_baseline.json
```

**2. Doble-check estructurado** — el mismo gate en JSON, verificando que
`errors == []` (los `warnings`/`canonical_duplicates` pre-existentes son
informativos, no fatales):

```bash
.venv/bin/python scripts/audit/lint_series_aliases.py \
  --baseline data/diagnostics/aliases_collisions_baseline.json --json \
  | .venv/bin/python -c "import json,sys; d=json.load(sys.stdin); print('errors:', d['errors']); print('warnings pre-existentes:', len(d['warnings'])); sys.exit(1 if d['errors'] else 0)"
```

**3. Invariantes del corpus** (todas a la vez):

```bash
.venv/bin/python scripts/validate_corpus.py
```

**4. Prueba de idempotencia/convergencia** — re-corré el backfill con **los MISMOS
`--only-keys`** que usaste en Step 4; debe converger (no volver a cambiar nada):

```bash
.venv/bin/python scripts/retrofit/backfill_series_aliases.py --only-keys key1,key2,key3 \
  | grep '\[SUMMARY\]'
# Debe imprimir  →  [SUMMARY] items cambiados: 0
```

Si la segunda corrida reporta `items cambiados: 0`, el mapeo convergió. Si reporta
un número > 0, el backfill NO es idempotente para esas keys — investigá antes de
cerrar (posible alias que sigue moviendo filas).

**5. Tests**:

```bash
.venv/bin/python -m pytest tests/test_extraction.py tests/test_lint_series_aliases.py tests/test_backfill_series_aliases.py -q
```

**6. Refrescar el índice de búsqueda en vivo** — web-next lee `series_aliases.json`
(derivado del YAML) por mtime; regeneralo para que el dropdown de búsqueda por obra
refleje los aliases nuevos sin un build completo:

```bash
.venv/bin/python scripts/export_series_aliases.py
```

Then write a brief report to the user:
- Total candidates processed.
- New canonicals added (with display name).
- Aliases merged into existing canonicals.
- Items remapped via backfill.
- Anything you skipped + why.
- **Colisiones PRE-EXISTENTES del baseline** (los warnings ⚠ del lint): listalas
  para que el owner decida si son duplicados reales a fusionar o falsos positivos
  legítimos (p.ej. un artbook vs el juego del mismo nombre). NO las resuelvas vos
  en esta corrida.

## Anti-patterns to avoid

- **Don't add single-letter or 2-3 char aliases.** They cause substring collisions (the resolver is exact-match, but humans editing the YAML may make mistakes later).
- **Don't add an alias whose normalization equals an existing canonical key for a different series.** Check the YAML before adding.
- **Don't bulk-merge without inspecting the data.** A confidence of 0.7 is a hint, not a verdict — check the sample titles to confirm.
- **Don't include the original Anilist `synonyms` blindly.** They contain transliterations to alphabets we don't target (cyrillic, hebrew, arabic, korean, thai) plus single-word generic aliases (BNHA, MHA, AoT, SnK) that pollute the namespace. Drop them.
- **Don't delete the unmapped_series.jsonl mid-run.** Truncate at the END, after the backfill applied cleanly.

## When to invoke this skill

- After each `manga_watch.py` scrape if new series were discovered.
- Once a week as a regular curation pass.
- Before generating a fresh build of the dashboard (so the filter-by-obra dropdown is consistent).
- When user reports "I see this series twice with different names in the dashboard".
