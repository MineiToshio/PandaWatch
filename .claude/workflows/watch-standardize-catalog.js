export const meta = {
  name: 'watch-standardize-catalog',
  description: 'Standardize pending manga items using 3-tier approach: deterministic auto-standardize, LLM validation, and full LLM derivation',
  phases: [
    { title: 'Audit', detail: 'Count pending items and compute tier distribution' },
    { title: 'Auto-standardize', detail: 'Apply Tier 1 deterministic standardization (0 tokens)' },
    { title: 'Classify', detail: 'Tier 2 LLM validation of heuristic proposals (haiku)' },
    { title: 'Derive', detail: 'Tier 3 full LLM derivation for unknown series (sonnet)' },
    { title: 'Merge', detail: 'Merge results, dedup, consistency check, generate slugs' },
  ],
}

// --- Schemas for structured output ---

const TIER2_ITEM_SCHEMA = {
  type: 'object',
  properties: {
    url: { type: 'string', description: 'URL of the item (copy from input exactly)' },
    accept_proposal: { type: 'boolean', description: 'True if you kept the proposed values unchanged' },
    // The output fields below are ALWAYS the FINAL value for the item: copy the
    // proposed_* value when accepting, or your corrected value when fixing.
    // They are required so the agent can never leave them implicit — the merge
    // step also falls back to the heuristic proposal if any come back empty.
    series_key: { type: 'string', description: 'FINAL series_key (copy proposed_series_key when accepting, else corrected)' },
    series_display: { type: 'string', description: 'FINAL series_display' },
    edition_key: { type: 'string', description: 'FINAL edition_key (copy proposed_edition_key when accepting, else corrected)' },
    edition_display: { type: 'string', description: 'FINAL edition_display' },
    volume: { type: 'string', description: 'FINAL volume (digits only or empty)' },
    title_standardized: { type: 'string', description: 'FINAL clean title: Series Edition Volume' },
    is_manga: { type: 'boolean', description: 'Whether this is manga (not figure/LN/comic)' },
    non_manga_reason: { type: 'string', description: 'Reason if is_manga=false' },
  },
  required: ['url', 'accept_proposal', 'is_manga', 'series_key', 'edition_key', 'volume', 'title_standardized'],
}

const TIER2_BATCH_SCHEMA = {
  type: 'object',
  properties: {
    items: {
      type: 'array',
      items: TIER2_ITEM_SCHEMA,
      description: 'One entry per input item, same order',
    },
  },
  required: ['items'],
}

const TIER3_ITEM_SCHEMA = {
  type: 'object',
  properties: {
    url: { type: 'string', description: 'URL of the item (copy from input exactly)' },
    is_manga: { type: 'boolean', description: 'Whether this is manga' },
    non_manga_reason: { type: 'string', description: 'Reason if is_manga=false' },
    series_key: { type: 'string', description: 'Lowercase kebab-case canonical series name' },
    series_display: { type: 'string', description: 'Display name for the series' },
    edition_key: { type: 'string', description: 'Format: {series}-{publisher_slug}-{edition_slug}-{country_slug}' },
    edition_display: { type: 'string', description: 'Display name for the edition' },
    volume: { type: 'string', description: 'Volume number as string, or empty' },
    title_standardized: { type: 'string', description: 'Clean title: Series Edition Volume' },
  },
  required: ['url', 'is_manga', 'series_key', 'edition_key', 'volume', 'title_standardized'],
}

const TIER3_BATCH_SCHEMA = {
  type: 'object',
  properties: {
    items: {
      type: 'array',
      items: TIER3_ITEM_SCHEMA,
      description: 'One entry per input item, same order',
    },
  },
  required: ['items'],
}

