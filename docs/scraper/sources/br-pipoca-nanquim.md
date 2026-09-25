# Fuente: Pipoca & Nanquim

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-08-29 (3ª recurrencia del ruido promocional del home).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Pipoca & Nanquim |
| **URL base** | `https://pipocaenanquim.com.br/` |
| **Índice / punto de entrada** | Listado del storefront Magento (paginado, `max_pages: 5`) |
| **Tipo de fuente** | Editorial (official) — tienda propia |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | Brasil (`Brasil`) — fuente mono-país |
| **Idioma(s)** | Portugués (PT-BR) |
| **Cobertura** | Catálogo mixto: manga premium (Junji Ito, omnibus de Tezuka, City Hunter Omnibus) junto con BD europea (Thorgal) |
| **Aporte al corpus** | 1 item (snapshot 2026-06-08) |
| **Parser / módulo** | Entrada en `sources.yml` (extractor genérico, sin parser propio) |

**Por qué importa / qué aporta de único**: editorial brasileña que publica manga
premium en PT-BR (Junji Ito, omnibus de Tezuka, City Hunter Omnibus). Es una de las
pocas fuentes del mercado brasileño con ediciones de autor / premium.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: storefront **Magento** (Mageshop), listado paginado
  acotado a `max_pages: 5`. Producto en `*.html`.
- **Estructura del HTML**: selectores del YAML (verbatim) —
  - `item_selector`: `li.product-item, .item.product`
  - `title_selector`: `a.product-item-link, a[href$='.html']`
- **Identificador de producto**: URL canónica del producto (`*.html`).
- **Catálogo mixto**: mezcla manga con BD europea (Thorgal). La comics blacklist filtra
  Thorgal; `purity: mixed` exige STRONG hint para el resto (ver §5).

---

## 5. Proceso de ingestión — técnico

- **FASE 1** del pipeline: se scrapea con el resto de fuentes del YAML
  (`manga_watch.py --workers 8`) vía el **extractor genérico** de Magento. **No tiene
  parser propio.**
