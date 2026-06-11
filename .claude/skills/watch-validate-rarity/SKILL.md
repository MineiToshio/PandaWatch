---
name: watch-validate-rarity
description: Verifica vía web los items cuya rareza "rare" viene de INCERTIDUMBRE (fallback de fuente de referencia o retailer_exclusive sin stock verificado) — no los que tienen evidencia estructural. Escribe stock_status como evidencia y re-deriva la rareza con el modelo (in_stock→common, agotado→rare/super_rare). Solo procesa items sin rarity_verified_at (incremental). Correr después de scrapes grandes o cuando quieras validar items nuevos.
argument-hint: "[--limit N] [--dry-run]"
---

# Validate rarity — verificación web de los rares por incertidumbre

Bajo el modelo default-common (2026-06-10), un item es `rare` por una de dos vías:

1. **Evidencia estructural** — keyword/patrón de no-reimpresión (限定版, édition
   collector FR, furoku, print run documentado…). Que esté en stock HOY no
   refuta que no se reimprime → **esta skill NO los demota** (disponibilidad
   momentánea ≠ probabilidad estructural; ver docstring de set_rarity.py).
2. **Incertidumbre** — fallback de fuente de referencia (solo Mangavariant/
   Sumikko/BooksPrivilege lo catalogan) o `retailer_exclusive` sin stock
   verificado. **Este es el universo de la skill**: la web puede resolver la
   incertidumbre en cualquiera de los dos sentidos.

El veredicto se escribe como **evidencia** (`stock_status` + `stock_checked_at`)
y la rareza se **re-deriva con `derive_rarity_tier()`** — la skill nunca asigna
un tier a mano. Consecuencias del modelo:
- `in_stock` → common… **salvo** que el item además tenga evidencia estructural
  más abajo en la cascada (p. ej. "tiratura limitata"): queda `rare` y el "=" es
  CORRECTO, no un bug — el check igual aportó el `stock_status`.
- `out_of_stock` → rare confirmado; si además tiene signal `retailer_exclusive`
  → **promoción a super_rare** (caso real piloto: Boruto Fnac Exclusive
  "Esaurito" → super_rare).
