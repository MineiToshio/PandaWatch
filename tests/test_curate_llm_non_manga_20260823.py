"""Tests del retrofit scripts/retrofit/curate_llm_non_manga_20260823.py.

Cierra la curación manual de los 265 items que el LLM de
`/watch-standardize-catalog` marcó `is_manga=false` el 2026-08-23.

Cubre:
  - Las 3 listas de veredicto son disjuntas y no vacías (nadie queda en dos).
  - Los INCIERTOS nunca se expulsan ni se desflagean.
  - Expulsa sólo las URLs de EXPEL_URLS; respeta `approved_at`.
  - Limpia de unmapped_series.jsonl SOLO filas `llm_non_manga` de expulsados y
    KEEP resueltos; conserva otras reasons y las filas inciertas.
  - Idempotencia: 2ª corrida → 0 cambios.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

_SPEC = importlib.util.spec_from_file_location(
    "curate_llm_non_manga_20260823",
    _ROOT / "scripts" / "retrofit" / "curate_llm_non_manga_20260823.py",
)
curate = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(curate)


def test_listas_de_veredicto_disjuntas_y_no_vacias():
    e, k, u = curate.EXPEL_URLS, curate.KEEP_RESOLVED_URLS, curate.KEEP_UNCERTAIN_URLS
    assert e and k and u
    assert not (e & k) and not (e & u) and not (k & u), "un item no puede tener 2 veredictos"
    assert len(e) + len(k) + len(u) == 265, "el universo curado son los 265 pendientes"


def test_inciertos_nunca_se_expulsan():
    """Regla del repo: ante la duda se conserva Y sigue flageado."""
    for url in curate.KEEP_UNCERTAIN_URLS:
        assert url not in curate.EXPEL_URLS


def _run(tmp_path, monkeypatch, items, queue, apply=True):
    it_p = tmp_path / "items.jsonl"
    q_p = tmp_path / "unmapped_series.jsonl"
    d_p = tmp_path / "diagnostics" / "rejected.jsonl"
    it_p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in items) + "\n")
    q_p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in queue) + "\n")
    monkeypatch.setattr(curate, "ITEMS", it_p)
    monkeypatch.setattr(curate, "UNMAPPED", q_p)
    monkeypatch.setattr(curate, "DIAG", d_p)
    monkeypatch.setattr(sys, "argv", ["x"] + (["--apply"] if apply else []))
    curate.main()
    rows = [json.loads(l) for l in it_p.read_text().splitlines() if l.strip()]
    q = [json.loads(l) for l in q_p.read_text().splitlines() if l.strip()]
    return rows, q


def test_expulsa_solo_lo_curado_y_limpia_la_cola(tmp_path, monkeypatch):
    bad = sorted(curate.EXPEL_URLS)[0]
    good = sorted(curate.KEEP_RESOLVED_URLS)[0]
    unc = sorted(curate.KEEP_UNCERTAIN_URLS)[0]
    items = [
        {"url": bad, "title": "no-manga"},
        {"url": good, "title": "light novel"},
        {"url": unc, "title": "incierto"},
        {"url": "https://otro.example/x", "title": "ajeno"},
    ]
    queue = [
        {"sample_url": bad, "reason": "llm_non_manga"},
        {"sample_url": good, "reason": "llm_non_manga"},
        {"sample_url": unc, "reason": "llm_non_manga"},
        {"sample_url": bad, "reason": "standardize_exhausted"},  # otra reason: se conserva
    ]
    rows, q = _run(tmp_path, monkeypatch, items, queue)
    urls = {r["url"] for r in rows}
    assert bad not in urls
    assert {good, unc, "https://otro.example/x"} <= urls
    # el KEEP queda PENDIENTE (sin standardized_at) para que standardize lo retome
    assert not any(r.get("standardized_at") for r in rows)
    q_pairs = {(r["sample_url"], r["reason"]) for r in q}
    assert (unc, "llm_non_manga") in q_pairs, "el incierto sigue flageado"
    assert (bad, "standardize_exhausted") in q_pairs, "otras reasons no se tocan"
    assert (bad, "llm_non_manga") not in q_pairs
    assert (good, "llm_non_manga") not in q_pairs


def test_respeta_aprobados(tmp_path, monkeypatch):
    bad = sorted(curate.EXPEL_URLS)[0]
    items = [{"url": bad, "title": "x", "approved_at": "2026-01-01T00:00:00+00:00"}]
    rows, _ = _run(tmp_path, monkeypatch, items, [{"sample_url": bad, "reason": "llm_non_manga"}])
    assert len(rows) == 1, "un golden record nunca se borra sin --include-approved"


def test_idempotente(tmp_path, monkeypatch):
    bad = sorted(curate.EXPEL_URLS)[0]
    items = [{"url": bad, "title": "x"}, {"url": "https://otro.example/x", "title": "y"}]
    queue = [{"sample_url": bad, "reason": "llm_non_manga"}]
    rows1, q1 = _run(tmp_path, monkeypatch, items, queue)
    rows2, q2 = _run(tmp_path, monkeypatch, rows1, q1 or [{"sample_url": "z", "reason": "otra"}])
    assert [r["url"] for r in rows1] == [r["url"] for r in rows2]
