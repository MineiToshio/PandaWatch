# Fuente: Rakuten Books (búsqueda dirigida)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | JP - Rakuten Books (search) |
| **URL base** | `https://books.rakuten.co.jp` |
| **Índice / punto de entrada** | `https://books.rakuten.co.jp/search?sitem={query}&g=001` (búsqueda dirigida; `g=001` = sección libros) |
| **Tipo de fuente** | Tienda (retailer) — marketplace multi-editorial |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `retailer` |
| **País** | Japón (`Japón`) — el país va al edition_key |
| **Idioma** | Japonés (CJK) |
| **Cobertura** | Ediciones especiales de manga vendidas en Rakuten Books, de muchas editoriales japonesas (no de una sola) |
| **Aporte al corpus** | ~107 items |
| **Parser / módulo** | Entrada `search_template` en `sources.yml` (sin parser propio) |

**Editoriales que abarca** (sacadas del corpus real — Rakuten es marketplace, así que el
`publisher` viene del producto, NO de la tienda; #44): Kodansha (≈14) · Kadokawa (≈11) ·
Shueisha (≈9) · Ichijinsha · Square Enix · Akita Shoten · Mag Garden · Wanibooks ·
Hakusensha · Bushiroad · Shogakukan, entre otras.

> **SIN `publisher` a propósito.** Rakuten Books es un marketplace multi-editorial, no
> una editorial. Citando el comentario del YAML verbatim:
>
> ```yaml
> # SIN publisher: Rakuten Books es un marketplace multi-editorial, no una
> # editorial. El nombre de la tienda NO es el publisher — dejarlo vacío evita
> # contaminar el edition_key y generar dups. Ver gotcha #44.
> ```
>
> Dejar `publisher` vacío evita que la tienda contamine el `edition_key` y genere
> duplicados (#44). El publisher real lo aporta cada producto.

**Por qué importa / qué aporta de único**: captura **ediciones especiales japonesas**
(限定版 / 特装版 / 特典付き / 画集, etc.) del mercado JP, de múltiples editoriales que
otras fuentes mono-editorial no cubren.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: búsqueda por query expandida desde
  `https://books.rakuten.co.jp/search?sitem={query}&g=001`. `{query}` se reemplaza por
  cada keyword japonesa de la lista (ver §5); cada keyword genera una fuente virtual.
- **Estructura del HTML**: lista de resultados con estos selectores (verbatim del YAML):
  - `item_selector`: `div.rbcomp__item-list__item`
  - `title_selector`: `.rbcomp__item-list__item__details__lead a`
- **Idioma japonés (CJK)**: tanto las queries como los títulos vienen en japonés.
- **`purity: mixed`** — la búsqueda trae no-manga (ver §8). Citando el YAML verbatim:
  `# search trae enciclopedias 図鑑, revistas 月号, idol boxes プレミアムBOX.`

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: bloque `"JP - Rakuten Books (search)"`. Es una fuente
  **SIMPLE** del YAML, sin parser propio. Se ingiere en **FASE 1** del pipeline
  (`manga_watch.py` con las fuentes del YAML), igual que el resto de fuentes search.
- **Fuentes virtuales por keyword**: la `search_template` se **expande** en una fuente
  virtual por cada keyword (tag `expansion`). Keywords (verbatim del YAML):
  限定版 · 特装版 · 初回限定 · 数量限定 · 特典付き · グッズ付き · 画集.
- **`purity: mixed` → STRONG manga hint (decisión #3)**: como la fuente es mixta, sólo
  pasan los items con una señal STRONG de manga; así se descartan enciclopedias (図鑑),
  revistas (月号) e idol boxes (プレミアムBOX) que la búsqueda arrastra. La comics
  blacklist aplica siempre.
- **País = Japón** (va al `edition_key`); **`publisher` vacío** (lo aporta el producto, #44).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#44: la tienda no es la editorial** — Rakuten Books es marketplace multi-editorial;
  poner el nombre de la tienda como `publisher` contaminaría el `edition_key` y generaría
  duplicados. ✅ Solución: el bloque NO define `publisher` (queda vacío a propósito); el
  publisher real lo aporta cada producto (corpus real: Kodansha, Kadokawa, Shueisha…).
- **Decisión #3 (purity `mixed` → STRONG manga hint)**: la búsqueda trae no-manga
  (enciclopedias 図鑑, revistas 月号, idol boxes プレミアムBOX). ✅ `purity: mixed`
  exige una señal STRONG de manga para que un item pase.

---

## 9. Pendientes / limitaciones conocidas

- {{pendiente: anti-bot / rate-limiting de Rakuten — no determinado en esta revisión}}.
- {{pendiente: calidad/origen de las imágenes de portada — no determinado}}.
- {{pendiente: diferencia full vs delta para esta fuente — por ahora se scrapea igual en
  ambos modos (la única diferencia full/delta documentada es listadomanga)}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "JP - Rakuten Books (search)"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "rakuten"
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