// Schema para cargar data/standardize-progress.json
const PROGRESS_LOAD_SCHEMA = {
  type: 'object',
  properties: {
    exists:        { type: 'boolean', description: 'true si el archivo existe' },
    tier1_done:    { type: 'boolean', description: 'Tier 1 ya completado en la corrida anterior' },
    has_tier2:     { type: 'boolean', description: 'Resultados Tier 2 guardados' },
    has_tier3:     { type: 'boolean', description: 'Resultados Tier 3 guardados' },
    tier2_results: { type: 'array',   items: { type: 'object' }, description: 'Resultados LLM Tier 2' },
    tier3_results: { type: 'array',   items: { type: 'object' }, description: 'Resultados LLM Tier 3' },
  },
  required: ['exists', 'tier1_done', 'has_tier2', 'has_tier3'],
}

// --- Publisher and edition slug allowlists for prompts ---

const PUBLISHER_SLUGS = `"darkhorse", "glenat", "viz", "panini", "norma", "planeta", "ivrea", "ivrea-ar",
"kana", "pika", "kaze", "kioon", "star", "kodansha", "kodansha-us", "shueisha",
"squareenix", "kadokawa", "meian", "ecc", "arechi", "delcourt", "tokyopop", "jbc",
"devir", "newpop", "kamite", "mangaline", "mangadreams", "funside", "milkyway",
"dokidoki", "nobinobi", "tomodomo", "fandogamia", "kurokawa", "akita", "hakusensha",
"ichijinsha", "futabasha", "takeshobo", "tokuma", "asciimw", "frontier", "yenpress",
"carlsen", "noeve", "distrito", "001edizioni", "goen", "gpmanga", "jpop", "dynit",
"edizionibd", "magicpress", "coconino", "tora", "dokusho", "tokyomangasha", "kbooks",
"luckpim", "ipm", "isan", "nxb", "mpeg", "sevenseas", "titan", "inklore", "vertical",
"udon", "shogakukan", "gentosha", "maggarden", "egmont", "dokico", "papertoons",
"crosscult", "mangacult", "loewe", "reprodukt", "altraverse", "universe",
"pipoca-nanquim", "kim-dong", "panini-mx", "panini-es", "panini-ar", "panini-br",
"crunchyroll", "rakuten"`

const EDITION_SLUGS = `"deluxe", "kanzenban", "perfect", "coffret", "boxset", "cofanetto", "variant",
"limited", "collector", "anniversary", "celebration", "color", "maximum", "ultimate",
"master", "library", "integral", "artbook", "fanbook", "guidebook", "magazine",
"steelbox", "slipcase", "prestige", "grimorio", "grimoire", "special", "regular"`

const COUNTRY_SLUGS = `"jp", "it", "es", "fr", "de", "us", "vn", "mx", "br", "th", "ar", "tw", "gb",
"pt", "pe", "cl", "kr", "eslatam"`

// Reglas compartidas por los prompts Tier 2 y Tier 3 (gotcha #69): tabla
// determinística término→slug + reuso de keys existentes. En sync con
// manga_watch.edition_slug_from_text / canonicalize_edition_slugs.py.
const EDITION_TYPE_RULES = `- HARD TERM TABLE (gotcha #69) — the title term decides the edition-type slug,
  ALWAYS the same way (a deterministic post-pass re-applies this table; never
  contradict it): 限定版 → "limited" · 特装版/同梱版 → "special" · 愛蔵版 → "deluxe" ·
  完全版 → "kanzenban" · "edición limitada"/"edizione limitata"/"édition limitée"/
  "limited edition" → "limited" · "coleccionista"/"collector" → "collector" ·
  "edición de lujo"/"deluxe" → "deluxe". NAMED editions (Maximum, Perfect,
  Ultimate, Master, Grimorio…) win over type terms.
- KEY REUSE (gotcha #69): if the item has \`known_edition_keys\` (keys already in
  the catalog for this series) and one matches this item's publisher+type+country,
  REUSE that exact key. NEVER mint a new key differing from an existing one only
  in the type slug (special/limited/collector/deluxe) — that splits one edition
  into two pages.
- PRESERVE (decisión 2026-06-07): if the item has \`existing_edition_key\`, do NOT
  re-derive the edition — the merge keeps the existing key; you only provide the
  canonical series, the translated VOLUME title, and the is_manga verdict.
- SERIES-NAME GUARD: if the edition-looking word is part of the SERIES' own name
  ("Trigun Maximum", "Ultimate Muscle"), it is NOT an edition type: pick the slug
  from the actual edition evidence (or "regular") and NEVER repeat the word in the
  title ("Trigun Maximum Maximum 2" is wrong → "Trigun Maximum 2").
- regular editions: the title carries NO edition word ("Noragami 27", never
  "Noragami Regular 27").`

