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
import threading
import time
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    {"phrase": "slipcase edition", "score": 40, "type": "box_set"},
    {"phrase": "omnibus", "score": 30, "type": "omnibus"},
    {"phrase": "compendium", "score": 30, "type": "omnibus"},
    {"phrase": "library edition", "score": 38, "type": "premium_format"},
    {"phrase": "ultimate edition", "score": 38, "type": "premium_format"},
    {"phrase": "definitive edition", "score": 38, "type": "premium_format"},
    {"phrase": "absolute edition", "score": 40, "type": "premium_format"},
    {"phrase": "launch bundle", "score": 30, "type": "bundle"},
    {"phrase": "special bundle", "score": 30, "type": "bundle"},
    {"phrase": "variant cover", "score": 40, "type": "variant_cover"},
    {"phrase": "exclusive cover", "score": 40, "type": "variant_cover"},
    # "variant" suelto (loanword usado en EN/IT/FR/ES retail manga): en
    # contexto manga, "Variant" sin "Cover" casi siempre significa variant
    # cover (ej. "One Piece 108 Variant Metal", "Demon Slayer 23 Variant
    # Limited Francese", "Hunter X Hunter 37 Variant"). Score moderado (30)
    # para no dominar el ranking; suficiente para que pase
    # is_collectible_edition vía COLLECTIBLE_EDITION_SIGNAL_TYPES.
    # Word-boundary evita falsos positivos sobre "covariant" / "invariant" /
    # "variante" (italiano "variante" lleva una vocal extra al final).
    {"phrase": "variant", "score": 30, "type": "variant_cover"},
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
    # purity: "manga_only" → catálogo cerrado (Norma, Ivrea, ListadoManga…).
    # Confiamos en el rescate por pack-extras (manga + figura de regalo, etc.).
    # purity: "mixed" → catálogo mixto (Dark Horse Direct, Amazon, retailers
    # genéricos). Solo se acepta el ítem si hay un STRONG manga hint en
    # título/descripción — no basta con "Collector's Edition".
    # Default "manga_only" para no romper el comportamiento histórico.
    purity: str = "manga_only"


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
    # image_local: filename del espejo local en data/images/ (Image storage
    # Fase 1). Vacío hasta que mirror_candidate_images lo descarga. image_url
    # queda como provenance + fallback. Ver "Image storage" en CLAUDE.md.
    image_local: str = ""
    # images: carrusel de imágenes asociadas al item (Fase 2 del parser
    # listadomanga-collections — schema aditivo). Cada elemento es
    # {url, local, kind, description} donde kind ∈ {cover, extra,
    # variant_cover, back_cover, gallery}. El primero (kind=cover) es la
    # portada principal y mantiene sincronía con image_url / image_local
    # como aliases (no breaking para consumidores existentes). Cuando hay
    # más de un elemento el dashboard renderiza un carrusel; si está vacío,
    # el frontend cae al image_url/image_local single.
    images: list[dict[str, str]] = field(default_factory=list)
    # extras: descripciones de items extra vinculados a este tomo
    # (Fase 2 — Layout B parser). Cada elemento es {description,
    # release_date, source_section} donde source_section ∈ {cofre, regalo,
    # extra}. Permite renderizar lista "Incluye: marcapáginas, postales..."
    # en el modal sin embeber todo en description.
    extras: list[dict[str, str]] = field(default_factory=list)
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
    # ES: badge de estado "Pre venta / Preventa" que aparece como título
    # cuando un selector Magento captura el badge en vez del nombre real.
    re.compile(r"^Pre[\s\-]?venta\s+", re.IGNORECASE),
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
    # FR Meian: el botón "En savoir plus" (≈ "Read more") se infiltraba en el
    # título cuando el selector capturaba un wrapper sin separarlo del CTA.
    re.compile(r"^En\s+savoir\s+plus\s+", re.IGNORECASE),
    # EN equivalentes (por si alguna fuente shopify/squarespace los devuelve).
    re.compile(r"^(?:Read|Learn|Find\s+out)\s+more\s+(?:about\s+)?", re.IGNORECASE),
    # Panini ES Magento — el card de search-result empieza con "Añadir a la
    # Lista de Deseos" (botón wishlist) cuando el selector toma el wrapper
    # completo. Strippear el prefijo entero.
    re.compile(r"^A[ñn]adir\s+a\s+la\s+Lista\s+de\s+Deseos\s+", re.IGNORECASE),
    # Pipoca & Nanquim (BR Magento) — botón "Lista de desejos" prefijo equivalente
    # al de Panini ES. También cubre "Adicionar à Lista" genérico de Magento BR.
    re.compile(r"^Lista\s+de\s+desejos\s+", re.IGNORECASE),
    re.compile(r"^Adicionar\s+(?:à|a)\s+lista(?:\s+de\s+desejos)?\s+", re.IGNORECASE),
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
    # Funside.it y similares italianos: botones "Aggiungi al carrello Confrontare"
    # capturados como PREFIX del título por el listing extractor genérico.
    re.compile(r"^Aggiungi\s+al\s+carrello\s+Confrontare\s+", re.IGNORECASE),
    re.compile(r"^Confrontare\s+", re.IGNORECASE),
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
    # Panini ES Magento search-result: cola completa tras el título real.
    # Formato: "<title> (Cómic|Manga) DD/MM/YY Regular Price X € -5% Special
    # Price Y € (Pre-venta|No está disponible|...)"
    re.compile(
        r"\s+(?:C[óo]mic|Manga)\s+\d{1,2}/\d{1,2}/\d{2,4}\s+Regular\s+Price\b.*$",
        re.IGNORECASE,
    ),
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
      3) Strip de markers de volumen HUÉRFANOS (sin número adyacente).
         Ej. "Ataque a los Titanes nº Collector's Edition" → "Ataque a los
         Titanes Collector's Edition". Sin esto, el LLM del skill
         `/standardize-catalog` ve "nº" suelto y lo interpreta como parte
         del nombre (lo deja como "no" residual en title y series_key —
         gotcha #29).
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
        # Strip de markers de volumen huérfanos (sin número adyacente):
        # `nº`, `n°`, `n.`, `vol.`, `vol`, `tomo`, `tome` que NO van seguidos
        # de un dígito (con o sin espacio). Conservamos los que sí tienen
        # número porque ahí denotan volumen legítimo ("Vol. 5", "nº 12").
        cleaned = _ORPHAN_VOL_MARKER_RE.sub(" ", cleaned)
        # Collapse whitespace tras posibles strips
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned == prev:
            break
    return cleaned


# Markers de volumen "huérfanos" — `nº` / `n°` / `vol.` que NO van seguidos
# de un número (con punto / espacio / nada entremedio). Solo strippear los
# markers que SIEMPRE son markers (no palabras del nombre):
# - `nº`, `n°`: nunca son palabras legítimas del título
# - `vol`/`vol.`: idem
# Excluimos `tomo`/`tome` porque pueden ser palabras legítimas del title
# ("¡ÚLTIMO TOMO!" en Norma Editorial).
# El `\.?` dentro del lookahead permite matchear "Vol. 1" (con punto +
# espacio + dígito) y NO strippearlo. Match típico que SÍ queremos:
# "Ataque a los Titanes nº Collector's Edition" → "nº" suelto → strip.
_ORPHAN_VOL_MARKER_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:n[º°]|vol)\.?(?!\.?\s*\d)(?![A-Za-z0-9])",
    re.IGNORECASE | re.UNICODE,
)


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
    # Rakuten — `l-id=search-c-item-img-NN` identifica el slot del listing
    # de búsqueda, no el producto. Sin este params, 5 búsquedas distintas
    # generaban 5 items duplicados del mismo /rb/<id>/ (bug detectado 2026-05-22).
    "l-id", "l_id",
    # Amazon — `tag` es el affiliate id (ya cubierto arriba); los otros son
    # tracking adicional de Amazon que aparece en URLs SocialAnime y otros
    # affiliates. `linkCode` (tipo de enlace), `th` (variant select), `psc`
    # (product select context), `ascsubtag`/`smid` (sub-affiliate / seller),
    # `pf_rd_*`/`pd_rd_*` (tracking interno de surfaces). Sin esto, dos URLs
    # del mismo ASIN con afiliados distintos generan rows duplicadas.
    "linkCode", "th", "psc", "ascsubtag", "smid",
    "pf_rd_p", "pf_rd_r", "pf_rd_s", "pf_rd_t", "pf_rd_i",
    "pd_rd_w", "pd_rd_r", "pd_rd_wg", "pd_rd_i",
    "content-id", "content_id",
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

    # 2.5. Amazon: el path puede llevar un segmento `/ref=...` de tracking
    # (`/dp/ASIN/ref=cm_sw_r_...`, `/gp/product/ASIN/ref=...`). Es un token
    # opaco que cambia por sesión/widget y rompe la igualdad de URL. Lo
    # quitamos para que normalizen al canónico `/dp/<ASIN>` o
    # `/gp/product/<ASIN>`. Aplica a cualquier amazon.<tld>.
    if "amazon." in parsed.netloc.lower():
        path = re.sub(r"/ref=[^/]+(?=/|$)", "", path)

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


def _phrase_has_letter_boundary_chars(phrase: str) -> bool:
    """¿La phrase contiene letras/dígitos ASCII donde un boundary aplica?"""
    return bool(re.search(r"[a-z0-9]", phrase, re.IGNORECASE))


def _build_phrase_pattern(normalized_phrase: str) -> re.Pattern[str]:
    """Construye un regex con word-boundary para frases con letras ASCII.

    Para frases con sólo caracteres CJK (japonés/coreano/chino) o sólo
    símbolos, no se aplica boundary porque \\b no funciona ahí — se usa
    substring directo.
    """
    if _phrase_has_letter_boundary_chars(normalized_phrase):
        # Word-boundary basado en caracteres alfanuméricos. Acentos y
        # caracteres especiales internos a la phrase se permiten porque
        # ya pasaron por normalize_text. \b solo funciona entre [a-z0-9_]
        # y otro carácter; para caracteres acentuados usamos lookarounds.
        return re.compile(
            rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])"
        )
    # CJK / símbolos puros: substring directo (sin boundary).
    return re.compile(re.escape(normalized_phrase))


# Cache de patrones compilados por phrase para no re-compilar en cada item.
_PHRASE_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def _phrase_pattern(normalized_phrase: str) -> re.Pattern[str]:
    pat = _PHRASE_PATTERN_CACHE.get(normalized_phrase)
    if pat is None:
        pat = _build_phrase_pattern(normalized_phrase)
        _PHRASE_PATTERN_CACHE[normalized_phrase] = pat
    return pat


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

        if normalized_phrase and _phrase_pattern(normalized_phrase).search(normalized):
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
    # Placeholders genéricos detectados en distintos retailers
    "/placeholders/", "/placeholder/", "placeholder_",
    "visuel_defaut",                        # Manga-Sanctuary
    "kodansha--placeholder",                # Kodansha USA
    "panini-placeholder",                   # Panini MX
    "productno_selection",                  # Panini IT cuando no hay foto
    "no_image", "no-image", "noimage", "no_photo",
    "coming_soon", "coming-soon", "comingsoon",
    "image_not_available", "image-not-available",
    "default_book", "default-book",
    "logo-glenat",                          # Glénat (logo se cuela como imagen)
    # Assets de tema / íconos de UI servidos como <img> (no son portadas).
    # Sanyodo (WP theme): icn_close.svg, "menu open"/"menu close", etc.
    # viven en /wp-content/themes/<x>/assets/images/common/.
    "/assets/images/common/",
    ".svg",                                 # un SVG nunca es portada de manga
    # Data URIs de 1x1 transparente (típico lazy-loading: la imagen real
    # vive en data-src o data-original, el src es solo placeholder).
    "data:image/gif;base64,r0lgodlh",
    "data:image/png;base64,ivborw0kggo",    # 1x1 PNG transparente común
)

IMAGE_URL_GOOD_PATTERNS = (
    "/goods/", "/products/", "/product/", "/cover", "/jacket",
    "/manga/", "/manga_", "/book", "/item",
    "e-hon.ne.jp",   # CDN de portadas de e-hon (Sanyodo linkea sus covers acá)
)


def _img_to_url(img: Any, source_url: str) -> str:
    """Extrae URL absoluta de un <img> probando src/data-src/srcset/etc.

    Saltea valores `data:` URI: en imágenes lazy-loaded el `src` suele ser
    un placeholder data-URI (1x1 transparente, o un SVG inline) mientras la
    portada real vive en data-src / data-lazy-src. Como `src` se prueba
    primero, sin este skip devolveríamos el placeholder data-URI — que no es
    descargable y rompe el espejo local de portadas.
    """
    for attr in ("src", "data-src", "data-original", "data-lazy-src", "srcset", "data-srcset"):
        val = img.get(attr)
        if not val:
            continue
        if "srcset" in attr:
            val = val.split(",")[0].strip().split(" ")[0]
        val = val.strip()
        if val.lower().startswith("data:"):
            continue
        url = canonicalize_url(source_url, val)
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


def _is_placeholder_image(url: str) -> bool:
    """Devuelve True si la URL parece un placeholder genérico de retailer
    (no es la portada real del producto). Centralizamos el check para que
    tanto el detail extractor como el listing extractor lo usen.
    """
    if not url:
        return True
    lower = url.lower()
    if any(p in lower for p in IMAGE_URL_BAD_PATTERNS):
        return True
    # URL truncada/sin nombre de archivo: termina en "/" o solo tiene
    # carpetas (caso visto: https://manga-sanctuary.com/img/o/).
    # Excepción: URLs sin extensión válidas como CDN modernos sin ext sí
    # se aceptan, pero deben tener algo después de la última /.
    if lower.rstrip("?#").endswith("/"):
        return True
    return False


