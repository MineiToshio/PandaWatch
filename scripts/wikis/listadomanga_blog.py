"""Parser del archivo histórico del BLOG de listadomanga.es.

Diferencia con `listadomanga.py` (calendario):
- listadomanga.py → calendario de lanzamientos por mes (productos).
- listadomanga_blog.py (este) → entradas del BLOG (anuncios, exclusivas
  retailer, ediciones limitadas, cross-posts de Threads/FB de editoriales).

Estructura del HTML (https://www.listadomanga.es/blog/YYYY/MM/page/N/):

    <div class="post-NNNNN post type-post status-publish format-standard hentry ...">
      <h3 id="post-NNNNN">
        <a href="https://www.listadomanga.es/blog/2024/06/28/grupo-anaya-...">
          Grupo Anaya empezará a publicar manga como Pika Ediciones
        </a>
      </h3>
      <small>28 de junio de 2024 por Listado Manga</small>
      <div class="entry">
        <p>Texto del post...</p>
        ...
      </div>
    </div>

10 posts por página. Paginación vía /page/2/, /page/3/, etc. — link al pie
de la página dice "« Entradas anteriores".

Diferencial vs Bootstrap:
- DIFERENCIAL: usar el RSS feed (ES - Listado Manga Blog RSS en sources.yml,
  kind:rss) — trae los ~10 posts más recientes en cada scrape regular.
- BOOTSTRAP: usar este módulo (--bootstrap-wiki listadomanga-blog) — recorre
  el archivo histórico mes por mes desde 2009-11 hasta hoy. Se corre una
  sola vez (o por backfill puntual) para popular items históricos.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

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


BASE_URL = "https://www.listadomanga.es/"
ARCHIVE_URL_TEMPLATE = "https://www.listadomanga.es/blog/{year}/{month:02d}/"
ARCHIVE_PAGE_URL_TEMPLATE = "https://www.listadomanga.es/blog/{year}/{month:02d}/page/{page}/"

# Fecha mínima del archivo (verificado manualmente — el blog arrancó nov 2009).
ARCHIVE_START = (2009, 11)


def _virtual_source() -> Source:
    """Source virtual para que candidate_from_source rellene metadata coherente."""
    return Source(
        name="ListadoManga (blog histórico)",
        country="España",
        language="Español",
        publisher="Varias editoriales",
        source_class="trusted_media",
        kind="html",
        url=BASE_URL,
        tags=["wiki", "listadomanga", "blog", "spain", "manga"],
        purity="manga_only",
    )


def parse_archive_page(html_text: str, source_url: str = BASE_URL) -> list[Candidate]:
    """Parsea una página del archivo (`/blog/YYYY/MM/[page/N/]`).

    Cada `div.post.hentry` se convierte en un Candidate. Title del post +
    excerpt (primer párrafo del `div.entry`) van como title+description.
    El link al post es la URL canónica del item.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    candidates: list[Candidate] = []
    source = _virtual_source()

    for post in soup.select("div.post.hentry"):
        # Title + link en h3 > a
        h3 = post.select_one("h3")
        if h3 is None:
            continue
        anchor = h3.find("a")
        if anchor is None:
            continue
        title = clean_text(anchor.get_text(" ", strip=True))
        if not title:
            continue
        link = anchor.get("href", "")
        if link:
            link = urljoin(source_url, link)
        else:
            continue

        # Date: <small>28 de junio de 2024 por Listado Manga</small>
        published_at = ""
        small = post.find("small")
        if small is not None:
            small_text = clean_text(small.get_text(" ", strip=True))
            # Solo conservamos la parte de la fecha
            m = re.match(r"^([\d]{1,2}\s+de\s+\w+\s+de\s+\d{4})", small_text)
            published_at = m.group(1) if m else small_text

        # Excerpt: primer párrafo significativo de div.entry.
        # Limitamos a ~600 chars para no inflar la description con el post entero.
        excerpt = ""
        entry = post.select_one("div.entry")
        if entry is not None:
            paragraphs = entry.find_all("p", limit=4)
            chunks: list[str] = []
            for p in paragraphs:
                text = clean_text(p.get_text(" ", strip=True))
                if text:
                    chunks.append(text)
                if sum(len(c) for c in chunks) > 600:
                    break
            excerpt = " ".join(chunks)[:800]

        # Categorías WordPress (post-NNNNN ... category-pika category-anaya):
        # se exponen en class="" del div.post — útiles como tags semánticos
        # adicionales para que el scoring pueda usarlos.
        post_classes = post.get("class") or []
        category_tags = [
            f"category:{c[len('category-'):]}"
            for c in post_classes
            if c.startswith("category-") and len(c) > len("category-")
        ]

        cand = candidate_from_source(
            source, title, link, excerpt, published_at=published_at,
        )
        if category_tags:
            cand.tags = list(cand.tags or []) + category_tags
        candidates.append(cand)
    return candidates


