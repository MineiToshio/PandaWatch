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
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urldefrag, quote_plus
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
    max_pages: int = 0  # 0 = usar default global (--max-pages); >0 = override


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
    price: str = ""
    image_url: str = ""
    release_date: str = ""
    product_type: str = ""
    author: str = ""
    stock_type: str = ""
    isbn: str = ""


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# Prefijos de "announcement" o etiqueta de editorial que se pegan al inicio.
TITLE_JUNK_PREFIXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^New\s+Product\s+Announcement\s*[:\-–—]\s*", re.IGNORECASE),
    # Panini genérico: "Panini: <cualquier categoría>_" → "<resto>"
    # Captura Fumetti_, Libri_, Manga_, Comics_, Productos de colección_, etc.
    re.compile(r"^Panini\s*:\s*[^_]{1,40}_\s*", re.IGNORECASE),
    re.compile(r"^Now\s+Shipping\s*[:\-]\s*", re.IGNORECASE),
    re.compile(r"^Coming\s+Soon\s*[:\-]\s*", re.IGNORECASE),
    re.compile(r"^Pre-?Order\s+Now\s*[:\-]\s*", re.IGNORECASE),
    re.compile(r"^Available\s+Now\s*[:\-]\s*", re.IGNORECASE),
    re.compile(r"^Just\s+Released\s*[:\-]\s*", re.IGNORECASE),
    # ES: estado "Próximamente / Próxima salida"
    re.compile(r"^Pr[óo]xima(?:mente)?\s+(?:salida\s+)?", re.IGNORECASE),
    # FR: estado "Nouveauté" / "À paraître" (con o sin acento, posiblemente con
    # mojibake si el encoding no se arregló antes).
    re.compile(r"^(?:Nouveaut[ée]s?|À\s+para[îi]tre)\s+", re.IGNORECASE),
    # FR: editorial pegada al inicio, con categoría opcional. P.ej.
    # "Glénat Manga ...", "Pika Seinen ...", "Pika Dreamland..." (sin categoría).
    # Solo se aplica al inicio, ningún manga real empieza por "Glénat"/"Pika".
    re.compile(
        r"^(?:Gl[ée]nat|Pika)\s+"
        r"(?:(?:Manga|Sh[ôo]nen|Sh[ôo]jo|Seinen|Josei|"
        r"[ÉE]dition\s+\S+|Art\s+Books?|Comics|Livres|Planning|"
        r"Nouveaut[ée]s?|Coll(?:ection)?|Aventure)\s+)?",
        re.IGNORECASE,
    ),
)

# Retailers cuyo "(X Exclusive)" en el sufijo es metadata redundante.
# Si el paréntesis menciona algo distinto (un artista, un evento), se mantiene.
_RETAILER_NAMES_ALT = (
    r"Dark\s+Horse\s+Direct",
    r"Kinokuniya",
    r"Barnes\s*(?:&|and)\s*Noble",
    r"B&N",
    r"Amazon",
    r"Walmart",
    r"Target",
    r"BAM",
    r"Books[-\s]?a[-\s]?Million",
    r"Crunchyroll",
    r"FYE",
    r"Forbidden\s+Planet",
    r"Right\s+Stuf",
    r"Hot\s+Topic",
)
_RETAILER_EXCLUSIVE_SUFFIX = re.compile(
    r"\s+\((?:" + "|".join(_RETAILER_NAMES_ALT) + r")\s+Exclusive\)\s*$",
    re.IGNORECASE,
)

# Patrones que indican "basura de e-commerce" pegada al título.
# Cada uno corta DESDE el match hasta el final del string.
TITLE_JUNK_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Shopify / e-commerce inglés
    re.compile(r"\s+Sale\s+price\s*:.*$", re.IGNORECASE),
    re.compile(r"\s+Regular\s+price\s*:.*$", re.IGNORECASE),
    re.compile(r"\s+Price\s*:.*$", re.IGNORECASE),
    re.compile(r"\s+(?:On\s+Sale|Sold\s+Out|In\s+Stock|Out\s+of\s+Stock|Coming\s+Soon|Pre-?Order)\s*$", re.IGNORECASE),
    re.compile(r"\s+from\s+\$\s*\d[\d.,]*.*$", re.IGNORECASE),
    # Sufijos "marketing" comunes
    re.compile(r"\s+Pre-?Order\s+Bonus\s*$", re.IGNORECASE),
    re.compile(r"\s+(?:NEW|NOVEDAD|NOUVEAU|NOVITÀ|新刊)\s*$", re.IGNORECASE),
    # Retailer exclusive en paréntesis (lista controlada)
    _RETAILER_EXCLUSIVE_SUFFIX,
    # E-commerce francés (Manga-Sanctuary y similares)
    re.compile(r"\s+Acheter\s+\d.*$", re.IGNORECASE),
    re.compile(r"\s+Ajouter\s+au\s+panier.*$", re.IGNORECASE),
    # E-commerce español
    re.compile(r"\s+Añadir\s+al\s+carrito.*$", re.IGNORECASE),
    re.compile(r"\s+Agregar\s+al\s+carrito.*$", re.IGNORECASE),
    re.compile(r"\s+Comprar\s+ahora.*$", re.IGNORECASE),
    re.compile(r"\s+Aggiungi\s+al\s+(?:carrello|confronto|lista).*$", re.IGNORECASE),
    re.compile(r"\s+Aggiungi\s+alla\s+lista.*$", re.IGNORECASE),
    re.compile(r"\s+Rimuovi\s+questo.*$", re.IGNORECASE),
    # E-commerce japonés
    re.compile(r"\s+カートに入れる.*$"),
    re.compile(r"\s+ほしい本に追加.*$"),
    re.compile(r"\s+詳細を見る.*$"),
    # Precio suelto al final ($X.XX, X,YY €, ¥XXX, etc.)
    re.compile(r"\s+(?:\$|US\$|USD)\s*\d[\d.,]*\s*$", re.IGNORECASE),
    re.compile(r"\s+\d{1,3}(?:[.,]\d{3})*[.,]\d{2}\s*€\s*$"),
    re.compile(r"\s+€\s*\d[\d.,]*\s*$"),
    re.compile(r"\s+¥\s*[\d,]+\s*$"),
    re.compile(r"\s+[\d,]+\s*円\s*$"),
    re.compile(r"\s+£\s*\d[\d.,]*\s*$"),
    # Trailing date dd/mm/yyyy o dd-mm-yyyy (típico Glénat/Pika, listings con
    # fecha de salida embedded en el título).
    re.compile(r"\s+\d{1,2}[/\-]\d{1,2}[/\-]20\d{2}\s*$"),
    # Cola descriptiva tipo Norma Editorial:
    # "Con sobrecubierta Incluye desplegable y páginas a color Formato A5 400
    # págs. aprox. En comiquerías y cadena de librerías MÁS INFO"
    # Estrategia: cortar DESDE la primera bandera descriptiva hasta el final.
    re.compile(
        r"\s+(?:Con\s+sobrecubierta|Incluye\s+(?:desplegable|p[áa]ginas)|"
        r"Formato\s+[AB]\d|En\s+comiquer[íi]as\s+y\s+cadena)\b.*$",
        re.IGNORECASE,
    ),
    # Sufijo "MÁS INFO" suelto (cuando el resto ya se limpió).
    re.compile(r"\s+M[ÁA]S\s+INFO\s*$", re.IGNORECASE),
    # "Pre-Order" suelto al final (sin "Bonus" ni "Now").
    re.compile(r"\s+Pre-?Order\s*$", re.IGNORECASE),
    # ".aprox" / "págs aprox" lone.
    re.compile(r"\s+\d+\s*p[áa]gs?\.?\s*(?:aprox\.?)?\s*$", re.IGNORECASE),
)


# Heurística: si el título contiene secuencias típicas de mojibake
# (UTF-8 decoded as Latin-1 o cp1252), se intenta reparar via round-trip.
_MOJIBAKE_HINT = re.compile(
    # 'Ã' seguido de un caracter ASCII alto (típico de UTF-8 leído como Latin-1):
    # incluye letras acentuadas (Ã©, Ã¨, Ã¡, Ã®, Ã´, Ã§, Ã±...) y también 'Ã '
    # (= "à " en UTF-8, preposición FR frecuente en títulos como "Tomes 91 à 104").
    r"Ã[\x80-\xbf\xa0©¨ª«¬®°±²³´µ¶·¸¹º»¼½¾¿ ]"
    r"|â€[™œžŸ\x9d\x99\x98]"
    r"|Â[\xa0-\xbf]"
)


# Fallback cuando el round-trip estricto falla por bytes inválidos en
# medio del título (típico: "Ã " donde "Ã" es mojibake de "à" y el espacio
# rompe la decodificación UTF-8). Cubre los pares más frecuentes.
_MOJIBAKE_PAIRS: tuple[tuple[str, str], ...] = (
    # Latin minúsculas: 'Ã' + byte high → letra acentuada
    ("Ã©", "é"), ("Ã¨", "è"), ("Ãª", "ê"), ("Ã ", "à "),
    ("Ã¢", "â"), ("Ã®", "î"), ("Ã´", "ô"), ("Ã»", "û"),
    ("Ã§", "ç"), ("Ã±", "ñ"), ("Ã¡", "á"), ("Ã³", "ó"),
    ("Ãº", "ú"), ("Ã­", "í"), ("Ã¼", "ü"), ("Ã¶", "ö"),
    # Latin mayúsculas
    ("Ã„", "Ä"), ("Ã‰", "É"), ("Ãˆ", "È"), ("Ã€", "À"),
    ("Ã‚", "Â"), ("Ã‡", "Ç"), ("Ã™", "Ù"), ("Ãš", "Ú"),
    ("Ã”", "Ô"), ("ÃŠ", "Ê"), ("Ã“", "Ó"),
    ("Ã", "Ñ"),  # Ã + U+0091 → Ñ (U+00D1)
    # Comillas / guiones tipográficos (UTF-8 leído como cp1252)
    ("â€™", "'"),   # â€™ → '
    ("â€œ", "\""),  # â€œ → "
    ("â€", "\""),  # â€\x9d → "
    ("â€“", "–"),    # â€" → –
    ("â€”", "—"),    # â€" → —
    # Â + algo (sobrante de codificación)
    ("Â°", "°"), ("Â·", "·"), ("Â¡", "¡"), ("Â¿", "¿"),
)


def _fix_mojibake(text: str) -> str:
    """Repara texto con encoding UTF-8 decodificado como Latin-1/cp1252.

    Estrategia en cascada:
      1) Si NO hay hint de mojibake, devuelve el texto tal cual.
      2) Intenta round-trip (cp1252|latin-1 → utf-8), itera hasta 3 veces
         para cubrir doble-mojibake.
      3) Si el round-trip estricto falla por bytes inválidos (caso típico:
         'Ã ' en medio del título), aplica un mapeo directo de pares
         comunes (_MOJIBAKE_PAIRS) y vuelve a iterar.
    """
    if not text:
        return text
    current = text
    for _ in range(3):
        if not _MOJIBAKE_HINT.search(current):
            return current
        next_state: str | None = None
        for src_enc in ("cp1252", "latin-1"):
            try:
                candidate = current.encode(src_enc, errors="strict").decode(
                    "utf-8", errors="strict"
                )
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if "�" in candidate:
                continue
            next_state = candidate
            break
        if next_state is None:
            # Fallback: sustitución de pares conocidos para arreglar lo que
            # se pueda. Si no cambia nada, abortamos para no entrar en bucle.
            replaced = current
            for bad, good in _MOJIBAKE_PAIRS:
                if bad in replaced:
                    replaced = replaced.replace(bad, good)
            if replaced == current:
                return current
            current = replaced
            continue
        if next_state == current:
            return current
        current = next_state
    return current


