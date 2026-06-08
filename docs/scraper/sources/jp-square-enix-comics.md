# Fuente: JP - Square Enix Comics

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

> ⚠️ Esta es la fuente **japonesa** (`magazine.jp.square-enix.com`). NO confundir con
> "US - Square Enix Manga Coming Soon" (Estados Unidos), que se documenta aparte.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | JP - Square Enix Comics |
| **URL base** | `https://magazine.jp.square-enix.com/top/comics/` |
| **Índice / punto de entrada** | `https://magazine.jp.square-enix.com/top/comics/` (auto-detección) |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País** | Japón (`Japón`) — el país va al edition_key (#46) |
| **Idioma** | Japonés (CJK) |
| **Cobertura** | Comics de Square Enix en Japón (sitio oficial de la editorial) |
| **Aporte al corpus** | ~1 item (mono-editorial: Square Enix) |
| **Parser / módulo** | Entrada en `sources.yml` (sin parser propio) |

**Por qué importa**: cubre el catálogo de manga japonés directo de la editorial Square
Enix, un mercado/idioma (JP) que las tiendas occidentales no capturan.

---

## 2. Descripción técnica de la fuente

- **Estructura**: sitio oficial de la editorial (`magazine.jp.square-enix.com`). Entrada
  por la landing de comics; sin sitemap ni feed declarados en el YAML.
- **Sin `selectors` en `sources.yml`** → el scraper usa **auto-detección** (extractor
  genérico de listados/productos), no un parser dedicado.
- **Identificador de producto**: URL canónica del producto en el dominio.
- **Idioma japonés (CJK)**: los detectores de señales usan substring para CJK, no
  word-boundary ASCII (#9). Encoding JP puede traer bytes mixtos → decodificar con
  `errors='replace'` si aparece mojibake (#28).

---

## 5. Proceso de ingestión — técnico

Fuente **simple del YAML**: se scrapea en la **FASE 1** del pipeline canónico
(`manga_watch.py --workers 8`, dentro de `scrape_delta.sh` / `scrape_full.sh`), vía el
**extractor genérico**. No tiene parser propio ni retrofits dedicados; aplican las reglas
y filtros generales (`is_likely_manga()`, scoring, dedup por `cluster_key`).

- Entrada: `sources.yml` → `name: "JP - Square Enix Comics"`, `kind: html`,
  `source_class: official`, `enabled: true`, `tags: [manga, official, japan]`.
- País del edition_key: Japón (#46).
- Sin lógica full vs delta propia: se scrapea igual en ambos modos.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#9 (CJK)**: en japonés los detectores de señales hacen match por substring (no
  boundary ASCII). Usar `_phrase_pattern()` para cualquier detector nuevo.
- **#28 (encoding JP)**: si el body trae bytes mixtos/mojibake, decodificar con
  `errors='replace'` (mismo patrón que booksprivilege para fuentes JP/CN).

---

## 9. Pendientes / limitaciones conocidas

- **Aporte mínimo**: hoy ~1 item en el corpus. {{pendiente: confirmar si la
  auto-detección captura bien el listado de comics o si rinde poco por falta de
  selectors dedicados}}.
- **Items de referencia sin precio/URL de tienda**: al ser sitio editorial (no tienda),
  puede faltar precio/compra; aplica el enrichment pass diferido (`enrich_references.py`).
- {{pendiente: estado de salud de la fuente según `source_health.py` (activa / 0 items)}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "JP - Square Enix Comics"

# Validar (gate estructural, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "jp.square-enix"
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

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`, 0 duras)
→ tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful, actualiza
esta ficha.