def _extract_image_from_detail_soup(soup: BeautifulSoup, source_url: str) -> str:
    """Extrae URL de portada de una página de detalle, varias estrategias.

    1) JSON-LD schema.org `image` field
    2) OpenGraph `og:image` / Twitter `twitter:image`
    3) meta itemprop="image"
    4) <img> con clases típicas de portada (cover, product-image, etc.)
    5) Ranking general de <img> tags del body (mismo scoring que el listing).

    Filtra placeholders conocidos via _is_placeholder_image — algunos sites
    devuelven cover.png / placeholder.jpg en og:image cuando el producto
    no tiene foto cargada, y queremos devolver "" en ese caso para que el
    item pueda ser re-fetcheado más tarde.
    """
    def _accept(url: str) -> str:
        """Devuelve url si no es placeholder; "" si lo es."""
        return "" if _is_placeholder_image(url) else url

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
                url = _accept(canonicalize_url(source_url, value.strip()))
                if url:
                    return url
            if isinstance(value, dict):
                v = (value.get("url") or value.get("@id") or "").strip()
                if v:
                    url = _accept(canonicalize_url(source_url, v))
                    if url:
                        return url
            if isinstance(value, list) and value:
                for v in value:
                    if isinstance(v, str) and v.strip():
                        url = _accept(canonicalize_url(source_url, v.strip()))
                        if url:
                            return url
                    if isinstance(v, dict):
                        s = (v.get("url") or v.get("@id") or "").strip()
                        if s:
                            url = _accept(canonicalize_url(source_url, s))
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
            url = _accept(canonicalize_url(source_url, meta["content"].strip()))
            if url:
                return url

    # 3) meta itemprop="image"
    meta = soup.find("meta", attrs={"itemprop": "image"})
    if meta and meta.get("content"):
        url = _accept(canonicalize_url(source_url, meta["content"].strip()))
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

    # === Name fallback: OG title → <title> ===
    # JSON-LD muchas veces no trae 'name'. og:title es estándar (lo expone
    # Whakoom, retailers Shopify/Magento, etc.) y es el title real de la
    # página tal como aparece en buscadores.
    if not result["name"]:
        for attrs in (
            {"property": "og:title"},
            {"name": "twitter:title"},
            {"property": "twitter:title"},
        ):
            meta = soup.find("meta", attrs=attrs)
            if meta and meta.get("content"):
                value = clean_text(meta["content"])
                if value:
                    result["name"] = value
                    break
        if not result["name"] and soup.title and soup.title.string:
            result["name"] = clean_text(soup.title.string)

    # === Description fallback: OG description ===
    if not result["description"]:
        for attrs in (
            {"property": "og:description"},
            {"name": "description"},
            {"name": "twitter:description"},
        ):
            meta = soup.find("meta", attrs=attrs)
            if meta and meta.get("content"):
                value = clean_text(meta["content"])
                if value:
                    result["description"] = value
                    break

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
    re.compile(r"\b[Nn][º°o\.]\s*\d+\b"),     # "nº 12", "n° 5", "N.1"
    re.compile(r"#\d+\b"),                # "#22"
    re.compile(r"(?:\d+[\s\-]?en[\s\-]?1|3 en 1|integral)", re.IGNORECASE),
    # Formatos físicos de libro/cómic coleccionable: Dark Horse Direct y
    # otros retailers mixtos publican muchos manga + comic deluxe. Estos
    # formatos confirman que el producto es un LIBRO, no figura/print/bookend.
    re.compile(r"\b(?:Deluxe\s+(?:Hardcover|Edition|Volume)|Library\s+Edition|Hardcover\s+Volumes?|Omnibus|Compendium|Slipcase\s+Edition)\b", re.IGNORECASE),
    # Boxsets/cofanettos/coffrets: formato de libro coleccionable.
    re.compile(r"\b(?:Box\s*Set|Boxset|Cofanetto|Coffret\s+Collector|Slipcase\s+Set|Box\s+Edition)\b", re.IGNORECASE),
    # Frame Art / Frame Book: libros de arte de manga (Tian Guan Ci Fu, etc.)
    re.compile(r"\bFrame\s+(?:Art|Book)\b", re.IGNORECASE),
    re.compile(r"\bThe\s+Art\s+of\b", re.IGNORECASE),  # artbooks "The Art of X"
    # Variantes en otras lenguas: ES "El arte de", FR "L'art de", IT "L'arte di".
    # "El arte de Berserk", "L'art de Studio Ghibli", etc. son artbooks legítimos.
    re.compile(r"\bEl\s+arte\s+de\b", re.IGNORECASE),
    re.compile(r"\bL['’]?art\s+de\b", re.IGNORECASE),
    re.compile(r"\bL['’]?arte\s+di\b", re.IGNORECASE),
    re.compile(r"\b(?:Encyclopedia|Visual\s+Companion|Visual\s+Guide)\b", re.IGNORECASE),
    # Términos japoneses inequívocos de manga/libro
    re.compile(r"巻|コミック|漫画|単行本|愛蔵版|完全版|文庫|新書|画集|設定資料集"),
    # "<Word> Edition / Edizione / Édition / Edición" con palabra-lore.
    # Captura "Berserk Tarot Edition", "OP Celebration Edition", "Vinland
    # Saga Tribute Edition", etc. — productos que claramente son manga +
    # edición especial pero cuyo título NO contiene vol/tomo/n°.
    # Stoplist evita "First Edition", "Spanish Edition", etc. (genéricos).
    # IGNORECASE necesario para catálogos italianos (Star Comics) que usan
    # TODO MAYÚSCULAS: "NO GUNS LIFE n. 1 VARIANT EDITION".
    re.compile(
        r"\b(?!(?:The|This|That|First|Second|Third|Fourth|Fifth|Next|Last|"
        r"Latest|New|Old|Same|Other|Another|Each|Every|Any|All|Some|Whole|"
        r"Print|Digital|Paperback|Hardcover|Spanish|English|French|Italian|"
        r"Japanese|German|US|UK|EU|Standard|Regular|Original|Final)\b)"
        r"[A-Za-z][\w\-]{2,}\s+"
        r"(?:Edition|Edizione|Édition|Edición|Edicion)\b",
        re.IGNORECASE,
    ),
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

# URLs de blogs editoriales — NUNCA son productos individuales. Aplica
# como descarte temprano en is_likely_manga(). La mayoría son posts de
# anuncios/news con texto libre que escapa a patrones de título.
_BLOG_URL_PATTERNS = re.compile(
    r"listadomanga\.es/blog/"
    r"|kodansha\.us/\d{4}/"           # kodansha.us/2025/05/13/...
    r"|viz\.com/blog/"
    r"|manga-news\.com/index\.php/actus/"
    r"|bsky\.app/profile/"            # Bluesky posts (vía SOCIAL sources)
    r"|/news/\d{4}/"                  # genérico: /news/YYYY/
    r"|/notice/\d+"                   # genérico: /notice/123
    , re.IGNORECASE,
)


# NON-MANGA tier HARD: productos que SIEMPRE son productos completos, jamás
# extras dentro de una edición especial de manga. Match aquí → descarte
# inmediato, sin pasar por rescue de strong-manga (esto es importante para
# casos como "<título japonés> Blu-ray BOX 下巻" donde "巻" matchearía como
# strong-manga pero el ítem real es Blu-ray).
_NON_MANGA_HARD: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:DVD|blu-?ray)(?:\s*(?:BOX|SET|EDITION|DISC)|\b)", re.IGNORECASE),
    re.compile(r"\bvinyl\s*figure\b", re.IGNORECASE),
    re.compile(r"\bPVC\s*(?:figure|statue|painted)\b", re.IGNORECASE),
    re.compile(r"\bpainted\s+statue\b", re.IGNORECASE),
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
    # Prints decorativos, bookends, standees (Dark Horse Direct los mezcla
    # con manga en el catálogo). Son productos completos, nunca extras.
    re.compile(r"\bfine\s+art\s+print\b", re.IGNORECASE),
    re.compile(r"\bart\s+print\b(?!\s+(?:edition|collection))", re.IGNORECASE),
    re.compile(r"\bbookends?\b", re.IGNORECASE),
    re.compile(r"\bstandees?\b", re.IGNORECASE),
    re.compile(r"\bcomic\s+cover\s+(?:art\s+)?print\b", re.IGNORECASE),
    re.compile(r"\bpaperweight\b", re.IGNORECASE),
    re.compile(r"\b(?:enamel\s+)?pin\s+set\b", re.IGNORECASE),
    # Bundles de cómics (no manga) — Dark Horse pack de variantes Alien/Conan/etc.
    re.compile(r"\b(?:Exclusive\s+)?Variant\s+Bundle\b", re.IGNORECASE),
    # Trading cards / cromos / coleccionables Panini (no manga, deporte/marca).
    re.compile(r"\bTrading\s+Cards?\b", re.IGNORECASE),
    re.compile(r"\b(?:Caja|Cajita)\s+Con\s+\d+\s+Sobres?\b", re.IGNORECASE),
    re.compile(r"\bBl[íi]ster\s+\d+\s+Sobres?\b", re.IGNORECASE),
    re.compile(r"\b[ÁA]lbum\s+(?:Pasta|tapa)\s+(?:Dura|Suave)\b", re.IGNORECASE),
    re.compile(r"\bMegapack\b|\bPocket\s+tin\b", re.IGNORECASE),
    re.compile(r"\bPack\s+Album\b", re.IGNORECASE),
    re.compile(r"\bTreasure\s+Box\s+de\s+Panini\b", re.IGNORECASE),
    re.compile(r"\bCromos?\b(?!\s+de\s+manga)", re.IGNORECASE),
    # Colecciones marca/franquicia no-manga (Panini México)
    re.compile(r"\bColecci[óo]n\s+(?:Hot\s+Wheels|Marvel\s+Cromos|Dragon\s+Ball\s+Super\s+Ultimate|Lady\s+Bug|Panini\s+FIFA|UEFA|Sticker\s+Album|de\s+cards?)\b", re.IGNORECASE),
    # Deportes / cromos de fútbol
    re.compile(r"\b(?:LIGA\s+ESTE|WORLD\s+CUP|FIFA(?:\s+\d|\s+Club|\s+\d{4})|UEFA|Champions\s+League|Eurocopa|Copa\s+America|JUG[ÓO]N\s+EUROCOPA)\b", re.IGNORECASE),
    # Joyería / accesorios / textiles
    re.compile(r"\b(?:Necklace|Medallion\s+Necklace|Pendant|Earring|Bracelet|Corbata|Pin\s+Set)\b", re.IGNORECASE),
    # Convenciones y "convention exclusives" como listado
    re.compile(r"\bConvention\s+Exclusives?\s*$", re.IGNORECASE),
    re.compile(r"\b(?:San\s+Diego\s+Comic\s+Con|SDCC|Comic\s+Con\s+\d{4})\s*[:\-]", re.IGNORECASE),
    # Packs Panini México "Paquete Especial" (cromos/coleccionables)
    re.compile(r"\bPaquete\s+Especial\b", re.IGNORECASE),
    # Estampas/álbumes faltantes (cromos Panini)
    re.compile(r"\bEstampas?\s+Faltantes?\b", re.IGNORECASE),
    re.compile(r"\bCONMEBOL\b", re.IGNORECASE),
    re.compile(r"\bLibertadores\b", re.IGNORECASE),
    # Items "basura" de menú de navegación (Glénat search trae /bd/,
    # /notre-histoire/, "rss"… como si fueran productos):
    re.compile(r"^BD\s+arrow_forward\s*$", re.IGNORECASE),
    re.compile(r"^arrow_(forward|back|down|up)\b", re.IGNORECASE),
    re.compile(r"^D[ée]couvrir\s+l'histoire\b", re.IGNORECASE),
    re.compile(r"^rss\s*$", re.IGNORECASE),
    # Podcast episodes (ES Norma)
    re.compile(r"^Episodio\s+\d+\s*[|—–\-]", re.IGNORECASE),
    re.compile(r"^Episode\s+\d+\s*[|—–\-]", re.IGNORECASE),
    # Titulares de noticias/anuncios (no productos): vienen antes que STRONG
    # porque pueden contener la palabra "manga" en titular pero no son items.
    # "Kodansha Reveals Fall 2025 New Print Manga Licenses..."
    # "One Piece Gives Luffy a Truly Godlike Birthday Tribute"
    re.compile(r"\b(?:Reveals?|Announces?|Unveils?)\s+(?:New\s+|Fall\s+|Spring\s+|Summer\s+|Winter\s+)?\w", re.IGNORECASE),
    re.compile(r"\b(?:Birthday|Anniversary)\s+Tribute\b", re.IGNORECASE),
    re.compile(r"\bAnime\s+Film\s+Reveal\b", re.IGNORECASE),
    re.compile(r"\bNew\s+(?:Print\s+)?(?:Manga\s+)?Licenses?\b", re.IGNORECASE),
    re.compile(r"\bAnnouncements?\s*\(?\d{4}\)?\s*$", re.IGNORECASE),
    re.compile(r"\bGives\s+\w+\s+a\s+", re.IGNORECASE),  # "Gives Luffy a Tribute"
    # Concursos / sweepstakes (Kodansha USA, Yen Press, etc.)
    re.compile(r"\bContest\s*[:\-]?\s*Win\s+", re.IGNORECASE),
    re.compile(r"\bSweepstakes?\b", re.IGNORECASE),
    re.compile(r"\bGiveaway\b", re.IGNORECASE),
    # "Preorder: <X> with exclusive items!" — formato de blog post de anuncio.
    re.compile(r"^Pre-?order\s*[:\-]\s*", re.IGNORECASE),
    # DC/Marvel facsímil (cómic, no manga)
    re.compile(r"\b(?:DC|Marvel)\s+Edici[óo]n\s+Facs[íi]mil\b", re.IGNORECASE),
    # JP: enciclopedias 図鑑 (Gakken animal/insect guides), revistas (X月号),
    # idol boxes (プレミアムBOX), bonus prefix sin contenido manga.
    re.compile(r"図鑑"),
    re.compile(r"\d+月号"),                  # "7月号" = revista mensual
    re.compile(r"プレミアムBOX"),
    re.compile(r"学研の図鑑"),
    re.compile(r"ブルーレイ|DVD\s*BOX"),
    # フィギュア (figure) sola es producto, NO matchear cuando viene seguida de
    # 付/同梱/付録 (with/included) — eso indica "manga con figura como extra"
    # (típico de ediciones especiales tipo "Ai Yori Aoshi 14 フィギュア付初回限定版").
    re.compile(r"フィギュア(?!付|同梱|付録)"),
    # --- Blog posts / news / listados editoriales -------------------------
    # Listadomanga blog histórico es ~100% noticias. Estos patrones también
    # capturan ruido similar de RSS feeds y resultados de search engines.
    # "Novedades de Norma Editorial para el 7 de Junio de 2024"
    re.compile(r"^Novedad(?:es)?\s+de\s+\w", re.IGNORECASE),
    # "Presentación de Panini Manga en el 31 Manga Barcelona"
    re.compile(r"^Presentaci[óo]n\s+de\s+\w", re.IGNORECASE),
    # "Norma Editorial licencia el artbook X", "Panini Manga licencia Y"
    re.compile(r"\b(?:Editorial|Comics?|Manga|Ediciones|Books)\s+licencia(?:n)?\s+\w", re.IGNORECASE),
    # "Panini Manga desvela los detalles...", "X reedita Y", "X recupera Y"
    re.compile(r"\b(?:desvela|reedita|recupera|relanza)\s+(?:los\s+|el\s+|la\s+|las\s+|todos\s+|el\s+catálogo|nuevas\s+)?\w", re.IGNORECASE),
    # "Norma Editorial anuncia 12 nuevas licencias"
    re.compile(r"\banuncia\s+(?:\d+\s+)?(?:nuevas?\s+)?licencias?\b", re.IGNORECASE),
    # "Norma Editorial confirma Sailor Moon Eternal Edition para Diciembre"
    re.compile(r"^[\w\s]+(?:Editorial|Comics?|Manga|Ediciones)\s+confirma\s+\w", re.IGNORECASE),
    # "X autor/a invitado/a", "X invitado/a virtual del Manga Barcelona"
    re.compile(r"\b(?:autor[ae]?s?\s+invitad[ao]s?|invitad[ao]s?\s+virtual(?:es)?)\b", re.IGNORECASE),
    # "Grupo Anaya empezará a publicar manga como Pika Ediciones"
    re.compile(r"\bempezar[áa]\s+a\s+publicar\b", re.IGNORECASE),
    # Crowdfunding announcements (Verkami, Kickstarter, etc.)
    re.compile(r"\b(?:crowdfunding|verkami|kickstarter|indiegogo)\b", re.IGNORECASE),
    # Salones del manga / convenciones — siempre son blog posts del salón.
    re.compile(r"\b(?:Manga\s+Barcelona|Japan\s+Weekend|Comic\s+Barcelona|Sal[óo]n\s+del\s+Manga|Manga\s+Madrid)\b", re.IGNORECASE),
    # "Especial XVIII Salón del Manga (2) - Novedades editoriales"
    re.compile(r"\bEspecial\s+(?:XVI{1,3}I?|\d+)[\s\w]*Sal[óo]n\b", re.IGNORECASE),
    # Posts/news EN markers
    re.compile(r"^FULLY\s+REVEALED\s+POST\b", re.IGNORECASE),
    re.compile(r"\bDebut\s+Revealed!?\b", re.IGNORECASE),
    re.compile(r"\bnovel\s+debuts?!", re.IGNORECASE),
    # Bluesky / Twitter prosa típica de stand de convención
    re.compile(r"\bpistoletazo\s+de\s+salida\b", re.IGNORECASE),
    # Manga-News (FR) headlines: "Un coffret collector pour le lancement du manga X"
    re.compile(r"^Un\s+coffret\s+collector\s+pour\s+le\s+lancement\b", re.IGNORECASE),
    # VIZ blog: "X Final Volume Collector's Guide"
    re.compile(r"\bFinal\s+Volume\s+Collector'?s\s+Guide\b", re.IGNORECASE),
    # --- Artbooks / guías de videojuegos (no manga) -----------------------
    # Square Enix guidebooks (Final Fantasy, Dragon Quest, Kingdom Hearts).
    re.compile(r"\bUltimania\b", re.IGNORECASE),
    # "El arte de <videojuego>", "Arte de Super Mario Odyssey"
    re.compile(
        r"\b(?:El\s+)?[Aa]rte\s+de\s+(?:Splatoon|Fire\s+Emblem|Super\s+Mario|Mario\s+Odyssey|Pok[ée]mon|Genshin|Persona\s+\d|Elden\s+Ring|Cyberpunk|Hyrule|Zelda)\b",
        re.IGNORECASE,
    ),
    # "The Art of <videojuego puro>" — franquicias sin adaptación manga conocida.
    # NOTA: la mayoría se manejan via comics_blacklist.yml (que se evalúa antes
    # que HARD). Aquí cubrimos sólo lo que necesita estar en HARD.
    re.compile(
        r"\bThe\s+Art\s+of\s+(?:Splatoon|Fire\s+Emblem|Super\s+Mario|Pok[ée]mon|Genshin|Persona\s+\d|Elden\s+Ring|Cyberpunk|Death\s+Stranding|Sekiro|Bloodborne)\b",
        re.IGNORECASE,
    ),
    # "The Making of <franquicia gaming>" — making-of de videojuegos.
    re.compile(r"\bThe\s+Making\s+of\s+\w", re.IGNORECASE),
    # Enciclopedias/guías de juegos de Nintendo / Square Enix
    re.compile(r"\bHyrule\s+Historia\b", re.IGNORECASE),
    re.compile(r"\b(?:Legend\s+of\s+)?Zelda\s*[:\-]?\s*Encyclop[ée]di?a\b", re.IGNORECASE),
    re.compile(r"\b(?:Legend\s+of\s+)?Zelda\s*[:\-]?\s*Enciclopedia\b", re.IGNORECASE),
    re.compile(r"\bBreath\s+of\s+the\s+Wild.{1,40}Creating\s+a\s+(?:Hero|Champion)\b", re.IGNORECASE),
    re.compile(r"\bFinal\s+Fantasy\s*[-:]?\s*Encyclop[ée]die\b", re.IGNORECASE),
    re.compile(r"\bLa\s+historia\s+de\s+Final\s+Fantasy\b", re.IGNORECASE),
    re.compile(r"\bDragon\s+Quest\s+\d+\s+Aniversario.{0,30}Enciclopedia\b", re.IGNORECASE),
    # "Hommage à Kingdom Hearts", "Génération Zelda - 35 ans"
    re.compile(
        r"\b(?:Hommage\s+à|G[ée]n[ée]ration)\s+(?:Kingdom\s+Hearts|Final\s+Fantasy|Zelda|Pok[ée]mon|Mario)\b",
        re.IGNORECASE,
    ),
    # --- Pokémon: ensayos / biografía / magazine (no manga) ---------------
    re.compile(r"\bPok[ée]mon\s+y\s+(?:Feminismo|Filosof[íi]a|Ciencia)\b", re.IGNORECASE),
    re.compile(r"\bBiograf[íi]a\s+Oficial\s+de\s+Satoshi\s+Tajiri\b", re.IGNORECASE),
    re.compile(r"^Revista\s+Pok[ée]mon\b", re.IGNORECASE),
    # --- Cyberpunk 2077 (Tarot Deck) y otros tarot+guidebook decks --------
    re.compile(r"\bCyberpunk\s+\d+:\s+Tarot\s+Deck\s+(?:&|and)\s+Guidebook\b", re.IGNORECASE),
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


