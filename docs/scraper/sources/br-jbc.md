# Fuente: Editora JBC

> ⚠️ **PODA 2026-06-12 (poda de fuentes muertas)** — `BR - Editora JBC Títulos`: Títulos deshabilitada (80 candidatos/run → 1 neto); JBC Checklist sigue activa y cubre la editorial.
> Registro completo: [descartadas/README.md](descartadas/README.md).

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-09-08 (yield regression recurrente = mediana obsoleta; §8).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Editora JBC |
| **URL base** | `https://editorajbc.com.br` |
| **Índice / punto de entrada** | Dos entradas en `sources.yml`: checklist mensual (`/checklist/atual/`) y catálogo completo (`/titulos/`) |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | Brasil (`Brasil`) — fuente mono-país |
| **Idioma(s)** | Portugués (PT-BR) |
| **Cobertura** | Catálogo de manga de Editora JBC: checklist mensual (~184 items/mes) + catálogo completo (~565 títulos) |
| **Aporte al corpus** | 5 items (al último corpus; ver §10) |
| **Parser / módulo** | Dos entradas en `sources.yml` (extractor genérico, sin módulo propio) |

**Editoriales que abarca** (del corpus real): Editora JBC (5 items, todos `Brasil`).

**Por qué importa / qué aporta de único**: cubre el catálogo oficial de Editora JBC,
una de las editoriales de manga de Brasil. Aporta presencia del mercado brasileño (PT-BR)
desde la propia editorial.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: sitio WordPress.
  - `/checklist/atual/` — checklist del mes (lanzamientos físicos, digitales,
    reimpresiones), página única.
  - `/titulos/` — catálogo completo, paginado (`max_pages: 5`).
  - URL de producto: `/mangas/colecao/<serie>/vol/<vol>/`.
- **Estructura del HTML**: cada producto es un card `div.card.item-mangas`. El título
  se toma del `<strong>` directo del card.
- **Identificador de producto**: la URL canónica del producto (`/mangas/colecao/<serie>/vol/<vol>/`).
- **Anti-bot / quirks**: ver el quirk del título en §5 y §8.

---

## 5. Proceso de ingestión — técnico

Ambas entradas se scrapean en **FASE 1** del pipeline (sources del YAML vía
`manga_watch.py`), usando el **extractor genérico** con los selectores declarados.
**No hay parser/módulo propio.**

- **`BR - Editora JBC Checklist`** (`/checklist/atual/`): checklist mensual,
  ~184 items/mes. Sin paginación.
- **`BR - Editora JBC Títulos`** (`/titulos/`): catálogo completo, ~565 títulos,
  con `max_pages: 5`.

Ambas comparten selectores:

```yaml
selectors:
  item_selector: "div.card.item-mangas"
  title_selector: "strong"
```

**Quirk del título en `<strong>`** (saca selectors/notes verbatim): el título se
extrae del `<strong>` directo **a propósito**. El anchor del card
(`a.post-selo-catalog-volume`) contiene un `<span>` con el texto "mais detalhes",
que **contaminaría** el título si se usara el anchor como `title_selector`. Por eso
se apunta al `<strong>` directo en lugar del anchor.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Título contaminado por "mais detalhes"** — el anchor `a.post-selo-catalog-volume`
  del card incluye un `<span>` "mais detalhes"; usarlo como `title_selector` ensuciaría
  el título. → ✅ Se usa el `<strong>` directo del card.
