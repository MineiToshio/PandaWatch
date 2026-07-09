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

Config opcional por fuente (sources.yml):
- user_agent: UA HTTP browser-like específico para esa fuente (para fuentes con
  anti-bot agresivo que rechazan el UA por defecto). Se aplica por-request, sin
  mutar la sesión compartida. Ver Source.user_agent / fetch_with_metadata.

Anti-bot: un 200 OK que en realidad es un challenge de Cloudflare/WAF se detecta
con detect_challenge() y se trata como FALLO de fuente (log CHALLENGE_DETECTED),
no como 0 items silencioso. Ante un 403 se hace un reintento único con UA
browser-like alternativo + backoff; si persiste, se loguea BLOCKED_403 y se
abandona la fuente (NO se reintenta en loop — escala el bloqueo).
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Iterable
from typing import Any
from urllib.parse import urljoin, urlparse, urldefrag, quote_plus
from urllib.robotparser import RobotFileParser

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Algunos sitios (egmont-shop.de) responden con >100 headers HTTP (decenas de
# Set-Cookie) y el default de http.client aborta con "got more than 100
# headers". Subir el límite es inocuo y desbloquea esas fuentes.
import http.client
http.client._MAXHEADERS = 200
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


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
    {"phrase": "coleccionista", "score": 32, "type": "collector"},
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
    {"phrase": "kanzenban", "score": 35, "type": "premium_format"},
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
    {"phrase": "regalos", "score": 20, "type": "bonus"},
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
    {"phrase": "collector", "score": 32, "type": "collector"},
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
    {"phrase": "beaux livres", "score": 30, "type": "artbook"},
    {"phrase": "livre d'illustration", "score": 35, "type": "artbook"},
    {"phrase": "livre d’illustration", "score": 35, "type": "artbook"},
    {"phrase": "artbook luxe", "score": 45, "type": "artbook"},
    # Vocabulario artbook FR de la línea Glénat (fuente "FR - Glénat Art Books").
    # "l'art de X" (normalize_text ya colapsa el apóstrofo curvo a ASCII, así que
    # una sola forma cubre "L'Art de Berserk" / "L’Art de …"). "super art book" y
    # "color walk" son series de artbooks concretas (Dragon Ball, One Piece).
    {"phrase": "l'art de", "score": 35, "type": "artbook"},
    {"phrase": "super art book", "score": 45, "type": "artbook"},
    {"phrase": "color walk", "score": 35, "type": "artbook"},

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

    # -------------------------
    # Alemán (fuentes directas DE 2026-06-12: altraverse, Egmont, TOKYOPOP,
    # Carlsen — antes Alemania entraba solo vía wiki Manga-Passion)
    # -------------------------
    {"phrase": "limitierte auflage", "score": 45, "type": "limited"},
    {"phrase": "streng limitiert", "score": 45, "type": "limited"},
    {"phrase": "limitiert", "score": 32, "type": "limited"},
    {"phrase": "sammelschuber", "score": 45, "type": "box_set"},
    {"phrase": "sammelbox", "score": 40, "type": "box_set"},
    {"phrase": "schuber", "score": 35, "type": "box_set"},
    {"phrase": "mit box", "score": 35, "type": "box_set"},
    {"phrase": "luxusausgabe", "score": 45, "type": "premium_format"},
    {"phrase": "luxury edition", "score": 40, "type": "premium_format"},
    {"phrase": "jubiläumsedition", "score": 40, "type": "collector"},
    {"phrase": "jubilaeumsedition", "score": 40, "type": "collector"},
    {"phrase": "erstauflage", "score": 20, "type": "bonus"},

    # -------------------------
    # Polaco (fuentes PL 2026-06-12: Mangarden/JPF, Mangastore)
    # -------------------------
    {"phrase": "edycja specjalna", "score": 40, "type": "special_edition"},
    {"phrase": "edycja limitowana", "score": 45, "type": "limited"},
    {"phrase": "wydanie limitowane", "score": 45, "type": "limited"},
    {"phrase": "edycja kolekcjonerska", "score": 45, "type": "collector"},
    {"phrase": "oprawa twarda", "score": 35, "type": "hardcover"},
    {"phrase": "twarda oprawa", "score": 35, "type": "hardcover"},
    {"phrase": "twarda okładka", "score": 35, "type": "hardcover"},
    {"phrase": "twarda okladka", "score": 35, "type": "hardcover"},
    {"phrase": "barwione brzegi", "score": 25, "type": "finish"},

    # -------------------------
    # Turco (fuente TR 2026-06-12: Gerekli Şeyler)
    # -------------------------
    {"phrase": "varyant kapak", "score": 40, "type": "variant_cover"},
    {"phrase": "varyant", "score": 30, "type": "variant_cover"},
    {"phrase": "özel edisyon", "score": 40, "type": "special_edition"},
    {"phrase": "kuşe kağıt", "score": 25, "type": "premium_format"},

    # -------------------------
    # Checo (fuente CZ 2026-06-12: Crew)
    # -------------------------
    {"phrase": "limitovaná edice", "score": 45, "type": "limited"},
    {"phrase": "limitovana edice", "score": 45, "type": "limited"},
    {"phrase": "limitovaná verze", "score": 45, "type": "limited"},
    {"phrase": "limitovana verze", "score": 45, "type": "limited"},
    {"phrase": "sběratelský box", "score": 45, "type": "box_set"},
    {"phrase": "sberatelsky box", "score": 45, "type": "box_set"},

    # -------------------------
    # Vietnamita (fuentes VN 2026-06-12: Kim Đồng, IPM)
    # -------------------------
    {"phrase": "bản đặc biệt", "score": 45, "type": "special_edition"},
    {"phrase": "ban dac biet", "score": 45, "type": "special_edition"},
    {"phrase": "bản giới hạn", "score": 45, "type": "limited"},
    {"phrase": "ban gioi han", "score": 45, "type": "limited"},
    {"phrase": "bản sưu tầm", "score": 45, "type": "collector"},
    {"phrase": "ban suu tam", "score": 45, "type": "collector"},
    {"phrase": "có box", "score": 35, "type": "box_set"},

    # -------------------------
    # Tailandés (fuente TH 2026-06-12: yaakz/Siam Inter)
    # -------------------------
    {"phrase": "ชุดพิเศษ", "score": 40, "type": "special_edition"},
    {"phrase": "ฉบับพิเศษ", "score": 40, "type": "special_edition"},
    {"phrase": "ฉบับจำกัด", "score": 45, "type": "limited"},
    {"phrase": "บ็อกซ์เซ็ต", "score": 40, "type": "box_set"},

    # -------------------------
    # Coreano (fuente KR 2026-06-12: Aladin — 한정판 son LEs de fábrica
    # con ISBN propio, no tomo+regalo de tienda)
    # -------------------------
    {"phrase": "한정판", "score": 50, "type": "limited"},
    {"phrase": "초회한정", "score": 50, "type": "limited"},
    {"phrase": "특별판", "score": 40, "type": "special_edition"},
    {"phrase": "특장판", "score": 45, "type": "special_edition"},
    {"phrase": "박스 세트", "score": 40, "type": "box_set"},
    {"phrase": "박스판", "score": 40, "type": "box_set"},
    {"phrase": "아트웍스", "score": 40, "type": "artbook"},
    {"phrase": "아트북", "score": 35, "type": "artbook"},
    {"phrase": "화집", "score": 40, "type": "artbook"},
    {"phrase": "포토카드", "score": 25, "type": "bonus"},
    {"phrase": "아크릴", "score": 25, "type": "bonus"},

    # -------------------------
    # Chino (fuentes TW/HK 2026-06-12: Tong Li, Kadokawa TW, SPP, Jade
    # Dynasty HK). OJO: el chino TRADICIONAL usa 裝 (no 装 como el JP) —
    # ambas variantes donde aplica. 首刷限定版 = "primera tirada limitada
    # con extras", LA señal taiwanesa típica.
    # -------------------------
    {"phrase": "首刷限定版", "score": 50, "type": "limited"},
    {"phrase": "首刷附錄版", "score": 45, "type": "bonus"},
    {"phrase": "畫展限定版", "score": 50, "type": "limited"},
    {"phrase": "限定版", "score": 50, "type": "limited"},     # ya cubre JP; repetido es inocuo
    {"phrase": "特裝版", "score": 50, "type": "special_edition"},  # tradicional (TW/HK)
    {"phrase": "典藏版", "score": 45, "type": "premium_format"},
    {"phrase": "珍藏版", "score": 45, "type": "premium_format"},
    {"phrase": "愛藏版", "score": 45, "type": "premium_format"},   # ≈ aizōban
    {"phrase": "盒裝套書", "score": 45, "type": "box_set"},
    {"phrase": "盒裝", "score": 40, "type": "box_set"},
    {"phrase": "完全版", "score": 35, "type": "premium_format"},
    {"phrase": "復刻版", "score": 35, "type": "premium_format"},
    {"phrase": "官網限定", "score": 45, "type": "retailer_exclusive"},
    {"phrase": "畫集", "score": 40, "type": "artbook"},            # tradicional de 画集

    # -------------------------
    # Portugués (PT-BR — Panini/JBC/NewPOP Brasil). normalize_text hace NFKD +
    # strip de acentos, así que "edição"→"edicao" matchea con o sin acento; no
    # hace falta duplicar la forma ASCII. "brindes" (freebies) es portugués, se
    # movió acá desde la sección ES.
    # -------------------------
    {"phrase": "edição limitada", "score": 45, "type": "limited"},
    {"phrase": "edição especial", "score": 40, "type": "special_edition"},
    {"phrase": "edição de colecionador", "score": 45, "type": "collector"},
    {"phrase": "edição definitiva", "score": 38, "type": "premium_format"},
    {"phrase": "capa dura", "score": 35, "type": "hardcover"},
    # NOTA: "box" suelto NO es una regla de frase — un token "box" desnudo
    # matchea nombres propios ("Blue Box", editorial "Black Box") y disparaba
    # box_set en tomos regulares (run 2026-07-07). El token "box" se detecta
    # SOLO en construcción de producto vía `_BOX_CONSTRUCTION_RE` (abajo). Las
    # variantes con keyword propia (box set, boxset, coffret, cofanetto, cofre,
    # slipcase, mit box, có box, 박스…) siguen por sus reglas dedicadas.
    {"phrase": "luva", "score": 40, "type": "box_set"},
    {"phrase": "estojo", "score": 40, "type": "box_set"},
    {"phrase": "caixa", "score": 35, "type": "box_set"},
    {"phrase": "sobrecapa", "score": 25, "type": "bonus"},
    {"phrase": "brindes", "score": 20, "type": "bonus"},
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
    # user_agent: UA HTTP específico para ESTA fuente (opcional, sources.yml
    # `user_agent:`). Algunas fuentes con anti-bot agresivo requieren un UA
    # browser-like distinto del UA por defecto del proyecto. Se aplica
    # por-request al fetchear la fuente (NO muta la sesión compartida entre
    # threads). Vacío = usar el UA de la sesión.
    user_agent: str = ""
    # throttle_group: fuentes que resuelven a la MISMA infraestructura compartida
    # (p. ej. varias tiendas Shopify tras el borde 23.227.38.0/24) comparten el
    # rate-limit remoto → un 429 en una golpea a todas. Las fuentes con el mismo
    # `throttle_group` comparten UN semáforo (limit 1) + un delay mínimo entre
    # requests del grupo, en vez de agruparse sólo por hostname. Vacío = se agrupa
    # por host como siempre. Ver ThrottleRegistry.
    throttle_group: str = ""


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
    # image_url / image_local son campos RUNTIME del Candidate (input del
    # scraper + output del mirror). NO se persisten como campos top-level del
    # row: candidate_to_json los convierte en images[0]. image_local es el
    # filename del espejo en data/images/, vacío hasta que mirror_candidate_images
    # lo descarga. Ver "Image storage" en CLAUDE.md / docs/reference/images.md.
    image_url: str = ""
    image_local: str = ""
    # images: carrusel de imágenes asociadas al item. Cada elemento es
    # {url, local, kind, description} donde kind ∈ {gallery, extra}.
    # images[0] es la portada (por posición, no por kind) y es la ÚNICA fuente
    # de verdad de la portada en el row persistido (decisión 2026-06-09). Cuando
    # hay más de un elemento el dashboard renderiza un carrusel.
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
    # Status de tienda como prefijo: "(PRE-ORDER) …", "(พรีออเดอร์) …" (IPM/Siam TH).
    re.compile(r"^\s*\(\s*(?:PRE-?ORDER|พรีออเดอร์)\s*\)\s*", re.IGNORECASE),
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
    # Tiendanube/Cúspide AR — variante del botón wishlist: "Agregar a mi lista
    # de deseos!" pegado al inicio del card. Mismo patrón que el de Panini ES.
    re.compile(r"^Agregar\s+a\s+mi\s+lista\s+de\s+deseos!?\s*", re.IGNORECASE),
    # Pipoca & Nanquim (BR Magento) — botón "Lista de desejos" prefijo equivalente
    # al de Panini ES. También cubre "Adicionar à Lista" genérico de Magento BR.
    re.compile(r"^Lista\s+de\s+desejos\s+", re.IGNORECASE),
    re.compile(r"^Adicionar\s+(?:à|a)\s+lista(?:\s+de\s+desejos)?\s+", re.IGNORECASE),
    # Aladin KR — el card de búsqueda empieza con "N. 크게보기 [국내도서]"
    # (posición + botón "ver grande" + tag "libro nacional"). El número va
    # anclado a 크게보기 para no comer números legítimos de inicio de título.
    re.compile(r"^\d{1,3}\.\s*크게보기\s*"),
    re.compile(r"^크게보기\s*"),
    re.compile(r"^\[국내도서\]\s*"),
)

# Prefijos de botón "leer más" que el scraper captura cuando el selector toma
# el wrapper completo del producto (el CTA queda incluido en el texto del nodo).
# Afectan `description` (y por ende `description_es`). Gotcha #37.
DESCRIPTION_JUNK_PREFIXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^EN\s+SAVOIR\s+PLUS\s*", re.IGNORECASE),   # FR Meian
    re.compile(r"^MÁS\s+INFORMACIÓN\s*", re.IGNORECASE),    # ES genérico
    re.compile(r"^LEER\s+MÁS\s*", re.IGNORECASE),           # ES genérico
    re.compile(r"^VER\s+MÁS\s*", re.IGNORECASE),            # ES genérico
    re.compile(r"^APRENDE\s+MÁS\s*", re.IGNORECASE),        # ES (variante traducción)
    re.compile(r"^READ\s+MORE\s*", re.IGNORECASE),           # EN genérico
    re.compile(r"^MEHR\s+ERFAHREN\s*", re.IGNORECASE),      # DE genérico
    re.compile(r"^SCOPRI\s+DI\s+PIÙ\s*", re.IGNORECASE),   # IT genérico
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
    # Funside.it y similares italianos: botones "Aggiungi al carrello [Confrontare]"
    # capturados como PREFIX del título por el listing extractor genérico.
    re.compile(r"^Aggiungi\s+al\s+carrello\s+(?:Confrontare\s+)?", re.IGNORECASE),
    re.compile(r"^Confrontare\s+", re.IGNORECASE),
    # Funside: nombre de la tienda pegado como SUFIJO ("… VARIANT GAMES ACADEMY
    # FUNSIDE", "… VARIANT FUNSIDE/ POPSTORE"). No es parte del nombre oficial.
    re.compile(r"\s+(?:GAMES\s+ACADEMY\s+)?FUNSIDE(?:\s*/\s*POPSTORE)?\s*$", re.IGNORECASE),
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
    # E-commerce italiano (Funside/Shopify): "<title> Prezzo normale €X Prezzo
    # di vendita €X Prezzo unitario / per Aggiungi al carrello". El selector
    # genérico captura toda la tarjeta; cortamos desde el bloque de precio.
    re.compile(r"\s+Prezzo\s+(?:normale|di\s+vendita|unitario|scontato)\b.*$", re.IGNORECASE),
    # Dynit y similares: "<title> #03 Disponibile dal: DD/MM/YYYY Dynit".
    re.compile(r"\s+Disponibile\s+dal\s*:.*$", re.IGNORECASE),
    # Badge "[NEW]" embebido (IPM/Siam TH): consume el espacio que lo PRECEDE y
    # deja el de después, para no pegar las palabras vecinas.
    re.compile(r"\s*\[\s*NEW\s*\]", re.IGNORECASE),
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


_HANGUL_RE = re.compile(r"[가-힣]")
# Retailers coreanos (Aladin/Hansan vía búsqueda "만화 한정판"): el selector
# captura la tarjeta entera — "{título} {vol} (한정판) - {bonus} {autor}(지은이) |
# {editorial}(만화) | {fecha} {precio} → {oferta} (할인), 마일리지 {x} 원 …
# 세일즈포인트 : …". El nombre OFICIAL termina en el marcador de edición
# "(…한정판)" / "한정판 [박스] [세트]"; todo lo demás es bonus + metadata de tienda.
_KR_EDITION_CUT = re.compile(r"(한정판\s*\)?(?:\s*박스)?(?:\s*세트)?).*$")
# Fallback (títulos coreanos SIN marcador de edición): cortar desde el primer
# marcador de rol de autor, el pipe de editorial "(만화) |", el precio "N원" o
# "세일즈포인트" — todo metadata inequívoca de la tienda.
_KR_META_TAIL = re.compile(
    r"\s*(?:\([^)]*?(?:지은이|옮긴이|원작|그림|감수|각색|글|엮은이)\)"
    r"|\|\s*[^|]+\(만화\)"
    r"|\d[\d,]*\s*원"
    r"|세일즈포인트).*$"
)


def _strip_korean_retailer_tail(title: str) -> str:
    """Quita la cola de tienda coreana (bonus + autor + editorial + precio +
    millas + sales-point) dejando el nombre oficial. Idempotente."""
    if "한정판" in title:
        cut = _KR_EDITION_CUT.sub(r"\1", title)
        if cut != title:
            stripped_cut = cut.strip()
            # Guard: si el recorte deja el título reducido al marcador de edición
            # desnudo ("한정판") o algo igual/más corto (vacío, solo el marcador),
            # NO recortar — conservar el título original. Sin esto, un título como
            # "한정판 <cola de tienda>" quedaba en "한정판" (3 chars) y luego lo
            # rechazaba is_collectible_edition por title_too_short (< 4), perdiendo
            # el item (caso vivo 2026-07-07).
            if stripped_cut and len(stripped_cut) > len("한정판"):
                return stripped_cut
            return title
    return _KR_META_TAIL.sub("", title).strip()


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
         `/watch-standardize-catalog` ve "nº" suelto y lo interpreta como parte
         del nombre (lo deja como "no" residual en title y series_key —
         gotcha #29).
    Iterando hasta estabilizar para que patrones cascading se resuelvan.
    """
    if not title:
        return title
    cleaned = _fix_mojibake(title)
    # Decodificar entidades HTML que el scraper no resolvió ("Collector&#039;s box",
    # "Girls &amp; Weapons" → "'", "&"). Idempotente.
    cleaned = html.unescape(cleaned)
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
        # Cola de tienda coreana (Aladin/Hansan): solo si hay Hangul.
        if _HANGUL_RE.search(cleaned):
            cleaned = _strip_korean_retailer_tail(cleaned)
        # Collapse whitespace tras posibles strips
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned == prev:
            break
    return cleaned


# Bonus de TIENDA (店舗特典) embebido en el título oficial JP — NO es el nombre
# del producto sino un perk de compra de UN retailer ("si compras en Rakuten te
# llevas una postal"). Va al campo `store_bonus` (visible en el detalle), NO en
# el `title` del grid (gotcha #93). Señal de ALTA precisión: el bracket japonés
# 【…特典…】 (特典 = "perk/bonus de compra"); 222 en el corpus, CERO con marcador
# de edición dentro. NO tocar 【…限定版/特装版/初回限定…】 (eso ES la edición), ni
# las colas de tienda en inglés de Mangavariant ("- Animate cover") que SÍ son
# la identidad de la variante.
_STORE_BONUS_EDITION_GUARD = re.compile(r"特装版|限定版|初回限定版|愛蔵版|完全版|通常版|特裝版|限定盤")
# Paréntesis que es SÓLO un marcador de volumen ("(3)", "(完)", "(上)", "(1-5巻)")
# — NO es descripción de bonus, no se consume aunque preceda al bracket 特典.
_VOLUME_PAREN_RE = re.compile(r"^[（(]\s*[\d０-９]+(?:\s*[-〜~]\s*[\d０-９]+)?\s*巻?\s*[）)]$"
                              r"|^[（(]\s*[完上中下前後初終]\s*[）)]$")
# Un bracket 【…特典…】, opcionalmente con su descripción adjacente entre
# paréntesis (full-width o half-width) inmediatamente ANTES que describe el
# contenido del bonus: "数学ゴールデン 2(描き下ろしイラストカード)【楽天ブックス限定特典】".
_STORE_BONUS_RE = re.compile(
    r"\s*(?P<paren>[（(][^）)]*[）)])?\s*【[^】]*特典[^】]*】"
)


def split_store_bonus(title: str) -> tuple[str, str]:
    """Devuelve (título sin el bonus de tienda, texto del bonus extraído).

    Sólo separa brackets 【…特典…】 (perk de compra de un retailer japonés), que
    no son parte del nombre oficial del producto. Conserva intactos los brackets
    que nombran la EDICIÓN (特装版/限定版/初回限定…) y los paréntesis que son sólo
    el volumen ("(3)"). Idempotente. Ver gotcha #93."""
    if not title or "特典" not in title:
        return title, ""
    bonuses: list[str] = []

    def _take(m: re.Match) -> str:
        frag = m.group(0)
        if _STORE_BONUS_EDITION_GUARD.search(frag):
            return frag  # el bracket nombra la edición → NO tocar
        paren = m.group("paren")
        if paren and _VOLUME_PAREN_RE.match(paren):
            # el paréntesis es el volumen, no la descripción del bonus: quitar
            # sólo el bracket 【…特典…】, conservar el volumen en el título.
            bracket = frag[frag.rindex("【"):]
            bonuses.append(bracket.strip())
            return paren
        bonuses.append(frag.strip())
        return " "

    cleaned = _STORE_BONUS_RE.sub(_take, title)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return (cleaned or title), " ".join(bonuses).strip()


def clean_description(desc: str) -> str:
    """Quita prefijos de botón 'leer más' capturados por el scraper (gotcha #37)."""
    if not desc:
        return desc
    cleaned = desc
    for pattern in DESCRIPTION_JUNK_PREFIXES:
        cleaned = pattern.sub("", cleaned).strip()
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


# URLs que son productos DIGITALES (ebooks), nunca ediciones físicas. PandaWatch
# cataloga ediciones físicas especiales — un ebook nunca califica. La búsqueda
# de Honto (`netstore/search.html`) mezcla resultados `/ebook/` (Kindle/digital)
# con los físicos; sin este filtro entraban al catálogo como falsos "限定版"
# (caso 2026-06-04: 7 items Honto, todos `/ebook/`, 4 con título-basura
# "〈autor〉 Work 限定版" del artefacto 作品). El patrón es por host+path para no
# rechazar otras URLs que contengan "ebook" en un slug legítimo.
_DIGITAL_ONLY_URL_PATTERNS: tuple[str, ...] = (
    "honto.jp/ebook/",
)


def is_digital_only_url(url: str) -> bool:
    """True si la URL es un producto puramente digital (ebook), no físico."""
    if not url:
        return False
    low = url.lower()
    return any(p in low for p in _DIGITAL_ONLY_URL_PATTERNS)


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


# Cuadernillo de ilustraciones (画集/イラスト集/アートワーク) ADJUNTO como bonus
# (付/つき/同梱/付属) — el producto es el tomo, no un artbook. Ver demotion en
# detect_signals (queja del owner 2026-06-04: tomos con "Artbook" en el título).
_ARTBOOK_BONUS_ATTACH_RE = re.compile(
    r"(画集|イラスト集|アートワーク)[^。]{0,8}?(付|つき|同梱|付属)"
)
# Frases artbook que designan un CUADERNILLO (no un artbook como producto). Si el
# artbook se detectó SOLO por estas (no por "art book"/"画集" standalone propio),
# y aparece adjunto como bonus, se demuele a `bonus`.
_ARTBOOK_BOOKLET_PHRASES = frozenset(
    normalize_text(p) for p in ("画集", "イラスト集", "アートワーク", "mini artbook")
)


# El token "box" desnudo matchea NOMBRES PROPIOS latinos — la editorial francesa
# "Black Box", la serie "Blue Box", "Tokyo Black Box" — y así disparaba box_set en
# decenas de tomos REGULARES (evidencia run 2026-07-07: 76 tomos de Manga-Sanctuary
# con publisher "Black Box" + "Blue Box" en 6 países). Mecanismo, no lista de series:
#
#   1. Construcción de producto en LATÍN (box + calificador, o "con box") → box_set.
#   2. Token "box" que NO forma un bigrama latino "<palabra> box" → box_set. Esto
#      preserva los boxes CJK (収納BOX, 特裝BOX, 全套收納BOX, 다용도BOX…) donde "BOX"
#      va pegado a un ideograma (no es un nombre propio latino) y era la ÚNICA señal.
#   3. Un bigrama latino "<palabra> box" SIN calificador de formato (Blue Box, Black
#      Box) → NO señala box_set (es el nombre de la serie/editorial).
#
# Las otras keywords de caja (box set/boxset/coffret/cofanetto/cofre/slipcase/
# mit box/có box/盒裝/박스…) tienen su propia regla y no dependen de esto.
_BOX_CONSTRUCTION_RE = re.compile(
    # box + calificador de formato después (NO "box vol/tomo/N" → eso es tomo regular)
    r"\bbox[\s\-]+(?:"
    r"set|sets|completo|completa|completos|completas|especial|deluxe|premium|"
    r"edition|edicion|edizione|collector|colecionador|colecionavel|"
    r"colecao|coleccao|coleccion|de|do|da|dos|das|com|con|ep"
    r")\b"
    # preposición "con/em/en box" (edición CON box) — mit/có ya tienen su regla
    r"|\b(?:com|con|em|en|avec)\s+box\b"
    # calificador de formato ANTES de box (NO colores/nombres propios: blue/black).
    # "Complete Box", "Deluxe Box", "Collector Box"… son cajas reales.
    r"|\b(?:complete|komplett|kompletn[iy]|completa|completo|deluxe|"
    r"collector|collectors|collezione|premium|storage|gift|slipcase)\s+box\b",
    re.IGNORECASE,
)
# Token "box" con word-boundary (mismo criterio que _build_phrase_pattern).
_BOX_TOKEN_RE = re.compile(r"(?<![a-z0-9])box(?![a-z0-9])")
_BOX_CONSTRUCTION_SCORE = 35

# "Colors" al FINAL del texto = artbook de ilustraciones a color de la línea
# manga ("<serie/autor> Colors": "Rumiko Takahashi Colors", "Ranma ½ Colors").
# Anclado a fin de `normalized` para NO disparar en tomos regulares que lleven
# "colors" en otra posición ("True Colors 3", "Colorful vol 2"): esos terminan en
# el número de tomo, no en "colors". normalize_text ya hizo casefold → sin flags.
_COLORS_ARTBOOK_RE = re.compile(r"(?:^|\s)colou?rs$")
_COLORS_ARTBOOK_SCORE = 30


def _box_set_signal_present(normalized: str) -> bool:
    """¿Hay una señal de box_set legítima por el token "box" en `normalized`?

    `normalized` viene de normalize_text (casefold + NFKD, así que el BOX de ancho
    completo japonés ya es "box"). Ver comentario de _BOX_CONSTRUCTION_RE.
    """
    if _BOX_CONSTRUCTION_RE.search(normalized):
        return True
    for m in _BOX_TOKEN_RE.finditer(normalized):
        # ¿La palabra inmediatamente anterior es latina? → bigrama tipo "blue box"
        # (nombre propio) → no cuenta. Si va pegado a CJK/puntuación/dígito o es el
        # inicio, es un box de producto (収納BOX, Re:BOX…) → cuenta.
        prefix = normalized[:m.start()].rstrip()
        if prefix and prefix[-1].isascii() and prefix[-1].isalpha():
            continue
        return True
    return False


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

    # "box" como señal de box_set (construcción latina o box CJK), excluyendo los
    # bigramas latinos de nombre propio (Blue Box / Black Box). Ver
    # _box_set_signal_present. Guarda contra doble-scoring si ya hay box_set por
    # otra keyword (coffret, cofanetto, 盒裝…).
    if "box_set" not in matched_types and _box_set_signal_present(normalized):
        matched_phrases.append("box [signal]")
        matched_types.append("box_set")
        score += _BOX_CONSTRUCTION_SCORE

    # "…Colors" al final = artbook (línea Glénat). Anclado a fin (ver
    # _COLORS_ARTBOOK_RE) para no marcar tomos regulares con "colors" mid-title.
    if "artbook" not in matched_types and _COLORS_ARTBOOK_RE.search(normalized):
        matched_phrases.append("colors [signal]")
        matched_types.append("artbook")
        score += _COLORS_ARTBOOK_SCORE

    # "画集付き" / "イラスト集付き特装版" = un cuadernillo de ilustraciones INCLUIDO
    # como bonus, NO el producto. El producto es el tomo de manga (特装版/限定版).
    # Sin esto, el skill /watch-standardize-catalog clasificaba estos tomos como edición
    # "Artbook" y reescribía el título a "X Artbook Special N" (queja del owner
    # 2026-06-04). Demuele artbook→bonus SOLO cuando el único indicio de artbook
    # es un cuadernillo adjunto (画集/イラスト集/アートワーク + 付/つき/同梱/付属)
    # y NO un artbook propio (p. ej. "笠井あゆみ画集" NO se demuele — no hay 付き).
    if "artbook" in matched_types and _ARTBOOK_BONUS_ATTACH_RE.search(normalized):
        artbook_phrases = {
            normalize_text(p) for p, t in zip(matched_phrases, matched_types)
            if t == "artbook"
        }
        if artbook_phrases and artbook_phrases <= _ARTBOOK_BOOKLET_PHRASES:
            matched_types = [t for t in matched_types if t != "artbook"]
            if "bonus" not in matched_types:
                matched_types.append("bonus")

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
    # Mes en español/francés/italiano/portugués/alemán:
    # "15 de junio de 2026" / "15 juin 2026" / "15 giugno 2026" /
    # "15 de junho de 2025" / "15. März 2026"
    re.compile(
        r"\b(\d{1,2}\.?\s+(?:de\s+)?(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre|"
        r"janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre|"
        r"gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre|"
        r"janeiro|fevereiro|março|marco|maio|junho|julho|setembro|outubro|novembro|dezembro|"
        r"januar|februar|märz|maerz|marz|juni|juli|oktober|dezember)"
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

# Normalización de release_date a ISO (gotcha #80). Mes textual en 4 idiomas
# (las grafías que comparten ES/IT — marzo, agosto — apuntan al mismo número).
_MONTH_NAMES: dict[str, int] = {
    # EN (con abreviaturas de 3-4 letras)
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    # ES
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
    # FR (con y sin acento)
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "aout": 8, "août": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12,
    # IT
    "gennaio": 1, "febbraio": 2, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "settembre": 9, "ottobre": 10, "dicembre": 12,
    # PT-BR (con y sin acento)
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "maio": 5,
    "junho": 6, "julho": 7, "setembro": 9, "outubro": 10, "novembro": 11,
    "dezembro": 12,
    # DE (con y sin acento)
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "marz": 3,
    "juni": 6, "juli": 7, "oktober": 10, "dezember": 12,
    # "april"/"mai"/"august"/"september"/"november"/"abril" ya cubiertos arriba.
}

_DATE_ISO_FULL_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T\s].*)?$")
_DATE_ISO_PARTIAL_RE = re.compile(r"^(\d{4})(?:-(\d{1,2}))?$")
# YYYY/MM/DD con hora opcional ("2023/09/27 10:00:00", JSON-LD de tiendas JP)
_DATE_YMD_RE = re.compile(r"^(\d{4})[/.](\d{1,2})[/.](\d{1,2})(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?$")
# DD/MM/YYYY (también con . o - como separador) — día primero (fuentes EU)
_DATE_DMY_RE = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})$")
_DATE_JP_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月(?:\s*(\d{1,2})\s*日)?")
# "15 de junio de 2026" / "2 juillet 2025" / "1er ottobre 2026" / "02 Jul 2025"
# El `\.?` tras el número cubre el formato alemán "15. März 2026".
_DATE_TEXT_DMY_RE = re.compile(
    r"\b(\d{1,2})(?:er|°|º)?\.?\s+(?:de\s+)?([a-zA-Zà-ÿÀ-Ÿ]+)\.?\s+(?:de\s+)?(\d{4})\b"
)
# "June 15, 2026" / "Jun 15 2026"
_DATE_TEXT_MDY_RE = re.compile(r"\b([a-zA-Z]+)\.?\s+(\d{1,2}),?\s+(\d{4})\b")


