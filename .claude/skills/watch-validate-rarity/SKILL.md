---
name: watch-validate-rarity
description: Verifica la rareza de items ambiguos (boxsets y artbooks con rarity="rare" de publishers grandes) buscando en la web si están en stock hoy. Actualiza a "common" cuando confirma stock activo. Solo procesa items sin rarity_verified_at (incremental). Correr después de scrapes grandes o cuando quieras validar items nuevos.
argument-hint: "[--limit N] [--dry-run]"
---

# Validate rarity — verificación web de items ambiguos

Valida la rareza de **boxsets y artbooks de publishers grandes** que tienen
`rarity="rare"` por default. Busca en la web si están en stock hoy:
- En stock → actualiza a `common`
- Sin stock / solo segunda mano / no encontrado → mantiene `rare`

Solo toca items sin `rarity_verified_at` (incremental). Corre rápido porque
el scope real es chico (~10-40 items por scrape normal).

## Step 0 — Bail early si no hay nada pendiente

```python
import json

items = [json.loads(l) for l in open('data/items.jsonl') if l.strip()]

AMBIGUOUS_TYPES = {'boxset', 'artbook', 'fanbook', 'manga'}
MAJOR_PUBLISHERS = {
    'viz', 'dark horse', 'darkhorse', 'panini', 'seven seas', 'sevenseas',
    'yen press', 'yenpress', 'kodansha', 'shueisha', 'planeta', 'norma',
    'glenat', 'glénat', 'pika', 'ki-oon', 'kioon', 'star comics', 'jpop',
    'j-pop', 'carlsen', 'egmont', 'manga cult', 'altraverse',
}

def is_major(item):
    pub = (item.get('publisher') or '').lower()
    return any(p in pub for p in MAJOR_PUBLISHERS)

pending = [
    i for i in items
    if i.get('rarity') == 'rare'
    and not i.get('rarity_verified_at')
    and i.get('product_type') in AMBIGUOUS_TYPES
    and is_major(i)
]

print(f"Total items: {len(items)}")
print(f"Items pendientes de verificar: {len(pending)}")

if not pending:
    print("Nada que verificar. Todas las rarezas están al día.")
    import sys; sys.exit(0)
```

Si 0 pendientes → reportar y parar.

## Step 1 — Agrupar por edition_key y preparar candidatos

Muchos items son volúmenes de la misma edición. Tiene más sentido verificar
**una vez por edición** que una vez por volumen. Tomamos el item más
representativo (mayor score) de cada edition_key.

```python
import json
from collections import defaultdict

items = [json.loads(l) for l in open('data/items.jsonl') if l.strip()]

AMBIGUOUS_TYPES = {'boxset', 'artbook', 'fanbook', 'manga'}
MAJOR_PUBLISHERS = {
    'viz', 'dark horse', 'darkhorse', 'panini', 'seven seas', 'sevenseas',
    'yen press', 'yenpress', 'kodansha', 'shueisha', 'planeta', 'norma',
    'glenat', 'glénat', 'pika', 'ki-oon', 'kioon', 'star comics', 'jpop',
    'j-pop', 'carlsen', 'egmont', 'manga cult', 'altraverse',
}

def is_major(item):
    pub = (item.get('publisher') or '').lower()
    return any(p in pub for p in MAJOR_PUBLISHERS)

pending = [
    i for i in items
    if i.get('rarity') == 'rare'
    and not i.get('rarity_verified_at')
    and i.get('product_type') in AMBIGUOUS_TYPES
    and is_major(i)
]

# Agrupar por edition_key; tomar el representativo de mayor score
by_edition = defaultdict(list)
standalone = []
for item in pending:
    ek = item.get('edition_key')
    if ek:
        by_edition[ek].append(item)
    else:
        standalone.append(item)

candidates = []
for ek, group in by_edition.items():
    rep = max(group, key=lambda i: i.get('score') or 0)
    candidates.append({
        'edition_key': ek,
        'title': rep.get('title', ''),
        'series_display': rep.get('series_display', ''),
        'edition_display': rep.get('edition_display', ''),
        'publisher': rep.get('publisher', ''),
        'country': rep.get('country', ''),
        'product_type': rep.get('product_type', ''),
        'release_date': rep.get('release_date', ''),
        'isbn': rep.get('isbn', ''),
        'n_volumes': len(group),
        'url': rep.get('url', ''),
    })
for item in standalone:
    candidates.append({
        'edition_key': None,
        'title': item.get('title', ''),
        'series_display': item.get('series_display', ''),
        'edition_display': item.get('edition_display', ''),
        'publisher': item.get('publisher', ''),
        'country': item.get('country', ''),
        'product_type': item.get('product_type', ''),
        'release_date': item.get('release_date', ''),
        'isbn': item.get('isbn', ''),
        'n_volumes': 1,
        'url': item.get('url', ''),
    })

# Cap a 60 para no exceder créditos en una corrida
MAX_CANDIDATES = 60
if len(candidates) > MAX_CANDIDATES:
    print(f"⚠️  {len(candidates)} candidatos — procesando los primeros {MAX_CANDIDATES}.")
    candidates = candidates[:MAX_CANDIDATES]

print(f"\nEdiciones a verificar: {len(candidates)}")
for c in candidates[:10]:
    print(f"  [{c['product_type']:8s}] {c['title'][:55]} ({c['publisher']}) — {c['n_volumes']} vol(s)")
if len(candidates) > 10:
    print(f"  ... y {len(candidates)-10} más")
```

