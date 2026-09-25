#!/usr/bin/env python3
"""Validador de candidatas de portada para el skill watch-search-covers.

Valida que cada URL candidata sea LA MISMA portada que la imagen de
referencia del item, en mejor resolución. Es la única fuente de verdad de
la validación del skill — delega TODO el criterio de identidad en
fetch_better_covers (_same_cover AND-gate + candidate_metadata_conflict),
así el skill y el pipeline de producción no pueden driftear.

Uso: sc_validate.py [input.json]
  input.json: {"item": {...}, "candidate_urls": [{"url","page_title","domain","query"}...],
               "curr_px": int, "ref_image_local": str, "reference_sha256": str (opcional)}
  stdout:     {"validated": [candidata...]} (+ "drift": "reference_changed"/"reference_missing"
               si `reference_sha256` no matchea la referencia actual — ver
               `reference_drift_reason` abajo, gotcha #178)
"""
import hashlib, re, sys, json, requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_better_covers as fbc

# ── Upgrade de URL a hi-res ────────────────────────────────────────────────────
# Patrones verificados empíricamente 2026-06-11. Orden: más específico primero.
# _same_cover valida cada descarga, así que una reescritura incorrecta no
# contamina (si la variante upgraded devuelve otra imagen, _same_cover la rechaza).

# buscalibre: reescribir fit-in/<W>x<H>/ → fit-in/1200x1200/ — NO quitar el
# segmento entero (gotcha #167, 2026-09-01). Quitarlo del todo no devuelve el
# original en máxima resolución: el CDN sirve un tamaño "base" intermedio,
# bastante menor que pedir 1200x1200 explícito. Verificado en vivo (request
# real, 2026-09-01) sobre la misma imagen:
#   fit-in/360x360/...   →  256×360   =  92 160 px  (a caballo del piso 90k
#                                         de LOW_QUALITY_PX → re-encolada
#                                         eternamente, nunca sube de calidad)
#   sin fit-in/ (segmento quitado, patrón viejo) → 384×540 = 207 360 px
#   fit-in/1200x1200/... →  853×1200  = 1 023 600 px  (5× más que quitar el
#                                         segmento, 11× más que el 360 original)
# No re-capa si el fit-in pedido ya es ≥1200 en ambas dimensiones (no downgrade
# — algún día el CDN podría devolver menos al pedir un tamaño mayor al real).
_BUSCALIBRE_RE = re.compile(r"(//images\.cdn\d*\.buscalibre\.com/)fit-in/(\d+)x(\d+)/")
_BUSCALIBRE_MAX_FIT = 1200


def _buscalibre_upgrade(m: "re.Match[str]") -> str:
    w, h = int(m.group(2)), int(m.group(3))
    if w >= _BUSCALIBRE_MAX_FIT and h >= _BUSCALIBRE_MAX_FIT:
        return m.group(0)  # ya pide alta resolución — no re-capar
    return f"{m.group(1)}fit-in/{_BUSCALIBRE_MAX_FIT}x{_BUSCALIBRE_MAX_FIT}/"


_URL_UPGRADES = [
    # whakoom: /small/ o /thumb/ o /medium/ → /large/
    (re.compile(r"(//i1\.whakoom\.com/)(?:small|thumb|medium)/"), r"\1large/"),
    # buscalibre: fit-in/<W>x<H>/ → fit-in/1200x1200/ (ver _buscalibre_upgrade)
    (_BUSCALIBRE_RE, _buscalibre_upgrade),
    # cultura: quitar cdn-cgi/image/width=<N>/  (hasta 2×)
    (re.compile(r"(//cdn\.cultura\.com/)cdn-cgi/image/width=\d+/"), r"\1"),
    # bdfugue (Magento): quitar cache/<hash8+>/  (2-5× px)
    (re.compile(r"(/media/catalog/product/)cache/[0-9a-f]{8,}/"), r"\1"),
    # WordPress genérico: quitar sufijo -<W>x<H> antes de la extensión
    (re.compile(r"-\d{2,4}x\d{2,4}(\.(?:jpe?g|png|webp))$"), r"\1"),
]


def upgrade_url_variants(url: str) -> list[str]:
    """Variantes de la URL en orden de preferencia: la hi-res derivada primero,
    la original como fallback. Patrones verificados 2026-06-11; _same_cover
    valida cada descarga, así que una reescritura incorrecta no contamina."""
    out = [url]
    for rx, repl in _URL_UPGRADES:
        up = rx.sub(repl, url)
        if up != url:
            out.insert(0, up)
            break
    return out

# Umbral aHash: el MISMO default endurecido que producción (6/64).
# _same_cover es un AND-gate (aHash ∧ dHash ∧ pHash ∧ NCC + entropía +
# denylist de placeholders); sin relax para originales chicas (audit 2026-06-10).
MAX_HASH_DIST = fbc.DEFAULT_MAX_HASH_DIST