// --- Prompt templates ---

function tier2Prompt(itemsJson) {
  return `You are validating manga catalog entries. The scraper already assigned series_key, edition_key, and volume using heuristics. Your job: check if they look correct and fix if not.

## INPUT (JSON array)
${itemsJson}

## RULES
- Each item has proposed_series_key, proposed_edition_key, proposed_volume, proposed_title.
- ALWAYS output the FINAL series_key, series_display, edition_key, edition_display, volume,
  and title_standardized for EVERY item — never leave them empty.
- If the proposal looks correct → set accept_proposal=true AND copy the proposed_* values
  verbatim into the output fields.
- If something is wrong → set accept_proposal=false and put your corrected values in the fields.
- is_manga: Mangavariant items → always true. Figures/statues/LNs/western comics → false.
- edition_key format: {series}-{publisher_slug}-{edition_slug}-{country_slug}. Pick ONE edition_slug, never compound.
- HARD RULE (país=edición, gotcha #46): edition_key ENDS with the country code of the EDITION
  (from the item's publisher/language, NOT the store). Two markets NEVER share an edition_key.
  country_slug allowlist: ${COUNTRY_SLUGS}. Unknown country → "xx".
- Publisher slugs: ${PUBLISHER_SLUGS}
- Edition slugs: ${EDITION_SLUGS}
${EDITION_TYPE_RULES}
- volume: digits only ("1", "18"), "" if none. If item has a volume → never "artbook" as edition_slug.

Process ALL items. Output count MUST equal input count.`
}

function tier3Prompt(itemsJson) {
  return `You are standardizing manga catalog entries from scratch. Derive series_key, edition_key, volume, and title for each item.

## INPUT (JSON array)
${itemsJson}

## RULES

### series_key
Lowercase kebab-case, no diacritics, max ~35 chars. Use globally-recognized name (EN preferred, JP romaji if canonical).
Examples: "berserk", "demon-slayer", "spy-x-family", "attack-on-titan", "one-piece", "fullmetal-alchemist".

### edition_key = {series_key}-{publisher_slug}-{edition_slug}-{country_slug}
- Publisher slugs: ${PUBLISHER_SLUGS}
- Edition slugs (pick ONE, never compound): ${EDITION_SLUGS}
- HARD RULE (país=edición, gotcha #46): edition_key ENDS with the country code of the EDITION
  (from the item's publisher/language, NOT the store). Two markets NEVER share an edition_key
  even if series+publisher+edition match (Panini IT vs Panini ES/MX/BR).
  country_slug allowlist: ${COUNTRY_SLUGS}. Unknown country → "xx".
  Since the country goes in the suffix, prefer "panini" over "panini-es" as publisher_slug
  (country-embedded publisher slugs only for legally distinct companies, e.g. "ivrea-ar").
- ANTI-COMPOUND: Never "deluxe-box", "ultimate-variant". Format vs name conflict → pick the name.
${EDITION_TYPE_RULES}
- If item has volume number → edition_slug is "special" (never "artbook").
- Artbook = standalone illustration book WITHOUT volume numbering.

### is_manga
- Mangavariant → ALWAYS true.
- Slipcases/box sets/coffrets/variant covers/artbooks/fanbooks → valid manga.
- Marvel/DC/IDW comics → false (unless "manga" in title).
- Figures/statues/t-shirts/trading cards → false.
- Light novels → false (non_manga_reason="light_novel").
- When in doubt → true.

### volume
Digits only. "1", "100", "1-3" for sets, "" if absent.

### title_standardized
"{Series Display} {Edition Suffix} {Volume}". Short, clean. No year, no retailer.

Process ALL items. Same series/publisher → same keys consistently. Output count MUST equal input count.`
}

