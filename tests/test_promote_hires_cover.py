"""Tests para scripts/retrofit/promote_hires_cover.py.

Todos son sin red — usan imágenes sintéticas PIL en tmp_path.

Casos:
  1. thumb + misma imagen grande → swap (images[k] pasa a images[0])
  2. thumb + imagen DISTINTA grande → no swap
  3. portada ya grande → no toca
  4. idempotencia: 2ª corrida no cambia nada
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

# Si otro test ya puso un stub de manga_watch sin backup_and_rotate
# (test_upgrade_image_resolution hace eso), lo quitamos para que
# promote_hires_cover pueda importar el módulo real.
import types as _types  # noqa: E402
_mw = sys.modules.get("manga_watch")
if _mw is not None and not hasattr(_mw, "backup_and_rotate"):
    del sys.modules["manga_watch"]

import promote_hires_cover as phc  # noqa: E402


# ── helpers de imágenes sintéticas ────────────────────────────────────────────

def _jpeg(im: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def _textured(w: int, h: int, seed: int = 0) -> Image.Image:
    """Portada con estructura suficiente para pasar el gate de entropía."""
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            r = ((x + seed) * 255) // max(w, 1)
            g = (y * 255) // max(h, 1)
            b = ((x + y + seed) * 255) // max(w + h, 1)
            px[x, y] = (r % 256, g % 256, b % 256)
    d = ImageDraw.Draw(im)
    d.ellipse([w // 5, h // 6, w * 4 // 5, h * 2 // 3], fill=(200, 30 + seed, 30))
    d.rectangle([w // 8, h * 3 // 4, w * 7 // 8, h * 15 // 16], fill=(20, 20 + seed, 120))
    return im


def _save(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def _make_item(
    images_dir: Path,
    *,
    thumb_w: int = 100,
    thumb_h: int = 150,
    hires_w: int = 400,
    hires_h: int = 600,
    same_image: bool = True,
) -> tuple[dict, str, str]:
    """
    Crea dos archivos de imagen en images_dir y devuelve
    (item_dict, thumb_filename, hires_filename).

    Si same_image=True, la hi-res es la misma portada escalada.
    Si same_image=False, la hi-res es una portada DISTINTA (seed diferente).
    """
    # Portada original (thumbnail)
    thumb_img = _textured(thumb_w, thumb_h, seed=0)
    thumb_bytes = _jpeg(thumb_img)
    thumb_fname = "thumb_cover.jpg"
    _save(images_dir / thumb_fname, thumb_bytes)

    # Candidata hi-res
    if same_image:
        # Misma imagen pero en alta resolución (reescalada desde el original)
        hires_img = thumb_img.resize((hires_w, hires_h), Image.LANCZOS)
    else:
        # Imagen completamente distinta
        hires_img = _textured(hires_w, hires_h, seed=99)
    hires_bytes = _jpeg(hires_img)
    hires_fname = "hires_cover.jpg"
    _save(images_dir / hires_fname, hires_bytes)

    item = {
        "title": "Test Manga Vol 1",
        "images": [
            {"url": "https://static.listadomanga.com/thumb.jpg",
             "local": thumb_fname, "kind": "gallery", "description": ""},
            {"url": "https://publisher.com/hires.jpg",
             "local": hires_fname, "kind": "gallery", "description": ""},
        ],
    }
    return item, thumb_fname, hires_fname


def _write_items(path: Path, items: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")


def _load_items(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


# ── test 1: thumb + misma imagen grande → swap ────────────────────────────────

def test_swap_when_hires_same_cover(tmp_path, monkeypatch):
    """images[0] es thumbnail (<90k px); images[1] es la misma en alta → swap."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    monkeypatch.setattr(phc, "IMAGES", images_dir)

    item, thumb_fname, hires_fname = _make_item(
        images_dir, thumb_w=100, thumb_h=150,
        hires_w=400, hires_h=600,
        same_image=True,
    )
    items_path = tmp_path / "items.jsonl"
    _write_items(items_path, [item])

    # Parcheamos backup_and_rotate para no necesitar la estructura real del repo.
    monkeypatch.setattr(phc, "backup_and_rotate", lambda *a, **kw: None)

    phc.run(items_path, dry_run=False)

    result = _load_items(items_path)
    assert len(result) == 1
    cover = result[0]["images"][0]
    # Después del swap, la portada debe ser la hi-res
    assert cover["local"] == hires_fname, (
        f"Esperaba hires_fname={hires_fname} como portada, "
        f"pero got '{cover['local']}'"
    )
    # El thumbnail debe seguir en la galería (no se eliminó)
    locals_in_gallery = [im["local"] for im in result[0]["images"]]
    assert thumb_fname in locals_in_gallery, "El thumbnail debe seguir en la galería"