# --- Comics blacklist (cargada desde data/comics_blacklist.yml) ------------
#
# Sólo se aplica a fuentes con purity="mixed" (Panini ES/MX, Dark Horse
# Direct, etc.). Fuentes 100% manga (Norma, Ivrea, Glénat manga…) lo
# ignoran — series como "Sakamoto Days" no pueden matchear nada de aquí.

_COMICS_BLACKLIST: dict[str, Any] | None = None  # lazy load
_COMICS_PUBLISHERS: frozenset[str] = frozenset()
_COMICS_FRANCHISE_PATTERN: re.Pattern[str] | None = None
_COMICS_FORMAT_PATTERN: re.Pattern[str] | None = None


def _load_comics_blacklist() -> dict[str, Any]:
    """Lee data/comics_blacklist.yml; resultado se cachea en globals."""
    global _COMICS_BLACKLIST, _COMICS_PUBLISHERS, _COMICS_FRANCHISE_PATTERN, _COMICS_FORMAT_PATTERN
    if _COMICS_BLACKLIST is not None:
        return _COMICS_BLACKLIST
    path = Path("data/comics_blacklist.yml")
    if not path.exists():
        _COMICS_BLACKLIST = {"publishers": [], "franchise_keywords": [], "format_keywords": []}
        return _COMICS_BLACKLIST
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        data = {}
    _COMICS_BLACKLIST = {
        "publishers": data.get("publishers") or [],
        "franchise_keywords": data.get("franchise_keywords") or [],
        "format_keywords": data.get("format_keywords") or [],
    }
    _COMICS_PUBLISHERS = frozenset(p.strip() for p in _COMICS_BLACKLIST["publishers"] if p)
    fr_kw = [re.escape(k) for k in _COMICS_BLACKLIST["franchise_keywords"] if k]
    if fr_kw:
        # Word boundaries lookahead/lookbehind para evitar substring match.
        # Ejemplo: "Batman" NO debe matchear "Batmanga" (manga real de Jiro
        # Kuwata sobre Batman). Para multi-word ("Conan the Barbarian") los
        # boundaries siguen funcionando porque los espacios ya separan.
        _COMICS_FRANCHISE_PATTERN = re.compile(
            r"(?<![\w])(?:" + "|".join(fr_kw) + r")(?![\w])",
            re.IGNORECASE,
        )
    fmt_kw = [re.escape(k) for k in _COMICS_BLACKLIST["format_keywords"] if k]
    if fmt_kw:
        _COMICS_FORMAT_PATTERN = re.compile(
            r"\b(?:" + "|".join(fmt_kw) + r")\b",
            re.IGNORECASE,
        )
    return _COMICS_BLACKLIST


def is_comic_not_manga(title: str, publisher: str) -> tuple[bool, str]:
    """Detecta si un item es claramente un cómic (no manga).

    Returns:
        (is_comic, reason)
    """
    _load_comics_blacklist()
    # Bypass: si el title menciona "manga" como substring (case-insensitive),
    # asumimos que ES manga aunque hable de un franchise occidental. Esto
    # cubre crossovers legítimos tipo:
    #   - "Batman: Il Batmanga di Jiro Kuwata" (manga japonés sobre Batman)
    #   - "Marvel Mangaverse" (manga oficial de Marvel)
    #   - "Star Wars Manga" (adaptación manga de SW)
    # En esos casos, la palabra "manga"/"mangaverse"/"batmanga" gana sobre
    # la franchise rule.
    if title and re.search(r"manga", title, re.IGNORECASE):
        return False, ""
    if publisher and publisher.strip() in _COMICS_PUBLISHERS:
        return True, f"comic_publisher:{publisher.strip()}"
    if title and _COMICS_FRANCHISE_PATTERN and _COMICS_FRANCHISE_PATTERN.search(title):
        m = _COMICS_FRANCHISE_PATTERN.search(title)
        return True, f"comic_franchise:{m.group(0)}"
    if title and _COMICS_FORMAT_PATTERN and _COMICS_FORMAT_PATTERN.search(title):
        m = _COMICS_FORMAT_PATTERN.search(title)
        return True, f"comic_format:{m.group(0)}"
    return False, ""


# --- Detector de NOVELA (no manga, no cómic) -------------------------------
#
# Las búsquedas en retailers (Fnac, Casa del Libro, Amazon) traen muchas
# NOVELAS bestseller con "edición coleccionista" (Rebecca Yarros, Sarah J.
# Maas, Booktok hits). Las novelas NO son manga ni light novel — son
# literatura adulta empaquetada como item coleccionable. Hay que filtrarlas.
#
# Cuidado: la palabra "novela" SÍ aparece legítimamente en "novela ligera" /
# "light novel" (manga-related). Sólo rechazamos cuando es novela "pura".

# URLs que sugieren sección NO-manga del retailer.
_NOVEL_URL_PATTERNS = re.compile(
    r"/literatura/|/literatura-juvenil/|/literatura-infantil/"
    r"|/novela-romantica/|/novela-fantastica/|/novela-historica/|/novela-juvenil/"
    r"|/ficcion/|/no-ficcion/|/best-?sellers?/"
    r"|/jovenes-adultos/|/young-adult/"
    r"|/ensayo/|/poesia/|/biograf",
    re.IGNORECASE,
)

# Palabras en title/desc que indican NOVELA si NO van acompañadas de manga.
_NOVEL_INDICATOR_PATTERNS = re.compile(
    r"\bnovela\s+(?:rom[áa]ntica|fant[áa]stica|hist[óo]rica|juvenil|gr[áa]fica|negra|negra)\b"
    r"|\bsaga\s+(?:literaria|romántica|romantica|fant[áa]stica)\b"
    r"|\b(?:bestseller|best-?seller)\b"
    r"|\bbooktok\b"
    r"|\b(?:novel|novela)\s+series\b",
    re.IGNORECASE,
)

# Whitelist override: si el title/desc menciona estos, NO es novela pura.
_NOVEL_BYPASS_PATTERNS = re.compile(
    r"\bmanga\b"
    r"|\blight\s+novel\b|\bnovela\s+ligera\b|\bnovela\s+gr[áa]fica\b"
    r"|\branobe\b|\bラノベ|\bライトノベル"
    r"|\bcomic\b|\bcómic\b|\bfumetto\b",
    re.IGNORECASE,
)


def is_pure_novel(title: str, description: str = "", url: str = "") -> tuple[bool, str]:
    """Detecta si un item es novela pura (no manga ni cómic).

    Casos típicos: novelas bestseller con "edición coleccionista" que se
    cuelan vía búsquedas tipo `site:fnac.es "edición coleccionista"`.

    Returns:
        (is_novel, reason)
    """
    blob = f"{title}\n{description}"
    # Bypass: si menciona manga/light novel/cómic, NO es novela pura.
    if _NOVEL_BYPASS_PATTERNS.search(blob):
        return False, ""
    # URL en sección literaria/novela
    if url and _NOVEL_URL_PATTERNS.search(url):
        m = _NOVEL_URL_PATTERNS.search(url)
        return True, f"novel_url:{m.group(0)}"
    # Indicadores explícitos en title/desc
    if _NOVEL_INDICATOR_PATTERNS.search(blob):
        m = _NOVEL_INDICATOR_PATTERNS.search(blob)
        return True, f"novel_indicator:{m.group(0)[:30]}"
    return False, ""


def is_likely_manga(
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    source_purity: str = "manga_only",
    publisher: str = "",
    url: str = "",
) -> tuple[bool, str]:
    """Heurística para decidir si un candidato es un manga (o libro relacionado:
    artbook, novela ligera, edición coleccionista con manga) versus un producto
    derivado puro (figura, estatua, Funko, DVD, puzzle, taza, etc.).

    Args:
        source_purity: "manga_only" (default) o "mixed". Cuando es "mixed",
            no permitimos rescue por pack-extras solo — exigimos STRONG manga
            hint adicional. Esto cierra el agujero donde "Collector's Edition"
            rescataba estatuas/prints en sources tipo Dark Horse Direct.

    Returns:
        (is_manga, reason) — `reason` describe la regla que aplicó.

    Reglas (en orden):
      0a. Tag externo indica anime/film/OAV/dérivé → False (alta confianza,
          viene de la taxonomía oficial de la fuente).
      0b. NON-MANGA HARD del título (DVD, Blu-ray, Funko, Vinyl Figure...).
          Estos productos NUNCA son extras en un pack de manga.
      1. STRONG manga hint en título o descripción → True
      2. PACK / extras hint (edición especial + figura, cofanetto...) → True,
         EXCEPTO cuando source_purity='mixed' y NO hay STRONG hint — la
         editorial publica figuras/prints/etc. donde "Collector's Edition"
         no implica manga.
      3. NON-MANGA SOFT (statue, puzzle, mug, plush…) → False
      4. Default → True (conservador, mejor false-positive que perder mangas)
    """
    if not title:
        return True, "default:empty"

    # 0a) Tag taxonómico de la fuente (Manga-Sanctuary categoriza con "type:...").
    # Comparación case-insensitive — Manga-Sanctuary etiqueta `type:oav` en
    # minúsculas mientras nuestro blacklist usa mixed-case (`type:OAV`).
    if tags:
        prefix_lc = tuple(p.lower() for p in _NON_MANGA_TAG_PREFIXES)
        for tag in tags:
            tag_lc = tag.lower()
            for prefix in prefix_lc:
                if tag_lc == prefix or tag_lc.startswith(prefix + " "):
                    return False, f"non_manga_tag:{tag}"

    # 0a-bis) Comics blacklist — se aplica SIEMPRE (no solo en mixed).
    # El blacklist tiene franquicias inequívocamente NO-manga (Spider-Man,
    # Batman, Sin City, Asterix, etc.) que NO existen en catálogos manga
    # legítimos. Aplicarlo en manga_only también atrapa basura que cuela
    # por searches (ej. Star Comics tiene purity=manga_only pero su search
    # ?q=variant trae Sin City).
    # NOTA: NO incluyas en blacklist nombres ambiguos que también puedan
    # aparecer en manga (Disney → Twisted Wonderland, Conan → Detective Conan).
    is_comic, reason = is_comic_not_manga(title, publisher)
    if is_comic:
        return False, reason

    # 0a-ter) Detector de novelas puras (no manga). Bestseller con "edición
    # coleccionista" se cuelan vía searches retailer (Fnac/Casa del Libro).
    is_novel, novel_reason = is_pure_novel(title, description, url=url)
    if is_novel:
        return False, novel_reason

    # 0a-quater) URLs de blogs/posts editoriales — NUNCA son productos.
    # ListadoManga /blog/ son anuncios/noticias; los redactan con prosa libre
    # que escaparía a los patrones de _NON_MANGA_HARD.
    if url and _BLOG_URL_PATTERNS.search(url):
        m = _BLOG_URL_PATTERNS.search(url)
        return False, f"blog_url:{m.group(0)[:40]}"

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
    # En fuentes "mixed" (catálogo no-100%-manga), pack-extras NO basta como
    # rescate — exigimos STRONG hint. Esto evita que "Collector's Edition"
    # rescate prints, bookends, estatuas, etc. en Dark Horse Direct y
    # retailers genéricos.
    if source_purity != "mixed":
        for pat in _MANGA_WITH_EXTRAS_PATTERNS:
            if pat.search(blob_extra):
                return True, f"pack:{pat.pattern[:40]}"

    # 3) Non-manga SOFT: solo si no se rescató antes.
    for pat in _NON_MANGA_SOFT:
        if pat.search(blob):
            return False, f"non_manga_soft:{pat.pattern[:40]}"

    # 4) Default según purity.
    # En sources 'manga_only' confiamos en su catálogo: aceptar si no hay
    # señal explícita de non-manga. En sources 'mixed' (Dark Horse Direct,
    # retailers mixtos) somos estrictos: sin STRONG manga hint, descartar.
    if source_purity == "mixed":
        return False, "default:mixed_no_strong_hint"
    return True, "default:no_match"


def derive_product_type(title: str, description: str, signal_types: list[str]) -> str:
    """Devuelve el tipo de producto detectado (manga / artbook / magazine / boxset / etc.)."""
    if not (title or description):
        return ""
    text = normalize_text(f"{title} {description}")
    # Magazine de serie (One Piece Magazine, Captain Tsubasa Magazine…).
    # Las revistas-paraguas (Shōnen Jump, Young Jump, etc.) las descarta luego
    # is_collectible_edition() vía _UMBRELLA_JP_MAGAZINE_PATTERN.
    if re.search(r"\bMagazine\b", title or ""):
        return "magazine"
    # Word-boundary match (igual que detect_signals). Antes hacíamos substring
    # match, lo que causaba que "Manga Artbooks" en descripción etiquetara
    # tomos regulares como product_type=artbook (Rin-ne, Bleach, etc.).
    for ptype, words in PRODUCT_TYPE_KEYWORDS:
        for w in words:
            if _phrase_pattern(normalize_text(w)).search(text):
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


