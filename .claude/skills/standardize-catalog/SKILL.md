---
name: standardize-catalog
description: Standardize new manga items in data/items.jsonl that haven't been processed yet (missing standardized_at field). Delegates to parallel subagents in batches of ~150-200 to assign canonical series_key/edition_key, rewrite titles to the standard format ("Berserk Deluxe 1"), extract volume numbers, identify non-manga items (move to data/non_manga_blacklist.jsonl), and dedup by (series_key, edition_key, volume). Skips items already standardized (incremental). Trigger manually after each scrape or weekly.
---

# Standardize catalog

You are processing manga items in `data/items.jsonl` that haven't been standardized yet. The **scraper** (`scripts/manga_watch.py`) does a rough heuristic assignment when items are first saved — but those items are **not yet marked** with `standardized_at`. This skill is the **verification + correction pass**: it re-derives the schema fields from scratch via LLM, fixes whatever the scraper got wrong, and marks each item with `standardized_at`.

**TRUST NOTHING the scraper assigned.** The scraper uses regex-based heuristics that may produce wrong `series_key` (e.g. "atomic-robo-5" when the "5" is the volume), wrong publisher slug, or wrong edition slug. Your job is to re-derive everything correctly. The user explicitly said: "no importa si por ahí hay algún error, ya después cuando pasa este skill ahí podemos mejorarlo."

## Incremental — process only what's pending

Each standardized item carries a `standardized_at` ISO timestamp. The skill **only processes items missing this field** (or, with `--force-all`, every item).

## Step 1 — Audit what's pending

```bash
.venv/bin/python -c "
import json
items = [json.loads(l) for l in open('data/items.jsonl')]
pending = [it for it in items if not it.get('standardized_at')]
print(f'Total items: {len(items)}')
print(f'Pendientes (sin standardized_at): {len(pending)}')
if pending:
    print(f'\nMuestra de 5 pendientes:')
    for it in pending[:5]:
        print(f'  - {it.get(\"title\",\"\")[:60]}  ← {it.get(\"source\",\"\")[:30]}')
"
```

If `Pendientes = 0` → report "nothing to standardize" and stop.

If `Pendientes < 30` → process them inline (no need for subagents, you can do them yourself in this conversation).

If `Pendientes >= 30` → use the parallel subagent workflow below.

## Step 2 — Partition into chunks (group siblings together)

**CRITICAL** — items que comparten coleccion/page-id DEBEN ir al MISMO chunk.
Razón: sin agrupamiento, el LLM clasifica cada item aislado y produce
edition_keys inconsistentes entre hermanos (Witch Hat vol 3 → "hardcover"
mientras vols 1/2 → "grimorio"). Con agrupamiento, el LLM ve los hermanos
y aplica consistencia.

Tipos de agrupamiento (en orden de prioridad):
1. **Listadomanga collections**: `coleccion.php?id=N` → un id = un grupo.
2. **URL base**: items con misma path-base (ignorando query) → un grupo.
3. **Resto**: distribuidos sin agrupar (cada item es su propio grupo).

