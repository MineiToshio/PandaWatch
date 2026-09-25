# Fuente: Delcourt / Tonkam

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-09-15 (falso positivo de yield regression reincidente; §8).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | FR - Delcourt / Tonkam Mangas |
| **URL base** | `https://www.editions-delcourt.fr/mangas` |
| **Índice / punto de entrada** | `https://www.editions-delcourt.fr/mangas` (paginado, `max_pages: 15`) |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | Francia (el país de la edición va al `edition_key`) |
| **Idioma(s)** | Francés |
| **Cobertura** | Catálogo de manga de la editorial francesa Delcourt / Tonkam |
| **Aporte al corpus** | 4 items (todos `country=Francia`, `publisher=Delcourt / Tonkam`) |
| **Parser / módulo** | Entrada en `sources.yml` (extractor genérico, sin parser propio) |

**Por qué importa / qué aporta de único**: editorial oficial francesa con ediciones
prestige (`tags` incluye `"prestige"`); aporta ediciones especiales del mercado FR que
no necesariamente cubren las tiendas/catálogos comunitarios.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: listado paginado bajo `editions-delcourt.fr/mangas`,
  recorrido hasta `max_pages: 15`. Página de producto por título.
- **Estructura del HTML/feed**: la entrada del YAML **no define `selectors`** → se usa la
  **auto-detección** del extractor genérico (sin recetas de selectores propias).