def clean_title(title: str) -> str:
    """Strippea basura de e-commerce y prefijos de announcement del título.

    Aplica en orden:
      0) Repara mojibake (FR Glénat/Pika a veces vienen mal codificados).
      1) Quita prefijos tipo 'New Product Announcement -', 'Panini: Fumetti_',
         'Nouveauté Glénat Manga', 'Próximamente', etc.
      2) Quita sufijos (precios, 'On Sale', '(Dark Horse Direct Exclusive)',
         fechas trailing, colas descriptivas tipo Norma).
    Iterando hasta estabilizar para que patrones cascading se resuelvan.
    """
    if not title:
        return title
    cleaned = _fix_mojibake(title)
    for _ in range(5):
        prev = cleaned
        # Prefijos
        for pattern in TITLE_JUNK_PREFIXES:
            cleaned = pattern.sub("", cleaned).strip()
        # Sufijos
        for pattern in TITLE_JUNK_PATTERNS:
            cleaned = pattern.sub("", cleaned).strip()
        if cleaned == prev:
            break
    return cleaned


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


# Query params que NO identifican al producto, solo tracking / posición.
TRACKING_PARAMS: frozenset[str] = frozenset({
    # Shopify (Dark Horse Direct, Milky Way, Kinokuniya, etc.)
    "_pos", "_sid", "_ss", "_psq", "_v",
    # UTM / ads
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "msclkid", "yclid", "dclid", "ttclid",
    # Mailchimp / newsletters
    "mc_cid", "mc_eid",
    # Genérico
    "ref", "source", "affiliate", "aff", "tag",
    # Magento / Panini
    "___store", "___from_store",
})


def normalize_url_for_dedup(url: str) -> str:
    """Normaliza URL para deduplicación.

    Strippea params de tracking (no identifican producto), normaliza
    case en host, y para Shopify colapsa /collections/X/products/Y → /products/Y
    (ambas URLs apuntan al mismo producto).

    Devuelve la URL normalizada o el input si no se puede parsear.
    """
    if not url:
        return url
    try:
        from urllib.parse import parse_qsl, urlencode, urlunparse
        parsed = urlparse(url)
    except Exception:
        return url

    # 1. Params: drop los de tracking, mantener el resto (ordenados para estabilidad).
    if parsed.query:
        params = parse_qsl(parsed.query, keep_blank_values=False)
        clean_params = sorted((k, v) for k, v in params if k not in TRACKING_PARAMS)
        new_query = urlencode(clean_params)
    else:
        new_query = ""

    # 2. Shopify: /collections/<col>/products/<handle> → /products/<handle>
    path = parsed.path
    m = re.match(r"^/collections/[^/]+/(products/.+)$", path)
    if m:
        path = "/" + m.group(1)

    # 3. Trailing slash: quitar excepto si el path es solo "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # 4. Host minúsculas.
    netloc = parsed.netloc.lower()

    return urlunparse(
        (parsed.scheme.lower(), netloc, path, parsed.params, new_query, "")
    )


FUZZY_STOPWORDS: frozenset[str] = frozenset({
    # Genéricas en varios idiomas — solas no aportan señal coleccionista.
    "edicion", "edition", "edizione",
    "de", "la", "el", "le", "les", "las", "los", "en", "con", "y", "e",
    "a", "and", "the", "of", "with", "et", "du", "di", "da", "del",
    "pack", "libro", "livre", "book", "version", "vol", "tome", "tomo",
    "pre", "order", "preorder", "preordine",
    "manga", "comic", "comics",
    # Palabras de envoltorio: la señal real está en otra palabra de la frase.
    "formato", "portada", "official", "coleccion", "collection",
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
    # Cap a 300 (antes 100). Da más resolución para ordenar items con muchas señales.
    # Items "edición limitada + hardcover + variant + exclusivo" pueden llegar a 200+.
    score = min(score, 300)
    return score, matched_phrases, matched_types


# ---------------------------------------------------------------------------
# Extracción de metadata adicional (precio, imagen, fecha, tipo de producto)
# ---------------------------------------------------------------------------

PRICE_PATTERNS = [
    # (regex, prefix/suffix template using $1 for amount)
    (re.compile(r"(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*€"), "€ {}"),
    (re.compile(r"€\s*(\d{1,3}(?:[.,]\d{3})*[.,]?\d{0,2})"), "€ {}"),
    (re.compile(r"USD\s*(\d{1,3}(?:[.,]\d{3})*[.,]?\d{0,2})", re.IGNORECASE), "USD {}"),
    (re.compile(r"\$\s*(\d{1,3}(?:[.,]\d{3})*[.,]?\d{0,2})"), "$ {}"),
    (re.compile(r"¥\s*(\d{1,3}(?:,\d{3})*)"), "¥ {}"),
    (re.compile(r"(\d{1,3}(?:,\d{3})*)\s*円"), "¥ {}"),
    (re.compile(r"(\d{1,3}(?:,\d{3})*)\s*yen", re.IGNORECASE), "¥ {}"),
    (re.compile(r"MXN\s*\$?\s*(\d{1,3}(?:[.,]\d{3})*[.,]?\d{0,2})", re.IGNORECASE), "MXN {}"),
    (re.compile(r"GBP\s*(\d{1,3}(?:[.,]\d{3})*[.,]?\d{0,2})", re.IGNORECASE), "£ {}"),
    (re.compile(r"£\s*(\d{1,3}(?:[.,]\d{3})*[.,]?\d{0,2})"), "£ {}"),
]


def extract_price(text: str) -> str:
    """Extrae primer precio detectado en el texto. Devuelve "" si no encuentra."""
    if not text:
        return ""
    for pattern, fmt in PRICE_PATTERNS:
        match = pattern.search(text)
        if match:
            return fmt.format(match.group(1).strip())
    return ""


# Patrones de fecha de lanzamiento en varios idiomas.
RELEASE_DATE_PATTERNS = [
    # ISO 8601
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
    # dd/mm/yyyy o dd-mm-yyyy
    re.compile(r"\b(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4})\b"),
    # Japonés: 2026年6月15日
    re.compile(r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)"),
    # Mes en inglés: June 15, 2026 / Jun 15 2026
    re.compile(
        r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b",
        re.IGNORECASE,
    ),
    # Mes en español/francés/italiano: 15 de junio de 2026 / 15 juin 2026 / 15 giugno 2026
    re.compile(
        r"\b(\d{1,2}\s+(?:de\s+)?(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre|"
        r"janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre|"
        r"gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)"
        r"(?:\s+de)?\s+\d{4})\b",
        re.IGNORECASE,
    ),
]

# Palabras-clave que sugieren que el contexto cercano contiene fecha de lanzamiento.
RELEASE_HINT_WORDS = re.compile(
    r"(disponible|disponibile|sortie|release|releases?\s+date|salida|sale\s+date|pub(?:lic|blic)at|"
    r"発売|発売日|preventa|pre-?order|onsale|on\s+sale|en\s+venta)",
    re.IGNORECASE,
)


def extract_release_date(text: str) -> str:
    """Best-effort extracción de fecha de lanzamiento. Devuelve "" si no encuentra."""
    if not text:
        return ""
    # Si hay palabras-clave de fecha de venta, buscar fecha cerca; si no, primera fecha encontrada.
    hint = RELEASE_HINT_WORDS.search(text)
    haystack = text
    if hint:
        start = max(0, hint.start() - 20)
        end = min(len(text), hint.end() + 80)
        haystack = text[start:end]
    for pattern in RELEASE_DATE_PATTERNS:
        match = pattern.search(haystack)
        if match:
            return match.group(1).strip()
    # Si no encontramos cerca del hint, intentar buscar en todo el texto.
    if hint:
        for pattern in RELEASE_DATE_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1).strip()
    return ""


IMAGE_URL_BAD_PATTERNS = (
    "/icon/", "/icons/", "/ui/", "/svg/", "favicon",
    "/logo", "spacer.gif", "pixel.gif", "blank.gif",
    "1x1.png", "/sprite", "loader.gif", "loading.gif",
    "/sys/", "/category/", "/badges/", "/badge/", "/banner/",
    "/promo/", "/btn", "/button", "/arrow", "/separator",
    "/star", "/rating", "/cart",
)

IMAGE_URL_GOOD_PATTERNS = (
    "/goods/", "/products/", "/product/", "/cover", "/jacket",
    "/manga/", "/manga_", "/book", "/item",
)


def _img_to_url(img: Any, source_url: str) -> str:
    """Extrae URL absoluta de un <img> probando src/data-src/srcset/etc."""
    for attr in ("src", "data-src", "data-original", "data-lazy-src", "srcset", "data-srcset"):
        val = img.get(attr)
        if not val:
            continue
        if "srcset" in attr:
            val = val.split(",")[0].strip().split(" ")[0]
        url = canonicalize_url(source_url, val.strip())
        if url and url != source_url:
            return url
    return ""


def _score_image(url: str, alt: str) -> int:
    """Score más alto = más probable que sea cover/portada de producto.

    Negativo para íconos, badges, logos. Positivo para paths de producto
    y alt text largo (suele ser título del producto).
    """
    lower = url.lower()
    if any(p in lower for p in IMAGE_URL_BAD_PATTERNS):
        return -100
    score = 0
    if any(p in lower for p in IMAGE_URL_GOOD_PATTERNS):
        score += 10
    if alt and len(alt) >= 10:
        score += 5
    elif alt and len(alt) >= 3:
        score += 1
    # Imágenes con números largos en el path suelen ser IDs de producto.
    if re.search(r"/\d{6,}", lower):
        score += 3
    return score


def extract_image_url(card: Any, source_url: str) -> str:
    """Extrae URL de la imagen más probable del card o de su contenedor.

    Algunos sites (KADOKAWA, grid CSS) ponen la imagen como sibling del card
    de texto, no dentro. Por eso buscamos en card primero y después en padres
    inmediatos (hasta 2 niveles).

    Rankea las imágenes encontradas: prefiere paths tipo /goods/, /products/,
    alts con título largo, IDs numéricos. Penaliza íconos, badges, logos.

    Si un contenedor tiene >8 imágenes, lo asumimos wrapper global y lo
    skipeamos (evita capturar header/footer/sidebar).
    """
    if card is None:
        return ""

    containers: list[Any] = [card]
    parent = card.parent
    for _ in range(2):
        if parent is None or parent.name in ("body", "html"):
            break
        containers.append(parent)
        parent = parent.parent

    best_url = ""
    best_score = -1
    for container in containers:
        try:
            imgs = container.find_all("img", limit=15)
        except Exception:
            continue
        if len(imgs) > 8:
            continue
        for img in imgs:
            url = _img_to_url(img, source_url)
            if not url:
                continue
            alt = (img.get("alt") or "").strip()
            score = _score_image(url, alt)
            if score > best_score:
                best_score = score
                best_url = url
        # Si ya encontramos una imagen con score positivo, no subimos más niveles.
        if best_score >= 5:
            return best_url

    return best_url if best_score >= 0 else ""


PRODUCT_TYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("artbook", [
        "artbook", "art book", "art-book",
        "libro de arte", "libro de ilustraciones", "libro d'illustrazione",
        "livre d'illustration", "beau livre",
        "画集", "イラスト集", "ビジュアルブック", "設定資料集", "visual book", "visual fanbook",
        "illustration book", "super illustration book",
    ]),
    ("fanbook", ["fanbook", "ファンブック"]),
    ("guidebook", ["guidebook", "guía oficial", "guia oficial", "official guidebook"]),
    ("boxset", [
        "box set", "boxset", "box-set", "slipcase",
        "cofre", "cofanetto", "coffret",
    ]),
    ("novel", ["light novel", "novel", "novela", "ranobe", "ライトノベル"]),
]


