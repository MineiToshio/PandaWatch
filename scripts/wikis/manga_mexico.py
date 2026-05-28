"""Parser de mangamexico.blogspot.com — catálogo wiki de manga publicado en México.

A diferencia de listadomanga.es (calendario por fecha), Manga México es un
**catálogo** mantenido por la comunidad con la lista completa de mangas
publicados por editoriales mexicanas (Panini México, Editorial Kamite,
Editorial Vid). No tiene calendario por fechas.

Estructura del HTML:

    <div class="post-body">
      ... párrafos introductorios ...
      <ul>
        <li>Akatsuki no Yona (3 en 1) - Volúmenes: 8/15+ ( Publicándose ) |
            Bimestral (Próx. en julio) | Precio actual: 349 MXN</li>
        <li>Akame Ga Kill - Volúmenes: 15/15 ( Finalizado )</li>
        <li>Chainsaw Man - Volúmenes: 19/20+ ( Publicándose ) |
            Sin periodicidad (Próx. indeterminado) | Precio actual: 169 MXN</li>
        ...
      </ul>
    </div>

Cada `<li>` tiene un texto plano con metadata embedded:
  - Título (separado por " - ")
  - "Volúmenes: X/Y[+]" donde Y+ indica que sigue abierta en JP
  - Estado entre paréntesis: Publicándose, Finalizado, Anunciado, Pausado, Licenciado
  - Periodicidad: Mensual, Bimestral, Trimestral, Sin periodicidad
  - "Próx. en <mes>" o "Próx. indeterminado"
  - "Precio actual: X MXN"

API pública (paralela a listadomanga.py):
    parse_catalog_page(html_text, source_url) -> list[Candidate]
    fetch_catalog(url, session, ...) -> list[Candidate]
    bootstrap(session, ...) -> list[Candidate]

Las URLs canónicas de las páginas de catálogo:
  - Panini México: /2015/10/mangas-de-panini-comics.html
  - Editorial Kamite: /2015/10/mangas-de-editorial-kamite.html
  - Editorial Vid: /2015/10/mangas-de-editorial-vid.html
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Callable

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


BASE_URL = "https://mangamexico.blogspot.com"

# Páginas de catálogo canónicas — una por editorial.
CATALOG_URLS = {
    "panini": f"{BASE_URL}/2015/10/mangas-de-panini-comics.html",
    "kamite": f"{BASE_URL}/2015/10/mangas-de-editorial-kamite.html",
    "vid":    f"{BASE_URL}/2015/10/mangas-de-editorial-vid.html",
}


# Regex para extraer metadata del texto de cada <li>.
_RX_VOLS = re.compile(r"Vol[úu]menes?:\s*([\d/+]+)", re.IGNORECASE)
_RX_TOMO_UNICO = re.compile(r"\bTomo[\s\-]?[úu]nico\b", re.IGNORECASE)
_RX_STATUS = re.compile(
    r"\(\s*(Publicándose|Publicandose|Finalizado|Anunciado|Pausado|Licenciado)\s*\)",
    re.IGNORECASE,
)
_RX_PRICE = re.compile(r"Precio\s+actual:\s*([\d.,]+)\s*MXN", re.IGNORECASE)
_RX_PROX = re.compile(r"Pr[óo]x\.?\s+(?:en|para)\s+(\w+)", re.IGNORECASE)
_RX_PERIODICITY = re.compile(
    r"\b(Mensual|Bimestral|Trimestral|Semestral|Anual|Sin\s+periodicidad)\b",
    re.IGNORECASE,
)


def _virtual_source(publisher_slug: str) -> Source:
    """Source sintética con datos de la editorial específica."""
    pretty = {
        "panini": "Panini México",
        "kamite": "Editorial Kamite",
        "vid":    "Editorial Vid",
    }.get(publisher_slug, publisher_slug.title())
    return Source(
        name=f"MX - Manga México ({pretty})",
        url=CATALOG_URLS.get(publisher_slug, BASE_URL),
        country="México",
        language="Español",
        publisher=pretty,
        source_class="trusted_media",
        kind="wiki",
        enabled=True,
        tags=["wiki", "manga-mexico", f"mexico-{publisher_slug}", "catalog"],
        notes=f"mangamexico.blogspot.com catalog page for {pretty}",
        selectors={},
        max_pages=0,
    )


def _parse_volumes(value: str) -> tuple[str, bool]:
    """'8/15+' → ('8/15', True). 'Tomo único' → ('1/1', False)."""
    if "+" in value:
        clean = value.replace("+", "").strip("/")
        return clean, True
    return value.strip("/"), False


def _split_title(text: str) -> tuple[str, str]:
    """Divide 'Akatsuki no Yona (3 en 1) - Volúmenes: 8/15+ ...' en
    (title, metadata). El separador es ' - ' o ' – ' o ' — '."""
    for sep in (" - ", " – ", " — "):
        if sep in text:
            idx = text.index(sep)
            return text[:idx].strip(), text[idx + len(sep):].strip()
    return text.strip(), ""


def parse_catalog_page(
    html_text: str,
    source_url: str = BASE_URL,
    publisher_slug: str = "panini",
) -> list[Candidate]:
    """Parsea una página de catálogo y devuelve candidates por <li>."""
    if not html_text:
        return []
    soup = BeautifulSoup(html_text, "html.parser")
    post = soup.find("div", class_="post-body") or soup.find("article") or soup
    source = _virtual_source(publisher_slug)
    candidates: list[Candidate] = []

    seen_titles: set[str] = set()
    for li in post.find_all("li"):
        text = clean_text(li.get_text(" ", strip=True))
        if not text or len(text) < 4:
            continue

        title, meta = _split_title(text)
        if not title or len(title) < 2 or len(title) > 200:
            continue
        # Skip dup en la misma página (la wiki a veces repite)
        title_key = title.lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        # Metadata extraída del texto
        status = ""
        m_status = _RX_STATUS.search(meta or text)
        if m_status:
            status = m_status.group(1).lower().replace("á", "a")
        volumes_label = ""
        m_vol = _RX_VOLS.search(meta or text)
        if m_vol:
            volumes_label = m_vol.group(1).strip()
        elif _RX_TOMO_UNICO.search(meta or text):
            volumes_label = "tomo único"
        price = ""
        m_price = _RX_PRICE.search(meta or text)
        if m_price:
            price = f"${m_price.group(1)} MXN"
        prox = ""
        m_prox = _RX_PROX.search(meta or text)
        if m_prox:
            prox = m_prox.group(1).lower()
        periodicity = ""
        m_per = _RX_PERIODICITY.search(meta or text)
        if m_per:
            periodicity = m_per.group(1).lower().replace(" ", "_")

        # URL del item: si el <li> tiene <a>, usa esa; sino fabricamos una
        # query única basada en el slug del título para evitar que el dedup
        # (normalize_url_for_dedup descarta fragments) colapse todo el
        # catálogo a un único item.
        a = li.find("a", href=True)
        if a:
            url = a["href"]
        else:
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
            sep = "&" if "?" in source_url else "?"
            url = f"{source_url}{sep}manga={publisher_slug}-{slug}"

        # Tags útiles
        tags = list(source.tags)
        if status:
            tags.append(f"status:{status}")
        if volumes_label:
            tags.append(f"volumes:{volumes_label}")
        if periodicity:
            tags.append(f"periodicity:{periodicity}")
        if prox:
            tags.append(f"next_month:{prox}")

        # Description (sirve también para scoring por señales)
        description = text

        cand = candidate_from_source(
            source, title=title, url=url, description=description,
        )
        cand.publisher = source.publisher
        cand.price = price
        cand.tags = tags
        # Filtro non-manga (rescata art books / packs, descarta merch)
        keep, _ = is_likely_manga(cand.title, cand.description, tags=cand.tags)
        if not keep:
            continue
        score_candidate(cand)
        candidates.append(cand)

    return candidates


def fetch_catalog(
    publisher_slug: str,
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
) -> list[Candidate]:
    url = CATALOG_URLS.get(publisher_slug)
    if not url:
        return []
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        if not response.encoding:
            response.encoding = response.apparent_encoding or "utf-8"
        html_text = response.text
    except (requests.RequestException, Exception):
        return []
    return parse_catalog_page(html_text, source_url=url, publisher_slug=publisher_slug)


# `iter_year_months` solo existe para compatibilidad con el dispatcher de
# `_run_wiki_bootstrap`, que también lo usa para reportar progreso. Devuelve
# una lista trivial (1 entrada por editorial) porque este catálogo no tiene
# semántica de mes/año.
def iter_year_months(
    year_from: int, month_from: int, year_to: int, month_to: int
) -> list[tuple[int, int]]:
    return [(0, i) for i in range(1, len(CATALOG_URLS) + 1)]


def bootstrap(
    year_from: int,
    month_from: int,
    year_to: int,
    month_to: int,
    session: requests.Session,
    sleep_seconds: float = 0.5,
    timeout: tuple[int, int] = (10, 30),
    min_score: int = 30,
    fetch_details: bool = False,
    publishers: tuple[str, ...] = ("panini", "kamite"),
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Recorre las páginas de catálogo (por editorial) y devuelve candidates.

    Los argumentos year/month se ignoran (catálogo no es por mes), pero se
    aceptan para conformar con la interfaz de bootstrap del dispatcher.
    """
    import time
    all_candidates: list[Candidate] = []
    for idx, slug in enumerate(publishers, start=1):
        print(f"[{idx}/{len(publishers)}] MangaMéxico catálogo: {slug}")
        cands = fetch_catalog(slug, session, timeout=timeout)
        kept = [c for c in cands if c.score >= min_score]
        print(f"    {len(cands)} items totales, {len(kept)} con score >= {min_score}")
        all_candidates.extend(kept)
        if flush_fn and kept:
            flush_fn(kept)
        if sleep_seconds > 0 and idx < len(publishers):
            time.sleep(sleep_seconds)
    return all_candidates


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--publisher", choices=list(CATALOG_URLS),
                        default="panini")
    parser.add_argument("--min-score", type=int, default=10)
    args = parser.parse_args()

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; manga-watch-debug)"
    cands = fetch_catalog(args.publisher, s)
    print(f"\nTotal: {len(cands)} candidates")
    kept = [c for c in cands if c.score >= args.min_score]
    print(f"Kept (score>={args.min_score}): {len(kept)}")
    for c in kept[:15]:
        print(f"  [{c.score}] {c.title[:60]}  price={c.price}")
