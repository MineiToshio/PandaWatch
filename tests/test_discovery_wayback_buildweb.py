"""Tests para el paquete A2-discovery-wayback-buildweb (auditoría Fable
2026-07-08): search_discovery.py, wayback_recover.py, build_web.py.

Cubre los hallazgos implementados:
  - search_discovery: escritura vía backup_and_rotate + append_jsonl (no
    open("a") crudo), dedup intra-run con URLs normalizadas, desactivación
    de engines agotados (DDG 202 / Gemini 429).
  - wayback_recover: _flush_wayback atómico (tmp+fsync+os.replace), guard de
    aprobados (approved_at), caché negativa persistente con distinción
    definitivo/transitorio, mapeo name→title (sin campo espurio `name`).
  - build_web: escape de `</` en el payload embebido (--embed).

Todos los tests usan tmp_path — nunca tocan data/ real.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import pytest
import requests

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))


# ─────────────────────────────────────────────────────────────────────────
# search_discovery.py — dedup normalizado (hallazgo #7)
# ─────────────────────────────────────────────────────────────────────────

def test_search_discovery_process_query_dedups_normalized_urls(monkeypatch):
    """Dos URLs del mismo producto con distinto tracking param (utm_source)
    deben normalizar a la MISMA clave y colapsar a 1 solo candidate — antes
    `known_urls.add(cand.url)` guardaba la URL cruda, así que la segunda
    variante (con OTRO tracking param) no matcheaba nada en el set y se
    colaba como duplicado."""
    from retrofit import search_discovery as sd

    dup_results = [
        {"url": "https://example.com/product/123?utm_source=newsletter",
         "title": "Deluxe Edition", "snippet": ""},
        {"url": "https://example.com/product/123?utm_source=twitter",
         "title": "Deluxe Edition (dup)", "snippet": ""},
    ]
    monkeypatch.setattr(sd, "search_ddg_html", lambda query, num=10, timeout=None: dup_results)
    monkeypatch.setattr(sd, "fetch_metadata_from_detail", lambda url, session, timeout: {})
    monkeypatch.setattr(sd, "is_likely_manga", lambda *a, **k: (True, []))
    monkeypatch.setattr(sd, "is_collectible_edition", lambda *a, **k: (True, []))
    monkeypatch.setattr(sd, "score_candidate", lambda cand: None)

    known_urls: set[str] = set()
    session = requests.Session()
    q = {"q": "test query", "engines": ["ddg"]}
    kept, engine_used, n_results = sd.process_query(
        q, {"ddg": {}}, session, known_urls, timeout=(5, 10),
        sleep_ddg=0, sleep_google=0, max_results=10,
    )

    assert n_results == 2
    assert len(kept) == 1, "las 2 URLs normalizan al mismo producto — sólo 1 candidate"
    normalized = sd.normalize_url_for_dedup("https://example.com/product/123?utm_source=newsletter")
    assert normalized in known_urls
    # La clave cruda (con tracking param) NUNCA debe quedar en el set.
    assert "https://example.com/product/123?utm_source=newsletter" not in known_urls
    assert "https://example.com/product/123?utm_source=twitter" not in known_urls


# ─────────────────────────────────────────────────────────────────────────
# search_discovery.py — engines agotados se desactivan (hallazgo #8)
# ─────────────────────────────────────────────────────────────────────────

def test_search_discovery_ddg_202_disables_engine_for_rest_of_run(monkeypatch):
    from retrofit import search_discovery as sd

    calls = []

    def _fake_ddg(query, num=10, timeout=None):
        calls.append(query)
        raise sd.SearchEngineExhaustedError("DDG HTTP 202 (soft rate-limit)")

    monkeypatch.setattr(sd, "search_ddg_html", _fake_ddg)

    dead_engines: set[str] = set()
    session = requests.Session()
    q1 = {"q": "query uno", "engines": ["ddg"]}
    q2 = {"q": "query dos", "engines": ["ddg"]}

    kept1, engine_used1, _ = sd.process_query(
        q1, {"ddg": {}}, session, set(), timeout=(5, 10),
        sleep_ddg=0, sleep_google=0, dead_engines=dead_engines,
    )
    kept2, engine_used2, _ = sd.process_query(
        q2, {"ddg": {}}, session, set(), timeout=(5, 10),
        sleep_ddg=0, sleep_google=0, dead_engines=dead_engines,
    )

    assert "ddg" in dead_engines
    # search_ddg_html sólo debe haberse invocado UNA vez (query 1) — la
    # query 2 lo saltea porque ya está en dead_engines.
    assert len(calls) == 1
    assert kept1 == [] and kept2 == []


def test_search_discovery_gemini_quota_exhausted_disables_gemini_and_google(monkeypatch):
    """gemini/google son alias del mismo cupo (compat yamls viejos) — agotar
    uno debe desactivar ambos."""
    from retrofit import search_discovery as sd

    monkeypatch.setattr(
        sd, "search_gemini_grounding",
        lambda q, api_key, model=None, num=10, timeout=None: (_ for _ in ()).throw(
            sd.SearchEngineExhaustedError("Gemini quota exhausted (429)")
        ),
    )
    dead_engines: set[str] = set()
    session = requests.Session()
    q = {"q": "query", "engines": ["gemini"]}
    sd.process_query(
        q, {"gemini": {"api_key": "x"}}, session, set(), timeout=(5, 10),
        sleep_ddg=0, sleep_google=0, dead_engines=dead_engines,
    )
    assert "gemini" in dead_engines
    assert "google" in dead_engines


# ─────────────────────────────────────────────────────────────────────────
# wayback_recover.py — find_wayback_snapshot: definitivo vs transitorio
# (hallazgo #13)
# ─────────────────────────────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc

    def get(self, url, params=None, timeout=None):
        if self._exc:
            raise self._exc
        return self._resp


def test_find_wayback_snapshot_no_snapshot_is_definitive():
    from retrofit import wayback_recover as wr

    session = _FakeSession(resp=_FakeResp(200, {"archived_snapshots": {}}))
    snap, definitive = wr.find_wayback_snapshot("https://x", session)
    assert snap is None
    assert definitive is True


def test_find_wayback_snapshot_network_error_is_not_definitive():
    from retrofit import wayback_recover as wr

    session = _FakeSession(exc=requests.ConnectionError("boom"))
    snap, definitive = wr.find_wayback_snapshot("https://x", session)
    assert snap is None
    assert definitive is False


def test_find_wayback_snapshot_429_is_not_definitive():
    from retrofit import wayback_recover as wr

    session = _FakeSession(resp=_FakeResp(429))
    snap, definitive = wr.find_wayback_snapshot("https://x", session)
    assert snap is None
    assert definitive is False


def test_negative_cache_ttl_boundaries():
    from retrofit import wayback_recover as wr

    fresh = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)).isoformat()
    stale = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=91)).isoformat()
    assert wr.negative_cache_is_fresh(fresh) is True
    assert wr.negative_cache_is_fresh(stale) is False
    assert wr.negative_cache_is_fresh("") is False
    assert wr.negative_cache_is_fresh("not-a-date") is False


# ─────────────────────────────────────────────────────────────────────────
# wayback_recover.py — recover_from_snapshot: mapeo name→title (hallazgo #6)
# ─────────────────────────────────────────────────────────────────────────

def test_recover_from_snapshot_maps_name_to_title_not_spurious_name(monkeypatch):
    from retrofit import wayback_recover as wr

    monkeypatch.setattr(
        wr, "fetch_metadata_from_detail",
        lambda url, session, timeout: {
            "name": "Recovered Product Name", "image_url": "", "author": "",
            "isbn": "", "release_date": "", "publisher": "", "description": "",
        },
    )
    snapshot = {
        "url": "http://web.archive.org/web/20200101000000/https://example.com/x",
        "timestamp": "20200101000000",
    }
    item = {"url": "https://example.com/x", "title": "", "images": []}

    recovered = wr.recover_from_snapshot(snapshot, item, session=None, timeout=(5, 10))

    assert "name" not in recovered, "no debe escribir el campo espurio 'name' (schema usa 'title')"
    assert recovered["title"] == "Recovered Product Name"
    assert recovered["recovered_from_wayback"] is True


def test_recover_from_snapshot_does_not_overwrite_existing_title(monkeypatch):
    from retrofit import wayback_recover as wr

    monkeypatch.setattr(
        wr, "fetch_metadata_from_detail",
        lambda url, session, timeout: {
            "name": "Different Name From Wayback", "image_url": "", "author": "",
            "isbn": "", "release_date": "", "publisher": "", "description": "",
        },
    )
    snapshot = {"url": "http://web.archive.org/web/20200101000000/https://example.com/x",
                "timestamp": "20200101000000"}
    item = {"url": "https://example.com/x", "title": "Original Official Title", "images": []}

    recovered = wr.recover_from_snapshot(snapshot, item, session=None, timeout=(5, 10))
    assert "title" not in recovered, "el item YA tiene title — wayback no debe pisarlo"


# ─────────────────────────────────────────────────────────────────────────
# wayback_recover.py main(): guard de aprobados (hallazgo #5), flush
# atómico (hallazgo #3), caché negativa end-to-end (hallazgo #13)
# ─────────────────────────────────────────────────────────────────────────

def _write_items(path: Path, items: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(it, ensure_ascii=False) for it in items) + "\n",
        encoding="utf-8",
    )


def test_wayback_main_skips_approved_items(tmp_path, monkeypatch):
    from retrofit import wayback_recover as wr

    items_path = tmp_path / "items.jsonl"
    approved_item = {
        "url": "https://example.com/approved-dead",
        "title": "Golden Record",
        "approved_at": "2026-01-01T00:00:00+00:00",
        "images": [],
    }
    _write_items(items_path, [approved_item])

    calls: list[str] = []
    monkeypatch.setattr(wr, "check_url_status", lambda url, session, timeout=8: calls.append(url) or 404)

    argv = [
        "wayback_recover.py",
        "--input", str(items_path), "--output", str(items_path),
        "--sleep", "0", "--no-negative-cache",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    rc = wr.main()
    assert rc == 0
    assert calls == [], "un item con approved_at nunca debe llegar ni al chequeo HTTP de Phase 1"


def test_wayback_main_include_approved_flag_processes_them(tmp_path, monkeypatch):
    from retrofit import wayback_recover as wr

    items_path = tmp_path / "items.jsonl"
    approved_item = {
        "url": "https://example.com/approved-dead",
        "title": "Golden Record",
        "approved_at": "2026-01-01T00:00:00+00:00",
        "images": [],
    }
    _write_items(items_path, [approved_item])

    calls: list[str] = []
    monkeypatch.setattr(wr, "check_url_status", lambda url, session, timeout=8: calls.append(url) or 200)

    argv = [
        "wayback_recover.py",
        "--input", str(items_path), "--output", str(items_path),
        "--sleep", "0", "--no-negative-cache", "--include-approved",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    rc = wr.main()
    assert rc == 0
    assert calls == ["https://example.com/approved-dead"], "--include-approved debe re-incluirlo"


def test_wayback_flush_is_atomic_tmp_then_replace(tmp_path, monkeypatch):
    """_flush_wayback debe escribir a un .tmp y recién ENTONCES os.replace —
    nunca truncar items.jsonl in-place (hallazgo #3)."""
    from retrofit import wayback_recover as wr

    items_path = tmp_path / "items.jsonl"
    item = {"url": "https://example.com/dead-item", "title": "", "images": []}
    _write_items(items_path, [item])

    monkeypatch.setattr(wr, "check_url_status", lambda url, session, timeout=8: 404)
    snap = {"url": "http://web.archive.org/web/20200101000000/https://example.com/dead-item",
            "timestamp": "20200101000000"}
    monkeypatch.setattr(wr, "find_wayback_snapshot", lambda url, session, timeout=15: (snap, True))
    monkeypatch.setattr(
        wr, "recover_from_snapshot",
        lambda snapshot, it, session, timeout: {
            "title": "Recovered Title",
            "recovered_from_wayback": True,
            "wayback_snapshot_url": snapshot["url"],
            "wayback_timestamp": snapshot["timestamp"],
        },
    )

    replace_calls: list[tuple[str, str]] = []
    orig_replace = wr.os.replace

    def _tracking_replace(src, dst):
        # En el momento del replace, el .tmp YA debe existir con el
        # contenido final (si no fuera atómico esto no sería garantizable).
        assert Path(src).exists()
        assert Path(src).name.endswith(".tmp")
        replace_calls.append((str(src), str(dst)))
        return orig_replace(src, dst)

    monkeypatch.setattr(wr.os, "replace", _tracking_replace)

    argv = [
        "wayback_recover.py",
        "--input", str(items_path), "--output", str(items_path),
        "--sleep", "0", "--no-negative-cache",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    rc = wr.main()

    assert rc == 0
    assert replace_calls, "os.replace nunca se llamó — el flush atómico no corrió"
    # Ningún .tmp debe sobrevivir tras el replace.
    assert not list(tmp_path.glob("*.tmp"))

    final = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    assert final["title"] == "Recovered Title"
    assert final["recovered_from_wayback"] is True


def test_wayback_negative_cache_skips_fresh_entries(tmp_path, monkeypatch):
    from retrofit import wayback_recover as wr

    items_path = tmp_path / "items.jsonl"
    item = {"url": "https://example.com/known-dead", "title": "X", "images": []}
    _write_items(items_path, [item])

    cache_path = tmp_path / "neg_cache.json"
    fresh_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    cache_path.write_text(
        json.dumps({"https://example.com/known-dead": fresh_iso}), encoding="utf-8",
    )

    monkeypatch.setattr(wr, "check_url_status", lambda url, session, timeout=8: 404)
    calls: list[str] = []
    monkeypatch.setattr(
        wr, "find_wayback_snapshot",
        lambda url, session, timeout=15: (calls.append(url), (None, True))[1],
    )

    argv = [
        "wayback_recover.py",
        "--input", str(items_path), "--output", str(items_path),
        "--sleep", "0", "--negative-cache-file", str(cache_path),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    rc = wr.main()
    assert rc == 0
    assert calls == [], "una URL con negativo fresco en caché no debe re-consultar Wayback"


def test_wayback_negative_cache_does_not_cache_transient_errors(tmp_path, monkeypatch):
    from retrofit import wayback_recover as wr

    items_path = tmp_path / "items.jsonl"
    item = {"url": "https://example.com/rate-limited", "title": "X", "images": []}
    _write_items(items_path, [item])

    cache_path = tmp_path / "neg_cache.json"

    monkeypatch.setattr(wr, "check_url_status", lambda url, session, timeout=8: 404)
    # Simula un 429/timeout: (None, False) = NO definitivo.
    monkeypatch.setattr(wr, "find_wayback_snapshot", lambda url, session, timeout=15: (None, False))

    argv = [
        "wayback_recover.py",
        "--input", str(items_path), "--output", str(items_path),
        "--sleep", "0", "--negative-cache-file", str(cache_path),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    rc = wr.main()
    assert rc == 0
    assert cache_path.exists()
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cache == {}, "un error transitorio (429/timeout) NUNCA debe cachearse como negativo"


def test_wayback_negative_cache_records_definitive_no_snapshot(tmp_path, monkeypatch):
    from retrofit import wayback_recover as wr

    items_path = tmp_path / "items.jsonl"
    item = {"url": "https://example.com/confirmed-no-snapshot", "title": "X", "images": []}
    _write_items(items_path, [item])

    cache_path = tmp_path / "neg_cache.json"

    monkeypatch.setattr(wr, "check_url_status", lambda url, session, timeout=8: 404)
    # (None, True) = consulta exitosa que CONFIRMA que no hay snapshot.
    monkeypatch.setattr(wr, "find_wayback_snapshot", lambda url, session, timeout=15: (None, True))

    argv = [
        "wayback_recover.py",
        "--input", str(items_path), "--output", str(items_path),
        "--sleep", "0", "--negative-cache-file", str(cache_path),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    rc = wr.main()
    assert rc == 0
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert "https://example.com/confirmed-no-snapshot" in cache


# ─────────────────────────────────────────────────────────────────────────
# build_web.py — escape de `</` en el payload embebido (hallazgo #9)
# ─────────────────────────────────────────────────────────────────────────

def test_build_web_inject_escapes_closing_script_tag():
    import build_web

    html = (
        '<html><body>'
        '<script id="manga-data" type="application/json">[]</script>'
        '</body></html>'
    )
    malicious_title = "Weird </script><script>alert(1)</script> Title"
    items = [{"title": malicious_title}]

    out = build_web.inject(html, items)

    assert "</script><script>alert(1)</script>" not in out
    assert r"<\/script>" in out

    # El HTML resultante debe seguir teniendo EXACTAMENTE un tag de cierre
    # real para <script id="manga-data">, y el JSON embebido debe seguir
    # siendo válido y preservar el título completo (json.loads interpreta
    # \/ igual que / — es un escape JSON válido).
    m = re.search(
        r'<script id="manga-data" type="application/json">(.*?)</script>',
        out, re.DOTALL,
    )
    assert m, "no se encontró el tag de cierre real tras el escape"
    parsed = json.loads(m.group(1))
    assert parsed[0]["title"] == malicious_title


def test_build_web_inject_without_closing_tag_in_payload_is_unaffected():
    import build_web

    html = (
        '<html><body>'
        '<script id="manga-data" type="application/json">[]</script>'
        '</body></html>'
    )
    items = [{"title": "Normal Title", "country": "Japón"}]
    out = build_web.inject(html, items)
    m = re.search(
        r'<script id="manga-data" type="application/json">(.*?)</script>',
        out, re.DOTALL,
    )
    assert m
    parsed = json.loads(m.group(1))
    assert parsed == items