- **Identificador de producto**: {{pendiente: SKU / ISBN / URL canónica — no confirmado}}.
- **Anti-bot / quirks**: posible **mojibake FR (#1)** — editoriales/portales franceses
  suelen devolver UTF-8 decodificado como cp1252; `clean_title()::_fix_mojibake()` lo
  repara primero. Otros quirks {{pendiente: no confirmados}}.
- **Calidad de imágenes**: {{pendiente: no confirmada}}.

---

## 5. Proceso de ingestión — técnico

- **Entrada**: `sources.yml` → `"FR - Delcourt / Tonkam Mangas"` (`kind: html`,
  `enabled: true`, `max_pages: 15`, `tags: ["manga", "official", "prestige"]`).
- **Captura**: se scrapea en la **FASE 1** del pipeline (`manga_watch.py --workers 8`),
  vía el **extractor genérico** de fuentes HTML. **No tiene parser propio** ni `selectors`
  definidos → auto-detección de label/value.
- **Filtros**: pasa por las reglas estándar del pipeline (`is_likely_manga`, pureza,
  filtros de coleccionable) como cualquier fuente del YAML; sin reglas dedicadas.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#1 (mojibake FR)** — fuentes francesas pueden devolver acentos corruptos; lo repara
  `_fix_mojibake()` en `clean_title()`. No metas regex-cleaning antes de esa reparación.
- **2026-09-11 — *yield regression* 🔴 (0 vs mediana 1): FALSO POSITIVO, la mediana la
  sostenía una señal espuria.** `source_health --baseline-alert` la marcó por caer de 1 a
  0 candidatos. Verificado: la página responde normal (HTTP 200, 312 KB, 34 cards
  detectadas — contra 36 cards y 319 KB el 09-09). Lo que cambió es que salió de la
  portada rotativa el único candidato que la fuente venía entregando **12 corridas
  seguidas** (08-30 → 09-09): la card `Color Collection`, que sólo matcheaba la señal
  fuzzy `color` (`páginas a color [fuzzy:color]`) y **nunca llegó al corpus** (0 items con
  esa URL). O sea, la mediana de 1 medía un falso candidato, no una edición especial. Los 8
  items reales de Delcourt del corpus (prestige/collector/perfect edition) entraron en
  corridas anteriores. **No tocar la fuente.**
  **Reincide 2026-09-15** (0 vs mediana 1, 21 corridas en la ventana): mismo falso
  positivo, 0 errores/challenges en el log. Se apagará cuando la ventana deje atrás las
  12 corridas de la card espuria `Color Collection`.
- **Observación (sin verificar el porqué)**: pese a `max_pages: 15`, el diagnóstico de
  09-09 y de 09-11 no reporta `Páginas visitadas` — el extractor recorre sólo la primera
  página del listado. Explicaría el aporte bajo de §9; confirmarlo requiere revisar la
  paginación del sitio (decisión del owner si vale la pena).

---

## 9. Pendientes / limitaciones conocidas

- **Aporte bajo (4 items)**: con `max_pages: 15` y auto-detección, la cobertura real es
  pequeña. {{pendiente: confirmar si es problema de selectores/auto-detección o catálogo
  acotado}}.
- **Sin `selectors` propios**: depende por completo de la auto-detección genérica; si el
  layout del sitio cambia, la captura puede degradarse silenciosamente.
- **`notes` en el YAML**: la entrada **no tiene** campo `notes`.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "FR - Delcourt / Tonkam Mangas"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver items reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "editions-delcourt"
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
→ tests (`pytest tests/test_extraction.py`) → build.

## 2026-09-16 — yield 0 contra mediana 1: ruido estadístico

`source_health` marcó `FR - Delcourt / Tonkam Mangas | 0 | mediana 1 | 0%` como
regresión 🔴. La fuente tiene mediana **1**, así que cualquier corrida sin novedades
la marca en rojo con "0% de la mediana". Sin errores, sin challenge, sin skip: el log
del run dice `candidatos con señales: 0` y nada más. Es el mismo artefacto de umbral
que Dark Horse `slipcase` (mediana 1) — **una mediana de 1 hace que el detector de
regresiones sea binario**. No investigar como avería salvo que se acumulen varias
corridas seguidas Y el sitio tenga novedades visibles.

## 2026-09-17 — 0 candidatos: verificado sano, falso positivo del baseline

`FR - Delcourt / Tonkam Mangas`: **0 candidatos con señales**, sin error ni skip. El
reporte lo listó como 🔴 con mediana 1 (23 corridas históricas).

Verificado en vivo el mismo día:

```
curl -sL https://www.editions-delcourt.fr/mangas
→ 200, 314 224 bytes
grep -oi deluxe → 10 apariciones
```

Las **10 apariciones de `deluxe` son el MISMO archivo de imagen**
(`2022-02/hikaru-no-go-deluxe-homepage-vignette.{jpg,webp}` repetido en `srcset`,
`<source>` y variantes retina) — un banner de portada de 2022, **no productos**. La página
de novedades simplemente no tiene ediciones especiales publicadas hoy.

**No hay avería.** Con mediana 1, cualquier corrida en 0 dispara "0% de la mediana" y la
fuente aparece en rojo arriba de todo el reporte. Es ruido estructural de fuentes de
yield bajo, no una señal.

**Para el owner (no aplicado):** suprimir la alerta de regresión cuando la mediana
histórica es ≤ 2 (no hay señal estadística que extraer de un 1 → 0).

## 2026-09-18 — 0 candidatos otra vez

Mismo falso positivo del baseline que el 09-16/09-17 (mediana 1).

## 2026-09-21 — 0 items, mediana obsoleta (sin cambio de diagnóstico)

El reporte de salud del delta marcó 🔴 `FR - Delcourt / Tonkam Mangas` con 0 vs mediana 1
(27 corridas). Mismo cuadro ya cerrado en esta ficha: la mediana de 1 es residuo histórico
y un 0 no distingue "avería" de "no hubo novedades". Dato que lo respalda: en la MISMA
corrida entró un producto nuevo con publisher Delcourt/Tonkam (*Jojolands 6* collector
Comptoir du Rêve) pero vía **Manga-Sanctuary**, no por esta fuente — o sea la novedad
existía y esta entrada no la lista. Sigue siendo cobertura del parser, no caída del host.
Nada aplicado.


## Revisión de ingestión — 2026-09-24

El sondeo volvió a dar cero candidatos. Se conserva el diagnóstico previo: cero señales no demuestra ruptura del selector (la mediana anterior contenía un falso positivo fuzzy). No se cambió ni deshabilitó la fuente.

Evidencia y alcance: [auditoría integral](../audits/2026-09-24-ingestion.md).

## Auditoría estratégica — 2026-09-25

El endpoint /mangas era portada/novedades y llevaba tres deltas con cero candidatos.
Se sustituye por /mangas/liste-mangas (150 páginas observadas). Selector de tarjetas
album-thumbnail restringido a enlaces de producto /mangas/.../album-; recomendaciones
/bd/ quedan fuera. FULL/DELTA administrados siguen toda la paginación; ensayo aislado
en reports/source-strategy-2026-09-25/delcourt. Retener el catálogo oficial complementa
Manga-Sanctuary; no asumir equivalencia total por pocas coincidencias históricas.

Auditoría 2026-09-25: Médaka-Box no es un box set por llevar «Box» en el nombre;
se corrige el caso separado por guion. Double Edition / Edition double tampoco
prueba formato premium; requiere hardcover, collector u otra señal adicional.
Las cajas y versiones premium reales de esas series siguen admitidas.
