# Fuente: AR - Distrito Manga (Cúspide)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-07-07.

> ⚠️ NO confundir con **"ES - Distrito Manga"** (España, `penguinlibros.com`), que se
> documenta aparte. Esta es la fuente **argentina** servida vía la librería Cúspide.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | AR - Distrito Manga (Cúspide) |
| **URL base** | `https://cuspide.com/editorial/distrito-manga/` |
| **Índice / punto de entrada** | `https://cuspide.com/editorial/distrito-manga/` (paginado, `max_pages: 5`) |
| **Tipo de fuente** | Tienda (retailer) — librería argentina |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `retailer` |
| **País** | Argentina (`Argentina`) |
| **Idioma** | Español |
| **Cobertura** | Catálogo del sello **Distrito Manga** (Penguin Random House) en Argentina, vendido por Cúspide |
| **Aporte al corpus** | 6 items (todos `Distrito Manga Argentina`) |
| **Parser / módulo** | Entrada en `sources.yml` (extractor genérico, sin módulo propio) |

**Por qué importa**: Distrito Manga es el sello de manga de **Penguin Random House**;
Cúspide (librería argentina) tiene el catálogo completo y es la vía de discovery del
mercado **argentino** de ese sello. Aporta cobertura de un país poco representado.

> **Tienda ≠ editorial (#44):** Cúspide es la **tienda**; el `publisher` real es el sello
> **Distrito Manga Argentina**. A diferencia de los retailers multi-editorial de #44 (donde
> el `publisher` NO debe setearse), aquí la fuente apunta a un sello único, así que
> `publisher="Distrito Manga Argentina"` es correcto y específico de la edición.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: índice del sello en Cúspide, paginado (hasta 5 páginas
  por `max_pages`). Cada producto enlaza a una página `/producto/…`.
- **Estructura del HTML**: listado tipo grilla.
  - `item_selector`: `.product`
  - `title_selector`: `a[href*='/producto/']`
- **Identificador de producto**: URL canónica `/producto/…` de Cúspide.
- **Anti-bot / quirks**: {{pendiente: no observado anti-bot/JS-render en esta fuente}}.
- **Calidad de imágenes**: {{pendiente: no verificada}}.

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: `"AR - Distrito Manga (Cúspide)"` (`kind: html`,
  `source_class: retailer`). Se procesa en **FASE 1** del pipeline (scrape de sources del
  YAML, `manga_watch.py --workers 8`) con el **extractor genérico** — NO tiene parser ni
  módulo propio.
- **Selectores**: `item_selector: .product`, `title_selector: a[href*='/producto/']`,
  `max_pages: 5`.
- **Publisher**: `Distrito Manga Argentina` (sello de Penguin Random House). Cúspide es la
  tienda, no la editorial (#44).
- **Notes verbatim (YAML)**: "Distrito Manga es sello de Penguin Random House; Cúspide tiene
  catálogo completo."

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#44 (tienda ≠ editorial)** — Cúspide es la tienda y Distrito Manga el sello. Acá el
  `publisher` apunta al sello correcto (fuente de un único sello), así que no cae en el caso
  problemático de #44 (retailers multi-editorial que contaminan el `publisher`).
- **Decisión**: NO confundir con la fuente homónima de España (`ES - Distrito Manga`,
  `penguinlibros.com`). País distinto = edición distinta (#46); el país (`Argentina`) va en
  el `edition_key`.
- **Prefijo de botón "Agregar a mi lista de deseos!" en el título (2026-07-07)**: se agregó
  un pattern nuevo a `TITLE_JUNK_PREFIXES` en `manga_watch.py` para
  `^Agregar\s+a\s+mi\s+lista\s+de\s+deseos!?\s*` (mismo mecanismo que el prefijo equivalente
  ya existente de Panini ES). El código lo etiqueta como variante "Tiendanube/Cúspide AR" del
  botón wishlist. **Nota de precisión**: el selector de ESTA fuente en `sources.yml` es
  `.product` / `a[href*='/producto/']` (no el patrón clásico Tiendanube `[data-product-id]` /
  `/productos/` — gotcha #4 — que sí usa la fuente vecina `AR - Kemuri Ediciones`); no está
  100% confirmado si el título afectado vino de esta fuente puntual o de otro retailer AR con
  el mismo texto de botón. Se documenta acá porque es el nombre citado explícitamente en el
  comentario del fix; si el próximo scrape muestra el prefijo intacto en algún item de Cúspide,
  hay que revisar el `title_selector`.

---

## 9. Pendientes / limitaciones conocidas

- Aporte chico (6 items). {{pendiente: confirmar si `max_pages: 5` cubre todo el catálogo o
  si se trunca.}}
- {{pendiente: calidad de imágenes y eventuales quirks de layout/anti-bot sin verificar.}}

## 2026-09-01 — denylist del placeholder "sin imagen" de cdn.livriz.com

Ola 3 de depuración de imágenes (ver `docs/reference/images.md` § "OLA 3"). Nota:
las imágenes de esta fuente no vienen de `cuspide.com` sino de `cdn.livriz.com`
(la plataforma de e-commerce que Distrito Manga/Cúspide usa para alojar assets de
producto). Tres items (`beck-distrito-kanzenban-ar-{3,5,8}`, BECK Kanzenban vols
3/5/8) tenían como ÚNICA foto un ícono genérico "sin imagen" (cámara tachada) que
esa CDN sirve cuando el producto no tiene foto real — confirmado visualmente
(conversión AVIF→PNG + lectura). Las 3 URLs originales terminan literalmente en
`no-disp.png` (dentro de un path con UUID único por asset), y las 3 resultaron
byte-idénticas en el espejo local (mismo sha1 pese a URLs/UUID distintos — el
mismo archivo template subido 3 veces). Agregado a `data/placeholder_signatures.json`
(sha1 `74527790152165b7db548ffb5ebfa09d426534c7`, dims 1200×1500). Purgado con
`purge_placeholder_images.py --only-reasons signature` (gotcha #161): las 3 filas
quedaron sin ninguna foto (pasan al bucket de búsqueda web / 📚 en la UI).

**Hallazgo NO aplicado — 4ª instancia detectada, fuera de la denylist aprobada**:
`beck-distrito-kanzenban-ar-14` (idx 0 de su galería) tiene el MISMO ícono, mismo
patrón de URL (`.../no-disp.png`), pero un archivo de OTRO tamaño (300×375, sha1
`0344093e1b791d935bc907a6c3888b660eb14806`, distinto del registrado). Es visualmente
el mismo placeholder, pero **no se agregó su firma ni se tocó** — no formaba parte
de las 28 filas que el owner revisó/aprobó en la ola 3, y la regla dura de gotcha
#160 exige validación explícita por instancia, no basta con "mismo patrón de URL
que una ya aprobada". `no-disp.png` (el basename literal, "no disponible" en
español) es candidato natural a un futuro `KNOWN_PLACEHOLDER_URL_FRAGMENTS` en
`image_store.py` si el owner quiere generalizar en vez de ir firma-por-firma —
pero eso barrería CUALQUIER item futuro con ese basename sin revisión visual
individual, así que queda como decisión suya, no aplicado acá.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "AR - Distrito Manga (Cúspide)"

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver items reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "cuspide"
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