```bash
.venv/bin/python << 'PY'
import json, re
from pathlib import Path
from collections import defaultdict

items = [json.loads(l) for l in open('data/items.jsonl')]
pending = [it for it in items if not it.get('standardized_at')]

CHUNK_SIZE = 150

def project(it):
    return {
        'url': it.get('url',''),
        'title': it.get('title',''),
        'title_original': it.get('title_original',''),
        'source': it.get('source',''),
        'publisher': it.get('publisher',''),
        'country': it.get('country',''),
        'language': it.get('language',''),
        'isbn': it.get('isbn',''),
        'signal_types': it.get('signal_types', []),
        # Hint del scraper para que el LLM tenga punto de partida + contexto
        # de la colección (clave para detectar nombres de edición específicos
        # como "Edición Grimorio" en vez de slug genérico "hardcover").
        'description_excerpt': (it.get('description','') or '')[:200],
        'scraper_series_key': it.get('series_key',''),
        'scraper_edition_key': it.get('edition_key',''),
    }

def group_key(it):
    """Devuelve la clave de grupo: items del mismo grupo van al mismo chunk."""
    url = it.get('url','')
    # 1. Listadomanga collections: coleccion.php?id=N
    m = re.search(r'listadomanga\.es/coleccion\.php\?id=(\d+)', url)
    if m: return f'lmc:{m.group(1)}'
    # 2. URL base (sin query): items que comparten path completo
    m = re.match(r'^(https?://[^?#]+)', url)
    base = m.group(1) if m else url
    return f'url:{base}'

# Agrupar pending items
groups = defaultdict(list)
for it in pending:
    groups[group_key(it)].append(it)

print(f"Grupos detectados: {len(groups)}")
big_groups = [(k, len(v)) for k, v in groups.items() if len(v) >= 5]
print(f"Grupos con ≥5 items: {len(big_groups)}")

# Empaquetar en chunks respetando los grupos (un grupo NUNCA se parte)
base = Path('/tmp/manga-standardize-run')
base.mkdir(parents=True, exist_ok=True)
for old in base.glob('chunk_*.jsonl'): old.unlink()
for old in base.glob('result_*.jsonl'): old.unlink()

chunks = []
current_chunk = []
current_size = 0
# Ordenar grupos: primero los grandes (para que vayan juntos), luego los chicos
sorted_groups = sorted(groups.values(), key=len, reverse=True)
for group in sorted_groups:
    if len(group) > CHUNK_SIZE:
        # Grupo gigante: ocupa su propio chunk (puede sobrepasar CHUNK_SIZE)
        if current_chunk:
            chunks.append(current_chunk); current_chunk = []; current_size = 0
        chunks.append(group)
        continue
    if current_size + len(group) > CHUNK_SIZE and current_chunk:
        chunks.append(current_chunk); current_chunk = []; current_size = 0
    current_chunk.extend(group)
    current_size += len(group)
if current_chunk:
    chunks.append(current_chunk)

for idx, chunk in enumerate(chunks):
    p = base / f'chunk_{idx:02d}.jsonl'
    p.write_text('\n'.join(json.dumps(project(it), ensure_ascii=False) for it in chunk))

print(f'Chunks creados: {len(chunks)}, sizes: {sorted([len(c) for c in chunks], reverse=True)[:5]}...')
print(f'Total items: {sum(len(c) for c in chunks)} (esperado {len(pending)})')
PY
```

## Step 3 — Spawn subagents in parallel waves

For each chunk, spawn a `general-purpose` subagent **in the background** (`run_in_background: true`). Wave size: 7 subagents in parallel max (to avoid overwhelming the system). If you have >7 chunks, launch the first 7 and the rest will go in subsequent waves as the first ones complete.

Each subagent gets this prompt template (substitute `<NN>` with the chunk number):

