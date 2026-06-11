"""Tests de sync_preview() — sincronización de cover_preview.json con el catálogo.

Verifica las 6 reglas de poda/eliminación de sync_preview():
  1. Cover ya ≥90k px → candidata pending replace_cover podada; si queda
     sin candidatas, la entry se elimina.
  2. Cover aún <90k px → candidata pending se conserva.
  3. Candidata approved se conserva AUNQUE el cover ya sea ≥90k.
  4. current_images/old_pixels se refrescan al estado real del item.
  5. Slug inexistente → entry eliminada.
  6. replace_image cuyo target ya no está en la galería → podada.
"""

import json
import sys
from pathlib import Path

import pytest

# Agregar scripts/retrofit/ y scripts/ al sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "retrofit"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from sync_cover_preview import sync_preview, LOW_QUALITY_PX  # noqa: E402

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_img(path: Path, size=(100, 150), color=(200, 30, 30)) -> None:
    """Crea una imagen JPEG sintética en `path`."""
    img = Image.new("RGB", size, color)
    img.save(path, "JPEG")


def _make_hires_img(path: Path) -> None:
    """Crea imagen ≥90k px (350×260 = 91000 px)."""
    _make_img(path, size=(350, 260))


def _make_lores_img(path: Path) -> None:
    """Crea imagen <90k px (100×150 = 15000 px)."""
    _make_img(path, size=(100, 150))


def _item(slug: str, images: list[dict] | None = None) -> dict:
    """Construye un dict mínimo de item.jsonl."""
    return {
        "slug": slug,
        "title": f"Test {slug}",
        "images": images or [],
    }


def _entry(slug: str, candidates: list[dict],
           old_url: str = "http://x/old.jpg",
           old_image: str = "old.jpg",
           old_pixels: int = 15_000) -> dict:
    """Construye una entry mínima de cover_preview.json."""
    return {
        "slug": slug,
        "title": f"Test {slug}",
        "old_url": old_url,
        "old_image": old_image,
        "old_pixels": old_pixels,
        "current_images": [{"url": old_url, "local": old_image,
                             "kind": "gallery", "is_cover": True}],
        "candidates": candidates,
    }


