"""tests/test_remediacion_20260708.py — paquete R (remediación) de la auditoría
Fable 2026-07-08. Los 5 hallazgos que el cross-check de cobertura confirmó como
FALTANTES:

  1. (#7) Matching cola↔catálogo + ledger por IDENTIDAD SECUNDARIA (url canónica
     del item, estable a re-slugs). Un re-slug ya no pierde las decisiones del
     owner ni neutraliza el veto del ledger.
  2. (#14) Lock cross-proceso (fcntl.flock) sobre cover_preview.json:
     `preview_write_lock` es reentrante en el mismo hilo y excluye entre procesos.
  3. (#9) `--include-upscaled` deja de ser no-op: `_process_item` ya no
     early-returnea para un item upscaleado cuando el flag está encendido.
  4. (#19) La búsqueda manual del gestor filtra contra el ledger de rechazos
     (misma fuente única: `is_rejected_candidate`).
  5. (nit) `normalize_release_dates._DMY_FAMILY` exige el MISMO separador
     (backreference) — "12-05/2024" ya no dispara un falso "[WARN] rango inválido".

Todos los tests operan sobre tmp_path; no tocan data/ real.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import fetch_better_covers as fbc  # noqa: E402
import sync_cover_preview as scp  # noqa: E402
import normalize_release_dates as nrd  # noqa: E402

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jpeg(path: Path, size=(300, 300)) -> None:
    """JPEG con detalle real (ruido) — NO blando, pasa _is_soft_image."""
    import random
    w, h = size
    img = Image.new("RGB", (w, h))
    px = img.load()
    rnd = random.Random(42)
    for y in range(h):
        for x in range(w):
            px[x, y] = (rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255))
    img.save(path, "JPEG", quality=92)


def _make_png_upscaled(path: Path, size=(600, 600)) -> None:
    """PNG grande (>200k px) → _is_upscaled True (px>=200k y termina en .png)."""
    Image.new("RGB", size, (210, 200, 230)).save(path, "PNG")


# ===========================================================================
# 1. (#7) Identidad secundaria — re-slug, backfill, ledger, guard 20%
# ===========================================================================

def _item(slug: str, url: str, local: str) -> dict:
    return {
        "slug": slug,
        "url": url,
        "images": [{"url": "http://cdn/x.png", "local": local, "kind": "gallery"}],
    }


def test_reslug_entry_migrates_not_pruned(tmp_path):
    """Entry con slug VIEJO + item con slug NUEVO y misma url canónica → la entry
    migra el slug (no se poda) y su decisión (approved) sobrevive."""
    images = tmp_path / "images"
    images.mkdir()
    _make_png_upscaled(images / "cov.png", (400, 400))  # 160k px, cualquier cosa sirve

    canon_url = "https://tienda/producto/berserk-deluxe-1"
    item = _item("berserk-deluxe-vol-1-nuevo-slug", canon_url, "cov.png")
    items_by_slug = {item["slug"]: item}

    entry = {
        "slug": "berserk-deluxe-vol-1-VIEJO",  # slug viejo, ya no existe
        "url": canon_url,
        "old_url": "http://cdn/x.png",
        "old_image": "cov.png",
        "candidates": [{
            "new_url": "http://web/better.jpg",
            "new_image": "better.jpg",
            "action": "replace_cover",
            "status": "approved",       # DECISIÓN del owner que debe sobrevivir
            "target": "",
        }],
    }
    synced, stats = scp.sync_preview([entry], items_by_slug, images, write_ledger=False)

    assert stats["dropped_missing_item"] == 0
    assert stats["slug_migrated"] == 1
    assert len(synced) == 1
    assert synced[0]["slug"] == "berserk-deluxe-vol-1-nuevo-slug"  # migrado
    assert synced[0]["candidates"][0]["status"] == "approved"       # decisión intacta


def test_legacy_entry_backfills_url_on_slug_match(tmp_path):
    """Entry legacy SIN url pero con slug que matchea → url se backfillea del item."""
    images = tmp_path / "images"
    images.mkdir()
    # Portada CHICA (<90k px) para que la candidata pending NO se pode (si no, la
    # entry quedaría vacía y este test mediría otra cosa).
    Image.new("RGB", (200, 200), (200, 30, 30)).save(images / "cov.png", "PNG")

    canon_url = "https://tienda/producto/one-piece-1"
    item = _item("one-piece-vol-1", canon_url, "cov.png")
    entry = {
        "slug": "one-piece-vol-1",  # matchea por slug
        # sin "url" (entry vieja)
        "old_url": "http://cdn/x.png",
        "old_image": "cov.png",
        "candidates": [{"new_url": "http://web/b.jpg", "new_image": "b.jpg",
                        "action": "replace_cover", "status": "pending", "target": ""}],
    }
    synced, stats = scp.sync_preview([entry], {item["slug"]: item}, images, write_ledger=False)
    assert stats["url_backfilled"] == 1
    assert synced[0]["url"] == canon_url


def test_truly_deleted_entry_still_pruned(tmp_path):
    """Sin slug ni url que resuelva → se poda (Regla 1 intacta)."""
    images = tmp_path / "images"
    images.mkdir()
    entry = {
        "slug": "no-existe",
        "url": "https://tienda/no-existe",
        "candidates": [{"new_url": "http://web/b.jpg", "new_image": "",
                        "action": "replace_cover", "status": "pending", "target": ""}],
    }
    synced, stats = scp.sync_preview([entry], {}, images, write_ledger=False)
    assert stats["dropped_missing_item"] == 1
    assert synced == []


def test_ledger_veto_survives_reslug_via_item_url():
    """El ledger vetó una URL bajo el slug viejo; tras el re-slug, el veto sigue
    vivo por la url canónica (item_url), no por el slug."""
    ledger = [{
        "slug": "slug-viejo",
        "url": "https://tienda/producto/x",
        "rejected_url": "http://web/malo.jpg",
        "reason": "otro_tomo",
    }]
    # Con el slug NUEVO pero la misma url canónica → sigue vetada.
    assert fbc.is_rejected_candidate(
        "slug-nuevo", "http://web/malo.jpg", None, ledger,
        item_url="https://tienda/producto/x") is True
    # Sin item_url y con slug nuevo → NO matchea (comportamiento previo).
    assert fbc.is_rejected_candidate(
        "slug-nuevo", "http://web/malo.jpg", None, ledger) is False
    # Compat hacia atrás: match por slug sigue funcionando.
    assert fbc.is_rejected_candidate(
        "slug-viejo", "http://web/malo.jpg", None, ledger) is True


def test_legacy_ledger_record_without_url_still_slug_only():
    """Record legacy sin `url` → sólo veta por slug (item_url no lo rescata)."""
    ledger = [{"slug": "s1", "rejected_url": "http://web/x.jpg", "reason": None}]
    assert fbc.is_rejected_candidate("s1", "http://web/x.jpg", None, ledger) is True
    assert fbc.is_rejected_candidate(
        "s2", "http://web/x.jpg", None, ledger, item_url="https://t/p") is False


def test_catalog_is_sane_counts_url_rescued(tmp_path):
    """Un re-slug MASIVO (todos los slugs cambiaron) no dispara el guard del 20%
    mientras las urls canónicas sigan resolviendo."""
    images = tmp_path / "images"
    items_by_slug = {}
    preview = []
    for i in range(10):
        url = f"https://tienda/p/{i}"
        items_by_slug[f"nuevo-{i}"] = {"slug": f"nuevo-{i}", "url": url, "images": []}
        preview.append({"slug": f"viejo-{i}", "url": url, "candidates": []})
    ok, reason = scp.catalog_is_sane(preview, items_by_slug, malformed_lines=0)
    assert ok is True, reason

    # Sin url canónica, los mismos slugs viejos SÍ superan el 20% → aborta.
    preview_no_url = [{"slug": f"viejo-{i}", "candidates": []} for i in range(10)]
    ok2, _ = scp.catalog_is_sane(preview_no_url, items_by_slug, malformed_lines=0)
    assert ok2 is False


def test_ledger_record_from_candidate_carries_url(tmp_path):
    """El record del ledger que arma sync incluye la url canónica de la entry."""
    entry = {"slug": "s", "url": "https://t/p", "old_pixels": 100}
    cand = {"new_url": "http://web/r.jpg", "action": "replace_cover", "target": "",
            "reject_reason": "otro_tomo"}
    rec = scp._ledger_record_from_candidate(entry, cand, tmp_path)
    assert rec["url"] == "https://t/p"
    assert rec["rejected_url"] == "http://web/r.jpg"


# ===========================================================================
# 2. (#14) Lock cross-proceso del preview
# ===========================================================================

def test_preview_write_lock_reentrant(tmp_path):
    """Reentrante en el mismo hilo (no se auto-bloquea)."""
    p = tmp_path / "cover_preview.json"
    with fbc.preview_write_lock(p, timeout=1.0):
        with fbc.preview_write_lock(p, timeout=1.0):
            pass  # no debe colgar ni levantar


@pytest.mark.skipif(fbc.fcntl is None, reason="fcntl no disponible (Windows)")
def test_preview_write_lock_excludes_across_processes(tmp_path):
    """Un proceso externo toma el lock y lo retiene; este proceso NO lo adquiere
    dentro del timeout corto → TimeoutError (exclusión cross-proceso real)."""
    p = tmp_path / "cover_preview.json"
    marker = tmp_path / "locked.marker"
    code = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(_ROOT / 'scripts')!r})
        sys.path.insert(0, {str(_ROOT / 'scripts' / 'retrofit')!r})
        import fetch_better_covers as fbc
        from pathlib import Path
        with fbc.preview_write_lock(Path({str(p)!r}), timeout=5.0):
            Path({str(marker)!r}).write_text("locked")
            time.sleep(3)
    """)
    proc = subprocess.Popen([sys.executable, "-c", code])
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists(), "el subproceso no tomó el lock"
        with pytest.raises(TimeoutError):
            with fbc.preview_write_lock(p, timeout=0.3):
                pass
    finally:
        proc.wait(timeout=10)
    # Tras liberarse, este proceso SÍ lo adquiere.
    with fbc.preview_write_lock(p, timeout=2.0):
        pass


