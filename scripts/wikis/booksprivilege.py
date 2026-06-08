"""Parser de booksprivilege.com — 店舗特典まとめました (Japón).

Agregador japonés de **店舗特典** (beneficios/extras de tienda): postales,
ilustraciones, shikishi, bromides, acrylic panels y demás bonus que los
retailers japoneses (アニメイト, ゲーマーズ, とらのあな, メロンブックス,
COMIC ZIN, など) entregan al comprar un tomo. El libro en sí es la
edición regular — el valor está en el extra. Esto es lo que las sources
JP que ya tenemos (Rakuten, Kadokawa Store, Sanyodo) NO marcan
explícitamente.

Estructura del sitio:

  - Calendar widget mensual en `?cal_ym=YYYY-M` con `<td class="has-book">
    <a href="?date=YYYY-MM-DD">N</a></td>` para los días con releases.
    Discovery natural: pedís el mes, sacás los días con contenido.
  - Listing diario en `?date=YYYY-MM-DD` con `<div class="book-item">`
    por entry. Cada uno tiene link `?id=NNNN` a la página de detalle.
  - Detail page en `?id=NNNN` con:
      <h1 class="entry-title"><a>陰の実力者になりたくて! (18)</a></h1>
      <div class="shop_box">                          ← una caja por SKU
        <div class="shop_image"><img src=".../P/4041173876.09_SL500_.jpg"/>
        <div class="shop_info">
          <div class="shop_title">陰の実力者になりたくて! (18) (角川コミックス・エース)</div>
          <div class="shop_author">坂野 杏梨, 逢沢 大介, 東西</div>
          <div class="shop_label">角川コミックス・エース</div>          ← imprint/sello
          <div class="shop_date">2026-05-25</div>
        </div>
      </div>
      [shop_box para el Kindle ASIN B0... — se descarta]
      <div class="shop-list">
        <div class="shop-row">
          <div class="shop-name-col">とらのあな</div>
          <div class="shop-benefit-col"><a>特製イラストカード</a></div>
        </div>
        <div class="shop-row">
          <div class="shop-name-col">ゲーマーズ</div>
          <div class="shop-benefit-col"><a>オリジナルブロマイド</a></div>
        </div>
        ...
      </div>

URL canónica en items.jsonl: la del detail (`?id=NNNN`) porque agrupa
todos los retailers y tokuten. La URL Amazon va en el description como
referencia de compra.

API pública (paralela a blogbbm.py / socialanime.py):
    parse_calendar_month(html_text, year, month) -> list[date]
    parse_daily_listing(html_text, source_url) -> list[str]   (item URLs)
    parse_detail_page(html_text, detail_url) -> Candidate | None
    fetch_html(session, url, timeout) -> str | None
    bootstrap(yf, mf, yt, mt, session, ...) -> list[Candidate]
    iter_year_months(yf, mf, yt, mt) -> list[(year, month)]
"""

from __future__ import annotations

import datetime as dt
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable
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


BASE_URL = "https://booksprivilege.com/"
CALENDAR_URL_TEMPLATE = "https://booksprivilege.com/?cal_ym={year}-{month}"
DAILY_URL_TEMPLATE = "https://booksprivilege.com/?date={year:04d}-{month:02d}-{day:02d}"
DETAIL_URL_TEMPLATE = "https://booksprivilege.com/?id={item_id}"

# Volume en el título: "(18)" o "(１８)" o "第18巻" o "vol. 18".
_VOL_PATTERNS = (
    re.compile(r"\((\d{1,4})\)\s*$"),                # "Title (18)"
    re.compile(r"第\s*(\d{1,4})\s*巻"),               # "第18巻"
    re.compile(r"\bvol\.?\s*(\d{1,4})\b", re.I),     # "vol. 18"
)

# ASIN/ISBN-10 del path Amazon CDN: /P/<10-chars>.09_SL500_.jpg
_AMAZON_ISBN_PATH = re.compile(r"/P/([0-9A-Z]{10})\.")

# Amazon CDN para portada por ISBN (usamos como fallback si el shop_image
# img directo viene roto). Formato canónico que el sitio ya emite.
_AMAZON_COVER_TEMPLATE = "https://images-fe.ssl-images-amazon.com/images/P/{isbn}.09_SL500_.jpg"

