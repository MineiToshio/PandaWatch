---
name: review-rejected
description: Analyze items in data/user_rejected.jsonl that the user rejected via the 👎 dashboard button. For each rejection, understand why it was a bad match for the catalog, categorize the root cause, propose concrete filter improvements to prevent similar items from being scraped in future delta and full runs, apply approved changes with tests, run the relevant retrofit scripts to clean the existing corpus, and finally truncate data/user_rejected.jsonl. Invoke whenever data/user_rejected.jsonl has entries, or when the user says they want to review rejected items or improve the scraper filters.
---

# Review rejected items and improve filters

You are reviewing items the user explicitly rejected from the catalog via the 👎 button. Each row in `data/user_rejected.jsonl` is a real item the scraper captured that shouldn't be there. Your job: understand WHY it slipped through, propose a targeted fix, apply it, and close the loop by cleaning the corpus and truncating the queue.

## Step 0 — Bail early if the queue is empty

```python
import json
rows = []
try:
    with open('data/user_rejected.jsonl', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
except FileNotFoundError:
    pass
print(f"{len(rows)} rejected items to review")
```

If 0 items → report "no rejected items in queue" and stop.

## Step 1 — Load and display the rejection queue

Print a summary table so you can see what you're working with:

```python
import json
from collections import defaultdict

with open('data/user_rejected.jsonl', encoding='utf-8') as f:
    rows = [json.loads(l) for l in f if l.strip()]

# Dedupe: if the same cluster removed N source rows, pick one representative
seen_clusters = set()
items = []
for r in rows:
    ck = r.get('cluster_key') or r.get('url')
    if ck not in seen_clusters:
        seen_clusters.add(ck)
        items.append(r)

for i, it in enumerate(items, 1):
    print(f"\n[{i}] {it.get('title','?')}")
    print(f"    source        : {it.get('source','?')}")
    print(f"    url           : {it.get('url','?')[:80]}")
    print(f"    score         : {it.get('score','?')}")
    print(f"    signal_types  : {it.get('signal_types','?')}")
    print(f"    product_type  : {it.get('product_type','?')}")
    print(f"    publisher     : {it.get('publisher','?')}")
    print(f"    country       : {it.get('country','?')}")
    print(f"    rejection_reason: {it.get('rejection_reason','?')}")
```

## Step 1.5 — Sanity-check for false rejections

Before diving into filter improvements, scan the list for items that **look like valid special editions that may have been removed by mistake** (wrong click, misread title, etc.).

For each item, ask: does it pass a quick mental check for being a genuine collectible?
- Does the title contain explicit special-edition signals? (`Deluxe`, `Limited`, `Collector`, `Box Set`, `特装版`, `限定版`, `Cofanetto`, `Edición Coleccionista`, `Artbook`, etc.)
- Is the `signal_types` list non-empty with premium signals (`limited`, `deluxe`, `box_set`, `artbook`, `variant_cover`, `kanzenban`, `lore_edition`, …)?
- Is the `score` high (≥ 50)?
- Does the `rejection_reason` the user wrote sound like genuine intent to block ("no es manga", "es merchandising", "novela ligera") rather than an accidental click or vague note?

Flag any item where the answer is "this looks like it belongs in the catalog and the reason is ambiguous or contradictory". Use this Python snippet to help spot them:

```python
import json

PREMIUM_SIGNALS = {
    "limited", "deluxe", "box_set", "artbook", "kanzenban",
    "lore_edition", "variant_cover", "hardcover", "collector",
    "special_edition", "bonus",
}

suspects = []
for it in items:
    signals = set(it.get("signal_types") or [])
    score = it.get("score", 0)
    reason = (it.get("rejection_reason") or "").lower()
    has_premium = bool(signals & PREMIUM_SIGNALS)
    short_reason = len(reason.split()) <= 4  # vague / accidental note?
    if has_premium and score >= 50 and short_reason:
        suspects.append(it)

print(f"\n⚠️  {len(suspects)} item(s) may have been rejected by mistake:\n")
for it in suspects:
    print(f"  • {it.get('title','?')}")
    print(f"    signal_types : {it.get('signal_types')}")
    print(f"    score        : {it.get('score')}")
    print(f"    reason       : {it.get('rejection_reason')}")
    print()
```

