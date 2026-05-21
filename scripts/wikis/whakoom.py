"""Spider de Whakoom — descubre ediciones manga + variantes sin login.

⚠️ ESTADO: USO OCASIONAL, NO REGULAR.

Desde que añadimos `scripts/retrofit/search_discovery.py` con Gemini API
+ Grounding with Google Search, esa es la vía recomendada para descubrir
items en Whakoom. Ventajas:
- Cubre items históricos (no solo /newtitles recientes).
- Sin riesgo de Cloudflare ban (este spider nos quemó la IP una vez).
- Mucho más rápido (~30s/query vs ~70 min de bootstrap).

Este módulo sigue siendo útil para:
- Bootstrap inicial cuando arrancás de cero y querés volumen rápido.
- Forensic recovery puntual cuando Gemini no trae algo específico.

Para uso regular en cada scrape, ver `ES/LatAm - Whakoom Novedades`
(kind:html en sources.yml) que sólo lee /newtitles sin hacer spider
profundo — ligero, sin riesgo, cubre el delta diario.

----



Whakoom (whakoom.com) es un tracker de coleccionistas español/LatAm que
indexa exhaustivamente cómics y manga publicados en España, Argentina,
México, etc. Sin login se accede a:

- `/newtitles`              → ~415 últimas novedades editoriales (radar).
- `/comics/{shortcode}`     → detail page de un volumen, lista sus ediciones.
- `/ediciones/{id}/{slug}`  → metadata completa de UNA edición con OG tags
                              + lista otras ediciones del mismo volumen
                              (variantes, portadas alternativas, deluxe).

Estrategia (BFS de 3 niveles):

    /newtitles
        ↓ extract anchors /comics/{X}
    /comics/{X}
        ↓ fetch + extract /ediciones/{N}
    /ediciones/{N}
        ↓ fetch + extract Candidate (OG metadata)
        ↓ extract sibling editions /ediciones/{N'} y agregar al queue

Esto descubre variantes que `/newtitles` solo no expone (ej. "Spy x Family
1 Portada Alternativa Ivrea Argentina" se descubre desde la página de la
edición regular de Spy x Family 1).

Diferencial vs Bootstrap:
- DIFERENCIAL: la source `ES/LatAm - Whakoom Novedades` (kind:html en
  sources.yml) corre en cada scrape regular y trae solo el nivel 1
  (/newtitles → /comics/X). Lightweight, captura novedades del día.
- BOOTSTRAP: --bootstrap-wiki whakoom corre el spider completo de 3
  niveles. Pesado (~1500 HTTP requests, ~15-30 min) pero descubre todas
  las variantes y portadas alternativas relacionadas a las novedades.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    from scripts.manga_watch import (  # type: ignore[import-not-found]
        Candidate,
        Source,
        candidate_from_source,
        clean_text,
        is_likely_manga,
        score_candidate,
    )
except ImportError:
    from manga_watch import (  # type: ignore[no-redef]
        Candidate,
        Source,
        candidate_from_source,
        clean_text,
        is_likely_manga,
        score_candidate,
    )


BASE_URL = "https://www.whakoom.com"
NEWTITLES_URL = f"{BASE_URL}/newtitles"

_COMICS_HREF_RE = re.compile(r"^/comics/[A-Za-z0-9]+/")
_EDICIONES_HREF_RE = re.compile(r"^/ediciones/(\d+)/")
_PUBLISHER_PAREN_RE = re.compile(r"\s*\(([^)]+)\)\s*$")


def _virtual_source() -> Source:
    return Source(
        name="ES/LatAm - Whakoom (spider)",
        country="España / LatAm",
        language="Español",
        publisher="Varias editoriales",
        source_class="trusted_media",
        kind="html",
        url=BASE_URL,
        tags=["wiki", "whakoom", "manga", "spain", "argentina", "mexico"],
        purity="mixed",   # Whakoom mezcla manga + cómic occidental + BD
    )


def _ua_session(session: requests.Session) -> requests.Session:
    """Setea headers HTTP "browser-like".

    Whakoom usa Cloudflare con anti-bot agresivo. Headers de browser
    completos (no sólo User-Agent) reducen significativamente la tasa
    de challenge / 429. Sin estos, Cloudflare nos identifica como
    bot trivial y rate-limita el sitio completo a nuestra IP.
    """
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": BASE_URL + "/",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": "1",
    })
    return session


# Detección de page Cloudflare challenge (no es 200 OK útil — es página
# de "verify human"). Si detectamos esto, la IP está banneada o en
# challenge mode. Mejor abortar limpiamente que insistir.
_CLOUDFLARE_CHALLENGE_MARKERS = (
    "cf-chl-bypass",
    "Just a moment...",
    "Checking your browser",
    "cf_challenge",
    "challenge-platform",
)


def _looks_like_cf_challenge(html_text: str) -> bool:
    """¿La página es un challenge de Cloudflare en lugar de contenido real?"""
    if not html_text or len(html_text) > 50000:
        # Pages largas (>50KB) son contenido real; challenges son 5-15KB.
        return False
    return any(marker in html_text for marker in _CLOUDFLARE_CHALLENGE_MARKERS)


# Throttle global: lockfile en ~/.cache/manga-watch/whakoom_lastrun
# para impedir correr el bootstrap completo más de 1x cada N horas.
# Esto protege la IP del usuario contra abuso accidental.
_THROTTLE_FILE = Path.home() / ".cache" / "manga-watch" / "whakoom_lastrun"
_THROTTLE_MIN_HOURS = 6  # mínimo 6h entre bootstraps completos


def _check_throttle(force: bool = False) -> None:
    """Verifica que no haya un bootstrap reciente; lanza SystemExit si sí.

    Usar `force=True` (--ignore-throttle) para saltarse esta protección
    (útil cuando sabés que cambió la IP o querés correr aún sabiendo el
    riesgo).
    """
    import datetime as dt
    if force or not _THROTTLE_FILE.exists():
        return
    try:
        ts = float(_THROTTLE_FILE.read_text().strip())
    except (ValueError, OSError):
        return
    last_run = dt.datetime.fromtimestamp(ts)
    elapsed = dt.datetime.now() - last_run
    remaining = dt.timedelta(hours=_THROTTLE_MIN_HOURS) - elapsed
    if remaining.total_seconds() > 0:
        hh = remaining.total_seconds() / 3600
        raise SystemExit(
            f"[WHAKOOM] Último bootstrap hace {elapsed} (< {_THROTTLE_MIN_HOURS}h).\n"
            f"Esperá {hh:.1f}h más para evitar quemar la IP, o pasá --ignore-throttle.\n"
            f"(Throttle file: {_THROTTLE_FILE})"
        )


def _record_run() -> None:
    """Marca el momento del último bootstrap completo."""
    import time
    _THROTTLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _THROTTLE_FILE.write_text(str(time.time()))


def extract_comics_urls_from_newtitles(html_text: str) -> list[str]:
    """Devuelve URLs absolutas a /comics/X desde el HTML de /newtitles."""
    soup = BeautifulSoup(html_text, "html.parser")
    urls: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if _COMICS_HREF_RE.match(href):
            urls.add(f"{BASE_URL}{href}")
    return sorted(urls)


def extract_ediciones_urls_from_html(html_text: str) -> list[tuple[int, str]]:
    """Devuelve [(id, absolute_url), ...] de todas las /ediciones/N referenciadas.

    Filtra duplicados por id (mismo id con diferentes slugs/suffixes solo se
    cuenta una vez).
    """
    soup = BeautifulSoup(html_text, "html.parser")
    seen: dict[int, str] = {}
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        m = _EDICIONES_HREF_RE.match(href)
        if not m:
            continue
        ed_id = int(m.group(1))
        # Saltar URLs con suffixes tipo `/todos` — son vistas de la lista
        # personal, no la canónica del item.
        path = href.split("?", 1)[0].rstrip("/")
        if path.count("/") > 3:  # /ediciones/N/slug/extra → extra
            continue
        # Reemplazar solo si no estaba ya (prefiere primera aparición).
        if ed_id not in seen:
            seen[ed_id] = f"{BASE_URL}{href}"
    return sorted(seen.items())


def parse_edition_page(html_text: str, edition_url: str) -> Candidate | None:
    """Convierte una página /ediciones/N en un Candidate con OG metadata.

    Devuelve None si no se puede extraer un title mínimo.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    source = _virtual_source()

    def og(prop: str) -> str:
        el = soup.find("meta", property=prop)
        return clean_text(el.get("content", "")) if el else ""

    og_title = og("og:title")
    if not og_title:
        # Fallback al <title>
        if soup.title and soup.title.string:
            og_title = clean_text(soup.title.string)
        if not og_title:
            return None
    og_desc = og("og:description")
    og_image = og("og:image")
    canonical = og("og:url") or edition_url

    # og:title suele venir tipo "Spy x Family #1 - Portada Alternativa (Ivrea Argentina)".
    # Separamos el publisher del paréntesis final.
    publisher = ""
    title_clean = og_title
    m = _PUBLISHER_PAREN_RE.search(og_title)
    if m:
        publisher = clean_text(m.group(1))
        title_clean = clean_text(og_title[: m.start()])

    # Publisher también disponible en class="publisher" (fallback).
    if not publisher:
        pub_el = soup.select_one(".publisher")
        if pub_el:
            publisher = clean_text(pub_el.get_text(" ", strip=True))

    cand = candidate_from_source(source, title_clean, canonical, og_desc)
    if publisher:
        cand.publisher = publisher
    if og_image:
        cand.image_url = og_image
    # País — heurística por publisher conocido.
    pub_lc = publisher.lower()
    if "argentina" in pub_lc:
        cand.country = "Argentina"
    elif any(k in pub_lc for k in ("méxico", "mexico", "panini manga méxico")):
        cand.country = "México"
    elif any(k in pub_lc for k in ("ivrea españa", "planeta", "norma", "panini españa")):
        cand.country = "España"
    return cand


