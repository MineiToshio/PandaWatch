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

const BASE = '/Users/Shared/Proyectos/manga-watch'

// Reglas de negocio del prompt (edition_key, publisher/país/tipo de edición,
// 画集付き, coleccion=edición, allowlists…) NO viven acá — viven en UNA
// fuente única (auditoría 2026-07-08, hallazgo F7: la regla 画集付き estaba
// SOLO en SKILL.md, 0 veces en este workflow — drift confirmado). Cada
// subagente Tier 2/3 lee ese archivo con su propia tool Read antes de
// procesar. Cambiar una regla ahí alcanza para los dos caminos (SKILL.md
// manual + este workflow).
const PROMPT_RULES_FILE = `${BASE}/.claude/skills/watch-standardize-catalog/prompt-rules.md`

// Run dir persistente del skill/workflow (auditoría 2026-07-08, hallazgo F3):
// antes vivía en /tmp/manga-standardize-run (volátil ante reboot), lo que
// forzaba a duplicar los resultados LLM completos dentro del checkpoint
// data/standardize-progress.json "por si acaso" — una bomba de tokens (hasta
// 2000 items × 8 campos, DOS veces). Ahora vive en data/ (gitignored) y
// sobrevive un reboot, así que el checkpoint solo necesita flags + qué
// chunks YA tienen result_*.jsonl en disco (detectable listando el dir) —
// nunca los payloads. `scripts/standardize_apply.py` declara su PROPIO
// DEFAULT_BASE idéntico (otra ola de la auditoría, no se toca acá); por eso
// TODAS las invocaciones de ambos scripts pasan `--base` explícito.
const RUN_DIR = 'data/standardize-run'
const PROGRESS_FILE = 'data/standardize-progress.json'

// --- Schemas for structured output ---

// Contrato de scripts/standardize_audit.py (hallazgo F6): el script escribe
// `${RUN_DIR}/summary.json` con estos campos — el agente los COPIA, nunca
// los recalcula ni los infiere de texto libre. Reemplaza el parseo por regex
// (`PENDING:\d+`, etc.) que fallaba silenciosamente ante cualquier
// reformateo del reporte de un subagente.
const S_AUDIT_SUMMARY = {
  type: 'object',
  properties: {
    total:     { type: 'integer' },
    pending:   { type: 'integer' },
    tier1:     { type: 'integer' },
    tier2:     { type: 'integer' },
    tier3:     { type: 'integer' },
    exhausted: { type: 'integer' },
  },
  required: ['total', 'pending', 'tier1', 'tier2', 'tier3'],
}

// Cuántos chunks escribió el paso de partición — reemplaza el regex
// `/(\d+)\s*chunk/` sobre el reporte libre del agente (hallazgo F6): si el
// agente reformateaba la frase, el fallback a 1 procesaba un solo chunk y
// dejaba el resto pendiente en silencio.
const S_CHUNK_COUNT = {
  type: 'object',
  properties: { chunks: { type: 'integer' } },
  required: ['chunks'],
}

// Índices NN de los `result_t{2,3}_NN.jsonl` YA presentes en el run dir —
// usado solo en modo resume para saltear chunks ya resueltos.
const S_EXISTING_RESULTS = {
  type: 'object',
  properties: {
    existing_indices: { type: 'array', items: { type: 'integer' } },
  },
  required: ['existing_indices'],
}

// Salida de CADA subagente Tier 2/3 (hallazgo F3): antes devolvía el batch
// COMPLETO de items (series_key/edition_key/... por item) como structured
// output — datos que el merge NUNCA leyó de ahí (los lee de los
// result_*.jsonl que el propio subagente escribe con la tool Write). Ese
// duplicado costaba ~50% de los tokens de salida de la fase más cara del
// workflow. Ahora el structured output es solo un resumen chico.
const S_CHUNK_SUMMARY = {
  type: 'object',
  properties: {
    count:       { type: 'integer', description: 'Items processed in this chunk' },
    urls_ok:     { type: 'array', items: { type: 'string' }, description: 'URLs standardized successfully' },
    urls_failed: { type: 'array', items: { type: 'string' }, description: 'URLs that could not be processed' },
  },
  required: ['count'],
}

// Checkpoint MÍNIMO (hallazgo F3d): solo flags, nunca payloads. Los chunks
// Tier 2/3 ya completados se detectan listando result_*.jsonl en el run dir
// persistente — no hace falta guardarlos acá.
const PROGRESS_LOAD_SCHEMA = {
  type: 'object',
  properties: {
    exists:     { type: 'boolean', description: 'true si el archivo existe' },
    tier1_done: { type: 'boolean', description: 'Tier 1 ya completado en la corrida anterior' },
  },
  required: ['exists'],
}

// ====== WORKFLOW BODY ======

// args: { limit?: number, force_all?: boolean, resume_progress?: boolean }
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

function tierProgressPayload(fields) {
  return { limit: limit || 0, force_all: forceAll, tier1_done: false, ...fields }
}

