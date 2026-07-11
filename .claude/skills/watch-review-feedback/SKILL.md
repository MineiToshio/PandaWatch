---
name: watch-review-feedback
description: Analyze items in data/feedback.jsonl that the user flagged via the 👎 dashboard button. Each entry already contains the full item data plus the user's reason. Categorize each feedback (filter issue vs. data quality issue), propose concrete fixes, apply approved changes with tests, run the relevant retrofit scripts, and finally clear the processed rows from data/feedback.jsonl. Trigger manually — invoke ONLY when the user explicitly asks to review feedback or improve the scraper/data. Never run automatically just because data/feedback.jsonl has entries.
argument-hint: "[--dry-run]"
---

# Review feedback and improve catalog quality

You are reviewing items the user flagged via the 👎 button. `data/feedback.jsonl` is a MIXED log: rows with `action="feedback"` (or no `action`, legacy) are a full item record (all fields from `items.jsonl`) plus `reason` and `submitted_at` — that's your queue. But `serve.py`'s move/merge/remove/batch-move operations also append audit rows to this SAME file (`action` set to one of those) — those are already-applied curation, not feedback to process; only count/list them informationally (see Step 0/1). The flagged item was **not removed** from the catalog — it is still visible. Your job: understand what's wrong, categorize it, propose a fix, apply approved changes, and close the loop by clearing the processed rows from the queue.

## Step 0 — Bail early if the queue is empty

> **`feedback.jsonl` es un log MIXTO.** El 👎 del dashboard escribe filas con
> `action="feedback"` (o sin `action`, legacy). Pero `move`/`merge`/`remove`/
> `batch-move` de `serve.py` escriben al MISMO archivo como registro de
> auditoría de operaciones **ya aplicadas** — no son feedback pendiente de
> procesar. El conteo de "items a revisar" debe filtrar por `action`.

```python
import json
rows = []
try:
    with open('data/feedback.jsonl', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
except FileNotFoundError:
    pass

feedback_rows = [r for r in rows if r.get('action', 'feedback') == 'feedback']
curation_rows = [r for r in rows if r.get('action', 'feedback') != 'feedback']
print(f"{len(feedback_rows)} feedback items to review "
      f"({len(curation_rows)} filas de curación ya aplicada en el mismo archivo, informativo)")
```

If 0 items en `feedback_rows` → report "no feedback in queue" and stop (aunque
`curation_rows` tenga entradas — esas no son trabajo pendiente).

## Step 1 — Load and display the feedback queue

`feedback.jsonl` already contains all item fields — no JOIN needed.

