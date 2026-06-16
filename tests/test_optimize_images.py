"""Tests para scripts/retrofit/optimize_images.py — backfill del espejo.

Sin red — espejo + items.jsonl + cover_preview.json sintéticos en tmp_path.

Cubre: conversión .png→.avif con resize, actualización de images[].local y
sources[].image_local en items.jsonl, actualización de cover_preview.json,
archivado de originales (y modo delete), idempotencia (skip de avif chico),
placeholders intactos, resize in situ de avif grande, y dry-run sin escritura.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from PIL import Image

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import optimize_images as oi  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _tile(w: int, h: int) -> Image.Image:
    im = Image.new("RGB", (64, 64))
    px = im.load()
    for y in range(64):
        for x in range(64):
            px[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 5) % 256)
    return im.resize((w, h))


def _write_png(path: Path, w: int, h: int) -> None:
    _tile(w, h).save(path, "PNG")


def _write_avif(path: Path, w: int, h: int) -> None:
    _tile(w, h).save(path, "AVIF", quality=60)


def _write_solid_png(path: Path, w=120, h=120) -> None:
    Image.new("RGB", (w, h), (255, 255, 255)).save(path, "PNG")


def _dims(path: Path):
    with Image.open(path) as im:
        return im.size


def _fmt(path: Path):
    with Image.open(path) as im:
        return im.format


def _items_file(tmp: Path, rows: list[dict]) -> Path:
    p = tmp / "items.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    return p


def _run(images_dir, items, preview, **kw):
    defaults = dict(workers=2, limit=0, dry_run=False, originals_mode="archive",
                    max_long_side=1600, quality=60)
    defaults.update(kw)
    return oi.run(images_dir, items, preview, **defaults)


# ── tests ───────────────────────────────────────────────────────────────────────

def test_converts_png_and_updates_items(tmp_path):
    imgs = tmp_path / "images"
    imgs.mkdir()
    _write_png(imgs / "aaaa000000000001.png", 2000, 3000)
    items = _items_file(tmp_path, [
        {"slug": "x", "images": [{"url": "u", "local": "aaaa000000000001.png"}]},
    ])
    preview = tmp_path / "cover_preview.json"

    _run(imgs, items, preview)

    assert (imgs / "aaaa000000000001.avif").is_file()
    assert _fmt(imgs / "aaaa000000000001.avif") == "AVIF"
    assert max(_dims(imgs / "aaaa000000000001.avif")) <= 1600
    # original archivado, no en su sitio
    assert not (imgs / "aaaa000000000001.png").exists()
    assert (imgs / "_originals" / "aaaa000000000001.png").is_file()
    # items.jsonl actualizado
    row = json.loads(items.read_text().strip())
    assert row["images"][0]["local"] == "aaaa000000000001.avif"


def test_updates_sources_image_local(tmp_path):
    imgs = tmp_path / "images"
    imgs.mkdir()
    _write_png(imgs / "bbbb000000000002.png", 1800, 2400)
    items = _items_file(tmp_path, [
        {"slug": "y",
         "images": [{"url": "u", "local": "bbbb000000000002.png"}],
         "sources": [{"url": "s", "image_local": "bbbb000000000002.png"}]},
    ])
    _run(imgs, items, tmp_path / "cp.json")
    row = json.loads(items.read_text().strip())
    assert row["images"][0]["local"] == "bbbb000000000002.avif"
    assert row["sources"][0]["image_local"] == "bbbb000000000002.avif"


def test_updates_cover_preview(tmp_path):
    imgs = tmp_path / "images"
    imgs.mkdir()
    _write_png(imgs / "cccc000000000003.png", 1800, 2400)
    items = _items_file(tmp_path, [
        {"slug": "z", "images": [{"url": "u", "local": "cccc000000000003.png"}]},
    ])
    preview = tmp_path / "cover_preview.json"
    preview.write_text(json.dumps([
        {"slug": "z", "old_image": "cccc000000000003.png",
         "candidates": [{"new_image": "cccc000000000003.png"}]},
    ]))
    _run(imgs, items, preview)
    data = json.loads(preview.read_text())
    assert data[0]["old_image"] == "cccc000000000003.avif"
    assert data[0]["candidates"][0]["new_image"] == "cccc000000000003.avif"


def test_idempotent_small_avif_skipped(tmp_path):
    imgs = tmp_path / "images"
    imgs.mkdir()
    _write_avif(imgs / "dddd000000000004.avif", 300, 400)
    before = (imgs / "dddd000000000004.avif").read_bytes()
    items = _items_file(tmp_path, [
        {"slug": "w", "images": [{"url": "u", "local": "dddd000000000004.avif"}]},
    ])
    res = _run(imgs, items, tmp_path / "cp.json")
    assert res["counter"].get("skip") == 1
    assert (imgs / "dddd000000000004.avif").read_bytes() == before  # intacto
    assert not (imgs / "_originals").exists()


def test_placeholder_untouched(tmp_path):
    imgs = tmp_path / "images"
    imgs.mkdir()
    _write_solid_png(imgs / "eeee000000000005.png")  # blanco → placeholder solid
    before = (imgs / "eeee000000000005.png").read_bytes()
    items = _items_file(tmp_path, [
        {"slug": "p", "images": [{"url": "u", "local": "eeee000000000005.png"}]},
    ])
    res = _run(imgs, items, tmp_path / "cp.json")
    assert res["counter"].get("skip") == 1
    assert (imgs / "eeee000000000005.png").read_bytes() == before
    assert not (imgs / "eeee000000000005.avif").exists()


def test_large_avif_resized_in_place(tmp_path):
    imgs = tmp_path / "images"
    imgs.mkdir()
    _write_avif(imgs / "ffff000000000006.avif", 2200, 2200)
    items = _items_file(tmp_path, [
        {"slug": "q", "images": [{"url": "u", "local": "ffff000000000006.avif"}]},
    ])
    res = _run(imgs, items, tmp_path / "cp.json")
    assert res["counter"].get("resized") == 1
    assert max(_dims(imgs / "ffff000000000006.avif")) <= 1600
    # mismo nombre → items.jsonl no cambia
    row = json.loads(items.read_text().strip())
    assert row["images"][0]["local"] == "ffff000000000006.avif"


def test_delete_originals_mode(tmp_path):
    imgs = tmp_path / "images"
    imgs.mkdir()
    _write_png(imgs / "0000000000000007.png", 1800, 2400)
    items = _items_file(tmp_path, [
        {"slug": "d", "images": [{"url": "u", "local": "0000000000000007.png"}]},
    ])
    _run(imgs, items, tmp_path / "cp.json", originals_mode="delete")
    assert (imgs / "0000000000000007.avif").is_file()
    assert not (imgs / "0000000000000007.png").exists()
    assert not (imgs / "_originals").exists()  # borrado, no archivado


def test_dry_run_writes_nothing(tmp_path):
    imgs = tmp_path / "images"
    imgs.mkdir()
    _write_png(imgs / "1111000000000008.png", 2000, 3000)
    items_before = _items_file(tmp_path, [
        {"slug": "dr", "images": [{"url": "u", "local": "1111000000000008.png"}]},
    ])
    snapshot = items_before.read_text()
    res = _run(imgs, items_before, tmp_path / "cp.json", dry_run=True)
    assert not (imgs / "1111000000000008.avif").exists()  # nada escrito
    assert (imgs / "1111000000000008.png").is_file()       # original intacto
    assert items_before.read_text() == snapshot            # items.jsonl intacto
    assert res["renames"] == 1                              # pero detectó el cambio
