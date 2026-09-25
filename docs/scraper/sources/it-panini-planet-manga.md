# Fuente: Panini / Planet Manga (Italia)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-09-23 (Queue-it #208 7º día: 18 source-runs saltados y el listado
> principal con yield parcial silencioso 47 vs mediana 75).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Panini / Planet Manga (Italia) |
| **URL base** | `https://www.panini.it/shp_ita_it/` |
| **Tipo de fuente** | Editorial oficial (Planet Manga es el sello de manga de Panini Italia) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País** | Italia — código que va al edition_key |
| **Idioma** | Italiano (IT) |
| **`publisher`** | `Panini / Planet Manga` (editorial real, no una tienda — #44 no aplica) |
| **Cobertura** | Catálogo de manga italiano de Planet Manga, con dos categorías de coleccionables directas |
| **Aporte al corpus** | ~142 items (re-ingest 2026-06-10: 128 → 142 con los tags `search:`; todos `country=Italia`) |
| **Parser / módulo** | Entrada(s) en `sources.yml` (sin parser propio) |

Son **tres entradas YAML del mismo sitio** (`panini.it`):

| `name` | URL |
|---|---|
| `IT - Panini Planet Manga` | `…/shp_ita_it/planet-manga.html` |
| `IT - Panini Variant ed Esclusive` | `…/planet-manga/tipologia/variant-ed-esclusive.html` |
| `IT - Panini Edizioni da Collezione e Cofanetti` | `…/planet-manga/tipologia/edizioni-da-collezione-e-cofanetti.html` |

**Por qué importa / qué aporta de único**: cubre el mercado italiano (IT) desde la
editorial oficial. Las dos últimas entradas apuntan directo a categorías de
**coleccionables**: *variant ed esclusive* (variantes y exclusivas) y *edizioni da
collezione e cofanetti* (ediciones de colección y cofres/box sets). Son justo el tipo
de producto que busca PandaWatch, sin tener que filtrar el catálogo general.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: tienda Magento. La entrada principal es la landing
  de Planet Manga; las otras dos son categorías filtradas por *tipologia* (variant/
  esclusive y edizioni da collezione/cofanetti). Cada listado enlaza a las páginas de
  producto del catálogo.
- **Selectores**: las tres entradas **no declaran selectores** en `sources.yml` → se
  apoyan en la **auto-detección genérica del extractor** (layout Magento estándar:
  título, imagen de producto).
- **Identificador de producto**: URL canónica del producto Magento.
- **`publisher` = Panini / Planet Manga** es editorial real; #44 (tienda≠editorial) no
  aplica.
- **Idioma italiano**: los títulos traen acentos (è, à…). No se confirmó mojibake en
  esta fuente; #1 (mojibake) está documentado sólo para FR (Glénat/Pika), no para
  panini.it. {{pendiente: confirmar si panini.it necesita el fix de encoding}}

---

## 5. Proceso de ingestión — técnico

- **Entradas en `sources.yml`**: las tres listadas en §1 (`kind: html`,
  `source_class: official`, `enabled: true`).
- **Fase del pipeline**: se scrapean en **FASE 1** (sources del YAML vía
  `manga_watch.py --workers 8`), junto al resto de fuentes simples. **NO tiene parser
  propio** ni paso de bootstrap-wiki: usa el **extractor genérico** de productos.
- Luego pasan por los retrofits de cleanup estándar (FASE 3: rescore → filtros →
  clean_titles → backfill de metadata/imágenes) como cualquier fuente del YAML.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- Sin parser propio: el comportamiento depende del extractor genérico Magento. Cualquier
  problema de captura es del extractor compartido, no de un módulo de esta fuente.
- **Títulos "bare" sin señal en las categorías coleccionables (audit 2026-06-10)**: las
  categorías "Variant ed Esclusive" y "Edizioni da Collezione e Cofanetti" listan títulos
  pelados ("Sakamoto Days 25") sin keyword de edición en el card → `detect_signals` daba
  0 y el gate de `manga_watch.py` descartaba ~50 items IT pese a que la categoría entera
  ES coleccionable. ✅ Fix: se agregó un tag `search:` a cada entrada en `sources.yml`
  (`"search:variant esclusiva"` y `"search:edizione da collezione cofanetto"`); el gate
  inyecta ese keyword en el texto combinado (mecanismo existente de search-context,
  `manga_watch.py` ~5001-5009), y en `score_candidate` los items sin señal propia reciben
  score base 10 (no decisivo — el keyword NO entra a `signal_types` ni rescata
  `is_collectible_edition`). **Efecto secundario conocido**: las sources con tag
  `search:` quedan excluidas del sitemap mining (filtro en `manga_watch.py` ~6927);
  aceptable porque estas dos categorías se scrapean como listings HTML normales.
- **Resultado del re-scrape con los tags `search:` (2026-06-10)**: las dos categorías
  coleccionables aportaron 54 flushes (6 Variant + 48 Edizioni/Cofanetti) → +14 items netos
  tras consolidar (varios ya existían vía AnimeClick). Entraron variantes Lucca Comics,
  cofanetti (Noblesse, Billy Bat, Food Wars, Berserk Serie Nera) y Ultimate Deluxe.
  **Limitación verificada**: el tag `search:` rescata el gate de SEÑALES pero NO
  `is_collectible_edition` — un título bare en la categoría Variant ("Sakamoto Days 25",
  "Spy x Family 1") sigue muriendo con reason `regular_tomo` (44/50 descartados en esa
  corrida). Sólo entran los items con keyword de edición en el propio título. Ver §9.
- {{pendiente: no se registró ningún otro problema específico de panini.it (mojibake,
  anti-bot, lazy-loading de imágenes) en esta revisión.}}

---

## 9. Pendientes / limitaciones conocidas

- Las tres entradas dependen de la **auto-detección genérica**; si Panini cambia el
  layout Magento, hay que revisar la extracción (no hay selectores fijos que ajustar).
- {{pendiente: encoding/mojibake IT sin confirmar (ver §2).}}
- **Variantes con título bare siguen fuera del corpus**: el fix de `search:` tags no
  rescata `is_collectible_edition` (decisión del audit 2026-06-10 — el keyword no es
  decisivo), así que la mayoría de la categoría "Variant ed Esclusive" (títulos pelados
  tipo "Sakamoto Days 25") queda descartada como `regular_tomo`. Si se quiere capturarla
  completa haría falta un bypass tipo `variant-catalog` o que el gate considere el
  search-context — decisión de producto pendiente del owner.
- {{pendiente: cobertura full vs delta sin diferenciar — hoy se scrapea igual siempre
  (es una fuente simple del YAML).}}

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo estas entradas (ajustar el name exacto):
.venv/bin/python scripts/manga_watch.py --only-source "IT - Panini Planet Manga"
.venv/bin/python scripts/manga_watch.py --only-source "IT - Panini Variant ed Esclusive"
.venv/bin/python scripts/manga_watch.py --only-source "IT - Panini Edizioni da Collezione e Cofanetti"

# Validar (gate estructural, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "panini.it"
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

## 2026-09-06 — el nombre del producto puede venir SIN el número de tomo (el SKU sí lo lleva)

El delta trajo 3 items hermanos de la misma edición (`one-punch-man-panini-cofanetto-it`):

| Título capturado | SKU | `volume` |
|---|---|---|
| One-Punch Man Special Edition | `MMAON054ISBNV_IT08` | *(vacío)* |
| One-Punch Man Special Edition 34 | `MMAON055ISBN_IT08` | 34 |
| One-Punch Man Special Edition 35 | `MMAON056ISBN_IT08` | 35 |

Verificado en vivo contra la página (HTTP 200): el primero **no es una página de índice ni
de categoría** — es un producto real, con su propio SKU, su JSON-LD `@type: Product` y una
descripción de argumento propia (el enfrentamiento Garo vs Saitama). Simplemente Panini
publicó ese producto con el número de tomo ausente del nombre.

Como el parser deriva `volume` del título, el item entra **sin volumen** y queda como
hermano huérfano dentro de un `edition_key` cuyos otros miembros sí están numerados. No
dispara ninguna violación dura (`validate_corpus` da 0 duras); sí es el tipo de fila que
rompe el orden por volumen dentro de la edición.

El SKU codifica la secuencia (`054`/`055`/`056`) y el sufijo difiere (`ISBNV` vs `ISBN`),
lo que sugiere —**hipótesis, no verificada**— que el item sin número es una variante del
tomo que precede a los otros dos. No se dedujo el número: inferirlo del SKU sería adivinar.

**Nada aplicado.** Recomendación, en orden de retorno:

1. **Fallback de `volume` por SKU** para esta fuente: cuando el título no trae número y el
   SKU matchea el patrón de la serie, usar la secuencia del SKU para ordenar (NO para
   inventar el número de tomo: ordenar ≠ numerar). Resuelve el orden sin arriesgar dato
   falso.
2. **Dejarlo como está** y aceptar el item sin volumen. Es 1 item; el costo de un fallback
   mal calibrado (numerar mal un tomo) es peor que el de un hueco visible.

La recomendación es la 2 salvo que el patrón se vuelva recurrente en esta fuente.

## 2026-09-13 — la fecha de salida está en el listado ("Fumetti 17/09/26") y no se extrae (gotcha #206)

Delta diario (`logs/scrape-delta-2026-09-13-110143/`). Las dos novedades del día de esta
fuente, `Atelier of Witch Hat – Grimoire Edition 3` y
`Ken Il Guerriero: Le Origini Del Mito Extreme Edition 12`, entraron **sin
`release_date`**, aunque el texto capturado del listado dice
`… Fumetti 17/09/26 Prezzo predefinito …`. Salen el 2026-09-17, así que el catálogo no las
muestra como preventa.

**No es un caso aislado.** Medido sobre las tres fuentes `IT - Panini*`:

| | Items |
|---|---:|
| Items de Panini Italia | 183 |
| Sin `release_date` | 158 |
| … con `Fumetti dd/mm/yy` en la descripción | **150** |
| … de esos, con fecha futura | 2 |

Por fuente: Edizioni da Collezione e Cofanetti 87, Planet Manga 46, Variant ed Esclusive 17.

**Causa:** el patrón numérico de `RELEASE_DATE_PATTERNS` (`manga_watch.py`) es
`\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}`, que exige **año de 4 dígitos**. Panini Italia usa año de
2. Verificado:

```
extract_release_date("… Fumetti 17/09/26 Prezzo …", "Italia")   → ''
extract_release_date("… Fumetti 17/09/2026 Prezzo …", "Italia") → '2026-09-17'
normalize_release_date("17/09/26", "Italia")                    → '17/09/26' (sin ISO)
```

**Para el owner (no aplicado):** reconocer `dd/mm/yy`, pero **anclado a la etiqueta**
(`Fumetti\s+\d{2}/\d{2}/\d{2}`) o a países con día primero. Un patrón suelto de año de 2
dígitos es ambiguo (en fuentes US sería `mm/dd/yy`) y puede matchear números que no son
fechas. Con test y re-extracción acotada a estas fuentes. Retorno: 150 fechas recuperadas
y las preventas de Panini Italia visibles a tiempo.

## 2026-09-16 — Queue-it también en `panini.it` (gotcha #208)

Corrida `logs/scrape-delta-2026-09-16-110158`. De las 3 entradas de `panini.it`:

| Fuente | Candidatos | Mediana | Nota |
|---|--:|--:|---|
| IT - Panini Planet Manga | 75 | — | OK |
| IT - Panini Variant ed Esclusive | 14 | 54 | 🚨 26% de la mediana |
| IT - Panini Edizioni da Collezione e Cofanetti | 0 | — | `[SKIP-empty]` 2354 chars |

El skip dice *"HTML muy corto… probablemente JS-rendered"*, pero verificado en vivo
el mismo día:

```
curl -sL "https://www.panini.it/shp_ita_it/planet-manga/tipologia/edizioni-da-collezione-e-cofanetti.html"
→ 302 → https://panini.queue-it.net/?c=panini&e=paniniitaly&…  (2340 chars)
```

Es la **sala de espera de Queue-it**, el mismo mecanismo que se destapó en
`panini.es` (ficha `es-panini-espana.md`, gotcha #208). En la verificación posterior
al run también `planet-manga.html` —la que había rendido 75— caía en la cola, así que
la cola se activa progresivamente y **no es una avería de parser**.

**Lectura del yield regression de `Variant ed Esclusive` (14 vs 54):** compatible con
que la cola haya entrado a mitad de la paginación. No hay evidencia de cambio de
selectores ni de catálogo; conviene re-medirlo en la próxima corrida antes de tocar
nada.

**Recomendación (decisión del owner):** misma que en la ficha ES — detectar
`queue-it.net` en la URL final y clasificarlo como challenge, no como `empty`;
`--enable-js` no resuelve nada acá.

## 2026-09-17 — La cola alcanza el listado principal; paginación truncada a 2 págs

Corrida `logs/scrape-delta-2026-09-17-110139`. Segundo día consecutivo de Queue-it, y
esta vez **la fuente que ayer estaba sana es la que se degradó**:

| Fuente | Hoy | Ayer | Mediana | Nota |
|---|--:|--:|--:|---|
| IT - Panini Planet Manga | **16 (2 págs)** | 75 | 75 | 🚨 21% de la mediana |
| IT - Panini Edizioni da Collezione e Cofanetti | 0 | 0 | — | `[SKIP-empty]` 2354 chars (2º día) |

Lo que la ficha de ayer anticipó ("la cola se activa progresivamente") quedó
**confirmado y medido**. Verificación en vivo el mismo día, post-run:

```
curl -sL "https://www.panini.it/shp_ita_it/planet-manga.html"
→ https://panini.queue-it.net/?c=panini&e=paniniitaly&…  (2287 chars)

# 10 intentos sobre la página 3 del listado:
pasaron=0  encolados=10  de 10
```

**El `16 (2 págs)` no es un cambio de catálogo: es la cola entrando a mitad de la
paginación.** Las dos primeras páginas pasaron, la tercera y siguientes cayeron en la
sala de espera y el paginador cortó sin error. Ese es el modo de fallo peligroso de
Queue-it para este pipeline: **no produce un error ni un skip — produce un yield
parcial silencioso**, que el reporte de salud muestra como "yield regression" y es
indistinguible de un catálogo que encogió.

**Dos `e=` distintos, dos colas independientes:** `e=paniniitaly` para `.it` y
`e=paninies` para `.es`. Cada dominio tiene su propio evento de Queue-it, así que las
fuentes ES e IT pueden degradarse en momentos distintos (como pasó ayer vs hoy).

**Para el owner (no aplicado, sube de prioridad):** la recomendación de ayer —detectar
`queue-it.net` en la URL final y clasificarlo como *challenge*— ahora debería cubrir
también el **paginador**: si una página intermedia cae en la cola, abortar la fuente y
marcarla como challenge en vez de devolver las páginas parciales como resultado bueno.
Sin eso, cada corrida bajo cola escribe un yield falso en el baseline y **corrompe la
mediana** que usa `source_health` para detectar regresiones reales.

## 2026-09-18 — Queue-it, tercer día: listado principal otra vez truncado (16 vs 75)

Planet Manga rindió 16 por segunda corrida seguida (mediana 75) y las secciones
`Panini Variant ed Esclusive` y `Edizioni da Collezione e Cofanetti` saltaron con ~2.3 KB
(página de la cola). Mismo modo de fallo del 09-17: yield parcial silencioso, no error.
Con 2 corridas en 16 la mediana del baseline empieza a arrastrarse hacia abajo — si la
cola se levanta, el reporte no marcará la recuperación como anomalía, pero si persiste
~10 corridas más la caída dejará de alertar.

## 2026-09-19 — Queue-it, cuarto día: el daño se mudó a las secciones de colección

Delta `logs/scrape-delta-2026-09-19-110115/`. Esta vez Planet Manga rindió **75 (5 págs)**,
pero las dos secciones que más importan para ediciones especiales quedaron **truncadas a 2
páginas**: `Panini Variant ed Esclusive` 14 (mediana 54) y `Edizioni da Collezione e
Cofanetti` 16 (mediana 80). Verificado en vivo tras el run: la URL de variantes responde
**302 → `panini.queue-it.net`**. Conclusión: la cola es por-request y "rota" entre secciones
de una corrida a otra; ninguna sección de `panini.it` es confiable mientras dure. Mismo modo
de fallo silencioso (#208): no hay error ni skip, sólo menos páginas. Sin cambios de config.

## 2026-09-20 — Queue-it, 5º día consecutivo (gotcha #208)

Las dos entradas de listado especializadas volvieron a saltarse con el mismo mensaje
engañoso del reporte de salud:

| Fuente | Skip |
|---|---|
| IT - Panini Variant ed Esclusive | `empty: HTML muy corto (2340 chars). Probablemente JS-rendered` |
| IT - Panini Edizioni da Collezione e Cofanetti | `empty: HTML muy corto (2354 chars). Probablemente JS-rendered` |

Los ~2.3 KB son la página de la cola de Queue-it, no un shell JS (ver #208): activar
`--enable-js` aterrizaría en la misma sala de espera. El tamaño es prácticamente
idéntico al de los días 09-16 → 09-19, lo que sugiere que la cola está puesta de forma
estable y no como pico de tráfico puntual.

**Dato positivo del día**: el listado principal `IT - Panini Planet Manga` NO se saltó y
rindió normal — de ahí salió el único item italiano nuevo del día (*Gurren Lagann Double
Edition 5*). Sigue confirmando que la avería de Queue-it es **por-request**, no por host.

Nada aplicado.

## 2026-09-21 — Los 2 sublistados de ediciones especiales caídos, el principal sano (gotcha #208)

Delta `logs/scrape-delta-2026-09-21-110220/01-scrape.log`, misma corrida, mismo host:

| Entrada | Resultado |
|---|---|
| `IT - Panini Planet Manga` (`planet-manga.html`) | **79 candidatos con señales (5 págs)** — sano, por encima de la mediana 75 |
| `IT - Panini Variant ed Esclusive` | `SKIP-empty`, 2340 chars |
| `IT - Panini Edizioni da Collezione e Cofanetti` | `SKIP-empty`, 2354 chars |

Verificado en vivo que los 2.3 KB son la cola, no un shell JS:

```
curl -s -o /dev/null -D - \
  "https://www.panini.it/shp_ita_it/manga/variant-ed-esclusive.html"
→ HTTP/2 302  →  https://panini.queue-it.net/?c=panini&e=paniniitaly&...
```

**Por qué importa más que un skip cualquiera**: los dos sublistados caídos son
precisamente los de *variant/esclusive* y *edizioni da collezione e cofanetti* — las dos
categorías de las que este proyecto se alimenta. El listado principal que SÍ rindió trae
el catálogo regular, así que la corrida "parece sana" (79 > mediana) mientras la ingesta
de ediciones especiales IT quedó en cero. Es el modo de fallo peligroso de #208 visto
desde el otro lado: no sólo yield parcial silencioso, sino yield parcial **sesgado hacia
lo irrelevante**.

Confirma además que la cola es **por-request** y no por-host: tres URLs del mismo dominio
en la misma corrida, una pasa y dos no.

**Nada aplicado (decisión del owner).**

## Seguimiento Queue-it (#208) — 2026-09-23, 7º día

Delta del 2026-09-23: **18 source-runs de Panini se saltaron** con `[SKIP-empty] …
HTML muy corto (~2 340 chars). Probablemente JS-rendered o vacío` — que, como ya está
verificado en vivo (#208), no es JS sino la **página de la sala de espera Queue-it**
(302 → `panini.queue-it.net`). Reparto: **16** searches de `panini.es` + **2** listados
IT (`Variant ed Esclusive`, `Edizioni da Collezione e Cofanetti`). Ayer fueron 19; el
volumen se sostiene.

**Lo importante de hoy es el listado principal**: `IT - Panini Planet Manga` **no se
saltó** pero rindió **47 candidatos en 4 páginas** contra una mediana de **75** y contra
los **79** de ayer — un **−40 %**, y **el reporte de salud NO lo marcó** como regresión.
Es exactamente el modo de fallo peligroso descrito en #208: la Queue-it actúa
**por-request**, así que algunas páginas de la paginación pasan y otras caen en la cola,
y el resultado es **yield parcial silencioso** — ni error, ni skip, ni 🔴. Peor: cada
corrida parcial se incorpora a la mediana histórica y la va bajando, con lo que el
propio baseline deja de poder detectar la avería.

**Además, #199 lo vuelve a tapar**: de los 18 skips reales el reporte de salud mostró
**3**, porque las 16 searches de `panini.es` se colapsaron en una sola fila fantasma
`ES - Panini España (search) [search` (el regex corta el nombre en el primer `:`), y las
16 entradas reales figuran con `Runs 0` y sin incidencias. El operador que lea sólo el
reporte ve 3 fuentes afectadas; el número real es 18.

**Nada aplicado (decisión del owner).** Recordatorio de #208: `--enable-js` NO resuelve
esto — Playwright aterrizaría en la misma sala de espera.

---

## Seguimiento Queue-it (#208) — 2026-09-24, 8º día: el listado principal cae ENTERO

**Escalada respecto a ayer.** El 09-23 `IT - Panini Planet Manga` **no se saltó**: rindió
47 candidatos en 4 páginas contra una mediana de 75 (yield parcial silencioso). Hoy la
misma entrada **se saltó completa**:

```
[SKIP-empty] IT - Panini Planet Manga: HTML muy corto (2301 chars). Probablemente JS-rendered
[SKIP-empty] IT - Panini Variant ed Esclusive: HTML muy corto (2340 chars)
[SKIP-empty] IT - Panini Edizioni da Collezione e Cofanetti: HTML muy corto (2354 chars)
```

Los 3 listados IT caídos a la vez, con el tamaño característico de la página de la sala de
espera (~2.3 KB). O sea la progresión de la semana es: **sano → truncado a 2 págs →
yield parcial (47/75) → skip total**. La avería sigue siendo *por-request*, pero hoy le
tocó a las 3 páginas de entrada.

**Conteo real de la corrida**: **19 source-runs saltados**, TODOS de Panini — los 3
listados IT de arriba + **16 searches de `panini.es`** (`aniversario`, `anniversary`,
`celebration`, `cofre`, `deluxe`, `edicion coleccionista`, `edicion especial`, `edicion
limitada`, `kanzenban`, `master edition`, `portada variante`, `tapa dura`, `tarot`,
`tribute`, `ultimate edition`, `variante`). Ninguna otra fuente del run se saltó.

**#199 lo vuelve a tapar, 9º día**: el reporte de salud mostró **4 filas** de las 19
reales, porque las 16 searches de `panini.es` se colapsan en una única fila fantasma
`ES - Panini España (search) [search` (el regex `([^:]+)` corta el nombre en el primer
`:`). Un operador que lea sólo el reporte ve 4 fuentes afectadas; el número real es 19.

**Nota sobre el baseline**: ahora que el listado principal pasó de yield parcial a skip,
el skip **es más honesto que el parcial** — un 0 con skip explícito no contamina la
mediana histórica, mientras que los 47 de ayer sí la bajaron. El daño al baseline ya
está hecho igual (mediana 75 y bajando).

**Nada aplicado (decisión del owner).** Recordatorio de #208: `--enable-js` NO resuelve
esto — Playwright aterrizaría en la misma sala de espera.


## Revisión de ingestión — 2026-09-24

Queue-it se detecta por el host final del redirect y se reporta como challenge; no significa que se haya eliminado la sala de espera. Fechas Fumetti dd/mm/yy se convierten a ISO con validación. SKIP de búsquedas conserva el nombre completo.

Evidencia y alcance: [auditoría integral](../audits/2026-09-24-ingestion.md).


Aplicado backfill acotado de 150 fechas ausentes desde Fumetti dd/mm/yy, con backup y cero violaciones duras. No cambia títulos ni fechas ya presentes.

### Queue-it resuelto por navegador — 2026-09-24

Con `--enable-js` (activo en full y delta), una respuesta Queue-it ahora abre
el URL original con Chromium. Si la página carga, las siguientes páginas de esa
fuente usan el navegador; si continúa bloqueada, se reporta fallo. Verificación
real: Panini IT variantes 4 páginas/81 candidatos; cofanetti 9 páginas/209;
Panini ES búsqueda deluxe 1 página/12. Las tres finalizaron sin errores, con
179 reportables tras gates. Esto no afirma cobertura completa de todas las
búsquedas españolas: prueba el mecanismo y esas tres entradas.

### Cobertura de agotados — 2026-09-24

El filtro público predeterminado `Acquistabile: Sì` excluye productos agotados.
Verificación en navegador: Planet Manga muestra 3584 productos con ese filtro
y 5902 al seguir `Cancella tutto` (`?skip_default_filters=true`). Las tres
categorías de Panini IT en YAML ahora incluyen ese parámetro. Estos conteos son
del listado completo, no todos califican como ediciones coleccionables.

El navegador conserva una sesión efímera por host de Panini durante la corrida,
reutilizando cookies/caché de navegación entre páginas; se elimina al cerrar el
browser del scraper y no usa el perfil personal. La categoría IT de variantes
verificó 8 páginas/168 candidatos con esta sesión (0 errores). Los demás hosts
conservan contextos independientes por render como antes.

### Títulos sin qualifier en categorías curadas — 2026-09-24

La categoría de variantes devolvió 168 candidatos pero el gate conservaba solo
38: `search:variant esclusiva` ayudaba a descubrir las cards, pero no probaba
coleccionabilidad ni superaba el score mínimo para títulos bare. Ambas categorías
especializadas declaran ahora `collector-catalog`: evidencia explícita de
selección editorial, con score base 20 y paridad en ingestión/cleanup. No se
aplica al catálogo general ni a búsquedas. No inventa `variant_cover`/`box_set`
para cada libro; los raw sin edición explícita se conservan por URL.

Reingesta tras corregir el gate de categorías: 446 candidatos, 442 reportables
tras dedup por URL y cero errores. Detectó 278 URLs primarias adicionales en
staging (145 variantes/exclusivas y 133 coleccionables/cofanetti).

### Reparación de referencias históricas — 2026-09-24

Se quitó 1 referencia de `www.panini.it` asociada a otra fila con ISBN
válido diferente del producto cuya URL primaria es esa misma referencia. Se
conservan ambos productos y su URL primaria; no se fusionan por ISBN. Evidencia
por URL/ISBN en `reports/ingestion-audit-2026-09-24/closure/publication-2-manifest.json`.

Cierre 2026-09-25: se incorporaron 108 referencias adicionales de esta fuente
a productos ya existentes, recuperadas del resultado del upsert en staging.
Cada URL tenía un único propietario propuesto y no existía aún en ninguna
ficha publicada; se conserva el producto canónico. Manifest: `publication-3-manifest.json`.

### Cierre del recorrido completo — 2026-09-25

Catálogo general: páginas 1–25 persistidas antes de la reanudación, seguida
de páginas 24–246 (223 páginas), sin errores. Cobertura única: 246 páginas.
La reanudación obtuvo 408 candidatos del catálogo general. Categorías dedicadas
repetidas con la regla corregida: variantes 8 páginas/168 candidatos;
coleccionables y cofanetti 12 páginas/278 candidatos. Los dos recorridos
especializados juntos produjeron 442 reportables sin errores.

## Auditoría estratégica — 2026-09-25

Se detectó Wayne Family Adventures Cofanetto sin la palabra Batman, cómic DC fuera de alcance. Se agrega el alias al gate común; no se retira la fuente por este producto. Evidencia: catálogo DC Batman: Wayne Family Adventures Volume One.

Gurren Lagann Double Edition: el [catálogo oficial A415](https://www.panini.it/media/paniniFiles/A415.pdf)
lo describe como formato doble en rústica 13×18, sin qualifier premium. Se retiran
las cinco fichas que habían entrado solo por el detector genérico X-Edition, con
copia revisable. Double Edition ya no basta para admisión; hardcover/cofre/extras
siguen admitiendo versiones realmente premium.
