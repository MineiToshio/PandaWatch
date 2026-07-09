#!/usr/bin/env python3
"""recover_lost_jp_titles.py — recupera el nombre OFICIAL de items de mercado
japonés cuyo `title_original` fue pisado por corridas tempranas del skill de
standardize (el original se perdió y `restore_official_titles.py` solo pudo
dejar el título generado, ej. "Tensura Special 32" en vez de
"転生したらスライムだった件(32) 特装版").

Detección (alta confianza): item de mercado JP (edition_key `…-jp` o país
Japón) cuyo título está en alfabeto latino Y tiene la forma generada
"{series_display} {EdiciónEN} {vol}" — una tienda/base japonesa nunca lista
así. Dos vías de recuperación, ninguna inventa nombres:

  1. **Con ISBN** → openBD (https://api.openbd.jp/v1/get, API pública oficial
     de la industria editorial JP): título oficial del libro. Batch en una
     sola request por lote.
  2. **Mangavariant (sin ISBN)** → re-fetch de la propia página del item vía
     PLAYWRIGHT (el sitio está detrás de un challenge JS sgcaptcha desde
     2026-06; requests devuelve 202) + `parse_variant_detail` (mismo parser
     del bootstrap): título oficial del listing ("{Serie} — {Edición}").

Lo recuperado pisa `title_original` (el original verdadero) y `title`
(clean_title del oficial). Re-deriva cluster_key y consolida. Respeta
`approved_at`. Idempotente: tras recuperar, el título deja de verse
"generado" y el item sale del set de candidatos.

Uso:
  .venv/bin/python scripts/retrofit/recover_lost_jp_titles.py --dry-run
  .venv/bin/python scripts/retrofit/recover_lost_jp_titles.py
  .venv/bin/python scripts/retrofit/recover_lost_jp_titles.py --limit 20
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import requests  # noqa: E402

import manga_watch as mw  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"
OPENBD = "https://api.openbd.jp/v1/get"

_CJK = re.compile(r"[぀-ヿ一-鿿가-힯]")
_ED_WORDS = (
    "Special|Limited|Deluxe|Collector|Variant|Artbook|Fanbook|Guidebook|"
    "Kanzenban|Perfect|Ultimate|Maximum|Master|Library|Integral|Coffret|"
    "Cofanetto|Boxset|Box Set|Omnibus|Prestige|Steelbox|Slipcase|"
    "Anniversary|Celebration|Color"
)


def _looks_generated(title: str, series_display: str) -> bool:
    """True si el título tiene la forma "{serie} {EdiciónEN} {vol}" que
    producía el skill viejo (el original se perdió)."""
    if not title or not series_display:
        return False
    if not title.lower().strip().startswith(series_display.lower().strip()):
        return False
    rest = title[len(series_display):].strip()
    return bool(re.fullmatch(
        rf"(?:(?:{_ED_WORDS})\s*)*(?:\d+(?:-\d+)?)?(?:\s*Edición Especial)?",
        rest, re.IGNORECASE,
    ))


def _is_jp_market(it: dict) -> bool:
    ek = it.get("edition_key", "") or ""
    return ek.endswith("-jp") or "jap" in (it.get("country") or "").lower()


def _openbd_titles(isbns: list[str]) -> dict[str, str]:
    """ISBN → título oficial (openBD). Lotes de 500 (límite de la API: 1000)."""
    out: dict[str, str] = {}
    for i in range(0, len(isbns), 500):
        batch = isbns[i:i + 500]
        try:
            r = requests.get(OPENBD, params={"isbn": ",".join(batch)}, timeout=30)
            r.raise_for_status()
            for isbn, entry in zip(batch, r.json()):
                if not entry:
                    continue
                summary = entry.get("summary") or {}
                title = (summary.get("title") or "").strip()
                vol = (summary.get("volume") or "").strip()
                if title:
                    out[isbn] = f"{title} {vol}".strip() if vol and vol not in title else title
        except Exception as exc:  # red caída ≠ corromper data: se reporta y sigue
            print(f"  [openbd] lote {i//500} falló: {exc}", file=sys.stderr)
    return out


def _mangavariant_titles(urls: list[str]) -> dict[str, str]:
    """url → título oficial del listing, vía Playwright.

    Mangavariant está detrás de un challenge JS de SiteGround (sgcaptcha,
    2026-06-12): requests devuelve 202 con meta-refresh. Playwright lo
    resuelve; la cookie del challenge se reutiliza en el mismo contexto, así
    que sólo la primera página paga la espera. Ver la ficha
    docs/scraper/sources/mangavariant.md."""
    from wikis.mangavariant import parse_variant_detail
    out: dict[str, str] = {}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [mv] playwright no instalado — se omiten los de mangavariant",
              file=sys.stderr)
        return out
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        for i, url in enumerate(urls):
            try:
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                for _ in range(10):  # challenge → meta-refresh → página real
                    t = page.title()
                    if t and not t.startswith("Loading") and "captcha" not in t.lower():
                        break
                    page.wait_for_timeout(2000)
                cand = parse_variant_detail(page.content(), url)
                if cand and (cand.title or "").strip():
                    out[url] = cand.title.strip()
            except Exception:
                continue
            if (i + 1) % 25 == 0:
                print(f"  [mv] {i + 1}/{len(urls)} ({len(out)} ok)")
        browser.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="cap de items a recuperar")
    args = ap.parse_args()

    items = [json.loads(l) for l in ITEMS.open() if l.strip()]
    cands = [
        it for it in items
        if not it.get("approved_at")
        and _is_jp_market(it)
        and not _CJK.search(it.get("title", "") or "")
        and _looks_generated(it.get("title", "") or "", it.get("series_display", "") or "")
    ]
    if args.limit:
        cands = cands[:args.limit]
    with_isbn = [it for it in cands if it.get("isbn")]
    mv = [it for it in cands if not it.get("isbn")
          and "mangavariant.com" in (it.get("url") or "")]
    rest = [it for it in cands if it not in with_isbn and it not in mv]
    print(f"[recover-jp] candidatos: {len(cands)} "
          f"(openBD: {len(with_isbn)}, mangavariant: {len(mv)}, sin vía: {len(rest)})")

    recovered: dict[str, str] = {}  # url → título oficial

    isbn_titles = _openbd_titles([it["isbn"] for it in with_isbn])
    for it in with_isbn:
        t = isbn_titles.get(it["isbn"], "")
        if t:
            recovered[it["url"]] = t

    recovered.update(_mangavariant_titles([it["url"] for it in mv]))

    changed, examples = 0, []
    for it in cands:
        official = recovered.get(it.get("url", ""), "")
        if not official:
            continue
        new = mw.clean_title(official) or official
        old = it.get("title", "") or ""
        if new == old:
            continue
        if len(examples) < 30:
            examples.append((old, new))
        if not args.dry_run:
            it["title"] = new
            it["title_original"] = official
            it["cluster_key"] = mw.derive_cluster_key(it)
        changed += 1

    print(f"[recover-jp] títulos recuperados: {changed} "
          f"(sin respuesta: {len(cands) - changed})")
    for o, n in examples:
        print(f"    {o!r}  →  {n!r}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if changed:
        before = len(items)
        items = mw.consolidate_by_cluster(items)
        print(f"[recover-jp] consolidate: {before} → {len(items)}")
        backup = mw.backup_and_rotate(ITEMS, "recoverjp")
        print(f"[recover-jp] backup: {backup}")
        mw.write_items_atomic(ITEMS, items)
        print(f"[recover-jp] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
