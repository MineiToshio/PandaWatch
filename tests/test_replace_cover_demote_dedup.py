"""Tests del fix a la gotcha #164 (2026-09-01): `_apply_improvement()`
promovía una imagen a `images[0]` sin revisar si esa misma imagen YA vivía en
la galería del propio item (`images[1:]`) — patrón "cola de promoción local"
(ver docs/reference/images.md § OLA 3 punto 3). El resultado quedaba
DUPLICADO: una vez en `images[0]` (portada nueva) y otra vez en su posición
ORIGINAL de galería (mismo `url`/`local`).

El fix vive en UN solo lugar (`_apply_improvement()`), así que cubre las tres
acciones que la llaman con el mismo mecanismo: `replace_cover_demote`,
`replace_cover` y `replace_and_add`. Cubre:

  1. `_apply_improvement()` a nivel unitario: dedupea cuando hay duplicado,
     no toca nada cuando no lo hay, es idempotente, y usa la MISMA clave
     canónica de dedup que el resto del pipeline (`manga_watch._img_stem`,
     robusta a sufijos de thumb/query params — no comparación de string pelada).
  2. `apply_preview()` end-to-end para `replace_cover_demote` (el patrón real
     de la ola de imágenes): con duplicado y sin duplicado.
  3. `apply_preview()` end-to-end para `replace_cover` normal (sin regresión).

Sigue el estilo de test_remove_image_action.py / test_apply_preview.py.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "retrofit"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_better_covers as fbc  # noqa: E402

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def _make_img(path: Path, size=(100, 150), color=(200, 30, 30)) -> None:
    img = Image.new("RGB", size, color)
    img.save(path, "JPEG")


# ---------------------------------------------------------------------------
# 1. _apply_improvement() — unitario, sin tocar disco
# ---------------------------------------------------------------------------

def test_apply_improvement_dedupes_preexisting_gallery_duplicate():
    """La candidata promovida YA vivía en images[1:] (patrón cola de promoción
    local) — antes del fix quedaba duplicada; ahora la copia vieja se remueve."""
    item = {
        "slug": "dup-item",
        "images": [
            {"url": "http://x/cover.jpg", "local": "cover.jpg", "kind": "gallery"},
            {"url": "http://x/photo2.jpg", "local": "photo2.jpg", "kind": "gallery",
             "description": "arte interior"},
        ],
    }
    fbc._apply_improvement(item, "http://x/photo2.jpg", "photo2.jpg")

    urls = [im["url"] for im in item["images"]]
    # Sólo una copia de photo2.jpg — ya no está duplicada.
    assert urls.count("http://x/photo2.jpg") == 1
    assert urls == ["http://x/photo2.jpg"]
    # El description más específico de la entry original se preserva en la
    # portada sobreviviente (no se pierde al pisar images[0]).
    assert item["images"][0]["description"] == "arte interior"


def test_apply_improvement_dedup_uses_canonical_img_stem_key():
    """La clave de dedup es la MISMA que usa el resto del pipeline
    (`manga_watch._img_stem`): normaliza sufijos de thumb CDN y query params
    irrelevantes, no una comparación de string pelada."""
    item = {
        "slug": "dup-item",
        "images": [
            {"url": "http://x/cover.jpg", "local": "cover.jpg", "kind": "gallery"},
            # Mismo archivo que la candidata, pero como thumb Shopify con
            # query param de versión — _img_stem las normaliza al mismo stem.
            {"url": "http://cdn.shopify.com/photo2_grande.jpg?v=123",
             "local": "photo2.jpg", "kind": "gallery"},
        ],
    }
    fbc._apply_improvement(item, "http://cdn.shopify.com/photo2.jpg", "photo2.jpg")

    urls = [im["url"] for im in item["images"]]
    assert len(urls) == 1
    assert urls == ["http://cdn.shopify.com/photo2.jpg"]


def test_apply_improvement_no_duplicate_is_a_noop_on_gallery():
    """Regresión: si la candidata NUNCA vivió en la galería (caso normal, web
    search), la galería no se toca — sólo se pisa images[0]."""
    item = {
        "slug": "fresh-item",
        "images": [
            {"url": "http://x/cover.jpg", "local": "cover.jpg", "kind": "gallery"},
            {"url": "http://x/unrelated.jpg", "local": "unrelated.jpg", "kind": "gallery"},
        ],
    }
    fbc._apply_improvement(item, "http://y/new-hires.jpg", "new.jpg")

    urls = [im["url"] for im in item["images"]]
    assert urls == ["http://y/new-hires.jpg", "http://x/unrelated.jpg"]


def test_apply_improvement_is_idempotent():
    """Llamar dos veces con los MISMOS argumentos no debe volver a duplicar
    nada — la segunda pasada ya no encuentra duplicado (se removió en la 1ª)."""
    item = {
        "slug": "dup-item",
        "images": [
            {"url": "http://x/cover.jpg", "local": "cover.jpg", "kind": "gallery"},
            {"url": "http://x/photo2.jpg", "local": "photo2.jpg", "kind": "gallery"},
        ],
    }
    fbc._apply_improvement(item, "http://x/photo2.jpg", "photo2.jpg")
    first_pass = json.loads(json.dumps(item))

    fbc._apply_improvement(item, "http://x/photo2.jpg", "photo2.jpg")

    assert item == first_pass
    urls = [im["url"] for im in item["images"]]
    assert urls.count("http://x/photo2.jpg") == 1


# ---------------------------------------------------------------------------
# 2. apply_preview() — replace_cover_demote end-to-end
# ---------------------------------------------------------------------------

@pytest.fixture()
def demote_setup(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_img(images_dir / "cover.jpg", (200, 300))     # portada actual, chica
    _make_img(images_dir / "photo2.jpg", (400, 600))    # candidata: YA vive en la galería

    item = {
        "slug": "demote-item",
        "title": "Demote Item",
        "images": [
            {"url": "http://x/cover.jpg", "local": "cover.jpg", "kind": "gallery"},
            {"url": "http://x/photo2.jpg", "local": "photo2.jpg", "kind": "gallery",
             "description": "arte interior"},
        ],
    }
    items_path = tmp_path / "items.jsonl"
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    preview = [{
        "slug": "demote-item",
        "title": "Demote Item",
        "old_url": "http://x/cover.jpg",
        "old_image": "cover.jpg",
        "old_pixels": 60000,
        "current_images": [
            {"url": "http://x/cover.jpg", "local": "cover.jpg", "kind": "gallery", "is_cover": True},
            {"url": "http://x/photo2.jpg", "local": "photo2.jpg", "kind": "gallery", "is_cover": False},
        ],
        "candidates": [{
            "action": "replace_cover_demote", "target": "",
            "new_url": "http://x/photo2.jpg", "new_image": "photo2.jpg",
            "new_pixels": 240000, "kind": "gallery", "status": "pending",
            "confidence": "high",
        }],
    }]
    preview_path = tmp_path / "cover_preview.json"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")
    monkeypatch.setattr(fbc, "_PREVIEW_PATH", preview_path)
    monkeypatch.setattr(fbc, "REJECTION_LEDGER_PATH", tmp_path / "cover_rejections.jsonl")
    return items_path, images_dir, preview_path


def test_approved_replace_cover_demote_dedupes_gallery(demote_setup):
    """El caso real de la ola de imágenes (OLA 3): la candidata aprobada YA
    vivía en la galería del item. Antes del fix quedaba duplicada; ahora la
    galería final tiene EXACTAMENTE 2 entries (la nueva portada + la vieja
    demovida), no 3."""
    items_path, images_dir, preview_path = demote_setup
    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    preview[0]["candidates"][0]["status"] = "approved"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")

    summary = fbc.apply_preview(items_path, images_dir)

    item_after = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    images = item_after["images"]
    urls = [im["url"] for im in images]

    # Ni rastro de duplicado: photo2.jpg aparece UNA sola vez.
    assert urls.count("http://x/photo2.jpg") == 1
    assert urls == ["http://x/photo2.jpg", "http://x/cover.jpg"]
    assert len(images) == 2

    # La nueva portada es photo2.jpg; description sobrevive el merge.
    assert images[0]["local"] == "photo2.jpg"
    assert images[0]["description"] == "arte interior"
    # La vieja portada quedó demovida como "extra", NO se borró.
    assert images[1]["kind"] == "extra"
    assert images[1]["local"] == "cover.jpg"

    assert summary["replaced"] == 1
    assert summary["galleried"] == 1
    # Regla dura de replace_cover_demote: la portada vieja se conserva
    # (nunca se borra su archivo del espejo).
    assert (images_dir / "cover.jpg").exists()
    assert (images_dir / "photo2.jpg").exists()


def test_approved_replace_cover_demote_without_duplicate_regression(demote_setup):
    """Regresión: candidata que NUNCA vivió en la galería del item (caso
    normal de búsqueda web) — el demote sigue funcionando como antes."""
    items_path, images_dir, preview_path = demote_setup
    _make_img(images_dir / "fresh.jpg", (500, 700))
    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    cand = preview[0]["candidates"][0]
    cand["status"] = "approved"
    cand["new_url"] = "http://y/fresh.jpg"
    cand["new_image"] = "fresh.jpg"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")

    fbc.apply_preview(items_path, images_dir)

    item_after = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    urls = [im["url"] for im in item_after["images"]]
    # Las 3 imágenes conviven: nueva portada + photo2 (intacta) + cover demovida.
    assert urls == ["http://y/fresh.jpg", "http://x/photo2.jpg", "http://x/cover.jpg"]


# ---------------------------------------------------------------------------
# 3. apply_preview() — replace_cover normal (sin regresión)
# ---------------------------------------------------------------------------

def test_approved_replace_cover_regression_no_duplicate_risk(tmp_path, monkeypatch):
    """`replace_cover` plano (sin demote), candidata fresca de búsqueda web:
    el fix no cambia el comportamiento — la portada vieja se descarta del
    espejo (huérfana), la galería del resto queda intacta."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_img(images_dir / "cover.jpg", (200, 300))
    _make_img(images_dir / "unrelated.jpg", (400, 600))
    _make_img(images_dir / "hires.jpg", (800, 1200))

    item = {
        "slug": "plain-item",
        "title": "Plain Item",
        "images": [
            {"url": "http://x/cover.jpg", "local": "cover.jpg", "kind": "gallery"},
            {"url": "http://x/unrelated.jpg", "local": "unrelated.jpg", "kind": "gallery"},
        ],
    }
    items_path = tmp_path / "items.jsonl"
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    preview = [{
        "slug": "plain-item",
        "title": "Plain Item",
        "old_url": "http://x/cover.jpg",
        "old_image": "cover.jpg",
        "old_pixels": 60000,
        "current_images": [
            {"url": "http://x/cover.jpg", "local": "cover.jpg", "kind": "gallery", "is_cover": True},
            {"url": "http://x/unrelated.jpg", "local": "unrelated.jpg", "kind": "gallery", "is_cover": False},
        ],
        "candidates": [{
            "action": "replace_cover", "target": "",
            "new_url": "http://y/hires.jpg", "new_image": "hires.jpg",
            "new_pixels": 960000, "kind": "gallery", "status": "approved",
            "confidence": "high",
        }],
    }]
    preview_path = tmp_path / "cover_preview.json"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")
    monkeypatch.setattr(fbc, "_PREVIEW_PATH", preview_path)
    monkeypatch.setattr(fbc, "REJECTION_LEDGER_PATH", tmp_path / "cover_rejections.jsonl")

    summary = fbc.apply_preview(items_path, images_dir)

    item_after = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    urls = [im["url"] for im in item_after["images"]]
    assert urls == ["http://y/hires.jpg", "http://x/unrelated.jpg"]
    assert summary["replaced"] == 1
    # Portada vieja huérfana → se borra del espejo.
    assert not (images_dir / "cover.jpg").exists()
    assert (images_dir / "unrelated.jpg").exists()
    assert (images_dir / "hires.jpg").exists()


