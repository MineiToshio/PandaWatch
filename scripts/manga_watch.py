#!/usr/bin/env python3
"""
manga_watch.py

Tracker personal de mangas físicos coleccionistas y artbooks.

Detecta:
- ediciones especiales / limitadas / collector
- tapa dura / deluxe / master / perfect / kanzenban / prestige
- box sets / cofres / cofanetti / coffrets / slipcases
- portadas variantes / retailer exclusives
- extras físicos: shikishi, póster, postal, booklet, acrílico, llavero, etc.
- artbooks / fanbooks / illustration books / 画集 / イラスト集 / 設定資料集

Archivos de salida:
- data/items.jsonl       historial append-only de hallazgos nuevos/cambiados
- data/state.json        estado para no repetir lo mismo todos los días
- reports/YYYY-MM-DD.md  reporte Markdown diario

Uso:
    python manga_watch.py
    python manga_watch.py --min-score 30
    python manga_watch.py --send-telegram
    python manga_watch.py --source-classes official,retailer
    python manga_watch.py --source-classes trusted_media,social
    python manga_watch.py --list-sources
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv


KEYWORD_RULES: list[dict[str, Any]] = [
    # -------------------------
    # Español
    # -------------------------
    {"phrase": "edición limitada", "score": 45, "type": "limited"},
    {"phrase": "edicion limitada", "score": 45, "type": "limited"},
    {"phrase": "edición especial", "score": 40, "type": "special_edition"},
    {"phrase": "edicion especial", "score": 40, "type": "special_edition"},
    {"phrase": "edición coleccionista", "score": 45, "type": "collector"},
    {"phrase": "edicion coleccionista", "score": 45, "type": "collector"},
    {"phrase": "coleccionista", "score": 28, "type": "collector"},
    {"phrase": "numerada", "score": 40, "type": "limited"},
    {"phrase": "pack limitado", "score": 35, "type": "pack"},
    {"phrase": "preventa", "score": 10, "type": "availability"},
    {"phrase": "próximamente", "score": 8, "type": "availability"},
    {"phrase": "proximamente", "score": 8, "type": "availability"},
    {"phrase": "tapa dura", "score": 35, "type": "hardcover"},
    {"phrase": "cartoné", "score": 35, "type": "hardcover"},
    {"phrase": "cartone", "score": 35, "type": "hardcover"},
    {"phrase": "gran formato", "score": 22, "type": "oversized"},
    {"phrase": "mayor formato", "score": 22, "type": "oversized"},
    {"phrase": "kanzenban", "score": 25, "type": "premium_format"},
    {"phrase": "integral", "score": 18, "type": "omnibus"},
    {"phrase": "3 en 1", "score": 16, "type": "omnibus"},
    {"phrase": "2 en 1", "score": 14, "type": "omnibus"},
    {"phrase": "cofre", "score": 40, "type": "box_set"},
    {"phrase": "sobrecubierta reversible", "score": 30, "type": "bonus"},
    {"phrase": "portada alternativa", "score": 35, "type": "variant_cover"},
    {"phrase": "portada variante", "score": 40, "type": "variant_cover"},
    {"phrase": "litografía", "score": 25, "type": "bonus"},
    {"phrase": "litografia", "score": 25, "type": "bonus"},
    {"phrase": "póster", "score": 20, "type": "bonus"},
    {"phrase": "poster", "score": 20, "type": "bonus"},
    {"phrase": "postal", "score": 18, "type": "bonus"},
    {"phrase": "postales", "score": 18, "type": "bonus"},
    {"phrase": "marcapáginas", "score": 18, "type": "bonus"},
    {"phrase": "marcapaginas", "score": 18, "type": "bonus"},
    {"phrase": "señalador", "score": 18, "type": "bonus"},
    {"phrase": "senalador", "score": 18, "type": "bonus"},
    {"phrase": "cuaderno especial", "score": 25, "type": "bonus"},
    {"phrase": "acrílico", "score": 25, "type": "bonus"},
    {"phrase": "acrilico", "score": 25, "type": "bonus"},
    {"phrase": "llavero", "score": 20, "type": "bonus"},
    {"phrase": "funda", "score": 22, "type": "box_set"},
    {"phrase": "relieve", "score": 20, "type": "finish"},
    {"phrase": "holográfico", "score": 25, "type": "finish"},
    {"phrase": "holografico", "score": 25, "type": "finish"},
    {"phrase": "cantos pintados", "score": 25, "type": "finish"},
    {"phrase": "páginas a color", "score": 18, "type": "bonus"},
    {"phrase": "paginas a color", "score": 18, "type": "bonus"},
    {"phrase": "extras", "score": 14, "type": "bonus"},
    {"phrase": "artbook", "score": 35, "type": "artbook"},
    {"phrase": "libro de arte", "score": 35, "type": "artbook"},
    {"phrase": "libro de ilustraciones", "score": 35, "type": "artbook"},
    {"phrase": "fanbook", "score": 30, "type": "fanbook"},
    {"phrase": "guía oficial", "score": 28, "type": "guidebook"},
    {"phrase": "guia oficial", "score": 28, "type": "guidebook"},

    # -------------------------
    # Inglés
    # -------------------------
    {"phrase": "special edition", "score": 40, "type": "special_edition"},
    {"phrase": "limited edition", "score": 45, "type": "limited"},
    {"phrase": "while supplies last", "score": 40, "type": "limited"},
    {"phrase": "numbered", "score": 40, "type": "limited"},
    {"phrase": "collector's edition", "score": 45, "type": "collector"},
    {"phrase": "collectors edition", "score": 45, "type": "collector"},
    {"phrase": "collector edition", "score": 45, "type": "collector"},
    {"phrase": "deluxe edition", "score": 38, "type": "deluxe"},
    {"phrase": "deluxe", "score": 30, "type": "deluxe"},
    {"phrase": "master edition", "score": 35, "type": "premium_format"},
    {"phrase": "perfect edition", "score": 35, "type": "premium_format"},
    {"phrase": "premium edition", "score": 35, "type": "premium_format"},
    {"phrase": "hardcover", "score": 35, "type": "hardcover"},
    {"phrase": "hardback", "score": 35, "type": "hardcover"},
    {"phrase": "oversized", "score": 22, "type": "oversized"},
    {"phrase": "box set", "score": 40, "type": "box_set"},
    {"phrase": "boxset", "score": 40, "type": "box_set"},
    {"phrase": "slipcase", "score": 35, "type": "box_set"},
    {"phrase": "launch bundle", "score": 30, "type": "bundle"},
    {"phrase": "special bundle", "score": 30, "type": "bundle"},
    {"phrase": "variant cover", "score": 40, "type": "variant_cover"},
    {"phrase": "exclusive cover", "score": 40, "type": "variant_cover"},
    {"phrase": "retailer exclusive", "score": 40, "type": "retailer_exclusive"},
    {"phrase": "kinokuniya exclusive", "score": 45, "type": "retailer_exclusive"},
    {"phrase": "barnes & noble exclusive", "score": 45, "type": "retailer_exclusive"},
    {"phrase": "crunchyroll exclusive", "score": 45, "type": "retailer_exclusive"},
    {"phrase": "books-a-million exclusive", "score": 45, "type": "retailer_exclusive"},
    {"phrase": "walmart exclusive", "score": 45, "type": "retailer_exclusive"},
    {"phrase": "shikishi", "score": 30, "type": "bonus"},
    {"phrase": "art board", "score": 25, "type": "bonus"},
    {"phrase": "booklet", "score": 25, "type": "bonus"},
    {"phrase": "mini artbook", "score": 30, "type": "artbook"},
    {"phrase": "acrylic", "score": 25, "type": "bonus"},
    {"phrase": "keychain", "score": 20, "type": "bonus"},
    {"phrase": "color pages", "score": 18, "type": "bonus"},
    {"phrase": "bonus", "score": 14, "type": "bonus"},
    {"phrase": "foil-stamped", "score": 25, "type": "finish"},
    {"phrase": "sprayed edges", "score": 25, "type": "finish"},
    {"phrase": "printed edges", "score": 25, "type": "finish"},
    {"phrase": "pre-order", "score": 10, "type": "availability"},
    {"phrase": "preorder", "score": 10, "type": "availability"},
    {"phrase": "coming soon", "score": 8, "type": "availability"},
    {"phrase": "art book", "score": 35, "type": "artbook"},
    {"phrase": "illustration book", "score": 35, "type": "artbook"},
    {"phrase": "super illustration book", "score": 45, "type": "artbook"},
    {"phrase": "official guidebook", "score": 30, "type": "guidebook"},
    {"phrase": "visual book", "score": 30, "type": "artbook"},
    {"phrase": "visual fanbook", "score": 35, "type": "artbook"},
    {"phrase": "setting book", "score": 30, "type": "artbook"},

    # -------------------------
    # Francés
    # -------------------------
    {"phrase": "édition collector", "score": 45, "type": "collector"},
    {"phrase": "edition collector", "score": 45, "type": "collector"},
    {"phrase": "collector", "score": 28, "type": "collector"},
    {"phrase": "édition limitée", "score": 45, "type": "limited"},
    {"phrase": "edition limitee", "score": 45, "type": "limited"},
    {"phrase": "tirage limité", "score": 45, "type": "limited"},
    {"phrase": "tirage limite", "score": 45, "type": "limited"},
    {"phrase": "version collector", "score": 40, "type": "collector"},
    {"phrase": "édition prestige", "score": 35, "type": "premium_format"},
    {"phrase": "edition prestige", "score": 35, "type": "premium_format"},
    {"phrase": "coffret collector", "score": 45, "type": "box_set"},
    {"phrase": "coffret", "score": 35, "type": "box_set"},
    {"phrase": "jaquette réversible", "score": 30, "type": "bonus"},
    {"phrase": "jaquette reversible", "score": 30, "type": "bonus"},
    {"phrase": "couverture alternative", "score": 35, "type": "variant_cover"},
    {"phrase": "couverture variante", "score": 35, "type": "variant_cover"},
    {"phrase": "ex-libris", "score": 30, "type": "bonus"},
    {"phrase": "marque-page", "score": 20, "type": "bonus"},
    {"phrase": "cartes postales", "score": 22, "type": "bonus"},
    {"phrase": "beau livre", "score": 30, "type": "artbook"},
    {"phrase": "livre d'illustration", "score": 35, "type": "artbook"},
    {"phrase": "livre d’illustration", "score": 35, "type": "artbook"},
    {"phrase": "artbook luxe", "score": 45, "type": "artbook"},

    # -------------------------
    # Italiano
    # -------------------------
    {"phrase": "edizione limitata", "score": 45, "type": "limited"},
    {"phrase": "edizione speciale", "score": 40, "type": "special_edition"},
    {"phrase": "edizione variant", "score": 40, "type": "variant_cover"},
    {"phrase": "variant cover edition", "score": 45, "type": "variant_cover"},
    {"phrase": "tribute variant cover edition", "score": 45, "type": "variant_cover"},
    {"phrase": "celebration edition", "score": 40, "type": "collector"},
    {"phrase": "cover variant", "score": 40, "type": "variant_cover"},
    {"phrase": "cover alternativa", "score": 35, "type": "variant_cover"},
    {"phrase": "esclusiva", "score": 35, "type": "retailer_exclusive"},
    {"phrase": "esclusive", "score": 35, "type": "retailer_exclusive"},
    {"phrase": "limitata 500 copie", "score": 50, "type": "limited"},
    {"phrase": "cofanetto", "score": 40, "type": "box_set"},
    {"phrase": "box-set", "score": 40, "type": "box_set"},
    {"phrase": "box da collezione", "score": 45, "type": "box_set"},
    {"phrase": "sovraccoperta", "score": 25, "type": "bonus"},
    {"phrase": "cartoline", "score": 22, "type": "bonus"},
    {"phrase": "segnalibro", "score": 20, "type": "bonus"},
    {"phrase": "libro d'illustrazione", "score": 35, "type": "artbook"},
    {"phrase": "libro di illustrazioni", "score": 35, "type": "artbook"},
    {"phrase": "grande formato", "score": 25, "type": "oversized"},
    {"phrase": "preordine", "score": 10, "type": "availability"},

    # -------------------------
    # Japonés: ediciones / extras / artbooks
    # -------------------------
    {"phrase": "特装版", "score": 50, "type": "special_edition"},
    {"phrase": "限定版", "score": 50, "type": "limited"},
    {"phrase": "初回限定", "score": 50, "type": "limited"},
    {"phrase": "数量限定", "score": 50, "type": "limited"},
    {"phrase": "完全受注生産", "score": 55, "type": "made_to_order"},
    {"phrase": "受注生産", "score": 45, "type": "made_to_order"},
    {"phrase": "予約限定", "score": 50, "type": "limited"},
    {"phrase": "限定特典", "score": 45, "type": "bonus"},
    {"phrase": "購入特典", "score": 35, "type": "bonus"},
    {"phrase": "店舗特典", "score": 40, "type": "retailer_exclusive"},
    {"phrase": "特典付き", "score": 40, "type": "bonus"},
    {"phrase": "予約受付中", "score": 10, "type": "availability"},
    {"phrase": "描き下ろし", "score": 35, "type": "new_art"},
    {"phrase": "描きおろし", "score": 35, "type": "new_art"},
    {"phrase": "複製原画", "score": 40, "type": "bonus"},
    {"phrase": "アクリルスタンド", "score": 30, "type": "bonus"},
    {"phrase": "アクリルカード", "score": 30, "type": "bonus"},
    {"phrase": "アクリルフィギュア", "score": 30, "type": "bonus"},
    {"phrase": "ポストカード", "score": 25, "type": "bonus"},
    {"phrase": "イラストカード", "score": 25, "type": "bonus"},
    {"phrase": "小冊子", "score": 30, "type": "bonus"},
    {"phrase": "ステッカー", "score": 20, "type": "bonus"},
    {"phrase": "カレンダー", "score": 20, "type": "bonus"},
    {"phrase": "トランプ付き", "score": 35, "type": "bonus"},
    {"phrase": "グッズ付き", "score": 35, "type": "bonus"},
    {"phrase": "画集", "score": 40, "type": "artbook"},
    {"phrase": "イラスト集", "score": 40, "type": "artbook"},
    {"phrase": "公式イラスト集", "score": 45, "type": "artbook"},
    {"phrase": "公式ビジュアルブック", "score": 40, "type": "artbook"},
    {"phrase": "ビジュアルファンブック", "score": 40, "type": "artbook"},
    {"phrase": "ファンブック", "score": 35, "type": "fanbook"},
    {"phrase": "設定資料集", "score": 40, "type": "artbook"},
]


@dataclass
class Source:
    name: str
    url: str
    country: str = ""
    language: str = ""
    publisher: str = ""
    source_class: str = "official"
    kind: str = "html"
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    selectors: dict[str, str] = field(default_factory=dict)


@dataclass
class Candidate:
    title: str
    url: str
    source: str
    source_url: str
    country: str
    language: str
    publisher: str
    source_class: str
    tags: list[str]
    description: str
    published_at: str = ""
    score: int = 0
    signals: list[str] = field(default_factory=list)
    signal_types: list[str] = field(default_factory=list)
    status: str = "unknown"
    content_hash: str = ""


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_text(value: str) -> str:
    text = clean_text(value).casefold()
    text = text.replace("’", "'").replace("`", "'")
    # No removemos caracteres japoneses; NFKD deja útil tanto latín como CJK.
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonicalize_url(base_url: str, href: str | None) -> str:
    if not href:
        return base_url
    href = href.strip()
    if href.startswith(("mailto:", "tel:", "javascript:")):
        return ""
    absolute = urljoin(base_url, href)
    absolute, _fragment = urldefrag(absolute)
    return absolute


FUZZY_STOPWORDS: frozenset[str] = frozenset({
    # Genéricas en varios idiomas — solas no aportan señal coleccionista.
    "edicion", "edition", "edizione",
    "de", "la", "el", "le", "les", "las", "los", "en", "con", "y", "e",
    "a", "and", "the", "of", "with", "et", "du", "di", "da", "del",
    "pack", "libro", "livre", "book", "version", "vol", "tome", "tomo",
    "pre", "order", "preorder", "preordine",
    "manga", "comic", "comics",
})

# Configuración de detección (se setea desde run()).
_DETECT_FUZZY: bool = False
_DETECT_FUZZY_DIVISOR: int = 3


def configure_detection(fuzzy: bool, fuzzy_divisor: int) -> None:
    """Setea modo fuzzy de detect_signals para todo el run."""
    global _DETECT_FUZZY, _DETECT_FUZZY_DIVISOR
    _DETECT_FUZZY = fuzzy
    _DETECT_FUZZY_DIVISOR = max(1, fuzzy_divisor)


def _derive_fuzzy_tokens(phrase: str) -> list[str]:
    """Devuelve las palabras 'fuertes' de una phrase (sin stopwords).

    Solo aplica a phrases con espacios. Las japonesas/coreanas/etc. monolíticas
    no se descomponen porque suelen ser palabras únicas significativas.
    """
    if not phrase or " " not in phrase:
        return []
    normalized = normalize_text(phrase)
    tokens = re.split(r"[\s\-']+", normalized)
    return [t for t in tokens if t and len(t) >= 3 and t not in FUZZY_STOPWORDS]


def detect_signals(text: str) -> tuple[int, list[str], list[str]]:
    normalized = normalize_text(text)
    matched_phrases: list[str] = []
    matched_types: list[str] = []
    score = 0

    for rule in KEYWORD_RULES:
        phrase = str(rule["phrase"])
        normalized_phrase = normalize_text(phrase)
        rule_score = int(rule["score"])
        rule_type = str(rule["type"])

        if normalized_phrase and normalized_phrase in normalized:
            matched_phrases.append(phrase)
            matched_types.append(rule_type)
            score += rule_score
            continue

        if _DETECT_FUZZY:
            tokens = _derive_fuzzy_tokens(phrase)
            for token in tokens:
                pattern = rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])"
                if re.search(pattern, normalized):
                    matched_phrases.append(f"{phrase} [fuzzy:{token}]")
                    matched_types.append(rule_type)
                    score += rule_score // _DETECT_FUZZY_DIVISOR
                    break

    matched_phrases = list(dict.fromkeys(matched_phrases))
    matched_types = list(dict.fromkeys(matched_types))
    score = min(score, 100)
    return score, matched_phrases, matched_types


def load_sources(path: Path) -> list[Source]:
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}. Crea sources.yml o usa el paquete que te pasé.")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources_raw = raw.get("sources", [])
    sources: list[Source] = []

    for item in sources_raw:
        if not isinstance(item, dict):
            continue
        tags_raw = item.get("tags", []) or []
        tags = [str(tag).strip() for tag in tags_raw if str(tag).strip()]
        sources.append(
            Source(
                name=str(item.get("name", "")).strip(),
                url=str(item.get("url", "")).strip(),
                country=str(item.get("country", "")).strip(),
                language=str(item.get("language", "")).strip(),
                publisher=str(item.get("publisher", "")).strip(),
                source_class=str(item.get("source_class", "official")).strip(),
                kind=str(item.get("kind", "html")).strip().lower(),
                enabled=bool(item.get("enabled", True)),
                tags=tags,
                notes=str(item.get("notes", "")).strip(),
                selectors=dict(item.get("selectors", {}) or {}),
            )
        )

    return [source for source in sources if source.name and source.url]


def filter_sources(
    sources: list[Source],
    source_classes: set[str] | None,
    countries: set[str] | None,
    include_disabled: bool,
) -> list[Source]:
    filtered: list[Source] = []
    for source in sources:
        if not include_disabled and not source.enabled:
            continue
        if source_classes and source.source_class not in source_classes:
            continue
        if countries and source.country not in countries:
            continue
        filtered.append(source)
    return filtered


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup_path = path.with_suffix(".broken.json")
        path.rename(backup_path)
        print(f"[WARN] state.json corrupto. Lo moví a {backup_path}")
        return {}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


class RobotsCache:
    def __init__(self, user_agent: str) -> None:
        self.user_agent = user_agent
        self.cache: dict[str, RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return True
        base = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = urljoin(base, "/robots.txt")
        if base not in self.cache:
            parser = RobotFileParser()
            parser.set_url(robots_url)
            try:
                parser.read()
                self.cache[base] = parser
            except Exception as exc:
                print(f"[WARN] No pude leer robots.txt de {base}: {exc}. Permito por defecto.")
                self.cache[base] = None
        parser = self.cache[base]
        if parser is None:
            return True
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception as exc:
            print(f"[WARN] Error evaluando robots.txt para {url}: {exc}. Permito por defecto.")
            return True


def make_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8,fr;q=0.7,it;q=0.7,ja;q=0.6",
        }
    )
    return session


def fetch_text(session: requests.Session, url: str, timeout: tuple[int, int]) -> str:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    if not response.encoding:
        response.encoding = response.apparent_encoding
    return response.text


def fetch_with_metadata(
    session: requests.Session, url: str, timeout: tuple[int, int]
) -> tuple[str, dict[str, Any]]:
    """Como fetch_text pero devuelve también metadata útil para diagnóstico."""
    start = time.perf_counter()
    response = session.get(url, timeout=timeout)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    response.raise_for_status()
    if not response.encoding:
        response.encoding = response.apparent_encoding
    metadata = {
        "http_status": response.status_code,
        "content_type": response.headers.get("Content-Type", ""),
        "fetch_ms": elapsed_ms,
        "final_url": response.url,
    }
    return response.text, metadata


# ---------------------------------------------------------------------------
# Playwright (opt-in, lazy import)
# ---------------------------------------------------------------------------

_PLAYWRIGHT_AVAILABLE: bool | None = None
_PLAYWRIGHT_BROWSER: Any | None = None
_PLAYWRIGHT_INSTANCE: Any | None = None
_PLAYWRIGHT_REAL_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _playwright_available() -> bool:
    """Check si Playwright está instalado (sin lanzar import si ya falló antes)."""
    global _PLAYWRIGHT_AVAILABLE
    if _PLAYWRIGHT_AVAILABLE is not None:
        return _PLAYWRIGHT_AVAILABLE
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        _PLAYWRIGHT_AVAILABLE = True
    except ImportError:
        _PLAYWRIGHT_AVAILABLE = False
    return _PLAYWRIGHT_AVAILABLE


def _get_playwright_browser() -> Any:
    """Singleton de browser para reutilizar entre sources."""
    global _PLAYWRIGHT_BROWSER, _PLAYWRIGHT_INSTANCE
    if _PLAYWRIGHT_BROWSER is not None:
        return _PLAYWRIGHT_BROWSER
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_INSTANCE = sync_playwright().start()
    # Argumentos para reducir señales de automation detectables por WAF.
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--no-sandbox",
    ]
    _PLAYWRIGHT_BROWSER = _PLAYWRIGHT_INSTANCE.chromium.launch(
        headless=True, args=launch_args
    )
    return _PLAYWRIGHT_BROWSER


def close_playwright() -> None:
    """Cierra browser al final del run (best-effort)."""
    global _PLAYWRIGHT_BROWSER, _PLAYWRIGHT_INSTANCE
    if _PLAYWRIGHT_BROWSER is not None:
        try:
            _PLAYWRIGHT_BROWSER.close()
        except Exception:
            pass
        _PLAYWRIGHT_BROWSER = None
    if _PLAYWRIGHT_INSTANCE is not None:
        try:
            _PLAYWRIGHT_INSTANCE.stop()
        except Exception:
            pass
        _PLAYWRIGHT_INSTANCE = None


def fetch_with_playwright(
    url: str, timeout_ms: int = 30000, wait_until: str = "domcontentloaded"
) -> tuple[str, dict[str, Any]]:
    """Renderiza la página con Chromium headless y devuelve (html, metadata).

    Requiere `pip install playwright && playwright install chromium`.
    """
    if not _playwright_available():
        raise RuntimeError(
            "Playwright no está instalado. Instalar con: "
            "pip install playwright && playwright install chromium"
        )
    browser = _get_playwright_browser()
    context = browser.new_context(
        user_agent=_PLAYWRIGHT_REAL_UA,
        locale="es-ES",
        viewport={"width": 1366, "height": 900},
        extra_http_headers={
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24", "Google Chrome";v="131"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Upgrade-Insecure-Requests": "1",
        },
    )
    # Stealth: ocultar señales de automation (navigator.webdriver, etc.)
    context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', {
          get: () => [
            { name: 'PDF Viewer' }, { name: 'Chrome PDF Viewer' },
            { name: 'Chromium PDF Viewer' }, { name: 'Microsoft Edge PDF Viewer' },
            { name: 'WebKit built-in PDF' }
          ]
        });
        Object.defineProperty(navigator, 'languages', { get: () => ['es-ES', 'es', 'en-US', 'en'] });
        window.chrome = { runtime: {} };
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) =>
          parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters);
        """
    )
    page = context.new_page()
    start = time.perf_counter()
    response = None
    try:
        response = page.goto(url, timeout=timeout_ms, wait_until=wait_until)
        # Si la página parece ser un challenge de Cloudflare/Akamai, esperar más.
        try:
            title = page.title().lower()
            if any(t in title for t in ("just a moment", "attention required", "access denied", "verification")):
                page.wait_for_timeout(6000)
        except Exception:
            pass
        # Esperar a que aparezca algún <a> con texto (best-effort, no falla si no llega).
        try:
            page.wait_for_function(
                """() => Array.from(document.querySelectorAll('a'))
                       .some(a => (a.textContent || '').trim().length > 5)""",
                timeout=8000,
            )
        except Exception:
            pass
        # Scroll para disparar lazy-load.
        try:
            page.evaluate(
                """async () => {
                  const total = document.body.scrollHeight;
                  for (let y = 0; y < total; y += 500) {
                    window.scrollTo(0, y);
                    await new Promise(r => setTimeout(r, 100));
                  }
                  window.scrollTo(0, 0);
                }"""
            )
            page.wait_for_timeout(1500)
        except Exception:
            pass
        html = page.content()
    finally:
        page.close()
        context.close()
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    metadata: dict[str, Any] = {
        "http_status": response.status if response else None,
        "content_type": "text/html (playwright)",
        "fetch_ms": elapsed_ms,
        "final_url": page.url if not page.is_closed() else url,
        "rendered_with": "playwright",
    }
    return html, metadata


