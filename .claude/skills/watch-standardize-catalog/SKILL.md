---
name: watch-standardize-catalog
description: Standardize new manga items in data/items.jsonl that haven't been processed yet (missing standardized_at field). Uses a 3-tier approach — Tier 1 items are auto-standardized deterministically (no LLM), Tier 2 get lightweight LLM validation, and only Tier 3 (unknown series, CJK) get full LLM derivation. Delegates Tier 2/3 to parallel subagents in small batches (~20 items). Skips items already standardized (incremental). Trigger manually after each scrape or weekly.
argument-hint: "[--limit N] [--force-all]"
---

# Standardize catalog

You are processing manga items in `data/items.jsonl` that haven't been standardized yet. The **scraper** (`scripts/manga_watch.py`) does a heuristic assignment when items are first saved — including `confidence_tier` (1/2/3) that indicates how much LLM help is needed. Items are **not yet marked** with `standardized_at`. This skill is the **verification + correction pass**.

## Preferred method: Workflow script

### Paso 0 — Verificar progreso anterior

Antes de invocar el workflow, verificar si existe `data/standardize-progress.json`:

```bash
python3 -c "
import json, os
if not os.path.exists('data/standardize-progress.json'):
    print('NO_PROGRESS')
else:
    d = json.load(open('data/standardize-progress.json'))
    print('PROGRESS_FOUND')
    print(f\"  Tier 1: {'✅ completado' if d.get('tier1_done') else '⏳ pendiente'}\")
    print('  Tier 2/3: se resumen solos detectando result_t{2,3}_*.jsonl en data/standardize-run/')
"
```

- **Si no existe** (`NO_PROGRESS`) → proceder directamente, sin preguntar nada.
- **Si existe** (`PROGRESS_FOUND`) → mostrar el estado al usuario y preguntar:
  - **"¿Continuar desde donde quedó?"** → usar `args: { resume_progress: true }`
  - **"¿Empezar de cero?"** → `rm data/standardize-progress.json` y correr sin ese arg

**Regla**: solo debe existir UN `data/standardize-progress.json` en todo el proyecto. Si el usuario pide empezar de cero, borrar el existente antes de invocar el workflow.

> **Checkpoint mínimo (2026-07-08, hallazgo F3)**: `data/standardize-progress.json`
> guarda SOLO flags (`tier1_done`) — nunca los resultados LLM completos. El run dir
> `data/standardize-run/` es persistente (ya no vive en `/tmp`), así que Tier 2/3 se
> resumen SOLOS: en modo `resume_progress`, el workflow lista qué `result_t{2,3}_NN.jsonl`
> ya existen en disco y solo relanza los chunks que faltan — nunca reprocesa un chunk ya
> resuelto ni duplica sus resultados en el checkpoint.

### Invocar el workflow

**Umbral único (regla): < 15 pendientes → procesar inline** (sin subagentes,
pasos manuales de abajo). **≥ 15 pendientes → el workflow guardado es el camino
PREFERIDO.** El camino manual con subagentes (Steps 3-10 de abajo) es el
**fallback** para ≥ 15 items cuando el tool `Workflow` no está disponible — hace
lo mismo que el workflow pero orquestado a mano.

Para batches de **≥ 15 items**, usar el workflow guardado:

```javascript
// Continuar desde progreso guardado:
Workflow({ name: 'watch-standardize-catalog', args: { resume_progress: true } })
Workflow({ name: 'watch-standardize-catalog', args: { limit: 100, resume_progress: true } })

// Empezar de cero (o sin progreso previo):
Workflow({ name: 'watch-standardize-catalog' })
Workflow({ name: 'watch-standardize-catalog', args: { limit: 100 } })
Workflow({ name: 'watch-standardize-catalog', args: { limit: 100, force_all: true } })
```

El workflow guarda un checkpoint chico en `data/standardize-progress.json` después de
Tier 1 (solo el flag `tier1_done`). Al finalizar exitosamente, borra ese archivo Y
`data/standardize-run/`. Si se interrumpe a mitad, ambos quedan — Tier 1 se saltea si
ya corrió, y Tier 2/3 retoman leyendo qué chunks ya tienen `result_*.jsonl` en
`data/standardize-run/` (nunca reprocesan ni duplican payloads en el checkpoint).

The workflow automates the entire pipeline: audit → Tier 1 auto-standardize → Tier 2
validation → Tier 3 derivation → merge + dedup + slugs + translation. Schema-validated
output eliminates truncated URLs and session-limit data loss.

