"""tests/test_audit_wo_e.py — WO-E de la auditoría post-scrape.

Cubre lo testeable en Python de los 5 cambios de WO-E (dominio: scrape_delta.sh
/ scrape_full.sh / build_web.py / serve.py / cover-preview.html):

  1. Restore ante corpus inválido (scrape_delta/full.sh) — sólo bash, se
     verifica con `bash -n` (ver skill/README del WO), no acá.
  2. Gate de validate_corpus en build_web.py (abortar en violaciones DURAS,
     --force como override consciente).
  3. Lock de scrape en curso en serve.py (423 en los endpoints que escriben
     items.jsonl mientras data/.scrape.lock está activo).
  4. approved_unapplied en GET /api/cover-preview (P24) — contador
     autoritativo de candidatas aprobadas sin aplicar.

No se corre build_web.py ni los .sh de verdad; el subprocess de
validate_corpus.py se mockea (--file es una interfaz que otro agente está
agregando en paralelo — se asume, no se ejerce el binario real).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import build_web


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_serve():
    """Módulo serve.py fresco (spec_from_file_location), mismo patrón que
    tests/test_extraction.py — cada test necesita mutar atributos globales
    (ITEMS_PATH, ROOT, _SCRAPE_LOCK_DIR) sin filtrar estado a otros tests."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("serve_mod_test_wo_e", "scripts/serve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _html_with_tag() -> str:
    return '<html><script id="manga-data" type="application/json">[]</script></html>'


# ---------------------------------------------------------------------------
# 2. GATE en build_web.py
# ---------------------------------------------------------------------------

def test_build_web_gate_blocks_hard_violations(tmp_path, monkeypatch):
    """rc=2 (violaciones DURAS) del validador → build_web ABORTA, no toca el HTML."""
    calls = []

    def fake_validate(path):
        calls.append(path)
        return 2

    monkeypatch.setattr(build_web, "_run_validate_corpus", fake_validate)

    items = tmp_path / "items.jsonl"
    items.write_text('{"a":1}\n', encoding="utf-8")
    out_html = tmp_path / "index.html"
    original = _html_with_tag()
    out_html.write_text(original, encoding="utf-8")

    monkeypatch.setattr(sys, "argv", [
        "build_web.py", "--input", str(items), "--output", str(out_html),
    ])
    rc = build_web.main()

    assert rc == 2
    assert calls == [items]
    assert out_html.read_text(encoding="utf-8") == original, "el gate debe abortar ANTES de escribir el HTML"


def test_build_web_gate_blocks_validator_error(tmp_path, monkeypatch):
    """rc≠0 y rc≠2 (el propio validador crasheó) también aborta, por precaución."""
    monkeypatch.setattr(build_web, "_run_validate_corpus", lambda path: 1)

    items = tmp_path / "items.jsonl"
    items.write_text('{"a":1}\n', encoding="utf-8")
    out_html = tmp_path / "index.html"
    out_html.write_text(_html_with_tag(), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", [
        "build_web.py", "--input", str(items), "--output", str(out_html),
    ])
    rc = build_web.main()
    assert rc == 1


def test_build_web_gate_force_bypasses_validation(tmp_path, monkeypatch):
    """--force saltea el gate por completo: ni siquiera se llama al validador."""
    def boom(path):
        raise AssertionError("--force no debería invocar validate_corpus")

    monkeypatch.setattr(build_web, "_run_validate_corpus", boom)

    items = tmp_path / "items.jsonl"
    items.write_text('{"a":1}\n', encoding="utf-8")
    out_html = tmp_path / "index.html"
    out_html.write_text(_html_with_tag(), encoding="utf-8")

    # --clear evita el export de aliases (que tocaría data/series_aliases.json
    # real si no se mockea); alcanza para probar que el gate no corrió.
    monkeypatch.setattr(sys, "argv", [
        "build_web.py", "--input", str(items), "--output", str(out_html),
        "--force", "--clear",
    ])
    rc = build_web.main()
    assert rc == 0


