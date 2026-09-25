"""Tests para scripts/retrofit/absorb_spool.py.

Post-mortem 2026-08-22/24 (Fix 2): el timeout de una corrida mató el proceso
DESPUÉS de que `mirror_candidate_images` corriera pero ANTES del `append_jsonl`
final — 274 items quedaron varados en `data/items.jsonl.spool`, invisibles
para la Fase 3 completa (sus retrofits hacen dump-completo con
`write_items_atomic`/`write_lines_atomic`, que NUNCA leen el spool). Este
script absorbe cualquier spool huérfano vía `append_jsonl(items_path, [])`
(mismo patrón que `tests/test_perf_lock_20260708.py`), como primer paso
explícito de la Fase 3.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import manga_watch as mw
from scripts.retrofit import absorb_spool


def _row(url: str, **kw) -> dict:
    r = {"url": url, "title": kw.get("title", "T"), "detected_at": kw.get("detected_at", "2026-01-01"),
         "score": kw.get("score", 50), "sources": kw.get("sources", [])}
    r.update(kw)
    return r


def test_absorb_spool_with_pending_lines(tmp_path, monkeypatch, capsys):
    """Spool huérfano con líneas: se absorbe, queda vacío items.jsonl + spool, y
    se borra el archivo .spool."""
    items_path = tmp_path / "items.jsonl"
    items_path.write_text(json.dumps(_row("http://x/1"), sort_keys=True) + "\n", encoding="utf-8")

    mw._append_spool(items_path, [_row("http://x/2", title="new")])
    spool_path = mw._items_spool_path(items_path)
    assert spool_path.exists()

    monkeypatch.setattr(sys, "argv", ["absorb_spool.py", "--items", str(items_path)])
    rc = absorb_spool.main()
    assert rc == 0

    assert not spool_path.exists()
    urls = {json.loads(l)["url"] for l in items_path.read_text(encoding="utf-8").splitlines() if l.strip()}
    assert urls == {"http://x/1", "http://x/2"}

    out = capsys.readouterr().out
    assert "spool huérfano encontrado" in out
    assert "absorbidas 1 filas" in out


def test_absorb_spool_no_spool_is_noop(tmp_path, monkeypatch, capsys):
    """Sin spool pendiente: no-op limpio, items.jsonl queda intacto."""
    items_path = tmp_path / "items.jsonl"
    original = json.dumps(_row("http://x/1"), sort_keys=True) + "\n"
    items_path.write_text(original, encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["absorb_spool.py", "--items", str(items_path)])
    rc = absorb_spool.main()
    assert rc == 0
    assert items_path.read_text(encoding="utf-8") == original

    out = capsys.readouterr().out
    assert "sin spool pendiente" in out


def test_absorb_spool_dry_run_does_not_absorb(tmp_path, monkeypatch, capsys):
    """--dry-run reporta el spool pendiente pero no lo absorbe (queda intacto)."""
    items_path = tmp_path / "items.jsonl"
    items_path.write_text(json.dumps(_row("http://x/1"), sort_keys=True) + "\n", encoding="utf-8")
    mw._append_spool(items_path, [_row("http://x/2")])
    spool_path = mw._items_spool_path(items_path)

    monkeypatch.setattr(sys, "argv", ["absorb_spool.py", "--items", str(items_path), "--dry-run"])
    rc = absorb_spool.main()
    assert rc == 0
    assert spool_path.exists()  # sigue ahí, no se tocó

    out = capsys.readouterr().out
    assert "no se absorbe nada" in out


def test_absorb_spool_missing_items_file_creates_it(tmp_path, monkeypatch):
    """Un spool huérfano sin items.jsonl (corpus borrado/nunca existió) igual
    se absorbe — append_jsonl crea el archivo."""
    items_path = tmp_path / "items.jsonl"  # no existe
    mw._append_spool(items_path, [_row("http://x/1")])
    spool_path = mw._items_spool_path(items_path)
    assert spool_path.exists()

    monkeypatch.setattr(sys, "argv", ["absorb_spool.py", "--items", str(items_path)])
    rc = absorb_spool.main()
    assert rc == 0
    assert not spool_path.exists()
    assert items_path.exists()
    urls = {json.loads(l)["url"] for l in items_path.read_text(encoding="utf-8").splitlines() if l.strip()}
    assert urls == {"http://x/1"}


def test_conflict_only_recovery_retries_without_spool(tmp_path, monkeypatch):
    items = tmp_path / "items.jsonl"
    shared = "https://shop.test/shared"
    items.write_text(json.dumps(_row("https://publisher.test/1", sources=[{"url": shared}])) + "\n")
    ledger = items.with_name(items.name + ".conflicts")
    ledger.write_text(json.dumps(_row(shared, title="Recovered title")) + "\n")
    monkeypatch.setattr(sys, "argv", ["absorb_spool.py", "--items", str(items)])
    assert absorb_spool.main() == 0
    assert mw.read_jsonl_strict(ledger) == []
    assert mw.read_jsonl_strict(items)[0]["title"] == "Recovered title"


def test_conflict_only_unresolved_returns_failure(tmp_path, monkeypatch):
    items = tmp_path / "items.jsonl"
    shared = "https://shop.test/shared"
    rows = [_row(f"https://publisher.test/{i}", sources=[{"url": shared}]) for i in [1, 2]]
    items.write_text("".join(json.dumps(r) + "\n" for r in rows))
    ledger = items.with_name(items.name + ".conflicts")
    pending = [_row(shared)]
    ledger.write_text(json.dumps(pending[0]) + "\n")
    monkeypatch.setattr(sys, "argv", ["absorb_spool.py", "--items", str(items)])
    assert absorb_spool.main() == 1
    assert mw.read_jsonl_strict(ledger) == pending
    assert len(mw.read_jsonl_strict(items)) == 2


def test_conflict_only_dry_run_preserves_files(tmp_path, monkeypatch):
    items = tmp_path / "items.jsonl"
    ledger = items.with_name(items.name + ".conflicts")
    raw = json.dumps(_row("https://shop.test/1")) + "\n"
    ledger.write_text(raw)
    monkeypatch.setattr(sys, "argv", ["absorb_spool.py", "--items", str(items), "--dry-run"])
    assert absorb_spool.main() == 0
    assert ledger.read_text() == raw
    assert not items.exists()