def candidate_from_source(source: Source, title: str, url: str, description: str, published_at: str = "") -> Candidate:
    return Candidate(
        title=title or f"Hallazgo en {source.name}",
        url=url or source.url,
        source=source.name,
        source_url=source.url,
        country=source.country,
        language=source.language,
        publisher=source.publisher,
        source_class=source.source_class,
        tags=source.tags,
        description=description[:2500],
        published_at=published_at,
    )


def extract_with_selectors(source: Source, soup: BeautifulSoup, max_items: int) -> list[Candidate]:
    selectors = source.selectors or {}
    item_selector = selectors.get("item_selector")
    if not item_selector:
        return []

    title_selector = selectors.get("title_selector")
    link_selector = selectors.get("link_selector")
    description_selector = selectors.get("description_selector")
    candidates: list[Candidate] = []

    try:
        cards = soup.select(item_selector)[:max_items]
    except Exception as exc:
        print(f"[WARN] Selector inválido en {source.name}: {exc}")
        return []

    for card in cards:
        title = ""
        link = ""
        description = ""

        if title_selector:
            title_el = card.select_one(title_selector)
            title = clean_text(title_el.get_text(" ", strip=True) if title_el else "")

        if link_selector:
            link_el = card.select_one(link_selector)
            if link_el and link_el.has_attr("href"):
                link = canonicalize_url(source.url, link_el.get("href"))

        if not link:
            first_link = card.find("a", href=True)
            if first_link:
                link = canonicalize_url(source.url, first_link.get("href"))

        if not title:
            if link_selector:
                link_el = card.select_one(link_selector)
                title = clean_text(link_el.get_text(" ", strip=True) if link_el else "")
            if not title:
                title = clean_text(card.get_text(" ", strip=True))[:180]

        if description_selector:
            desc_el = card.select_one(description_selector)
            description = clean_text(desc_el.get_text(" ", strip=True) if desc_el else "")
        if not description:
            description = clean_text(card.get_text(" ", strip=True))

        if title or description:
            candidates.append(candidate_from_source(source, title, link or source.url, description))

    return candidates


