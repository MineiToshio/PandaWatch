export const meta = {
  name: 'listadomanga-audit',
  description: 'Audita el proceso de ingestión de ListadoManga — detecta gaps entre el sitio real y el parser, prioriza y aplica mejoras para delta y full',
  phases: [
    { title: 'Análisis de código',   detail: 'Lee parser, enforcer y scripts de auditoría en paralelo (haiku)' },
    { title: 'Selección de muestra', detail: 'Extrae IDs de colecciones representativas por tipo de caso del corpus local (haiku)' },
    { title: 'Inspección Chrome',    detail: 'Navega lista.php, calendario.php y muestra estratificada de colecciones — TODOS los tipos de caso (sonnet)' },
    { title: 'Síntesis',             detail: 'Identifica gaps reales entre sitio y parser, prioriza por impacto (sonnet)' },
    { title: 'Implementación',       detail: 'Aplica mejoras críticas, verifica enforcer + validador (sonnet)' },
  ],
}

const BASE = '/Users/Shared/Proyectos/manga-watch'

// Checkpoint persistente de las fases 1-3 (auditoría 2026-07-08, hallazgo
// F11.1): la fase Chrome es la más cara del workflow (~15-25 navegaciones);
// antes, si moría a mitad de camino, se perdía TODO y había que re-navegar
// desde cero. Mismo patrón que data/standardize-progress.json.
const CHECKPOINT_FILE = 'data/listadomanga-audit-progress.json'

// args: { chrome_model?: string, resume?: boolean }
// chrome_model — override del modelo de los steps Chrome (default 'sonnet').
//   Antes hardcodeado a 'fable' (modelo temporal) — auditoría 2026-07-08,
//   hallazgo F1: la tarea es EXTRACCIÓN MECÁNICA (JS pre-escrito abajo +
//   salida constreñida por schema S_CHROME), no razonamiento sobre HTML
//   libre — sonnet alcanza de sobra y no depende de un modelo que puede
//   dejar de existir. Parametrizable para experimentar con otro modelo.
// resume — si true, carga el checkpoint de ${CHECKPOINT_FILE} y saltea las
//   fases 1-3 (o los grupos Chrome) ya completados.
let ARGS = args
if (typeof ARGS === 'string') {
  try { ARGS = JSON.parse(ARGS) } catch { ARGS = {} }
}
const CHROME_MODEL = (ARGS && ARGS.chrome_model) || 'sonnet'
const doResume = !!(ARGS && ARGS.resume)

// ─── SCHEMAS ────────────────────────────────────────────────────────────────

const S_CODE = {
  type: 'object',
  properties: {
    summary:      { type: 'string' },
    gaps:         { type: 'array', items: { type: 'string' } },
    key_patterns: { type: 'array', items: { type: 'string' }, description: 'Strings/patrones H2 exactos que el parser usa para detectar secciones' },
  },
  required: ['summary', 'gaps', 'key_patterns'],
}

// Muestra estratificada: IDs de coleccion.php?id=N por tipo de caso
const S_SAMPLE = {
  type: 'object',
  description: 'IDs de colecciones representativas por tipo de caso (2-3 por tipo)',
  properties: {
    regular_normal:    { type: 'array', items: { type: 'string' }, description: 'Edición normal: solo tomos regulares, sin nada premium/especial' },
    regular_premium:   { type: 'array', items: { type: 'string' }, description: 'Edición premium (kanzenban, cartoné, A5): todos los tomos entran' },
    con_especiales:    { type: 'array', items: { type: 'string' }, description: 'Edición con sección de Ediciones Especiales' },
    con_variantes:     { type: 'array', items: { type: 'string' }, description: 'Edición con sección de Portadas alternativas' },
    con_packs:         { type: 'array', items: { type: 'string' }, description: 'Edición con sección de Packs' },
    con_limited:       { type: 'array', items: { type: 'string' }, description: 'Edición con items de kind=limited' },
    con_cofres_extras: { type: 'array', items: { type: 'string' }, description: 'Edición con Layout B: cofres/extras de 1ª edición vinculados a tomos' },
    con_galeria:       { type: 'array', items: { type: 'string' }, description: 'Items con galería (images[] > 1 entrada): confirma Layout B funcionando' },
    recientes:         { type: 'array', items: { type: 'string' }, description: 'Colecciones con ID >= 6000 (recientes, para detectar cambios de HTML)' },
    adulto:            { type: 'array', items: { type: 'string' }, description: 'Colecciones que potencialmente tienen modal de adult content (si las hay en el corpus)' },
  },
  required: ['regular_normal', 'regular_premium', 'con_especiales', 'con_variantes', 'con_packs', 'con_cofres_extras', 'recientes'],
}

