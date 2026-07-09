"""Tests para scripts/audit/data_quality.py.

Cubren la auditoría Fable 2026-07-08 (paquete B-observabilidad):
- #7: archivo_tiny / pixelada juzgan por PÍXELES (image_store.placeholder_reason),
  no por bytes<6KB — el espejo es 100% AVIF y los bytes mienten (~1060 falsos
  positivos medidos sobre el corpus real).
- #6: check_urls respeta data/dup_decisions.jsonl igual que audit_items.
- #9/#11: _load_items abre con encoding="utf-8" y tolera líneas corruptas.
- #12: slug_stale loguea WARN en vez de tragarse la excepción en silencio.
- #13: _FIX_PROMPT_REF_ROTA habla en términos de images[N], no de
  image_local/image_url top-level (eliminados del schema 2026-06-09).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from scripts.audit import data_quality as dq


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _real_cover_bytes(images_dir: Path, name: str, size=(600, 900)) -> Path:
    """Imagen 'real' de alto contraste: comprime MUY chico en bytes (por debajo
    del viejo umbral de 6KB) pero NO es un placeholder estructural — std alto
    (bimodal 0/255), dimensiones grandes. Es exactamente el caso que #7
    corrige (antes: falso positivo 'archivo_tiny'; ahora: pasa limpio)."""
    images_dir.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(im)
    draw.rectangle([0, 0, size[0] // 2, size[1]], fill=(0, 0, 0))
    p = images_dir / name
    im.save(p, format="PNG", optimize=True)
    return p


def _placeholder_solid_bytes(images_dir: Path, name: str, size=(500, 500)) -> Path:
    """Placeholder estructural real: sólido de un solo color (std~0)."""
    images_dir.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", size, (230, 230, 230))
    p = images_dir / name
    im.save(p, format="PNG")
    return p


def _placeholder_tiny_bytes(images_dir: Path, name: str) -> Path:
    """Tracking pixel 1x1 (patrón clásico Amazon para ISBN sin carátula)."""
    images_dir.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (1, 1), (255, 255, 255))
    p = images_dir / name
    im.save(p, format="PNG")
    return p


def _item(url: str, *, local: str = "", cluster_key: str = "", **extra) -> dict:
    it = {
        "url": url,
        "title": extra.pop("title", "Test Item"),
        "source": extra.pop("source", "Test Source"),
        "cluster_key": cluster_key or f"edition:{url}",
    }
    if local:
        it["images"] = [{
            "url": f"https://cdn.example/{local}", "local": local,
            "kind": "gallery", "description": "",
        }]
    it.update(extra)
    return it


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Aísla ROOT/IMAGES a tmp_path: estos tests NO deben leer/escribir nada
    del repo real (data/items.jsonl, data/dup_decisions.jsonl, etc.)."""
    images_dir = tmp_path / "data" / "images"
    images_dir.mkdir(parents=True)
    monkeypatch.setattr(dq, "ROOT", tmp_path)
    monkeypatch.setattr(dq, "IMAGES", images_dir)
    return tmp_path, images_dir


# --------------------------------------------------------------------------- #
# #7: _measure_cover — píxeles vía image_store.placeholder_reason(), no bytes
# --------------------------------------------------------------------------- #

def test_measure_cover_real_image_high_contrast_not_flagged(isolated):
    """Antes: bytes<6KB marcaba esto 'archivo_tiny' (falso positivo medido:
    ~1060 items reales, portadas de 642x600/520x604...). Ahora: alto contraste
    comprime chico en bytes pero NO es un placeholder estructural (std alto) →
    no se flaggea."""
    _, images_dir = isolated
    p = _real_cover_bytes(images_dir, "real.png")
    assert p.stat().st_size < 6 * 1024  # confirma que el viejo umbral SÍ disparaba
    px, reason = dq._measure_cover(p)
    assert reason == ""
    assert px == 600 * 900