For **< 15 items**, process inline using the manual steps below.

## Architecture: 3-tier processing

The scraper's `derive_series_metadata()` now assigns a `confidence_tier`:

- **Tier 1** (~30%): Series resolved in `series_aliases.yml`, publisher known, edition unambiguous. **Auto-standardized deterministically — no LLM needed.**
- **Tier 2** (~9%): Series resolved but edition ambiguous (lore/special/regular) or publisher unknown. **Lightweight LLM validation** (~100 tokens/item).
- **Tier 3** (~37%): Series NOT in aliases (CJK titles, new series). **Full LLM derivation** (~1200 tokens/item).
- **Empty** (~24%): Heuristic punted entirely (too short, all digits). Treated as Tier 3.

This saves ~38% of tokens compared to sending everything through full LLM.

## Incremental — process only what's pending

Each standardized item carries a `standardized_at` ISO timestamp. The skill **only processes items missing this field** (or, with `--force-all`, every item).

## Step 1 — Audit + tier distribution

La lógica de auditoría/tiering vive en `scripts/standardize_audit.py` (fuente
única — NO embebas una copia acá). Escribe las proyecciones por tier a
`data/standardize-run/tier{1,2,3}.json` — run dir **persistente** (antes vivía
en `/tmp/manga-standardize-run`, volátil ante reboot; 2026-07-08 se movió a
`data/`, gitignored). Cada proyección Tier 2/3 trae `proposed_*`,
`existing_edition_key` (si el item ya tiene edición asignada) y
`known_edition_keys` (keys YA existentes en el corpus para esa serie — para
REUSAR, no acuñar variantes).

Además escribe `data/standardize-run/summary.json` — el **contrato de
conteos** (`{total, pending, tier1, tier2, tier3, exhausted}`). Es la fuente
de verdad de PENDING/TIER1/TIER2/TIER3: leelo (o pedile a un subagente que lo
lea con schema) en vez de parsear el stdout con regex.

```bash
.venv/bin/python scripts/standardize_audit.py            # [--limit N] [--force-all]
```

Los items con `approved_at` (golden records) NUNCA entran al pending set.

If `PENDING = 0` (ver `summary.json`) → report "nothing to standardize" and stop.

If `Pendientes < 15` → process ALL tiers inline (no subagents needed).

If `Pendientes >= 15` → el workflow guardado es el camino PREFERIDO; los Steps
3-10 de abajo (subagentes) son el fallback si el tool `Workflow` no está
disponible. (Mismo umbral que la intro — una sola regla, 15.)

## Step 2 — Auto-standardize Tier 1 (deterministic, no LLM)

Tier 1 items have high-confidence heuristic assignments. Apply them directly
(la lógica vive en `scripts/standardize_apply.py` — NO embebas una copia).
**`standardize_apply.py` y `standardize_audit.py` declaran el MISMO
`DEFAULT_BASE = data/standardize-run`; igual se pasa `--base` explícito por
robustez, para garantizar que ambos scripts apunten al mismo run dir:**

```bash
.venv/bin/python scripts/standardize_apply.py tier1 --base data/standardize-run     # [--force-all]
```

## Step 3 — Partition Tier 2 + 3 into chunks

**CRITICAL — REGLA DE AGRUPACIÓN (misma que usa el chunker del workflow):**
items que comparten coleccion/page-id (`group_key`) DEBEN ir en el MISMO chunk.
`group_key` = `lmc:{id}` para URLs `listadomanga.es/coleccion.php?id=N`; para el
resto, la URL base sin query (`url:{base}`). Los hermanos SIEMPRE juntos; los
chunks pueden quedar desparejos.

