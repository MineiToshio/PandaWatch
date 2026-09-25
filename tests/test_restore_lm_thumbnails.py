"""Tests para scripts/retrofit/restore_lm_thumbnails_20260902.py (gotcha #185).

Sin red — imágenes sintéticas PIL. Cubre los 3 caminos de recuperación
(disco / orphans / missing) y los guards que NUNCA deben reintroducir un
placeholder ni tocar items fuera de alcance (backup no-listadomanga, backup ya
placeholder, item que ya tiene portada).
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "retrofit"))

import image_store  # noqa: E402
import restore_lm_thumbnails_20260902 as rlt  # noqa: E402


def _png_bytes(w, h) -> bytes:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 5) % 256)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _solid_png(w, h) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (255, 255, 255)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _isolate_signatures(monkeypatch):
    monkeypatch.setattr(image_store, "_signatures_cache", {})


def _setup(tmp_path):
    items_path = tmp_path / "items.jsonl"
    backup_path = tmp_path / "backup.jsonl"
    images_dir = tmp_path / "images"
    orphans_dir = images_dir / "_orphans"
    images_dir.mkdir()
    orphans_dir.mkdir()
    return items_path, backup_path, images_dir, orphans_dir


def _write_jsonl(path: Path, items: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(it) for it in items) + "\n", encoding="utf-8")


def test_restores_from_orphans_and_moves_file_back(tmp_path):
    items_path, backup_path, images_dir, orphans_dir = _setup(tmp_path)
    (orphans_dir / "thumb.png").write_bytes(_png_bytes(208, 300))

    items = [{"slug": "a", "title": "A", "images": []}]
    backup = [{"slug": "a", "title": "A", "images": [
        {"url": "https://static.listadomanga.com/realhash.png", "local": "thumb.png", "kind": "gallery"},
    ]}]
    _write_jsonl(items_path, items)
    _write_jsonl(backup_path, backup)

    rlt.run(items_path, backup_path, dry_run=False)

    out = json.loads(items_path.read_text().splitlines()[0])
    assert out["images"] == [{
        "url": "https://static.listadomanga.com/realhash.png",
        "local": "thumb.png", "kind": "gallery", "description": "",
    }]
    assert (images_dir / "thumb.png").exists()
    assert not (orphans_dir / "thumb.png").exists()  # se movió, no se copió


def test_restores_from_disk_directly(tmp_path):
    items_path, backup_path, images_dir, orphans_dir = _setup(tmp_path)
    (images_dir / "thumb.png").write_bytes(_png_bytes(208, 300))

    items = [{"slug": "a", "title": "A", "images": []}]
    backup = [{"slug": "a", "title": "A", "images": [
        {"url": "https://static.listadomanga.com/realhash.png", "local": "thumb.png", "kind": "gallery"},
    ]}]
    _write_jsonl(items_path, items)
    _write_jsonl(backup_path, backup)

    rlt.run(items_path, backup_path, dry_run=False)

    out = json.loads(items_path.read_text().splitlines()[0])
    assert out["images"][0]["local"] == "thumb.png"


def test_missing_file_restores_url_only(tmp_path):
    items_path, backup_path, images_dir, orphans_dir = _setup(tmp_path)
    # ningún archivo en disco ni en orphans

    items = [{"slug": "a", "title": "A", "images": []}]
    backup = [{"slug": "a", "title": "A", "images": [
        {"url": "https://static.listadomanga.com/realhash.png", "local": "gone.png", "kind": "gallery"},
    ]}]
    _write_jsonl(items_path, items)
    _write_jsonl(backup_path, backup)

    rlt.run(items_path, backup_path, dry_run=False)

    out = json.loads(items_path.read_text().splitlines()[0])
    assert out["images"] == [{
        "url": "https://static.listadomanga.com/realhash.png",
        "local": "", "kind": "gallery", "description": "",
    }]


def test_never_restores_known_placeholder(tmp_path):
    items_path, backup_path, images_dir, orphans_dir = _setup(tmp_path)
    known_hash = next(iter(image_store.KNOWN_PLACEHOLDER_URL_STEMS))
    placeholder_url = f"https://static.listadomanga.com/{known_hash}.png"

    items = [{"slug": "a", "title": "A", "images": []}]
    backup = [{"slug": "a", "title": "A", "images": [
        {"url": placeholder_url, "local": "censored.png", "kind": "gallery"},
    ]}]
    _write_jsonl(items_path, items)
    _write_jsonl(backup_path, backup)

    rlt.run(items_path, backup_path, dry_run=False)

    out = json.loads(items_path.read_text().splitlines()[0])
    assert out["images"] == []  # correctamente vacío, no se toca


def test_never_restores_when_orphan_file_is_actually_a_placeholder(tmp_path):
    """Defensa en profundidad: aunque el backup no lo tenía fichado como placeholder
    conocido, si el archivo recuperado en _orphans/ resulta estructuralmente
    basura al re-verificar, NO se restaura."""
    items_path, backup_path, images_dir, orphans_dir = _setup(tmp_path)
    (orphans_dir / "white.png").write_bytes(_solid_png(300, 450))

    items = [{"slug": "a", "title": "A", "images": []}]
    backup = [{"slug": "a", "title": "A", "images": [
        {"url": "https://static.listadomanga.com/unregisteredplaceholder.png", "local": "white.png", "kind": "gallery"},
    ]}]
    _write_jsonl(items_path, items)
    _write_jsonl(backup_path, backup)

    rlt.run(items_path, backup_path, dry_run=False)

    out = json.loads(items_path.read_text().splitlines()[0])
    assert out["images"] == []
    assert (orphans_dir / "white.png").exists()  # no se movió


def test_skips_items_that_already_have_a_cover(tmp_path):
    items_path, backup_path, images_dir, orphans_dir = _setup(tmp_path)
    items = [{"slug": "a", "title": "A", "images": [
        {"url": "http://x/existing.png", "local": "existing.png", "kind": "gallery"},
    ]}]
    backup = [{"slug": "a", "title": "A", "images": [
        {"url": "https://static.listadomanga.com/realhash.png", "local": "thumb.png", "kind": "gallery"},
    ]}]
    _write_jsonl(items_path, items)
    _write_jsonl(backup_path, backup)

    rlt.run(items_path, backup_path, dry_run=False)

    out = json.loads(items_path.read_text().splitlines()[0])
    assert out["images"][0]["local"] == "existing.png"  # intacto


def test_skips_non_listadomanga_source_out_of_scope(tmp_path):
    items_path, backup_path, images_dir, orphans_dir = _setup(tmp_path)
    (orphans_dir / "amazon.png").write_bytes(_png_bytes(300, 450))
    items = [{"slug": "a", "title": "A", "images": []}]
    backup = [{"slug": "a", "title": "A", "images": [
        {"url": "https://m.media-amazon.com/images/I/abc.jpg", "local": "amazon.png", "kind": "gallery"},
    ]}]
    _write_jsonl(items_path, items)
    _write_jsonl(backup_path, backup)

    rlt.run(items_path, backup_path, dry_run=False)

    out = json.loads(items_path.read_text().splitlines()[0])
    assert out["images"] == []  # fuera del alcance de esta reparación puntual


def test_dry_run_writes_nothing_and_does_not_move_files(tmp_path):
    items_path, backup_path, images_dir, orphans_dir = _setup(tmp_path)
    (orphans_dir / "thumb.png").write_bytes(_png_bytes(208, 300))
    items = [{"slug": "a", "title": "A", "images": []}]
    backup = [{"slug": "a", "title": "A", "images": [
        {"url": "https://static.listadomanga.com/realhash.png", "local": "thumb.png", "kind": "gallery"},
    ]}]
    _write_jsonl(items_path, items)
    _write_jsonl(backup_path, backup)
    raw = items_path.read_text()

    rlt.run(items_path, backup_path, dry_run=True)

    assert items_path.read_text() == raw
    assert (orphans_dir / "thumb.png").exists()
    assert not (images_dir / "thumb.png").exists()


def test_idempotent_second_run_is_a_noop(tmp_path):
    items_path, backup_path, images_dir, orphans_dir = _setup(tmp_path)
    (orphans_dir / "thumb.png").write_bytes(_png_bytes(208, 300))
    items = [{"slug": "a", "title": "A", "images": []}]
    backup = [{"slug": "a", "title": "A", "images": [
        {"url": "https://static.listadomanga.com/realhash.png", "local": "thumb.png", "kind": "gallery"},
    ]}]
    _write_jsonl(items_path, items)
    _write_jsonl(backup_path, backup)

    rlt.run(items_path, backup_path, dry_run=False)
    first = items_path.read_text()
    rlt.run(items_path, backup_path, dry_run=False)  # ya tiene portada — nada que hacer
    assert items_path.read_text() == first
