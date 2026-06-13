---
name: watch-search-covers
description: Busca imágenes en alta resolución para items con portada o foto de galería de baja calidad o ausente usando Chrome. Combina Yandex búsqueda-por-foto (reverse image, usando la imagen actual como consulta) + queries de texto con contexto en Google Imágenes (udm=2). "Baja calidad" usa el mismo umbral que el panel de calidad de datos (90 000 px). Por cada imagen objetivo itera fuentes hasta juntar matches; valida cada candidata con fetch_better_covers._same_cover() para quedarse SOLO con la MISMA imagen en mejor resolución. Escribe a data/cover_preview.json para aprobación manual. NUNCA modifica items.jsonl. Por defecto solo procesa portadas (img_idx 0). Args opcionales: --limit N, --slug SLUG, --include-no-image, --include-gallery, --gallery-only, --retry-failed, --query-extra "texto".
argument-hint: "[--limit N] [--slug SLUG] [--include-no-image] [--include-gallery] [--gallery-only] [--retry-failed] [--query-extra \"texto\"]"
---

# search-covers — Búsqueda de portadas hi-res con Chrome

Usa Chrome para buscar portadas en alta resolución para items con **imagen de baja calidad**
(según el mismo criterio del panel de calidad de datos) o sin imagen. Para cada item combina
dos motores: (1) **Yandex búsqueda por foto** (reverse image, usando la imagen actual como
consulta) y (2) **varias queries de texto con contexto** en **Google Imágenes** (`udm=2`).
Extrae URLs candidatas del HTML y las valida con Python exigiendo que sean **la misma portada
en mejor resolución**. Las aprobadas se escriben a `data/cover_preview.json` para revisión
manual en `http://localhost:8000/web/cover-preview.html`.

> **Cómo se extraen las URLs de Google (importante)**: en la vista nueva de Google Imágenes
> (`&udm=2`) los `img.src` son thumbnails **base64** y el patrón viejo `"ou":"..."` da vacío
> (por eso versiones anteriores de este skill creían que Google "no funcionaba" y usaban Bing).
> PERO las URLs full-res de cada resultado SÍ están en el **HTML crudo** (`innerHTML`) y se
> extraen con un regex de URLs de imagen externas (ver Step 3b). Eso **no** dispara el bloqueo
> del MCP porque el regex corta antes de cualquier `?` (sin query strings). Verificado en vivo
> 2026-06-06: ~70-75 candidatas full-res por query, consistente.
>
> **Motores de búsqueda — qué funciona y qué no (todo probado en vivo 2026-06-06)**:
> - **Yandex reverse image (USADO, primaria)**: `https://yandex.com/images/search?rpt=imageview&url=<old_url>`.
>   Sin captcha, accesible, y devuelve **portadas del tomo/edición correctos** (mucho mejor que
>   Lens). Se extrae con el mismo regex sobre `innerHTML`. Es la mejor "búsqueda por foto" gratis.
> - **Google texto `udm=2` (USADO, complemento)**: las queries con contexto pegan la edición
>   exacta cuando existe (Frieren 14 → dist 7, que Yandex no logró). Por eso van juntas.
> - **Google Lens (NO usado)**: accesible (regex sobre `innerHTML`, NO leas `location.href` que
>   dispara `[BLOCKED: Cookie/query string data]`), pero con un thumbnail de 150×150 cae en
>   matching "a nivel franquicia" → fan art, wikis, merch, Mercari, tomos equivocados. 0 matches.
> - **Bing Visual Search (NO usable)**: redirige a búsqueda web de entidad y se bloquea.
> - **Serper Lens (de pago)**: la reversa real de mejor calidad vive en producción
>   (`fetch_better_covers._search_serper_lens`), requiere `SERPER_API_KEY` (hoy comentada en `.env`).
>
> **Ojo (limitación de fondo)**: el catálogo son **ediciones especiales**, y tanto el texto como
> la reversa tienden a devolver la edición **regular/hermana**, cuyo arte difiere → `_same_cover`
> la rechaza (correctamente). Por eso para varios items no habrá candidata: el hi-res del scan
> especial exacto simplemente no está indexado. Es esperado, no un bug.
>
> **Fallback a Bing texto**: si Google muestra consent wall (muy pocas URLs externas, `< 3` en
> varias variantes de texto seguidas), cambiá la `url` a
> `https://www.bing.com/images/search?q=<query>&first=1` y extraé con `a.iusc[m].murl`
> (filtrando URLs con `?`). El resto del pipeline (validación, flush) es igual.