def test_approved_replace_cover_when_new_url_already_in_gallery_dedupes(tmp_path, monkeypatch):
    """Caso borde de robustez: un `replace_cover` (sin demote explícito) que
    por la razón que sea promueve una URL que YA está en la galería del item
    tiene el MISMO riesgo de duplicar que `replace_cover_demote` — el fix
    vive en `_apply_improvement()` y cubre ambas acciones por igual."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_img(images_dir / "cover.jpg", (200, 300))
    _make_img(images_dir / "photo2.jpg", (400, 600))

    item = {
        "slug": "edge-item",
        "title": "Edge Item",
        "images": [
            {"url": "http://x/cover.jpg", "local": "cover.jpg", "kind": "gallery"},
            {"url": "http://x/photo2.jpg", "local": "photo2.jpg", "kind": "gallery"},
        ],
    }
    items_path = tmp_path / "items.jsonl"
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    preview = [{
        "slug": "edge-item",
        "title": "Edge Item",
        "old_url": "http://x/cover.jpg",
        "old_image": "cover.jpg",
        "old_pixels": 60000,
        "current_images": [
            {"url": "http://x/cover.jpg", "local": "cover.jpg", "kind": "gallery", "is_cover": True},
            {"url": "http://x/photo2.jpg", "local": "photo2.jpg", "kind": "gallery", "is_cover": False},
        ],
        "candidates": [{
            "action": "replace_cover", "target": "",
            "new_url": "http://x/photo2.jpg", "new_image": "photo2.jpg",
            "new_pixels": 240000, "kind": "gallery", "status": "approved",
            "confidence": "high",
        }],
    }]
    preview_path = tmp_path / "cover_preview.json"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")
    monkeypatch.setattr(fbc, "_PREVIEW_PATH", preview_path)
    monkeypatch.setattr(fbc, "REJECTION_LEDGER_PATH", tmp_path / "cover_rejections.jsonl")

    fbc.apply_preview(items_path, images_dir)

    item_after = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    urls = [im["url"] for im in item_after["images"]]
    assert urls.count("http://x/photo2.jpg") == 1
    assert urls == ["http://x/photo2.jpg"]
