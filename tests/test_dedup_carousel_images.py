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
    # Aísla el reporte de dudosos del --redteam-auto del repo real (nunca
    # escribir en data/diagnostics/ del proyecto durante los tests).
    monkeypatch.setattr(dci, "DUDOSOS_REPORT", tmp_path / "dudosos-report.json")
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


# ── --redteam-auto: regla AUTO validada por red-team (OLA 2, 2026-09-01) ──────
# La regla en sí (SHA-256 idéntico, o dHash<=2 + dims DISTINTAS + aspect<=2%)
# se testea primero como función PURA sobre fingerprints sintéticos (rápido,
# determinístico, sin depender de que una imagen real produzca un dHash
# exacto) y después con imágenes reales para el flujo end-to-end.

def _rf(sha256="", dhash=0, px=100, w=10, h=10):
    return {"sha256": sha256, "dhash": dhash, "px": px, "w": w, "h": h}


def test_redteam_classify_sha256_identical_is_auto_even_without_dhash():
    rf1 = _rf(sha256="same", dhash=None, w=300, h=450)
    rf2 = _rf(sha256="same", dhash=None, w=300, h=450)
    assert dci._redteam_classify(rf1, rf2) == "auto"


def test_redteam_classify_dhash_le2_distinct_dims_same_aspect_is_auto():
    rf1 = _rf(sha256="a", dhash=0b000, w=300, h=450, px=300 * 450)
    rf2 = _rf(sha256="b", dhash=0b010, w=600, h=900, px=600 * 900)  # 2x exacto
    assert dci.fbc._hamming(rf1["dhash"], rf2["dhash"]) == 1
    assert dci._redteam_classify(rf1, rf2) == "auto"


def test_redteam_classify_same_dims_is_dudoso_not_auto():
    """El falso positivo típico del red-team: dims EXACTAMENTE iguales
    (shikishi de colores distintos, caja llena vs vacía) — aunque el dHash
    esté a distancia 1, NUNCA es auto."""
    rf1 = _rf(sha256="a", dhash=0b000, w=300, h=450, px=300 * 450)
    rf2 = _rf(sha256="b", dhash=0b001, w=300, h=450, px=300 * 450)
    assert dci._redteam_classify(rf1, rf2) == "dudoso"


def test_redteam_classify_dhash_band_3_8_is_dudoso():
    rf1 = _rf(sha256="a", dhash=0b000, w=300, h=450, px=300 * 450)
    rf2 = _rf(sha256="b", dhash=0b111, w=600, h=900, px=600 * 900)  # hamming=3
    assert dci.fbc._hamming(rf1["dhash"], rf2["dhash"]) == 3
    assert dci._redteam_classify(rf1, rf2) == "dudoso"


def test_redteam_classify_aspect_over_2pct_is_dudoso_not_auto():
    rf1 = _rf(sha256="a", dhash=0b1, w=300, h=450, px=300 * 450)  # ratio .6667
    rf2 = _rf(sha256="b", dhash=0b0, w=620, h=900, px=620 * 900)  # ratio .6889, diff ~3.3%
    assert dci.fbc._hamming(rf1["dhash"], rf2["dhash"]) == 1
    assert dci._redteam_classify(rf1, rf2) == "dudoso"


def test_redteam_classify_outside_scan_band_is_none():
    rf1 = _rf(sha256="a", dhash=0b000000000, w=300, h=450, px=300 * 450)
    rf2 = _rf(sha256="b", dhash=0b111111111, w=600, h=900, px=600 * 900)  # hamming=9 > 8
    assert dci.fbc._hamming(rf1["dhash"], rf2["dhash"]) == 9
    assert dci._redteam_classify(rf1, rf2) is None


def test_redteam_auto_removes_byte_identical_duplicate(harness):
    dci, items_path, images = harness
    same_bytes = _png_bytes(_textured(300, 450, seed=3))
    _save(images / "dup_a.png", same_bytes)
    _save(images / "dup_b.png", same_bytes)  # bytes IDÉNTICOS, otro nombre de archivo
    item = {
        "slug": "sha-dup", "title": "SHA dup",
        "images": [
            {"url": "http://x/dup_a.png", "local": "dup_a.png", "kind": "gallery"},
            {"url": "http://x/dup_b.png", "local": "dup_b.png", "kind": "gallery"},
        ],
    }
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    rc = _run(["--redteam-auto"])
    assert rc == 0
    saved = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    assert len(saved["images"]) == 1  # el duplicado byte-idéntico se quitó