def _safe_iso_date(year: int, month: int, day: int) -> str:
    """ISO YYYY-MM-DD si (year, month, day) es una fecha real; "" si no."""
    if not 1900 <= year <= 2100:
        return ""
    try:
        return dt.date(year, month, day).isoformat()
    except ValueError:
        return ""


# Países cuyas fuentes escriben las fechas ambiguas D/M/YYYY como MM/DD/YYYY.
# Cuando ambos componentes son <=12 el formato es AMBIGUO; para estas fuentes se
# interpreta mes-primero (hallazgo B14 Fable 2026-07-08). El resto = día-primero
# (default EU histórico, gotcha #80).
_MDY_COUNTRIES = frozenset({"US", "CA"})


def normalize_release_date(raw: str, country: str = "") -> str:
    """Normaliza una fecha de lanzamiento a ISO: YYYY-MM-DD, YYYY-MM o YYYY.

    La granularidad parcial es legítima y se respeta (nunca se inventa día ni
    mes). Si el formato no se reconoce o la fecha es inválida, devuelve el
    valor SIN tocar (nunca destruye información). Gotcha #80.

    `country` (opcional): país de la FUENTE. Para D/M/YYYY AMBIGUO (ambos
    componentes <=12) se usa MM/DD si el país es US/CA; en cualquier otro caso
    day-first. Un segundo componente >12 ya es inequívoco y no depende del país.
    """
    value = (raw or "").strip()
    if not value:
        return ""
    m = _DATE_ISO_FULL_RE.match(value)
    if m:
        # Ya es ISO (quizás con cola de hora "T10:00:00"); re-validar y recortar.
        return _safe_iso_date(int(m.group(1)), int(m.group(2)), int(m.group(3))) or value
    m = _DATE_ISO_PARTIAL_RE.match(value)
    if m:
        year, month = int(m.group(1)), m.group(2)
        if not 1900 <= year <= 2100 or month is None:
            return value
        return f"{year:04d}-{int(month):02d}" if 1 <= int(month) <= 12 else value
    m = _DATE_YMD_RE.match(value)
    if m:
        return _safe_iso_date(int(m.group(1)), int(m.group(2)), int(m.group(3))) or value
    m = _DATE_DMY_RE.match(value)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if month > 12 and day <= 12:  # inequívocamente mes-primero (fuente US)
            day, month = month, day
        elif day <= 12 and month <= 12 and (country or "").upper() in _MDY_COUNTRIES:
            # Ambiguo + fuente US/CA → MM/DD (el primer componente es el mes).
            day, month = month, day
        return _safe_iso_date(year, month, day) or value
    m = _DATE_JP_RE.search(value)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if m.group(3):
            return _safe_iso_date(year, month, int(m.group(3))) or value
        if 1900 <= year <= 2100 and 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"
        return value
    for pattern, day_idx, month_idx in ((_DATE_TEXT_DMY_RE, 1, 2), (_DATE_TEXT_MDY_RE, 2, 1)):
        m = pattern.search(value)
        if m:
            month_num = _MONTH_NAMES.get(m.group(month_idx).lower().rstrip("."))
            if month_num:
                iso = _safe_iso_date(int(m.group(3)), month_num, int(m.group(day_idx)))
                if iso:
                    return iso
    return value


def extract_release_date(text: str, country: str = "") -> str:
    """Best-effort extracción de fecha de lanzamiento, normalizada a ISO.

    Devuelve "" si no encuentra. El match crudo (DD/MM/YYYY, 年月日, mes
    textual…) pasa por normalize_release_date() para que al corpus solo
    entren fechas ISO (gotcha #80). `country` se propaga para desambiguar
    D/M vs M/D en fuentes US/CA (B14).
    """
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
            return normalize_release_date(match.group(1).strip(), country=country)
    # Si no encontramos cerca del hint, intentar buscar en todo el texto.
    if hint:
        for pattern in RELEASE_DATE_PATTERNS:
            match = pattern.search(text)
            if match:
                return normalize_release_date(match.group(1).strip(), country=country)
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
    "no_image", "no-image", "noimage", "no_photo", "no_cover", "no-cover",
    "coming_soon", "coming-soon", "comingsoon",
    "image_not_available", "image-not-available",
    "default_book", "default-book",
    # Placeholders detectados 2026-06-12 (sweep de covers repetidas, gotcha #90)
    "/img/ph/",                             # Crew CZ (ph = placeholder; komiks.png)
    "19book_150cover",                      # Aladin KR (default sin portada)
    "img-non-disponibile",                  # Shopify IT (Manga Dreams)
    "transparent-pixel",                    # Amazon 1x1
    "otakucalendar.png",                    # logo del sitio servido como cover
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
    # Banners de publicidad de tienda servidos como <img> de galería.
    # KADOKAWA Store inyecta top_bar_banner_sp_*.png y bnr_honyaclub.jpg en el
    # carrusel del producto — no son portada ni foto del producto (el
    # "/banner/" de arriba no los agarra porque el path es "/top_bar_banner/"
    # o "/img/bnr_"). Ver gotcha imágenes.
    "top_bar_banner",
    "/bnr_",
    # Avatares de usuario / assets de UI de AnimeClick servidos como <img> en
    # la ficha (el carrusel levantaba el avatar de quien subió la edición).
    "/bundles/accommon/",
    "/immagini/avatar/",
    "utente_registrato",
    # Íconos de UI de Funside (candado "scheda prodotto", etc.).
    "icona_lucchetto",
    # Banners promocionales de Rakuten Books servidos como portada
    # (/books/img/bnr/event/... — campañas de puntos, no es portada).
    "/img/bnr/",
    # Íconos de estrella de rating de honto.jp servidos como portada
    # (img.honto.jp/library/img/pc/img_star5_s.png).
    "img_star",
    # Placeholder "now printing" de e-hon.ne.jp (libro sin portada todavía).
    "nowprinting",
    # Aviso de contenido adulto de Manga-Sanctuary servido como portada.
    "/img/adulte",
    # Banners del sitio Otaku Calendar (Header-Spring.png, Twitter-Card-*.png).
    "/images/site/yomi/",
    # Banner promocional "Lista de Mangas Panini" que Manga México (blog en
    # Blogger) sirve como imagen del post — se colaba como portada idéntica en
    # decenas de mangas distintos. No es portada de producto.
    "lista%20de%20mangas",
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
    # data-src/data-original ANTES que src: cuando coexisten, data-* es la
    # imagen real y src el placeholder de lazy-load (el punto entero del
    # patrón). Caso Crew CZ: src=/img/ph/komiks.png + data-src=cover real
    # (gotcha #90; el orden src-first dejó 4 boxes checos con placeholder).
    for attr in ("data-src", "data-original", "data-lazy-src", "src", "srcset", "data-srcset"):
        val = img.get(attr)
        if not val:
            continue
        if "srcset" in attr:
            # Los srcset listan entradas de menor a mayor resolución; tomar la mayor.
            # Formato por entrada: "<url> [<N>w|<Nx>]" separadas por coma.
            entries = [e.strip() for e in val.split(",") if e.strip()]
            if not entries:
                continue
            best_url = ""
            best_w = -1
            for entry in entries:
                parts = entry.split()
                if not parts:
                    continue
                entry_url = parts[0]
                if len(parts) >= 2:
                    desc = parts[-1]
                    m = re.match(r"(\d+)[wx]$", desc, re.IGNORECASE)
                    w = int(m.group(1)) if m else 0
                else:
                    # Sin descriptor: tomar la última entrada (heurística: orden ascendente)
                    w = 0
                if w > best_w or (w == 0 and best_w <= 0):
                    best_w = w
                    best_url = entry_url
            # Sin descriptores numéricos: la última entrada es la mayor
            if best_w <= 0:
                best_url = entries[-1].split()[0]
            val = best_url
        val = val.strip()
        if val.lower().startswith("data:"):
            continue
        # Placeholders de lazy-load que NO son data-URIs: archivos loader/
        # blank/spinner reales (Mangarden: /gfx/pol/loader.gif con la portada
        # en data-src). Sin este skip devolvíamos el loader como portada y
        # nunca llegábamos a data-src (167 items PL sin foto, 2026-06-12).
        if _LAZY_PLACEHOLDER_RE.search(val):
            continue
        url = canonicalize_url(source_url, val)
        if url and url != source_url:
            return url
    return ""


# Nombres de archivo EXACTOS de placeholder de lazy-load (se saltean en
# _img_to_url para caer al data-src real). Sin wildcard tras el nombre:
# "lazy.jpg"/"grey-edition.jpg" pueden ser imágenes reales — solo el nombre
# pelado (con sufijo numérico opcional tipo loader2.gif / blank_1x1.png).
_LAZY_PLACEHOLDER_RE = re.compile(
    r"(?:^|/)(?:loader|loading|blank|placeholder|spacer|spinner|"
    r"transparent|pixel|dummy|no[-_]?image|noimage|default)"
    r"(?:[-_]?\d+(?:x\d+)?)?\.(?:gif|png|svg|jpe?g|webp)\b",
    re.IGNORECASE,
)


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


# ⚠️ EL ORDEN DE ESTA LISTA ES LA PRIORIDAD (de más específico a menos).
# `derive_product_type` devuelve el PRIMER ptype cuya keyword matchee, así que
# un "Artbook Box Set" resuelve a `artbook` (no `boxset`) porque artbook va
# antes. No reordenes sin entender el efecto: un cambio de orden reclasifica
# items y exige correr `scripts/retrofit/rescore.py`. Cubierto por
# test_derive_product_type_priority_artbook_over_boxset.
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


# Enum canónico de `product_type` — FUENTE ÚNICA (Fable 2026-07-08, hallazgo #10).
# Los valores posibles del campo product_type de un item: los ptypes de
# PRODUCT_TYPE_KEYWORDS (artbook/fanbook/guidebook/boxset/novel) + 'manga'
# (default de derive_product_type), 'magazine' (match directo en el título) y
# 'audiobook' (bookFormat de JSON-LD en _schema_product_result). El string vacío
# "" (sin clasificar) NO forma parte del enum. `validate_corpus.py` y
# `standardize_apply.py` deben IMPORTAR esta constante en vez de copiarla a mano
# (hoy tienen copias; el paquete E de la próxima ola las consume).
PRODUCT_TYPE_ENUM: frozenset[str] = frozenset(
    {p for p, _kw in PRODUCT_TYPE_KEYWORDS} | {"manga", "magazine", "audiobook"}
)


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

# Etiqueta de "autor" horneada al inicio del VALOR ("Autori: Kentaro Miura").
# Pasa cuando la fuente repite el label dentro del campo (Panini IT, JSON-LD
# sucio). Sólo con [:：] — "Di"/"By" sin dos puntos pueden ser parte del nombre.
_AUTHOR_LABEL_PREFIX = re.compile(
    r"^\s*(?:autori?|autor(?:es)?|authors?|auteurs?|autrice|by|par|von"
    r"|著者|作者|原作|作画)\s*[:：]\s*",
    re.IGNORECASE,
)


def clean_author(raw: str) -> str:
    """Limpia el campo author: quita labels horneados al inicio del valor.
    Único punto de normalización — candidate_to_json lo aplica SIEMPRE."""
    s = clean_text(raw or "")
    while True:
        m = _AUTHOR_LABEL_PREFIX.match(s)
        if not m:
            break
        s = s[m.end():]
    return s.strip()


def _validate_author_candidate(raw: str) -> str:
    cleaned = clean_text(raw)
    if not cleaned or len(cleaned) < 3 or len(cleaned) > 80:
        return ""
    first_word = cleaned.split()[0]
    if first_word.lower() in AUTHOR_FIRST_WORD_BLACKLIST:
        return ""
    first_char = first_word[0]
    # Aceptar: mayúscula latina, o carácter CJK/Hangul (Hiragana/Katakana/Han/
    # Hangul coreano). Reutiliza _CJK_RE (fuente única del rango, incluye Hangul)
    # en vez del rango U+3040–U+9FFF que dejaba fuera a los autores KR.
    is_uppercase_latin = first_char.isupper() and first_char.isalpha()
    is_cjk = _has_cjk(first_char)
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
        if first_char.isupper() or _has_cjk(first_char):
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


def _isbn10_check(body: str) -> bool:
    """Valida ISBN-10 (mod-11, con 'X'=10 SÓLO en la última posición)."""
    if len(body) != 10:
        return False
    total = 0
    for i, ch in enumerate(body):
        if ch == "X":
            if i != 9:          # X sólo válida como dígito de control final
                return False
            val = 10
        elif ch.isdigit():
            val = int(ch)
        else:
            return False
        total += val * (10 - i)
    return total % 11 == 0


def _isbn10_to_13(body: str) -> str:
    """Convierte un ISBN-10 (ya validado) a ISBN-13 con prefijo GS1 978."""
    core = "978" + body[:9]  # se descarta el dígito de control del 10
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(core))
    check = (10 - total % 10) % 10
    return core + str(check)


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
                cleaned = cleaned.upper()
                if len(cleaned) == 13 and cleaned.isdigit() and _isbn13_check(cleaned):
                    return cleaned
                # B7: ISBN-10 estructurado exige checksum (un SKU de 10 dígitos
                # no puede colarse como ISBN); si valida se convierte a ISBN-13.
                if len(cleaned) == 10 and _isbn10_check(cleaned):
                    return _isbn10_to_13(cleaned)

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
                        cleaned = re.sub(r"[^0-9Xx]", "", val).upper()
                        if len(cleaned) == 13 and cleaned.isdigit() and _isbn13_check(cleaned):
                            return cleaned
                        if len(cleaned) == 10 and _isbn10_check(cleaned):
                            return _isbn10_to_13(cleaned)

    # 2. Regex en texto plano + URL.
    if text:
        for match in ISBN13_PATTERN.finditer(text):
            digits = "".join(match.groups())
            if _isbn13_check(digits):
                return digits

    return ""


# Un ISBN crudo puede traer separadores internos (guiones, espacios) DENTRO del
# número y basura ALREDEDOR (prefijos "ISBN：", sufijos "Deluxe"). Tokenizamos en
# runs de [0-9Xx] separados por no-alfanuméricos-de-ISBN, así "9784…980 Deluxe"
# NO concatena la 'x' de "Deluxe" al número (el bug podrido del reporte).
_ISBN_TOKEN_RE = re.compile(r"[0-9Xx](?:[0-9Xx \-]*[0-9Xx])?")


def normalize_isbn(raw: str, source: str = "") -> str:
    """Normaliza y VALIDA un ISBN crudo para almacenarlo/deduplicarlo.

    Normalizador real (Fable 2026-07-08, hallazgo cover-sync #6 + B7), ya no un
    simple strip. El pipeline:

      1. Tokeniza el crudo en runs de dígitos/X (separadores internos guion/
         espacio permitidos), descartando basura alrededor. El "： " (dos puntos
         fullwidth U+FF1A, gotcha #108) y sufijos como "Deluxe" caen fuera del
         token del número — así "…980 Deluxe" NUNCA se guarda como "…980X" (la
         'x' de "Deluxe" es su propio token, no parte del ISBN).
      2. Por cada token, valida:
         - ISBN-13: 13 dígitos, prefijo GS1 978/979, checksum mod-10 correcto.
         - ISBN-10: mod-11 con 'X'=10 sólo como dígito final → se CONVIERTE a
           ISBN-13 (prefijo 978, checksum recomputado) para tener una sola forma.
      3. Devuelve el PRIMER token que valida (multi-ISBN en un campo → el primero).

    Fail-safe (gotcha #108): si NINGÚN token valida, conserva el token más
    ISBN-like limpio (preferencia por longitud 13/10, si no el más largo) y
    loguea `ISBN_ANOMALY` a stderr — el valor puede ser un identificador parcial
    útil y descartarlo perdería señal. Devuelve "" si no hay ningún dígito.

    Idempotente: un ISBN-13 válido ya limpio se devuelve intacto y sin log; un
    ISBN-10 válido converge a su ISBN-13 en la 1ª pasada y queda estable.
    """
    if not raw:
        return ""
    tokens = [re.sub(r"[ \-]", "", t).upper() for t in _ISBN_TOKEN_RE.findall(raw)]
    tokens = [t for t in tokens if t]
    if not tokens:
        return ""
    for cand in tokens:
        if len(cand) == 13 and cand.isdigit() and cand[:3] in ("978", "979") \
                and _isbn13_check(cand):
            return cand
        if len(cand) == 10 and _isbn10_check(cand):
            return _isbn10_to_13(cand)
    # Fail-safe: ningún token es un ISBN válido. Conservar el más ISBN-like.
    def _tok_rank(t: str) -> tuple[int, int]:
        return (1 if len(t) in (10, 13) else 0, len(t))
    best = max(tokens, key=_tok_rank)
    print(f"[ISBN_ANOMALY] source={source or '?'} raw={raw!r} kept={best!r}",
          file=sys.stderr)
    return best


SCHEMA_ORG_CURRENCY_SYMBOLS = {
    "EUR": "€", "USD": "$", "JPY": "¥", "GBP": "£",
    "MXN": "MXN", "ARS": "$", "CAD": "$", "AUD": "$",
}



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


# Tipos JSON-LD que NO son un producto individual aunque contengan la subcadena
# "Book"/"Comic" — son la SERIE/tienda, cuyo `name` es la obra, no el tomo, y
# poblarían name/publisher/fecha con datos equivocados (gotcha M5 Fable 2026-07-08).
_SCHEMA_NON_PRODUCT_TYPES = frozenset({"bookseries", "comicseries", "bookstore"})
_SCHEMA_PRODUCT_HINTS = ("product", "book", "comic", "manga", "graphicnovel")


def _schema_item_is_product(item: dict) -> bool:
    """¿El item JSON-LD es un Product/Book/Comic individual?

    Matchea por TOKEN del `@type` (no substring del string entero): así
    `BookSeries`/`BookStore`/`ComicSeries` quedan excluidos aunque contengan
    "Book"/"Comic". Un `@type` lista con al menos un token-producto sí cuenta.
    """
    t = item.get("@type", "")
    types = t if isinstance(t, list) else [t]
    for one in types:
        low = str(one).strip().lower()
        if not low or low in _SCHEMA_NON_PRODUCT_TYPES:
            continue
        if any(h in low for h in _SCHEMA_PRODUCT_HINTS):
            return True
    return False


def _blank_schema_result() -> dict[str, str]:
    return {
        "name": "",
        "image_url": "",
        "description": "",
        "author": "",
        "isbn": "",
        "release_date": "",
        "publisher": "",
        "product_type": "",
    }


