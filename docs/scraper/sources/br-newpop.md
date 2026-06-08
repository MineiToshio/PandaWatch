# Fuente: NewPOP (Brasil)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | NewPOP (Brasil) |
| **URL base** | `https://www.lojanewpop.com.br` |
| **Índice / punto de entrada** | 4 colecciones de la tienda: `/pre-venda`, `/mangas`, `/one-shots`, `/pacotes` |
| **Tipo de fuente** | Editorial (official) — tienda propia de NewPOP Editora (plataforma Loja Integrada) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País** | Brasil (`Brasil`) — fuente mono-país |
| **Idioma** | Portugués (PT-BR) |
| **Editorial** | NewPOP Editora (publisher real; la tienda es su canal directo, #44) |
| **Cobertura** | Catálogo de manga de NewPOP en Brasil: pre-venta, catálogo completo (~111 títulos), one-shots y packs/boxsets |
| **Aporte al corpus** | 1 item al corte (ver §9) |
| **Parser / módulo** | 4 entradas en `sources.yml` ("BR - NewPOP …") — extractor genérico con selectores, sin módulo propio |

**Por qué importa / qué aporta de único**: cubre el catálogo brasileño de **NewPOP
Editora** directo de su tienda oficial. La colección de **pre-venta** es útil para
detectar **ediciones especiales** tempranas (p. ej. Cutie Honey en edición
diferenciada); **one-shots** suele traer formatos premium (integral, libro de arte) y
**pacotes** trae packs/boxsets de coleções completas, ocasionalmente limitadas con
extras. Aporta un mercado (Brasil) y un idioma (PT-BR).

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: tienda en **Loja Integrada**. Se ingieren 4
  colecciones/categorías distintas del mismo dominio (`lojanewpop.com.br`):
  `/pre-venda`, `/mangas` (`max_pages: 5`), `/one-shots` (`max_pages: 3`) y
  `/pacotes` (`max_pages: 3`). Cada una es una grilla de productos paginada.
- **Estructura del HTML**: los productos salen en `li[class*='categoria-id-']`
  (cada producto es `li.categoria-id-<NNN>`), y el título limpio en `a[title]`.
  Esos son los selectores configurados (`item_selector` / `title_selector`),
  idénticos en las 4 entradas.
- **Identificador de producto**: URL del producto dentro de la tarjeta (o URL
  sintética del listing si no hay enlace canónico, #27).
- **Anti-bot / quirks**: {{pendiente: no verificado en vivo — sólo 1 item en el corpus}}.
- **Calidad de imágenes**: {{pendiente: no verificado}}.

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: 4 bloques, todos con `publisher: NewPOP Editora`,
  `country: Brasil`, `language: Portugués`, `source_class: official`, `kind: html`,
  `enabled: true`, y los mismos selectores:

  ```yaml
  selectors:
    item_selector: "li[class*='categoria-id-']"
    title_selector: "a[title]"
  ```

  | Entrada | URL | `max_pages` | Notas (verbatim del YAML) |
  |---|---|---|---|
  | **BR - NewPOP Lançamentos** | `/pre-venda` | (sin límite) | "Loja Integrada. Pre-venta de NewPOP — útil para detectar ediciones especiales (Cutie Honey edición diferenciada, etc.). Cada producto en li.categoria-id-<NNN>; título limpio en a[title]." |
  | **BR - NewPOP Mangas** | `/mangas` | 5 | "Loja Integrada — catálogo completo manga NewPOP (~111 títulos visibles en página 1: Cavaleiros do Zodíaco, Ashita no Joe, Coelacanth, Gon, Hellbound, etc.)." |
  | **BR - NewPOP One-shots** | `/one-shots` | 3 | "One-shots de NewPOP — ediciones únicas, suelen tener formato especial (cofanetto, libro de arte, integral)." |
  | **BR - NewPOP Pacotes** | `/pacotes` | 3 | "Packs / boxsets NewPOP — coleções completas con descuento y ocasionalmente ediciones limitadas con extras." (`tags` incluye `boxset`) |

- **Cómo se ingiere**: son **fuentes simples del YAML**, procesadas en la **FASE 1**
  del pipeline (`manga_watch.py --workers 8`) por el **extractor genérico con
  selectores** (`extract_with_selectors` en `scripts/manga_watch.py`), que recorre
  cada `li[class*='categoria-id-']` y arma un item por tarjeta usando `a[title]` como
  título. **No tienen parser propio** ni reglas de agrupación dedicadas.
- **Filtros aguas abajo**: como cualquier fuente, pasan por los retrofits de cleanup
  de la FASE 3 (rescore → filtros → clean_titles → backfill de metadata/imágenes)
  antes del build.

---

## 9. Pendientes / limitaciones conocidas

- **Sólo 1 item en el corpus** al corte (2026-06-08), pese a que las 4 colecciones de
  la tienda están `enabled: true`. Falta una corrida que confirme que
  `li[class*='categoria-id-']` matchea las tarjetas reales en las 4 URLs y que el
  extractor genérico produce items válidos. Si aparecen en rojo en `source_health`,
  revisar primero el `item_selector`.
- **"BR - NewPOP Catálogo"** (`newpop.com.br/catalogo/`, dominio distinto al de la
  tienda) está **`enabled: false`**: la auto-detección no encuentra cards (0
  candidatos en dry-run), el listado parece JS-rendered (#12) o usa un contenedor no
  estándar. Su cobertura real se obtiene vía las colecciones de `lojanewpop.com.br`.
  Re-activar con selectores explícitos cuando se inspeccione el HTML.
- **Selectores frágiles de Loja Integrada**: si la tienda re-maqueta la grilla, los
  selectores pueden dejar de matchear en silencio (0 items, sin error).
- {{pendiente: comportamiento anti-bot / calidad de imágenes — no verificado en vivo}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo las 4 colecciones de NewPOP:
.venv/bin/python scripts/manga_watch.py --only-source "BR - NewPOP Lançamentos"
.venv/bin/python scripts/manga_watch.py --only-source "BR - NewPOP Mangas"
.venv/bin/python scripts/manga_watch.py --only-source "BR - NewPOP One-shots"
.venv/bin/python scripts/manga_watch.py --only-source "BR - NewPOP Pacotes"

# Validar el corpus (gate estructural, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver items reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "newpop"
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