```
Standardize manga catalog entries. Read `/tmp/manga-standardize-run/chunk_<NN>.jsonl` and write `/tmp/manga-standardize-run/result_<NN>.jsonl` with one JSON per input item, SAME ORDER.

## OUTPUT FIELDS:
```json
{"url":"","is_manga":true,"non_manga_reason":"","series_key":"","series_display":"","edition_key":"","edition_display":"","volume":"","title_standardized":""}
```

## RULES

### is_manga
- ALL `Global - Mangavariant` items → ALWAYS true. NEVER false.
- Slipcases/box sets/coffrets/cofanetti/steelbox/variant covers (even w/o volume)/artbooks/fanbooks/magazines → valid.
- Marvel/DC/IDW/Image comics → false unless "manga" in title or known adaptation.
- Figures/statues/plushies/t-shirts/mugs/trading cards/news posts → false.
- Light novels (roman/light-novel/LN URLs) → false (non_manga_reason="light_novel").
- **When in doubt → true.**

### series_key
Lowercase, kebab-case, no diacritics. Cap ~35 chars. Use globally-recognized name (EN typically, JP romanji if canonical). Examples: "berserk", "demon-slayer", "spy-x-family", "attack-on-titan", "naruto", "boruto", "jujutsu-kaisen", "one-piece", "fullmetal-alchemist", "20th-century-boys".

### edition_key — `{series}-{publisher_slug}-{edition_slug}`
publisher_slug (allowlist canonical — usar el slug literal de esta lista):
- **Major ES/LatAm/US/FR/IT (single-token)**: "darkhorse", "glenat", "viz",
  "panini", "norma", "planeta", "ivrea", "kana", "pika", "kaze", "kioon",
  "star", "kodansha", "shueisha", "squareenix", "kadokawa", "meian", "ecc",
  "arechi", "delcourt", "tokyopop", "jbc", "devir", "newpop", "kamite",
  "mangaline", "mangadreams", "funside", "milkyway", "dokidoki", "nobinobi",
  "tomodomo", "fandogamia".
- **Multi-token publishers (usar el slug COMPLETO con guion)**: "ivrea-ar"
  (Ivrea Argentina, distinto de "ivrea" España), "kodansha-us" (Kodansha
  USA), "pipoca-nanquim" (Pipoca & Nanquim BR), "kim-dong" (Kim Đồng VN),
  "panini-mx", "panini-es", "panini-ar", "panini-br" (mercados distintos
  cuando hay variantes locales).
- **JP/IT/FR/BR publishers comunes (también canonical, NO usar "unknown")**:
  "kurokawa" (FR Solo Leveling line), "edizionibd" (Edizioni BD IT),
  "dynit" (IT), "jpop" (J-Pop IT), "shogakukan", "akita" (Akita Shoten JP),
  "hakusensha" (JP), "ichijinsha" (JP), "futabasha" (JP), "takeshobo" (JP),
  "tokuma" (JP), "asciimw" (ASCII Media Works JP), "frontier" (Frontier
  Works JP), "yenpress" (US), "carlsen" (DE), "noeve" (Noeve Grafx FR),
  "distrito" (Distrito Manga ES), "001edizioni" (001 Edizioni IT),
  "goen" (Goen IT), "gpmanga" (GP Manga IT), "kbooks" (Kbooks FR import
  imprint), "luckpim" (Luckpim TH), "ipm" (IPM VN), "isan" (Isan TH),
  "nxb" (NXB Trẻ VN), "mpeg" (MPEG/Newpop variants BR), "tokyomangasha"
  (TokyoManga.it IT distributor), "crunchyroll" (Crunchyroll Manga US).
- **Unknown publisher** (no en la lista de arriba) → "unknown" como fallback,
  pero PREFERÍ buscar el slug canónico arriba antes. Si el publisher es
  un retailer (Amazon, Fnac, Cdiscount) NO uses "unknown" — usá el slug
  del publisher real (editor del libro), no del retailer.

edition_slug (most distinctive): "deluxe", "kanzenban", "perfect", "coffret", "boxset", "cofanetto", "variant", "limited", "collector", "anniversary", "celebration", "color", "maximum", "ultimate", "master", "library", "integral", "artbook", "fanbook", "guidebook", "magazine", "steelbox", "slipcase", "prestige", "grimorio", "grimoire", "regular", "special", "taniguchi" (línea Panini IT autor-específica).

**REGLA ANTI-COMPOUND** — IMPORTANTE: elegir **UN SOLO** slug, NO componer dos
edition_slugs juntos. Errores comunes a evitar:
- ❌ `demon-slayer-norma-special-limited` (compone "special" + "limited")
- ✅ `demon-slayer-norma-limited` (elegí el más específico: "Especial Limitada"
  → "limited" porque "limitada" es más distintivo que "especial")
- ❌ `kingdom-meian-coffret-collector` (compone "coffret" + "collector")
- ✅ `kingdom-meian-collector` (formato "coffret" se descarta, "collector" es
  el nombre de la edición)
- ❌ `kill-la-kill-udon-hardcover-limited`
- ✅ `kill-la-kill-udon-limited`

**TRAMPAS OBSERVADAS en corridas pasadas** (no caer en éstas — corregidas
retroactivamente el 2026-05-24, ver gotcha update):
- ❌ `tokyo-ghoul-edizionibd-deluxe-box` → ✅ `tokyo-ghoul-edizionibd-boxset`
  (es una **box** que CONTIENE la edición deluxe — el slug físico-final
  es "boxset", "deluxe" es un atributo del contenido pero NO del producto
  físico que es la box).
- ❌ `blame-panini-ultimate-deluxe` → ✅ `blame-panini-ultimate`
  ("Ultimate Deluxe Edition" es la línea editorial Panini IT "Ultimate";
  el "Deluxe" es genérico de formato y se descarta).
- ❌ `shonan-junai-gumi-meian-collector-box` → ✅ `shonan-junai-gumi-meian-collector`
  ("Collector's Box" — collector es el nombre de la edición, box es formato
  físico genérico — collector gana).
- ❌ `blanca-panini-taniguchi-deluxe` → ✅ `blanca-panini-taniguchi`
  ("Taniguchi Deluxe Collection" es la línea Panini IT autor-específica
  "Taniguchi"; "deluxe" se descarta).
- ❌ `love-clinic-jpop-collection-box` → ✅ `love-clinic-jpop-boxset`
  ("Collection Box" — collection es genérico, el producto físico es boxset).
- ❌ `tokyo-ghoul-edizionibd-deluxe-box` (cualquier `*-X-box` donde X es slug
  ≠ "boxset") → casi siempre `*-boxset`.
- ❌ `z-mazinger-panini-ultimate-variant` → ✅ `z-mazinger-panini-variant`
  ("Ultimate Variant" — variant es la edición; ultimate es prefijo de la
  línea pero NO se compone).

**Regla general derivada**: si dudás entre dos slugs donde UNO es **formato
físico** (`box`, `boxset`, `hardcover`, `coffret`, `cofanetto`, `kanzenban`,
`deluxe`, `slipcase`, `steelbox`) y el OTRO es **nombre de edición/colección**
(`collector`, `ultimate`, `taniguchi`, `master`, `maximum`, `integral`,
`grimorio`, `prestige`, `limited`, `anniversary`, `variant`, etc.), elegí el
nombre de edición — el formato físico es metadata implícita.
**Excepción**: si el producto físico ES una box que contiene N tomos (NO un
volumen individual), el slug correcto puede ser `boxset` solo, descartando
el nombre de la edición que contiene (porque hay un edition_key separado
para los tomos individuales de esa edición).

Cuando dudás entre dos slugs:
1. Si UNO es nombre de edición específico (limited/collector/integral/grimorio/
   anniversary/maximum) y el OTRO es formato físico (hardcover/coffret/kanzenban/
   boxset) → elegí el nombre de edición específico.
2. Si AMBOS son nombres de edición (limited vs special) → elegí el MÁS específico:
   - "Especial Limitada" → "limited" (limitada es más específico)
   - "Edición Coleccionista Especial" → "collector" (coleccionista es nombre)
   - "Collector's Variant" → "variant" (variant cover es distintivo)
3. Excepción permitida (compound real): cuando ambos slugs juntos forman un
   nombre de edición conocido, ej. "ultra-collector" (Ultra Collector's Edition),
   "first-print" (First Print). Pero EVITAR a menos que sea inequívoco.

**REGLA DE CONSISTENCIA — IMPORTANTE**:
- Items que comparten **misma URL base** o **misma `coleccion.php?id=N`** son TOMOS de
  la MISMA colección. DEBEN compartir el mismo `series_key` + `publisher_slug`.
  El `edition_slug` también debe ser el mismo a menos que el `title` indique
  edición claramente distinta (e.g., "Variant Cover" vs "Special Edition" vs
  "Box Set"). Si tienes duda → asignar el MISMO `edition_slug` a los hermanos.
- **Preferir nombre de edición ESPECÍFICO sobre slug genérico de formato**.
  Si `description_excerpt` o `title` mencionan un nombre de edición concreto
  (ej. "Edición Grimorio", "Edición Coleccionista", "Maximum Edition", "Edición
  Integral"), usar ese como `edition_slug` ("grimorio", "collector", "maximum",
  "integral") — NO sustituirlo por el slug del formato físico ("hardcover",
  "kanzenban"). Ejemplo: "Atelier of Witch Hat Edición Grimorio nº3" en formato
  cartoné A5 → `edition_slug="grimorio"` (NO "hardcover").
- Si el `scraper_edition_key` viene populated y matchea el patrón esperado,
  usarlo como hint (no obligatorio, pero úsalo si parece razonable).

### edition_display
"{Edition Name} ({Publisher})". Omit parens if unknown publisher.

### volume
String. Digits only. "1", "100", "1-3" for multi-vol sets, "" if absent (artbooks, one-shots, cover-only).

### title_standardized
`{Series Display} {Edition Suffix} {Volume}`. Short, clean. NO year, NO retailer, NO "(Reedición)".

## EXECUTION
1. Read input file with Read tool.
2. **Pre-pass: detectar grupos de hermanos** — items con misma URL base /
   coleccion_id están agrupados consecutivamente en el input (este chunker
   los junta a propósito). Cuando proceses items consecutivos del mismo
   grupo, **fija** el `series_key`, `publisher_slug` y `edition_slug` que
   usaste para el primero del grupo y reúsalo en todos los demás, salvo
   que el title indique edición distinta explícita.
3. Process EVERY item.
4. Output line count MUST equal input line count.
5. Report: total, distinct series_keys, distinct edition_keys, is_manga=false
   count, y **número de "grupos de hermanos" que asignaste consistentemente**.

CRITICAL: Same series/publisher → same keys consistently across the file.
DOUBLE CRITICAL: hermanos de la misma colección (misma URL base) DEBEN
compartir series_key, publisher_slug y (preferentemente) edition_slug.
```