- **`purity: mixed`** (decisión #3): en una fuente mixed sólo pasa lo que trae **STRONG
  manga hint**; un producto sin esa señal no entra al catálogo.
- **Comics blacklist** (#11): filtra la BD europea (Thorgal) antes de la regla de purity.
  La blacklist aplica siempre.
- Entrada en `sources.yml` bajo `"BR - Pipoca & Nanquim"` (`enabled: true`).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Catálogo mixto manga / BD europea** — Thorgal y similares conviven con manga premium.
  La comics blacklist (#11) los filtra; `purity: mixed` (decisión #3) exige STRONG hint
  para el resto. ✅

---

## 9. Pendientes / limitaciones conocidas

- **Aporte real bajo**: 1 item en el corpus (snapshot 2026-06-08). {{pendiente: confirmar
  si es cobertura esperada o si el STRONG-hint gate está filtrando manga válido del
  catálogo PT-BR}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "BR - Pipoca & Nanquim"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "pipocaenanquim"
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

## 2026-08-25 — badges promocionales del home entran como "series" a la cola de aliases

Delta diario (`logs/scrape-delta-2026-08-25-110223/`). De las 7 entradas que Pipoca &
Nanquim aportó a `data/unmapped_series.jsonl` en esta corrida, **4 no son series sino
badges promocionales del home**, todas con `sample_url` = la raíz del sitio
(`https://pipocaenanquim.com.br/`):

- `50-off-lancamento` → "50% OFF Lançamento"
- `30-off-lancamento` → "30% OFF Lançamento"
- `20-off-lancamento` → "20% OFF Lançamento"
- `30-off-pre-venda`  → "30% OFF Pré Venda"

El patrón es claro: el parser está tomando el **texto del badge de descuento** que la
tienda superpone sobre la card del producto y tratándolo como el título, en vez del
nombre del libro. Se distingue de un item legítimo por dos señales combinadas: la URL
no baja al detalle del producto (se queda en la raíz) y el título matchea
`\d+% ?off` / `pré[- ]venda`.

Una quinta entrada, `100 Discos Para Conhecer Aguardela`, es **material fuera de
alcance** (libro sobre música, no manga) — la fuente es `mixed` y este es el tipo de
falso positivo que la purity debería frenar, pero llega hasta la cola de curación
porque `is_likely_manga` no tiene señal para descartarlo.

Impacto acotado: son entradas de la cola de aliases, no items publicados. Ensucian la
curación manual, no el corpus.

**Para el owner (no aplicado — cambiar el parser/config es decisión suya):** el fix
barato es descartar en el parser los candidatos cuya URL no baje del home Y cuyo título
matchee el patrón de descuento; es una regla local a esta fuente y no toca
`is_likely_manga`. El retorno es que la cola de aliases deja de recibir ruido recurrente
de esta tienda en cada delta.

## 2026-08-26 — el ruido de badges promocionales se repite idéntico (2ª corrida)

Delta diario (`logs/scrape-delta-2026-08-26-110228/`). El patrón descrito en la entrada
del 2026-08-25 se repitió **exactamente igual**: de las 7 entradas que la fuente aportó a
`data/unmapped_series.jsonl`, las mismas 4 son badges promocionales con `sample_url` = la
raíz del sitio (`50-off-lancamento`, `30-off-lancamento`, `20-off-lancamento`,
`30-off-pre-venda`), y `100-discos-para-conhecer-aguardela` volvió a colarse como material
fuera de alcance. Las otras 2 son legítimas (`shigurui-frenesi-da-morte`,
`a-arte-de-ogiva-o-mundo-nao-e-mais`).

Lo que agrega esta corrida es **evidencia de que el ruido es determinístico y recurrente**,
no un artefacto de una corrida puntual: cada delta va a volver a inyectar las mismas 4
entradas basura a la cola de curación mientras el parser no las filtre. Como todas tienen
`item_count = 1`, además quedan fuera de los pases acotados de aliases por `--min-count 2`,
así que se acumulan sin resolverse.

**Para el owner (no aplicado — cambiar el parser/config es decisión suya):** la
recomendación del 08-25 sigue en pie y ahora con recurrencia confirmada. El fix barato
(descartar candidatos cuya URL no baje del home Y cuyo título matchee `\d+% ?off` /
`pré[- ]venda`) sigue siendo local a esta fuente.

## 2026-08-29 — 3ª corrida idéntica: el ruido promocional ya es crónico

Delta diario (`logs/scrape-delta-2026-08-29-110244/`). Tercera repetición **exacta** del
patrón de 08-25 / 08-26: las mismas 4 badges promocionales (`50-off-lancamento`,
`30-off-lancamento`, `20-off-lancamento`, `30-off-pre-venda`) volvieron a entrar a
`data/unmapped_series.jsonl` con `sample_url` = la raíz del sitio, y
`100-discos-para-conhecer-aguardela` (material fuera de alcance) otra vez con ellas. Las
legítimas de esta corrida siguen siendo las mismas dos: `shigurui-frenesi-da-morte` y
`a-arte-de-ogiva-o-mundo-nao-e-mais`.

Con tres corridas consecutivas el diagnóstico deja de ser "recurrente" y pasa a ser
**crónico y perfectamente predecible**: el costo no es el corpus (estas entradas nunca
llegan a `items.jsonl`, sólo a la cola) sino la **curación** — cada pase de aliases las
vuelve a ver, y como tienen `item_count = 1` no las levanta ningún pase acotado por
`--min-count ≥ 2`, así que se sedimentan indefinidamente.

**Para el owner (no aplicado — sigue siendo su decisión):** el fix del 08-25 no cambió
—descartar en el parser de ESTA fuente los candidatos cuya `sample_url` sea el home Y
cuyo título matchee `\d+% ?off` / `pré[- ]venda`— y ahora tiene 3 corridas de evidencia
detrás. Alternativa aún más barata si no se quiere tocar el parser: purgar esas 4 keys de
la cola de una vez, aceptando que van a volver en el próximo delta.

## 2026-08-30 — 4ª corrida idéntica (sin novedad, sólo confirma la predictibilidad)

Delta diario (`logs/scrape-delta-2026-08-30-111729/`). Cuarta repetición **exacta**: las
mismas 4 badges promocionales (`50-off-lancamento`, `30-off-lancamento`,
`20-off-lancamento`, `30-off-pre-venda`) + `100-discos-para-conhecer-aguardela` en
`data/unmapped_series.jsonl`, y las mismas 2 legítimas (`shigurui-frenesi-da-morte`,
`a-arte-de-ogiva-o-mundo-nao-e-mais`). 7 filas en total, de las cuales **5 son ruido**.

Confirmado también que el corpus sigue limpio: la fuente aporta **1 solo item vivo** en
`items.jsonl` — las badges nunca llegan al corpus, sólo a la cola. El diagnóstico y la
recomendación del 08-25/08-26/08-29 no cambian; esta entrada sólo deja constancia de que
el patrón es reproducible corrida a corrida sin variación alguna.

Contexto nuevo de esta corrida (transversal, no exclusivo de esta fuente): la cola
`unmapped_series.jsonl` se escribe en la FASE 1 del scrape, **antes** de los gates
deterministas de la FASE 3 — por eso acumula filas de candidatos que después se filtran.
En este run, 223 de 485 filas (46%) apuntan a una URL que ya no existe en el corpus. Las
badges de Pipoca son un caso particular de ese mecanismo general.

## 2026-09-05 — read timeout del host (avería de red, no de parser)

Delta diario (`logs/scrape-delta-2026-09-05-113236/`). La fuente cayó en
`🔴 Broken (HTTP errors)` del reporte de salud con:

```
[ERROR] BR - Pipoca & Nanquim: request error
HTTPSConnectionPool(host='pipocaenanquim.com.br', port=443): Read timed out.
```

**Es un modo de fallo distinto al ruido de badges promocionales** documentado en las 4
entradas de 08-25/08-30: aquel era el parser trayendo basura de más; este es la petición
que nunca completa, así que la fuente aportó **0 items** en la corrida. Sin candidatos
tampoco hubo badges promocionales entrando a la cola de aliases — el ruido crónico no
aparece hoy simplemente porque no hubo respuesta que parsear.

Un `Read timed out` aislado es típicamente transitorio (host lento bajo el paralelismo de
`--workers 8` + `--per-host-limit 2`). **Nada aplicado.** Si se repite en las próximas
corridas, la señal deja de ser "el host estuvo lento" y pasa a ser "el host nos está
cortando", y ahí sí conviene revisar timeout/backoff por-host para esta fuente.