### Present findings to the user

If `suspects` is non-empty, report them prominently **before** proceeding:

```
⚠️  POSIBLES RECHAZOS ACCIDENTALES (N items):

[1] "Berserk Deluxe Edition Vol. 14" (Dark Horse)
    Señales  : ['deluxe', 'hardcover']  |  Score: 120
    Motivo dado: "no"
    ¿Fue rechazado por error? Si querés restaurarlo, decime el número.

[2] ...

Si ninguno fue un error, respondé "ninguno" y continúo con el análisis.
```

**Wait for the user's response.**

- If the user identifies items to restore, add each one back to `data/items.jsonl` using `append_jsonl` semantics (write the row without `rejection_reason`/`rejected_at`, preserve all original fields):

```python
import json
from pathlib import Path

ITEMS_PATH = Path("data/items.jsonl")
restore_urls = {"<url_1>", "<url_2>"}  # fill from user selection

# Load user_rejected to get the full original rows
rejected_rows = []
with open("data/user_rejected.jsonl", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            rejected_rows.append(json.loads(line))

# Restore: write back to items.jsonl (append; append_jsonl handles upsert)
# Remove the rejection-specific fields before restoring
REJECT_FIELDS = {"rejection_reason", "rejected_at"}
restored = []
for row in rejected_rows:
    if row.get("url") in restore_urls:
        clean = {k: v for k, v in row.items() if k not in REJECT_FIELDS}
        restored.append(clean)

existing_urls = set()
if ITEMS_PATH.exists():
    with ITEMS_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    existing_urls.add(json.loads(line).get("url"))
                except Exception:
                    pass

with ITEMS_PATH.open("a", encoding="utf-8") as f:
    for row in restored:
        if row.get("url") not in existing_urls:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"  ✓ Restaurado: {row.get('title','?')}")
```

- Remove restored items from the working `items` list so they are NOT included in the `user_rejected.jsonl` truncation or filter analysis.
- If the user says "ninguno" / none, continue directly to Step 2.

If `suspects` is empty, skip this step entirely and go straight to Step 2.

---

## Step 2 — Categorize each item

For each deduplicated item, classify its root cause using the taxonomy below. Read `scripts/manga_watch.py` and `data/comics_blacklist.yml` as needed to understand existing patterns before proposing additions.

### Taxonomy of root causes

| Category | Description | Fix target |
|---|---|---|
| **A: non_manga_merch** | Merchandise, figures, bookends, prints, statues, DVDs, Blu-rays, games, t-shirts, calendars | Add keyword/publisher to `_NON_MANGA_HARD` in `manga_watch.py` |
| **B: trading_cards** | Sticker albums, trading cards, panini figuritas, Pokémon cards | Add to `_NON_MANGA_HARD` |
| **C: news_blog_post** | News article, blog post, announcement, "X reveals", "Win this", listicle | Add to `_NON_MANGA_HARD` news-family patterns |
| **D: regular_edition** | Regular tomo that is not a special/limited/variant — not a collectible | Improve `is_collectible_edition` or scoring (remove a false signal) |
| **E: source_noise** | The ENTIRE source is too noisy (most items from it are wrong) | Flag source `purity: mixed` in `sources.yml`, or disable it |
| **F: western_comic** | Marvel, DC, Euro BD, superhero comics — not manga | Add publisher or franchise to `data/comics_blacklist.yml` |
| **G: light_novel** | Pure light novel without manga content | Add hint to `is_pure_novel` pattern in `manga_watch.py` |
| **H: user_preference** | Item is technically valid (IS a manga special edition) but the user doesn't want it in their personal catalog | No code change — mark as "user preference, no fix needed". Document it. |
| **I: false_signal** | A scoring signal fired incorrectly (e.g., `lore_edition` from a generic word) | Fix/remove the false signal from `KEYWORD_RULES` or `_GENERIC_X_EDITION_PATTERN` exclusions |
| **J: wrong_source_config** | Item was fetched because a source's selectors are too broad | Tighten selectors in `sources.yml` |