class WhakoomBlocked(Exception):
    """Cloudflare challenge detectado — IP está banneada o en cuarentena.

    El spider debe abortar todo el bootstrap cuando se levanta esta
    excepción; insistir empeoraría el bloqueo.
    """


def fetch_url(
    url: str,
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
    max_retries_429: int = 3,
) -> str:
    """GET con encoding-fix; devuelve "" en error.

    Maneja 429 (rate-limit) con backoff exponencial: 10s → 20s → 40s.
    Levanta `WhakoomBlocked` si detecta página de Cloudflare challenge —
    la IP está bloqueada y seguir presionando es contraproducente.
    """
    delay = 10
    for attempt in range(max_retries_429 + 1):
        try:
            response = session.get(url, timeout=timeout, allow_redirects=True)
        except requests.RequestException:
            return ""
        if response.status_code == 429:
            if attempt >= max_retries_429:
                print(f"[WHAKOOM] 429 persistente en {url[:60]} — saltando")
                return ""
            print(f"[WHAKOOM] 429 — sleeping {delay}s y reintento ({url[:60]})")
            time.sleep(delay)
            delay *= 2
            continue
        # Cloudflare a veces devuelve 403 con challenge.
        if response.status_code in (403, 503):
            text = response.text
            if _looks_like_cf_challenge(text):
                raise WhakoomBlocked(
                    f"Cloudflare challenge detectado en {url[:60]} (HTTP {response.status_code})"
                )
            return ""
        if response.status_code != 200:
            return ""
        if not response.encoding:
            response.encoding = response.apparent_encoding
        # 200 OK con cuerpo de challenge (Cloudflare a veces lo hace).
        if _looks_like_cf_challenge(response.text):
            raise WhakoomBlocked(
                f"Cloudflare challenge en HTTP 200 — IP bloqueada ({url[:60]})"
            )
        return response.text
    return ""