```python
import json
from collections import defaultdict

with open('data/feedback.jsonl', encoding='utf-8') as f:
    rows = [json.loads(l) for l in f if l.strip()]

# feedback.jsonl es un log MIXTO (ver Step 0): filtrar a solo action="feedback"
# para la cola a procesar. Las filas move/merge/remove/batch-move son registro
# de auditoría de curación YA aplicada — se cuentan y listan aparte, informativo,
# NUNCA se procesan ni se "arreglan" acá.
feedback_rows = [r for r in rows if r.get('action', 'feedback') == 'feedback']
curation_rows = [r for r in rows if r.get('action', 'feedback') != 'feedback']

if curation_rows:
    print(f"\n{len(curation_rows)} filas de curación ya aplicada (informativo, NO procesar):")
    for r in curation_rows[:10]:
        label = r.get('title') or r.get('url', '?')
        print(f"    {r.get('action','?'):12s} {r.get('submitted_at','?')}  {label[:60]}")
    if len(curation_rows) > 10:
        print(f"    ... {len(curation_rows) - 10} más")

# Dedupe SOLO sobre feedback_rows: si el mismo cluster tiene múltiples entradas,
# NO quedarse solo con la más reciente — concatenar todos los reasons (con su
# submitted_at) para no perder contexto a la hora de categorizar. Las demás
# columnas (title, score, signal_types, etc.) se toman de la fila más reciente,
# porque el item pudo actualizarse entre feedbacks.
seen_clusters = {}
for r in feedback_rows:
    ck = r.get('cluster_key') or r.get('url')
    if ck not in seen_clusters:
        merged = dict(r)
        merged['_reasons'] = [(r.get('reason', '?'), r.get('submitted_at', '?'))]
        seen_clusters[ck] = merged
    else:
        prev_reasons = seen_clusters[ck]['_reasons']
        prev_reasons.append((r.get('reason', '?'), r.get('submitted_at', '?')))
        if r.get('submitted_at', '') > seen_clusters[ck].get('submitted_at', ''):
            merged = dict(r)
            merged['_reasons'] = prev_reasons
            seen_clusters[ck] = merged

items = list(seen_clusters.values())

for i, it in enumerate(items, 1):
    print(f"\n[{i}] {it.get('title','?')}")
    print(f"    source        : {it.get('source','?')}")
    print(f"    url           : {it.get('url','?')[:80]}")
    print(f"    score         : {it.get('score','?')}")
    print(f"    signal_types  : {it.get('signal_types','?')}")
    print(f"    product_type  : {it.get('product_type','?')}")
    print(f"    publisher     : {it.get('publisher','?')}")
    print(f"    country       : {it.get('country','?')}")
    print(f"    series_key    : {it.get('series_key','?')}")
    print(f"    edition_key   : {it.get('edition_key','?')}")
    print(f"    cover         : {((it.get('images') or [{}])[0].get('url') or '?')[:80]}")
    for reason, ts in it['_reasons']:
        print(f"    reason        : {reason}  ({ts})")
```

## Step 2 — Categorize each item

For each deduplicated item, classify the feedback using the taxonomy below. Read `reason` first — it often tells you exactly what's wrong. Then look at `signal_types`, `source`, `publisher`, the cover (`images[0]`), and `url` to confirm.

### Taxonomy

#### Filter / catalog issues (fix target: scraper code or sources.yml)

| Category | Description | Fix target |
|---|---|---|
| **A: non_manga_merch** | Merchandise, figures, bookends, prints, statues, DVDs, games, t-shirts | `_NON_MANGA_HARD` in `manga_watch.py` |
| **B: trading_cards** | Sticker albums, trading cards, panini figuritas | `_NON_MANGA_HARD` |
| **C: news_blog_post** | News article, blog post, announcement, "X reveals", listicle | `_NON_MANGA_HARD` news-family patterns |
| **D: regular_edition** | Regular tomo, not a special/limited/variant — false signal made it pass | Fix `is_collectible_edition` or remove false signal |
| **E: source_noise** | The entire source is too noisy (most items from it are wrong) | `purity: mixed` in `sources.yml`, or disable source |
| **F: western_comic** | Marvel, DC, Euro BD, superhero comics — not manga | `data/comics_blacklist.yml` |
| **G: light_novel** | Pure light novel without manga content | `is_pure_novel` in `manga_watch.py` |
| **H: user_preference** | Technically valid special edition, but user doesn't want it in their catalog | No code change — document and skip |
| **I: false_signal** | A signal fired incorrectly (e.g., `lore_edition` from a generic word) | Fix `KEYWORD_RULES` or `_GENERIC_X_EDITION_PATTERN` exclusions |
| **J: wrong_source_config** | Item was fetched because selectors are too broad | Tighten selectors in `sources.yml` |

#### Data quality issues (fix target: data fields, not scraper logic)

| Category | Description | Fix target |
|---|---|---|
| **K: wrong_image** | Cover is wrong item, wrong edition, low quality, or still a placeholder | `backfill_metadata.py --only image_url`, `fetch_better_covers.py`, or manual fix |
| **L: wrong_metadata** | Author, price, ISBN, or description is incorrect or missing | `backfill_metadata.py --only <field>` or manual fix |
| **M: wrong_classification** | `series_key`, `edition_key`, or `volume` is misassigned | Manual edit of item + possibly `series_aliases.yml` + `generate_slugs.py` |
| **N: bad_title** | Title contains scraping garbage (button text, prefix noise, truncation) | `clean_titles.py` or manual fix |