For each item, state:
- Category (A–J)
- Root cause explanation (1-2 sentences)
- Confidence: HIGH / MEDIUM / LOW
- Proposed fix (specific — quote the exact pattern, publisher name, or signal name)

If an item's reason is ambiguous (e.g., "esto no me gusta"), look at its `signal_types`, `source`, `publisher`, and `url` to infer the most likely category.

## Step 3 — Scan the corpus + consolidate proposals

### 3a — Corpus scan: find more items matching each bad pattern

Before presenting proposals, **search `data/items.jsonl` for other items that already match the same bad pattern** — items the user hasn't rejected yet but that would be caught by the same fix. This is the most important expansion: you're not just fixing the rejected items, you're cleaning up all occurrences of the same problem in the corpus.

Run a targeted scan per category. Use Python:

```python
import json, re
from pathlib import Path

with open("data/items.jsonl", encoding="utf-8") as f:
    corpus = [json.loads(l) for l in f if l.strip()]

# Build per-proposal hit lists. Examples below — adapt to the actual proposals.

# A/B/C — keyword pattern: look for the same keyword in title + title_original
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
    hits = []
    for item in corpus:
        signals = set(item.get("signal_types") or [])
        same_src = (item.get("source","") == source_name or
                    item.get("publisher","") == publisher)
        if same_src and not (signals & PREMIUM):
            hits.append(item)
    return hits

# E — source_noise: ALL items from the noisy source
def corpus_source_hits(source_name, corpus):
    return [i for i in corpus if i.get("source","") == source_name]

# F — western_comic: items from the same publisher (or franchise keyword in title)
def corpus_publisher_hits(publisher, corpus):
    return [i for i in corpus if i.get("publisher","").lower() == publisher.lower()]

# G — light_novel: items from same publisher or with LN keywords
def corpus_novel_hits(publisher_hint, corpus):
    LN_WORDS = re.compile(
        r"\b(light novel|ノベル|novela ligera|roman léger|romanzo leggero)\b", re.I
    )
    return [i for i in corpus
            if publisher_hint.lower() in i.get("publisher","").lower()
            or LN_WORDS.search(i.get("title","") + " " + i.get("title_original",""))]

# I — false_signal: items that have the specific signal type that fired falsely
def corpus_signal_hits(signal_name, corpus):
    return [i for i in corpus
            if signal_name in (i.get("signal_types") or [])]

# Print hits summary for each proposal (adapt variable names to actual proposals)
# Example:
# hits = corpus_keyword_hits(re.compile(r"\bbandana\b", re.I), corpus)
# print(f"'bandana' pattern → {len(hits)} hits in corpus:")
# for h in hits[:5]: print(f"  - {h.get('title','?')} ({h.get('source','?')})")
```

For each proposal, print:
- Number of corpus hits
- First 5 representative examples (title + source)
- Whether they look like genuine false positives or edge cases that need manual review

### 3b — Present consolidated proposals to the user

Group all HIGH/MEDIUM confidence fixes by type. Include the corpus scan results in each proposal:

