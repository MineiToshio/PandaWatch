---
name: watch-evaluate-sources
description: Evaluate candidate data sources before adding them to the scraping pipeline. Pass a list of URLs or source names in any format. The skill inspects each site, samples real items, checks data quality against catalog requirements, estimates corpus overlap, and outputs a concise viability table — no implementation.
argument-hint: "<url-o-nombre> [url-o-nombre ...]"
---

# Evaluate candidate data sources

Audita fuentes candidatas ANTES de implementarlas. Output: reporte de viabilidad conciso. Sin implementación.

## Contexto del catálogo

PandaWatch rastrea **ediciones especiales físicas de manga**:
- ✅ Edición Limitada / Collector's / Deluxe / Hardcover
- ✅ Variant covers (portadas alternativas)
- ✅ Box sets / slipcases / cofres
- ✅ Artbooks / libros de ilustraciones
- ✅ Kanzenban / ediciones completas
- ✅ Ediciones con extras (SOLO si la fuente tiene FOTO del extra)
- ❌ Tomos regulares sin qualifier especial
- ❌ Noticias / blogs / anuncios
- ❌ Merchandise (figuras, posters, ropa)
- ❌ Contenido digital

**Fuentes ya activas** (para calcular overlap y detectar redundancia): NO hay
tabla fija acá — `sources.yml` es la única fuente de verdad y cambia seguido
(63 enabled de 151 al 2026-07-11; se podó/agregó varias veces desde que este
doc tenía una tabla hardcodeada — hallazgo ES-2, auditoría Fable 2026-07-11:
esa tabla no incluía las fuentes agregadas en junio 2026, PL-Mangarden ×2,
PL-Mangastore, KR-Aladin, todas aprobadas usando ESTE MISMO skill). El Step 0
carga la lista viva agrupada por país — ver ahí.

**Lección crítica — BooksPrivilege (2026-05-26)**: tenía 11,000 items de
店舗特典 (bonuses de tienda para tomos regulares). El 99.7% eran tomos
normales con postal/acrylic stand de regalo. La foto era SOLO la portada
del manga, NO del extra. Sin foto del extra = inútil para un catálogo visual
público. Se deshabilitó y se limpiaron 11,145 items. **Cualquier fuente que
cubra bonuses/extras/tokuten DEBE tener foto del extra — si no, es ❌ automático.**

---

## Step 0 — Parsear input + cargar fuentes activas en vivo

Extrae la lista de fuentes candidatas del mensaje del usuario. Puede ser
URLs, nombres, texto libre o mixto. Normaliza a lista de `{id, url, contexto_extra}`.

Además, cargá la lista de fuentes `enabled` de `sources.yml` agrupada por país
(reemplaza la tabla hardcodeada — hallazgo ES-2). Usa `load_active_sources_by_country()`
de `scripts/audit/source_overlap.py` (no reimplementes el parseo de sources.yml):

```python
import sys
sys.path.insert(0, "scripts/audit")
from source_overlap import load_active_sources_by_country

by_country = load_active_sources_by_country("sources.yml")
for country, entries in sorted(by_country.items()):
    print(f"{country or '(global/wiki)'}:")
    for e in entries:
        print(f"  - {e['name']} (kind={e['kind']}, purity={e['purity']})")
```

Esta lista `by_country` alimenta el criterio **C5 (Comparación con fuentes
existentes)** del Step 1 — pasala como contexto al prompt de cada subagente
(reemplazando `{FUENTES_ACTIVAS_DEL_PAIS}`, filtrado al país que cubre la
fuente candidata cuando se conoce, o la lista completa si no).

---

## Step 1 — Reconnaissance (un subagente por fuente, en paralelo)

Spawna un subagente `general-purpose` **con modelo `sonnet`** por fuente
(es investigación web con criterio pero acotada por fuente y en fan-out de N
en paralelo — Sonnet rinde muy bien en comprensión web y sale mucho más
barato que N Opus simultáneos). Prompt template:

---

**PROMPT SUBAGENTE:**

Eres un auditor de fuentes de datos para PandaWatch, un catálogo de ediciones
especiales físicas de manga. Evalúa `{URL_O_NOMBRE}` siguiendo estos pasos.

**Fuentes ya activas que cubren el país/nicho de esta candidata** (cargadas en
vivo desde `sources.yml` en el Step 0 — usalas para C5, no asumas cobertura
de memoria):

```
{FUENTES_ACTIVAS_DEL_PAIS}
```

### A. Fetch listing principal

Usa WebFetch para cargar la página de catálogo/listing. Si la URL es genérica
(solo el dominio), busca la sección de ediciones especiales / variantes /
limitadas. Entiende qué tipos de items muestra.

### B. Muestra de items

