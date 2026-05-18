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


def detect_signals(text: str) -> tuple[int, list[str], list[str]]:
    normalized = normalize_text(text)
    matched_phrases: list[str] = []
    matched_types: list[str] = []
    score = 0

    for rule in KEYWORD_RULES:
        phrase = str(rule["phrase"])
        normalized_phrase = normalize_text(phrase)
        if normalized_phrase and normalized_phrase in normalized:
            matched_phrases.append(phrase)
            matched_types.append(str(rule["type"]))
            score += int(rule["score"])

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


def extract_generic_html(source: Source, html_text: str, max_items: int) -> list[Candidate]:
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    selector_candidates = extract_with_selectors(source, soup, max_items=max_items)
    if selector_candidates:
        return selector_candidates

    candidates: list[Candidate] = []
    seen_urls: set[str] = set()

    # Estrategia genérica: link + bloque padre. Solo guardamos si hay señales.
    for anchor in soup.find_all("a", href=True):
        if len(candidates) >= max_items:
            break
        url = canonicalize_url(source.url, anchor.get("href"))
        if not url or url in seen_urls:
            continue
        title = clean_text(anchor.get_text(" ", strip=True))
        if not title or len(title) < 3:
            continue
        parent = anchor.find_parent(["article", "li", "section", "div"]) or anchor.parent
        description = clean_text(parent.get_text(" ", strip=True) if parent else title)
        combined = f"{title}\n{description}"
        score, _signals, _types = detect_signals(combined)
        if score <= 0:
            continue
        seen_urls.add(url)
        candidates.append(candidate_from_source(source, title[:260], url, description))

    # Fallback: si la página entera contiene señales, creamos un único hallazgo.
    if not candidates:
        page_title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else source.name)
        page_text = clean_text(soup.get_text(" ", strip=True))
        score, signals, _types = detect_signals(page_text)
        if score > 0:
            snippets = make_snippets(page_text, signals, limit=6)
            candidates.append(
                candidate_from_source(
                    source,
                    f"{page_title} — posibles menciones coleccionistas",
                    source.url,
                    "\n".join(snippets)[:2200] if snippets else page_text[:1400],
                )
            )

    return candidates


def extract_rss(source: Source, feed_text: str, max_items: int) -> list[Candidate]:
    parsed = feedparser.parse(feed_text)
    candidates: list[Candidate] = []
    for entry in parsed.entries[:max_items]:
        title = clean_text(entry.get("title", ""))
        link = clean_text(entry.get("link", "")) or source.url
        summary = clean_text(entry.get("summary", "") or entry.get("description", "") or entry.get("content", ""))
        published_at = clean_text(entry.get("published", "") or entry.get("updated", "") or entry.get("created", ""))
        if not title and not summary:
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


def write_markdown_report(path: Path, reportable: list[Candidate], errors: list[str], min_score: int) -> None:
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


def run(args: argparse.Namespace) -> int:
    load_dotenv()

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

    print(f"[INFO] Fuentes totales en YAML: {len(sources_all)}")
    print(f"[INFO] Fuentes activas tras filtros: {len(sources)}")
    print(f"[INFO] Score mínimo: {args.min_score}")
    print(f"[INFO] Clases: {args.source_classes or 'todas'}")
    print(f"[INFO] Países: {args.countries or 'todos'}")
    print(f"[INFO] Respetar robots.txt: {args.respect_robots}")

    for index, source in enumerate(sources, start=1):
        print(f"[{index}/{len(sources)}] {source.name} :: {source.url}")
        try:
            if args.respect_robots and not robots.allowed(source.url):
                message = f"robots.txt no permite acceder a {source.url}"
                print(f"[SKIP] {message}")
                errors.append(f"{source.name}: {message}")
                continue

            text = fetch_text(session=session, url=source.url, timeout=(args.connect_timeout, args.read_timeout))
            if source.kind in {"rss", "feed", "atom"}:
                candidates = extract_rss(source, text, max_items=args.max_items_per_source)
            else:
                candidates = extract_generic_html(source, text, max_items=args.max_items_per_source)

            scored = [score_candidate(candidate) for candidate in candidates]
            all_candidates.extend(scored)
            print(f"    candidatos con señales: {len(scored)}")

        except requests.HTTPError as exc:
            message = f"{source.name}: HTTP error {exc}"
            print(f"[ERROR] {message}")
            errors.append(message)
        except requests.RequestException as exc:
            message = f"{source.name}: request error {exc}"
            print(f"[ERROR] {message}")
            errors.append(message)
        except Exception as exc:
            message = f"{source.name}: error inesperado {exc}"
            print(f"[ERROR] {message}")
            errors.append(message)

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
        write_markdown_report(path=report_path, reportable=reportable, errors=errors, min_score=args.min_score)

    print("")
    print("[RESUMEN]")
    print(f"  candidatos totales con señales: {len(all_candidates)}")
    print(f"  reportables: {len(reportable)}")
    print(f"  errores: {len(errors)}")
    print(f"  reporte: {report_path}")

    if args.send_telegram and not args.dry_run:
        try:
            send_telegram_message(make_telegram_message(reportable, report_path))
            print("[OK] Envié alerta por Telegram")
        except Exception as exc:
            print(f"[ERROR] No pude enviar Telegram: {exc}")
            return 2

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
    parser.add_argument("--dry-run", action="store_true", help="Ejecuta sin escribir estado, JSONL ni reportes")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