# Publisher canónico desde el `shop_label` (imprint japonés). Cubre los
# imprints más frecuentes; los no listados quedan con el label literal
# como publisher y el skill /watch-standardize-catalog los canonicaliza después.
_LABEL_TO_PUBLISHER: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"角川"), "Kadokawa"),
    (re.compile(r"KADOKAWA", re.I), "Kadokawa"),
    (re.compile(r"講談社"), "Kodansha"),
    (re.compile(r"小学館"), "Shogakukan"),
    (re.compile(r"集英社"), "Shueisha"),
    (re.compile(r"白泉社"), "Hakusensha"),
    (re.compile(r"秋田書店"), "Akita Shoten"),
    (re.compile(r"一迅社"), "Ichijinsha"),
    (re.compile(r"スクウェア・?エニックス|SQUARE\s*ENIX", re.I), "Square Enix"),
    (re.compile(r"双葉社"), "Futabasha"),
    (re.compile(r"竹書房"), "Takeshobo"),
    (re.compile(r"徳間書店"), "Tokuma"),
    (re.compile(r"フロンティアワークス"), "Frontier Works"),
    (re.compile(r"マッグガーデン"), "Mag Garden"),
    (re.compile(r"イースト・?プレス"), "East Press"),
    (re.compile(r"芳文社"), "Houbunsha"),
    (re.compile(r"少年画報社"), "Shounen Gahosha"),
    (re.compile(r"リブレ"), "Libre"),
    (re.compile(r"幻冬舎"), "Gentosha"),
    (re.compile(r"ホビージャパン"), "Hobby Japan"),
    (re.compile(r"オーバーラップ"), "Overlap"),
    (re.compile(r"アスキー・?メディアワークス|ASCII", re.I), "ASCII Media Works"),
)


def _virtual_source() -> Source:
    return Source(
        name="JP - BooksPrivilege (店舗特典)",
        url=BASE_URL,
        country="Japón",
        language="Japonés",
        publisher="",               # se rellena por item desde shop_label
        source_class="trusted_media",
        kind="wiki",
        enabled=True,
        tags=["wiki", "booksprivilege", "japon", "tokuten"],
        notes="booksprivilege.com — agregador JP de 店舗特典 (extras de tienda)",
        selectors={},
        max_pages=0,
        purity="manga_only",        # el sitio cura solo libros con tokuten
    )


def _publisher_from_label(label: str) -> str:
    """Resuelve un imprint japonés (角川コミックス・エース) a publisher
    canónico (Kadokawa). Si no matchea ningún pattern, devuelve el label
    como-está y que el skill /watch-standardize-catalog lo normalice."""
    if not label:
        return ""
    for pat, display in _LABEL_TO_PUBLISHER:
        if pat.search(label):
            return display
    return label.strip()


def _extract_volume(title: str) -> str:
    """De '陰の実力者になりたくて! (18)' → '18'."""
    if not title:
        return ""
    for pat in _VOL_PATTERNS:
        m = pat.search(title)
        if m:
            v = m.group(1).lstrip("0") or m.group(1)
            return v
    return ""


def parse_calendar_month(html_text: str, year: int, month: int) -> list[dt.date]:
    """Parsea la página `?cal_ym=YYYY-M` y devuelve las fechas con releases.

    El widget calendario contiene `<td class="has-book"><a href="?date=YYYY-MM-DD">N</a></td>`
    para cada día con contenido. Los `<td class="empty">` y los sin clase
    son días sin releases (los ignoramos).
    """
    if not html_text:
        return []
    soup = BeautifulSoup(html_text, "html.parser")
    out: list[dt.date] = []
    for td in soup.find_all("td", class_="has-book"):
        a = td.find("a", href=re.compile(r"\?date=\d{4}-\d{2}-\d{2}"))
        if not a:
            continue
        m = re.search(r"\?date=(\d{4})-(\d{2})-(\d{2})", a.get("href", ""))
        if not m:
            continue
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y != year or mo != month:
            # Días "spill-over" de meses adyacentes que el widget muestra
            # en los bordes — los descartamos para evitar duplicados al
            # iterar varios meses contiguos.
            continue
        try:
            out.append(dt.date(y, mo, d))
        except ValueError:
            continue
    # Dedupe + sort
    return sorted(set(out))