# --- Filtro "es edición coleccionable" -------------------------------------
#
# Después de pasar `is_likely_manga` (item es un manga válido o libro relacionado),
# este segundo gate decide si es EDICIÓN ESPECIAL / COLECCIONABLE / VARIANTE /
# CON EXTRAS DE PRIMERA EDICIÓN / ARTBOOK / FANBOOK / GUIDEBOOK / MAGAZINE-DE-SERIE.
#
# El producto NO es un catálogo general de manga — sólo lo coleccionable.
# Por eso "Naruto 12 (regular)" se rechaza, pero "Naruto 12 con marcapáginas
# exclusivo primera edición" se acepta (signal_type=bonus).

# Signal types que prueban "es una edición especial / coleccionable".
#
# ⚠️ `omnibus` NO está acá: el usuario decidió (2026-05-22) que "omnibus" /
# "X en X" / "X-in-X" por sí solo NO califica — es básicamente un tomo más
# grueso. Solo se acepta cuando viene CON un qualifier premium adicional
# (hardcover, deluxe, limited, variant_cover, box_set, etc.). Como esos
# qualifiers SÍ están en este set, un omnibus premium pasa por ellos.
# Ver gotcha #18 en CLAUDE.md.
COLLECTIBLE_EDITION_SIGNAL_TYPES = frozenset({
    "limited", "special_edition", "collector", "deluxe", "premium_format",
    "box_set", "variant_cover", "retailer_exclusive", "made_to_order",
    "bundle", "pack", "new_art", "oversized", "hardcover",
    "lore_edition",  # set por score_candidate cuando título dispara X-Edition regex
})

# Signal types de "extras de primera edición" sobre un tomo regular
# (marcapáginas, postales, póster, acrílico, sobrecubierta reversible, etc.).
# Suficientes para incluir el item: el usuario los quiere ver.
FIRST_EDITION_EXTRAS_SIGNAL_TYPES = frozenset({
    "bonus", "finish",
})

# Product types intrínsecamente coleccionables o "manga-related".
COLLECTIBLE_PRODUCT_TYPES = frozenset({
    "artbook", "fanbook", "guidebook", "magazine", "boxset",
})

# Regex generalista "<Word> Edition / Edizione / Édition / Edición".
# Captura lore-words específicas a cada manga sin necesidad de diccionario:
# "Beherit Edition", "Tarot Edition", "Tribute Edition", "Master Edition",
# "Celebration Edition", "Final Edition", "Metal Edition", "Anniversary
# Edition", etc.
#
# Excluye palabras genéricas que no implican edición especial ("First Edition",
# "New Edition", "Print Edition", "Spanish Edition", "Digital Edition", etc.).
# "Omnibus" se EXCLUYE específicamente porque no es una marca de edición
# coleccionable: "Omnibus Edition" = paperback con varios chapters reunidos,
# básicamente un tomo más grueso. La regla del usuario (gotcha #18): omnibus
# solo cuenta como coleccionable si viene con otro qualifier premium
# (hardcover/deluxe/limited/variant/box/extras). Ver `is_collectible_edition`.
#
# El patrón matchea Edición/Edizione/Édition además de Edition, así que las
# palabras genéricas en ES/IT/FR DEBEN excluirse igual que las inglesas — si
# no, "Nueva Edición" (= "New Edition", una reimpresión) dispara lore_edition
# falsamente y cuela tomos/omnibus normales por el gate. Ver gotcha #24.
_GENERIC_X_EDITION_PATTERN = re.compile(
    r"\b(?!(?:The|This|That|First|Second|Third|Fourth|Fifth|Next|Last|"
    r"Latest|New|Old|Same|Other|Another|Each|Every|Any|All|Some|Whole|"
    r"Print|Digital|Paperback|Hardcover|Spanish|English|French|Italian|"
    r"Japanese|German|US|UK|EU|Standard|Regular|Original|Final|"
    r"Omnibus"
    # Genéricos ES/IT/FR (mismas categorías que la lista inglesa de arriba:
    # new / ordinales / standard / regular / original / digital / idioma).
    r"|Nueva|Nuova|Nouvelle|Primera|Prima|Première|Premiere"
    r"|Segunda|Seconda|Tercera|Terza|Última|Ultima"
    r"|Estándar|Estandar|Regolare|Originale|Digitale|Numérique|Numerique|Impresa"
    r"|Española|Espanola|Inglesa|Italiana|Japonesa|Alemana|Francesa)\b)"
    r"([A-Za-z][\w\-]{2,})\s+"
    r"(?:Edition|Edizione|Édition|Edición|Edicion)\b",
    re.IGNORECASE,
)

# "Shape de número de volumen manga" — distingue "One Piece 100" de
# "Top 10 Limited Editions". Acepta:
#   - vol/tome/tomo/band/volume + N (con o sin punto)
#   - n°/Nº/N°/N. + N
#   - #N
#   - número al final del title (típico de listings retail: "Berserk 41")
#   - número japonés con marcador de volumen (12巻)
#   - rangos tipo "1-12", "Vol 1 a 5"
_MANGA_VOLUME_SHAPE = re.compile(
    r"\b(?:vol|tome|tomo|band|volume|volumen)\s*\.?\s*\d{1,3}\b"  # vol N (1-3 dígitos)
    r"|\b[Nn][º°o\.]\s*\d{1,3}\b"                                  # n°N
    r"|#\d{1,3}\b"                                                 # #N
    r"|\s\d{1,3}\s*(?:\([^)]+\))?\s*$"                             # número al final
                                                                   # NOTA: 1-3 dígitos para
                                                                   # excluir años (2024, 1999).
                                                                   # Manga rarely > 999 volúmenes.
    r"|\d{1,3}\s*巻"                                               # 12巻
    r"|\b\d{1,3}\s*[-–]\s*\d{1,3}\b",                              # 1-12 rango
    re.IGNORECASE,
)


# Revistas-paraguas japonesas (antologías multi-serie): fuera de scope.
# Las revistas de UNA serie ("One Piece Magazine", "Captain Tsubasa Magazine")
# no matchean esto y pasan por product_type='magazine'.
#
# Sólo nombres inequívocos (compuestos o muy específicos). Nombres ambiguos
# que también pueden aparecer como palabra en series (Kiss → Kamisama Kiss;
# Margaret, Morning, LaLa) NO se incluyen — preferimos perder pocos
# umbrella-magazines a rechazar mangas reales.
_UMBRELLA_JP_MAGAZINE_PATTERN = re.compile(
    r"\b(?:Weekly\s+|Monthly\s+)?(?:Sh[ōo]nen|Young|Big|Bessatsu)\s+"
    r"(?:Jump|Magazine|Sunday|Comic|Spirits|Original|Superior)\b"
    r"|\b(?:Comic\s+Beam|Comic\s+Zenon|Comic\s+Bunch|Comic\s+Birz|"
    r"Megami\s+Magazine|Newtype|Animage)\b"
    r"|週刊少年(?:ジャンプ|マガジン|サンデー|チャンピオン)"
    r"|月刊(?:少年|ヤング|アフタヌーン|モーニング)",
    re.IGNORECASE,
)


_PRODUCT_URL_SHAPE = re.compile(
    # Patrones de URL canónica de catálogo manga/cómic. Una URL con shape
    # de producto cuenta como prueba de que es un item real.
    r"/products?/|/manga/|/fumetto/|/livre/|/livres/|/libro/|/libros/"
    r"|/produit[s]?/|/producto[s]?/|/articulo[s]?/"
    r"|-vol-?\d+|-tome-?\d+|-tomo-?\d+|-band-?\d+"
    r"|-(?:collector|deluxe|limited|special|variant|edition|hardcover"
    r"|boxset|cofanetto|coffret|kanzenban|omnibus|integral|prestige)-"
    r"|-p\d+\.html|/p/\d+",
    re.IGNORECASE,
)

# URLs de blog/news que invalidan el match de _PRODUCT_URL_SHAPE.
# Una URL como `/blog/top-10-limited-editions` matchea "limited-editions" pero
# es claramente contenido editorial, no un producto.
_BLOG_URL_PATTERN = re.compile(
    r"/blog[s]?/|/news/|/noticias?/|/actu[a-z]*/|/articles?/|/post[s]?/"
    r"|/category/|/categoria/|/tag/|/tags/|/author[s]?/"
    r"|\.(?:atom|rss|xml)$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Cluster key — agrupación lógica de items que representan el "mismo producto"
# aunque vengan de fuentes distintas.
# ---------------------------------------------------------------------------

# Patrones para extraer número de volumen del título, ordenados de más
# específico a menos. El primero que matchee gana.
_VOLUME_EXTRACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bvol\.?\s*(\d{1,4})\b", re.IGNORECASE),
    re.compile(r"\bvolume\s*(\d{1,4})\b", re.IGNORECASE),
    re.compile(r"\btomo\s*(\d{1,4})\b", re.IGNORECASE),
    re.compile(r"\btome\s*(\d{1,4})\b", re.IGNORECASE),
    re.compile(r"\bn[.ºo°]\s*(\d{1,4})\b", re.IGNORECASE),
    re.compile(r"#\s*(\d{1,4})\b"),
    re.compile(r"(\d{1,4})\s*巻"),  # JP "巻"
    # Volumen entre paréntesis (común en JP: "タイトル（15）", "Title (10)")
    # Acepta paréntesis half-width y full-width.
    re.compile(r"[（(]\s*(\d{1,4})\s*[）)]"),
)

# Palabras a stripear del título para obtener `series_name`. Cubren markers
# de volumen y variant edition en ES/IT/FR/EN/JP. Word-boundary regex.
_SERIES_STRIP_TOKENS: tuple[str, ...] = (
    # Variant edition keywords (lo que ya está en signal_types — los stripeamos
    # del título para que series sea sólo el nombre de la obra).
    "celebration edition", "edicion especial", "edición especial",
    "edicion deluxe", "edición deluxe", "edicion coleccionista",
    "edición coleccionista", "edicion original", "édition originale",
    "edition collector", "edition limitee", "édition limitée",
    "deluxe edition", "collector edition", "limited edition",
    "variant cover", "variant edition", "box set", "boxset", "cofanetto",
    "coffret integrale", "coffret intégrale", "coffret",
    "kanzenban", "perfect edition", "ultimate edition",
    "first print", "premiere edition", "première edition",
    # Markers de volumen / pieza
    "tomo", "tome", "volume", "vol.", "vol",
    "n.", "n°", "nº", "no.", "no",
    # Markers stripables varios
    "manga", "edición", "edicion", "edition",
)

