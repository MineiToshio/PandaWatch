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

**Fuentes ya activas** (para calcular overlap y detectar redundancia):

| País/Región | Fuentes activas |
|---|---|
| Japón | Sumikko (限定版/特装版, ~2700 items), AnimeClick IT (ediz. speciali) |
| España | ListadoManga calendario + colecciones, Panini ES, Norma, Planeta, Distrito |
| Francia | Manga-Sanctuary (~950 items), Kurokawa, Glénat, Ki-oon, Pika |
| Italia | SocialAnime (variants + cofanetti, ~523 items), AnimeClick IT (~1037 items) |
| Alemania | MangaPassion (Sonderausgaben + Variants, ~841 items) |
| Global | Mangavariant (~1613 items, 13 países) |
| México | MangaMéxico, Panini MX, MangaLine MX |
| Brasil | BlogBBM (variant covers + box sets) |
| USA/EN | Dark Horse Direct, Otaku Calendar |

**Lección crítica — BooksPrivilege (2026-05-26)**: tenía 11,000 items de
店舗特典 (bonuses de tienda para tomos regulares). El 99.7% eran tomos
normales con postal/acrylic stand de regalo. La foto era SOLO la portada
del manga, NO del extra. Sin foto del extra = inútil para un catálogo visual
público. Se deshabilitó y se limpiaron 11,145 items. **Cualquier fuente que
cubra bonuses/extras/tokuten DEBE tener foto del extra — si no, es ❌ automático.**

---

## Step 0 — Parsear input

Extrae la lista de fuentes candidatas del mensaje del usuario. Puede ser
URLs, nombres, texto libre o mixto. Normaliza a lista de `{id, url, contexto_extra}`.

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

### A. Fetch listing principal

Usa WebFetch para cargar la página de catálogo/listing. Si la URL es genérica
(solo el dominio), busca la sección de ediciones especiales / variantes /
limitadas. Entiende qué tipos de items muestra.

### B. Muestra de 5 items

Elige 5 items del listing (variados: distintas series/editoriales si es posible)
y fetchea sus páginas de detalle. Por cada item registra:

1. Título completo
2. ¿Es una edición especial real? (sí/no + por qué)
3. Campos presentes: nombre de serie, tipo de edición, editorial, imagen de portada
4. **Si el item incluye extras/bonuses/tokuten**:
   ¿Hay foto del EXTRA en sí (tapestry, acrylic stand, postal, accesorios)?
   ¿O solo la portada del manga?
   ESTO ES CRÍTICO. "Solo portada del manga" = el sitio no sirve para extras.

### C. Rubrica de evaluación

**C1 — Content Fit** (falla aquí = skip el resto, veredicto ❌ directo)
- ¿Qué % del listing son ediciones especiales reales (no tomos regulares)?
- Si < 20%: FAIL. Si 20-60%: borderline. Si > 60%: pass.

**C2 — Campos mínimos** (evaluar sobre los 5 items sampleados)
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

**C5 — Comparación con fuentes existentes**
¿Ya tenemos algo que cubra el mismo nicho (mismo país + tipo de contenido)?
Si sí: ¿esta fuente es mejor (más items, más campos, más editoriales)?
¿O es redundante?

### D. Output (JSON estructurado, sin prose)

```json
{
  "source": "url o nombre",
  "country": "país que cubre",
  "language": "idioma del contenido",
  "content_fit": "pass|fail|borderline",
  "content_fit_note": "razón breve (1 frase)",
  "special_edition_ratio": "~X%",
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
      "note": "..."
    }
  ],
  "preliminary_verdict": "viable|not_viable|borderline",
  "verdict_reason": "una frase"
}
```

---

## Step 2 — Overlap check (solo fuentes con preliminary_verdict viable o borderline)

Corre este snippet para entender el estado actual del corpus:

```python
import json
from collections import defaultdict

existing_isbns = set()
existing_series = set()
country_counts = defaultdict(int)

with open('data/items.jsonl') as f:
    for line in f:
        item = json.loads(line)
        if item.get('isbn'):
            existing_isbns.add(item['isbn'].strip())
        if item.get('series_key'):
            existing_series.add(item['series_key'])
        country_counts[item.get('country', '?')] += 1

print(f"Corpus: {sum(country_counts.values())} items, {len(existing_isbns)} ISBNs únicos, {len(existing_series)} series")
for c, n in sorted(country_counts.items(), key=lambda x: -x[1])[:10]:
    print(f"  {c}: {n}")
```

Para cada fuente viable, cruza los ISBNs de su muestra con `existing_isbns`.
Calcula % overlap. Si el subagente reportó series_keys, normaliza (slugify,
minúsculas, sin diacríticos) y cruza con `existing_series`.

Regla de overlap:
- < 30% overlap → fuente claramente nueva, aporta
- 30-70% → viable si aporta campos que nos faltan o nuevo país/editorial
- > 70% → solo viable si es SUPERIOR a la fuente existente (más items, más campos, fotos extras)
- ~100% overlap Y no superior → ❌ Redundante

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
- `Reemplaza [fuente actual]` — superior a algo que ya tenemos, desactivar la vieja
- `Complementa [fuente actual]` — overlap parcial pero aporta algo que la otra no tiene
- `No — sin foto de extras` — cubre bonuses pero sin imagen del extra
- `No — >70% redundante` — ya lo tenemos mejor cubierto
- `No — contenido incorrecto` — mayoritariamente tomos regulares / noticias
- `No — acceso bloqueado` — anti-bot fuerte, Playwright complejo
- `No — escala insuficiente` — < 50 items coleccionables

### Detalle (solo fuentes ✅ y ⚠️)

Por cada una: 2-3 bullets máximo.
- Qué cubre que no tenemos
- Qué falta o es condicional
- Acción recomendada

### Fuentes ❌ — razón en una frase

| Fuente | Razón |
|--------|-------|
| ... | ... |

---

## Constraints

- **NO implementes nada.** Solo el reporte.
- Output conciso — sin prose larga, sin repetir lo que ya dice la tabla.
- Si una fuente falla en Content Fit: ❌ directo, sin evaluar el resto de criterios.
- Si una fuente cubre extras/bonuses/tokuten y NO tiene foto del extra: ❌ automático (lección BooksPrivilege).
- Si el sitio requiere login o está completamente bloqueado: ❌ "acceso bloqueado".
- Máximo 1 párrafo de detalle por fuente viable.
