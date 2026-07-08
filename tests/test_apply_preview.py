"""Tests de apply_preview() — el camino "aplicar aprobadas" del panel
cover-preview. Regresión del bug 2026-06-11: una entry con candidata
aprobada + otra pendiente conservaba la aprobada en el JSON (la UI la
mostraba "pegada") y su old_image apuntaba a la portada ya reemplazada."""

import io
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


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_img(images_dir / "old_cover.jpg", (100, 150))
    _make_img(images_dir / "new_cover.jpg", (400, 600))
    _make_img(images_dir / "pending_cand.jpg", (300, 450))

    item = {
        "slug": "test-item",
        "title": "Test",
        "images": [{"url": "http://x/old.jpg", "local": "old_cover.jpg", "kind": "gallery"}],
    }
    items_path = tmp_path / "items.jsonl"
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    preview = [{
        "slug": "test-item",
        "title": "Test",
        "old_url": "http://x/old.jpg",
        "old_image": "old_cover.jpg",
        "old_pixels": 15000,
        "current_images": [{"url": "http://x/old.jpg", "local": "old_cover.jpg",
                            "kind": "gallery", "is_cover": True}],
        "candidates": [
            {"new_url": "http://x/new.jpg", "new_image": "new_cover.jpg",
             "new_pixels": 240000, "action": "replace_cover", "target": "",
             "kind": "gallery", "status": "approved", "confidence": "low"},
            {"new_url": "http://x/pending.jpg", "new_image": "pending_cand.jpg",
             "new_pixels": 135000, "action": "replace_cover", "target": "",
             "kind": "gallery", "status": "pending", "confidence": "low"},
        ],
    }]
    preview_path = tmp_path / "cover_preview.json"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")
    monkeypatch.setattr(fbc, "_PREVIEW_PATH", preview_path)
    monkeypatch.setattr(fbc, "REJECTION_LEDGER_PATH", tmp_path / "cover_rejections.jsonl")
    return items_path, images_dir, preview_path


def test_approved_applies_and_leaves_only_pending(setup, capsys):
    items_path, images_dir, preview_path = setup
    fbc.apply_preview(items_path, images_dir)

    # 1. El catálogo tiene la portada nueva.
    item = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    assert item["images"][0]["local"] == "new_cover.jpg"
    assert item["images"][0]["url"] == "http://x/new.jpg"

    # 2. La entry sigue (tiene una pendiente) pero SOLO con la pendiente:
    #    la aprobada ya aplicada no debe quedar "pegada" en la cola.
    remaining = json.loads(preview_path.read_text(encoding="utf-8"))
    assert len(remaining) == 1
    cands = remaining[0]["candidates"]
    assert len(cands) == 1
    assert cands[0]["status"] == "pending"
    assert cands[0]["new_image"] == "pending_cand.jpg"

    # 3. El estado "actual" de la entry se refrescó al post-apply: la
    #    comparación de la pendiente es contra la portada vigente.
    assert remaining[0]["old_image"] == "new_cover.jpg"
    assert remaining[0]["old_url"] == "http://x/new.jpg"
    assert remaining[0]["current_images"][0]["local"] == "new_cover.jpg"
    assert remaining[0]["current_images"][0]["is_cover"] is True


def test_all_decided_removes_entry_and_preview(setup):
    items_path, images_dir, preview_path = setup
    # Decidir también la segunda candidata (rechazada).
    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    preview[0]["candidates"][1]["status"] = "rejected"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")

    fbc.apply_preview(items_path, images_dir)

    # Todo decidido → el preview desaparece y la rechazada se limpia del disco.
    assert not preview_path.exists()
    assert not (images_dir / "pending_cand.jpg").exists()
    item = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    assert item["images"][0]["local"] == "new_cover.jpg"


def _missing_file_setup(tmp_path, monkeypatch):
    """Fixture común: candidata approved cuyo archivo local no existe en disco."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_img(images_dir / "old_cover.jpg", (100, 150))
    # new_cover.jpg intencionalmente AUSENTE del disco.

    item = {
        "slug": "missing-item",
        "title": "Missing Test",
        "images": [{"url": "http://x/old.jpg", "local": "old_cover.jpg", "kind": "gallery"}],
    }
    items_path = tmp_path / "items.jsonl"
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    preview = [{
        "slug": "missing-item",
        "title": "Missing Test",
        "old_url": "http://x/old.jpg",
        "old_image": "old_cover.jpg",
        "old_pixels": 15000,
        "current_images": [{"url": "http://x/old.jpg", "local": "old_cover.jpg",
                            "kind": "gallery", "is_cover": True}],
        "candidates": [
            {"new_url": "http://x/new.jpg", "new_image": "new_cover.jpg",
             "new_pixels": 240000, "action": "replace_cover", "target": "",
             "kind": "gallery", "status": "approved", "confidence": "low"},
        ],
    }]
    preview_path = tmp_path / "cover_preview.json"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")
    monkeypatch.setattr(fbc, "_PREVIEW_PATH", preview_path)
    monkeypatch.setattr(fbc, "REJECTION_LEDGER_PATH", tmp_path / "cover_rejections.jsonl")
    return items_path, images_dir, preview_path


def test_approved_missing_file_skipped_when_redownload_fails(tmp_path, monkeypatch):
    """Archivo local ausente Y la re-descarga falla → items.jsonl NO cambia,
    la candidata sigue en el preview (approved), summary trae
    skipped_missing_file=1."""
    items_path, images_dir, preview_path = _missing_file_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(fbc, "_fetch", lambda url, session, **kw: None)

    summary = fbc.apply_preview(items_path, images_dir)

    item_after = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    assert item_after["images"][0]["local"] == "old_cover.jpg"

    assert preview_path.exists()
    remaining = json.loads(preview_path.read_text(encoding="utf-8"))
    assert len(remaining) == 1
    cands = remaining[0]["candidates"]
    assert len(cands) == 1
    assert cands[0]["status"] == "approved"

    assert summary.get("skipped_missing_file") == 1
    assert summary.get("redownloaded") == 0


def test_approved_missing_file_self_heals(tmp_path, monkeypatch):
    """Archivo local ausente pero new_url responde → apply re-descarga el
    archivo y aplica la candidata (self-healing): items.jsonl actualizado,
    summary trae redownloaded=1 y skipped_missing_file=0."""
    items_path, images_dir, preview_path = _missing_file_setup(tmp_path, monkeypatch)

    buf = io.BytesIO()
    Image.new("RGB", (400, 600), (30, 60, 200)).save(buf, "JPEG")
    img_bytes = buf.getvalue()
    monkeypatch.setattr(fbc, "_fetch", lambda url, session, **kw: img_bytes)

    summary = fbc.apply_preview(items_path, images_dir)

    assert summary.get("redownloaded") == 1
    assert summary.get("skipped_missing_file") == 0

    # La portada se aplicó con el archivo re-descargado (nombre sha nuevo).
    item_after = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    new_local = item_after["images"][0]["local"]
    assert new_local and new_local != "old_cover.jpg"
    assert (images_dir / new_local).exists()
    # Todo decidido → el preview se limpió.
    assert not preview_path.exists()