def _schema_product_result(items: list[dict], source_url: str) -> dict[str, str]:
    """Rellena el dict de metadata desde una lista de items JSON-LD ya aplanados.

    Fuente ÚNICA de la extracción de campos Schema.org: la usan tanto
    `extract_schema_org_product` (que primero parsea los <script>) como el mapa
    por-card del listing (`_build_card_schema_map`). No re-buscar scripts acá.
    """
    result = _blank_schema_result()
    for item in items:
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
            result["description"] = clean_description(clean_text(str(item["description"])))[:2000]

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
                    cleaned = re.sub(r"[^0-9Xx]", "", val).upper()
                    if len(cleaned) == 13 and cleaned.isdigit() and _isbn13_check(cleaned):
                        result["isbn"] = cleaned
                        break
                    # B7: ISBN-10 exige checksum (mod-11) y se convierte a 13.
                    if len(cleaned) == 10 and _isbn10_check(cleaned):
                        result["isbn"] = _isbn10_to_13(cleaned)
                        break

        # release_date / datePublished
        if not result["release_date"]:
            # dateModified NO entra: es la fecha de último registro/edición
            # de la ficha, no el 発売日 del libro (podía desviar años). M5.
            date_val = (
                item.get("datePublished")
                or item.get("releaseDate")
                or item.get("dateCreated")
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


def extract_schema_org_product(soup_or_card: Any, source_url: str) -> dict[str, str]:
    """Extrae metadata de un Product/Book Schema.org en JSON-LD.

    Acepta tanto un BeautifulSoup completo como un Tag (card individual). Si la
    card contiene un <script type='application/ld+json'> con Product, devuelve
    todos los campos disponibles. Si no, devuelve dict vacío.

    Devuelve dict con: name, image_url, description, author, isbn,
    release_date, publisher, product_type (manga/artbook/boxset/...).
    """
    if soup_or_card is None:
        return _blank_schema_result()
    try:
        scripts = soup_or_card.find_all("script", attrs={"type": "application/ld+json"})
    except Exception:
        return _blank_schema_result()
    items: list[dict] = []
    for script in scripts:
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        items.extend(_schema_iter_items(data))
    return _schema_product_result(items, source_url)


def _build_card_schema_map(soup: Any, source_url: str) -> list[tuple[Any, dict[str, str]]]:
    """Mapa (nodo_contenedor → schema) de los Product JSON-LD por card.

    A1 (Fable 2026-07-08): `extract_generic_html` decompone los <script> ANTES
    de que los extractores card-level llamen a `extract_schema_org_product`, así
    que el JSON-LD por card quedaba MUERTO en el listing. Este mapa se construye
    ANTES del decompose, guardando el PADRE del <script> (que sobrevive al
    decompose del <script>), para poder atribuir el schema a la card que lo
    contiene sin dejar el JSON crudo contaminando el texto de las cards.
    """
    mapping: list[tuple[Any, dict[str, str]]] = []
    try:
        scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    except Exception:
        return mapping
    for script in scripts:
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        items = _schema_iter_items(data)
        if not any(_schema_item_is_product(it) for it in items):
            continue
        anchor = script.parent
        if anchor is None:
            continue
        mapping.append((anchor, _schema_product_result(items, source_url)))
    return mapping


def _schema_for_card(card: Any, schema_map: list[tuple[Any, dict[str, str]]]) -> dict[str, str]:
    """Devuelve el schema pre-parseado cuyo <script> vivía DENTRO de esta card.

    Camina desde el nodo-ancla (padre del script) hacia arriba buscando la card;
    si ninguno matchea (JSON-LD a nivel página, o ancla ya desprendida por
    strip_chrome) devuelve el dict vacío (fallback benigno)."""
    if not schema_map:
        return _blank_schema_result()
    for anchor, result in schema_map:
        node = anchor
        while node is not None:
            if node is card:
                return result
            node = getattr(node, "parent", None)
    return _blank_schema_result()


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


# Selectores CSS comunes para galerías de producto. Cubre los frameworks de
# e-commerce más usados por las fuentes (Shopify, Tiendanube, WooCommerce,
# Magento, PrestaShop, Squarespace, custom). El extractor multi-imagen los
# prueba en cascada después de OG/JSON-LD para complementar la cover con
# tomas adicionales (vista trasera, contenido, lomo, extras de la edición).
_GALLERY_CSS_SELECTORS: tuple[str, ...] = (
    # Shopify
    ".product__media img",
    ".product-single__photo img",
    ".product__photo img",
    "[data-product-images] img",
    "[data-product-image] img",
    "[data-zoom-image]",
    "[data-product-media] img",
    ".product-gallery img",
    ".product-gallery__image img",
    # Tiendanube
    ".js-product-slides img",
    ".js-product-slide img",
    ".swiper-slide img",
    "[data-image-id] img",
    # WooCommerce / Magento / PrestaShop
    ".woocommerce-product-gallery__image img",
    ".woocommerce-product-gallery img",
    ".fotorama__img",
    ".fotorama img",
    ".gallery-image",
    ".product-image-thumbs img",
    ".product-images img",
    ".product__images img",
    ".product_images img",
    ".product-photo img",
    "#product-images img",
    "#product_images img",
    "#product-gallery img",
    # Genéricos
    "[class*='gallery'] img",
    "[class*='carousel'] img",
    "[class*='slider'] img",
    "[class*='thumbs'] img",
    "[class*='thumbnails'] img",
    "[class*='additional-images'] img",
    "[class*='product-photo'] img",
    "[class*='product-images'] img",
    "[class*='cover'] img",
    "[class*='jacket'] img",
    "[class*='detail'] img",
    "[id*='product'] img",
)


def _gallery_url_normalize(url: str) -> str:
    """Normaliza una URL de gallery para dedup: strippea query params no
    significativos y upscalea miniaturas conocidas a su tamaño full cuando
    aplica (Shopify usa `?v=12345` o `_100x100.jpg` para miniaturas, la
    full sin sufijo es la misma imagen).
    """
    if not url:
        return ""
    # Shopify thumb suffix: `_100x100.jpg`, `_grande.jpg`, `_small.png`, etc.
    # Strippeamos el sufijo para que el thumb dedupee contra la full.
    url = re.sub(
        r"_(?:\d+x\d+|small|medium|grande|large|master|compact|original|x\d+|pico|icon|thumb|mini|crop_center)"
        r"(?=\.(?:jpe?g|png|webp|gif|avif)(?:\?|$))",
        "",
        url,
        flags=re.IGNORECASE,
    )
    # Strip query params irrelevantes para dedup (v, version, _, t).
    if "?" in url:
        base, q = url.split("?", 1)
        keep = []
        for pair in q.split("&"):
            k = pair.split("=", 1)[0].lower()
            if k in {"v", "version", "_", "t", "rev", "cache", "ts"}:
                continue
            keep.append(pair)
        url = base + ("?" + "&".join(keep) if keep else "")
    return url


# Selectores para acotar el extractor a la "zona del producto principal" y
# evitar absorber thumbnails de carruseles de "productos relacionados",
# "recently viewed" o sidebars editoriales. Probamos en orden de
# especificidad. Si ninguno matchea, caemos al soup entero (limit más bajo).
_PRODUCT_SCOPE_SELECTORS: tuple[str, ...] = (
    "[itemtype*='schema.org/Product']",
    "[itemtype*='schema.org/Book']",
    "[itemtype*='Product']",
    "[itemtype*='Book']",
    "#product-detail",
    "#product_detail",
    "#product-main",
    "#product-single",
    "#product",
    ".product-detail",
    ".product-single",
    ".product-main",
    ".product-page",
    ".product-info",
    ".product__info",
    ".product-content",
    ".ficha-producto",
    ".ficha",
    "article.product",
    "main",
)


_IMAGE_EXT_RE = re.compile(
    r"\.(jpe?g|png|webp|avif|gif)$", re.IGNORECASE
)


def _img_anchor_full_url(img_node: Any, source_url: str) -> str:
    """Si el <img> está envuelto en un <a href="full.ext"> (padre o abuelo),
    devuelve la URL del href como versión full-res (patrón Magento/Fotorama/
    PrestaShop/LightGallery: thumb en src, full-res en el link que lo envuelve).

    Devuelve "" si no hay ancla, si el href no termina en extensión de imagen
    (ignorando query string), o si el href queda fuera del scope del producto
    (mismo dominio, sin marcadores de "relacionados" — gotcha #31).
    """
    for ancestor in (img_node.parent, img_node.parent.parent if img_node.parent else None):
        if ancestor is None:
            continue
        if ancestor.name != "a":
            continue
        href = (ancestor.get("href") or "").strip()
        if not href:
            continue
        # Verificar que el href termina en extensión de imagen (sin query string)
        href_path = href.split("?", 1)[0].split("#", 1)[0]
        if not _IMAGE_EXT_RE.search(href_path):
            continue
        url = canonicalize_url(source_url, href)
        if not url:
            continue
        # No salir del dominio del producto (gotcha #31): el href debe ser del
        # mismo host que source_url, o relativo.
        from urllib.parse import urlparse as _urlparse
        src_host = _urlparse(source_url).netloc
        href_host = _urlparse(url).netloc
        if src_host and href_host and src_host != href_host:
            continue
        return url
    return ""


def _find_product_scope(soup: BeautifulSoup):
    """Devuelve el contenedor del producto principal o None si no hay match."""
    for selector in _PRODUCT_SCOPE_SELECTORS:
        try:
            node = soup.select_one(selector)
        except Exception:
            continue
        if node:
            return node
    return None


def _related_grid_card_ids(scope: Any, source_url: str) -> set[int]:
    """IDs de los contenedores que forman una GRILLA de 'productos relacionados'
    dentro del scope del producto (repetición de product-cards, cada una con
    enlace a una PÁGINA DE PRODUCTO distinta).

    Varias fuentes (Star Comics, retailers Shopify) incrustan un carrusel de
    'otri volumi / ti potrebbe interessare' DENTRO del `<main>` del producto.
    Sus thumbnails son de OTROS productos y no deben entrar al carrusel del
    producto que se scrapea. El filtro de mismo-directorio (gotcha #31) no
    alcanza cuando la cover del PROPIO producto también vive en el subdir
    `thumbnail/` (misma carpeta que los relacionados): no queda señal de path
    que los separe. La señal robusta es ESTRUCTURAL — son cards repetidas que
    enlazan a productos DISTINTOS, no la galería del propio producto.

    Devuelve el set de `id()` de esas cards para que el harvest de galería
    (selectores CSS + fallback) las saltee. Vacío si no hay grilla: una galería
    legítima (front/back/lomo del MISMO producto, lightbox a archivos de imagen)
    no enlaza a N páginas de producto distintas, así que no se detecta.
    """
    try:
        clusters = detect_product_clusters(scope, source_url)
    except Exception:
        return set()
    own = canonicalize_url(source_url, source_url)
    grid_cards: list[Any] = []
    product_hrefs: set[str] = set()
    for card in clusters:
        if not card.find("img"):
            continue
        anchor = card.find("a", href=True)
        if not anchor:
            continue
        href = (anchor.get("href") or "").split("?", 1)[0].split("#", 1)[0]
        # Un ancla que apunta a un ARCHIVO de imagen (lightbox/zoom) NO es un
        # enlace a otro producto: es la propia galería. No cuenta como grilla.
        if _IMAGE_EXT_RE.search(href):
            continue
        url = canonicalize_url(source_url, anchor.get("href"))
        if not url or url == own:
            continue
        grid_cards.append(card)
        product_hrefs.add(url)
    # >=3 cards con imagen que enlazan a >=3 productos DISTINTOS = listing real.
    if len(grid_cards) < 3 or len(product_hrefs) < 3:
        return set()
    return {id(c) for c in grid_cards}


def _node_in_grid(node: Any, grid_card_ids: set[int]) -> bool:
    """True si `node` es (o desciende de) una card de grilla de relacionados."""
    if not grid_card_ids:
        return False
    cur = node
    while cur is not None:
        if id(cur) in grid_card_ids:
            return True
        cur = getattr(cur, "parent", None)
    return False


def _extract_images_from_detail_soup(
    soup: BeautifulSoup,
    source_url: str,
    limit: int = 6,
) -> list[dict[str, str]]:
    """Extrae el carrusel/galería de imágenes de una página de detalle.

    Devuelve lista de dicts `{url, kind, description}`. El primer elemento
    (posición 0) es la portada; el resto son vistas adicionales. `kind`
    solo distingue `gallery` (default) vs `extra` (bonus/cofre/regalo).

    Estrategias en cascada, mergeadas y dedupeadas por URL canónica:
      1) JSON-LD schema.org `image` (string, dict, lista) — la cover/feed
         oficial del sitio.
      2) OpenGraph `og:image` / Twitter `twitter:image` — usualmente la
         cover; puede repetir JSON-LD pero queda dedupeada.
      3) `meta itemprop="image"` (Schema.org markup directo).
      4) Selectores CSS de galería (Shopify/Tiendanube/Magento/WooCommerce
         + genéricos `[class*='gallery'] img`) — captura el carrusel real
         del frontend cuando el sitio lo expone.
      5) Fallback: ranking de `<img>` del body que matcheen
         IMAGE_URL_GOOD_PATTERNS y tengan alt text largo.

    Best-effort: si el sitio sólo expone una imagen (típico en APIs como
    mangapassion, catálogos minimalistas como booksprivilege/sumikko/Rakuten),
    devuelve lista de 1. Si no encuentra nada, devuelve lista vacía.

    Filtra placeholders, íconos UI, SVGs, data: URIs (ver
    IMAGE_URL_BAD_PATTERNS y _is_placeholder_image).
    """
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(raw_url: str, alt: str = "", kind_hint: str = "") -> None:
        """Resuelve, valida, dedupea, y appendea. Devuelve sin tocar si limit."""
        if len(out) >= limit:
            return
        if not raw_url:
            return
        url = canonicalize_url(source_url, raw_url.strip())
        if not url or _is_placeholder_image(url):
            return
        # _score_image rechaza badges/logos/íconos via IMAGE_URL_BAD_PATTERNS.
        # En este punto sirve como filtro secundario por si _is_placeholder_image
        # dejó pasar algo borderline.
        if _score_image(url, alt) < 0:
            return
        norm = _gallery_url_normalize(url)
        if norm in seen:
            return
        seen.add(norm)
        out.append({
            "url": url,
            "kind": kind_hint or "gallery",
            "description": (alt or "").strip()[:120],
        })

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
            if isinstance(value, str):
                _add(value)
            elif isinstance(value, dict):
                _add(value.get("url") or value.get("@id") or "")
            elif isinstance(value, list):
                for v in value:
                    if isinstance(v, str):
                        _add(v)
                    elif isinstance(v, dict):
                        _add(v.get("url") or v.get("@id") or "")

    # 2) OpenGraph / Twitter (cover canónica para social previews).
    for attrs in (
        {"property": "og:image"},
        {"property": "og:image:url"},
        {"property": "og:image:secure_url"},
        {"name": "twitter:image"},
        {"name": "twitter:image:src"},
    ):
        for meta in soup.find_all("meta", attrs=attrs):
            if meta.get("content"):
                _add(meta["content"])

    # 3) meta itemprop="image"
    for meta in soup.find_all("meta", attrs={"itemprop": "image"}):
        if meta.get("content"):
            _add(meta["content"])

    # 4) Selectores CSS de galería. Acotamos a la "zona del producto principal"
    # cuando el soup expone un contenedor identificable
    # (schema.org/Product/Book, #product-detail, .ficha, <main>, etc.). Sin
    # este scope, sitios como Norma o retailers Shopify devuelven los
    # thumbnails de "productos relacionados" / "recently viewed" como si
    # fueran de la misma galería del producto, contaminando el carrusel.
    scope = _find_product_scope(soup) or soup
    # Grilla de 'productos relacionados' incrustada en el scope (gotcha #31):
    # sus thumbnails son de OTROS productos. Los excluimos ANTES del filtro de
    # path porque cuando la cover propia también es un thumbnail el filtro de
    # directorio no puede separarlos.
    grid_card_ids = _related_grid_card_ids(scope, source_url)
    for selector in _GALLERY_CSS_SELECTORS:
        if len(out) >= limit:
            break
        try:
            nodes = scope.select(selector)
        except Exception:
            continue
        for node in nodes:
            if len(out) >= limit:
                break
            if not node:
                continue
            if _node_in_grid(node, grid_card_ids):
                continue
            if node.name == "img":
                # Preferir el href del <a> envolvente cuando apunta a full-res
                # (patrón Magento/Fotorama/PrestaShop/LightGallery: thumb en src,
                # full en el link). Fallback a _img_to_url si no hay ancla válida.
                url = _img_anchor_full_url(node, source_url) or _img_to_url(node, source_url)
                alt = (node.get("alt") or "").strip()
            else:
                # `[data-zoom-image]` y similares: leer el atributo directo.
                url = ""
                for attr in ("data-zoom-image", "data-image", "data-src",
                             "data-original", "href", "src"):
                    v = node.get(attr)
                    if v:
                        url = canonicalize_url(source_url, v.strip())
                        break
                alt = (node.get("alt") or node.get("title") or "").strip()
            _add(url, alt=alt)

    # 5) Ranking fallback (solo si seguimos sin nada útil o muy poco).
    # También acotado al scope del producto si lo hay — un fallback no debe
    # contaminar más que los selectores específicos.
    if len(out) < 2:
        fallback_scope = _find_product_scope(soup) or soup.body or soup
        scored: list[tuple[int, str, str]] = []
        for img in fallback_scope.find_all("img", limit=60):
            if _node_in_grid(img, grid_card_ids):
                continue
            url = _img_to_url(img, source_url)
            if not url:
                continue
            alt = (img.get("alt") or "").strip()
            score = _score_image(url, alt)
            if score >= 5:
                scored.append((score, url, alt))
        scored.sort(key=lambda t: t[0], reverse=True)
        for _score, url, alt in scored:
            _add(url, alt=alt)

    # 6) Filtro de "mismo folder que la cover": cuando el sitio tiene
    # carruseles de "productos relacionados" dentro del scope del producto
    # principal (caso real: Norma `<main>` incluye el sidebar de also-buy;
    # Star Comics incrusta un carrusel de "otros volúmenes" en el detail),
    # los thumbs de OTROS productos colaban como gallery. Si la cover tiene
    # un parent path identificable (>=2 segmentos), filtramos las gallery a
    # las que viven en el MISMO directorio que la cover. Cover siempre se
    # mantiene.
    #
    # IMPORTANTE: la comparación es por directorio EXACTO, no substring.
    # Star Comics sirve la cover en `/files/immagini/fumetti-cover/<X>` y los
    # thumbnails de productos relacionados en
    # `/files/immagini/fumetti-cover/thumbnail/<Y>` — un SUBdirectorio. Un
    # check `stem in url` dejaba pasar los contaminantes porque el parent de
    # la cover (`.../fumetti-cover`) es substring del path del subdirectorio
    # (`.../fumetti-cover/thumbnail/...`). Comparar el directorio padre exacto
    # los descarta (gotcha #31).
    if len(out) >= 2:
        from urllib.parse import urlparse

        def _parent_dir(u: str) -> str:
            try:
                p = urlparse(u).path.rstrip("/")
                return p.rsplit("/", 1)[0]
            except Exception:
                return ""

        cover_parent = _parent_dir(out[0]["url"])
        segments = [s for s in cover_parent.split("/") if s]
        gallery = out[1:]
        gallery_dirs = [_parent_dir(im["url"]) for im in gallery]
        shares_cover = any(d == cover_parent for d in gallery_dirs)

        anchor_dir: str | None = None
        if len(segments) >= 2 and shares_cover:
            # Caso clásico (gotcha #31): la cover y su galería comparten dir;
            # anclamos a ese dir para descartar carruseles de otros productos.
            anchor_dir = cover_parent
        elif not shares_cover and gallery:
            # M6 (Fable 2026-07-08): la cover vive en OTRO dir que la galería
            # (Shopify moderno: cover en /s/products/, galería en /s/files/).
            # Si NINGUNA gallery comparte dir con la cover pero hay un dir
            # MAYORITARIO entre las gallery (>=2 imgs y >=2/3), usar ESE como
            # ancla en vez de descartar toda la galería legítima (false-positive
            # inverso al #31).
            from collections import Counter

            counts = Counter(
                d for d in gallery_dirs if len([s for s in d.split("/") if s]) >= 2
            )
            if counts:
                top_dir, top_n = counts.most_common(1)[0]
                if top_n >= 2 and top_n * 3 >= len(gallery) * 2:
                    anchor_dir = top_dir

        if anchor_dir is not None:
            filtered = [out[0]] + [
                im for im in gallery if _parent_dir(im["url"]) == anchor_dir
            ]
            # Solo aplicamos el filtro si descartamos >=2 imágenes (señal
            # de que había contaminación real). Si descartamos <=1, era
            # un site con paths heterogéneos legítimos — no tocamos.
            if len(out) - len(filtered) >= 2:
                out = filtered

    return out


def _extract_image_from_detail_soup(soup: BeautifulSoup, source_url: str) -> str:
    """Compatibilidad: devuelve solo la URL de la primera imagen extraída
    (la cover). Para multi-imagen, usar _extract_images_from_detail_soup.
    """
    imgs = _extract_images_from_detail_soup(soup, source_url, limit=1)
    return imgs[0]["url"] if imgs else ""


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
    isbn) si encuentra un label conocido. Solo el PRIMER valor por
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
    country: str = "",
) -> dict[str, Any]:
    """Fetch HTTP a la URL del producto y extrae todos los metadatos posibles.

    Devuelve dict con author / image_url / isbn / name / release_date /
    publisher / description / images (campos vacíos si no se encuentra). Hace
    1 HTTP request opt-in (--fetch-details).

    El campo `images` es una lista de dicts `{url, kind, description}`
    representando el carrusel completo del producto. images[0] es la portada
    (por convención de posición, no por kind). Cuando el sitio sólo expone
    una imagen, la lista contiene un único elemento sincronizado con
    `image_url`. `kind` solo distingue `gallery` vs `extra`.
    """
    result: dict[str, Any] = {
        "author": "", "image_url": "", "isbn": "",
        "name": "", "release_date": "",
        "publisher": "", "description": "",
        "images": [],
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
    for key in ("name", "release_date", "publisher", "description"):
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
    for field in ("author", "publisher", "release_date", "isbn"):
        if not result.get(field) and label_pairs.get(field):
            result[field] = label_pairs[field]

    # Excepción a la prioridad del JSON-LD: una releaseDate con componente
    # HORARIO ("2022/05/27 10:00:00") es el inicio de venta EN LA TIENDA, no
    # el 発売日 del libro (caso real: store.kadokawa.co.jp, 27/05 vs 31/05).
    # Si la ficha técnica (label-pairs) trae fecha, esa gana.
    if (result.get("release_date")
            and re.search(r"\d{1,2}:\d{2}", result["release_date"])
            and label_pairs.get("release_date")):
        result["release_date"] = label_pairs["release_date"]

    # Al corpus solo entran fechas ISO (gotcha #80). Va DESPUÉS de la
    # excepción de arriba, que necesita ver el componente horario crudo.
    if result.get("release_date"):
        result["release_date"] = normalize_release_date(result["release_date"], country=country)

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

    # === Image + carrusel (multi-image) ===
    # Extraemos SIEMPRE el carrusel completo (best-effort: si el sitio sólo
    # expone una imagen, la lista queda con 1 elemento). image_url se setea
    # con la cover (primer elemento) sólo si Schema.org no lo trajo ya, para
    # no pisar la cover canónica que el sitio prefiere. El array `images`
    # SIEMPRE refleja el carrusel detectado en la página, y si trajo una
    # cover JSON-LD que NO está en el array (raro), la mergemos al frente.
    gallery = _extract_images_from_detail_soup(soup, url)
    if result["image_url"]:
        cover_url = result["image_url"]
        already_present = any(
            _gallery_url_normalize(im.get("url", "")) == _gallery_url_normalize(cover_url)
            for im in gallery
        )
        if not already_present:
            gallery.insert(0, {"url": cover_url, "kind": "gallery", "description": ""})
    elif gallery:
        result["image_url"] = gallery[0]["url"]
    result["images"] = gallery

    # === ISBN (si Schema.org no lo trajo) ===
    if not result["isbn"]:
        body_text = clean_text(soup.body.get_text(" ", strip=True) if soup.body else "")
        result["isbn"] = extract_isbn(f"{body_text}\n{url}", soup)
    # Normaliza en el punto de extracción: el valor de la ficha técnica (label
    # pairs) llega con "： " fullwidth pegado en fuentes JP. Fuente única de
    # limpieza para que md.get("isbn") ya salga limpio a los call-sites.
    result["isbn"] = normalize_isbn(result["isbn"], source=url)

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
                value = clean_description(clean_text(meta["content"]))
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


_ULTRA_RARE_KEYWORDS = (
    # Explicit numbering language (multilingual)
    "numbered edition", "numéroté", "numérotée",
    "numerado", "numerada", "numerato", "numerata",
    # Signed — ES/FR/DE/PT (no double-meaning issue in these languages)
    # "firmado/firmada" moved to _has_hand_signed(): "lámina firmada" means a
    # PRINTED signature on a giveaway art print, not a hand-signed copy.
    "signed by",
    "signé", "signiert", "autografado",
    # IT mano firmato: "autografato/autografata" = firmado A MANO (no double
    # meaning; distinto de "firmato" que en IT significa autoría, ver nota abajo).
    "autografato", "autografata",
    # DE numerado a mano: "nummeriert" aparece en convención de coleccionista
    # ("limitiert auf 777 Exemplare und nummeriert") — investigación 2026-06-10.
    "nummeriert",
    # Events across markets — only explicitly exclusive keywords
    "event exclusive", "event only", "event-only",
    "comiket", "jump festa", "anime expo exclusive",
    "wonder festival", "wonfes",
    "nuit one piece", "noche one piece",
    "japan expo exclusive",
    # JP: exclusivas de evento/venue (inalcanzables fuera del día del evento)
    "会場限定", "イベント限定",
    # Lottery / gacha ultra tier
    "lottery", "ichiban kuji", "last one prize",
    "ultra limited", "ultra limitata", "ultra-limitée",
    "抽選", "くじ",
    # Convention exclusive (cross-market)
    "convention exclusive",
)

# Regex patterns for ultra_rare that need more context than a bare keyword.
_ULTRA_RARE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Numbered copies: X/Y where X is a digit and Y is a common print-run
    # denominator. Bare "/200" matched "2007/2008" (year range, gotcha).
    re.compile(r'\d\s*/\s*(?:100|150|200|250|300|400|500|600|750|800|1000|1200|2000|2500)\b'),
    # "autograph" — require word boundary (avoids substring in unrelated text)
    re.compile(r'\bautograph(?:ed|e[sd])?\b', re.I),
)
# NOTE: Italian "firmato/a" intentionally excluded. In IT descriptions it
# commonly means "by" (authored), not "signed by" — e.g. "il capolavoro
# firmato One e Yusuke Murata". Genuinely signed IT items are caught via
# _PRINT_RUN_RE ("limitata a 100 copie") or other ultra_rare keywords.
# Spanish "firmado/a" stays in _ULTRA_RARE_KEYWORDS — no double meaning.

# Explicit print-run regex: "limited to N copies" (multilingual).
# Used for both ultra_rare (N <= 500) and super_rare (N <= 2500).
# Formas cubiertas:
#   ES/IT/FR/DE: "limitada/limitata/limitée/limitiert a/to/à/auf/di N …"
#   IT: "tiratura limitata di N copie" (preposición di)
#   IT: "in sole/soli N copie/esemplari/pezzi" — lead-in sin "limitat-"
#   IT: "stampata in soli N esemplari"
#   DE: "limitiert auf N Exemplare/exemplaren" (forma alemana)
#   EN: "limited to N numbered copies" (adjetivo numbered opcional)
#   Unidades nuevas: pezzi (IT), ejemplares (ES), exemplaren (DE)
#   PT-BR: "cópias" (con acento en la o) además de "copias/copies/copie".
_PRINT_RUN_RE = re.compile(
    r'(?:(?:limited|limitata?|limitée?|limitad[oa]|limitiert)\s+(?:a|to|à|auf|di)|in\s+sol[ei]|stampat[oa]\s+in\s+sol[ei])'
    r'\s+(\d[\d.,]*)\s*'
    r'(?:numbered\s+)?'
    r'(?:c[óo]p[iíy]e?s?|exempla[ir]res?|exemplaren?|esemplari|pezzi|st[üu]ck|unidades|ejemplares|pi[èe]ces)',
    re.I,
)

# IT: "N copie numerate" (numbered copies) sin lead-in "limitat-": la sola
# mención de copie NUMERATE es evidencia de tirada numerada. Se folda en
# _extract_print_run para que aplique la cascada ≤500 (ultra) / ≤2500 (super).
_PRINT_RUN_NUMERATE_RE = re.compile(r'\b(\d[\d.,]*)\s+copie\s+numerate\b', re.I)

# Cupo de compra por persona (NO es tirada): "limited to 2 copies per person",
# "par personne", "pro Person" y la forma JP "お一人様N点限り" / "お1人様…"
# (donde el número va DESPUÉS del marcador). Un cupo por persona es un límite de
# COMPRA, no evidencia de escasez de la edición (falso ultra_rare).
_PER_PERSON_QUOTA_RE = re.compile(
    r'(?:per|par|pro)\s+(?:person|persona|customer|order|household|personne)',
    re.I,
)
_JP_PER_PERSON_RE = re.compile(r'お\s*(?:一|1)\s*人様')

# Contexto inmediato que indica firma IMPRESA (en una lámina/postal de regalo),
# no un ejemplar firmado a mano. Caso real: Capitán Harlock Letrablanka —
# "lámina firmada" (firma impresa) lo subía a ultra_rare con 170 copias en stock.
_PRINTED_SIGNATURE_NOUNS_RE = re.compile(
    r'(?:l[áa]minas?|postal(?:es)?|prints?|ilustraci[óo]n(?:es)?|tarjetas?|'
    r'p[óo]ster(?:es|s)?|estampas?)\b[^.;,!?]{0,24}$'
)


def _has_hand_signed(text: str) -> bool:
    """True si el texto indica un ejemplar firmado A MANO.

    "firmado/firmada" precedido (en la misma cláusula) por lámina/postal/
    print/etc. es una firma IMPRESA en un extra de regalo — no evidencia de
    ultra_rare. Caso real: "lámina firmada" de Letrablanka con 170 copias en
    stock; "postal de regalo firmada por la autora".
    """
    for m in re.finditer(r'\bfirmad[oa]s?\b', text):
        prefix = text[max(0, m.start() - 40):m.start()].strip()
        if _PRINTED_SIGNATURE_NOUNS_RE.search(prefix):
            continue
        return True
    return False


# Keywords que indican tirada única explícita / no-reimpresión. Son la
# EVIDENCIA que mantiene un item en 'rare' bajo el modelo default-common
# (2026-06-10). Investigación 2026-05-30: 98%+ de confianza de que estos
# indican no-reimpresión.
_SINGLE_RUN_KEYWORDS = (
    # Explícito "tirada única" / "no reimpresión" (multilingual)
    "tirage unique", "tirada única", "tiratura unica", "edizione unica",
    "tiratura limitata", "limitata alla prima tiratura",
    "limitata nel tempo",
    "no se reimprimirá", "no volverá a imprimirse",
    # ES: formulaciones directas de no-reimpresión
    "no habrá reimpresiones", "no se reimprime",
    # ES: tirada limitada / sin reimpresión (con y sin acento; el text de
    # derive_rarity_tier es lower() pero NO strip de acentos).
    "tirada limitada", "sin reimpresión", "sin reimpresion",
    "single print run", "one print run only",
    "limited to a single print",
    # First-print-only bonuses (el libro se reimprime, el bonus no)
    "prima tiratura", "primera tirada", "première tirage",
    "初版限定", "初回限定", "shokai gentei",
    # Event-tied editions (celebración con extras)
    "celebration edition",
    # Lucca Comics — sustituido por patrón word-boundary (_SINGLE_RUN_PATTERNS)
    # que captura variantes ("Variant Lucca 2015", "a Lucca", "Lucca Changes").
    # Las entradas de keyword se QUITAN; el patrón es la autoridad.
    # JP: 限定版/特装版 son single-print-run por convención de mercado (no se
    # reimprimen con el extra); 受注生産 es literalmente impresión bajo pedido.
    "限定版", "特装版", "受注生産", "完全受注生産",
    # JP: exclusivas de tienda/quantity — no se reimprimen con el extra de la tienda
    "アニメイト限定", "とらのあな限定", "ゲーマーズ限定", "店舗限定",
    "完全生産限定", "数量限定",
    # FR: política editorial oficial (Pika FAQ 2026): "les éditions limitées et les
    # éditions collectors ne sont pas réimprimées" — misma convención que 限定版 JP.
    "édition collector", "coffret collector",
    # KR: 한정판 (LE de fábrica con ISBN propio) / 초회한정 (first-print-only).
    # NO 한정 a secas (sobre-matchea: aparece en frases no-escasez). El signal
    # `limited` ya existe para estas keywords (ver detect signals KR), pero
    # derive_rarity_tier no consume ese signal — la evidencia entra acá.
    "한정판", "초회한정",
    # Explicit sold-out / agotado en editorial
    "verlagsvergriffen", "épuisé éditeur",
)
# NOTA (2026-06-10): la familia genérica "limited edition / édition limitée /
# edizione limitata / edición limitada" y "anniversary/aniversario" se QUITÓ
# de esta lista: en un tracker de ediciones especiales esas frases describen
# a la mitad del corpus (3 367 items con signal `limited`) y no discriminan
# escasez real — eran la causa #1 de que 81% del corpus quedara en 'rare'
# (precisión medida: 54%). La escasez real se evidencia con print run,
# no-reimpresión explícita, lotería/evento o stock agotado verificado.

# Señales de tirada única / escasez que necesitan regex (orden de palabras libre
# o word boundary) y no pueden expresarse como keyword simple.
_SINGLE_RUN_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Lucca Comics: cualquier mención word-boundary captura variantes como
    # "Variant Lucca 2015", "in esclusiva a Lucca", "Lucca Changes".
    # Sin tirada explícita no distinguimos 50 de 5000 copias → rare, no ultra.
    # Items con print run explícito siguen llegando a ultra_rare via _PRINT_RUN_RE.
    re.compile(r'\blucca\b', re.I),
    # Exclusivas de evento/festival con orden de palabras libre:
    # "sold exclusively at Napoli Comicon 2015",
    # "available exclusively at Japan Expo 2025",
    # "released exclusively during the festival Comic Fes 2023".
    re.compile(
        r'exclusiv\w*[^.;:!?]{0,60}\b(?:comicon|comic[- ]?con|japan ?expo|manga barcelona|'
        r'cartoomics|etna comics|comic ?fes|festival|fiera)\b'
        r'|\b(?:comicon|comic[- ]?con|japan ?expo|manga barcelona)\b[^.;:!?]{0,40}exclusiv',
        re.I,
    ),
    # Variantes furoku/appendix de revista JP (Mangavariant): inobtenibles
    # fuera del mercado de segunda mano.
    re.compile(r'appendix of the (?:omnibus )?magazine|supplement to the magazine|\bfuroku\b', re.I),
    # Exclusiva de retailer expresada en texto (sin signal retailer_exclusive):
    # "exclusive to Kinokuniya bookstores", "exclusive to Panini online shop".
    re.compile(r'exclusive(?:ly)?\s+(?:to|at)\s+[^.;:!?]{0,40}(?:online\s+(?:store|shop)|bookstores?\b)', re.I),
    # Out-of-print / agotado en editorial (multilingual).
    re.compile(r'\bout of print\b|descatalogad[oa]|fuera de cat[áa]logo|\bvergriffen\b|épuisé|\besaurito\b|絶版', re.I),
)

_TOKUTEN_SOURCES = frozenset({
    "booksprivilege",
})

# Fuentes de referencia: catalogan qué EXISTE, no qué está disponible hoy.
# Catalogan SOLO ediciones de colección, no catálogo de tienda.
# Guard activo en derive_rarity_tier: si el item proviene ÚNICAMENTE de estas
# fuentes y ninguna regla de evidencia lo clasificó, la incertidumbre se
# resuelve a 'rare' (fallback, 2026-06-10, decisión owner).
_REFERENCE_ONLY_SOURCES = frozenset({
    "mangavariant", "sumikko", "booksprivilege", "blogbbm",
})

# NOTA (2026-06-11): se eliminó la whitelist `_COMMON_CATALOG_RULES` /
# `_matches_common_catalog` (líneas de catálogo permanente por publisher,
# 2026-05-30). Era parte del modelo viejo default-rare (excepción para llegar
# a common); con el modelo default-common quedó sin callers — el default ya ES
# common y la escasez se prueba con evidencia. Si se necesita de nuevo, está
# en git history (commit 0a4ead5 y anteriores).


def _is_reference_only_source(source: str) -> bool:
    """True si la fuente es de referencia/catálogo, no de retailer."""
    src = source.lower()
    return any(r in src for r in _REFERENCE_ONLY_SOURCES)