- `not_found` → rare confirmado (consistente con "solo lo documenta una DB de
  coleccionismo" / "el canal exclusivo ya no lo lista").
- `inconclusive` → **no se toca NADA** (ni stock_status ni rarity_verified_at):
  el item queda pendiente y se reintenta en una corrida futura.

Todo item con veredicto firme queda con `rarity_verified_at` (no se re-verifica;
sticky ante re-scrapes; `set_rarity.py --force` lo respeta).

## Step 0 — Seleccionar candidatos (solo rares por incertidumbre)

```python
import json, sys, collections
sys.path.insert(0, 'scripts')
from manga_watch import (_TOKUTEN_SOURCES, _SINGLE_RUN_KEYWORDS, _SINGLE_RUN_PATTERNS,
                         _extract_print_run, _is_reference_only_source, is_approved)

items = [json.loads(l) for l in open('data/items.jsonl') if l.strip()]

def item_sources(item):
    names = [s.get('name') or s.get('source') or '' for s in (item.get('sources') or [])]
    return [n for n in names if n] or [item.get('source') or '']

def uncertainty_reason(item):
    """'referencia' | 'retailer_exclusive' | None si su rare tiene evidencia estructural.
    Replica el ORDEN de las ramas rare de derive_rarity_tier. NOTA: un item
    retailer_exclusive puede tener ADEMÁS keywords estructurales más abajo —
    sigue siendo candidato porque un 'out_of_stock' lo PROMUEVE a super_rare
    (con 'in_stock' se queda en rare por la keyword: resultado '=' esperado)."""
    text = f"{item.get('title','')} {item.get('description','')}".lower()
    src = (item.get('source') or '').lower()
    if _extract_print_run(text) is not None: return None
    if item.get('stock_status') == 'out_of_stock': return None   # ya hay evidencia
    if 'retailer_exclusive' in (item.get('signal_types') or []): return 'retailer_exclusive'
    if any(t in src for t in _TOKUTEN_SOURCES): return None
    if any(kw in text for kw in _SINGLE_RUN_KEYWORDS): return None
    if any(p.search(text) for p in _SINGLE_RUN_PATTERNS): return None
    if all(_is_reference_only_source(s) for s in item_sources(item)): return 'referencia'
    return None

pending = []
for i in items:
    if i.get('rarity') != 'rare' or i.get('rarity_verified_at') or is_approved(i):
        continue
    reason = uncertainty_reason(i)
    if reason:
        pending.append((reason, i))

print(f"Total items: {len(items)}")
print(f"Rares por incertidumbre pendientes: {len(pending)}")
print(dict(collections.Counter(r for r, _ in pending)))
```

Si 0 pendientes → reportar y parar.

## Step 1 — Agrupar por edición y priorizar

Una verificación por **edición** (no por volumen): el representativo de mayor
score responde por el grupo. La aplicación del Step 3 alcanza SOLO a los items
candidatos del grupo (no a todo el edition_key — un volumen hermano ya common o
ya verificado no se toca).

```python
# ... continúa del bloque anterior (misma sesión de python)
by_group = collections.defaultdict(list)
for reason, item in pending:
    gid = item.get('edition_key') or item.get('slug') or item.get('url')
    by_group[gid].append((reason, item))

def priority(group):
    """retailer_exclusive primero (puede PROMOVER a super_rare); luego
    mercados occidentales (verificación más confiable que JP); luego impacto."""
    reasons = {r for r, _ in group}
    rep = max((i for _, i in group), key=lambda i: i.get('score') or 0)
    western = rep.get('country') not in ('Japón', 'Tailandia', 'Taiwán', 'Vietnam')
    return (0 if 'retailer_exclusive' in reasons else 1, 0 if western else 1, -len(group))

groups = sorted(by_group.items(), key=lambda kv: priority(kv[1]))

LIMIT = 40  # honrar --limit si el usuario lo pasó
groups = groups[:LIMIT]

candidates = []
for gid, group in groups:
    rep = max((i for _, i in group), key=lambda i: i.get('score') or 0)
    candidates.append({
        'group_id': gid,           # ¡usar EXACTAMENTE este id en los resultados!
        'reason': sorted({r for r, _ in group})[0],
        'title': rep.get('title', ''),
        'series_display': rep.get('series_display', ''),
        'edition_display': rep.get('edition_display', ''),
        'publisher': rep.get('publisher', ''),
        'country': rep.get('country', ''),
        'release_date': rep.get('release_date', ''),
        'isbn': rep.get('isbn', ''),
        'n_volumes': len(group),
        'url': rep.get('url', ''),
        'price': rep.get('price', ''),   # precio de lista conocido — referencia para el veredicto
    })

print(f"\nEdiciones a verificar ({len(candidates)}):")
for c in candidates:
    print(f"  [{c['reason']:18s}] {c['title'][:50]:50s} ({c['publisher'][:18]}, {c['country']}) — {c['n_volumes']} item(s)")
    print(f"      url: {c['url'][:90]}  isbn: {c['isbn'] or '-'}")

json.dump(candidates, open('/tmp/rarity_validation_candidates.json', 'w'), ensure_ascii=False, indent=1)
```

Muestra los candidatos al usuario antes de buscar.

## Step 2 — Verificación web por edición (escalera de métodos)

Para cada candidato, en este orden — parar en el primer veredicto firme:

1. **La URL del item, si ya es de retailer** (muchos retailer_exclusive de
   AnimeClick traen el link de Amazon/tienda): fetch directo.
   - WebFetch funciona en tiendas chicas/Shopify (mangadreams.it, mycomics.it,
     mangayo.it) y en tiendas de publisher (starcomics.com, j-pop.it).
   - WebFetch **NO funciona** en Amazon (HTTP 500 anti-bot) ni panini.it
     (waiting room queue-it) → esos van por Chrome (punto 3).
2. **Tienda del publisher** del país (starcomics.com, j-pop.it, normaeditorial.com,
   etc.) — es el mejor ground truth: si el publisher aún lo vende, es common.
   Caso real piloto: Amazon ambiguo pero starcomics.com con "Acquista ora" → common.
3. **Amazon del país vía Chrome** (`/dp/{ISBN10}` si hay ISBN). NO usar
   get_page_text (página entera = ~3k tokens); extraer SOLO selectores con
   javascript_tool, ideal en browser_batch de a varios:
   ```js
   const g=(s)=>document.querySelector(s)?.textContent.trim().slice(0,120)||'';
   JSON.stringify({title:g('#productTitle'),avail:g('#availability'),
                   price:g('.a-price .a-offscreen'),buybox:g('#buybox-see-all-buying-choices')||g('#outOfStock')})
   ```
4. **WebSearch** solo para DESCUBRIR la ficha (query: `"{isbn}"` o
   `"{title}" {publisher} site:amazon.{tld}`) — los snippets NO sirven como
   veredicto de stock; con la URL hallada volver a 1-3.

**Lectura del resultado de Amazon (gotchas reales del piloto):**
- `avail` = "Disponibilità immediata" / "In stock" / "Only N left" con precio
  ≈ lista → `in_stock`.
- `avail` = "Non disponibile" / solo ofertas de usados / marketplace-only con
  precio ≥1.5× lista → `out_of_stock` (mercado secundario = señal de rare).
- `buybox` = "See All Buying Options" SIN `avail` → buy box geolocalizado
  (cuenta sin dirección local): **`inconclusive`**, NO es out_of_stock.
- "Only N left" SIN precio visible, o ASIN que devuelve página vacía →
  `inconclusive`.
- Búsqueda de Amazon sin resultados para una "esclusiva Amazon" → `not_found`
  (el canal exclusivo ya no lo lista — rare confirmado).

**Veredicto — precisión > recall** (un common equivocado ESCONDE un item
difícil; ante la duda, `inconclusive`):
- `in_stock` — señal explícita de disponibilidad en retail a precio ~lista
  (usar `price` del candidato como referencia), del retailer primario o tienda
  del publisher. Marketplace de terceros con sobreprecio NO cuenta.
- `out_of_stock` — la ficha EXISTE pero figura "agotado" / "épuisé" /
  "esaurito" / "ausverkauft" / "sold out" / 品切れ / solo usados / solo
  marketplace ≥1.5× lista.
- `not_found` — sin ficha en el retail del país tras buscar. NO confundir con
  ambigüedad.
- `inconclusive` — cualquier ambigüedad (geo, captcha, página vacía, edición
  dudosa, otro país). No estampa nada; se reintenta en el futuro.

Cuidado con el **país**: la edición es del país del item (regla dura del
owner). Encontrar la edición US en stock NO resuelve la edición FR.

Guarda `/tmp/rarity_validation_results.json` (group_id EXACTO del candidato):
```json
[
  {"group_id": "phantom-seer-star-limited-it",
   "verdict": "in_stock",
   "rationale": "starcomics.com (publisher) — 'Acquista ora', €10,50",
   "evidence_url": "https://..."},
  ...
]
```
`verdict` ∈ {`in_stock`, `out_of_stock`, `not_found`, `inconclusive`}. Todo
candidato buscado debe tener una entrada.

## Step 3 — Aplicar: stock_status + re-derivación con el modelo

Aplica SOLO a los items que eran candidatos (mismo filtro del Step 0) — nunca a
todo el edition_key (los hermanos ya common/verificados no se tocan).

```python
import json, os, sys, datetime as dt
from pathlib import Path
sys.path.insert(0, 'scripts')   # ANTES del import — el wrapper de la raíz no exporta estos símbolos (gotcha #64)
from manga_watch import (derive_rarity_tier, backup_and_rotate, is_approved,
                         _TOKUTEN_SOURCES, _SINGLE_RUN_KEYWORDS, _SINGLE_RUN_PATTERNS,
                         _extract_print_run, _is_reference_only_source)

DRY_RUN = False  # True si el usuario pasó --dry-run

results = {r['group_id']: r for r in json.load(open('/tmp/rarity_validation_results.json'))}
items = [json.loads(l) for l in open('data/items.jsonl') if l.strip()]

def item_sources(item):
    names = [s.get('name') or s.get('source') or '' for s in (item.get('sources') or [])]
    return [n for n in names if n] or [item.get('source') or '']

def uncertainty_reason(item):
    text = f"{item.get('title','')} {item.get('description','')}".lower()
    src = (item.get('source') or '').lower()
    if _extract_print_run(text) is not None: return None
    if item.get('stock_status') == 'out_of_stock': return None
    if 'retailer_exclusive' in (item.get('signal_types') or []): return 'retailer_exclusive'
    if any(t in src for t in _TOKUTEN_SOURCES): return None
    if any(kw in text for kw in _SINGLE_RUN_KEYWORDS): return None
    if any(p.search(text) for p in _SINGLE_RUN_PATTERNS): return None
    if all(_is_reference_only_source(s) for s in item_sources(item)): return 'referencia'
    return None

candidate_ids = set()
for i in items:
    if i.get('rarity') != 'rare' or i.get('rarity_verified_at') or is_approved(i):
        continue
    if uncertainty_reason(i):
        candidate_ids.add(id(i))

now = dt.datetime.now(dt.timezone.utc).isoformat()
updated, inconclusive, log = 0, 0, []
for item in items:
    if id(item) not in candidate_ids:
        continue
    gid = item.get('edition_key') or item.get('slug') or item.get('url')
    res = results.get(gid)
    if not res:
        continue
    if res['verdict'] == 'inconclusive':
        inconclusive += 1
        continue
    old = item.get('rarity', '')
    if res['verdict'] in ('in_stock', 'out_of_stock'):
        item['stock_status'] = res['verdict']
        item['stock_checked_at'] = now
    # Re-derivar con el modelo — la skill no asigna tiers a mano.
    item['rarity'] = derive_rarity_tier(
        signal_types=item.get('signal_types') or [],
        source=item.get('source') or '',
        description=item.get('description') or '',
        title=item.get('title') or '',
        publisher=item.get('publisher') or '',
        stock_status=item.get('stock_status') or '',
        sources=item_sources(item),
    )
    item['rarity_verified_at'] = now
    updated += 1
    log.append({'slug': item.get('slug'), 'group_id': gid, 'old': old,
                'new': item['rarity'], 'verdict': res['verdict'],
                'rationale': res.get('rationale', ''),
                'evidence_url': res.get('evidence_url', ''), 'at': now})

print(f"Items {'que cambiarían' if DRY_RUN else 'actualizados'}: {updated} | inconclusos (sin tocar): {inconclusive}")
for e in log:
    mark = '→' if e['old'] != e['new'] else '='
    print(f"  {e['old']:5s} {mark} {e['new']:10s} [{e['verdict']:12s}] {e['slug']}")

if not DRY_RUN and updated:
    backup_and_rotate(Path('data/items.jsonl'), 'validate-rarity')   # Path, NO str
    tmp = 'data/items.jsonl.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    os.replace(tmp, 'data/items.jsonl')
    with open('data/diagnostics/rarity_validation_log.jsonl', 'a', encoding='utf-8') as f:
        for e in log:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')
    print("✓ data/items.jsonl actualizado + log en data/diagnostics/rarity_validation_log.jsonl")
```

## Step 4 — Verificación y reporte final

```bash
.venv/bin/python scripts/validate_corpus.py 2>&1 | tail -2
# El guard debe saltarse los recién verificados y no driftear:
.venv/bin/python scripts/retrofit/set_rarity.py --force --dry-run 2>&1 | grep -E "verificados|cambiarían"
```

```python
import json
from collections import Counter
items = [json.loads(l) for l in open('data/items.jsonl') if l.strip()]
c = Counter(i.get('rarity') for i in items)
verified = sum(1 for i in items if i.get('rarity_verified_at'))
print(f"Total con rarity_verified_at: {verified}")
for tier in ['common', 'rare', 'super_rare', 'ultra_rare']:
    print(f"  {tier:12s}: {c.get(tier, 0):5d}")
```

Cerrar con: ediciones verificadas, veredictos por tipo (in_stock/out_of_stock/
not_found/inconclusive), items que cambiaron de tier y en qué dirección
(common ↔ rare ↔ super_rare), y pendientes para la próxima corrida (los
inconclusos vuelven a entrar).

## Notas de implementación

**Scope por diseño:**
- SOLO rares por incertidumbre (fallback referencia / retailer_exclusive). Los
  rares con evidencia estructural no se demotan — su rareza no depende del
  stock de hoy. Un retailer_exclusive con evidencia estructural SÍ es candidato
  (out_of_stock lo promueve a super_rare; in_stock lo deja en rare → "=").
- Prioridad: retailer_exclusive primero, después mercados occidentales (la
  verificación JP es poco confiable), después tamaño del grupo.
- Cap default 40 ediciones por corrida (`--limit N`). ~1 verificación por edición.
- Items aprobados (`is_approved`) y ya verificados: intocables.

**`rarity_verified_at` / `stock_status`:**
- `rarity_verified_at`: ISO UTC; el item no se re-verifica; `set_rarity.py
  --force` lo respeta (override `--include-verified`).
- `stock_status` + `stock_checked_at`: la evidencia persistida; misma interfaz
  que llenará el futuro retrofit `check_stock.py`. La skill es la variante
  manual/web de ese contrato.
- Stock = evidencia a nivel EDICIÓN (se verifica el representativo), pero se
  aplica SOLO a los items candidatos del grupo.
- Log de auditoría: `data/diagnostics/rarity_validation_log.jsonl` (append).

**Cuándo correr:**
- Después de scrapes grandes con items nuevos de Mangavariant/fuentes de
  referencia, o cuando el contador del Step 0 crezca.
- No integrar en `/watch-standardize-catalog` (costo de tokens).
