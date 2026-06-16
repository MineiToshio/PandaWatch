"""Tests para scripts/retrofit/migrate_images_to_avif.py — migración a AVIF.

Sin red — espejo + _originals/ + items.jsonl sintéticos en tmp_path.

Cubre: re-derivación desde el original (no desde el WebP), dedup por contenido,
placeholder intacto, idempotencia (master ya AVIF), y fallback sin original.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import migrate_images_to_avif as mig  # noqa: E402


def _tile(w, h):
    im = Image.new("RGB", (64, 64))
    px = im.load()
    for y in range(64):
        for x in range(64):
            px[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 5) % 256)
    return im.resize((w, h))


def _save(path: Path, w, h, fmt, **kw):
    path.parent.mkdir(parents=True, exist_ok=True)
    _tile(w, h).save(path, fmt, **kw)


def _solid(path: Path, w=120, h=120):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), (255, 255, 255)).save(path, "PNG")


def _dims(path):
    with Image.open(path) as im:
        return im.size


def _fmt(path):
    with Image.open(path) as im:
        return im.format


def _items(tmp, rows):
    p = tmp / "items.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    return p


def _run(imgs, orig, items, preview, **kw):
    d = dict(workers=1, limit=0, dry_run=False, max_long_side=1600, quality=60)
    d.update(kw)
    return mig.run(imgs, orig, items, preview, **d)


def test_rederives_from_original_not_webp(tmp_path):
    imgs = tmp_path / "images"
    orig = imgs / "_originals"
    # master actual WebP CHICO (800x1200); original GRANDE (2000x3000)
    _save(imgs / "aaaa000000000001.webp", 800, 1200, "WEBP", quality=80)
    _save(orig / "aaaa000000000001.png", 2000, 3000, "PNG")
    items = _items(tmp_path, [
        {"slug": "x", "images": [{"url": "u", "local": "aaaa000000000001.webp"}]},
    ])
    _run(imgs, orig, items, tmp_path / "cp.json")

    avif = imgs / "aaaa000000000001.avif"
    assert avif.is_file() and _fmt(avif) == "AVIF"
    # Si viniera del WebP (800), el lado largo sería 1200; del original (3000) → 1600.
    assert max(_dims(avif)) == 1600
    assert not (imgs / "aaaa000000000001.webp").exists()  # WebP viejo borrado
    assert (orig / "aaaa000000000001.png").is_file()      # original intacto
    row = json.loads(items.read_text().strip())
    assert row["images"][0]["local"] == "aaaa000000000001.avif"


def test_dedup_collapses_identical(tmp_path):
    imgs = tmp_path / "images"
    orig = imgs / "_originals"
    # dos masters distintos pero con ORIGINALES idénticos → 1 solo AVIF
    for stem in ("aaaa000000000001", "bbbb000000000002"):
        _save(imgs / f"{stem}.webp", 600, 900, "WEBP", quality=80)
        _save(orig / f"{stem}.png", 1200, 1800, "PNG")  # mismo contenido
    items = _items(tmp_path, [
        {"slug": "a", "images": [{"url": "u", "local": "aaaa000000000001.webp"}]},
        {"slug": "b", "images": [{"url": "v", "local": "bbbb000000000002.webp"}]},
    ])
    res = _run(imgs, orig, items, tmp_path / "cp.json")

    avifs = sorted(p.name for p in imgs.iterdir() if p.suffix == ".avif")
    assert len(avifs) == 1  # colapsadas a un solo archivo
    assert res["deduped"] == 1
    rows = [json.loads(l) for l in items.read_text().splitlines() if l.strip()]
    locals_ = {r["images"][0]["local"] for r in rows}
    assert locals_ == {avifs[0]}  # ambos items apuntan al mismo AVIF


def test_placeholder_master_untouched(tmp_path):
    imgs = tmp_path / "images"
    orig = imgs / "_originals"
    orig.mkdir(parents=True)
    _solid(imgs / "cccc000000000003.png")  # placeholder, sin original archivado
    items = _items(tmp_path, [
        {"slug": "p", "images": [{"url": "u", "local": "cccc000000000003.png"}]},
    ])
    res = _run(imgs, orig, items, tmp_path / "cp.json")
    assert res["counter"].get("skip") == 1
    assert (imgs / "cccc000000000003.png").is_file()        # intacto
    assert not (imgs / "cccc000000000003.avif").exists()
    row = json.loads(items.read_text().strip())
    assert row["images"][0]["local"] == "cccc000000000003.png"


def test_rerun_idempotent_avif_skipped(tmp_path):
    imgs = tmp_path / "images"
    orig = imgs / "_originals"
    orig.mkdir(parents=True)
    _save(imgs / "dddd000000000004.avif", 1000, 1500, "AVIF", quality=60)
    before = (imgs / "dddd000000000004.avif").read_bytes()
    items = _items(tmp_path, [
        {"slug": "w", "images": [{"url": "u", "local": "dddd000000000004.avif"}]},
    ])
    res = _run(imgs, orig, items, tmp_path / "cp.json")
    assert res["counter"].get("skip") == 1
    assert (imgs / "dddd000000000004.avif").read_bytes() == before


def test_resumes_existing_avif_without_rederiving(tmp_path):
    """Re-run tras crash: el .avif ya escrito por la corrida previa se COMMITEA tal cual
    (sin re-derivar — continúa donde quedó) y el .webp se borra."""
    imgs = tmp_path / "images"
    orig = imgs / "_originals"
    # estado de crash: el .avif ya está, el .webp sigue, items SIGUE en .webp
    _save(imgs / "aaaa000000000001.webp", 600, 900, "WEBP", quality=80)
    _save(orig / "aaaa000000000001.png", 1200, 1800, "PNG")
    # .avif "ya hecho" con tamaño DISTINTO al que daría re-derivar (1600) → prueba no-rederive
    _save(imgs / "aaaa000000000001.avif", 800, 1200, "AVIF", quality=60)
    existing = (imgs / "aaaa000000000001.avif").read_bytes()
    items = _items(tmp_path, [
        {"slug": "x", "images": [{"url": "u", "local": "aaaa000000000001.webp"}]},
    ])
    res = _run(imgs, orig, items, tmp_path / "cp.json")

    assert res["counter"].get("resumed") == 1
    avif = imgs / "aaaa000000000001.avif"
    assert avif.read_bytes() == existing  # commiteado TAL CUAL, no re-derivado
    assert _dims(avif) == (800, 1200)     # 800x1200 (no 1600) → confirma que NO re-derivó
    assert not (imgs / "aaaa000000000001.webp").exists()  # webp viejo borrado
    row = json.loads(items.read_text().strip())
    assert row["images"][0]["local"] == "aaaa000000000001.avif"


def test_incremental_commit_per_batch(tmp_path):
    """Con batch chico, cada lote se commitea DURANTE la corrida (progreso durable):
    items.jsonl flipea y los webp se borran por lote, no recién al final."""
    imgs = tmp_path / "images"
    orig = imgs / "_originals"
    for stem in ("aaaa000000000001", "bbbb000000000002"):
        _save(imgs / f"{stem}.webp", 600, 900, "WEBP", quality=80)
        _save(orig / f"{stem}.png", 1200, 1800, "PNG")
    items = _items(tmp_path, [
        {"slug": "a", "images": [{"url": "u", "local": "aaaa000000000001.webp"}]},
        {"slug": "b", "images": [{"url": "v", "local": "bbbb000000000002.webp"}]},
    ])
    res = _run(imgs, orig, items, tmp_path / "cp.json", batch=1)
    assert res["renames"] == 2 and res["deleted"] == 2
    rows = [json.loads(l) for l in items.read_text().splitlines() if l.strip()]
    assert all(r["images"][0]["local"].endswith(".avif") for r in rows)
    assert not list(imgs.glob("*.webp"))  # todos los webp borrados (commiteados)


def test_fallback_to_webp_when_no_original(tmp_path):
    imgs = tmp_path / "images"
    orig = imgs / "_originals"
    orig.mkdir(parents=True)
    _save(imgs / "eeee000000000005.webp", 900, 1350, "WEBP", quality=80)  # sin original
    items = _items(tmp_path, [
        {"slug": "f", "images": [{"url": "u", "local": "eeee000000000005.webp"}]},
    ])
    _run(imgs, orig, items, tmp_path / "cp.json")
    assert (imgs / "eeee000000000005.avif").is_file()       # convertido desde el WebP
    assert not (imgs / "eeee000000000005.webp").exists()
    row = json.loads(items.read_text().strip())
    assert row["images"][0]["local"] == "eeee000000000005.avif"