async function writeProgress(fields) {
  await agent(
    `Write this JSON to ${PROGRESS_FILE} (create or overwrite): ${JSON.stringify(tierProgressPayload(fields))}`,
    { label: 'checkpoint', phase: 'Audit', model: 'haiku' }
  )
}

// --- Progreso persistente ---
// Si args.resume_progress === true, cargamos el checkpoint chico (solo
// tier1_done) y saltamos Tier 1 si ya corrió. Tier 2/3 se resumen SOLOS
// detectando qué result_*.jsonl ya existen en ${RUN_DIR} — no dependen de
// este archivo. Si NO es resume, limpiamos el run dir primero para no
// reusar chunks/resultados de una corrida anterior con otro limit/force_all.
const resumeProgress = !!(ARGS && ARGS.resume_progress)
let savedTier1Done = false

if (resumeProgress) {
  const prog = await agent(
    `Check if ${PROGRESS_FILE} exists using Bash (ls command).
If it exists, read it with the Read tool and return its contents parsed as structured output.
If it does not exist, return { "exists": false, "tier1_done": false }.`,
    { label: 'load-progress', phase: 'Audit', schema: PROGRESS_LOAD_SCHEMA, model: 'haiku' }
  )
  if (prog && prog.exists) {
    savedTier1Done = !!prog.tier1_done
    log(`Progreso cargado — T1:${savedTier1Done ? '✅' : '⏳'}. T2/T3 se resumen solos detectando result_*.jsonl en ${RUN_DIR}/.`)
  } else {
    log('No se encontró archivo de progreso — empezando de cero')
  }
} else {
  await agent(`Run: rm -rf ${RUN_DIR} && echo "Clean OK"`,
    { label: 'clean-run-dir', phase: 'Audit', model: 'haiku' })
}

phase('Audit')

// Step 1: Read pending items and compute tier distribution.
// La lógica vive en scripts/standardize_audit.py (fuente única, compartida
// con el SKILL.md) — escribe tier{1,2,3}.json con proposed_*,
// existing_edition_key y known_edition_keys, MÁS summary.json (el contrato
// de conteos, hallazgo F6). El agente copia summary.json tal cual, nunca
// recalcula ni parsea texto libre.
const auditSummary = await agent(
  `Run this command:

\`\`\`bash
.venv/bin/python scripts/standardize_audit.py --base ${RUN_DIR}${forceAll ? ' --force-all' : ''}${limit ? ` --limit ${limit}` : ''}
\`\`\`

Then read ${RUN_DIR}/summary.json with the Read tool and return ITS CONTENTS
as structured output verbatim — copy the numbers from the file, do not
recompute or guess them from the command's stdout.`,
  { label: 'audit', phase: 'Audit', schema: S_AUDIT_SUMMARY, model: 'haiku' }
)

const pendingCount = auditSummary.pending || 0
if (pendingCount === 0) {
  log('Nothing to standardize — corpus is up to date.')
  return { status: 'nothing_to_standardize', items_processed: 0 }
}

const tier1Count = auditSummary.tier1 || 0
const tier2Count = auditSummary.tier2 || 0
const tier3Count = auditSummary.tier3 || 0

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
.venv/bin/python scripts/standardize_apply.py tier1 --base ${RUN_DIR}${forceAll ? ' --force-all' : ''}
\`\`\``,
    { label: 'auto-t1', phase: 'Auto-standardize', model: 'haiku' }
  )
  log(`Tier 1 auto-standardized: ${tier1Count} items`)
  // Checkpoint mínimo: solo el flag (hallazgo F3d — nada de payloads acá).
  await writeProgress({ tier1_done: true })
} else {
  log('No Tier 1 items to auto-standardize.')
}

// --- Helper: subagente Tier 2/3 para UN chunk. Lee las reglas de la fuente
// única (prompt-rules.md) en vez de recibirlas inlineadas (hallazgo F7). ---
function tierChunkTask({ tier, idx, model, phase: phaseName }) {
  const label = String(idx).padStart(2, '0')
  const chunkFile = `${RUN_DIR}/t${tier}_chunk_${label}.json`
  const resultFile = `${RUN_DIR}/result_t${tier}_${label}.jsonl`
  const tierInstructions = tier === 2
    ? `Estos son items Tier 2 — el scraper ya propuso series_key/edition_key/volume
(campos proposed_*). Tu trabajo es VALIDAR cada propuesta contra las reglas
del archivo de arriba, sección "Reglas específicas por tier" → Tier 2.`
    : `Estos son items Tier 3 — sin heurística confiable. Derivá todo desde cero
siguiendo las reglas del archivo de arriba, sección "Reglas específicas por
tier" → Tier 3.`
  return () => agent(
    `Antes de procesar, leé COMPLETO ${PROMPT_RULES_FILE} — son las reglas
OBLIGATORIAS de negocio (edition_key, publisher/país/tipo de edición,
画集付き, coleccion=edición, allowlists…). Aplicalas literalmente, no las
reinterpretes ni las resumas de memoria.

Leé ${chunkFile}. ${tierInstructions}

1. Con la tool Write, escribí tus resultados a ${resultFile} — UN objeto
   JSON compacto por línea (JSONL), una línea por item de entrada, MISMO
   ORDEN. Cada línea debe tener exactamente estos campos: url, is_manga,
   non_manga_reason, series_key, series_display, edition_key,
   edition_display, volume.
2. Devolvé la salida estructurada: count = items procesados, urls_ok = URLs
   estandarizadas con éxito, urls_failed = URLs que no pudiste procesar.

Procesá TODOS los items. La cantidad de líneas del JSONL debe igualar la
cantidad de items de entrada.`,
    { label: `${tier === 2 ? 'validate' : 'derive'}-t${tier}-${label}`, phase: phaseName, schema: S_CHUNK_SUMMARY, model }
  )
}

