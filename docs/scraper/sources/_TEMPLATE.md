<!--
PLANTILLA para documentar una fuente. Cómo usarla:
  1. Copia este archivo a `docs/scraper/sources/<nombre-fuente>.md` (kebab-case).
  2. Rellena cada sección. Borra las notas en cursiva (_…_) y los comentarios <!-- -->.
  3. Secciones marcadas (OPCIONAL) se omiten si no aplican al tipo de fuente:
       - Fuente SIMPLE (entrada en sources.yml, HTML/RSS/JS): §1, §2, §5 (básico),
         §8, §9, §10. Probablemente NO tiene §3/§4/§6/§7 propios.
       - Fuente WIKI / módulo propio con discovery y reglas (ej. ListadoManga): todas.
  4. Referencia completa rellenada: `listadomanga.md`.
  5. Agrega el link a CLAUDE.md (tabla "cargar bajo demanda") si es una fuente clave.
  6. Las gotchas se citan por número (#N) → docs/reference/gotchas.md.
-->

# Fuente: {{Nombre de la fuente}}

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: {{YYYY-MM-DD}}.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | {{Nombre}} |
| **URL base** | `{{https://…}}` |
| **Índice / punto de entrada** | `{{URL de listado, sitemap, feed, o N/A}}` |
| **Tipo de fuente** | {{tienda (retailer) · editorial (official) · catálogo comunitario · media · social}} |
| **`kind` en sources.yml** | {{html · rss · js · bluesky · wiki · N/A}} |
| **`source_class`** | {{official · retailer · trusted_media · social}} |
| **País(es)** | {{España (es), … — código de país que va al edition_key}} |
| **Idioma(s)** | {{ES, EN, …}} |
| **Cobertura** | {{qué publica / cuántos productos / qué editoriales}} |
| **Aporte al corpus** | {{~N items}} |
| **Parser / módulo** | `{{scripts/wikis/<x>.py o entrada en sources.yml}}` |

_Si la fuente abarca varias editoriales/países, lístalos acá (sácalos del corpus real:
ver el snippet de §10). Recuerda: `publisher` = editorial real, NO la tienda (#44)._

**Por qué importa / qué aporta de único**: _qué captura esta fuente que otras no
(ediciones especiales, un mercado, un idioma, formato premium, etc.)._

---

## 2. Descripción técnica de la fuente

_Cómo está armada la fuente (sin el proceso de scraping todavía):_

- **Estructura de URLs / páginas**: _índice, página de producto, paginación, sitemap…_
- **Estructura del HTML/feed**: _selectores clave, secciones, dónde está título/
  imagen/ISBN. Si hay variantes de layout, lístalas._
- **Identificador de producto**: _SKU, ISBN, URL canónica, o URL sintética (`?item=`, #27)._
- **Anti-bot / quirks**: _Cloudflare, JS-rendered (#12), Brotli (#15), tracking params
  (#19/#26), mojibake (#1), imágenes lazy/placeholder (#6), portadas censuradas, etc._
- **Calidad de imágenes**: _alta/baja resolución; de dónde sale la portada._

---

## 3. Proceso de ingestión — vista de producto (OPCIONAL)

_Sólo si la fuente tiene lógica de captura no trivial (qué entra y qué no). Para una
tienda simple "cada producto del listado = un item", se puede omitir. Describe el flujo
SIN tecnicismos de scraping, generalizado (usa `{{obra}}`/`{{producto}}`, no ejemplos
concretos). Pasos numerados. Incluye las reglas de negocio que nunca se rompen._

1. {{Ir al índice / listado.}}
2. {{Tomar cada item…}}
3. {{Qué se decide / qué entra al catálogo y qué se descarta.}}
4. {{Repetir hasta terminar.}}

**Reglas de producto que nunca se rompen:** _país=edición (#46), coleccion=edición si
aplica (#48), qué cuenta como coleccionable, etc._

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA) (OPCIONAL)

_Sólo si la fuente se recorre distinto en full vs delta. Para una fuente del YAML que se
scrapea igual siempre, omitir._

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| Script / flag | {{…}} | {{…}} |
| Discovery | {{cómo se descubre qué scrapear}} | {{…}} |
| Frecuencia | {{…}} | {{…}} |
| Cuándo | {{…}} | {{…}} |

---

## 5. Proceso de ingestión — técnico

_Para una fuente del YAML: dónde está la entrada en `sources.yml`, qué `extract_*`
maneja su layout, y cualquier helper específico. Para una wiki/módulo propio: lo de abajo._

### 5.1 Modelo de datos / claves (si tiene reglas propias)
- _Cómo se deriva `edition_key`, `cluster_key`, `volume`, país. Reglas duras._

### 5.2 Qué captura el parser (mapea el §3 al código)
- _Cada sección/caso → función del código + signal_types + kind._

### 5.3 Flujo end-to-end
- _Dónde entra en `scrape_full.sh`/`scrape_delta.sh` (qué fase/paso), retrofits que la tocan._

---

## 6. Reglas de agrupación / enforcer (OPCIONAL)

_Sólo si la fuente tiene retrofits/enforcer dedicados (como el de ListadoManga). Lista
los pasos en orden y qué hace cada uno. Si no, esta sección se borra._

---

## 7. Validación (OPCIONAL)

_Cómo verificar que la ingestión de esta fuente está bien. En general:_
- **`scripts/validate_corpus.py`** (gate estructural, aplica a TODO el corpus).
- _Auditoría específica de la fuente si existe (re-fetch + comparar parser vs DB)._
- _Idempotencia si la fuente tiene retrofits (correr 2× → items.jsonl idéntico)._

---

## 8. Problemas encontrados — qué funcionó y qué NO

_El historial es lo más valioso para la próxima conversación. Cita las gotchas (#N)._

- **{{#N}}: {{problema}}** — {{qué pasaba}} → ✅/❌ {{fix o estado}}.
- **Decisiones (lo que NO se hace)**: _ej. omnibus pelado no califica (#18); no mergear
  cross-país (#46); etc._

---

## 9. Pendientes / limitaciones conocidas

- _Cosas que NO funcionan aún, casos sin resolver, deuda. Sé honesto._

---

## 10. Runbook / comandos útiles

```bash
# Scrape de esta fuente (ajustar al caso):
.venv/bin/python scripts/manga_watch.py {{--bootstrap-wiki <x> | --only-source "<name>"}}

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "{{dominio o nombre de la fuente}}"
def hit(it):
    return any(NEEDLE in (u.get('url','') or '') for u in [it]+it.get('sources',[])) or NEEDLE in (it.get('url','') or '')
items=[json.loads(l) for l in open("data/items.jsonl") if l.strip()]
sel=[it for it in items if hit(it)]
print("items:", len(sel))
print("países:", Counter((it.get('country') or '') for it in sel if it.get('country')))
print("editoriales:", Counter((it.get('publisher') or '') for it in sel if it.get('publisher')).most_common(20))
PY
```

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`, 0 duras)
→ tests (`pytest tests/test_extraction.py`) → build. Si la fuente tiene retrofits, prueba
idempotencia. Si tocaste algo meaningful, actualiza esta ficha.