const S_CHROME = {
  type: 'object',
  properties: {
    pages_inspected: { type: 'array', items: { type: 'string' }, description: 'URLs visitadas' },
    h2_sections_per_page: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          url:      { type: 'string' },
          h2_list:  { type: 'array', items: { type: 'string' } },
          formato:  { type: 'string', description: 'Texto del campo "Formato:" encontrado en la página' },
          table_classes: { type: 'array', items: { type: 'string' }, description: 'Clases/atributos de las <table> encontradas' },
          anomalies:    { type: 'array', items: { type: 'string' }, description: 'Cualquier elemento HTML no documentado o inesperado' },
        },
        required: ['url', 'h2_list'],
      },
    },
    undocumented_sections: { type: 'array', items: { type: 'string' }, description: 'H2 encontrados que NO están en la lista de secciones conocidas del parser' },
    structural_gaps:       { type: 'array', items: { type: 'string' }, description: 'Diferencias entre el HTML real y lo que el parser espera' },
    notes: { type: 'string' },
  },
  required: ['pages_inspected', 'h2_sections_per_page', 'undocumented_sections', 'structural_gaps', 'notes'],
}

const S_IMPROVEMENTS = {
  type: 'object',
  properties: {
    critical: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title:    { type: 'string' },
          problem:  { type: 'string' },
          solution: { type: 'string' },
          affects:  { type: 'string', enum: ['delta', 'full', 'ambos'] },
          files:    { type: 'array', items: { type: 'string' } },
        },
        required: ['title', 'problem', 'solution', 'affects', 'files'],
      },
    },
    medium: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title:    { type: 'string' },
          problem:  { type: 'string' },
          solution: { type: 'string' },
          affects:  { type: 'string' },
        },
        required: ['title', 'problem', 'solution', 'affects'],
      },
    },
    low:  { type: 'array', items: { type: 'object', properties: { title: { type: 'string' }, notes: { type: 'string' } }, required: ['title', 'notes'] } },
    skip: { type: 'array', items: { type: 'object', properties: { item: { type: 'string' }, reason: { type: 'string' } }, required: ['item', 'reason'] } },
  },
  required: ['critical', 'medium', 'low', 'skip'],
}

// Checkpoint de las fases 1-3 (hallazgo F11.1). Reusa S_CODE/S_SAMPLE/S_CHROME
// para las sub-formas en vez de declarar objetos libres.
const S_PROGRESS = {
  type: 'object',
  properties: {
    exists:          { type: 'boolean' },
    has_analysis:    { type: 'boolean' },
    has_sample:      { type: 'boolean' },
    parser_analysis:   S_CODE,
    enforcer_analysis: S_CODE,
    audit_analysis:    S_CODE,
    sample:            S_SAMPLE,
    chrome_results: {
      type: 'array',
      description: 'Resultados Chrome ya completados en una corrida anterior, por label',
      items: {
        type: 'object',
        properties: { label: { type: 'string' }, result: S_CHROME },
        required: ['label', 'result'],
      },
    },
  },
  required: ['exists'],
}

// Gate final (hallazgo F11.3): SOLO reporta PASS/FAIL + evidencia — el
// verificador ya no "corrige" nada por su cuenta (antes lo hacía sin dejar
// registro de qué tocó, y el workflow igual retornaba éxito).
const S_FINAL_CHECK = {
  type: 'object',
  properties: {
    status:           { type: 'string', enum: ['PASS', 'FAIL'] },
    tests_output:      { type: 'string' },
    validator_output:  { type: 'string' },
    violations:        { type: 'array', items: { type: 'string' }, description: 'Violaciones ERROR del validador o tests que fallaron, si status=FAIL' },
  },
  required: ['status', 'tests_output', 'validator_output'],
}

async function writeCheckpoint(progress, phaseName) {
  await agent(
    `Write this JSON to ${BASE}/${CHECKPOINT_FILE} (create or overwrite): ${JSON.stringify(progress)}`,
    { label: 'save-checkpoint', phase: phaseName || 'Análisis de código', model: 'haiku' }
  )
}

// ─── Checkpoint: cargar progreso anterior (si args.resume) ──────────────────
let progress = {
  exists: false, has_analysis: false, has_sample: false,
  parser_analysis: null, enforcer_analysis: null, audit_analysis: null,
  sample: null, chrome_results: [],
}
if (doResume) {
  const checkpoint = await agent(
    `Check if ${BASE}/${CHECKPOINT_FILE} exists using Bash (ls command).
If it exists, read it with the Read tool and return its contents parsed as structured output.
If it does not exist, return { "exists": false }.`,
    { label: 'load-checkpoint', phase: 'Análisis de código', schema: S_PROGRESS, model: 'haiku' }
  )
  if (checkpoint && checkpoint.exists) {
    progress = {
      exists: true,
      has_analysis: !!checkpoint.has_analysis,
      has_sample: !!checkpoint.has_sample,
      parser_analysis: checkpoint.parser_analysis || null,
      enforcer_analysis: checkpoint.enforcer_analysis || null,
      audit_analysis: checkpoint.audit_analysis || null,
      sample: checkpoint.sample || null,
      chrome_results: checkpoint.chrome_results || [],
    }
    log(`Checkpoint cargado — análisis:${progress.has_analysis ? '✅' : '⏳'} muestra:${progress.has_sample ? '✅' : '⏳'} chrome:${progress.chrome_results.length}/6`)
  } else {
    log('Sin checkpoint previo — empezando de cero')
  }
}