Spawn pattern (you can launch 7 at once in a single message):

```python
# Pseudocode — in actual skill execution, use the Agent tool 7x in parallel
for chunk_num in chunks_to_process:
    Agent(
        subagent_type='general-purpose',
        description=f'Standardize chunk {chunk_num:02d}',
        prompt=<template above with chunk_num substituted>,
        run_in_background=True,
    )
```

Wait for completion notifications, then process the next wave.

## Step 3.5 — Verificar integridad post-spawn (CRÍTICO)

Antes de hacer merge, hay que verificar que cada `result_NN.jsonl`
tiene el **mismo número de URLs** que el `chunk_NN.jsonl` correspondiente
y que las URLs no se truncaron. Trampas observadas (2026-05-24):

1. **Session limits**: subagente hit limit a mitad de chunk y output
   queda short por N items.
2. **URL truncation**: subagente lee URLs largas y las copia al output
   cortadas (típicamente a ~80-100 chars). Detectable por mismatch URL
   entre chunk y result.

Snippet de verificación + auto-recovery:

```bash
.venv/bin/python << 'PY'
import json
from pathlib import Path
base = Path('/tmp/manga-standardize-run')
missing_items = []  # (chunk_n, item_dict) — items que necesitan procesarse inline
for cf in sorted(base.glob('chunk_*.jsonl')):
    n = cf.stem.replace('chunk_', '')
    rf = base / f'result_{n}.jsonl'
    chunk_urls, chunk_items = [], {}
    for line in open(cf):
        line = line.strip()
        if not line: continue
        try:
            it = json.loads(line)
            chunk_urls.append(it['url'])
            chunk_items[it['url']] = it
        except: pass
    chunk_set = set(chunk_urls)

    # If result missing → ALL items go to retry queue
    if not rf.exists():
        for url in chunk_urls:
            missing_items.append((n, chunk_items[url]))
        continue

    result_urls = set()
    out_lines = []
    # FIX URL TRUNCATION: build prefix map for chunk URLs
    prefix_map = {url[:80]: url for url in chunk_urls}
    patched = 0
    for line in open(rf):
        line = line.strip()
        if not line: continue
        try: r = json.loads(line)
        except: continue
        if r.get('url') not in chunk_set:
            # Try prefix match (URL was truncated by subagent)
            match = prefix_map.get(r.get('url','')[:80])
            if match:
                r['url'] = match
                patched += 1
            else:
                continue  # garbage row, drop
        result_urls.add(r['url'])
        out_lines.append(json.dumps(r, ensure_ascii=False))

    # Re-write the result file with patched URLs
    if patched > 0:
        rf.write_text('\n'.join(out_lines) + '\n')
        print(f"chunk {n}: patched {patched} truncated URLs")

    # Queue missing items for inline processing
    for url in chunk_set - result_urls:
        missing_items.append((n, chunk_items[url]))

print(f"\nTotal items requiring inline processing: {len(missing_items)}")
if missing_items:
    print("Sample missing:")
    for n, it in missing_items[:10]:
        print(f"  chunk {n}: {it.get('title','')[:60]}")
    # Save to file for the assistant to process manually
    with open(base / 'inline_retry.jsonl', 'w') as fh:
        for n, it in missing_items:
            fh.write(json.dumps({'chunk': n, 'item': it}, ensure_ascii=False) + '\n')
    print(f"\nSaved to {base / 'inline_retry.jsonl'} for manual processing.")
PY
```

