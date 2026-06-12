# Fuente: Mangarden (JPF, Polonia)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-12 (alta de la fuente).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | PL - Mangarden (JPF tapa dura) · PL - Mangarden (JPF preorders) |
| **URL base** | `https://mangarden.pl` |
| **Puntos de entrada** | `/pl/menu/j-p-f-twarda-oprawa-2044.html` (~156, 5 págs `?counter=N`) · `/pl/menu/j-p-f-twarda-oprawa-preorder-2349.html` (~38) |
| **Tipo de fuente** | Tienda oficial de la editorial JPF (Japonica Polonica Fantastica) |
| **`kind`** | `html` |
| **`source_class`** | `official` |
| **País / idioma** | Polonia / Polaco |
| **Cobertura** | Línea "twarda oprawa" (tapa dura) de JPF — línea premium LIMITADA solo-preorder, NO el formato estándar (JPF publica en rústica) |
| **Aporte al corpus** | ~200 ediciones únicas (primera fuente de Polonia; el país estaba en 0) |
| **Parser** | Entradas en `sources.yml` con selectores |

**Por qué importa**: abre Polonia (mercado manga grande, 0 items antes). La línea
twarda oprawa incluye FMA Ultimate Deluxe, Akira edycja specjalna, Sailor Moon
Eternal (glitter), Dragon Ball Full Color, Battle Angel Alita B5 — confirmado en
ficha de producto: "Wydanie w oprawie twardej jest wydaniem limitowanym do kupienia
wyłącznie w pre-orderze" (la tapa dura es limitada y solo por preorder).

---

## 2. Descripción técnica

- HTML server-rendered, sin anti-bot, sin JS. Paginación `?counter=N`.
- Selectores: `item_selector: div.product` · `title/link_selector: a.product__name`.
- **Sin ISBN expuesto** (JSON-LD Product con `mpn` vacío) → dedup cae a tier fuzzy.
- JSON-LD schema.org/Product embebido en cada ficha (precio/availability).
- Señales en título: `(oprawa twarda)`, `edycja specjalna`, `DELUXE` — soportadas
  por las keyword rules polacas (alta 2026-06-12 en `KEYWORD_RULES`).

## 5. Proceso de ingestión

- FASE 1 del pipeline (fuente YAML estándar). El volume shape polaco `tom N`
  se agregó a `_MANGA_VOLUME_SHAPE` y `_STRONG_MANGA_PATTERNS` (2026-06-12).
- Dry-run de alta: 204 candidatos / 203 reportables (main) + 38/38 (preorders).

## 8. Problemas conocidos

- **Duplicados del mismo producto**: sufijos de estado en el título — `- OSTATNIE`
  (último stock) y `(II Gatunek)` (segunda calidad/dañado, MISMO producto, ~15-20%
  del listing). Se colapsan por título normalizado en el dedup fuzzy; si aparecen
  duplicados II Gatunek en el corpus, limpiar título y re-consolidar.
- **Sin fecha de publicación estructurada** — `release_date` queda vacío (backfill
  no aplica: la ficha tampoco la tiene).

## 9. Pendientes

- Poblar aliases PL en `series_aliases.yml` (títulos polacos: "Atak Tytanów" →
  attack-on-titan, "Miecz nieśmiertelnego" → blade-of-the-immortal…) vía
  `/watch-enrich-series-aliases`.

## 10. Runbook

```bash
.venv/bin/python scripts/manga_watch.py --only-source "PL - Mangarden (JPF tapa dura)" --dry-run
.venv/bin/python scripts/manga_watch.py --only-source "PL - Mangarden (JPF preorders)" --dry-run
```