For each item, state:
- Category (A–N)
- Root cause explanation (1-2 sentences)
- Confidence: HIGH / MEDIUM / LOW
- Proposed fix (specific — quote the exact pattern, field, or value)

If the reason is ambiguous, look at `signal_types` + `source` + `url` to infer the most likely category.

## Step 3 — Scan corpus and consolidate proposals

### 3a — For filter issues (A–J, I): find more items matching each bad pattern

Before presenting proposals, **search `data/items.jsonl` for other items that already match the same bad pattern** — items the user hasn't flagged yet but that would be caught by the same fix.

```python
import json, re
from pathlib import Path

with open("data/items.jsonl", encoding="utf-8") as f:
    corpus = [json.loads(l) for l in f if l.strip()]

# A/B/C — keyword pattern
def corpus_keyword_hits(pattern_re, corpus):
    hits = []
    for item in corpus:
        text = " ".join(filter(None, [
            item.get("title", ""), item.get("title_original", ""),
            item.get("description", ""),
        ]))
        if pattern_re.search(text):
            hits.append(item)
    return hits

# D — regular_edition: items with no premium signals from the same source/publisher
def corpus_regular_edition_hits(source_name, publisher, corpus):
    PREMIUM = {"limited","deluxe","box_set","artbook","kanzenban",
                "lore_edition","variant_cover","hardcover","collector",
                "special_edition","bonus"}
    return [i for i in corpus
            if (i.get("source") == source_name or i.get("publisher") == publisher)
            and not (set(i.get("signal_types") or []) & PREMIUM)]

# E — source noise: all items from the noisy source
def corpus_source_hits(source_name, corpus):
    return [i for i in corpus if i.get("source") == source_name]

# F — western_comic: items from the same publisher
def corpus_publisher_hits(publisher, corpus):
    return [i for i in corpus if i.get("publisher","").lower() == publisher.lower()]

# I — false signal: items that have the specific signal type
def corpus_signal_hits(signal_name, corpus):
    return [i for i in corpus if signal_name in (i.get("signal_types") or [])]

# Print summary per proposal — adapt to actual proposals
# hits = corpus_keyword_hits(re.compile(r"\bbandana\b", re.I), corpus)
# print(f"'bandana' → {len(hits)} hits:")
# for h in hits[:5]: print(f"  - {h.get('title','?')} ({h.get('source','?')})")
```

### 3b — For data quality issues (K–N): show affected items directly

For K/L/M/N, show the specific item(s) from feedback and whether similar items in the corpus are likely affected by the same issue.

```python
# K — wrong_image: check corpus for items from same source whose cover (images[0])
# matches a bad URL pattern. La portada es images[0] (única fuente de verdad).
import sys; sys.path.insert(0, "scripts")
import image_store
def corpus_image_issue_hits(source_name, bad_image_pattern_re, corpus):
    return [i for i in corpus
            if i.get("source") == source_name
            and bad_image_pattern_re.search(image_store.cover_url(i))]

# M — wrong_classification: find siblings with same series_key that may also be wrong
def corpus_series_siblings(series_key, corpus):
    return [i for i in corpus if i.get("series_key") == series_key]
```

### 3c — Present consolidated proposals to the user

Group all HIGH/MEDIUM confidence fixes by type:

