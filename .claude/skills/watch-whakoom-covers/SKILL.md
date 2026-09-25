---
name: watch-whakoom-covers
description: Busca portadas en alta resolución para items ES (España) con imagen ausente o de baja calidad, resolviendo la página de EDICIÓN de Whakoom (whakoom.com/ediciones/<id>/<slug>) en vez de una búsqueda de imágenes genérica. Localiza la edición vía Bing (site:whakoom.com), la abre en el Browser pane y extrae metadata pública (editorial, idioma, formato, total de tomos, ediciones hermanas, lista de tomos con su cover) — SIN login, SIN tocar /comics/ ni /todos (bloqueadas por robots.txt / requieren cuenta). Sólo resuelve edición cuando editorial + idioma "Spanish (Spain)" + total de tomos coinciden con la colección de listadomanga del item; si hay ambigüedad entre ediciones hermanas (regular/kanzenban/deluxe), NO resuelve. Sólo cubre tomos <= 11 (Whakoom muestra como máximo los primeros ~11 tomos sin login) — tomos >11 quedan fuera del alcance de este skill. La validación de identidad/calidad de la imagen (misma portada, mejor resolución, no borrosa) es 100% de fetch_better_covers/sc_validate.py — este skill no reimplementa ese criterio. Escribe a data/cover_preview.json para aprobación manual. NUNCA modifica items.jsonl. Args opcionales: --limit N, --slugs SLUG1,SLUG2, --target-rule {area,scale}, --include-approved.
argument-hint: "[--limit N] [--slugs SLUG1,SLUG2] [--target-rule area|scale] [--include-approved]"
---

# watch-whakoom-covers — Portadas ES vía página de edición de Whakoom