# ===========================================================================
# 3. (#9) --include-upscaled deja de ser no-op
# ===========================================================================

def test_include_upscaled_bypasses_early_return(tmp_path, monkeypatch):
    """Un item upscaleado (PNG >200k px) supera min_pixels; sin el flag
    `_process_item` early-returnea (None), con el flag procesa candidatas y
    devuelve un reemplazo real más chico (effective_gain=0)."""
    images = tmp_path / "images"
    images.mkdir()
    _make_png_upscaled(images / "up.png", (600, 600))  # 360k px, pastel
    cand_bytes = None
    cand_path = tmp_path / "cand.jpg"
    _make_jpeg(cand_path, (300, 300))  # 90k px, con detalle real
    cand_bytes = cand_path.read_bytes()

    item = {
        "slug": "up-item",
        "url": "https://t/up",
        "isbn": "9781234567897",
        "images": [{"url": "http://cdn/up.png", "local": "up.png", "kind": "gallery"}],
    }

    monkeypatch.setattr(fbc, "_candidates_from_isbn", lambda isbn, s: ["http://web/cand.jpg"])
    monkeypatch.setattr(fbc, "_candidates_from_isbn_openlibrary", lambda isbn, s: [])
    monkeypatch.setattr(fbc, "_candidates_from_isbn_google_books", lambda isbn, s: [])
    monkeypatch.setattr(fbc, "_fetch", lambda url, s, **k: cand_bytes)
    monkeypatch.setattr(fbc, "_same_cover", lambda a, b, d: True)

    import requests
    session = requests.Session()

    common = dict(
        session=session, images_dir=images, min_pixels=fbc.DEFAULT_MIN_PIXELS,
        min_gain=fbc.DEFAULT_MIN_GAIN, max_hash_dist=fbc.DEFAULT_MAX_HASH_DIST,
        no_search=False, serper_key="", tavily_key="", dry_run=True, verbose=False,
    )
    # Sin el flag → early-return (imagen "grande" no se toca).
    r_off = fbc._process_item(item, include_upscaled=False, **common)
    assert r_off is None
    # Con el flag → procesa y devuelve un reemplazo real.
    r_on = fbc._process_item(item, include_upscaled=True, **common)
    assert r_on is not None
    assert r_on["new_url"] == "http://web/cand.jpg"


