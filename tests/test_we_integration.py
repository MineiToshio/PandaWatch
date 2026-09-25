"""Integración we_plan → we_resolve → sc_validate → sc_flush (vía whakoom
"por página de edición" para portadas ES, owner 2026-09-02).

we_resolve.py NO valida imágenes ni escribe cover_preview.json — sólo decide
QUÉ URL de whakoom corresponde al tomo pedido. La validación de identidad/
calidad (descarga real + `_same_cover` + `_is_soft_image` + denylist) y el
encolado siguen siendo 100% de `sc_validate.py`/`sc_flush.py` (fuente única,
sin reimplementar — igual que /watch-search-covers). Este archivo prueba que
la salida de `we_resolve.resolve_candidates()` es un input válido y funcional
para `sc_validate.validate()` y que el resultado fluye a `sc_flush.flush()`.

Todos los tests son SIN red — monkeypatch de fbc._fetch.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

_ROOT = Path(__file__).resolve().parent.parent
for p in (_ROOT / "scripts", _ROOT / "scripts" / "retrofit"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import fetch_better_covers as fbc  # noqa: E402
import sc_validate                 # noqa: E402
import sc_flush                    # noqa: E402
import we_resolve                  # noqa: E402


def _jpeg(im: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def _textured_cover(w: int = 400, h: int = 600) -> Image.Image:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 255) // w, (y * 255) // h, ((x + y) * 255) // (w + h))
    d = ImageDraw.Draw(im)
    d.ellipse([w // 5, h // 6, w * 4 // 5, h * 2 // 3], fill=(200, 30, 30))
    d.rectangle([w // 8, h * 3 // 4, w * 7 // 8, h * 15 // 16], fill=(20, 20, 120))
    return im


def _item() -> dict:
    return {
        "slug": "dragon-ball-planeta-es-3",
        "title": "Dragon Ball 3",
        "title_original": "Dragon Ball 3",
        "series_display": "Dragon Ball",
        "series_key": "dragon-ball",
        "publisher": "Planeta Cómic",
        "country": "España",
        "volume": "3",
        "images": [],
    }


def _edition() -> dict:
    return {
        "edition_id": 1001,
        "edition_url": "https://www.whakoom.com/ediciones/1001/dragon-ball",
        "title": "Dragon Ball",
        "publisher": "Planeta Cómic",
        "language": "Spanish (Spain)",
        "total_tomos": 25,
        "other_editions": [],
        "volumes": [
            {"n": "1", "img_url": "https://i1.whakoom.com/small/aa/bb/hash1.jpg"},
            {"n": "3", "img_url": "https://i1.whakoom.com/small/aa/bb/hash3.jpg"},
        ],
    }


def test_resolved_candidate_flows_through_sc_validate(tmp_path, monkeypatch):
    """we_resolve resuelve una edición → sc_validate la valida (sin
    referencia real, gate débil) → verified False pero se acepta y trae
    new_image/new_url listos para sc_flush."""
    fetched_urls = []

    def mock_fetch(url, session, **kwargs):
        fetched_urls.append(url)
        return _jpeg(_textured_cover())

    monkeypatch.setattr(fbc, "_fetch", mock_fetch)

    item = _item()
    listado = {"coleccion_id": 1832, "total_tomos": 25}
    resolved = we_resolve.resolve_candidates(item, listado, [_edition()])
    assert resolved["resolved"] is True

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    data = {
        "item": item,
        "candidate_urls": resolved["candidate_urls"],
        "curr_px": 0,          # item sin imagen (típico target "sin imagen" de we_plan)
        "ref_image_local": "",
    }
    validated = sc_validate.validate(data, images_dir=images_dir)
    assert len(validated) == 1
    cand = validated[0]
    # sc_validate hizo el upgrade small→large (fuente única de esa reescritura).
    assert cand["new_url"] == "https://i1.whakoom.com/large/aa/bb/hash3.jpg"
    assert cand["verified"] is False  # sin referencia real → gate débil
    assert cand["confidence"] == "low"
    assert cand["status"] == "pending"
    assert (images_dir / cand["new_image"]).exists()
    # La URL de fetch efectivamente probada incluyó la variante /large/.
    assert any("/large/" in u for u in fetched_urls)


def test_resolved_candidate_flows_through_sc_flush(tmp_path, monkeypatch):
    def mock_fetch(url, session, **kwargs):
        return _jpeg(_textured_cover())

    monkeypatch.setattr(fbc, "_fetch", mock_fetch)

    item = _item()
    listado = {"coleccion_id": 1832, "total_tomos": 25}
    resolved = we_resolve.resolve_candidates(item, listado, [_edition()])

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    data = {"item": item, "candidate_urls": resolved["candidate_urls"], "curr_px": 0, "ref_image_local": ""}
    validated = sc_validate.validate(data, images_dir=images_dir)
    assert validated

    preview_path = tmp_path / "cover_preview.json"
    acc_path = tmp_path / "acc.json"
    flush_input = tmp_path / "flush_input.json"
    flush_input.write_text(json.dumps({
        "slug": item["slug"],
        "item": item,
        "candidates": validated,
        "candidate_action": "replace_cover",
        "candidate_target": "",
        "old_local": "",
        "old_url": "",
        "curr_px": 0,
    }), encoding="utf-8")

    sc_flush.flush(str(flush_input), str(preview_path), str(acc_path), images_dir=str(images_dir))

    entries = json.loads(preview_path.read_text(encoding="utf-8"))
    assert len(entries) == 1
    assert entries[0]["slug"] == item["slug"]
    assert len(entries[0]["candidates"]) == 1


def test_not_resolved_produces_no_candidate_urls():
    """Publisher mismatch → we_resolve no produce candidate_urls; nada que
    pasarle a sc_validate (el caller del skill saltea el target)."""
    item = _item()
    item["publisher"] = "Norma Editorial"
    listado = {"coleccion_id": 1832, "total_tomos": 25}
    result = we_resolve.resolve_candidates(item, listado, [_edition()])
    assert result["resolved"] is False
    assert result["candidate_urls"] == []