def bootstrap(
    year_from: int,           # ignorado — Whakoom no es por mes
    month_from: int,          # ignorado
    year_to: int,             # ignorado
    month_to: int,            # ignorado
    session: requests.Session,
    sleep_seconds: float = 2.0,   # Whakoom rate-limit es estricto
    timeout: tuple[int, int] = (10, 30),
    min_score: int = 30,
    fetch_details: bool = False,  # ignorado — spider ya hace detail-fetch
    max_editions: int = 1500,
    ignore_throttle: bool = False,
) -> list[Candidate]:
    """Spider Whakoom — descubre ediciones desde /newtitles vía BFS.

    Los argumentos year_from/month_to son ignorados (Whakoom no indexa
    por mes); se mantienen por compatibilidad con la interfaz de wikis.

    `max_editions=1500` acota el BFS. Default seguro: ~60-70 min con
    sleep_seconds=2.0 sin disparar Cloudflare challenge.

    Rate-limit:
    - Whakoom devuelve 429 si se le pide demasiado rápido. Backoff
      exponencial maneja eso. Si ves muchos [WHAKOOM] 429, sube a 3.0.
    - Cloudflare puede levantar challenge a la IP entera (no solo a este
      script). El spider aborta con `WhakoomBlocked` si detecta esa
      página. Si esto pasa, esperá 1-2h antes de reintentar.
    - Throttle local: bloqueamos auto-runs <6h tras el último para
      evitar quemar la IP por accidente. `ignore_throttle=True` lo salta.
    """
    _check_throttle(force=ignore_throttle)
    _ua_session(session)
    print(f"[WHAKOOM] BFS spider, max_editions={max_editions}, sleep={sleep_seconds}s")
    try:
        return _bootstrap_inner(
            session=session, sleep_seconds=sleep_seconds,
            timeout=timeout, min_score=min_score, max_editions=max_editions,
        )
    except WhakoomBlocked as exc:
        print(f"\n[WHAKOOM] ABORTADO: {exc}")
        print(f"[WHAKOOM] Tu IP está en cuarentena Cloudflare. Esperá 1-2h.")
        print(f"[WHAKOOM] Verificalo abriendo {NEWTITLES_URL} en un navegador.")
        return []