Muestra los candidatos al usuario antes de buscar.

## Step 2 — Búsqueda web por edición

Para cada candidato, buscar en el retailer principal del país si está en stock.

**Reglas de búsqueda:**
- Francia → `amazon.fr` o `fnac.com`
- Italia → `amazon.it`
- Alemania → `amazon.de`
- España → `amazon.es`
- Estados Unidos → `amazon.com`
- Japón → `cdjapan.co.jp` o `amazon.co.jp`
- Brasil → `amazon.com.br`
- Otros → `amazon.com`

**Query:** `"{title}" site:amazon.{tld}` o `"{series_display} {edition_display}" {publisher}`

**Decisión:**
- Encontrado con "Añadir al carrito" / "In Stock" / "disponible" → `common`
- Encontrado pero "agotado" / "no disponible" / solo usados → `rare` (mantener)
- No encontrado → `rare` (mantener)

**Atajos (sin buscar):**
- `release_date` del último año + publisher grande + `product_type=manga` → `common` directamente
- `product_type=artbook` + sin `release_date` + 1 fuente → `rare` (no hay suficiente info)

Guarda los resultados en `/tmp/rarity_validation_results.json`:
```json
[
  {
    "edition_key": "berserk-darkhorse-deluxe",
    "rarity": "common",
    "rationale": "In stock amazon.com $22.49",
    "url": "https://..."
  },
  ...
]
```

## Step 3 — Aplicar resultados al corpus

```python
import json, os, datetime as dt

# Cargar resultados
results = json.load(open('/tmp/rarity_validation_results.json'))
result_map = {r['edition_key']: r for r in results if r.get('edition_key')}

# Cargar items
items = [json.loads(l) for l in open('data/items.jsonl') if l.strip()]

now = dt.datetime.now(dt.timezone.utc).isoformat()
updated = 0
for item in items:
    if item.get('rarity_verified_at'):
        continue  # ya verificado, no tocar
    ek = item.get('edition_key')
    if ek and ek in result_map:
        res = result_map[ek]
        new_rarity = res['rarity']
        # Nunca degradar: si tenía super_rare/ultra_rare, no bajar a common/rare
        current = item.get('rarity', 'rare')
        if current in ('super_rare', 'ultra_rare'):
            pass  # no tocar
        else:
            item['rarity'] = new_rarity
            item['rarity_verified_at'] = now
            updated += 1

print(f"Items actualizados: {updated}")

# Escribir
from manga_watch import backup_and_rotate  # type: ignore
import sys; sys.path.insert(0, 'scripts')
from manga_watch import backup_and_rotate

backup_and_rotate('data/items.jsonl', 'validate-rarity')
tmp = 'data/items.jsonl.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    for item in items:
        f.write(json.dumps(item, ensure_ascii=False) + '\n')
os.replace(tmp, 'data/items.jsonl')
print("✓ data/items.jsonl actualizado")
```

## Step 4 — Reporte final

```python
import json
from collections import Counter

items = [json.loads(l) for l in open('data/items.jsonl') if l.strip()]
c = Counter(i.get('rarity') for i in items)
verified = sum(1 for i in items if i.get('rarity_verified_at'))

print("\n=== RESULTADO ===")
print(f"Verificados en esta corrida: {updated}")
print(f"Total items con rarity_verified_at: {verified}")
print(f"\nDistribución actual:")
for tier in ['common', 'rare', 'super_rare', 'ultra_rare']:
    print(f"  {tier:12s}: {c.get(tier, 0):5d}")
```

## Notas de implementación

**Scope acotado por diseño:**
- Solo `product_type` en `{boxset, artbook, fanbook, manga}` — los `manga` regulares solo si son de publisher grande (probable que haya deluxe en catálogo activo).
- Solo publishers grandes — los publishers pequeños/niche casi siempre son `rare`.
- Cap de 60 candidatos por corrida — evita gastar todos los créditos en una sola llamada.
- Agrupación por `edition_key` — 1 búsqueda por edición, no por volumen.

**Campo `rarity_verified_at`:**
- ISO timestamp UTC de cuándo se verificó vía web search.
- Un item con `rarity_verified_at` no se re-verifica en corridas futuras.
- Sticky en `append_jsonl` (igual que `rarity`): un re-scrape no lo borra.
- Si querés re-verificar todo, eliminar el campo manualmente o con:
  ```python
  for item in items:
      item.pop('rarity_verified_at', None)
  ```

**Cuándo correr:**
- Después de un scrape grande que agregó boxsets/artbooks nuevos.
- No necesita correr después de scrapes pequeños (delta diario) — el default `rare` está bien.
- No integrar en `/watch-standardize-catalog` para no inflar el costo de tokens.
