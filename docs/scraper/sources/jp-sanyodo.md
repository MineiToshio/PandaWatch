# Fuente: Sanyodo (三洋堂)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-07-07.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | JP - Sanyodo Comic Limited Editions |
| **URL base** | `https://www.sanyodo.co.jp` |
| **Índice / punto de entrada** | `https://www.sanyodo.co.jp/news/bks_new_comic_limited-edition` |
| **Tipo de fuente** | Tienda (retailer) multi-editorial |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `retailer` |
| **País** | Japón (`Japón`) — el país de la edición (idioma/editorial), no el de la tienda (#46) |
| **Idioma** | Japonés (CJK) |
| **Cobertura** | Ediciones limitadas (限定版) de manga japonés que la tienda revende; multi-editorial |
| **Aporte al corpus** | ~83 items |
| **Parser / módulo** | Entrada en `sources.yml` (sin módulo propio) |

**Editoriales que abarca** (del corpus real; `publisher` lo completa el merge por ISBN o
el skill, NO la fuente — ver §5 y #44):

Kodansha (≈12) · Shogakukan (≈8) · Akita Shoten (≈8) · Kadokawa (≈8) · Ichijinsha (≈8) ·
Hakusensha (≈6) · Frontier Works (≈3) · Futabasha (≈3) · Tokuma Shoten · Takeshobo ·
Square Enix · Libre · Shodensha · Bushiroad, entre otras.

**Por qué importa / qué aporta de único**: captura **ediciones limitadas japonesas
(限定版)** que se venden a través de una tienda generalista — un ángulo distinto al de las
fichas de la editorial oficial, útil para descubrir ediciones especiales del mercado JP.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: página de noticias/listado de novedades de "comic
  limited-edition" (`/news/bks_new_comic_limited-edition`). Cada entrada apunta a un
  producto de edición limitada.
- **Estructura del HTML**: HTML estático; el extractor genérico de FASE 1 toma título /
  imagen del layout de la tienda (sin selectores dedicados).
- **Identificador de producto**: URL del producto en `sanyodo.co.jp`.
- **Quirks**: contenido en **japonés (CJK)** — el matching de keywords usa substring CJK,
  no boundary ASCII (#29). Las ediciones limitadas se reconocen por el literal 限定版.
- **`publisher` deliberadamente vacío** — ver §5 y #44.

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: `JP - Sanyodo Comic Limited Editions` (`kind: html`,
  `source_class: retailer`, `enabled: true`, tags `limited` / `special-edition` /
  `retailer` / `japan`). Se scrapea en **FASE 1** (sources del YAML, `manga_watch.py`) con
  el **extractor genérico** — NO tiene parser propio.
- **`publisher` ausente A PROPÓSITO.** El YAML lo documenta verbatim:

  > `# SIN publisher: Sanyodo es una tienda multi-editorial que revende ediciones`
  > `# estándar de Square Enix, Akita Shoten, Kadokawa, etc. El nombre de la tienda`
  > `# NO es la editorial — dejarlo vacío evita contaminar el edition_key`
  > `# (`...-unknown-...`) y crear dups con la ficha de la editorial oficial. La`
  > `# editorial real la completa el merge por ISBN o el skill. Ver gotcha #44.`

  Dejar `publisher` vacío evita que el nombre de la tienda se hornee en el `edition_key`
  (`…-unknown-…`) y genere duplicados del MISMO libro (mismo ISBN) frente a la ficha de la
  editorial oficial. La editorial real la completa el **merge por ISBN** o el **skill**
  (#44). NUNCA mapear el nombre "Sanyodo" en `_PUBLISHER_SLUG_MAP`.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Veredicto de auditoría de ingestión (2026-07-07): SE MANTIENE — no podar ni
  deshabilitar.** Sanyodo solapa un 82% por `cluster_key` con Sumikko (la fuente JP
  de limitadas más grande), pero su valor no es sólo de descubrimiento: aporta
  **precio en 25 de los 76 items solapados**, dato que Sumikko no siempre tiene.
  Ese precio/stock alimenta directamente al skill `/watch-validate-rarity` (evidencia
  de `stock_status` para re-derivar rareza). Podarla perdería esa señal de evidencia,
  no sólo cobertura de catálogo.
- **#44 (tienda ≠ editorial)** — es la gotcha central de esta fuente. Antes seteaba
  `publisher: "Sanyodo"`, lo que contaminaba el `edition_key` y producía dups de mismo-ISBN
  contra la editorial oficial. ✅ Fix: se removió el `publisher` de la fuente; el corpus
  existente lo limpió `scripts/retrofit/fix_store_publisher.py` (cubre `sanyodo` en
  `_STORE_EXACT`/`_STORE_PREFIX`), que recupera la editorial real por slug del edition_key o
  por hermano-ISBN.
- **#29 (CJK)** — contenido en japonés: el matching de keywords usa substring CJK.
- **#82 (dígitos full-width en títulos)** — Sanyodo escribe varios títulos íntegramente en
  caracteres full-width ("学園アイドルマスター ＧＯＬＤ ＲＵＳＨ 特装版 ７", "ｃｉｔｒｕｓ ＋（７）特装版").
  `\d` en regex unicode matchea ０-９, así que `_extract_volume` devolvía el dígito crudo
  (`volume: "７"`) y contaminaba el `cluster_key` (`edition:…|７`). ✅ Fix 2026-06-12:
  `FULLWIDTH_DIGITS_TABLE` en `manga_watch.py` (fuente única; `generate_slugs.py` la importa)
  aplicada en `_extract_volume`, `_normalize_series_name`, `derive_cluster_key` y la frontera
  de escritura de `volume` en `candidate_to_json`. Los 2 items afectados se repararon con
  `backfill_cluster_key.py`.

---

## 9. Pendientes / limitaciones conocidas

- **`publisher` se completa downstream**: la fuente NO trae editorial; depende del merge por
  ISBN o del skill `/watch-standardize-catalog`. Items sin hermano-ISBN ni standardize
  pueden quedar sin editorial hasta esa pasada.
- {{pendiente: estructura exacta del HTML de la página de producto y robustez del extractor
  genérico frente a su layout — no verificado contra la fuente en vivo en esta ficha}}.
- {{pendiente: estado de anti-bot / rate-limit de sanyodo.co.jp — no observado}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente (FASE 1, extractor genérico):
.venv/bin/python scripts/manga_watch.py --only-source "JP - Sanyodo Comic Limited Editions"

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "sanyodo"
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
esta ficha. Recuerda: NUNCA setear `publisher` con el nombre de la tienda (#44).
