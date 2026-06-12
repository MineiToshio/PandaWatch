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
    t2 = d.get('tier2_results') or []
    t3 = d.get('tier3_results') or []
    print('PROGRESS_FOUND')
    print(f\"  Tier 1: {'✅ completado' if d.get('tier1_done') else '⏳ pendiente'}\")
    print(f\"  Tier 2: {'✅ ' + str(len(t2)) + ' items guardados' if d.get('has_tier2') else '⏳ pendiente'}\")
    print(f\"  Tier 3: {'✅ ' + str(len(t3)) + ' items guardados' if d.get('has_tier3') else '⏳ pendiente'}\")
"
```

- **Si no existe** (`NO_PROGRESS`) → proceder directamente, sin preguntar nada.
- **Si existe** (`PROGRESS_FOUND`) → mostrar el estado al usuario y preguntar:
  - **"¿Continuar desde donde quedó?"** → usar `args: { resume_progress: true }`
  - **"¿Empezar de cero?"** → `rm data/standardize-progress.json` y correr sin ese arg

**Regla**: solo debe existir UN `data/standardize-progress.json` en todo el proyecto. Si el usuario pide empezar de cero, borrar el existente antes de invocar el workflow.

### Invocar el workflow

Para batches de **30+ items**, usar el workflow guardado:

```javascript
// Continuar desde progreso guardado:
Workflow({ name: 'watch-standardize-catalog', args: { resume_progress: true } })
Workflow({ name: 'watch-standardize-catalog', args: { limit: 100, resume_progress: true } })

// Empezar de cero (o sin progreso previo):
Workflow({ name: 'watch-standardize-catalog' })
Workflow({ name: 'watch-standardize-catalog', args: { limit: 100 } })
Workflow({ name: 'watch-standardize-catalog', args: { limit: 100, force_all: true } })
```

El workflow guarda checkpoints automáticamente en `data/standardize-progress.json` después de
cada fase LLM (Tier 1, Tier 2, Tier 3). Al finalizar exitosamente, elimina el archivo.
Si el workflow se interrumpe a mitad, el progreso queda guardado para retomar.

The workflow automates the entire pipeline: audit → Tier 1 auto-standardize → Tier 2
validation → Tier 3 derivation → merge + dedup + slugs + translation. Schema-validated
output eliminates truncated URLs and session-limit data loss.

For **< 30 items**, process inline using the manual steps below.

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
`/tmp/manga-standardize-run/tier{1,2,3}.json`. Cada proyección Tier 2/3 trae
`proposed_*`, `existing_edition_key` (si el item ya tiene edición asignada) y
`known_edition_keys` (keys YA existentes en el corpus para esa serie — para
REUSAR, no acuñar variantes).

```bash
.venv/bin/python scripts/standardize_audit.py            # [--limit N] [--force-all]
```

Los items con `approved_at` (golden records) NUNCA entran al pending set.

If `PENDING = 0` → report "nothing to standardize" and stop.

If `Pendientes < 15` → process ALL tiers inline (no subagents needed).

If `Pendientes >= 15` → use the tiered workflow below.

## Step 2 — Auto-standardize Tier 1 (deterministic, no LLM)

Tier 1 items have high-confidence heuristic assignments. Apply them directly
(la lógica vive en `scripts/standardize_apply.py` — NO embebas una copia):

```bash
.venv/bin/python scripts/standardize_apply.py tier1     # [--force-all]
```

## Step 3 — Partition Tier 2 + 3 into chunks

**CRITICAL** — items that share coleccion/page-id MUST go in the SAME chunk.

Tier 2 and Tier 3 items get different prompt templates but can share chunks
if they're siblings. Chunk size: **20-30 items** (smaller than before to avoid
session limits — the #1 reliability problem in past runs).

```bash
.venv/bin/python << 'PY'
import json, re
from pathlib import Path
from collections import defaultdict

BASE = Path('/tmp/manga-standardize-run')
CHUNK_SIZE = 25

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
Wave size: 7 subagents max. Chunks are smaller (20-30) so more waves but
each agent finishes faster and never hits session limits.

Each subagent gets this prompt template:

```
Standardize manga catalog entries. Read `/tmp/manga-standardize-run/chunk_<NN>.jsonl` and write `/tmp/manga-standardize-run/result_<NN>.jsonl` with one JSON per input item, SAME ORDER.

## OUTPUT FIELDS:
```json
{"url":"","is_manga":true,"non_manga_reason":"","series_key":"","series_display":"","edition_key":"","edition_display":"","volume":""}
```

**POLÍTICA DE TÍTULOS (dura, 2026-06-12): el `title` NO se toca.** Es el nombre
OFICIAL con que la fuente/editorial publica el producto. NO lo traduzcas, NO lo
renombres a la serie canónica, NO le agregues tipo de edición (Kanzenban/Deluxe/…).
El nombre reconocible vive en `series_display` (canónico) y la búsqueda resuelve
aliases multilingües. NO emitas ningún campo de título.

## TIER-SPECIFIC INSTRUCTIONS

Each input item has a `tier` field (2 or 3).

**Tier 2 items** come with `proposed_*` fields (heuristic assignment). The heuristic
already resolved the series via aliases.yml and assigned a publisher slug. Your job is
to VALIDATE and optionally CORRECT:
- Check if proposed_series_key looks right for this title.
- Check if the edition_slug is the best match (the heuristic might have assigned
  "special" when "collector" or "limited" is more specific).
- If the proposed values look correct, USE THEM (don't re-derive from scratch).
- If something is wrong, fix it using the same rules as Tier 3.

**Tier 3 items** have NO reliable heuristic — derive everything from scratch.

## RULES

### is_manga
- ALL `Global - Mangavariant` items → ALWAYS true. NEVER false.
- Slipcases/box sets/coffrets/cofanetti/steelbox/variant covers/artbooks/fanbooks/magazines → valid.
- Marvel/DC/IDW/Image comics → false unless "manga" in title or known adaptation.
- Figures/statues/plushies/t-shirts/mugs/trading cards/news posts → false.
- Light novels (roman/light-novel/LN URLs) → false (non_manga_reason="light_novel").
- **When in doubt → true.**

### series_key
Lowercase, kebab-case, no diacritics. Cap ~35 chars. Use globally-recognized name.
Pure ASCII (`[a-z0-9-]`) — no raw CJK and no Cyrillic/Greek homoglyphs copied from
sources (gotcha #81); transliterate to romaji. The pipeline re-sanitizes with
`sanitize_key_ascii()`, so non-ASCII keys never reach the corpus anyway.

### edition_key — `{series}-{publisher_slug}-{edition_slug}-{country_slug}`

**NO RE-DERIVES la edición si el item YA tiene `edition_key` asignado** (viene como
`existing_edition_key` en el input). El scraper ya aplicó las reglas duras de agrupación
(coleccion=edición, país, nombre oficial) — está bien. Para esos items tu trabajo es
SOLO: serie canónica + detectar non-manga. El apply del
skill conserva el `edition_key`/`edition_display` existentes (y el `title` SIEMPRE). Sólo derivá la edición
desde cero para items SIN `edition_key` (ej. algunas fuentes que no son listadomanga).
Las reglas de abajo aplican a esos casos.

**REUSO DE KEYS EXISTENTES (gotcha #69)**: si el item trae `known_edition_keys`
(edition_keys YA existentes en el corpus para esa serie), y una matchea el
publisher+tipo+país de este item, USA ESA KEY EXACTA. NUNCA acuñes una key nueva que
difiera de una existente solo en el slug de tipo (special/limited/collector/deluxe) —
eso parte la misma edición en dos páginas.

**TABLA DE TÉRMINOS DE TIPO (DURA, gotcha #69)** — el término del título manda y se
mapea SIEMPRE igual (un post-paso determinístico, `canonicalize_edition_slugs.py`,
re-aplica esta tabla; no la contradigas):
- 限定版 → `limited` · 特装版 / 同梱版 → `special` · 愛蔵版 → `deluxe` · 完全版 → `kanzenban`
- "edición limitada" / "edizione limitata" / "édition limitée" / "limited edition" → `limited`
- "coleccionista" / "collector" → `collector` · "edición de lujo" / "deluxe" → `deluxe`
- Ediciones NOMBRADAS (Maximum, Perfect, Ultimate, Master, Grimorio…) ganan sobre el
  término de tipo: "One Piece Maximum 限定版" → `maximum`.
- **GUARD de nombre de serie**: si la palabra "de edición" es parte del NOMBRE de la
  serie ("Trigun Maximum", "Ultimate Muscle"), NO es tipo de edición — usá la evidencia
  real de edición (o `regular`) para el SLUG. El título no se toca.

**REGLA DE NEGOCIO DURA (gotcha #46): país distinto = edición distinta, SIEMPRE.**
El `edition_key` TERMINA con el código de país de la EDICIÓN (derivado de
editorial/idioma del item, NO de la tienda). Dos mercados NUNCA comparten
edition_key aunque coincidan series+publisher+edición (Panini IT vs Panini ES/MX/BR,
Kazé FR vs DE, etc.). country_slug (allowlist):
"jp", "it", "es", "fr", "de", "us", "vn", "mx", "br", "th", "ar", "tw", "gb", "pt",
"pe", "cl", "kr", "eslatam". Si no sabés el país → "xx".
Ejemplo: Hunter x Hunter variante de Panini España = `hunter-x-hunter-panini-variant-es`;
la de Panini Italia = `hunter-x-hunter-panini-variant-it` (NUNCA el mismo).
NOTA: como el país ya va en el sufijo, NO uses slugs de publisher con país embebido
(usá "panini", NO "panini-es"; "ivrea", NO "ivrea-ar" salvo que sean editoriales
legalmente distintas). El país lo aporta el sufijo.

publisher_slug (allowlist — use literal slug from this list):
"darkhorse", "glenat", "viz", "panini", "norma", "planeta", "ivrea", "ivrea-ar",
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
"crunchyroll", "rakuten".

edition_slug (pick ONE — NEVER compound two together):
"deluxe", "kanzenban", "perfect", "coffret", "boxset", "cofanetto", "variant",
"limited", "collector", "anniversary", "celebration", "color", "maximum", "ultimate",
"master", "library", "integral", "artbook", "fanbook", "guidebook", "magazine",
"steelbox", "slipcase", "prestige", "grimorio", "grimoire", "special", "regular".

**ANTI-COMPOUND RULE**: Choose ONE slug. Never "deluxe-box", "ultimate-variant", etc.
When format-slug (boxset/hardcover/coffret) conflicts with edition-name
(collector/ultimate/limited), choose the edition-name.

**ARTBOOK vs SPECIAL**: If the item has a volume number → `special`/`limited`
(never `artbook`). Only standalone illustration books WITHOUT a volume → `artbook`.
EXCEPCIÓN: si la COLECCIÓN ENTERA es un libro de ilustraciones (su título dice
"Libro de Ilustraciones" / "Illustrations" / "Art Works" / "The Art of" / 画集),
entonces TODOS sus tomos son `artbook` aunque estén numerados (es una serie de
artbooks, no tomos especiales). Ej. FMA cole=524 "Libro de Ilustraciones 1/2".

**listadomanga — REGLA DURA: cada `/coleccion?id=N` es UNA edición = UNA página.**
La MISMA obra en `/coleccion` distintos = ediciones DISTINTAS → NUNCA el mismo
edition_key. Y al revés (gotcha #48): TODOS los tomos de una MISMA `/coleccion`
(regulares, especiales, cofres, variantes) comparten el MISMO edition_key — el de
la edición BASE de la coleccion (la `regular` si existe; si no, la predominante,
ej. Berserk Maximum). NO separes el tomo 34 "Edición Especial" en
`…-special` aparte de los regulares de su coleccion: va en la misma página, con el
mismo edition_key. Lo que distingue al especial-34 del regular-34 es el `cluster_key`
(tier-0 `lmc:{coleccion}:{kind}:{vol}`), NO el edition_key. Un post-paso determinístico
(`unify_coleccion_edition.py`) lo fuerza, pero generá ya el edition_key base. Los
tomos REGULARES con cofre/extras de 1ª edición (description con "regalos / brindes"
o tag `from_extras`) son edición `regular`, el cofre es un bonus.

**`edition_display` = NOMBRE OFICIAL de la edición, SIN traducir (gotcha #49).** NO un
slug genérico traducido ("Special (Norma Editorial)", "Regular"). Nada se traduce:
ni el nombre de la EDICIÓN ni el `title` del tomo — ambos van tal cual. Para items de
listadomanga, el item YA trae el `edition_display` correcto (= título de la coleccion,
ej. "Ataque a los Titanes", "Guardianes de la Noche (Kimetsu no Yaiba)", "Berserk
(Maximum) (Castellano)"): **CONSÉRVALO, no lo regeneres ni lo traduzcas.** Para otras
fuentes, usá el nombre oficial de la edición (no inventes un slug traducido).

CRITICAL — "画集付き" / "イラスト集付き" = artbook INCLUDED AS BONUS, not the product.
A Japanese title like "宇宙兄弟(39) 画集付き特装版" / "暁のヨナ イラスト集付き特装版 47"
is a regular VOLUME (note the number) that ships WITH a mini art booklet. It is NOT an
artbook. Rule:
- 画集/イラスト集/アートワーク immediately followed by 付き/付/つき/同梱 (= "with/included")
  → the artbook is a BONUS → edition = `special` (特装版/同梱版) or `limited` (限定版),
  product_type = `manga`.
  e.g. "宇宙兄弟(39) 画集付き特装版" → edition_key `space-brothers-kodansha-special`
  (el title queda tal cual, en japonés).
- 画集/イラスト集 as the standalone product, NO 付き (e.g. "笠井あゆみ画集 麗人") → real
  `artbook`. Same logic for "ファンブック付き" (fanbook bonus) vs a standalone "Visual Fanbook".
(detect_signals/derive_product_type now demote this automatically, but assign the
edition_key/title correctly here too — those are curated fields.)

### volume
String. Digits only. "1", "100", "1-3" for sets, "" if absent.

## EXECUTION
1. Read input. 2. Process EVERY item. 3. Output line count MUST equal input. 4. Report totals.
CRITICAL: Same series/publisher → same keys consistently.
```

## Step 5 — Verify integrity

```bash
.venv/bin/python << 'PY'
import json
from pathlib import Path
base = Path('/tmp/manga-standardize-run')
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
heurística como fallback de keys vacías (sin keys usables → el item queda
PENDIENTE, nunca huérfano), manda los non-manga a la blacklist, corrige
outliers de serie por /coleccion, recomputa cluster_key y consolida:

```bash
.venv/bin/python scripts/standardize_apply.py merge     # [--force-all]
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
rm -rf /tmp/manga-standardize-run
```

Report to the user:
- Tier 1 auto-standardized (0 tokens).
- Tier 2+3 processed by LLM.
- Distinct new series_keys.
- Non-manga removed.
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
- **Don't use chunks larger than 30** — session limits cause data loss with big chunks.
- **Don't skip the `canonical_series_key` step in merge.**
- **Don't skip Step 9 (translation)** for small runs.
- **Don't truncate `/tmp/manga-standardize-run/` until merge is confirmed.**

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