// ====== WORKFLOW BODY ======

// args: { limit?: number, force_all?: boolean }
// limit   — max items to process (0 = unlimited)
// force_all — if true, re-process already-standardized items too (within limit);
//             if false, only process items missing standardized_at
// Default batch cap of 2000: bounds per-run session/token usage so a large
// force-run no longer tries to process everything at once and exhausts the
// account session limit mid-merge. The skill is incremental — remaining items
// are picked up by the next run. Pass args.limit to override (e.g. 0 for no cap).
// DEFENSIVO (visto 2026-06-11): el harness puede entregar `args` como STRING
// JSON en vez de objeto — sin este parse, limit/force_all se ignoraban.
let ARGS = args
if (typeof ARGS === 'string') {
  try { ARGS = JSON.parse(ARGS) } catch { ARGS = {} }
}
const limit = (ARGS && ARGS.limit !== undefined) ? parseInt(ARGS.limit) : 2000
const forceAll = !!(ARGS && ARGS.force_all)
if (limit || forceAll) {
  log(`Mode: ${forceAll ? 'force-all' : 'incremental'}, limit: ${limit || 'none'}`)
}

// --- Progreso persistente ---
// data/standardize-progress.json guarda los resultados LLM de corridas anteriores.
// Si args.resume_progress === true, cargamos ese estado y saltamos las fases ya completadas.
// Al finalizar exitosamente, el archivo se elimina.
const PROGRESS_FILE = 'data/standardize-progress.json'
const resumeProgress = !!(ARGS && ARGS.resume_progress)

let savedTier1Done = false
let savedTier2Results = null   // null = aún no procesado; array = ya procesado (puede estar vacío)
let savedTier3Results = null

if (resumeProgress) {
  const prog = await agent(
    `Check if ${PROGRESS_FILE} exists using Bash (ls command).
If it exists, read it with the Read tool and return its contents parsed as structured output.
If it does not exist, return { "exists": false, "tier1_done": false, "has_tier2": false, "has_tier3": false, "tier2_results": [], "tier3_results": [] }.`,
    { label: 'load-progress', phase: 'Audit', schema: PROGRESS_LOAD_SCHEMA, model: 'haiku' }
  )
  if (prog && prog.exists) {
    savedTier1Done    = !!prog.tier1_done
    savedTier2Results = prog.has_tier2 ? (prog.tier2_results || []) : null
    savedTier3Results = prog.has_tier3 ? (prog.tier3_results || []) : null
    log(`Progreso cargado — T1:${savedTier1Done ? '✅' : '⏳'}  T2:${prog.has_tier2 ? `✅ (${(savedTier2Results||[]).length} items)` : '⏳'}  T3:${prog.has_tier3 ? `✅ (${(savedTier3Results||[]).length} items)` : '⏳'}`)
  } else {
    log('No se encontró archivo de progreso — empezando de cero')
  }
}

phase('Audit')

// Step 1: Read pending items and compute tier distribution.
// La lógica vive en scripts/standardize_audit.py (fuente única, compartida con
// el SKILL.md) — escribe tier{1,2,3}.json con proposed_*, existing_edition_key
// y known_edition_keys (keys ya existentes en el corpus para cada serie).
const auditResult = await agent(
  `Run this command and report its output verbatim:

\`\`\`bash
.venv/bin/python scripts/standardize_audit.py${forceAll ? ' --force-all' : ''}${limit ? ` --limit ${limit}` : ''}
\`\`\`

Report the TOTAL/PENDING/TIER1/TIER2/TIER3 numbers. If PENDING is 0, say "nothing to standardize".`,
  // Agente mecánico (corre un comando y reporta) → haiku alcanza y ahorra tokens.
  { label: 'audit', phase: 'Audit', model: 'haiku' }
)