```
PROPUESTAS DE MEJORA (N total):

[1] [A: non_manga_merch] Agregar "bandana" a _NON_MANGA_HARD
    Motivo: 2 items de Animate JP con "バンダナ付き" (bandana bonus) pasaron
    como special_edition. El producto es una bandana, no manga.
    Riesgo: BAJO — "bandana" no aparece en títulos manga legítimos.
    Retrofit: rescore.py + filter_non_manga.py

    ⚠️  TAMBIÉN EN EL CORPUS ACTUAL: 7 items más matchean este patrón
        - "Banana Fish Bandana Set" (Animate JP)
        - "My Hero Academia Bandana Edición Especial" (Animate JP)
        - ... (5 más)
        → Si aprobás esta propuesta, el retrofit los elimina también.

[2] [D: regular_edition] "One Piece Vol. 110" de Norma — tomo regular
    Motivo: señal `special_edition` fue un falso positivo del selector
    demasiado amplio. El item es una edición estándar sin ningún extra.
    Riesgo: BAJO — la corrección en is_collectible_edition es quirúrgica.
    Retrofit: filter_collectible.py

    ⚠️  TAMBIÉN EN EL CORPUS ACTUAL: 14 tomos regulares de Norma con el
        mismo falso positivo (sin señal premium real):
        - "Berserk Vol. 41" (Norma) — score 22, signals: []
        - "Naruto Vol. 72" (Norma) — score 18, signals: []
        - ... (12 más)
        → El retrofit los eliminaría. ¿Querés revisarlos antes?

[2b] Si no aprobás la corrección de código pero igual querés eliminar
     esos 14 tomos regulares del corpus, podemos borrarlos directamente
     de items.jsonl sin cambiar ningún filtro.

[3] [E: source_noise] Cambiar purity de "JP - Kotobukiya" a "mixed"
    Motivo: 3 de 3 items rechazados son figuras, no manga.
    Riesgo: MEDIO — verificar si algún item de esa fuente ES manga real.
    Retrofit: filter_non_manga.py

    📋 TODOS LOS ITEMS DE ESA FUENTE EN EL CORPUS (12 total):
        - "Figura Asuka Evangelion" (Kotobukiya) ← merchandise
        - "Dragon Ball Z Statue" (Kotobukiya) ← merchandise
        - "Berserk Artbook" (Kotobukiya) ← ¿manga real?
        → Revisar antes de aplicar para no perder el artbook.

...

[N] [H: user_preference] "Nausicaä regular tomo" — sin cambio de código
    Preferencia personal. Se documenta en el resumen pero no se cambia
    ningún filtro ni se buscan similares en el corpus.

¿Aprobás las propuestas [1], [2], [3] ... ?
(Podés aprobar todas, algunas, pedir que primero muestre los corpus hits
completos de alguna, o aprobar la eliminación directa sin cambio de código.)
```

**Esperar confirmación del usuario antes de continuar.**

### Important: corpus hits require explicit user approval

- **Never delete corpus items silently.** Always show the count and samples first.
- If the corpus has > 10 hits for a proposal, offer to show the full list before proceeding.
- If the user approves the code fix, the retrofit handles corpus cleanup automatically (preferred path).
- If the user wants to remove corpus hits **without** changing code (e.g., category H extended to similar items), offer a direct deletion snippet instead.

Items con categoría H (user_preference) o confianza LOW no necesitan cambio de código. Solo se listan en el resumen final.

## Step 4 — Apply approved changes

For each approved proposal, apply the change to the codebase. Follow CLAUDE.md conventions:

### A/B/C: Adding to `_NON_MANGA_HARD`

Read the current `_NON_MANGA_HARD` list in `manga_watch.py` first. Add the new keyword using `_phrase_pattern()` if it's a word-boundary match. Examples:

```python
# Good: word-boundary via _phrase_pattern
re.compile(_phrase_pattern(r"bandana"), re.I),

# Good: compound product (no word boundary needed)
re.compile(r"acrylic\s+keychain", re.I),
```

Always add a comment explaining why this specific pattern is safe.

### D: Fixing `is_collectible_edition`

Read the function in `manga_watch.py`. If a signal fired falsely (e.g., `lore_edition` from "Nueva Edición"), add the Spanish/Italian/French equivalent to the exclusion list of `_GENERIC_X_EDITION_PATTERN`. See gotcha #24 in CLAUDE.md.

### E: Source purity change

In `sources.yml`, find the source by name and change `purity: "manga_only"` to `purity: "mixed"`. If the source yields 0 real items after the change, consider disabling it with `enabled: false`.

### F: Comics blacklist