Dos etapas (auditoría Fable 2026-07-08, hallazgo F13 — 5 items daba un
intervalo de confianza muy amplio para la regla de overlap 30/70% del Step 2):

1. **Triage chico** (3-5 items): alcanza para estimar C1 (Content Fit). Si
   falla (< 20% ediciones especiales reales) → veredicto ❌ directo, no hace
   falta ampliar la muestra — cortá acá.
2. **Si C1 pasa** (borderline o pass): ampliá la muestra a **8-10 items
   totales** (variados: distintas series/editoriales si es posible) y
   fetcheá sus páginas de detalle para el resto de la rúbrica (C2-C5) y para
   que el overlap del Step 2 tenga una base más confiable.

Por cada item de la muestra final registra:

1. Título completo
2. ¿Es una edición especial real? (sí/no + por qué)
3. Campos presentes: nombre de serie, tipo de edición, editorial, imagen de portada
4. **Si el item incluye extras/bonuses/tokuten**:
   ¿Hay foto del EXTRA en sí (tapestry, acrylic stand, postal, accesorios)?
   ¿O solo la portada del manga?
   ESTO ES CRÍTICO. "Solo portada del manga" = el sitio no sirve para extras.
5. **`isbn`** (hallazgo ES-1, auditoría Fable 2026-07-11): fetcheá la detail
   page del item y capturá el ISBN si está publicado (código de barras,
   metadata, ficha técnica). Dejalo `""` si la página no lo muestra —
   NUNCA inventes un ISBN. Este campo es lo que le da al Step 2 un overlap
   real en vez de un % estimado a ojo.
6. **`series_key_guess`**: el nombre de la serie tal como aparece en el
   título/ficha (ej. "One Piece"), SIN slugificar — el Step 2 lo normaliza
   con el mismo slug que usa el pipeline. No es el `series_key` canónico del
   corpus, es tu mejor lectura del nombre de la serie desde la página.

### C. Rubrica de evaluación

**C1 — Content Fit** (falla aquí = skip el resto, veredicto ❌ directo)
- ¿Qué % del listing son ediciones especiales reales (no tomos regulares)?
- Si < 20%: FAIL. Si 20-60%: borderline. Si > 60%: pass.
- **`catalog_scope`** (hallazgo F3b, auditoría Fable 2026-07-11): además del
  ratio de ediciones especiales, preguntá explícitamente ¿qué fracción del
  listing es NO-manga (figuras, comics occidentales, cards, merch)? Esta es
  la señal que decide `purity: manga_only` vs `mixed` al dar de alta la
  fuente (ver Source.purity en manga_watch.py) — C1 medía sólo "% especiales"
  y nunca preguntaba esto, así que el purity del alta salía a ciegas.
  Reportá `"manga_only"` (catálogo cerrado a manga) o `"mixed"` (vende manga
  + otras cosas — sólo pasan items con STRONG manga hint).

**C2 — Campos mínimos** (evaluar sobre los items sampleados — 8-10 si pasó C1)
- Nombre de la serie: disponible? (s/n)
- Tipo de edición (qualifier: Limited/Deluxe/Collector/etc.): disponible? (s/n)
- Editorial/Publisher: disponible? (s/n)
- Foto de la portada/edición: disponible? (s/n)
- ⚠️ Si la fuente cubre bonuses/extras/tokuten: ¿foto del extra en sí? (s/n/n-a)
  → Si cubre extras y NO tiene foto → campo bloqueante = FAIL automático

**C3 — Escala estimada**
- ¿Cuántos items coleccionables tiene el sitio en total? (estima por paginación)
- < 50: baja prioridad / 50-500: media / 500+: alta prioridad
- ¿Últimos items añadidos? (¿sitio activo en últimos 3 meses?)