def make_snippets(text: str, signals: list[str], limit: int = 5) -> list[str]:
    clean = clean_text(text)
    lower = normalize_text(clean)
    snippets: list[str] = []
    for signal in signals:
        normalized_signal = normalize_text(signal)
        index = lower.find(normalized_signal)
        if index < 0:
            continue
        start = max(0, index - 180)
        end = min(len(clean), index + 360)
        snippet = clean[start:end].strip()
        if snippet:
            snippets.append(f"...{snippet}...")
        if len(snippets) >= limit:
            break
    return snippets


CHROME_SELECTORS_TO_STRIP = [
    "header",
    "footer",
    "nav",
    "aside",
    "[role='navigation']",
    "[role='banner']",
    "[role='contentinfo']",
    "[class*='menu']",
    "[class*='Menu']",
    "[class*='footer']",
    "[class*='Footer']",
    "[class*='header']",
    "[class*='Header']",
    "[class*='nav']",
    "[id*='menu']",
    "[id*='footer']",
    "[id*='header']",
]


def strip_chrome(soup: BeautifulSoup) -> None:
    """Quita menús, headers, footers y nav del soup para reducir contaminación."""
    for selector in CHROME_SELECTORS_TO_STRIP:
        for tag in soup.select(selector):
            tag.decompose()