def fetch_archive_month(
    year: int,
    month: int,
    session: requests.Session,
    timeout: tuple[int, int] = (10, 30),
    max_pages: int = 10,
    sleep_between_pages: float = 0.5,
) -> list[Candidate]:
    """Descarga + parsea TODAS las páginas de un mes del archivo del blog.

    El blog tiene 10 posts por página. Paginación interna /page/N/ hasta que
    la página devuelve 404 o 0 posts (lo que ocurra primero). `max_pages`
    es un safety cap (rara vez un mes excede 3-4 páginas = 30-40 posts).
    """
    import time
    all_candidates: list[Candidate] = []
    seen_links: set[str] = set()

    for page in range(1, max_pages + 1):
        if page == 1:
            url = ARCHIVE_URL_TEMPLATE.format(year=year, month=month)
        else:
            url = ARCHIVE_PAGE_URL_TEMPLATE.format(
                year=year, month=month, page=page,
            )
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code == 404:
                break
            response.raise_for_status()
            if not response.encoding:
                response.encoding = response.apparent_encoding
            text = response.text
        except requests.RequestException:
            break

        page_candidates = parse_archive_page(text, source_url=url)
        if not page_candidates:
            break

        new_in_page = 0
        for c in page_candidates:
            if c.url in seen_links:
                continue
            seen_links.add(c.url)
            all_candidates.append(c)
            new_in_page += 1
        # Si la página no aportó nada nuevo (mismo set que página anterior →
        # paginación rota), cortamos.
        if new_in_page == 0:
            break

        if sleep_between_pages > 0:
            time.sleep(sleep_between_pages)

    # Filtro non-manga + score.
    scored: list[Candidate] = []
    for c in all_candidates:
        is_m, _ = is_likely_manga(
            c.title, c.description, tags=c.tags,
            source_purity="manga_only", publisher="",
        )
        if not is_m:
            continue
        scored.append(score_candidate(c))
    return scored


def iter_year_months(
    year_from: int, month_from: int, year_to: int, month_to: int,
) -> list[tuple[int, int]]:
    """Itera (year, month) en orden ascendente. Inclusivo en ambos extremos."""
    pairs: list[tuple[int, int]] = []
    y, m = year_from, month_from
    while (y, m) <= (year_to, month_to):
        pairs.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
        if y > year_to + 5:  # safety
            break
    return pairs


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
) -> list[Candidate]:
    """Recorre meses entre [from, to] y devuelve candidates scored.

    Sólo retorna items con score >= min_score.

    Notas:
    - El blog publica ~10-30 posts/mes desde 2009-11. Cubrir todo el archivo
      (~199 meses a fecha 2026-05) toma ~30-60 min con sleep 0.5s.
    - `fetch_details` no aplica aquí (cada post YA fue parseado completo
      desde el archivo, no necesita un segundo GET).
    """
    import time
    all_candidates: list[Candidate] = []
    pairs = iter_year_months(year_from, month_from, year_to, month_to)
    for idx, (y, m) in enumerate(pairs, start=1):
        print(f"[{idx}/{len(pairs)}] ListadoManga Blog {y}-{m:02d}")
        cands = fetch_archive_month(y, m, session, timeout=timeout)
        kept = [c for c in cands if c.score >= min_score]
        print(f"    {len(cands)} posts totales, {len(kept)} con score >= {min_score}")
        all_candidates.extend(kept)
        if sleep_seconds > 0 and idx < len(pairs):
            time.sleep(sleep_seconds)

    print(f"\n[OK] Total: {len(all_candidates)} posts coleccionables")
    return all_candidates