def parse_daily_listing(html_text: str) -> list[int]:
    """Parsea `?date=YYYY-MM-DD` y devuelve la lista de item ids (`?id=NNN`).

    Cada `<div class="book-item">` contiene un `<a href="?id=NNNN">`. Si
    el día está vacío, el sitio renderiza `該当する書籍はありません。`
    y devolvemos lista vacía.
    """
    if not html_text:
        return []
    soup = BeautifulSoup(html_text, "html.parser")
    out: list[int] = []
    for item in soup.find_all("div", class_="book-item"):
        a = item.find("a", href=re.compile(r"\?id=\d+"))
        if not a:
            continue
        m = re.search(r"\?id=(\d+)", a.get("href", ""))
        if not m:
            continue
        try:
            out.append(int(m.group(1)))
        except ValueError:
            continue
    # Dedupe preservando orden
    seen: set[int] = set()
    deduped: list[int] = []
    for i in out:
        if i not in seen:
            seen.add(i)
            deduped.append(i)
    return deduped


def parse_detail_page(html_text: str, detail_url: str) -> Candidate | None:
    """Parsea `?id=NNNN` y construye un Candidate.

    Devuelve None si:
    - No hay título identificable.
    - No hay shop_box con ISBN-10 válido (solo Kindle ASIN B0... → skip;
      el ASIN debe empezar con dígito para ser ISBN legacy real).
    """
    if not html_text:
        return None
    soup = BeautifulSoup(html_text, "html.parser")

    article = soup.find("article")
    if not article:
        return None

    # Title del <h1 class="entry-title">.
    title_el = article.find(class_="entry-title")
    if not title_el:
        return None
    title = clean_text(title_el.get_text(" ", strip=True))
    if not title:
        return None

    # Recorrer los shop_box buscando el primero con ISBN-10 (no Kindle).
    isbn: str = ""
    image_url: str = ""
    author: str = ""
    label: str = ""
    release_date: str = ""
    amazon_url: str = ""

    for box in article.find_all(class_="shop_box"):
        img = box.find("img", src=_AMAZON_ISBN_PATH)
        if not img:
            continue
        m = _AMAZON_ISBN_PATH.search(img.get("src", ""))
        if not m:
            continue
        asin = m.group(1)
        # Kindle ASINs empiezan con 'B0' y NO son ISBN. Skip.
        if asin.startswith("B"):
            continue
        # Primer ISBN real gana — extraemos su metadata.
        isbn = asin
        image_url = _AMAZON_COVER_TEMPLATE.format(isbn=isbn)
        info = box.find(class_="shop_info")
        if info:
            label_el = info.find(class_="shop_label")
            if label_el:
                label = clean_text(label_el.get_text(" ", strip=True))
            author_el = info.find(class_="shop_author")
            if author_el:
                author = clean_text(author_el.get_text(" ", strip=True))
            date_el = info.find(class_="shop_date")
            if date_el:
                release_date = clean_text(date_el.get_text(" ", strip=True))
        # URL Amazon canónica (sin afiliados, los strippea gotcha #26).
        a = box.find("a", href=re.compile(r"amazon\.co\.jp/dp/"))
        if a:
            amazon_url = a.get("href", "").split("?", 1)[0]
        break

    if not isbn:
        # Solo Kindle, o sin shop_box válido — descartamos.
        return None

    # Shop list — construir la descripción del tokuten.
    shop_lines: list[str] = []
    shop_list = article.find(class_="shop-list") or soup.find(class_="shop-list")
    if shop_list:
        for row in shop_list.find_all(class_="shop-row"):
            name_el = row.find(class_="shop-name-col")
            benefit_el = row.find(class_="shop-benefit-col")
            if not name_el or not benefit_el:
                continue
            name = clean_text(name_el.get_text(" ", strip=True))
            # Algunos benefits llevan <br/> entre items, el clean_text los
            # colapsa a espacio simple — perfecto para una línea por shop.
            benefit = clean_text(benefit_el.get_text(" ", strip=True))
            if not name or not benefit:
                continue
            shop_lines.append(f"{name}: {benefit}")

    publisher = _publisher_from_label(label)
    source = _virtual_source()
    if publisher:
        source.publisher = publisher

    # Description: marker explícito de 店舗特典 (para que detect_signals
    # levante el signal `bonus`) + lista de tiendas con sus extras +
    # link Amazon como referencia de compra.
    descr_parts: list[str] = ["店舗特典 / store bonus / bonus edition."]
    if shop_lines:
        descr_parts.append("Tokuten: " + " | ".join(shop_lines))
    if amazon_url:
        descr_parts.append(f"Amazon JP: {amazon_url}")
    if label and label != publisher:
        descr_parts.append(f"Sello: {label}.")
    description = " ".join(descr_parts).strip()[:2500]

    cand = candidate_from_source(
        source,
        title=title,
        url=detail_url,
        description=description,
        published_at=release_date,
    )
    cand.image_url = image_url
    cand.release_date = release_date
    cand.isbn = isbn
    if author:
        cand.author = author

    volume = _extract_volume(title)
    if volume:
        cand.tags = list(source.tags) + [f"bp-vol:{volume}"]

    score_candidate(cand)
    return cand