def _extract_print_run(text: str) -> int | None:
    """Extract explicit print run from text, e.g. 'limited to 216 copies' → 216.

    Guardas contra falsos positivos:
    - Cupo de compra por persona ("limited to 2 copies per person", "par
      personne", "お一人様2点限り"): es un límite de COMPRA, no la tirada → None.
    - Backstop: descarta print runs < 10 (no existen tiradas retail de <10
      ejemplares; un número tan chico casi siempre es un cupo/typo).

    También reconoce "N copie numerate" (IT, sin lead-in "limitat-").
    """
    m = _PRINT_RUN_RE.search(text)
    if not m:
        m = _PRINT_RUN_NUMERATE_RE.search(text)
    if not m:
        return None
    # Cupo por persona en el contexto inmediato del match → no es tirada.
    # Latin: el marcador ("per person"…) va DESPUÉS del número; JP: お一人様 va
    # ANTES (cubrimos ambas direcciones mirando una ventana alrededor del match).
    tail = text[m.end():m.end() + 24]
    window = text[max(0, m.start() - 16):m.end() + 24]
    if _PER_PERSON_QUOTA_RE.search(tail) or _JP_PER_PERSON_RE.search(window):
        return None
    try:
        run = int(m.group(1).replace(",", "").replace(".", ""))
    except (ValueError, AttributeError):
        return None
    if run < 10:
        return None
    return run


def derive_rarity_tier(
    signal_types: list[str],
    source: str,
    description: str,
    title: str,
    publisher: str = "",
    stock_status: str = "",
    sources: list[str] | None = None,
) -> str:
    """Clasifica un item en uno de 4 tiers de rareza — modelo default-common.

    Rediseño 2026-06-10: el default pasó de 'rare' a 'common'. El modelo viejo
    ("rare salvo que pruebes lo contrario") dejó al 81% del corpus en rare con
    54% de precisión medida contra la web. Ahora cada tier por encima de common
    exige EVIDENCIA:

    1. ultra_rare: numerado, firmado a mano (no firma impresa en lámina),
       exclusiva de evento, lotería, O print run explícito ≤ 500.
    2. super_rare: print run explícito ≤ 2500, O retailer_exclusive CON stock
       agotado verificado (stock_status='out_of_stock').
    3. rare: escasez evidenciada sin tirada corta documentada — stock agotado
       verificado, retailer_exclusive/tokuten sin verificación, keyword de
       no-reimpresión (_SINGLE_RUN_KEYWORDS), o patrón de evento/furoku/OOP
       (_SINGLE_RUN_PATTERNS: Lucca word-boundary, exclusivas de festival,
       furoku/appendix de revista, exclusivas de retailer en texto, out-of-print),
       o item exclusivamente de fuentes de referencia sin evidencia en ningún
       sentido (fallback de incertidumbre — ver _REFERENCE_ONLY_SOURCES).
    4. common: default. Sin badge en la UI; se promueve solo con evidencia
       (retrofit check_stock.py llena stock_status desde las páginas fuente).

    `stock_status`: '' (desconocido) | 'in_stock' | 'out_of_stock' — lo llena
    el retrofit check_stock.py con timestamp en stock_checked_at.

    `sources`: lista de nombres de TODAS las fuentes del item (para el fallback
    de referencia). Si es None se usa [source] como fallback de un solo origen.

    Returns: 'ultra_rare' | 'super_rare' | 'rare' | 'common'
    """
    sigs = set(signal_types or [])
    text = f"{title} {description}".lower()
    src = (source or "").lower()
    print_run = _extract_print_run(text)
    out_of_stock = stock_status == "out_of_stock"

    # --- Ultra Rare: tirada ínfima documentada o canal de evento/lotería ---
    if any(kw in text for kw in _ULTRA_RARE_KEYWORDS):
        return "ultra_rare"
    if _has_hand_signed(text):
        return "ultra_rare"
    if any(pat.search(text) for pat in _ULTRA_RARE_PATTERNS):
        return "ultra_rare"
    if print_run is not None and print_run <= 500:
        return "ultra_rare"

    # --- Super Rare: tirada corta documentada o exclusiva agotada ---
    if print_run is not None and print_run <= 2500:
        return "super_rare"
    if "retailer_exclusive" in sigs and out_of_stock:
        return "super_rare"

    # --- Rare: escasez evidenciada sin tirada corta documentada ---
    if print_run is not None:
        # Tirada explícita >2500: documentadamente única, pero no corta.
        return "rare"
    if out_of_stock:
        return "rare"
    if "retailer_exclusive" in sigs and stock_status != "in_stock":
        # Exclusiva de retailer sin stock verificado: escasa por canal, pero
        # sin evidencia de agotamiento no llega a super_rare (caso real: Ichi
        # the Witch variant en stock a $11.99 estaba marcada super_rare).
        # Con stock VERIFICADO ('in_stock') la exclusividad de canal no impide
        # conseguirlo hoy → sigue la cascada (normalmente common).
        return "rare"
    if any(t in src for t in _TOKUTEN_SOURCES):
        return "rare"
    # Keyword de no-reimpresión (_SINGLE_RUN_KEYWORDS): evidencia de escasez
    # SALVO que el stock esté verificado in_stock (guard red team). Si podemos
    # comprarlo hoy, la convención de "no se reimprime" no lo hace escaso:
    # p. ej. un 限定版 JP todavía disponible en la tienda → common, no rare.
    if stock_status != "in_stock" and any(kw in text for kw in _SINGLE_RUN_KEYWORDS):
        return "rare"
    if any(p.search(text) for p in _SINGLE_RUN_PATTERNS):
        return "rare"

    # --- Fallback fuentes de referencia (2026-06-10, decisión owner) ---
    # Mangavariant/Sumikko/BooksPrivilege catalogan SOLO coleccionables, no
    # catálogo de tienda. Si el item proviene ÚNICAMENTE de ahí y ninguna
    # regla de evidencia lo clasificó, la incertidumbre se resuelve a 'rare'
    # (no a common): que esté documentado en una DB de coleccionismo y en
    # ninguna tienda ES la señal. Con stock verificado sigue common.
    all_sources = sources if sources is not None else ([source] if source else [])
    if all_sources and stock_status != "in_stock" \
            and all(_is_reference_only_source(s) for s in all_sources):
        return "rare"

    # --- Common: default (sin evidencia de escasez) ---
    # El signal `limited` y `variant_cover` ya NO fuerzan rare: en este corpus
    # (tracker de ediciones especiales) describen al item típico, no escasez.
    return "common"


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
    re.compile(r"\b(?:vol(?:ume|umen|\.)?|tome|tomo|tom|band)\s*\.?\s*\d", re.IGNORECASE),
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
        r"(?:Edition|Edizione|Édition|Edición|Edicion|Edição|Edicao)\b",
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

# URLs de productos NO-manga por sección del sitio. El título no alcanza:
# "Castlevania: The Complete Series, Limited Edition" (Blu-ray de VIZ) no
# dice DVD/Blu-ray, pero su URL vive bajo /anime/. Descarte temprano en
# is_likely_manga(), mismo mecanismo que _BLOG_URL_PATTERNS.
_NON_MANGA_URL_PATTERNS = re.compile(
    r"viz\.com/anime/"                # Blu-ray/DVD/steelbook de anime VIZ
    , re.IGNORECASE,
)


# NON-MANGA tier HARD: productos que SIEMPRE son productos completos, jamás
# extras dentro de una edición especial de manga. Match aquí → descarte
# inmediato, sin pasar por rescue de strong-manga (esto es importante para
# casos como "<título japonés> Blu-ray BOX 下巻" donde "巻" matchearía como
# strong-manga pero el ítem real es Blu-ray).
_NON_MANGA_HARD: tuple[re.Pattern[str], ...] = (
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
    re.compile(r"\bcomic\s+cover\s+(?:art\s+)?print\b", re.IGNORECASE),
    re.compile(r"\bpaperweight\b", re.IGNORECASE),
    re.compile(r"\b(?:enamel\s+)?pin\s+set\b", re.IGNORECASE),
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
    # 図鑑未掲載 = "no publicado en el zukan" (describe el BONUS de una edición
    # especial, ej. キン肉マン data files) → no matchear (gotcha #92).
    re.compile(r"図鑑(?!未掲載)"),
    re.compile(r"\d+月号"),                  # "7月号" = revista mensual
    # 限定版プレミアムBOX = edición limitada premium de un MANGA; el target son
    # idol/goods boxes sin marcador de edición de libro (gotcha #92).
    re.compile(r"(?<!限定版)プレミアムBOX"),
    re.compile(r"学研の図鑑"),
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

# NON-MANGA tier HARD-UNLESS-BONUS (gotcha #92): productos completos (DVD,
# figura, standee, bundle) que en los TÍTULOS OFICIALES de ediciones
# especiales aparecen como BONUS incluido — desde la política de títulos
# 2026-06-12 el title es el nombre oficial scrapeado, así que vuelve a nombrar
# el extra ("夏目友人帳 フィギュアストラップ付き特装版", "テラフォーマーズ(21)特装版 DVD
# LIMITED EDITION", "Ediz. variant. Con acrylic standee"). Si el título trae
# un marcador de inclusión (付き/同梱/特装版/con/with/avec…) el match NO
# descarta; sin marcador, descarte HARD normal.
_NON_MANGA_HARD_UNLESS_BONUS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:DVD|blu-?ray)(?:\s*(?:BOX|SET|EDITION|DISC)|\b)", re.IGNORECASE),
    re.compile(r"ブルーレイ|DVD\s*BOX"),
    # フィギュア sola es producto; el lookahead corto cubre "フィギュア付" directo,
    # el rescue por marcador cubre "フィギュアストラップ付き" (sustantivo entremedio).
    re.compile(r"フィギュア(?!付|同梱|付録)"),
    # standee / Variant Bundle como producto principal (Dark Horse Direct);
    # como bonus en ediciones italianas ("Con acrylic standee", "Variant
    # Bundle con Storia Extra") se rescatan por el marcador.
    re.compile(r"\bstandees?\b", re.IGNORECASE),
    re.compile(r"\b(?:Exclusive\s+)?Variant\s+Bundle\b", re.IGNORECASE),
)

# Marcadores de "bonus incluido" — POSICIONALES respecto del match (gotcha
# #92): el marcador debe estar pegado al producto-bonus, no en cualquier parte
# del título ("神の庭付き楠木邸 Blu-ray BOX" tiene 付き como parte del NOMBRE de
# la obra y sigue siendo un Blu-ray de anime → rechazar).
#   - 特装版/同梱版 en cualquier parte: término de edición de LIBRO (no rescata
#     limited de anime, que usan 限定版 a secas).
#   - 付/同梱 hasta 12 chars DESPUÉS del match ("(Blu-ray)付限定版",
#     "フィギュアストラップ付き", "DVD＋パクティオカード同梱").
#   - con/with/avec/mit/inkl/incluye/+ hasta 16 chars ANTES ("Con acrylic
#     standee") o 6 DESPUÉS ("Variant Bundle con Storia Extra").
#   - "+"/"＋" en cualquier parte ANTES del match: dos obras unidas en un
#     bundle de manga ("Yomi No Tsugai Variant + FMA Variant Bundle 1").
_BOOK_EDITION_MARK_RE = re.compile(r"特装版|同梱版")
_BONUS_AFTER_RE = re.compile(r"付|同梱")
_BONUS_ROMANCE_RE = re.compile(
    r"\b(?:con|with|avec|mit|inkl\.?|incluye[n]?|include[sd]?)\b|\bw/|[+＋]",
    re.IGNORECASE,
)


def _bonus_context_near(blob: str, m: re.Match) -> bool:
    """True si el match de _NON_MANGA_HARD_UNLESS_BONUS está marcado como
    bonus incluido de una edición (ver gotcha #92)."""
    if _BOOK_EDITION_MARK_RE.search(blob):
        return True
    if _BONUS_AFTER_RE.search(blob[m.end():m.end() + 12]):
        return True
    if _BONUS_ROMANCE_RE.search(blob[max(0, m.start() - 16):m.start()]):
        return True
    if _BONUS_ROMANCE_RE.search(blob[m.end():m.end() + 6]):
        return True
    if "+" in blob[:m.start()] or "＋" in blob[:m.start()]:
        return True
    return False

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
    # T-shirt como producto; "con/with/avec/mit/+ T-shirt" es BONUS de una
    # edición (ej. "Sakamoto Days Variant con T-shirt 3", gotcha #92).
    # Lookbehinds fijos en serie (Python exige anchura fija por lookbehind).
    re.compile(
        r"(?<!con )(?<!with )(?<!avec )(?<!mit )(?<!\+ )(?:\bT-?shirt\b)|\bcamiseta\b|\bplayera\b",
        re.IGNORECASE,
    ),
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
_COMICS_TITLE_EXCEPTION_PATTERN: re.Pattern[str] | None = None
_COMICS_FORMAT_PATTERN: re.Pattern[str] | None = None