def test_build_web_gate_skips_when_input_missing(tmp_path, monkeypatch):
    """Si --input no existe (repo nuevo, sin scrape todavía), el gate se
    saltea con un warning en vez de fallar — no hay nada que validar."""
    calls = []
    monkeypatch.setattr(build_web, "_run_validate_corpus", lambda path: calls.append(path) or 0)

    missing = tmp_path / "no-existe.jsonl"
    out_html = tmp_path / "index.html"
    out_html.write_text(_html_with_tag(), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", [
        "build_web.py", "--input", str(missing), "--output", str(out_html), "--clear",
    ])
    rc = build_web.main()
    assert rc == 0
    assert calls == [], "no debe invocar validate_corpus si --input no existe"


def test_build_web_gate_passes_through_when_valid(tmp_path, monkeypatch):
    """rc=0 (corpus válido) → el gate deja pasar y el resto de build_web corre normal."""
    calls = []
    monkeypatch.setattr(build_web, "_run_validate_corpus", lambda path: calls.append(path) or 0)

    items = tmp_path / "items.jsonl"
    items.write_text('{"a":1}\n', encoding="utf-8")
    out_html = tmp_path / "index.html"
    out_html.write_text(_html_with_tag(), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", [
        "build_web.py", "--input", str(items), "--output", str(out_html), "--clear",
    ])
    rc = build_web.main()
    assert rc == 0
    assert calls == [items]
    # --clear deja el embed vacío (ya lo estaba) — confirma que llegó hasta el final.
    assert '<script id="manga-data" type="application/json">[]</script>' in out_html.read_text(encoding="utf-8")


