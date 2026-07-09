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
   Sumikko/BooksPrivilege —esta última deshabilitada, solo datos históricos— lo catalogan) o `retailer_exclusive` sin stock
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

## Step 0/1 — Seleccionar, agrupar y priorizar candidatos

Compilado a `scripts/audit/rarity_candidates.py` (auditoría Fable 2026-07-08,
hallazgo F5 — antes `uncertainty_reason()` vivía DUPLICADA dos veces en este
documento, una copia manual del orden de ramas `rare` de `derive_rarity_tier()`
que podía driftear sin que ningún test lo detectara). `rarity_uncertainty_reason()`
es ahora la ÚNICA implementación — la usan tanto este script como
`apply_rarity_verdicts.py` (Step 3), y un test de coherencia
(`tests/test_rarity_candidates.py`) fija, con un fixture por rama, que el orden
coincide con `derive_rarity_tier()` en `manga_watch.py`.

```bash
.venv/bin/python scripts/audit/rarity_candidates.py [--limit N]
```

Selecciona items `rarity="rare"` sin `rarity_verified_at` ni `approved_at` cuyo
`rare` viene de INCERTIDUMBRE (`retailer_exclusive` sin stock verificado, o
fuente de referencia sin otra evidencia — nunca los que tienen evidencia
estructural), agrupa por edición (`edition_key` > `slug` > `url` — una
verificación por edición, no por volumen) y prioriza: `retailer_exclusive`
primero (puede promover a `super_rare`), luego mercados occidentales
(verificación más confiable que JP), luego tamaño del grupo. Tope default 40
ediciones (`--limit N`, honrá el que pasó el usuario al invocar el skill).

Imprime la lista priorizada en pantalla (título, editorial, país, ISBN, url) y
escribe `data/diagnostics/rarity_validation_candidates.json` con el mismo
contenido — el Step 2 usa `group_id` de ahí para indexar los veredictos web.

Si el script reporta "Rares por incertidumbre pendientes: 0" → reportar al
usuario y parar.

Mostrá la salida del script al usuario antes de pasar al Step 2.

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

Guarda `data/diagnostics/rarity_validation_results.json` (group_id EXACTO del candidato):
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

Compilado a `scripts/retrofit/apply_rarity_verdicts.py` (auditoría Fable
2026-07-08, hallazgo F5 — reemplaza el snippet embebido que DUPLICABA
`uncertainty_reason()` por segunda vez). Re-selecciona candidatos con la MISMA
`rarity_uncertainty_reason()` del Step 0/1 (`scripts/audit/rarity_candidates.py`,
fuente única) por si el universo cambió entre selección y aplicación, y aplica
SOLO a esos — nunca a todo el `edition_key` (los hermanos ya common/verificados
no se tocan).

```bash
.venv/bin/python scripts/retrofit/apply_rarity_verdicts.py [--dry-run]
```

Lee `data/diagnostics/rarity_validation_results.json` (el archivo del Step 2),
escribe `stock_status`/`stock_checked_at` como EVIDENCIA (solo para veredictos
`in_stock`/`out_of_stock`) y **re-deriva `rarity` con `derive_rarity_tier()`** —
el script nunca asigna un tier a mano. `inconclusive` no toca nada (ni
`stock_status` ni `rarity_verified_at`). Golden records (`approved_at`) se
saltean. Backupea `items.jsonl` antes de escribir y apendea el log de auditoría
a `data/diagnostics/rarity_validation_log.jsonl`. Imprime el resumen
(actualizados / inconclusos / aprobados saltados) y el detalle por item
(`old → new [verdict] slug`).

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
  referencia, o cuando el contador del Step 0/1 crezca.
- No integrar en `/watch-standardize-catalog` (costo de tokens).

**Tier de modelo recomendado (auditoría Fable 2026-07-08, hallazgo F10)**: el
skill corre en el hilo principal. Los Steps 0/1/3 son 100% mecánicos (scripts
determinísticos, cero LLM); el Step 2 (verificación web) sí razona — lee
buybox/geolocalización/ambigüedad de página y decide un veredicto con
criterio. **`sonnet` es suficiente** para ese razonamiento acotado; no hace
falta `opus`.
