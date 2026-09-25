"""Tests del gain guard de apply_preview (gotcha #182, Cierre Etapas 1-2,
2026-09-02): `apply_preview` aplicaba una candidata `approved` de
`replace_cover`/`replace_cover_demote`/`replace_and_add` sin re-validar
ganancia de píxeles contra la portada ACTUAL del item al momento de aplicar —
sólo confiaba en `old_pixels`, congelado en `cover_preview.json` al momento
de PLANEAR/aprobar. Si otro proceso (típicamente `upgrade_image_resolution.py`)
mejoraba la portada actual ENTRE la aprobación y el apply, la candidata
aprobada podía terminar siendo un DOWNGRADE real — caso confirmado en
producción: `travidebla-unknown-artbook-jp` (candidata de 508 200 px pisó una
portada que mientras tanto había subido a 1 020 000 px vía el patrón r10s.jp
de Rakuten), revertido a mano porque este guard no existía.

Fix: `_no_gain_at_apply()` re-lee la portada ACTUAL de disco (no el
`old_pixels` congelado) al momento mismo de aplicar. Si la candidata no
mejora, la candidata vuelve a "pending" con `invalid_reason="no_gain_at_apply"`
(mismo patrón que `remove_image`/`would_remove_cover`, gotcha #168) — excepto
si la portada ACTUAL es un placeholder o no existe, donde aplica igual.
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
    """Imagen con textura suficiente para NO matchear `placeholder_reason`
    ("solid:STD" — un color plano tiene std de luminancia ~0). Un degradé +
    un óvalo son suficiente entropía sin dejar de ser barato de generar."""
    w, h = size
    img = Image.new("RGB", size, color)
    px = img.load()
    for y in range(h):
        for x in range(w):
            r = (color[0] + x) % 256
            g = (color[1] + y) % 256
            b = (color[2] + x + y) % 256
            px[x, y] = (r, g, b)
    img.save(path, "JPEG")


def _make_solid_placeholder(path: Path, size=(100, 150)) -> None:
    """Imagen sólida (std de luminancia ~0) — matchea `placeholder_reason`
    ("solid:STD") independientemente de sus dimensiones/píxeles."""
    img = Image.new("RGB", size, (255, 255, 255))
    img.save(path, "JPEG")


def _setup(tmp_path, monkeypatch, *, current_size, candidate_size,
           current_is_placeholder=False, action="replace_cover"):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    if current_is_placeholder:
        _make_solid_placeholder(images_dir / "current_cover.jpg", current_size)
    else:
        _make_img(images_dir / "current_cover.jpg", current_size)
    _make_img(images_dir / "candidate.jpg", candidate_size, color=(30, 200, 30))

    item = {
        "slug": "test-item",
        "title": "Test",
        "images": [{"url": "http://x/current.jpg", "local": "current_cover.jpg", "kind": "gallery"}],
    }
    items_path = tmp_path / "items.jsonl"
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    cand = {
        "new_url": "http://x/candidate.jpg", "new_image": "candidate.jpg",
        # old_pixels/new_pixels FROZEN al momento de aprobar — a propósito
        # desalineados de los tamaños reales en disco arriba, para probar que
        # el guard re-lee el archivo ACTUAL en vez de confiar en esto.
        "new_pixels": 999999, "action": action, "target": "",
        "kind": "gallery", "status": "approved", "confidence": "high",
    }
    preview = [{
        "slug": "test-item",
        "title": "Test",
        "old_url": "http://x/current.jpg",
        "old_image": "current_cover.jpg",
        "old_pixels": 1,  # frozen, deliberadamente mentiroso
        "current_images": [{"url": "http://x/current.jpg", "local": "current_cover.jpg",
                            "kind": "gallery", "is_cover": True}],
        "candidates": [cand],
    }]
    preview_path = tmp_path / "cover_preview.json"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")
    monkeypatch.setattr(fbc, "_PREVIEW_PATH", preview_path)
    monkeypatch.setattr(fbc, "REJECTION_LEDGER_PATH", tmp_path / "cover_rejections.jsonl")
    return items_path, images_dir, preview_path


class TestGainGuardReplaceCover:
    def test_real_gain_applies(self, tmp_path, monkeypatch):
        """La candidata SÍ mejora píxeles reales respecto de la portada ACTUAL
        en disco → se aplica normalmente."""
        items_path, images_dir, preview_path = _setup(
            tmp_path, monkeypatch, current_size=(100, 150), candidate_size=(400, 600),
        )
        result = fbc.apply_preview(items_path, images_dir)
        assert result["replaced"] == 1
        assert result["skipped_no_gain_at_apply"] == 0

        item = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
        assert item["images"][0]["local"] == "candidate.jpg"

    def test_no_gain_reverts_to_pending_with_invalid_reason(self, tmp_path, monkeypatch):
        """La portada ACTUAL (releída de disco) YA es mejor o igual que la
        candidata — p.ej. otro proceso la mejoró entre la aprobación y este
        apply. La candidata NO se aplica: vuelve a pending con
        invalid_reason="no_gain_at_apply", se cuenta en el resumen, y el
        item conserva su portada actual intacta."""
        items_path, images_dir, preview_path = _setup(
            tmp_path, monkeypatch, current_size=(850, 1200), candidate_size=(600, 847),
        )
        result = fbc.apply_preview(items_path, images_dir)
        assert result["replaced"] == 0
        assert result["skipped_no_gain_at_apply"] == 1

        # Portada del item intacta (NO downgradeada).
        item = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
        assert item["images"][0]["local"] == "current_cover.jpg"

        # La candidata sigue en el preview, ahora pending con el invalid_reason.
        remaining = json.loads(preview_path.read_text(encoding="utf-8"))
        assert len(remaining) == 1
        cand = remaining[0]["candidates"][0]
        assert cand["status"] == "pending"
        assert cand["invalid_reason"] == "no_gain_at_apply"

    def test_current_cover_placeholder_applies_anyway(self, tmp_path, monkeypatch):
        """La portada ACTUAL es un placeholder (imagen sólida, std~0) aunque
        tenga MÁS píxeles nominales que la candidata — la excepción del guard
        aplica igual: cualquier imagen real gana contra un placeholder."""
        items_path, images_dir, preview_path = _setup(
            tmp_path, monkeypatch, current_size=(2000, 3000), candidate_size=(400, 600),
            current_is_placeholder=True,
        )
        result = fbc.apply_preview(items_path, images_dir)
        assert result["replaced"] == 1
        assert result["skipped_no_gain_at_apply"] == 0

        item = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
        assert item["images"][0]["local"] == "candidate.jpg"

    def test_no_current_cover_applies_anyway(self, tmp_path, monkeypatch):
        """Item sin portada previa (`local` vacío / archivo ausente) → nada
        que degradar, aplica siempre."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _make_img(images_dir / "candidate.jpg", (400, 600), color=(30, 200, 30))
        item = {
            "slug": "test-item", "title": "Test",
            "images": [{"url": "", "local": "", "kind": "gallery"}],
        }
        items_path = tmp_path / "items.jsonl"
        items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")
        preview = [{
            "slug": "test-item", "title": "Test",
            "old_url": "", "old_image": "", "old_pixels": 0,
            "current_images": [{"url": "", "local": "", "kind": "gallery", "is_cover": True}],
            "candidates": [{
                "new_url": "http://x/candidate.jpg", "new_image": "candidate.jpg",
                "new_pixels": 240000, "action": "replace_cover", "target": "",
                "kind": "gallery", "status": "approved", "confidence": "high",
            }],
        }]
        preview_path = tmp_path / "cover_preview.json"
        preview_path.write_text(json.dumps(preview), encoding="utf-8")
        monkeypatch.setattr(fbc, "_PREVIEW_PATH", preview_path)
        monkeypatch.setattr(fbc, "REJECTION_LEDGER_PATH", tmp_path / "cover_rejections.jsonl")

        result = fbc.apply_preview(items_path, images_dir)
        assert result["replaced"] == 1
        assert result["skipped_no_gain_at_apply"] == 0