```
PROPUESTAS DE MEJORA (N total):

[1] [A: non_manga_merch] Agregar "bandana" a _NON_MANGA_HARD
    Motivo: item "Naruto Bandana Set" pasó como special_edition.
    Riesgo: BAJO — "bandana" no aparece en títulos manga legítimos.
    Retrofit: filter_non_manga.py

    ⚠️  TAMBIÉN EN EL CORPUS ACTUAL: 4 items más matchean este patrón
        - "Bleach Bandana Edición Limitada" (Animate JP)
        - ... (3 más)
        → Si aprobás esta propuesta, el retrofit los elimina también.

[2] [K: wrong_image] Portada equivocada en "Berserk Deluxe 12"
    Motivo: la portada (images[0]) apunta a la del vol.11 (Norma CDN).
    Fix: backfill_metadata.py --only image_url --limit N (no existe flag --url; para un item puntual usar image_store.set_cover() manual)
    (o corrección manual de images[0] en items.jsonl vía image_store.set_cover)

[3] [M: wrong_classification] series_key "berserk-41" → debería ser "berserk"
    Motivo: el heurístico del scraper interpretó el número como parte del slug.
    Fix: editar el item + agregar alias en series_aliases.yml si hay variantes.
    Hermanos en corpus: 0 (case único).

[4] [H: user_preference] "Nausicaä regular tomo" — sin cambio de código
    Preferencia personal. Se documenta pero no se cambia ningún filtro.

¿Aprobás las propuestas [1], [2], [3]?
```

**Esperar confirmación del usuario antes de continuar.**

### Important: corpus hits require explicit user approval

- **Nunca borrar items del corpus silenciosamente.** Siempre mostrar count + samples antes.
- Si el corpus tiene > 10 hits para una propuesta, ofrecer mostrar la lista completa.
- Si el usuario aprueba el fix de código, el retrofit limpia el corpus automáticamente (camino preferido).
- Items categoría H (user_preference) o confianza LOW → solo documentar en el resumen final, no cambiar código.

## Step 4 — Apply approved changes

> **Golden records guard.** Before applying any **data-quality** fix that
> rewrites a specific item in `items.jsonl` (categories K–N: wrong image,
> wrong metadata, wrong series/edition key, junk title), check
> `item.get('approved_at')`. If the item is **approved**, do NOT auto-edit it
> — the owner marked it correct. Surface it to the owner and ask before
> touching it. Filter/code fixes (A–J) are about scraper logic, not specific
> rows, so they're fine; but when a retrofit follows, it already skips
> approved items by default (`--include-approved` to override).

### A/B/C: Adding to `_NON_MANGA_HARD`

Read the current `_NON_MANGA_HARD` list in `manga_watch.py`. Add using `_phrase_pattern()` for word-boundary matching:

```python
re.compile(_phrase_pattern(r"bandana"), re.I),
```

### D: Fixing `is_collectible_edition`