AUTHOR_PREFIX_PATTERN = re.compile(
    r"(?:autor[ae]?s?|author|auteur|autore|著者|作者|原作|作画)"
    r"\s*[:：]\s*"
    r"([^.,;\n|\\/()\[\]<>0-9]{2,80}?)"
    r"(?=\s*(?:[.,;\n|·\\/]|\s-\s|$))",
    re.IGNORECASE | re.UNICODE,
)

AUTHOR_BY_PATTERN = re.compile(
    r"(?:^|\s)(?:by|par|di|du)\s+"
    r"([^.,;\n|\\/()\[\]<>0-9]{2,80}?)"
    r"(?=\s*(?:[.,;\n|·\\/]|\s-\s|$))",
    re.IGNORECASE | re.UNICODE,
)

AUTHOR_FIRST_WORD_BLACKLIST = frozenset({
    "la", "el", "los", "las", "the", "this", "that", "le", "les",
    "una", "uno", "il", "lo", "manga", "edicion", "edition", "edizione",
    "tomo", "libro", "book", "vol", "volume", "editorial", "publisher",
    "sin", "without", "no", "not", "with", "con", "y", "and", "or",
})


def _validate_author_candidate(raw: str) -> str:
    cleaned = clean_text(raw)
    if not cleaned or len(cleaned) < 3 or len(cleaned) > 80:
        return ""
    first_word = cleaned.split()[0]
    if first_word.lower() in AUTHOR_FIRST_WORD_BLACKLIST:
        return ""
    first_char = first_word[0]
    # Aceptar: mayúscula latina, o carácter CJK (Hiragana/Katakana/Han).
    is_uppercase_latin = first_char.isupper() and first_char.isalpha()
    is_cjk = "぀" <= first_char <= "鿿"
    if not (is_uppercase_latin or is_cjk):
        return ""
    return cleaned


AUTHOR_LINK_HREF_PATTERN = re.compile(
    r"/(?:autor|auteur|author|mangaka|kreator|verfasser|autore)/",
    re.IGNORECASE,
)

JSON_LD_AUTHOR_FIELDS = ("author", "creator", "illustrator", "writer")


def _extract_json_ld_author(soup: BeautifulSoup) -> str:
    """Busca autor en bloques JSON-LD (Schema.org)."""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            for field in JSON_LD_AUTHOR_FIELDS:
                value = item.get(field)
                if isinstance(value, str) and value.strip():
                    return value.strip()
                if isinstance(value, dict):
                    name = (value.get("name") or "").strip()
                    if name:
                        return name
                if isinstance(value, list):
                    for entry in value:
                        if isinstance(entry, str) and entry.strip():
                            return entry.strip()
                        if isinstance(entry, dict):
                            name = (entry.get("name") or "").strip()
                            if name:
                                return name
    return ""


def _extract_author_from_links(soup: BeautifulSoup) -> str:
    """Detect author from <a href="/autor/..."> / /auteur/ / /author/ patterns."""
    for link in soup.find_all("a", href=AUTHOR_LINK_HREF_PATTERN):
        text = clean_text(link.get_text(" ", strip=True))
        if not text or len(text) < 3 or len(text) > 80:
            continue
        lower = text.lower()
        if any(skip in lower for skip in ("todos", "all authors", "voir tous", "see all")):
            continue
        first_char = text[0]
        if first_char.isupper() or "぀" <= first_char <= "鿿":
            return text
    return ""


ISBN13_PATTERN = re.compile(
    r"(?:ISBN(?:-13)?[\s:\-]*)?(97[89])[\s\-]?(\d{1,5})[\s\-]?(\d{1,7})[\s\-]?(\d{1,7})[\s\-]?(\d)",
    re.IGNORECASE,
)
ISBN10_PATTERN = re.compile(
    r"(?:ISBN(?:-10)?[\s:\-]*)?(\d{1,5})[\s\-]?(\d{1,7})[\s\-]?(\d{1,7})[\s\-]?([\dXx])(?!\d)",
    re.IGNORECASE,
)


def _isbn13_check(digits: str) -> bool:
    """Valida ISBN-13 con dígito de control."""
    if len(digits) != 13 or not digits.isdigit():
        return False
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits[:12]))
    return (10 - total % 10) % 10 == int(digits[12])


def extract_isbn(text: str, soup: Any = None) -> str:
    """Extrae ISBN-13 (preferido) o ISBN-10 del texto y/o del HTML."""
    # 1. Selectores HTML estructurados.
    if soup is not None:
        for attrs in (
            {"itemprop": "isbn"},
            {"itemprop": "productID"},
            {"name": "isbn"},
            {"property": "book:isbn"},
        ):
            try:
                meta = soup.find("meta", attrs=attrs)
            except Exception:
                meta = None
            if meta and meta.get("content"):
                cleaned = re.sub(r"[\s\-]", "", meta["content"])
                # productID puede venir "isbn:9781234567897"
                if ":" in cleaned:
                    cleaned = cleaned.split(":")[-1]
                if len(cleaned) == 13 and cleaned.isdigit() and _isbn13_check(cleaned):
                    return cleaned
                if len(cleaned) == 10:
                    return cleaned

        # JSON-LD: buscar isbn / productID
        try:
            scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
        except Exception:
            scripts = []
        for script in scripts:
            raw = script.string or script.get_text() or ""
            if not raw.strip():
                continue
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                for key in ("isbn", "ISBN", "productID", "gtin13", "gtin"):
                    val = item.get(key)
                    if isinstance(val, str):
                        cleaned = re.sub(r"[^0-9Xx]", "", val)
                        if len(cleaned) == 13 and cleaned.isdigit() and _isbn13_check(cleaned):
                            return cleaned
                        if len(cleaned) == 10:
                            return cleaned

    # 2. Regex en texto plano + URL.
    if text:
        for match in ISBN13_PATTERN.finditer(text):
            digits = "".join(match.groups())
            if _isbn13_check(digits):
                return digits

    return ""


SCHEMA_ORG_CURRENCY_SYMBOLS = {
    "EUR": "€", "USD": "$", "JPY": "¥", "GBP": "£",
    "MXN": "MXN", "ARS": "$", "CAD": "$", "AUD": "$",
}


def _format_schema_price(price: str, currency: str) -> str:
    if not price:
        return ""
    cur = (currency or "").upper().strip()
    sym = SCHEMA_ORG_CURRENCY_SYMBOLS.get(cur, cur)
    return f"{sym} {price}".strip()


def _schema_iter_items(data: Any) -> list[dict]:
    """Aplana JSON-LD: dict, lista, o @graph → lista de dicts."""
    items: list[dict] = []
    candidates = data if isinstance(data, list) else [data]
    for c in candidates:
        if not isinstance(c, dict):
            continue
        graph = c.get("@graph")
        if isinstance(graph, list):
            items.extend(g for g in graph if isinstance(g, dict))
        else:
            items.append(c)
    return items


def _schema_item_is_product(item: dict) -> bool:
    """¿El item JSON-LD es Product/Book/Comic?"""
    t = item.get("@type", "")
    if isinstance(t, list):
        t = " ".join(str(x) for x in t)
    t = str(t)
    return any(k in t for k in ("Product", "Book", "Comic", "Manga", "GraphicNovel"))


def extract_schema_org_product(soup_or_card: Any, source_url: str) -> dict[str, str]:
    """Extrae metadata de un Product/Book Schema.org en JSON-LD.

    Acepta tanto un BeautifulSoup completo como un Tag (card individual). Si la
    card contiene un <script type='application/ld+json'> con Product, devuelve
    todos los campos disponibles. Si no, devuelve dict vacío.

    Devuelve dict con: name, image_url, description, author, isbn, price,
    release_date, publisher, product_type (manga/artbook/boxset/...).
    """
    result = {
        "name": "",
        "image_url": "",
        "description": "",
        "author": "",
        "isbn": "",
        "price": "",
        "release_date": "",
        "publisher": "",
        "product_type": "",
    }
    if soup_or_card is None:
        return result

    try:
        scripts = soup_or_card.find_all("script", attrs={"type": "application/ld+json"})
    except Exception:
        return result

    for script in scripts:
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        for item in _schema_iter_items(data):
            if not _schema_item_is_product(item):
                continue

            # name
            if not result["name"] and item.get("name"):
                result["name"] = clean_text(str(item["name"]))

            # image
            if not result["image_url"]:
                img = item.get("image")
                url = ""
                if isinstance(img, str):
                    url = img.strip()
                elif isinstance(img, dict):
                    url = (img.get("url") or img.get("@id") or "").strip()
                elif isinstance(img, list) and img:
                    first = img[0]
                    if isinstance(first, str):
                        url = first.strip()
                    elif isinstance(first, dict):
                        url = (first.get("url") or first.get("@id") or "").strip()
                if url:
                    canonical = canonicalize_url(source_url, url)
                    if canonical and _score_image(canonical, "") >= -10:
                        result["image_url"] = canonical

            # description
            if not result["description"] and item.get("description"):
                result["description"] = clean_text(str(item["description"]))[:2000]

            # author / creator
            if not result["author"]:
                auth = item.get("author") or item.get("creator")
                value = ""
                if isinstance(auth, str):
                    value = auth.strip()
                elif isinstance(auth, dict):
                    value = (auth.get("name") or "").strip()
                elif isinstance(auth, list) and auth:
                    first = auth[0]
                    if isinstance(first, str):
                        value = first.strip()
                    elif isinstance(first, dict):
                        value = (first.get("name") or "").strip()
                if value:
                    result["author"] = clean_text(value)

            # publisher / brand
            if not result["publisher"]:
                pub = item.get("publisher") or item.get("brand")
                value = ""
                if isinstance(pub, str):
                    value = pub.strip()
                elif isinstance(pub, dict):
                    value = (pub.get("name") or "").strip()
                if value:
                    result["publisher"] = clean_text(value)

            # isbn (con validación de checksum)
            if not result["isbn"]:
                for key in ("isbn", "ISBN", "productID", "gtin13", "gtin"):
                    val = item.get(key)
                    if isinstance(val, str):
                        cleaned = re.sub(r"[^0-9Xx]", "", val)
                        if len(cleaned) == 13 and cleaned.isdigit() and _isbn13_check(cleaned):
                            result["isbn"] = cleaned
                            break
                        if len(cleaned) == 10:
                            result["isbn"] = cleaned
                            break

            # price (offers.price o offers.lowPrice)
            if not result["price"]:
                offers = item.get("offers")
                offer_list: list[dict] = []
                if isinstance(offers, dict):
                    offer_list = [offers]
                elif isinstance(offers, list):
                    offer_list = [o for o in offers if isinstance(o, dict)]
                for off in offer_list:
                    p = off.get("price") or off.get("lowPrice")
                    if p is None:
                        continue
                    currency = off.get("priceCurrency", "")
                    result["price"] = _format_schema_price(str(p), str(currency))
                    if result["price"]:
                        break

            # release_date / datePublished
            if not result["release_date"]:
                date_val = (
                    item.get("datePublished")
                    or item.get("releaseDate")
                    or item.get("dateCreated")
                    or item.get("dateModified")
                )
                if date_val:
                    result["release_date"] = str(date_val).strip()[:30]

            # product_type desde @type o bookFormat
            if not result["product_type"]:
                t = item.get("@type", "")
                if isinstance(t, list):
                    t = " ".join(str(x) for x in t)
                t = str(t).lower()
                book_format = str(item.get("bookFormat", "")).lower()
                if "graphicnovel" in t or "comic" in t or "manga" in t:
                    result["product_type"] = "manga"
                elif "audiobook" in book_format:
                    result["product_type"] = "audiobook"
                elif "hardcover" in book_format:
                    result["product_type"] = "manga"  # tapa dura, sigue siendo manga

    return result


