# Fuente: Milky Way Ediciones

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-09-15 (falso positivo de yield regression reconfirmado; §8).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Milky Way Ediciones |
| **URL base** | `https://www.milkywayediciones.com` |
| **Índice / punto de entrada** | `https://www.milkywayediciones.com/collections/proximamente` (preventas) + `search?q={query}` (búsqueda por keyword) |
| **Tipo de fuente** | Editorial (official) — tienda propia en Shopify |
| **`kind` en sources.yml** | `html` (ambas entradas) |
| **`source_class`** | `official` |
| **País(es)** | España (`es`) — fuente mono-país |
| **Idioma(s)** | Español |
| **Cobertura** | Manga publicado por Milky Way Ediciones en España (ediciones especiales/limitadas, deluxe, tapa dura, kanzenban) + preventas/próximos lanzamientos |
| **Aporte al corpus** | ~16 items |
| **Parser / módulo** | Sin parser propio — dos entradas en `sources.yml` vía extractor genérico |

**Por qué importa / qué aporta de único**: tienda oficial de la editorial Milky Way
Ediciones. Aporta sus **preventas/próximos lanzamientos** (que aún no aparecen en otras
fuentes) y sus **ediciones especiales/deluxe** vía búsqueda por keyword, directo de la
fuente primaria (`publisher = Milky Way Ediciones`, no una tienda revendedora, #44).

---

## 2. Descripción técnica de la fuente

- **Plataforma**: Shopify. Listados en `/collections/...`, fichas de producto en
  `/products/...`; la búsqueda usa `/search?q=...` (#4: Shopify usa
  `li.grid__item`/`[data-product-card]` + `/products/`).
- **Dos puntos de entrada distintos** (dos entradas del YAML, mismo dominio):
  - **`ES - Milky Way Próximamente`** (`html`): listado fijo de la colección
    `collections/proximamente` (preventas / próximos lanzamientos). Sin `selectors`
    custom → extractor genérico de Shopify.
  - **`ES - Milky Way (search)`** (`html`): `search_template`
    `https://www.milkywayediciones.com/search?q={query}`, expandido por keyword
    (ver §5).
- **Identificador de producto**: URL canónica del producto Shopify (`/products/<slug>`).
- **Calidad de imágenes**: portadas de la CDN de Shopify (`cdn.shopify.com`),
  resolución aceptable. {{pendiente: confirmar resolución típica si se vuelve relevante}}.

---

## 5. Proceso de ingestión — técnico

Sin parser propio: ambas entradas se scrapean en la **FASE 1** del pipeline
(`manga_watch.py`, sources del YAML) con el **extractor genérico de Shopify**.

- **`ES - Milky Way Próximamente`**: se recorre como una fuente HTML simple — se visita
  el listado `collections/proximamente` y cada producto del grid entra como un item.
- **`ES - Milky Way (search)`**: el `search_template` se expande a **una fuente virtual
  por keyword** (`edicion limitada`, `edicion especial`, `deluxe`, `tapa dura`,
  `kanzenban`) vía `_expand_search_template()`; cada keyword dispara un `GET`
  `search?q=<keyword>` y los resultados entran como items. El `source_purity` de la
  entrada se propaga a esos hijos search-template (#7).
- Ambas comparten `publisher = Milky Way Ediciones`, `country = España`,
  `source_class = official`. El país va al `edition_key` como `…-es` (#46).
- El merge multi-fuente es el estándar del proyecto (`consolidate_by_cluster()` en
  `manga_watch.py`, decisión #1); esta fuente no tiene reglas de agrupación propias.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **0 candidatos en "Próximamente" es NORMAL, no un selector roto** (verificado
  2026-07-07, auditoría de ingestión): cuando no hay preventas activas, Shopify
  **server-renderea el estado vacío** de la colección ("0 productos") — no es un
  fallo de `item_selector` ni de la fuente. Antes de sospechar un selector roto por
  0 items de esta fuente, confirmar primero si la colección `collections/proximamente`
  realmente tiene productos publicados en ese momento.
- **Agrupada preventivamente en `throttle_group` (2026-07-07, gotcha #114)**:
  `milkywayediciones.com` resuelve al mismo borde Shopify `23.227.38.0/24`
  (`23.227.38.32`) que Dark Horse Direct, Funside Variant y Manga Dreams — las tres
  SÍ devolvieron HTTP 429 el 2026-07-07 (Milky Way no, en esta corrida). Por
  compartir el mismo borde, `ES - Milky Way Próximamente` se agregó al
  `throttle_group: "shopify"` como medida preventiva (semáforo compartido + delay
  mínimo 2s). **`ES - Milky Way (search)` todavía NO tiene el campo seteado** — si
  llega a 429ear, agregarlo ahí también.
- **2026-09-08 — `deluxe` marcado *yield regression* (6 vs mediana 14): FALSO POSITIVO
  por mediana obsoleta.** El search rindió **6 el 09-07 y 6 el 09-08** — idéntico, no
  hay caída. La alerta salta porque la mediana del baseline (14) se calcula sobre una
  ventana que todavía incluye el régimen viejo de 13-16; la fuente se estabilizó en un
  nivel nuevo y la mediana no lo alcanzó. Mismo patrón que `BR - Editora JBC Checklist`
  (99→20, mediana 72.5). **No tocar la fuente**: `edicion especial` (19) y `tapa dura`
  (6) siguen normales, y la fuente respondió sin errores en la corrida.
  **Reconfirmado 2026-09-11**: `deluxe` rindió 6 por **cuarta corrida seguida** (09-07,
  09-08, 09-09, 09-11; HTTP 200, 33 cards) y la alerta volvió a saltar (6 vs 14). Nivel
  estable, no caída — se apagará cuando la ventana de la mediana deje atrás el régimen
  13-16.
  **Reincide 2026-09-15**: `deluxe` = 6 otra vez (mediana ya bajó de 14 a 13, 21 corridas
  en la ventana). Mismo nivel estable; sin errores ni challenges.
- **Curación LLM non-manga 2026-08-23 (gotcha #149)**: un post de
  `/blogs/news/nuevas-licencias-…` había entrado como producto con el titular como
  `title`. Fix aplicado: `_BLOG_URL_PATTERNS` en `manga_watch.py` ahora incluye
  `/blogs/[^/]+/` (en Shopify los productos viven en `/products/` y las listas en
  `/collections/`).

---

## 9. Pendientes / limitaciones conocidas

- **Sin `selectors` custom**: ambas entradas dependen del extractor genérico de Shopify.
  Si Milky Way cambia el tema de Shopify y rompe los selectores por defecto (#4), habría
  que agregar `selectors` en el YAML.
- **Variantes Shopify multi-tomo** (#16): no hay evidencia de que esta tienda modele
  packs/box sets como 1 producto = N SKUs. {{pendiente: confirmar si alguna ficha usa
  variantes de volumen; de ser así, evaluar `shopify_variants.py`}}.
- **Cobertura search-template**: limitada a las 5 keywords configuradas; ediciones
  especiales con otra nomenclatura podrían no salir en la búsqueda.
- **Watchlist benigna (2026-08-24)**: `ES - Milky Way Próximamente` y
  `ES - Milky Way (search) [search: kanzenban]` dieron 0 candidatos en las 3
  últimas corridas medidas (2026-07-07, 2026-08-22, 2026-08-24 —
  `logs/metrics.jsonl`). Decisión del owner: **NO podar** — 0 items en 3
  corridas puede significar simplemente que no hubo ediciones especiales
  nuevas / con la keyword "kanzenban" en esa ventana, no que el selector esté
  roto (`status: healthy`, `errors: 0` en las 3). Validar selectores recién si
  llegan a 0 con un corpus shift visible o pasan >3 meses sin ningún candidato.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente (preventas):
.venv/bin/python scripts/manga_watch.py --only-source "ES - Milky Way Próximamente"

# Scrape sólo la búsqueda por keyword:
.venv/bin/python scripts/manga_watch.py --only-source "ES - Milky Way (search)"

# Validar (gate estructural, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "milkywayediciones"
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

## 2026-09-16 — `deluxe` a 6: tercera medición igual, la mediana es la obsoleta

`source_health` volvió a marcar `ES - Milky Way (search) [search: deluxe] | 6 |
mediana 13 | 46%`. Es la **tercera corrida consecutiva con el mismo 6** (2026-09-07,
09-08 y hoy), contra una mediana que arrastra valores viejos. Las otras searches del
mismo host rindieron normal en la misma corrida (`edicion limitada` 20,
`edicion especial` 18, `tapa dura` 6, `kanzenban` 0), así que no hay avería de host ni
de parser: el catálogo deluxe de Milky Way simplemente tiene ese tamaño ahora.

Ya anotado el 2026-09-08 como "no hay caída"; queda aquí la confirmación para no
volver a diagnosticarlo. Mismo patrón que gotcha #190 (mediana histórica obsoleta que
dispara falsos positivos indefinidamente).

## 2026-09-17 — `deluxe` rinde 6 por cuarta corrida seguida

`ES - Milky Way (search) [search: deluxe]`: **6 candidatos**, igual que el 09-16, el 09-15
y el 09-08. Mediana del baseline: 13.

Cuatro corridas con el MISMO valor no son una caída — son el nivel real de la búsqueda. La
mediana de 13 es histórica y ya no describe a la fuente. Las otras searches del mismo host
rindieron normal en la misma corrida (`edicion limitada` 20, `edicion especial` 19,
`tapa dura` 6), así que **no hay problema de host, de UA ni de parser**.

**Para el owner (no aplicado):** re-basar la mediana de esta search. Mismo caso que las
searches de Dark Horse y que JBC — ver `us-dark-horse-direct.md` § 2026-09-17.

## 2026-09-18 — `deluxe` 6 (5ª corrida igual); entra un cuaderno como "artbook"

Mediana obsoleta, sin avería. Entró además `Atelier of Witch Hat Notebook` (papelería,
cuaderno de la franquicia): el LLM lo marcó `is_manga=false` y quedó en curación.

### Reparación de referencias históricas — 2026-09-24

Se quitó 1 referencia de `www.milkywayediciones.com` asociada a otra fila con ISBN
válido diferente del producto cuya URL primaria es esa misma referencia. Se
conservan ambos productos y su URL primaria; no se fusionan por ISBN. Evidencia
por URL/ISBN en `reports/ingestion-audit-2026-09-24/closure/publication-2-manifest.json`.

### Caché de imágenes — auditoría 2026-09-25

El inventario detectó referencias locales con nombres derivados de una normalización
legacy que descartaba parámetros de URL. Se desactivó esa reutilización ambigua;
se preservan parámetros de identidad/versión. Esto es un riesgo del caché local,
no prueba de un producto incorrecto en esta fuente. La revisión por URL y el
resultado de las re-descargas están en `reports/image-audit-2026-09-25/`. Ante
contenido cambiado o descarga fallida se conserva la imagen anterior.