// ─── FASE 1: Análisis de código ──────────────────────────────────────────────
phase('Análisis de código')

let parserAnalysis, enforcerAnalysis, auditAnalysis
if (progress.has_analysis) {
  log('Fase 1 (Análisis de código) — cargada del checkpoint, salteando')
  parserAnalysis = progress.parser_analysis
  enforcerAnalysis = progress.enforcer_analysis
  auditAnalysis = progress.audit_analysis
} else {
  [parserAnalysis, enforcerAnalysis, auditAnalysis] = await parallel([

    () => agent(`
Lee COMPLETO el archivo ${BASE}/scripts/wikis/listadomanga_collections.py (~2034 líneas) y el doc ${BASE}/docs/scraper/sources/listadomanga.md.

Identifica:
1. Todos los H2 que el parser espera explícitamente para detectar secciones (cítalos textualmente)
2. Secciones del HTML que el parser IGNORA explícitamente — y por qué
3. TODOs / FIXMEs / casos no manejados
4. Strings hardcoded frágiles que romperían si el sitio cambia el HTML
5. Casos edge marcados como "pendiente" o "no implementado"
6. Diferencias entre mode=lista (full) y mode=calendar (delta) en la lógica de parsing
7. Secciones del HTML que el código nunca menciona (posibles gaps)

key_patterns: los H2 exactos que el parser usa (ej. "Números editados (Ediciones Especiales)", "Cofres de regalo con las primeras ediciones de")
gaps: posibles casos no cubiertos
`.trim(),
      { label: 'leer-parser', phase: 'Análisis de código', schema: S_CODE, model: 'haiku' }
    ),

    () => agent(`
Lee estos archivos en ${BASE}:
- scripts/retrofit/enforce_listadomanga_rules.py
- scripts/validate_corpus.py

Identifica:
1. Qué invariantes verifica validate_corpus.py para items de listadomanga (cítalas por nombre)
2. Qué pasos del enforcer dependen de strings del sitio o del HTML (frágiles ante cambios)
3. TODOs o casos edge no manejados en el enforcer
4. Warnings que deberían ser errores duros (o viceversa)
5. Posibles mejoras al pipeline de validación

key_patterns: nombres exactos de invariantes del validador
gaps: fragilidades y posibles mejoras
`.trim(),
      { label: 'leer-enforcer', phase: 'Análisis de código', schema: S_CODE, model: 'haiku' }
    ),

    () => agent(`
Lee estos archivos en ${BASE}:
- scripts/scrape_delta.sh
- scripts/scrape_full.sh (si no existe, lee scripts/ingest_listadomanga_full.py)
- scripts/audit/data_quality.py
- scripts/retrofit/README.md (primeras 100 líneas)

Identifica:
1. Diferencias exactas entre el pipeline delta y full — qué fases tiene uno y no el otro
2. Oportunidades para igualar cobertura o acelerar el pipeline
3. Checks de calidad que faltan en la auditoría bidireccional
4. Scripts que podrían ser más robustos

key_patterns: las fases del pipeline delta vs full
gaps: diferencias injustificadas entre delta y full, checks que faltan
`.trim(),
      { label: 'leer-scripts-pipeline', phase: 'Análisis de código', schema: S_CODE, model: 'haiku' }
    ),
  ])

  progress.has_analysis = true
  progress.parser_analysis = parserAnalysis
  progress.enforcer_analysis = enforcerAnalysis
  progress.audit_analysis = auditAnalysis
  await writeCheckpoint(progress, 'Análisis de código')
}

// ─── FASE 2: Selección de muestra estratificada ───────────────────────────────
phase('Selección de muestra')