def _extract_image_from_detail_soup(soup: BeautifulSoup, source_url: str) -> str:
    """Extrae URL de portada de una página de detalle, varias estrategias.

    1) JSON-LD schema.org `image` field
    2) OpenGraph `og:image` / Twitter `twitter:image`
    3) meta itemprop="image"
    4) <img> con clases típicas de portada (cover, product-image, etc.)
    5) Ranking general de <img> tags del body (mismo scoring que el listing).
    """
    # 1) JSON-LD
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            value = item.get("image")
            if isinstance(value, str) and value.strip():
                url = canonicalize_url(source_url, value.strip())
                if url:
                    return url
            if isinstance(value, dict):
                v = (value.get("url") or value.get("@id") or "").strip()
                if v:
                    url = canonicalize_url(source_url, v)
                    if url:
                        return url
            if isinstance(value, list) and value:
                for v in value:
                    if isinstance(v, str) and v.strip():
                        url = canonicalize_url(source_url, v.strip())
                        if url:
                            return url
                    if isinstance(v, dict):
                        s = (v.get("url") or v.get("@id") or "").strip()
                        if s:
                            url = canonicalize_url(source_url, s)
                            if url:
                                return url

    # 2) OpenGraph / Twitter
    for attrs in (
        {"property": "og:image"},
        {"property": "og:image:url"},
        {"name": "twitter:image"},
        {"name": "twitter:image:src"},
    ):
        meta = soup.find("meta", attrs=attrs)
        if meta and meta.get("content"):
            url = canonicalize_url(source_url, meta["content"].strip())
            if url:
                return url

    # 3) meta itemprop="image"
    meta = soup.find("meta", attrs={"itemprop": "image"})
    if meta and meta.get("content"):
        url = canonicalize_url(source_url, meta["content"].strip())
        if url:
            return url

    # 4) <img> con clases típicas de portada (Schema.org / E-commerce)
    for selector in (
        "img[itemprop='image']",
        "img.cover",
        "img.product-image",
        "img.product-image-photo",
        "[class*='product-image'] img",
        "[class*='cover'] img",
        "[class*='jacket'] img",
        "[class*='detail'] img",
        "[id*='product'] img",
        "main img",
        "article img",
    ):
        try:
            node = soup.select_one(selector)
        except Exception:
            continue
        if node and node.name == "img":
            url = _img_to_url(node, source_url)
            if url and _score_image(url, (node.get("alt") or "").strip()) >= 0:
                return url

    # 5) Fallback: rankear todos los <img> del body.
    body = soup.body or soup
    best_url = ""
    best_score = -1
    for img in body.find_all("img", limit=30):
        url = _img_to_url(img, source_url)
        if not url:
            continue
        score = _score_image(url, (img.get("alt") or "").strip())
        if score > best_score:
            best_score = score
            best_url = url
    return best_url if best_score >= 5 else ""


# Etiquetas conocidas (multilingüe) que aparecen en páginas de detalle como
# pares clave-valor: <li><span>LABEL</span>VALUE</li>, <dt>L</dt><dd>V</dd>,
# <tr><th>L</th><td>V</td></tr>, <div class='label'>L</div><div>V</div>...
_FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "author": (
        "dessinateur", "scénariste", "scenariste", "auteur", "auteurs",
        "autor", "autores", "author", "authors", "autore", "autori",
        "mangaka", "writer", "creator",
        "著者", "作者", "原作", "漫画",
    ),
    "publisher": (
        "editeur", "éditeur", "editeurs", "éditeurs",
        "editor", "editorial", "publisher", "editore",
        "出版社", "発行",
    ),
    "release_date": (
        "date parution", "date de parution", "date de sortie",
        "fecha publicación", "fecha publicacion", "fecha de salida",
        "release date", "release", "publication date",
        "data uscita", "data di pubblicazione", "data di uscita",
        "発売日", "刊行日", "publication",
    ),
    "price": (
        "prix", "precio", "price", "prezzo",
        "価格", "本体価格", "税込価格", "定価",
    ),
    "isbn": (
        "ean-13", "ean", "isbn", "isbn-13", "isbn-10",
    ),
}

# Mapa inverso: label_lower -> field_name (pre-computado para lookup rápido)
_LABEL_TO_FIELD: dict[str, str] = {
    label.lower(): field
    for field, labels in _FIELD_LABELS.items()
    for label in labels
}


def _extract_label_value_pairs(soup) -> dict[str, str]:
    """Extrae pares (label → value) de páginas de detalle con estructuras tipo
    'ficha técnica'. Soporta:

      - <li><span>LABEL</span>VALUE</li>     (Manga-Sanctuary, Pika, Glénat)
      - <dt>LABEL</dt><dd>VALUE</dd>          (sitios con definition lists)
      - <tr><th>LABEL</th><td>VALUE</td></tr> (tablas de specs)
      - <tr><td>LABEL</td><td>VALUE</td></tr> (tablas sin th)

    Devuelve dict con claves normalizadas (author, publisher, release_date,
    price, isbn) si encuentra un label conocido. Solo el PRIMER valor por
    campo se conserva.
    """
    found: dict[str, str] = {}

    def _try_register(label: str, value: str) -> None:
        if not label or not value:
            return
        # Normaliza la etiqueta: minúsculas, sin ':', sin signos extra.
        norm = label.strip().rstrip(":").rstrip(" :").strip().lower()
        # Quita parens al final: "Auteur(s)" → "auteur"
        norm = re.sub(r"\(s\)$", "", norm).strip()
        field = _LABEL_TO_FIELD.get(norm)
        if not field or field in found:
            return
        cleaned = clean_text(value)
        if not cleaned or len(cleaned) > 200:
            return
        found[field] = cleaned

    # 1) <li><span>LABEL</span>VALUE</li>
    for li in soup.find_all("li"):
        span = li.find("span")
        if not span:
            continue
        label = span.get_text(" ", strip=True)
        if not label or len(label) > 30:
            continue
        full_text = li.get_text(" ", strip=True)
        if not full_text.startswith(label):
            continue
        value = full_text[len(label):].strip(" :\xa0")
        _try_register(label, value)

    # 2) <dt>LABEL</dt><dd>VALUE</dd>
    for dt in soup.find_all("dt"):
        label = dt.get_text(" ", strip=True)
        dd = dt.find_next_sibling("dd")
        if dd and label:
            _try_register(label, dd.get_text(" ", strip=True))

    # 3) <tr><th>LABEL</th><td>VALUE</td></tr> o <tr><td>LABEL</td><td>VALUE</td></tr>
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if len(cells) >= 2:
            label = cells[0].get_text(" ", strip=True)
            value = cells[1].get_text(" ", strip=True)
            _try_register(label, value)

    return found


def fetch_metadata_from_detail(
    url: str,
    session: requests.Session,
    timeout: tuple[int, int],
) -> dict[str, str]:
    """Fetch HTTP a la URL del producto y extrae todos los metadatos posibles.

    Devuelve dict con author / image_url / isbn / name / price / release_date /
    publisher / description (campos vacíos si no se encuentra). Hace 1 HTTP
    request opt-in (--fetch-details).
    """
    result = {
        "author": "", "image_url": "", "isbn": "",
        "name": "", "price": "", "release_date": "",
        "publisher": "", "description": "",
    }
    if not url:
        return result
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        if not response.encoding:
            response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, "html.parser")
    except (requests.RequestException, Exception):
        return result

    # === Schema.org/JSON-LD primero (es la fuente más confiable) ===
    schema = extract_schema_org_product(soup, url)
    for key in ("name", "price", "release_date", "publisher", "description"):
        if schema.get(key):
            result[key] = schema[key]
    if schema.get("image_url"):
        result["image_url"] = schema["image_url"]
    if schema.get("isbn"):
        result["isbn"] = schema["isbn"]
    if schema.get("author"):
        result["author"] = schema["author"]

    # === Extractor genérico de pares LABEL/VALUE (ficha técnica) ===
    # Cubre Manga-Sanctuary, Pika, Glénat y muchos otros sitios que estructuran
    # los metadatos del producto como una lista de pares.
    label_pairs = _extract_label_value_pairs(soup)
    for field in ("author", "publisher", "release_date", "price", "isbn"):
        if not result.get(field) and label_pairs.get(field):
            result[field] = label_pairs[field]

    # === Author (si Schema.org no lo trajo) ===
    if not result["author"]:
        author = _extract_json_ld_author(soup)
        if not author:
            for attrs in (
                {"name": "author"},
                {"property": "book:author"},
                {"property": "og:book:author"},
                {"name": "twitter:creator"},
            ):
                meta = soup.find("meta", attrs=attrs)
                if meta and meta.get("content"):
                    value = clean_text(meta["content"])
                    if value:
                        author = value
                        break
        if not author:
            author = _extract_author_from_links(soup)
        if not author:
            body_text = clean_text(soup.body.get_text(" ", strip=True) if soup.body else "")
            author = extract_author(body_text[:3000], soup)
        result["author"] = author

    # === Image (si Schema.org no lo trajo) ===
    if not result["image_url"]:
        result["image_url"] = _extract_image_from_detail_soup(soup, url)

    # === ISBN (si Schema.org no lo trajo) ===
    if not result["isbn"]:
        body_text = clean_text(soup.body.get_text(" ", strip=True) if soup.body else "")
        result["isbn"] = extract_isbn(f"{body_text}\n{url}", soup)

    return result


# Mantengo el helper antiguo para no romper código/tests externos.
def fetch_author_from_detail(
    url: str,
    session: requests.Session,
    timeout: tuple[int, int],
) -> str:
    """Compat helper: ahora delega en fetch_metadata_from_detail()."""
    return fetch_metadata_from_detail(url, session, timeout).get("author", "")


def extract_author(text: str, card: Any = None) -> str:
    """Best-effort extracción del autor/mangaka. Devuelve "" si no encuentra."""
    # 1) Selectores HTML estructurados.
    if card is not None:
        for selector in (
            "[itemprop='author']",
            "[class*='author']",
            "[class*='Author']",
            "[class*='byline']",
            "[class*='mangaka']",
            "meta[name='author']",
        ):
            try:
                node = card.select_one(selector)
            except Exception:
                continue
            if node is None:
                continue
            value = node.get("content") if node.name == "meta" else node.get_text(" ", strip=True)
            cleaned = clean_text(value or "")
            if cleaned and 2 < len(cleaned) < 80:
                return cleaned
    # 2) Regex sobre texto plano.
    if text:
        for pattern in (AUTHOR_PREFIX_PATTERN, AUTHOR_BY_PATTERN):
            match = pattern.search(text)
            if match:
                result = _validate_author_candidate(match.group(1))
                if result:
                    return result
    return ""


# Stock limitado: solo lo afirmamos cuando hay señal clara. La ausencia de
# señal NO implica que sea stock permanente — simplemente no lo sabemos.
LIMITED_STOCK_SIGNAL_TYPES = frozenset({
    "limited", "made_to_order", "retailer_exclusive",
})

LIMITED_STOCK_KEYWORDS = (
    "while supplies last", "mientras haya stock", "hasta agotar",
    "tirage limité", "tirage limite",
    "数量限定", "完全受注生産", "受注生産", "予約限定", "初回限定",
    "limitata 500", "limitata 1000", "numbered",
    "numerada", "numerée", "numerata",
)


def derive_stock_type(signal_types: list[str], title: str, description: str) -> str:
    """Devuelve 'limited' si hay señal explícita de stock limitado, "" si no."""
    if any(t in LIMITED_STOCK_SIGNAL_TYPES for t in signal_types or []):
        return "limited"
    if not (title or description):
        return ""
    text = normalize_text(f"{title} {description}")
    for kw in LIMITED_STOCK_KEYWORDS:
        if normalize_text(kw) in text:
            return "limited"
    return ""