def _container_signature(tag: Any) -> tuple[str, tuple[str, ...]] | None:
    """Firma estable de un tag para agrupar contenedores 'iguales'."""
    classes = tag.get("class") or []
    if not classes:
        return None
    return (tag.name, tuple(sorted(classes)))


def _median_description_length(tags: list[Any]) -> int:
    """Devuelve la longitud mediana del texto agrupado de una lista de tags."""
    if not tags:
        return 0
    lengths = sorted(len(clean_text(t.get_text(" ", strip=True))) for t in tags)
    return lengths[len(lengths) // 2]


def _detect_table_rows(soup: BeautifulSoup, source_url: str) -> list[Any]:
    """Detecta filas de tabla con anchors únicos.

    Estrategia: agrega TODOS los <tr> del documento con anchor único.
    Algunos sitios (Listado Manga) usan muchas mini-tablas en lugar de una grande;
    el conjunto global todavía representa una lista de productos.
    """
    usable: list[Any] = []
    seen: set[str] = set()
    for row in soup.find_all("tr"):
        anchor = row.find("a", href=True)
        if not anchor:
            continue
        url = canonicalize_url(source_url, anchor.get("href"))
        if not url or url in seen:
            continue
        seen.add(url)
        usable.append(row)
    if len(usable) >= 10:
        return usable
    return []


def detect_product_clusters(soup: BeautifulSoup, source_url: str) -> list[Any]:
    """Detecta clusters de tarjetas de producto en el HTML.

    Estrategia:
    1. Selectores directos típicos de e-commerce (cualquier tag).
    2. Filas de tabla repetidas (sitios tipo Listado Manga).
    3. Agrupación por (tag, classes); el grupo gana por tamaño * calidad
       de descripción (clusters image-only pierden frente a cards reales).
    """
    direct_selectors = [
        "[class*='product-item']",
        "[class*='product-card']",
        "[class*='ProductCard']",
        "[class*='ProductItem']",
        "[class*='product-tile']",
        "[class*='ProductTile']",
        ".product-item",
        ".product-card",
        ".product",
        "li[class*='product']",
        "div[class*='product']",
        "article[class*='product']",
        "article[class*='post']",
        "article[class*='entry']",
        "[class*='item-product']",
        "[class*='news-item']",
        "[class*='post-item']",
    ]
    for selector in direct_selectors:
        try:
            matches = soup.select(selector)
        except Exception:
            continue
        usable = [m for m in matches if m.find("a", href=True)]
        if len(usable) >= 3:
            return usable

    # 2) Tablas con filas repetidas (Listado Manga y similares).
    table_rows = _detect_table_rows(soup, source_url)
    if table_rows:
        return table_rows

    # 3) Agrupación por firma de tag+classes, ponderada por calidad de descripción.
    groups: dict[tuple[str, tuple[str, ...]], list[Any]] = {}
    for tag in soup.find_all(["article", "li", "div", "section"]):
        signature = _container_signature(tag)
        if signature is None:
            continue
        groups.setdefault(signature, []).append(tag)

    candidates_with_score: list[tuple[float, list[Any]]] = []
    fallback_best: list[Any] = []
    for tags in groups.values():
        if len(tags) < 3:
            continue
        hrefs: set[str] = set()
        usable: list[Any] = []
        for tag in tags:
            anchor = tag.find("a", href=True)
            if not anchor:
                continue
            url = canonicalize_url(source_url, anchor.get("href"))
            if not url or url in hrefs:
                continue
            hrefs.add(url)
            usable.append(tag)
        if len(usable) < 3:
            continue
        if len(usable) > len(fallback_best):
            fallback_best = usable
        joined_classes = " ".join(usable[0].get("class") or []).lower()
        keyword_bonus = sum(
            keyword in joined_classes
            for keyword in ("product", "item", "card", "post", "tile", "article", "entry")
        )
        median_desc = _median_description_length(usable)
        # Score: tamaño * (1 + log2 calidad de descripción) + bonus de keywords.
        # Esto hace que un cluster de cards reales (median 200) le gane a uno de
        # solo imágenes (median 5) aunque tenga menos elementos.
        import math
        quality = math.log2(max(median_desc, 1) + 1)
        score = len(usable) * (1 + quality * 0.4) + keyword_bonus * 3
        candidates_with_score.append((score, usable))

    if candidates_with_score:
        candidates_with_score.sort(key=lambda x: x[0], reverse=True)
        return candidates_with_score[0][1]
    return fallback_best


def _derive_title(card: Any, anchor: Any) -> str:
    """Extrae título de un card en orden de prioridad razonable."""
    title = clean_text(anchor.get_text(" ", strip=True))
    if title:
        return title
    # Anchor envuelve solo una imagen: probar alt.
    img = anchor.find("img")
    if img:
        alt = clean_text(img.get("alt") or img.get("title") or "")
        if alt:
            return alt
    # Headings dentro de la card.
    heading = card.find(["h1", "h2", "h3", "h4", "h5", "h6"])
    if heading:
        text = clean_text(heading.get_text(" ", strip=True))
        if text:
            return text
    # Elementos con class title/name/heading.
    for selector in ("[class*='title']", "[class*='Title']", "[class*='name']", "[class*='Name']"):
        try:
            node = card.select_one(selector)
        except Exception:
            continue
        if node:
            text = clean_text(node.get_text(" ", strip=True))
            if text:
                return text
    # Última opción: img alt de cualquier imagen dentro de la card.
    img = card.find("img")
    if img:
        alt = clean_text(img.get("alt") or img.get("title") or "")
        if alt:
            return alt
    return ""


def _candidate_from_card(source: Source, card: Any) -> Candidate | None:
    anchor = card.find("a", href=True)
    if not anchor:
        return None
    url = canonicalize_url(source.url, anchor.get("href"))
    if not url:
        return None
    title = _derive_title(card, anchor)
    if not title or len(title) < 3:
        return None
    description = clean_text(card.get_text(" ", strip=True))
    # Filtro de longitudes: bloques contaminados (>2000) o ruido (<25).
    # 25 chars permite cards de e-commerce con título corto + precio.
    if len(description) < 25 or len(description) > 2000:
        return None
    return candidate_from_source(source, title[:260], url, description)


JS_SHELL_IDS = ("root", "app", "__next", "__nuxt", "react-root", "react-app")


def detect_empty_or_js(html_text: str, soup: BeautifulSoup) -> tuple[str, str] | None:
    """Devuelve (categoria, mensaje) si el HTML parece vacío o JS-renderizado.

    Categorías: 'empty' (HTML muy corto), 'js-shell' (div root/app vacío),
    'no-links' (ningún <a> con texto significativo). Devuelve None si parece OK.
    """
    raw_len = len(html_text or "")
    if raw_len < 5000:
        return ("empty", f"HTML muy corto ({raw_len} chars). Probablemente JS-rendered o vacío.")

    for shell_id in JS_SHELL_IDS:
        node = soup.find(id=shell_id)
        if node is None:
            continue
        inner_text = clean_text(node.get_text(" ", strip=True))
        if len(inner_text) < 80 and not node.find("a", href=True):
            return (
                "js-shell",
                f"<{node.name} id='{shell_id}'> sin contenido. Probablemente requiere Playwright.",
            )

    significant_links = 0
    for anchor in soup.find_all("a", href=True):
        text = clean_text(anchor.get_text(" ", strip=True))
        if len(text) >= 10:
            significant_links += 1
            if significant_links >= 5:
                break
    if significant_links < 5:
        return (
            "no-links",
            f"Sin enlaces con texto significativo ({significant_links} encontrados). JS o página vacía.",
        )

    return None


def extract_generic_html(
    source: Source,
    html_text: str,
    max_items: int,
    info: dict[str, Any] | None = None,
) -> list[Candidate]:
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    # 1) Selectores manuales del YAML tienen prioridad.
    selector_candidates = extract_with_selectors(source, soup, max_items=max_items)
    if selector_candidates:
        if info is not None:
            info["extraction_method"] = "yaml-selectors"
            info["cards_found"] = len(selector_candidates)
            info["candidates_after_signals"] = len(selector_candidates)
        return selector_candidates

    # 2) Quitamos menú/footer/nav del soup antes de buscar productos.
    strip_chrome(soup)

    # 3) Detectamos clusters de productos repetidos.
    cards = detect_product_clusters(soup, source.url)
    if info is not None:
        info["extraction_method"] = "clusters" if cards else "none"
        info["cards_found"] = len(cards)
        info["cards_skipped_no_anchor"] = 0
        info["cards_skipped_short_desc"] = 0
        info["cards_skipped_long_desc"] = 0
        info["cards_skipped_dup_url"] = 0
        info["cards_skipped_no_signals"] = 0
        info["candidates_after_signals"] = 0

    if not cards:
        # Sin patrón repetido detectable. Es preferible silencio que ruido.
        return []

    candidates: list[Candidate] = []
    seen_urls: set[str] = set()
    for card in cards[:max_items]:
        candidate = _candidate_from_card(source, card)
        if candidate is None:
            if info is not None:
                # Inspeccionamos por qué fue None para diagnóstico.
                anchor = card.find("a", href=True)
                if not anchor:
                    info["cards_skipped_no_anchor"] += 1
                else:
                    raw_desc_len = len(clean_text(card.get_text(" ", strip=True)))
                    if raw_desc_len < 25:
                        info["cards_skipped_short_desc"] += 1
                    elif raw_desc_len > 2000:
                        info["cards_skipped_long_desc"] += 1
                    else:
                        info["cards_skipped_no_anchor"] += 1
            continue
        if candidate.url in seen_urls:
            if info is not None:
                info["cards_skipped_dup_url"] += 1
            continue
        combined = f"{candidate.title}\n{candidate.description}"
        score, _signals, _types = detect_signals(combined)
        if score <= 0:
            if info is not None:
                info["cards_skipped_no_signals"] += 1
            continue
        seen_urls.add(candidate.url)
        candidates.append(candidate)

    if info is not None:
        info["candidates_after_signals"] = len(candidates)

    return candidates


def _parse_feed_date(value: str) -> dt.datetime | None:
    """Best-effort parse para fechas RSS. Devuelve None si no se puede parsear."""
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    # Intento ISO 8601 (`2024-05-12T10:00:00Z`, `2024-05-12T10:00:00+00:00`).
    try:
        candidate = value.strip().replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except ValueError:
        return None


def extract_rss(source: Source, feed_text: str, max_items: int, max_age_days: int = 0) -> list[Candidate]:
    parsed = feedparser.parse(feed_text)
    candidates: list[Candidate] = []
    cutoff: dt.datetime | None = None
    if max_age_days > 0:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=max_age_days)

    for entry in parsed.entries[:max_items]:
        title = clean_text(entry.get("title", ""))
        link = clean_text(entry.get("link", "")) or source.url
        summary = clean_text(entry.get("summary", "") or entry.get("description", "") or entry.get("content", ""))
        published_at = clean_text(entry.get("published", "") or entry.get("updated", "") or entry.get("created", ""))
        if not title and not summary:
            continue
        if cutoff is not None and published_at:
            parsed_date = _parse_feed_date(published_at)
            if parsed_date is not None and parsed_date < cutoff:
                continue
        combined = f"{title}\n{summary}"
        score, _signals, _types = detect_signals(combined)
        # Para RSS guardamos solo entradas con señales. Esto baja muchísimo el ruido.
        if score <= 0:
            continue
        candidates.append(candidate_from_source(source, title, link, summary, published_at=published_at))
    return candidates


