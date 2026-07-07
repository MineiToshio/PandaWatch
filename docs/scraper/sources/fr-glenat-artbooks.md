# Fuente: Glénat Art Books (Francia)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-07-07.

> Esta ficha cubre SÓLO la entrada `"FR - Glénat Art Books"`. La línea manga
> (`"FR - Glénat Manga Nouveautés"`) tiene su propia ficha:
> [fr-glenat.md](fr-glenat.md). Se separaron porque, desde 2026-07-07, cada
> entrada requiere un `kind` distinto (ver §2).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Glénat Art Books (Francia) |
| **URL base** | `https://www.glenat.com` |
| **Índice / punto de entrada** | `https://www.glenat.com/livres-keywords-art-book/` |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `js` (cambiado desde `html` el 2026-07-07, ver §2) |
| **`source_class`** | `official` |
| **País(es)** | Francia (`Francia`) — el país va al edition_key |
| **Idioma(s)** | Francés (FR) |
| **Cobertura** | Art books / libros de ilustraciones de la línea manga de Glénat |
| **Aporte al corpus** | 0 items al corte (histórico: 0 con HTTP 200, ver §8) |
| **Parser / módulo** | Entrada en `sources.yml` (extractor genérico HTML; requiere `--enable-js`) |

**Por qué importa / qué aporta de único**: los art books son un formato premium que
otras fuentes no siempre capturan; Glénat es una de las pocas editoriales FR que
mantiene un listado dedicado para ellos.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: un único listado por keyword
  (`/livres-keywords-art-book/`), sin paginación configurada.
- **Estructura del HTML/feed**: **el sitio migró a Next.js con hidratación
  client-side** (detectado en la auditoría de ingestión 2026-07-07). El HTML que
  llega por `requests` (sin ejecutar JS) ya NO trae el grid de productos — los ~24
  art books del listado quedan invisibles para el extractor genérico estático.
- **Identificador de producto**: URL canónica de la ficha en `glenat.com`.
- **Anti-bot / quirks**: no es anti-bot — es renderizado client-side puro (React/Next
  hydration). Requiere `--enable-js` (Playwright) para ver el grid.
- **Calidad de imágenes**: {{pendiente: no determinada — sin items en el corpus}}.

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: `"FR - Glénat Art Books"` (`publisher: Glénat Manga`,
  `country: Francia`, `source_class: official`, `kind: js`, `enabled: true`, tags
  `["artbook", "official", "france"]`).