_SERIES_STRIP_RE = re.compile(
    # Lookaround alphanumeric — soporta tokens que terminan en puntuación
    # (e.g. "vol.", "n.") porque \b no matchea entre `.` y space.
    r"(?<![A-Za-z0-9])(?:"
    + "|".join(re.escape(t) for t in sorted(_SERIES_STRIP_TOKENS, key=len, reverse=True))
    + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# Bracket/parenthesis contents (suelen contener variantes específicas que
# rompen la identidad de "serie" — ej. "(BeBoy Comics Deluxe)" en JP).
_BRACKETED_RE = re.compile(r"[\(\[\{【（［].*?[\)\]\}】）］]")


def _extract_volume(title: str) -> str:
    """Devuelve el volumen como string (e.g. "100") o "" si no detecta."""
    if not title:
        return ""
    for pat in _VOLUME_EXTRACT_PATTERNS:
        m = pat.search(title)
        if m:
            return m.group(1)
    return ""


def _normalize_series_name(title: str, volume: str) -> str:
    """Limpia el título para quedarse sólo con el nombre de la serie.

    - strip de keywords variant (deluxe, kanzenban, …)
    - strip de markers de volumen
    - strip de números (si están sueltos al final, casi siempre son vol)
    - strip de bracketed content (suele ser ruido de retailer)
    - lower + collapse whitespace
    - NO strip de unicode (preservamos kanji/kana/accents — son discriminantes)
    """
    if not title:
        return ""
    text = _BRACKETED_RE.sub(" ", title)
    text = _SERIES_STRIP_RE.sub(" ", text)
    # Quitar el número de volumen específico si lo conocemos
    if volume:
        text = re.sub(rf"(?<!\d){re.escape(volume)}(?!\d)", " ", text)
    # Quitar puntuación común que sobra (incluye `.` y `/` porque títulos como
    # "One Piece — Vol.98 - Celebration edition" dejan un `.` residual tras
    # remover "vol" y el número del volumen — sin esto, "one piece ." y
    # "one piece" no mergean).
    text = re.sub(r"[:\-–—_,;|./\\]+", " ", text)
    # Collapse y lowercase
    text = re.sub(r"\s+", " ", text).strip().lower()
    # Defensa adicional: limpieza de puntuación de bordes (preserva kanji/kana
    # en medio porque str.strip(chars) solo opera en los extremos).
    text = text.strip(" -–—.,:;|/\\")
    return text


# Jerarquía de "tier" de variante para cluster_key. La idea: distintas fuentes
# detectan signal_types ligeramente distintos para el mismo producto
# (ej. Star Comics ve [collector, lore_edition] mientras Mangavariant ve
# [bonus, special_edition, collector, lore_edition] para la MISMA One Piece
# Vol.98 Celebration Edition). Si usamos el set completo como discriminante,
# nunca mergean. En cambio mapeamos cada item al tier MÁS ESPECÍFICO al que
# pertenece (primer match de esta lista) y usamos solo ese tier.
#
# Orden: producto-class > formato estructural > release específicamente nombrado
# > formato premium > variant > limited > generic-special.
_VARIANT_TIER_RULES: list[tuple[str, frozenset[str]]] = [
    ("artbook",       frozenset({"artbook", "fanbook", "guidebook"})),
    ("omnibus",       frozenset({"omnibus"})),
    ("box_set",       frozenset({"box_set", "bundle", "pack"})),
    ("kanzenban",     frozenset({"premium_format"})),
    ("lore_edition",  frozenset({"lore_edition"})),  # X-Anniversary, Celebration…
    ("variant_cover", frozenset({"variant_cover", "new_art",
                                  "retailer_exclusive", "made_to_order"})),
    ("deluxe",        frozenset({"deluxe", "hardcover", "oversized"})),
    ("limited",       frozenset({"limited"})),
    ("special",       frozenset({"special_edition", "collector",
                                  "bonus", "finish"})),
]


def _variant_tier(signal_types: list[str] | None) -> str:
    """Mapea un set de signal_types al tier MÁS ESPECÍFICO que matchee.

    Devuelve "" si no matchea ninguno (tomo regular). El tier reemplaza el
    set completo en cluster_key — dos items del mismo tier mergean.
    """
    if not signal_types:
        return ""
    sig_set = {str(s).lower() for s in signal_types if s}
    for tier_name, members in _VARIANT_TIER_RULES:
        if sig_set & members:
            return tier_name
    return ""


def derive_cluster_key(item: dict[str, Any]) -> str:
    """Devuelve la clave de agrupación para deduplicar items entre fuentes.

    Estrategia en cascada:
    1. Si hay ISBN → "isbn:<isbn>". Esto es autoritativo (ISBN es unique per
       edición/mercado, así que items con mismo ISBN son el mismo objeto).
    2. Si NO hay ISBN pero podemos derivar `(language, series, volume)` con
       una serie de >= 3 caracteres → clave fuzzy combinando esos +
       variant_tier (un tier único derivado de signal_types) + publisher.
       Items con misma clave fuzzy son tratados como el mismo producto.
    3. Cualquier otro caso (sin ISBN y series demasiado corta o sin volumen)
       → "url:<url>". Esto garantiza standalone — no se agrupa con nada más,
       evitando falsos positivos.

    `variant_tier` y `publisher` son discriminantes para EVITAR juntar
    "OP100 normal" con "OP100 Celebration" (distinto tier) o ediciones de
    publishers distintos. Idioma es discriminante para no mezclar mercados.

    Antes este campo era `variant_sig = ",".join(sorted(signal_types))`. El
    problema: dos fuentes con descripciones distintas detectan signal_types
    ligeramente distintos del MISMO producto, y el set completo no mergea.
    `_variant_tier` colapsa esa varianza eligiendo solo el tier más
    específico — más tolerante, sigue diferenciando tomo-regular vs especial.
    """
    isbn = (item.get("isbn") or "").strip()
    if isbn:
        return f"isbn:{isbn}"
    title = item.get("title") or ""
    language = (item.get("language") or "").strip().lower()
    publisher = (item.get("publisher") or "").strip().lower()
    signal_types = item.get("signal_types") or []
    variant_tier = _variant_tier(signal_types)
    volume = _extract_volume(title)
    series = _normalize_series_name(title, volume)
    url = (item.get("url") or "").strip()

    # Guardas anti-falso-positivo: series, language y volume son
    # requeridos para considerar dos items "el mismo producto" sin ISBN.
    if (not series or len(series) < 3
            or not language
            or not volume):
        return f"url:{url}"

    return f"fuzzy:{language}|{series}|{volume}|{variant_tier}|{publisher}"


def is_collectible_edition(
    title: str,
    description: str,
    signal_types: list[str] | None,
    product_type: str,
    tags: list[str] | None = None,
    isbn: str = "",
    url: str = "",
) -> tuple[bool, str]:
    """Decide si un item (que ya pasó `is_likely_manga`) es coleccionable.

    El producto del proyecto son SOLO ediciones especiales / variantes /
    coleccionistas / con extras de primera edición / artbooks / magazines
    de serie. Un tomo regular sin nada especial NO es coleccionable.

    Reglas (cualquier match → True):
      0. Revista-paraguas JP (Shōnen Jump, Young Jump…) → False de entrada.
      1. signal_types incluye al menos uno de COLLECTIBLE_EDITION_SIGNAL_TYPES
         (limited, collector, deluxe, variant_cover, retailer_exclusive,
         box_set, bundle, etc.).
      2. signal_types incluye FIRST_EDITION_EXTRAS (bonus / finish) — un tomo
         "regular" con marcapáginas exclusivo / sobrecubierta reversible /
         póster / sprayed edges sigue siendo coleccionable.
      3. product_type ∈ COLLECTIBLE_PRODUCT_TYPES (artbook, fanbook,
         guidebook, magazine, boxset).
      4. Título matchea `<Word> Edition/Edizione/Édition/Edición` con
         palabra-lore (Beherit, Tarot, Tribute, Master, Celebration, etc.).

    Returns:
        (is_collectible, reason)
    """
    if not title:
        return False, "no_title"

    # 0a) Título demasiado corto/genérico para ser un nombre de manga real.
    # Casos como "Pre venta", "Sin stock", "Disponible" — basura de selectores.
    stripped = title.strip()
    if len(stripped) < 4:
        return False, "title_too_short"

    # 0a-bis) Títulos junk reconocibles: descuentos ("-10%"), categorías
    # genéricas ("Manga", "Comics"), placeholders. Estos vienen de selectores
    # mal apuntados (badges Magento, headers de categoría WordPress).
    if re.fullmatch(r"-?\d+%?", stripped):                       # "-10%", "10%", "-5"
        return False, "title_junk_discount"
    if stripped.lower() in {"manga", "comic", "comics", "fumetto",
                            "novedades", "novedad", "nouveauté",
                            "edizione", "edition", "edizioni"}:
        return False, "title_junk_generic"

    # 0b) Revista-paraguas → fuera.
    if _UMBRELLA_JP_MAGAZINE_PATTERN.search(title):
        return False, "umbrella_magazine"

    # Union: signal_types pasados (de title+desc del candidate) ∪ los recomputados
    # desde el title solo. Esto cubre dos casos:
    #   - title="Naruto 100 Edición Coleccionista" → title-signals capta collector
    #   - title="One Piece 100" desc="glénat collector étui" → passed sigs capta collector
    # Ambos son legítimos.
    _, _, title_signal_types = detect_signals(title)
    title_sig_set = set(title_signal_types)
    sig_set = set(signal_types or []) | title_sig_set

    # "Es un producto físico real" — al menos una prueba de shape:
    #   (a) la señal de edición está en el TÍTULO (no solo en desc), O
    #   (b) el title tiene shape de NÚMERO DE VOLUMEN manga (no cualquier
    #       número — eso pasaría "Top 10 Limited Editions"), O
    #   (c) el item tiene ISBN catalogado (libro físico identificado).
    has_volume_shape = bool(_MANGA_VOLUME_SHAPE.search(title))
    has_isbn = bool((isbn or "").strip())
    # URL canónica de producto (Manga-Sanctuary, retailers, etc.) también
    # cuenta como prueba: la URL frecuentemente lleva el slug específico de
    # la edición ("manga-hell-s-paradise-vol-1-collector-fnac") aunque el
    # title solo diga el nombre de la serie. Pero invalidamos si la URL es
    # claramente de blog/news (`/blog/top-10-limited-editions`).
    _url = url or ""
    has_product_url = (
        bool(_PRODUCT_URL_SHAPE.search(_url))
        and not _BLOG_URL_PATTERN.search(_url)
    )

    # 1) Signal types de edición especial — exigiendo prueba de producto.
    matched_special = sig_set & COLLECTIBLE_EDITION_SIGNAL_TYPES
    if matched_special:
        title_special = title_sig_set & COLLECTIBLE_EDITION_SIGNAL_TYPES
        if title_special or has_volume_shape or has_isbn or has_product_url:
            return True, f"signal:{','.join(sorted(matched_special))}"
        # Signal sólo en desc Y no hay shape de producto → sospechoso (blog
        # post/listicle de "Top 10 limited editions"). No rescatar por esta
        # vía; seguimos evaluando reglas 2-4 por si encajan.

    # 2) Extras de primera edición (bonus/finish): requiere que el título
    # tenga un NÚMERO (volumen). Esto distingue:
    #   - "Naruto 12 con marcapáginas exclusivo" → tiene "12" → KEEP
    #   - "Fandango your tickets, posters, trailers" → no tiene número → REJECT
    # Los news/social posts rara vez incluyen un número aislado al estilo
    # de un volumen de manga.
    matched_extras = sig_set & FIRST_EDITION_EXTRAS_SIGNAL_TYPES
    if matched_extras and re.search(r"\b\d+\b", title):
        return True, f"extras:{','.join(sorted(matched_extras))}"

    # 3) Product type intrínsecamente coleccionable.
    # artbook/fanbook/guidebook/magazine son inherently coleccionables.
    # boxset requiere defensa extra: como signal box_set puede venir de "boxset"
    # en una descripción narrativa ("Top 10 ... boxset"), exigimos prueba de
    # producto (boxset-word en title, volume shape o ISBN).
    if product_type in COLLECTIBLE_PRODUCT_TYPES:
        if product_type != "boxset":
            return True, f"product_type:{product_type}"
        # boxset → exigir prueba de producto
        has_boxset_word = bool(re.search(
            r"\b(?:box\s*set|boxset|box-set|cofanetto|coffret|cofre|slipcase|estuche)\b",
            title, re.IGNORECASE,
        ))
        if has_boxset_word or has_volume_shape or has_isbn or has_product_url:
            return True, f"product_type:{product_type}"

    # 4) Regex generalista <Word> Edition / Edizione / etc.
    m = _GENERIC_X_EDITION_PATTERN.search(title)
    if m:
        return True, f"x_edition:{m.group(1).lower()}"

    return False, "regular_tomo"


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
                    purity=str(item.get("purity", "manga_only")).strip().lower(),
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
    """Upsert por URL normalizada: una línea por item único en disco.

    Antes éramos append-only y dejábamos que la web hiciera dedup al cargar,
    pero el archivo crecía indefinidamente (2-3x el tamaño necesario). Ahora:

      1. Leemos items.jsonl existente y lo indexamos por URL normalizada.
      2. Para cada row nueva: reemplaza la entrada existente o agrega.
      3. Reescribimos el archivo entero atómicamente (.tmp + rename).

    Performance: para 3000 items, esto es ~50ms en disco SSD. Imperceptible
    en el contexto de un scrape que tarda minutos.

    Si dos items distintos comparten URL normalizada (raro), gana el último.
    Si una row no tiene URL, se appendea sin merge.
    """
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Cargar existentes en un dict {key -> row}.
    existing: dict[str, dict[str, Any]] = {}
    no_url_rows: list[dict[str, Any]] = []
    if path.exists():
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                url = item.get("url", "")
                if not url:
                    no_url_rows.append(item)
                    continue
                key = normalize_url_for_dedup(url)
                existing[key] = item  # last-wins si hubiera duplicados en el archivo

    # 2. Upsert con las rows nuevas (last-wins por URL).
    #
    # Excepción: si el row existente tiene `standardized_at`, preservamos los
    # campos seteados por el skill `/standardize-catalog` (title canónico,
    # series_key/edition_key, volume, etc.). Los campos scrapeados (price,
    # image_url, isbn, author, stock_type, signal_types, score, detected_at)
    # SÍ se refrescan con la row nueva. Sin esta merge, un re-scrape borra
    # toda la estandarización LLM-verified — efecto descubierto el
    # 2026-05-22 cuando se re-scrapeó mangadreams variants-europeas.
    _CURATED_FIELDS = (
        "standardized_at",
        "title",
        "title_original",
        "series_key",
        "series_display",
        "edition_key",
        "edition_display",
        "volume",
    )
    for row in rows:
        url = row.get("url", "")
        if not url:
            no_url_rows.append(row)
            continue
        key = normalize_url_for_dedup(url)
        old = existing.get(key)
        # image_local es sticky: un re-scrape que no descargó la portada
        # (--skip-image-download o fallo de red puntual) no debe borrar el
        # espejo local que ya teníamos. Ver "Image storage" en CLAUDE.md.
        if old and old.get("image_local") and not row.get("image_local"):
            row["image_local"] = old["image_local"]
        # images[] es UNION-MERGE entre old y new (Fase 2 listadomanga-collections):
        # un re-scrape que sólo trae la cover no debe borrar los extras que
        # se agregaron en una pasada previa con merge extra→tomo, y viceversa
        # — un re-scrape de extras no debe borrar la cover. Deduplicamos por
        # (kind, url) preservando el orden (primero los del old, después los
        # nuevos del row que no estén). Si ambos están vacíos, no escribir.
        old_images = list((old or {}).get("images") or [])
        new_images = list(row.get("images") or [])
        if old_images or new_images:
            seen_keys: set[tuple[str, str]] = set()
            merged_images: list[dict[str, Any]] = []
            for im in old_images + new_images:
                k = (im.get("kind", ""), im.get("url", ""))
                if k in seen_keys:
                    continue
                seen_keys.add(k)
                merged_images.append(im)
            row["images"] = merged_images
        # extras[]: misma lógica de union-merge dedup por (description, release_date).
        old_extras = list((old or {}).get("extras") or [])
        new_extras = list(row.get("extras") or [])
        if old_extras or new_extras:
            seen_e: set[tuple[str, str]] = set()
            merged_e: list[dict[str, Any]] = []
            for ex in old_extras + new_extras:
                k = (ex.get("description", ""), ex.get("release_date", ""))
                if k in seen_e:
                    continue
                seen_e.add(k)
                merged_e.append(ex)
            row["extras"] = merged_e
        if old and old.get("standardized_at"):
            merged = dict(row)
            for field in _CURATED_FIELDS:
                if old.get(field) not in (None, ""):
                    merged[field] = old[field]
            existing[key] = merged
        else:
            existing[key] = row

    # 3. Reescribir atómicamente. Conservamos el orden: primero todos los que
    #    tienen URL (ordenados por detected_at para estabilidad), luego los
    #    sin URL al final.
    def _detected_key(item: dict[str, Any]) -> str:
        return str(item.get("detected_at", "") or "")

    sorted_rows = sorted(existing.values(), key=_detected_key)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        for item in sorted_rows:
            file.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
        for item in no_url_rows:
            file.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    tmp_path.replace(path)


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
_PLAYWRIGHT_REAL_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Dedicated Playwright worker thread + request queue.
#
# Por qué un dedicated thread y no un singleton compartido entre workers
# del ThreadPoolExecutor:
#   `sync_playwright().start()` instala greenlets bound al thread que lo
#   inicia. Si OTRO thread del pool intenta llamar métodos del browser
#   singleton, Playwright tira `greenlet.error: Cannot switch to a
#   different thread` (observado en scrape_full del 2026-05-24 con
#   workers=8 → 4 sources kind:js fallaron: Crunchyroll Noticias, Kibook,
#   Seven Seas Box Sets, Meian).
#
#   El `js_lock` viejo solo serializaba el acceso pero NO movía las
#   llamadas al thread dueño del greenlet event loop.
#
# Solución: TODO el trabajo Playwright (start, launch, navigate, close)
# corre en UN solo dedicated thread (`_PLAYWRIGHT_WORKER`). Los workers
# HTTP siguen paralelos; cuando uno necesita Playwright, mete un job en
# `_PLAYWRIGHT_QUEUE` y espera la respuesta vía `queue.Queue` privada.
# La queue serializa naturalmente (sin lock manual) y greenlets nunca
# cruzan threads.
import queue as _queue_mod

_PLAYWRIGHT_QUEUE: _queue_mod.Queue | None = None
_PLAYWRIGHT_WORKER: threading.Thread | None = None
_PLAYWRIGHT_WORKER_LOCK = threading.Lock()
_PLAYWRIGHT_SHUTDOWN_SENTINEL = object()


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


def _playwright_worker_loop(req_queue: _queue_mod.Queue) -> None:
    """Loop del dedicated thread: lazy-launch del browser + procesa jobs.

    Cada job es (url, timeout_ms, wait_until, resp_queue) — el worker
    ejecuta `_fetch_impl` y devuelve `('ok', (html, meta))` o
    `('err', exc)` por la `resp_queue` del caller.

    Sentinel `_PLAYWRIGHT_SHUTDOWN_SENTINEL` termina el loop limpiamente.
    """
    pw_instance = None
    browser = None
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--no-sandbox",
    ]
    while True:
        job = req_queue.get()
        try:
            if job is _PLAYWRIGHT_SHUTDOWN_SENTINEL:
                break
            url, timeout_ms, wait_until, resp_q = job
            try:
                # Lazy-launch en el primer job (el greenlet binding queda
                # en ESTE thread, donde vive permanentemente).
                if browser is None:
                    from playwright.sync_api import sync_playwright
                    pw_instance = sync_playwright().start()
                    browser = pw_instance.chromium.launch(
                        headless=True, args=launch_args
                    )
                result = _fetch_with_playwright_impl(
                    browser, url, timeout_ms, wait_until
                )
                resp_q.put(("ok", result))
            except Exception as exc:  # noqa: BLE001
                resp_q.put(("err", exc))
        finally:
            req_queue.task_done()
    # Cleanup del browser dentro del MISMO thread (donde se creó).
    if browser is not None:
        try:
            browser.close()
        except Exception:
            pass
    if pw_instance is not None:
        try:
            pw_instance.stop()
        except Exception:
            pass


def _ensure_playwright_worker() -> _queue_mod.Queue:
    """Lazy-init del dedicated thread + queue. Idempotente y thread-safe."""
    global _PLAYWRIGHT_QUEUE, _PLAYWRIGHT_WORKER
    with _PLAYWRIGHT_WORKER_LOCK:
        if _PLAYWRIGHT_QUEUE is None:
            _PLAYWRIGHT_QUEUE = _queue_mod.Queue()
        if _PLAYWRIGHT_WORKER is None or not _PLAYWRIGHT_WORKER.is_alive():
            _PLAYWRIGHT_WORKER = threading.Thread(
                target=_playwright_worker_loop,
                args=(_PLAYWRIGHT_QUEUE,),
                name="playwright-worker",
                daemon=True,
            )
            _PLAYWRIGHT_WORKER.start()
        return _PLAYWRIGHT_QUEUE


def close_playwright() -> None:
    """Termina el dedicated thread + cleanup browser (best-effort)."""
    global _PLAYWRIGHT_QUEUE, _PLAYWRIGHT_WORKER
    with _PLAYWRIGHT_WORKER_LOCK:
        worker = _PLAYWRIGHT_WORKER
        q = _PLAYWRIGHT_QUEUE
        if worker is not None and worker.is_alive() and q is not None:
            q.put(_PLAYWRIGHT_SHUTDOWN_SENTINEL)
            worker.join(timeout=10)
        _PLAYWRIGHT_WORKER = None
        _PLAYWRIGHT_QUEUE = None