Si `Total items requiring inline processing > 0`, **procesar inline**
ANTES del merge step:
- Si son ≤10 items: el asistente principal genera los 10 records JSON
  directamente y los appendea al respectivo `result_NN.jsonl`.
- Si son >10 items: agruparlos en un nuevo "chunk de retry"
  (`chunk_retry.jsonl`) y spawn un subagente fresh con el mismo prompt
  template. Después agregar el resultado al merge normal.

**NO saltear este paso.** Sin él, items que el subagente perdió quedan
en items.jsonl SIN `standardized_at` y serán re-procesados en la próxima
corrida del skill (gasto innecesario de tokens + posible inconsistencia
si la corrida actual cambió las reglas).

## Step 4 — Merge results + apply

After all subagent results are written to `result_NN.jsonl`, merge:

```bash
.venv/bin/python << 'PY'
import json, sys
sys.path.insert(0, 'scripts')
import series_aliases, importlib
importlib.reload(series_aliases)
from series_aliases import canonical_series_key, _build_lookup
_build_lookup.cache_clear()
from pathlib import Path
import datetime as dt

BASE = Path('/tmp/manga-standardize-run')
ITEMS = Path('data/items.jsonl')
BLACKLIST = Path('data/non_manga_blacklist.jsonl')

# Load all results
results = {}
for p in sorted(BASE.glob('result_*.jsonl')):
    for line in open(p):
        r = json.loads(line)
        results[r['url']] = r

items = [json.loads(l) for l in open(ITEMS)]
now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

non_manga = []
final = []
for it in items:
    if it.get('standardized_at'):
        # Already standardized, keep as-is
        final.append(it)
        continue
    r = results.get(it.get('url',''))
    if not r:
        # Didn't get a result for this item — skip (will retry next run)
        final.append(it)
        continue
    if not r.get('is_manga', True):
        non_manga.append({
            'url': it.get('url',''),
            'title': it.get('title',''),
            'source': it.get('source',''),
            'publisher': it.get('publisher',''),
            'reason': r.get('non_manga_reason','flagged_by_review'),
            'reviewed_at': now_iso,
        })
        continue
    # Apply standardization
    it['series_key'] = r.get('series_key','')
    it['series_display'] = r.get('series_display','')
    it['edition_key'] = r.get('edition_key','')
    it['edition_display'] = r.get('edition_display','')
    it['volume'] = r.get('volume','')
    new_title = r.get('title_standardized','').strip()
    if new_title:
        # Preservar el título scrapeado original antes de sobrescribir.
        # Esto permite que el search del dashboard encuentre items tipeando
        # el título en JP/ES/FR original aunque el display sea EN canonical.
        # Ver gotcha #22.
        if not it.get('title_original'):
            it['title_original'] = it.get('title','')
        it['title'] = new_title
    # Apply canonical resolution (aliases.yml)
    new_sk, new_sd = canonical_series_key(it['title'], it['series_key'], it['series_display'])
    if new_sk != it['series_key']:
        old_sk = it['series_key']
        it['series_key'] = new_sk
        it['series_display'] = new_sd
        if it['edition_key'].startswith(old_sk + '-'):
            it['edition_key'] = new_sk + it['edition_key'][len(old_sk):]
    elif new_sd != it['series_display']:
        it['series_display'] = new_sd
    # Mark as standardized
    it['standardized_at'] = now_iso
    final.append(it)

# CONSISTENCY CHECK — corregir outliers automáticamente.
# Items con misma URL base (= mismo coleccion_id de listadomanga) deberían
# compartir series_key + edition_key. Cuando hay ≥3 items con un valor y
# 1-2 outliers, los outliers casi siempre son errores del LLM. Aplicamos
# el valor dominante automáticamente (con sample report al final).
import re as _re
from collections import defaultdict as _dd, Counter as _cnt
_groups = _dd(list)
for it in final:
    if not it.get('standardized_at'): continue
    url = it.get('url','') or ''
    m = _re.search(r'listadomanga\.es/coleccion\.php\?id=(\d+)', url)
    if m:
        _groups[f'lmc:{m.group(1)}'].append(it)
    # No agrupamos por URL base no-lmc — esos suelen ser items individuales
    # de retailers donde la URL ya identifica el producto.
_outliers_fixed = 0
_outlier_samples = []
for gk, grp in _groups.items():
    if len(grp) < 4: continue  # solo grupos grandes: 3+ items mayoritarios
    # Series_key consistency
    sk_counts = _cnt(it.get('series_key','') for it in grp)
    dom_sk, dom_sk_n = sk_counts.most_common(1)[0]
    if dom_sk_n >= 3:
        for it in grp:
            if it.get('series_key','') and it['series_key'] != dom_sk:
                old = (it['series_key'], it.get('edition_key',''))
                # Fix series_key + edition_key prefix
                old_ek = it.get('edition_key','')
                if old_ek.startswith(it['series_key'] + '-'):
                    it['edition_key'] = dom_sk + old_ek[len(it['series_key']):]
                it['series_key'] = dom_sk
                dom_sd = next((x.get('series_display','') for x in grp if x.get('series_key')==dom_sk), '')
                if dom_sd: it['series_display'] = dom_sd
                _outliers_fixed += 1
                if len(_outlier_samples) < 5:
                    _outlier_samples.append(f"  {it.get('title','')[:50]}: {old[0]} → {dom_sk}")
    # Edition_key consistency dentro del mismo series_key dominante
    grp_dom = [it for it in grp if it.get('series_key','') == dom_sk]
    if len(grp_dom) >= 4:
        ek_counts = _cnt(it.get('edition_key','') for it in grp_dom)
        dom_ek, dom_ek_n = ek_counts.most_common(1)[0]
        if dom_ek_n >= 3 and len(ek_counts) <= 3:  # tolerar 1-2 outliers
            for it in grp_dom:
                if it.get('edition_key','') and it['edition_key'] != dom_ek:
                    # Solo fix si la diferencia es solo en edition_slug
                    # (no en series prefix), para evitar mergear ediciones
                    # legítimamente distintas (Variant vs Special).
                    old_ek_parts = it['edition_key'].split('-')
                    dom_ek_parts = dom_ek.split('-')
                    if len(old_ek_parts) >= 2 and old_ek_parts[:-1] == dom_ek_parts[:-1]:
                        # Solo edition_slug difiere — solo fix si el outlier
                        # es slug genérico de formato (hardcover/kanzenban)
                        # y el dominante es un nombre específico (grimorio/
                        # collector/integral).
                        FORMAT_GENERIC = {'hardcover', 'kanzenban', 'deluxe', 'regular'}
                        SPECIFIC_NAME = {'grimorio', 'grimoire', 'collector', 'integral',
                                         'maximum', 'kanzenban', 'perfect', 'master',
                                         'special', 'limited', 'variant'}
                        outlier_slug = old_ek_parts[-1]
                        dom_slug = dom_ek_parts[-1]
                        if outlier_slug in FORMAT_GENERIC and dom_slug in SPECIFIC_NAME:
                            if len(_outlier_samples) < 10:
                                _outlier_samples.append(f"  {it.get('title','')[:50]}: {it['edition_key']} → {dom_ek}")
                            it['edition_key'] = dom_ek
                            _outliers_fixed += 1

print(f"\n[CONSISTENCY CHECK] outliers auto-corregidos: {_outliers_fixed}")
for s in _outlier_samples:
    print(s)

# Dedup by (series_key, edition_key, volume) across the entire corpus
def comp(it):
    return (100 if it.get('isbn') else 0) + (10 if it.get('image_url') else 0) + (5 if it.get('price') else 0)
winners = {}
for it in final:
    sk = it.get('series_key',''); ek = it.get('edition_key',''); v = it.get('volume','')
    if not (sk and ek): continue
    k = (sk, ek, v)
    if k not in winners or comp(it) > comp(winners[k]):
        winners[k] = it
deduped = []
seen = set()
dedup_removed = 0
for it in final:
    sk = it.get('series_key',''); ek = it.get('edition_key',''); v = it.get('volume','')
    if not (sk and ek):
        deduped.append(it); continue
    k = (sk, ek, v)
    if k in seen:
        dedup_removed += 1
        continue
    seen.add(k)
    deduped.append(winners[k])

# Write items.jsonl
tmp = ITEMS.with_suffix(ITEMS.suffix + '.tmp')
with tmp.open('w', encoding='utf-8') as fh:
    for it in deduped:
        fh.write(json.dumps(it, ensure_ascii=False) + '\n')
tmp.replace(ITEMS)

# Append non_manga to blacklist (idempotent: check existing URLs first)
existing_bl = set()
if BLACKLIST.exists():
    for line in open(BLACKLIST):
        try:
            existing_bl.add(json.loads(line).get('url',''))
        except: pass
new_bl = [nm for nm in non_manga if nm['url'] not in existing_bl]
with BLACKLIST.open('a', encoding='utf-8') as fh:
    for nm in new_bl:
        fh.write(json.dumps(nm, ensure_ascii=False) + '\n')

print(f'Items totales: {len(items)} → {len(deduped)}')
print(f'Standardized: {sum(1 for it in deduped if it.get("standardized_at"))}')
print(f'Non-manga movidos a blacklist: {len(new_bl)}')
print(f'Deduped: {dedup_removed}')
PY
```

