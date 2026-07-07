# Fuente: Dark Horse Direct

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-07-07.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Dark Horse Direct |
| **URL base** | `https://www.darkhorsedirect.com` |
| **Índice / punto de entrada** | `https://www.darkhorsedirect.com/collections/comics` (listado) + `https://www.darkhorsedirect.com/search?q={query}` (búsqueda) |
| **Tipo de fuente** | Tienda oficial de Dark Horse (Shopify) — listado oficial + búsqueda como retailer |
| **`kind` en sources.yml** | `html` (ambas entradas) |
| **`source_class`** | `official` (listado) · `retailer` (búsqueda) |
| **País** | Estados Unidos (`Estados Unidos`) |
| **Idioma** | Inglés (EN) |
| **Cobertura** | Catálogo MIXTO de Shopify: comics + manga + figuras + estatuas + prints + bookends. Sólo se aceptan ítems con STRONG manga hint. |
| **Aporte al corpus** | ~31 items (corpus actual) |
| **Parser / módulo** | Entradas en `sources.yml` (sin parser propio); extractor genérico de la fuente |

**Editoriales reales en el corpus** (`publisher`, no la tienda): Dark Horse Manga
(≈19) · Dark Horse (≈12). Sólo país: Estados Unidos.

**Por qué importa / qué aporta de único**: ediciones exclusivas y premium de Dark
Horse en EE. UU. (limited editions, deluxe hardcovers, box sets, slipcase, variants)
que muchas veces sólo se consiguen directo en su tienda.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: tienda Shopify. Dos accesos: el listado oficial
  `/collections/comics` (paginado, `max_pages: 15`) y el buscador
  `/search?q={query}`, que se expande por keyword (ver §5).
- **Estructura del HTML**: Shopify estándar. Cada serie multi-tomo se modela como UN
  `og:type=product` con un `<select>` de N volúmenes (variantes) — hay que expandirlas
  (#16).
- **Identificador de producto**: URL del producto Shopify; las variantes multi-tomo
  generan una URL por volumen vía el helper de variantes (#16).
- **Anti-bot / quirks**: catálogo mixto — además de manga trae figuras, estatuas,
  prints y bookends; por eso `purity: mixed` (ver §5). El helper de variantes Shopify
  está restringido al dominio `darkhorsedirect.com` (#16).
- **Calidad de imágenes**: portadas de producto de Shopify (alta resolución).

---

## 5. Proceso de ingestión — técnico

Ambas entradas viven en `sources.yml` y se scrapean en **FASE 1** (scrape de sources
del YAML, `manga_watch.py`) con el **extractor genérico** — no hay parser propio.

- **`US - Dark Horse Direct Manga`** (`official`, `html`): recorre el listado
  `/collections/comics` hasta `max_pages: 15`. `publisher: Dark Horse Manga`. Tags:
  `manga, hardcover, official, store, dark-horse`.
- **`US - Dark Horse Direct (search)`** (`retailer`, `html`): la `search_template`
  `/search?q={query}` se expande en **fuentes virtuales por keyword** (una corrida de
  búsqueda por término). `publisher: Dark Horse Direct`. Keywords: `limited edition`,
  `deluxe`, `hardcover`, `boxset`, `slipcase`, `exclusive`, `variant`. Tags:
  `manga, retailer, exclusive, dark-horse`.

**`purity: mixed` (ambas) → STRONG manga hint (decisión #3).** Al ser un catálogo
mixto, sólo pasa lo que tiene un STRONG manga hint; la comics blacklist aplica
siempre. **No** se rescata un ítem por traer "Collector's Edition" sola.

**Variantes Shopify multi-tomo (#16)**: una serie = 1 producto con `<select>` de N
volúmenes; los helpers de `shopify_variants.py` (`extract_shopify_variants`,
`is_volume_variants`, `build_variant_url`) las expanden a un ítem por tomo. Restringido
a dominios conocidos (hoy `darkhorsedirect.com`).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **403 transitorio en las queries de búsqueda (2026-05-21)**: la entrada `(search)`
  devolvió 403 en algunas keywords ese día (autorresuelto en la corrida siguiente sin
  cambios de código). Verificado en vivo el 2026-07-07 (chequeo manual previo al
  delta real): la fuente respondía normal, sin ningún challenge.
- **429 real en el primer delta post-mejoras (2026-07-07, gotcha #114)**: horas
  después del chequeo manual de arriba, la corrida real de `scrape_delta.sh` sí
  disparó `HTTP error 429 Client Error: Too Many Requests` en varias keywords de
  `US - Dark Horse Direct (search)` (limited edition, deluxe, slipcase, hardcover,
  exclusive, variant). Causa: `darkhorsedirect.com` resuelve al mismo borde Shopify
  `23.227.38.0/24` que Milky Way, Funside Variant y Manga Dreams — el rate-limit es
  del BORDE compartido, no de esta tienda puntual (`--per-host-limit` agrupa por
  hostname y no lo detecta). Fix: `throttle_group: "shopify"` en las dos entradas
  YAML de esta fuente (`US - Dark Horse Direct Manga` y `(search)`) — comparten
  semáforo (limit 1) + delay mínimo 2s con las otras tres tiendas del mismo grupo
  (`--throttle-group-delay`).

---

## 9. Pendientes / limitaciones conocidas

- El helper de variantes Shopify (#16) está limitado a `darkhorsedirect.com`; si otra
  tienda Shopify usa el mismo patrón habría que ampliar el allowlist de dominios.
- {{pendiente: no se determinó un valor de paginación para la entrada de búsqueda
  (`max_pages` no está definido en su entrada del YAML)}}.
- **Monitorear el próximo run** si `throttle_group` (delay 2s + semáforo compartido
  con Milky Way/Funside Variant/Manga Dreams) evita el 429 recurrente en `(search)`;
  si persiste, considerar reducir keywords por corrida o aumentar el delay.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo de esta fuente (cada entrada por su nombre exacto):
.venv/bin/python scripts/manga_watch.py --only-source "US - Dark Horse Direct Manga"
.venv/bin/python scripts/manga_watch.py --only-source "US - Dark Horse Direct (search)"

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "darkhorsedirect"
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
