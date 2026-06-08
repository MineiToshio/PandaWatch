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
    edition_key: { type: 'string', description: 'Format: {series}-{publisher_slug}-{edition_slug}' },
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
- edition_key format: {series}-{publisher_slug}-{edition_slug}. Pick ONE edition_slug, never compound.
- Publisher slugs: ${PUBLISHER_SLUGS}
- Edition slugs: ${EDITION_SLUGS}
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

### edition_key = {series_key}-{publisher_slug}-{edition_slug}
- Publisher slugs: ${PUBLISHER_SLUGS}
- Edition slugs (pick ONE, never compound): ${EDITION_SLUGS}
- ANTI-COMPOUND: Never "deluxe-box", "ultimate-variant". Format vs name conflict → pick the name.
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
const limit = (args && args.limit) ? parseInt(args.limit) : 0
const forceAll = !!(args && args.force_all)
if (limit || forceAll) {
  log(`Mode: ${forceAll ? 'force-all' : 'incremental'}, limit: ${limit || 'none'}`)
}

// --- Progreso persistente ---
// data/standardize-progress.json guarda los resultados LLM de corridas anteriores.
// Si args.resume_progress === true, cargamos ese estado y saltamos las fases ya completadas.
// Al finalizar exitosamente, el archivo se elimina.
const PROGRESS_FILE = 'data/standardize-progress.json'
const resumeProgress = !!(args && args.resume_progress)

let savedTier1Done = false
let savedTier2Results = null   // null = aún no procesado; array = ya procesado (puede estar vacío)
let savedTier3Results = null

