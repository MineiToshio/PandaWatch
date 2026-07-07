# Fuente: Pika Ediciones (España)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-07-07.

> ⚠️ **No confundir con "Pika Édition" (Francia).** Esta ficha es la editorial
> **española** Pika Ediciones, ingerida vía el agregador `hablamosdelibros.es`. La
> francesa es otra fuente distinta.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Pika Ediciones (España) |
| **URL base** | `https://hablamosdelibros.es/editorial/pika-ediciones/` |
| **Índice / punto de entrada** | `https://hablamosdelibros.es/editorial/pika-ediciones/` |
| **Tipo de fuente** | Editorial (official), ingerida vía agregador externo (`hablamosdelibros.es`) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País** | España (`es`) — fuente mono-país |
| **Idioma** | Español (ES) |
| **Cobertura** | Catálogo de la editorial Pika Ediciones (España) listado en el agregador |
| **Aporte al corpus** | 0 items al corte (ver §9) |
| **Parser / módulo** | Entrada en `sources.yml` ("ES - Pika Ediciones") — extractor genérico, sin módulo propio |

**Por qué importa / qué aporta de único**: cubre el catálogo de manga de la
editorial española **Pika Ediciones**, un sello no tan grande que no siempre está en
las fuentes principales del mercado español. La página propia de la editorial no se
scrapea directamente: se usa el agregador `hablamosdelibros.es`, que expone su
catálogo en una grilla.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: una única página de listado por editorial en el
  agregador (`/editorial/pika-ediciones/`), con los productos en una grilla.
- **Estructura del HTML**: el listado se arma con bloques de Elementor. El
  `item_selector` configurado es `div.ae-bg-gallery-type-default.e-con.e-con-boxed`
  (cada bloque = una tarjeta de producto). Título/imagen salen de cada tarjeta vía el
  extractor genérico de listings.
- **Identificador de producto**: URL del producto dentro de la tarjeta (o URL
  sintética del listing si no hay enlace canónico).
- **Anti-bot / quirks**: {{pendiente: no verificado en vivo — no hay items en el
  corpus todavía}}.
- **Calidad de imágenes**: {{pendiente: no verificado}}.

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: bloque `"ES - Pika Ediciones"`
  (`publisher: Pika Ediciones`, `country: España`, `source_class: official`,
  `kind: html`, `enabled: true`). Único selector configurado:

  ```yaml
  selectors:
    item_selector: "div.ae-bg-gallery-type-default.e-con.e-con-boxed"
  ```

- **Cómo se ingiere**: es una fuente **simple del YAML**, procesada en la **FASE 1**
  del pipeline (`manga_watch.py --workers 8`) por el **extractor genérico de HTML**
  (`extract_generic_html` en `scripts/manga_watch.py`), que recorre cada elemento que
  matchea `item_selector` y arma un item por tarjeta. **No tiene parser propio** ni
  reglas de agrupación dedicadas.
- **Filtros aguas abajo**: como cualquier fuente, pasa por los retrofits de cleanup de
  la FASE 3 (rescore → filtros → clean_titles → backfill de metadata/imágenes) antes
  del build.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **404 en `hablamosdelibros.es/editorial/pika-ediciones/` (2026-06-12) — FUE
  TRANSITORIO**: se había reportado la URL caída con 404. Verificado en vivo el
  2026-07-07 (auditoría de ingestión): la página responde **HTTP 200** y expone
  **18 productos**. No fue un cambio de URL/estructura del agregador ni un problema
  de selector — fue un blip transitorio del sitio. Falta correr un scrape real para
  confirmar que el `item_selector` sigue matcheando esos 18 productos y que llegan a
  `items.jsonl`.

---

## 9. Pendientes / limitaciones conocidas

- **0 items en el corpus** al corte (2026-06-08), pero la fuente **SÍ está viva** (ver
  §8 — 200 OK, 18 productos verificados 2026-07-07). Falta una corrida que confirme
  que el `item_selector` matchea las tarjetas reales del agregador y que el extractor
  genérico produce items válidos.
- **Selector frágil de Elementor**: las clases `ae-bg-gallery-type-default`,
  `e-con`, `e-con-boxed` son de Elementor; si el agregador re-maqueta la página, el
  selector puede dejar de matchear en silencio (0 items, sin error). Revisar el
  selector si esta fuente aparece en rojo en `source_health`.
- **Dependencia de un tercero**: se ingiere vía `hablamosdelibros.es`, no la web propia
  de la editorial; cambios del agregador (no de Pika) afectan la ingestión.
- {{pendiente: comportamiento anti-bot / calidad de imágenes — no verificado en vivo}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "ES - Pika Ediciones"

# Validar el corpus (gate estructural, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver items reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "hablamosdelibros"
def hit(it):
    blobs=[it.get('url','') or '']+[ (s.get('url','') or '') for s in it.get('sources',[]) ]
    return any(NEEDLE in b for b in blobs)
items=[json.loads(l) for l in open("data/items.jsonl") if l.strip()]
sel=[it for it in items if hit(it)]
print("items:", len(sel))
print("países:", Counter((it.get('country') or '') for it in sel if it.get('country')))
print("editoriales:", Counter((it.get('publisher') or '') for it in sel if it.get('publisher')).most_common(20))
PY
```

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`,
0 duras) → tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo
meaningful, actualiza esta ficha.
