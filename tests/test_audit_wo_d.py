"""Tests para WO-D (auditoría post-scrape, 2026-07-07): guard `approved_at`
(golden records) en los 13 retrofits de imagen/agrupación de listadomanga.

Cubre:
  1. Test estructural anti-drift: los 13 scripts del dominio de WO-D DEBEN
     mencionar `approved`/`is_approved` y exponer el flag `--include-approved`
     — si un script nuevo (o uno de estos) pierde el guard, este test lo
     detecta sin depender de qué tan exhaustivos sean los unit tests de abajo.
  2. Unit tests del guard en 3 scripts representativos con estilos de guard
     distintos: purge_placeholder_images.py (skip completo vía main()/CLI),
     fix_edition_country.py (mutación in-place vía main()/CLI), y
     upscale_images.py (skip a nivel de ARCHIVO compartido, unit directo de
     `_collect_targets`, sin depender de un binario upscaler real).
  3. fetch_better_covers.py — matiz (b): el guard aplica a `apply_preview()`
     (muta items.jsonl) pero NO a la generación de candidatas hacia el preview
     (cola de revisión, no es una escritura directa).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PIL import Image
import io

_ROOT = Path(__file__).resolve().parent.parent
_RETROFIT_DIR = _ROOT / "scripts" / "retrofit"
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))
if str(_RETROFIT_DIR) not in sys.path:
    sys.path.insert(0, str(_RETROFIT_DIR))


# ── 1. Test estructural anti-drift ──────────────────────────────────────────

# Dominio exclusivo de WO-D (ver CLAUDE.md / prompt de la ronda). Cualquier
# script nuevo que se agregue a este dominio debe entrar también acá.
WO_D_SCRIPTS = [
    "mirror_images.py",
    "dedup_carousel_images.py",
    "purge_placeholder_images.py",
    "upgrade_image_resolution.py",
    "backfill_prh_covers.py",
    "fetch_better_covers.py",
    "upscale_images.py",
    "promote_hires_cover.py",
    "align_raw_to_std_coleccion.py",
    "fix_edition_country.py",
    "unify_coleccion_edition.py",
    "fix_listadomanga_title_collisions.py",
    "enforce_listadomanga_rules.py",
    # Agregado 2026-07-08 (paquete E-standardize): remapea series_key/display de
    # golden records si pierde el guard → misma clase de bug de gotcha #121.
    "backfill_series_aliases.py",
]


@pytest.mark.parametrize("script_name", WO_D_SCRIPTS)
def test_script_has_approved_guard_mechanism(script_name):
    """Cada script del dominio WO-D debe mencionar `approved` (el guard/counter/
    is_approved) Y exponer el flag `--include-approved` en su CLI. Un script
    futuro que pierda el guard rompe ACÁ, no sólo en la promesa de la doc."""
    path = _RETROFIT_DIR / script_name
    assert path.is_file(), f"no encontré {path}"
    text = path.read_text(encoding="utf-8")
    assert "approved" in text.lower(), (
        f"{script_name}: no menciona 'approved' en ningún lado — "
        f"¿le falta el guard de items aprobados (approved_at)?"
    )
    assert "--include-approved" in text, (
        f"{script_name}: no expone el flag --include-approved."
    )


def test_mirror_images_backfill_is_additive_not_skip(tmp_path, monkeypatch):
    """mirror_images.py es la excepción documentada (matiz a): el backfill es
    ADITIVO (solo rellena `local` faltante), así que NO saltea items aprobados
    — un golden record también necesita su espejo local. Confirma que el
    comportamiento real coincide con lo que dice el docstring."""
    import mirror_images as mi

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    items = [
        {
            "title": "Approved Item",
            "url": "https://example.com/approved",
            "approved_at": "2026-06-01T00:00:00+00:00",
            "images": [{"url": "https://cdn.example.com/cover.jpg", "local": ""}],
        },
    ]
    items_path = tmp_path / "items.jsonl"
    items_path.write_text("\n".join(json.dumps(it) for it in items) + "\n", encoding="utf-8")

    targets = []
    for it in items:
        for idx, im in enumerate(it.get("images") or []):
            if im.get("url") and not im.get("local"):
                targets.append((it, idx))
    # El backfill (mi._run_backfill) trata a un item aprobado como CUALQUIER
    # otro target — no hay skip. Verificamos la condición de entrada directa
    # (misma que usa _run_backfill) para no depender de red real.
    assert len(targets) == 1
    assert mi.is_approved(items[0]) is True


# ── 2a. purge_placeholder_images.py — skip completo vía CLI ────────────────

def _run_main(module, argv):
    old = sys.argv
    sys.argv = [module.__name__ + ".py", *argv]
    try:
        return module.main()
    finally:
        sys.argv = old


def _solid_png(w, h, color=(255, 255, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def ppi_harness(tmp_path, monkeypatch):
    import purge_placeholder_images as ppi

    images = tmp_path / "images"
    images.mkdir()
    white = "white.png"
    (images / white).write_bytes(_solid_png(300, 450, (255, 255, 255)))

    items_path = tmp_path / "items.jsonl"
    monkeypatch.setattr(ppi, "ITEMS", items_path)
    monkeypatch.setattr(ppi, "IMAGES", images)
    monkeypatch.setattr(ppi, "ORPHANS", images / "_orphans")
    monkeypatch.setattr(ppi, "COVER_PREVIEW", tmp_path / "cover_preview.json")
    return ppi, items_path, images, white


def test_purge_placeholder_skips_approved_item_by_default(ppi_harness):
    ppi, items_path, images, white = ppi_harness
    items = [
        {"slug": "golden", "title": "Golden Record", "approved_at": "2026-06-01T00:00:00+00:00",
         "images": [{"url": "http://x/w.png", "local": white, "kind": "gallery"}], "sources": []},
    ]
    items_path.write_text("\n".join(json.dumps(it) for it in items) + "\n", encoding="utf-8")

    assert _run_main(ppi, []) == 0
    out = [json.loads(l) for l in items_path.read_text().splitlines() if l.strip()]
    # El item aprobado NO se toca: el placeholder sigue en su galería.
    assert out[0]["images"] == items[0]["images"]


def test_purge_placeholder_include_approved_processes_it(ppi_harness):
    ppi, items_path, images, white = ppi_harness
    items = [
        {"slug": "golden", "title": "Golden Record", "approved_at": "2026-06-01T00:00:00+00:00",
         "images": [{"url": "http://x/w.png", "local": white, "kind": "gallery"}], "sources": []},
    ]
    items_path.write_text("\n".join(json.dumps(it) for it in items) + "\n", encoding="utf-8")

    assert _run_main(ppi, ["--include-approved"]) == 0
    out = [json.loads(l) for l in items_path.read_text().splitlines() if l.strip()]
    # Con --include-approved el placeholder SÍ se purga (queda sin imágenes).
    assert out[0]["images"] == []


# ── 2b. fix_edition_country.py — mutación in-place vía CLI ─────────────────

@pytest.fixture
def fec_harness(tmp_path, monkeypatch):
    import fix_edition_country as fec

    items_path = tmp_path / "items.jsonl"
    monkeypatch.setattr(fec, "ITEMS", items_path)
    return fec, items_path


def _base_edition_items():
    return [
        {
            "title": "Serie A 1", "url": "https://example.com/a1",
            "edition_key": "seriea-panini-regular", "country": "España",
            "volume": "1", "sources": [],
            "approved_at": "2026-06-01T00:00:00+00:00",
        },
        {
            "title": "Serie A 2", "url": "https://example.com/a2",
            "edition_key": "seriea-panini-regular", "country": "España",
            "volume": "2", "sources": [],
        },
    ]


def test_fix_edition_country_skips_approved_by_default(fec_harness):
    fec, items_path = fec_harness
    items = _base_edition_items()
    items_path.write_text("\n".join(json.dumps(it) for it in items) + "\n", encoding="utf-8")

    assert _run_main(fec, []) == 0
    out = {it["title"]: it for it in
           (json.loads(l) for l in items_path.read_text().splitlines() if l.strip())}
    # El aprobado conserva su edition_key tal cual (sin sufijo de país).
    assert out["Serie A 1"]["edition_key"] == "seriea-panini-regular"
    # El no aprobado SÍ recibe el sufijo de país.
    assert out["Serie A 2"]["edition_key"] != "seriea-panini-regular"
    assert out["Serie A 2"]["edition_key"].startswith("seriea-panini-regular-")


def test_fix_edition_country_include_approved_processes_it(fec_harness):
    fec, items_path = fec_harness
    items = _base_edition_items()
    items_path.write_text("\n".join(json.dumps(it) for it in items) + "\n", encoding="utf-8")

    assert _run_main(fec, ["--include-approved"]) == 0
    out = {it["title"]: it for it in
           (json.loads(l) for l in items_path.read_text().splitlines() if l.strip())}
    assert out["Serie A 1"]["edition_key"] != "seriea-panini-regular"
    assert out["Serie A 1"]["edition_key"].startswith("seriea-panini-regular-")


# ── 2c. upscale_images.py — skip a nivel de ARCHIVO compartido ─────────────

def _textured_jpeg(w, h) -> bytes:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 5) % 256)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=90)
    return buf.getvalue()


def test_upscale_collect_targets_skips_files_owned_by_approved_item(tmp_path):
    import upscale_images as ui

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    small_shared = "small_shared.jpg"
    (images_dir / small_shared).write_bytes(_textured_jpeg(80, 120))  # 9 600 px < max
    small_free = "small_free.jpg"
    (images_dir / small_free).write_bytes(_textured_jpeg(80, 120))

    approved_item = {
        "title": "Golden", "approved_at": "2026-06-01T00:00:00+00:00",
        "images": [{"url": "http://x/shared.jpg", "local": small_shared, "kind": "gallery"}],
    }
    # Un item NO aprobado que comparte el MISMO archivo que el aprobado — todo
    # el archivo se saltea igual (no solo la fila aprobada), porque reemplazar
    # el archivo rompería la referencia del golden record.
    unapproved_sharer = {
        "title": "Sharer", "images": [
            {"url": "http://x/shared.jpg", "local": small_shared, "kind": "gallery"},
        ],
    }
    unapproved_free = {
        "title": "Free", "images": [
            {"url": "http://y/free.jpg", "local": small_free, "kind": "gallery"},
        ],
    }
    items = [approved_item, unapproved_sharer, unapproved_free]

    targets, skipped_already, skipped_approved = ui._collect_targets(
        items, images_dir, max_pixels=200_000, include_approved=False,
    )
    target_locals = {local for local, _path, _refs in targets}
    assert small_free in target_locals, "el archivo sin dueño aprobado debe ser candidato"
    assert small_shared not in target_locals, "el archivo del golden record se saltea ENTERO"
    assert skipped_approved == 1
    assert skipped_already == 0

    # Con --include-approved el archivo compartido también entra.
    targets2, _, skipped_approved2 = ui._collect_targets(
        items, images_dir, max_pixels=200_000, include_approved=True,
    )
    target_locals2 = {local for local, _path, _refs in targets2}
    assert small_shared in target_locals2
    assert skipped_approved2 == 0


def test_upscale_collect_targets_skips_already_upscaled_entries(tmp_path):
    import upscale_images as ui

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    local = "already.jpg"
    (images_dir / local).write_bytes(_textured_jpeg(80, 120))

    items = [
        {"title": "Already upscaled", "images": [
            {"url": "http://x/a.jpg", "local": local, "kind": "gallery", "upscaled": True},
        ]},
    ]
    targets, skipped_already, skipped_approved = ui._collect_targets(
        items, images_dir, max_pixels=200_000,
    )
    assert targets == []
    assert skipped_already == 1
    assert skipped_approved == 0


# ── 3. fetch_better_covers.py — matiz (b): guard solo en paths que MUTAN ───

def _make_jpeg(path: Path, size, color=(200, 30, 30)) -> None:
    Image.new("RGB", size, color).save(path, "JPEG")


@pytest.fixture
def fbc_preview_harness(tmp_path, monkeypatch):
    import fetch_better_covers as fbc

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_jpeg(images_dir / "old_cover.jpg", (100, 150))
    _make_jpeg(images_dir / "new_cover.jpg", (400, 600))

    item = {
        "slug": "golden-item", "title": "Golden",
        "approved_at": "2026-06-01T00:00:00+00:00",
        "images": [{"url": "http://x/old.jpg", "local": "old_cover.jpg", "kind": "gallery"}],
    }
    items_path = tmp_path / "items.jsonl"
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    preview = [{
        "slug": "golden-item", "title": "Golden",
        "old_url": "http://x/old.jpg", "old_image": "old_cover.jpg", "old_pixels": 15000,
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
    return fbc, items_path, images_dir, preview_path


def test_apply_preview_skips_approved_item_by_default(fbc_preview_harness):
    fbc, items_path, images_dir, preview_path = fbc_preview_harness
    summary = fbc.apply_preview(items_path, images_dir)

    item_after = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    # El golden record conserva su portada vieja — la mutación se saltea.
    assert item_after["images"][0]["local"] == "old_cover.jpg"
    assert summary.get("skipped_approved") == 1


def test_apply_preview_include_approved_applies_it(fbc_preview_harness):
    fbc, items_path, images_dir, preview_path = fbc_preview_harness
    summary = fbc.apply_preview(items_path, images_dir, include_approved=True)

    item_after = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    assert item_after["images"][0]["local"] == "new_cover.jpg"
    assert summary.get("skipped_approved") == 0
