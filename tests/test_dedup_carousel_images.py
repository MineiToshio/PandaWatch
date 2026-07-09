"""Tests para scripts/retrofit/dedup_carousel_images.py.

Sin red — usan imágenes sintéticas PIL en tmp_path. Cubre el paquete de
fixes de la auditoría Fable 2026-07-08 (hallazgo #5 y #12):

  - backup_and_rotate (no un slot fijo `.pre-dedup-bak`).
  - flush incremental (no un write único al final).
  - _bytes_cache con cota LRU.
  - json.dumps con sort_keys=True.
  - THUMB_ASPECT_TOL importado de image_store (fuente única).
  - #12: si la portada cae como duplicado, un `extra` NO puede ascender a
    portada — el próximo `gallery` sobreviviente sí.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

# Si otro test ya dejó un stub incompleto de manga_watch en sys.modules
# (algún test que solo necesitaba un subconjunto de símbolos), lo quitamos
# para que este archivo importe el módulo real — mismo patrón que
# test_promote_hires_cover.py.
import types as _types  # noqa: E402
_mw = sys.modules.get("manga_watch")
if _mw is not None and not all(
    hasattr(_mw, sym) for sym in ("backup_and_rotate", "is_approved", "make_session")
):
    del sys.modules["manga_watch"]
if "dedup_carousel_images" in sys.modules:
    del sys.modules["dedup_carousel_images"]

import image_store  # noqa: E402
import dedup_carousel_images as dci  # noqa: E402


# ── helpers de imágenes sintéticas ────────────────────────────────────────────

def _textured(w: int, h: int, seed: int = 0) -> Image.Image:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (
                ((x + seed) * 255 // max(w, 1)) % 256,
                (y * 255 // max(h, 1)) % 256,
                ((x + y + seed) * 255 // max(w + h, 1)) % 256,
            )
    return im


def _png_bytes(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _save(path: Path, data: bytes) -> None:
    path.write_bytes(data)


# ── unit: constante centralizada (hallazgo #12) ───────────────────────────────

def test_thumb_aspect_tol_imported_from_image_store():
    assert dci.THUMB_ASPECT_TOL == image_store.THUMB_ASPECT_TOL == 0.06


# ── unit: cache LRU con cota (hallazgo #5d) ───────────────────────────────────

def test_bytes_cache_has_lru_cap():
    dci._bytes_cache.clear()
    for i in range(dci._BYTES_CACHE_MAX + 20):
        dci._cache_put(f"http://x/{i}.jpg", b"x")
    assert len(dci._bytes_cache) <= dci._BYTES_CACHE_MAX
    # las primeras (más viejas) deben haber sido evictadas
    assert "http://x/0.jpg" not in dci._bytes_cache
    # las últimas siguen presentes
    assert f"http://x/{dci._BYTES_CACHE_MAX + 19}.jpg" in dci._bytes_cache


def test_bytes_cache_get_moves_to_end():
    dci._bytes_cache.clear()
    dci._cache_put("a", b"1")
    dci._cache_put("b", b"2")
    dci._cache_get("a")  # "a" pasa a ser el más reciente
    for i in range(dci._BYTES_CACHE_MAX - 1):
        dci._cache_put(f"filler{i}", b"x")
    # "a" sobrevive (se tocó), "b" es el candidato más viejo a evictar
    assert "a" in dci._bytes_cache


# ── integración end-to-end ────────────────────────────────────────────────────

@pytest.fixture
def harness(tmp_path, monkeypatch):
    images = tmp_path / "images"
    images.mkdir()

    base = _textured(300, 450, seed=7)
    full_bytes = _png_bytes(base)
    thumb_bytes = _png_bytes(base.resize((100, 150)))
    extra_bytes = _png_bytes(_textured(200, 200, seed=99))  # foto no relacionada

    _save(images / "full.png", full_bytes)
    _save(images / "thumb.png", thumb_bytes)
    _save(images / "extra.png", extra_bytes)

    items_path = tmp_path / "items.jsonl"
    monkeypatch.setattr(dci, "ITEMS", items_path)
    monkeypatch.setattr(dci, "IMAGES", images)
    return dci, items_path, images


def _run(argv):
    old = sys.argv
    sys.argv = ["dedup_carousel_images.py", *argv]
    try:
        return dci.main()
    finally:
        sys.argv = old


def test_extra_does_not_promote_to_cover_when_portada_dropped(harness):
    """Hallazgo #12: la portada (thumb) cae como dup del `full` hi-res; el
    `extra` que queda en el medio NUNCA debe terminar en images[0]."""
    dci, items_path, images = harness
    item = {
        "slug": "a",
        "title": "A",
        "images": [
            {"url": "http://x/thumb.png", "local": "thumb.png", "kind": "gallery"},
            {"url": "http://x/extra.png", "local": "extra.png", "kind": "extra"},
            {"url": "http://x/full.png", "local": "full.png", "kind": "gallery"},
        ],
    }
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    rc = _run(["--all"])
    assert rc == 0

    saved = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    imgs = saved["images"]
    assert len(imgs) == 2  # el thumb (dup de menor resolución) se quitó
    assert imgs[0]["local"] == "full.png"  # el hi-res quedó de portada
    assert imgs[0]["kind"] == "gallery"
    # el extra sigue en la galería, nunca se descarta ni se promueve
    assert any(im["local"] == "extra.png" for im in imgs)
    assert not any(im["local"] == "thumb.png" for im in imgs)


def test_backup_and_rotate_used_not_fixed_slot(harness):
    dci, items_path, images = harness
    item = {
        "slug": "a", "title": "A",
        "images": [
            {"url": "http://x/thumb.png", "local": "thumb.png", "kind": "gallery"},
            {"url": "http://x/full.png", "local": "full.png", "kind": "gallery"},
        ],
    }
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    _run(["--all"])

    # backup_and_rotate escribe en data/backups/<filename>/<filename>.pre-<label>-bak
    backup_dir = items_path.parent / "backups" / items_path.name
    assert backup_dir.exists()
    backups = list(backup_dir.glob("*.pre-dedup-carousel-bak"))
    assert backups, "backup_and_rotate no dejó rastro con el label esperado"
    # el slot legacy fijo NO debe existir más
    assert not (items_path.parent / "items.jsonl.pre-dedup-bak").exists()


def test_output_is_sorted_keys_and_utf8(harness):
    dci, items_path, images = harness
    item = {
        "slug": "a", "title": "Título con ñ",
        "images": [
            {"url": "http://x/thumb.png", "local": "thumb.png", "kind": "gallery"},
            {"url": "http://x/full.png", "local": "full.png", "kind": "gallery"},
        ],
    }
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    _run(["--all"])

    line = items_path.read_text(encoding="utf-8").splitlines()[0]
    saved = json.loads(line)
    # sort_keys=True: las claves del dict serializado están en orden alfabético
    assert line == json.dumps(saved, ensure_ascii=False, sort_keys=True)
    assert "Título con ñ" == saved["title"]  # ensure_ascii=False preserva UTF-8


def test_no_dup_leaves_item_untouched(harness):
    dci, items_path, images = harness
    item = {
        "slug": "a", "title": "A",
        "images": [
            {"url": "http://x/full.png", "local": "full.png", "kind": "gallery"},
            {"url": "http://x/extra.png", "local": "extra.png", "kind": "extra"},
        ],
    }
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    _run(["--all"])
    saved = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    assert len(saved["images"]) == 2


def test_dry_run_writes_nothing(harness):
    dci, items_path, images = harness
    item = {
        "slug": "a", "title": "A",
        "images": [
            {"url": "http://x/thumb.png", "local": "thumb.png", "kind": "gallery"},
            {"url": "http://x/full.png", "local": "full.png", "kind": "gallery"},
        ],
    }
    original = json.dumps(item) + "\n"
    items_path.write_text(original, encoding="utf-8")

    _run(["--all", "--dry-run"])

    assert items_path.read_text(encoding="utf-8") == original
    backup_dir = items_path.parent / "backups"
    assert not backup_dir.exists()


def test_incremental_flush_called_before_final_write(harness, monkeypatch):
    """Hallazgo #5b: un write único al final pierde todo si el proceso muere
    a mitad de una corrida larga. Verificamos que `_write_items` se invoque
    más de una vez cuando hay suficientes items con cambios (> _FLUSH_EVERY)."""
    dci, items_path, images = harness

    lines = []
    for i in range(55):
        lines.append(json.dumps({
            "slug": f"s{i}", "title": f"T{i}",
            "images": [
                {"url": f"http://x/thumb{i}.png", "local": "thumb.png", "kind": "gallery"},
                {"url": f"http://x/full{i}.png", "local": "full.png", "kind": "gallery"},
            ],
        }))
    items_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    calls = []
    real_write = dci._write_items

    def _counting_write(dst, items):
        calls.append(len(calls))
        return real_write(dst, items)

    monkeypatch.setattr(dci, "_write_items", _counting_write)
    rc = _run(["--all"])
    assert rc == 0
    # 55 items cambiados con _FLUSH_EVERY=50 → 1 flush parcial + 1 final = 2
    assert len(calls) >= 2
