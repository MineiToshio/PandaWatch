# Fuente: Dark Horse Direct

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-09-15 (`limited edition`/`exclusive` caen con paginación completa — probable cambio de ranking; §8).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Dark Horse Direct |
| **URL base** | `https://www.darkhorsedirect.com` |
| **Índice / punto de entrada** | `https://www.darkhorsedirect.com/collections/comics` (listado) + `https://www.darkhorsedirect.com/search?q={query}` (búsqueda) |
| **Tipo de fuente** | Tienda oficial de Dark Horse (Shopify) — listado oficial + búsqueda como retailer |
| **`kind` en sources.yml** | `html` (ambas entradas) |
| **`source_class`** | `official` (listado) · `retailer` (búsqueda) |
| **País** | Estados Unidos (`Estados Unidos`) |
| **Idioma** | Inglés (EN) |
| **Cobertura** | Catálogo MIXTO de Shopify: comics + manga + figuras + estatuas + prints + bookends. Sólo se aceptan ítems con STRONG manga hint. |
| **Aporte al corpus** | ~31 items (corpus actual) |
| **Parser / módulo** | Entradas en `sources.yml` (sin parser propio); extractor genérico de la fuente |

**Editoriales reales en el corpus** (`publisher`, no la tienda): Dark Horse Manga
(≈19) · Dark Horse (≈12). Sólo país: Estados Unidos.

**Por qué importa / qué aporta de único**: ediciones exclusivas y premium de Dark
Horse en EE. UU. (limited editions, deluxe hardcovers, box sets, slipcase, variants)
que muchas veces sólo se consiguen directo en su tienda.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: tienda Shopify. Dos accesos: el listado oficial
  `/collections/comics` (paginado, `max_pages: 15`) y el buscador
  `/search?q={query}`, que se expande por keyword (ver §5).