**C4 — Factibilidad técnica**
- ¿Acceso público sin login? (s/n)
- ¿Requiere JavaScript/Playwright? (s/n — agrega complejidad)
- ¿Protección anti-bot fuerte? (Cloudflare challenge, CAPTCHA) (s/n)
- ¿API pública disponible? (s/n — ideal, más estable)
- ¿HTML parseable con BeautifulSoup? (s/n)
- **Muerto vs JS-rendered** (hallazgo ES-3/ES-4, auditoría Fable 2026-07-11):
  WebFetch NO ejecuta JavaScript. Si la página vino vacía o como un esqueleto
  sin items, **antes de concluir "sitio muerto"** revisá el HTML crudo en
  busca de señales de que el contenido se hidrata client-side: `__NEXT_DATA__`,
  `__NUXT__`, bundles JS grandes (`main.*.js`, `chunk.*.js`), endpoints XHR/API
  referenciados en `<script>` inline, o un `<div id="app">`/`id="root">` casi
  vacío. Si encontrás esas señales, NO es "sitio muerto" — es candidata a
  `kind: js` (el pipeline ya soporta 17 fuentes con `kind: js`, opt-in
  `--enable-js`, gotcha #12). Si hay tools de Chrome disponibles, opcionalmente
  confirmá cargando la página con JS habilitado antes de descartar. El
  veredicto "página vacía" que mezclaba sitio muerto con JS-rendered queda
  separado en dos: ver los veredictos del Step 3.

**C5 — Comparación con fuentes existentes**
¿Ya tenemos algo que cubra el mismo nicho (mismo país + tipo de contenido)?
Usá la lista `{FUENTES_ACTIVAS_DEL_PAIS}` de arriba (cargada en vivo desde
`sources.yml`, no de memoria). Si sí: ¿esta fuente es mejor (más items, más
campos, más editoriales)? ¿O es redundante?

### D. Output (JSON estructurado, sin prose)

```json
{
  "source": "url o nombre",
  "country": "país que cubre",
  "language": "idioma del contenido",
  "content_fit": "pass|fail|borderline",
  "content_fit_note": "razón breve (1 frase)",
  "special_edition_ratio": "~X%",
  "catalog_scope": "manga_only|mixed",
  "scale_estimate": "~N items",
  "active": true,
  "last_update": "YYYY-MM o desconocido",
  "fields": {
    "series_name": true,
    "edition_type": true,
    "publisher": false,
    "cover_image": true,
    "extra_photo": null
  },
  "technical": {
    "public_access": true,
    "requires_js": false,
    "antibot": false,
    "api_available": false,
    "html_parseable": true
  },
  "existing_coverage": "ninguna|parcial|total — [nombre fuente existente si aplica]",
  "sample_items": [
    {
      "title": "...",
      "is_special_edition": true,
      "fields_found": ["series", "edition_type", "publisher", "cover_image"],
      "isbn": "",
      "series_key_guess": "...",
      "note": "..."
    }
  ],
  "preliminary_verdict": "viable|not_viable|borderline",
  "verdict_reason": "una frase"
}
```

`isbn` y `series_key_guess` (hallazgo ES-1) son los campos que el Step 2 usa
para el overlap real — `isbn` vacío (`""`) es válido y esperado si la detail
page no lo publica, NO inventes un valor para rellenar el campo.

Además de devolver este JSON como resultado del subagente, **escribilo también a
`data/diagnostics/source-eval-<id>.json`** (`<id>` = slug del nombre/dominio de la
fuente, ej. `source-eval-nueva-tienda-fr.json`) — trazabilidad de la corrida y
permite que el Step 2 lo parsee mecánicamente en vez de depender solo de lo que
el subagente devolvió en memoria.

> **Nota (auditoría Fable 2026-07-08, hallazgo F13)**: este contrato es
> descriptivo, no un JSON Schema ejecutable — `evaluate-sources` es un skill
> INTERACTIVO (reporte de viabilidad para que el owner decida, no un workflow
> automatizado), así que no amerita la inversión de un schema formal + validación
> por código. El formato de arriba + el archivo por-fuente en `data/diagnostics/`
> alcanzan para que el Step 2/3 lean resultados consistentes entre subagentes.

---

## Step 2 — Overlap check (solo fuentes con preliminary_verdict viable o borderline)

Hallazgo ES-1 (auditoría Fable 2026-07-11): este step YA NO le pide al LLM que
"cruce a ojo" los ISBNs de la muestra — corre `scripts/audit/source_overlap.py`,
que hace el cruce real contra `data/items.jsonl` usando las mismas funciones
de normalización que el pipeline (`normalize_isbn`, `_slugify_kebab`). Es
100% de solo lectura.

Para cada fuente viable, usá el JSON que el subagente ya escribió en
`data/diagnostics/source-eval-<id>.json` (Step 1, sección D):

```bash
.venv/bin/python scripts/audit/source_overlap.py \
  --eval-file data/diagnostics/source-eval-<id>.json --json
```

Output (`--json`): `{"corpus": {...}, "isbn_overlap": {...}, "series_overlap": {...}}`.
Cada bucket `overlap` trae `sample_total`, `matched`, `pct` y `classification`
(`nuevo` / `parcial` / `redundante`), o `classification: "sin_datos"` con
`pct: null` si la muestra no trajo ningún ISBN/serie (la detail page no lo
publicaba — pasa seguido, no es un error).

Regla de overlap (aplicada por el script, `overlap_classification()`):
- < 30% overlap → `nuevo` — fuente claramente nueva, aporta
- 30-70% → `parcial` — viable si aporta campos que nos faltan o nuevo país/editorial
- > 70% → `redundante` — sólo viable si es SUPERIOR a la fuente existente (más items, más campos, fotos extras)

**Para la tabla del Step 3**: la celda "Overlap" sale del `pct`/`classification`
del script. Si `classification == "sin_datos"`, la celda debe decir
literalmente **"sin datos (muestra sin ISBN)"** — NUNCA un % inventado por el
LLM. En ese caso, apoyate en `series_overlap` (si tiene datos) o en el
`existing_coverage` cualitativo que ya reportó el subagente en el Step 1.

---

## Step 3 — Reporte final

### Tabla resumen (siempre primero)

| # | Fuente | País | Viable | Items est. | Overlap | Veredicto |
|---|--------|------|--------|-----------|---------|-----------|
| 1 | url | País | ✅ | ~N | ~X% | Agregar |
| 2 | url | País | ⚠️ | ~N | ~X% | Borderline — ver detalle |
| 3 | url | País | ❌ | ~N | — | No — [razón] |

**Códigos de viabilidad:**
- ✅ = Agregar — cobertura nueva, todos los campos OK, fotos OK
- ⚠️ = Borderline — condicional, requiere aclaración
- ❌ = No viable

**Veredictos posibles:**
- `Agregar` — genuinamente nuevo
- `Viable — requiere kind: js` (hallazgo ES-3/ES-4) — el listing/detail depende
  de JS para renderizar (WebFetch trajo un esqueleto vacío pero con señales de
  hidratación client-side, C4); no es descarte, es una fuente `kind: js` más
  para el pipeline (17 ya activas así) — el resto de la rúbrica se evalúa igual
- `Reemplaza [fuente actual]` — superior a algo que ya tenemos, desactivar la vieja
- `Complementa [fuente actual]` — overlap parcial pero aporta algo que la otra no tiene
- `No — sin foto de extras` — cubre bonuses pero sin imagen del extra
- `No — >70% redundante` — ya lo tenemos mejor cubierto
- `No — contenido incorrecto` — mayoritariamente tomos regulares / noticias
- `No — sitio muerto` — página vacía SIN señales de JS (no `__NEXT_DATA__`,
  no bundles grandes, no endpoints XHR) — distinto de "requiere kind: js" (C4)
- `No — acceso bloqueado` — anti-bot fuerte (Cloudflare challenge/CAPTCHA),
  Playwright no alcanzaría o sería demasiado frágil
- `No — escala insuficiente` — < 50 items coleccionables

### Detalle (solo fuentes ✅ y ⚠️)

Por cada una: 2-3 bullets máximo.
- Qué cubre que no tenemos
- Qué falta o es condicional
- Acción recomendada — si es `catalog_scope: mixed`, sugerí explícitamente
  `purity: mixed` para el alta en sources.yml (ver Source.purity); si es
  `manga_only`, sugerí `purity: manga_only` (default)

### Fuentes ❌ — razón en una frase

| Fuente | Razón |
|--------|-------|
| ... | ... |

### Nota final (sólo si algún veredicto es `Agregar`, `Reemplaza` o `Complementa`)

Recordá al owner que el alta de una fuente nueva requiere crear su ficha
`docs/scraper/sources/<fuente>.md` desde `_TEMPLATE.md` (política de docs de
CLAUDE.md — regla dura de fuentes) además de la entrada en `sources.yml`. Esto
NO es parte del reporte de viabilidad (este skill no implementa nada), es un
recordatorio de qué falta después de que el owner decida agregar.

Además: una fuente de **referencia sin e-commerce** (wiki, base de datos
comunitaria tipo Mangavariant) es first-class para este catálogo — el
objetivo es discovery, no siempre compra. La AUSENCIA de precio/botón de
tienda NO es un motivo de descarte ni penaliza el veredicto; evaluála igual
por la rúbrica C1-C5 normal.

---

## Constraints

- **NO implementes nada.** Solo el reporte.
- Output conciso — sin prose larga, sin repetir lo que ya dice la tabla.
- Si una fuente falla en Content Fit: ❌ directo, sin evaluar el resto de criterios.
- Si una fuente cubre extras/bonuses/tokuten y NO tiene foto del extra: ❌ automático (lección BooksPrivilege).
- Si el sitio requiere login o está completamente bloqueado por anti-bot: ❌ "acceso bloqueado".
- Si el sitio vino vacío pero sin señales de JS (ni `__NEXT_DATA__`, ni bundles, ni XHR): ❌ "sitio muerto" — NO lo confundas con JS-rendered (C4).
- Si el sitio vino vacío CON señales de JS: NO es descarte — veredicto "Viable — requiere kind: js".
- **La celda "Overlap" del Step 3 sale SIEMPRE de `scripts/audit/source_overlap.py` (Step 2), nunca de una estimación del LLM.** Si el script devuelve `classification: sin_datos`, la celda dice "sin datos (muestra sin ISBN)" — nunca un %.
- Máximo 1 párrafo de detalle por fuente viable.
