# Fuente: Kana

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Kana |
| **URL base** | `https://www.kana.fr/` |
| **Índice / punto de entrada** | `https://www.kana.fr/` |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | Francia (`Francia`) — fuente mono-país |
| **Idioma(s)** | Francés |
| **Cobertura** | Sitio oficial de la editorial Kana (manga publicado en Francia). |
| **Aporte al corpus** | 1 item |
| **Parser / módulo** | Entrada en `sources.yml` ("FR - Kana"); sin parser propio |

**Editoriales que abarca** (del corpus real): Kana (1 item, país Francia).

**Por qué importa / qué aporta de único**: editorial oficial francesa, dentro del
mercado FR junto a Glénat, Pika, Delcourt/Tonkam, etc. Hoy su aporte al corpus es
marginal (1 item).

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: sitio de la editorial bajo `kana.fr/`. La entrada
  del YAML apunta a la home; no tiene índice/sitemap configurado.
- **Estructura del HTML/feed**: la entrada **no define `selectors`** → la captura usa
  la **auto-detección genérica** del extractor (no hay selectores a medida para su
  layout).
- **Identificador de producto**: URL canónica del producto (sin SKU/ISBN propio).
- **Anti-bot / quirks**: posible **mojibake FR (#1)** — sitios franceses (Glénat/Pika)
  devuelven UTF-8 decodificado como cp1252; `clean_title()::_fix_mojibake()` lo repara
  primero. Aplica como precaución si aparece texto corrupto en títulos de Kana.
- **Calidad de imágenes**: {{pendiente: no determinado a partir del corpus (1 item)}}.

---

## 5. Proceso de ingestión — técnico

- Fuente **simple del YAML**, capturada en **FASE 1** (`manga_watch.py --workers 8`,
  dentro de `scrape_full.sh` / `scrape_delta.sh`) vía el **extractor genérico**.
- **No tiene parser propio** ni reglas de agrupación dedicadas; sin `selectors`, depende
  de la auto-detección de label/value del extractor.
- Pasa por los retrofits de cleanup estándar de FASE 3 (rescore → filtros → clean_titles
  → backfill de metadata/imágenes) como cualquier item del corpus.

---

## 9. Pendientes / limitaciones conocidas

- **Aporte casi nulo**: 1 item en el corpus. {{pendiente: confirmar si la home sin
  `selectors`/índice es suficiente para descubrir productos, o si hace falta un índice/
  selectores propios para subir el rendimiento}}.
- **`FR - Kana Actualités`** (`https://www.kana.fr/actualites/`) es una entrada hermana
  con `enabled: false` (audit 2026-05-25: 0 items). Queda fuera del pipeline; es la
  sección de noticias del mismo sitio.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "FR - Kana"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "kana.fr"
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

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`, 0
duras) → tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful,
actualiza esta ficha.
