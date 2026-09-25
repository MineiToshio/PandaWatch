---
name: watch-search-covers
description: Busca imágenes en alta resolución para items con portada o foto de galería de baja calidad o ausente usando Chrome. Combina Yandex búsqueda-por-foto (reverse image, usando la imagen actual como consulta) + queries de texto con contexto en Bing Imágenes (motor de texto primario desde 2026-07-11; Google udm=2 quedó como fallback de emergencia por riesgo de cuenta). Nunca hace reverse-image contra una referencia placeholder conocida (gotcha #171/#179: la detecta sc_plan.py y la trata como "sin imagen", sólo texto) ni valida contra una referencia que driftó desde el plan (gotcha #178/#179: sc_validate.py corta el target si la imagen de referencia cambió/desapareció a mitad de la corrida). "Baja calidad" en PORTADAS (img_idx 0) usa por defecto el factor de reescalado en card (fetch_better_covers.cover_upscale_factor >= UPSCALE_TARGET_MIN = 1.6, apaisadas primero — validado con visión sobre 579 casos reales, Etapa 1 2026-09-02, gotcha #172); --target-rule area restaura el criterio viejo (90 000 px, el mismo del panel de calidad) por compatibilidad. La galería (img_idx >= 1) sigue usando siempre el criterio de 90 000 px. Por cada imagen objetivo itera fuentes hasta juntar matches; valida cada candidata con fetch_better_covers._same_cover() (misma imagen) y _is_soft_image() (descarta escaneos chicos y blandos que se verían pixelados) para quedarse SOLO con la MISMA portada en mejor resolución y buena calidad. Escribe a data/cover_preview.json para aprobación manual. NUNCA modifica items.jsonl. Sin --limit procesa el 100% de los targets pendientes. Por defecto procesa portadas Y fotos de galería (img_idx 0 y >= 1). Args opcionales: --limit N, --slug SLUG, --include-no-image, --only-covers, --gallery-only, --target-rule {scale,area}, --retry-failed, --query-extra "texto", --serper-fallback (paso final opcional que invoca el motor de producción para reverse-image via Google Lens en los targets que quedaron en 0 matches).
argument-hint: "[--limit N] [--slug SLUG] [--include-no-image] [--only-covers] [--gallery-only] [--target-rule scale|area] [--retry-failed] [--query-extra \"texto\"] [--serper-fallback]"
---

# search-covers — Búsqueda de portadas hi-res con Chrome

Usa Chrome para buscar portadas en alta resolución para items con **imagen de baja calidad**
(según el mismo criterio del panel de calidad de datos) o sin imagen. Para cada item combina
dos motores: (1) **Yandex búsqueda por foto** (reverse image, usando la imagen actual como
consulta) y (2) **varias queries de texto con contexto** en **Bing Imágenes** (motor de texto
primario). Extrae URLs candidatas del HTML y las valida con Python exigiendo que sean **la misma
portada en mejor resolución**. Las aprobadas se escriben a `data/cover_preview.json` para
revisión manual en `http://localhost:8000/web/cover-preview.html`.

> **Motor de texto primario = Bing (decisión 2026-07-11 — investigación web + red team).**
> Antes el canal de texto era Google udm=2 y Bing era solo fallback de consent-wall. Se
> INVIRTIÓ. La razón principal NO es velocidad sino **RIESGO DE CUENTA**: el scraping corre con
> `credentials:include` (las cookies de sesión del owner). Con Google, el bloqueo (`429` →
> `/sorry`) queda atado a la **cuenta Google real del owner** y puede escalar de captcha a
> **suspensión de cuenta** (Gmail/Ads colaterales) — no solo un IP-ban temporal. Bing es, por
> consenso de la comunidad de scraping, el motor más tolerante de los tres grandes, con umbrales
> mucho más altos, patrón `murl` estable (lo usan herramientas comerciales desde hace años sin
> cambios) y sin historial de suspensión de cuenta. Y —crítico— **Bing HONRA `site:`**
> (verificado en vivo 2026-07-11: `site:whakoom.com` devolvió covers de whakoom `/large/`), así
> que la vía whakoom (100% de los matches ES del piloto) se conserva intacta. El plan
> (`sc_plan.py`) ahora emite las variantes de texto como **Bing** (campo `engine: "bing"`).
>
> **Cómo se extraen las URLs de Bing**: en `https://www.bing.com/images/search?q=<query>&first=1`
> el metadato de cada resultado va como JSON en el atributo `m` de cada card, con `murl`
> (full-res), `turl` (thumb), `purl` (source). El patrón `murl&quot;:&quot;<URL>&quot;` sobre el
> HTML crudo (`innerHTML`) devuelve las URLs full-res directas — más limpio que Google (cuyo
> `img.src` eran thumbnails base64). El regex genérico de URLs de imagen (cortando antes de `&`)
> también funciona. Ver Step 3b.
>
> **Motores de búsqueda — qué funciona y qué no**:
> - **Bing Imágenes texto (USADO, PRIMARIO)**: `https://www.bing.com/images/search?q=<query>&first=1`.
>   Extracción por `murl`. Tolerante al scraping, honra `site:whakoom.com`. Corrida en vivo
>   2026-07-11: 366 fetches con delay de 500ms, cero bloqueos. Es el motor de texto por defecto.
> - **Yandex reverse image (USADO, primaria por-foto)**: `https://yandex.com/images/search?rpt=imageview&url=<old_url>`.
>   Sin captcha, accesible, devuelve **portadas del tomo/edición correctos**. Se extrae con el
>   regex genérico sobre `innerHTML`. Es la mejor "búsqueda por foto" gratis. No se bloqueó.
> - **Google texto `udm=2` (FALLBACK DE EMERGENCIA, ya NO primario)**: las URLs full-res están en
>   el `innerHTML` (los `img.src` son thumbnails base64). Se conserva SOLO como escape si Bing se
>   degrada/bloquea, y con **fuertes cautelas** (ver "Fallback a Google" abajo). **Preferí Serper
>   Lens (Step 5) antes que Google texto** para exprimir residuales: Lens corre server-side, sin
>   las cookies del owner.
> - **Google Lens vía Chrome (NO usado)**: sube un THUMBNAIL de 150×150 y cae en matching "a nivel
>   franquicia" → fan art, wikis, merch, tomos equivocados. 0 matches. **No confundir con Serper
>   Lens**: ese manda la URL completa de la imagen y el matching corre server-side — mucha mejor
>   precisión (Step 5).
> - **Serper Lens (de pago, ACTIVA)**: la reversa real de mejor calidad vive en producción
>   (`fetch_better_covers._search_serper_lens`, endpoint `/lens` de Serper — Google Lens
>   server-side, **sin necesitar cookies del owner** ni que la imagen esté indexada) y requiere
>   `SERPER_API_KEY` (configurada y ACTIVA en `.env`). Este skill (100% Chrome) no la llama
>   directo, pero es la vía de fallback del **Step 5** — en particular para targets cuya imagen
>   actual es un thumbnail de `static.listadomanga.com`: Yandex los omite, pero Lens no necesita
>   indexación.
>
> **Throttling + jitter (obligatorio, todos los motores).** El bloqueo de Google en el piloto lo
> gatilló hacer fetches rápidos SIN pausa, no el motor per se. Regla de ritmo: **delay entre
> requests con jitter aleatorio** (nunca fijo — el timing regular es en sí una firma de bot).
> Bing: ~500ms-1s + jitter. Yandex: similar. Si un motor devuelve `429`/captcha: **backoff y
> stop** (no reintentar en caliente). Con el método navigate 1×1 del Step 3 el ritmo ya es lento
> por naturaleza; si se acelera con `fetch()` en lote, el throttle+jitter es imprescindible.
>
> **Ojo (limitación de fondo)**: el catálogo son **ediciones especiales**, y tanto el texto como
> la reversa tienden a devolver la edición **regular/hermana**, cuyo arte difiere → `_same_cover`
> la rechaza (correctamente). Por eso para varios items no habrá candidata: el hi-res del scan
> especial exacto simplemente no está indexado. Es esperado, no un bug.
>
> **Fallback a Google texto (emergencia, con cautelas)**: SOLO si Bing se degrada (muy pocas URLs,
> `< 3` en varias variantes seguidas) o se bloquea. **Sin la sesión del owner (obligatorio)**: NO
> navegues a Google (una navegación normal va logueada y ata cualquier bloqueo a su cuenta, que
> puede escalar a suspensión — gotcha #145). En su lugar, navegá **una sola vez** a
> `https://www.google.com/` y desde esa página dispará los fetches same-origin con
> **`credentials: 'omit'`** (la Fetch API no adjunta cookies a ese request → sale anónimo; NO
> desloguea al owner, solo desacopla ESE pedido de su identidad):
>
> ```javascript
> // Estando en una página google.com (navegar 1 vez a https://www.google.com/ primero):
> const r = await fetch('https://www.google.com/search?q=' + encodeURIComponent(query) + '&udm=2',
>                       {credentials: 'omit'});           // ← anónimo, no usa la sesión del owner
> const html = await r.text();
> const ext = [...new Set((html.match(/https?:\/\/[^"\s]+?\.(?:jpg|jpeg|png|webp)/gi) || [])
>   .filter(u => !/google|gstatic/.test(u)))];
> ```
>
> **Cautelas duras** (la IP sigue siendo la del owner, así que el volumen igual se acota): delay
> 3-5s + jitter fuerte, tope bajo por sesión (≤40 requests), **stop al primer `429`/`/sorry`** (el
> cooldown es largo). Es un recurso escaso, no el camino por defecto — para exprimir residuales
> preferí `--serper-fallback` (Step 5), que corre server-side y ni siquiera toca el navegador del
> owner. El resto del pipeline (validación, flush) es igual.

**"Baja calidad" en PORTADAS (img_idx 0)** = factor de reescalado en la card del catálogo
(`fetch_better_covers.cover_upscale_factor(w, h)` = `min(300/w, 420/h)`, la card real es
~300×420 px con `object-fit: contain`) **>= `fetch_better_covers.UPSCALE_TARGET_MIN`
(1.6)**, con las **apaisadas** (`w > h`, recorte destruido — p.ej. `cover150/` de
image.aladin.co.kr) priorizadas primero (default desde 2026-09-02, `--target-rule scale`).
El ÁREA sola (< 90 000 px, criterio viejo, mismo umbral de `scripts/audit/data_quality.py`
para "pixelada" en el panel) **NO predice si una portada se ve mal**: un triage con visión
sobre 579 portadas < 90 000 px del corpus real (Etapa 1, `docs/reference/images.md` §
"Etapa 1 — resultados", gotcha #172) encontró que el 91,2% se ven BIEN — el 84% son
`static.listadomanga.com` a ~210×300 px, que en la card sólo se estira 1.4×. El factor de
reescalado separa correctamente lo bueno (528 casos <=1.6×) de lo malo (51 casos >=2.0×,
distribución bimodal). `--target-rule area` restaura el criterio viejo por compatibilidad.
La **galería** (img_idx >= 1) sigue usando siempre el criterio de 90 000 px — la Etapa 1
sólo evaluó portadas. Ninguno de los dos criterios es configurable por número; si hace
falta cambiar el umbral, se cambia la constante en `fetch_better_covers.py`
(`UPSCALE_TARGET_MIN` o `LOW_QUALITY_PX`), no este documento.

**Referencia degenerada (`< MIN_REF_PX`, 2 500 px)**: una imagen actual por debajo de ese
mínimo (típicamente un GIF de 1×1 px = placeholder "imagen no disponible" de Amazon) NO sirve
como referencia para `_same_cover` — rechazaría toda candidata (0 matches garantizados). Esos
targets se tratan como **"sin imagen"**: se saltan salvo `--include-no-image`, y ahí van
`verified:false` y sin variante reverse. Sin este guard los ~46 placeholders de 1px copaban el
`--limit` en cada corrida (ordenan primero por px) y nunca se llegaba a las portadas reales de
baja resolución (fix estructural 2026-06-12).

**La regla de oro de relevancia** (lo que arregla el problema histórico de "me manda otros
volúmenes / ediciones / cosas no relacionadas"): una candidata SOLO se acepta si pasa TRES
verificaciones: (1) `fetch_better_covers._same_cover(actual, candidata, MAX_HASH_DIST)` — el
AND-gate endurecido del audit 2026-06-10: **aspect ratio ±25% ∧ aHash ≤6 ∧ dHash ≤8 ∧
pHash ≤8 ∧ NCC ≥0.90 + gate de entropía + denylist de placeholders** (capa incomputable =
rechazo, default-deny); (2) `fetch_better_covers.candidate_metadata_conflict(item, url,
page_title)` — si la URL/título de la candidata declara OTRO volumen u OTRO ISBN que el item,
hard reject; y (3) `fetch_better_covers._is_soft_image(candidata)` — **gate de calidad de
display (gotcha #98)**: la identidad no garantiza calidad. Una candidata se rechaza si es
CHICA (`< SOFT_GUARD_PX` = 150k px) Y BLANDA (`_detail_ratio < DETAIL_RATIO_MIN` = 0.115):
un escaneo blando/upscale tiene más px pero, mostrado agrandado, se ve pixelado. Las grandes
pero blandas pasan (se muestran reducidas → nítidas). Otro volumen / otra edición / arte
distinto / escaneo blando chico → se descarta. Está bien que una candidata no sea
pixel-idéntica (puede ser un escaneo mejor con el mismo arte), pero tiene que ser
**visiblemente la misma portada Y verse bien**. Precisión > recall: mejor 0 candidatas que
una no relacionada o fea. (Las tres viven en `sc_validate.py`, fuente única con producción.)

**Denylist de rechazos (ledger, 2026-07-08)**: además de las tres verificaciones de arriba,
`sc_validate.py` consulta `fetch_better_covers.is_rejected_candidate(slug, url, hash, ledger)`
contra `data/cover_rejections.jsonl` — cada candidata que el owner rechazó alguna vez en la UI
queda registrada ahí (URL, hash aHash, motivo, y metadata de la candidata) y **no vuelve a
proponerse** en corridas futuras del skill (el índice externo no cambia entre corridas, así
que sin esto se re-buscaría y re-ofrecería lo mismo ya descartado). El veto es por URL exacta
(siempre) o por hash (solo si el motivo registrado es de IDENTIDAD — otro tomo, otra edición,
etc. — nunca por motivo de calidad, para no vetar la MISMA candidata correcta en mejor
resolución). Esto es 100% del motor (`fetch_better_covers.py`), delegado sin cambios de código
en este skill. El owner puede etiquetar el motivo de rechazo opcionalmente en la UI
(`cover-preview.html`) con los chips de un clic o las teclas `1`-`5` (Otro tomo / Otra edición /
Arte sin logo / No es la obra / Mala calidad) que aparecen tras rechazar una candidata —
etiquetar es opcional y nunca bloquea el flujo de aprobar/rechazar.

**Regla absoluta**: NUNCA escribe ni modifica `data/items.jsonl`. Solo escribe a
`data/cover_preview.json`. Todas las candidatas van con `confidence: "low"` y
`status: "pending"` — el owner aprueba o rechaza manualmente en la UI.

> **Antes de correr**: si tenés `cover-preview.html` abierto en el navegador, cerrá o recargá
> la pestaña. Si aprobás/rechazás algo en la UI mientras el skill corre, el POST
> `/api/save-cover-preview` manda la copia en memoria (vieja) y pisa lo que el skill agregó.
> El flush del skill es self-healing (re-asienta todo en cada item, ver Step 3e), pero igual
> conviene no editar la cola durante la corrida.

## Parámetros reconocidos

| Flag | Default | Qué hace |
|---|---|---|
| `--limit N` | `0` (todas) | Máximo de targets (imágenes) a procesar. **Por defecto se procesan TODAS** las que falten (100%); pasá `--limit N` solo si querés acotar a N en esta corrida. |
| `--slug SLUG` | — | Procesa solo el item con ese slug exacto. |
| `--only-covers` | off | Salta la galería (img_idx ≥ 1) y procesa solo portadas (img_idx 0). Útil para acotar a portadas sin mezclar con fotos de galería. |
| `--gallery-only` | off | Salta las portadas (img_idx 0) y procesa solo imágenes de galería (img_idx ≥ 1). |
| `--target-rule {scale,area}` | `scale` | Criterio de "baja calidad" para PORTADAS (img_idx 0; la galería siempre usa área). `scale` (default, 2026-09-02): factor de reescalado en card >= 1.6, apaisadas primero — ver más arriba y gotcha #172. `area` = criterio viejo (< 90 000 px), conservado por compatibilidad. |
| `--include-gallery` | off | **DEPRECADO / no-op**: la galería ya se procesa por defecto. Se sigue aceptando para no romper invocaciones viejas, pero no cambia nada. |
| `--include-no-image` | off | Por defecto se saltan items sin imagen (no hay portada actual con qué verificar `_same_cover`). Con este flag se incluyen, pero sus candidatas quedan **sin verificar** (`verified: false`). |
| `--retry-failed` | off | Por defecto se omiten targets cuyo último intento (en `data/cover_search_attempts.jsonl`) tuvo 0 matches y fue hace menos de 30 días. Con este flag se procesan igual. |
| `--query-extra "texto"` | — | Texto adicional al final de cada variante de query de texto (Bing). |
| `--serper-fallback` | off | Paso FINAL opcional (Step 5): tras terminar el loop de Chrome, invoca el motor de producción (`fetch_better_covers.py`, ya con `SERPER_API_KEY` activa) para reverse-image vía Google Lens en los targets que terminaron en 0 matches. De pago (~US$0.30-1.00 / 1000 búsquedas Lens) — solo se corre si el owner lo pide explícitamente con este flag. |

> **Por defecto se procesan portadas Y fotos de galería** (`img_idx 0` y `>= 1`). Ojo: las fotos
> de galería interior (extras/bonus) son irrecuperables en la mayoría de casos — no existe copia
> externa de esa foto específica (en una corrida real, 12 de 25 targets de galería dieron 0
> matches), así que es esperable que la galería aporte pocas candidatas. Usar `--only-covers`
> para acotar a portadas, o `--gallery-only` para exclusivamente galería.

**Tier de modelo recomendado (auditoría Fable 2026-07-08, hallazgo F10)**: el skill
corre en el hilo principal, no fan-out. El loop es mecánico (navegar Chrome +
extraer con regex + validar por subprocess) y el criterio genuino vive en scripts
(`sc_plan.py`/`sc_validate.py`/`sc_flush.py`/`fetch_better_covers.py`), no en
razonamiento del modelo — **`sonnet` alcanza de sobra; nunca hace falta `opus`**.

---

## Step 0 — Verificar que Chrome está disponible

Llamar `mcp__claude-in-chrome__list_connected_browsers`. Si no hay browsers conectados,
abortar con:

```
ERROR: Chrome no disponible.

Para usar este skill:
1. Instala la extensión "Claude for Chrome" desde el Chrome Web Store.
2. Abre Chrome y asegúrate de que la extensión esté activa y conectada.
3. Vuelve a invocar /watch-search-covers
```

Después, obtené un tab ID con `mcp__claude-in-chrome__tabs_context_mcp` (`createIfEmpty: true`).

---

## Step 1 — Identificar items y construir el PLAN de queries

Planificador determinista (0 tokens LLM) compilado a `scripts/retrofit/sc_plan.py`
(auditoría Fable 2026-07-08, hallazgo F9 — antes ~300 líneas de Python embebido que
ya habían drifteado 3 veces; mismo criterio que `sc_validate.py`/`sc_flush.py`, que
tuvieron el mismo problema y ya son scripts permanentes con tests). **No copies el
algoritmo acá**: si hace falta un cambio de comportamiento, se cambia el script (y
sus tests en `tests/test_sc_plan.py`), no este documento.

Invocá el script con los flags que reciba el skill (todos opcionales, mapean 1:1 a
los parámetros del skill):

```bash
.venv/bin/python scripts/retrofit/sc_plan.py \
    [--limit N] [--slug SLUG] [--include-no-image] \
    [--only-covers] [--gallery-only] [--target-rule scale|area] [--retry-failed] \
    [--query-extra "texto"]
```

Escribe `.tmp_sc_plan.json` (la lista de targets que consume el loop del Step 3) y
resetea `.tmp_sc_acc.json` (acumulador self-healing de esta corrida), e imprime en
stdout el resumen de targets a procesar (título, editorial, tipo de target, píxeles
actuales, cantidad de queries). Si no hay imágenes que necesiten búsqueda, imprime
"No hay imágenes que necesiten búsqueda. Nada que hacer." y termina en 0 — en ese
caso el skill reporta y para, sin entrar al Step 2/3.

Qué hace el script (para contexto, no para reimplementar):
- Umbral de "baja calidad" en PORTADAS = `fetch_better_covers.cover_upscale_factor(w, h)
  >= fetch_better_covers.UPSCALE_TARGET_MIN` (1.6, default, `--target-rule scale`), con
  apaisadas primero; `--target-rule area` usa el criterio viejo,
  `fetch_better_covers.LOW_QUALITY_PX` (90 000 px). Ambos se importan del motor para que
  no puedan driftear de producción. La galería (img_idx ≥ 1) siempre usa `LOW_QUALITY_PX`.
- Referencia degenerada (< `MIN_REF_PX` = 2 500 px, típico placeholder 1×1 de Amazon)
  se trata como "sin imagen": se salta salvo `--include-no-image`.
- **Referencia PLACEHOLDER (gotcha #179, 2026-09-02)**: aunque tenga tamaño de canvas
  real (no cae en el guard de arriba), una referencia detectada por
  `image_store.known_placeholder_url_reason(url)` (por URL — p.ej. la "tarjeta de
  título" `.gif` de Rakuten, gotcha #171) o `image_store.placeholder_reason(bytes)`
  (por contenido/firma) se trata IGUAL que "sin imagen": se salta DURO por defecto (con
  contador y motivo en el resumen impreso), y con `--include-no-image` entra con
  referencia blanqueada. Motivo: reverse-image contra un placeholder devuelve basura
  sistemática (hallazgo del juez: 9/9 candidatas de la Etapa 2 usando la tarjeta de
  Rakuten como consulta fueron slides/logos/cabeceras sin relación). Cada target trae
  un campo **`reference_kind`** (`"real"` / `"placeholder"` / `"none"`) — el Step 3 lo
  lee para decidir la vía de búsqueda (ver abajo).
- Salta `(slug, action, target)` que YA tienen una candidata del skill (campo
  `match_dist`) en cualquier estado — pending/approved/rejected — en
  `data/cover_preview.json`.
- Salta targets con 0 matches en los últimos 30 días (`data/cover_search_attempts.jsonl`),
  salvo `--retry-failed`.
- Arma las variantes de query por idioma: whakoom primero para Español, luego
  yandex-reverse; yandex-reverse primero para el resto de idiomas (sin whakoom); las
  de texto (serie+vol+edición+editorial+"portada") van después, en **Bing Imágenes**
  (motor de texto primario). Cada variante trae un campo `engine` (`bing` para texto y
  whakoom, `yandex` para reverse) que el loop del Step 3 registra en el ledger de intentos.
  Con `reference_kind != "real"` la variante `yandex-reverse` NUNCA se genera (no hay
  `ref_url` utilizable) — estructural, no depende de que el Step 3 la filtre.
- Cada target trae **`reference_sha256`** (sha256 del archivo local de referencia al
  momento del plan; `""` si `reference_kind != "real"`) — guard ANTI-DRIFT que consume
  `sc_validate.py` en el Step 3b (ver gotcha #178/#179).

---

## Step 2 — El validador de imágenes (permanente, NO se regenera)

La validación vive en `scripts/retrofit/sc_validate.py` — un script PERMANENTE y
testeado (`tests/test_sc_validate.py`) que delega todo el criterio en
`fetch_better_covers`: identidad (`_same_cover` AND-gate + `candidate_metadata_conflict`)
y calidad de display (`_is_soft_image`: descarta candidatas chicas+blandas, gotcha #98).
**No escribas ni copies código de validación en esta corrida**: las versiones
anteriores de este skill regeneraban una copia embebida y esa copia drifteó de
producción (umbral laxo, sin filtro de volumen/ISBN) — fue la causa de los falsos
positivos pre-2026-06-11. Si la validación necesita cambios, se cambia el script
(y sus tests), no este documento.

Sanity check antes del loop:

```python
import subprocess
r = subprocess.run(['.venv/bin/python', 'scripts/retrofit/sc_validate.py', '/nonexistent'],
                   capture_output=True, text=True)
print(r.stdout.strip())   # debe imprimir {"validated": [], "error": "input not found: ..."}
```

---

## Step 3 — Loop: por cada item, ITERAR variantes hasta juntar matches

Para **cada item** del plan (índice `i`), recorrer sus variantes de query en orden. Tras cada
variante, validar lo encontrado y acumular las candidatas verificadas (dedup por `new_url`).
**Cortar apenas haya `TARGET_MATCHES` (=3) candidatas verificadas**, o cuando se agoten las
variantes. Así no se gastan navegaciones de más cuando la primera query ya acertó, pero se
sigue intentando con otra cuando no.

Llevá un acumulador en memoria por item: `item_candidates = []`.

### 3a. Cargar el item y sus variantes

```python
import json
from pathlib import Path

plan = json.loads(Path('.tmp_sc_plan.json').read_text(encoding='utf-8'))
target             = plan[i]
slug               = target['slug']
curr_px            = target['pixels']
img_idx            = target.get('img_idx', 0)
image_ref_local    = target.get('image_ref_local', '')
reference_kind     = target.get('reference_kind', 'real')     # "real"/"placeholder"/"none"
reference_sha256   = target.get('reference_sha256', '')       # guard anti-drift (gotcha #178/#179)
candidate_action   = target.get('candidate_action', 'replace_cover')
candidate_target   = target.get('candidate_target', '')
target_label       = target.get('target_label', 'portada')
variants           = target['variants']
# Defensiva (el plan YA nunca genera 'reverse' sin referencia real —
# build_variants necesita un ref_url http utilizable — pero un plan viejo de
# antes de este fix, o un futuro drift del planificador, no debería poder
# disparar un reverse-image contra una referencia placeholder/ausente):
if reference_kind != 'real':
    variants = [v for v in variants if v.get('kind') != 'reverse']

# item completo desde items.jsonl — SIEMPRE releído fresco (no el snapshot del
# plan): si desapareció del corpus entre el Step 1 y este target (purga/expulsión
# concurrente, gotcha #178), no tiene sentido buscarle portada.
item = None
for l in open('data/items.jsonl'):
    if not l.strip():
        continue
    o = json.loads(l)
    if o.get('slug') == slug:
        item = o; break

if item is None:
    print(f"\n[{i+1}/{len(plan)}] {slug} — DRIFT: el item ya no está en items.jsonl "
          f"(expulsado/re-slugueado entre el plan y esta corrida). Salteado, 0 navegaciones.")
    continue   # siguiente target del plan; no hay con qué construir el input de sc_validate

TARGET_MATCHES  = 3
item_candidates = []   # acumulador verificado de ESTE target (una imagen)
engines_used    = set()   # motores realmente consultados (para el ledger de intentos)
drift_detected  = ''      # motivo de drift (gotcha #178/#179), si `sc_validate.py` lo marca en 3b

print(f"\n[{i+1}/{len(plan)}] {item.get('title','')} [{target_label}]")
print(f"  Imagen actual: {curr_px:,} px" if curr_px > 0 else "  Sin imagen")
if reference_kind != 'real':
    print(f"  reference_kind={reference_kind}: sin referencia utilizable — sólo variantes de "
          f"TEXTO (nunca yandex-reverse con esta referencia).")
```

### 3b. Por cada variante: navegar + extraer + validar (parar al juntar matches)

Repetir para cada `variant` en `variants` **hasta** que `len(item_candidates) >= TARGET_MATCHES`:

1. **Navegar + extraer en un solo `browser_batch`** (navigate a `variant['url']` +
   javascript_tool). Imprimí `variant['label']` y `variant['query']` antes, y registrá el
   motor consultado: `engines_used.add(variant.get('engine', ''))`.

   > **Nota MCP**: dentro de `browser_batch`, los items van con el nombre CORTO de la
   > tool (`"name": "navigate"`, `"name": "javascript_tool"`), NUNCA el nombre MCP
   > completo (`mcp__claude-in-chrome__...` → "unknown tool"). Y el item de
   > `javascript_tool` DEBE llevar `"input": {"action": "javascript_exec", "tabId": ...,
   > "text": ...}` — sin el campo `action` el MCP rechaza con "javascript_exec is the
   > only supported action".

   > **Nota de escaping en regex JS**: al escribir el regex via MCP, los backslashes se
   > escapan UNA vez (no doble). El regex correcto es `/https?:\/\/[^"\s]+?\.(?:jpg|jpeg|png|webp)/gi`
   > con `\s` literal (un backslash). Si se escribe `\\s` (doble), el MCP lo convierte en
   > `\s` correcto, pero si se parte desde markdown con `\\\\s`, el double-escape se propaga
   > y rompe el patrón. Usar SIEMPRE el literal de un solo backslash en el string JS.

   **La extracción depende de `variant['kind']`:**

   **Si `variant['kind'] == 'reverse'` (Yandex, búsqueda por foto)** — es la primera variante
   de cada item, usa la imagen actual como consulta:

   ```javascript
   // Yandex reverse image: las URLs de resultados están en el HTML crudo. Mismo regex,
   // excluyendo dominios de Yandex/Google. Corta antes de "?" → sin bloqueo del MCP.
   // Regex: un backslash antes de s (\s) — NO doble.
   const t = document.body ? document.body.innerText : '';
   const html = document.documentElement.innerHTML;
   const ext = [...new Set((html.match(/https?:\/\/[^"\s]+?\.(?:jpg|jpeg|png|webp)/gi) || [])
     .filter(u => !/yandex|yastatic|google|gstatic/.test(u)))];
   JSON.stringify({captcha: /captcha|robot|not a robot/i.test(t), urls: ext.slice(0, 20)})
   ```

   > Si `captcha == true` → Yandex está pidiendo verificación; saltá esta variante (seguí con
   > las de texto). No intentes resolver el captcha.

   **Si `variant['kind'] == 'text'` (Bing Imágenes — `variant['engine'] == 'bing'`)**:

   ```javascript
   // Bing Imágenes: las URLs full-res están en el atributo `m` (JSON) de cada card, como
   // murl&quot;:&quot;<URL>&quot;. Extraé por ese patrón; el regex genérico (cortando antes de
   // "&") también funciona. Filtrá dominios de Bing/Microsoft. Regex: un backslash antes de s.
   const html = document.documentElement.innerHTML;
   const ext = [...new Set((html.match(/https?:\/\/[^"\s&]+?\.(?:jpg|jpeg|png|webp)/gi) || [])
     .filter(u => !/bing|microsoft|gstatic|google|yandex/.test(u)))];
   JSON.stringify(ext.slice(0, 25))
   ```

   > **Nota de truncado**: el output del MCP se corta si es muy largo. Si se trunca, usá solo
   > las URLs completas que llegaron (ignorá la última si quedó a medias). No reintentes por el
   > truncado — con `_same_cover` filtrando, alcanza con que la portada correcta aparezca entre
   > las que sí llegaron.
   >
   > **Si Bing se degrada** (`ext` casi vacío, `< 3`, en varias variantes seguidas) o devuelve
   > captcha/429 → recién ahí el **fallback de emergencia a Google** (ver "Fallback a Google
   > texto" en la nota inicial): `https://www.google.com/search?q=<query>&udm=2`, extraé con el
   > regex genérico filtrando `google`/`gstatic`, con **delay 3-5s + jitter, tope ≤40/sesión y
   > stop al primer `/sorry`**. Preferí `--serper-fallback` (Step 5) antes que esto.

   En ambos casos: tomá la lista de URLs (`urls` para reverse, `ext` para texto). Si viene
   vacía → esa variante no dio resultados; pasá a la siguiente.

   > **Ritmo (throttling + jitter)**: entre variantes/targets mantené un delay con jitter
   > aleatorio (Bing ~500ms-1s). No dispares navegaciones sin pausa: el timing regular y el
   > volumen sin freno son lo que gatilla los bloqueos (fue la causa del 429 de Google en el
   > piloto, no el motor).

2. **Validar las URLs de esa variante** (mismo patrón que antes, vía el validador):

   ```python
   import json, subprocess, uuid
   from pathlib import Path

   urls_from_chrome = [...]   # URLs extraídas del motor (Google udm=2 / Yandex reverse / fallback) para ESTA variante
   candidate_urls = [
       {'url': u, 'page_title': '', 'domain': u.split('/')[2] if u.startswith('http') else '',
        'query': variant['query']}
       for u in urls_from_chrome if u.startswith('http')
   ]

   tmp_in = Path(f'.tmp_sc_input_{uuid.uuid4().hex[:8]}.json')
   tmp_in.write_text(json.dumps({'item': item, 'candidate_urls': candidate_urls,
                                 'curr_px': curr_px,
                                 'ref_image_local': image_ref_local,
                                 'reference_sha256': reference_sha256}, ensure_ascii=False), encoding='utf-8')
   result = subprocess.run(['.venv/bin/python', 'scripts/retrofit/sc_validate.py', str(tmp_in)],
                           capture_output=True, text=True)
   tmp_in.unlink(missing_ok=True)
   out = json.loads(result.stdout) if result.returncode == 0 else {}
   got = out.get('validated', []) if result.returncode == 0 else []
   if result.returncode != 0:
       print(f"    ERROR validación: {result.stderr[:200]}")

   # Guard anti-drift (gotcha #178/#179): la referencia con la que se armó el
   # plan ya no es la actual (purga/reemplazo concurrente a mitad de la
   # corrida) — sc_validate.py lo detecta comparando reference_sha256 contra
   # el archivo actual y devuelve [] SIN tocar la red. Cortar el resto de las
   # variantes de ESTE target (todas darían el mismo drift) en vez de seguir
   # gastando navegaciones para una referencia obsoleta.
   if out.get('drift'):
       drift_detected = out['drift']
       print(f"    DRIFT ({drift_detected}): la referencia cambió desde que se armó el "
             f"plan — cortando variantes restantes de este target, 0 candidatas.")
       break

   # Acumular dedup por new_url
   for c in got:
       if not any(ec['new_url'] == c['new_url'] for ec in item_candidates):
           item_candidates.append(c)
   vmark = '✓' if got else '·'
   print(f"  [{variant['label']}] {len(candidate_urls)} urls → "
         f"{len(got)} match(es) · acumulado {len(item_candidates)} {vmark}")
   ```

3. Si `len(item_candidates) >= TARGET_MATCHES` → **parar de iterar variantes** para este item.

### 3c. Ordenar y recortar las candidatas del item

```python
# Mejor primero (menor distancia, mayor resolución) y tope de 10 por item
item_candidates.sort(key=lambda c: (c.get('match_dist') if c.get('match_dist') is not None else 99,
                                    -c.get('new_pixels', 0)))
item_candidates = item_candidates[:10]
print(f"  → {len(item_candidates)} candidatas finales para {slug}")
```

### 3d. Registrar el intento en `data/cover_search_attempts.jsonl`

Al terminar cada target (con o sin matches), **siempre** apendear una línea al archivo de intentos:

```python
import json, datetime
from pathlib import Path

attempts_path = Path('data/cover_search_attempts.jsonl')
attempt_entry = {
    'slug'        : slug,
    'action'      : candidate_action,
    'target'      : candidate_target,
    'attempted_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00'),
    'matches'     : len(item_candidates),
    'engines'     : sorted(e for e in engines_used if e),   # trazabilidad del motor (2026-07-11)
}
if drift_detected:
    attempt_entry['drift'] = drift_detected   # gotcha #178/#179: no confundir con 0-match real
with attempts_path.open('a', encoding='utf-8') as f:
    f.write(json.dumps(attempt_entry, ensure_ascii=False) + '\n')
```

> **`drift` vs. 0-match real**: un target con `drift` se registra igual que cualquier
> otro 0-match a los efectos del skip de 30 días (`--retry-failed` lo ignora), pero el
> campo lo distingue en el log de un 0-match genuino (`_same_cover` rechazando
> ediciones distintas) — útil para diagnosticar si una corrida sufrió una purga
> concurrente (gotcha #178) sin tener que releer el snapshot del plan a mano.

> **Por qué se registra `engines`** (red team 2026-07-11): sin saber QUÉ motor produjo cada
> intento, el skip de 30 días del Step 1 cierra el reintento de un target aunque el 0-match
> haya venido de un motor degradado (ej. Bing flojo para un idioma nicho). Registrar el motor
> deja el rastro para diagnosticar match-rate por motor/idioma y decidir reintentos con criterio.
> (El motor de producción `fetch_better_covers` ya apendea su propio campo `engines` — mismo
> nombre, formato coherente.)

### 3e. Si no hubo matches, no inventar

Si `item_candidates` quedó vacío, **no se escribe nada** para ese item en `cover_preview.json`
(es correcto: preferimos 0 candidatas a candidatas no relacionadas). Continuar con el siguiente item.

### 3f. Flush self-healing a cover_preview.json (después de cada item)

El flush es un script PERMANENTE (`scripts/retrofit/sc_flush.py`) — nunca reescribir esta
lógica inline. Una corrida anterior reconstruyó los dicts a mano y perdió el campo `new_image`,
rompiendo la cola completa; el script ahora lo rechaza con exit 1 antes de escribir nada.
Las candidatas se pasan EXACTAMENTE como las devolvió `sc_validate.py`, sin modificarlas.

**Guard de URL compartida (gotcha #173/#174, 2026-09-02):** en cada flush, `sc_flush.py`
re-evalúa TODO el acumulador de la corrida (`.tmp_sc_acc.json`) buscando la MISMA `new_url`
propuesta a ≥2 slugs distintos — el caso medido en la Etapa 2 tanda 1: para items **sin
imagen de referencia** (`--include-no-image`), `sc_validate.py` no puede correr
`_same_cover` y whakoom a veces devuelve la miniatura de la SERIE o de OTRO tomo (36/50
items de esa tanda tenían la misma `new_url` propuesta a otro tomo de la misma serie). Si el
`page_title`/`new_url` declara el tomo de un solo slug del grupo, esa se conserva y el resto
queda `rejected`/`otro_tomo`; si no hay forma de desambiguar, todas quedan `pending` pero con
`shared_with`/`confidence:"low"`/`needs_visual_review:true` — **nunca se auto-aprueban**. El
stdout del flush trae el resumen (`shared_url_guard`). No requiere ninguna acción del skill:
es automático dentro de `sc_flush.py`. Detalle en `docs/reference/images.md` § "Validación
sin referencia — guard de URL compartida".

```python
import json, subprocess, uuid
from pathlib import Path

if item_candidates:
    tmp_fl = Path(f'.tmp_sc_flush_{uuid.uuid4().hex[:8]}.json')
    tmp_fl.write_text(json.dumps({
        'slug': slug, 'item': item, 'candidates': item_candidates,
        'candidate_action': candidate_action, 'candidate_target': candidate_target,
        'old_local': image_ref_local, 'old_url': target.get('image_ref_url',''),
        'curr_px': curr_px,
    }, ensure_ascii=False), encoding='utf-8')
    r = subprocess.run(['.venv/bin/python', 'scripts/retrofit/sc_flush.py', str(tmp_fl)],
                       capture_output=True, text=True)
    tmp_fl.unlink(missing_ok=True)
    print(r.stdout.strip() or r.stderr[:200])
```

---

## Step 4 — Limpiar y reportar

Borrar los archivos temporales, luego reportar:

```python
import json
from pathlib import Path

# Cleanup
for p in ['.tmp_sc_plan.json', '.tmp_sc_acc.json']:
    Path(p).unlink(missing_ok=True)
for f in Path('.').glob('.tmp_sc_input_*.json'):
    f.unlink(missing_ok=True)
for f in Path('.').glob('.tmp_sc_flush_*.json'):
    f.unlink(missing_ok=True)

preview_path = Path('data/cover_preview.json')
entries = json.loads(preview_path.read_text(encoding='utf-8')) if preview_path.exists() else []
with_pending = sum(1 for e in entries
                   if any(c.get('status') == 'pending' for c in e.get('candidates', [])))
total_pending = sum(sum(1 for c in e.get('candidates', []) if c.get('status') == 'pending')
                    for e in entries)

print(f"\n✓ Búsqueda completada:")
print(f"  Items procesados con Chrome: {len(plan)}")
print(f"  Productos con candidatas:    {with_pending}")
print(f"  Candidatas totales pending:  {total_pending}")
print(f"  Revisar y aprobar en:        http://localhost:8000/web/cover-preview.html")
```

> Es **esperable y correcto** que ahora haya menos candidatas que antes: el filtro `_same_cover`
> descarta todo lo que no sea la misma portada. Items para los que Bing texto no tiene la portada
> hi-res quedarán sin candidatas — eso es preferible a llenarte la cola de cosas no relacionadas.
> Para esos casos existe un paso adicional opcional: **Step 5** (`--serper-fallback`), la
> búsqueda reversa por foto vía Serper Lens (la key ya está activa, no hace falta conseguir una).

---

## Step 5 (opcional, `--serper-fallback`) — Fallback a Serper Lens vía el motor de producción

Solo si el usuario invocó el skill con `--serper-fallback`. Corre DESPUÉS del Step 4, sobre los
targets que este skill no pudo resolver: los que terminaron el Step 3 con 0 matches, y en
particular los que el Step 1 saltó la variante Yandex por tener como referencia un thumbnail de
`static.listadomanga.com` (Yandex no los tiene indexados — pero Google Lens hace el matching
visual **server-side**, recibiendo la URL de la imagen, y NO necesita que esté indexada en
ningún lado, así que esos targets SÍ son elegibles para este fallback).

**Acotar por slug** (`--slugs`, agregado 2026-07-08): el motor YA acepta acotar la corrida a una
lista exacta de slugs — `--slugs slug1,slug2` (coma-separado) y/o repetible (`--slugs a --slugs
b`). Se aplica ADEMÁS de los filtros de candidatura: un slug pedido que no es candidato (px ya
buenos, signal de skip, o inexistente) se reporta en el output y se saltea (no se fuerza su
búsqueda). Esto cierra el gap anterior — para el fallback dirigido a los targets que este skill
dejó en 0 matches, pasá exactamente esos slugs. (`--limit N` sigue disponible como filtro de
alcance por cantidad; `--slugs` es el filtro por identidad exacta.) El motor (invocado
directo, sin pasar por `sc_plan.py`) sigue gateando con `fetch_better_covers.LOW_QUALITY_PX`
(90 000 px, sin cambios — este script no adoptó el criterio nuevo de `--target-rule scale` del
Step 1). En el 100% de los casos reales las dos cosas coinciden (un target apaisado/blando de
baja resolución también tiene área < 90 000 px), pero si algún día `--slugs` reporta como "no
candidato" un slug que el Step 1 sí marcó, es por esta diferencia de criterio, no un bug.

Invocación exacta (verificada contra el `argparse` real del motor — `--preview` es el
comportamiento POR DEFECTO sin `--apply`):

```bash
# Toda la cola (acotando por cantidad):
.venv/bin/python scripts/retrofit/fetch_better_covers.py --limit 50 --verbose

# Solo los slugs que quedaron en 0 matches (acotando por identidad):
.venv/bin/python scripts/retrofit/fetch_better_covers.py \
    --slugs slug-que-fallo-1,slug-que-fallo-2 --verbose
```

- **Nunca pasar `--apply` ni `--apply-preview`**: sin `--apply`, `run()` recibe `preview=True`
  (default real del código: `preview=not args.apply`) → TODO va a `data/cover_preview.json`
  para aprobación manual, igual que el resto de este skill. Coherente con la Regla absoluta
  (nunca toca `items.jsonl`).
- `SERPER_API_KEY` se lee automáticamente de `.env` (está activa; no hace falta `--serper-key`).
- Por item, el motor prueba en este orden: CDN determinístico (si hay ISBN) → **Serper Lens**
  (si no hubo hit de CDN y hay `serper_key` + URL de imagen actual — YA es la estrategia
  PRIMARIA de búsqueda web del motor, sin flag extra) → texto Serper/Tavily (solo si Lens no
  encontró nada). Lo único gateado por `--serper-fallback` es que ESTE skill decida invocar el
  motor como paso final; el motor en sí no necesita ningún flag especial para usar Lens.
- Las candidatas de Lens con **referencia utilizable** (bytes descargables + px ≥ 10 000) pasan
  por el MISMO AND-gate `_same_cover` que las candidatas de Chrome (bypass cerrado, fix
  2026-07-08 / gotcha #131) → quedan `verified: true`, pero `confidence` sigue `"low"` (nunca
  auto-aplican). Sin referencia utilizable, el gate queda fail-closed (aspect ±0.25 +
  `candidate_metadata_conflict` + `_validate_page_content` con reintento, sin bypass abierto) y
  quedan `verified: false`.
- El motor también apendea a `data/cover_search_attempts.jsonl` (mismo formato que este skill +
  campo `engines`), así que el skip de 30 días del Step 1 (`--retry-failed` para ignorarlo) ya
  es coherente entre ambos caminos — no hace falta lógica extra en este documento.
- **Costo**: ~US$0.30-1.00 por 1000 búsquedas Lens (key activa, de pago). **Piloto
  recomendado**: primera corrida con `--limit 50`, revisar la cola en
  `http://localhost:8000/web/cover-preview.html`, y solo después escalar el límite o correrlo
  sin `--limit`.

Al terminar, reportar cuántas candidatas nuevas aportó este paso (comparar `total_pending` de
`cover_preview.json` antes/después de invocar el motor).

---

## Reglas (no negociables)

1. **NUNCA** escribir ni modificar `data/items.jsonl`
2. **NUNCA** llamar `--apply` ni `apply_preview()` — la aprobación es del owner
3. Todas las candidatas: `confidence: "low"`, `status: "pending"`
4. Solo invocar cuando el usuario lo pida explícitamente
5. Una candidata con imagen actual SOLO se acepta si pasa `_same_cover()` (AND-gate: misma
   portada) Y no tiene conflicto de metadata (`candidate_metadata_conflict()`: otro volumen /
   otro ISBN declarado en la URL/título → hard reject). Sin imagen actual
   (`--include-no-image`) queda `verified: false` para revisión más estricta — y además pasa
   por el guard de URL compartida entre slugs de `sc_flush.py` (gotcha #173/#174): si la
   misma `new_url` termina propuesta a ≥2 slugs de la corrida sin poder desambiguar por
   tomo, ninguna se auto-aprueba (quedan `pending` con `needs_visual_review:true`).
6. Máximo 10 candidatas por item; máx 3 matches dispara el corte de iteración
7. El skill es incremental: un (slug, action, target) con candidata DEL SKILL (campo
   `match_dist`) en CUALQUIER estado — pending, approved o rejected — se salta
   automáticamente (no se re-busca lo ya adjudicado). Las candidatas del script python
   `fetch_better_covers` (sin `match_dist`) NO bloquean: el skill corre igual sobre esos items.
8. Borrar los `.tmp_sc_*` al finalizar (son temporales). `scripts/retrofit/sc_validate.py` y `scripts/retrofit/sc_flush.py` son PERMANENTES — nunca borrarlos ni regenerar su lógica inline. `sc_flush.py` rechaza con exit 1 cualquier candidata sin `new_image` o `new_url` (guarda anti-drift).
9. Una candidata cuya URL (o hash con motivo de identidad) ya esté en `data/cover_rejections.jsonl`
   (ledger de rechazos del owner) NUNCA se propone de nuevo — la denylist la consulta
   `sc_validate.py` vía `fetch_better_covers.is_rejected_candidate()`, sin código propio en este
   skill.
10. El Step 5 (`--serper-fallback`, de pago) solo corre si el owner lo pide explícitamente con
    ese flag — nunca por defecto, y nunca con `--apply`/`--apply-preview`.
11. **Motor de texto = Bing por defecto** (riesgo de cuenta: scrapear Google con las cookies del
    owner puede escalar a suspensión de su cuenta Google). Google udm=2 es SOLO fallback de
    emergencia si Bing se degrada, y SIEMPRE **anónimo** — fetch con `credentials: 'omit'` desde
    una página `google.com` (no navegar logueado; no desloguea al owner, solo desacopla el
    request de su cuenta), con throttle fuerte (3-5s+jitter), tope ≤40/sesión y stop al primer
    `/sorry`. Ritmo con jitter en todos los motores; nunca ráfagas sin pausa. Para exprimir
    residuales, preferí `--serper-fallback` (server-side, ni toca el navegador del owner) antes
    que el fallback de Google.
12. **NUNCA** reverse-image (Yandex) contra una referencia placeholder (gotcha #171/#179):
    `sc_plan.py` detecta y saltea DURO cualquier referencia que matchee
    `image_store.known_placeholder_url_reason()` o `image_store.placeholder_reason()` — con
    `--include-no-image` entra con `reference_kind: "placeholder"` y SOLO variantes de texto
    (nunca se genera la variante `yandex-reverse` para esa referencia). Reverse-image contra un
    placeholder produce basura sistemática (hallazgo del juez: 9/9 candidatas sin relación).
13. **Guard anti-drift (gotcha #178/#179)**: si la referencia con la que se armó el plan cambió
    o desapareció a mitad de la corrida (purga/reemplazo concurrente), `sc_validate.py`
    (`reference_drift_reason`, comparando `reference_sha256` del plan contra el archivo actual)
    devuelve `drift` y el target se corta SIN generar candidatas sobre una referencia obsoleta —
    nunca cae al gate débil sin-referencia por un item que en realidad sí tenía referencia al
    momento del plan. Recomendación de proceso, no reemplazada por este guard: no correr este
    skill en paralelo con `purge_placeholder_images.py`/`mirror_images.py --gc` sobre el mismo
    corpus.