def fetch_with_playwright(
    url: str, timeout_ms: int = 30000, wait_until: str = "domcontentloaded"
) -> tuple[str, dict[str, Any]]:
    """Renderiza la página con Chromium headless y devuelve (html, metadata).

    Internamente delega al dedicated `_PLAYWRIGHT_WORKER` thread vía queue
    (ver comentario arriba — sin esto, ThreadPoolExecutor con workers>1
    causa `greenlet.error: Cannot switch to a different thread`).

    Requiere `pip install playwright && playwright install chromium`.
    """
    if not _playwright_available():
        raise RuntimeError(
            "Playwright no está instalado. Instalar con: "
            "pip install playwright && playwright install chromium"
        )
    req_q = _ensure_playwright_worker()
    resp_q: _queue_mod.Queue = _queue_mod.Queue()
    req_q.put((url, timeout_ms, wait_until, resp_q))
    # Espera con timeout generoso (timeout_ms del fetch + buffer para
    # launch del browser + cola si hay backlog de jobs).
    status, value = resp_q.get(timeout=(timeout_ms / 1000) + 60)
    if status == "err":
        raise value
    return value


def _fetch_with_playwright_impl(
    browser: Any,
    url: str,
    timeout_ms: int,
    wait_until: str,
) -> tuple[str, dict[str, Any]]:
    """Implementation real del fetch — corre SIEMPRE en el dedicated thread.

    NO llamar directamente; entrá por `fetch_with_playwright` que despacha
    el job via queue al thread dueño del greenlet event loop.
    """
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
        # En sources mixed (Dark Horse Direct, etc.), exigimos STRONG manga hint.
        is_manga, _reason = is_likely_manga(
            candidate.title, candidate.description,
            tags=candidate.tags, source_purity=source.purity,
            publisher=candidate.publisher or source.publisher,
            url=candidate.url,
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
        is_manga, _reason = is_likely_manga(
            title, summary, source_purity=source.purity,
            publisher=source.publisher, url=link,
        )
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


_BLUESKY_PROFILE_RE = re.compile(r"bsky\.app/profile/([A-Za-z0-9._:-]+)")


def bluesky_handle_from_url(url: str) -> str:
    """Extrae 'foo.bsky.social' de 'https://bsky.app/profile/foo.bsky.social'."""
    if not url:
        return ""
    m = _BLUESKY_PROFILE_RE.search(url)
    return m.group(1) if m else ""


def bluesky_api_url(handle: str, limit: int = 30) -> str:
    """URL pública XRPC para obtener el feed de un actor (sin auth)."""
    return (
        "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
        f"?actor={quote_plus(handle)}&limit={limit}&filter=posts_no_replies"
    )


def extract_bluesky_posts(
    source: Source, json_text: str, max_items: int, max_age_days: int = 0,
) -> list[Candidate]:
    """Convierte JSON del XRPC author feed de Bluesky en Candidates.

    Cada post → 1 Candidate. Si el post tiene un embed external (link card
    apuntando a una tienda), se usa el title del link como title del item
    y la URL del link como URL canónica. Si no, el texto del post va como
    title y la URL es el post de Bluesky en sí (radar de news).
    """
    try:
        data = json.loads(json_text)
    except (json.JSONDecodeError, ValueError):
        return []
    feed = data.get("feed") or []
    if not isinstance(feed, list):
        return []
    cutoff: dt.datetime | None = None
    if max_age_days > 0:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=max_age_days)
    candidates: list[Candidate] = []
    for entry in feed[:max_items]:
        post = entry.get("post") or {}
        rec = post.get("record") or {}
        text = clean_text(rec.get("text", "") or "")
        if not text:
            continue
        created = (rec.get("createdAt") or "").strip()
        if cutoff and created:
            parsed = _parse_feed_date(created)
            if parsed is not None and parsed < cutoff:
                continue
        author = post.get("author") or {}
        handle = author.get("handle", "")
        # Construir URL pública del post: /profile/<handle>/post/<rkey>.
        uri = post.get("uri", "") or ""
        m = re.search(r"app\.bsky\.feed\.post/([a-zA-Z0-9]+)$", uri)
        rkey = m.group(1) if m else ""
        post_url = f"https://bsky.app/profile/{handle}/post/{rkey}" if rkey and handle else (uri or source.url)
        # Embed: external link → preferir su title/uri (suele ser link a producto).
        embed = rec.get("embed") or post.get("embed") or {}
        external = None
        if isinstance(embed, dict):
            if isinstance(embed.get("external"), dict):
                external = embed["external"]
            # Anidado bajo $type "app.bsky.embed.external"
            elif embed.get("$type", "").endswith(".external") and isinstance(embed.get("external"), dict):
                external = embed["external"]
        if external:
            ext_uri = clean_text(external.get("uri", ""))
            ext_title = clean_text(external.get("title", ""))
            ext_desc = clean_text(external.get("description", ""))
            title = ext_title or text[:150]
            description = "\n".join(filter(None, [text, ext_desc]))
            link = ext_uri or post_url
        else:
            # Sólo post de texto. Texto va como title (truncado) y description completa.
            title = text[:150]
            description = text
            link = post_url
        # Imagen: thumb del primer embed.images si existe.
        image_url = ""
        if isinstance(embed, dict):
            imgs = embed.get("images") or []
            if isinstance(imgs, list) and imgs:
                first = imgs[0]
                if isinstance(first, dict):
                    image_url = first.get("thumb", "") or first.get("fullsize", "")
        cand = candidate_from_source(source, title, link, description, published_at=created)
        if image_url:
            cand.image_url = image_url
        candidates.append(cand)
    return candidates


def score_candidate(candidate: Candidate) -> Candidate:
    # Las señales (signal_types) describen al ITEM. Sólo se computan sobre
    # title + description — campos que pertenecen al item.
    #
    # NO incluimos source/publisher/tags/search_keywords aquí porque
    # contaminan signal_types. Por ejemplo:
    #   - source "IT - Panini Edizioni da Collezione e Cofanetti" tiene
    #     "cofanetti" → todos sus items heredarían signal box_set.
    #   - tag "search:boxset" inyectado → todos los resultados heredarían
    #     signal box_set aunque no lo sean.
    #   - tag "edition:coffret collector" de Manga-Sanctuary también
    #     contaminaba.
    # Las descripciones (cuando existen y son del item) SÍ son legítimas:
    # un retailer puede poner "Coffret collector" en la descripción.
    item_text = "\n".join([candidate.title, candidate.description])
    score, signals, signal_types = detect_signals(item_text)

    # Boost por regex X-Edition (Tarot/Beherit/Celebration/Tribute/Master/etc).
    # Esto evita el problema "Berserk Tarot Edition" — pasa is_likely_manga +
    # gate, pero detect_signals devuelve 0 (las palabras lore no están en
    # KEYWORD_RULES) y el score queda < min_score, descartando el item.
    m = _GENERIC_X_EDITION_PATTERN.search(candidate.title or "")
    if m:
        lore_word = m.group(0)
        if lore_word not in signals:
            signals = list(signals) + [lore_word]
        if "lore_edition" not in signal_types:
            signal_types = list(signal_types) + ["lore_edition"]
        score += 35

    # Boost de score (NO signals) por search-keyword: la editorial ya filtró
    # su catálogo por ese keyword, así que cualquier card devuelta merece
    # un empujón de score — pero no entra al signal_types del item.
    search_keywords: list[str] = [
        tag.split(":", 1)[1].strip()
        for tag in (candidate.tags or [])
        if tag.startswith("search:")
    ]
    if search_keywords and score == 0:
        # Si no encontramos NINGUNA señal en title+desc pero la editorial nos
        # devolvió este item bajo un search keyword coleccionista, le damos
        # un score base bajo (no decisivo). El gate is_collectible_edition
        # NO se rescata por esto — sólo por señales reales del item.
        score = 10

    # Boost por URL canónica de edición especial. Una URL Manga-Sanctuary tipo
    # "manga-X-vol-N-collector-Y" o un slug retailer con "-collector-/-deluxe-/
    # -limited-/etc." es evidencia fuerte de coleccionable. Esto sube items
    # legítimos como "One Piece 100" (title genérico + URL '-collector-tui-')
    # por encima del slider default. No aplica si la URL es de blog/news.
    if score > 0 and candidate.url:
        _url = candidate.url
        if not _BLOG_URL_PATTERN.search(_url) and _PRODUCT_URL_SHAPE.search(_url):
            # Pattern más estricto: solo URLs que mencionen edición coleccionable
            # explícitamente (no /products/ genérico — sólo si lleva la palabra-edición).
            if re.search(
                r"-(?:collector|deluxe|limited|special|variant|edition|"
                r"hardcover|boxset|cofanetto|coffret|kanzenban|omnibus|"
                r"integral|prestige|exclusive|exclusiv\w*|esclusiv\w*)-",
                _url, re.IGNORECASE,
            ):
                score += 10

    # Boost adicional: ISBN catalogado + signal de edición = item validado
    # (libro físico identificado, no blog post). +5.
    if (
        score > 0
        and (candidate.isbn or "").strip()
        and set(signal_types) & COLLECTIBLE_EDITION_SIGNAL_TYPES
    ):
        score += 5

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

    # Gate "es edición coleccionable": el producto del proyecto son SOLO
    # ediciones especiales/variantes/coleccionistas/con extras/artbooks.
    # Aplicado aquí (punto único) para que cubra todos los pipelines: HTML,
    # RSS, wiki bootstrap, sitemap mining.
    #
    # BYPASS para fuentes 100% curadas: bases comunitarias como Mangavariant
    # catalogan SOLO variants por diseño — el gate por keywords ("variant",
    # "limited", "deluxe"…) descarta ~30% de items legítimos cuyo title solo
    # dice "Vol.1 - Cover A" o "First print". Marcamos esas filas con el tag
    # 'variant-catalog' en el parser y las dejamos pasar sin filtrar. Ver
    # "URL como referencia" en CLAUDE.md.
    pre_filter_count = len(candidates)
    filtered: list[Candidate] = []
    collectible_rejected = 0
    collectible_bypassed = 0
    for candidate in candidates:
        if "variant-catalog" in (candidate.tags or []):
            filtered.append(candidate)
            collectible_bypassed += 1
            continue
        is_coll, _reason = is_collectible_edition(
            candidate.title,
            candidate.description,
            candidate.signal_types,
            candidate.product_type,
            tags=candidate.tags,
            isbn=candidate.isbn,
            url=candidate.url,
        )
        if is_coll:
            filtered.append(candidate)
        else:
            collectible_rejected += 1
    if collectible_rejected:
        print(
            f"[GATE] {collectible_rejected}/{pre_filter_count} candidatos "
            f"descartados por no ser edición coleccionable"
        )
    if collectible_bypassed:
        print(
            f"[GATE] {collectible_bypassed} candidatos pasaron con bypass "
            f"(tag variant-catalog — fuente curada)"
        )
    candidates = filtered

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


# Publisher → slug mapping. Mismo set que usa el skill standardize-catalog.
# Si agregás publishers nuevos, sincronizar con el skill prompt.
_PUBLISHER_SLUG_MAP: dict[str, str] = {
    # Sintaxis: lowercase substring → slug. Match por substring case-insensitive.
    "dark horse": "darkhorse",
    "glénat": "glenat",
    "glenat": "glenat",
    "viz": "viz",
    "panini": "panini",
    "planet manga": "panini",
    "norma": "norma",
    "planeta": "planeta",
    "ivrea argentina": "ivrea-ar",
    "ivrea ar": "ivrea-ar",
    "ivrea": "ivrea",
    "kana": "kana",
    "pika": "pika",
    "crunchyroll": "kaze",
    "kazé": "kaze",
    "kaze": "kaze",
    "ki-oon": "kioon",
    "ki oon": "kioon",
    "star comics": "star",
    "kodansha usa": "kodansha-us",
    "kodansha": "kodansha",
    "shueisha": "shueisha",
    "square enix": "squareenix",
    "kadokawa": "kadokawa",
    "meian": "meian",
    "ecc": "ecc",
    "arechi": "arechi",
    "delcourt": "delcourt",
    "tonkam": "delcourt",
    "tokyopop": "tokyopop",
    "jbc": "jbc",
    "devir": "devir",
    "newpop": "newpop",
    "pipoca": "pipoca-nanquim",
    "kamite": "kamite",
    "mangaline": "mangaline",
    "manga line": "mangaline",
    "manga dreams": "mangadreams",
    "funside": "funside",
    "milky way": "milkyway",
    "milkyway": "milkyway",
    "doki-doki": "dokidoki",
    "doki doki": "dokidoki",
    "nobi nobi": "nobinobi",
    "tomodomo": "tomodomo",
    "fandogamia": "fandogamia",
    "rakuten": "rakuten",
    "kurokawa": "kurokawa",
    "akita": "akita",
    "hakusensha": "hakusensha",
    "gentosha": "gentosha",
    "mag garden": "maggarden",
}


def _publisher_slug(publisher: str) -> str:
    """Devuelve el slug canónico del publisher, o 'unknown'.

    Match por substring lowercase. El primer pattern del map que matchee gana
    (orden de inserción importa: poner los más específicos arriba).
    """
    if not publisher:
        return "unknown"
    pub_lc = publisher.lower()
    for key, slug in _PUBLISHER_SLUG_MAP.items():
        if key in pub_lc:
            return slug
    return "unknown"


def _slugify_kebab(s: str) -> str:
    """Slugifica a kebab-case: lowercase, sin diacríticos, sin punctuation."""
    if not s:
        return ""
    import unicodedata as _ud
    s = _ud.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not _ud.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def derive_series_metadata(candidate: Candidate) -> dict[str, str]:
    """Asigna heurísticamente `series_key`, `edition_key`, etc. desde el title.

    Esto es la PRIMERA pasada cruda del scraper. Imperfecta a propósito —
    el skill `/standardize-catalog` (subagentes con LLM) la verifica y
    corrige después. NO setea `standardized_at`, así el skill sabe que
    todavía debe procesar este item.

    Reusa los helpers existentes (`_extract_volume`, `_normalize_series_name`,
    `_variant_tier`) que ya manejan vol/tome/巻, mojibake, etc.

    Devuelve `{series_key, series_display, edition_key, edition_display,
    volume, title_standardized}` con strings vacíos cuando no se puede
    derivar (better empty than wrong).
    """
    title = candidate.title or ""
    if not title:
        return {}

    # 1) Volume — reusa el helper canónico
    volume = _extract_volume(title)

    # 2) Series name — strip de keywords + slug
    raw_series = _normalize_series_name(title, volume)
    series_key = _slugify_kebab(raw_series)
    if not series_key or len(series_key) < 3:
        # Demasiado corto (probable garbage) — mejor empty, el skill lo asigna.
        return {}
    # Guards defensivos contra casos donde el heurístico falla obvio:
    # - series_key todo dígitos → es probablemente un volumen mal-extraído (ej.
    #   "鬼滅の刃 23 特装版" deja "23" porque _extract_volume no captura
    #   números sueltos sin marker "vol/tome/巻").
    if series_key.isdigit():
        return {}
    # - series_key termina con número (probable volumen pegado al nombre por
    #   falta de marker "vol/tome/巻"). Ej: "atomic-robo-5", "berserk-41".
    # Excepción: títulos legítimos que TERMINAN en número como "20th Century
    # Boys" → sería "20th-century-boys" (no termina en dígito). Y "Akira" →
    # no termina en dígito. Y "Saint Seiya: Episode G" → no.
    # Falsos positivos son raros — y si pasan, el skill los corrige.
    if re.search(r"-\d{1,3}$", series_key) and not volume:
        return {}
    # Cap en ~35 chars para evitar series_keys absurdas (truncar limpiamente
    # en un guión, no a media palabra).
    if len(series_key) > 35:
        truncated = series_key[:35]
        last_dash = truncated.rfind("-")
        if last_dash > 10:
            series_key = truncated[:last_dash]
        else:
            series_key = truncated
    series_display = raw_series.title() if raw_series else series_key

    # 3) Publisher slug
    pub_slug = _publisher_slug(candidate.publisher or "")

    # 4) Edition slug from signal_types (reusa _variant_tier)
    tier = _variant_tier(candidate.signal_types or [])
    edition_slug_map = {
        "artbook": "artbook",
        "omnibus": "omnibus",
        "box_set": "boxset",
        "kanzenban": "kanzenban",
        "lore_edition": "lore",
        "variant_cover": "variant",
        "deluxe": "deluxe",
        "limited": "limited",
        "special": "special",
    }
    edition_slug = edition_slug_map.get(tier, "regular")

    edition_key = f"{series_key}-{pub_slug}-{edition_slug}"
    edition_name_map = {
        "deluxe": "Deluxe",
        "kanzenban": "Kanzenban",
        "boxset": "Box Set",
        "variant": "Variant",
        "limited": "Limited",
        "lore": "Special Edition",
        "artbook": "Artbook",
        "omnibus": "Omnibus",
        "special": "Special",
        "regular": "Regular",
    }
    edition_name = edition_name_map.get(edition_slug, "Regular")
    publisher_display = candidate.publisher or ""
    edition_display = (
        f"{edition_name} ({publisher_display})" if publisher_display else edition_name
    )

    # 5) title_standardized
    parts = [series_display.strip(), edition_name if edition_slug != "regular" else "", volume]
    title_standardized = " ".join(p for p in parts if p).strip()

    return {
        "series_key": series_key,
        "series_display": series_display,
        "edition_key": edition_key,
        "edition_display": edition_display,
        "volume": volume,
        "title_standardized": title_standardized,
    }