log(`Audit complete: ${auditResult}`)

// Parse audit results — tolerate spaces around colon (agent may reformat)
function parseMarker(text, key) {
  const re = new RegExp(key + '\\s*[:=]\\s*(\\d+)', 'i')
  const m = text.match(re)
  return m ? parseInt(m[1]) : 0
}

const pendingCount = parseMarker(auditResult, 'PENDING')

if (pendingCount === 0) {
  log('Nothing to standardize — corpus is up to date.')
  return { status: 'nothing_to_standardize', items_processed: 0 }
}

const tier1Count = parseMarker(auditResult, 'TIER1')
const tier2Count = parseMarker(auditResult, 'TIER2')
const tier3Count = parseMarker(auditResult, 'TIER3')

log(`Tier 1 (auto): ${tier1Count}, Tier 2 (validate): ${tier2Count}, Tier 3 (derive): ${tier3Count}`)

// Step 2: Auto-standardize Tier 1 deterministically
phase('Auto-standardize')

if (savedTier1Done) {
  log('Tier 1: saltando — ya completado en la corrida anterior')
} else if (tier1Count > 0) {
  await agent(
    `Auto-standardize Tier 1 items (la lógica vive en scripts/standardize_apply.py,
fuente única compartida con el SKILL.md). Run this command and report the count:

\`\`\`bash
.venv/bin/python scripts/standardize_apply.py tier1${forceAll ? ' --force-all' : ''}
\`\`\``,
    { label: 'auto-t1', phase: 'Auto-standardize', model: 'haiku' }
  )
  log(`Tier 1 auto-standardized: ${tier1Count} items`)
  // Checkpoint: Tier 1 completo, T2/T3 aún pendientes
  await agent(
    `Write this JSON to ${PROGRESS_FILE} (create or overwrite):
${JSON.stringify({ limit: limit||0, force_all: forceAll, tier1_done: true, has_tier2: false, has_tier3: false, tier2_results: null, tier3_results: null }, null, 2)}`,
    { label: 'checkpoint-t1', phase: 'Auto-standardize', model: 'haiku' }
  )
} else {
  log('No Tier 1 items to auto-standardize.')
}

// Step 3: Process Tier 2 with haiku (lightweight validation)
phase('Classify')

const tier2Results = savedTier2Results ? [...savedTier2Results] : []
if (savedTier2Results !== null) {
  log(`Tier 2: saltando — ${savedTier2Results.length} resultados cargados del progreso guardado`)
} else if (tier2Count > 0) {
  const t2ChunkSize = 20
  const t2Agent = await agent(
    `Read /tmp/manga-standardize-run/tier2.json. Split into chunks of ${t2ChunkSize} items.
Write each chunk to /tmp/manga-standardize-run/t2_chunk_NN.json (00, 01, 02, ...).
Report how many chunks you created.`,
    { label: 'chunk-t2', phase: 'Classify', model: 'haiku' }
  )

  // Count chunks
  const chunkCountMatch = t2Agent.match(/(\d+)\s*chunk/)
  const t2ChunkCount = chunkCountMatch ? parseInt(chunkCountMatch[1]) : 1

  if (t2ChunkCount > 0) {
    const t2Thunks = []
    for (let i = 0; i < t2ChunkCount; i++) {
      const idx = String(i).padStart(2, '0')
      t2Thunks.push(() =>
        agent(
          `Read /tmp/manga-standardize-run/t2_chunk_${idx}.json.
These are Tier 2 items — the scraper already proposed series_key/edition_key/volume.
Validate each proposal. ${tier2Prompt('(see the file contents)')}

Read the file, then:
1. Use the Write tool to write your results to /tmp/manga-standardize-run/result_t2_${idx}.jsonl — ONE compact JSON object per line (JSONL), one line per input item, SAME ORDER. Each line must have exactly these fields: url, is_manga, non_manga_reason, series_key, series_display, edition_key, edition_display, volume, title_standardized.
2. Then return structured output with the same results for ALL items in the file.`,
          {
            label: `validate-t2-${idx}`,
            phase: 'Classify',
            schema: TIER2_BATCH_SCHEMA,
            // Tier 2 = validación liviana de propuestas ya derivadas (la meta
            // siempre dijo haiku; el código usaba sonnet y gastaba de más).
            model: 'haiku',
          }
        )
      )
    }
    const t2BatchResults = await parallel(t2Thunks)
    for (const r of t2BatchResults) {
      if (r && r.items) tier2Results.push(...r.items)
    }
    log(`Tier 2 validated: ${tier2Results.length} items via haiku`)
  }
  // Checkpoint: T1+T2 completos, T3 aún pendiente
  await agent(
    `Write this JSON to ${PROGRESS_FILE} (create or overwrite):
${JSON.stringify({ limit: limit||0, force_all: forceAll, tier1_done: true, has_tier2: true, has_tier3: false, tier2_results: tier2Results, tier3_results: null }, null, 2)}`,
    { label: 'checkpoint-t2', phase: 'Classify', model: 'haiku' }
  )
} else {
  log('No Tier 2 items.')
}