# ===========================================================================
# 4. (#19) La búsqueda manual filtra contra el ledger
# ===========================================================================

def test_manual_search_filter_excludes_and_counts():
    """Replica el contrato del handler serve `_handle_image_search`: excluye las
    URLs vetadas por el ledger (por slug o url canónica) y cuenta las ocultas."""
    ledger = [
        {"slug": "s1", "url": "https://t/p1", "rejected_url": "http://web/a.jpg",
         "reason": "otra_edicion"},
    ]
    deduped = ["http://web/a.jpg", "http://web/b.jpg", "http://web/c.jpg"]
    slug, item_url = "s1", "https://t/p1"
    hidden = 0
    kept = []
    for u in deduped:
        if fbc.is_rejected_candidate(slug, u, None, ledger, item_url=item_url):
            hidden += 1
        else:
            kept.append(u)
    assert hidden == 1
    assert "http://web/a.jpg" not in kept
    assert kept == ["http://web/b.jpg", "http://web/c.jpg"]


# ===========================================================================
# 5. (nit) _DMY_FAMILY exige el mismo separador
# ===========================================================================

def test_dmy_family_requires_matching_separator():
    assert nrd._DMY_FAMILY.match("12/05/2024")
    assert nrd._DMY_FAMILY.match("12.05.2024")
    assert nrd._DMY_FAMILY.match("12-05-2024")
    # separadores mixtos → NO es DMY legítimo
    assert nrd._DMY_FAMILY.match("12-05/2024") is None
    assert nrd._DMY_FAMILY.match("12/05.2024") is None


def test_mixed_separator_not_flagged_invalid(tmp_path, monkeypatch, capsys):
    """"12-05/2024" (separadores mixtos) NO debe caer en el WARN de rangos
    inválidos; el DMY realmente inválido (32/05/2024) sí."""
    items = tmp_path / "items.jsonl"
    rows = [
        {"slug": "mixed-sep", "url": "u1", "release_date": "12-05/2024"},
        {"slug": "bad-invalid", "url": "u2", "release_date": "32/05/2024"},
        {"slug": "good-dmy", "url": "u3", "release_date": "12/05/2024"},
    ]
    items.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["nrd", "--input", str(items), "--dry-run"])
    rc = nrd.main()
    assert rc == 0
    out = capsys.readouterr().out
    # Bloque del WARN de rangos inválidos.
    assert "rangos inválidos" in out
    warn_block = out[out.find("rangos inválidos"):]
    if "[REPORT]" in warn_block:
        warn_block = warn_block[:warn_block.find("[REPORT]")]
    assert "bad-invalid" in warn_block          # el inválido real sí se reporta
    assert "mixed-sep" not in warn_block         # el de separadores mixtos NO