# --- Filtro non-manga -------------------------------------------------------
#
# Algunas fuentes oficiales (Dark Horse Direct, Panini MX search, KADOKAWA
# Store) mezclan en su catálogo figuras, estatuas, puzzles, DVDs, Funkos y
# otros productos derivados que NO son manga. La regla del usuario:
#   "Solo quiero mangas, pero asegúrate de no descartar un manga con extras
#    por error. Por ejemplo, un manga edición especial que vino con una
#    figura de extras."
#
# Estrategia:
#   1. STRONG_MANGA_HINTS: si el título contiene cualquier indicador
#      inequívoco de manga (manga, tomo N, vol N, kanzenban, artbook,
#      doujinshi, etc.), se acepta SIEMPRE.
#   2. PACK_EXTRAS_HINTS: si el título contiene patrones tipo
#      "edición especial + figura", "incluye figurita", "shikishi", etc.
#      → es un manga con extras, se acepta.
#   3. NON_MANGA_HEAD: si el título empieza o destaca con figura/estatua/
#      Funko/DVD/puzzle/etc. SIN ningún rescue de (1) o (2), se descarta.
#   4. Default: aceptar (conservador, mejor false-positive que perder mangas).

# Indicadores fuertes de manga/libro de manga. Si está en el título, se
# acepta sin importar lo demás.
_STRONG_MANGA_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bmanga\b", re.IGNORECASE),
    re.compile(r"\b(?:vol(?:ume|umen|\.)?|tome|tomo|band)\s*\.?\s*\d", re.IGNORECASE),
    re.compile(r"\b(?:kanzenban|kanzeban|bunko|aizoban|tankōbon|tankobon|wideban|ultimate edition)\b", re.IGNORECASE),
    re.compile(r"\b(?:art\s*book|artbook|fan\s*book|fanbook|data\s*book|guide\s*book|illustrations? book|character book)\b", re.IGNORECASE),
    re.compile(r"\b(?:doujinshi|d[oō]jinshi|d[oō]jin)\b", re.IGNORECASE),
    re.compile(r"\b(?:light\s*novel|novela ligera|roman l[ée]ger)\b", re.IGNORECASE),
    re.compile(r"\bn[º°o]\s*\d+\b"),     # "nº 12", "n° 5"
    re.compile(r"#\d+\b"),                # "#22"
    re.compile(r"(?:\d+[\s\-]?en[\s\-]?1|3 en 1|integral)", re.IGNORECASE),
    # Términos japoneses inequívocos de manga/libro
    re.compile(r"巻|コミック|漫画|単行本|愛蔵版|完全版|文庫|新書|画集|設定資料集"),
)

# Patrones que confirman "manga + extras" (set / pack / edición coleccionista).
# Si el título es una figura PERO también dice "incluye manga", se acepta.
_MANGA_WITH_EXTRAS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\+\s*(?:figura|figurine|figure|statue|estatua|maquette)\b", re.IGNORECASE),
    re.compile(r"(?:edición|edicion|edizione|edition|édition)\s+(?:especial|coleccionista|limit\w+|collector|coffret|deluxe)", re.IGNORECASE),
    re.compile(r"\bcofre\s+especial\b|\bcofanetto\b|\bcoffret\b|\bbox\s*set\b|\bboxset\b", re.IGNORECASE),
    re.compile(r"(?:incluye|includes|inclut|incluye además|con extras|with bonus|con bonus)", re.IGNORECASE),
    re.compile(r"\bshikishi\b|\bmarcap[áa]ginas\b|\bbloc de notas\b|\bpostales\b|\bp[óo]ster\s+reversible\b", re.IGNORECASE),
)

# NON-MANGA tier HARD: productos que SIEMPRE son productos completos, jamás
# extras dentro de una edición especial de manga. Match aquí → descarte
# inmediato, sin pasar por rescue de strong-manga (esto es importante para
# casos como "<título japonés> Blu-ray BOX 下巻" donde "巻" matchearía como
# strong-manga pero el ítem real es Blu-ray).
_NON_MANGA_HARD: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:DVD|blu-?ray)(?:\s*(?:BOX|SET|EDITION|DISC)|\b)", re.IGNORECASE),
    re.compile(r"\bvinyl\s*figure\b", re.IGNORECASE),
    re.compile(r"\bPVC\s*(?:figure|statue)\b", re.IGNORECASE),
    re.compile(r"\baction\s*figure\b", re.IGNORECASE),
    re.compile(r"\bnendoroid\b|\bfigma\b", re.IGNORECASE),
    re.compile(r"\b(?:pop!?\s+)?funko\b|\bfunko\s+pop\b", re.IGNORECASE),
    re.compile(r"\bmodel\s*kit\b", re.IGNORECASE),
    # Marcas dedicadas a figuras coleccionables (no manga).
    re.compile(r"\bQ[\s\-]?Posket\b", re.IGNORECASE),
    re.compile(r"\bYou\s?Tooz\b", re.IGNORECASE),
    re.compile(r"\bBanpresto\b", re.IGNORECASE),
    # "Figure Bundle / Set / Pack / Series" — pack de figuras, no manga.
    re.compile(r"\bFigure\s+(?:Bundle|Set|Pack|Series)\b", re.IGNORECASE),
    re.compile(r"ブルーレイ|DVD\s*BOX|フィギュア"),
)

# NON-MANGA tier SOFT: pueden aparecer como extras en packs de manga. Por eso
# solo aplica si NO se rescató antes via strong-manga o pack-extras.
_NON_MANGA_SOFT: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:premium\s+)?statu(?:e|ette)\b", re.IGNORECASE),
    re.compile(r"\bmaquette\b", re.IGNORECASE),
    re.compile(r"\bbust\b(?!\s*card)", re.IGNORECASE),
    re.compile(r"\bdiorama\b", re.IGNORECASE),
    re.compile(r"\bplush\b|\bpeluche\b", re.IGNORECASE),
    re.compile(r"\bskate\s*deck\b", re.IGNORECASE),
    re.compile(r"\b(?:puzzle|jigsaw|rompecabeza)\b", re.IGNORECASE),
    re.compile(r"\b(?:keychain|llavero|porte-?cl[ée]s)\b", re.IGNORECASE),
    re.compile(r"\bposter\s+only\b", re.IGNORECASE),
    re.compile(r"\b(?:card\s*game|trading\s*card)\b", re.IGNORECASE),
    re.compile(r"\bcosplay\s+(?:costume|suit|outfit|wig)\b", re.IGNORECASE),
    re.compile(r"\b(?:soundtrack|OST original)\b", re.IGNORECASE),
    re.compile(r"\b(?:mug|taza)\b", re.IGNORECASE),
    re.compile(r"\b(?:backpack|mochila)\b", re.IGNORECASE),
    re.compile(r"\bT-?shirt\b|\bcamiseta\b|\bplayera\b", re.IGNORECASE),
    re.compile(r"\bsticker\s+pack\b", re.IGNORECASE),
    # "Figure" como sustantivo principal (al final del título, con o sin paréntesis).
    re.compile(r"\bFigure\b\s*(?:\([^)]*\))?\s*$", re.IGNORECASE),
    # "Art for X Figure" / "Preview for X Figure" → noticia sobre la figura.
    re.compile(r"\bArt\s+for\s+.+\s+Figure\b", re.IGNORECASE),
    # "Statuettes" plural — packs de estatuillas (single 'statuette' ya cae arriba)
    re.compile(r"\bstatuettes\b", re.IGNORECASE),
)


# Tags taxonómicos de fuentes externas (Manga-Sanctuary, ListadoManga) que
# indican que el item NO es un manga: anime, films, OAV, merchandising,
# productos derivados. "produit spécial manga" se preserva porque son packs
# de manga reales (coffret manga + artbook, etc.).
_NON_MANGA_TAG_PREFIXES = (
    "type:série tv animée",
    "type:série tv",
    "type:OAV",
    "type:film",
    "type:produit dérivé",
    "type:produit spécial anime",
    "type:webtoon",   # técnicamente parecido a manga pero el usuario quiere manga
    "type:goodies",
    "type:dvd",
    "type:blu-ray",
)


def is_likely_manga(
    title: str,
    description: str = "",
    tags: list[str] | None = None,
) -> tuple[bool, str]:
    """Heurística para decidir si un candidato es un manga (o libro relacionado:
    artbook, novela ligera, edición coleccionista con manga) versus un producto
    derivado puro (figura, estatua, Funko, DVD, puzzle, taza, etc.).

    Returns:
        (is_manga, reason) — `reason` describe la regla que aplicó.

    Reglas (en orden):
      0a. Tag externo indica anime/film/OAV/dérivé → False (alta confianza,
          viene de la taxonomía oficial de la fuente).
      0b. NON-MANGA HARD del título (DVD, Blu-ray, Funko, Vinyl Figure...).
          Estos productos NUNCA son extras en un pack de manga.
      1. STRONG manga hint en título o descripción → True
      2. PACK / extras hint (edición especial + figura, cofanetto...) → True
      3. NON-MANGA SOFT (statue, puzzle, mug, plush…) → False
      4. Default → True (conservador, mejor false-positive que perder mangas)
    """
    if not title:
        return True, "default:empty"

    # 0a) Tag taxonómico de la fuente (Manga-Sanctuary categoriza con "type:...").
    if tags:
        for tag in tags:
            for prefix in _NON_MANGA_TAG_PREFIXES:
                if tag == prefix or tag.startswith(prefix + " "):
                    return False, f"non_manga_tag:{tag}"

    blob = title
    if description:
        # Mirar también en descripción para 'incluye manga' etc. pero NO
        # para detectar non-manga: la descripción de un manga puede mencionar
        # "figura de regalo" sin que el manga deje de ser manga.
        blob_extra = f"{title}\n{description}"
    else:
        blob_extra = title

    # 0) Non-manga HARD: discriminante absoluto.
    for pat in _NON_MANGA_HARD:
        if pat.search(blob):
            return False, f"non_manga_hard:{pat.pattern[:40]}"

    # 1) Strong manga hints
    for pat in _STRONG_MANGA_PATTERNS:
        if pat.search(blob_extra):
            return True, f"strong:{pat.pattern[:40]}"

    # 2) Pack / extras (manga con figura/poster/etc.)
    for pat in _MANGA_WITH_EXTRAS_PATTERNS:
        if pat.search(blob_extra):
            return True, f"pack:{pat.pattern[:40]}"

    # 3) Non-manga SOFT: solo si no se rescató antes.
    for pat in _NON_MANGA_SOFT:
        if pat.search(blob):
            return False, f"non_manga_soft:{pat.pattern[:40]}"

    return True, "default:no_match"


def derive_product_type(title: str, description: str, signal_types: list[str]) -> str:
    """Devuelve el tipo de producto detectado (manga / artbook / boxset / etc.)."""
    if not (title or description):
        return ""
    text = normalize_text(f"{title} {description}")
    for ptype, words in PRODUCT_TYPE_KEYWORDS:
        for w in words:
            if normalize_text(w) in text:
                return ptype
    # Fallback por signal_types (señales del scoring)
    if signal_types:
        if any(t in {"artbook", "fanbook"} for t in signal_types):
            return "artbook"
        if "guidebook" in signal_types:
            return "guidebook"
        if "box_set" in signal_types:
            return "boxset"
    return "manga" if (title or description) else ""


