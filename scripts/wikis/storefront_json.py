"""Storefronts con API JSON — un módulo, N perfiles (2026-06-12).

Cinco tiendas/editoriales exponen su catálogo vía APIs JSON sin auth. En vez
de cinco módulos casi idénticos, UN módulo con PERFILES declarativos (fuente
única de la lógica de paginado/filtrado/mapeo — regla "arreglar el mecanismo"):

| Perfil      | País | Plataforma  | API |
|-------------|------|-------------|-----|
| ``jd-intl``  | HK   | WooCommerce | /wp-json/wc/store/v1/products (paginado X-WP-TotalPages) |
| ``spp-tw``   | TW   | 91APP       | /webapi/SearchV2/GetShopSalePageBySearch (startIndex) |
| ``kimdong``  | VN   | Sapo/Bizweb | /collections/all/products.json?page=N |
| ``ipm``      | VN   | Haravan     | /collections/all/products.json?page=N (cap 50/pág) |
| ``yaakz``    | TH   | Laravel     | /api/products?filter[parent_category_id]=1098 |

Cada perfil define: cómo listar (generador de dicts crudos), cómo mapear un
dict a Candidate, y un filtro de título (debe matchear las señales de
edición especial del idioma — ya en KEYWORD_RULES). El score/gate del
pipeline hace el resto.

Evaluaciones: /watch-evaluate-sources 2026-06-12 (6 auditores; ver fichas
en docs/scraper/sources/ y el handoff mejoras-handoff-20260612.md §10).

API pública (misma firma que los demás wiki parsers)::

    bootstrap_jd_intl / bootstrap_spp / bootstrap_kimdong / bootstrap_ipm /
    bootstrap_yaakz(yf, mf, yt, mt, session, ...) -> list[Candidate]
    iter_year_months(...)                          -> [(yf, mf)] (batch único)
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterator

import requests

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    from scripts.manga_watch import (  # type: ignore[import-not-found]
        Candidate,
        Source,
        candidate_from_source,
        clean_text,
        score_candidate,
    )
except ImportError:
    from manga_watch import (  # type: ignore[no-redef]
        Candidate,
        Source,
        candidate_from_source,
        clean_text,
        score_candidate,
    )

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
}

_ISBN_RE = re.compile(r"ISBN[\s:]*([0-9][0-9\-\s]{8,20}[0-9Xx])", re.IGNORECASE)


def _get_json(session: requests.Session, url: str, params: dict | None = None,
              timeout: tuple[int, int] = (15, 45)) -> Any:
    """GET JSON con 2 reintentos. None si falla."""
    for attempt in range(3):
        try:
            resp = session.get(url, params=params, headers=_HEADERS, timeout=timeout)
            if resp.ok:
                return resp.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1.0 * (attempt + 1))
    return None


# ---------------------------------------------------------------------------
# Perfiles
# ---------------------------------------------------------------------------

def _jd_intl_list(session: requests.Session, sleep: float) -> Iterator[dict]:
    """WooCommerce Store API — catálogo completo (~1246, 13 págs a 100)."""
    page = 1
    while page <= 20:
        data = _get_json(session, "https://jd-intl.com/wp-json/wc/store/v1/products",
                         {"per_page": 100, "page": page, "orderby": "date"})
        if not data:
            break
        yield from data
        if len(data) < 100:
            break
        page += 1
        time.sleep(sleep)


# Marcadores premium de Jade Dynasty (auditoría: 珍藏版 91 + 愛藏版 54 +
# 完全版 128 + 盒裝 17 + 豪華 45 ≈ 300-350 únicos). 新裝版 queda FUERA:
# es re-edición regular (≈ "Nueva Edición", ver stoplist del gate).
_JD_SPECIAL_RE = re.compile(r"珍藏版|愛藏版|完全版|盒裝|豪華|限定|彩色版")


def _jd_intl_map(p: dict, source: Source) -> Candidate | None:
    name = clean_text(p.get("name") or "")
    url = (p.get("permalink") or "").strip()
    if not name or not url:
        return None
    if not _JD_SPECIAL_RE.search(name):
        return None
    desc_html = (p.get("short_description") or "") + " " + (p.get("description") or "")
    desc = clean_text(desc_html)[:1200]
    cand = candidate_from_source(source, title=name, url=url, description=desc)
    imgs = p.get("images") or []
    if imgs and imgs[0].get("src"):
        cand.image_url = imgs[0]["src"]
    m = _ISBN_RE.search(desc_html)
    if m:
        cand.isbn = re.sub(r"[^0-9Xx]", "", m.group(1))
    return cand


_SPP_KEYWORDS = ["限定版", "特裝版", "典藏版", "盒裝"]


def _spp_list(session: requests.Session, sleep: float) -> Iterator[dict]:
    """91APP SearchV2 — paginación server-side real por startIndex."""
    seen: set[Any] = set()
    for kw in _SPP_KEYWORDS:
        start = 0
        while start < 3000:  # TotalSize 限定版 ≈ 2200 (auditoría)
            data = _get_json(
                session,
                "https://www.spp.com.tw/webapi/SearchV2/GetShopSalePageBySearch",
                {"shopId": 41817, "keyword": kw, "order": 2,
                 "startIndex": start, "maxCount": 150},
            )
            # La respuesta envuelve la lista en Data/SalePageList (defensivo:
            # aceptar ambas formas).
            items = []
            if isinstance(data, dict):
                inner = data.get("Data") or data
                items = (inner.get("SalePageList") or inner.get("SalePages")
                         or inner.get("List") or [])
            elif isinstance(data, list):
                items = data
            if not items:
                break
            new = 0
            for it in items:
                pid = it.get("Id") or it.get("SalePageId")
                if pid in seen:
                    continue
                seen.add(pid)
                new += 1
                yield it
            if new == 0 or len(items) < 150:
                break
            start += len(items)
            time.sleep(sleep)


def _spp_map(p: dict, source: Source) -> Candidate | None:
    name = clean_text(p.get("Title") or p.get("title") or "")
    pid = p.get("Id") or p.get("SalePageId")
    if not name or not pid:
        return None
    # Solo qualifiers en el TÍTULO (la búsqueda es full-text; sin esto entra
    # ruido de descripciones — evaluación: 4072 crudos → ~719 netos).
    if not any(kw in name for kw in ("限定版", "特裝版", "典藏", "盒裝")):
        return None
    # Excluir photobooks/novelas/merch evidentes.
    if any(bad in name for bad in ("寫真", "畫冊典藏", "原畫", "複製")):
        return None
    url = f"https://www.spp.com.tw/SalePage/Index/{pid}"
    cand = candidate_from_source(source, title=name, url=url, description="")
    pic = p.get("PicUrl") or p.get("picUrl") or ""
    if pic:
        cand.image_url = pic if pic.startswith("http") else f"https:{pic}"
    return cand


_VN_SPECIAL_RE = re.compile(
    r"bản đặc biệt|ban dac biet|bản giới hạn|ban gioi han|bản sưu tầm"
    r"|ban suu tam|boxset|box set|deluxe|artbook|có box",
    re.IGNORECASE,
)
# Series cuyo NOMBRE contiene la señal (ruido conocido de Kim Đồng).
_VN_FALSE_POSITIVE_RE = re.compile(
    r"pokémon đặc biệt|pokemon dac biet|đội quân doraemon đặc biệt"
    r"|tuyển tập đặc biệt",
    re.IGNORECASE,
)


def _shopify_like_list(base: str, session: requests.Session, sleep: float,
                       limit: int = 100, max_pages: int = 100) -> Iterator[dict]:
    """Sapo/Bizweb y Haravan clonan el /products.json de Shopify."""
    page = 1
    while page <= max_pages:
        data = _get_json(session, f"{base}/collections/all/products.json",
                         {"page": page, "limit": limit})
        products = (data or {}).get("products") or []
        if not products:
            break
        yield from products
        page += 1
        time.sleep(sleep)


def _vn_map(p: dict, source: Source, base: str) -> Candidate | None:
    name = clean_text(p.get("name") or p.get("title") or "")
    handle = p.get("alias") or p.get("handle") or ""
    if not name or not handle:
        return None
    if not _VN_SPECIAL_RE.search(name) or _VN_FALSE_POSITIVE_RE.search(name):
        return None
    url = f"{base}/products/{handle}"
    desc = clean_text(p.get("summary") or p.get("body_html") or "")[:1200]
    cand = candidate_from_source(source, title=name, url=url, description=desc)
    imgs = p.get("images") or []
    if imgs:
        first = imgs[0]
        src = first.get("src") if isinstance(first, dict) else str(first)
        if src:
            cand.image_url = src if src.startswith("http") else f"https:{src}"
    # Haravan (IPM): EAN-13 vietnamita en variants[].barcode; fecha en
    # published_at. Sufijos de letra ocasionales se limpian.
    variants = p.get("variants") or []
    if variants and isinstance(variants[0], dict):
        barcode = (variants[0].get("barcode") or "").strip()
        barcode = re.sub(r"[^0-9]", "", barcode)
        if len(barcode) == 13:
            cand.isbn = barcode
    pub = (p.get("published_at") or "")[:10]
    if pub:
        cand.release_date = pub
    return cand


def _yaakz_list(session: requests.Session, sleep: float) -> Iterator[dict]:
    """API Laravel — categoría 1098 Box Set/Limited Edition (~58 items)."""
    page = 1
    while page <= 10:
        data = _get_json(session, "https://www.yaakz.com/api/products",
                         {"filter[parent_category_id]": 1098,
                          "page": page, "per_page": 20})
        inner = (data or {}).get("data") or data or {}
        items = inner.get("data") if isinstance(inner, dict) else inner
        if not items:
            break
        yield from items
        last = inner.get("last_page") if isinstance(inner, dict) else None
        if last and page >= int(last):
            break
        page += 1
        time.sleep(sleep)


def _yaakz_map(p: dict, source: Source) -> Candidate | None:
    name = clean_text(p.get("name") or "")
    pid = p.get("id")
    if not name or not pid:
        return None
    # Excluir cajas vacías de reposición y bundles de suscripción duplicados.
    if name.startswith("กล่องเปล่า") or "[Subscription Order]" in name:
        return None
    slug = p.get("slug") or pid
    cand = candidate_from_source(
        source, title=name, url=f"https://www.yaakz.com/product/{slug}",
        description="",
    )
    # El API devuelve `images` como STRING — a veces UNA URL, a veces varias
    # separadas por coma — no lista (bugs 2026-06-12: imgs[0] tomaba el
    # primer CARÁCTER; luego la string completa "url1,url2" daba 301/html).
    imgs = p.get("images") or []
    if isinstance(imgs, str):
        imgs = [u.strip() for u in imgs.split(",") if u.strip()]
    if imgs:
        first = imgs[0]
        src = (first.get("url") or first.get("src") or "") if isinstance(first, dict) else str(first)
        if src.startswith("http"):
            cand.image_url = src
    return cand


_PROFILES: dict[str, dict[str, Any]] = {
    "jd-intl": {
        "source": dict(
            name="HK - Jade Dynasty (ediciones premium)",
            url="https://jd-intl.com/",
            country="Hong Kong", language="Chino", publisher="Jade Dynasty",
            source_class="official", tags=["manga", "wiki", "hongkong"],
        ),
        "list": _jd_intl_list,
        "map": _jd_intl_map,
    },
    "spp-tw": {
        "source": dict(
            name="TW - Sharp Point 尖端 (especiales)",
            url="https://www.spp.com.tw/",
            country="Taiwán", language="Chino", publisher="Sharp Point",
            source_class="official", tags=["manga", "wiki", "taiwan"],
        ),
        "list": _spp_list,
        "map": _spp_map,
    },
    "kimdong": {
        "source": dict(
            name="VN - NXB Kim Đồng (bản đặc biệt)",
            url="https://nxbkimdong.com.vn/",
            country="Vietnam", language="Vietnamita", publisher="Kim Đồng",
            source_class="official", tags=["manga", "wiki", "vietnam"],
        ),
        "list": lambda s, sl: _shopify_like_list("https://nxbkimdong.com.vn", s, sl, 100),
        "map": lambda p, src: _vn_map(p, src, "https://nxbkimdong.com.vn"),
    },
    "ipm": {
        "source": dict(
            name="VN - IPM (bản sưu tầm / boxset)",
            url="https://ipm.vn/",
            country="Vietnam", language="Vietnamita", publisher="IPM",
            source_class="official", tags=["manga", "wiki", "vietnam"],
        ),
        # Haravan capea limit a 50.
        "list": lambda s, sl: _shopify_like_list("https://ipm.vn", s, sl, 50),
        "map": lambda p, src: _vn_map(p, src, "https://ipm.vn"),
    },
    "yaakz": {
        "source": dict(
            name="TH - Siam Inter / yaakz (box sets)",
            url="https://www.yaakz.com/",
            country="Tailandia", language="Tailandés", publisher="Siam Inter Comics",
            source_class="official", tags=["manga", "wiki", "thailand"],
        ),
        "list": _yaakz_list,
        "map": _yaakz_map,
    },
}


def _make_source(profile: str) -> Source:
    cfg = _PROFILES[profile]["source"]
    return Source(kind="wiki", purity="manga_only", **cfg)


def _bootstrap(
    profile: str,
    session: requests.Session,
    sleep_seconds: float = 0.3,
    min_score: int = 0,
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    cfg = _PROFILES[profile]
    source = _make_source(profile)
    print(f"[storefront:{profile}] listando {source.url}")

    candidates: list[Candidate] = []
    pending: list[Candidate] = []
    seen_urls: set[str] = set()
    raw_count = 0
    for raw in cfg["list"](session, sleep_seconds):
        raw_count += 1
        cand = cfg["map"](raw, source)
        if cand is None or cand.url in seen_urls:
            continue
        seen_urls.add(cand.url)
        score_candidate(cand)
        if min_score and cand.score < min_score:
            continue
        candidates.append(cand)
        pending.append(cand)
        if flush_fn and len(pending) >= 20:
            flush_fn(pending)
            pending = []
    if flush_fn and pending:
        flush_fn(pending)
    print(f"[storefront:{profile}] {raw_count} productos crudos → "
          f"{len(candidates)} candidatos")
    return candidates


def _make_bootstrap(profile: str):
    def bootstrap(
        year_from: int, month_from: int,    # noqa: ARG001 — catálogos completos,
        year_to: int, month_to: int,        # noqa: ARG001 — el filtro de fecha no aplica
        session: requests.Session,
        sleep_seconds: float = 0.3,
        timeout: tuple[int, int] = (15, 45),  # noqa: ARG001
        min_score: int = 0,
        fetch_details: bool = False,        # noqa: ARG001 — el listing ya trae todo
        flush_fn: "Callable[[list[Candidate]], None] | None" = None,
        **kwargs: Any,
    ) -> list[Candidate]:
        return _bootstrap(profile, session, sleep_seconds=sleep_seconds,
                          min_score=min_score, flush_fn=flush_fn, **kwargs)
    return bootstrap


bootstrap_jd_intl = _make_bootstrap("jd-intl")
bootstrap_spp = _make_bootstrap("spp-tw")
bootstrap_kimdong = _make_bootstrap("kimdong")
bootstrap_ipm = _make_bootstrap("ipm")
bootstrap_yaakz = _make_bootstrap("yaakz")


def iter_year_months(
    year_from: int, month_from: int,
    year_to: int, month_to: int,    # noqa: ARG001
) -> list[tuple[int, int]]:
    """Catálogos completos por API; un único batch."""
    return [(year_from, month_from)]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("profile", choices=sorted(_PROFILES))
    parser.add_argument("--sleep-seconds", type=float, default=0.3)
    parser.add_argument("--limit", type=int, default=0, help="cortar tras N candidatos (debug)")
    args = parser.parse_args()

    with requests.Session() as sess:
        cands = _bootstrap(args.profile, sess, sleep_seconds=args.sleep_seconds)
        for c in cands[: args.limit or len(cands)]:
            print(f"  {c.score:3} | {c.title[:60]} | {c.url[:60]}")