Tier 2 y Tier 3 usan prompts distintos pero pueden compartir chunk si son
hermanos. **Tamaños de chunk canónicos: 20 (Tier 2) / 15 (Tier 3)** — los
MISMOS que usa el workflow (que particiona cada tier por separado). Como el
camino manual empaqueta chunks MIXTOS T2+T3 de hermanos, los limita a **20**
(el mayor de los dos; chunks más chicos evitan los límites de sesión, el
problema de fiabilidad #1 de corridas pasadas).

```bash
.venv/bin/python << 'PY'
import json, re
from pathlib import Path
from collections import defaultdict

BASE = Path('data/standardize-run')
CHUNK_SIZE = 20   # canónico: 20 (T2) / 15 (T3); chunks mixtos → cap 20

# Las proyecciones YA vienen completas del audit (proposed_*, tier,
# existing_edition_key, known_edition_keys) — acá solo se particiona.
remaining = (json.load(open(BASE / 'tier2.json'))
             + json.load(open(BASE / 'tier3.json')))

def group_key(p):
    url = p.get('url','')
    m = re.search(r'listadomanga\.es/coleccion\.php\?id=(\d+)', url)
    if m: return f'lmc:{m.group(1)}'
    m = re.match(r'^(https?://[^?#]+)', url)
    return f'url:{m.group(1) if m else url}'

groups = defaultdict(list)
for p in remaining:
    groups[group_key(p)].append(p)

# Pack into chunks respecting groups
for old in BASE.glob('chunk_*.jsonl'): old.unlink()
for old in BASE.glob('result_*.jsonl'): old.unlink()

chunks = []
current = []
for group in sorted(groups.values(), key=len, reverse=True):
    if len(group) > CHUNK_SIZE:
        if current: chunks.append(current); current = []
        chunks.append(group)
        continue
    if len(current) + len(group) > CHUNK_SIZE and current:
        chunks.append(current); current = []
    current.extend(group)
if current: chunks.append(current)

for idx, chunk in enumerate(chunks):
    p = BASE / f'chunk_{idx:02d}.jsonl'
    p.write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in chunk))

print(f'Chunks: {len(chunks)}, sizes: {sorted([len(c) for c in chunks], reverse=True)[:5]}...')
print(f'Total items for LLM: {sum(len(c) for c in chunks)}')
PY
```

## Step 4 — Spawn subagents in parallel

For each chunk, spawn a `general-purpose` subagent **in the background**.
Wave size: 7 subagents max. Chunks are small (≤20, ver Step 3) so more waves but
each agent finishes faster and never hits session limits.

Each subagent gets this prompt template. **Las reglas de negocio (edition_key,
publisher/país/tipo de edición, 画集付き, coleccion=edición, allowlists…) NO
van acá — viven en `.claude/skills/watch-standardize-catalog/prompt-rules.md`
(fuente única, auditoría 2026-07-08 hallazgo F7: esa regla existía SOLO acá y
0 veces en el workflow — drift confirmado). El subagente lee ese archivo con
su tool Read antes de procesar; no le pegues las reglas al prompt.**

```
Antes de procesar, leé COMPLETO .claude/skills/watch-standardize-catalog/prompt-rules.md
— son las reglas OBLIGATORIAS de negocio (edition_key, publisher/país/tipo de
edición, 画集付き, coleccion=edición, allowlists…). Aplicalas literalmente, no
las reinterpretes ni las resumas de memoria.

Standardize manga catalog entries. Read `data/standardize-run/chunk_<NN>.jsonl` and write `data/standardize-run/result_<NN>.jsonl` with one JSON per input item, SAME ORDER.

## OUTPUT FIELDS:
```json
{"url":"","is_manga":true,"non_manga_reason":"","series_key":"","series_display":"","edition_key":"","edition_display":"","volume":""}
```

## TIER-SPECIFIC INSTRUCTIONS

Each input item has a `tier` field (2 or 3). Ver "Reglas específicas por
tier" en `prompt-rules.md` para el detalle de qué hacer en cada caso
(Tier 2 = validar `proposed_*`; Tier 3 = derivar desde cero).

## EXECUTION
1. Read input. 2. Process EVERY item. 3. Output line count MUST equal input. 4. Report totals.
CRITICAL: Same series/publisher → same keys consistently.
```

## Step 5 — Verify integrity

```bash
.venv/bin/python << 'PY'
import json
from pathlib import Path
base = Path('data/standardize-run')
missing_items = []
for cf in sorted(base.glob('chunk_*.jsonl')):
    n = cf.stem.replace('chunk_', '')
    rf = base / f'result_{n}.jsonl'
    chunk_urls = {}
    for line in open(cf):
        line = line.strip()
        if not line: continue
        try:
            it = json.loads(line)
            chunk_urls[it['url']] = it
        except: pass

    if not rf.exists():
        for url, it in chunk_urls.items():
            missing_items.append((n, it))
        continue

    result_urls = set()
    prefix_map = {url[:80]: url for url in chunk_urls}
    out_lines = []
    patched = 0
    for line in open(rf):
        line = line.strip()
        if not line: continue
        try: r = json.loads(line)
        except: continue
        if r.get('url') not in chunk_urls:
            match = prefix_map.get(r.get('url','')[:80])
            if match:
                r['url'] = match; patched += 1
            else: continue
        result_urls.add(r['url'])
        out_lines.append(json.dumps(r, ensure_ascii=False))

    if patched > 0:
        rf.write_text('\n'.join(out_lines) + '\n')
        print(f"chunk {n}: patched {patched} truncated URLs")

    for url in set(chunk_urls) - result_urls:
        missing_items.append((n, chunk_urls[url]))

print(f"\nMissing items: {len(missing_items)}")
if missing_items:
    with open(base / 'inline_retry.jsonl', 'w') as fh:
        for n, it in missing_items:
            fh.write(json.dumps({'chunk': n, 'item': it}, ensure_ascii=False) + '\n')
    print(f"Saved to inline_retry.jsonl — process inline before merge.")
PY
```

If missing > 0, process inline (≤10) or spawn a retry subagent (>10).

## Step 6 — Merge results + apply

La lógica de merge vive en `scripts/standardize_apply.py` (fuente única — NO
embebas una copia acá). Lee los `result_*.jsonl`, aplica los veredictos
preservando el `edition_key` existente (el LLM no re-agrupa), usa la propuesta
heurística como fallback de keys vacías, corrige outliers de serie por
/coleccion, recomputa cluster_key y consolida:

- **Keys vacías → PENDIENTE, nunca huérfano.** Sin keys usables, el item queda sin
  `standardized_at` y se reintenta en la próxima corrida; se le suma 1 a
  `standardize_attempts`. Al llegar a `MAX_STANDARDIZE_ATTEMPTS=3` (contado en
  `standardize_audit.py` la próxima vez que se audite), el item se EXCLUYE de las
  proyecciones Tier 2/3 (no gasta más LLM en loop) y se manda a
  `data/unmapped_series.jsonl` (reason `standardize_exhausted`) para curación manual.
- **`is_manga=false` YA NO EXPULSA a `non_manga_blacklist.jsonl` (2026-07-07).** El
  veredicto del LLM NO borra la fila ni la manda a blacklist — el item queda PENDIENTE
  (sin `standardized_at`) y se registra en `data/unmapped_series.jsonl` (reason
  `llm_non_manga`) para curación manual. Son los gates DETERMINISTAS del pipeline
  (`filter_non_manga`/`filter_collectible`, Fase 3 del scrape) los que deciden la
  expulsión real en la próxima corrida — no el veredicto del LLM directamente (un falso
  negativo del LLM en un título ambiguo/CJK ya no puede borrar un item real del
  corpus). **Excepción dura**: un item con source Mangavariant NUNCA se expulsa — si el
  LLM lo marca `is_manga=false`, se IGNORA el veredicto (WARN en consola) y sigue el
  flujo normal de estandarización.
- **`product_type` siempre del enum** (manga/artbook/fanbook/guidebook/boxset/novel/
  magazine/audiobook). Si el LLM devuelve un edition-kind (special/deluxe/variant/
  limited/collector — eso va en `edition_key`, nunca en `product_type`), se descarta y
  se re-deriva con `derive_product_type()` (importada de `manga_watch.py`, fuente
  única).

```bash
.venv/bin/python scripts/standardize_apply.py merge --base data/standardize-run     # [--force-all]
```

El viejo enforcement embebido `[LMC-EDITIONS]` ya NO va acá: lo cubre el
Step 6b (enforcer determinístico).

## Step 6b — Enforce REGLAS DE AGRUPACIÓN (determinístico, AUTORIDAD FINAL)

**El LLM NO es la autoridad sobre la agrupación.** El skill puede haber re-derivado
`edition_key`/`edition_display` vía LLM; este paso RE-APLICA determinísticamente las
reglas duras y sobreescribe lo que haya quedado mal — es la fuente de verdad de:
- **#49** `edition_display` = nombre OFICIAL de la coleccion (sin traducir; se recupera
  del `description`, sin red).