**"Baja calidad"** = imagen con menos de **90 000 px** (ancho × alto). Es el mismo umbral
que usa `scripts/audit/data_quality.py` para marcar imágenes como "pixelada" en el panel.
No es un parámetro configurable — si el panel de calidad lo marca como problema, este skill
lo intenta resolver.

**Referencia degenerada (`< MIN_REF_PX`, 2 500 px)**: una imagen actual por debajo de ese
mínimo (típicamente un GIF de 1×1 px = placeholder "imagen no disponible" de Amazon) NO sirve
como referencia para `_same_cover` — rechazaría toda candidata (0 matches garantizados). Esos
targets se tratan como **"sin imagen"**: se saltan salvo `--include-no-image`, y ahí van
`verified:false` y sin variante reverse. Sin este guard los ~46 placeholders de 1px copaban el
`--limit` en cada corrida (ordenan primero por px) y nunca se llegaba a las portadas reales de
baja resolución (fix estructural 2026-06-12).

**La regla de oro de relevancia** (lo que arregla el problema histórico de "me manda otros
volúmenes / ediciones / cosas no relacionadas"): una candidata SOLO se acepta si pasa DOS
verificaciones: (1) `fetch_better_covers._same_cover(actual, candidata, MAX_HASH_DIST)` — el
AND-gate endurecido del audit 2026-06-10: **aspect ratio ±25% ∧ aHash ≤6 ∧ dHash ≤8 ∧
pHash ≤8 ∧ NCC ≥0.90 + gate de entropía + denylist de placeholders** (capa incomputable =
rechazo, default-deny); y (2) `fetch_better_covers.candidate_metadata_conflict(item, url,
page_title)` — si la URL/título de la candidata declara OTRO volumen u OTRO ISBN que el item,
hard reject. Otro volumen / otra edición / arte distinto se descarta. Está bien que una
candidata no sea pixel-idéntica (puede ser un escaneo mejor con el mismo arte), pero tiene
que ser **visiblemente la misma portada**. Precisión > recall: mejor 0 candidatas que una
no relacionada.

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
| `--limit N` | `20` | Máximo de targets (imágenes) a procesar en esta sesión. |
| `--slug SLUG` | — | Procesa solo el item con ese slug exacto. |
| `--gallery-only` | off | Salta las portadas (img_idx 0) y procesa solo imágenes de galería (img_idx ≥ 1). Útil para buscar mejoras de galería sin mezclar con portadas ya encoladas. |
| `--include-gallery` | off | Procesa tanto portadas como imágenes de galería (img_idx 0 y ≥ 1). Sin este flag ni `--gallery-only`, solo se procesan portadas. |
| `--include-no-image` | off | Por defecto se saltan items sin imagen (no hay portada actual con qué verificar `_same_cover`). Con este flag se incluyen, pero sus candidatas quedan **sin verificar** (`verified: false`). |
| `--retry-failed` | off | Por defecto se omiten targets cuyo último intento (en `data/cover_search_attempts.jsonl`) tuvo 0 matches y fue hace menos de 30 días. Con este flag se procesan igual. |
| `--query-extra "texto"` | — | Texto adicional al final de cada variante de query en Google. |

> **Por defecto solo se procesan portadas** (`img_idx == 0`). Las fotos de galería interior
> (extras/bonus) son irrecuperables en la mayoría de casos — no existe copia externa de esa
> foto específica. En una corrida real, 12 de 25 targets eran fotos de galería con 0 matches.
> Usar `--include-gallery` para procesar ambas, o `--gallery-only` para exclusivamente galería.

---

## Step 0 — Verificar que Chrome está disponible

Llamar `mcp__Claude_in_Chrome__list_connected_browsers`. Si no hay browsers conectados,
abortar con:

```
ERROR: Chrome no disponible.

Para usar este skill:
1. Instala la extensión "Claude for Chrome" desde el Chrome Web Store.
2. Abre Chrome y asegúrate de que la extensión esté activa y conectada.
3. Vuelve a invocar /watch-search-covers
```

Después, obtené un tab ID con `mcp__Claude_in_Chrome__tabs_context_mcp` (`createIfEmpty: true`).

---

## Step 1 — Identificar items y construir el PLAN de queries

Parsear los parámetros, filtrar `items.jsonl`, y para cada target generar **una lista ordenada
de variantes de query** (la iteración del Step 3). Las variantes usan los helpers de producción
(`fetch_better_covers`) para meter contexto de serie + volumen + tipo de edición + editorial +
el término "portada" en el idioma correcto.

```python
import json, sys, urllib.parse
from pathlib import Path
sys.path.insert(0, 'scripts/retrofit')
import fetch_better_covers as fbc

# Umbral de "baja calidad": mismo valor que data_quality.py --px (default 90 000).
LOW_QUALITY_PX = 90_000

# Umbral de "referencia usable": por debajo de esto la imagen actual es un
# placeholder roto (típico: GIF de 1×1 px de Amazon "imagen no disponible") y NO
# sirve como referencia para _same_cover — el gate de aspect ratio y los hashes
# rechazarían toda candidata (0 matches garantizados). Estos targets se tratan
# como "sin imagen": se saltan salvo --include-no-image (y ahí van verified:false,
# sin variante reverse, porque no hay con qué hacer búsqueda por foto). Sin este
# guard los ~46 placeholders de 1px copan el --limit en cada corrida y nunca se
# llega a las portadas reales de baja resolución (causa estructural, 2026-06-12).
MIN_REF_PX = 2_500

# Ajustar según los parámetros recibidos al invocar el skill
LIMIT            = 20        # --limit N
SLUG_FILTER      = None      # --slug SLUG  (o None)
INCLUDE_NO_IMAGE = False     # --include-no-image
QUERY_EXTRA      = ""        # --query-extra "texto"  (o "")

SKIP_SIGNALS    = {'variant_cover', 'retailer_exclusive'}
GALLERY_ONLY    = False     # --gallery-only
INCLUDE_GALLERY = False     # --include-gallery (procesa portadas Y galería)
RETRY_FAILED    = False     # --retry-failed (ignorar la exclusión de 30 días)

# Términos de edición que NO cubre fbc._EDITION_HINT, por idioma.
EXTRA_EDITION_HINT = {
    'special': {'Español': 'edición especial', 'Inglés': 'special edition',
                'Italiano': 'edizione speciale', 'Francés': 'édition spéciale',
                'Portugués': 'edição especial', 'default': 'special edition'},
}

items      = [json.loads(l) for l in open('data/items.jsonl') if l.strip()]
images_dir = Path('data/images')

preview_path = Path('data/cover_preview.json')
# Skip key = (slug, action, target_url) — así cubrimos portada y cada foto de galería por separado
already_in_preview = set()
if preview_path.exists():
    try:
        for e in json.loads(preview_path.read_text(encoding='utf-8')):
            for c in e.get('candidates', []):
                if c.get('status') == 'pending':
                    already_in_preview.add((
                        e.get('slug', ''),
                        c.get('action', 'replace_cover'),
                        c.get('target', ''),
                    ))
    except (ValueError, OSError):
        pass

# Memoria de intentos: excluir targets con 0 matches en los últimos 30 días.
# Razón: sin esto cada corrida re-quema presupuesto en los mismos targets imposibles
# (ediciones especiales no indexadas en ningún motor). --retry-failed lo ignora.
import datetime
attempts_path = Path('data/cover_search_attempts.jsonl')
recently_failed = set()   # skip_key = (slug, action, target)
if not RETRY_FAILED and attempts_path.exists():
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    last_attempt: dict = {}   # skip_key → dict más reciente
    try:
        for line in attempts_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line:
                continue
            a = json.loads(line)
            key = (a.get('slug',''), a.get('action',''), a.get('target',''))
            prev = last_attempt.get(key)
            if prev is None or a.get('attempted_at','') > prev.get('attempted_at',''):
                last_attempt[key] = a
    except (ValueError, OSError):
        pass
    for key, a in last_attempt.items():
        if a.get('matches', 1) == 0:
            try:
                ts = datetime.datetime.fromisoformat(a['attempted_at'].replace('Z', '+00:00'))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=datetime.timezone.utc)
                if ts >= cutoff:
                    recently_failed.add(key)
            except (KeyError, ValueError):
                pass

def get_pixels_local(local_fname):
    if not local_fname:
        return 0
    p = images_dir / local_fname
    if not p.exists():
        return 0
    try:
        from PIL import Image
        with Image.open(p) as img:
            return img.width * img.height
    except Exception:
        return 0

def edition_term(item):
    """Tipo de edición en el idioma del item (kanzenban, boxset, edición especial...)."""
    lang = item.get('language', '')
    slug = fbc._edition_slug(item.get('edition_key', ''))
    if not slug:
        return ''
    hint = fbc._EDITION_HINT.get(slug, {})
    if hint:
        return hint.get(lang, hint.get('default', ''))
    extra = EXTRA_EDITION_HINT.get(slug, {})
    return extra.get(lang, extra.get('default', ''))

def build_variants(item, ref_url=None):
    """
    Lista ORDENADA de (label, query) — de la más específica a la más amplia.
    El loop del Step 3 las prueba en orden e itera hasta juntar suficientes matches.
    ref_url: URL de la imagen de referencia para Yandex reverse (la portada =
    images[0].url, o la foto de galería que se esté procesando).
    """
    title      = (item.get('title') or '').strip()
    title_orig = (item.get('title_original') or '').strip()
    series     = (item.get('series_display') or '').strip()
    volume     = str(item.get('volume') or '').strip()
    lang       = item.get('language', '')
    cover_term = fbc._COVER_TERM.get(lang, 'cover')
    pub_short  = fbc._simplify_publisher(item.get('publisher', ''))
    ed_term    = edition_term(item)

    def clean(q):
        q = ' '.join(q.split())
        return f"{q} {QUERY_EXTRA}".strip() if QUERY_EXTRA else q

    variants = []
    # 1. La más específica: serie + volumen + edición + editorial + portada
    if series:
        v1 = f"{series} {volume} {ed_term} {pub_short} {cover_term}"
        variants.append(('serie+vol+ed', clean(v1)))
    # 2. title_original (lo que indexan los retailers locales) + editorial + portada
    if title_orig and title_orig != title:
        variants.append(('title_original', clean(f"{title_orig} {pub_short} {cover_term}")))
    # 3. title (en inglés/canónico) + editorial + portada
    if title:
        variants.append(('title', clean(f"{title} {pub_short} {cover_term}")))
    # 4. amplia: serie + volumen + edición + editorial (sin término portada)
    if series:
        variants.append(('amplia', clean(f"{series} {volume} {ed_term} {pub_short}")))
    # Dedup conservando orden (variantes de TEXTO → Google udm=2)
    seen, out = set(), []
    for label, q in variants:
        if q and q.lower() not in seen:
            seen.add(q.lower())
            out.append({'label': label, 'query': q, 'kind': 'text',
                        'url': f"https://www.google.com/search?q={urllib.parse.quote(q)}&udm=2"})

    # Variante WHAKOOM (texto, Google udm=2) — va PRIMERO para ítems en Español.
    # Evidencia: en la corrida real 2026-06-11, whakoom produjo el 100% de los matches ES
    # (8/8); yandex-reverse 0 (los thumbnails de listadomanga no están indexados por Yandex).
    # Su CDN (i1.whakoom.com/small/) tiene upgrade automático a /large/ en sc_validate.py.
    if lang == 'Español':
        wk_q = ' '.join(p for p in [series or title, volume] if p).strip()
        if wk_q:
            wk_query = f"site:whakoom.com {wk_q}"
            wk_url   = f"https://www.google.com/search?q={urllib.parse.quote(wk_query)}&udm=2"
            out.insert(0, {'label': 'whakoom', 'query': wk_query,
                           'kind': 'text', 'url': wk_url})

    # Variante REVERSE-IMAGE (Yandex) — segundo para ES, primero para otros idiomas.
    # El mejor motor de búsqueda por foto gratuito (sin captcha, devuelve portadas del
    # tomo correcto). Usa la imagen de referencia ref_url como consulta.
    # Solo si tiene URL http usable. Va detrás de whakoom para ES porque los thumbnails
    # de listadomanga no están indexados por Yandex (0 matches verificados 2026-06-11).
    # EXCEPCIÓN: si la referencia ES un thumbnail de listadomanga, la variante se OMITE
    # por completo — Yandex no tiene esas imágenes en su índice y devuelve resultados
    # genéricos no relacionados (0/14 intentos en 3 lotes reales, 2026-06-11).
    old_url = (ref_url or '').strip()
    if old_url.startswith('http') and 'static.listadomanga.com' not in old_url:
        yx = f"https://yandex.com/images/search?rpt=imageview&url={urllib.parse.quote(old_url, safe='')}"
        # Para ES: insertar después de whakoom (pos 1); para otros idiomas: al inicio (pos 0)
        yandex_pos = 1 if (lang == 'Español' and out and out[0].get('label') == 'whakoom') else 0
        out.insert(yandex_pos, {'label': 'yandex-reverse', 'query': f"[reverse] {series or title}",
                                'kind': 'reverse', 'url': yx})

    return out

targets = []
for item in items:
    if SLUG_FILTER and item.get('slug') != SLUG_FILTER:
        continue
    if item.get('approved_at'):
        continue
    if SKIP_SIGNALS & set(item.get('signal_types', [])):
        continue
    slug = item.get('slug', '')

    # Construir lista de imágenes a evaluar. La portada es images[0] (única fuente
    # de verdad). Si el item no tiene images[], igual lo procesamos con un entry
    # vacío para que la búsqueda por TEXTO corra (sin Yandex reverse, que necesita
    # una URL de referencia) — útil para items sin portada con --include-no-image.
    imgs = item.get('images') or []
    if not imgs:
        imgs = [{'url': '', 'local': '', 'kind': 'gallery'}]

    for img_idx, img in enumerate(imgs):
        local   = img.get('local', '')
        ref_url = img.get('url', '')
        px      = get_pixels_local(local)

        if img_idx == 0:
            # Portada: saltar si --gallery-only está activo
            if GALLERY_ONLY:
                continue
            if px < MIN_REF_PX:
                # Referencia ausente o placeholder roto (1×1 px): no sirve para
                # _same_cover. Se trata como "sin imagen" → skip salvo
                # --include-no-image, y en ese caso se blanquea la referencia
                # (local + ref_url) para que la candidata quede verified:false y
                # NO se construya variante reverse sobre un placeholder degenerado.
                if not INCLUDE_NO_IMAGE:
                    continue
                local   = ''
                ref_url = ''
                px      = 0
            elif px >= LOW_QUALITY_PX:
                continue
        else:
            # Galería: por defecto se salta (las fotos de galería interior son
            # irrecuperables en su mayoría — no existe copia externa). Solo entra
            # con --gallery-only o --include-gallery. Verificado: en la corrida
            # real 2026-06-11, 12/25 targets eran galería con 0 matches posibles.
            if not GALLERY_ONLY and not INCLUDE_GALLERY:
                continue
            # Galería: solo procesar si existe local usable y es baja calidad
            # (necesitamos _same_cover → skip si no hay referencia usable o es
            # un placeholder roto por debajo de MIN_REF_PX)
            if px < MIN_REF_PX or px >= LOW_QUALITY_PX:
                continue

        action     = 'replace_cover' if img_idx == 0 else 'replace_image'
        target_url = '' if img_idx == 0 else ref_url
        skip_key   = (slug, action, target_url)
        if skip_key in already_in_preview:
            continue
        if skip_key in recently_failed:
            continue

        targets.append({
            'slug'            : slug,
            'pixels'          : px,
            'img_idx'         : img_idx,
            'image_ref_local' : local,
            'image_ref_url'   : ref_url,
            'candidate_action': action,
            'candidate_target': target_url,
            'target_label'    : 'portada' if img_idx == 0 else f'galería {img_idx}',
            'variants'        : build_variants(item, ref_url=ref_url),
        })

targets.sort(key=lambda x: (x['pixels'] > 0, x['pixels']))
targets = targets[:LIMIT]

# Persistir el plan para el loop del Step 3
Path('.tmp_sc_plan.json').write_text(json.dumps(targets, ensure_ascii=False), encoding='utf-8')

# Reset del accumulator self-healing (slugs de ESTA corrida → entry completo)
Path('.tmp_sc_acc.json').write_text('{}', encoding='utf-8')

if not targets:
    print("No hay imágenes que necesiten búsqueda. Nada que hacer.")
    raise SystemExit(0)

by_slug = {it['slug']: it for it in items}
n_items = len(set(t['slug'] for t in targets))
print(f"Targets a procesar: {len(targets)} imágenes en {n_items} item(s)")
for t in targets:
    it  = by_slug.get(t['slug'], {})
    px_str = f"{t['pixels']:,} px" if t['pixels'] > 0 else "sin imagen"
    lbl    = t['target_label']
    print(f"  • {it.get('title','')[:45]}  ({it.get('publisher','')}) [{lbl}] — {px_str}  · {len(t['variants'])} queries")
```

---

## Step 2 — El validador de imágenes (permanente, NO se regenera)

La validación vive en `scripts/retrofit/sc_validate.py` — un script PERMANENTE y
testeado (`tests/test_sc_validate.py`) que delega todo el criterio de identidad en
`fetch_better_covers` (`_same_cover` AND-gate + `candidate_metadata_conflict`).
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
target           = plan[i]
slug             = target['slug']
curr_px          = target['pixels']
img_idx          = target.get('img_idx', 0)
image_ref_local  = target.get('image_ref_local', '')
candidate_action = target.get('candidate_action', 'replace_cover')
candidate_target = target.get('candidate_target', '')
target_label     = target.get('target_label', 'portada')
variants         = target['variants']

# item completo desde items.jsonl
item = None
for l in open('data/items.jsonl'):
    if not l.strip():
        continue
    o = json.loads(l)
    if o.get('slug') == slug:
        item = o; break

TARGET_MATCHES  = 3
item_candidates = []   # acumulador verificado de ESTE target (una imagen)

print(f"\n[{i+1}/{len(plan)}] {item.get('title','')} [{target_label}]")
print(f"  Imagen actual: {curr_px:,} px" if curr_px > 0 else "  Sin imagen")
```

### 3b. Por cada variante: navegar + extraer + validar (parar al juntar matches)

Repetir para cada `variant` en `variants` **hasta** que `len(item_candidates) >= TARGET_MATCHES`:

1. **Navegar + extraer en un solo `browser_batch`** (navigate a `variant['url']` +
   javascript_tool). Imprimí `variant['label']` y `variant['query']` antes.

   > **Nota MCP**: dentro de `browser_batch`, los items van con el nombre CORTO de la
   > tool (`"name": "navigate"`, `"name": "javascript_tool"`), NUNCA el nombre MCP
   > completo (`mcp__Claude_in_Chrome__...` → "unknown tool"). Y el item de
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

   **Si `variant['kind'] == 'text'` (Google udm=2)**:

   ```javascript
   // Google Imágenes (udm=2): las URLs full-res NO están en img.src (son base64) sino en el
   // HTML crudo. Regex de URLs de imagen externas (no google/gstatic). El patrón corta antes
   // de cualquier "?" → sin query strings → no dispara el bloqueo del MCP.
   // Regex: un backslash antes de s (\s) — NO doble.
   const html = document.documentElement.innerHTML;
   const ext = [...new Set((html.match(/https?:\/\/[^"\s]+?\.(?:jpg|jpeg|png|webp)/gi) || [])
     .filter(u => !u.includes('google') && !u.includes('gstatic')))];
   JSON.stringify(ext.slice(0, 25))
   ```

   > **Nota de truncado**: el output del MCP se corta si es muy largo. Si se trunca, usá solo
   > las URLs completas que llegaron (ignorá la última si quedó a medias). No reintentes por el
   > truncado — con `_same_cover` filtrando, alcanza con que la portada correcta aparezca entre
   > las que sí llegaron.
   >
   > **Consent wall de Google**: si `ext` viene casi vacío (`< 3`) en varias variantes de texto
   > seguidas, Google muestra consent wall → fallback a Bing (ver nota al inicio):
   > `https://www.bing.com/images/search?q=<query>&first=1`, extraé con `a.iusc[m].murl`
   > (filtrando URLs con `?`).

   En ambos casos: tomá la lista de URLs (`urls` para reverse, `ext` para texto). Si viene
   vacía → esa variante no dio resultados; pasá a la siguiente.

2. **Validar las URLs de esa variante** (mismo patrón que antes, vía el validador):

   ```python
   import json, subprocess, uuid
   from pathlib import Path

   urls_from_chrome = [...]   # resultado del JS de Bing para ESTA variante
   candidate_urls = [
       {'url': u, 'page_title': '', 'domain': u.split('/')[2] if u.startswith('http') else '',
        'query': variant['query']}
       for u in urls_from_chrome if u.startswith('http')
   ]

   tmp_in = Path(f'.tmp_sc_input_{uuid.uuid4().hex[:8]}.json')
   tmp_in.write_text(json.dumps({'item': item, 'candidate_urls': candidate_urls,
                                 'curr_px': curr_px,
                                 'ref_image_local': image_ref_local}, ensure_ascii=False), encoding='utf-8')
   result = subprocess.run(['.venv/bin/python', 'scripts/retrofit/sc_validate.py', str(tmp_in)],
                           capture_output=True, text=True)
   tmp_in.unlink(missing_ok=True)
   got = json.loads(result.stdout).get('validated', []) if result.returncode == 0 else []
   if result.returncode != 0:
       print(f"    ERROR validación: {result.stderr[:200]}")

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
}
with attempts_path.open('a', encoding='utf-8') as f:
    f.write(json.dumps(attempt_entry, ensure_ascii=False) + '\n')
```

### 3e. Si no hubo matches, no inventar

Si `item_candidates` quedó vacío, **no se escribe nada** para ese item en `cover_preview.json`
(es correcto: preferimos 0 candidatas a candidatas no relacionadas). Continuar con el siguiente item.

### 3f. Flush self-healing a cover_preview.json (después de cada item)

El flush es un script PERMANENTE (`scripts/retrofit/sc_flush.py`) — nunca reescribir esta
lógica inline. Una corrida anterior reconstruyó los dicts a mano y perdió el campo `new_image`,
rompiendo la cola completa; el script ahora lo rechaza con exit 1 antes de escribir nada.
Las candidatas se pasan EXACTAMENTE como las devolvió `sc_validate.py`, sin modificarlas.

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
> Para esos casos la única vía mejor es la búsqueda reversa por foto (Serper Lens, requiere key).

---

## Reglas (no negociables)

1. **NUNCA** escribir ni modificar `data/items.jsonl`
2. **NUNCA** llamar `--apply` ni `apply_preview()` — la aprobación es del owner
3. Todas las candidatas: `confidence: "low"`, `status: "pending"`
4. Solo invocar cuando el usuario lo pida explícitamente
5. Una candidata con imagen actual SOLO se acepta si pasa `_same_cover()` (AND-gate: misma
   portada) Y no tiene conflicto de metadata (`candidate_metadata_conflict()`: otro volumen /
   otro ISBN declarado en la URL/título → hard reject). Sin imagen actual
   (`--include-no-image`) queda `verified: false` para revisión más estricta.
6. Máximo 10 candidatas por item; máx 3 matches dispara el corte de iteración
7. El skill es incremental: slugs con candidatas pendientes se saltan automáticamente
8. Borrar los `.tmp_sc_*` al finalizar (son temporales). `scripts/retrofit/sc_validate.py` y `scripts/retrofit/sc_flush.py` son PERMANENTES — nunca borrarlos ni regenerar su lógica inline. `sc_flush.py` rechaza con exit 1 cualquier candidata sin `new_image` o `new_url` (guarda anti-drift).
