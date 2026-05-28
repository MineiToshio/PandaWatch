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
from typing import Any, Callable, Iterable

import requests
from bs4 import BeautifulSoup

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    from scripts.manga_watch import (  # type: ignore[import-not-found]
        Candidate,
        Source,
        _extract_images_from_detail_soup,
        candidate_from_source,
        clean_text,
        is_likely_manga,
        score_candidate,
    )
except ImportError:
    from manga_watch import (  # type: ignore[no-redef]
        Candidate,
        Source,
        _extract_images_from_detail_soup,
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

# Detecta una URL absoluta o relativa a /ediciones/N/slug en cualquier subdominio
# Whakoom (whakoom.com, en.whakoom.com, www.whakoom.com, etc.).
_EDITION_ABS_URL_RE = re.compile(
    r"^https?://(?:[a-z]+\.)?whakoom\.com/ediciones/(\d+)/",
    re.IGNORECASE,
)
# Lo mismo para /comics/<shortcode>/<slug>/<vol>.
_COMIC_ABS_URL_RE = re.compile(
    r"^https?://(?:[a-z]+\.)?whakoom\.com/comics/([A-Za-z0-9]+)/",
    re.IGNORECASE,
)


def is_whakoom_edition_url(url: str) -> bool:
    """¿Es una URL a una página /ediciones/ de Whakoom?

    Detecta tanto www.whakoom.com como subdominios localizados
    (en.whakoom.com, it.whakoom.com, etc.).
    """
    if not url:
        return False
    return bool(_EDITION_ABS_URL_RE.match(url))


def is_whakoom_comic_url(url: str) -> bool:
    """¿Es una URL a un tomo individual /comics/.../<vol> de Whakoom?"""
    if not url:
        return False
    return bool(_COMIC_ABS_URL_RE.match(url))


def edition_todos_url(edition_url: str) -> str:
    """Devuelve la URL de la pestaña 'Comics' de una edición (`.../todos`).

    Whakoom muestra solo los primeros ~11 tomos en la página principal;
    la lista completa está en `<edition_url>/todos`.
    """
    base = edition_url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if base.endswith("/todos"):
        return edition_url
    return f"{base}/todos"


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
        # OJO: NO incluimos "br" (Brotli) — requests no lo decodifica nativo
        # y devolveríamos bytes binarios como text. Cloudflare/Whakoom usa
        # Brotli por defecto cuando se le pide, así que evitarlo en el header
        # nos garantiza HTML decodificado. Sin esto, response.text es basura.
        "Accept-Encoding": "gzip, deflate",
        "Referer": BASE_URL + "/",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": "1",
    })
    return session