def _bootstrap_inner(
    *,
    session: requests.Session,
    sleep_seconds: float,
    timeout: tuple[int, int],
    min_score: int,
    max_editions: int,
) -> list[Candidate]:

    # Nivel 1: /newtitles → comics URLs
    print(f"[WHAKOOM] Fase 1: fetch {NEWTITLES_URL}")
    text = fetch_url(NEWTITLES_URL, session, timeout=timeout)
    if not text:
        print(f"[WHAKOOM] ERROR: no se pudo descargar /newtitles")
        return []
    comics_urls = extract_comics_urls_from_newtitles(text)
    print(f"[WHAKOOM] /newtitles → {len(comics_urls)} comics URLs")

    # Nivel 2: cada /comics/X → /ediciones/N URLs
    print(f"[WHAKOOM] Fase 2: spider {len(comics_urls)} comics")
    ediciones_queue: list[str] = []
    seen_ediciones: set[int] = set()
    for idx, comic_url in enumerate(comics_urls, start=1):
        if idx % 50 == 0:
            print(f"  [{idx}/{len(comics_urls)}] queued={len(ediciones_queue)}")
        text = fetch_url(comic_url, session, timeout=timeout)
        if not text:
            continue
        for ed_id, ed_url in extract_ediciones_urls_from_html(text):
            if ed_id not in seen_ediciones:
                seen_ediciones.add(ed_id)
                ediciones_queue.append(ed_url)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    print(f"[WHAKOOM] /comics/* → {len(seen_ediciones)} ediciones únicas")

    # Nivel 3: cada /ediciones/N → Candidate + descubrir variantes hermanas
    # max_editions acota el TOTAL del BFS (queue + expansión). Si Fase 2 ya
    # superó el límite, igualmente procesamos al menos los descubiertos en Fase 2.
    edition_cap = max(max_editions, len(seen_ediciones))
    print(f"[WHAKOOM] Fase 3: fetch + parse {len(ediciones_queue)} ediciones (cap={edition_cap})")
    candidates: list[Candidate] = []
    queue_idx = 0
    while queue_idx < len(ediciones_queue) and len(seen_ediciones) <= edition_cap:
        ed_url = ediciones_queue[queue_idx]
        queue_idx += 1
        text = fetch_url(ed_url, session, timeout=timeout)
        if not text:
            continue

        # Parse edition → candidate
        cand = parse_edition_page(text, ed_url)
        if cand is not None:
            # Filtro upstream non-manga aquí mismo para no scorear basura
            is_m, _ = is_likely_manga(
                cand.title, cand.description,
                source_purity="mixed", publisher=cand.publisher,
            )
            if is_m:
                candidates.append(score_candidate(cand))

        # Descubrir variantes hermanas (BFS shallow)
        for ed_id, sib_url in extract_ediciones_urls_from_html(text):
            if ed_id not in seen_ediciones:
                seen_ediciones.add(ed_id)
                ediciones_queue.append(sib_url)
                if len(seen_ediciones) >= edition_cap:
                    break

        if queue_idx % 100 == 0:
            print(f"  [{queue_idx}/{len(ediciones_queue)}] candidates so far: {len(candidates)}")
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    kept = [c for c in candidates if c.score >= min_score]
    print(f"\n[WHAKOOM] Total ediciones visitadas: {queue_idx}")
    print(f"[WHAKOOM] Candidates parseados: {len(candidates)}")
    print(f"[WHAKOOM] Con score >= {min_score}: {len(kept)}")
    # Solo grabamos el timestamp si el run completó (no fue abortado por
    # CF challenge ni saltó por throttle). Esto evita que un run fallido
    # bloquee runs subsiguientes.
    _record_run()
    return kept


def iter_year_months(
    year_from: int, month_from: int, year_to: int, month_to: int,
) -> list[tuple[int, int]]:
    """Stub para compat con la interfaz de wikis. Whakoom no itera por mes."""
    return [(year_from, month_from)]