SKIP_DOMAINS = frozenset({
    'instagram.com', 'twitter.com', 'x.com', 'facebook.com',
    'pinterest.com', 'pinimg.com', 'tiktok.com', 'reddit.com', 'redd.it',
    'youtube.com', 'ytimg.com', 'tumblr.com', 'gstatic.com',
    'zerochan.net', 'danbooru', 'donmai.us', 'goodreads.com', 'gr-assets.com',
    'redbubble.com', 'redbubble.net', 'picclick.com', 'picclickimg.com',
    'mercari.com', 'mercdn.net',
})

MAX_CANDIDATES_PER_CALL = 25   # Google trae ~70+/query; tope por llamada


def _resolve_reference_bytes(item: dict, ref_image_local: str, images_dir: Path) -> bytes:
    """Bytes de la imagen de referencia ACTUAL: `ref_image_local` si existe en
    disco (foto de galería puntual pasada por el plan), si no la portada
    (`images[0]`) vía `fbc._get_current_bytes`. `b''` si no hay nada resoluble.

    Fuente ÚNICA de esta resolución dentro del script — `validate()` y
    `reference_drift_reason()` la comparten para que el chequeo anti-drift
    compare EXACTAMENTE contra lo mismo que `_same_cover` termina usando."""
    if ref_image_local and (images_dir / ref_image_local).exists():
        return (images_dir / ref_image_local).read_bytes()
    return fbc._get_current_bytes(item, images_dir) or b''


def reference_drift_reason(data: dict, images_dir: Path = Path('data/images')) -> str:
    """"" si la referencia sigue siendo la misma que cuando `sc_plan.py` armó el
    plan; si no, el motivo corto del drift (gotcha #178, 2026-09-02).

    `sc_plan.py` persiste `reference_sha256` (sha256 del archivo local de
    referencia al momento del plan) en cada target con `reference_kind ==
    "real"`. El loop de Chrome del Step 3 del skill tarda decenas de minutos;
    en esa ventana otra sesión puede purgar/reemplazar esa imagen (medido:
    la purga de placeholders `.gif` de Rakuten de gotcha #176a corriendo en
    paralelo invalidó 15/48 targets de una corrida real, "Etapa 2 tanda 2" en
    docs/reference/images.md). Sin este guard, `sc_validate` cae al gate
    DÉBIL sin-referencia (`curr_bytes == b''`) y genera candidatas
    `verified:false` de dudosa relación real sobre una portada que el corpus
    ya no tiene.

    - `data['reference_sha256']` ausente/vacío → nada que comparar (plan
      viejo sin el campo, o target "sin imagen"/placeholder que nunca tuvo
      referencia real) → `""`, el guard es puramente ADITIVO.
    - Referencia actual irresoluble (archivo movido/borrado Y sin portada en
      `item['images']`) → `"reference_missing"`.
    - Referencia actual resoluble pero con OTRO contenido → `"reference_changed"`.
    """
    expected_sha = (data.get('reference_sha256') or '').strip()
    if not expected_sha:
        return ""
    item = data.get('item') or {}
    ref_local = data.get('ref_image_local') or ''
    current_bytes = _resolve_reference_bytes(item, ref_local, images_dir)
    if not current_bytes:
        return "reference_missing"
    if hashlib.sha256(current_bytes).hexdigest() != expected_sha:
        return "reference_changed"
    return ""