def candidate_to_json(candidate: Candidate) -> dict[str, Any]:
    row = {
        "detected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": candidate.status,
        "score": candidate.score,
        "signals": candidate.signals,
        "signal_types": candidate.signal_types,
        "title": candidate.title,
        # title_original preserva el título scrapeado tal como vino de la
        # fuente (con clean_title aplicado: mojibake fixed, junk removido).
        # NO se sobrescribe cuando el skill /standardize-catalog estandariza
        # `title` a la forma international ("Demon Slayer Limited 23") — el
        # original "鬼滅の刃 23 特装版" queda preservado acá. Ver gotcha #22.
        "title_original": candidate.title,
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
        "image_local": candidate.image_local,
        "release_date": candidate.release_date,
        "product_type": candidate.product_type,
        "author": candidate.author,
        "stock_type": candidate.stock_type,
        "isbn": candidate.isbn,
    }
    # images[] aditivo (Fase 2 listadomanga-collections): carrusel. Normalizamos
    # garantizando que el primer elemento sea kind=cover y sincronice con
    # image_url/image_local. Si el Candidate no trajo images[], lo derivamos
    # del image_url/image_local — backwards-compatible para el resto del
    # pipeline.
    images_list = list(getattr(candidate, "images", []) or [])
    if not images_list and candidate.image_url:
        images_list = [{
            "url": candidate.image_url,
            "local": candidate.image_local,
            "kind": "cover",
            "description": "",
        }]
    elif images_list:
        # Si hay un cover explícito en images[], moverlo al frente. Si NO hay
        # cover (todos los elementos son kind=extra/variant_cover/etc.),
        # NO promover artificialmente — mantenemos el kind original. Esto
        # respeta el caso "tomo creado desde extras" (Fase 2 from_extras)
        # donde la única imagen disponible es del extra (cofre/marcapáginas)
        # y semánticamente NO es una cover.
        cover_idx = next(
            (i for i, im in enumerate(images_list) if im.get("kind") == "cover"),
            -1,
        )
        if cover_idx > 0:
            images_list.insert(0, images_list.pop(cover_idx))
        # Sincronizar image_url/image_local con el primer elemento (sea cover
        # o extra). image_url tiene el rol legacy de "alguna imagen visible";
        # el dashboard puede consumirla aunque kind no sea cover.
        first = images_list[0]
        if first.get("url") and not row["image_url"]:
            row["image_url"] = first["url"]
        if first.get("local") and not row["image_local"]:
            row["image_local"] = first["local"]
    if images_list:
        row["images"] = images_list

    extras_list = list(getattr(candidate, "extras", []) or [])
    if extras_list:
        row["extras"] = extras_list

    row["cluster_key"] = derive_cluster_key(row)
    # Hook: si el Candidate ya tiene series_key/edition_key (set por una pasada
    # de estandarización manual o por un scraper futuro), aplicar
    # canonical_series_key() para normalizar a la forma del aliases.yml.
    # Pipeline integration de gotcha #20 (series aliases multilingües).
    try:
        from series_aliases import (
            canonical_series_key,
            is_canonical_key,
            log_unmapped_series,
        )
    except ImportError:
        canonical_series_key = None  # YAML no disponible o falta dep
        is_canonical_key = None
        log_unmapped_series = None
    # Paso A: si el Candidate no tiene series_key/edition_key, derivar
    # heurísticamente desde el title (función rápida, regex-based). El skill
    # `/standardize-catalog` luego corrige los casos raros.
    sk = getattr(candidate, "series_key", "") or ""
    sd = getattr(candidate, "series_display", "") or ""
    ek = getattr(candidate, "edition_key", "") or ""
    ed = getattr(candidate, "edition_display", "") or ""
    vol = getattr(candidate, "volume", "") or ""
    title_std = ""

    if not (sk and ek):
        derived = derive_series_metadata(candidate)
        if derived:
            sk = sk or derived.get("series_key", "")
            sd = sd or derived.get("series_display", "")
            ek = ek or derived.get("edition_key", "")
            ed = ed or derived.get("edition_display", "")
            vol = vol or derived.get("volume", "")
            title_std = derived.get("title_standardized", "")

    # Paso B: pasar el series_key/display por el aliases.yml resolver. Esto
    # consolida traducciones multilingües (Demon Slayer = Kimetsu no Yaiba =
    # 鬼滅の刃 = Guardianes de la Noche) a la canonical key.
    if canonical_series_key is not None and (sk or sd):
        new_sk, new_sd = canonical_series_key(candidate.title, sk, sd)
        if ek.startswith(sk + "-") and new_sk != sk:
            ek = new_sk + ek[len(sk):]
        sk, sd = new_sk, new_sd

    # Paso C: escribir al row final
    if sk:
        row["series_key"] = sk
    if sd:
        row["series_display"] = sd
    if ek:
        row["edition_key"] = ek
    if ed:
        row["edition_display"] = ed
    if vol:
        row["volume"] = vol
    # No re-escribimos el title si ya viene seteado; el `title_standardized`
    # de la heurística queda como reference pero no overridea el title scrapeado.
    # El skill /standardize-catalog es el que reescribe título al merge.

    # Paso D: si el series_key NO está en aliases.yml, loguearlo al unmapped
    # queue para que el skill enrich-series-aliases lo procese.
    if log_unmapped_series is not None and sk and is_canonical_key is not None:
        if not is_canonical_key(sk):
            log_unmapped_series(
                series_key=sk,
                series_display=sd,
                title=candidate.title,
                url=candidate.url,
                source=candidate.source,
            )
    return row


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
        self._entries_lock = threading.Lock()
        # `current` mantiene compatibilidad con código serial existente
        # (e.g. wiki bootstraps). En el loop principal paralelo cada worker
        # maneja su propio `entry` explícitamente.
        self.current: dict[str, Any] | None = None
        self.run_started_at = dt.datetime.now()

    def _target(self, entry: dict[str, Any] | None) -> dict[str, Any] | None:
        """Devuelve el entry a mutar: el explícito si se pasa, si no self.current."""
        return entry if entry is not None else self.current

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
        with self._entries_lock:
            self.entries.append(entry)
        return entry

    def record_fetch(
        self, metadata: dict[str, Any], html_text: str,
        entry: dict[str, Any] | None = None,
    ) -> None:
        e = self._target(entry)
        if not self.enabled or e is None:
            return
        e["http_status"] = metadata.get("http_status")
        e["content_type"] = metadata.get("content_type", "")
        e["fetch_ms"] = metadata.get("fetch_ms")
        e["html_size"] = len(html_text or "")

    def record_anchor_counts(
        self, soup: BeautifulSoup, entry: dict[str, Any] | None = None,
    ) -> None:
        e = self._target(entry)
        if not self.enabled or e is None:
            return
        all_anchors = soup.find_all("a", href=True)
        significant = 0
        for anchor in all_anchors:
            if len(clean_text(anchor.get_text(" ", strip=True))) >= 10:
                significant += 1
        e["anchor_count"] = len(all_anchors)
        e["anchor_count_significant"] = significant

    def record_status(
        self, status: str, message: str = "",
        entry: dict[str, Any] | None = None,
    ) -> None:
        e = self._target(entry)
        if not self.enabled or e is None:
            return
        e["status"] = status
        if message:
            e["error"] = message

    def record_error(
        self, exc: Exception, entry: dict[str, Any] | None = None,
    ) -> None:
        e = self._target(entry)
        if not self.enabled or e is None:
            return
        e["status"] = e.get("status") or "other"
        e["error"] = f"{type(exc).__name__}: {exc}"

    def record_candidates(
        self, candidates: list[Candidate], entry: dict[str, Any] | None = None,
    ) -> None:
        e = self._target(entry)
        if not self.enabled or e is None:
            return
        scored_with_signals = [c for c in candidates if c.score > 0]
        e["candidates_after_scoring"] = len(scored_with_signals)
        top = sorted(scored_with_signals, key=lambda c: c.score, reverse=True)[:5]
        e["top_titles"] = [
            {"score": c.score, "title": c.title[:160], "url": c.url} for c in top
        ]
        seen_signals: list[str] = []
        for c in top:
            for sig in c.signals:
                if sig not in seen_signals:
                    seen_signals.append(sig)
        e["top_signals"] = seen_signals[:10]

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

    def end(self, entry: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Finaliza el status del entry y lo devuelve.

        Si `entry` se pasa explícitamente, se usa ese (thread-safe). Si no,
        cae al self.current global (compat con código serial)."""
        target = entry if entry is not None else self.current
        if not self.enabled or target is None:
            if entry is None:
                self.current = None
            return None
        if target.get("status") == "pending":
            if target.get("candidates_after_scoring", 0) > 0:
                target["status"] = "ok"
            else:
                target["status"] = "no-candidates"
        if entry is None:
            self.current = None
        return target

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


def mirror_candidate_images(
    candidates: list[Candidate],
    data_dir: Path,
    session: requests.Session,
    workers: int = 1,
    timeout: tuple[int, int] = (10, 30),
) -> tuple[int, int]:
    """Espejo local de portadas (Image storage, Fase 1).

    Descarga a `data/images/` la portada de cada candidate nuevo/cambiado
    que tenga `image_url` y todavía no tenga `image_local`. Setea
    `candidate.image_local` con el filename local. `image_url` queda
    intacto como provenance + fallback.

    Idempotente: si la imagen ya está en disco, `download_image` la
    reusa sin tocar la red. Falla siempre de forma elegante — un fallo
    de descarga sólo deja `image_local` vacío.

    Devuelve (descargadas_ok, fallidas).
    """
    try:
        import image_store
    except ImportError:
        return (0, 0)

    # Cover (image_url) targets — comportamiento previo.
    cover_targets = [
        c for c in candidates
        if c.status in {"new", "changed"} and c.image_url and not c.image_local
    ]
    # images[] extras (Fase 2 listadomanga-collections): cada elemento
    # con kind != cover y sin `local` poblado se mira como target. Cada
    # tarea descarga UNA imagen extra de UN Candidate.
    extra_targets: list[tuple[Candidate, int]] = []
    for c in candidates:
        if c.status not in {"new", "changed"}:
            continue
        imgs = getattr(c, "images", None) or []
        for idx, im in enumerate(imgs):
            if im.get("kind") == "cover":
                continue  # cover ya cubierta por image_url
            if im.get("url") and not im.get("local"):
                extra_targets.append((c, idx))

    if not cover_targets and not extra_targets:
        return (0, 0)

    images_dir = data_dir / image_store.IMAGES_DIRNAME

    def _one_cover(cand: Candidate) -> tuple[Candidate, str]:
        filename = image_store.download_image(
            cand.image_url, images_dir, session=session,
            timeout=timeout, referer=cand.url or cand.source_url,
        )
        return cand, filename

    def _one_extra(args: tuple[Candidate, int]) -> tuple[Candidate, int, str]:
        cand, idx = args
        im = cand.images[idx]
        filename = image_store.download_image(
            im["url"], images_dir, session=session,
            timeout=timeout, referer=cand.url or cand.source_url,
        )
        return cand, idx, filename

    cover_results: list[tuple[Candidate, str]] = []
    extra_results: list[tuple[Candidate, int, str]] = []
    if workers <= 1:
        cover_results = [_one_cover(c) for c in cover_targets]
        extra_results = [_one_extra(t) for t in extra_targets]
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="image") as pool:
            futs = [pool.submit(_one_cover, c) for c in cover_targets]
            futs.extend(pool.submit(_one_extra, t) for t in extra_targets)
            for fut in as_completed(futs):
                res = fut.result()
                if len(res) == 2:
                    cover_results.append(res)
                else:
                    extra_results.append(res)

    downloaded = 0
    failed = 0
    for cand, filename in cover_results:
        if filename:
            cand.image_local = filename
            # Sincronizar también en images[] si existe el cover ahí.
            for im in (getattr(cand, "images", None) or []):
                if im.get("kind") == "cover" and im.get("url") == cand.image_url:
                    im["local"] = filename
                    break
            downloaded += 1
        else:
            failed += 1
    for cand, idx, filename in extra_results:
        if filename:
            cand.images[idx]["local"] = filename
            downloaded += 1
        else:
            failed += 1
    return (downloaded, failed)


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
    elif args.bootstrap_wiki == "listadomanga-blog":
        from wikis.listadomanga_blog import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "whakoom":
        from wikis.whakoom import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "manga-sanctuary":
        from wikis.manga_sanctuary import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "otaku-calendar":
        from wikis.otaku_calendar import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "manga-mexico":
        from wikis.manga_mexico import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "mangavariant":
        from wikis.mangavariant import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "socialanime":
        from wikis.socialanime import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "blogbbm":
        from wikis.blogbbm import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "listadomanga-collections":
        from wikis.listadomanga_collections import bootstrap as wiki_bootstrap, iter_year_months
    else:
        raise SystemExit(f"Wiki no soportada: {args.bootstrap_wiki}")

    # Kwargs extra solo aplicables a ciertas wikis (ej. listadomanga-collections
    # itera por id en vez de por fecha). El resto las ignora vía **kwargs.
    extra_kwargs: dict[str, Any] = {}
    if args.bootstrap_wiki == "listadomanga-collections":
        extra_kwargs = {
            "id_from": int(getattr(args, "coleccion_from", 1) or 1),
            "id_to": int(getattr(args, "coleccion_to", 6500) or 6500),
            "mode": str(getattr(args, "coleccion_mode", "lista") or "lista"),
        }

    candidates = wiki_bootstrap(
        yf, mf, yt, mt,
        session=session,
        sleep_seconds=args.sleep_seconds,
        timeout=(args.connect_timeout, args.read_timeout),
        min_score=args.min_score,
        fetch_details=bool(args.fetch_details),
        **extra_kwargs,
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
        if not getattr(args, "skip_image_download", False):
            _wk = max(1, int(getattr(args, "workers", 1) or 1))
            dl, fail = mirror_candidate_images(
                reportable, items_path.parent, session,
                workers=_wk, timeout=(args.connect_timeout, args.read_timeout),
            )
            print(f"[IMAGES] {dl} portadas al espejo local data/images/ ({fail} fallidas)")
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
                cand.title, cand.description,
                tags=cand.tags, source_purity=source.purity,
                publisher=cand.publisher or source.publisher,
                url=cand.url,
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
        if not getattr(args, "skip_image_download", False):
            _wk = max(1, int(getattr(args, "workers", 1) or 1))
            dl, fail = mirror_candidate_images(
                reportable, items_path.parent, session,
                workers=_wk, timeout=(args.connect_timeout, args.read_timeout),
            )
            print(f"[IMAGES] {dl} portadas al espejo local data/images/ ({fail} fallidas)")
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

    print(f"[INFO] Fuentes totales en YAML: {len(sources_all)}")
    print(f"[INFO] Fuentes activas tras filtros: {len(sources)}")
    print(f"[INFO] Score mínimo: {args.min_score}")
    print(f"[INFO] Clases: {args.source_classes or 'todas'}")
    print(f"[INFO] Países: {args.countries or 'todos'}")
    print(f"[INFO] Respetar robots.txt: {args.respect_robots}")

    workers = max(1, int(getattr(args, "workers", 1) or 1))
    per_host_limit = max(1, int(getattr(args, "per_host_limit", 2) or 2))
    if workers > 1:
        print(f"[INFO] Concurrencia: workers={workers}, per-host-limit={per_host_limit}")

    # Per-host semaphore para no martillar el mismo dominio bajo concurrencia.
    host_semaphores: dict[str, threading.Semaphore] = defaultdict(
        lambda: threading.Semaphore(per_host_limit)
    )
    host_locks_lock = threading.Lock()
    # Playwright sync NO es thread-safe (greenlets bound al thread inicial).
    # NO usamos un lock manual: `fetch_with_playwright` despacha jobs al
    # dedicated `_PLAYWRIGHT_WORKER` thread via queue, que serializa
    # naturalmente y garantiza que todas las llamadas corren en el thread
    # dueño del greenlet event loop. Ver comentario en
    # `_playwright_worker_loop` arriba.
    print_lock = threading.Lock()

    def _safe_print(line: str) -> None:
        with print_lock:
            print(line)

    def _host_sem_for(url: str) -> threading.Semaphore:
        host = (urlparse(url).hostname or "").lower()
        with host_locks_lock:
            return host_semaphores[host]

    def _scrape_one(index: int, source: Source) -> dict[str, Any]:
        """Ejecuta el scrape completo de una fuente. Thread-safe.

        Devuelve dict con: candidates, errors, problems, text (último HTML
        fetcheado para dump diagnóstico), entry (DiagnosticRecorder entry o
        None)."""
        local_errors: list[str] = []
        local_problems: list[dict[str, str]] = []
        local_candidates: list[Candidate] = []
        text = ""
        entry = diagnostic.begin(source) if diagnostic.enabled else None
        _safe_print(f"[{index}/{len(sources)}] {source.name} :: {source.url}")

        def _record_problem(category: str, message: str) -> None:
            local_problems.append({"source": source.name, "category": category, "message": message})

        try:
            if args.respect_robots and not robots.allowed(source.url):
                message = f"robots.txt no permite acceder a {source.url}"
                _safe_print(f"[SKIP] {message}")
                local_errors.append(f"{source.name}: {message}")
                _record_problem("robots", message)
                diagnostic.record_status("robots", message, entry=entry)
                return {
                    "candidates": local_candidates, "errors": local_errors,
                    "problems": local_problems, "text": text, "entry": entry,
                }

            if source.kind in {"rss", "feed", "atom", "bluesky"}:
                effective_max_pages = 1
            elif source.max_pages > 0:
                effective_max_pages = source.max_pages
            else:
                effective_max_pages = args.max_pages

            if source.kind == "js":
                if not args.enable_js:
                    message = "Fuente kind:js requiere --enable-js (Playwright)"
                    _safe_print(f"[SKIP-js] {source.name}: {message}")
                    _record_problem("js-shell", message)
                    diagnostic.record_status("js-shell", message, entry=entry)
                    return {
                        "candidates": local_candidates, "errors": local_errors,
                        "problems": local_problems, "text": text, "entry": entry,
                    }
                if not _playwright_available():
                    message = "Playwright no instalado. Ver requirements-playwright.txt"
                    _safe_print(f"[ERROR] {source.name}: {message}")
                    local_errors.append(f"{source.name}: {message}")
                    _record_problem("other", message)
                    diagnostic.record_status("other", message, entry=entry)
                    return {
                        "candidates": local_candidates, "errors": local_errors,
                        "problems": local_problems, "text": text, "entry": entry,
                    }

            visited_urls: set[str] = set()
            current_url = source.url
            all_candidates_source: list[Candidate] = []
            pages_visited = 0
            skipped_for_js = False
            host_sem = _host_sem_for(source.url)

            for page_num in range(1, effective_max_pages + 1):
                visited_urls.add(current_url)
                pages_visited = page_num

                # Fetch con per-host semaphore (HTTP). Las fuentes kind:js
                # van por `fetch_with_playwright` que internamente despacha
                # al dedicated `_PLAYWRIGHT_WORKER` thread (sin lock manual
                # aquí; la queue del worker serializa los jobs JS).
                if source.kind == "js":
                    text, fetch_meta = fetch_with_playwright(
                        url=current_url,
                        timeout_ms=args.read_timeout * 1000,
                    )
                elif source.kind == "bluesky":
                    handle = bluesky_handle_from_url(current_url)
                    if not handle:
                        message = f"URL de Bluesky sin handle: {current_url}"
                        _safe_print(f"[ERROR] {source.name}: {message}")
                        local_errors.append(message)
                        _record_problem("bluesky-handle", message)
                        break
                    api_url = bluesky_api_url(handle, limit=args.max_items_per_source)
                    with _host_sem_for(api_url):
                        text, fetch_meta = fetch_with_metadata(
                            session=session,
                            url=api_url,
                            timeout=(args.connect_timeout, args.read_timeout),
                        )
                else:
                    with host_sem:
                        text, fetch_meta = fetch_with_metadata(
                            session=session,
                            url=current_url,
                            timeout=(args.connect_timeout, args.read_timeout),
                        )

                if page_num == 1:
                    diagnostic.record_fetch(fetch_meta, text, entry=entry)

                if source.kind in {"rss", "feed", "atom"}:
                    page_candidates = extract_rss(
                        source, text,
                        max_items=args.max_items_per_source,
                        max_age_days=args.max_age_days,
                    )
                    if diagnostic.enabled and entry is not None and page_num == 1:
                        entry["extraction_method"] = "rss"
                        entry["candidates_after_signals"] = len(page_candidates)
                    all_candidates_source.extend(page_candidates)
                    break

                if source.kind == "bluesky":
                    page_candidates = extract_bluesky_posts(
                        source, text,
                        max_items=args.max_items_per_source,
                        max_age_days=args.max_age_days,
                    )
                    if diagnostic.enabled and entry is not None and page_num == 1:
                        entry["extraction_method"] = "bluesky"
                        entry["candidates_after_signals"] = len(page_candidates)
                    all_candidates_source.extend(page_candidates)
                    break

                pre_soup = BeautifulSoup(text, "html.parser")
                for stripped in pre_soup(["script", "style", "noscript", "svg"]):
                    stripped.decompose()
                if page_num == 1:
                    diagnostic.record_anchor_counts(pre_soup, entry=entry)

                if source.kind == "js":
                    page_candidates = extract_generic_html(
                        source, text,
                        max_items=args.max_items_per_source,
                        info=entry if page_num == 1 else None,
                    )
                else:
                    js_check = detect_empty_or_js(text, pre_soup) if page_num == 1 else None
                    if js_check is not None:
                        category, message = js_check
                        _safe_print(f"[SKIP-{category}] {source.name}: {message}")
                        _record_problem(category, message)
                        diagnostic.record_status(category, message, entry=entry)
                        skipped_for_js = True
                        break
                    page_candidates = extract_generic_html(
                        source, text,
                        max_items=args.max_items_per_source,
                        info=entry if page_num == 1 else None,
                    )

                all_candidates_source.extend(page_candidates)

                if page_num >= effective_max_pages:
                    break
                next_url = find_next_page_url(pre_soup, current_url, visited_urls)
                if not next_url:
                    break
                # Pequeña pausa entre páginas del mismo sitio (solo aplica
                # cuando no estamos en paralelo — con concurrencia el host_sem
                # ya serializa requests al mismo dominio).
                if workers == 1 and args.sleep_seconds > 0:
                    time.sleep(min(args.sleep_seconds, 1.0))
                current_url = next_url

            if not skipped_for_js:
                scored = [score_candidate(candidate) for candidate in all_candidates_source]
                local_candidates.extend(scored)
                diagnostic.record_candidates(scored, entry=entry)
                if diagnostic.enabled and entry is not None:
                    entry["pages_visited"] = pages_visited
                pages_note = f" ({pages_visited} págs)" if pages_visited > 1 else ""
                _safe_print(f"    [{source.name[:30]:30s}] candidatos con señales: {len(scored)}{pages_note}")

        except requests.HTTPError as exc:
            message = f"{source.name}: HTTP error {exc}"
            _safe_print(f"[ERROR] {message}")
            local_errors.append(message)
            _record_problem("http", str(exc))
            diagnostic.record_status("http", str(exc), entry=entry)
        except requests.RequestException as exc:
            message = f"{source.name}: request error {exc}"
            _safe_print(f"[ERROR] {message}")
            local_errors.append(message)
            _record_problem("request", str(exc))
            diagnostic.record_status("request", str(exc), entry=entry)
        except Exception as exc:
            message = f"{source.name}: error inesperado {exc}"
            _safe_print(f"[ERROR] {message}")
            local_errors.append(message)
            _record_problem("other", str(exc))
            diagnostic.record_error(exc, entry=entry)

        return {
            "candidates": local_candidates, "errors": local_errors,
            "problems": local_problems, "text": text, "entry": entry,
        }

    if workers == 1:
        # Path serial: idéntico al comportamiento histórico.
        for index, source in enumerate(sources, start=1):
            result = _scrape_one(index, source)
            all_candidates.extend(result["candidates"])
            errors.extend(result["errors"])
            problems.extend(result["problems"])
            finalized = diagnostic.end(entry=result["entry"])
            diagnostic.maybe_dump_html(finalized, result["text"])
            if args.sleep_seconds > 0 and index < len(sources):
                time.sleep(args.sleep_seconds)
    else:
        # Path paralelo: ThreadPoolExecutor con per-host semaphore.
        # JS sources se serializan vía el dedicated _PLAYWRIGHT_WORKER
        # thread (queue interna); workers HTTP siguen paralelos.
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scrape") as pool:
            futures = {
                pool.submit(_scrape_one, idx, src): src
                for idx, src in enumerate(sources, start=1)
            }
            for fut in as_completed(futures):
                try:
                    result = fut.result()
                except Exception as exc:
                    src = futures[fut]
                    msg = f"{src.name}: error en worker {exc}"
                    _safe_print(f"[ERROR] {msg}")
                    errors.append(msg)
                    problems.append({"source": src.name, "category": "other", "message": str(exc)})
                    continue
                all_candidates.extend(result["candidates"])
                errors.extend(result["errors"])
                problems.extend(result["problems"])
                finalized = diagnostic.end(entry=result["entry"])
                diagnostic.maybe_dump_html(finalized, result["text"])

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

        def _fetch_one_detail(c: Candidate) -> tuple[Candidate, dict[str, str]]:
            """Worker thread-safe: solo hace HTTP + parsing, no muta nada."""
            host_sem = _host_sem_for(c.url)
            with host_sem:
                metadata = fetch_metadata_from_detail(
                    c.url, session, timeout=(args.connect_timeout, args.read_timeout)
                )
            return c, metadata

        def _apply_metadata(idx: int, c: Candidate, metadata: dict[str, str]) -> None:
            """Aplica metadata al candidate y al state. Llamado SECUENCIALMENTE."""
            nonlocal enriched_author, enriched_image
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
                _safe_print(f"  [{idx}/{len(eligible)}] {c.source[:30]:30s} → {', '.join(updates)}")
            else:
                _safe_print(f"  [{idx}/{len(eligible)}] {c.source[:30]:30s} → (sin cambios)")

        if workers == 1:
            for idx, c in enumerate(eligible, start=1):
                try:
                    _, metadata = _fetch_one_detail(c)
                except Exception as exc:
                    _safe_print(f"  [{idx}/{len(eligible)}] {c.source[:30]:30s} → ERROR: {exc}")
                    metadata = {}
                _apply_metadata(idx, c, metadata)
                if args.sleep_seconds > 0 and idx < len(eligible):
                    time.sleep(min(args.sleep_seconds, 1.0))
        else:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="detail") as pool:
                futures = {pool.submit(_fetch_one_detail, c): (idx, c)
                           for idx, c in enumerate(eligible, start=1)}
                for fut in as_completed(futures):
                    idx, c = futures[fut]
                    try:
                        _, metadata = fut.result()
                    except Exception as exc:
                        _safe_print(f"  [{idx}/{len(eligible)}] {c.source[:30]:30s} → ERROR: {exc}")
                        metadata = {}
                    _apply_metadata(idx, c, metadata)

        print(
            f"[FETCH-DETAILS] {enriched_author} autores · {enriched_image} imágenes enriquecidas"
        )

    if not args.dry_run:
        save_state(state_path, state)
        # Espejo local de portadas (Image storage, Fase 1): descarga la
        # imagen de cada item nuevo/cambiado a data/images/ y guarda el
        # filename en image_local. Ver "Image storage" en CLAUDE.md.
        if not args.skip_image_download:
            dl, fail = mirror_candidate_images(
                reportable, data_dir, session,
                workers=workers, timeout=(args.connect_timeout, args.read_timeout),
            )
            print("")
            print(f"[IMAGES] {dl} portadas descargadas al espejo local data/images/ ({fail} fallidas)")
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
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Cantidad de fuentes a procesar en paralelo. Default: 1 (serial — comportamiento histórico). "
             "Recomendado: 6-8 para overnight runs (corta phase 1 de ~25min a ~5min). kind:js se serializa "
             "internamente porque Playwright sync no es thread-safe.",
    )
    parser.add_argument(
        "--per-host-limit", type=int, default=2,
        help="Bajo --workers > 1, máximo de requests concurrentes al mismo dominio. Default: 2. "
             "Sube si tu red lo permite y los retailers no rate-limitean; baja a 1 para sitios sensibles.",
    )
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
        "--skip-image-download",
        action="store_true",
        help="No descarga las portadas al espejo local data/images/ (Image "
             "storage Fase 1). Por defecto el scrape sí las descarga. Útil "
             "para corridas de prueba rápidas.",
    )
    parser.add_argument(
        "--bootstrap-wiki",
        choices=["listadomanga", "listadomanga-blog", "whakoom", "manga-sanctuary", "otaku-calendar", "manga-mexico", "mangavariant", "socialanime", "blogbbm", "listadomanga-collections"],
        help="En lugar de scrapear las fuentes del YAML, importa items de una wiki comunitaria. Soporta: listadomanga (calendario ES), listadomanga-blog (archivo histórico del blog ES — anuncios/exclusivas, complementa el feed RSS), whakoom (spider 3 niveles desde /newtitles → /comics/ → /ediciones/ con variantes), manga-sanctuary (Francia), otaku-calendar (EN/US, por mes), manga-mexico (catálogo MX por editorial), mangavariant (base global de variants/ediciones, 13 países — ignora --wiki-from/--wiki-to, importa todo el sitemap), socialanime (MangaStore italiano: variant/limited/special editions + cofanetti, ~840 items vía JSON feed), blogbbm (Biblioteca Brasileira de Mangás: dos posts curados — capas variantes + volúmenes con extras — actualizados continuamente), listadomanga-collections (parser por colección individual coleccion.php?id=N — ediciones especiales/portadas alternativas/packs/formato premium; usa --coleccion-from y --coleccion-to en vez del rango de fechas).",
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
        "--coleccion-from",
        type=int,
        default=1,
        help="Id inicial de la iteración para --bootstrap-wiki listadomanga-collections. Default: 1.",
    )
    parser.add_argument(
        "--coleccion-to",
        type=int,
        default=6500,
        help="Id final de la iteración para --bootstrap-wiki listadomanga-collections SOLO si --coleccion-mode=range. En el modo 'lista' (default) este flag se ignora.",
    )
    parser.add_argument(
        "--coleccion-mode",
        choices=["lista", "range"],
        default="lista",
        help="Discovery para --bootstrap-wiki listadomanga-collections. 'lista' (default): usa lista.php como índice oficial alfabético (~3432 colecciones activas, modo recomendado). 'range': iteración numérica id_from..id_to (legacy, útil para re-procesar rangos específicos como ids problemáticos detectados en UNKNOWN h2).",
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