def _cand(action: str = "replace_cover",
          status: str = "pending",
          new_url: str = "http://x/new.jpg",
          new_image: str = "new.jpg",
          target: str = "") -> dict:
    """Construye un dict de candidata."""
    return {
        "action": action,
        "status": status,
        "new_url": new_url,
        "new_image": new_image,
        "new_pixels": 200_000,
        "target": target,
        "kind": "gallery",
        "confidence": "low",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cover_hires_pending_pruned_entry_dropped(tmp_path):
    """Regla 1: cover ya ≥90k px → candidata pending replace_cover podada.
    Como queda sin candidatas, la entry se elimina (dropped_empty)."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    cover_file = "cover_hires.jpg"
    _make_hires_img(images_dir / cover_file)

    item = _item("my-slug", images=[
        {"url": "http://x/cover.jpg", "local": cover_file, "kind": "gallery"}
    ])
    items_by_slug = {"my-slug": item}

    entry = _entry("my-slug", candidates=[_cand("replace_cover")])
    synced, stats = sync_preview([entry], items_by_slug, images_dir)

    assert synced == []
    assert stats["pruned_cover_ok"] == 1
    assert stats["dropped_empty"] == 1
    assert stats["dropped_missing_item"] == 0


def test_cover_lores_pending_kept(tmp_path):
    """Regla 2: cover aún <90k px → candidata pending se conserva."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    cover_file = "cover_lores.jpg"
    _make_lores_img(images_dir / cover_file)

    item = _item("slug-lo", images=[
        {"url": "http://x/cover.jpg", "local": cover_file, "kind": "gallery"}
    ])
    items_by_slug = {"slug-lo": item}

    entry = _entry("slug-lo", candidates=[_cand("replace_cover")])
    synced, stats = sync_preview([entry], items_by_slug, images_dir)

    assert len(synced) == 1
    assert len(synced[0]["candidates"]) == 1
    assert synced[0]["candidates"][0]["status"] == "pending"
    assert stats["pruned_cover_ok"] == 0
    assert stats["dropped_empty"] == 0


def test_approved_kept_even_if_cover_hires(tmp_path):
    """Regla 3: candidata approved se conserva AUNQUE el cover ya sea ≥90k.
    Las decisiones del owner (approved/rejected) son intocables."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    cover_file = "cover_hires2.jpg"
    _make_hires_img(images_dir / cover_file)

    item = _item("slug-ap", images=[
        {"url": "http://x/cover.jpg", "local": cover_file, "kind": "gallery"}
    ])
    items_by_slug = {"slug-ap": item}

    approved = _cand("replace_cover", status="approved")
    pending = _cand("replace_cover", status="pending",
                    new_url="http://x/pending.jpg", new_image="pending.jpg")
    entry = _entry("slug-ap", candidates=[approved, pending])
    synced, stats = sync_preview([entry], items_by_slug, images_dir)

    # La approved se conserva; la pending se poda por cover ok
    assert len(synced) == 1
    cands = synced[0]["candidates"]
    assert len(cands) == 1
    assert cands[0]["status"] == "approved"
    assert stats["pruned_cover_ok"] == 1


def test_state_refresh(tmp_path):
    """Regla 4: current_images y old_pixels se refrescan al estado real del item."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    new_cover_file = "new_cover.jpg"
    _make_lores_img(images_dir / new_cover_file)  # 15000 px
    gallery_file = "gallery.jpg"
    _make_hires_img(images_dir / gallery_file)  # 91000 px

    # El catálogo evolucionó: ahora tiene 2 imágenes con new_cover como portada
    item = _item("slug-ref", images=[
        {"url": "http://x/new.jpg", "local": new_cover_file, "kind": "gallery"},
        {"url": "http://x/gallery.jpg", "local": gallery_file, "kind": "gallery"},
    ])
    items_by_slug = {"slug-ref": item}

    # La entry tiene datos congelados del estado anterior
    entry = _entry("slug-ref",
                   candidates=[_cand("replace_cover", new_url="http://x/better.jpg")],
                   old_url="http://x/OLD_STALE.jpg",
                   old_image="stale.jpg",
                   old_pixels=999)
    synced, _ = sync_preview([entry], items_by_slug, images_dir)

    assert len(synced) == 1
    e = synced[0]
    # old_url/old_image refrescan desde images[0] del item actual
    assert e["old_url"] == "http://x/new.jpg"
    assert e["old_image"] == new_cover_file
    # old_pixels recalculado con PIL
    assert e["old_pixels"] == 100 * 150  # 15000 px (size de _make_lores_img)
    # current_images refleja images[] del item actual
    assert len(e["current_images"]) == 2
    assert e["current_images"][0]["is_cover"] is True
    assert e["current_images"][1]["is_cover"] is False


def test_missing_slug_dropped(tmp_path):
    """Regla 5: slug inexistente en el catálogo → entry eliminada."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()

    items_by_slug = {}  # vacío — slug no existe
    entry = _entry("slug-gone", candidates=[_cand("replace_cover")])
    synced, stats = sync_preview([entry], items_by_slug, images_dir)

    assert synced == []
    assert stats["dropped_missing_item"] == 1
    assert stats["dropped_empty"] == 0


def test_replace_image_target_gone_pruned(tmp_path):
    """Regla 6: replace_image cuyo target ya no está en la galería → podada."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    cover_file = "cover_lores.jpg"
    _make_lores_img(images_dir / cover_file)

    # El item ya no tiene la foto target en su galería
    item = _item("slug-tg", images=[
        {"url": "http://x/cover.jpg", "local": cover_file, "kind": "gallery"},
    ])
    items_by_slug = {"slug-tg": item}

    gone_target = "http://x/old_gallery_photo.jpg"  # no está en item.images
    cand = _cand("replace_image", target=gone_target)
    entry = _entry("slug-tg", candidates=[cand])
    synced, stats = sync_preview([entry], items_by_slug, images_dir)

    assert synced == []
    assert stats["pruned_target_gone"] == 1
    assert stats["dropped_empty"] == 1


def test_replace_image_target_hires_pruned(tmp_path):
    """replace_image cuyo target YA está en la galería y es ≥90k px → podada."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    cover_file = "cover_lores.jpg"
    _make_lores_img(images_dir / cover_file)
    gallery_file = "gallery_hires.jpg"
    _make_hires_img(images_dir / gallery_file)

    gallery_url = "http://x/gallery.jpg"
    item = _item("slug-thi", images=[
        {"url": "http://x/cover.jpg", "local": cover_file, "kind": "gallery"},
        {"url": gallery_url, "local": gallery_file, "kind": "gallery"},
    ])
    items_by_slug = {"slug-thi": item}

    cand = _cand("replace_image", target=gallery_url)
    entry = _entry("slug-thi", candidates=[cand])
    synced, stats = sync_preview([entry], items_by_slug, images_dir)

    assert synced == []
    assert stats["pruned_target_ok"] == 1
    assert stats["dropped_empty"] == 1


def test_already_current_pruned(tmp_path):
    """Candidata pending cuya new_url ya es la portada actual → podada."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    cover_file = "cover_lores.jpg"
    _make_lores_img(images_dir / cover_file)

    current_cover_url = "http://x/cover.jpg"
    item = _item("slug-ac", images=[
        {"url": current_cover_url, "local": cover_file, "kind": "gallery"},
    ])
    items_by_slug = {"slug-ac": item}

    # La candidata apunta a la misma URL que ya es la portada
    cand = _cand("replace_cover", new_url=current_cover_url)
    entry = _entry("slug-ac", candidates=[cand])
    synced, stats = sync_preview([entry], items_by_slug, images_dir)

    assert synced == []
    assert stats["pruned_already_current"] == 1


def test_multiple_entries_mixed(tmp_path):
    """Varios entries con distintos resultados: algunos se conservan, otros no."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    lo = "lores.jpg"; hi = "hires.jpg"
    _make_lores_img(images_dir / lo)
    _make_hires_img(images_dir / hi)

    items_by_slug = {
        "keep-me": _item("keep-me", images=[
            {"url": "http://x/lo.jpg", "local": lo, "kind": "gallery"}
        ]),
        # "gone-slug" no está → dropped
    }

    entries = [
        _entry("keep-me", candidates=[_cand("replace_cover")]),
        _entry("gone-slug", candidates=[_cand("replace_cover")]),
    ]
    synced, stats = sync_preview(entries, items_by_slug, images_dir)

    assert len(synced) == 1
    assert synced[0]["slug"] == "keep-me"
    assert stats["dropped_missing_item"] == 1