- **#48** una `/coleccion` = UNA edición (unify).
- **#46** país = edición (sufijo de país en `edition_key`).
- **#69** slug de TIPO de edición = término del título (canonicalize_edition_slugs:
  限定版→limited, 特装版→special… — corrige la inconsistencia del LLM en fuentes no-lmc).
- **#70** series_key sin variantes mecánicas (merge_duplicate_series: "the-",
  apóstrofes, vocales largas romaji) + publisher unificado (normalize_edition_publishers).
- cluster_key tier-0 lmc, desambiguación de títulos, consolidate, dedup de portadas, slugs.

Corré SIEMPRE esto al final (reemplaza el viejo enforcement embebido `[LMC-EDITIONS]`
y el Step 8 de slugs — ambos quedan cubiertos acá). Idempotente.

```bash
.venv/bin/python scripts/retrofit/enforce_listadomanga_rules.py
```

## Step 7 — Run tests

```bash
.venv/bin/python -m pytest tests/test_extraction.py -q
```

## Step 7b — Validar el corpus (gate DURO — BLOQUEANTE)

Corré SIEMPRE el validador de invariantes DESPUÉS del merge/enforce. Es la
misma red que el gate del scrape (`validate_corpus.py`, PHASE 4), pero ese
backstop puede tardar días/meses en correr — y `serve.py` sirve `items.jsonl`
EN VIVO sin pasar por el build. Por eso el skill valida en el mismo turn.