- **Estructura del HTML**: Shopify estándar. Cada serie multi-tomo se modela como UN
  `og:type=product` con un `<select>` de N volúmenes (variantes) — hay que expandirlas
  (#16).
- **Identificador de producto**: URL del producto Shopify; las variantes multi-tomo
  generan una URL por volumen vía el helper de variantes (#16).
- **Anti-bot / quirks**: catálogo mixto — además de manga trae figuras, estatuas,
  prints y bookends; por eso `purity: mixed` (ver §5). El helper de variantes Shopify
  está restringido al dominio `darkhorsedirect.com` (#16).
- **Calidad de imágenes**: portadas de producto de Shopify (alta resolución).

---

## 5. Proceso de ingestión — técnico

Ambas entradas viven en `sources.yml` y se scrapean en **FASE 1** (scrape de sources
del YAML, `manga_watch.py`) con el **extractor genérico** — no hay parser propio.

- **`US - Dark Horse Direct Manga`** (`official`, `html`): recorre el listado
  `/collections/comics` hasta `max_pages: 15`. `publisher: Dark Horse Manga`. Tags:
  `manga, hardcover, official, store, dark-horse`.
- **`US - Dark Horse Direct (search)`** (`retailer`, `html`): la `search_template`
  `/search?q={query}` se expande en **fuentes virtuales por keyword** (una corrida de
  búsqueda por término). `publisher: Dark Horse Direct`. Keywords: `limited edition`,
  `deluxe`, `hardcover`, `boxset`, `slipcase`, `exclusive`, `variant`. Tags:
  `manga, retailer, exclusive, dark-horse`.

**`purity: mixed` (ambas) → STRONG manga hint (decisión #3).** Al ser un catálogo
mixto, sólo pasa lo que tiene un STRONG manga hint; la comics blacklist aplica
siempre. **No** se rescata un ítem por traer "Collector's Edition" sola.

**Variantes Shopify multi-tomo (#16)**: una serie = 1 producto con `<select>` de N
volúmenes; los helpers de `shopify_variants.py` (`extract_shopify_variants`,
`is_volume_variants`, `build_variant_url`) las expanden a un ítem por tomo. Restringido
a dominios conocidos (hoy `darkhorsedirect.com`).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **403 transitorio en las queries de búsqueda (2026-05-21)**: la entrada `(search)`
  devolvió 403 en algunas keywords ese día (autorresuelto en la corrida siguiente sin
  cambios de código). Verificado en vivo el 2026-07-07 (chequeo manual previo al
  delta real): la fuente respondía normal, sin ningún challenge.
- **429 real en el primer delta post-mejoras (2026-07-07, gotcha #114)**: horas
  después del chequeo manual de arriba, la corrida real de `scrape_delta.sh` sí
  disparó `HTTP error 429 Client Error: Too Many Requests` en varias keywords de
  `US - Dark Horse Direct (search)` (limited edition, deluxe, slipcase, hardcover,
  exclusive, variant). Causa: `darkhorsedirect.com` resuelve al mismo borde Shopify
  `23.227.38.0/24` que Milky Way, Funside Variant y Manga Dreams — el rate-limit es
  del BORDE compartido, no de esta tienda puntual (`--per-host-limit` agrupa por
  hostname y no lo detecta). Fix: `throttle_group: "shopify"` en las dos entradas
  YAML de esta fuente (`US - Dark Horse Direct Manga` y `(search)`) — comparten
  semáforo (limit 1) + delay mínimo 2s con las otras tres tiendas del mismo grupo
  (`--throttle-group-delay`).
- **2026-09-08 — `hardcover` cayó 32→17 por PAGINACIÓN TRUNCADA, transitorio**: el
  reporte de salud lo marcó como *yield regression* (49% de la mediana). El
  discriminante NO es el conteo sino las **páginas recorridas**: 09-07 = `32 (5 págs)`,
  09-08 = `17 (3 págs)`. Verificado en vivo el mismo día: `search?q=hardcover&page=5`
  responde **200 con ~305 KB y 24 enlaces `/products/`**, o sea el catálogo SIGUE
  teniendo ≥5 páginas — no hubo cambio de catálogo ni de selectors. **No fue el borde
  Shopify compartido** (gotcha #114): en la MISMA corrida, `deluxe` (19, 5 págs),
  `exclusive` (16, 5 págs), Funside Variant (225, 5 págs) y Manga Dreams (160, 10 págs)
  rindieron idéntico a ayer — el corte fue aislado a esta query. Lectura: truncamiento
  puntual de la paginación; **si se repite, mirar primero el número de págs, no el de
  candidatos**.
- **2026-09-15 — `limited edition` y `exclusive` caen con paginación COMPLETA (no es el
  caso del 09-08)**: el reporte de salud marcó `limited edition` 5 (mediana 15.5) y
  `exclusive` 5 (mediana 13). Serie de candidatos con señales en los últimos deltas
  (todas con **5 págs** recorridas): `limited edition` 16 → 16 → **9** (09-13) → **5**;
  `exclusive` 15 → 14 → 14 → **5**. En la MISMA corrida `deluxe` (19, 5 págs) y
  `hardcover` (32, 5 págs) rindieron idéntico a su historial, así que tampoco es el borde
  Shopify compartido. Verificado en vivo el mismo día: `search?q=limited+edition&page=5`
  → 200, ~243 KB, 9 enlaces `/products/`; `q=exclusive&page=5` → 200, ~270 KB, 13 enlaces.
  O sea, la búsqueda sigue sirviendo productos en todas las páginas: lo que bajó es
  cuántos de esos productos traen señal de edición especial. Lectura más probable:
  **cambio de ranking/orden de resultados de la búsqueda de Shopify** (productos con
  señal desplazados más allá de la pág. 5), no avería del parser. Causa NO confirmada:
  `data/state.json` sólo actualiza `last_seen_at` de items nuevos/cambiados (#204), así
  que no permite reconstruir qué productos dejaron de aparecer. **Si persiste 2-3
  corridas más**, probar subir `max_pages` de la entrada `(search)` o agregar
  `&sort_by=created-descending` a esos dos términos (decisión del owner, no aplicada).
- **Curación LLM non-manga 2026-08-23**: 14 items expulsados (Critical Role/Vox
  Machina, The Witcher, World of Warcraft Chronicle, réplica 1:1 del casco de
  Helldivers 2, artbooks de videojuego: Cyberpunk 2077, Horizon Forbidden West,
  Masters of the Universe, Over the Garden Wall). La fuente ya tiene
  `purity: mixed`, pero la regla 4 de `is_likely_manga` (default → True) los dejaba
  pasar igual; ahora caen por las ~75 keywords nuevas agregadas a
  `data/comics_blacklist.yml`.

---

## 9. Pendientes / limitaciones conocidas

- El helper de variantes Shopify (#16) está limitado a `darkhorsedirect.com`; si otra
  tienda Shopify usa el mismo patrón habría que ampliar el allowlist de dominios.
- {{pendiente: no se determinó un valor de paginación para la entrada de búsqueda
  (`max_pages` no está definido en su entrada del YAML)}}.
- **Monitorear el próximo run** si `throttle_group` (delay 2s + semáforo compartido
  con Milky Way/Funside Variant/Manga Dreams) evita el 429 recurrente en `(search)`;
  si persiste, considerar reducir keywords por corrida o aumentar el delay.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo de esta fuente (cada entrada por su nombre exacto):
.venv/bin/python scripts/manga_watch.py --only-source "US - Dark Horse Direct Manga"
.venv/bin/python scripts/manga_watch.py --only-source "US - Dark Horse Direct (search)"

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "darkhorsedirect"
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

## 2026-08-28 — las búsquedas `deluxe`/`exclusive`/`slipcase` traen cómic/artbook occidental

Delta diario (`logs/scrape-delta-2026-08-28-160959/`). Tres items entraron por las
queries de búsqueda y el LLM del skill de estandarización los marcó `is_manga=false`;
quedaron pendientes en `data/unmapped_series.jsonl` (reason `llm_non_manga`):

- `H.P. Lovecraft's At the Mountains of Madness HC (Deluxe Edition)` — `[search: deluxe]`
- `H.P. Lovecraft's The Dunwich Horror Deluxe Edition HC` — `[search: exclusive]`
- `The World of Cyberpunk 2077 HC (Deluxe Edition)` — `[search: slipcase]`

Causa: Dark Horse es editorial mixta y los términos de edición (`deluxe`, `exclusive`,
`slipcase`) son agnósticos de medio. No es un bug del parser: la fuente está trayendo
exactamente lo que se le pidió, pero fuera de alcance.

**Para el owner (no aplicado):** sumar estos títulos/series a `data/comics_blacklist.yml`
para que el gate determinista los expulse y no se re-ingesten cada corrida (gotcha #154).

## 2026-08-29 — vuelve a flaggearse, y esta vez el flag se PERDIÓ (gotcha #155)

Delta diario (`logs/scrape-delta-2026-08-29-110244/`). Los 3 items ya documentados en la entrada del 2026-08-28 (`H.P. Lovecraft's At the Mountains of Madness HC`, `H.P. Lovecraft's The Dunwich Horror Deluxe Edition HC`, `The World of Cyberpunk 2077 HC`) volvieron a entrar como `product_type=manga` por los searches `deluxe`/`exclusive`/`slipcase`, y volvieron a ser flageados por el LLM como no-manga.

Dos cosas que agrega esta corrida:

1. **La recurrencia está confirmada**: el gate LLM de `/watch-standardize-catalog`
   vuelve a marcar exactamente el mismo material, y los gates deterministas
   (`filter_non_manga`/`filter_collectible`) vuelven a no expulsarlo, así que sigue
   contando como manga en el corpus. El patrón es el de gotcha #154 (veredicto LLM que
   no expulsa + gate determinista que no lo cubre), estable corrida a corrida.
2. **El flag se destruyó el mismo día**: el pase de `/watch-enrich-series-aliases` que
   corrió después trunca `data/unmapped_series.jsonl` entero (gotcha #155), así que las
   filas `llm_non_manga` de esta corrida desaparecieron de la cola de curación sin que
   nadie las revisara. Sobreviven sólo en
   `data/backups/unmapped_series.jsonl/unmapped_series.jsonl.pre-enrich-bak`, que rota.

Consecuencia práctica: mientras las dos etapas corran en ese orden, **este material se
va a re-flaggear y re-perder todos los días**, y la cola nunca acumula la evidencia que
haría falta para justificar un fix. No se tocó ninguna configuración de la fuente.

## 2026-08-30 — el search `slipcase` trae un artbook de videojuego (no manga)

Delta diario (`logs/scrape-delta-2026-08-30-111729/`). El search `[search: slipcase]`
inyectó `The World of Cyberpunk 2077 HC (Deluxe Edition)` — artbook/companion del
videojuego de CD Projekt, sin relación con manga.

Flageado `llm_non_manga` por `/watch-standardize-catalog` y **no expulsado** por los
gates deterministas (gotcha #154). Además quedó con `product_type: manga` (debería ser
`artbook` como mínimo) y `edition: Deluxe (Dark Horse Direct)`.

Causa: `slipcase` es vocabulario de **formato de edición**, no de manga, y Dark Horse
Direct es un catálogo mayoritariamente occidental (cómic US, artbooks de videojuegos)
con una minoría de manga. La fuente aparece en `sources.yml` sin `purity` declarada →
default `manga_only`, que NO exige STRONG manga hint.

Nota de contexto: esta fuente es el ejemplo canónico citado en el código como catálogo
`mixed` (`manga_watch.py`, comentario de `purity`), pero sus entradas de tipo `search`
no lo declaran.

**Para el owner (no aplicado — cambio de configuración):** declarar `purity: mixed` en
las entradas `search` de esta fuente. Retorno: el gate de pureza exigiría STRONG manga
hint y cortaría la entrada de artbooks de videojuego y cómic US sin tocar los deluxe de
manga legítimos (Blade of the Immortal, Berserk…), que sí traen señal fuerte.

## 2026-08-31 — el artbook de Cyberpunk 2077 sigue en el corpus (2º día)

Delta diario (`logs/scrape-delta-2026-08-31-110202/`). Sin fila nueva: el item flageado
ayer —`The World of Cyberpunk 2077 HC (Deluxe Edition)`, search `slipcase`,
`note: non_manga_media`— **sigue vivo en el corpus** con `product_type: manga` y
`edition_display: Deluxe (Dark Horse Direct)`, porque el veredicto del LLM no expulsa y
los gates deterministas no lo agarraron. Su fila de curación sobrevivió sólo porque
esta corrida (igual que la del 08-30) NO ejecutó `/watch-enrich-series-aliases`.

Contexto del mismo run: los searches de esta fuente aportan 31 filas huérfanas a la
cola de aliases (18 de `hardcover` + 13 de `limited edition`), consistente con la
gotcha #156 — los searches por término de FORMATO tienen ~100% de filas huérfanas.

## 2026-09-02 — el search `slipcase` trae artbook de videojuego y cómic occidental

Delta diario (`logs/scrape-delta-2026-09-02-110142/`). Items nuevos de este run:
`The World of Cyberpunk 2077 HC (Deluxe Edition)` (artbook/companion de videojuego) y
`The Goon Library Edition Volumes HC (Second Edition)` (cómic occidental de Eric Powell).
Ambos re-flageados `llm_non_manga` (`non_manga_media` / `western_comic`) y ambos vivos
en el corpus.

Es el catálogo esperable de Dark Horse: la editorial publica manga licenciado Y su propio
cómic occidental y libros de videojuegos bajo los mismos formatos de lujo, así que un
search por término de FORMATO (`slipcase`) no discrimina. Mismo patrón que el search
`variant` de Star Comics y el de Funside — el término de formato es ortogonal al medio.

Nada aplicado: acotar el search de esta fuente es decisión del owner.

### RESUELTO el mismo día (2026-09-02) — el owner pidió arreglar las fuentes

Expulsados 4 items (2 más de los 2 reportados a la mañana, encontrados al revisar el
catálogo completo de la fuente): `The World of Cyberpunk 2077 HC`, `Cyberpunk 2077
Library Edition Volume 1 HC`, `The Goon Library Edition Volumes HC` y `Birdking Library
Edition HC`. Keywords `"Cyberpunk 2077"`, `"The Goon"` y `"Birdking"` en
`data/comics_blacklist.yml`, cada una verificada contra el corpus (0 manga real
afectado).

**Hallazgo de mecanismo que explica por qué `purity: mixed` no alcanzaba.** Esta fuente
YA estaba en `mixed`, que exige STRONG manga hint… y aun así estos items pasaban. La
razón: el guard de `mixed` protege la regla 2 (pack/extras) de `is_likely_manga()`, pero
estos entran por la regla 1 (STRONG hint), que corre ANTES y no consulta la purity. Y los
"STRONG hints" que disparaban eran `Deluxe Edition` / `Library Edition` — **términos de
FORMATO de edición, no de medio**. Un hardcover de lujo es un hardcover de lujo sea manga,
cómic occidental o artbook de videojuego.

No se cambió la regla 1 en este turno: sacar los términos de formato del set STRONG es un
cambio de blast radius grande (medio corpus se detecta exactamente por "vol N" / "Deluxe
Edition") y merece su propio trabajo medido. Queda anotado como la deuda estructural real
detrás de esta familia de falsos positivos. Mientras tanto el blacklist por franquicia
cubre los casos concretos.

## 2026-09-05 — flag de yield estadísticamente vacío (`slipcase`: 0 vs mediana 1)

`source_health --baseline-alert` marcó `US - Dark Horse Direct (search) [search: slipcase]
| 0 | mediana 1 | 0%` como 🔴 regresión.

Es un **artefacto del reporte, no un hallazgo**: con una mediana histórica de **1**, basta
que el término no devuelva nada una vez para caer a "0% de la mediana" y disparar la alerta
en rojo. La búsqueda corrió sin errores ni challenges; el resto de los términos de Dark
Horse Direct (`limited edition`, `deluxe`, `hardcover`, `boxset`) y el catálogo curado
(15 candidatos, 4 págs) funcionaron normal.

Anotado para no re-diagnosticarlo: **`source_health` no debería alertar sobre series cuya
mediana es ≤2** — el ruido supera a la señal. Recomendación para el owner (no aplicada):
un piso mínimo de mediana para que una fuente entre al cálculo de regresión de yield.

**2026-09-11 — reincide la misma alerta, y confirma que el término está vacío de forma
estable.** Historial de `logs/metrics.jsonl`: `slipcase` rindió 1-2 del 08-30 al 09-02 y
**0 en las 8 corridas siguientes** (09-03 → 09-11). HTTP 200, 22 cards, 2 páginas, sin
errores ni challenges. La alerta sigue apareciendo porque la mediana de la ventana aún es
1; se apagará sola cuando la ventana sólo contenga ceros. No es avería: desde el fix del
09-02 (blacklist por franquicia) el término dejó de traer artbooks de videojuego y cómic
occidental, que eran justamente lo que rendía. Refuerza la recomendación del piso de
mediana y abre otra: evaluar si `slipcase` sigue aportando algo o conviene retirarlo
(decisión del owner).

## 2026-09-16 — `limited edition` y `exclusive` ya no devuelven manga (confirmado en vivo)

`source_health` marcó dos regresiones seguidas:

| Search | Hoy | Mediana | % |
|---|--:|--:|--:|
| `limited edition` | 1 | 15 | 7% |
| `exclusive` | 1 | 13 | 8% |

**No es una avería.** La paginación se recorrió completa (5 págs cada una) y las
otras searches del mismo host rindieron normal en la misma corrida (`deluxe` 15,
`hardcover` 25). Verificado en vivo el mismo día: la página 1 de cada búsqueda
devuelve ~25 y ~23 productos, así que el fetch está sano — lo que cambió es **qué**
devuelve el buscador de la tienda:

```
/search?q=limited+edition → statues, pins de convención, skate decks, giclée prints,
  vinyl figures (Helldivers 2, The Last of Us, Witcher, Doom, Mass Effect, Halo…)
/search?q=exclusive      → idem (Critical Role bookends, beanies, réplicas 1:1…)
```

De los ~25 resultados de `limited edition`, los únicos con forma de libro son
`the-legend-of-zelda-tears-of-the-kingdom-secrets-of-the-zonai-hc` y
`mazebook-hc-dark-horse-direct-exclusive` — ninguno manga. El pipeline los filtró
correctamente y dejó 1 candidato con señales. **El filtro está haciendo su trabajo.**

Cierra el diagnóstico abierto el 2026-09-15 ("caen a 5 con paginación completa,
probable cambio de ranking"): la trayectoria 15 → 5 → 1 es el buscador de Dark Horse
Direct escorándose hacia merchandising, no el scraper degradándose.

**Recomendación (decisión del owner, nada aplicado):** estos dos términos cuestan 5
páginas cada uno por corrida (10 fetches) para 0 items útiles. Conviene quitarlos o
darles contexto (`limited edition manga`) y quedarse con `deluxe` y `hardcover`, que
siguen rindiendo 15 y 25. **Ojo**: la mediana histórica (15/13) quedará obsoleta y
seguirá generando falsas alarmas mientras los términos existan — mismo patrón que
JBC y Milky Way (gotcha #190).

## 2026-09-17 — `limited edition`/`exclusive` estables en el nivel bajo; `hardcover` cae a 12

Corrida `logs/scrape-delta-2026-09-17-110139`, **las 5 páginas recorridas en los tres
casos** (o sea: no es paginación truncada):

| Search | Hoy | Ayer | Mediana | Págs |
|---|--:|--:|--:|--:|
| `limited edition` | 3 | 1 | 15 | 5 |
| `exclusive` | 2 | 1 | 13 | 5 |
| `hardcover` | 12 | — | 32.5 | 5 |

`limited edition` y `exclusive` **quedan cerradas**: la verificación en vivo del 09-16
mostró que el buscador devuelve ~25 productos pero son estatuas, pins y skate decks — el
filtro los descarta correctamente. Los valores de hoy (3 y 2) confirman que el nivel real
de estas dos searches es de un dígito bajo y que **la mediana de 15/13 quedó obsoleta**,
arrastrada por corridas viejas con otro ranking.

`hardcover` con 12 sobre 5 páginas completas es la misma familia de causa: el buscador de
Shopify reordena por relevancia y qué entra en las primeras 5 páginas varía por día. El
09-08 ya se había medido 17 con paginación truncada y `page=5` devolviendo 24 productos.

**No hay avería de fuente en Dark Horse.** Lo que hay es una **mediana de baseline que ya
no representa a la fuente**; mientras no se recalcule, estas tres searches van a seguir
apareciendo en 🚨 YIELD REGRESSIONS todos los días y a gastar atención del reporte matinal.

**Para el owner (no aplicado):** recortar la ventana histórica del baseline de
`source_health` (p. ej. mediana de las últimas N corridas en vez de todas), o
re-basar manualmente estas searches. Es el mismo problema de fondo que JBC y que Milky Way
`deluxe`.

## 2026-09-18 — `variant` 0 y `limited edition` 6: mismo nivel bajo

`variant` 0 (mediana 2) y `limited edition` 6 (mediana 15). Coherente con el cambio de
ranking verificado el 09-16; mediana obsoleta, no avería.

## 2026-09-21 — `variant` 0 y `limited edition` 6: mediana obsoleta (sin cambio)

Reporte de salud del delta: `[search: variant]` 0 vs mediana 2 (26 corridas) y
`[search: limited edition]` 6 vs mediana 14.5. Mismo diagnóstico ya verificado en vivo en
esta ficha el 2026-09-16/17: el buscador devuelve productos pero son estatuas, pins y
skate decks que el filtro descarta correctamente, y las medianas arrastran corridas viejas
con ranking distinto. No es avería. Nada aplicado.

### Caché de imágenes — auditoría 2026-09-25

El inventario detectó referencias locales con nombres derivados de una normalización
legacy que descartaba parámetros de URL. Se desactivó esa reutilización ambigua;
se preservan parámetros de identidad/versión. Esto es un riesgo del caché local,
no prueba de un producto incorrecto en esta fuente. La revisión por URL y el
resultado de las re-descargas están en `reports/image-audit-2026-09-25/`. Ante
contenido cambiado o descarga fallida se conserva la imagen anterior.