let sample
if (progress.has_sample) {
  log('Fase 2 (Selección de muestra) — cargada del checkpoint, salteando')
  sample = progress.sample
} else {
  // Extraer IDs de colecciones representativas del corpus local por tipo de caso
  // cluster_key de listadomanga tiene formato: lmc:{cole}:{kind}:{vol}
  sample = await agent(`
Ejecuta este script Python en ${BASE} para extraer IDs de colecciones representativas del corpus:

  cd ${BASE} && .venv/bin/python - << 'PYEOF'
import json, re
from collections import defaultdict

by_kind = defaultdict(set)   # kind -> set of cole_ids
with_gallery = set()          # cole_ids con galería (images > 1)
all_cole_ids = set()

with open('data/items.jsonl') as f:
    for line in f:
        try:
            item = json.loads(line)
        except:
            continue
        ck = item.get('cluster_key', '')
        if not ck.startswith('lmc:'):
            continue
        parts = ck.split(':')
        if len(parts) < 3:
            continue
        cole = parts[1]
        kind = parts[2]
        all_cole_ids.add(cole)
        by_kind[kind].add(cole)
        # Detectar galería: items con más de 1 imagen
        images = item.get('images', [])
        if len(images) > 1:
            with_gallery.add(cole)

# Colecciones recientes: IDs numéricos >= 6000
recientes = sorted([c for c in all_cole_ids if c.isdigit() and int(c) >= 6000], key=int, reverse=True)

result = {
    'regular_normal':    list(by_kind.get('regular', set()))[:5],
    'regular_premium':   [],  # se aproxima por alta densidad de regulares por cole
    'con_especiales':    list(by_kind.get('especial', set()))[:3],
    'con_variantes':     list(by_kind.get('variant', set()))[:3],
    'con_packs':         list(by_kind.get('pack', set()))[:3],
    'con_limited':       list(by_kind.get('limited', set()))[:3],
    'con_cofres_extras': list(with_gallery - by_kind.get('especial', set()) - by_kind.get('variant', set()))[:3],
    'con_galeria':       list(with_gallery)[:3],
    'recientes':         recientes[:5],
    'all_kinds':         {k: len(v) for k, v in by_kind.items()},
    'total_coles':       len(all_cole_ids),
}

# Premium aproximado: coles con > 5 items regulares (proxy de edición premium)
dense = defaultdict(int)
with open('data/items.jsonl') as f:
    for line in f:
        try:
            item = json.loads(line)
        except:
            continue
        ck = item.get('cluster_key', '')
        if ck.startswith('lmc:'):
            parts = ck.split(':')
            if len(parts) >= 3 and parts[2] == 'regular':
                dense[parts[1]] += 1
premium_coles = [c for c, n in dense.items() if n > 5]
result['regular_premium'] = premium_coles[:3]

print(json.dumps(result, indent=2))
PYEOF

Devuelve el resultado como objeto JSON estructurado.
`.trim(),
    { label: 'seleccion-muestra', phase: 'Selección de muestra', schema: S_SAMPLE, model: 'haiku' }
  )

  progress.has_sample = true
  progress.sample = sample
  await writeCheckpoint(progress, 'Selección de muestra')
}

log(`Muestra lista — tipos encontrados: ${Object.entries(sample).filter(([k,v]) => Array.isArray(v) && v.length > 0).map(([k]) => k).join(', ')}`)

// ─── FASE 3: Inspección Chrome ────────────────────────────────────────────────
phase('Inspección Chrome')

const CHROME_PREAMBLE = `
Primero carga los schemas de Chrome con ToolSearch, query: "select:mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__get_page_text,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__find".
Si ese select no devuelve tools (el server MCP puede tener otro nombre en esta
máquina), reintentá con ToolSearch por PALABRAS CLAVE: query "chrome navigate
javascript" (max_results alto) y usá los nombres reales que aparezcan.

Reglas para no saturar el contexto:
- Nunca extraigas el DOM completo. Usa javascript_tool con selectores específicos.
- Limita cada extracción a < 2000 chars por página.
- Prefiere get_page_text sobre snapshots del DOM.
`.trim()

// Secciones documentadas como conocidas (para detectar nuevas)
const KNOWN_H2 = [
  'Números editados',
  'Números editados (Ediciones Especiales)',
  'Números editados (Portadas alternativas)',
  'Números editados (Packs)',
  'Números editados (Edición Revisada)',
  'Números no editados',
  'Números en preparación',
  'Cofres de regalo con las primeras ediciones de',
  'Sinopsis de',
  'Extras de',
  'Otras ediciones de',
]