def score_candidate(candidate: Candidate) -> Candidate:
    combined = "\n".join(
        [
            candidate.title,
            candidate.description,
            candidate.publisher,
            candidate.source,
            " ".join(candidate.tags),
        ]
    )
    score, signals, signal_types = detect_signals(combined)

    # Bonus suave por clase de fuente. Las fuentes oficiales/retailer suelen ser más accionables.
    if score > 0:
        if candidate.source_class == "official":
            score += 5
        elif candidate.source_class == "retailer":
            score += 4
        elif candidate.source_class == "social":
            score -= 5

    candidate.score = max(0, min(score, 100))
    candidate.signals = signals
    candidate.signal_types = signal_types
    candidate.content_hash = sha256_text(
        json.dumps(
            {
                "title": candidate.title,
                "url": candidate.url,
                "description": candidate.description,
                "score": candidate.score,
                "signals": candidate.signals,
                "source_class": candidate.source_class,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return candidate


def candidate_key(candidate: Candidate) -> str:
    if candidate.url:
        return f"url:{candidate.url}"
    raw = f"{candidate.source}|{candidate.publisher}|{candidate.title}"
    return f"hash:{sha256_text(raw)}"


def process_state(
    candidates: list[Candidate],
    state: dict[str, Any],
    min_score: int,
    include_seen: bool,
) -> tuple[list[Candidate], dict[str, Any]]:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    deduped: dict[str, Candidate] = {}

    for candidate in candidates:
        key = candidate_key(candidate)
        current = deduped.get(key)
        if current is None or candidate.score > current.score:
            deduped[key] = candidate

    reportable: list[Candidate] = []
    for key, candidate in deduped.items():
        previous = state.get(key)
        if previous is None:
            candidate.status = "new"
        elif previous.get("content_hash") != candidate.content_hash:
            candidate.status = "changed"
        else:
            candidate.status = "seen"

        state[key] = {
            "title": candidate.title,
            "url": candidate.url,
            "source": candidate.source,
            "publisher": candidate.publisher,
            "source_class": candidate.source_class,
            "country": candidate.country,
            "language": candidate.language,
            "score": candidate.score,
            "signals": candidate.signals,
            "signal_types": candidate.signal_types,
            "content_hash": candidate.content_hash,
            "first_seen_at": previous.get("first_seen_at") if previous else now,
            "last_seen_at": now,
        }

        if candidate.score >= min_score and (include_seen or candidate.status in {"new", "changed"}):
            reportable.append(candidate)

    reportable.sort(key=lambda item: item.score, reverse=True)
    return reportable, state


def candidate_to_json(candidate: Candidate) -> dict[str, Any]:
    return {
        "detected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": candidate.status,
        "score": candidate.score,
        "signals": candidate.signals,
        "signal_types": candidate.signal_types,
        "title": candidate.title,
        "url": candidate.url,
        "source": candidate.source,
        "source_url": candidate.source_url,
        "source_class": candidate.source_class,
        "publisher": candidate.publisher,
        "country": candidate.country,
        "language": candidate.language,
        "tags": candidate.tags,
        "published_at": candidate.published_at,
        "description": candidate.description,
        "content_hash": candidate.content_hash,
    }


def markdown_escape_pipe(value: str) -> str:
    return value.replace("|", "\\|")


PROBLEM_CATEGORY_LABELS = {
    "empty": "Vacías / muy cortas",
    "js-shell": "JS-rendered (necesitan Playwright)",
    "no-links": "Sin enlaces significativos",
    "http": "Errores HTTP",
    "request": "Errores de red / timeout",
    "robots": "Bloqueadas por robots.txt",
    "selector": "Selectores YAML inválidos",
    "other": "Otros errores",
}

PROBLEM_CATEGORY_ORDER = list(PROBLEM_CATEGORY_LABELS.keys())


def write_markdown_report(
    path: Path,
    reportable: list[Candidate],
    errors: list[str],
    problems: list[dict[str, str]],
    min_score: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    now_local = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    date_title = dt.date.today().isoformat()

    urgent = [item for item in reportable if item.score >= 70]
    interesting = [item for item in reportable if 35 <= item.score < 70]
    low = [item for item in reportable if item.score < 35]

    lines: list[str] = []
    lines.append(f"# Manga Watch — {date_title}")
    lines.append("")
    lines.append(f"Generado: `{now_local}`")
    lines.append(f"Score mínimo del reporte: `{min_score}`")
    lines.append("")
    lines.append("## Resumen")
    lines.append("")
    lines.append(f"- Hallazgos reportables: **{len(reportable)}**")
    lines.append(f"- Urgentes: **{len(urgent)}**")
    lines.append(f"- Interesantes: **{len(interesting)}**")
    lines.append(f"- Bajos/artbooks simples: **{len(low)}**")
    lines.append(f"- Errores de fuentes: **{len(errors)}**")
    lines.append("")

    if not reportable:
        lines.append("## Sin hallazgos nuevos")
        lines.append("")
        lines.append("No encontré cambios nuevos que pasen el score mínimo.")
        lines.append("")

    def add_section(title: str, items: list[Candidate]) -> None:
        if not items:
            return
        lines.append(f"## {title}")
        lines.append("")
        for index, item in enumerate(items, start=1):
            lines.append(f"### {index}. {item.title}")
            lines.append("")
            lines.append(f"- **Score:** {item.score}")
            lines.append(f"- **Estado:** {item.status}")
            lines.append(f"- **Clase de fuente:** {item.source_class}")
            lines.append(f"- **País:** {item.country or 'N/D'}")
            lines.append(f"- **Idioma:** {item.language or 'N/D'}")
            lines.append(f"- **Editorial/fuente:** {item.publisher or item.source}")
            lines.append(f"- **Fuente:** {item.source}")
            if item.published_at:
                lines.append(f"- **Fecha publicada:** {item.published_at}")
            lines.append(f"- **Señales:** {', '.join(item.signals) if item.signals else 'N/D'}")
            lines.append(f"- **Tipos:** {', '.join(item.signal_types) if item.signal_types else 'N/D'}")
            lines.append(f"- **Tags:** {', '.join(item.tags) if item.tags else 'N/D'}")
            lines.append(f"- **Link:** {item.url}")
            lines.append("")
            if item.description:
                lines.append("**Fragmento:**")
                lines.append("")
                lines.append(f"> {item.description[:1000]}")
                lines.append("")

    add_section("🔥 Urgentes", urgent)
    add_section("✅ Interesantes", interesting)
    add_section("🎨 Bajos / artbooks simples / revisar", low)

    if reportable:
        lines.append("## Tabla rápida")
        lines.append("")
        lines.append("| Score | Estado | Clase | País | Editorial | Título | Link |")
        lines.append("|---:|---|---|---|---|---|---|")
        for item in reportable:
            title = markdown_escape_pipe(item.title[:100])
            publisher = markdown_escape_pipe((item.publisher or item.source)[:60])
            country = markdown_escape_pipe(item.country or "N/D")
            source_class = markdown_escape_pipe(item.source_class or "N/D")
            lines.append(
                f"| {item.score} | {item.status} | {source_class} | {country} | {publisher} | {title} | {item.url} |"
            )
        lines.append("")

    if problems:
        lines.append("## Fuentes problemáticas")
        lines.append("")
        grouped: dict[str, list[dict[str, str]]] = {}
        for problem in problems:
            grouped.setdefault(problem.get("category", "other"), []).append(problem)
        for category in PROBLEM_CATEGORY_ORDER:
            items = grouped.get(category)
            if not items:
                continue
            label = PROBLEM_CATEGORY_LABELS.get(category, category)
            lines.append(f"### {label} ({len(items)})")
            lines.append("")
            for item in items:
                lines.append(f"- **{item.get('source', '?')}** — {item.get('message', '')}")
            lines.append("")
        # Categorías no mapeadas
        unknown_categories = set(grouped.keys()) - set(PROBLEM_CATEGORY_ORDER)
        for category in sorted(unknown_categories):
            items = grouped[category]
            lines.append(f"### {category} ({len(items)})")
            lines.append("")
            for item in items:
                lines.append(f"- **{item.get('source', '?')}** — {item.get('message', '')}")
            lines.append("")

    if errors:
        lines.append("## Errores")
        lines.append("")
        for error in errors:
            lines.append(f"- {error}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def make_telegram_message(reportable: list[Candidate], report_path: Path) -> str:
    today = dt.date.today().isoformat()
    if not reportable:
        return f"Manga Watch — {today}\n\nSin hallazgos nuevos relevantes.\nReporte: {report_path}"

    top = reportable[:10]
    lines: list[str] = []
    lines.append(f"Manga Watch — {today}")
    lines.append("")
    lines.append(f"Hallazgos nuevos/cambiados: {len(reportable)}")
    lines.append("")
    for index, item in enumerate(top, start=1):
        lines.append(f"{index}. [{item.score}] {item.title}")
        lines.append(f"   {item.country or 'N/D'} · {item.publisher or item.source} · {item.source_class}")
        if item.signals:
            lines.append(f"   Señales: {', '.join(item.signals[:6])}")
        lines.append(f"   {item.url}")
        lines.append("")
    if len(reportable) > len(top):
        lines.append(f"...y {len(reportable) - len(top)} más.")
    lines.append(f"Reporte local: {report_path}")
    return "\n".join(lines)


def send_telegram_message(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env o variables de entorno.")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = [text[i : i + 3800] for i in range(0, len(text), 3800)]
    for chunk in chunks:
        response = requests.post(
            url,
            data={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": "true"},
            timeout=(10, 25),
        )
        response.raise_for_status()


def parse_csv_arg(value: str | None) -> set[str] | None:
    if not value:
        return None
    items = {part.strip() for part in value.split(",") if part.strip()}
    return items or None


def _slugify(value: str) -> str:
    """Slug seguro para nombres de archivo."""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "source"


class DiagnosticRecorder:
    """Captura información detallada por fuente para análisis posterior.

    Activado con --diagnostic. Genera tres outputs en log_dir:
    - diagnostic-<timestamp>.json (estructurado, machine-readable)
    - diagnostic-<timestamp>.md   (legible para humanos, agrupado por estado)
    - raw/<slug>.html             (HTML crudo de fuentes problemáticas)
    """

    DUMP_CATEGORIES = {"empty", "js-shell", "no-links", "no-candidates", "http", "request"}
    DUMP_MAX_BYTES = 250 * 1024  # 250 KB por fuente (suficiente para skipear preloads)

    def __init__(self, enabled: bool, log_dir: Path) -> None:
        self.enabled = enabled
        self.log_dir = log_dir
        self.raw_dir = log_dir / "raw"
        self.entries: list[dict[str, Any]] = []
        self.current: dict[str, Any] | None = None
        self.run_started_at = dt.datetime.now()

    def begin(self, source: Source) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        entry: dict[str, Any] = {
            "name": source.name,
            "url": source.url,
            "country": source.country,
            "language": source.language,
            "publisher": source.publisher,
            "source_class": source.source_class,
            "kind": source.kind,
            "status": "pending",
            "http_status": None,
            "content_type": "",
            "fetch_ms": None,
            "html_size": None,
            "anchor_count": None,
            "anchor_count_significant": None,
            "extraction_method": None,
            "cards_found": None,
            "candidates_after_signals": 0,
            "candidates_after_scoring": 0,
            "top_titles": [],
            "top_signals": [],
            "error": None,
            "raw_dump_path": None,
        }
        self.current = entry
        self.entries.append(entry)
        return entry

    def record_fetch(self, metadata: dict[str, Any], html_text: str) -> None:
        if not self.enabled or self.current is None:
            return
        self.current["http_status"] = metadata.get("http_status")
        self.current["content_type"] = metadata.get("content_type", "")
        self.current["fetch_ms"] = metadata.get("fetch_ms")
        self.current["html_size"] = len(html_text or "")

    def record_anchor_counts(self, soup: BeautifulSoup) -> None:
        if not self.enabled or self.current is None:
            return
        all_anchors = soup.find_all("a", href=True)
        significant = 0
        for anchor in all_anchors:
            if len(clean_text(anchor.get_text(" ", strip=True))) >= 10:
                significant += 1
        self.current["anchor_count"] = len(all_anchors)
        self.current["anchor_count_significant"] = significant

    def record_status(self, status: str, message: str = "") -> None:
        if not self.enabled or self.current is None:
            return
        self.current["status"] = status
        if message:
            self.current["error"] = message

    def record_error(self, exc: Exception) -> None:
        if not self.enabled or self.current is None:
            return
        self.current["status"] = self.current.get("status") or "other"
        self.current["error"] = f"{type(exc).__name__}: {exc}"

    def record_candidates(self, candidates: list[Candidate]) -> None:
        if not self.enabled or self.current is None:
            return
        scored_with_signals = [c for c in candidates if c.score > 0]
        self.current["candidates_after_scoring"] = len(scored_with_signals)
        top = sorted(scored_with_signals, key=lambda c: c.score, reverse=True)[:5]
        self.current["top_titles"] = [
            {"score": c.score, "title": c.title[:160], "url": c.url} for c in top
        ]
        seen_signals: list[str] = []
        for c in top:
            for sig in c.signals:
                if sig not in seen_signals:
                    seen_signals.append(sig)
        self.current["top_signals"] = seen_signals[:10]

    def maybe_dump_html(self, entry: dict[str, Any] | None, html_text: str) -> None:
        if not self.enabled or entry is None:
            return
        status = entry.get("status")
        if status not in self.DUMP_CATEGORIES:
            return
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        slug = _slugify(entry["name"])
        path = self.raw_dir / f"{slug}.html"
        snippet = (html_text or "")[: self.DUMP_MAX_BYTES]
        path.write_text(snippet, encoding="utf-8", errors="replace")
        entry["raw_dump_path"] = str(path)

    def end(self) -> dict[str, Any] | None:
        """Finaliza el status del entry actual y devuelve el entry (o None)."""
        if not self.enabled or self.current is None:
            self.current = None
            return None
        entry = self.current
        if entry.get("status") == "pending":
            if entry.get("candidates_after_scoring", 0) > 0:
                entry["status"] = "ok"
            else:
                entry["status"] = "no-candidates"
        self.current = None
        return entry

    def write(self) -> tuple[Path, Path] | None:
        if not self.enabled:
            return None
        self.log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = self.run_started_at.strftime("%Y-%m-%d-%H%M%S")
        json_path = self.log_dir / f"diagnostic-{timestamp}.json"
        md_path = self.log_dir / f"diagnostic-{timestamp}.md"

        # ---- JSON ----
        summary = self._build_summary()
        payload = {
            "run_started_at": self.run_started_at.isoformat(),
            "summary": summary,
            "sources": self.entries,
        }
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False),
            encoding="utf-8",
        )

        # ---- Markdown ----
        md_path.write_text(self._build_markdown(summary), encoding="utf-8")
        return json_path, md_path

    def _build_summary(self) -> dict[str, Any]:
        by_status: dict[str, int] = {}
        slow_sources: list[dict[str, Any]] = []
        no_candidate_sources: list[str] = []
        for entry in self.entries:
            status = entry.get("status") or "unknown"
            by_status[status] = by_status.get(status, 0) + 1
            fetch_ms = entry.get("fetch_ms") or 0
            if fetch_ms > 5000:
                slow_sources.append({"name": entry["name"], "fetch_ms": fetch_ms})
            if status == "no-candidates":
                no_candidate_sources.append(entry["name"])
        return {
            "total_sources": len(self.entries),
            "by_status": by_status,
            "slow_sources_over_5s": slow_sources,
            "no_candidate_sources": no_candidate_sources,
        }

    def _build_markdown(self, summary: dict[str, Any]) -> str:
        STATUS_ORDER = [
            ("ok", "✅ OK — candidatos con señales"),
            ("no-candidates", "⚠️ OK pero sin candidatos detectados"),
            ("empty", "🚫 HTML vacío / muy corto"),
            ("js-shell", "🧩 JS-rendered (SPA shell)"),
            ("no-links", "🔗 Sin enlaces significativos"),
            ("http", "❌ Error HTTP"),
            ("request", "🌐 Error de red / timeout"),
            ("robots", "🤖 Bloqueado por robots.txt"),
            ("other", "💥 Otros errores"),
        ]
        grouped: dict[str, list[dict[str, Any]]] = {}
        for entry in self.entries:
            grouped.setdefault(entry.get("status") or "unknown", []).append(entry)

        lines: list[str] = []
        lines.append(f"# Manga Watch — diagnóstico {self.run_started_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("## Resumen")
        lines.append("")
        lines.append(f"- Fuentes totales analizadas: **{summary['total_sources']}**")
        for status, count in summary["by_status"].items():
            label = next((lbl for s, lbl in STATUS_ORDER if s == status), status)
            lines.append(f"- {label}: **{count}**")
        if summary["slow_sources_over_5s"]:
            lines.append("")
            lines.append("### Fuentes lentas (>5s)")
            for item in summary["slow_sources_over_5s"]:
                lines.append(f"- {item['name']} — {item['fetch_ms']} ms")
        lines.append("")

        for status, label in STATUS_ORDER:
            items = grouped.get(status, [])
            if not items:
                continue
            lines.append(f"## {label} ({len(items)})")
            lines.append("")
            for entry in items:
                self._render_entry(lines, entry)
        # Estados no mapeados
        rendered = {s for s, _ in STATUS_ORDER}
        for status, items in grouped.items():
            if status in rendered:
                continue
            lines.append(f"## {status} ({len(items)})")
            lines.append("")
            for entry in items:
                self._render_entry(lines, entry)
        return "\n".join(lines)

    def _render_entry(self, lines: list[str], entry: dict[str, Any]) -> None:
        lines.append(f"### {entry['name']}")
        lines.append("")
        lines.append(f"- **URL:** {entry['url']}")
        lines.append(f"- **Clase / país:** {entry['source_class']} · {entry['country']}")
        lines.append(f"- **Kind:** {entry['kind']}")
        if entry.get("http_status") is not None:
            lines.append(f"- **HTTP:** {entry['http_status']} · {entry.get('content_type', '')}")
        if entry.get("fetch_ms") is not None:
            lines.append(f"- **Tiempo fetch:** {entry['fetch_ms']} ms")
        if entry.get("html_size") is not None:
            lines.append(f"- **Tamaño HTML:** {entry['html_size']} chars")
        if entry.get("anchor_count") is not None:
            lines.append(
                f"- **Anchors:** {entry['anchor_count']} totales · "
                f"{entry['anchor_count_significant']} con texto ≥10 chars"
            )
        if entry.get("extraction_method"):
            lines.append(f"- **Método extracción:** {entry['extraction_method']}")
        if entry.get("cards_found") is not None:
            lines.append(f"- **Cards detectados:** {entry['cards_found']}")
        skips = []
        for key, label in [
            ("cards_skipped_no_anchor", "sin anchor"),
            ("cards_skipped_short_desc", "desc <40"),
            ("cards_skipped_long_desc", "desc >2000"),
            ("cards_skipped_dup_url", "url duplicada"),
            ("cards_skipped_no_signals", "sin señales"),
        ]:
            value = entry.get(key)
            if value:
                skips.append(f"{label}: {value}")
        if skips:
            lines.append(f"- **Cards descartados:** {' · '.join(skips)}")
        lines.append(
            f"- **Candidatos con señales:** {entry.get('candidates_after_scoring', 0)}"
        )
        if entry.get("top_signals"):
            lines.append(f"- **Top señales:** {', '.join(entry['top_signals'])}")
        if entry.get("top_titles"):
            lines.append("- **Top títulos:**")
            for top in entry["top_titles"]:
                lines.append(f"    - `[{top['score']}]` {top['title']} → {top['url']}")
        if entry.get("error"):
            lines.append(f"- **Error:** `{entry['error']}`")
        if entry.get("raw_dump_path"):
            lines.append(f"- **HTML crudo:** `{entry['raw_dump_path']}`")
        lines.append("")


def run(args: argparse.Namespace) -> int:
    load_dotenv()

    configure_detection(
        fuzzy=bool(getattr(args, "fuzzy_keywords", False)),
        fuzzy_divisor=int(getattr(args, "fuzzy_divisor", 3)),
    )

    sources_path = Path(args.sources)
    data_dir = Path(args.data_dir)
    reports_dir = Path(args.reports_dir)

    sources_all = load_sources(sources_path)
    sources = filter_sources(
        sources_all,
        source_classes=parse_csv_arg(args.source_classes),
        countries=parse_csv_arg(args.countries),
        include_disabled=args.include_disabled,
    )

    only_source = (args.only_source or "").strip()
    if only_source:
        matched = [s for s in sources_all if s.name == only_source]
        if not matched:
            available = ", ".join(s.name for s in sources_all)
            print(f"[ERROR] --only-source '{only_source}' no coincide con ninguna fuente.")
            print(f"        Fuentes disponibles: {available}")
            return 2
        sources = matched

    if args.list_sources:
        for source in sources:
            enabled = "enabled" if source.enabled else "disabled"
            print(f"[{enabled}] {source.source_class:13s} | {source.country:16s} | {source.name} | {source.url}")
        return 0

    state_path = data_dir / "state.json"
    items_path = data_dir / "items.jsonl"
    report_path = reports_dir / f"{dt.date.today().isoformat()}.md"

    state = load_state(state_path)
    session = make_session(args.user_agent)
    robots = RobotsCache(args.user_agent)

    all_candidates: list[Candidate] = []
    errors: list[str] = []
    problems: list[dict[str, str]] = []

    log_dir = Path(getattr(args, "log_dir", "logs"))
    diagnostic = DiagnosticRecorder(enabled=bool(getattr(args, "diagnostic", False)), log_dir=log_dir)

    def record_problem(source_name: str, category: str, message: str) -> None:
        problems.append({"source": source_name, "category": category, "message": message})

    print(f"[INFO] Fuentes totales en YAML: {len(sources_all)}")
    print(f"[INFO] Fuentes activas tras filtros: {len(sources)}")
    print(f"[INFO] Score mínimo: {args.min_score}")
    print(f"[INFO] Clases: {args.source_classes or 'todas'}")
    print(f"[INFO] Países: {args.countries or 'todos'}")
    print(f"[INFO] Respetar robots.txt: {args.respect_robots}")

    for index, source in enumerate(sources, start=1):
        print(f"[{index}/{len(sources)}] {source.name} :: {source.url}")
        diagnostic.begin(source)
        text = ""
        info: dict[str, Any] | None = diagnostic.current if diagnostic.enabled else None
        try:
            if args.respect_robots and not robots.allowed(source.url):
                message = f"robots.txt no permite acceder a {source.url}"
                print(f"[SKIP] {message}")
                errors.append(f"{source.name}: {message}")
                record_problem(source.name, "robots", message)
                diagnostic.record_status("robots", message)
                continue

            if source.kind == "js":
                if not args.enable_js:
                    message = "Fuente kind:js requiere --enable-js (Playwright)"
                    print(f"[SKIP-js] {source.name}: {message}")
                    record_problem(source.name, "js-shell", message)
                    diagnostic.record_status("js-shell", message)
                    continue
                if not _playwright_available():
                    message = "Playwright no instalado. Ver requirements-playwright.txt"
                    print(f"[ERROR] {source.name}: {message}")
                    errors.append(f"{source.name}: {message}")
                    record_problem(source.name, "other", message)
                    diagnostic.record_status("other", message)
                    continue
                text, fetch_meta = fetch_with_playwright(
                    url=source.url,
                    timeout_ms=args.read_timeout * 1000,
                )
            else:
                text, fetch_meta = fetch_with_metadata(
                    session=session,
                    url=source.url,
                    timeout=(args.connect_timeout, args.read_timeout),
                )
            diagnostic.record_fetch(fetch_meta, text)

            if source.kind in {"rss", "feed", "atom"}:
                candidates = extract_rss(
                    source,
                    text,
                    max_items=args.max_items_per_source,
                    max_age_days=args.max_age_days,
                )
                if diagnostic.enabled and info is not None:
                    info["extraction_method"] = "rss"
                    info["candidates_after_signals"] = len(candidates)
            else:
                pre_soup = BeautifulSoup(text, "html.parser")
                for stripped in pre_soup(["script", "style", "noscript", "svg"]):
                    stripped.decompose()
                diagnostic.record_anchor_counts(pre_soup)
                # Si ya renderizamos con Playwright, saltamos el check de JS-shell
                # (era para detectar páginas que necesitan exactamente esto).
                if source.kind == "js":
                    candidates = extract_generic_html(
                        source,
                        text,
                        max_items=args.max_items_per_source,
                        info=info,
                    )
                else:
                    js_check = detect_empty_or_js(text, pre_soup)
                    if js_check is not None:
                        category, message = js_check
                        print(f"[SKIP-{category}] {source.name}: {message}")
                        record_problem(source.name, category, message)
                        diagnostic.record_status(category, message)
                        candidates = []
                    else:
                        candidates = extract_generic_html(
                            source,
                            text,
                            max_items=args.max_items_per_source,
                            info=info,
                        )

            scored = [score_candidate(candidate) for candidate in candidates]
            all_candidates.extend(scored)
            diagnostic.record_candidates(scored)
            print(f"    candidatos con señales: {len(scored)}")

        except requests.HTTPError as exc:
            message = f"{source.name}: HTTP error {exc}"
            print(f"[ERROR] {message}")
            errors.append(message)
            record_problem(source.name, "http", str(exc))
            diagnostic.record_status("http", str(exc))
        except requests.RequestException as exc:
            message = f"{source.name}: request error {exc}"
            print(f"[ERROR] {message}")
            errors.append(message)
            record_problem(source.name, "request", str(exc))
            diagnostic.record_status("request", str(exc))
        except Exception as exc:
            message = f"{source.name}: error inesperado {exc}"
            print(f"[ERROR] {message}")
            errors.append(message)
            record_problem(source.name, "other", str(exc))
            diagnostic.record_error(exc)
        finally:
            finalized = diagnostic.end()
            diagnostic.maybe_dump_html(finalized, text)

        if args.sleep_seconds > 0 and index < len(sources):
            time.sleep(args.sleep_seconds)

    reportable, state = process_state(
        candidates=all_candidates,
        state=state,
        min_score=args.min_score,
        include_seen=args.include_seen,
    )

    if not args.dry_run:
        save_state(state_path, state)
        new_or_changed_rows = [
            candidate_to_json(candidate) for candidate in reportable if candidate.status in {"new", "changed"}
        ]
        append_jsonl(items_path, new_or_changed_rows)
        write_markdown_report(
            path=report_path,
            reportable=reportable,
            errors=errors,
            problems=problems,
            min_score=args.min_score,
        )

    print("")
    print("[RESUMEN]")
    print(f"  candidatos totales con señales: {len(all_candidates)}")
    print(f"  reportables: {len(reportable)}")
    print(f"  errores: {len(errors)}")
    print(f"  reporte: {report_path}")

    diagnostic_paths = diagnostic.write()
    if diagnostic_paths is not None:
        json_path, md_path = diagnostic_paths
        print("")
        print("[DIAGNÓSTICO]")
        print(f"  json: {json_path}")
        print(f"  markdown: {md_path}")
        if (diagnostic.raw_dir).exists():
            dumps = sorted(diagnostic.raw_dir.glob("*.html"))
            print(f"  HTMLs crudos (fuentes problemáticas): {len(dumps)} en {diagnostic.raw_dir}/")

    if args.list_empty_sources:
        empty_categories = {"empty", "js-shell", "no-links"}
        empty_problems = [p for p in problems if p.get("category") in empty_categories]
        print("")
        print(f"[FUENTES VACÍAS / JS-rendered] ({len(empty_problems)})")
        for problem in empty_problems:
            print(f"  [{problem['category']}] {problem['source']} — {problem['message']}")

    if args.send_telegram and not args.dry_run:
        try:
            send_telegram_message(make_telegram_message(reportable, report_path))
            print("[OK] Envié alerta por Telegram")
        except Exception as exc:
            print(f"[ERROR] No pude enviar Telegram: {exc}")
            close_playwright()
            return 2

    close_playwright()
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tracker personal de mangas físicos coleccionistas y artbooks.")
    parser.add_argument("--sources", default="sources.yml", help="Archivo YAML con fuentes. Default: sources.yml")
    parser.add_argument("--data-dir", default="data", help="Directorio de datos. Default: data")
    parser.add_argument("--reports-dir", default="reports", help="Directorio de reportes Markdown. Default: reports")
    parser.add_argument("--min-score", type=int, default=30, help="Score mínimo. Default: 30, recomendado para incluir artbooks")
    parser.add_argument("--max-items-per-source", type=int, default=80, help="Máximo candidatos por fuente. Default: 80")
    parser.add_argument("--sleep-seconds", type=float, default=1.5, help="Pausa entre fuentes. Default: 1.5")
    parser.add_argument("--connect-timeout", type=int, default=10, help="Timeout conexión HTTP. Default: 10")
    parser.add_argument("--read-timeout", type=int, default=30, help="Timeout lectura HTTP. Default: 30")
    parser.add_argument("--user-agent", default="manga-watch-personal/0.2 (+personal-use)", help="User-Agent")
    parser.add_argument("--respect-robots", action="store_true", help="Respeta robots.txt antes de consultar cada fuente")
    parser.add_argument("--include-seen", action="store_true", help="Incluye elementos ya vistos en el reporte")
    parser.add_argument("--include-disabled", action="store_true", help="Incluye fuentes enabled:false")
    parser.add_argument("--source-classes", default="", help="Filtra por clases: official,retailer,trusted_media,social")
    parser.add_argument("--countries", default="", help="Filtra por país exacto, separado por comas. Ej: España,Francia,Japón")
    parser.add_argument("--send-telegram", action="store_true", help="Envía resumen por Telegram")
    parser.add_argument("--list-sources", action="store_true", help="Lista fuentes tras filtros y termina")
    parser.add_argument(
        "--list-empty-sources",
        action="store_true",
        help="Al final, lista fuentes detectadas como vacías/JS-rendered",
    )
    parser.add_argument(
        "--only-source",
        default="",
        help="Procesa solo la fuente con este nombre exacto (útil para debug).",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=30,
        help="Para feeds RSS, ignora entradas más viejas que N días. 0 = sin filtro. Default: 30",
    )
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="Activa modo diagnóstico: dumpea JSON/Markdown con stats por fuente y HTML crudo de fuentes problemáticas",
    )
    parser.add_argument(
        "--log-dir",
        default="logs",
        help="Directorio para logs diagnósticos. Default: logs",
    )
    parser.add_argument(
        "--enable-js",
        action="store_true",
        help="Habilita rendering con Playwright para fuentes con kind:js. Requiere 'pip install playwright && playwright install chromium'",
    )
    parser.add_argument(
        "--fuzzy-keywords",
        action="store_true",
        help="Activa matching por palabra individual además de la frase exacta. 'tomo especial' matchea 'edición especial' con score reducido.",
    )
    parser.add_argument(
        "--fuzzy-divisor",
        type=int,
        default=3,
        help="Divisor del score cuando una palabra fuzzy matchea pero no la frase completa. Default: 3",
    )
    parser.add_argument("--dry-run", action="store_true", help="Ejecuta sin escribir estado, JSONL ni reportes")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