- **Cambio de `kind` (2026-07-07)**: pasó de `html` a `js` (`sources.yml:974`) tras
  confirmar que el HTML estático no trae el grid. Con `kind: js` la fuente ahora se
  procesa vía el worker Playwright dedicado (gotcha #12) cuando el scrape corre con
  `--enable-js`; sin ese flag, la fuente sigue sin aportar items (no crashea, sólo
  queda en 0).
- Sin parser propio: usa el extractor genérico de listings sobre el HTML ya
  renderizado por Playwright.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Síntoma histórico: 0 items pese a HTTP 200** — la fuente respondía 200 OK en
  cada corrida (no había error de red ni bloqueo visible), pero nunca aportó items.
  Ese patrón es **indistinguible de una fuente vacía** cuando no hay un baseline de
  yield esperado — el bug pasó desapercibido varios ciclos de scrape hasta la
  auditoría de ingestión 2026-07-07, que abrió el HTML crudo y confirmó que el grid
  de productos no estaba (sólo el shell de Next.js). ✅ Diagnóstico: hidratación
  client-side, no anti-bot ni selector roto. Fix: `kind: js` para forzar
  renderizado con Playwright.
- **Segundo bug (2026-07-07): el fetch js ya trae los productos, pero se perdían en
  el gate de coleccionable.** Con `--enable-js` el grid se rendea y produce ~24
  productos / ~16 candidatos, pero **0 llegaban al corpus**. Causa: los artbooks se
  llaman "L'Art de Berserk", "Dragon Ball Le super art book", "One Piece Color Walk",
  "Rumiko Takahashi Colors" — `is_likely_manga()` los reconoce (patrón STRONG
  `\bL['’]?art\s+de\b` / "art book"), pero `detect_signals()` NO tenía el vocabulario
  FR de artbook → score=0 (mueren en `if score <= 0: continue`) o, con señal,
  `derive_product_type` caía en "manga" e `is_collectible_edition` los rechazaba como
  `regular_tomo`. ✅ Fix (gotcha #116): **bypass por tag `artbook`** en el gate de
  coleccionable (`is_curated_collectible_source`, análogo a `variant-catalog`; fuerza
  `product_type="artbook"`) + **vocabulario FR de artbook** en `KEYWORD_RULES`
  ("l'art de", "super art book", "color walk", "beaux livres", "…Colors" anclado a
  fin). Los 2 ítems de BD occidental de la misma página (**Cromwell**, **Druillet**)
  NO se cuelan: sin keyword de artbook dan score=0 y mueren en el gate de señal, muy
  antes del bypass (que además siempre corre DESPUÉS de `is_likely_manga`).
- **Inestabilidad de hidratación Next.js (a vigilar).** Se observó **16 candidatos en
  producción vs. 1-2 en un re-fetch inmediato** de la misma URL — el render js no es
  determinista corrida a corrida (timing de hidratación / lazy-load del grid). El
  yield de esta fuente puede variar entre scrapes por esta razón; no asumir que "menos
  items que la vez pasada" == regresión del parser.
- **Riesgo residual (BD con "L'Art de").** Un artbook de BD occidental titulado
  literalmente "L'Art de \<autor-BD\>" SÍ dispara el STRONG hint de `is_likely_manga`
  y el nuevo keyword `l'art de` → pasaría el bypass. Los Cromwell/Druillet actuales no
  usan esa forma (por eso caen por score=0), pero si aparece uno, agregar esa
  franquicia BD a `data/comics_blacklist.yml` (único filtro que distingue "L'Art de
  Berserk" —manga— de "L'Art de Druillet" —BD—; la purity no basta porque el STRONG
  hint pasa igual en `mixed`).
- **Lección para el `source_health` / auditorías futuras**: un 200 sostenido con 0
  items no es evidencia de "fuente sin contenido nuevo" — hay que abrir el HTML
  crudo al menos una vez por fuente nueva/migrada para confirmar que el contenido
  esperado efectivamente está en el HTML servido sin JS.

---

## 9. Pendientes / limitaciones conocidas

- **Verificar aporte real tras el cambio a `kind: js` + fix del gate de
  coleccionable**: los fixes se aplicaron (2026-07-07: `kind: js` y bypass artbook +
  vocabulario FR, gotcha #116); falta una corrida con `--enable-js` que confirme que
  el grid de ~24 art books efectivamente se captura y llega al corpus. Ojo con la
  inestabilidad de hidratación (§8): el conteo puede variar entre corridas.
- **Requiere Playwright instalado** (`pip install playwright && playwright install
  chromium`) y correr el scrape con `--enable-js`; sin eso la fuente queda en 0
  igual que antes (silenciosamente).

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente (requiere --enable-js para que kind:js funcione):
.venv/bin/python scripts/manga_watch.py --only-source "FR - Glénat Art Books" --enable-js

# Validar (gate estructural, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver items reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "livres-keywords-art-book"
def hit(it):
    blobs=[it.get('url','') or '']+[ (s.get('url','') or '') for s in it.get('sources',[]) ]
    return any(NEEDLE in b for b in blobs)
items=[json.loads(l) for l in open("data/items.jsonl") if l.strip()]
sel=[it for it in items if hit(it)]
print("items:", len(sel))
PY
```

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`, 0 duras)
→ tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful, actualiza
esta ficha.