def _expand_search_template(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Expande una entrada con search_template+keywords en N entradas virtuales.

    Cada keyword genera una "fuente expandida" con:
    - name: "<base name> [search: <keyword>]"
    - url: search_template.format(query=quote_plus(keyword))
    - tags: tags base + ["expansion", "search:<keyword>"]
    """
    template = item.get("search_template")
    keywords = item.get("keywords") or []
    if not template or not isinstance(keywords, list) or not keywords:
        return [item]

    base_tags = item.get("tags", []) or []
    expanded: list[dict[str, Any]] = []
    base_name = str(item.get("name", "")).strip() or "search"
    for kw in keywords:
        kw_str = str(kw).strip()
        if not kw_str:
            continue
        url = template.format(query=quote_plus(kw_str))
        new_item = {k: v for k, v in item.items() if k not in {"search_template", "keywords"}}
        new_item["name"] = f"{base_name} [search: {kw_str}]"
        new_item["url"] = url
        new_item["tags"] = list(base_tags) + ["expansion", f"search:{kw_str}"]
        expanded.append(new_item)
    return expanded


def load_sources(path: Path) -> list[Source]:
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}. Crea sources.yml o usa el paquete que te pasé.")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources_raw = raw.get("sources", [])
    sources: list[Source] = []

    for raw_item in sources_raw:
        if not isinstance(raw_item, dict):
            continue
        # Expandir search_template+keywords si está presente.
        for item in _expand_search_template(raw_item):
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
                    max_pages=int(item.get("max_pages", 0) or 0),
                )
            )

    return [source for source in sources if source.name and source.url]


def filter_sources(
    sources: list[Source],
    source_classes: set[str] | None,
    countries: set[str] | None,
    include_disabled: bool,
    include_tags: set[str] | None = None,
    exclude_tags: set[str] | None = None,
    only_tags: set[str] | None = None,
) -> list[Source]:
    filtered: list[Source] = []
    for source in sources:
        if not include_disabled and not source.enabled:
            continue
        if source_classes and source.source_class not in source_classes:
            continue
        if countries and source.country not in countries:
            continue
        source_tags = set(source.tags or [])
        if only_tags and not (source_tags & only_tags):
            continue
        if include_tags and not (source_tags & include_tags):
            continue
        if exclude_tags and (source_tags & exclude_tags):
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


NEXT_PAGE_TEXTS: frozenset[str] = frozenset({
    "siguiente", "next", "next page", "next »", "›", "»", "→",
    "suivant", "successivo", "次へ", "次のページ", "下一页", "下一頁",
    "más resultados", "load more", "ver más",
})

NEXT_PAGE_SELECTORS: tuple[str, ...] = (
    "link[rel='next']",
    "a[rel='next']",
    "a.next",
    "a.pagination__next",
    "a.pagination-next",
    "li.next a",
    "li.pagination-next a",
    "a[class*='-next']",
    "a[class*='Next']",
    "a[class*='next-page']",
    "a[aria-label*='Next' i]",
    "a[aria-label*='Siguiente' i]",
    "a[aria-label*='Suivant' i]",
    "a[aria-label*='Página siguiente' i]",
    "a[aria-label*='Pagina successiva' i]",
)


def find_next_page_url(
    soup: BeautifulSoup, current_url: str, visited: set[str]
) -> str | None:
    """Detecta el link a la próxima página. Devuelve URL absoluta o None.

    Estrategias en orden de confiabilidad:
    1. <link rel="next"> en <head> (estándar SEO)
    2. Selectores conocidos: .next, .pagination__next, [aria-label*=Next], etc.
    3. Texto del link: Siguiente / Next / › / » / Suivant / 次へ / ...
    4. Detección de patrón ?page=N en current_url → buscar ?page=N+1

    Evita loops: no devuelve URLs ya visitadas ni la misma current_url.
    """

    def _accept(href: str | None) -> str | None:
        if not href:
            return None
        url = canonicalize_url(current_url, href)
        if not url or url == current_url or url in visited:
            return None
        # Ignorar URLs de otros dominios (paginación normalmente es same-origin).
        if urlparse(url).netloc and urlparse(current_url).netloc:
            if urlparse(url).netloc != urlparse(current_url).netloc:
                return None
        return url

    # 1 + 2: Selectores conocidos.
    for selector in NEXT_PAGE_SELECTORS:
        try:
            node = soup.select_one(selector)
        except Exception:
            continue
        if node and node.get("href"):
            result = _accept(node.get("href"))
            if result:
                return result

    # 3: Texto del link.
    for anchor in soup.find_all("a", href=True):
        text = clean_text(anchor.get_text(" ", strip=True)).lower()
        if text in NEXT_PAGE_TEXTS:
            result = _accept(anchor.get("href"))
            if result:
                return result

    # 4: Detectar parámetro ?page=N / ?p=N / ?paged=N en current_url y buscar N+1.
    parsed = urlparse(current_url)
    if parsed.query:
        from urllib.parse import parse_qs, urlencode, urlunparse
        params = parse_qs(parsed.query, keep_blank_values=True)
        for page_param in ("page", "p", "paged"):
            values = params.get(page_param)
            if not values:
                continue
            try:
                current_page = int(values[0])
            except (ValueError, TypeError):
                continue
            next_params = {k: v[:] for k, v in params.items()}
            next_params[page_param] = [str(current_page + 1)]
            next_query = urlencode(next_params, doseq=True)
            next_url = urlunparse(
                (parsed.scheme, parsed.netloc, parsed.path, parsed.params, next_query, parsed.fragment)
            )
            if next_url != current_url and next_url not in visited:
                # Verificar que el N+1 aparezca explícitamente en algún anchor de la página.
                # Esto evita generar URLs que no existen.
                for anchor in soup.find_all("a", href=True):
                    href = anchor.get("href", "")
                    if f"{page_param}={current_page + 1}" in href:
                        return next_url
    return None


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
    cleaned_title = clean_title(title) if title else title
    return Candidate(
        title=cleaned_title or f"Hallazgo en {source.name}",
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
            candidate = candidate_from_source(source, title, link or source.url, description)
            schema = extract_schema_org_product(card, source.url)
            if schema.get("name") and len(schema["name"]) >= 3:
                candidate.title = clean_title(schema["name"])[:260]
            if schema.get("description") and len(schema["description"]) > len(candidate.description):
                candidate.description = schema["description"][:2500]
            candidate.price = schema.get("price") or extract_price(candidate.description)
            candidate.image_url = schema.get("image_url") or extract_image_url(card, source.url)
            candidate.release_date = schema.get("release_date") or extract_release_date(candidate.description)
            candidate.author = schema.get("author") or extract_author(candidate.description, card)
            candidate.isbn = schema.get("isbn") or extract_isbn(f"{candidate.description}\n{candidate.url}", card)
            candidates.append(candidate)

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


GENERIC_ANCHOR_TEXTS: frozenset[str] = frozenset({
    # Español
    "leer mas", "leer más", "ver mas", "ver más", "ver detalles", "mas info",
    "más info", "más información", "comprar", "añadir al carrito",
    "agregar al carrito",
    # Inglés
    "read more", "see more", "learn more", "view details", "view more",
    "add to cart", "buy now", "shop now", "details",
    # Francés
    "lire la suite", "voir plus", "en savoir plus", "voir le produit",
    "ajouter au panier",
    # Italiano
    "leggi tutto", "leggi di piu", "leggi di più", "scopri di piu",
    "scopri di più", "vedi tutti", "aggiungi al carrello",
    # Japonés
    "詳しく見る", "続きを読む", "詳細を見る", "もっと見る", "カートに入れる",
    # Genéricos
    "more", "info", "details", "shop", "go", "next", "→",
})


def _is_generic_anchor_text(text: str) -> bool:
    """¿Es texto genérico de 'leer más / ver detalle' en lugar del título real?"""
    if not text:
        return True
    lower = text.lower().strip()
    if lower in GENERIC_ANCHOR_TEXTS:
        return True
    # Caso "Leer más sobre X..." (empieza con un texto genérico).
    for generic in GENERIC_ANCHOR_TEXTS:
        if lower.startswith(generic + " ") or lower.startswith(generic + ":"):
            return True
    return False


def _derive_title(card: Any, anchor: Any) -> str:
    """Extrae título de un card en orden de prioridad razonable.

    Si el texto del anchor es genérico ("Leer más", "Lire la suite", "詳しく見る",
    etc.), busca el título real en headings / [class*='title'] / img alt.
    """
    title = clean_text(anchor.get_text(" ", strip=True))
    if title and not _is_generic_anchor_text(title):
        return title

    # Anchor envuelve solo una imagen: probar alt.
    img = anchor.find("img")
    if img:
        alt = clean_text(img.get("alt") or img.get("title") or "")
        if alt and not _is_generic_anchor_text(alt):
            return alt
    # Headings dentro de la card.
    heading = card.find(["h1", "h2", "h3", "h4", "h5", "h6"])
    if heading:
        text = clean_text(heading.get_text(" ", strip=True))
        if text and not _is_generic_anchor_text(text):
            return text
    # Elementos con class title/name/heading.
    for selector in ("[class*='title']", "[class*='Title']", "[class*='name']", "[class*='Name']"):
        try:
            node = card.select_one(selector)
        except Exception:
            continue
        if node:
            text = clean_text(node.get_text(" ", strip=True))
            if text and not _is_generic_anchor_text(text):
                return text
    # Última opción: img alt de cualquier imagen dentro de la card.
    img = card.find("img")
    if img:
        alt = clean_text(img.get("alt") or img.get("title") or "")
        if alt and not _is_generic_anchor_text(alt):
            return alt
    # Fallback: si el único texto disponible es genérico, devolvemos el anchor
    # original (al menos no perdemos el item; el reporte lo va a mostrar feo).
    return title


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
    candidate = candidate_from_source(source, title[:260], url, description)

    # Estrategia 0: si la card tiene JSON-LD inline (Shopify, Magento moderno…),
    # usar esos datos como override (mayor calidad que las heurísticas).
    schema = extract_schema_org_product(card, source.url)

    # Title: si Schema.org tiene un name más específico, lo usamos.
    if schema.get("name") and len(schema["name"]) >= 3:
        candidate.title = clean_title(schema["name"])[:260]

    # Description: si la de Schema es más sustancial, la preferimos.
    if schema.get("description") and len(schema["description"]) > len(candidate.description):
        candidate.description = schema["description"][:2500]

    candidate.price = schema.get("price") or extract_price(candidate.description)
    candidate.image_url = schema.get("image_url") or extract_image_url(card, source.url)
    candidate.release_date = schema.get("release_date") or extract_release_date(candidate.description)
    candidate.author = schema.get("author") or extract_author(candidate.description, card)
    candidate.isbn = schema.get("isbn") or extract_isbn(f"{candidate.description}\n{url}", card)
    return candidate


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
        # Inyectar keywords de búsqueda dirigida en el combined text para que
        # cards de Glénat / Pika / etc. pasen el filtro aunque el card no
        # incluya el keyword textualmente.
        search_kw_text = " ".join(
            tag.split(":", 1)[1].strip()
            for tag in (source.tags or [])
            if tag.startswith("search:")
        )
        combined = f"{candidate.title}\n{candidate.description}\n{search_kw_text}"
        score, _signals, _types = detect_signals(combined)
        if score <= 0:
            if info is not None:
                info["cards_skipped_no_signals"] += 1
            continue
        # Filtro non-manga: descarta figuras/estatuas/Funkos/DVDs/etc.
        # con rescue para mangas que vienen con extras (figura de regalo, etc.).
        is_manga, _reason = is_likely_manga(
            candidate.title, candidate.description, tags=candidate.tags
        )
        if not is_manga:
            if info is not None:
                info["cards_skipped_non_manga"] = info.get("cards_skipped_non_manga", 0) + 1
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
        # Filtro non-manga: descarta figuras/estatuas/Funkos/DVDs/etc.
        is_manga, _reason = is_likely_manga(title, summary)
        if not is_manga:
            continue
        candidate = candidate_from_source(source, title, link, summary, published_at=published_at)
        candidate.price = extract_price(summary)
        # RSS rara vez incluye <img> en el summary; intentamos parsearlo si está embebido.
        if "<img" in (entry.get("summary", "") or entry.get("content", "") or ""):
            try:
                rss_soup = BeautifulSoup(
                    entry.get("summary", "") or str(entry.get("content", "")), "html.parser"
                )
                candidate.image_url = extract_image_url(rss_soup, source.url)
            except Exception:
                pass
        candidate.release_date = extract_release_date(summary) or published_at
        candidate.author = extract_author(summary)
        candidate.isbn = extract_isbn(f"{summary}\n{link}")
        candidates.append(candidate)
    return candidates


def score_candidate(candidate: Candidate) -> Candidate:
    # Si la source es una búsqueda dirigida (tag 'search:<keyword>'), inyectamos
    # ese keyword como señal "fantasma" en el texto a evaluar. La editorial ya
    # filtró su catálogo por ese keyword, así que cualquier card devuelta puede
    # razonablemente considerarse coleccionista — aunque el snippet visible no
    # lo diga textualmente.
    search_keywords: list[str] = [
        tag.split(":", 1)[1].strip()
        for tag in (candidate.tags or [])
        if tag.startswith("search:")
    ]

    combined = "\n".join(
        [
            candidate.title,
            candidate.description,
            candidate.publisher,
            candidate.source,
            " ".join(candidate.tags),
            # Inyección de keywords de búsqueda dirigida:
            " ".join(search_keywords),
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

    candidate.score = max(0, min(score, 300))
    candidate.signals = signals
    candidate.signal_types = signal_types
    candidate.product_type = derive_product_type(
        candidate.title, candidate.description, signal_types
    )
    candidate.stock_type = derive_stock_type(
        signal_types, candidate.title, candidate.description
    )
    _recompute_content_hash(candidate)
    return candidate


def _recompute_content_hash(candidate: Candidate) -> None:
    """Recalcula content_hash a partir de los campos persistidos.

    Usado tras un detail-fetch que actualiza author / metadata, para que
    el cambio se refleje en el hash y se detecte como 'changed'.
    """
    candidate.content_hash = sha256_text(
        json.dumps(
            {
                "title": candidate.title,
                "url": candidate.url,
                "description": candidate.description,
                "score": candidate.score,
                "signals": candidate.signals,
                "source_class": candidate.source_class,
                "price": candidate.price,
                "release_date": candidate.release_date,
                "product_type": candidate.product_type,
                "author": candidate.author,
                "stock_type": candidate.stock_type,
                "isbn": candidate.isbn,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def candidate_key(candidate: Candidate) -> str:
    """Clave de dedup. Normaliza URL para colapsar mismo producto con
    URLs sutilmente distintas (tracking params Shopify, collections, etc.)."""
    if candidate.url:
        return f"url:{normalize_url_for_dedup(candidate.url)}"
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

    # Primer pase: dedup por URL normalizada (mismo producto, mismo retailer).
    for candidate in candidates:
        key = candidate_key(candidate)
        current = deduped.get(key)
        if current is None or candidate.score > current.score:
            deduped[key] = candidate

    # Segundo pase: colapsar por ISBN (mismo producto físico, distintos retailers).
    # Solo si el ISBN no está vacío. Conservamos el candidato de mayor score; los
    # otros se descartan y NO entran al state ni al reportable.
    by_isbn: dict[str, str] = {}
    isbn_collapsed = 0
    for key, cand in list(deduped.items()):
        if not cand.isbn:
            continue
        existing_key = by_isbn.get(cand.isbn)
        if existing_key is None:
            by_isbn[cand.isbn] = key
            continue
        # Hay otro candidato con el mismo ISBN → comparar scores.
        existing = deduped[existing_key]
        if cand.score > existing.score:
            del deduped[existing_key]
            by_isbn[cand.isbn] = key
        else:
            del deduped[key]
        isbn_collapsed += 1
    if isbn_collapsed:
        print(f"[DEDUP] {isbn_collapsed} duplicados colapsados por ISBN coincidente")

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
            "price": candidate.price,
            "image_url": candidate.image_url,
            "release_date": candidate.release_date,
            "product_type": candidate.product_type,
            "author": candidate.author,
            "stock_type": candidate.stock_type,
            "isbn": candidate.isbn,
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
        "price": candidate.price,
        "image_url": candidate.image_url,
        "release_date": candidate.release_date,
        "product_type": candidate.product_type,
        "author": candidate.author,
        "stock_type": candidate.stock_type,
        "isbn": candidate.isbn,
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
            if item.product_type:
                lines.append(f"- **Tipo de producto:** {item.product_type}")
            if item.author:
                lines.append(f"- **Autor:** {item.author}")
            if item.stock_type == "limited":
                lines.append("- **Stock:** ⚠️ limitado / numerado")
            if item.price:
                lines.append(f"- **Precio:** {item.price}")
            if item.release_date:
                lines.append(f"- **Fecha de lanzamiento:** {item.release_date}")
            if item.published_at:
                lines.append(f"- **Fecha publicada:** {item.published_at}")
            lines.append(f"- **Señales:** {', '.join(item.signals) if item.signals else 'N/D'}")
            lines.append(f"- **Tipos:** {', '.join(item.signal_types) if item.signal_types else 'N/D'}")
            lines.append(f"- **Tags:** {', '.join(item.tags) if item.tags else 'N/D'}")
            lines.append(f"- **Link:** {item.url}")
            if item.image_url:
                lines.append(f"- **Imagen:** {item.image_url}")
                lines.append("")
                lines.append(f"![{item.title[:80]}]({item.image_url})")
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
            "pages_visited": 1,
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
        if entry.get("pages_visited", 1) > 1:
            lines.append(f"- **Páginas visitadas:** {entry['pages_visited']}")
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


def _parse_wiki_month(value: str, default_year: int, default_month: int) -> tuple[int, int]:
    """Parsea 'YYYY-MM' a (year, month). Si está vacío, usa defaults."""
    if not value:
        return default_year, default_month
    try:
        y, m = value.split("-")
        return int(y), int(m)
    except (ValueError, AttributeError):
        raise SystemExit(f"--wiki-from/--wiki-to debe ser YYYY-MM. Recibido: {value!r}")


def _run_wiki_bootstrap(
    args: argparse.Namespace,
    session: requests.Session,
    state: dict[str, Any],
    state_path: Path,
    items_path: Path,
    report_path: Path,
) -> int:
    """Modo --bootstrap-wiki: importa items de una wiki comunitaria al state."""
    today = dt.date.today()
    yf, mf = _parse_wiki_month(args.wiki_from, 2024, 1)
    yt, mt = _parse_wiki_month(args.wiki_to, today.year, today.month)

    print(f"[BOOTSTRAP-WIKI] fuente: {args.bootstrap_wiki}")
    print(f"                rango: {yf:04d}-{mf:02d} → {yt:04d}-{mt:02d}")
    print(f"                min-score: {args.min_score}")
    print()

    # Asegurar que scripts/ esté en sys.path para que 'wikis' sea importable
    # tanto si corremos desde root como desde el wrapper.
    _scripts_dir = str(Path(__file__).resolve().parent)
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)

    if args.bootstrap_wiki == "listadomanga":
        from wikis.listadomanga import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "manga-sanctuary":
        from wikis.manga_sanctuary import bootstrap as wiki_bootstrap, iter_year_months
    else:
        raise SystemExit(f"Wiki no soportada: {args.bootstrap_wiki}")

    candidates = wiki_bootstrap(
        yf, mf, yt, mt,
        session=session,
        sleep_seconds=args.sleep_seconds,
        timeout=(args.connect_timeout, args.read_timeout),
        min_score=args.min_score,
        fetch_details=bool(args.fetch_details),
    )
    months = iter_year_months(yf, mf, yt, mt)

    print(f"\n[BOOTSTRAP-WIKI] {len(candidates)} candidates con score>={args.min_score} sobre {len(months)} meses")

    # process_state aplica el dedup en cascada (URL normalizada + ISBN).
    reportable, state = process_state(
        candidates=candidates,
        state=state,
        min_score=args.min_score,
        include_seen=args.include_seen,
    )

    if not args.dry_run:
        save_state(state_path, state)
        new_or_changed = [
            candidate_to_json(c) for c in reportable if c.status in {"new", "changed"}
        ]
        append_jsonl(items_path, new_or_changed)
        write_markdown_report(
            path=report_path,
            reportable=reportable,
            errors=[],
            problems=[],
            min_score=args.min_score,
        )

    print()
    print("[RESUMEN BOOTSTRAP-WIKI]")
    print(f"  candidates totales: {len(candidates)}")
    print(f"  reportables (new/changed): {sum(1 for c in reportable if c.status in {'new', 'changed'})}")
    print(f"  ya conocidos (seen): {sum(1 for c in reportable if c.status == 'seen')}")
    print(f"  jsonl: {items_path}")
    print(f"  state: {state_path}")
    print(f"  reporte: {report_path}")
    return 0


def _run_sitemap_mining(
    args: argparse.Namespace,
    sources: list[Source],
    session: requests.Session,
    state: dict[str, Any],
    state_path: Path,
    items_path: Path,
    report_path: Path,
) -> int:
    """Modo --discover-sitemaps: descubre productos vía /sitemap.xml."""
    _scripts_dir = str(Path(__file__).resolve().parent)
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
    from sitemap_miner import discover_and_filter

    # Solo sources canónicas HTML (no rss, no js, no search-template).
    eligible = [
        s for s in sources
        if s.kind == "html"
        and s.enabled
        and not any(t.startswith("search:") for t in (s.tags or []))
        and "expansion" not in (s.tags or [])
    ]
    print(f"[SITEMAP] {len(eligible)} sources elegibles (kind=html, no expansion)")
    print(f"[SITEMAP] max-urls por source: {args.sitemap_max_urls}")
    print()

    all_candidates: list[Candidate] = []
    sitemap_stats: list[dict[str, Any]] = []

    for idx, source in enumerate(eligible, start=1):
        print(f"[{idx}/{len(eligible)}] {source.name}")
        result = discover_and_filter(
            source.url, session,
            max_urls=args.sitemap_max_urls * 10,  # más amplio antes de filtrar
            timeout=(args.connect_timeout, args.read_timeout),
        )
        if not result["sitemap_url"]:
            print(f"    (sin sitemap accesible)")
            sitemap_stats.append({"source": source.name, "sitemap": "", "urls": 0, "products": 0, "candidates": 0})
            continue

        product_urls = result["product_urls"][: args.sitemap_max_urls]
        print(f"    sitemap: {result['sitemap_url']}")
        print(f"    URLs totales: {len(result['all_urls'])} · productos filtrados: {len(result['product_urls'])} · a procesar: {len(product_urls)}")

        # Procesar cada URL: 1 HTTP por URL (fetch_metadata_from_detail ahora
        # devuelve TODOS los campos incluido name/price/release/publisher).
        kept = 0
        for u_idx, prod_url in enumerate(product_urls, start=1):
            md = fetch_metadata_from_detail(
                prod_url, session,
                timeout=(args.connect_timeout, args.read_timeout),
            )
            title = md.get("name") or _slugify(urlparse(prod_url).path).replace("-", " ")[:200]
            description = md.get("description") or title
            cand = candidate_from_source(source, title=title[:260], url=prod_url, description=description[:2500])
            cand.publisher = md.get("publisher") or source.publisher
            cand.price = md.get("price", "")
            cand.image_url = md.get("image_url", "")
            cand.release_date = md.get("release_date", "")
            cand.author = md.get("author", "")
            cand.isbn = md.get("isbn", "")
            cand.tags = list(source.tags or []) + ["sitemap"]
            score_candidate(cand)
            # Filtro non-manga (figuras, estatuas, DVDs, etc.).
            is_manga, _reason = is_likely_manga(
                cand.title, cand.description, tags=cand.tags
            )
            if not is_manga:
                continue
            if cand.score >= args.min_score:
                all_candidates.append(cand)
                kept += 1
            if args.sleep_seconds > 0 and u_idx < len(product_urls):
                time.sleep(min(args.sleep_seconds, 0.5))
            if u_idx % 50 == 0:
                print(f"    [{u_idx}/{len(product_urls)}] kept={kept}")

        print(f"    → {kept} candidates con score >= {args.min_score}")
        sitemap_stats.append({
            "source": source.name,
            "sitemap": result["sitemap_url"],
            "urls": len(result["all_urls"]),
            "products": len(result["product_urls"]),
            "candidates": kept,
        })

    print()
    print(f"[SITEMAP] Total candidates con señales: {len(all_candidates)}")

    reportable, state = process_state(
        candidates=all_candidates,
        state=state,
        min_score=args.min_score,
        include_seen=args.include_seen,
    )

    if not args.dry_run:
        save_state(state_path, state)
        new_or_changed = [
            candidate_to_json(c) for c in reportable if c.status in {"new", "changed"}
        ]
        append_jsonl(items_path, new_or_changed)
        write_markdown_report(
            path=report_path,
            reportable=reportable,
            errors=[],
            problems=[],
            min_score=args.min_score,
        )

    print("\n[RESUMEN SITEMAP MINING]")
    print(f"  sources procesadas: {len(eligible)}")
    print(f"  con sitemap útil:   {sum(1 for s in sitemap_stats if s['sitemap'])}")
    print(f"  candidates totales: {len(all_candidates)}")
    print(f"  reportables (new/changed): {sum(1 for c in reportable if c.status in {'new', 'changed'})}")
    print(f"  ya conocidos (seen):       {sum(1 for c in reportable if c.status == 'seen')}")
    print(f"  jsonl: {items_path}")
    print()
    print(f"Top 5 sources por items aportados:")
    sitemap_stats.sort(key=lambda x: -x["candidates"])
    for s in sitemap_stats[:5]:
        if s["candidates"] > 0:
            print(f"  {s['candidates']:4d}  ({s['products']:4d} productos del sitemap)  {s['source']}")
    return 0


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
        include_tags=parse_csv_arg(getattr(args, "include_tags", "")),
        exclude_tags=parse_csv_arg(getattr(args, "exclude_tags", "")),
        only_tags=parse_csv_arg(getattr(args, "only_tags", "")),
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

    # === Fase 2: bootstrap desde wiki comunitaria ===
    if args.bootstrap_wiki:
        return _run_wiki_bootstrap(args, session, state, state_path, items_path, report_path)

    # === Fase 3: sitemap mining ===
    if args.discover_sitemaps:
        return _run_sitemap_mining(args, sources, session, state, state_path, items_path, report_path)

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

            # Determinar max_pages efectivo para esta fuente.
            if source.kind in {"rss", "feed", "atom"}:
                effective_max_pages = 1  # RSS no se pagina
            elif source.max_pages > 0:
                effective_max_pages = source.max_pages
            else:
                effective_max_pages = args.max_pages

            # Pre-validación para kind:js.
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

            # Loop de paginación.
            visited_urls: set[str] = set()
            current_url = source.url
            all_candidates_source: list[Candidate] = []
            pages_visited = 0
            skipped_for_js = False

            for page_num in range(1, effective_max_pages + 1):
                visited_urls.add(current_url)
                pages_visited = page_num

                # Fetch (HTTP normal o Playwright según kind).
                if source.kind == "js":
                    text, fetch_meta = fetch_with_playwright(
                        url=current_url,
                        timeout_ms=args.read_timeout * 1000,
                    )
                else:
                    text, fetch_meta = fetch_with_metadata(
                        session=session,
                        url=current_url,
                        timeout=(args.connect_timeout, args.read_timeout),
                    )

                # Solo registramos fetch/anchors de la página 1 en diagnostic.
                if page_num == 1:
                    diagnostic.record_fetch(fetch_meta, text)

                # Extract según kind.
                if source.kind in {"rss", "feed", "atom"}:
                    page_candidates = extract_rss(
                        source,
                        text,
                        max_items=args.max_items_per_source,
                        max_age_days=args.max_age_days,
                    )
                    if diagnostic.enabled and info is not None and page_num == 1:
                        info["extraction_method"] = "rss"
                        info["candidates_after_signals"] = len(page_candidates)
                    all_candidates_source.extend(page_candidates)
                    break  # RSS no pagina

                pre_soup = BeautifulSoup(text, "html.parser")
                for stripped in pre_soup(["script", "style", "noscript", "svg"]):
                    stripped.decompose()
                if page_num == 1:
                    diagnostic.record_anchor_counts(pre_soup)

                if source.kind == "js":
                    page_candidates = extract_generic_html(
                        source,
                        text,
                        max_items=args.max_items_per_source,
                        info=info if page_num == 1 else None,
                    )
                else:
                    js_check = detect_empty_or_js(text, pre_soup) if page_num == 1 else None
                    if js_check is not None:
                        category, message = js_check
                        print(f"[SKIP-{category}] {source.name}: {message}")
                        record_problem(source.name, category, message)
                        diagnostic.record_status(category, message)
                        skipped_for_js = True
                        break
                    page_candidates = extract_generic_html(
                        source,
                        text,
                        max_items=args.max_items_per_source,
                        info=info if page_num == 1 else None,
                    )

                all_candidates_source.extend(page_candidates)

                # ¿Hay próxima página?
                if page_num >= effective_max_pages:
                    break
                next_url = find_next_page_url(pre_soup, current_url, visited_urls)
                if not next_url:
                    break
                # Pequeña pausa entre páginas del mismo sitio.
                if args.sleep_seconds > 0:
                    time.sleep(min(args.sleep_seconds, 1.0))
                current_url = next_url

            if not skipped_for_js:
                scored = [score_candidate(candidate) for candidate in all_candidates_source]
                all_candidates.extend(scored)
                diagnostic.record_candidates(scored)
                # Registrar pages_visited en diagnostic.
                if diagnostic.enabled and info is not None:
                    info["pages_visited"] = pages_visited
                pages_note = f" ({pages_visited} págs)" if pages_visited > 1 else ""
                print(f"    candidatos con señales: {len(scored)}{pages_note}")

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

    # Detail-fetch para enriquecer autor en items importantes (opt-in).
    if args.fetch_details:
        # Item es elegible si le falta autor O imagen (ambos enriquecibles desde detail).
        eligible = [
            c for c in reportable
            if c.status in {"new", "changed"}
            and c.score >= args.fetch_details_min_score
            and (not c.author or not c.image_url)
            and c.source_class in ("official", "retailer")
            and c.url
        ]
        # Skip URLs que coincidan con la URL de la fuente (son listings).
        source_urls = {s.url for s in sources}
        eligible = [c for c in eligible if c.url not in source_urls]
        print("")
        print(
            f"[FETCH-DETAILS] {len(eligible)} items elegibles "
            f"(score>={args.fetch_details_min_score}, sin autor o sin imagen, official/retailer)"
        )
        enriched_author = 0
        enriched_image = 0
        for idx, c in enumerate(eligible, start=1):
            metadata = fetch_metadata_from_detail(
                c.url, session, timeout=(args.connect_timeout, args.read_timeout)
            )
            new_author = metadata.get("author") or ""
            new_image = metadata.get("image_url") or ""
            new_isbn = metadata.get("isbn") or ""
            updates: list[str] = []
            if new_author and not c.author:
                c.author = new_author
                enriched_author += 1
                updates.append(f"autor: {new_author[:50]}")
            if new_image and not c.image_url:
                c.image_url = new_image
                enriched_image += 1
                updates.append(f"img: ✓")
            if new_isbn and not c.isbn:
                c.isbn = new_isbn
                updates.append(f"isbn: {new_isbn}")
            if updates:
                _recompute_content_hash(c)
                key = candidate_key(c)
                if key in state:
                    state[key]["author"] = c.author
                    state[key]["image_url"] = c.image_url
                    state[key]["isbn"] = c.isbn
                    state[key]["content_hash"] = c.content_hash
                print(f"  [{idx}/{len(eligible)}] {c.source[:30]:30s} → {', '.join(updates)}")
            else:
                print(f"  [{idx}/{len(eligible)}] {c.source[:30]:30s} → (sin cambios)")
            if args.sleep_seconds > 0 and idx < len(eligible):
                time.sleep(min(args.sleep_seconds, 1.0))
        print(
            f"[FETCH-DETAILS] {enriched_author} autores · {enriched_image} imágenes enriquecidas"
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
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Máximo de páginas a seguir por fuente cuando hay link 'siguiente'. Default: 5 (suficiente para búsquedas Fase 1 y categorías específicas). Override por fuente en YAML con 'max_pages: 15' para catálogos grandes. RSS siempre = 1.",
    )
    parser.add_argument("--sleep-seconds", type=float, default=1.5, help="Pausa entre fuentes. Default: 1.5")
    parser.add_argument("--connect-timeout", type=int, default=10, help="Timeout conexión HTTP. Default: 10")
    parser.add_argument("--read-timeout", type=int, default=30, help="Timeout lectura HTTP. Default: 30")
    parser.add_argument("--user-agent", default="manga-watch-personal/0.2 (+personal-use)", help="User-Agent")
    parser.add_argument("--respect-robots", action="store_true", help="Respeta robots.txt antes de consultar cada fuente")
    parser.add_argument("--include-seen", action="store_true", help="Incluye elementos ya vistos en el reporte")
    parser.add_argument("--include-disabled", action="store_true", help="Incluye fuentes enabled:false")
    parser.add_argument("--source-classes", default="", help="Filtra por clases: official,retailer,trusted_media,social")
    parser.add_argument("--countries", default="", help="Filtra por país exacto, separado por comas. Ej: España,Francia,Japón")
    parser.add_argument(
        "--include-tags",
        default="",
        help="Solo procesa fuentes que tienen AL MENOS uno de estos tags (CSV). Ej: expansion,manga",
    )
    parser.add_argument(
        "--exclude-tags",
        default="",
        help="Excluye fuentes que tienen alguno de estos tags (CSV). Ej: expansion para skipear las búsquedas.",
    )
    parser.add_argument(
        "--only-tags",
        default="",
        help="Alias estricto: solo fuentes con AL MENOS uno de estos tags (igual a --include-tags). Ej: --only-tags expansion",
    )
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
    parser.add_argument(
        "--fetch-details",
        action="store_true",
        help="Tras detectar items, hace 1 HTTP extra a la página de cada item para extraer autor (solo para items new/changed con score alto). Mejora cobertura de author del 2%% al ~50%%.",
    )
    parser.add_argument(
        "--fetch-details-min-score",
        type=int,
        default=70,
        help="Score mínimo para hacer detail-fetch. Default: 70 (solo urgentes).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Ejecuta sin escribir estado, JSONL ni reportes")
    parser.add_argument(
        "--bootstrap-wiki",
        choices=["listadomanga", "manga-sanctuary"],
        help="En lugar de scrapear las fuentes del YAML, importa items de una wiki comunitaria (Fase 2 del PRD). Soporta: listadomanga (España), manga-sanctuary (Francia).",
    )
    parser.add_argument(
        "--wiki-from",
        default="2024-01",
        help="Mes inicial para --bootstrap-wiki (formato YYYY-MM). Default: 2024-01",
    )
    parser.add_argument(
        "--wiki-to",
        default="",
        help="Mes final para --bootstrap-wiki (YYYY-MM). Default: mes actual.",
    )
    parser.add_argument(
        "--discover-sitemaps",
        action="store_true",
        help="Fase 3: descubre URLs de producto vía /sitemap.xml de cada source HTML. Procesa cada URL con detail-fetch para extraer Schema.org metadata. Itera por todas las sources canónicas html.",
    )
    parser.add_argument(
        "--sitemap-max-urls",
        type=int,
        default=500,
        help="Máximo de URLs a procesar por source con --discover-sitemaps. Default: 500.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