## Step 5 — Run tests

```bash
.venv/bin/python -m pytest tests/test_extraction.py -q
```

## Step 6 — Generate slugs

Run `generate_slugs.py` to assign `slug` values to the newly standardized items.
This is the last write to `items.jsonl` before cleanup.

```bash
.venv/bin/python scripts/retrofit/generate_slugs.py --only-missing --verbose
```

`--only-missing` skips items that already have a `slug` (idempotent). `--verbose`
prints each assignment so you can spot unexpected fallback slugs (`item-{sha1}`)
that indicate items with missing `edition_key` — those may need a follow-up
`/standardize-catalog` pass.

## Step 7 — Translate new descriptions

Run `translate_descriptions.py` to populate `description_es` (and `extras[].description_es`)
for the items that were just standardized. Newly scraped items never have the
`description_es` key, so the script automatically skips everything that was already
translated in previous passes — no extra flag required.

```bash
.venv/bin/python scripts/retrofit/translate_descriptions.py --workers 4
```

**How the targeting works** (no manual filtering needed):
- Items WITH `description_es` key (whole corpus from previous runs) → skipped.
- Items WITHOUT `description_es` key (newly standardized items) → translated.
- Items whose `description` is already in Spanish → written with `description_es = ""`
  (sentinel = "processed, already Spanish") so they won't be re-queued next time.

