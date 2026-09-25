# Fuente: Mangarden (JPF, Polonia)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-09-23 (gotcha #214: el rótulo de stock y el `tom NN` entran
> al `edition_key` y parten cada edición en N ediciones de un tomo; §8bis).

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
  **2026-09-15 — el colapso NO ocurre cuando el producto pasa de preorder a último
  stock: 5 duplicados vivos en el corpus.** Mangarden cambia el SLUG de la URL cuando
  cambia el estado (`…-oprawa-twarda-preorder-18166.html` →
  `…-oprawa-twarda-ostatnie-NNNNN.html`, con otro id numérico), así que el delta del
  09-15 los trajo como URLs nuevas. Quedaron 5 pares (FMA Deluxe 13, JoJo parte IV 11,
  Kapitan Tsubasa 16, Urusei Yatsura 14, Yu Yu Hakusho 13): la fila vieja con
  `edition_key` `…-jpfantastica-deluxe-pl` / `…-jpf-special-pl`, y la nueva con publisher
  `unknown` y el sufijo de estado filtrado a la clave
  (`yu-yu-hakusho-tom-13-ostatnie-unknown-deluxe-pl`,
  `urusei-yatsura-tom-14-ostatnie-unknown-deluxe-pl`). Ni el dedup fuzzy ni la
  estandarización los unieron porque las `edition_key` difieren. Ya había filas previas
  del mismo defecto (DNAngel 02-05 `- OSTATNIE`, con
  `d-n-angel-tom-deluxe-ostatnie-unknown-deluxe-pl`). **Recomendación (no aplicada,
  decisión del owner)**: (1) que `clean_title()` quite los sufijos de estado de
  Mangarden (`- OSTATNIE`, `- PREORDER`, `(II Gatunek)`) ANTES de derivar claves;
  (2) publisher fijo `J.P.Fantastica` para el host; (3) re-consolidar los pares con el
  retrofit de claves + `enforce_listadomanga_rules.py`.
- **Sin fecha de publicación estructurada** — `release_date` queda vacío (backfill
  no aplica: la ficha tampoco la tiene).
- **Contaminación de galería entre tomos hermanos de un mismo "zestaw" (box)
  (descubierto en la OLA 3 de depuración de imágenes, 2026-09-01, gotcha #160)**:
  al menos un producto "Battle Angel Alita Last Order" (deluxe box, varios tomos
  listados como items separados) trae en su propio `images[]` las PORTADAS de
  OTROS tomos del mismo box (ej. el tomo 03 incluye en su galería la portada real
  del tomo 12 y del tomo 11, no solo la propia) — probablemente porque la página
  de producto muestra miniaturas de todos los volúmenes del set y el extractor de
  galería las capturó todas sin acotar al scope del tomo individual. NO es un
  placeholder (son portadas reales de OTROS tomos), así que
  `purge_placeholder_images.py` no debe tocarlas — es un bug de scope de galería,
  no de contenido genérico. Detectado por casualidad al recalcular grupos de
  SHA-256 compartido por ≥5 items (dos grupos nuevos, no relacionados con
  placeholders, resultaron ser este caso). Sin fix aplicado esta ola (fuera de
  scope); si se retoma, acotar el extractor de galería de Mangarden al contenedor
  del producto individual, igual que la detección estructural de "grilla de
  relacionados" que ya existe para otras fuentes (ver
  `docs/reference/images.md` § "Detección ESTRUCTURAL de grilla de relacionados").

## 8bis. Edición partida por tomo y por rótulo de stock (#214) — 2026-09-23

**Medido sobre el corpus completo**: 130 items de esta fuente tienen `-tom-NN-`
dentro del `edition_key`, y **128 de ellos viven en una "edición" de UN SOLO item**.
Son 29 familias / 156 `edition_key` que deberían ser 29 ediciones.

| Serie | `edition_key` distintas (deberían ser 1) |
|---|--:|
| Ranma ½ (deluxe) | 16 |
| Inuyasha | 15 |
| Urusei Yatsura | 13 |
| Yu Yu Hakusho | 12 |
| Fullmetal Alchemist Deluxe | 10 |
| City Hunter | 10 |
| Sailor Moon Eternal | 9 |
| Initial D | 7 |

**Causa**: el título publicado lleva pegados dos textos que no pertenecen al nombre
de la edición — el número de tomo (`Ranma ½ tom 02 (oprawa twarda)`) y un **rótulo
de estado de inventario** (`- OSTATNIE` = últimas unidades, `- II Gatunek` = segunda
calidad). La derivación del `edition_key` los consume como nombre de edición.

**Lo grave es que el rótulo es MUTABLE**: describe el stock de hoy, no el producto.
Al cambiarlo la tienda, el mismo tomo cambia de `edition_key` → de `slug` → de
identidad, y nace un duplicado. Ya ocurre dentro de una serie: Ranma ½ tomo 06 quedó
en `…-tom-06-ii-gatunek-…` mientras sus hermanos están en `…-ostatnie-…`. `ostatnie`
aparece hoy en 94 `edition_key`. **Esta es la causa de mecanismo de los 5 duplicados
`preorder → ostatnie` anotados el 2026-09-15 en §8** — aquello era el síntoma.

**Ningún gate lo detecta**: `EKPREFIX` pasa (el prefijo sí empieza con el
`series_key`), `DUPVOL` no dispara (cada edición tiene un solo tomo, no hay volumen
repetido *dentro* de una edición) y `SLUGUNIQ`/`SLUGFMT` aprueban. Cada fila es
válida por separado; lo que está mal es la partición, y no hay invariante que la mire.
Colateral de #210 en la misma familia: el `edition_key` dice `-unknown-deluxe-pl`
aunque el campo `publisher` del item sí trae `J.P.Fantastica`.

**Efecto de producto**: la UI muestra ~29 series polacas como 156 ediciones de un
tomo cada una, en vez de 29 ediciones con sus tomos ordenados — rompe además la regla
dura "dentro de una edición, siempre orden por volumen".

**NO APLICADO** (decisión del owner: el fix cambia slugs, mismo riesgo que #213).
Propuesta: (a) denylist corta de rótulos de stock (`OSTATNIE`, `II GATUNEK`,
`PRZEDSPRZEDAŻ`, `ZAPOWIEDŹ`) aplicada al título ANTES de derivar keys; (b) excluir
el `tom NN` del `edition_key` (el tomo ya vive en `volume`); (c) invariante de
partición (warn) para familias de `edition_key` que difieren sólo en un número
embebido — general, no sólo para Polonia.

## 9. Pendientes

- Poblar aliases PL en `series_aliases.yml` (títulos polacos: "Atak Tytanów" →
  attack-on-titan, "Miecz nieśmiertelnego" → blade-of-the-immortal…) vía
  `/watch-enrich-series-aliases`.

## 10. Runbook

```bash
.venv/bin/python scripts/manga_watch.py --only-source "PL - Mangarden (JPF tapa dura)" --dry-run
.venv/bin/python scripts/manga_watch.py --only-source "PL - Mangarden (JPF preorders)" --dry-run
```

### Auditoría full — 2026-09-24

Se reconoce `tom 06` como volumen 6. Antes, los tomos sin volumen detectado
compartían clave de edición vacía y se absorbían entre sí. El volumen observado
incompatible elimina una asociación secundaria incorrecta, preservando productos.