def fetch_html(
    session: requests.Session,
    url: str,
    timeout: tuple[int, int] = (10, 30),
) -> str | None:
    """Descarga `url` y devuelve el HTML decodificado.

    El sitio declara `charset=UTF-8` pero embebe alt-text en cp932 (ads).
    Decodificamos con errors='replace' para no romper en los bytes
    sucios — el body útil (japonés) es UTF-8 limpio.
    """
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        # Forzar UTF-8 ignorando los bytes ad-banner cp932 sucios.
        return resp.content.decode("utf-8", errors="replace")
    except requests.RequestException as exc:
        print(f"[booksprivilege] WARN {url}: {exc}")
        return None


def iter_year_months(
    year_from: int, month_from: int,
    year_to: int, month_to: int,
) -> list[tuple[int, int]]:
    """Iterador de (year, month) inclusive de (yf, mf) a (yt, mt)."""
    if (year_from, month_from) > (year_to, month_to):
        year_from, month_from, year_to, month_to = (
            year_to, month_to, year_from, month_from,
        )
    out: list[tuple[int, int]] = []
    y, m = year_from, month_from
    while (y, m) <= (year_to, month_to):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def bootstrap(
    year_from: int,
    month_from: int,
    year_to: int,
    month_to: int,
    session: requests.Session,
    sleep_seconds: float = 0.2,
    timeout: tuple[int, int] = (10, 30),
    min_score: int = 0,
    fetch_details: bool = False,  # noqa: ARG001 (detail siempre se fetchea)
    flush_fn: "Callable[[list[Candidate]], None] | None" = None,
    **kwargs: Any,
) -> list[Candidate]:
    """Iterá meses → días con releases → items, parseando cada detail page.

    `sleep_seconds` aplica entre detail-fetches (puede haber decenas por
    día en meses populares). El calendar fetch + listing fetch son
    despreciables (1 + N días por mes).
    `flush_fn`: si se provee, se llama con los candidates del mes al terminar
    cada mes — permite escritura incremental sin esperar a que terminen todos
    los meses.
    """
    months = iter_year_months(year_from, month_from, year_to, month_to)
    print(f"[booksprivilege] {len(months)} mes(es) a procesar: "
          f"{year_from:04d}-{month_from:02d} → {year_to:04d}-{month_to:02d}")

    seen_ids: set[int] = set()
    candidates: list[Candidate] = []

    for (y, m) in months:
        cal_url = CALENDAR_URL_TEMPLATE.format(year=y, month=m)
        cal_html = fetch_html(session, cal_url, timeout=timeout)
        if not cal_html:
            continue
        days = parse_calendar_month(cal_html, y, m)
        print(f"[booksprivilege] {y:04d}-{m:02d}: {len(days)} día(s) con releases")

        month_candidates: list[Candidate] = []
        for day in days:
            daily_url = DAILY_URL_TEMPLATE.format(year=day.year, month=day.month, day=day.day)
            daily_html = fetch_html(session, daily_url, timeout=timeout)
            if not daily_html:
                continue
            item_ids = parse_daily_listing(daily_html)
            for item_id in item_ids:
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                detail_url = DETAIL_URL_TEMPLATE.format(item_id=item_id)
                detail_html = fetch_html(session, detail_url, timeout=timeout)
                if not detail_html:
                    continue
                cand = parse_detail_page(detail_html, detail_url)
                if not cand:
                    continue
                if min_score and cand.score < min_score:
                    continue
                month_candidates.append(cand)
                if sleep_seconds:
                    time.sleep(sleep_seconds)

        candidates.extend(month_candidates)
        if flush_fn and month_candidates:
            flush_fn(month_candidates)

    print(f"[booksprivilege] terminado: {len(candidates)} candidates con score>={min_score}")
    return candidates


if __name__ == "__main__":
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; manga-watch-personal/0.2)"
    today = dt.date.today()
    yf, mf = today.year, max(1, today.month - 1)
    yt, mt = today.year, today.month
    cands = bootstrap(yf, mf, yt, mt, session=s, min_score=0, sleep_seconds=0.1)
    print(f"\nTotal: {len(cands)} candidates")
    for c in cands[:10]:
        print(f"  [{c.score:3d}] {c.publisher[:15]:15s} | {c.signal_types} | {c.title[:60]}")