def test_measure_cover_solid_color_flagged(isolated):
    _, images_dir = isolated
    p = _placeholder_solid_bytes(images_dir, "solid.png")
    px, reason = dq._measure_cover(p)
    assert reason.startswith("solid:")
    assert px is None


def test_measure_cover_1x1_flagged_tiny(isolated):
    _, images_dir = isolated
    p = _placeholder_tiny_bytes(images_dir, "pixel.png")
    px, reason = dq._measure_cover(p)
    assert reason.startswith("tiny:")
    assert px is None


def test_measure_cover_broken_file(isolated):
    _, images_dir = isolated
    p = images_dir / "broken.png"
    p.write_bytes(b"not a real image")
    px, reason = dq._measure_cover(p)
    assert reason == "broken"
    assert px is None


def test_measure_cover_missing_file(isolated):
    _, images_dir = isolated
    px, reason = dq._measure_cover(images_dir / "does-not-exist.png")
    assert reason == "broken"
    assert px is None


# --------------------------------------------------------------------------- #
# #7: integración — audit_items / check_urls con el criterio pixel-based
# --------------------------------------------------------------------------- #

def test_audit_items_archivo_tiny_uses_pixels_not_bytes(isolated):
    """La portada de alto contraste (bytes chicos, píxeles reales) ya NO cae
    en archivo_tiny; el placeholder sólido SÍ."""
    _, images_dir = isolated
    _real_cover_bytes(images_dir, "real.png")
    _placeholder_solid_bytes(images_dir, "solid.png")
    items = [
        _item("https://a.example/1", local="real.png"),
        _item("https://a.example/2", local="solid.png"),
    ]
    report = dq.audit_items(items, px=90000, measure=True)
    by_id = {c["id"]: c for c in report["categories"]}
    tiny_urls = {e["url"] for e in by_id["archivo_tiny"]["items"]}
    assert "https://a.example/1" not in tiny_urls
    assert "https://a.example/2" in tiny_urls


def test_audit_items_no_measure_falls_back_to_bytes(isolated):
    """Sin medición de píxeles (--no-measure), cae al umbral de bytes viejo —
    heurística imperfecta pero mejor que nada cuando no se puede medir."""
    _, images_dir = isolated
    p = _real_cover_bytes(images_dir, "real.png")
    assert p.stat().st_size < 6 * 1024
    items = [_item("https://a.example/1", local="real.png")]
    report = dq.audit_items(items, px=90000, measure=False)
    by_id = {c["id"]: c for c in report["categories"]}
    tiny_urls = {e["url"] for e in by_id["archivo_tiny"]["items"]}
    assert "https://a.example/1" in tiny_urls  # fallback: bytes<6KB SÍ marca


def test_check_urls_archivo_tiny_uses_pixels_not_bytes(isolated):
    """Mismo criterio pixel-based que audit_items, replicado en check_urls
    (usado por el live-update del Panel de Calidad)."""
    _, images_dir = isolated
    _real_cover_bytes(images_dir, "real.png")
    items = [_item("https://a.example/1", local="real.png")]
    result = dq.check_urls(["https://a.example/1"], items=items)
    assert "archivo_tiny" not in result["https://a.example/1"]


# --------------------------------------------------------------------------- #
# #6: check_urls respeta data/dup_decisions.jsonl
# --------------------------------------------------------------------------- #

def test_check_urls_flags_undecided_isbn_dup(isolated):
    items = [
        {"url": "https://a.example/1", "isbn": "978-1", "cluster_key": "edition:a"},
        {"url": "https://a.example/2", "isbn": "978-1", "cluster_key": "edition:b"},
    ]
    result = dq.check_urls(["https://a.example/1"], items=items)
    assert "dup_product" in result["https://a.example/1"]