// Step 4: Process Tier 3 with sonnet (full derivation)
phase('Derive')

const tier3Results = savedTier3Results ? [...savedTier3Results] : []
if (savedTier3Results !== null) {
  log(`Tier 3: saltando — ${savedTier3Results.length} resultados cargados del progreso guardado`)
} else if (tier3Count > 0) {
  const t3ChunkSize = 15  // smaller for complex items

  const t3Agent = await agent(
    `Read /tmp/manga-standardize-run/tier3.json. Split into chunks of ${t3ChunkSize} items.
Write each chunk to /tmp/manga-standardize-run/t3_chunk_NN.json (00, 01, 02, ...).
Report how many chunks you created.`,
    { label: 'chunk-t3', phase: 'Derive', model: 'haiku' }
  )

  const t3ChunkCountMatch = t3Agent.match(/(\d+)\s*chunk/)
  const t3ChunkCount = t3ChunkCountMatch ? parseInt(t3ChunkCountMatch[1]) : 1

  if (t3ChunkCount > 0) {
    const t3Thunks = []
    for (let i = 0; i < t3ChunkCount; i++) {
      const idx = String(i).padStart(2, '0')
      t3Thunks.push(() =>
        agent(
          `Read /tmp/manga-standardize-run/t3_chunk_${idx}.json.
These are Tier 3 items — derive everything from scratch.
${tier3Prompt('(see the file contents)')}

Read the file, then:
1. Use the Write tool to write your results to /tmp/manga-standardize-run/result_t3_${idx}.jsonl — ONE compact JSON object per line (JSONL), one line per input item, SAME ORDER. Each line must have exactly these fields: url, is_manga, non_manga_reason, series_key, series_display, edition_key, edition_display, volume, title_standardized.
2. Then return structured output for ALL items.`,
          {
            label: `derive-t3-${idx}`,
            phase: 'Derive',
            schema: TIER3_BATCH_SCHEMA,
            model: 'sonnet',
          }
        )
      )
    }
    const t3BatchResults = await parallel(t3Thunks)
    for (const r of t3BatchResults) {
      if (r && r.items) tier3Results.push(...r.items)
    }
    log(`Tier 3 derived: ${tier3Results.length} items via sonnet`)
  }
  // Checkpoint: T1+T2+T3 completos — solo queda el merge
  await agent(
    `Write this JSON to ${PROGRESS_FILE} (create or overwrite):
${JSON.stringify({ limit: limit||0, force_all: forceAll, tier1_done: true, has_tier2: true, has_tier3: true, tier2_results: tier2Results, tier3_results: tier3Results }, null, 2)}`,
    { label: 'checkpoint-t3', phase: 'Derive', model: 'haiku' }
  )
} else {
  log('No Tier 3 items.')
}