- **2026-09-08 — la *yield regression* recurrente es MEDIANA OBSOLETA, no una avería**
  (cierra el diagnóstico abierto de gotcha #190). La serie histórica de candidatos es
  `[99, 99, 20, 20, 20, 20, 20, 20, 20, 20]`: la fuente cambió de régimen UNA vez
  (99 → 20) y desde entonces lleva **8 corridas clavada en 20**. La mediana del baseline
  (72.5) sigue arrastrando los dos 99 viejos, así que `20 / 72.5 = 28%` dispara la
  alerta TODAS las corridas y lo seguirá haciendo hasta que los 99 salgan de la ventana.
  No es "el checklist se va llenando durante el mes" (esa hipótesis ya quedó refutada el
  09-05) ni la forma-calendario: es puramente el baseline. **Ninguna acción sobre la
  fuente**; lo que habría que ajustar es la ventana/robustez del baseline en
  `scripts/audit/source_health.py` — decisión del owner.

---

## 9. Pendientes / limitaciones conocidas

- **Aporte bajo al corpus** (5 items): {{pendiente: confirmar si es esperado por el
  filtro de coleccionables o si hay sub-captura — la editorial publica ~565 títulos}}.
- {{pendiente: comportamiento full vs delta — ambas entradas se scrapean igual siempre;
  no hay distinción full/delta documentada para esta fuente}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente (ajustar al nombre exacto de la entrada):
.venv/bin/python scripts/manga_watch.py --only-source "BR - Editora JBC Checklist"
.venv/bin/python scripts/manga_watch.py --only-source "BR - Editora JBC Títulos"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "editorajbc"
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

---

## 2026-09-01 — caída de yield del checklist (99 → 20, primer día del mes)

Delta diario (`logs/scrape-delta-2026-09-01-110203/`). `source_health` marca
**YIELD REGRESSION** en `BR - Editora JBC Checklist`: 20 candidatos contra una mediana
histórica de 99 sobre 9 corridas (20% de la mediana).

Datos duros del run:
- La URL respondió normal — sin error HTTP, sin challenge, sin skip: la línea del log
  es `[BR - Editora JBC Checklist] candidatos con señales: 20`.
- La mediana venía **clavada en 99.0** en las 6 corridas anteriores (08-25, 08-26,
  08-28, 08-29, 08-30, 08-31), o sea no es deriva progresiva: es un escalón.
- La otra entrada de la fuente (`BR - Editora JBC Títulos`) no aparece marcada.

**Hipótesis principal (no verificada)**: la entrada apunta a
`https://editorajbc.com.br/checklist/atual/` — un checklist **del mes en curso**. Hoy
es 1 de septiembre; lo esperable es que la editorial acabe de rotar la página al mes
nuevo y que todavía tenga pocos lanzamientos cargados, contra un agosto ya completo.
Si es eso, el yield debería recuperarse solo en los próximos días y no hay nada que
arreglar. La hipótesis alternativa —cambio de markup/selectores que dejó de ver parte
de la grilla— no se puede descartar sin inspeccionar el HTML actual.

**No aplicado**: nada. Recomendación al owner: re-chequear el conteo dentro de 3-5
días. Si sigue en ~20 con el mes ya poblado, ahí sí hay que revisar los selectores de
`/checklist/atual/` (no antes: tocar selectores por un falso positivo de rotación de
mes es peor que esperar).

## 2026-09-02 — regresión de yield: 20 candidatos contra una mediana de 99

Delta diario (`logs/scrape-delta-2026-09-02-110142/`). Único 🚨 YIELD REGRESSION del run:
`BR - Editora JBC Checklist` devolvió 20 candidatos contra una mediana histórica de 99
sobre 10 corridas (20% de la mediana). Sin errores, sin challenge, sin skips — la fuente
respondió, simplemente trajo mucho menos.

Sin diagnóstico todavía: puede ser el checklist real de JBC más corto este mes
(estacional, plausible en una página de "lançamentos") o un cambio de marcado que dejó
al parser viendo sólo parte de la grilla. Se necesita una segunda corrida para separar
las dos hipótesis — un mes flojo se recupera solo, un parser roto no.

Nada aplicado. Si en el próximo delta sigue en ~20, revisar los selectores contra la
página en vivo.

### RESUELTO (2026-09-02) — falso positivo de calendario, la fuente está sana

Verificado EN VIVO el mismo día: `editorajbc.com.br/checklist/atual/` devolvió HTTP 200,
encabezado **"Checklist – 3º trimestre de 2026"**, mes en curso **"Setembro de 2026"**,
**20 cards** y sin paginación. El selector `div.card.item-mangas` + `strong` parsea los
20 títulos perfecto (`Akane-Banashi #09`, `Blue Box #09`, `Cherry Magic #10`,
`Haikyu!! #22`, …). **No hay nada roto y no se tocó ningún selector.**

La causa de la alerta: el checklist es del MES EN CURSO y se va llenando a lo largo del
mes. El 2 de septiembre tenía 20 entradas; la mediana de 99 se calcula sobre corridas de
meses ya completos. La comparación era entre un mes a medio publicar y meses enteros.

Generalizado como gotcha #190: `source_health --baseline-alert` va a dar este falso
positivo a principio de mes en TODA fuente con forma de calendario. Antes de tocar
selectores por una alerta de yield en una de ellas, verificar en vivo cuántos items tiene
la página ese día.

### 2026-09-03 — la predicción de la gotcha #190 se cumplió (2º día seguido)

El delta de hoy (3 de septiembre) volvió a marcar la fuente como 🚨 YIELD REGRESSION:
**20 candidatos vs mediana 99 (20%)**, exactamente el mismo cuadro que ayer. Y otra vez es
**falso positivo**: el scrape corrió sano — `https://editorajbc.com.br/checklist/atual/`
respondió, 20 candidatos con señales, items extraídos con ISBN e imágenes, `errores: 0`.

La causa es la de siempre: el checklist es **el mes en curso**, así que a principio de mes
la página tiene una fracción de lo que tendrá al cierre, y la mediana histórica está
calculada sobre corridas de mes avanzado. La alerta debería reaparecer cada primeros de
mes y desaparecer sola.

**No se tocó nada.** Confirmación de que la regla de #190 aplica: ante una alerta de yield
en una fuente con forma de calendario, mirar el día del mes antes que los selectores.

---

## 2026-09-04 — 3ª confirmación consecutiva: el flag de yield es estacional, no una avería

`source_health --baseline-alert` volvió a marcar **20 candidatos vs mediana 99 (20%)**,
idéntico al 09-01 y al 09-02. Tercer flag seguido con **exactamente el mismo número**.

Eso cierra la duda que quedaba abierta: **20 no es un yield degradado, es el checklist
completo de principio de mes**. `editorajbc.com.br/checklist/atual/` publica el mes en
curso; los primeros días lista sólo los lanzamientos ya confirmados y se va llenando. La
mediana de 99 es el promedio de corridas tomadas a mitad/fin de mes, así que comparar
contra ella al día 1-4 **siempre** va a dar ~20%.

Es la gotcha **#190** en vivo por tercera vez: `source_health` da falso positivo de yield
en fuentes con **forma de calendario**, porque su baseline no tiene noción de en qué
punto del ciclo se tomó la muestra.

**Nada que arreglar en la fuente** (el parser está sano: 20 candidatos, 0 errores, 0
challenges). Lo que se puede mejorar algún día es `source_health`: normalizar el baseline
de las fuentes tipo calendario por día-del-mes, o marcarlas para que no disparen alerta
en la primera semana. Mientras no se haga, **este flag es ruido esperable los primeros
días de cada mes** y no debería consumir atención del owner.

## 2026-09-05 — 4ª confirmación: el checklist NO se va llenando durante el mes

`source_health --baseline-alert`: otra vez **20 candidatos vs mediana 99 (20%)**, con 0
errores y 0 challenges. Cuarto flag consecutivo con **exactamente el mismo número** (09-01,
09-02, 09-04, 09-05).

Esto **refina** la explicación del 2026-09-04. Ahí se dijo que el checklist "publica el mes
en curso; los primeros días lista sólo los lanzamientos ya confirmados y **se va
llenando**". Con el dato de hoy —día 5 del mes, todavía 20— esa parte no se sostiene: si
se fuera llenando progresivamente, para el día 5 el conteo debería haber subido. Lo que sí
se sostiene es lo central: **20 no es un yield degradado**. La lectura más consistente con
las 4 muestras es que `checklist/atual/` expone un bloque estable de ~20 entradas durante
buena parte del mes y la mediana de 99 viene de corridas tomadas en otro punto del ciclo
(o de una versión anterior de la página).

Sigue sin haber nada que arreglar en la fuente. Lo que cambia es la recomendación sobre
`source_health` (gotcha #190): en vez de "no alertar la primera semana", lo correcto para
esta fuente sería **no compararla contra una mediana global** — su baseline necesita
noción del punto del ciclo, o directamente un umbral propio. Mientras tanto, el flag de
JBC es ruido conocido: 4 corridas seguidas sin señal nueva.

### 2026-09-07 — 5ª muestra: 20 otra vez, con el mes ya avanzado

Día 7 del mes, `checklist/atual/` → **20 candidatos**, idéntico a las 4 muestras previas
(20 el 09-02, 09-05 y 09-06). El reporte de salud lo vuelve a marcar 🔴 (20 vs mediana 99,
20%), quinta vez consecutiva.

Refuerza la conclusión ya escrita arriba y descarta definitivamente la hipótesis del
"checklist que se va llenando": cinco lecturas en seis días, todas exactamente 20. El
bloque es **estable**, no progresivo. La mediana de 99 pertenece a otro régimen de la
página, no a un yield que hoy esté degradado.

Nada que arreglar en la fuente. La deuda sigue siendo del comparador de `source_health`
(gotcha #190): esta fuente necesita baseline propio, no la mediana global.