def test_build_web_help_is_sane():
    """--help no debe crashear y debe listar el flag nuevo (chequeo de humo)."""
    result = subprocess.run(
        [sys.executable, "scripts/build_web.py", "--help"],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0
    assert "--force" in result.stdout


# ---------------------------------------------------------------------------
# 3. Lock de scrape en curso (serve.py)
# ---------------------------------------------------------------------------

def test_scrape_lock_pid_none_when_no_lock_dir(tmp_path):
    serve = _load_serve()
    serve._SCRAPE_LOCK_DIR = tmp_path / ".scrape.lock"  # no existe
    assert serve._scrape_lock_pid() is None


def test_scrape_lock_pid_returns_pid_when_alive(tmp_path):
    serve = _load_serve()
    lock_dir = tmp_path / ".scrape.lock"
    lock_dir.mkdir()
    (lock_dir / "pid").write_text(str(os.getpid()), encoding="utf-8")
    serve._SCRAPE_LOCK_DIR = lock_dir
    assert serve._scrape_lock_pid() == os.getpid()


def test_scrape_lock_pid_none_when_stale(tmp_path):
    """PID de un proceso que ya terminó → lock stale → tratado como 'sin lock'
    (mismo criterio que acquire_lock() en los .sh: kill -0 falla)."""
    serve = _load_serve()
    # Un proceso que arranca y termina al toque: su PID queda garantizado muerto.
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_pid = proc.pid
    proc.wait(timeout=10)

    lock_dir = tmp_path / ".scrape.lock"
    lock_dir.mkdir()
    (lock_dir / "pid").write_text(str(dead_pid), encoding="utf-8")
    serve._SCRAPE_LOCK_DIR = lock_dir
    assert serve._scrape_lock_pid() is None


def test_scrape_lock_pid_none_on_garbage_pid_file(tmp_path):
    serve = _load_serve()
    lock_dir = tmp_path / ".scrape.lock"
    lock_dir.mkdir()
    (lock_dir / "pid").write_text("not-a-number", encoding="utf-8")
    serve._SCRAPE_LOCK_DIR = lock_dir
    assert serve._scrape_lock_pid() is None


def test_reject_if_scrape_locked_responds_423_and_blocks(tmp_path):
    serve = _load_serve()
    lock_dir = tmp_path / ".scrape.lock"
    lock_dir.mkdir()
    (lock_dir / "pid").write_text(str(os.getpid()), encoding="utf-8")
    serve._SCRAPE_LOCK_DIR = lock_dir

    h = object.__new__(serve.MangaWatchHandler)
    responses = []
    h._json = lambda status, payload: responses.append((status, payload))

    blocked = h._reject_if_scrape_locked()
    assert blocked is True
    assert len(responses) == 1
    status, payload = responses[0]
    assert status == 423
    assert payload["pid"] == os.getpid()
    assert "error" in payload


def test_reject_if_scrape_locked_false_and_silent_when_unlocked(tmp_path):
    serve = _load_serve()
    serve._SCRAPE_LOCK_DIR = tmp_path / ".scrape.lock"
    h = object.__new__(serve.MangaWatchHandler)
    h._json = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debería responder sin lock"))
    assert h._reject_if_scrape_locked() is False


def test_handle_approve_blocked_while_locked_does_not_write(tmp_path):
    """Regresión del lost-update: con el scrape lock activo, /api/approve debe
    responder 423 SIN tocar items.jsonl (ni siquiera intenta leerlo/parsear
    el body — el guard es la primera línea del handler)."""
    serve = _load_serve()
    lock_dir = tmp_path / ".scrape.lock"
    lock_dir.mkdir()
    (lock_dir / "pid").write_text(str(os.getpid()), encoding="utf-8")
    serve._SCRAPE_LOCK_DIR = lock_dir

    items = tmp_path / "items.jsonl"
    original = json.dumps({"url": "https://x", "cluster_key": "url:https://x"}) + "\n"
    items.write_text(original, encoding="utf-8")
    serve.ITEMS_PATH = items

    h = object.__new__(serve.MangaWatchHandler)
    responses = []
    h._json = lambda status, payload: responses.append((status, payload))

    h._handle_approve()

    assert len(responses) == 1
    assert responses[0][0] == 423
    assert items.read_text(encoding="utf-8") == original, "no debe escribir items.jsonl bajo lock"


# ---------------------------------------------------------------------------
# 4. approved_unapplied (P24)
# ---------------------------------------------------------------------------

def test_count_approved_unapplied_multi_candidate_schema():
    serve = _load_serve()
    entries = [
        {"slug": "a", "candidates": [{"status": "approved"}, {"status": "pending"}]},
        {"slug": "b", "candidates": [{"status": "rejected"}]},
        {"slug": "c", "candidates": [{"status": "approved"}, {"status": "approved"}]},
    ]
    assert serve._count_approved_unapplied(entries) == 3


def test_count_approved_unapplied_legacy_flat_schema():
    serve = _load_serve()
    entries = [
        {"slug": "a", "status": "approved"},
        {"slug": "b", "status": "pending"},
    ]
    assert serve._count_approved_unapplied(entries) == 1


def test_count_approved_unapplied_empty():
    serve = _load_serve()
    assert serve._count_approved_unapplied([]) == 0


def test_cover_preview_get_reports_approved_unapplied(tmp_path, monkeypatch):
    serve = _load_serve()
    serve.ROOT = tmp_path
    (tmp_path / "data").mkdir()

    items = tmp_path / "data" / "items.jsonl"
    items.write_text(json.dumps({"slug": "s1", "url": "https://x"}) + "\n", encoding="utf-8")
    serve.ITEMS_PATH = items

    preview_path = tmp_path / "data" / "cover_preview.json"
    preview_path.write_text(json.dumps([
        {"slug": "s1", "candidates": [{"status": "approved", "new_url": "https://y/img.jpg"}]},
    ]), encoding="utf-8")

    # Passthrough: evita depender de PIL / archivos de imagen reales para el sync.
    monkeypatch.setattr(serve, "_sync_preview", lambda preview, items_by_slug, images_dir: (preview, {}))

    h = object.__new__(serve.MangaWatchHandler)
    responses = []
    h._json = lambda status, payload: responses.append((status, payload))
    h._handle_cover_preview_get()

    assert len(responses) == 1
    status, body = responses[0]
    assert status == 200
    assert body["approved_unapplied"] == 1
    assert len(body["entries"]) == 1


def test_cover_preview_get_zero_when_no_preview_file(tmp_path):
    serve = _load_serve()
    serve.ROOT = tmp_path
    (tmp_path / "data").mkdir()

    h = object.__new__(serve.MangaWatchHandler)
    responses = []
    h._json = lambda status, payload: responses.append((status, payload))
    h._handle_cover_preview_get()

    assert len(responses) == 1
    status, body = responses[0]
    assert status == 200
    assert body["approved_unapplied"] == 0
    assert body["entries"] == []