// Los 6 grupos de inspección Chrome. Modelo mecánico (extracción con JS
// pre-escrito abajo + schema S_CHROME, no razonamiento sobre HTML libre —
// ver nota de CHROME_MODEL arriba). Antes corrían los 6 en parallel() sobre
// UN solo browser (hallazgo F11.2): listadomanga es un sitio chico y 6
// clientes simultáneos del mismo origen es poco cortés además de propenso a
// contención de tabs. Ahora corren de a 2 (paralelismo 2), checkpointeando
// después de cada par.
const chromeTasks = [
  {
    label: 'chrome-discovery',
    build: () => agent(`
${CHROME_PREAMBLE}

Navega las dos páginas de discovery y extrae su estructura.

PÁGINA 1: https://www.listadomanga.es/lista.php
Con javascript_tool extrae:
  ({
    total: document.querySelectorAll('a[href*="coleccion.php"]').length,
    sample_rows: Array.from(document.querySelectorAll('tr')).slice(0,8).map(r =>
      r.innerText.trim().replace(/\\s+/g,' ').slice(0,200)
    ),
    columns: Array.from(document.querySelectorAll('th')).map(th => th.innerText.trim()),
    has_filters: !!document.querySelector('select, input[type=text]'),
    link_format: document.querySelector('a[href*="coleccion.php"]')?.href
  })

PÁGINA 2: https://www.listadomanga.es/calendario.php
Con javascript_tool extrae:
  ({
    h2s: Array.from(document.querySelectorAll('h2')).map(h => h.innerText.trim()),
    total_links: document.querySelectorAll('a[href*="coleccion.php"]').length,
    sample_links: Array.from(document.querySelectorAll('a[href*="coleccion.php"]')).slice(0,8).map(a =>
      a.href + ' | ' + a.innerText.trim().slice(0,60)
    ),
    month_nav: Array.from(document.querySelectorAll('a')).filter(a =>
      a.href.includes('calendario') && a.href !== window.location.href
    ).map(a => a.href).slice(0,4)
  })

Busca en lista.php: ¿hay columnas extras (editorial, tipo, fecha)? ¿paginación? ¿filtros?
Busca en calendario.php: ¿cómo navegar meses anteriores? ¿fecha por item? ¿nuevo vs re-impresión?

Secciones conocidas del parser (para detectar nuevas):
${KNOWN_H2.map(s => '  - ' + s).join('\n')}
`.trim(),
      { label: 'chrome-discovery', phase: 'Inspección Chrome', schema: S_CHROME, model: CHROME_MODEL }
    ),
  },

  {
    label: 'chrome-normal-cofres',
    build: () => agent(`
${CHROME_PREAMBLE}

Inspecciona colecciones de tipo: edición normal y con cofres/extras.
IDs a navegar (del corpus real): ${[...(sample.regular_normal || []).slice(0,2), ...(sample.con_cofres_extras || []).slice(0,2)].map(id => `https://www.listadomanga.es/coleccion.php?id=${id}`).join(', ') || 'https://www.listadomanga.es/coleccion.php?id=1606, https://www.listadomanga.es/coleccion.php?id=2857'}

Para CADA URL:
  javascript_tool:
  ({
    url: window.location.href,
    h2s: Array.from(document.querySelectorAll('h2')).map(h => h.innerText.trim()),
    formato: document.querySelector('b')?.closest('p,td,div')?.innerText?.slice(0,200) || '',
    tables: Array.from(document.querySelectorAll('table')).map(t =>
      t.className + '|w=' + (t.getAttribute('width')||'') + '|s=' + (t.getAttribute('style')||'').slice(0,60)
    ),
    adult_modal: !!document.querySelector('[class*="adult"],[id*="adult"],dialog,[class*="modal"]'),
    img_attrs: Array.from(document.querySelectorAll('img.portada')).slice(0,3).map(i =>
      Object.keys(i.dataset).join(',') + ' lazy=' + i.getAttribute('loading')
    ),
  })

Secciones conocidas del parser (cualquier H2 fuera de esta lista es hallazgo nuevo):
${KNOWN_H2.map(s => '  - ' + s).join('\n')}

Busca especialmente: secciones Layout B (tablas de 920px de ancho con cofres/extras), si los cofres usan <table width="920"> o otra clase/estructura diferente.
`.trim(),
      { label: 'chrome-normal-cofres', phase: 'Inspección Chrome', schema: S_CHROME, model: CHROME_MODEL }
    ),
  },

  {
    label: 'chrome-especiales-variantes-packs',
    build: () => agent(`
${CHROME_PREAMBLE}

Inspecciona colecciones con ediciones especiales, portadas variantes y packs.
IDs a navegar: ${[...(sample.con_especiales || []).slice(0,2), ...(sample.con_variantes || []).slice(0,1), ...(sample.con_packs || []).slice(0,1)].map(id => `https://www.listadomanga.es/coleccion.php?id=${id}`).join(', ') || 'https://www.listadomanga.es/coleccion.php?id=1606'}

Para CADA URL:
  javascript_tool:
  ({
    url: window.location.href,
    h2s: Array.from(document.querySelectorAll('h2')).map(h => h.innerText.trim()),
    formato: document.querySelector('b')?.closest('p,td,div')?.innerText?.slice(0,200) || '',
    tables: Array.from(document.querySelectorAll('table')).map(t =>
      t.className + '|w=' + (t.getAttribute('width')||'') + '|s=' + (t.getAttribute('style')||'').slice(0,60)
    ),
    especiales_sample: Array.from(document.querySelectorAll('h2')).find(h =>
      h.innerText.includes('Especial')
    )?.nextElementSibling?.innerHTML?.slice(0,400) || '',
  })

Busca especialmente:
- ¿Los H2 de sección tienen texto EXACTO o con variaciones (ej. "Números editados (Edición Especial)" vs "Números editados (Ediciones Especiales)")?
- ¿Hay secciones de "Números editados (Edición Limitada)" como H2 separado de "Especiales"?
- ¿El contenido dentro de las secciones sigue el mismo layout <table class="ventana_id1">?

Secciones conocidas del parser:
${KNOWN_H2.map(s => '  - ' + s).join('\n')}
`.trim(),
      { label: 'chrome-especiales-variantes-packs', phase: 'Inspección Chrome', schema: S_CHROME, model: CHROME_MODEL }
    ),
  },

  {
    label: 'chrome-premium',
    build: () => agent(`
${CHROME_PREAMBLE}

Inspecciona colecciones premium: kanzenban, cartoné, tapa dura, A5, tomo doble.
IDs a navegar: ${(sample.regular_premium || ['6242', '3100']).slice(0,3).map(id => `https://www.listadomanga.es/coleccion.php?id=${id}`).join(', ')}

Para CADA URL:
  javascript_tool:
  ({
    url: window.location.href,
    h2s: Array.from(document.querySelectorAll('h2')).map(h => h.innerText.trim()),
    formato: document.querySelector('b')?.closest('p,td,div')?.innerText?.slice(0,300) || '',
    tables: Array.from(document.querySelectorAll('table')).map(t =>
      t.className + '|w=' + (t.getAttribute('width')||'') + '|s=' + (t.getAttribute('style')||'').slice(0,60)
    ),
  })

Busca ESPECIALMENTE:
1. ¿El "Formato:" sigue siendo un texto como "Formato: kanzenban" o cambió su estructura HTML (ya no es un <b> seguido de texto)?
2. ¿Hay nuevas palabras clave para detectar premium que no estén en el parser? (rústica con solapas, full color, etc.)
3. ¿Las ediciones premium tienen alguna sección adicional que las normales no tienen?
4. ¿El formato "Tomo doble A5" sigue teniendo esa forma exacta?

Secciones conocidas del parser:
${KNOWN_H2.map(s => '  - ' + s).join('\n')}
`.trim(),
      { label: 'chrome-premium', phase: 'Inspección Chrome', schema: S_CHROME, model: CHROME_MODEL }
    ),
  },

  {
    label: 'chrome-recientes',
    build: () => agent(`
${CHROME_PREAMBLE}

Inspecciona colecciones recientes (IDs altos) para detectar cambios de HTML o nuevos tipos.
IDs a navegar: ${(sample.recientes || []).slice(0,4).map(id => `https://www.listadomanga.es/coleccion.php?id=${id}`).join(', ') || 'https://www.listadomanga.es/lista.php (busca los últimos IDs)'}

Si no tienes IDs recientes del corpus, primero navega lista.php y extrae los hrefs de las últimas filas (las más recientes suelen estar al final o en orden alfanumérico).

Para CADA URL de colección:
  javascript_tool:
  ({
    url: window.location.href,
    h2s: Array.from(document.querySelectorAll('h2')).map(h => h.innerText.trim()),
    formato: document.querySelector('b')?.closest('p,td,div')?.innerText?.slice(0,200) || '',
    tables: Array.from(document.querySelectorAll('table')).map(t =>
      t.className + '|w=' + (t.getAttribute('width')||'')
    ),
    adult_modal: !!document.querySelector('[class*="adult"],[id*="adult"],dialog,[class*="modal"]'),
    any_new_elements: Array.from(document.querySelectorAll('[class]'))
      .map(el => el.tagName + '.' + el.className)
      .filter(c => !['ventana_id1','portada','cen'].some(k => c.includes(k)))
      .slice(0,10),
  })

Busca: ¿el HTML de las colecciones recientes es idéntico al de las antiguas? ¿Hay clases CSS nuevas, divs nuevos, o cambios de estructura?

Secciones conocidas del parser:
${KNOWN_H2.map(s => '  - ' + s).join('\n')}
`.trim(),
      { label: 'chrome-recientes', phase: 'Inspección Chrome', schema: S_CHROME, model: CHROME_MODEL }
    ),
  },

  {
    label: 'chrome-limited-gallery',
    build: () => agent(`
${CHROME_PREAMBLE}

Inspecciona colecciones con ediciones limitadas y/o con galería de fotos (extras vinculados).
IDs a navegar: ${[...(sample.con_limited || []).slice(0,2), ...(sample.con_galeria || []).slice(0,2)].map(id => `https://www.listadomanga.es/coleccion.php?id=${id}`).join(', ') || 'https://www.listadomanga.es/coleccion.php?id=2857'}

Para CADA URL:
  javascript_tool:
  ({
    url: window.location.href,
    h2s: Array.from(document.querySelectorAll('h2')).map(h => h.innerText.trim()),
    formato: document.querySelector('b')?.closest('p,td,div')?.innerText?.slice(0,200) || '',
    layout_b_tables: Array.from(document.querySelectorAll('table[width="920"]')).map(t =>
      t.innerHTML.slice(0,600)
    ),
    has_adult_modal: !!document.querySelector('[class*="adult"],[id*="adult"],dialog'),
  })

Busca especialmente:
- ¿Las tablas de Layout B (cofres/extras) siempre tienen width="920"? ¿O hay variaciones?
- ¿Los extras de 1ª edición están siempre dentro de una <table width="920">?
- ¿Hay algún caso donde los extras estén en un <div> en lugar de tabla?
- ¿Las ediciones "limitadas" tienen su propia sección H2 o van dentro de "Ediciones Especiales"?

Secciones conocidas del parser:
${KNOWN_H2.map(s => '  - ' + s).join('\n')}
`.trim(),
      { label: 'chrome-limited-gallery', phase: 'Inspección Chrome', schema: S_CHROME, model: CHROME_MODEL }
    ),
  },
]

const chromeResultsMap = new Map((progress.chrome_results || []).map(r => [r.label, r.result]))
const pendingChromeTasks = chromeTasks.filter(t => !chromeResultsMap.has(t.label))

if (pendingChromeTasks.length === 0) {
  log('Fase 3 (Inspección Chrome) — 6/6 cargados del checkpoint, salteando')
} else {
  if (chromeResultsMap.size > 0) {
    log(`Fase 3 (Inspección Chrome) — ${chromeResultsMap.size}/6 ya del checkpoint, corriendo ${pendingChromeTasks.length} restantes`)
  }
  // Paralelismo 2 (no los 6 juntos): listadomanga es un sitio chico — 6
  // clientes simultáneos del mismo origen es poco cortés y propenso a
  // contención de tabs sobre el mismo browser (hallazgo F11.2).
  for (let i = 0; i < pendingChromeTasks.length; i += 2) {
    const pair = pendingChromeTasks.slice(i, i + 2)
    const results = await parallel(pair.map(t => t.build))
    pair.forEach((t, idx) => chromeResultsMap.set(t.label, results[idx]))
    progress.chrome_results = Array.from(chromeResultsMap, ([label, result]) => ({ label, result }))
    await writeCheckpoint(progress, 'Inspección Chrome')
  }
}

const allChromeResults = chromeTasks.map(t => chromeResultsMap.get(t.label)).filter(Boolean)
log(`Chrome completado — ${allChromeResults.length} grupos inspeccionados`)
const totalPagesInspected = allChromeResults.reduce((n, r) => n + (r.pages_inspected?.length || 0), 0)
log(`Total páginas visitadas: ~${totalPagesInspected}`)

// ─── FASE 4: Síntesis y priorización ─────────────────────────────────────────
phase('Síntesis')

const synthesis = await agent(`
Eres el arquitecto técnico de PandaWatch. Sintetiza los hallazgos y genera un plan de mejoras CONCRETO y BASADO EN EVIDENCIA.

CONTEXTO DEL PROYECTO:
- ListadoManga: fuente más importante, ~1900-2000 items de ~67 fuentes
- Parser: scripts/wikis/listadomanga_collections.py (2034 líneas)
- Enforcer determinista e idempotente: scripts/retrofit/enforce_listadomanga_rules.py
- FULL: lista.php (~3432 colecciones) | DELTA: calendario.php (~500-600 ids recientes)
- Reglas duras: 1 coleccion=1 edition_key, país ES en edition_key, cluster_key lmc tier-0
- Validación: validate_corpus.py — invariantes SLUG/CLKEY/DUPCL/DUPSYN/LMCKIND/TITLE/ONECOLE/DUPVOL
- Gotchas ya RESUELTAS (no re-proponer): #43-#60

ANÁLISIS DEL PARSER:
${JSON.stringify(parserAnalysis)}

ANÁLISIS DEL ENFORCER Y VALIDADOR:
${JSON.stringify(enforcerAnalysis)}

ANÁLISIS DEL PIPELINE DELTA/FULL:
${JSON.stringify(auditAnalysis)}

MUESTRA DE CORPUS (tipos y cantidades encontradas):
${JSON.stringify(sample)}

HALLAZGOS DE CHROME (${allChromeResults.length} grupos, ~${totalPagesInspected} páginas):
${JSON.stringify(allChromeResults)}

Criterios de priorización:
- CRÍTICO: evidencia de items perdiéndose O datos incorrectos entrando. Solo con evidencia de Chrome o código.
- MEDIO: robustez ante cambios del sitio, cobertura incremental, mejor calidad de datos.
- BAJO: nice-to-have cosmético, sin impacto en corpus.
- SKIP: parece gap pero no lo es — documentar por qué.

Para cada mejora CRÍTICA: archivos exactos a tocar, qué cambiar específicamente.
NO proponer nada sin evidencia directa de los hallazgos.
NO proponer nada que rompa idempotencia o las invariantes del validador.
NO re-proponer gotchas #43-#60 ya resueltas.
`.trim(),
  { label: 'sintesis-mejoras', phase: 'Síntesis', schema: S_IMPROVEMENTS, model: 'sonnet' }
)

log(`Críticas: ${synthesis.critical.length} | Medias: ${synthesis.medium.length} | Bajas: ${synthesis.low.length} | Skip: ${synthesis.skip.length}`)

// Checkpoint de fases 1-3 ya no hace falta a partir de acá — la parte cara
// (Chrome) está resuelta y la síntesis/implementación son baratas. Se
// limpia al final (éxito o "no hay críticas").
async function cleanupCheckpoint() {
  await agent(`Run: rm -f ${BASE}/${CHECKPOINT_FILE} && echo "Cleanup OK"`,
    { label: 'cleanup-checkpoint', phase: 'Síntesis', model: 'haiku' })
}

// ─── FASE 5: Implementación ───────────────────────────────────────────────────
if (synthesis.critical.length === 0) {
  log('No hay mejoras críticas con evidencia suficiente — el proceso está bien calibrado.')
  await cleanupCheckpoint()
  return { status: 'no-critical-improvements', synthesis, chrome_pages: totalPagesInspected, final_check_status: 'not_applicable' }
}

phase('Implementación')

const implementations = await pipeline(
  synthesis.critical,
  async (improvement) => agent(`
Implementa esta mejora en el proceso de ingestión de ListadoManga.

MEJORA:
  Título:   ${improvement.title}
  Problema: ${improvement.problem}
  Solución: ${improvement.solution}
  Afecta:   ${improvement.affects}
  Archivos: ${improvement.files.join(', ')}

REGLAS DURAS (nunca romper):
1. 1 coleccion.php?id=N = 1 edition_key
2. País ES siempre en edition_key (sufijo …-es)
3. cluster_key tier-0 lmc: "lmc:{cole}:{kind}:{vol}"
4. Enforcer idempotente: 2× → resultado byte-idéntico
5. validate_corpus.py: 0 violaciones duras
6. NO duplicar lógica de merge_cluster()/consolidate_by_cluster()
7. Cambio MÍNIMO — sin refactoring extra

PROCESO:
1. Lee cada archivo antes de editarlo
2. Implementa el cambio
3. Si tocas listadomanga_collections.py, verifica:
   cd ${BASE} && .venv/bin/python -c "
import sys; sys.path.insert(0,'scripts')
import requests, wikis.listadomanga_collections as L
s = requests.Session(); s.headers['User-Agent'] = 'mw/0.2'
items = list(L.fetch_collection(1606, s))
print(f'OK — {len(items)} items cole 1606')
"
4. Corre tests: cd ${BASE} && .venv/bin/python -m pytest tests/test_extraction.py -q 2>&1 | tail -10
5. Actualiza ${BASE}/docs/scraper/sources/listadomanga.md:
   - §8 si es bug resuelto (asigna siguiente número de gotcha disponible)
   - §9 si es limitación nueva conocida
   - La sección que corresponda si es otro tipo de cambio

Reporta: archivos tocados, qué líneas cambiaron, resultado de tests.
`.trim(),
    { label: `impl-${improvement.title.slice(0, 25)}`, phase: 'Implementación', model: 'sonnet' }
  )
)

// Gate final: SOLO reporta PASS/FAIL + evidencia (hallazgo F11.3). El
// verificador ya NO diagnostica ni corrige nada por su cuenta — si hay
// violaciones duras o tests rotos, el workflow retorna FAIL con la
// evidencia y la corrección es un paso explícito posterior (fuera de este
// gate), no algo que el propio gate haga sin dejar rastro.
const finalCheck = await agent(`
Verifica el estado final del corpus tras todos los cambios implementados. NO
corrijas nada — este paso es SOLO de verificación/reporte.

Ejecuta en ${BASE}, en orden:
1. .venv/bin/python -m pytest tests/test_extraction.py -q 2>&1 | tail -20
2. .venv/bin/python scripts/validate_corpus.py 2>&1 | tail -30

Reporta:
- status: "PASS" si los tests pasaron Y el validador NO reportó violaciones
  ERROR; "FAIL" en cualquier otro caso.
- tests_output: el output relevante del comando 1 (verbatim).
- validator_output: el output relevante del comando 2 (verbatim).
- violations: lista de violaciones ERROR del validador o tests que fallaron
  (vacía si status=PASS).
`.trim(),
  { label: 'verificacion-final', phase: 'Implementación', schema: S_FINAL_CHECK, model: 'sonnet' }
)

await cleanupCheckpoint()

return {
  improvements_implemented: synthesis.critical.length,
  deferred: synthesis.medium.length + synthesis.low.length,
  critical_titles: synthesis.critical.map(i => i.title),
  medium_titles: synthesis.medium.map(i => i.title),
  chrome_pages_inspected: totalPagesInspected,
  final_check: finalCheck,
  final_check_status: finalCheck.status,
}