If the corpus is large (>500 pending) and you want to see progress, add `--limit N`
to do a partial run, then re-run without `--limit` to finish. The script flushes
every 50 items, so a kill mid-run loses at most 50 items' worth of work.

## Step 8 — Cleanup + report

```bash
rm -rf /tmp/manga-standardize-run
```

Then report to the user:
- Total items standardized this run.
- Distinct new series_keys discovered (might want to alias them via `/enrich-series-aliases`).
- Distinct edition_keys.
- Non-manga removed (with sample reasons).
- Items deduplicated.
- Items translated in Step 7 (if any).
- Suggest running `/enrich-series-aliases` if new series_keys appeared.

## Anti-patterns

- **Don't process items that already have `standardized_at`** unless the user explicitly asked for `--force-all`. Wastes API calls.
- **Don't lower the chunk size below 100** unless the corpus is tiny. Subagent setup overhead is non-trivial; bigger chunks amortize it.
- **Don't skip the `canonical_series_key` step in merge** — that's where Demon Slayer's various names collapse to one. Without it, the standardization output is partial.
- **Don't forget to set `standardized_at`** on each processed item — that's what makes future runs incremental.
- **Don't truncate `/tmp/manga-standardize-run/` until you've confirmed the merge wrote items.jsonl successfully.** If the merge fails, you want the raw subagent outputs preserved for debugging.
- **Don't skip Step 7 (translation)** for small runs. Even 1 new item without `description_es` will keep showing its raw non-Spanish description in both UIs.

## Force-rerun the whole catalog

If standardization rules changed significantly and you want to re-process EVERYTHING:

```bash
# Backup first! (usa backup_and_rotate para respetar la rotación max-3)
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