// Step 5: Merge everything back
phase('Merge')

// Write LLM results to files for the merge script
const allLlmResults = []

// Process Tier 2 results. The agent always emits the FINAL values in the
// output fields (schema-required). We pass them straight through; the merge
// script falls back to the heuristic proposal (tier2.json) for any item that
// still comes back with empty keys, and leaves un-keyable items PENDING rather
// than marking them standardized with empty keys (the orphan bug).
for (const r of tier2Results) {
  allLlmResults.push({
    url: r.url,
    is_manga: r.is_manga,
    non_manga_reason: r.non_manga_reason || '',
    series_key: r.series_key || '',
    series_display: r.series_display || '',
    edition_key: r.edition_key || '',
    edition_display: r.edition_display || '',
    volume: r.volume || '',
    title_standardized: r.title_standardized || '',
  })
}

// Process Tier 3 results
for (const r of tier3Results) {
  allLlmResults.push({
    url: r.url,
    is_manga: r.is_manga,
    non_manga_reason: r.non_manga_reason || '',
    series_key: r.series_key || '',
    series_display: r.series_display || '',
    edition_key: r.edition_key || '',
    edition_display: r.edition_display || '',
    volume: r.volume || '',
    title_standardized: r.title_standardized || '',
  })
}

log(`Total LLM results to merge: ${allLlmResults.length}`)

// Write results for the merge script
const mergeAgent = await agent(
  `Merge standardization results into items.jsonl.

The per-chunk LLM result files already exist on disk at
/tmp/manga-standardize-run/result_t2_*.jsonl and result_t3_*.jsonl (each subagent
wrote its own JSONL). DO NOT transcribe any data yourself — the merge logic lives
in scripts/standardize_apply.py (single source of truth, shared with the SKILL.md):
it reads those files via glob, preserves existing edition_keys (the LLM is not the
grouping authority), falls back to heuristic proposals for empty keys (items with
no usable keys stay PENDING, never orphans), blacklists non-manga, fixes series
outliers per /coleccion, recomputes cluster_key and consolidates:

\`\`\`bash
.venv/bin/python scripts/standardize_apply.py merge${forceAll ? ' --force-all' : ''}
\`\`\`

Then ENFORCE the grouping rules (Step 6b of the skill — MANDATORY, the LLM is NOT the
authority on grouping; this deterministically re-applies país=edición, coleccion=edición,
official edition_display, edition-type slugs from title terms (#69), duplicate-series
merge (#70), publisher unification, cluster_key re-derivation, consolidate, dedup and slugs):
\`\`\`bash
.venv/bin/python scripts/retrofit/enforce_listadomanga_rules.py
\`\`\`

Then run slugs and translation:
\`\`\`bash
.venv/bin/python scripts/retrofit/generate_slugs.py --only-missing --verbose
.venv/bin/python scripts/retrofit/translate_descriptions.py --workers 4
\`\`\`

Then run tests and the corpus validator (ALL invariants at once — single-dimension
checks give false "0 issues"):
\`\`\`bash
.venv/bin/python -m pytest tests/test_extraction.py -q
.venv/bin/python scripts/validate_corpus.py
\`\`\`

Report all results, including the validator output.`,
  // Mecánico: corre comandos y reporta — la lógica vive en los scripts.
  { label: 'merge-and-finalize', phase: 'Merge', model: 'haiku' }
)

log(`Merge complete: ${mergeAgent}`)

// Cleanup: borrar temporales Y el archivo de progreso (corrida exitosa)
await agent(
  `Run: rm -rf /tmp/manga-standardize-run && rm -f ${PROGRESS_FILE} && echo "Cleanup OK"`,
  { label: 'cleanup', phase: 'Merge', model: 'haiku' }
)

return {
  status: 'completed',
  tier1_auto: tier1Count,
  tier2_validated: tier2Results.length,
  tier3_derived: tier3Results.length,
  total_processed: tier1Count + tier2Results.length + tier3Results.length,
}