def _load_comics_blacklist() -> dict[str, Any]:
    """Lee data/comics_blacklist.yml; resultado se cachea en globals."""
    global _COMICS_BLACKLIST, _COMICS_PUBLISHERS
    global _COMICS_FRANCHISE_PATTERN, _COMICS_TITLE_EXCEPTION_PATTERN, _COMICS_FORMAT_PATTERN
    if _COMICS_BLACKLIST is not None:
        return _COMICS_BLACKLIST
    # Anclar a la raíz del repo (parent de scripts/) — NO al CWD: si el proceso
    # corre desde otro directorio, un path relativo dejaba de filtrar Marvel/DC
    # en SILENCIO (hallazgo B4 Fable 2026-07-08). Fallback al CWD por compat.
    path = Path(__file__).resolve().parent.parent / "data" / "comics_blacklist.yml"
    if not path.exists():
        path = Path("data/comics_blacklist.yml")
    if not path.exists():
        print(f"[WARN] comics_blacklist.yml no encontrado ({path}); "
              "is_comic_not_manga NO filtrará Marvel/DC/etc.", file=sys.stderr)
        _COMICS_BLACKLIST = {
            "publishers": [], "franchise_keywords": [],
            "title_exceptions": [], "format_keywords": [],
        }
        return _COMICS_BLACKLIST
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception as exc:
        print(f"[WARN] comics_blacklist.yml no parseó ({path}): {exc}; "
              "is_comic_not_manga degradado a blacklist vacía.", file=sys.stderr)
        data = {}
    _COMICS_BLACKLIST = {
        "publishers": data.get("publishers") or [],
        "franchise_keywords": data.get("franchise_keywords") or [],
        # Soporte retrocompatible: acepta tanto "title_exceptions" (nuevo nombre)
        # como "franchise_exceptions" (nombre legacy, por si hubiera YAMLs viejos).
        "title_exceptions": data.get("title_exceptions") or data.get("franchise_exceptions") or [],
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
    exc_kw = [re.escape(k) for k in _COMICS_BLACKLIST["title_exceptions"] if k]
    if exc_kw:
        # Substring case-insensitive — las excepciones son frases específicas
        # (p.ej. "Deadpool: Samurai", "Eagle: The Making of") que no pueden
        # matchear falsamente. Neutralizan tanto franchise_keywords como
        # patrones hard non-manga.
        _COMICS_TITLE_EXCEPTION_PATTERN = re.compile(
            r"(?:" + "|".join(exc_kw) + r")",
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
        # Antes de rechazar, verificar si el título está en title_exceptions:
        # títulos que contienen una keyword de franquicia occidental pero son
        # manga reales (crossovers, adaptaciones japonesas oficiales, etc.).
        if _COMICS_TITLE_EXCEPTION_PATTERN and _COMICS_TITLE_EXCEPTION_PATTERN.search(title):
            pass  # excepción activa → no rechazar por franchise
        else:
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
# danmei/manhua/manhwa/donghua: las novels asiáticas (Seven Seas danmei
# deluxe: Mo Dao Zu Shi, Dinghai Fusheng Records…) son "light novels con
# bonus" — EN scope según CLAUDE.md. Un artbook tampoco es novela pura.
_NOVEL_BYPASS_PATTERNS = re.compile(
    r"\bmanga\b"
    r"|\blight\s+novel\b|\bnovela\s+ligera\b|\bnovela\s+gr[áa]fica\b"
    r"|\branobe\b|\bラノベ|\bライトノベル"
    r"|\bdanmei\b|\bmanhua\b|\bmanhwa\b|\bdonghua\b"
    r"|\bart\s*book\b"
    # "(Novel)" como paréntesis en el título = marcador de línea editorial
    # asiática (Seven Seas danmei/LN). Los bestsellers occidentales que este
    # filtro caza no se titulan "X (Novel)".
    r"|\(novel\)"
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

    # 0a-quinquies) URLs de secciones no-manga del sitio (anime/video).
    # El título de un Blu-ray de VIZ no menciona DVD/Blu-ray; la URL sí.
    if url and _NON_MANGA_URL_PATTERNS.search(url):
        m = _NON_MANGA_URL_PATTERNS.search(url)
        return False, f"non_manga_url:{m.group(0)[:40]}"

    blob = title
    if description:
        # Mirar también en descripción para 'incluye manga' etc. pero NO
        # para detectar non-manga: la descripción de un manga puede mencionar
        # "figura de regalo" sin que el manga deje de ser manga.
        blob_extra = f"{title}\n{description}"
    else:
        blob_extra = title

    # 0) Non-manga HARD: discriminante absoluto.
    # Antes de evaluar los patrones hard, verificar title_exceptions: títulos
    # que son manga reales y podrían matchear un patrón hard (ej. "Eagle: The
    # Making of an Asian-American President" matchea \bThe\s+Making\s+of\b).
    _load_comics_blacklist()
    if title and _COMICS_TITLE_EXCEPTION_PATTERN and _COMICS_TITLE_EXCEPTION_PATTERN.search(title):
        pass  # título exceptuado → saltar todos los patrones hard
    else:
        for pat in _NON_MANGA_HARD:
            if pat.search(blob):
                return False, f"non_manga_hard:{pat.pattern[:40]}"
        # HARD-UNLESS-BONUS (gotcha #92): el producto-completo (DVD/figura/
        # standee/bundle) NO descarta si el título oficial lo marca como
        # bonus incluido de una edición (付き/同梱/特装版/con/with/… pegado
        # al match — ver _bonus_context_near).
        for pat in _NON_MANGA_HARD_UNLESS_BONUS:
            m = pat.search(blob)
            if m and not _bonus_context_near(blob, m):
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
    # "magazine" case-insensitive (títulos reales como "ONE PIECE magazine",
    # gotcha #96), pero ignorando lo que va entre paréntesis para no disparar
    # con marketing tipo "Berserk 41 (sale magazine)".
    if re.search(r"\bmagazine\b", _BRACKETED_RE.sub(" ", title or ""), re.IGNORECASE):
        return "magazine"
    # "画集付き特装版" = el artbook es un cuadernillo INCLUIDO como bonus, no el
    # producto → NO clasificar como artbook (el producto es el tomo). Mismo
    # criterio que la demotion de detect_signals. Ver queja del owner 2026-06-04.
    suppress_artbook = bool(_ARTBOOK_BONUS_ATTACH_RE.search(text))
    # Word-boundary match (igual que detect_signals). Antes hacíamos substring
    # match, lo que causaba que "Manga Artbooks" en descripción etiquetara
    # tomos regulares como product_type=artbook (Rin-ne, Bleach, etc.).
    for ptype, words in PRODUCT_TYPE_KEYWORDS:
        if ptype == "artbook" and suppress_artbook:
            continue
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


def is_curated_collectible_source(candidate: Any) -> bool:
    """¿El candidato viene de una fuente 100% CURADA de coleccionables y debe
    saltar el gate `is_collectible_edition`?

    Dos catálogos curados por diseño donde exigir la keyword en el título
    descartaría items legítimos:

    - **variant-catalog** (Mangavariant): cataloga SOLO variants; su título a
      menudo dice sólo "Vol.1 - Cover A" / "First print" sin keyword de edición.
    - **artbook** (catálogos de artbooks de editoriales, p.ej. "FR - Glénat Art
      Books"): la PÁGINA entera son artbooks, pero el título del producto rara
      vez trae "art book"/"画集" ("L'Art de Berserk", "One Piece Color Walk",
      "Rumiko Takahashi Colors"). Sin este bypass caían como `regular_tomo`
      pese a ser literalmente el catálogo de artbooks de la editorial. Para
      estos forzamos `product_type='artbook'` (si no es ya un tipo coleccionable)
      para que la fila quede correctamente tipada y `is_collectible_edition` la
      acepte por su regla 3.

    ⚠️ Este bypass se aplica SIEMPRE **después** de `is_likely_manga`: los items
    no-manga de esas mismas páginas (BD occidental — Cromwell, Druillet en la
    página de Glénat) ya quedaron filtrados aguas arriba por relevancia-manga /
    purity. Este helper NO relaja ese gate; sólo el de coleccionabilidad.
    """
    tags = getattr(candidate, "tags", None) or []
    if "variant-catalog" in tags:
        return True
    if "artbook" in tags:
        if getattr(candidate, "product_type", "") not in COLLECTIBLE_PRODUCT_TYPES:
            candidate.product_type = "artbook"
        return True
    return False

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
    # "3-in-1 Edition" / "2-in-1 Edition" (VIZ/Shojo Beat) capturan "in-1"
    # como lore-word; son omnibus rústica = tomo grueso (gotcha #18).
    r"Omnibus|in-1"
    # Genéricos ES/IT/FR (mismas categorías que la lista inglesa de arriba:
    # new / ordinales / standard / regular / original / digital / idioma).
    r"|Nueva|Nuova|Nouvelle|Primera|Prima|Première|Premiere"
    r"|Segunda|Seconda|Tercera|Terza|Última|Ultima"
    r"|Estándar|Estandar|Regolare|Originale|Digitale|Numérique|Numerique|Impresa"
    r"|Española|Espanola|Inglesa|Italiana|Japonesa|Alemana|Francesa"
    # Genéricos PT-BR: reimpresión / formato estándar / mercado. Sin esto,
    # "Primeira Edição" / "Nova Edição" / "Edição Brasileira" colarían tomos
    # normales por el gate de coleccionable. (Segunda ya está cubierta arriba.)
    r"|Primeira|Nova|Padrão|Padrao|Comum|Brochura|Brasileira)\b)"
    r"([A-Za-z][\w\-]{2,})\s+"
    r"(?:Edition|Edizione|Édition|Edición|Edicion|Edição|Edicao)\b",
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
    r"\b(?:vol|tome|tomo|tom|band|volume|volumen)\s*\.?\s*\d{1,3}\b"  # vol N (1-3 dígitos; tom = polaco)
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
# 2026-06-10: también revistas de PRENSA occidentales sobre cultura manga.
# Caso real: "ATOM" (Custom Publishing France, 33 nºs) entró como 14 items
# mapeados a la serie astro-boy. IMPORTANTE: las alternativas de título
# "Atom Hardcover" / "Mighty Atom Magazine|Deluxe|Hardcover" se REMOVIERON
# de este patrón porque colisionan con las ediciones deluxe REALES de Astro
# Boy de Planeta (ES, slugs astro-boy-planeta-deluxe-es-1..7) — tras la
# estandarización también quedan como "Astro Boy | Mighty Atom Deluxe N".
# La revista ATOM se discrimina por URL (ver _UMBRELLA_MAGAZINE_URL_PATTERN).
# "Atom" suelto sigue sin incluirse (colisiona con Atom: The Beginning).
_UMBRELLA_JP_MAGAZINE_PATTERN = re.compile(
    r"\b(?:Weekly\s+|Monthly\s+)?(?:Sh[ōo]nen|Young|Big|Bessatsu)\s+"
    r"(?:Jump|Magazine|Sunday|Comic|Spirits|Original|Superior)\b"
    r"|\b(?:Comic\s+Beam|Comic\s+Zenon|Comic\s+Bunch|Comic\s+Birz|"
    r"Megami\s+Magazine|Newtype|Animage)\b"
    r"|\b(?:Animeland|Otaku\s+USA|Coyote\s+Mag)\b"
    r"|週刊少年(?:ジャンプ|マガジン|サンデー|チャンピオン)"
    r"|月刊(?:少年|ヤング|アフタヌーン|モーニング)",
    re.IGNORECASE,
)

# Revistas-paraguas detectadas por URL (no por título, para evitar colisiones
# con series legítimas que comparten parte del nombre).
# Caso: revista "ATOM" de Custom Publishing FR — todos los items tienen URL
# en manga-sanctuary.com con path "/magazine-atom-vol-N-...". No se puede
# discriminar por título porque "Mighty Atom Deluxe N" es también el título
# estandarizado de los tomos deluxe reales de Planeta (ES).
_UMBRELLA_MAGAZINE_URL_PATTERN = re.compile(
    r"manga-sanctuary\.com/magazine-atom-",
    re.IGNORECASE,
)


def _is_umbrella_magazine_title(title: str, signal_types: list[str] | None) -> bool:
    """True sólo si el TÍTULO *es* una revista-paraguas (antología multi-serie),
    no si meramente la menciona como descriptor.

    Gotcha #95: `_UMBRELLA_JP_MAGAZINE_PATTERN.search(title)` a secas producía
    falsos positivos sobre productos legítimos cuyo título lleva el nombre de la
    revista como SUFIJO descriptivo:
      - portadas variantes ("Sakamoto Days — The Order - Shonen Jump"),
      - revistas de UNA serie ("ONE PIECE magazine ... 週刊少年ジャンプと...").
    Esos items se rechazaban como `umbrella_magazine` (HARD_REASON en
    filter_collectible, ignora `standardized_at`) y se borraban del corpus pese a
    estar estandarizados — destrucción de datos en el cleanup del pipeline.

    Discriminadores (la antología real lleva su nombre como SUJETO inicial):
      1. `variant_cover` en signal_types ⇒ es una portada variante de una serie;
         el nombre de la revista es descriptivo ⇒ NO es la antología.
      2. El match de la revista debe arrancar al INICIO del título (con un margen
         corto para prefijos tipo "週刊"/"月刊"/store). "Weekly Shōnen Jump 2023
         No.42" o "週刊少年ジャンプ ..." matchean al inicio; los descriptores
         que aparecen tras "<Serie> — Vol.N - ..." no.
    """
    if "variant_cover" in set(signal_types or []):
        return False
    m = _UMBRELLA_JP_MAGAZINE_PATTERN.search(title)
    if not m:
        return False
    return m.start() <= 3


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

# Dígitos full-width JP → ASCII (gotcha #82). `\d` en regex unicode de Python
# MATCHEA ０-９ (U+FF10-FF19), así que los patterns de volumen capturan el
# dígito crudo ("特装版 ７" → volume "７") y contamina cluster_key. FUENTE
# ÚNICA de esta tabla — generate_slugs.py la importa de acá, no la dupliques.
FULLWIDTH_DIGITS_TABLE = str.maketrans("０１２３４５６７８９", "0123456789")

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
    # Acepta paréntesis half-width y full-width. El negative-lookahead descarta
    # AÑOS 19xx/20xx entre paréntesis ("Berserk Official Guidebook (2016)"), que
    # se colaban como volumen fantasma (hallazgo M2 Fable 2026-07-08).
    re.compile(r"[（(]\s*(?!(?:19|20)\d{2}[）)])(\d{1,4})\s*[）)]"),
    # Número seguido de calificador de edición (gotcha #60): "Title 13 Edición Especial",
    # "Berserk 21 Variant", "Title 1 Edición Limitada". El calificador hace inequívoco
    # que el número es un volumen, no parte del título. Más específico que el trailing.
    re.compile(
        r"\s(\d{1,3})\s+(?:Edici[oó]n\s+(?:Especial|Limitada|Coleccionista|Deluxe)|"
        r"Variant\b|Limited\b|Special\b|Artbook\b|Fanbook\b|Deluxe\b|Kanzenban\b|"
        r"Omnibus\b|Integral\b)",
        re.IGNORECASE,
    ),
    # Trailing bare number: "Berserk Deluxe 1", "One Piece 98".
    # Última prioridad. Guards: no captura años (1900-2099), ni ISBNs (>4 dígitos).
    # Requiere espacio antes del número para no capturar sufijos pegados ("abc123").
    re.compile(r"\s(\d{1,3})\s*$"),
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
    # Markers de volumen / pieza. OJO: NO incluir "no"/"no." — la palabra "no"
    # es parte real de nombres de serie ("No Longer Human", "Kaiju No. 8", "No
    # Guns Life", "Make wa Tada no Mahou"): stripearla mutilaba el series_key y
    # rompía la resolución de aliases (gotcha #43, hallazgo A2 Fable 2026-07-08).
    # El marcador real es nº/n° (con º/°), que sigue cubierto por _SERIES_STRIP_RE
    # y la pasada extra de abajo.
    "tomo", "tome", "volume", "vol.", "vol",
    "n.", "n°", "nº",
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
    # Full-width → ASCII ANTES de matchear: \d captura ０-９ igual, pero el
    # volumen devuelto debe ser ASCII puro (gotcha #82).
    title = title.translate(FULLWIDTH_DIGITS_TABLE)
    for pat in _VOLUME_EXTRACT_PATTERNS:
        # Preferir el ÚLTIMO match del patrón: el volumen va DESPUÉS del nombre,
        # así un número embebido en el nombre de la serie ("Kaiju Nº8 nº16") no
        # le gana al tomo real (hallazgo M1 Fable 2026-07-08; el fix del parser
        # de colecciones —gotcha #74— se generaliza acá al helper).
        matches = pat.findall(title)
        if matches:
            return matches[-1]
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
    # Full-width → ASCII primero: el volumen que llega ya es ASCII
    # (_extract_volume normaliza), así que sin esto el strip del número de
    # volumen no matchearía el "７" del título original (gotcha #82).
    text = title.translate(FULLWIDTH_DIGITS_TABLE)
    text = _BRACKETED_RE.sub(" ", text)
    text = _SERIES_STRIP_RE.sub(" ", text)
    # Quitar el MARCADOR de volumen + número juntos (nº1, n°1, #5, 巻3, 第3巻).
    # Sin esto, al quitar solo el dígito más abajo quedaba el marcador suelto
    # "nº" y el slug terminaba en "-no" (bug 2026-06-07: "Slam Dunk nº1" →
    # series_key "slam-dunk-no"). El `º`/`°` hace inequívoco que es marcador.
    text = re.sub(r"(?:n[º°]|＃|#|第)\s*\d*\s*巻?", " ", text, flags=re.IGNORECASE)
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


def isbn13(raw: str) -> str:
    """Normaliza un ISBN a ISBN-13 de dígitos puros. "" si no es un ISBN.

    Sin esto, el MISMO libro con ISBN-10 en una fuente e ISBN-13 (o con
    guiones) en otra cae en clusters distintos: la auditoría 2026-06-10
    encontró 88 grupos de duplicados escondidos así.
    """
    digits = re.sub(r"[^0-9Xx]", "", raw or "")
    if len(digits) == 13 and digits.isdigit():
        return digits
    if len(digits) == 10:
        core = "978" + digits[:9]
        if not core.isdigit():
            return ""
        check = (10 - sum(int(d) * (3 if i % 2 else 1)
                          for i, d in enumerate(core)) % 10) % 10
        return core + str(check)
    return ""


def derive_cluster_key(item: dict[str, Any]) -> str:
    """Devuelve la clave de agrupación para deduplicar items entre fuentes.

    Estrategia en cascada (más autoritativo primero):
    1. `edition_key` + `volume` → "edition:<edition_key>|<volume>". El
       edition_key lo asigna `/watch-standardize-catalog` (LLM-verified) o el
       heurístico del scraper, y representa la misma edición + publisher
       + mercado. Dos items con el MISMO edition_key + volume son el mismo
       producto físico aunque vengan de fuentes distintas — incluso si
       uno tiene ISBN y otro no (ej. PRH Comics con ISBN + Dark Horse
       Direct sin ISBN → mismo tomo, una sola card). El edition_key ya
       codifica publisher+market en su slug por construcción
       (`gon-norma-collector` vs `gon-glenat-collector`), por eso no
       necesita campos extra. El ISBN se preserva como metadata del item
       para búsqueda y enrichment, pero no como discriminante de grupo.
    2. Si NO hay edition_key, pero podemos derivar
       `(country, series, volume)` con una serie de >= 3 caracteres →
       fuzzy combinando esos + variant_tier + publisher.
    3. Cualquier otro caso → "url:<url>" (standalone, no se agrupa).

    ISBN NO se usa como criterio de fusión (removido 2026-07-07). La premisa
    "un ISBN = una edición" es FALSA en manga: portadas variantes comparten
    ISBN, especial y normal comparten ISBN, y varios retailers (p. ej.
    Mangaline MX) reusan un mismo ISBN en toda su línea — ej. 9788419177629
    aparece en Devilman #3 Y en Mao Dante #1, dos series distintas. Usar el
    ISBN pelado como clave fusionaba destructivamente ediciones/series
    distintas. El ISBN se CONSERVA en el row como metadata (búsqueda,
    enrichment) pero un item con isbn y sin edition_key CAE a la cascada
    fuzzy → url, que sí respeta la regla dura país+serie+volumen+tier+publisher.

    `variant_tier` y `publisher` son discriminantes para EVITAR juntar
    "OP100 normal" con "OP100 Celebration" (distinto tier) o ediciones de
    publishers distintos. PAÍS es discriminante (país = edición): no mezcla
    mercados que comparten idioma (ES-España vs ES-México).

    Antes este campo era `variant_sig = ",".join(sorted(signal_types))`. El
    problema: dos fuentes con descripciones distintas detectan signal_types
    ligeramente distintos del MISMO producto, y el set completo no mergea.
    `_variant_tier` colapsa esa varianza eligiendo solo el tier más
    específico — más tolerante, sigue diferenciando tomo-regular vs especial.
    """
    # Tier 0 (listadomanga): TODO item de una /coleccion clusteriza por
    # coleccion+kind+volumen, ANTES del edition_key. Regla del owner (gotcha #42/#48):
    # una /coleccion = UNA página de edición (todos sus tomos comparten edition_key),
    # PERO el dedup debe seguir distinguiendo variantes del mismo volumen (regular-34
    # vs especial-34) → la clave de cluster lleva el KIND. Los items de listadomanga
    # NUNCA se fusionan cross-fuente (verificado: 0 sources externas), así que usar
    # lmc en vez de edition_key no rompe ningún merge multi-fuente.
    #   - kind del synthetic URL `&item=<kind>-<vol>` si existe;
    #   - si no (old-format sin item=), del campo `lm_kind` (seteado por el retrofit
    #     unify_coleccion_edition); default 'regular'.
    _cole = re.search(r"listadomanga\.es/coleccion\.php\?id=(\d+)", item.get("url") or "")
    if _cole:
        # Canonicalizar el kind: el synthetic URL usa español (especial/alternativa/
        # limitada) y el lm_kind viejo usa el edition_slug inglés (special/variant/
        # limited). Mapeamos a UN vocabulario para que el MISMO producto (old-format
        # std vs new raw) comparta cluster y deduplique (gotcha #52).
        _LMC_KIND_CANON = {"especial": "special", "alternativa": "variant",
                           "limitada": "limited"}
        _it = re.search(r"[?&]item=([a-z]+)-([^-&]+)", item.get("url") or "")
        if _it:
            kind = _LMC_KIND_CANON.get(_it.group(1), _it.group(1))
            return f"lmc:{_cole.group(1)}:{kind}:{_it.group(2)}"
        kind = (item.get("lm_kind") or "regular").strip() or "regular"
        kind = _LMC_KIND_CANON.get(kind, kind)
        vol = (item.get("volume") or "").strip().translate(FULLWIDTH_DIGITS_TABLE)
        return f"lmc:{_cole.group(1)}:{kind}:{vol}"

    # Tier 1: edition_key (set by skill /watch-standardize-catalog o por el
    # heurístico de candidate_to_json). Cuando dos items comparten
    # edition_key, son por definición la misma edición/publisher/market.
    # Volume los distingue (tomo 1 vs tomo 2 de la misma edición).
    edition_key = (item.get("edition_key") or "").strip()
    if edition_key:
        # translate: el campo volume puede venir de parsers de fuente o del
        # LLM del standardize, no solo de _extract_volume (gotcha #82).
        volume = (item.get("volume") or "").strip().translate(FULLWIDTH_DIGITS_TABLE)
        return f"edition:{edition_key}|{volume}"

    # Tier 2: fuzzy (país + serie + volumen + variant_tier + publisher).
    # OJO: NO hay tier ISBN. El ISBN pelado NO es criterio de fusión (removido
    # 2026-07-07): en manga el mismo ISBN se repite entre ediciones/series
    # DISTINTAS (portadas variantes, especial vs normal, y retailers como
    # Mangaline MX que reusan un ISBN en toda su línea), así que fusionarlo
    # era destructivo. Un item con isbn pero sin edition_key cae acá (fuzzy)
    # o a url:, respetando la regla dura país=edición. El ISBN queda en el row
    # como metadata, no como clave.
    title = item.get("title") or ""
    country = (item.get("country") or "").strip().lower()
    publisher = (item.get("publisher") or "").strip().lower()
    signal_types = item.get("signal_types") or []
    variant_tier = _variant_tier(signal_types)
    volume = _extract_volume(title)
    series = _normalize_series_name(title, volume)
    url = (item.get("url") or "").strip()

    # Guardas anti-falso-positivo: series, country y volume son requeridos
    # para considerar dos items "el mismo producto" sin ISBN ni edition_key.
    # PAÍS (no idioma) es el discriminante porque "país = edición" es regla
    # dura: ES-España y ES-México comparten language pero son ediciones
    # DISTINTAS y no deben colapsar en el mismo cluster. Si country está
    # vacío, tampoco generamos clave fuzzy (evita que todos los country-vacío
    # caigan en el mismo bucket) → cae al tier url:.
    if (not series or len(series) < 3
            or not country
            or not volume):
        return f"url:{url}"

    return f"fuzzy:{country}|{series}|{volume}|{variant_tier}|{publisher}"


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
    #   - Por título: antologías JP + revistas occidentales inequívocas.
    #   - Por URL: casos donde el título colisiona con series reales (p.ej.
    #     revista ATOM de Custom Publishing FR vs. tomos Planeta deluxe ES).
    if _is_umbrella_magazine_title(title, signal_types):
        return False, "umbrella_magazine"
    if url and _UMBRELLA_MAGAZINE_URL_PATTERN.search(url):
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
    ) or bool(
        # URL sintética de listadomanga (coleccion.php?id=N&item=<kind>-<vol>):
        # es un producto catalogado VERIFICADO (una /coleccion real). Cuenta como
        # prueba-de-producto (gotcha #50) — si no, ediciones premium de 1 tomo sin
        # número en el título (ej. "21st Century Boys" Kanzenban) caían como
        # `regular_tomo` porque su signal premium viene del título de la coleccion.
        re.search(r"listadomanga\.es/coleccion\.php\?id=\d+&item=", _url)
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
    # tenga shape de VOLUMEN de manga. Esto distingue:
    #   - "Naruto 12 con marcapáginas exclusivo" → vol 12 → KEEP
    #   - "Ataque a los Titanes nº1" (cofre 1ª ed.) → vol 1 → KEEP
    #   - "Fandango your tickets, posters, trailers" → sin volumen → REJECT
    # El número puede venir suelto ("Naruto 12 con marcapáginas") O pegado a
    # "nº"/"n°" ("Ataque a los Titanes nº1", los cofres de 1ª ed. de listadomanga).
    # `\b\d+\b` SOLO NO basta: la "º" es word-char Unicode → sin boundary, y
    # tumbaba TODOS los cofres "nºN" con sólo signal `bonus` (caso real Attack on
    # Titan cole 1606: regular-1/17/27 rechazados como `regular_tomo`).
    matched_extras = sig_set & FIRST_EDITION_EXTRAS_SIGNAL_TYPES
    if matched_extras and re.search(r"\b\d+\b|n[º°]\s*\d+", title):
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
                    user_agent=str(item.get("user_agent", "")).strip(),
                    throttle_group=str(item.get("throttle_group", "")).strip(),
                )
            )

    return [source for source in sources if source.name and source.url]


class ThrottleRegistry:
    """Semáforos de concurrencia por HOST, con soporte de GRUPOS compartidos.

    Por defecto limita a `per_host_limit` requests concurrentes por hostname
    (comportamiento histórico). Las fuentes cuyo host está mapeado a un
    `throttle_group` (sources.yml) comparten en cambio UN semáforo por grupo
    (limit `group_limit`, default 1) más un delay mínimo `group_delay` entre
    requests del grupo.

    Motivación (run 2026-07-07): Dark Horse Direct, IT-Funside e IT-Manga Dreams
    resuelven al MISMO borde Shopify (23.227.38.0/24) y comparten el rate-limit
    remoto; un 429 en una golpea a todas. Agrupar sólo por hostname (el
    `--per-host-limit`) no las serializa entre sí. El grupo sí.

    Thread-safe: `acquire(url)` es un context manager usable desde los workers.
    """

    def __init__(
        self,
        per_host_limit: int,
        host_to_group: dict[str, str] | None = None,
        group_limit: int = 1,
        group_delay: float = 2.0,
    ) -> None:
        self.per_host_limit = max(1, int(per_host_limit))
        self.host_to_group = {
            (h or "").lower(): g for h, g in (host_to_group or {}).items() if h and g
        }
        self.group_limit = max(1, int(group_limit))
        self.group_delay = max(0.0, float(group_delay))
        self._sems: dict[str, threading.Semaphore] = {}
        self._last_start: dict[str, float] = {}
        self._lock = threading.Lock()

    def _key_for(self, url: str) -> tuple[str, bool]:
        host = (urlparse(url).hostname or "").lower()
        group = self.host_to_group.get(host)
        if group:
            return f"group:{group}", True
        return f"host:{host}", False

    def _sem(self, key: str, is_group: bool) -> threading.Semaphore:
        with self._lock:
            sem = self._sems.get(key)
            if sem is None:
                limit = self.group_limit if is_group else self.per_host_limit
                sem = threading.Semaphore(limit)
                self._sems[key] = sem
            return sem

    def _reserve_delay(self, key: str) -> float:
        """Reserva el próximo slot temporal del grupo y devuelve cuánto dormir.

        Espaciamos los INICIOS de request del grupo en al menos `group_delay`.
        Se reserva bajo lock (marcando el próximo inicio) para que threads que
        entren en ráfaga encadenen su espera en vez de solaparse.
        """
        if self.group_delay <= 0:
            return 0.0
        with self._lock:
            now = time.monotonic()
            last = self._last_start.get(key, 0.0)
            target = max(now, last + self.group_delay)
            self._last_start[key] = target
            return target - now

    @contextmanager
    def acquire(self, url: str):
        key, is_group = self._key_for(url)
        sem = self._sem(key, is_group)
        sem.acquire()
        try:
            if is_group:
                wait = self._reserve_delay(key)
                if wait > 0:
                    time.sleep(wait)
            yield
        finally:
            sem.release()


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
    # A7 (Fable 2026-07-08): flush+fsync antes del rename atómico — sin esto,
    # un corte justo tras el .tmp podía dejarlo sólo en page cache. Un
    # state.json vacío/truncado tras un corte reporta TODO el corpus como
    # "new" en el próximo run (re-flush completo).
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as file:
        file.write(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
        file.flush()
        os.fsync(file.fileno())
    tmp.replace(path)


def backup_and_rotate(path: Path, label: str, max_keep: int = 3,
                      timestamped: bool = False) -> Path:
    """Crea un backup de `path` en data/backups/<filename>/ y rota los más viejos.

    Default (`timestamped=False`, comportamiento histórico intacto): slot FIJO
    `data/backups/<filename>/<filename>.pre-<label>-bak`. Cada llamada lo pisa y
    la rotación ordena TODA la carpeta por mtime y deja max_keep — así los
    backups rotativos del scrape no se acumulan.

    Con `timestamped=True`: el nombre incluye timestamp
    `<filename>.<YYYYmmdd-HHMMSS>.pre-<label>-bak`, así llamadas sucesivas NO se
    pisan entre sí; la rotación poda SÓLO por el glob de ese patrón (mismo label)
    conservando los max_keep más recientes, sin tocar los slots fijos de otros
    labels. Útil para snapshots que deben conservarse (no pisarse) entre corridas.

    Crea las carpetas necesarias si no existen. Devuelve el Path del backup creado.
    """
    backups_dir = path.parent / "backups" / path.name
    backups_dir.mkdir(parents=True, exist_ok=True)
    if timestamped:
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = backups_dir / f"{path.name}.{ts}.pre-{label}-bak"
        dest.write_bytes(path.read_bytes())
        # Rotar SÓLO los backups timestamped de este label (no los slots fijos).
        family = sorted(
            backups_dir.glob(f"{path.name}.*.pre-{label}-bak"),
            key=lambda f: f.stat().st_mtime,
        )
    else:
        dest = backups_dir / f"{path.name}.pre-{label}-bak"
        dest.write_bytes(path.read_bytes())
        # A6 (Fable 2026-07-08): rotar SÓLO por-label, nunca la carpeta
        # entera. Antes esto ordenaba TODO `backups_dir` por mtime y podaba a
        # max_keep GLOBAL — con ~20 labels distintos escribiendo en la misma
        # carpeta (rescore, cluster, translate, apply-approvals, dedup-isbn,
        # dup-merge de serve…), una cadena de 3+ llamadas fixed-slot (el
        # enforcer encadena 5+) dejaba 3 archivos EN TOTAL, borrando el
        # snapshot pre-run inicial y los backups timestamped=True que
        # prometen conservarse. El slot fijo de este label es SIEMPRE 1
        # archivo (se pisa arriba), así que acá sólo hay que asegurarse de no
        # tocar los demás labels ni los timestamped.
        family = sorted(
            backups_dir.glob(f"{path.name}.pre-{label}-bak"),
            key=lambda f: f.stat().st_mtime,
        )
    for old in family[:-max_keep]:
        old.unlink()
    return dest


def is_approved(item: dict[str, Any]) -> bool:
    """True si el item fue aprobado manualmente desde el dashboard.

    `approved_at` (timestamp ISO) es un "golden record" marker: el owner
    confirmó que la metadata de esta card es correcta. Los retrofits y skills
    deben SALTEAR estos items (no re-derivar ni re-filtrar) y pueden usarlos
    como ejemplos de referencia de "dato bien hecho". El re-scrape preserva
    los campos descriptivos y sólo refresca info de mercado (precio/stock).
    Ver `append_jsonl` y la sección de aprobación en CLAUDE.md.
    """
    return bool(item.get("approved_at"))


# ── Modelo 1-fila-por-producto: merge de cluster (FUENTE ÚNICA DE VERDAD) ──────
#
# Un producto físico (cluster) es UNA fila en items.jsonl con un array
# `sources[]` que lista todas las fuentes donde se encontró. Estas tres
# primitivas son la ÚNICA implementación del merge — las usan append_jsonl
# (ingesta), build_web (embed) y el retrofit consolidate_sources. NO duplicar la
# lógica en otro lado (la divergencia entre sitios de merge fue la raíz de los
# bugs de fotos de 2026-06-02).

_SOURCE_FIELDS = (
    "source", "source_class", "country", "publisher", "language", "url",
    "image_url", "image_local", "stock_type", "detected_at",
    "release_date", "score",
)

# Campos curados que no deben perderse al elegir la fila canónica del cluster.
_CLUSTER_CURATED = (
    "series_key", "series_display", "edition_key", "edition_display", "volume",
    "standardized_at", "slug", "approved_at", "approved_by", "isbn",
    "author", "description", "description_es", "rarity", "rarity_verified_at",
)


def source_entry(item: dict[str, Any]) -> dict[str, Any]:
    """Subconjunto por-fuente de un item (precio/URL/país/stock por tienda)."""
    return {("name" if k == "source" else k): item.get(k, "" if k != "score" else 0)
            for k in _SOURCE_FIELDS}


def _img_stem(url: str) -> str:
    """Clave de dedup para images[]: normaliza la URL para que la misma imagen
    en distintas resoluciones de CDN (Shopify thumb/full, WP -NxM, query params
    irrelevantes) produzca el mismo stem y no genere entradas duplicadas.

    Delega en _gallery_url_normalize (strip Shopify size suffix + strip query
    params irrelevantes) ANTES de quitar el protocolo, para que
    "cdn.example.com/img_100x100.jpg" == "cdn.example.com/img.jpg".
    """
    normalized = _gallery_url_normalize(url or "")
    return re.sub(r"^https?://", "", normalized.split("?", 1)[0]).lower()


# Portada del row = primer images[] con url (images[0]). Es la ÚNICA fuente de
# verdad de la portada (se eliminaron los campos top-level image_url/image_local,
# decisión 2026-06-09). Versión canónica del accesor: image_store.cover_image;
# acá se inlinea para evitar fragilidad de import en el módulo core.
def _row_cover(it: dict[str, Any]) -> dict[str, Any] | None:
    for im in (it.get("images") or []):
        if im and im.get("url"):
            return im
    return None


def _cluster_completeness(it: dict[str, Any]) -> int:
    return (
        (1 if it.get("approved_at") else 0) * 10000
        + (1 if it.get("standardized_at") else 0) * 1000
        + (100 if it.get("isbn") else 0)
        + (10 if _row_cover(it) else 0)
    )


def _union_merge_images(images: Iterable[dict[str, Any] | None]) -> list[dict[str, Any]]:
    """Union-merge de images[] — FUENTE ÚNICA (Fable 2026-07-08, hallazgo A9).

    La usan `append_jsonl` (upsert old+new) y `merge_cluster` (consolidación por
    cluster). Antes divergían: `merge_cluster._push_img` dedupeaba SÓLO por
    `_img_stem`, sin rellenar `local`/`description` y aliaseando el dict del
    miembro; `append_jsonl` dedupeaba por `(kind, stem)`, rellenaba y copiaba. Esa
    divergencia dejaba viva la gotcha #87 en el camino de cluster (que corre en
    CADA append_jsonl vía consolidate_by_cluster).

    Contrato único:
      - Dedup por `(kind, _img_stem(url))`, preservando el ORDEN de 1ª aparición.
      - El entry conservado RELLENA sus campos vacíos (`local`, `description`)
        desde los duplicados posteriores — sticky en ambas direcciones (#87).
      - Cada entry es una COPIA (`dict(im)`): nunca aliasa el dict del miembro
        (mina para consolidate_sources).
      - Ignora imágenes sin `url`.
    """
    kept_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for im in images:
        if not im or not im.get("url"):
            continue
        k = (im.get("kind", ""), _img_stem(im.get("url", "")))
        kept = kept_by_key.get(k)
        if kept is not None:
            for f in ("local", "description"):
                if not kept.get(f) and im.get(f):
                    kept[f] = im[f]
            continue
        entry = dict(im)
        kept_by_key[k] = entry
        out.append(entry)
    return out


# Confiabilidad relativa de una fuente para rellenar metadata (publisher/fecha/
# ISBN) faltante en la canónica de un cluster (Fable 2026-07-08, hallazgo B15).
# Antes el fill tomaba el PRIMER miembro no-vacío por orden FÍSICO del archivo, así
# que "qué publisher gana" era arbitrario y una tienda ruidosa podía pisar a la
# editorial. Criterio determinista: official (sitio de la editorial) > bases
# comunitarias curadas > medios de confianza > catálogos curados > retailer
# (comercio, publisher a menudo ruidoso) > social > desconocido. Empate → orden
# físico (comportamiento previo). NO es autoridad sobre la agrupación (eso lo hace
# cluster_key); sólo desempata el relleno de campos escalares.
_SOURCE_CLASS_RANK: dict[str, int] = {
    "official": 6,
    "trusted_catalog": 5,
    "trusted_media": 4,
    "curated": 3,
    "retailer": 2,
    "social": 1,
}


def _member_reliability(it: dict[str, Any]) -> int:
    return _SOURCE_CLASS_RANK.get(it.get("source_class", ""), 0)


def merge_cluster(group: list[dict[str, Any]]) -> dict[str, Any]:
    """Fusiona N filas del MISMO producto en una sola, con `sources[]`.

    - Canónica = la más completa (aprobada > estandarizada > ISBN > imagen).
    - Campos faltantes en la canónica se rellenan desde cualquier miembro.
    - `sources[]` = union de las fuentes (usa el `sources[]` guardado de cada
      miembro si lo trae, si no `source_entry(member)`), dedup por URL.
    - `images[]` = union con la PORTADA canónica (`canonical.images[0]`) SIEMPRE
      primera (carrusel[0] == card), dedup por URL stem.
    - `extras[]` = union dedup por (description, release_date).
    """
    if len(group) == 1:
        only = dict(group[0])
        if not (isinstance(only.get("sources"), list) and only["sources"]):
            only["sources"] = [source_entry(only)]
        return only

    canonical = max(group, key=_cluster_completeness)
    merged = dict(canonical)
    # B15: rellenar campos escalares faltantes desde el miembro MÁS CONFIABLE
    # (source_class), no por orden físico. Sort ESTABLE por -reliability → los
    # empates conservan el orden físico (comportamiento previo).
    by_reliability = sorted(group, key=lambda it: -_member_reliability(it))
    for f in ("author", "release_date",
              "description", "isbn", "publisher"):
        if not merged.get(f):
            for it in by_reliability:
                if it.get(f):
                    merged[f] = it[f]
                    break
    for f in _CLUSTER_CURATED:
        if merged.get(f) in (None, ""):
            for it in by_reliability:
                if it.get(f) not in (None, ""):
                    merged[f] = it[f]
                    break

    # images union (FUENTE ÚNICA con append_jsonl, A9): portada canónica primero,
    # luego todas las de los miembros. Dedup por (kind, stem) + fill de local/
    # description + copia — todo dentro de _union_merge_images.
    cover = _row_cover(canonical)
    image_seq: list[dict[str, Any] | None] = [cover] if cover else []
    for it in group:
        image_seq.extend(it.get("images") or [])
    imgs = _union_merge_images(image_seq)
    if imgs:
        merged["images"] = imgs

    # extras union
    seen_e: set[tuple[str, str]] = set()
    extras: list[dict] = []
    for it in group:
        for ex in (it.get("extras") or []):
            if not ex or not ex.get("description"):
                continue
            k = (ex["description"], ex.get("release_date", ""))
            if k in seen_e:
                continue
            seen_e.add(k)
            extras.append(ex)
    if extras:
        merged["extras"] = extras

    merged["score"] = max((i.get("score") or 0) for i in group)

    # sources union — usa el sources[] guardado de cada miembro si lo trae
    seen_s: set[str] = set()
    sources: list[dict] = []
    for it in group:
        entries = it["sources"] if (isinstance(it.get("sources"), list) and it["sources"]) else [source_entry(it)]
        for s in entries:
            u = normalize_url_for_dedup(s.get("url", "") or "")
            if u in seen_s:
                continue
            seen_s.add(u)
            sources.append(s)
    sources.sort(key=lambda s: (s.get("url", "") != canonical.get("url", ""),
                                s.get("country", ""), s.get("name", "")))
    merged["sources"] = sources
    return merged


def consolidate_by_cluster(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Colapsa filas del mismo `cluster_key` en 1 fila por producto con sources[].

    Clusters `url:` (standalone) quedan como 1 fila cada uno. Idempotente.
    """
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for r in rows:
        key = r.get("cluster_key") or derive_cluster_key(r)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)
    return [merge_cluster(groups[k]) for k in order]


def description_src_hash(description: str) -> str:
    """Huella de la `description` fuente de una traducción: sha1(description)[:12].

    FUENTE ÚNICA de la fórmula. La escribe translate_descriptions.py como
    `description_es_src_hash` al traducir, y el upsert la verifica para invalidar
    traducciones obsoletas: si un re-scrape trae una `description` cuyo hash no
    coincide con el guardado, la traducción `description_es` vieja quedó stale y
    NO se preserva (se deja re-traducir). No reimplementar la fórmula en otro lado.
    """
    return hashlib.sha1((description or "").encode("utf-8")).hexdigest()[:12]


def _translation_is_stale(old: dict[str, Any], new_description: str) -> bool:
    """True si la `description_es` de `old` quedó obsoleta frente a `new_description`.

    Compara `description_es_src_hash` (= sha1 de la description que se tradujo)
    contra el hash de la description entrante. Backward-compatible: si el row
    viejo NO tiene el hash (traducciones previas a WO-B) → False (nunca stale,
    comportamiento sticky de siempre intacto).

    A4 (Fable 2026-07-08): una `new_description` VACÍA NO marca stale. Un
    re-scrape que no recapturó la descripción (drift de selector, layout roto,
    challenge parcial) llega con description="" — tratarla como "sin cambios"
    y PRESERVAR la traducción pagada, en vez de descartarla y re-traducir.
    """
    if not new_description:
        return False
    old_hash = old.get("description_es_src_hash")
    if not old_hash:
        return False
    return old_hash != description_src_hash(new_description)


def write_items_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    """Escribe `rows` (dicts ya serializables) como JSONL atómicamente.

    Helper único (A7, Fable 2026-07-08): tmp + flush + fsync + os.replace.
    `append_jsonl` ya usaba este patrón para su dump completo (upsert +
    consolidate); este helper lo generaliza para que los retrofits que hacen
    un dump-completo de `items.jsonl` (ya con la lista final de filas, sin
    necesidad de upsert) dejen de usar `write_text`/tmp-sin-fsync directo —
    un kill a mitad de esa escritura corrompía/truncaba el archivo (gotcha
    #133). Serializa con `sort_keys=True`, el mismo formato que usa
    `append_jsonl`, para que la prueba de idempotencia byte-a-byte sea válida
    entre pasadas de scripts distintos.

    Crea `path.parent` si hace falta. No hace upsert ni consolidación — el
    caller ya debe traer la lista final de filas a escribir.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        for item in rows:
            file.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
        # Durabilidad: forzar el flush del buffer de Python + fsync del FD antes
        # del rename atómico, para que un corte de energía justo tras el replace
        # no deje el archivo truncado/vacío (el .tmp podría estar en el page
        # cache pero no en disco).
        file.flush()
        os.fsync(file.fileno())
    tmp_path.replace(path)


def write_lines_atomic(path: Path, lines: list[str]) -> None:
    """Escribe `lines` (strings YA serializadas, típicamente JSON-por-línea)
    atómicamente: tmp + flush + fsync + os.replace.

    Complemento de `write_items_atomic` (A7, Fable 2026-07-08) para los
    writers que preservan el texto crudo de la línea original — p.ej. una
    línea corrupta que no se pudo parsear (patrón B11 raw-preserve) o un
    dump que ya trae las líneas formateadas — en vez de reserializar un
    dict. Mismo patrón de durabilidad que `write_items_atomic`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    text = "\n".join(lines)
    if lines:
        text += "\n"
    with tmp_path.open("w", encoding="utf-8") as file:
        file.write(text)
        file.flush()
        os.fsync(file.fileno())
    tmp_path.replace(path)


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
    # campos seteados por el skill `/watch-standardize-catalog` (title canónico,
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
        "description_es",  # traducción al español (translate_descriptions.py)
        "approved_at",     # golden record marker (aprobado desde el dashboard)
        "approved_by",
        # Gotcha #65: el upsert NO debe degradar filas estandarizadas. `slug`
        # lo asigna generate_slugs.py (el scraper nunca lo trae); `detected_at`
        # es la PRIMERA detección, no la última; `score`/`signals`/`signal_types`
        # se computaron sobre el texto crudo ORIGINAL — la verdad
        # post-estandarización vive en la etiqueta de edición, no en el texto
        # del re-scrape (gotcha #61), recomputarlos pierde señales.
        "slug",
        "detected_at",
        "score",
        "signals",
        "signal_types",
    )
    # Campos volátiles de mercado: SÍ se refrescan aunque el item esté aprobado
    # (un golden record congela la metadata descriptiva, no el stock).
    # M13 (Fable 2026-07-08): `detected_at` NO es volátil — es la PRIMERA
    # detección (ya curado en _CURATED_FIELDS para estandarizados). Antes, un
    # aprobado re-scrapeado lo pisaba con hoy y saltaba al final del archivo
    # (orden por detected_at), pareciendo "recién detectado". Fuera de acá, el
    # upsert preserva el viejo para TODOS (approved parte de dict(old)).
    _VOLATILE_FIELDS = ("stock_type", "sources")
    for row in rows:
        url = row.get("url", "")
        if not url:
            no_url_rows.append(row)
            continue
        key = normalize_url_for_dedup(url)
        old = existing.get(key)
        # El espejo local de la portada es sticky vía el union-merge de images[]
        # de más abajo: dedup por (kind, url) preservando primero el entry viejo,
        # así un re-scrape que no descargó (--skip-image-download o fallo de red)
        # conserva el `local` que ya teníamos en images[0]. Ver "Image storage".
        # description_es es sticky: un re-scrape no debe borrar las
        # traducciones escritas por translate_descriptions.py. Las traducciones
        # también están en _CURATED_FIELDS (para items con standardized_at),
        # pero el sticky cubre TODOS los items independientemente del flag.
        # Guard de traducción stale (WO-B): si el re-scrape trae una
        # `description` distinta de la que se tradujo (hash no coincide), NO
        # preservamos la traducción vieja — se deja re-traducir (y se descarta el
        # hash stale, que el row entrante no trae). Sin hash → sticky de siempre.
        if old and old.get("description_es") and not row.get("description_es") \
                and not _translation_is_stale(old, row.get("description") or ""):
            row["description_es"] = old["description_es"]
            # Preservar el hash junto a la traducción para que futuros re-scrapes
            # puedan volver a validar (el scraper crudo nunca lo trae).
            if old.get("description_es_src_hash") and not row.get("description_es_src_hash"):
                row["description_es_src_hash"] = old["description_es_src_hash"]
        # slug es sticky para TODOS los items (no sólo estandarizados): lo
        # asigna generate_slugs.py en curación y el scraper nunca lo trae.
        # Sin esto un re-scrape deja slug=None → violación SLUG (gotcha #65).
        if old and old.get("slug") and not row.get("slug"):
            row["slug"] = old["slug"]
        # rarity es sticky SÓLO cuando la vieja tiene respaldo curado: verificada
        # por web (rarity_verified_at, set_rarity.py / validate-rarity skill),
        # estandarizada o aprobada. En esos casos un re-scrape no debe pisar el
        # valor (p.ej. 'common' asignado tras verificar stock en tiempo real).
        # M11 (Fable 2026-07-08): raw-sobre-raw NO es sticky — ambas rarezas
        # salen de la MISMA derivación determinista (candidate_to_json), así que
        # evidencia estructural nueva de un re-scrape (tirada numerada, "esaurito")
        # DEBE poder actualizar una rareza aún no verificada. Antes el sticky era
        # incondicional y congelaba la rareza en el valor del primer ingest.
        _rarity_curated = bool(
            old and (old.get("rarity_verified_at")
                     or old.get("standardized_at")
                     or old.get("approved_at"))
        )
        if _rarity_curated and old.get("rarity") and old["rarity"] != row.get("rarity"):
            row["rarity"] = old["rarity"]
        # rarity_verified_at es sticky: preservar el timestamp de verificación
        # web (skill /watch-validate-rarity). Un re-scrape no debe borrar la marca
        # de que este item ya fue verificado por búsqueda web.
        if old and old.get("rarity_verified_at") and not row.get("rarity_verified_at"):
            row["rarity_verified_at"] = old["rarity_verified_at"]
        # images_backfilled_at es sticky: lo setea backfill_metadata.py --only images
        # tras hacer el fetch de galería completo. Un re-scrape no debe re-encolar
        # items que ya fueron procesados. Si la nueva fila no lo trae (ningún scraper
        # lo escribe), preservar el que ya estaba.
        if old and old.get("images_backfilled_at") and not row.get("images_backfilled_at"):
            row["images_backfilled_at"] = old["images_backfilled_at"]
        # images[] es UNION-MERGE entre old y new (Fase 2 listadomanga-collections):
        # un re-scrape que sólo trae la cover no debe borrar los extras que
        # se agregaron en una pasada previa con merge extra→tomo, y viceversa
        # — un re-scrape de extras no debe borrar la cover. El union-merge
        # (dedup por (kind, stem), fill de local/description, copia) vive en
        # _union_merge_images — MISMA primitiva que usa merge_cluster (A9), para
        # que el pipeline sea punto fijo entre ambos sitios (gotcha #87).
        # Orden: primero los del old, después los nuevos.
        old_images = list((old or {}).get("images") or [])
        new_images = list(row.get("images") or [])
        if old_images or new_images:
            row["images"] = _union_merge_images(old_images + new_images)
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
        # sources[] sticky+merge (modelo 1-fila-por-producto): cada fila ES una
        # fuente. El scraper no setea sources[], así que la fila entrante es
        # `source_entry(row)`. Preservamos las fuentes HERMANAS que ya estaban
        # (otro retailer del mismo producto cuya URL no se re-scrapeó esta vez) y
        # refrescamos/agregamos la propia. Sin esto, un re-scrape de una sola
        # fuente borraría las demás del array. La consolidación por cluster (al
        # final) une además filas-fuente que llegaron con URLs distintas.
        incoming = list(row["sources"]) if (isinstance(row.get("sources"), list) and row["sources"]) else [source_entry(row)]
        seen_src = {normalize_url_for_dedup(s.get("url", "") or "") for s in incoming}
        for s in ((old or {}).get("sources") or []):
            if normalize_url_for_dedup(s.get("url", "") or "") not in seen_src:
                incoming.append(s)
        row["sources"] = incoming
        if old and is_approved(old):
            # Golden record: el owner aprobó esta card desde el dashboard.
            # Congelamos TODA la metadata descriptiva (partimos de old) y sólo
            # refrescamos los campos volátiles de mercado (precio/stock/fuentes)
            # con los valores del re-scrape. Ver is_approved() + CLAUDE.md.
            merged = dict(old)
            for vf in _VOLATILE_FIELDS:
                if vf in row:
                    merged[vf] = row[vf]
            existing[key] = merged
        elif old and old.get("standardized_at"):
            merged = dict(row)
            # Guard de traducción stale (WO-B): si la description cambió, la
            # description_es curada quedó obsoleta → no restaurarla ni su hash
            # (se deja re-traducir). El resto de campos curados se preservan.
            stale_tr = _translation_is_stale(old, row.get("description") or "")
            for field in _CURATED_FIELDS:
                if field == "description_es" and stale_tr:
                    continue
                if old.get(field) not in (None, ""):
                    merged[field] = old[field]
            # description_es_src_hash no está en _CURATED_FIELDS: preservarlo
            # explícitamente cuando la traducción sigue vigente (para revalidar
            # en el próximo re-scrape); descartarlo cuando quedó stale.
            if not stale_tr and old.get("description_es_src_hash"):
                merged["description_es_src_hash"] = old["description_es_src_hash"]
            # A4: `description` tampoco está en _CURATED_FIELDS. Si el re-scrape
            # no la recapturó (llega vacía), preservar la vieja — no borrar el
            # sinopsis sobre el que además cuelga la traducción. Si el re-scrape
            # trae una description nueva, gana la nueva (y stale_tr ya descartó la
            # traducción arriba).
            if not merged.get("description") and old.get("description"):
                merged["description"] = old["description"]
            # Gotcha #65: la fila cruda trae cluster_key de tier fuzzy/url:.
            # Con edition_key/volume curados ya restaurados, re-derivar acá
            # devuelve el tier edition: y mantiene la invariante CLKEY
            # (stored == derive_cluster_key(item)) sin reparación manual.
            merged["cluster_key"] = derive_cluster_key(merged)
            existing[key] = merged
        else:
            # Item RAW (no aprobado, no estandarizado): el upsert reemplaza la
            # fila entera. Fill-if-empty para isbn/author/release_date/description:
            # si el re-scrape NO recapturó uno de esos campos (llega vacío/None)
            # pero el viejo lo tenía (backfill_metadata.py, o un scrape previo con
            # mejor cobertura), conservamos el viejo. Si el nuevo trae valor,
            # SIEMPRE gana el nuevo. `description` se agregó (A4, Fable
            # 2026-07-08): un scrape con drift de selector no debe borrar el
            # sinopsis. No toca la lógica sticky de arriba (standardized/approved
            # van por otra rama).
            if old:
                for _f in ("isbn", "author", "release_date", "description"):
                    if not row.get(_f) and old.get(_f):
                        row[_f] = old[_f]
            existing[key] = row

    # 3. Reescribir atómicamente. Conservamos el orden: primero todos los que
    #    tienen URL (ordenados por detected_at para estabilidad), luego los
    #    sin URL al final.
    def _detected_key(item: dict[str, Any]) -> str:
        return str(item.get("detected_at", "") or "")

    # Consolidación por producto: colapsa filas que comparten cluster_key (el
    # mismo producto encontrado en varias fuentes con URLs distintas) en UNA
    # sola fila con `sources[]`. Esto es lo que implementa el modelo
    # 1-fila-por-producto al ingestar — un producto re-encontrado NO agrega una
    # fila nueva, suma su fuente al array. Idempotente.
    consolidated = consolidate_by_cluster(list(existing.values()))
    sorted_rows = sorted(consolidated, key=_detected_key)
    write_items_atomic(path, sorted_rows + no_url_rows)


def flush_source_candidates(
    candidates: list["Candidate"],
    state: dict[str, Any],
    items_path: Path,
    min_score: int,
    dry_run: bool = False,
) -> int:
    """Escribe al JSONL los candidatos new/changed de UNA fuente inmediatamente.

    Se llama después de que cada fuente termina en el loop principal (tanto
    serial como paralelo). Propósito: si el proceso es matado a mitad del
    scrape, los items de las fuentes ya completadas no se pierden.

    NO actualiza `state` — eso sigue haciéndolo `process_state` al final del
    run completo. Consecuencia: si el proceso es interrumpido y relanzado, los
    items ya escritos aparecerán como "new"/"changed" de nuevo, pero
    `append_jsonl` los upsertea idempotentemente (sin duplicados en el JSONL).

    Si el run completa normalmente, el `append_jsonl` final sobreescribe estas
    entradas con datos enriquecidos (detail-fetch), lo cual es correcto.

    Retorna la cantidad de filas escritas.
    """
    if dry_run or not candidates:
        return 0
    to_write: list[dict[str, Any]] = []
    for c in candidates:
        if c.score < min_score:
            continue
        if not is_curated_collectible_source(c):
            is_coll, _ = is_collectible_edition(
                c.title, c.description, c.signal_types, c.product_type,
                tags=c.tags, isbn=c.isbn, url=c.url,
            )
            if not is_coll:
                continue
        key = candidate_key(c)
        prev = state.get(key)
        if prev is None:
            c.status = "new"
        elif prev.get("content_hash") != c.content_hash:
            c.status = "changed"
        else:
            continue  # "seen" — ya está en el JSONL sin cambios
        to_write.append(candidate_to_json(c))
    if to_write:
        append_jsonl(items_path, to_write)
    return len(to_write)


class RobotsCache:
    """Cachea el robots.txt por host. Sólo se usa con `--respect-robots`
    (opt-in, ver conventions.md).

    M10 (Fable 2026-07-08): antes `parser.read()` usaba `urlopen` SIN
    timeout — el único fetch del pipeline sin límite, capaz de colgar el
    worker para siempre si un host no responde. Ahora fetchea con la
    `session` del proyecto (Retry + timeout de `make_session`/`fetch_text`,
    fuente única) y alimenta al parser vía `parser.parse(text.splitlines())`
    en vez de dejar que el propio parser abra la conexión. El dict `cache`
    se muta desde N threads (workers HTTP en paralelo) → protegido con un
    lock.
    """

    def __init__(self, user_agent: str, session: requests.Session | None = None,
                 timeout: tuple[int, int] = (10, 15)) -> None:
        self.user_agent = user_agent
        self.session = session or make_session(user_agent)
        self.timeout = timeout
        self.cache: dict[str, RobotFileParser | None] = {}
        self._lock = threading.Lock()

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return True
        base = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = urljoin(base, "/robots.txt")
        with self._lock:
            cached = base in self.cache
            parser = self.cache.get(base)
        if not cached:
            parser = RobotFileParser()
            parser.set_url(robots_url)
            try:
                text = fetch_text(self.session, robots_url, timeout=self.timeout)
                parser.parse(text.splitlines())
            except Exception as exc:
                print(f"[WARN] No pude leer robots.txt de {base}: {exc}. Permito por defecto.")
                parser = None
            with self._lock:
                self.cache[base] = parser
        if parser is None:
            return True
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception as exc:
            print(f"[WARN] Error evaluando robots.txt para {url}: {exc}. Permito por defecto.")
            return True


# ---------------------------------------------------------------------------
# Detección de challenge anti-bot (Cloudflare / WAF) — FUENTE ÚNICA
# ---------------------------------------------------------------------------
#
# La usan: el path HTTP plano de `_scrape_one`, el path Playwright
# (`_fetch_with_playwright_impl`) y el spider de Whakoom
# (`scripts/wikis/whakoom.py`, que la importa y delega su
# `_looks_like_cf_challenge` acá). NO reimplementar en otro lado.
#
# Marcadores ESTRUCTURALES inequívocos de Cloudflare (form/token/UI path del
# challenge). NO usar "challenge-platform" a secas: el script JSD de
# bot-detection (/cdn-cgi/challenge-platform/scripts/jsd/main.js) aparece en
# CUALQUIER página protegida. El challenge UI real vive en /h/ (no /scripts/).
_CHALLENGE_STRUCTURAL_MARKERS = (
    "cf-chl-bypass",                    # form metadata del challenge
    "__cf_chl_rt_tk",                   # token de challenge
    "/cdn-cgi/challenge-platform/h/",   # UI path del challenge (no /scripts/)
)
# Marcadores de TÍTULO/TEXTO (Cloudflare "Just a moment" + WAFs genéricos).
# Ambiguos fuera de una página de challenge, así que solo se evalúan en páginas
# CORTAS: los challenges pesan 5-15KB; el contenido real supera 50KB y podría
# contener estas frases en el body (falso positivo).
_CHALLENGE_TEXT_MARKERS = (
    "just a moment",
    "checking your browser",
    "attention required",
    "access denied",
    "verification",
)
_CHALLENGE_TEXT_MAX_LEN = 50000


def detect_challenge(html: str, status: int | None = None) -> str | None:
    """¿La respuesta es un challenge anti-bot en lugar de contenido real?

    Devuelve el tipo de challenge ("cloudflare" | "challenge") o None si la
    página parece contenido legítimo. `status` (código HTTP) se acepta para
    futuros WAFs que solo challenguean con 403/503 — hoy no altera la decisión.
    """
    if not html:
        return None
    lowered = html.lower()
    for marker in _CHALLENGE_STRUCTURAL_MARKERS:
        if marker in lowered:
            return "cloudflare"
    if len(html) <= _CHALLENGE_TEXT_MAX_LEN:
        for marker in _CHALLENGE_TEXT_MARKERS:
            if marker in lowered:
                return "challenge"
    return None


class Blocked403Error(Exception):
    """La fuente devolvió 403 incluso tras un reintento con UA alternativo.

    Señaliza que hay que ABANDONAR la fuente en este run. El red team vetó
    agregar 403 al Retry de urllib3: reintentar idéntico escala el bloqueo. El
    reintento único con UA browser-like alternativo se hace en `_scrape_one`.
    """


# Backoff (segundos) antes del reintento único ante 403.
_BLOCKED_403_BACKOFF_SECONDS = 4.0
# UA browser-like de respaldo para el reintento único ante 403 (distinto del UA
# por defecto del proyecto, que algunos WAF bloquean por identificarlo como bot).
_BROWSER_LIKE_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def make_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    # Retry automático ante fallos TRANSITORIOS (reset TCP, DNS hiccup,
    # 429/5xx). Sin esto, un blip de red descarta la fuente/colección entera
    # del run. Solo GET/HEAD (idempotentes); respeta Retry-After del server.
    # raise_on_status=False → tras agotar retries devuelve la respuesta y
    # raise_for_status() del caller decide, igual que antes.
    retry = Retry(
        total=3,
        connect=2,
        read=2,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    # pool_* > default (10): con --workers 8 y muchas fuentes en el mismo
    # host, el pool default descarta conexiones ("connection pool is full").
    adapter = HTTPAdapter(max_retries=retry, pool_connections=32, pool_maxsize=32)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
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
                # Evidencia aceptada: (a) href con page=N+1 (paginación clásica),
                # o (b) href javascript de paginación con el número N+1 como
                # argumento — `Javascript:Page_Set('2')` (Aladin/ASP.NET),
                # `fn_paging(2)`, etc. El sitio acepta ?page=N igual aunque
                # sus links usen JS (verificado Aladin 2026-06-12).
                js_next = re.compile(
                    rf"^javascript:[\w.]*pag\w*[_.]?\w*\(['\"]?{current_page + 1}['\"]?\)",
                    re.IGNORECASE,
                )
                for anchor in soup.find_all("a", href=True):
                    href = anchor.get("href", "")
                    if f"{page_param}={current_page + 1}" in href or js_next.match(href.strip()):
                        return next_url
    return None


def fetch_with_metadata(
    session: requests.Session, url: str, timeout: tuple[int, int],
    *, user_agent: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Como fetch_text pero devuelve también metadata útil para diagnóstico.

    `user_agent` (opcional) sobreescribe el UA SOLO para esta request (per-source
    UA de sources.yml, o el UA browser-like del reintento ante 403), sin mutar
    la sesión compartida entre threads.
    """
    start = time.perf_counter()
    headers = {"User-Agent": user_agent} if user_agent else None
    response = session.get(url, timeout=timeout, headers=headers)
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
        # detect_challenge() es la fuente única de markers (comparte lista con el
        # path HTTP y con whakoom); acá se evalúa contra el TÍTULO renderizado.
        try:
            if detect_challenge(page.title()):
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


# Badges de descuento/oferta que themes de tienda (WooCommerce y similares)
# insertan en la card ANTES del título: "Sconto 10%", "-10%", "Sale", "Offerta"…
# El title_selector genérico cae a h2/h3/a y capturaba ese badge como título (caso
# IT - Dynit, run 2026-07-07: title "Sconto 10%"/"Sconto 5%"). No es el nombre del
# producto — se salta al elegir el título dentro de la card.
_SALE_BADGE_RE = re.compile(
    r"^\s*(?:"
    r"-?\s*\d{1,3}\s*%\s*(?:off|di\s+sconto|sconto|dto\.?|desc\.?|de\s+descuento)?"  # -10%, 10% off
    r"|sconto\s*-?\s*\d{1,3}\s*%?"                       # Sconto 10%
    r"|descuento\s*-?\s*\d{1,3}\s*%?"                    # Descuento 10%
    r"|r[ée]duction\s*-?\s*\d{1,3}\s*%?"                 # Réduction 10%
    r"|(?:in\s+)?saldo|sale|offerta|oferta|promo(?:zione)?|solde[s]?"
    r"|sconto|descuento|rebaja|r[ée]duction"  # badges "desnudos" sin % (IT - Funside, run 2026-07-07)
    r")\s*$",
    re.IGNORECASE,
)


def _is_sale_badge(text: str) -> bool:
    """¿El texto es SÓLO un badge de descuento/oferta (no un título de producto)?

    Comparación de TEXTO COMPLETO (fullmatch): sólo se salta el candidato cuando
    el texto ENTERO es el badge. Un título real que contenga la palabra en
    contexto ("Garage Sale Vol 1", "Summer Sale Special Edition") NO se salta.
    """
    return bool(text) and bool(_SALE_BADGE_RE.fullmatch(text.strip()))


def _first_non_badge_title(card: Any, title_selector: str) -> str:
    """Primer elemento del title_selector cuyo texto NO es un badge de descuento.

    `select_one` devolvía el PRIMER match en orden de documento — si el theme
    pone un "Sconto 10%" antes del título, ese era el título. Iteramos y saltamos
    badges; si todos son badges (raro), caemos al primero (comportamiento viejo).
    """
    try:
        els = card.select(title_selector)
    except Exception:
        return ""
    fallback = ""
    for el in els:
        t = clean_text(el.get_text(" ", strip=True))
        if not t:
            continue
        if not fallback:
            fallback = t
        if not _is_sale_badge(t):
            return t
    return fallback


def extract_with_selectors(
    source: Source,
    soup: BeautifulSoup,
    max_items: int,
    schema_map: list[tuple[Any, dict[str, str]]] | None = None,
) -> list[Candidate]:
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
            title = _first_non_badge_title(card, title_selector)

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

        if is_digital_only_url(link):
            continue  # ebook/digital — PandaWatch cataloga ediciones físicas

        if title or description:
            candidate = candidate_from_source(source, title, link or source.url, description)
            # A1: en el listing los <script> ya fueron decompuestos → usar el
            # mapa pre-parseado por card. Fuera de ese path (soup fresco, tests
            # directos) cae al extractor clásico sobre la card.
            schema = (
                _schema_for_card(card, schema_map) if schema_map is not None
                else extract_schema_org_product(card, source.url)
            )
            if schema.get("name") and len(schema["name"]) >= 3:
                candidate.title = clean_title(schema["name"])[:260]
            if schema.get("description") and len(schema["description"]) > len(candidate.description):
                candidate.description = schema["description"][:2500]
            candidate.image_url = schema.get("image_url") or extract_image_url(card, source.url)
            candidate.release_date = normalize_release_date(
                schema.get("release_date") or "", country=source.country
            ) or extract_release_date(candidate.description, country=source.country)
            candidate.author = schema.get("author") or extract_author(candidate.description, card)
            candidate.isbn = normalize_isbn(
                schema.get("isbn") or extract_isbn(f"{candidate.description}\n{candidate.url}", card),
                source=candidate.source,
            )
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


def _candidate_from_card(
    source: Source,
    card: Any,
    schema_map: list[tuple[Any, dict[str, str]]] | None = None,
) -> Candidate | None:
    anchor = card.find("a", href=True)
    if not anchor:
        return None
    url = canonicalize_url(source.url, anchor.get("href"))
    if not url:
        return None
    title = _derive_title(card, anchor)
    if not title or len(title) < 3:
        return None
    description = clean_description(clean_text(card.get_text(" ", strip=True)))
    # Filtro de longitudes: bloques contaminados (>2000) o ruido (<25).
    # 25 chars permite cards de e-commerce con título corto + precio.
    if len(description) < 25 or len(description) > 2000:
        return None
    candidate = candidate_from_source(source, title[:260], url, description)

    # Estrategia 0: si la card tiene JSON-LD inline (Shopify, Magento moderno…),
    # usar esos datos como override (mayor calidad que las heurísticas). En el
    # listing los <script> ya fueron decompuestos → mapa pre-parseado (A1).
    schema = (
        _schema_for_card(card, schema_map) if schema_map is not None
        else extract_schema_org_product(card, source.url)
    )

    # Title: si Schema.org tiene un name más específico, lo usamos.
    if schema.get("name") and len(schema["name"]) >= 3:
        candidate.title = clean_title(schema["name"])[:260]

    # Description: si la de Schema es más sustancial, la preferimos.
    if schema.get("description") and len(schema["description"]) > len(candidate.description):
        candidate.description = schema["description"][:2500]

    candidate.image_url = schema.get("image_url") or extract_image_url(card, source.url)
    candidate.release_date = normalize_release_date(
        schema.get("release_date") or "", country=source.country
    ) or extract_release_date(candidate.description, country=source.country)
    candidate.author = schema.get("author") or extract_author(candidate.description, card)
    candidate.isbn = normalize_isbn(
        schema.get("isbn") or extract_isbn(f"{candidate.description}\n{url}", card),
        source=candidate.source,
    )
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


_SQEX_CDN = "https://fyre.cdn.sewest.net/"
_SQEX_BASE = "https://squareenixmangaandbooks.square-enix-games.com"
_SQEX_NEXT_F_RE = re.compile(r'self\.__next_f\.push\(\[1,(.+)\]\)$', re.DOTALL)


def extract_squareenix_rsc(
    source: Source,
    html_text: str,
    max_items: int,
    info: dict[str, Any] | None = None,
) -> list[Candidate]:
    """Square Enix Manga & Books US (release-calendar): app Next.js RSC.

    El DOM solo renderiza ~10 items del mes visible, pero el catálogo COMPLETO
    (~488 productos, todos los meses) viene embebido en el payload `__next_f`
    (React Server Components wire format) dentro de <script> sin type — que la
    extracción genérica descarta al decomponer scripts. Acá se concatena el
    payload, se localiza el array `"products":` y se emiten candidatos.
    Sin Playwright: el payload llega en el HTML servido (SSR).
    Falla silenciosamente a [] si Square Enix cambia el build de Next.js.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    payload = ""
    for s in soup.find_all("script", src=False):
        t = (s.string or "").strip()
        m = _SQEX_NEXT_F_RE.match(t)
        if m:
            try:
                payload += json.loads(m.group(1))
            except (json.JSONDecodeError, TypeError):
                continue
    idx = payload.find('"products":')
    if idx == -1:
        if info is not None:
            info["extraction_method"] = "sqex-rsc-no-products"
        return []
    idx += len('"products":')
    depth, end = 0, idx
    for i in range(idx, len(payload)):
        c = payload[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    try:
        products = json.loads(payload[idx:end + 1])
    except json.JSONDecodeError:
        if info is not None:
            info["extraction_method"] = "sqex-rsc-bad-json"
        return []

    candidates: list[Candidate] = []
    seen: set[str] = set()
    for p in products:
        if not isinstance(p, dict) or not p.get("slug") or not p.get("title"):
            continue
        url = f"{_SQEX_BASE}/en-us/product/{p['slug']}"
        if url in seen:
            continue
        seen.add(url)
        release = (p.get("releaseMonth") or "").strip()  # "July 2026"
        cand = candidate_from_source(
            source,
            title=p["title"],
            url=url,
            description=f"{release} — {p['title']}".strip(" —"),
        )
        cover = ((p.get("coverArt") or {}).get("image") or "").strip()
        if cover:
            cand.image_url = cover if cover.startswith("http") else _SQEX_CDN + cover
        if release:
            # "July 2026" → "2026-07-01" (el calendario solo da mes/año)
            m = re.match(r"^([A-Za-z]+)\s+(\d{4})$", release)
            if m:
                months = {"january": "01", "february": "02", "march": "03",
                          "april": "04", "may": "05", "june": "06", "july": "07",
                          "august": "08", "september": "09", "october": "10",
                          "november": "11", "december": "12"}
                mm = months.get(m.group(1).lower())
                if mm:
                    cand.release_date = f"{m.group(2)}-{mm}-01"
            if not cand.release_date:
                cand.release_date = extract_release_date(release)
        candidates.append(cand)
        if len(candidates) >= max_items:
            break
    if info is not None:
        info["extraction_method"] = "sqex-rsc"
        info["cards_found"] = len(candidates)
        info["candidates_after_signals"] = len(candidates)
    return candidates


# Extractores DEDICADOS por dominio: sitios cuyo contenido no es alcanzable ni
# con selectores YAML ni con clusters (p.ej. payload Next.js RSC embebido en
# <script>, que extract_generic_html descarta). Se chequean ANTES del flujo
# genérico en extract_generic_html. Clave = substring del dominio en source.url.
_SITE_EXTRACTORS: dict[str, Any] = {
    "squareenixmangaandbooks.square-enix-games.com": extract_squareenix_rsc,
}


def extract_generic_html(
    source: Source,
    html_text: str,
    max_items: int,
    info: dict[str, Any] | None = None,
) -> list[Candidate]:
    # 0) Extractor dedicado del sitio (si existe) — corre sobre el HTML CRUDO
    # (los datos pueden vivir en <script>, que abajo se decompone).
    for domain, extractor in _SITE_EXTRACTORS.items():
        if domain in (source.url or ""):
            dedicated = extractor(source, html_text, max_items, info)
            if dedicated:
                return dedicated
            break  # dedicado falló → cae al flujo genérico (mejor que nada)

    soup = BeautifulSoup(html_text, "html.parser")
    # A1: mapa card→schema construido ANTES del decompose (los <script> ld+json
    # se destruyen abajo, pero sus datos ya quedaron atribuidos a la card).
    schema_map = _build_card_schema_map(soup, source.url)
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    # 1) Selectores manuales del YAML tienen prioridad.
    selector_candidates = extract_with_selectors(
        source, soup, max_items=max_items, schema_map=schema_map
    )
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
        candidate = _candidate_from_card(source, card, schema_map=schema_map)
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
        # RSS rara vez incluye <img> en el summary; intentamos parsearlo si está embebido.
        if "<img" in (entry.get("summary", "") or entry.get("content", "") or ""):
            try:
                rss_soup = BeautifulSoup(
                    entry.get("summary", "") or str(entry.get("content", "")), "html.parser"
                )
                candidate.image_url = extract_image_url(rss_soup, source.url)
            except Exception:
                pass
        candidate.release_date = extract_release_date(summary) or normalize_release_date(published_at)
        candidate.author = extract_author(summary)
        candidate.isbn = normalize_isbn(extract_isbn(f"{summary}\n{link}"), source=candidate.source)
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
                "release_date": candidate.release_date,
                "product_type": candidate.product_type,
                "author": clean_author(candidate.author),
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
    # dice "Vol.1 - Cover A" o "First print". Idem los catálogos de artbooks de
    # editorial (tag 'artbook', p.ej. Glénat Art Books): la página entera son
    # artbooks pero el título rara vez trae la keyword. `is_curated_collectible_source`
    # centraliza ambos bypass (y para 'artbook' fija product_type='artbook'). Se
    # aplica DESPUÉS de is_likely_manga, así que los no-manga ya quedaron fuera.
    # Ver "URL como referencia" en CLAUDE.md y la ficha fr-glenat-artbooks.md.
    pre_filter_count = len(candidates)
    filtered: list[Candidate] = []
    collectible_rejected = 0
    collectible_bypassed = 0
    for candidate in candidates:
        if is_curated_collectible_source(candidate):
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

    # A5 (Fable 2026-07-08): ELIMINADO el 2º pase que colapsaba por ISBN pelado.
    # "un ISBN = un producto" es FALSO en manga (el mismo ISBN se reparte entre
    # ediciones/series distintas — p.ej. 9788419177629 en Devilman #3 y Mao Dante
    # #1), por eso la decisión #4 ya quitó el tier `isbn:` de derive_cluster_key.
    # El colapso descartaba al perdedor (fusión destructiva incoherente con #4) y,
    # peor, como el flush ya lo había escrito a items.jsonl pero nunca entraba al
    # state, cada run lo re-veía "new" y lo re-flusheaba — churn eterno de la fila.
    # El merge legítimo (mismo producto en varios retailers) lo hace la
    # consolidación por `cluster_key` (fuente única, respeta país/edición) al
    # escribir. Acá sólo dedup por URL normalizada (1er pase, arriba).

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
            "release_date": candidate.release_date,
            "product_type": candidate.product_type,
            "author": clean_author(candidate.author),
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
    # "manga dreams" REMOVIDO (2026-06-10): es una TIENDA multi-editorial, no
    # editorial — el mapeo horneó `-mangadreams-` en 49 edition_keys y partió
    # ediciones (berserk-mangadreams-deluxe-it vs berserk-panini-deluxe-it).
    # Misma regla que Rakuten/Sanyodo (gotcha #44, ver nota abajo).
    "funside": "funside",
    "milky way": "milkyway",
    "milkyway": "milkyway",
    "doki-doki": "dokidoki",
    "doki doki": "dokidoki",
    "nobi nobi": "nobinobi",
    "tomodomo": "tomodomo",
    "fandogamia": "fandogamia",
    # NOTA: NO mapear nombres de TIENDA (Rakuten, Sanyodo, Honto, Animate…) a un
    # slug — son marketplaces multi-editorial, no editoriales. Mapearlos
    # contaminaba el edition_key con el slug de la tienda (`...-rakuten-...`) y
    # rompía el merge por ISBN con la ficha de la editorial oficial. Ver gotcha #44.
    "kurokawa": "kurokawa",
    "soleil": "soleil",
    "ankama": "ankama",
    "akata": "akata",
    "third éditions": "thirdeditions",
    "third editions": "thirdeditions",
    "akita": "akita",
    "hakusensha": "hakusensha",
    "gentosha": "gentosha",
    "mag garden": "maggarden",
    # Publishers JP adicionales
    "ichijinsha": "ichijinsha",
    "一迅社": "ichijinsha",
    "futabasha": "futabasha",
    "双葉社": "futabasha",
    "takeshobo": "takeshobo",
    "竹書房": "takeshobo",
    "tokuma": "tokuma",
    "徳間書店": "tokuma",
    "ascii media works": "asciimw",
    "ascii media": "asciimw",
    "frontier works": "frontier",
    "shogakukan": "shogakukan",
    "小学館": "shogakukan",
    # Publishers IT adicionales
    "j-pop": "jpop",
    "j pop": "jpop",
    "jpop": "jpop",
    "dynit": "dynit",
    "edizioni bd": "edizionibd",
    "001 edizioni": "001edizioni",
    "goen": "goen",
    "gp manga": "gpmanga",
    "gp publishing": "gpmanga",
    "magic press": "magicpress",
    "coconino": "coconino",
    "tora": "tora",
    "dokusho": "dokusho",
    "tokyo manga": "tokyomangasha",
    "tokyomanga": "tokyomangasha",
    "東京漫画社": "tokyomangasha",
    # Publishers FR adicionales
    "noeve": "noeve",
    "noeve grafx": "noeve",
    # Publishers US/EN adicionales
    "yen press": "yenpress",
    "seven seas": "sevenseas",
    "titan comics": "titan",
    "titan manga": "titan",
    "titan": "titan",
    "inklore": "inklore",
    "vertical": "vertical",
    "udon": "udon",
    # Publishers ES adicionales
    "distrito manga": "distrito",
    "distrito": "distrito",
    "astiberri": "astiberri",
    "ponent mon": "ponentmon",
    "ponent": "ponentmon",
    "ediciones b": "edicionesb",
    "bruguera": "bruguera",
    "debolsillo": "debolsillo",
    "reservoir books": "reservoir",
    "ooso comics": "ooso",
    "ooso": "ooso",
    "letrablanka": "letrablanka",
    "héroes de papel": "heroesdepapel",
    "heroes de papel": "heroesdepapel",
    "nowevolution": "nowevolution",
    "ominiky": "ominiky",
    "loftur": "loftur",
    "fujur": "fujur",
    "anaya": "anaya",
    "fanbooks": "fanbooks",
    "monogatari": "monogatari",
    "odaiba": "odaiba",
    "ediciones babylon": "babylon",
    "babylon": "babylon",
    "la cúpula": "lacupula",
    "la cupula": "lacupula",
    "gamepress": "gamepress",
    "shockdom": "shockdom",
    # Publishers BR adicionales
    "mpeg": "mpeg",
    # Publishers VN/TH adicionales
    "kim dong": "kim-dong",
    "kim đồng": "kim-dong",
    "luckpim": "luckpim",
    "ipm": "ipm",
    "isan manga": "isan",
    "nxb tre": "nxb",
    "nxb trẻ": "nxb",
    # Publishers alemanes (DACH)
    "carlsen": "carlsen",
    "egmont manga": "egmont",
    "egmont": "egmont",
    "dokico": "dokico",
    "papertoons": "papertoons",
    "cross cult": "crosscult",
    "manga cult": "mangacult",
    "loewe manga": "loewe",
    "loewe": "loewe",
    "reprodukt": "reprodukt",
    "altraverse": "altraverse",
    "universe": "universe",
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


# REGLA DE NEGOCIO DURA (2026-06-07): país distinto = edición distinta, SIEMPRE.
# El país se hornea en el edition_key como sufijo (`…-{country_slug}`) para que
# dos mercados NUNCA compartan edición/cluster aunque tengan la misma editorial
# matriz (Panini IT vs Panini ES/MX/BR, Kazé FR vs DE, etc.). Ver gotcha #46.
_COUNTRY_SLUG_MAP: dict[str, str] = {
    "japón": "jp", "japon": "jp", "japan": "jp",
    "italia": "it", "italy": "it",
    "españa": "es", "espana": "es", "spain": "es",
    "francia": "fr", "france": "fr",
    "alemania": "de", "germany": "de", "deutschland": "de",
    "estados unidos": "us", "usa": "us", "united states": "us",
    "vietnam": "vn",
    "méxico": "mx", "mexico": "mx",
    "brasil": "br", "brazil": "br",
    "tailandia": "th", "thailand": "th",
    "argentina": "ar",
    "taiwán": "tw", "taiwan": "tw",
    "reino unido": "gb", "united kingdom": "gb", "uk": "gb",
    "portugal": "pt",
    "perú": "pe", "peru": "pe",
    "chile": "cl",
    "corea": "kr", "korea": "kr",
    # Países agregados con la expansión 2026-06-12 (sin esto el fallback
    # horneaba códigos de 4 letras NO idempotentes: core/polo/cheq/turq/hong
    # se re-apendeaban en cada enforcer — gotcha #91).
    "corea del sur": "kr", "south korea": "kr",
    "polonia": "pl", "poland": "pl",
    "chequia": "cz", "czechia": "cz", "república checa": "cz", "republica checa": "cz",
    "turquía": "tr", "turquia": "tr", "turkey": "tr",
    "hong kong": "hk",
    "china": "cn",
    "indonesia": "id",
    "españa / latam": "eslatam", "latam": "latam",
}


def _country_slug(country: str) -> str:
    """Código corto del país para hornearlo en el edition_key (regla país=edición).

    Devuelve 'xx' si el país es vacío/desconocido (así un item sin país no
    colapsa con uno que sí lo tiene). Match exacto normalizado y, como fallback,
    los 2 primeros chars alfabéticos del país slugificado.
    """
    if not country or not country.strip():
        return "xx"
    c = country.strip().lower()
    if c in _COUNTRY_SLUG_MAP:
        return _COUNTRY_SLUG_MAP[c]
    # fallback determinístico: primeras letras del país (evita colisión silenciosa)
    import unicodedata as _ud
    norm = "".join(ch for ch in _ud.normalize("NFKD", c) if not _ud.combining(ch))
    norm = "".join(ch for ch in norm if ch.isalpha())
    return norm[:4] or "xx"


_ESPECIAL_PARENS_RE = re.compile(r"^(.*\d)\s*\((?:Edici[óo]n\s+)?Especial\)\s*$", re.IGNORECASE)
# SÓLO frases de edición en ESPAÑOL: reordenar/expandir el español NO traduce (política
# de títulos). El inglés "Special Edition" se dejaba caer aquí y se convertía en "Edición
# Especial" → traducción prohibida (gotcha #94): un título japonés/italiano/inglés terminaba
# con la marca española ("葬送のフリーレン 15 Edición Especial"). El inglés ya NO matchea.
_ESPECIAL_REORDER_RE = re.compile(
    r"^(.*?)\s+(?:Edici[óo]n\s+Especial|Especial)\s+(\d+(?:[.\-]\d+)?)\s*$",
    re.IGNORECASE,
)


def format_especial_title(title: str) -> str:
    """Normaliza el título de una EDICIÓN ESPECIAL **en español** a "{serie} {vol}
    Edición Especial" (gotcha #52). Idempotente. Sólo cambia títulos que ya tienen el
    patrón especial EN ESPAÑOL (un regular como "Atelier of Witch Hat 5" no matchea →
    queda igual). NO traduce: un título en inglés "X Special Edition N" se deja intacto
    (gotcha #94 — traducir violaba la política de títulos).
      - "X N (Edición Especial)"                 → "X N Edición Especial"
      - "X Edición Especial N" / "X Especial N"  → "X N Edición Especial"
      - "X Special Edition N" (inglés)           → SIN CAMBIO
    """
    t = (title or "").strip()
    t = _ESPECIAL_PARENS_RE.sub(r"\1 Edición Especial", t)   # quitar paréntesis
    m = _ESPECIAL_REORDER_RE.match(t)                         # mover el vol al frente
    if m:
        t = f"{m.group(1).strip()} {m.group(2)} Edición Especial"
    return t


# Homoglifos cirílicos/griegos → ASCII (gotcha #81). NFKD NO los descompone:
# una "о" cirílica U+043E sobrevive la normalización y el regex la descarta
# como punctuation → "Taihо to Stamp" quedaba "taih-to-stamp". Sólo
# confusables visuales inequívocos de letras latinas minúsculas (la tabla se
# aplica después de lower(), que ya baja О→о, Ο→ο).
_HOMOGLYPH_TO_ASCII = str.maketrans({
    # Cirílico
    "а": "a", "е": "e", "ё": "e", "о": "o", "р": "p", "с": "c",
    "у": "y", "х": "x", "і": "i", "ї": "i", "ј": "j", "ѕ": "s",
    "һ": "h", "ԁ": "d", "ԛ": "q", "ԝ": "w",
    # Griego
    "ο": "o", "α": "a", "ι": "i", "κ": "k", "ν": "v",
})


def _slugify_kebab(s: str) -> str:
    """Slugifica a kebab-case: lowercase, sin diacríticos, sin punctuation.

    Unicode (gotcha #81): homoglifos cirílicos/griegos se mapean a ASCII
    ANTES de NFKD (que no los descompone); CJK y cualquier otro no-ASCII
    restante se descarta de forma controlada vía el regex (actúa como
    separador y strip("-") limpia los bordes): "Maku ga Oriru to Bokura wa
    番" → "maku-ga-oriru-to-bokura-wa".
    """
    if not s:
        return ""
    import unicodedata as _ud
    s = s.lower().translate(_HOMOGLYPH_TO_ASCII)
    s = _ud.normalize("NFKD", s)
    s = "".join(c for c in s if not _ud.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def sanitize_key_ascii(key: str) -> str:
    """Fuerza una clave de agrupación (series_key/edition_key) a ASCII kebab.

    Idempotente sobre claves ya limpias. Es la frontera para claves que NO
    salen de `_slugify_kebab`: canónicas de series_aliases.yml (las acuña el
    LLM del enrich skill) y claves propuestas por el LLM del standardize
    (gotcha #81: "taihо-to-stamp" con о cirílica, "maku-ga-oriru-to-bokura-
    wa-番" con CJK crudo). Si la sanitización vacía la clave devuelve ""
    (el caller decide el fallback).
    """
    return _slugify_kebab(key or "")


# --- Edition slug refinement: language/title-aware ---
# Title keywords que refinan el edition_slug más allá del tier genérico.
# Orden: más específico primero. Cada regla: (regex, slug_resultado).
_EDITION_SLUG_TITLE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bmaximum\b", re.I), "maximum"),
    (re.compile(r"\bperfect\s+edition\b", re.I), "perfect"),
    (re.compile(r"\bultimate\b", re.I), "ultimate"),
    (re.compile(r"\bmaster\s+edition\b", re.I), "master"),
    (re.compile(r"\blibrary\s+edition\b", re.I), "library"),
    (re.compile(r"\bprestige\b", re.I), "prestige"),
    (re.compile(r"\bgrimorio\b", re.I), "grimorio"),
    (re.compile(r"\bgrimoire\b", re.I), "grimoire"),
    (re.compile(r"\bintegral[e]?\b", re.I), "integral"),
    (re.compile(r"\bcollector\b", re.I), "collector"),
    (re.compile(r"\bcoleccionista\b", re.I), "collector"),
    (re.compile(r"\banniversary\b|\baniversario\b|\banniversaire\b", re.I), "anniversary"),
    (re.compile(r"\bcelebration\b", re.I), "celebration"),
    (re.compile(r"\bsteelbox\b|\bsteelbook\b", re.I), "steelbox"),
    (re.compile(r"\bslipcase\b", re.I), "slipcase"),
    (re.compile(r"\bcofanetto\b", re.I), "cofanetto"),
    (re.compile(r"\bcoffret\b", re.I), "coffret"),
)

# Términos de TIPO de edición → slug canónico (tabla determinística, gotcha #69).
# El LLM del skill standardize elegía special/limited/collector/deluxe de forma
# inconsistente entre corridas (限定版 a veces "limited", a veces "special") y
# partía la MISMA edición en dos edition_keys. Esta tabla es la AUTORIDAD sobre
# el tipo: la consume el heurístico del scraper, se enuncia en los prompts del
# skill y `canonicalize_edition_slugs.py` la re-aplica post-LLM. Se evalúa
# DESPUÉS de las ediciones nombradas (_EDITION_SLUG_TITLE_RULES): "Ultimate
# Deluxe" es ultimate, no deluxe.
_EDITION_TYPE_TERM_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # JP — términos de mercado inequívocos
    (re.compile(r"限定版"), "limited"),
    (re.compile(r"特装版|同梱版"), "special"),
    (re.compile(r"愛蔵版"), "deluxe"),
    (re.compile(r"完全版"), "kanzenban"),
    # Occidente — tipo nombrado explícito en el título. OJO al orden: "especial
    # limitada" y "edición limitada" son LIMITED (van ANTES que la regla de
    # `edición especial`→special) para que "Edición Especial Limitada" resuelva a
    # limited y no a special. Se anclan a la FRASE completa ("edición especial",
    # "especial limitada"), NUNCA a "especial" suelto (rozaría nombres de serie).
    (
        re.compile(
            r"\bespecial\s+limitada\b|"
            r"\bedici[oó]n\s+limitada\b|\bedizione\s+limitata\b|"
            r"\b[ée]dition\s+limit[ée]e\b|\blimited\s+edition\b",
            re.I,
        ),
        "limited",
    ),
    (
        re.compile(
            r"\bedici[oó]n\s+de\s+lujo\b|\bedizione\s+deluxe\b|\bdeluxe\b", re.I
        ),
        "deluxe",
    ),
    # `edición especial` → special (DESPUÉS de la regla limited, ver nota arriba).
    (re.compile(r"\bedici[oó]n\s+especial\b", re.I), "special"),
)


def edition_slug_from_text(text: str) -> str:
    """Slug de edición derivado SOLO del texto (título), o "" si no hay término.

    Fuente única de verdad del mapeo término→slug (gotcha #69): primero las
    ediciones nombradas (Maximum, Perfect, Collector…), después los términos de
    tipo (限定版→limited, 特装版→special…). Determinística: mismo texto → mismo
    slug, en cualquier corrida y en cualquier consumidor (scraper, retrofit,
    validador, prompts del skill).
    """
    if not text:
        return ""
    for pat, slug in _EDITION_SLUG_TITLE_RULES:
        if pat.search(text):
            return slug
    for pat, slug in _EDITION_TYPE_TERM_RULES:
        if pat.search(text):
            return slug
    return ""


# Language → slug para tiers ambiguos (box_set, kanzenban)
_EDITION_SLUG_LANG_MAP: dict[str, dict[str, str]] = {
    "box_set": {
        "fr": "coffret",
        "it": "cofanetto",
    },
    "kanzenban": {
        "it": "perfect",  # Panini IT "Perfect Edition" line
    },
}


def _refine_edition_slug(
    tier: str, title: str, language: str, pub_slug: str,
) -> str:
    """Refina el edition_slug usando contexto de idioma y título.

    El tier viene de _variant_tier (genérico). Esta función lo especializa
    consultando el título por keywords de edición nombrada (Maximum, Perfect,
    Grimorio, etc.) y el idioma para slugs culturales (coffret/cofanetto).
    """
    # 1) El TÍTULO manda (tabla determinística, gotcha #69) — aplica AUN con
    # tier vacío: si el título dice 限定版/Collector/Maximum…, ese es el slug.
    by_text = edition_slug_from_text(title or "")
    if by_text:
        return by_text

    if not tier:
        return "regular"

    title_lc = (title or "").lower()

    # 2) Language-aware refinement para tiers ambiguos
    lang = (language or "")[:2].lower()
    lang_map = _EDITION_SLUG_LANG_MAP.get(tier)
    if lang_map and lang in lang_map:
        return lang_map[lang]

    # 3) Publisher-specific refinement
    if tier == "kanzenban" and pub_slug == "panini":
        if "ultimate" in title_lc:
            return "ultimate"
        if "perfect" in title_lc:
            return "perfect"

    # 4) Fallback al mapa estático
    static_map = {
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
    return static_map.get(tier, "regular")


# Slugs de edición válidos en el edition_key (mismo allowlist que los prompts
# del skill standardize). Usado para parsear la cola `-{pub}-{slug}-{country}`.
_KNOWN_EDITION_SLUGS = frozenset({
    "deluxe", "kanzenban", "perfect", "coffret", "boxset", "cofanetto",
    "variant", "limited", "collector", "anniversary", "celebration", "color",
    "maximum", "ultimate", "master", "library", "integral", "artbook",
    "fanbook", "guidebook", "magazine", "steelbox", "slipcase", "prestige",
    "grimorio", "grimoire", "special", "regular", "lore", "omnibus",
})


def rebuild_edition_key_prefix(edition_key: str, series_key: str) -> str | None:
    """Reconstruye el edition_key para que su prefijo sea `series_key`.

    Invariante de formato: `edition_key = {series_key}-{pub}-{slug}-{country}`
    (+ sufijo opcional `-cN`). Cuando el series_key se re-canonicaliza después
    de acuñada la key (o la key vino con la serie truncada a 35 chars), el
    prefijo queda stale y el reemplazo por startswith no lo detecta. Acá se
    parsea la cola desde la derecha (country, slug del allowlist, publisher —
    probando primero los de dos tokens tipo "ivrea-ar"/"panini-mx") y se
    re-arma con el series_key actual.

    Devuelve la key corregida, o None si ya está bien o no se puede parsear.
    """
    if not edition_key or not series_key:
        return None
    parts = edition_key.split("-")
    suffix = ""
    if parts and re.fullmatch(r"c\d+", parts[-1]):
        suffix = "-" + parts[-1]
        parts = parts[:-1]
    if len(parts) < 4:
        return None
    country, slug = parts[-1], parts[-2]
    if slug not in _KNOWN_EDITION_SLUGS:
        return None
    known_pubs = set(_PUBLISHER_SLUG_MAP.values()) | {"unknown"}
    if len(parts) >= 5 and "-".join(parts[-4:-2]) in known_pubs:
        pub = "-".join(parts[-4:-2])
        series_part = "-".join(parts[:-4])
    elif parts[-3] in known_pubs:
        pub = parts[-3]
        series_part = "-".join(parts[:-3])
    else:
        # Publisher NO reconocido: sin él no se puede separar serie/pub con
        # certeza (mutilaría "nxb-tre"→"tre" o "panini-standard"→"standard").
        # Precisión > recall: no tocar.
        return None
    # Comparar el SEGMENTO de serie exacto, no startswith.
    if series_part == series_key:
        return None
    if series_part.startswith(series_key + "-"):
        # La key es MÁS específica que el series_key. Eso puede ser un
        # distinguidor LEGÍTIMO (danganronpa-1-2-reload, sword-art-online-
        # aincrad: artbooks/coffrets distintos sin volumen — fusionarlos
        # mezclaría productos). Solo reparar cuando el extra es claramente
        # mecánico: (a) repetición del final del series_key ("takumi-kun-
        # series-series", "shugo-chara-jewel-joker-jewel-joker"), o
        # (b) equivalencia bajo la normalización agresiva.
        extra = series_part[len(series_key) + 1:]
        from series_aliases import aggressive_series_norm as _agg
        if not (series_key.endswith("-" + extra) or series_key == extra
                or _agg(series_part) == _agg(series_key)):
            return None
    # Resto de los casos: serie traducida/alias ("pokemon-sol-luna" vs
    # "pokemon-sun-moon"), truncada, o MENOS específica que el series_key
    # ("hakuoki" vs "hakuoki-shinkai") → re-alinear es seguro.
    return f"{series_key}-{pub}-{slug}-{country}{suffix}"


# Rangos CJK + Hangul + Kana (para detectar títulos no-latinos en el tier guard).
_CJK_RE = re.compile(
    r'[぀-ヿ'   # Hiragana + Katakana
    r'㐀-䶿'    # CJK Ext A
    r'一-鿿'    # CJK Unified
    r'豈-﫿'    # CJK Compatibility
    r'가-힣]'   # Hangul
)


def _has_cjk(text: str) -> bool:
    """True si el texto contiene ideogramas CJK, kana japonés o hangul coreano."""
    return bool(_CJK_RE.search(text or ""))


def derive_series_metadata(candidate: Candidate) -> dict[str, str]:
    """Asigna heurísticamente `series_key`, `edition_key`, etc. desde el title.

    Esto es la PRIMERA pasada cruda del scraper. Imperfecta a propósito —
    el skill `/watch-standardize-catalog` (subagentes con LLM) la verifica y
    corrige después. NO setea `standardized_at`, así el skill sabe que
    todavía debe procesar este item.

    Reusa los helpers existentes (`_extract_volume`, `_normalize_series_name`,
    `_variant_tier`) que ya manejan vol/tome/巻, mojibake, etc.

    Devuelve `{series_key, series_display, edition_key, edition_display,
    volume}` con strings vacíos cuando no se puede derivar (better empty
    than wrong). NO genera ni propone títulos: el `title` es el nombre
    OFICIAL scrapeado y nunca se reescribe (política de títulos 2026-06-12).
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
    # capitalize por-palabra (NO str.title(): rompe apóstrofes — "hell's" →
    # "Hell'S"). capitalize() sólo toca el primer carácter de cada palabra.
    series_display = (
        " ".join(w.capitalize() for w in raw_series.split()) if raw_series else series_key
    )

    # 3) Publisher slug
    pub_slug = _publisher_slug(candidate.publisher or "")

    # 3b) Try canonical series resolution (aliases.yml) — if it matches,
    # we have high confidence in the series_key.
    from series_aliases import canonical_series_key as _csk, is_canonical_key as _ick
    resolved_sk, resolved_sd = _csk(title, series_key, series_display)
    series_resolved = (resolved_sk != series_key)
    if series_resolved:
        # Las canónicas del YAML las acuña el LLM del enrich skill —
        # sanitizar a ASCII por si traen homoglifos/CJK (gotcha #81).
        series_key = sanitize_key_ascii(resolved_sk) or series_key
        series_display = resolved_sd

    # 4) Edition slug from signal_types — language/title-aware refinement
    tier = _variant_tier(candidate.signal_types or [])
    edition_slug = _refine_edition_slug(
        tier, title, candidate.language or "", pub_slug,
    )

    # País SIEMPRE en el edition_key (regla dura país=edición, gotcha #46): dos
    # mercados nunca comparten edición aunque coincidan series+publisher+edition.
    country_slug = _country_slug(candidate.country or "")
    edition_key = f"{series_key}-{pub_slug}-{edition_slug}-{country_slug}"
    _EDITION_NAME_MAP = {
        "deluxe": "Deluxe", "kanzenban": "Kanzenban", "boxset": "Box Set",
        "coffret": "Coffret", "cofanetto": "Cofanetto",
        "variant": "Variant", "limited": "Limited", "lore": "Special Edition",
        "artbook": "Artbook", "omnibus": "Omnibus", "special": "Special",
        "regular": "Regular", "maximum": "Maximum", "perfect": "Perfect",
        "ultimate": "Ultimate", "master": "Master", "library": "Library",
        "prestige": "Prestige", "grimorio": "Grimorio", "grimoire": "Grimoire",
        "integral": "Integral", "collector": "Collector",
        "anniversary": "Anniversary", "celebration": "Celebration",
        "steelbox": "Steelbox", "slipcase": "Slipcase",
    }
    edition_name = _EDITION_NAME_MAP.get(edition_slug, edition_slug.title())
    publisher_display = candidate.publisher or ""
    edition_display = (
        f"{edition_name} ({publisher_display})" if publisher_display else edition_name
    )

    # 5) Confidence tier for /watch-standardize-catalog routing
    #   Tier 1: series resolved in aliases + known publisher + unambiguous edition
    #   Tier 2: series resolved but edition ambiguous OR publisher unknown
    #   Tier 3: series NOT resolved (unknown series, CJK-only, etc.)
    is_canonical = series_resolved or _ick(series_key)
    pub_known = pub_slug != "unknown"
    edition_unambiguous = edition_slug not in ("lore", "special", "regular")
    if is_canonical and pub_known and edition_unambiguous:
        confidence_tier = 1
    elif is_canonical:
        confidence_tier = 2
    else:
        confidence_tier = 3

    # Guard red team (resolución CJK dudosa): si el título es CJK/Hangul pero la
    # serie canónica salió de un token latino MINORITARIO del título, la
    # resolución no es confiable para auto-estandarizar → sacarlo de Tier 1 a
    # Tier 2 (que el LLM la valide). Caso real: "冴えない彼女の育てかた 深崎暮人画集
    # 上 Flat." resolvía series_key='flat' (4 chars, el único latín del título).
    # NO degrada bilingües con match latino sustancial ("ワンピース ONE PIECE" →
    # 'one-piece' sigue Tier 1): el owner paga tokens solo con ambigüedad real.
    if confidence_tier == 1 and _has_cjk(title):
        key_latin = re.sub(r"[^a-z0-9]", "", series_key.lower())
        title_latin = re.sub(r"[^a-z0-9]", "", title.lower())
        minority = (
            len(key_latin) < 5
            or (bool(title_latin) and len(key_latin) / len(title_latin) < 0.30)
        )
        if minority:
            confidence_tier = 2

    return {
        "series_key": series_key,
        "series_display": series_display,
        "edition_key": edition_key,
        "edition_display": edition_display,
        "volume": volume,
        "confidence_tier": confidence_tier,
    }


def candidate_to_json(candidate: Candidate) -> dict[str, Any]:
    # El title es el nombre OFICIAL, pero los retailers JP le pegan su perk de
    # compra (店舗特典) — "(…ポストカード)【楽天ブックス限定特典】". Eso NO es el nombre
    # del producto: se separa al campo store_bonus (visible en el detalle, no en
    # el grid). title_original conserva el nombre oficial COMPLETO (con el bonus),
    # para no perder el dato. Ver gotcha #93.
    official_title = candidate.title
    grid_title, store_bonus = split_store_bonus(official_title)
    row = {
        "detected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": candidate.status,
        "score": candidate.score,
        "signals": candidate.signals,
        "signal_types": candidate.signal_types,
        "title": grid_title,
        "store_bonus": store_bonus,
        # title_original preserva el título scrapeado tal como vino de la
        # fuente (con clean_title aplicado: mojibake fixed, junk removido), INCL.
        # el store_bonus. NO se sobrescribe cuando el skill estandariza. Ver #22.
        "title_original": official_title,
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
        # Guardia universal de fecha: normaliza en el sink de escritura para que
        # NINGÚN camino (retailers JP, wikis Sumikko/Rakuten/KADOKAWA/Sanyodo…)
        # deje una fecha cruda ("2025/04/25 10:00:00", "2026年04月08日") en el
        # campo persistido (gotcha #80). Es idempotente y no rompe la excepción
        # tienda-vs-発売日 de fetch_metadata_from_detail: esa decide QUÉ fecha
        # usar (viendo el componente horario crudo) ANTES de llegar acá; este
        # guard sólo la lleva a ISO.
        "release_date": normalize_release_date(candidate.release_date),
        "product_type": candidate.product_type,
        "author": clean_author(candidate.author),
        "stock_type": candidate.stock_type,
        # Guardia universal de ISBN: normaliza en el sink de escritura para que
        # NINGÚN camino (listadomanga, wikis, retailers) deje "： "/guiones en el
        # campo persistido. El ISBN es metadata (búsqueda, selección de canónica
        # en merge_cluster) — ya NO es criterio de cluster_key (ver derive_cluster_key).
        "isbn": normalize_isbn(candidate.isbn, source=candidate.source),
    }
    # images[] es la ÚNICA fuente de verdad de la portada (decisión 2026-06-09):
    # `images[0]` es la portada; no hay campos top-level image_url/image_local.
    # El Candidate runtime sí trae image_url/image_local (input del scraper +
    # output del mirror); acá los convertimos en `images[0]` si el scraper no
    # pobló images[] directamente (la mayoría de fuentes simples sólo setean
    # candidate.image_url). Si el scraper ya trajo images[] (listadomanga-
    # collections), garantizamos que image_url/image_local del Candidate estén
    # reflejados en images[0] (el mirror los sincroniza, pero por las dudas).
    images_list = list(getattr(candidate, "images", []) or [])
    if not images_list and candidate.image_url:
        images_list = [{
            "url": candidate.image_url,
            "local": candidate.image_local,
            "kind": "gallery",
            "description": "",
        }]
    elif images_list and candidate.image_url:
        first = images_list[0]
        if not first.get("url"):
            first["url"] = candidate.image_url
        if not first.get("local") and candidate.image_local \
                and first.get("url") == candidate.image_url:
            first["local"] = candidate.image_local
    if images_list:
        row["images"] = images_list

    extras_list = list(getattr(candidate, "extras", []) or [])
    if extras_list:
        row["extras"] = extras_list

    # original_title: título en el idioma original del producto, atributo
    # dinámico que setea el parser de colecciones de listadomanga (mismo
    # mecanismo que edition_display/volume). Solo se persiste si no-vacío para
    # no inflar todas las filas con un campo vacío. OJO: NO confundir con
    # title_original (gotcha #93), que es el nombre OFICIAL scrapeado completo.
    original_title = getattr(candidate, "original_title", "") or ""
    if original_title:
        row["original_title"] = original_title

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
    # `/watch-standardize-catalog` luego corrige los casos raros.
    sk = getattr(candidate, "series_key", "") or ""
    sd = getattr(candidate, "series_display", "") or ""
    ek = getattr(candidate, "edition_key", "") or ""
    ed = getattr(candidate, "edition_display", "") or ""
    vol = getattr(candidate, "volume", "") or ""

    if not (sk and ek):
        derived = derive_series_metadata(candidate)
        if derived:
            sk = sk or derived.get("series_key", "")
            sd = sd or derived.get("series_display", "")
            ek = ek or derived.get("edition_key", "")
            ed = ed or derived.get("edition_display", "")
            vol = vol or derived.get("volume", "")

    # Paso B: pasar el series_key/display por el aliases.yml resolver. Esto
    # consolida traducciones multilingües (Demon Slayer = Kimetsu no Yaiba =
    # 鬼滅の刃 = Guardianes de la Noche) a la canonical key.
    if canonical_series_key is not None and (sk or sd):
        new_sk, new_sd = canonical_series_key(candidate.title, sk, sd)
        if ek.startswith(sk + "-") and new_sk != sk:
            ek = new_sk + ek[len(sk):]
        sk, sd = new_sk, new_sd

    # Frontera única del campo volume: puede venir del parser de la fuente
    # (candidate.volume) o del heurístico — dígitos full-width JP se
    # normalizan acá, ANTES de escribir el row (gotcha #82).
    vol = (vol or "").translate(FULLWIDTH_DIGITS_TABLE)

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
    # El `title` NUNCA se reescribe: es el nombre OFICIAL con que la fuente
    # publica el producto (política de títulos 2026-06-12). Ni la heurística,
    # ni el skill /watch-standardize-catalog, ni los retrofits lo renombran a
    # la serie canónica ni lo traducen — la serie canónica vive en
    # series_key/series_display y la búsqueda resuelve aliases.

    # cluster_key se deriva DESPUÉS del Paso C: con edition_key ya escrito en
    # el row, la clave sale en tier edition: (o lmc:). Derivarla antes dejaba
    # toda fila fresca en tier fuzzy/url: → stored != derive_cluster_key(item),
    # violación CLKEY hasta correr backfill_cluster_key (gotcha #65).
    row["cluster_key"] = derive_cluster_key(row)

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

    # Rarity — derivar solo si el item no tiene ya un valor curado. Los items
    # que pasaron por web-search en set_rarity.py tienen 'common' asignado;
    # no pisarlo con 'rare' en un re-scrape. Ver gotcha sobre _CURATED_FIELDS.
    # sources= no se pasa aquí: al momento del scrape el row tiene una sola
    # fuente y el fallback default ([source]) la cubre correctamente.
    if not row.get("rarity"):
        row["rarity"] = derive_rarity_tier(
            signal_types=row.get("signal_types") or [],
            source=row.get("source") or "",
            description=row.get("description") or "",
            title=row.get("title") or "",
            publisher=row.get("publisher") or "",
            stock_status=row.get("stock_status") or "",
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
    "challenge": "Challenge anti-bot (Cloudflare/WAF)",
    "blocked-403": "Bloqueadas con 403 (tras reintento)",
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
    # images[] non-cover (idx > 0): cada elemento sin `local` poblado
    # se mira como target. idx=0 ya cubierta por image_url arriba.
    extra_targets: list[tuple[Candidate, int]] = []
    for c in candidates:
        if c.status not in {"new", "changed"}:
            continue
        imgs = getattr(c, "images", None) or []
        for idx, im in enumerate(imgs):
            if idx == 0:
                continue
            if im.get("url") and not im.get("local"):
                extra_targets.append((c, idx))

    if not cover_targets and not extra_targets:
        return (0, 0)

    images_dir = data_dir / image_store.IMAGES_DIRNAME

    def _one_cover(cand: Candidate) -> tuple[Candidate, str]:
        # Normalize CDN resize params before downloading so image_url and
        # image_local always reflect the full-res version from the first scrape.
        clean_url = image_store.normalize_image_url(cand.image_url)
        if clean_url != cand.image_url:
            cand.image_url = clean_url
        filename = image_store.download_image(
            cand.image_url, images_dir, session=session,
            timeout=timeout, referer=cand.url or cand.source_url,
        )
        return cand, filename

    def _one_extra(args: tuple[Candidate, int]) -> tuple[Candidate, int, str]:
        cand, idx = args
        im = cand.images[idx]
        # Normalize CDN resize params for gallery images too.
        clean_url = image_store.normalize_image_url(im["url"])
        if clean_url != im["url"]:
            im["url"] = clean_url
        filename = image_store.download_image(
            im["url"], images_dir, session=session,
            timeout=timeout, referer=cand.url or cand.source_url,
        )
        return cand, idx, filename

    cover_results: list[tuple[Candidate, str]] = []
    extra_results: list[tuple[Candidate, int, str]] = []
    future_errors = 0
    if workers <= 1:
        cover_results = [_one_cover(c) for c in cover_targets]
        extra_results = [_one_extra(t) for t in extra_targets]
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="image") as pool:
            futs = [pool.submit(_one_cover, c) for c in cover_targets]
            futs.extend(pool.submit(_one_extra, t) for t in extra_targets)
            for fut in as_completed(futs):
                # M7 (Fable 2026-07-08): un future que levanta (bug de
                # image_store, URL malformada, etc.) NO debe abortar el resto
                # del mirror — se cuenta como fallo y seguimos, igual que el
                # loop de detail-fetch.
                try:
                    res = fut.result()
                except Exception:
                    future_errors += 1
                    continue
                if len(res) == 2:
                    cover_results.append(res)
                else:
                    extra_results.append(res)

    downloaded = 0
    failed = future_errors
    for cand, filename in cover_results:
        if filename:
            cand.image_local = filename
            imgs = getattr(cand, "images", None) or []
            if imgs and imgs[0].get("url") == cand.image_url:
                imgs[0]["local"] = filename
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
    elif args.bootstrap_wiki == "booksprivilege":
        from wikis.booksprivilege import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "sumikko":
        from wikis.sumikko import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "listadomanga-collections":
        from wikis.listadomanga_collections import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "mangapassion":
        from wikis.mangapassion import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "animeclick":
        from wikis.animeclick import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "prhcomics":
        from wikis.prhcomics import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "kinokuniya":
        from wikis.kinokuniya import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "yenpress":
        from wikis.yenpress_calendar import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "shueisha":
        from wikis.shueisha_books import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "viz":
        from wikis.viz_artbooks import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "sevenseas":
        from wikis.sevenseas import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "kodansha-us":
        from wikis.kodansha_us import bootstrap as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "jd-intl":
        from wikis.storefront_json import bootstrap_jd_intl as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "spp-tw":
        from wikis.storefront_json import bootstrap_spp as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "kimdong":
        from wikis.storefront_json import bootstrap_kimdong as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "ipm":
        from wikis.storefront_json import bootstrap_ipm as wiki_bootstrap, iter_year_months
    elif args.bootstrap_wiki == "yaakz":
        from wikis.storefront_json import bootstrap_yaakz as wiki_bootstrap, iter_year_months
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
        _ids_file = getattr(args, "coleccion_ids_file", "") or ""
        if _ids_file:
            with open(_ids_file) as _fh:
                extra_kwargs["explicit_ids"] = [
                    int(x) for x in _fh.read().split() if x.strip().isdigit()
                ]
    # animeclick SIEMPRE necesita fetch_details=True — el calendario solo da
    # título + publisher + imagen; precio, fecha y descripción viven en el
    # detail page. El flag --fetch-details de la CLI es para el source loop
    # principal (distinto propósito), no para wiki bootstraps.
    if args.bootstrap_wiki == "animeclick":
        extra_kwargs["fetch_details"] = True

    # sevenseas TAMBIÉN: el listing API no trae ISBN/fecha/portada — viven en
    # el detail (media?parent + HTML del libro). Sin enrich la fuente pierde
    # su valor de dedup (ISBN).
    if args.bootstrap_wiki == "sevenseas":
        extra_kwargs["fetch_details"] = True

    # kodansha-us: el API solo da series; los volúmenes (ISBN/fecha/portada)
    # se extraen de las páginas individuales. Siempre fetch_details=True.
    if args.bootstrap_wiki == "kodansha-us":
        extra_kwargs["fetch_details"] = True

    # Evitar argumento duplicado: si extra_kwargs ya setea fetch_details
    # (ej. animeclick siempre True), no lo pasar también en el kwarg genérico.
    if "fetch_details" not in extra_kwargs:
        extra_kwargs["fetch_details"] = bool(args.fetch_details)

    # Pasamos flush_fn a todos los wikis: escribe candidatos a items.jsonl
    # incrementalmente mientras el bootstrap corre para no perder datos si el
    # proceso muere a mitad. Cada wiki llama a flush_fn en su unidad natural
    # (por mes, por página, por edición, etc.). append_jsonl es idempotente,
    # así que el write final de process_state simplemente actualiza campos.
    if not args.dry_run:
        _flush_items_path = items_path  # closure capture

        def _wiki_flush_fn(batch: list) -> None:
            # M9 (Fable 2026-07-08): delegar en flush_source_candidates (FUENTE
            # ÚNICA del flush) en vez de reimplementar el gate SIN el check de
            # state. Así un re-bootstrap de wiki NO reescribe los items ya "seen"
            # (mismo content_hash) — antes reescribía TODO el batch (multiplicando
            # los rewrites de 33 MB) y dejaba los raw con status/detected_at
            # frescos. `state` viene por closure de esta misma función.
            written = flush_source_candidates(
                batch, state, _flush_items_path, args.min_score
            )
            if written:
                print(f"[FLUSH-WIKI] {written} items escritos incrementalmente")

        extra_kwargs["flush_fn"] = _wiki_flush_fn

    candidates = wiki_bootstrap(
        yf, mf, yt, mt,
        session=session,
        sleep_seconds=args.sleep_seconds,
        timeout=(args.connect_timeout, args.read_timeout),
        min_score=args.min_score,
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
        # A3 (Fable 2026-07-08): state se persiste DESPUÉS de que las filas
        # lleguen a items.jsonl — mismo motivo que en run() (ver comentario
        # allí): si save_state corre antes y el proceso muere (o
        # mirror_candidate_images levanta) entre medio, state ya marca estos
        # candidates como conocidos pero items.jsonl nunca los recibió.
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
        save_state(state_path, state)
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
                country=source.country,
            )
            title = md.get("name") or _slugify(urlparse(prod_url).path).replace("-", " ")[:200]
            description = md.get("description") or title
            cand = candidate_from_source(source, title=title[:260], url=prod_url, description=description[:2500])
            cand.publisher = md.get("publisher") or source.publisher
            cand.image_url = md.get("image_url", "")
            md_images = md.get("images") or []
            if md_images:
                cand.images = list(md_images)
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
        # A3 (Fable 2026-07-08): mismo orden que run()/wiki-bootstrap — state
        # se persiste después de que items.jsonl ya tiene las filas.
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
        save_state(state_path, state)
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

    # --only-source es repetible (action=append). Histórico: era single-valued
    # y el flag repetido pisaba en silencio los anteriores (bug 2026-06-12:
    # una ingesta de 10 fuentes solo corrió la última).
    only_sources = [s.strip() for s in (args.only_source or []) if s and s.strip()]
    if only_sources:
        wanted = set(only_sources)
        matched = [s for s in sources_all if s.name in wanted]
        missing = wanted - {s.name for s in matched}
        if missing:
            available = ", ".join(s.name for s in sources_all)
            print(f"[ERROR] --only-source no coincide: {', '.join(sorted(missing))}")
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
    robots = RobotsCache(args.user_agent, session=session,
                          timeout=(args.connect_timeout, args.read_timeout))

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

    # Semáforos de concurrencia: por host por defecto, o por throttle_group para
    # fuentes que comparten infraestructura remota (p. ej. borde Shopify). Ver
    # ThrottleRegistry. host_to_group se arma desde las fuentes cargadas (no sólo
    # las activas: el enriquecimiento de detalles puede tocar hosts agrupados).
    host_to_group: dict[str, str] = {}
    for _s in sources:
        grp = getattr(_s, "throttle_group", "")
        if grp:
            _h = (urlparse(_s.url).hostname or "").lower()
            if _h:
                host_to_group[_h] = grp
    throttle_group_delay = float(getattr(args, "throttle_group_delay", 2.0) or 0.0)
    throttle = ThrottleRegistry(
        per_host_limit,
        host_to_group=host_to_group,
        group_delay=throttle_group_delay,
    )
    if workers > 1 and host_to_group:
        _grp_names = sorted(set(host_to_group.values()))
        print(
            f"[INFO] Throttle groups: {', '.join(_grp_names)} "
            f"(limit 1, delay {throttle_group_delay:g}s) — "
            f"{len(host_to_group)} host(s) agrupados"
        )
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

    def _fetch_source_html(
        source: Source, url: str, timeout: tuple[int, int]
    ) -> tuple[str, dict[str, Any]]:
        """Fetch HTML de una fuente `html`, con UA por-fuente + manejo de 403.

        - Usa `source.user_agent` (sources.yml) si está definido; si no, el UA
          de la sesión.
        - Ante un 403: UN reintento único con UA browser-like alternativo +
          backoff (NO se reintenta en loop — 403 idéntico escala el bloqueo).
          Si el 403 persiste, loguea BLOCKED_403 y levanta Blocked403Error para
          abandonar la fuente en este run.
        """
        per_source_ua = (getattr(source, "user_agent", "") or "").strip() or None
        try:
            return fetch_with_metadata(session, url, timeout, user_agent=per_source_ua)
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is None or resp.status_code != 403:
                raise
        # 403 → un reintento único con UA browser-like alternativo + backoff.
        alt_ua = _BROWSER_LIKE_UA if per_source_ua != _BROWSER_LIKE_UA else _PLAYWRIGHT_REAL_UA
        _safe_print(
            f"[403] {source.name}: reintento único con UA browser-like tras "
            f"{int(_BLOCKED_403_BACKOFF_SECONDS)}s"
        )
        time.sleep(_BLOCKED_403_BACKOFF_SECONDS)
        try:
            return fetch_with_metadata(session, url, timeout, user_agent=alt_ua)
        except requests.HTTPError as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code == 403:
                _safe_print(f"[BLOCKED_403] source={source.name}")
                raise Blocked403Error(source.name) from exc
            raise

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

        # M8 (Fable 2026-07-08): inicializados ANTES del try (no dentro, tras
        # los early-return de robots/js) para que estén siempre definidos
        # cuando un except dispare `_finalize_partial_pages()` — incluidas
        # excepciones que ocurran antes de llegar al loop de paginación.
        all_candidates_source: list[Candidate] = []
        pages_visited = 0
        skipped_for_js = False
        challenge_hit = False

        def _finalize_partial_pages() -> None:
            """M8 (Fable 2026-07-08): scorea y guarda lo acumulado en
            `all_candidates_source` hasta el momento del error — un
            HTTPError/timeout/Blocked403 en la página N de una fuente
            paginada ya NO descarta las páginas 1..N-1 que sí se scrapearon
            con éxito. El problema/error ya se registró aparte; esto sólo
            recupera el trabajo parcial."""
            if not all_candidates_source:
                return
            scored = [score_candidate(candidate) for candidate in all_candidates_source]
            local_candidates.extend(scored)
            diagnostic.record_candidates(scored, entry=entry)
            if diagnostic.enabled and entry is not None:
                entry["pages_visited"] = pages_visited
            pages_note = f" ({pages_visited} págs)" if pages_visited > 1 else ""
            _safe_print(
                f"    [{source.name}] candidatos con señales: {len(scored)}{pages_note} [parcial, error en página siguiente]"
            )

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
                    with throttle.acquire(api_url):
                        text, fetch_meta = fetch_with_metadata(
                            session=session,
                            url=api_url,
                            timeout=(args.connect_timeout, args.read_timeout),
                        )
                else:
                    with throttle.acquire(current_url):
                        # Path HTTP plano: UA por-fuente + manejo de 403 (un
                        # reintento con UA alternativo; si persiste, Blocked403Error).
                        text, fetch_meta = _fetch_source_html(
                            source, current_url,
                            timeout=(args.connect_timeout, args.read_timeout),
                        )

                if page_num == 1:
                    diagnostic.record_fetch(fetch_meta, text, entry=entry)

                # Anti-bot: un 200 OK que en realidad es un challenge
                # (Cloudflare/WAF) NO es "0 items": es un fallo de fuente.
                # Detectarlo y tratarlo como tal para no confundir un bloqueo
                # con una fuente vacía. Solo aplica al path HTTP plano (rss/
                # bluesky son JSON; js tiene su propio manejo en Playwright).
                if source.kind not in {"rss", "feed", "atom", "bluesky", "js"}:
                    challenge_type = detect_challenge(text, fetch_meta.get("http_status"))
                    if challenge_type:
                        message = (
                            f"challenge anti-bot ({challenge_type}) en HTTP "
                            f"{fetch_meta.get('http_status')}"
                        )
                        _safe_print(
                            f"[CHALLENGE_DETECTED] source={source.name} type={challenge_type}"
                        )
                        local_errors.append(f"{source.name}: {message}")
                        _record_problem("challenge", message)
                        diagnostic.record_status("challenge", message, entry=entry)
                        challenge_hit = True
                        break

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

            if not skipped_for_js and not challenge_hit:
                scored = [score_candidate(candidate) for candidate in all_candidates_source]
                local_candidates.extend(scored)
                diagnostic.record_candidates(scored, entry=entry)
                if diagnostic.enabled and entry is not None:
                    entry["pages_visited"] = pages_visited
                pages_note = f" ({pages_visited} págs)" if pages_visited > 1 else ""
                # Nombre completo (sin truncar) para que source_health.py pueda
                # mapear la línea a la entrada de sources.yml. Ver gotcha de
                # observabilidad / scripts/audit/source_health.py.
                _safe_print(f"    [{source.name}] candidatos con señales: {len(scored)}{pages_note}")

        except requests.HTTPError as exc:
            message = f"{source.name}: HTTP error {exc}"
            _safe_print(f"[ERROR] {message}")
            local_errors.append(message)
            _record_problem("http", str(exc))
            diagnostic.record_status("http", str(exc), entry=entry)
            _finalize_partial_pages()
        except requests.RequestException as exc:
            message = f"{source.name}: request error {exc}"
            _safe_print(f"[ERROR] {message}")
            local_errors.append(message)
            _record_problem("request", str(exc))
            diagnostic.record_status("request", str(exc), entry=entry)
            _finalize_partial_pages()
        except Blocked403Error:
            # 403 persistente tras el reintento con UA alternativo: fuente
            # abandonada en este run (BLOCKED_403 ya se logueó en _fetch_source_html).
            message = f"{source.name}: bloqueada con 403 tras reintento (BLOCKED_403)"
            _safe_print(f"[ERROR] {message}")
            local_errors.append(message)
            _record_problem("blocked-403", "403 persistente tras reintento con UA alternativo")
            diagnostic.record_status("blocked-403", "BLOCKED_403", entry=entry)
            _finalize_partial_pages()
        except Exception as exc:
            message = f"{source.name}: error inesperado {exc}"
            _safe_print(f"[ERROR] {message}")
            local_errors.append(message)
            _record_problem("other", str(exc))
            diagnostic.record_error(exc, entry=entry)
            _finalize_partial_pages()

        return {
            "candidates": local_candidates, "errors": local_errors,
            "problems": local_problems, "text": text, "entry": entry,
        }

    # Contador para el flush incremental (sólo se muestra si hay algo que escribir).
    _flushed_total = 0

    if workers == 1:
        # Path serial: idéntico al comportamiento histórico.
        for index, source in enumerate(sources, start=1):
            result = _scrape_one(index, source)
            all_candidates.extend(result["candidates"])
            errors.extend(result["errors"])
            problems.extend(result["problems"])
            finalized = diagnostic.end(entry=result["entry"])
            diagnostic.maybe_dump_html(finalized, result["text"])
            # Flush incremental: escribe candidatos new/changed de esta fuente
            # inmediatamente para no perder datos si el proceso es interrumpido.
            n = flush_source_candidates(
                result["candidates"], state, items_path, args.min_score, args.dry_run
            )
            _flushed_total += n
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
                # Flush incremental: escribe candidatos new/changed de esta fuente
                # inmediatamente para no perder datos si el proceso es interrumpido.
                n = flush_source_candidates(
                    result["candidates"], state, items_path, args.min_score, args.dry_run
                )
                _flushed_total += n

    if _flushed_total:
        _safe_print(f"[FLUSH] {_flushed_total} items escritos incrementalmente al JSONL")

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
            with throttle.acquire(c.url):
                metadata = fetch_metadata_from_detail(
                    c.url, session, timeout=(args.connect_timeout, args.read_timeout),
                    country=c.country,
                )
            return c, metadata

        def _apply_metadata(idx: int, c: Candidate, metadata: dict[str, Any]) -> None:
            """Aplica metadata al candidate y al state. Llamado SECUENCIALMENTE."""
            nonlocal enriched_author, enriched_image
            new_author = metadata.get("author") or ""
            new_image = metadata.get("image_url") or ""
            new_images = metadata.get("images") or []
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
            # Carrusel multi-imagen: enriquece si el detail page expone galería
            # y el Candidate todavía no la trajo (típicamente la fuente original
            # sólo trajo la cover desde el listing).
            if new_images and len(new_images) > len(getattr(c, "images", []) or []):
                c.images = list(new_images)
                if len(new_images) > 1:
                    updates.append(f"imgs: {len(new_images)}")
            if new_isbn and not c.isbn:
                c.isbn = new_isbn
                updates.append(f"isbn: {new_isbn}")
            if updates:
                _recompute_content_hash(c)
                key = candidate_key(c)
                if key in state:
                    state[key]["author"] = c.author
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
                    errors.append(f"fetch-details {c.source}: {c.url} → {exc}")
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
                        errors.append(f"fetch-details {c.source}: {c.url} → {exc}")
                        metadata = {}
                    _apply_metadata(idx, c, metadata)

        print(
            f"[FETCH-DETAILS] {enriched_author} autores · {enriched_image} imágenes enriquecidas"
        )

    if not args.dry_run:
        # A3 (Fable 2026-07-08): save_state va DESPUÉS de mirror+append, no
        # antes. `_apply_metadata` ya actualizó `state[key]["content_hash"]`
        # con el hash POST-detail-fetch; si persistíamos ese state ANTES de
        # que la fila enriquecida llegara a items.jsonl, un crash entre medio
        # (o una excepción en mirror_candidate_images) dejaba el
        # enriquecimiento perdido para siempre: el próximo run ve el hash ya
        # "al día" en state y nunca re-escribe ni re-hace el detail-fetch.
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
        save_state(state_path, state)
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
    # Anti-bot: contar challenges / 403 por fuente para que un BLOQUEO no se
    # confunda con "fuente vacía" (una fuente challengeada trae 0 items pero
    # NO está vacía). Desglose por fuente debajo del contador.
    challenge_problems = [p for p in problems if p.get("category") == "challenge"]
    blocked_problems = [p for p in problems if p.get("category") == "blocked-403"]
    if challenge_problems or blocked_problems:
        print(
            f"  anti-bot: {len(challenge_problems)} challenge(s), "
            f"{len(blocked_problems)} bloqueo(s) 403"
        )
        for p in challenge_problems:
            print(f"    [challenge] {p.get('source', '?')} — {p.get('message', '')}")
        for p in blocked_problems:
            print(f"    [blocked-403] {p.get('source', '?')}")
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
    parser.add_argument("--min-score", type=int, default=20, help="Score mínimo. Default: 20 (coincide con el umbral del dashboard y con los scripts canónicos scrape_delta/scrape_full).")
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
    parser.add_argument(
        "--throttle-group-delay", type=float, default=2.0,
        help="Segundos mínimos entre requests de fuentes que comparten `throttle_group` "
             "en sources.yml (p. ej. tiendas Shopify tras el mismo borde). Default: 2.0. "
             "0 = sólo serializar (limit 1) sin delay.",
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
        action="append",
        default=None,
        help="Procesa solo la(s) fuente(s) con este nombre exacto (repetible: "
             "--only-source A --only-source B). Útil para debug e ingestas "
             "dirigidas.",
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
        choices=["listadomanga", "listadomanga-blog", "whakoom", "manga-sanctuary", "otaku-calendar", "manga-mexico", "mangavariant", "socialanime", "blogbbm", "booksprivilege", "sumikko", "listadomanga-collections", "mangapassion", "animeclick", "prhcomics", "kinokuniya", "yenpress", "shueisha", "viz", "sevenseas", "kodansha-us", "jd-intl", "spp-tw", "kimdong", "ipm", "yaakz"],
        help="En lugar de scrapear las fuentes del YAML, importa items de una wiki comunitaria. Soporta: listadomanga (calendario ES), listadomanga-blog (archivo histórico del blog ES — anuncios/exclusivas, complementa el feed RSS), whakoom (spider 3 niveles desde /newtitles → /comics/ → /ediciones/ con variantes), manga-sanctuary (Francia), otaku-calendar (EN/US, por mes), manga-mexico (catálogo MX por editorial), mangavariant (base global de variants/ediciones, 13 países — ignora --wiki-from/--wiki-to, importa todo el sitemap), socialanime (MangaStore italiano: variant/limited/special editions + cofanetti, ~840 items vía JSON feed), blogbbm (Biblioteca Brasileira de Mangás: dos posts curados — capas variantes + volúmenes con extras — actualizados continuamente), booksprivilege (agregador JP de 店舗特典/extras de tienda: por cada release lista los bonus de cada retailer japonés — Animate, Gamers, Toranoana, Melonbooks, COMIC ZIN, etc. — que no aparecen en el catálogo regular), sumikko (catálogo curado JP de 限定版/特装版 — ~3178 ediciones limitadas y especiales con ISBN, complementario a booksprivilege que es store-bonus; sumikko se enfoca en la edición en sí: acrylic stand付き, 小冊子付き, 缶バッジ付き, BOX, etc.), listadomanga-collections (parser por colección individual coleccion.php?id=N — ediciones especiales/portadas alternativas/packs/formato premium; usa --coleccion-from y --coleccion-to en vez del rango de fechas).",
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
        "--coleccion-ids-file",
        default="",
        help="Archivo con ids de colección (uno o varios por línea, whitespace-sep) "
             "para --bootstrap-wiki listadomanga-collections. Si se pasa, IGNORA "
             "--coleccion-mode/from/to y procesa EXACTAMENTE esos ids en orden "
             "(ingesta por chunks resumible).",
    )
    parser.add_argument(
        "--coleccion-mode",
        choices=["lista", "range", "calendar"],
        default="lista",
        help="Discovery para --bootstrap-wiki listadomanga-collections. 'lista' (default): usa lista.php como índice oficial alfabético (~3432 colecciones activas, modo recomendado para el FULL). 'range': iteración numérica id_from..id_to (legacy). 'calendar' (DELTA): descubre los ids de colección con actividad en el calendario (calendario.php) en la ventana --wiki-from→--wiki-to y parsea SOLO esas colecciones completas — da la misma riqueza de ediciones/cofres/variantes que el full pero acotado a lo reciente.",
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