# Detección de page Cloudflare challenge (no es 200 OK útil — es página
# de "verify human"). Si detectamos esto, la IP está banneada o en
# challenge mode. Mejor abortar limpiamente que insistir.
#
# ⚠️ NO usar "challenge-platform" como marker: aparece en CUALQUIER página
# protegida por Cloudflare como parte del JSD bot-detection script
# (/cdn-cgi/challenge-platform/scripts/jsd/main.js). El path real de un
# challenge UI es /cdn-cgi/challenge-platform/h/g/... (con /h/, no /scripts/).
# Lo mismo con "cf_challenge": demasiado genérico.
_CLOUDFLARE_CHALLENGE_MARKERS = (
    "cf-chl-bypass",                          # form metadata del challenge
    "Just a moment...",                       # title de la página de espera
    "Checking your browser",                  # texto del verify
    "__cf_chl_rt_tk",                         # token de challenge
    "/cdn-cgi/challenge-platform/h/",         # UI path del challenge (no /scripts/)
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


_VOLUME_LI_SELECTOR = "li[id^='comic'] a[href^='/comics/']"
# Captura "#12", "12" o "#A" (algunos one-shots no tienen número).
_ISSUE_NUMBER_RE = re.compile(r"^#?\s*([0-9A-Za-z]+)")

# Whakoom oculta el `/comics/<shortcode>` canónico de páginas /ediciones/
# detrás de `/login?ReturnUrl=...`. Para one-shots (ediciones de un solo
# tomo) ese es el ÚNICO lugar donde aparece la URL del comic.
_LOGIN_RETURN_COMIC_RE = re.compile(
    r"/login\?ReturnUrl=(/comics/[A-Za-z0-9]+/[a-zA-Z0-9_-]+(?:/\d+)?)",
)


def _extract_oneshot_comic_url(html_text: str) -> str:
    """Si /ediciones/ es un one-shot, devuelve la URL canónica /comics/.

    Whakoom no expone `/comics/...` directamente en una página /ediciones/
    cuando es de un solo tomo: el link siempre está envuelto en un
    `/login?ReturnUrl=...`. Sacamos el ReturnUrl y reconstruimos la URL
    absoluta.

    Devuelve "" si no se puede extraer.
    """
    m = _LOGIN_RETURN_COMIC_RE.search(html_text)
    if not m:
        return ""
    return f"{BASE_URL}{m.group(1)}"


def parse_volume_links(html_text: str) -> list[dict]:
    """Extrae los tomos individuales listados en una página /ediciones/ o /todos.

    Devuelve una lista de dicts con `{url, title, issue, image_url}` donde:
    - `url`: URL absoluta al tomo /comics/<shortcode>/<slug>/<N>.
    - `title`: título textual del tomo (ej. "Berserk Deluxe Edition #1").
    - `issue`: número de tomo extraído del span .issue-number (ej. "1").
    - `image_url`: cover del tomo (puede ser thumbnail "small/").

    Dedupea por URL: si la misma URL aparece varias veces, conserva la
    primera. No filtra duplicados por shortcode entre páginas distintas
    — eso lo resuelve el caller mergeando por URL.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    out: list[dict] = []
    seen_urls: set[str] = set()
    for a in soup.select(_VOLUME_LI_SELECTOR):
        href = (a.get("href") or "").strip()
        if not href.startswith("/comics/"):
            continue
        url = f"{BASE_URL}{href}"
        if url in seen_urls:
            continue
        seen_urls.add(url)
        title = clean_text(a.get("title") or "")
        if not title:
            # Fallback: <strong>Series</strong> <span class="issue-number">#N</span>
            strong = a.find("strong")
            issue_el = a.select_one(".issue-number")
            parts = []
            if strong:
                parts.append(clean_text(strong.get_text(" ", strip=True)))
            if issue_el:
                parts.append(clean_text(issue_el.get_text(" ", strip=True)))
            title = " ".join(p for p in parts if p)
        issue = ""
        issue_el = a.select_one(".issue-number")
        if issue_el:
            m = _ISSUE_NUMBER_RE.match(clean_text(issue_el.get_text(" ", strip=True)))
            if m:
                issue = m.group(1)
        image_url = ""
        img = a.find("img")
        if img:
            image_url = (img.get("src") or "").strip()
        out.append({
            "url": url,
            "title": title,
            "issue": issue,
            "image_url": image_url,
        })
    return out


# Mapping del id de bandera de Whakoom (visible en `lang/N.png`) a
# (lenguaje, país) cuando podemos inferirlo. Es heurístico — el `.title`
# adyacente al `.value.flag` es la verdad textual; este map es fallback
# si solo tenemos el flag.
_WHAKOOM_FLAG_LANG_HINT: dict[str, str] = {
    # IDs estables observados; ampliar conforme veamos más ediciones.
    "1": "Español",
    "9": "Inglés",
    "16": "Italiano",
}


_LANG_TITLE_TO_LANGUAGE: list[tuple[str, str]] = [
    # (substring case-insensitive en .title, language canónico)
    ("english", "Inglés"),
    ("spanish", "Español"),
    ("español", "Español"),
    ("italian", "Italiano"),
    ("italiano", "Italiano"),
    ("french", "Francés"),
    ("français", "Francés"),
    ("portuguese", "Portugués"),
    ("português", "Portugués"),
    ("japanese", "Japonés"),
    ("german", "Alemán"),
]


def _detect_language_from_edition_html(soup: BeautifulSoup) -> tuple[str, str]:
    """Devuelve `(language, country)` inferidos de la página de edición.

    Estrategia:
    1. Texto del `.title` adyacente al `.value.flag` (ej.
       "English (United States)" → ("Inglés", "Estados Unidos")).
    2. Fallback al `lang/N.png` del flag.
    3. ("", "") si nada matchea.
    """
    # Buscar el `<li>` que contiene el flag dentro de `ul.info-summary`.
    for li in soup.select("ul.info-summary > li"):
        flag = li.select_one(".value.flag")
        if not flag:
            continue
        title_el = li.select_one(".title")
        title_text = clean_text(title_el.get_text(" ", strip=True)) if title_el else ""
        language = ""
        country = ""
        title_lc = title_text.lower()
        for needle, lang in _LANG_TITLE_TO_LANGUAGE:
            if needle in title_lc:
                language = lang
                break
        # Country aparece entre paréntesis: "English (United States)"
        country_match = re.search(r"\(([^)]+)\)\s*$", title_text)
        if country_match:
            raw = country_match.group(1).strip()
            country = {
                "United States": "Estados Unidos",
                "United Kingdom": "Reino Unido",
                "Spain": "España",
                "Argentina": "Argentina",
                "Mexico": "México",
                "México": "México",
                "Italy": "Italia",
                "France": "Francia",
                "Germany": "Alemania",
                "Japan": "Japón",
                "Brazil": "Brasil",
                "Portugal": "Portugal",
            }.get(raw, raw)
        # Fallback al flag.png si el texto no nos dio idioma.
        if not language:
            m = re.search(r"/lang/(\d+)\.png", flag.get("style", ""))
            if m:
                language = _WHAKOOM_FLAG_LANG_HINT.get(m.group(1), "")
        return language, country
    return "", ""


def _extract_authors(soup: BeautifulSoup) -> str:
    """Devuelve autores como string `"A, B"` desde `h3.autores + p`."""
    h3 = soup.select_one("h3.autores")
    if not h3:
        return ""
    p = h3.find_next("p")
    if not p:
        return ""
    names = []
    for a in p.find_all("a"):
        n = clean_text(a.get_text(" ", strip=True))
        if n and n not in names:
            names.append(n)
    if not names:
        # Fallback: texto crudo limpio (cortando "(Script, Drawing, ...)" finales)
        raw = clean_text(p.get_text(" ", strip=True))
        raw = re.sub(r"\s*\([^)]*\)\s*$", "", raw)
        return raw
    return ", ".join(names)


def parse_edition_metadata(html_text: str) -> dict:
    """Extrae metadata edición-nivel (publisher, autor, idioma, tipo…).

    Estos campos se HEREDAN por cada tomo expandido. La URL canónica de
    la edición se usa solo como `source_url` para el grupo; cada tomo
    tiene su propia `/comics/...` URL.

    Devuelve `{title, publisher, edition_type, language, country, author,
    image_url, description}`. Campos vacíos cuando no se pueden extraer.
    """
    soup = BeautifulSoup(html_text, "html.parser")

    def og(prop: str) -> str:
        el = soup.find("meta", property=prop)
        return clean_text(el.get("content", "")) if el else ""

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = clean_text(h1.get_text(" ", strip=True))
    if not title:
        title = og("og:title")

    publisher = ""
    pub_el = soup.select_one("p.publisher a, p.publisher")
    if pub_el:
        publisher = clean_text(pub_el.get_text(" ", strip=True))

    edition_type = ""
    et_el = soup.select_one("p.edition-type")
    if et_el:
        edition_type = clean_text(et_el.get_text(" ", strip=True))

    language, country = _detect_language_from_edition_html(soup)

    author = _extract_authors(soup)

    description = og("og:description")

    image_url = og("og:image")

    # Multi-imagen edición-nivel: páginas /ediciones/ a veces traen thumbnails
    # de portadas alternativas/back-cover además del og:image principal.
    try:
        images = _extract_images_from_detail_soup(soup, BASE_URL)
    except Exception:
        images = []

    return {
        "title": title,
        "publisher": publisher,
        "edition_type": edition_type,
        "language": language,
        "country": country,
        "author": author,
        "description": description,
        "image_url": image_url,
        "images": images,
    }


def _merge_volume_dicts(*volume_lists: list[dict]) -> list[dict]:
    """Mergea N listas de volume dicts (de páginas distintas) por URL.

    Si la misma URL aparece en varias listas, prefiere la primera versión
    no-vacía de cada campo (title, issue, image_url).
    """
    merged: dict[str, dict] = {}
    for vol_list in volume_lists:
        for vol in vol_list:
            url = vol.get("url", "")
            if not url:
                continue
            if url not in merged:
                merged[url] = dict(vol)
                continue
            existing = merged[url]
            for key in ("title", "issue", "image_url"):
                if not existing.get(key) and vol.get(key):
                    existing[key] = vol[key]
    return list(merged.values())


def expand_whakoom_edition(
    edition_url: str,
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
    sleep_seconds: float = 1.5,
    fetch_todos: bool = True,
    edition_html: str | None = None,
    todos_html: str | None = None,
) -> list[Candidate]:
    """Expande una página /ediciones/ en N Candidates, uno por tomo.

    Lee la página principal (metadata + ~11 primeros tomos) y opcionalmente
    `/todos` (listado completo). Cada tomo hereda publisher/autor/idioma/
    país/tipo de edición + descripción de la edición padre, y aporta:
    URL `/comics/...`, título "<serie> #N" y cover individual.

    Levanta `WhakoomBlocked` si Cloudflare devuelve challenge en cualquiera
    de las requests — el caller debe abortar el batch (la IP está en
    cuarentena, no tiene sentido seguir presionando).

    Parametros `edition_html` / `todos_html` permiten pasar HTML pre-fetched
    para tests sin sesión HTTP real.
    """
    # Carga HTML edición principal
    if edition_html is None:
        edition_html = fetch_url(edition_url, session, timeout=timeout)
        if not edition_html:
            return []
    meta = parse_edition_metadata(edition_html)
    main_volumes = parse_volume_links(edition_html)

    # Carga /todos para completar tomos que no entran en la página principal.
    todos_volumes: list[dict] = []
    if fetch_todos:
        if todos_html is None:
            t_url = edition_todos_url(edition_url)
            if t_url != edition_url:
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
                todos_html = fetch_url(t_url, session, timeout=timeout)
        if todos_html:
            todos_volumes = parse_volume_links(todos_html)

    volumes = _merge_volume_dicts(main_volumes, todos_volumes)

    # Fallback one-shot: si la edición no lista tomos (ej. "Cofre Aniversario",
    # "Edición Especial Limitada"), buscamos la URL /comics/ enmascarada en
    # `/login?ReturnUrl=...` y producimos UN único Candidate con la metadata
    # edición-nivel. Así no perdemos el item y respetamos la regla "el
    # catálogo solo guarda /comics/".
    if not volumes:
        oneshot_url = _extract_oneshot_comic_url(edition_html)
        if not oneshot_url:
            return []
        volumes = [{
            "url": oneshot_url,
            "title": meta.get("title", ""),
            "issue": "",
            "image_url": meta.get("image_url", ""),
        }]

    source = _virtual_source()
    candidates: list[Candidate] = []
    edition_series = meta.get("title", "")
    for vol in volumes:
        # Título por defecto: el del <a title="..."> ("Serie #N").
        # Si no vino, lo armamos a partir de la edición + issue.
        vol_title = vol.get("title", "")
        if not vol_title:
            issue = vol.get("issue", "")
            if edition_series and issue:
                vol_title = f"{edition_series} #{issue}"
            elif edition_series:
                vol_title = edition_series
            else:
                continue  # sin título, no podemos crear candidato útil
        # Descripción: la de la edición (todos los tomos comparten plot).
        cand = candidate_from_source(
            source, vol_title, vol["url"], meta.get("description", ""),
        )
        # Heredar metadata edición-nivel.
        if meta.get("publisher"):
            cand.publisher = meta["publisher"]
        if meta.get("language"):
            cand.language = meta["language"]
        if meta.get("country"):
            cand.country = meta["country"]
        if meta.get("author"):
            cand.author = meta["author"]
        # Cover: preferir el del tomo individual; fallback a la portada general.
        cand.image_url = vol.get("image_url", "") or meta.get("image_url", "")
        # Multi-imagen edición-nivel: si la /ediciones/ page expuso una galería
        # con portadas alternativas, se hereda a cada tomo (el merge de
        # candidate_to_json + append_jsonl la deduplica por URL).
        meta_images = meta.get("images") or []
        if len(meta_images) > 1:
            cand.images = list(meta_images)
        candidates.append(cand)
    return candidates


# ---------------------------------------------------------------------------
# Publisher pages — listan /ediciones/ del editor, no productos directos
# ---------------------------------------------------------------------------

_PUBLISHER_PATH_RE = re.compile(
    r"^https?://(?:[a-z]+\.)?whakoom\.com/publisher/\d+/",
    re.IGNORECASE,
)


def is_whakoom_publisher_url(url: str) -> bool:
    """¿Es una URL `/publisher/<id>/<slug>` de Whakoom?

    Estas páginas listan todas las /ediciones/ de un editor — son
    índices puros, NO productos.
    """
    if not url:
        return False
    return bool(_PUBLISHER_PATH_RE.match(url))


def expand_whakoom_publisher_url(
    publisher_url: str,
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
    sleep_seconds: float = 1.5,
    publisher_html: str | None = None,
) -> list[Candidate]:
    """Expande una página /publisher/ extrayendo sus /ediciones/ + tomos.

    Estrategia: fetch publisher page → extraer todas las URLs
    `/ediciones/<id>/...` linkeadas → para cada una, llamar a
    `expand_whakoom_edition` (que a su vez devuelve N tomos).

    Levanta `WhakoomBlocked` si Cloudflare bloquea en cualquier punto.
    """
    if publisher_html is None:
        publisher_html = fetch_url(publisher_url, session, timeout=timeout)
        if not publisher_html:
            return []
    pairs = extract_ediciones_urls_from_html(publisher_html)
    if not pairs:
        return []
    all_cands: list[Candidate] = []
    for n, (_ed_id, ed_url) in enumerate(pairs):
        if n > 0 and sleep_seconds > 0:
            time.sleep(sleep_seconds)
        try:
            cands = expand_whakoom_edition(
                ed_url, session, timeout=timeout, sleep_seconds=sleep_seconds,
            )
        except WhakoomBlocked:
            raise
        all_cands.extend(cands)
    return all_cands


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
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
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
            flush_fn=flush_fn,
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
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
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

    # Nivel 3: cada /ediciones/N → N Candidates (uno por tomo) + descubrir
    # variantes hermanas. Una /ediciones/ no es un item: es una colección
    # (ej. "Berserk Deluxe Edition" tiene 14 tomos), así que la expandimos
    # vía expand_whakoom_edition() y guardamos un candidate por cada
    # /comics/<X>/<slug>/<vol>. Esto evita registrar series enteras como
    # un solo registro en items.jsonl.
    edition_cap = max(max_editions, len(seen_ediciones))
    print(f"[WHAKOOM] Fase 3: fetch + expand {len(ediciones_queue)} ediciones (cap={edition_cap})")
    candidates: list[Candidate] = []
    queue_idx = 0
    while queue_idx < len(ediciones_queue) and len(seen_ediciones) <= edition_cap:
        ed_url = ediciones_queue[queue_idx]
        queue_idx += 1
        # Fetch página principal solo una vez para descubrir hermanas + expandir.
        text = fetch_url(ed_url, session, timeout=timeout)
        if not text:
            continue

        # Expandir edición en N candidates (uno por tomo). fetch_todos=True
        # implica una segunda HTTP request para /todos cuando la edición
        # supera los ~11 tomos de la página principal.
        expanded = expand_whakoom_edition(
            ed_url, session, timeout=timeout, sleep_seconds=sleep_seconds,
            edition_html=text,  # ya lo tenemos descargado
        )
        edition_new: list[Candidate] = []
        for cand in expanded:
            is_m, _ = is_likely_manga(
                cand.title, cand.description,
                source_purity="mixed", publisher=cand.publisher,
            )
            if is_m:
                scored = score_candidate(cand)
                candidates.append(scored)
                edition_new.append(scored)
        if flush_fn and edition_new:
            flush_fn(edition_new)

        # Descubrir variantes hermanas (BFS shallow) — desde el HTML principal,
        # no necesitamos refetchearlo.
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