# ── test 2: thumb + imagen DISTINTA grande → no swap ─────────────────────────

def test_no_swap_when_hires_different_cover(tmp_path, monkeypatch):
    """images[1] es DISTINTA a images[0] → no swap."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    monkeypatch.setattr(phc, "IMAGES", images_dir)

    item, thumb_fname, hires_fname = _make_item(
        images_dir, thumb_w=100, thumb_h=150,
        hires_w=400, hires_h=600,
        same_image=False,
    )
    items_path = tmp_path / "items.jsonl"
    _write_items(items_path, [item])
    monkeypatch.setattr(phc, "backup_and_rotate", lambda *a, **kw: None)

    phc.run(items_path, dry_run=False)

    result = _load_items(items_path)
    # Sin swap: images[0] sigue siendo el thumbnail original
    assert result[0]["images"][0]["local"] == thumb_fname


# ── test 3: portada ya grande → no toca ──────────────────────────────────────

def test_no_change_when_cover_already_large(tmp_path, monkeypatch):
    """images[0] ya es hi-res (≥90k px) → el script no lo toca."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    monkeypatch.setattr(phc, "IMAGES", images_dir)

    # Portada ya grande
    big_img = _textured(400, 600)
    big_bytes = _jpeg(big_img)
    big_fname = "big_cover.jpg"
    _save(images_dir / big_fname, big_bytes)

    # Galería con algo más pequeño (pero que no debería importar)
    small_img = _textured(100, 150, seed=5)
    small_bytes = _jpeg(small_img)
    small_fname = "small_extra.jpg"
    _save(images_dir / small_fname, small_bytes)

    item = {
        "title": "Test Manga Vol 2",
        "images": [
            {"url": "https://publisher.com/big.jpg",
             "local": big_fname, "kind": "gallery", "description": ""},
            {"url": "https://other.com/small.jpg",
             "local": small_fname, "kind": "gallery", "description": ""},
        ],
    }
    items_path = tmp_path / "items.jsonl"
    _write_items(items_path, [item])
    monkeypatch.setattr(phc, "backup_and_rotate", lambda *a, **kw: None)

    phc.run(items_path, dry_run=False)

    result = _load_items(items_path)
    assert result[0]["images"][0]["local"] == big_fname


# ── test 4: idempotencia ──────────────────────────────────────────────────────

def test_idempotence(tmp_path, monkeypatch):
    """Dos corridas seguidas producen el mismo items.jsonl."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    monkeypatch.setattr(phc, "IMAGES", images_dir)

    item, thumb_fname, hires_fname = _make_item(
        images_dir, thumb_w=100, thumb_h=150,
        hires_w=400, hires_h=600,
        same_image=True,
    )
    items_path = tmp_path / "items.jsonl"
    _write_items(items_path, [item])
    monkeypatch.setattr(phc, "backup_and_rotate", lambda *a, **kw: None)

    # Primera corrida → hace el swap
    phc.run(items_path, dry_run=False)
    after_first = items_path.read_text(encoding="utf-8")

    # Segunda corrida → no debe cambiar nada (la portada ya es hi-res)
    phc.run(items_path, dry_run=False)
    after_second = items_path.read_text(encoding="utf-8")

    assert after_first == after_second, (
        "La segunda corrida modificó items.jsonl: el script no es idempotente."
    )