if (resumeProgress) {
  const prog = await agent(
    `Check if ${PROGRESS_FILE} exists using Bash (ls command).
If it exists, read it with the Read tool and return its contents parsed as structured output.
If it does not exist, return { "exists": false, "tier1_done": false, "has_tier2": false, "has_tier3": false, "tier2_results": [], "tier3_results": [] }.`,
    { label: 'load-progress', phase: 'Audit', schema: PROGRESS_LOAD_SCHEMA }
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

// Step 1: Read pending items and compute tier distribution
const auditResult = await agent(
  `Read data/items.jsonl and compute the standardization tier distribution.
Run this Python script and report the output:

\`\`\`bash
.venv/bin/python << 'PY'
import json, sys, pickle
sys.path.insert(0, 'scripts')
from manga_watch import derive_series_metadata, Candidate
from pathlib import Path

FORCE_ALL = ${forceAll ? 'True' : 'False'}
LIMIT = ${limit}

items = [json.loads(l) for l in open('data/items.jsonl')]
if FORCE_ALL:
    pending = [it for it in items if not it.get('approved_at')]
else:
    pending = [it for it in items if not it.get('standardized_at') and not it.get('approved_at')]
if LIMIT:
    pending = pending[:LIMIT]
print(f'TOTAL:{len(items)}')
print(f'PENDING:{len(pending)}')

if not pending:
    print('DONE:nothing_to_standardize')
    exit()

tiers = {1: [], 2: [], 3: []}
for it in pending:
    c = Candidate(
        title=it.get('title_original') or it.get('title',''),
        url=it.get('url',''), source=it.get('source',''),
        source_url=it.get('source_url',''), country=it.get('country',''),
        language=it.get('language',''), publisher=it.get('publisher',''),
        source_class=it.get('source_class',''), tags=it.get('tags',[]),
        description=it.get('description',''),
        signal_types=it.get('signal_types',[]),
    )
    md = derive_series_metadata(c)
    tier = md.get('confidence_tier', 3) if md else 3
    projected = {
        'url': it.get('url',''), 'title': it.get('title',''),
        'title_original': it.get('title_original',''),
        'source': it.get('source',''), 'publisher': it.get('publisher',''),
        'country': it.get('country',''), 'language': it.get('language',''),
        'isbn': it.get('isbn',''), 'signal_types': it.get('signal_types', []),
        'description_excerpt': (it.get('description','') or '')[:200],
    }
    if md:
        projected['proposed_series_key'] = md.get('series_key','')
        projected['proposed_series_display'] = md.get('series_display','')
        projected['proposed_edition_key'] = md.get('edition_key','')
        projected['proposed_edition_display'] = md.get('edition_display','')
        projected['proposed_volume'] = md.get('volume','')
        projected['proposed_title'] = md.get('title_standardized','')
    tiers[tier].append(projected)

base = Path('/tmp/manga-standardize-run')
base.mkdir(parents=True, exist_ok=True)
for t in [1, 2, 3]:
    with open(base / f'tier{t}.json', 'w') as f:
        json.dump(tiers[t], f, ensure_ascii=False)

print(f'TIER1:{len(tiers[1])}')
print(f'TIER2:{len(tiers[2])}')
print(f'TIER3:{len(tiers[3])}')
PY
\`\`\`

Report the numbers. If PENDING is 0, say "nothing to standardize".`,
  { label: 'audit', phase: 'Audit' }
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
    `Auto-standardize Tier 1 items. Run this Python script:

\`\`\`bash
.venv/bin/python << 'PY'
import json, datetime as dt
from pathlib import Path

FORCE_ALL = ${forceAll ? 'True' : 'False'}
ITEMS = Path('data/items.jsonl')
BASE = Path('/tmp/manga-standardize-run')
tier1 = json.load(open(BASE / 'tier1.json'))

url_to_md = {}
for p in tier1:
    url_to_md[p['url']] = p

items = [json.loads(l) for l in open(ITEMS)]
now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
applied = 0

for it in items:
    if it.get('standardized_at') and not FORCE_ALL:
        continue
    md = url_to_md.get(it.get('url',''))
    if not md:
        continue
    if not it.get('title_original'):
        it['title_original'] = it.get('title', '')
    it['series_key'] = md.get('proposed_series_key', '')
    it['series_display'] = md.get('proposed_series_display', '')
    it['edition_key'] = md.get('proposed_edition_key', '')
    it['edition_display'] = md.get('proposed_edition_display', '')
    it['volume'] = md.get('proposed_volume', '')
    if md.get('proposed_title'):
        it['title'] = md['proposed_title']
    it['standardized_at'] = now_iso
    applied += 1

tmp = ITEMS.with_suffix(ITEMS.suffix + '.tmp')
with tmp.open('w', encoding='utf-8') as fh:
    for it in items:
        fh.write(json.dumps(it, ensure_ascii=False) + '\\n')
tmp.replace(ITEMS)
print(f'Tier 1 auto-standardized: {applied} items (0 LLM tokens)')
PY
\`\`\`

Report the count.`,
    { label: 'auto-t1', phase: 'Auto-standardize' }
  )
  log(`Tier 1 auto-standardized: ${tier1Count} items`)
  // Checkpoint: Tier 1 completo, T2/T3 aún pendientes
  await agent(
    `Write this JSON to ${PROGRESS_FILE} (create or overwrite):
${JSON.stringify({ limit: limit||0, force_all: forceAll, tier1_done: true, has_tier2: false, has_tier3: false, tier2_results: null, tier3_results: null }, null, 2)}`,
    { label: 'checkpoint-t1', phase: 'Auto-standardize' }
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
    { label: 'chunk-t2', phase: 'Classify' }
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

Read the file, then return structured output with your validation results for ALL items in the file.`,
          {
            label: `validate-t2-${idx}`,
            phase: 'Classify',
            schema: TIER2_BATCH_SCHEMA,
            model: 'sonnet',
          }
        )
      )
    }
    const t2BatchResults = await parallel(t2Thunks)
    for (const r of t2BatchResults) {
      if (r && r.items) tier2Results.push(...r.items)
    }
    log(`Tier 2 validated: ${tier2Results.length} items via sonnet`)
  }
  // Checkpoint: T1+T2 completos, T3 aún pendiente
  await agent(
    `Write this JSON to ${PROGRESS_FILE} (create or overwrite):
${JSON.stringify({ limit: limit||0, force_all: forceAll, tier1_done: true, has_tier2: true, has_tier3: false, tier2_results: tier2Results, tier3_results: null }, null, 2)}`,
    { label: 'checkpoint-t2', phase: 'Classify' }
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
    { label: 'chunk-t3', phase: 'Derive' }
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

Read the file, then return structured output for ALL items.`,
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
    { label: 'checkpoint-t3', phase: 'Derive' }
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

First, write this JSON to /tmp/manga-standardize-run/llm_results.json:
${JSON.stringify(allLlmResults)}

Then run the merge + dedup + consistency check + slug generation + translation pipeline:

\`\`\`bash
.venv/bin/python << 'PY'
import json, sys
sys.path.insert(0, "scripts")
import series_aliases, importlib
importlib.reload(series_aliases)
from series_aliases import canonical_series_key, _build_lookup
_build_lookup.cache_clear()
from pathlib import Path
import datetime as dt, re
from collections import defaultdict, Counter

ITEMS = Path("data/items.jsonl")
BLACKLIST = Path("data/non_manga_blacklist.jsonl")

FORCE_ALL = ${forceAll ? 'True' : 'False'}
results_list = json.load(open("/tmp/manga-standardize-run/llm_results.json"))
results = {r["url"]: r for r in results_list}

# Heuristic proposals (Tier 2/3 audit projections) — used as fallback when an
# LLM result comes back with empty keys, so an accepted-but-blank Tier 2 item
# does not become an orphan with empty series_key/edition_key.
proposals = {}
for _t in ("tier2.json", "tier3.json"):
    _p = Path("/tmp/manga-standardize-run") / _t
    if _p.exists():
        try:
            for _proj in json.load(open(_p)):
                proposals[_proj.get("url","")] = _proj
        except Exception:
            pass

items = [json.loads(l) for l in open(ITEMS)]
now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

pending_before = sum(1 for it in items if not it.get("standardized_at"))
left_pending = 0  # items with a result but no usable keys → retried next run

non_manga = []
final = []
for it in items:
    if it.get("standardized_at") and not FORCE_ALL:
        final.append(it); continue
    r = results.get(it.get("url",""))
    if not r:
        final.append(it); continue
    if not r.get("is_manga", True):
        non_manga.append({
            "url": it.get("url",""), "title": it.get("title",""),
            "source": it.get("source",""), "publisher": it.get("publisher",""),
            "reason": r.get("non_manga_reason","flagged"),
            "reviewed_at": now_iso,
        })
        continue
    # Pull final values, falling back to the heuristic proposal for empties.
    prop = proposals.get(it.get("url",""), {})
    sk = (r.get("series_key","") or "").strip() or prop.get("proposed_series_key","")
    ek = (r.get("edition_key","") or "").strip() or prop.get("proposed_edition_key","")
    if not (sk and ek):
        # No usable keys even after fallback — leave PENDING (no standardized_at)
        # so the next run retries instead of creating an orphan.
        left_pending += 1
        final.append(it); continue
    it["series_key"] = sk
    it["series_display"] = (r.get("series_display","") or "").strip() or prop.get("proposed_series_display","")
    it["edition_key"] = ek
    it["edition_display"] = (r.get("edition_display","") or "").strip() or prop.get("proposed_edition_display","")
    it["volume"] = (r.get("volume","") or "").strip() or prop.get("proposed_volume","")
    new_title = ((r.get("title_standardized","") or "").strip() or prop.get("proposed_title","")).strip()
    if new_title:
        if not it.get("title_original"):
            it["title_original"] = it.get("title","")
        it["title"] = new_title
    new_sk, new_sd = canonical_series_key(it["title"], it["series_key"], it["series_display"])
    if new_sk != it["series_key"]:
        old_sk = it["series_key"]
        it["series_key"] = new_sk
        it["series_display"] = new_sd
        if it["edition_key"].startswith(old_sk + "-"):
            it["edition_key"] = new_sk + it["edition_key"][len(old_sk):]
    elif new_sd != it["series_display"]:
        it["series_display"] = new_sd
    it["standardized_at"] = now_iso
    final.append(it)

# Consistency check (listadomanga collection groups)
groups = defaultdict(list)
for it in final:
    if not it.get("standardized_at"): continue
    url = it.get("url","") or ""
    m = re.search(r"listadomanga\\.es/coleccion\\.php\\?id=(\\d+)", url)
    if m: groups[f"lmc:{m.group(1)}"].append(it)

outliers = 0
for gk, grp in groups.items():
    if len(grp) < 4: continue
    sk_counts = Counter(it.get("series_key","") for it in grp)
    dom_sk, dom_sk_n = sk_counts.most_common(1)[0]
    if dom_sk_n >= 3:
        for it in grp:
            if it.get("series_key","") and it["series_key"] != dom_sk:
                old_ek = it.get("edition_key","")
                if old_ek.startswith(it["series_key"] + "-"):
                    it["edition_key"] = dom_sk + old_ek[len(it["series_key"]):]
                it["series_key"] = dom_sk
                outliers += 1

# Consolidar por producto (modelo 1-fila-por-producto): el edition_key/volume
# cambió al estandarizar, así que recomputamos cluster_key y FUSIONAMOS los
# duplicados con merge_cluster (NO los borramos — perdería las fuentes hermanas).
# consolidate_by_cluster es la MISMA primitiva que usa append_jsonl al ingestar.
from manga_watch import derive_cluster_key, consolidate_by_cluster
for it in final:
    it["cluster_key"] = derive_cluster_key(it)
_before_consolidate = len(final)
deduped = consolidate_by_cluster(final)
dedup_count = _before_consolidate - len(deduped)

tmp = ITEMS.with_suffix(ITEMS.suffix + ".tmp")
with tmp.open("w", encoding="utf-8") as fh:
    for it in deduped:
        fh.write(json.dumps(it, ensure_ascii=False) + "\\n")
tmp.replace(ITEMS)

existing_bl = set()
if BLACKLIST.exists():
    for line in open(BLACKLIST):
        try: existing_bl.add(json.loads(line).get("url",""))
        except: pass
new_bl = [nm for nm in non_manga if nm["url"] not in existing_bl]
with BLACKLIST.open("a", encoding="utf-8") as fh:
    for nm in new_bl:
        fh.write(json.dumps(nm, ensure_ascii=False) + "\\n")

standardized_after = sum(1 for it in deduped if it.get("standardized_at"))
still_pending = sum(1 for it in deduped if not it.get("standardized_at"))
print(f"Items: {len(items)} -> {len(deduped)}")
print(f"Non-manga: {len(new_bl)}")
print(f"Deduped: {dedup_count}")
print(f"Outliers fixed: {outliers}")
# Integrity report — surfaces any item that the LLM step failed to key.
print(f"INTEGRITY: pending_before={pending_before} left_pending(no usable keys)={left_pending} still_pending_after={still_pending}")
orphans = sum(1 for it in deduped if it.get("standardized_at") and not (it.get("series_key") and it.get("edition_key")))
if orphans:
    print(f"WARNING: {orphans} standardized items have EMPTY keys (orphans) — investigate before relying on dedup/slugs.")
else:
    print("INTEGRITY OK: 0 standardized items with empty keys.")
PY
\`\`\`

Then run slugs and translation:
\`\`\`bash
.venv/bin/python scripts/retrofit/generate_slugs.py --only-missing --verbose
.venv/bin/python scripts/retrofit/translate_descriptions.py --workers 4
\`\`\`

Then run tests:
\`\`\`bash
.venv/bin/python -m pytest tests/test_extraction.py -q
\`\`\`

Report all results.`,
  { label: 'merge-and-finalize', phase: 'Merge' }
)

log(`Merge complete: ${mergeAgent}`)

// Cleanup: borrar temporales Y el archivo de progreso (corrida exitosa)
await agent(
  `Run: rm -rf /tmp/manga-standardize-run && rm -f ${PROGRESS_FILE} && echo "Cleanup OK"`,
  { label: 'cleanup', phase: 'Merge' }
)

return {
  status: 'completed',
  tier1_auto: tier1Count,
  tier2_validated: tier2Results.length,
  tier3_derived: tier3Results.length,
  total_processed: tier1Count + tier2Results.length + tier3Results.length,
}