def test_redteam_auto_removes_rescaled_duplicate_and_repromotes_cover(harness):
    """La portada (images[0]) es la versión CHICA; el `extra` queda en medio;
    el hi-res gana. El `extra` nunca debe terminar en images[0]."""
    dci, items_path, images = harness
    base = _textured(300, 450, seed=11)
    small_bytes = _png_bytes(base)
    big_bytes = _png_bytes(base.resize((600, 900), Image.LANCZOS))  # 2x exacto, mismo aspect
    extra_bytes = _png_bytes(_textured(150, 150, seed=42))
    _save(images / "small.png", small_bytes)
    _save(images / "big.png", big_bytes)
    _save(images / "extra2.png", extra_bytes)
    item = {
        "slug": "rescaled", "title": "Rescaled",
        "images": [
            {"url": "http://x/small.png", "local": "small.png", "kind": "gallery"},
            {"url": "http://x/extra2.png", "local": "extra2.png", "kind": "extra"},
            {"url": "http://x/big.png", "local": "big.png", "kind": "gallery"},
        ],
    }
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    rc = _run(["--redteam-auto"])
    assert rc == 0
    saved = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    imgs = saved["images"]
    assert len(imgs) == 2
    assert imgs[0]["local"] == "big.png"  # el hi-res quedó de portada
    assert imgs[0]["kind"] == "gallery"
    assert any(im["local"] == "extra2.png" for im in imgs)  # el extra sobrevive
    assert not any(im["local"] == "small.png" for im in imgs)


def test_redteam_dudoso_same_dims_is_reported_not_removed(harness):
    """Dos imágenes DISTINTAS (contenido) pero con las MISMAS dimensiones —
    el caso de falso positivo típico del red-team. NUNCA se auto-elimina;
    debe quedar reportada en el JSON de dudosos."""
    dci, items_path, images = harness
    base = _textured(300, 450, seed=21)
    a_bytes = _png_bytes(base)
    b_img = base.copy()
    b_img.putpixel((0, 0), (255, 0, 0))  # 1 píxel distinto, MISMAS dims, distinto sha256
    b_bytes = _png_bytes(b_img)
    assert a_bytes != b_bytes
    _save(images / "sib_a.png", a_bytes)
    _save(images / "sib_b.png", b_bytes)
    item = {
        "slug": "siblings", "title": "Siblings",
        "images": [
            {"url": "http://x/sib_a.png", "local": "sib_a.png", "kind": "gallery"},
            {"url": "http://x/sib_b.png", "local": "sib_b.png", "kind": "gallery"},
        ],
    }
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    rc = _run(["--redteam-auto", "--dry-run"])
    assert rc == 0
    # dry-run: items.jsonl no cambia, pero el reporte de dudosos SÍ se escribe
    # (es evidencia, no una escritura sobre el catálogo).
    saved = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    assert len(saved["images"]) == 2  # nada se tocó

    report = json.loads(dci.DUDOSOS_REPORT.read_text(encoding="utf-8"))
    assert report["count"] == 1
    pair = report["pairs"][0]
    assert pair["slug"] == "siblings"
    assert pair["same_dims"] is True
    locals_in_pair = {pair["image_a"]["local"], pair["image_b"]["local"]}
    assert locals_in_pair == {"sib_a.png", "sib_b.png"}


def test_redteam_auto_backup_label_is_wave2_dedup(harness):
    dci, items_path, images = harness
    same_bytes = _png_bytes(_textured(300, 450, seed=5))
    _save(images / "d1.png", same_bytes)
    _save(images / "d2.png", same_bytes)
    item = {
        "slug": "a", "title": "A",
        "images": [
            {"url": "http://x/d1.png", "local": "d1.png", "kind": "gallery"},
            {"url": "http://x/d2.png", "local": "d2.png", "kind": "gallery"},
        ],
    }
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    _run(["--redteam-auto"])

    backup_dir = items_path.parent / "backups" / items_path.name
    backups = list(backup_dir.glob("*.pre-wave2-dedup-bak"))
    assert backups, "backup_and_rotate no dejó rastro con el label wave2-dedup"


def test_redteam_auto_idempotent_second_run_no_changes(harness):
    dci, items_path, images = harness
    base = _textured(300, 450, seed=8)
    small_bytes = _png_bytes(base)
    big_bytes = _png_bytes(base.resize((600, 900), Image.LANCZOS))
    _save(images / "s.png", small_bytes)
    _save(images / "b.png", big_bytes)
    item = {
        "slug": "idem", "title": "Idem",
        "images": [
            {"url": "http://x/s.png", "local": "s.png", "kind": "gallery"},
            {"url": "http://x/b.png", "local": "b.png", "kind": "gallery"},
        ],
    }
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    _run(["--redteam-auto"])
    first = items_path.read_text(encoding="utf-8")
    _run(["--redteam-auto"])
    second = items_path.read_text(encoding="utf-8")
    assert first == second  # 2ª corrida: nada que dedupear, salida byte-idéntica