def validate(data: dict, images_dir: Path = Path('data/images'),
             drift_reason: str | None = None) -> list[dict]:
    """Valida las candidatas del payload y devuelve las aceptadas (ordenadas).

    `drift_reason`: si se pasa `None` (default), se calcula acá con
    `reference_drift_reason(data, images_dir)`; si el caller ya lo calculó
    (p.ej. `main()`, para reportarlo aparte en stdout) puede pasarlo para no
    recalcularlo. Si hay drift, se devuelve `[]` ANTES de tocar la red — no
    tiene sentido descargar/validar candidatas contra una referencia que ya
    no es la portada real del item (gotcha #178)."""
    item       = data['item']
    candidates = data['candidate_urls']
    curr_px    = data.get('curr_px', 0)
    slug       = item.get('slug', '')

    if drift_reason is None:
        drift_reason = reference_drift_reason(data, images_dir)
    if drift_reason:
        return []

    # ITEM 1 — denylist de rechazos: se consulta vía fbc.is_rejected_candidate
    # (fuente única, misma política que producción). Se carga una vez por llamada.
    ledger = fbc.load_rejection_ledger()

    session = requests.Session()
    session.headers.update({'User-Agent': fbc._UA})

    # Imagen de referencia: ref_image_local si se pasó (foto de galería);
    # si no, la portada (images[0]) vía _get_current_bytes.
    ref_local = data.get('ref_image_local') or ''
    curr_bytes = _resolve_reference_bytes(item, ref_local, images_dir)

    validated = []
    for cand in candidates[:MAX_CANDIDATES_PER_CALL]:
        orig_url = (cand.get('url') or '').strip()
        domain   = cand.get('domain') or (orig_url.split('/')[2] if orig_url.startswith('http') else '')
        if not orig_url or not orig_url.startswith('http'):
            continue
        if any(bad in domain for bad in SKIP_DOMAINS):
            continue
        # R5 — conflicto de metadata declarada: la URL/título de la candidata
        # declara OTRO volumen u OTRO ISBN que el item → hard reject (filtro
        # para "mismo manga, tomo equivocado"; mismo criterio que producción).
        # Se evalúa sobre la URL ORIGINAL una sola vez, antes del loop de variantes.
        if fbc.candidate_metadata_conflict(item, orig_url, cand.get('page_title', '')):
            continue
        # ITEM 1 — denylist: URL exacta vetada → saltar SIN descargar.
        if fbc.is_rejected_candidate(slug, orig_url, None, ledger):
            continue

        # Intentar variantes de URL en orden (hi-res primero, original como fallback).
        # La primera que devuelva imagen válida (≥5 000 bytes) gana; si falla, sigue.
        img_bytes = None
        used_url  = orig_url
        for variant_url in upgrade_url_variants(orig_url):
            try:
                b = fbc._fetch(variant_url, session)
            except Exception:
                b = None
            if b and len(b) >= 5_000:
                img_bytes = b
                used_url  = variant_url
                break

        if not img_bytes:
            continue
        # ITEM 1 — denylist por HASH (o por URL de la variante efectivamente usada):
        # sólo veta por hash con motivo de identidad (política en el motor).
        if fbc.is_rejected_candidate(slug, used_url, fbc._ahash_hex(img_bytes), ledger):
            continue
        new_px = fbc._get_pixels_from_bytes(img_bytes)
        if new_px < 10_000:
            continue
        # Debe ser MEJOR resolución que la actual (si hay actual)
        if curr_px > 0 and new_px < max(curr_px * fbc.DEFAULT_MIN_GAIN, 30_000):
            continue

        # ─── Gate de detalle efectivo (gotcha #98) ───
        # Aunque pase el px-gain, una candidata "blanda" (escaneo comprimido /
        # upscale: muchos píxeles, poco detalle real) NO es upgrade. Misma
        # función que producción (fetch_better_covers._process_item) → skill y
        # pipeline no driftean.
        if fbc._is_soft_image(img_bytes):
            continue

        # ─── Verificación de identidad (el corazón del skill) ───
        match_dist = None
        if curr_bytes:
            if not fbc._same_cover(curr_bytes, img_bytes, MAX_HASH_DIST):
                continue
            from cover_identity import visual_identity
            if not visual_identity(curr_bytes, img_bytes)['ok']:
                continue
            h1 = fbc._ahash(curr_bytes); h2 = fbc._ahash(img_bytes)
            if h1 is not None and h2 is not None:
                match_dist = fbc._hamming(h1, h2)
            verified = True
        else:
            # Item sin imagen actual (--include-no-image): no hay con qué
            # verificar. Se acepta pero queda marcado para revisión estricta.
            verified = False

        filename = fbc._save_image(img_bytes, images_dir)
        if not filename:
            continue
        # new_pixels = resolución del archivo YA NORMALIZADO (AVIF ≤1600px), no la del
        # original — el cover-preview debe mostrar lo que realmente queda guardado.
        try:
            stored_px = fbc._get_pixels_from_bytes((images_dir / filename).read_bytes()) or new_px
        except OSError:
            stored_px = new_px
        validated.append({
            'new_image'  : filename,
            'new_url'    : used_url,
            'new_pixels' : stored_px,
            'ref_pixels' : curr_px,
            'match_dist' : match_dist,
            'verified'   : verified,
            'page_title' : cand.get('page_title', ''),
            'domain'     : domain,
            'query'      : cand.get('query', ''),
            'confidence' : 'low',
            'action'     : 'replace_cover',
            'target'     : '',
            'kind'       : 'gallery',
            'status'     : 'pending',
        })

    # Mejor primero: menor distancia (más parecida), luego mayor resolución
    validated.sort(key=lambda c: (c['match_dist'] if c['match_dist'] is not None else 99,
                                  -c['new_pixels']))
    return validated


def main() -> None:
    if len(sys.argv) > 1:
        inp = Path(sys.argv[1])
        if not inp.exists():
            print(json.dumps({'validated': [], 'error': f'input not found: {inp}'}))
            return
    else:
        tmp_inputs = sorted(Path('.').glob('.tmp_sc_input_*.json'))
        if not tmp_inputs:
            print(json.dumps({'validated': [], 'error': 'no input file found'}))
            return
        inp = tmp_inputs[0]
    data = json.loads(inp.read_text(encoding='utf-8'))
    drift = reference_drift_reason(data)
    out = {'validated': validate(data, drift_reason=drift)}
    if drift:
        out['drift'] = drift
    print(json.dumps(out))


if __name__ == '__main__':
    main()