Read the function in `manga_watch.py`. If a signal fired falsely, add the equivalent to the exclusion list of `_GENERIC_X_EDITION_PATTERN` (see CLAUDE.md gotcha #24) or tighten the relevant condition.

### E: Source purity change

In `sources.yml`, change `purity: "manga_only"` → `purity: "mixed"`. If the source yields 0 real items after, consider `enabled: false`.

### F: Comics blacklist

Edit `data/comics_blacklist.yml` — add publisher to `publishers` or franchise keyword to `franchise_keywords`. Never add publishers that also publish manga (Panini, Norma, Planeta).

### G: Light novel hints

In `manga_watch.py`, find `is_pure_novel()`. Add the publisher or URL hint pattern.

### I: False signal fix

Find the entry in `KEYWORD_RULES` or `_GENERIC_X_EDITION_PATTERN`. Remove the conflicting keyword or add it to the exclusion list (CLAUDE.md gotchas #9, #24).

### K: Wrong image

Option 1 — run backfill for that specific item:
```bash
.venv/bin/python scripts/retrofit/backfill_metadata.py --only image_url --dry-run
# then apply
```

Option 2 — single item with a known correct URL: `fix_item_fields.py` (auditoría
Fable 2026-07-08, hallazgo F12 — reemplaza el snippet manual que reescribía
`items.jsonl` a mano sin `backup_and_rotate`). `cover_url` es un campo sintético
que delega en `image_store.set_cover()` (la MISMA función del resto del pipeline):

```bash
.venv/bin/python scripts/retrofit/fix_item_fields.py \
    --url "<item_url>" --set cover_url="<correct_image_url>"
```

Then re-download:
```bash
.venv/bin/python scripts/retrofit/mirror_images.py --no-gc
```

### L: Wrong metadata

```bash
# Example: re-fetch author for a specific source
.venv/bin/python scripts/retrofit/backfill_metadata.py --only author --dry-run
# then apply if it looks right
```

Or for a single item, use `fix_item_fields.py` (same pattern as K above) for
fields it covers (`isbn`, `publisher`, `language`, `description`…).

### M: Wrong classification

1. Fix the item with `fix_item_fields.py` (auditoría Fable 2026-07-08, hallazgo
   F12 — reemplaza el snippet manual que reescribía `items.jsonl` sin
   `backup_and_rotate` ni guard `approved_at`, y que además seteaba `title` a
   mano contradiciendo la política de títulos, gotcha #92 — **NUNCA renombres
   el `title`; categoría M es sobre series/edition/volume, no el nombre
   oficial**):
```bash
.venv/bin/python scripts/retrofit/fix_item_fields.py --url "<item_url>" \
    --set series_key="<correct_series_key>" \
    --set series_display="<correct_display>" \
    --set edition_key="<correct_edition_key>" \
    --set edition_display="<correct_display>" \
    --set volume="<correct_volume>"
```
   El script re-deriva `cluster_key` automáticamente (sus insumos incluyen
   `edition_key`/`volume`) y hace `backup_and_rotate` + guard `approved_at`.

2. If the issue is a missing alias (same work under a different name), add to `data/series_aliases.yml`.

3. `cluster_key` ya lo re-derivó `fix_item_fields.py` en el paso 1. El `slug`
   es **sticky por diseño** (gotcha #65) — una vez asignado, NO se recalcula
   solo porque cambiaron `series_key`/`edition_key`/`volume`. Correr
   `generate_slugs.py --only-missing` acá es solo para rellenar el slug de
   items que todavía no tengan uno (p. ej. si el fix también tocó un item sin
   slug); **no refresca** el slug de este item recategorizado:
```bash
.venv/bin/python scripts/retrofit/generate_slugs.py --only-missing
```
   Si el owner quisiera que el slug de ESTE item puntual refleje la nueva
   clasificación, es una decisión explícita aparte (no asumir que corresponde
   solo por haber corregido la categoría M) — no la tomes de oficio acá.

### N: Bad title

If it's a systematic pattern (same prefix on multiple items from same source), fix in `manga_watch.py` and run:
```bash
.venv/bin/python scripts/retrofit/clean_titles.py --dry-run
.venv/bin/python scripts/retrofit/clean_titles.py
```

If it's a one-off (real scraping garbage — button text, prefix noise,
truncation — NEVER a rename to the canonical series), use `fix_item_fields.py`
with `--allow-title` explícito (imprime el warning de la política de títulos):
```bash
.venv/bin/python scripts/retrofit/fix_item_fields.py --url "<item_url>" \
    --set title="<cleaned_title>" --allow-title
```

## Step 5 — Add tests (filter changes only)

For every code change to filters (A–J, I), add a unit test in `tests/test_extraction.py` with the exact title string from the feedback. Use the appropriate group:

- `test_is_likely_manga_rejects_*` for `_NON_MANGA_HARD/SOFT` changes
- `test_is_comic_not_manga_*` for comics blacklist
- `test_is_collectible_edition_*` for gate changes
- `test_is_pure_novel_*` for novel filter

Then run the full suite:
```bash
.venv/bin/python -m pytest tests/test_extraction.py -q
```

**If any test fails: fix before continuing.**

Data quality fixes (K–N) do not need new tests unless they reveal a systematic extractor bug worth covering.

## Step 6 — Run retrofit scripts (filter changes only)

> ⚠️ **Gotcha #61 — el corpus está ~98.9% estandarizado, y eso apaga estos
> retrofits sobre la fila que originó el feedback.** `rescore.py` (línea ~126)
> saltea por defecto cualquier item con `standardized_at` (recomputar
> `signal_types` desde texto crudo "lava" las señales de la etiqueta ya
> derivada). `filter_collectible.py` (línea ~81) sobre un item estandarizado
> solo aplica los gates duros (`title_too_short`, `title_junk_discount`,
> `title_junk_generic`, `umbrella_magazine`, `no_title`); si el gate devuelve
> `regular_tomo` (el caso típico de la categoría **D**) sobre un item con
> `standardized_at`, el script lo **conserva a propósito** — no lo rechaza.
>
> Consecuencia práctica: para categorías **D** (`regular_edition`) e **I**
> (`false_signal`) sobre un item YA estandarizado, correr `rescore.py` /
> `filter_collectible.py` es **no-op sobre ese item puntual** — no esperes que
> el retrofit lo saque del corpus. La vía correcta ahí es un **fix puntual**:
> `fix_item_fields.py` para corregir el campo que corresponda (p. ej. bajar
> `score` o quitar el signal falso de `signal_types` directamente), o
> re-estandarizar el item (quitar su `standardized_at` puntual y correr el
> flujo de standardize de nuevo para que re-derive la etiqueta desde cero).
> El retrofit masivo (`rescore.py`/`filter_collectible.py` sin
> `--include-standardized`) solo tiene efecto real sobre la porción **cruda**
> del corpus (el ~1.1% restante) o sobre items nuevos que entren después.

| What changed | Retrofits to run | Efecto sobre items estandarizados |
|---|---|---|
| `_NON_MANGA_HARD` / `_NON_MANGA_SOFT` / `is_pure_novel` / `is_comic_not_manga` | `filter_non_manga.py` | Sí aplica — estos filtros no tienen el guard de `standardized_at` |
| `is_collectible_edition` / `COLLECTIBLE_EDITION_SIGNAL_TYPES` | `filter_collectible.py` | Solo gates duros; `regular_tomo` sobre estandarizado se CONSERVA (no-op para D) |
| `KEYWORD_RULES` / `detect_signals` / `score_candidate` | `rescore.py` then `filter_collectible.py` | `rescore.py` SALTEA items con `standardized_at` por defecto (no-op para D/I sobre esa fila) |
| `sources.yml` purity change | `filter_non_manga.py` | Sí aplica — mismo filtro sin guard |

Always dry-run first:
```bash
.venv/bin/python scripts/retrofit/filter_non_manga.py --dry-run
.venv/bin/python scripts/retrofit/filter_non_manga.py   # apply if looks right
```

Estos retrofits SIGUEN siendo correctos para limpiar el resto del corpus
(items crudos o futuros que matcheen el mismo patrón); lo que NO hacen es
resolver automáticamente el item puntual que motivó el feedback si ya está
estandarizado — ese va por el fix puntual descrito arriba.

## Step 7 — Clear the processed rows from `feedback.jsonl`

`feedback.jsonl` es el log MIXTO descrito en el Step 0/1: además de las filas
`action="feedback"` que este skill procesa, puede tener filas `move`/`merge`/
`remove`/`batch-move` de `serve.py` (registro de auditoría de curación ya
aplicada). El backup timestamped de abajo es la retención real de ese rastro
completo — por eso corre siempre primero y nunca se salta —, pero la
reescritura del archivo YA NO es un truncado ciego: en vez de
`: > data/feedback.jsonl` (que también borraría, sin dejar rastro en el
backup ya tomado, cualquier fila escrita por `serve.py` o por un nuevo 👎 del
dashboard MIENTRAS el skill corría), reescribimos el archivo conservando solo
las filas que esta corrida **no vio** — identificadas por `submitted_at`,
comparado contra el `submitted_at` de cada fila cargada en el Step 1 (tanto
`feedback_rows` como `curation_rows`, es decir el `rows` completo del Step 1).

```python
import json
from pathlib import Path
from scripts.manga_watch import backup_and_rotate

path = Path('data/feedback.jsonl')

# 1. Backup completo (feedback + curación) — retención del rastro de auditoría.
#    timestamped=True (2026-07-07): cada corrida guarda su PROPIO timestamp en
#    vez de pisar el slot fijo `feedback.jsonl.pre-review-bak`, así no se pierde
#    el histórico de corridas anteriores (rota por el mismo label, conserva los
#    3 más recientes). Ver docs/reference/conventions.md y
#    scripts/retrofit/README.md § Backups.
backup_and_rotate(path, 'review', timestamped=True)

# 2. Reescritura atómica: conservar solo las filas NO vistas en el Step 1
#    (mismo submitted_at que ya cargamos == procesada/registrada esta corrida).
seen_submitted_at = {r.get('submitted_at') for r in rows}  # `rows` viene del Step 1

remaining = []
with open(path, encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get('submitted_at') not in seen_submitted_at:
            remaining.append(line)

tmp = path.with_suffix('.jsonl.tmp')
with open(tmp, 'w', encoding='utf-8') as f:
    for line in remaining:
        f.write(line + '\n')
tmp.replace(path)  # atómico (os.replace bajo el capó) — sin ventana de archivo vacío

print(f"feedback.jsonl: {len(remaining)} filas nuevas retenidas (no vistas esta corrida)")
```

**Do NOT clear before all approved changes are applied.**

## Step 8 — Final report + update CLAUDE.md

```
RESUMEN DE /watch-review-feedback
============================
Items revisados          : N
  → Problemas de filtros : X  (categorías A–J)
  → Calidad de datos     : Y  (categorías K–N)
  → Preferencia personal : Z  (categoría H, sin acción)

Cambios de código        : X
Tests agregados          : Y
Items corpus removidos   : Z (via retrofits)

Cambios aplicados:
  - [1] _NON_MANGA_HARD += "bandana" → filter_non_manga removió 5 items
  - [2] image_url corregida para "Berserk Deluxe 12" + re-download cover
  - [3] series_key "berserk-41" → "berserk" + cluster_key refresh
  ...

feedback.jsonl: N filas procesadas retiradas (M filas nuevas no vistas retenidas)
```

Luego actualizá la fecha de la línea `Last updated:` de `CLAUDE.md` (sin agregar prosa — CLAUDE.md ya no lleva changelog) y el doc de referencia que corresponda en `docs/reference/` según la política de documentación. En concreto, según la naturaleza del fix aplicado:

- **Regla dura de FUENTES**: si el fix tocó `sources.yml` (categorías E/J) o el
  parser/selectores de una fuente específica, actualizá su ficha
  `docs/scraper/sources/<fuente>.md` en el MISMO turn (si la fuente todavía no
  tiene ficha, creala desde `_TEMPLATE.md`). No es opcional — aplica a
  cualquier bug/quirk/fix/cambio de cobertura de esa fuente, lo haya
  encontrado este skill o cualquier otro trabajo.
- **Gotcha nueva**: si el fix reveló un quirk de parser, un caso de dedup, un
  falso positivo/negativo, o cualquier comportamiento no documentado
  previamente, agregalo a `docs/reference/gotchas.md` con el número
  siguiente al último existente (bumpeá el heading — las gotchas se citan por
  número en todo el repo, ese número es estable).

---

## Referencia rápida: categorías y sus pointers en CLAUDE.md

- `_NON_MANGA_HARD` / `_NON_MANGA_SOFT`: design decision #2, gotcha #9
- Comics blacklist: design decision #3, gotcha #11
- `is_collectible_edition`: conventions "When you add or modify a filter pattern"
- `is_pure_novel`: misma sección
- Source purity: design decision #3, gotchas #7, #10
- False `lore_edition` de palabras genéricas: gotcha #24
- `_phrase_pattern()` para word-boundary: gotcha #9
- `backfill_metadata.py`: file map en CLAUDE.md, sección retrofit
- `clean_titles.py` / `generate_slugs.py`: file map en CLAUDE.md
- Categorías D/I sobre item con `standardized_at` (rescore/filter_collectible no-op): gotcha #61 (Step 6)
- Slug sticky por diseño, `--only-missing` no refresca: gotcha #65 (Step 4 → M)

Ante la duda sobre si un fix es seguro, preferir **no cambiar código** y marcar como categoría H. Mejor dejar un item marginal en el corpus que romper items legítimos con un patrón demasiado amplio.