Edit `data/comics_blacklist.yml` — add publisher to the `publishers` list OR franchise keyword to the `franchise_keywords` list. Never add publishers that also publish manga (Panini, Norma, Planeta).

### G: Light novel hints

In `manga_watch.py`, find `is_pure_novel()`. Add the publisher name or URL hint pattern that identifies this as a novel-only source.

### I: False signal fix

Find the relevant entry in `KEYWORD_RULES` or `_GENERIC_X_EDITION_PATTERN`. Either remove the conflicting keyword or add it to the exclusion list. See CLAUDE.md gotchas #9 and #24.

## Step 5 — Add tests

For EVERY code change, add a unit test in `tests/test_extraction.py` with the exact title string from the rejected item. Use the appropriate test group:
- `test_is_likely_manga_rejects_*` for `_NON_MANGA_HARD/SOFT` changes
- `test_is_comic_not_manga_*` for comics blacklist changes
- `test_is_collectible_edition_*` for gate changes
- `test_is_pure_novel_*` for novel filter changes

Then run the full suite and confirm it's green:

```bash
.venv/bin/python -m pytest tests/test_extraction.py -q
```

**If any test fails: fix the failing test or revert the change before continuing.**

## Step 6 — Run retrofit scripts

Run the appropriate retrofits to clean the existing corpus. Choose based on what changed:

| What changed | Retrofits to run |
|---|---|
| `is_likely_manga` / `_NON_MANGA_HARD` / `_NON_MANGA_SOFT` / `is_pure_novel` / `is_comic_not_manga` | `filter_non_manga.py` |
| `is_collectible_edition` / `COLLECTIBLE_EDITION_SIGNAL_TYPES` | `filter_collectible.py` |
| `KEYWORD_RULES` / `detect_signals` / `score_candidate` | `rescore.py` then `filter_collectible.py` |
| `sources.yml` purity change | `filter_non_manga.py` |

Always use `--dry-run` first to see impact:

```bash
.venv/bin/python scripts/retrofit/filter_non_manga.py --dry-run
.venv/bin/python scripts/retrofit/filter_non_manga.py   # apply if dry-run looks right
```

Report how many items were removed from the corpus in each retrofit run.

## Step 7 — Truncate `user_rejected.jsonl`

Once all approved changes are applied and retrofits done, clear the queue.
Back up first, then truncate:

```bash
.venv/bin/python -c "from scripts.manga_watch import backup_and_rotate; from pathlib import Path; backup_and_rotate(Path('data/user_rejected.jsonl'), 'review')"
: > data/user_rejected.jsonl
```

**Do NOT truncate before all changes are applied.** The queue is the source of truth for this session.

## Step 8 — Final report

Print a summary with:

```
RESUMEN DE /review-rejected
===========================
Items revisados        : N
Cambios de código      : X
Tests agregados        : Y
Items corpus removidos : Z (via retrofits)
Categorías sin código  : [list of H/LOW items — user preference or low confidence]

Cambios aplicados:
  - [1] _NON_MANGA_HARD += "bandana" → filter_non_manga removió 5 items
  - [2] sources.yml: Kotobukiya → purity:mixed → filter_non_manga removió 3 items
  ...

user_rejected.jsonl: truncado (0 items pendientes)
```

Also update the "Last updated" section of CLAUDE.md with a one-paragraph summary of what changed, following the documentation policy.

---

## Reference: categories of fixes and their CLAUDE.md pointers

- `_NON_MANGA_HARD` / `_NON_MANGA_SOFT`: design decision #2, gotcha #9
- Comics blacklist: design decision #3, gotcha #11
- `is_collectible_edition`: conventions "When you add or modify a filter pattern"
- `is_pure_novel`: same section
- Source purity: design decision #3, gotchas #7, #10
- False `lore_edition` from generic words: gotcha #24
- `_phrase_pattern()` for word-boundary matching: gotcha #9

When in doubt about whether a fix is safe, err on the side of **not changing code** and marking the item as category H. It's better to leave a marginal item in the corpus than to break legitimate items with an overly broad pattern.
