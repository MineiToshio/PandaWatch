"""Tests de la acción `remove_image` (OLA 2 dudosos, 2026-09-01) — elimina una
imagen de `images[]` SIN reemplazo. Cubre:

  1. _normalize_preview_entry(): defaults del contexto del par (keep_url/
     keep_local/remove_dims/keep_dims/same_dims).
  2. apply_preview(): approved → remueve del catálogo; guard de portada
     (target == images[0] → NUNCA se remueve, la candidata vuelve a pending).
  3. apply_preview(): rejected → no se aplica nada, la imagen sigue en la
     galería, se registra en el ledger de rechazos como siempre.
  4. sync_preview(): poda candidatas pending obsoletas (target ya no está en
     la galería, o target pasó a ser la portada vigente).

Sigue el estilo de test_apply_preview.py / test_sync_cover_preview.py.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "retrofit"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_better_covers as fbc  # noqa: E402
from sync_cover_preview import sync_preview  # noqa: E402

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def _make_img(path: Path, size=(100, 150), color=(200, 30, 30)) -> None:
    img = Image.new("RGB", size, color)
    img.save(path, "JPEG")


# ---------------------------------------------------------------------------
# 1. _normalize_preview_entry
# ---------------------------------------------------------------------------

def test_normalize_fills_pair_context_defaults():
    entry = {
        "slug": "some-item",
        "candidates": [
            {"action": "remove_image", "target": "http://x/loser.jpg",
             "new_url": "http://x/loser.jpg", "new_image": "loser.jpg",
             "status": "pending"},
        ],
    }
    normalized = fbc._normalize_preview_entry(entry)
    cand = normalized["candidates"][0]
    assert cand["action"] == "remove_image"
    # Defaults sembrados aunque la entry de entrada no los traiga.
    assert cand["keep_url"] == ""
    assert cand["keep_local"] == ""
    assert cand["remove_dims"] is None
    assert cand["keep_dims"] is None
    assert cand["same_dims"] is None


def test_normalize_preserves_pair_context_when_present():
    entry = {
        "slug": "some-item",
        "candidates": [
            {"action": "remove_image", "target": "http://x/loser.jpg",
             "new_url": "http://x/loser.jpg", "new_image": "loser.jpg",
             "status": "pending", "keep_url": "http://x/winner.jpg",
             "keep_local": "winner.jpg", "remove_dims": [300, 400],
             "keep_dims": [600, 800], "same_dims": False, "match_dist": 2},
        ],
    }
    cand = fbc._normalize_preview_entry(entry)["candidates"][0]
    assert cand["keep_url"] == "http://x/winner.jpg"
    assert cand["keep_local"] == "winner.jpg"
    assert cand["remove_dims"] == [300, 400]
    assert cand["keep_dims"] == [600, 800]
    assert cand["same_dims"] is False
    assert cand["match_dist"] == 2


# ---------------------------------------------------------------------------
# 2/3. apply_preview()
# ---------------------------------------------------------------------------

@pytest.fixture()
def remove_setup(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_img(images_dir / "cover.jpg", (400, 600))     # portada, NUNCA se toca
    _make_img(images_dir / "winner.jpg", (400, 600))    # gemela que se conserva
    _make_img(images_dir / "loser.jpg", (300, 400))     # candidata a remover

    item = {
        "slug": "dup-item",
        "title": "Dup Item",
        "images": [
            {"url": "http://x/cover.jpg", "local": "cover.jpg", "kind": "gallery"},
            {"url": "http://x/winner.jpg", "local": "winner.jpg", "kind": "gallery"},
            {"url": "http://x/loser.jpg", "local": "loser.jpg", "kind": "gallery"},
        ],
    }
    items_path = tmp_path / "items.jsonl"
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    preview = [{
        "slug": "dup-item",
        "title": "Dup Item",
        "old_url": "http://x/cover.jpg",
        "old_image": "cover.jpg",
        "old_pixels": 240000,
        "current_images": [
            {"url": "http://x/cover.jpg", "local": "cover.jpg", "kind": "gallery", "is_cover": True},
            {"url": "http://x/winner.jpg", "local": "winner.jpg", "kind": "gallery", "is_cover": False},
            {"url": "http://x/loser.jpg", "local": "loser.jpg", "kind": "gallery", "is_cover": False},
        ],
        "candidates": [{
            "action": "remove_image", "target": "http://x/loser.jpg",
            "new_url": "http://x/loser.jpg", "new_image": "loser.jpg",
            "new_pixels": 120000, "kind": "gallery", "status": "pending",
            "confidence": "low", "keep_url": "http://x/winner.jpg",
            "keep_local": "winner.jpg", "remove_dims": [300, 400],
            "keep_dims": [400, 600], "same_dims": False, "match_dist": 1,
        }],
    }]
    preview_path = tmp_path / "cover_preview.json"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")
    monkeypatch.setattr(fbc, "_PREVIEW_PATH", preview_path)
    monkeypatch.setattr(fbc, "REJECTION_LEDGER_PATH", tmp_path / "cover_rejections.jsonl")
    return items_path, images_dir, preview_path


def test_approved_remove_image_drops_from_gallery(remove_setup):
    items_path, images_dir, preview_path = remove_setup
    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    preview[0]["candidates"][0]["status"] = "approved"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")

    summary = fbc.apply_preview(items_path, images_dir)

    item_after = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    urls = [im["url"] for im in item_after["images"]]
    assert "http://x/loser.jpg" not in urls
    assert urls == ["http://x/cover.jpg", "http://x/winner.jpg"]
    # La portada NUNCA se toca por esta acción.
    assert item_after["images"][0]["local"] == "cover.jpg"

    assert summary["removed_no_replacement"] == 1
    assert summary["skipped_invalid_removal"] == 0
    # Todo decidido → el preview queda limpio.
    assert not preview_path.exists()
    # El archivo de la imagen removida, huérfano, se limpia del espejo.
    assert not (images_dir / "loser.jpg").exists()
    # El "gemelo" conservado y la portada siguen intactos en disco.
    assert (images_dir / "winner.jpg").exists()
    assert (images_dir / "cover.jpg").exists()


def test_rejected_remove_image_keeps_both_images(remove_setup):
    items_path, images_dir, preview_path = remove_setup
    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    preview[0]["candidates"][0]["status"] = "rejected"
    preview[0]["candidates"][0]["reject_reason"] = "otro_tomo"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")

    summary = fbc.apply_preview(items_path, images_dir)

    item_after = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    urls = [im["url"] for im in item_after["images"]]
    # Rechazar = conservar AMBAS imágenes tal cual estaban.
    assert urls == ["http://x/cover.jpg", "http://x/winner.jpg", "http://x/loser.jpg"]
    assert summary["removed_no_replacement"] == 0
    assert summary["reverted"] == 0  # nada se había aplicado; no hay "revertir"

    # El archivo de la imagen rechazada sigue vivo (todavía referenciado).
    assert (images_dir / "loser.jpg").exists()

    # Se registró en el ledger de rechazos como cualquier otra candidata.
    ledger_path = fbc.REJECTION_LEDGER_PATH
    assert ledger_path.exists()
    records = [json.loads(l) for l in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["action"] == "remove_image"
    assert records[0]["rejected_url"] == "http://x/loser.jpg"
    assert records[0]["reason"] == "otro_tomo"


def test_approved_remove_image_never_removes_cover(remove_setup):
    """Regla dura: si `target` ya es images[0] (la galería cambió desde que se
    armó la candidata — no debería pasar en la práctica), la remoción NO se
    aplica: la candidata vuelve a pending en vez de dejar el item sin portada
    ni aplicar un "removed" fantasma."""
    items_path, images_dir, preview_path = remove_setup
    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    cand = preview[0]["candidates"][0]
    cand["status"] = "approved"
    # Simula que "loser.jpg" pasó a ser la portada vigente entretanto.
    cand["target"] = "http://x/cover.jpg"
    cand["new_url"] = "http://x/cover.jpg"
    cand["new_image"] = "cover.jpg"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")

    summary = fbc.apply_preview(items_path, images_dir)

    item_after = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    urls = [im["url"] for im in item_after["images"]]
    # Las 3 imágenes siguen intactas — nada se removió.
    assert urls == ["http://x/cover.jpg", "http://x/winner.jpg", "http://x/loser.jpg"]
    assert summary["removed_no_replacement"] == 0
    assert summary["skipped_invalid_removal"] == 1

    # La candidata vuelve a pending (no queda "approved" fantasma) y sigue
    # en el preview para que el owner la vea.
    assert preview_path.exists()
    remaining = json.loads(preview_path.read_text(encoding="utf-8"))
    remaining_cand = remaining[0]["candidates"][0]
    assert remaining_cand["status"] == "pending"
    assert remaining_cand.get("invalid_reason") == "would_remove_cover"


def test_apply_preview_dry_run_does_not_touch_disk(remove_setup):
    items_path, images_dir, preview_path = remove_setup
    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    preview[0]["candidates"][0]["status"] = "approved"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")
    before_items = items_path.read_text(encoding="utf-8")
    before_preview = preview_path.read_text(encoding="utf-8")

    summary = fbc.apply_preview(items_path, images_dir, dry_run=True)

    assert summary["removed_no_replacement"] == 1  # reporta lo que HARÍA
    assert items_path.read_text(encoding="utf-8") == before_items
    assert preview_path.read_text(encoding="utf-8") == before_preview
    assert (images_dir / "loser.jpg").exists()


# ---------------------------------------------------------------------------
# 4. sync_preview() — poda de candidatas remove_image obsoletas
# ---------------------------------------------------------------------------

def _item(slug: str, images: list[dict]) -> dict:
    return {"slug": slug, "title": f"Test {slug}", "images": images}


def _remove_entry(slug: str, target: str, keep_url: str = "http://x/winner.jpg") -> dict:
    return {
        "slug": slug,
        "title": f"Test {slug}",
        "old_url": "http://x/cover.jpg",
        "old_image": "cover.jpg",
        "old_pixels": 240000,
        "current_images": [
            {"url": "http://x/cover.jpg", "local": "cover.jpg", "kind": "gallery", "is_cover": True},
            {"url": target, "local": "loser.jpg", "kind": "gallery", "is_cover": False},
        ],
        "candidates": [{
            "action": "remove_image", "target": target,
            "new_url": target, "new_image": "loser.jpg",
            "new_pixels": 120000, "kind": "gallery", "status": "pending",
            "confidence": "low", "keep_url": keep_url, "keep_local": "winner.jpg",
        }],
    }


def test_sync_prunes_remove_image_when_target_gone(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_img(images_dir / "cover.jpg", (400, 600))
    # El item YA no tiene "loser.jpg" en su galería (otra pasada la sacó).
    item = _item("dup-item", images=[
        {"url": "http://x/cover.jpg", "local": "cover.jpg", "kind": "gallery"},
    ])
    entry = _remove_entry("dup-item", target="http://x/loser.jpg")
    synced, stats = sync_preview([entry], {"dup-item": item}, images_dir)

    assert synced == []
    assert stats["pruned_remove_target_gone"] == 1
    assert stats["dropped_empty"] == 1


def test_sync_prunes_remove_image_when_target_became_cover(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_img(images_dir / "loser.jpg", (300, 400))
    # El item evolucionó: "loser.jpg" ahora es la PORTADA (images[0]) —
    # jamás se propone removerla, la candidata se poda por obsoleta.
    item = _item("dup-item", images=[
        {"url": "http://x/loser.jpg", "local": "loser.jpg", "kind": "gallery"},
    ])
    entry = _remove_entry("dup-item", target="http://x/loser.jpg")
    synced, stats = sync_preview([entry], {"dup-item": item}, images_dir)

    assert synced == []
    assert stats["pruned_remove_would_be_cover"] == 1
    assert stats["dropped_empty"] == 1


def test_sync_prunes_remove_image_when_keep_gone(tmp_path):
    """Gotcha #168 (2026-09-01): la gemela que se CONSERVABA (`keep_url`) ya
    no está en la galería del item (otra pasada la sacó, o ya fue promovida a
    portada con otra url) — sin su gemela, la candidata queda huérfana. Caso
    real: vanquished-queens-unknown-limited-jp-3 (`keep_url` apuntaba a
    9784798602233.jpg, ausente de `images[]`). Ninguna de las podas 3e/3f la
    alcanza (`target` SIGUE en la galería), así que sin este chequeo queda
    pending para siempre."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_img(images_dir / "cover.jpg", (400, 600))
    _make_img(images_dir / "loser.jpg", (300, 400))
    # El item tiene "loser.jpg" (target) pero YA NO tiene "winner.jpg" (keep_url).
    item = _item("dup-item", images=[
        {"url": "http://x/cover.jpg", "local": "cover.jpg", "kind": "gallery"},
        {"url": "http://x/loser.jpg", "local": "loser.jpg", "kind": "gallery"},
    ])
    entry = _remove_entry("dup-item", target="http://x/loser.jpg",
                           keep_url="http://x/winner.jpg")
    synced, stats = sync_preview([entry], {"dup-item": item}, images_dir)

    assert synced == []
    assert stats["pruned_remove_keep_gone"] == 1
    assert stats["dropped_empty"] == 1
    assert stats["pruned_remove_target_gone"] == 0
    assert stats["pruned_remove_would_be_cover"] == 0


def test_sync_keeps_remove_image_when_still_valid(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_img(images_dir / "cover.jpg", (400, 600))
    _make_img(images_dir / "loser.jpg", (300, 400))
    _make_img(images_dir / "winner.jpg", (400, 600))
    # AMBAS fotos del par siguen en la galería (target Y keep_url) — la
    # candidata está genuinamente vigente.
    item = _item("dup-item", images=[
        {"url": "http://x/cover.jpg", "local": "cover.jpg", "kind": "gallery"},
        {"url": "http://x/loser.jpg", "local": "loser.jpg", "kind": "gallery"},
        {"url": "http://x/winner.jpg", "local": "winner.jpg", "kind": "gallery"},
    ])
    entry = _remove_entry("dup-item", target="http://x/loser.jpg")
    synced, stats = sync_preview([entry], {"dup-item": item}, images_dir)

    assert len(synced) == 1
    assert len(synced[0]["candidates"]) == 1
    assert synced[0]["candidates"][0]["status"] == "pending"
    assert stats["pruned_remove_target_gone"] == 0
    assert stats["pruned_remove_would_be_cover"] == 0
    assert stats["pruned_remove_keep_gone"] == 0
