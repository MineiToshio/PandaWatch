#!/usr/bin/env python3
"""search_discovery.py — descubre items vía search engines (Gemini + DDG).

Cubre el gap de discovery que ningún source directo cubre:
- Whakoom catalog (sólo Google indexa /ediciones/{N}; DDG no).
- Fnac / Casa del Libro / Amazon ES (bloquean scraping pero Google indexa).
- Posts sociales (FB/Reddit/Twitter públicos).
- Lore-words específicas a series ("Beherit Edition", "Tarot Edition").

Estrategia de motores:
- Gemini API con "Grounding with Google Search" tool: free 500-1500 RPD
  (sin tarjeta), devuelve URLs reales del index de Google. Único motor
  que ve whakoom.com profundo. Requiere GEMINI_API_KEY en env.
  (NOTA: el viejo Custom Search JSON API está cerrado a nuevos clientes
  desde 2025; Gemini grounding es el reemplazo oficial de Google.)
- DuckDuckGo HTML scraping: free, sin API. Buen complemento para Reddit,
  blog posts, social. NO sirve para whakoom (no lo indexa).

Cada query en data/search_queries.yml declara qué engines acepta. El runner
prueba en orden — primer engine con resultados gana.

Uso:
    # Necesita GEMINI_API_KEY exportado (para queries que requieran Google)
    python scripts/retrofit/search_discovery.py
    python scripts/retrofit/search_discovery.py --dry-run
    python scripts/retrofit/search_discovery.py --engines ddg    # solo DDG
    python scripts/retrofit/search_discovery.py --limit 5        # primeras 5 queries
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any

import requests
import yaml
from dotenv import load_dotenv

# Cargar variables desde .env del root del proyecto si existe (no falla si no
# está — vars también pueden venir del environment del shell).
load_dotenv()

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# Misma estrategia de fallback que los wikis: scripts.manga_watch (con paquete)
# si conftest agregó ROOT a sys.path; manga_watch (sin paquete) si corremos el
# script directo desde scripts/ con _SCRIPTS en sys.path.
try:
    from scripts.manga_watch import (  # type: ignore[import-not-found]
        Candidate,
        Source,
        candidate_from_source,
        fetch_metadata_from_detail,
        is_collectible_edition,
        is_likely_manga,
        score_candidate,
        candidate_to_json,
        derive_product_type,
        detect_signals,
        make_session,
    )
    from scripts.wikis.whakoom import (  # type: ignore[import-not-found]
        WhakoomBlocked,
        expand_whakoom_edition,
        expand_whakoom_publisher_url,
        is_whakoom_edition_url,
        is_whakoom_publisher_url,
    )
except ImportError:
    from manga_watch import (  # type: ignore[no-redef]
        Candidate,
        Source,
        candidate_from_source,
        fetch_metadata_from_detail,
        is_collectible_edition,
        is_likely_manga,
        score_candidate,
        candidate_to_json,
        derive_product_type,
        detect_signals,
        make_session,
    )
    from wikis.whakoom import (  # type: ignore[no-redef]
        WhakoomBlocked,
        expand_whakoom_edition,
        expand_whakoom_publisher_url,
        is_whakoom_edition_url,
        is_whakoom_publisher_url,
    )


DEFAULT_QUERIES_FILE = Path("data/search_queries.yml")
DEFAULT_ITEMS_FILE = Path("data/items.jsonl")

# DDG es estricto con queries `site:*`. 3s causaba 202 (soft rate-limit)
# en runs reales. 7s = ~8/min, conservador.
DEFAULT_SLEEP_DDG = 7.0
# Gemini 2.5 Flash free tier: 15 RPM TPM + 500 RPD shared. PERO grounding
# cobra por cada Google search interno que el modelo decide hacer (puede
# ser 5-10 por prompt). Las quotas reales se queman en ~10-15 prompts.
# Sleep 4.5s respeta 15 RPM pero no es lo que se agota — es la quota diaria.
DEFAULT_SLEEP_GEMINI = 4.5
# Tavily: 1k búsquedas/mes free, sin rate-limit por minuto agresivo.
# 1s entre queries es más que suficiente.
DEFAULT_SLEEP_TAVILY = 1.0


# -----------------------------------------------------------------------------
# Engines
# -----------------------------------------------------------------------------

class SearchEngineError(Exception):
    """Error transitorio del search engine (rate-limit, captcha, etc.)."""


# Default model. Flash es free 500-1500 RPD en 2026, suficiente para 50-200
# queries/run × varios runs/día. Pro tiene más capacidades pero el grounding
# no es gratis en Pro.
_GEMINI_MODEL = "gemini-2.5-flash"


def _resolve_vertex_redirect(
    redirect_url: str,
    session: requests.Session,
    timeout: tuple[int, int] = (5, 10),
) -> str:
    """Resuelve un redirect de Vertex AI Search a la URL final del sitio.

    Las URLs que devuelve Gemini en `groundingChunks[].web.uri` son
    wrappers tipo `https://vertexaisearch.cloud.google.com/grounding-api
    -redirect/AUZ...` que expiran rápido (típicamente <5 min). Hay que
    seguirlos en el momento para obtener la URL canónica del sitio.

    Devuelve la URL final o "" si el redirect falla / expiró.
    """
    try:
        r = session.get(redirect_url, allow_redirects=True, timeout=timeout)
    except requests.RequestException:
        return ""
    if r.status_code != 200:
        return ""
    return r.url


def search_gemini_grounding(
    query: str,
    api_key: str,
    model: str = _GEMINI_MODEL,
    num: int = 10,
    timeout: tuple[int, int] = (10, 30),
    resolve_redirects: bool = True,
) -> list[dict[str, str]]:
    """Gemini API con "Grounding with Google Search" tool.

    El modelo decide qué buscar en Google y devuelve `groundingChunks` con
    `{web: {uri, title}}`. PERO el `uri` es un wrapper de Vertex AI Search
    (`vertexaisearch.cloud.google.com/grounding-api-redirect/...`) que
    expira en minutos. Nosotros seguimos cada redirect inmediatamente para
    obtener la URL canónica del sitio (caro pero necesario — N+1 requests
    por query).

    Free tier (2026): Gemini 2.5 Flash = 500 RPD compartido + 15 RPM,
    grounding incluido sin costo extra. Sin tarjeta de crédito.

    Args:
        query: prompt para el modelo. Le pedimos que liste resultados
            crudos sin analizarlos.
        api_key: GEMINI_API_KEY (de https://aistudio.google.com).
        num: max URLs a extraer del `groundingChunks` (Gemini no lo
            limita explícitamente; típico 5-20 chunks por query).
        resolve_redirects: si True (default), seguir los redirects de
            Vertex para obtener URLs canónicas. False para tests.

    Raises:
        SearchEngineError: en caso de 429 (quota), 401/403 (auth), o
            otro error transitorio.
    """
    if not api_key:
        raise SearchEngineError("GEMINI_API_KEY no configurada")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    # Prompt deliberadamente seco: queremos que el modelo BUSQUE y nos
    # devuelva resultados, no que los resuma/analice. Lo importante es lo
    # que aparece en groundingChunks, no el texto generado.
    prompt = (
        f"Search the web for: {query}\n\n"
        "Return a brief list of the most relevant pages found. "
        "Don't analyze the content, just list them."
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
    }
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(
            url, headers=headers, json=body, timeout=timeout,
        )
    except requests.RequestException as exc:
        raise SearchEngineError(f"HTTP error: {exc}") from exc
    if response.status_code == 429:
        raise SearchEngineError("Gemini quota exhausted (429)")
    if response.status_code in (401, 403):
        try:
            err = response.json().get("error", {}).get("message", "")
        except (ValueError, KeyError):
            err = ""
        raise SearchEngineError(f"Gemini auth {response.status_code}: {err}")
    if response.status_code != 200:
        raise SearchEngineError(f"Gemini HTTP {response.status_code}")
    try:
        data = response.json()
    except (ValueError, KeyError):
        return []
    raw_results = parse_gemini_grounding_response(data, max_results=num)
    if not resolve_redirects:
        return raw_results

    # Resolver redirects de Vertex inmediatamente — expiran en minutos.
    redirect_session = requests.Session()
    redirect_session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
    })
    resolved: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for r in raw_results:
        original = r.get("url", "")
        if "vertexaisearch.cloud.google.com" in original:
            real_url = _resolve_vertex_redirect(original, redirect_session)
            if not real_url:
                continue  # redirect falló / expiró
        else:
            real_url = original
        if real_url in seen_urls:
            continue
        seen_urls.add(real_url)
        resolved.append({
            "url": real_url,
            "title": r.get("title", ""),
            "snippet": r.get("snippet", ""),
        })
    return resolved


def parse_gemini_grounding_response(
    data: dict, max_results: int = 10,
) -> list[dict[str, str]]:
    """Extrae [{url,title,snippet}] de la respuesta de Gemini.

    Path: response.candidates[0].groundingMetadata.groundingChunks[i].web.uri/title

    El `snippet` lo dejamos vacío — Gemini no expone snippets por chunk.
    El title viene del propio web.title del result, no del AI generated text.
    """
    out: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    candidates = data.get("candidates") or []
    if not candidates:
        return out
    metadata = (candidates[0] or {}).get("groundingMetadata") or {}
    chunks = metadata.get("groundingChunks") or []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        web = chunk.get("web") or {}
        uri = (web.get("uri") or "").strip()
        title = (web.get("title") or "").strip()
        if not uri or uri in seen_urls:
            continue
        seen_urls.add(uri)
        out.append({"url": uri, "title": title, "snippet": ""})
        if len(out) >= max_results:
            break
    return out


def search_tavily(
    query: str,
    api_key: str,
    num: int = 10,
    timeout: tuple[int, int] = (10, 30),
) -> list[dict[str, str]]:
    """Tavily Search API. Free tier: 1,000 búsquedas/mes (sin tarjeta).

    Devuelve [{'url','title','snippet'}] directamente — sin redirects, sin
    parsing HTML. Tavily está optimizado para AI agents, su index es
    propio (no Google, no Bing) pero cubre web pública decentemente.

    Caso de uso: fallback cuando Gemini quota se agota (Gemini cobra por
    búsqueda interna del modelo, se va rápido). Tavily NO ve whakoom
    profundo (no es Google), pero sí Reddit, Fnac, retailers comunes.
    """
    if not api_key:
        raise SearchEngineError("TAVILY_API_KEY no configurada")
    try:
        response = requests.post(
            "https://api.tavily.com/search",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "search_depth": "basic",   # más barato que "advanced"
                "max_results": max(1, min(num, 20)),
                "include_answer": False,   # ahorra tokens
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise SearchEngineError(f"HTTP error: {exc}") from exc
    if response.status_code == 429:
        raise SearchEngineError("Tavily rate-limit (429)")
    if response.status_code in (401, 403):
        raise SearchEngineError(f"Tavily auth {response.status_code}")
    if response.status_code != 200:
        raise SearchEngineError(f"Tavily HTTP {response.status_code}")
    try:
        data = response.json()
    except (ValueError, KeyError):
        return []
    return parse_tavily_response(data, max_results=num)


def parse_tavily_response(
    data: dict, max_results: int = 10,
) -> list[dict[str, str]]:
    """Extrae [{url,title,snippet}] del response de Tavily.

    Path: response.results[].url / .title / .content
    """
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for r in data.get("results", []) or []:
        if not isinstance(r, dict):
            continue
        url = (r.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append({
            "url": url,
            "title": (r.get("title") or "").strip(),
            "snippet": (r.get("content") or "").strip()[:300],
        })
        if len(out) >= max_results:
            break
    return out


_DDG_REDIRECT_RE = re.compile(r"uddg=([^&\"]+)")
_DDG_RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>',
    re.DOTALL,
)
_DDG_SNIPPET_RE = re.compile(
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL,
)


def search_ddg_html(
    query: str,
    num: int = 10,
    timeout: tuple[int, int] = (10, 20),
) -> list[dict[str, str]]:
    """DuckDuckGo HTML scraping. Free, sin API.

    Limitaciones:
    - NO indexa whakoom.com/ediciones (usa Bing+propio).
    - Sí indexa Reddit, blog posts, FB/Twitter público.
    - ~10-50 queries/min antes de rate-limit ligero.
    """
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise SearchEngineError(f"HTTP error: {exc}") from exc
    if response.status_code == 429:
        raise SearchEngineError("DDG rate-limit (429)")
    # 202 Accepted: DDG soft-rate-limit / captcha placeholder. Esperar 1h
    # antes de reintentar — insistir empeora.
    if response.status_code == 202:
        raise SearchEngineError(
            "DDG HTTP 202 (soft rate-limit) — esperá ~1h o usá Google"
        )
    if response.status_code != 200:
        raise SearchEngineError(f"DDG HTTP {response.status_code}")
    text = response.text
    return parse_ddg_html(text, max_results=num)


def parse_ddg_html(html_text: str, max_results: int = 10) -> list[dict[str, str]]:
    """Parser puro del HTML de DuckDuckGo — extraído para testear sin red.

    DDG envuelve URLs en redirects `//duckduckgo.com/l/?uddg=<URL>` para
    tracking. Resolvemos a la URL real decodificando uddg.
    """
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    # Buscar bloques de result__a
    for m in _DDG_RESULT_RE.finditer(html_text):
        href = m.group(1)
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
        # Resolver redirect uddg
        rm = _DDG_REDIRECT_RE.search(href)
        if rm:
            real_url = urllib.parse.unquote(rm.group(1))
        else:
            real_url = href
        # Saltar URLs internas de DDG
        if real_url.startswith("//") or "duckduckgo.com" in real_url:
            continue
        if real_url in seen_urls:
            continue
        seen_urls.add(real_url)
        results.append({"url": real_url, "title": title, "snippet": ""})
        if len(results) >= max_results:
            break
    return results


# -----------------------------------------------------------------------------
# Discovery runner
# -----------------------------------------------------------------------------

def url_already_known(url: str, known_urls: set[str]) -> bool:
    """Dedup contra items existentes (por URL normalizada simple)."""
    try:
        from scripts.manga_watch import normalize_url_for_dedup  # type: ignore[import-not-found]
    except ImportError:
        from manga_watch import normalize_url_for_dedup  # type: ignore[no-redef]
    return normalize_url_for_dedup(url) in known_urls


# URLs que NUNCA son productos individuales (listas curadas, videos, foros,
# soporte, etc.). Tavily a veces las devuelve y desperdiciamos un detail-fetch
# por nada. Filtrarlas upstream ahorra HTTP requests + reduce falsos positivos.
_URL_BLACKLIST_PATTERNS = re.compile(
    r"/lists?/"               # /lists/X (user-curated lists)
    r"|/collection(?:/|$)"    # /collection/ user pages
    r"|/profile/"             # social profiles
    r"|/news?titles?(?:/|$)"  # /newtitles (catalog index, no specific item)
    r"|youtube\.com/watch"    # YouTube videos
    r"|youtube\.com/shorts/"  # YouTube Shorts
    r"|youtu\.be/"            # YouTube short
    r"|reddit\.com/r/[^/]+/comments/"  # Reddit threads (no products)
    r"|zendesk\.com"          # support forums
    r"|/community/"           # community posts
    r"|wikipedia\.org/wiki/"  # wikipedia
    r"|/help/|/support/"      # help pages
    r"|tiktok\.com/"          # TikTok
    r"|instagram\.com/(?:p|reel|tv)/"  # Instagram posts / reels / IGTV
    r"|facebook\.com/[^/]+/(?:posts|videos|reel)/"  # FB posts / videos / reels
    r"|threads\.net/"         # Threads (Meta)
    r"|twitter\.com/[^/]+/status/"   # tweets
    r"|x\.com/[^/]+/status/"
    r"|/comments/"            # generic comment threads
    r"|/blog/.+/page/"        # blog pagination index (not the post)
    # --- Páginas-índice descubiertas en auditoría (gotcha #14):
    # OJO: NO bloqueamos whakoom.com/publisher/ aquí — esas se expanden
    # en el loop de process_query (ver expand_whakoom_publisher_url).
    r"|whakoom\.com/(?:autores|tag)/"  # índices Whakoom (autores/tags)
    r"|/blogs/news/"           # Shopify blogs/news (anuncios editoriales)
    r"|/collections/[^/?#]+/?$"  # /collections/X sin /products/Y
    , re.IGNORECASE,
)


def url_is_useful(url: str) -> bool:
    """¿Esta URL parece ser de un producto/edición específica?

    Devuelve False para listas curadas, videos, foros y otros formatos
    que nunca corresponden a un item individual coleccionable.
    """
    if not url:
        return False
    return not _URL_BLACKLIST_PATTERNS.search(url)


def candidate_from_search_result(
    url: str,
    snippet_title: str,
    snippet_text: str,
    query: str,
    engine: str,
    session: requests.Session,
    timeout: tuple[int, int],
) -> Candidate | None:
    """Convierte un resultado de search en Candidate vía detail-fetch.

    El title/snippet del search engine son backup si el detail-fetch falla.
    """
    # Source virtual para que aparezca atribuido a la búsqueda.
    domain = urllib.parse.urlparse(url).netloc
    source = Source(
        name=f"SEARCH - {engine} ({domain})",
        country="",
        language="",
        publisher="",
        source_class="trusted_media",
        kind="html",
        url=url,
        tags=["search", f"engine:{engine}", f"query:{query[:60]}"],
        purity="mixed",
    )

    # Intentar detail-fetch para metadata real (OG tags, JSON-LD, etc.)
    try:
        md = fetch_metadata_from_detail(url, session, timeout=timeout)
    except Exception:
        md = {}

    title = (md.get("name") or "").strip() or snippet_title
    if not title:
        return None
    description = (md.get("description") or "").strip() or snippet_text
    cand = candidate_from_source(source, title, url, description)
    # Rellenar metadata si la detail-fetch la trae
    for field in ("image_url", "price", "release_date", "author", "isbn", "publisher"):
        val = md.get(field)
        if val:
            setattr(cand, field, val)
    return cand


def process_query(
    query: dict,
    engines_avail: dict[str, dict],
    session: requests.Session,
    known_urls: set[str],
    timeout: tuple[int, int],
    sleep_ddg: float,
    sleep_google: float,
    max_results: int = 10,
) -> tuple[list[Candidate], str, int]:
    """Procesa una query: intenta cada engine en orden hasta éxito.

    Returns: (candidates_kept, engine_used, results_count).
    """
    q_text = query.get("q", "")
    if not q_text:
        return [], "", 0
    engines_pref = query.get("engines") or ["google", "ddg"]

    results: list[dict[str, str]] = []
    engine_used = ""
    last_error = ""
    for engine in engines_pref:
        if engine not in engines_avail:
            continue
        cfg = engines_avail[engine]
        try:
            if engine in ("gemini", "google"):  # "google" alias por compat con yamls viejos
                results = search_gemini_grounding(
                    q_text, cfg["api_key"], model=cfg.get("model", _GEMINI_MODEL),
                    num=max_results, timeout=timeout,
                )
            elif engine == "tavily":
                results = search_tavily(
                    q_text, cfg["api_key"], num=max_results, timeout=timeout,
                )
            elif engine == "ddg":
                results = search_ddg_html(q_text, num=max_results, timeout=timeout)
        except SearchEngineError as exc:
            last_error = f"{engine}: {exc}"
            continue
        if results:
            engine_used = engine
            break

    if not results:
        print(f"    [{engine_used or 'none'}] 0 results ({last_error or 'no engine worked'})")
        return [], engine_used, 0

    print(f"    [{engine_used}] {len(results)} results — processing...")

    # Sleep según engine usado (después de hacer la query, antes de la siguiente).
    if engine_used == "ddg":
        sleep_after = sleep_ddg
    elif engine_used == "tavily":
        sleep_after = DEFAULT_SLEEP_TAVILY
    else:  # gemini / google
        sleep_after = sleep_google

    kept: list[Candidate] = []
    skipped_blacklist = 0
    skipped_whakoom_blocked = False
    for r in results:
        url = r.get("url", "")
        if not url:
            continue
        if not url_is_useful(url):
            skipped_blacklist += 1
            continue
        if url_already_known(url, known_urls):
            continue

        # Whakoom /ediciones/<id>/<slug> es un índice (toda la edición),
        # no un tomo individual. Hay que expandirla en N candidates
        # (uno por /comics/<X>/<slug>/<vol>) antes de evaluar filtros.
        # Whakoom /publisher/<id>/<slug> es la página del editor: expone
        # las /ediciones/ del editor, así que se expande dos niveles
        # (publisher → ediciones → tomos). Ver gotcha #14 en CLAUDE.md.
        if is_whakoom_edition_url(url) or is_whakoom_publisher_url(url):
            if skipped_whakoom_blocked:
                continue  # ya fallamos antes en este batch, no insistir
            try:
                if is_whakoom_publisher_url(url):
                    expanded = expand_whakoom_publisher_url(
                        url, session, timeout=timeout, sleep_seconds=1.5,
                    )
                else:
                    expanded = expand_whakoom_edition(
                        url, session, timeout=timeout, sleep_seconds=1.5,
                    )
            except WhakoomBlocked:
                print(f"    [whakoom] Cloudflare challenge en {url[:60]} — "
                      f"saltando resto de URLs whakoom en esta query")
                skipped_whakoom_blocked = True
                continue
            cands_to_process = expanded
            # Marcar la URL padre como conocida también, para no re-procesarla
            known_urls.add(url)
        else:
            cand = candidate_from_search_result(
                url, r.get("title", ""), r.get("snippet", ""),
                q_text, engine_used, session, timeout,
            )
            cands_to_process = [cand] if cand is not None else []

        for cand in cands_to_process:
            if cand is None:
                continue
            if url_already_known(cand.url, known_urls):
                continue
            is_m, _ = is_likely_manga(
                cand.title, cand.description, tags=cand.tags,
                source_purity="mixed", publisher=cand.publisher,
                url=cand.url,
            )
            if not is_m:
                continue
            score_candidate(cand)
            is_c, _ = is_collectible_edition(
                cand.title, cand.description, cand.signal_types, cand.product_type,
                tags=cand.tags, isbn=cand.isbn, url=cand.url,
            )
            if not is_c:
                continue
            kept.append(cand)
            known_urls.add(cand.url)
        # Sleep entre detail-fetches dentro de la misma query
        time.sleep(0.3)

    if skipped_blacklist:
        print(f"    (saltadas {skipped_blacklist} URLs no-producto: listas/videos/foros)")

    # Sleep entre queries (respetando rate del engine usado)
    time.sleep(sleep_after)
    return kept, engine_used, len(results)


def load_known_urls(items_path: Path) -> set[str]:
    """Carga URLs ya conocidas para dedupear search results."""
    try:
        from scripts.manga_watch import normalize_url_for_dedup  # type: ignore[import-not-found]
    except ImportError:
        from manga_watch import normalize_url_for_dedup  # type: ignore[no-redef]
    known: set[str] = set()
    if not items_path.exists():
        return known
    for line in items_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            it = json.loads(line)
        except json.JSONDecodeError:
            continue
        u = it.get("url", "")
        if u:
            known.add(normalize_url_for_dedup(u))
    return known


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--queries-file", default=str(DEFAULT_QUERIES_FILE))
    p.add_argument("--items-file", default=str(DEFAULT_ITEMS_FILE))
    p.add_argument(
        "--engines", default="",
        help="Restringir a estos engines (csv). Ej. --engines ddg. Default: respeta el archivo de queries.",
    )
    p.add_argument("--limit", type=int, default=0, help="Procesar solo las primeras N queries.")
    p.add_argument("--sleep-ddg", type=float, default=DEFAULT_SLEEP_DDG)
    p.add_argument(
        "--sleep-google", type=float, default=DEFAULT_SLEEP_GEMINI,
        help="Segundos entre queries a Gemini. Default 4.5 (15 RPM free tier).",
    )
    p.add_argument("--connect-timeout", type=int, default=10)
    p.add_argument("--read-timeout", type=int, default=20)
    p.add_argument("--max-results", type=int, default=10, help="Max URLs por query (Google cap=10).")
    p.add_argument("--dry-run", action="store_true",
                   help="No fetchea ni escribe; solo lista las queries a correr.")
    args = p.parse_args()

    # Cargar queries
    qpath = Path(args.queries_file)
    if not qpath.exists():
        print(f"[ERROR] no existe {qpath}", file=sys.stderr)
        return 1
    with qpath.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    queries = data.get("queries") or []
    if not queries:
        print(f"[ERROR] {qpath} no tiene 'queries'", file=sys.stderr)
        return 1

    # Override engines si CLI lo pide
    if args.engines.strip():
        forced = [e.strip() for e in args.engines.split(",") if e.strip()]
        for q in queries:
            q["engines"] = forced

    if args.limit > 0:
        queries = queries[: args.limit]

    # Engines configurados
    engines_avail: dict[str, dict] = {"ddg": {}}
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_key:
        cfg = {"api_key": gemini_key}
        gemini_model = os.environ.get("GEMINI_MODEL", "").strip()
        if gemini_model:
            cfg["model"] = gemini_model
        engines_avail["gemini"] = cfg
        # Alias 'google' por compat con yamls que aún usan engines:[google].
        engines_avail["google"] = cfg
        print(f"[INFO] Gemini configurado (key={gemini_key[:10]}..., model={cfg.get('model', _GEMINI_MODEL)})")
    else:
        print(f"[WARN] Gemini NO configurado (falta GEMINI_API_KEY).")
        print(f"       Obtené una key gratis en https://aistudio.google.com/")
    tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if tavily_key:
        engines_avail["tavily"] = {"api_key": tavily_key}
        print(f"[INFO] Tavily configurado (key={tavily_key[:12]}..., 1k/mes free)")
    else:
        print(f"[WARN] Tavily NO configurado (falta TAVILY_API_KEY).")
        print(f"       Obtené una key gratis en https://tavily.com (sin tarjeta).")
    print(f"[INFO] Engines disponibles: {sorted(engines_avail.keys())}")
    print(f"[INFO] Queries a procesar: {len(queries)}")

    if args.dry_run:
        print(f"\n[DRY-RUN] Queries:")
        for i, q in enumerate(queries[:20], start=1):
            print(f"  [{i}] engines={q.get('engines')} | {q.get('q','')[:80]}")
        if len(queries) > 20:
            print(f"  ... y {len(queries)-20} más")
        return 0

    timeout = (args.connect_timeout, args.read_timeout)
    session = make_session("Mozilla/5.0 (compatible; manga-watch-search/1.0)")
    items_path = Path(args.items_file)
    known_urls = load_known_urls(items_path)
    print(f"[INFO] URLs conocidas (dedup): {len(known_urls)}")

    engine_counter: Counter[str] = Counter()
    kept_total: list[Candidate] = []
    for idx, q in enumerate(queries, start=1):
        print(f"\n[{idx}/{len(queries)}] {q.get('q','')[:80]}")
        kept, engine_used, n_results = process_query(
            q, engines_avail, session, known_urls, timeout,
            args.sleep_ddg, args.sleep_google, args.max_results,
        )
        engine_counter[engine_used or "skip"] += 1
        kept_total.extend(kept)
        print(f"    → +{len(kept)} candidates kept (acumulado: {len(kept_total)})")

    print(f"\n[OK] Engines usados:")
    for e, n in engine_counter.most_common():
        print(f"  {e:10s}  {n} queries")
    print(f"\n[OK] Total candidates: {len(kept_total)}")

    if not kept_total:
        return 0

    # Append a items.jsonl
    with items_path.open("a", encoding="utf-8") as fh:
        for c in kept_total:
            fh.write(json.dumps(candidate_to_json(c), ensure_ascii=False) + "\n")
    print(f"[OK] Appended {len(kept_total)} items a {items_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