class TestGainGuardReplaceCoverDemote:
    def test_no_gain_blocks_demote_too(self, tmp_path, monkeypatch):
        """El guard cubre replace_cover_demote (mismo mecanismo,
        `_apply_improvement` es el choke point) — no sólo replace_cover."""
        items_path, images_dir, preview_path = _setup(
            tmp_path, monkeypatch, current_size=(850, 1200), candidate_size=(600, 847),
            action="replace_cover_demote",
        )
        result = fbc.apply_preview(items_path, images_dir)
        assert result["replaced"] == 0
        assert result["skipped_no_gain_at_apply"] == 1
        item = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
        assert item["images"][0]["local"] == "current_cover.jpg"
        assert len(item["images"]) == 1  # no se demoteó nada a galería


class TestGainGuardReplaceAndAdd:
    def test_no_gain_blocks_replace_and_add_too(self, tmp_path, monkeypatch):
        items_path, images_dir, preview_path = _setup(
            tmp_path, monkeypatch, current_size=(850, 1200), candidate_size=(600, 847),
            action="replace_and_add",
        )
        result = fbc.apply_preview(items_path, images_dir)
        assert result["replaced"] == 0
        assert result["galleried"] == 0
        assert result["skipped_no_gain_at_apply"] == 1
        item = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
        assert len(item["images"]) == 1
        assert item["images"][0]["local"] == "current_cover.jpg"