// --- Helper: partición + resume selectivo, compartido por Tier 2 y Tier 3. ---
async function runTierChunks({ tier, tierCount, chunkSize, model, phaseName }) {
  if (tierCount === 0) {
    log(`No Tier ${tier} items.`)
    return
  }
  const chunkResult = await agent(
    `Read ${RUN_DIR}/tier${tier}.json. Split into chunks of ${chunkSize} items.
Write each chunk to ${RUN_DIR}/t${tier}_chunk_NN.json (00, 01, 02, ...).`,
    { label: `chunk-t${tier}`, phase: phaseName, schema: S_CHUNK_COUNT, model: 'haiku' }
  )
  const chunkCount = chunkResult.chunks || 0
  if (chunkCount === 0) {
    log(`Tier ${tier}: 0 chunks creados.`)
    return
  }

  const allIndices = Array.from({ length: chunkCount }, (_, i) => i)
  let missingIndices = allIndices
  // Resume selectivo (hallazgo F3): solo re-lanza los chunks SIN result file
  // — el resto ya está resuelto en disco (run dir persistente).
  if (resumeProgress) {
    const existing = await agent(
      `List files matching ${RUN_DIR}/result_t${tier}_*.jsonl using Bash (ls). For
each file found, extract the NN index from its name (e.g. result_t${tier}_03.jsonl -> 3).`,
      { label: `check-t${tier}-results`, phase: phaseName, schema: S_EXISTING_RESULTS, model: 'haiku' }
    )
    const existingSet = new Set(existing.existing_indices || [])
    missingIndices = allIndices.filter(i => !existingSet.has(i))
    if (missingIndices.length < allIndices.length) {
      log(`Tier ${tier}: ${allIndices.length - missingIndices.length}/${allIndices.length} chunks ya resueltos (checkpoint) — corriendo ${missingIndices.length} restantes`)
    }
  }

  if (missingIndices.length > 0) {
    await parallel(missingIndices.map(idx => tierChunkTask({ tier, idx, model, phase: phaseName })))
  }
  log(`Tier ${tier}: ${chunkCount} chunk(s) totales — ${missingIndices.length} corridos esta vez`)
}

// Step 3: Process Tier 2 with haiku (lightweight validation)
phase('Classify')
await runTierChunks({ tier: 2, tierCount: tier2Count, chunkSize: 20, model: 'haiku', phaseName: 'Classify' })

// Step 4: Process Tier 3 with sonnet (full derivation)
phase('Derive')
await runTierChunks({ tier: 3, tierCount: tier3Count, chunkSize: 15, model: 'sonnet', phaseName: 'Derive' })

// Step 5: Merge everything back
phase('Merge')

const mergeAgent = await agent(
  `Merge standardization results into items.jsonl.

The per-chunk LLM result files already exist on disk at
${RUN_DIR}/result_t2_*.jsonl and result_t3_*.jsonl (each subagent wrote its
own JSONL). DO NOT transcribe any data yourself — the merge logic lives in
scripts/standardize_apply.py (single source of truth, shared with the
SKILL.md): it reads those files via glob, preserves existing edition_keys
(the LLM is not the grouping authority), falls back to heuristic proposals
for empty keys (items with no usable keys stay PENDING, never orphans),
blacklists non-manga, fixes series outliers per /coleccion, recomputes
cluster_key and consolidates:

\`\`\`bash
.venv/bin/python scripts/standardize_apply.py merge --base ${RUN_DIR}${forceAll ? ' --force-all' : ''}
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

// Cleanup: borrar el run dir Y el archivo de progreso (corrida exitosa)
await agent(
  `Run: rm -rf ${RUN_DIR} && rm -f ${PROGRESS_FILE} && echo "Cleanup OK"`,
  { label: 'cleanup', phase: 'Merge', model: 'haiku' }
)

return {
  status: 'completed',
  tier1_auto: tier1Count,
  tier2_validated: tier2Count,
  tier3_derived: tier3Count,
  total_processed: tier1Count + tier2Count + tier3Count,
}
