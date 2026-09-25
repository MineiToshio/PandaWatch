#!/usr/bin/env python3
"""Repunta las URLs de AR - Ivrea Argentina que apuntaban a un JPG.

La home de ivrea.com.ar envuelve cada miniatura en `<a href="…/portada.jpg">`
(patrón lightbox de WordPress) y ese ancla va ANTES del enlace real al producto
en el DOM. El extractor tomaba la primera a ciegas, así que 19 de las 20
entradas `sources[]` de la fuente quedaron apuntando a un archivo de imagen: un
enlace que no lleva a ninguna ficha, sin ISBN ni fecha que leer. Era la ÚNICA
fuente del corpus con este problema (0 casos en las otras ~56).

El mecanismo ya está arreglado en `manga_watch.py` (`_product_anchor()` prefiere
el primer ancla que NO sea un archivo de imagen). Este retrofit arregla lo YA
ingresado.

Las fichas reales son por SERIE: `ivrea.com.ar/titulo/<slug>/`. El slug se
resuelve contra el índice REAL del catálogo del sitio (no se inventa) y cada
URL candidata se VERIFICA con una petición en vivo antes de escribirla. Un item
que no resuelve se deja intacto y se reporta.

Uso:
    .venv/bin/python scripts/retrofit/fix_ivrea_image_urls_20260907.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from manga_watch import backup_and_rotate, write_items_atomic  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"
HOST = "ivrea.com.ar"
CATALOG_URLS = (
    "https://www.ivrea.com.ar/catalogo/",
    "https://www.ivrea.com.ar/shonen/",
    "https://www.ivrea.com.ar/seinen/",
    "https://www.ivrea.com.ar/shojo/",
)
TITULO_RE = re.compile(r"/titulo/")
IMAGE_URL_RE = re.compile(r"\.(?:jpg|jpeg|png|webp|avif|gif)$", re.IGNORECASE)
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


def slugify(text: str, keep_separators: bool = True) -> str:
    # Los apóstrofes se COMEN, no se convierten en separador: WordPress genera
    # "jojos-bizarre-adventure" a partir de "JoJo's Bizarre Adventure".
    text = re.sub(r"[\u2019\u02bc'`]", "", text or "")
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    if keep_separators:
        return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return re.sub(r"[^a-z0-9]+", "", ascii_text.lower())


def fetch_catalog_slugs(session: requests.Session) -> set[str]:
    slugs: set[str] = set()
    for url in CATALOG_URLS:
        try:
            resp = session.get(url, timeout=30)
        except requests.RequestException as exc:
            print(f"  [warn] {url}: {exc}")
            continue
        if resp.status_code != 200:
            print(f"  [warn] {url}: HTTP {resp.status_code}")
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        for anchor in soup.find_all("a", href=TITULO_RE):
            slug = (anchor.get("href") or "").rstrip("/").rsplit("/", 1)[-1]
            if slug:
                slugs.add(slug)
    return slugs


def candidate_slugs(item: dict) -> list[str]:
    """Slugs a probar, del más específico al más general."""
    out: list[str] = []
    for base in (item.get("series_display") or "", item.get("title") or ""):
        if not base:
            continue
        # Quitar el nº de tomo y los adornos habituales del título.
        cleaned = re.sub(r"[#№]\s*\d+.*$", "", base)
        cleaned = re.sub(r"\s+\d+\s*$", "", cleaned)
        for text in (base, cleaned):
            full = slugify(text)
            if not full:
                continue
            out.append(full)
            out.append(slugify(text, keep_separators=False))
            # Truncado progresivo: "jojo-s-bizarre-adventure-jojolion-17" →
            # … → "jojos-bizarre-adventure" (con y sin separadores).
            parts = full.split("-")
            for cut in range(len(parts) - 1, 1, -1):
                prefix = "-".join(parts[:cut])
                out.append(prefix)
                out.append(prefix.replace("-", ""))
    seen: set[str] = set()
    ordered = []
    for slug in out:
        if slug and slug not in seen:
            seen.add(slug)
            ordered.append(slug)
    return ordered


def is_image_url(url: str) -> bool:
    clean = (url or "").split("?", 1)[0].split("#", 1)[0]
    return HOST in clean and bool(IMAGE_URL_RE.search(clean))


def is_image_source(source: dict) -> bool:
    return is_image_url(source.get("url") or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    session = requests.Session()
    session.headers.update(UA)

    print("Leyendo el índice de fichas del catálogo…")
    slugs = fetch_catalog_slugs(session)
    print(f"  {len(slugs)} slugs /titulo/ conocidos\n")
    if not slugs:
        print("No se pudo leer el catálogo — se aborta sin tocar nada.")
        return 1

    items = [json.loads(line) for line in ITEMS.read_text().splitlines() if line.strip()]

    verified: dict[str, str] = {}   # slug -> url verificada
    rejected: set[str] = set()
    fixed = 0
    unresolved: list[str] = []

    for it in items:
        targets = [s for s in (it.get("sources") or []) if is_image_source(s)]
        # El item lleva TAMBIÉN una `url` de nivel superior (la primaria, la que
        # leen las proyecciones de standardize y varios retrofits). Reparar sólo
        # `sources[]` deja la mitad del bug vivo — detectado 2026-09-07 al ver
        # que las proyecciones Tier 2 seguían mostrando el .jpg.
        top_level_broken = is_image_url(it.get("url") or "")
        if not targets and not top_level_broken:
            continue
        title = (it.get("title") or "")[:46]
        chosen = None
        for slug in candidate_slugs(it):
            if slug not in slugs or slug in rejected:
                continue
            if slug in verified:
                chosen = verified[slug]
                break
            url = f"https://www.ivrea.com.ar/titulo/{slug}/"
            try:
                resp = session.get(url, timeout=30)
            except requests.RequestException:
                rejected.add(slug)
                continue
            if resp.status_code == 200:
                verified[slug] = url
                chosen = url
                break
            rejected.add(slug)
        if not chosen:
            unresolved.append(f"{it.get('slug')} | {title}")
            continue
        for source in targets:
            print(f"  {title:48s}\n    sources[]: {source['url'][-46:]} → {chosen}")
            source["url"] = chosen
            fixed += 1
        if top_level_broken:
            print(f"  {title:48s}\n    url:       {(it.get('url') or '')[-46:]} → {chosen}")
            it["url"] = chosen
            fixed += 1

    print(f"\nEntradas sources[] repuntadas: {fixed}")
    if unresolved:
        print(f"Sin ficha resoluble ({len(unresolved)}) — se dejaron intactas:")
        for line in unresolved:
            print(f"  {line}")

    if args.dry_run:
        print("[DRY-RUN] No se escribió nada.")
        return 0
    if fixed:
        backup_and_rotate(ITEMS, "ivrea-image-urls")
        write_items_atomic(ITEMS, items)
        print("items.jsonl actualizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