def test_check_urls_respects_dup_decisions(isolated):
    """Un grupo marcado 'distinct' desde el panel (data/dup_decisions.jsonl)
    NO debe volver a flaggearse en el live-update — antes check_urls ignoraba
    el archivo por completo y re-flageaba el mismo grupo en cada corrida,
    rompiendo la idempotencia del panel."""
    tmp_path, _ = isolated
    items = [
        {"url": "https://a.example/1", "isbn": "978-1", "cluster_key": "edition:a"},
        {"url": "https://a.example/2", "isbn": "978-1", "cluster_key": "edition:b"},
    ]
    # Misma firma EXACTA que produce _emit_dup_group / _group_is_dup_and_undecided.
    urls_sorted = sorted(it["url"] for it in items)
    sig = "ISBN 978-1|" + hashlib.sha1(
        "\n".join(urls_sorted).encode("utf-8")).hexdigest()[:12]
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "dup_decisions.jsonl").write_text(
        json.dumps({"signature": sig, "decision": "distinct"}) + "\n",
        encoding="utf-8",
    )
    result = dq.check_urls(["https://a.example/1"], items=items)
    assert "dup_product" not in result.get("https://a.example/1", [])


def test_check_urls_undecided_triple_group_still_flags(isolated):
    """La firma se recomputa también para el match 'triple' (serie+edición+
    volumen), no sólo ISBN."""
    items = [
        {"url": "https://a.example/1", "series_key": "s1", "edition_key": "e1",
         "volume": "3", "cluster_key": "edition:a"},
        {"url": "https://a.example/2", "series_key": "s1", "edition_key": "e1",
         "volume": "3", "cluster_key": "edition:b"},
    ]
    result = dq.check_urls(["https://a.example/1"], items=items)
    assert "dup_product" in result["https://a.example/1"]


# --------------------------------------------------------------------------- #
# #9 / #11: _load_items — encoding explícito + tolerancia a líneas corruptas
# --------------------------------------------------------------------------- #

def test_load_items_tolerates_corrupt_lines_and_utf8(tmp_path, capsys):
    p = tmp_path / "items.jsonl"
    good1 = json.dumps({"url": "https://a", "title": "日本語タイトル"}, ensure_ascii=False)
    good2 = json.dumps({"url": "https://b", "title": "Ñoño"}, ensure_ascii=False)
    p.write_text(good1 + "\n" + "{esto no es json válido,,,\n" + good2 + "\n", encoding="utf-8")
    items = dq._load_items(p)
    assert len(items) == 2
    assert items[0]["title"] == "日本語タイトル"
    assert items[1]["title"] == "Ñoño"
    err = capsys.readouterr().err
    assert "línea corrupta" in err


def test_load_items_skips_blank_lines(tmp_path):
    p = tmp_path / "items.jsonl"
    p.write_text('{"url": "https://a"}\n\n\n{"url": "https://b"}\n', encoding="utf-8")
    items = dq._load_items(p)
    assert len(items) == 2


# --------------------------------------------------------------------------- #
# #12: slug_stale loguea WARN en vez de tragarse la excepción
# --------------------------------------------------------------------------- #

def test_slug_stale_logs_warn_on_exception(isolated, monkeypatch, capsys):
    tmp_path, _ = isolated

    def _boom(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(dq._slugs, "_best_representative", _boom)
    items = [_item("https://a.example/1", cluster_key="edition:a")]
    report = dq.audit_items(items, measure=False)
    err = capsys.readouterr().err
    assert "slug_stale" in err
    assert "boom" in err
    readiness = {r["id"]: r for r in report["readiness"]}
    assert readiness["slugs"]["stale"] == 0


# --------------------------------------------------------------------------- #
# #13: _FIX_PROMPT_REF_ROTA habla en términos de images[N]
# --------------------------------------------------------------------------- #

def test_fix_prompt_ref_rota_uses_images_array_not_top_level_fields():
    prompt = dq._FIX_PROMPT_REF_ROTA
    assert "images[N]" in prompt
    assert "image_local/image_url top-level" in prompt
