"""tests/test_cover_sync_guards.py — paquete A1-covers-sync (auditoría Fable
2026-07-08, data/diagnostics/fable-audit-cover-sync-normalize-20260708.md).

Cobertura:
  1. `sync_cover_preview.catalog_is_sane()` — guard de catálogo ausente/corrupto
     (#1, ALTA): líneas malformadas, catálogo vacío con cola no vacía, umbral de
     20% de slugs sin match. Además el CLI (`main()`) aborta sin escribir nada.
  2. `serve._handle_cover_preview_get()` degrada a solo-lectura con el mismo
     guard (no persiste sobre un catálogo que no cargó).
  3. `sync_cover_images.run()` aborta si el espejo (`data/images/`) no existe
     (#2, ALTA) en vez de clasificar TODO local como basura.
  4. `_fix_bad_cover` no promueve `kind: "extra"` a portada, y preserva extras
     legítimas al limpiar (#8).
  5. `prune_soft_cover_candidates.py` marca candidatas blandas como `rejected` +
     ledger, igual que `revalidate_cover_preview.py` (#9, política unificada).
  6. `sort_keys=True` en el escritor de `sync_cover_images.py` (#12).
  7. GC de candidatas huérfanas en `sync_preview()` (#14) — borra sólo lo que
     nada más referencia; nunca un archivo que también usa un item real.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import sync_cover_preview as scp  # noqa: E402
import sync_cover_images as sci  # noqa: E402
import prune_soft_cover_candidates as psc  # noqa: E402
import fetch_better_covers as fbc  # noqa: E402

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers de imágenes sintéticas
# ---------------------------------------------------------------------------

def _make_img(path: Path, size=(100, 150), color=(200, 30, 30)) -> None:
    Image.new("RGB", size, color).save(path, "JPEG")


def _make_soft_gradient(path: Path, size=(300, 300)) -> None:
    """Imagen CHICA (<150k px) y BLANDA (bajo detalle real): gradiente suave,
    sólo frecuencias bajas — sobrevive downscale+upscale casi intacta, así que
    `fetch_better_covers._is_soft_image` da True. Verificado empíricamente
    (ratio ~0.004, muy por debajo de DETAIL_RATIO_MIN=0.115)."""
    w, h = size
    img = Image.new("L", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = int(255 * x / w)
    img.convert("RGB").save(path, "JPEG", quality=90)


@pytest.fixture()
def ledger_path(tmp_path, monkeypatch):
    """Aísla el ledger de rechazos — sin esto, prune_soft_cover_candidates.py
    (vía fetch_better_covers.ledger_append) escribiría al archivo REAL del repo."""
    p = tmp_path / "cover_rejections.jsonl"
    monkeypatch.setattr(fbc, "REJECTION_LEDGER_PATH", p)
    return p


def _load_serve():
    """Módulo serve.py fresco — mismo patrón que tests/test_audit_wo_e.py: cada
    test necesita mutar globals (ROOT, ITEMS_PATH) sin filtrar estado a otros tests."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("serve_mod_test_cover_guards", "scripts/serve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. catalog_is_sane() — guard de catálogo ausente/corrupto (#1, ALTA)
# ---------------------------------------------------------------------------

def test_catalog_is_sane_ok_when_slugs_match():
    preview = [{"slug": "a"}, {"slug": "b"}]
    items_by_slug = {"a": {}, "b": {}}
    ok, reason = scp.catalog_is_sane(preview, items_by_slug, 0)
    assert ok is True
    assert reason == ""


def test_catalog_is_sane_flags_malformed_lines():
    preview = [{"slug": "a"}]
    items_by_slug = {"a": {}}
    ok, reason = scp.catalog_is_sane(preview, items_by_slug, 3)
    assert ok is False
    assert "3" in reason


def test_catalog_is_sane_flags_empty_catalog_nonempty_queue():
    # items.jsonl ausente/vacío pero la cola SÍ tiene entries → catálogo no cargó.
    preview = [{"slug": "a"}]
    ok, reason = scp.catalog_is_sane(preview, {}, 0)
    assert ok is False
    assert "vacío" in reason


def test_catalog_is_sane_ok_when_both_empty():
    # Catálogo e cola vacíos → inofensivo (nada que purgar).
    ok, reason = scp.catalog_is_sane([], {}, 0)
    assert ok is True


def test_catalog_is_sane_flags_over_20pct_missing():
    # 3/10 slugs matchean, 7/10 no → 70% missing, supera el 20%.
    preview = [{"slug": f"s{i}"} for i in range(10)]
    items_by_slug = {"s0": {}, "s1": {}, "s2": {}}
    ok, reason = scp.catalog_is_sane(preview, items_by_slug, 0)
    assert ok is False
    assert "70%" in reason or "7/10" in reason


def test_catalog_is_sane_ok_at_boundary_20pct():
    # 8/10 matchean, 2/10 no (20% exacto) → NO supera el umbral (>20%, no >=).
    preview = [{"slug": f"s{i}"} for i in range(10)]
    items_by_slug = {f"s{i}": {} for i in range(8)}
    ok, reason = scp.catalog_is_sane(preview, items_by_slug, 0)
    assert ok is True


def test_sync_main_aborts_on_malformed_items_without_writing(tmp_path, monkeypatch, capsys):
    """CLI: items.jsonl con una línea corrupta → abortar, no tocar cover_preview.json."""
    preview_path = tmp_path / "cover_preview.json"
    original = [{"slug": "s1", "candidates": [{"status": "pending", "new_url": "https://x/a.jpg",
                                                "new_image": "", "action": "replace_cover"}]}]
    preview_path.write_text(json.dumps(original), encoding="utf-8")

    items_path = tmp_path / "items.jsonl"
    items_path.write_text('{"slug": "s1"\n', encoding="utf-8")  # JSON truncado a propósito

    images_dir = tmp_path / "images"
    images_dir.mkdir()

    monkeypatch.setattr(scp, "PREVIEW_PATH", preview_path)
    monkeypatch.setattr(scp, "ITEMS_PATH", items_path)
    monkeypatch.setattr(scp, "IMAGES_DIR", images_dir)

    rc = scp.main([])
    assert rc == 1

    out = capsys.readouterr().out
    assert "ABORT" in out

    # cover_preview.json NUNCA se tocó.
    assert json.loads(preview_path.read_text(encoding="utf-8")) == original
    assert not (tmp_path / "backups").exists()


def test_sync_main_aborts_on_missing_items_file(tmp_path, monkeypatch, capsys):
    """CLI: items.jsonl no existe pero la cola sí tiene entries → abortar."""
    preview_path = tmp_path / "cover_preview.json"
    original = [{"slug": "s1", "candidates": [{"status": "pending"}]}]
    preview_path.write_text(json.dumps(original), encoding="utf-8")

    monkeypatch.setattr(scp, "PREVIEW_PATH", preview_path)
    monkeypatch.setattr(scp, "ITEMS_PATH", tmp_path / "nope.jsonl")
    monkeypatch.setattr(scp, "IMAGES_DIR", tmp_path / "images")

    rc = scp.main([])
    assert rc == 1
    assert json.loads(preview_path.read_text(encoding="utf-8")) == original


# ---------------------------------------------------------------------------
# 2. GET /api/cover-preview degrada a solo-lectura (#1, ALTA)
# ---------------------------------------------------------------------------

def test_cover_preview_get_degrades_when_items_missing(tmp_path):
    serve = _load_serve()
    serve.ROOT = tmp_path
    (tmp_path / "data").mkdir()

    serve.ITEMS_PATH = tmp_path / "data" / "items.jsonl"  # NO existe

    preview_path = tmp_path / "data" / "cover_preview.json"
    original_preview = [
        {"slug": "s1", "candidates": [{"status": "pending", "new_url": "https://y/img.jpg"}]},
    ]
    preview_path.write_text(json.dumps(original_preview), encoding="utf-8")

    h = object.__new__(serve.MangaWatchHandler)
    responses = []
    h._json = lambda status, payload: responses.append((status, payload))
    h._handle_cover_preview_get()

    assert len(responses) == 1
    status, body = responses[0]
    assert status == 200
    assert body["synced"].get("degraded") is True
    assert body["entries"] == original_preview
    # Nunca se persistió nada: el archivo en disco sigue igual.
    assert json.loads(preview_path.read_text(encoding="utf-8")) == original_preview


def test_cover_preview_get_degrades_when_items_malformed(tmp_path):
    serve = _load_serve()
    serve.ROOT = tmp_path
    (tmp_path / "data").mkdir()

    items_path = tmp_path / "data" / "items.jsonl"
    items_path.write_text("not json at all\n", encoding="utf-8")
    serve.ITEMS_PATH = items_path

    preview_path = tmp_path / "data" / "cover_preview.json"
    original_preview = [{"slug": "s1", "candidates": [{"status": "pending"}]}]
    preview_path.write_text(json.dumps(original_preview), encoding="utf-8")

    h = object.__new__(serve.MangaWatchHandler)
    responses = []
    h._json = lambda status, payload: responses.append((status, payload))
    h._handle_cover_preview_get()

    status, body = responses[0]
    assert status == 200
    assert body["synced"].get("degraded") is True
    assert body["entries"] == original_preview


def test_cover_preview_get_syncs_normally_when_catalog_sane(tmp_path):
    """Caso feliz: no debe degradar cuando el catálogo matchea bien."""
    serve = _load_serve()
    serve.ROOT = tmp_path
    (tmp_path / "data").mkdir()

    items_path = tmp_path / "data" / "items.jsonl"
    items_path.write_text(json.dumps({"slug": "s1", "url": "https://x", "images": []}) + "\n",
                          encoding="utf-8")
    serve.ITEMS_PATH = items_path

    preview_path = tmp_path / "data" / "cover_preview.json"
    original_preview = [
        {"slug": "s1", "candidates": [{"status": "approved", "new_url": "https://y/img.jpg"}]},
    ]
    preview_path.write_text(json.dumps(original_preview), encoding="utf-8")

    h = object.__new__(serve.MangaWatchHandler)
    responses = []
    h._json = lambda status, payload: responses.append((status, payload))
    h._handle_cover_preview_get()

    status, body = responses[0]
    assert status == 200
    assert "degraded" not in body["synced"]
    assert body["approved_unapplied"] == 1


# ---------------------------------------------------------------------------
# 3. sync_cover_images.run() aborta si el espejo no existe (#2, ALTA)
# ---------------------------------------------------------------------------

def test_sync_cover_images_aborts_when_mirror_missing(tmp_path, capsys):
    items_path = tmp_path / "items.jsonl"
    item = {
        "title": "Test",
        "images": [{"url": "https://x/visuel_defaut.png", "local": "ph.png", "kind": "gallery"}],
    }
    original_text = json.dumps(item, ensure_ascii=False) + "\n"
    items_path.write_text(original_text, encoding="utf-8")
    # NO se crea tmp_path / "images" — el espejo está ausente.

    sci.run(items_path, dry_run=False, include_approved=False)

    out = capsys.readouterr().out
    assert "ABORT" in out
    # items.jsonl no se tocó (ni backup, ni escritura).
    assert items_path.read_text(encoding="utf-8") == original_text
    assert not (tmp_path / "backups").exists()


def test_compute_junk_local_skips_files_not_in_mirror(tmp_path):
    """Cuando el espejo SÍ existe pero un archivo referenciado no está ahí,
    debe tratarse como skip legítimo, NO como basura (0 bytes)."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    # "ghost.jpg" nunca se creó en el espejo.
    items = [{"images": [{"local": "ghost.jpg", "url": "https://x/ghost.jpg"}],
              "series_display": "Ghost", "title": "Ghost 1"}]
    junk = sci._compute_junk_local(items, images_dir)
    assert "ghost.jpg" not in junk


# ---------------------------------------------------------------------------
# 4. _fix_bad_cover no promueve "extra" a portada, preserva extras (#8)
# ---------------------------------------------------------------------------

def test_fix_bad_cover_prefers_gallery_over_extra():
    it = {
        "images": [
            {"url": "https://x/visuel_defaut.png", "local": "ph.png", "kind": "gallery"},
            {"url": "https://x/postal.jpg", "local": "postal.jpg", "kind": "extra"},
            {"url": "https://x/real-cover.jpg", "local": "real.jpg", "kind": "gallery"},
        ],
    }
    assert sci._fix_bad_cover(it) is True
    assert it["images"][0]["url"] == "https://x/real-cover.jpg"
    # La extra sigue en la galería, no se perdió.
    locals_ = [im["local"] for im in it["images"]]
    assert "postal.jpg" in locals_


def test_fix_bad_cover_preserves_extra_when_no_gallery_replacement():
    it = {
        "images": [
            {"url": "https://x/visuel_defaut.png", "local": "ph.png", "kind": "gallery"},
            {"url": "https://x/postal.jpg", "local": "postal.jpg", "kind": "extra"},
        ],
    }
    assert sci._fix_bad_cover(it) is True
    # Antes esto vaciaba TODO el array; ahora la extra sobrevive.
    assert it["images"] != []
    locals_ = [im["local"] for im in it["images"]]
    assert "postal.jpg" in locals_
    assert "ph.png" not in locals_  # la portada basura SÍ se quitó


# ---------------------------------------------------------------------------
# 5. sort_keys=True en el escritor de sync_cover_images.py (#12)
# ---------------------------------------------------------------------------

def test_sync_cover_images_writes_sort_keys(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    items_path = tmp_path / "items.jsonl"
    # Item con portada basura para forzar un cambio real (que dispare la escritura).
    item = {
        "zzz_last_key": "z",
        "aaa_first_key": "a",
        "images": [{"url": "https://x/visuel_defaut.png", "local": "ph.png", "kind": "gallery"}],
    }
    items_path.write_text(json.dumps(item, ensure_ascii=False) + "\n", encoding="utf-8")

    sci.run(items_path, dry_run=False, include_approved=False)

    line = items_path.read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    resorted = json.dumps(parsed, ensure_ascii=False, sort_keys=True)
    assert line == resorted, "la línea escrita debe tener las keys en orden alfabético"


# ---------------------------------------------------------------------------
# 6. prune_soft_cover_candidates.py: rejected + ledger (#9, política unificada)
# ---------------------------------------------------------------------------

def test_prune_marks_soft_candidate_as_rejected_with_ledger(tmp_path, monkeypatch, ledger_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    soft_file = "soft.jpg"
    _make_soft_gradient(images_dir / soft_file)

    preview_path = tmp_path / "cover_preview.json"
    entries = [{
        "slug": "s1",
        "title": "Test",
        "old_pixels": 10_000,
        "candidates": [{
            "status": "pending",
            "action": "replace_cover",
            "new_url": "https://x/soft.jpg",
            "new_image": soft_file,
            "domain": "x.com",
        }],
    }]
    preview_path.write_text(json.dumps(entries), encoding="utf-8")

    monkeypatch.setattr(psc, "COVER_PREVIEW", preview_path)
    monkeypatch.setattr(psc, "IMAGES", images_dir)
    monkeypatch.setattr(sys, "argv", ["prune_soft_cover_candidates.py"])

    rc = psc.main()
    assert rc == 0

    updated = json.loads(preview_path.read_text(encoding="utf-8"))
    assert len(updated) == 1
    cand = updated[0]["candidates"][0]
    # Hallazgo #9: antes esto ELIMINABA la candidata en silencio; ahora se
    # conserva marcada rejected, igual que revalidate_cover_preview.py.
    assert cand["status"] == "rejected"
    assert cand["reject_reason"] == "soft_image"

    # Y quedó registrada en el ledger de rechazos (antes: sin rastro).
    ledger_rows = [json.loads(l) for l in ledger_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(ledger_rows) == 1
    assert ledger_rows[0]["slug"] == "s1"
    assert ledger_rows[0]["reason"] == "soft_image"

    # backup_and_rotate corrió (hallazgo #5) — ya no el slot fijo .bak-prune-soft.
    assert (tmp_path / "backups" / "cover_preview.json").exists()


def test_prune_dry_run_does_not_touch_ledger_or_file(tmp_path, monkeypatch, ledger_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    soft_file = "soft.jpg"
    _make_soft_gradient(images_dir / soft_file)

    preview_path = tmp_path / "cover_preview.json"
    original = [{
        "slug": "s1", "title": "Test", "old_pixels": 10_000,
        "candidates": [{"status": "pending", "action": "replace_cover",
                        "new_url": "https://x/soft.jpg", "new_image": soft_file, "domain": "x.com"}],
    }]
    preview_path.write_text(json.dumps(original), encoding="utf-8")

    monkeypatch.setattr(psc, "COVER_PREVIEW", preview_path)
    monkeypatch.setattr(psc, "IMAGES", images_dir)
    monkeypatch.setattr(sys, "argv", ["prune_soft_cover_candidates.py", "--dry-run"])

    rc = psc.main()
    assert rc == 0
    assert json.loads(preview_path.read_text(encoding="utf-8")) == original
    assert not ledger_path.exists()


# ---------------------------------------------------------------------------
# 7. GC de candidatas huérfanas en sync_preview() (#14)
# ---------------------------------------------------------------------------

def test_sync_preview_gc_removes_unreferenced_candidate_file(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    orphan_file = "orphan.jpg"
    _make_img(images_dir / orphan_file)

    # Slug no existe → Regla 1 dropea la entry entera; la candidata queda huérfana.
    entry = {
        "slug": "gone",
        "old_image": "",
        "candidates": [{"status": "pending", "action": "replace_cover",
                        "new_url": "https://x/orphan.jpg", "new_image": orphan_file}],
    }
    synced, stats = scp.sync_preview([entry], {}, images_dir, write_ledger=True)

    assert synced == []
    assert stats["gc_orphans_removed"] == 1
    assert not (images_dir / orphan_file).exists()


def test_sync_preview_gc_never_deletes_file_used_by_real_item(tmp_path):
    """Guard de seguridad: si el archivo de la candidata huérfana coincide con
    el `local` de un item REAL (mismo filename), NUNCA se borra."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    shared_file = "shared.jpg"
    _make_img(images_dir / shared_file)

    # Item real cuya portada usa el MISMO filename que la candidata huérfana.
    real_item = {"slug": "real", "images": [{"url": "https://x/cover.jpg", "local": shared_file,
                                              "kind": "gallery"}]}
    items_by_slug = {"real": real_item}

    entry = {
        "slug": "gone",  # no existe en items_by_slug → se dropea
        "old_image": "",
        "candidates": [{"status": "pending", "action": "replace_cover",
                        "new_url": "https://x/shared.jpg", "new_image": shared_file}],
    }
    synced, stats = scp.sync_preview([entry], items_by_slug, images_dir, write_ledger=True)

    assert synced == []
    assert stats["gc_orphans_removed"] == 0
    assert (images_dir / shared_file).exists()  # el archivo del item real sigue ahí


def test_sync_preview_gc_never_deletes_file_used_by_sources_image_local(tmp_path):
    """Guard: un archivo de candidata podada cuyo filename está referenciado
    SOLO por un `sources[].image_local` de un item (ref legacy per-fuente, ~5.9k
    items del corpus la tienen poblada) tampoco se borra — misma protección que
    el GC de mirror_images (revisión del orquestador 2026-07-08)."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    shared_file = "legacy_source_ref.jpg"
    _make_img(images_dir / shared_file)

    # Item real que NO usa el archivo en images[], pero SÍ en sources[].image_local.
    real_item = {
        "slug": "real",
        "images": [{"url": "https://x/cover.jpg", "local": "other.jpg", "kind": "gallery"}],
        "sources": [
            "garbage-non-dict-entry",  # isinstance guard: entries no-dict se ignoran
            {"name": "tienda", "url": "https://t/x", "image_local": shared_file},
        ],
    }
    items_by_slug = {"real": real_item}

    entry = {
        "slug": "gone",  # no existe → se dropea, su candidata queda "huérfana"
        "old_image": "",
        "candidates": [{"status": "pending", "action": "replace_cover",
                        "new_url": "https://x/legacy.jpg", "new_image": shared_file}],
    }
    synced, stats = scp.sync_preview([entry], items_by_slug, images_dir, write_ledger=True)

    assert synced == []
    assert stats["gc_orphans_removed"] == 0
    assert (images_dir / shared_file).exists()  # la ref de sources[] lo protege


def test_sync_preview_gc_skipped_in_probe_mode():
    """write_ledger=False (probe puro, usado por revalidate) nunca borra archivos."""
    images_dir = None  # ni siquiera necesitamos un dir real: si tocara disco, explotaría
    entry = {
        "slug": "gone",
        "old_image": "",
        "candidates": [{"status": "pending", "action": "replace_cover",
                        "new_url": "https://x/o.jpg", "new_image": "o.jpg"}],
    }
    # Pasamos un Path que no existe — si el código intentara resolverlo se rompería
    # solo si tratara de listar/crear el dir; unlink/exists sobre un path inexistente
    # simplemente no encuentra nada, así que esto también verifica que no explota.
    from pathlib import Path as _P
    fake_dir = _P("/nonexistent-dir-for-probe-test")
    synced, stats = scp.sync_preview([entry], {}, fake_dir, write_ledger=False)
    assert synced == []
    assert stats["gc_orphans_removed"] == 0