```bash
.venv/bin/python scripts/validate_corpus.py
```

**Si el exit code es != 0 → NO des la corrida por cerrada.** Hay violaciones de
invariantes (exit 2 = violaciones DURAS). Investigá y arreglá ANTES de seguir
con slugs/traducción o de anunciar éxito; no borres el run dir todavía
(necesario para diagnóstico/resume). El workflow guardado hace exactamente esto
y propaga el exit code al return final (`completed_with_violations`).

## Step 8 — Generate slugs

> Nota: el enforcer del Step 6b ya corre `generate_slugs.py` internamente —
> este paso es idempotente y sirve solo como red de seguridad si saltaste 6b.

```bash
.venv/bin/python scripts/retrofit/generate_slugs.py --only-missing --verbose
```

## Step 9 — Translate new descriptions

```bash
.venv/bin/python scripts/retrofit/translate_descriptions.py --workers 4
```

## Step 10 — Cleanup + report

```bash
rm -rf data/standardize-run
```

Report to the user:
- Tier 1 auto-standardized (0 tokens).
- Tier 2+3 processed by LLM.
- Distinct new series_keys.
- Non-manga flagged by the LLM (pending + registered to `unmapped_series.jsonl`,
  reason `llm_non_manga` — NOT removed from the corpus; see the note in Step 6).
- Items with `standardize_attempts` reaching the cap (escalated to
  `unmapped_series.jsonl`, reason `standardize_exhausted`).
- Items deduplicated.
- Items translated.
- Suggest running `/watch-enrich-series-aliases` if new series_keys appeared.

## Anti-patterns

- **NEVER write to items with `approved_at`** (golden records). The owner
  approved them from the dashboard — they are frozen. Even `--force-all` must
  NOT touch them: they stay out of the pending set. You MAY read them as
  reference examples of correct data, but never overwrite their fields.
- **Don't process items that already have `standardized_at`** unless `--force-all`.
- **Don't skip Step 2 (Tier 1 auto-standardize)** — it saves ~30% of tokens.
- **Don't use chunks larger than 20** — session limits cause data loss with big chunks (canónico: 20 T2 / 15 T3).
- **Don't skip the `canonical_series_key` step in merge.**
- **Don't skip Step 9 (translation)** for small runs.
- **Don't truncate `data/standardize-run/` until merge is confirmed.**

## Force-rerun the whole catalog

```bash
.venv/bin/python -c "from scripts.manga_watch import backup_and_rotate; from pathlib import Path; backup_and_rotate(Path('data/items.jsonl'), 'standardize-force')"
.venv/bin/python -c "
import json
items = [json.loads(l) for l in open('data/items.jsonl')]
for it in items: it.pop('standardized_at', None)
with open('data/items.jsonl','w',encoding='utf-8') as fh:
    for it in items: fh.write(json.dumps(it, ensure_ascii=False) + '\n')
print(f'Cleared standardized_at on {len(items)} items')
"
```

Then re-run the skill normally.

## When to invoke

- After each `manga_watch.py` scrape (new items will have empty `standardized_at`).
- Before publishing a fresh build of the dashboard.
- Weekly as part of overnight maintenance.
- When you notice messy titles, missing series_keys, or non-manga items in the dashboard.