Vía alternativa a `/watch-search-covers` para el mercado **España**, aprobada por el
owner el 2026-09-02. En vez de buscar una imagen suelta por texto/reverse-image (que
sobre el pool ES sólo acertó 1% real, gotcha #173), este skill busca la **página de
edición** de Whakoom (`/ediciones/<id>/<slug>`) — que expone editorial, idioma,
formato, total de tomos y la lista de los primeros ~11 tomos con su cover — y la
valida contra los metadatos del item (editorial + idioma + total de tomos de la
colección de `listadomanga.es` a la que pertenece) ANTES de proponer una imagen.
Precisión sobre recall, igual que el resto del pipeline de imágenes: mejor no
resolver que resolver a ciegas.

**Regla dura de acceso** (owner + robots.txt de whakoom.com): este skill **NUNCA**
navega a `/comics/<hash>/…` ni a `<edición>/todos` (ambas exigen login; `/comics/`
está además en `Disallow:` de robots.txt) y **NUNCA** intenta resolver ni rodear un
captcha/challenge de Cloudflare — si aparece uno, se abandona ESE target (0
candidatas) y se sigue con el siguiente. Consecuencia estructural: sólo se pueden
resolver tomos **`volume <= 11` o sin volumen** (oneshot); `we_plan.py` ya filtra
por esto — ver docs/scraper/sources/whakoom.md § "Resolución por página de edición
para portadas ES".

**Regla absoluta**: NUNCA escribe ni modifica `data/items.jsonl`. Sólo escribe a
`data/cover_preview.json` (vía `sc_validate.py` + `sc_flush.py`, sin reimplementar
esa lógica). Todas las candidatas van con `confidence: "low"` y `status: "pending"`
— el owner aprueba o rechaza manualmente en `http://localhost:8000/web/cover-preview.html`.

**Tier de modelo**: igual que `/watch-search-covers` — el loop es mecánico
(navegar + extraer JSON compacto + invocar scripts deterministas), el criterio
genuino vive en código (`we_plan.py`/`we_resolve.py`/`sc_validate.py`/`sc_flush.py`).
`sonnet` alcanza de sobra.

**Sólo corre a pedido explícito del owner** (política de skills del repo,
CLAUDE.md § "Skills invocation policy") — nunca automático tras un scrape.

---

## Parámetros reconocidos

| Flag | Default | Qué hace |
|---|---|---|
| `--limit N` | `0` (todos) | Máximo de targets a procesar en esta corrida. |
| `--slugs SLUG1,SLUG2` | — | Procesa solo esos slugs exactos (ignora `--limit`). |
| `--target-rule {area,scale}` | `area` | Criterio de "portada de baja calidad" en `we_plan.py`. `area` (default acá, distinto de `sc_plan.py`): píxeles < 90 000 — es el pool que motivó esta vía (portadas `static.listadomanga.com` ~210×300 px). `scale` es más estricto (factor de reescalado en card >= 1.6, gotcha #172/#175) y deja muy pocos targets ES. |
| `--include-approved` | off | Incluye items con `approved_at` (golden records). Por defecto se excluyen. |

---

## Step 0 — Verificar el Browser pane

Este skill usa el **Browser pane de Claude Code** (`mcp__Claude_Browser__*`), NO la
extensión Chrome del owner: las páginas `/ediciones/` son públicas y no requieren la
sesión/cookies del owner, así que no hay motivo para arriesgar su cuenta. Si el
Browser pane no está disponible, usar `mcp__claude-in-chrome__*` como fallback
únicamente (mismos pasos, mismas reglas de acceso).

Antes de arrancar el loop, confirmar que el pane abre `https://www.whakoom.com/`
sin bloqueo (una navegación de sanity-check). Si Cloudflare devuelve un challenge
en esa primera carga, **no insistir**: reportar al owner que Whakoom está
bloqueando la sesión actual y terminar sin procesar targets.

---

## Step 1 — Plan determinista (0 tokens LLM)

```bash
.venv/bin/python scripts/retrofit/we_plan.py \
    [--limit N] [--slugs SLUG1,SLUG2] [--target-rule area|scale] [--include-approved]
```

Escribe `.tmp_we_plan.json` e imprime en stdout el **universo real**: cuántos items
ES son resolubles (`volume <= 11` o vacío) vs no resolubles (`>11`, requiere login),
y cuántos targets quedan tras excluir ya-adjudicados/aprobados. Si imprime "No hay
targets pendientes", reportar y terminar sin entrar al loop. El resumen también
muestra cuántos targets tienen `total_tomos` **REMOTO** (`listadomanga_meta.py`) vs
heurístico **LOCAL** de fallback (ver Step 1b).

No copiar el algoritmo acá — si hace falta un cambio de criterio, se cambia
`scripts/retrofit/we_plan.py` (y sus tests en `tests/test_we_plan.py`).

---

## Step 1b — Completar `total_tomos` REMOTO (opt-in, hace red — tanda 3, 2026-09-02)

`we_plan.py` en sí NO hace red (mismo perfil que `sc_plan.py`); por defecto arma
`listado.total_tomos` con el heurístico LOCAL (conteo de items del corpus por
`edition_key`), que puede infra-contar series en curso. Antes de la corrida final
que arma el `.tmp_we_plan.json` que consume el Step 2, correr:

```bash
.venv/bin/python scripts/retrofit/listadomanga_meta.py --from-plan .tmp_we_plan.json
.venv/bin/python scripts/retrofit/we_plan.py [mismos flags que arriba]   # re-generar con el caché ya poblado
```

Esto fetchea (GET a `listadomanga.es/coleccion.php?id=N`, throttle 2s por
default) el `total_tomos`/`formato`/`paginas`/`editorial`/`ongoing` REALES de
cada `coleccion_id` distinto del plan que todavía no esté en
`data/listadomanga_collection_meta.jsonl`, y los cachea ahí (append-only, no se
borra entre corridas). Al re-correr `we_plan.py`, los targets de esas colecciones
salen con `listado.source == "listadomanga_remota"` en vez de `"local_count"` —
`we_resolve.py` (Step 4) usa ese dato como criterio DURO de desambiguación entre
ediciones hermanas, así que maximizar la cobertura remota reduce directamente los
`total_tomos_mismatch` (63/144 rechazos de la tanda 2 fueron por este motivo, ver
`docs/reference/images.md` § "Whakoom tanda 2"). Es SEGURO saltear este paso
(el skill sigue funcionando con el heurístico local, como antes de tanda 3) —
sólo reduce el hit rate.

No copiar el algoritmo acá — si hace falta un cambio de criterio, se cambia
`scripts/retrofit/listadomanga_meta.py` (y sus tests en `tests/test_listadomanga_meta.py`).

---

## Step 2 — Por cada target: localizar la edición

Cargar `.tmp_we_plan.json` y, para cada `target` (índice `i`):

```python
import json
from pathlib import Path

plan = json.loads(Path('.tmp_we_plan.json').read_text(encoding='utf-8'))
target = plan[i]
slug            = target['slug']
series_display  = target['series_display']
publisher       = target['publisher']
volume          = target['volume']            # "" para oneshot
listado         = target['listado']            # {coleccion_id, total_tomos, formato}
query           = target['query']              # site:whakoom.com "<serie>" <editorial>
bing_url        = target['bing_url']
cached_edition_url = target['edition_url']      # "" si no hay caché

item = None
for l in open('data/items.jsonl'):
    if not l.strip():
        continue
    o = json.loads(l)
    if o.get('slug') == slug:
        item = o; break
if item is None:
    print(f"[{i+1}/{len(plan)}] {slug} — DRIFT: ya no está en items.jsonl. Salteado.")
    continue
```

### 2a. Si ya hay `edition_url` en caché (`we_plan.py` la trajo de `data/whakoom_edition_map.jsonl`)

Saltar directo al **Step 3** con esa única URL — no repetir la búsqueda Bing.

### 2b. Si no, buscar en Bing IMÁGENES (máximo 3 candidatas)

```
navigate → target['bing_url']    # bing.com/images/search?q=site:whakoom.com "<serie>" <editorial>
```

> **Por qué Imágenes y no Bing web (hallazgo del piloto real, 2026-09-02)**:
> `bing.com/search` (web) devolvió un **challenge/captcha** ("Resuelve el desafío
> siguiente para continuar") de forma consistente para esta query — incluso en
> una sesión de Chrome autenticada del owner. **Nunca se intenta resolver ese
> challenge** (regla dura, ver Reglas al final). `bing.com/images/search` con la
> MISMA query NO fue challengeada (mismo endpoint que ya usa `sc_plan.py` a
> escala) — cada card de resultado trae `purl` (page URL) en su atributo `m`,
> que es la página `/ediciones/` real. Si en tu corrida `bing.com/images/search`
> también challengea, no insistas: reportá el bloqueo y terminá la corrida (ver
> Step 0).

Extraer con `javascript_tool` los `purl` de `whakoom.com/ediciones/<id>/<slug>`:

```javascript
const html = document.documentElement.innerHTML;
const re = /purl&quot;:&quot;(https?:\/\/(?:[a-z]+\.)?whakoom\.com\/ediciones\/\d+\/[a-zA-Z0-9_-]+)&quot;/g;
const found = [];
let m;
while ((m = re.exec(html))) { found.push(m[1]); }
JSON.stringify([...new Set(found)])
```

> **Filtro de relevancia OBLIGATORIO antes de abrir candidatas**: a diferencia
> de Bing web, Bing Imágenes **no** parece honrar estrictamente la frase exacta
> entre comillas — puede devolver ediciones de Whakoom sin relación alguna con
> la serie (verificado en vivo: para "Bloom Into You" trajo también "Weathering
> With You", "Savage Dragon", "One Piece Film Red"...). Antes de navegar a
> CUALQUIER candidata, quedate sólo con las cuyo slug de URL contenga al menos
> un token de `series_display`/`title` (normalizado, sin acentos, longitud >= 4
> caracteres — p.ej. "bloom"/"into" de "Bloom Into You"). Tomá como mucho **3**
> tras ese filtro, en el orden que las devolvió Bing (más relevante primero,
> según su propio ranking). Si el filtro deja 0 candidatas → 0 candidatas para
> este target, registrar intento (Step 5) y seguir con el siguiente. **Nunca**
> ampliar la búsqueda quitando `site:` ni navegar a `/comics/`/`/todos` para
> "encontrarla igual" — si Bing no la indexa reconociblemente, no hay vía
> pública para este target. (`we_resolve.py` igual rechazaría una candidata no
> relacionada por editorial/idioma/total de tomos — este filtro sólo evita
> gastar navegaciones en algo obviamente no relacionado.)

**Ritmo**: delay 2-3s con jitter entre la navegación a Bing y la siguiente acción
(igual disciplina que `/watch-search-covers`).

---

## Step 3 — Abrir cada edición candidata y extraer JSON compacto

Para cada URL candidata (máximo 3; cortar apenas una pase la validación del Step 4):

```
navigate → edition_url
wait 2-3s (rate limit conservador — Cloudflare)
```

**Si la navegación devuelve un challenge/captcha de Cloudflare** (título/texto tipo
"Checking your browser", "cf-chl", formulario "I'm not a robot"): **no lo resuelvas**.
Abandoná ESTE target (0 candidatas), esperá al menos 60s antes de la próxima
navegación a whakoom.com, y si vuelve a pasar en el siguiente target, cortá el resto
de la corrida y reportá al owner que Whakoom está challengeando la sesión.

Extraer **SOLO el JSON compacto** con `javascript_tool` — nunca el DOM completo.
**Ojo con el `return`**: el REPL de `javascript_tool` devuelve el resultado de la
ÚLTIMA expresión; una IIFE `(() => { ... })()` con cuerpo de bloque (`{ }`)
**necesita `return` explícito** — sin él el resultado es `undefined` (error real
del piloto 2026-09-02, primer intento).

> **Whakoom tiene DOS templates de página de edición** (hallazgo del piloto real,
> 2026-09-02) — el script de abajo cubre ambos:
> - **"cómics"** (manga con tomos numerados, la mayoría de items): header con
>   `p.publisher`/`p.edition-type`/`p.edition-issues` ("N cómics"), idioma en
>   `ul.info-summary .value.flag` + `.title` adyacente, tomos en
>   `li[id^='comic'] a[href^='/comics/']`, hermanas en `ul.v2-edition-list a.title`.
> - **"libro/artbook"** (oneshots sin tomos numerados — box sets, artbooks,
>   ediciones especiales de un solo volumen): NO tiene `p.publisher`; el idioma+
>   editorial vienen concatenados bajo "Información adicional" como
>   `"Español (España) · Planeta Cómic"`, y la portada única es el
>   `meta[property="og:image"]` (ya en `/large/`, no hace falta upgrade).
>
> **Idioma en el idioma de la UI, no siempre en inglés**: `www.whakoom.com` (sin
> subdominio, el que usa este skill) muestra el idioma en **ESPAÑOL**
> ("Español (España)"), no en inglés ("Spanish (Spain)") — a diferencia de lo
> que sugería el reconocimiento inicial (que aparentemente vio otra sesión/
> locale). `we_resolve.is_spanish_spain()` ya cubre ambas formas — no asumas
> un idioma de UI fijo si cambiás la extracción.

```javascript
(() => {
  const bodyText = () => document.body.innerText;
  const h1 = document.querySelector('h1');
  const title = h1 ? h1.innerText.trim() : '';
  let publisher = '', formato = '', total_tomos = null, language = '';

  // `ongoing` (tanda 3, endurecimiento #1): best-effort, SIN selector CSS
  // verificado en vivo todavía — busca el texto "Ongoing"/"En curso" cerca del
  // contador de la edición. Si un piloto real confirma un selector estable
  // (p.ej. un badge de estado junto a p.edition-issues), reemplazar este
  // regex por ese selector y actualizar whakoom.md § 6. Falso negativo (no
  // detecta "Ongoing" real) es SEGURO — sólo pierde la relajación `>=` de esa
  // edición particular; falso positivo es más riesgoso, por eso el patrón es
  // angosto (sólo dentro de header/info-summary, no todo bodyText()).
  let ongoing = false;
  const headerBlock = document.querySelector('p.edition-issues, ul.info-summary');
  if (headerBlock && /\b(Ongoing|En curso)\b/i.test(headerBlock.parentElement ? headerBlock.parentElement.innerText : headerBlock.innerText)) {
    ongoing = true;
  }

  const pubEl = document.querySelector('p.publisher');
  if (pubEl) {
    // Template "cómics".
    publisher = pubEl.innerText.trim();
    const etEl = document.querySelector('p.edition-type');
    formato = etEl ? etEl.innerText.trim() : '';
    const issuesEl = document.querySelector('p.edition-issues');   // "113 cómics"
    if (issuesEl) {
      const m = issuesEl.innerText.match(/(\d+)/);
      total_tomos = m ? parseInt(m[1], 10) : null;
    }
    const flagLi = document.querySelector('ul.info-summary .value.flag');
    if (flagLi) {
      const t = flagLi.parentElement.querySelector('.title');
      language = t ? t.innerText.trim() : '';
    }
  } else {
    // Template "libro/artbook" — "Español (España) · Planeta Cómic" en una línea.
    // OJO: el separador "·" en esta línea a veces trae NBSP (U+00A0), no un
    // espacio normal, alrededor — regex con espacio literal falla en
    // silencio en esos casos (bug real del piloto 2026-09-02, "Radiant -
    // Portadas alternativas"). `\s` en JS SÍ matchea NBSP — usarlo siempre
    // acá en vez de un espacio literal " ".
    const m = bodyText().match(/([A-Za-zÀ-ÿ]+\s?\([^)]+\))\s*·\s*([^\n]+)/);
    if (m) { language = m[1].trim(); publisher = m[2].trim(); }
    const fm = bodyText().match(/\n(Rústica|Cartoné|Tapa dura|Grapa|Brochado)[^\n]{0,40}\n/);
    formato = fm ? fm[0].trim() : '';
    total_tomos = 1;   // libro/artbook = SIEMPRE un solo "tomo" (oneshot)
  }

  // Tomos listados (máx ~11 sin login, template "cómics").
  const volumes = Array.from(document.querySelectorAll("li[id^='comic'] a[href^='/comics/']")).map(a => {
    const issueEl = a.querySelector('.issue-number');
    const img = a.querySelector('img');
    return { n: issueEl ? issueEl.innerText.replace(/^#/, '').trim() : '',
             img_url: img ? (img.getAttribute('src') || '') : '' };
  });

  // Sin p.edition-issues pero SÍ hay tomos listados y NO hay "Ver todos" →
  // el total real es exactamente volumes.length (no hace falta el contador).
  if (total_tomos === null && volumes.length > 0 && !/Ver todos/.test(bodyText())) {
    total_tomos = volumes.length;
  }

  // Template "libro/artbook": no hay lista de tomos — la portada única es
  // og:image (ya en /large/). Sintetizamos UN volumen sin número (oneshot) para
  // que we_resolve.py pueda resolverlo igual que un tomo #1 numerado.
  if (volumes.length === 0 && !pubEl) {
    const og = document.querySelector('meta[property="og:image"]');
    if (og && og.getAttribute('content')) {
      volumes.push({ n: '', img_url: og.getAttribute('content') });
    }
  }

  // Ediciones hermanas ("Otras ediciones"): ul.v2-edition-list > li > a.title,
  // con spans .info ("Español (España)Grapa" — idioma+formato SIN separador,
  // partido por el primer "(...)"), .publisher y .stats ("Números:17").
  // `edition_url` (tanda 3, endurecimiento #4): el href de la propia hermana —
  // sin esto, we_resolve.py no puede sugerir "sibling_urls" cuando NINGUNA
  // candidata resuelve por idioma (hallazgo tanda 2: 33 language_mismatch,
  // Bing suele indexar mejor la edición LatAm que la de España para la MISMA
  // obra+editorial; el hub LatAm normalmente lista la hermana ES acá mismo).
  const other_editions = Array.from(document.querySelectorAll('ul.v2-edition-list a.title')).map(a => {
    const infoText = (a.querySelector('.info') || {}).textContent || '';
    const statsText = (a.querySelector('.stats') || {}).textContent || '';
    const langM = infoText.match(/^(.*?\([^)]+\))/);
    const total_m = statsText.match(/(\d+)/);
    const href = a.getAttribute('href') || '';
    return {
      language: langM ? langM[1].trim() : '',
      formato: langM ? infoText.slice(langM[0].length).trim() : infoText.trim(),
      publisher: ((a.querySelector('.publisher') || {}).textContent || '').trim(),
      total_tomos: total_m ? parseInt(total_m[1], 10) : null,
      edition_url: href ? new URL(href, location.href).href : '',
    };
  });

  return JSON.stringify({ url: location.href, title, publisher, language, formato,
                          total_tomos, ongoing, other_editions, volumes });
})()
```

> **Limitación conocida — ambigüedad de TIPO de producto en oneshots**
> (hallazgo del piloto real, 2026-09-02): para un item sin volumen (box set,
> artbook), `we_resolve.py` sólo exige editorial + idioma + total de tomos — no
> distingue "un box set de N tomos" de "un artbook/libro" si ambos casan por
> casualidad en editorial+idioma+`total_tomos == 1`. Caso real: "Bloom Into You
> Box Set" (item ES, 1 fila en el corpus → `listado.total_tomos = 1`) casi
> resuelve contra "Astrolabio - Bloom Into You Illustration Works" (un artbook
> de ilustraciones, NO el box set) — mismo publisher, mismo idioma, y el
> template "libro" también cuenta como 1 tomo. La mitigación estructural ya
> existe (nunca auto-aplica; `confidence: "low"` siempre; el owner ve la
> portada propuesta — un artbook se distingue a simple vista de un box set) pero
> NO hay guard determinista adicional — queda como mejora pendiente (ver Reglas
> y el reporte de piloto en `docs/reference/images.md`).

Guardar el resultado como una entrada de `candidates[]` (con `edition_id` extraído
del path de la URL y `edition_url` = la URL abierta) y seguir con la próxima URL
candidata **hasta juntar todas las que abriste** (no hace falta parar antes — abrís
como máximo 3 por target).

---

## Step 4 — Resolver la edición (determinista, `we_resolve.py`)

```python
import json, subprocess, uuid
from pathlib import Path

we_input = {
    'item': item,
    'listado': listado,                 # {coleccion_id, total_tomos, formato, paginas,
                                          #  editorial, ongoing, source} del plan (tanda 3)
    'candidates': edition_candidates,    # lo que juntó el Step 3 (1-3 ediciones)
}
tmp_in = Path(f'.tmp_we_input_{uuid.uuid4().hex[:8]}.json')
tmp_in.write_text(json.dumps(we_input, ensure_ascii=False), encoding='utf-8')
r = subprocess.run(['.venv/bin/python', 'scripts/retrofit/we_resolve.py', str(tmp_in)],
                   capture_output=True, text=True)
tmp_in.unlink(missing_ok=True)
result = json.loads(r.stdout) if r.returncode == 0 else {'resolved': False, 'reason': 'error', 'candidate_urls': [], 'sibling_urls': []}
```

`we_resolve.py` decide de forma 100% determinista (no reimplementar este criterio
acá — si necesita cambiar, se cambia el script y sus tests en
`tests/test_we_resolve.py`):

1. **Idioma** debe ser `"Spanish (Spain)"` (no LatAm, no otro país).
2. **Editorial** coincide con `item.publisher` por **conjunto de tokens**
   normalizados (sin acentos, sin stopwords editoriales), no por substring —
   tolera un imprint co-editado con el orden de tokens invertido (tanda 3,
   endurecimiento #3, cierra `task_07e139d6`).
3. **Total de tomos**: si `listado.total_tomos` es conocido (REMOTO si el
   Step 1b corrió, si no LOCAL — conteo del corpus por `edition_key`), la
   edición candidata debe declarar el MISMO número (±0) — **salvo** que
   `listado.ongoing` o la propia `cand.ongoing` sean `true` (serie en curso
   en cualquiera de los dos lados), en cuyo caso se acepta
   `cand.total_tomos >= listado.total_tomos` (tanda 3, endurecimiento #1 —
   cubre tanto "listadomanga no editó aún lo que whakoom ya cuenta" como el
   contador de whakoom desactualizado, whakoom.md § 6). Si `listado.total_tomos`
   es desconocido, se exige que ninguna edición hermana (`other_editions`) sea
   también Español-España del mismo publisher — si la hay, no se puede
   desambiguar.
4. **Guard de reedición** (tanda 3, endurecimiento #2): si la edición es
   oneshot (`total_tomos == 1`) o tiene una hermana ES del mismo publisher con
   el MISMO `total_tomos`, el formato+páginas embebidos en el SLUG de whakoom
   (`"<título>-rustica_240_pp"`) deben ser consistentes con
   `listado.formato`/`listado.paginas` (remoto) — sin datos suficientes para
   comparar y con esa hermana presente, no resuelve
   (`ambiguous_sibling_same_publisher`; caso real que motivó esto:
   `sensor-ecc-deluxe-es`, único error de la curación tanda 1).
5. Si **más de una** de las ediciones abiertas pasa 1-4 → **ambiguo, no resuelve**.
6. Si una sola pasa, ubica el tomo pedido (`item.volume`) en `volumes[]` de esa
   edición (o el único tomo, si es oneshot sin volumen).

`we_resolve.py` **siempre** apendea una fila a `data/whakoom_edition_map.jsonl`
(resuelto o no, con el motivo) — así corridas futuras de `we_plan.py` no repiten
la misma búsqueda Bing para la misma serie+editorial.

Si `result['resolved']` es `False`: no hay nada que validar todavía.

**`sibling_urls` (tanda 3, endurecimiento #4)**: si `result['reason'] ==
'language_mismatch'`, `result['sibling_urls']` puede traer URLs de ediciones
ES-España del mismo publisher que alguna candidata abierta listaba en "Otras
ediciones" (hallazgo tanda 2: 33 `language_mismatch`, típicamente Bing indexó
mejor la hermana LatAm). Si `sibling_urls` no está vacío: abrilas como
candidatas nuevas del **Step 3** (misma extracción, mismo rate limit 2-3s) y
volvé a llamar `we_resolve.py` con `edition_candidates` = las originales +
estas — **UNA sola pasada adicional** por target (no encadenar sibling_urls de
sibling_urls, para no arriesgar un loop). Si vuelve a fallar, registrar el
intento (Step 6) con el motivo final y seguir con el próximo target. Si
`sibling_urls` está vacío o `reason` no es `language_mismatch`, registrar el
intento (Step 6) con `matches: 0` y motivo `result['reason']`, y seguir con el
próximo target.

---

## Step 5 — Validar la candidata (permanente, `sc_validate.py` — NO reimplementar)

Si `result['resolved']` es `True`, `result['candidate_urls']` trae **una** URL
(la imagen del tomo en el CDN de Whakoom, tamaño `/small/` o `/thumb/` — el
upgrade a `/large/` ya lo hace `sc_validate.py`, mismo mecanismo que
`/watch-search-covers`). Pasarla EXACTAMENTE por el mismo validador permanente:

```python
tmp_val = Path(f'.tmp_sc_input_{uuid.uuid4().hex[:8]}.json')
tmp_val.write_text(json.dumps({
    'item': item,
    'candidate_urls': result['candidate_urls'],
    'curr_px': target['pixels'],
    'ref_image_local': target['image_ref_local'],
    'reference_sha256': target['reference_sha256'],
}, ensure_ascii=False), encoding='utf-8')
r = subprocess.run(['.venv/bin/python', 'scripts/retrofit/sc_validate.py', str(tmp_val)],
                   capture_output=True, text=True)
tmp_val.unlink(missing_ok=True)
out = json.loads(r.stdout) if r.returncode == 0 else {'validated': []}
validated = out.get('validated', [])
if out.get('drift'):
    print(f"  DRIFT ({out['drift']}): referencia cambió desde el plan — 0 candidatas.")
    validated = []
```

Con `target['reference_kind'] != 'real'` (item sin imagen), `sc_validate.py` corre
el **gate débil sin-referencia** (aspect ratio + `candidate_metadata_conflict` +
`_is_soft_image`, sin `_same_cover`) y la candidata queda `verified: false` — se
acepta igual pero marcada para revisión más estricta del owner, igual que
`--include-no-image` en `/watch-search-covers`.

Con referencia real, `sc_validate.py` exige `_same_cover` (AND-gate de identidad)
— si la edición resuelta tiene arte distinto al de la portada capada actual
(logo/crop/color distintos, gotcha #173), la candidata se rechaza acá con 0
matches. Es correcto: mejor 0 candidatas que una portada de otra impresión.

---

## Step 6 — Registrar el intento (siempre, con o sin matches)

```python
import datetime

attempts_path = Path('data/cover_search_attempts.jsonl')
entry = {
    'slug': slug,
    'action': 'replace_cover',
    'target': '',
    'attempted_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00'),
    'matches': len(validated) if result.get('resolved') else 0,
    'engines': ['whakoom_edicion'],
}
if not result.get('resolved'):
    entry['reason'] = result.get('reason', '')
with attempts_path.open('a', encoding='utf-8') as f:
    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
```

---

## Step 7 — Encolar (permanente, `sc_flush.py` — NO reimplementar)

Si `validated` no está vacío, cada candidata debe llevar `via: "whakoom_edicion"`
(campo que usa `we_plan.py` para reconocer targets ya adjudicados por ESTE skill,
igual que `match_dist` lo es para `/watch-search-covers`):

```python
for c in validated:
    c['via'] = 'whakoom_edicion'

if validated:
    tmp_fl = Path(f'.tmp_sc_flush_{uuid.uuid4().hex[:8]}.json')
    tmp_fl.write_text(json.dumps({
        'slug': slug, 'item': item, 'candidates': validated,
        'candidate_action': 'replace_cover', 'candidate_target': '',
        'old_local': target['image_ref_local'], 'old_url': target['image_ref_url'],
        'curr_px': target['pixels'],
    }, ensure_ascii=False), encoding='utf-8')
    r = subprocess.run(['.venv/bin/python', 'scripts/retrofit/sc_flush.py', str(tmp_fl)],
                       capture_output=True, text=True)
    tmp_fl.unlink(missing_ok=True)
    print(r.stdout.strip() or r.stderr[:200])
```

`sc_flush.py` valida estructuralmente cada candidata (rechaza con exit 1 si falta
`new_image`/`new_url` o algún campo de proveniencia — la misma guarda que protege
a `/watch-search-covers`), aplica el guard de URL compartida entre slugs
(gotcha #173/#174 — relevante acá también: dos tomos de la misma serie pueden
recibir la miniatura equivocada de Whakoom) y escribe bajo el mismo lock
cross-proceso que el resto del pipeline de imágenes.

---

## Step 8 — Limpiar y reportar

```python
for p in ['.tmp_we_plan.json']:
    Path(p).unlink(missing_ok=True)
for pattern in ['.tmp_we_input_*.json', '.tmp_sc_input_*.json', '.tmp_sc_flush_*.json']:
    for f in Path('.').glob(pattern):
        f.unlink(missing_ok=True)
```

Reportar: targets procesados, ediciones resueltas inequívocas / ambiguas / no
encontradas (desglosado por motivo — `we_resolve.py` los deja en
`data/whakoom_edition_map.jsonl`), candidatas encoladas (`verified: true/false`),
bloqueos de Cloudflare si los hubo, y el link a
`http://localhost:8000/web/cover-preview.html` para revisión manual.

---

## Reglas (no negociables)

1. **NUNCA** escribir ni modificar `data/items.jsonl`.
2. **NUNCA** navegar a `/comics/<hash>/…` ni a `<edición>/todos` (login + robots.txt
   `Disallow: /comics/`) — el alcance de este skill es SOLO tomos `<= 11` o
   sin volumen, ya filtrado por `we_plan.py`.
3. **NUNCA** intentar resolver ni rodear un captcha/challenge de Cloudflare — si
   aparece, abandonar el target y esperar antes de la próxima navegación a
   whakoom.com; dos challenges seguidos cortan la corrida entera.
4. **NUNCA** entrar con credenciales ni loguearse en Whakoom.
5. Todas las candidatas: `confidence: "low"`, `status: "pending"`, `via:
   "whakoom_edicion"`.
6. Una edición sólo se resuelve si pasa **exactamente una** de las candidatas
   abiertas por el filtro editorial+idioma+total de tomos+guard de reedición de
   `we_resolve.py` — si hay ambigüedad entre hermanas (regular/kanzenban/deluxe),
   no se resuelve. Seguir un `sibling_urls` (endurecimiento #4) cuenta como parte
   de la MISMA resolución del target, no como un target nuevo — máximo una pasada
   adicional del Step 3 por target.
7. La validación de identidad/calidad de imagen es 100% `sc_validate.py` — no
   reimplementar `_same_cover`/`_is_soft_image`/`candidate_metadata_conflict` acá.
8. `we_resolve.py` **siempre** apendea a `data/whakoom_edition_map.jsonl` (caché
   append-only, resuelto o no) — no lo borres ni lo trunques entre corridas.
9. Rate limit conservador: **2-3s** entre navegaciones a whakoom.com (Cloudflare);
   sin ráfagas.
10. Un `(slug, "replace_cover", "")` con candidata `via == "whakoom_edicion"` ya
    en `data/cover_preview.json` (cualquier estado) se salta automáticamente —
    `we_plan.py` no lo vuelve a plantear.
11. Borrar los `.tmp_we_*`/`.tmp_sc_*` al finalizar. `sc_validate.py` y
    `sc_flush.py` son PERMANENTES — nunca borrarlos ni regenerar su lógica inline.
