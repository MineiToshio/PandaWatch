"""Tests para scripts/retrofit/listadomanga_meta.py — endurecimiento #1
(tanda 3, 2026-09-02) del skill `/watch-whakoom-covers`: caché + fetch de la
metadata REAL de una colección de listadomanga.es (`coleccion.php?id=N`),
que `we_plan.py` usa como referencia de `total_tomos` en vez de (o además
de) el heurístico local por conteo de `edition_key`.

Cobertura:
  1. `parse_meta_from_html` — total_tomos, formato, editorial desde una
     sección regular (premium por formato).
  2. `ongoing` — True cuando hay una sección "Números en preparación" con
     tomos anunciados aún no editados; esos tomos NO cuentan en total_tomos.
  3. `paginas` — sólo se completa cuando hay exactamente 1 tomo publicado
     (oneshot); vacío con más de un tomo.
  4. Sin candidates → total_tomos None (no se pudo determinar).
  5. `fetch_collection_meta` — error de red devuelve None (no explota).
  6. Caché append-only: `load_meta_cache` toma la última fila por
     coleccion_id; `append_meta_cache_row` persiste; `ensure_meta_cached` no
     refetchea lo ya cacheado.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "scripts", _ROOT / "scripts" / "retrofit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import listadomanga_meta  # type: ignore


def _lmc_html_minimal(
    *sections_html: str,
    formato: str = "Cartoné, sobrecubierta",
    title: str = "Dragon Ball (Planeta)",
    publisher: str = "Planeta Cómic",
    author: str = "Akira Toriyama",
    original_title: str = "Test",
) -> str:
    """Construye un HTML mínimo de coleccion.php con header + secciones
    dadas — mismo patrón que `_lmc_html_minimal` de test_extraction.py."""
    header = (
        f'<h2>{title}\t\t</h2><hr/>'
        f'<b>T&iacute;tulo original:</b> {original_title}<br/>'
        f'<b>Guion:</b> <a href="autor.php?id=1">{author}</a><br/>'
        f'<b>Editorial espa&ntilde;ola:</b> <a href="editorial.php?id=1">{publisher}</a><br/>'
        f'<b>Formato:</b> {formato}<br/>'
    )
    body = ''.join(sections_html)
    return f'<html><body>{"X" * 1500}{header}{body}</body></html>'


def _lmc_section(header: str, *items_html: str) -> str:
    items = ''.join(items_html)
    return (
        f'<table><tr><td><table class="ventana_id1" style="width: 974px">'
        f'<tr><td class="izq"><h2>{header}</h2></td></tr></table></td></tr></table>'
        f'<table style="padding: 0px;"><tr style="padding: 0px;">{items}</tr></table>'
    )


def _lmc_item(
    volume, series: str, desc_extra: str = "", price: str = "10,00 €",
    pages: str = "192 páginas en B/N", day: str = "23", month: str = "Marzo",
    year: str = "2023", image_id: str = "abc123", cls: str = "ventana_id1",
) -> str:
    desc_line = f'{desc_extra}<br/>' if desc_extra else ''
    title_line = f'{series} n&ordm;{volume}<br/>' if volume else f'{series}<br/>'
    return (
        f'<td><table class="{cls}" style="width: 184px;"><tr><td class="cen">'
        f'<img class="portada" src="https://static.listadomanga.com/{image_id}.jpg" '
        f'alt="{series} nº{volume}"/>'
        f'<div style="height: 8px"></div>'
        f'{title_line}'
        f'{desc_line}'
        f'{pages}<br/>'
        f'{price}<br/>'
        f'{day} <a href="novedades.php">{month} {year}</a>'
        f'</td></tr></table></td><td class="separacion"></td>'
    )


# ── 1. Regular section, premium format ──────────────────────────────────────

def test_parses_total_tomos_formato_editorial_from_regular_section():
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Dragon Ball", image_id="a1"),
            _lmc_item(2, "Dragon Ball", image_id="a2"),
            _lmc_item(3, "Dragon Ball", image_id="a3"),
        ),
    )
    meta = listadomanga_meta.parse_meta_from_html(html, 1832)
    assert meta is not None
    assert meta["total_tomos"] == 3
    assert meta["editorial"] == "Planeta Cómic"
    assert "Cartoné" in meta["formato"]
    assert meta["ongoing"] is False
    assert meta["paginas"] == ""  # más de un tomo -> no se reporta


# ── 2. Ongoing (Números en preparación) ─────────────────────────────────────

def test_ongoing_true_with_preparacion_section_and_excludes_from_total():
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Dragon Ball", image_id="a1"),
            _lmc_item(2, "Dragon Ball", image_id="a2"),
        ),
        _lmc_section(
            "N&uacute;meros en preparaci&oacute;n",
            _lmc_item(3, "Dragon Ball", image_id="a3"),
        ),
    )
    meta = listadomanga_meta.parse_meta_from_html(html, 1832)
    assert meta is not None
    assert meta["total_tomos"] == 2  # el anunciado (vol 3) NO cuenta
    assert meta["ongoing"] is True


# ── 3. paginas sólo con exactamente 1 tomo publicado ────────────────────────

def test_paginas_captured_for_oneshot_in_special_section():
    # Sección "Ediciones Especiales" se procesa SIEMPRE (no gateada por
    # formato premium) — usamos formato NO premium a propósito.
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Ediciones Especiales)",
            _lmc_item("", "Sensor", desc_extra="Edición Deluxe", pages="240 páginas en B/N", image_id="s1"),
        ),
        formato="Tomo (130x183) r&uacute;stica (tapa blanda) con sobrecubierta",
    )
    meta = listadomanga_meta.parse_meta_from_html(html, 5000)
    assert meta is not None
    assert meta["total_tomos"] == 1
    # _PAGES_RE captura sólo "<N> páginas" (el resto de la línea, "en B/N",
    # no aporta al guard de reedición que sólo necesita el número).
    assert meta["paginas"] == "240 páginas"


def test_paginas_empty_when_multiple_tomos():
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Dragon Ball", image_id="a1"),
            _lmc_item(2, "Dragon Ball", image_id="a2"),
        ),
    )
    meta = listadomanga_meta.parse_meta_from_html(html, 1832)
    assert meta["paginas"] == ""


# ── 4. Sin candidates → total_tomos None ────────────────────────────────────

def test_no_sections_total_tomos_none():
    html = _lmc_html_minimal()  # sólo header, sin secciones de tomos
    meta = listadomanga_meta.parse_meta_from_html(html, 1)
    assert meta is not None
    assert meta["total_tomos"] is None
    assert meta["ongoing"] is False


def test_too_short_html_returns_none():
    assert listadomanga_meta.parse_meta_from_html("<html>x</html>", 1) is None
    assert listadomanga_meta.parse_meta_from_html("", 1) is None


# ── 5. fetch_collection_meta — error de red no explota ──────────────────────

class _RaisingSession:
    def get(self, *a, **kw):
        import requests
        raise requests.exceptions.ConnectionError("boom")


def test_fetch_collection_meta_network_error_returns_none():
    result = listadomanga_meta.fetch_collection_meta(1832, session=_RaisingSession())
    assert result is None


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.encoding = "utf-8"

    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self, html_text: str):
        self._html = html_text
        self.calls: list[str] = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        return _FakeResponse(self._html)


def test_fetch_collection_meta_uses_coleccion_url_template():
    html = _lmc_html_minimal(
        _lmc_section("N&uacute;meros editados", _lmc_item(1, "Dragon Ball", image_id="a1")),
    )
    sess = _FakeSession(html)
    meta = listadomanga_meta.fetch_collection_meta(1832, session=sess)
    assert meta is not None
    assert meta["total_tomos"] == 1
    assert sess.calls == ["https://www.listadomanga.es/coleccion.php?id=1832"]


# ── 6. Caché append-only ─────────────────────────────────────────────────────

def test_load_meta_cache_last_row_wins(tmp_path):
    cache_path = tmp_path / "meta.jsonl"
    rows = [
        {"coleccion_id": 1832, "total_tomos": 20, "ongoing": True, "formato": "", "paginas": "", "editorial": ""},
        {"coleccion_id": 1832, "total_tomos": 25, "ongoing": False, "formato": "", "paginas": "", "editorial": ""},
    ]
    with cache_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    cache = listadomanga_meta.load_meta_cache(cache_path)
    assert cache[1832]["total_tomos"] == 25
    assert cache[1832]["ongoing"] is False


def test_load_meta_cache_missing_file_returns_empty(tmp_path):
    assert listadomanga_meta.load_meta_cache(tmp_path / "nope.jsonl") == {}


def test_append_meta_cache_row_persists_with_timestamp(tmp_path):
    cache_path = tmp_path / "meta.jsonl"
    listadomanga_meta.append_meta_cache_row(cache_path, {
        "coleccion_id": 1832, "total_tomos": 25, "ongoing": False,
        "formato": "Rústica", "paginas": "", "editorial": "Planeta Cómic",
    })
    rows = [json.loads(l) for l in cache_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 1
    assert rows[0]["coleccion_id"] == 1832
    assert "fetched_at" in rows[0]


def test_ensure_meta_cached_returns_cached_without_fetching(tmp_path, monkeypatch):
    cache_path = tmp_path / "meta.jsonl"
    cache = {1832: {"coleccion_id": 1832, "total_tomos": 25, "ongoing": False,
                     "formato": "", "paginas": "", "editorial": ""}}

    def _boom(*a, **kw):
        raise AssertionError("no debería fetchear algo ya cacheado")

    monkeypatch.setattr(listadomanga_meta, "fetch_collection_meta", _boom)
    result = listadomanga_meta.ensure_meta_cached(1832, cache, cache_path)
    assert result["total_tomos"] == 25


def test_ensure_meta_cached_fetches_caches_and_sleeps_when_missing(tmp_path, monkeypatch):
    cache_path = tmp_path / "meta.jsonl"
    cache: dict[int, dict] = {}
    slept: list[float] = []

    def _fake_fetch(cid, session=None, timeout=(10, 30)):
        return {"coleccion_id": cid, "total_tomos": 11, "ongoing": True,
                "formato": "Rústica", "paginas": "", "editorial": "Norma"}

    monkeypatch.setattr(listadomanga_meta, "fetch_collection_meta", _fake_fetch)
    monkeypatch.setattr(listadomanga_meta.time, "sleep", lambda s: slept.append(s))

    result = listadomanga_meta.ensure_meta_cached(4139, cache, cache_path, sleep_seconds=2.0)
    assert result["total_tomos"] == 11
    assert 4139 in cache
    assert slept == [2.0]
    reloaded = listadomanga_meta.load_meta_cache(cache_path)
    assert reloaded[4139]["total_tomos"] == 11


def test_ensure_meta_cached_returns_none_on_fetch_failure(tmp_path, monkeypatch):
    cache_path = tmp_path / "meta.jsonl"
    cache: dict[int, dict] = {}
    monkeypatch.setattr(listadomanga_meta, "fetch_collection_meta", lambda *a, **kw: None)
    result = listadomanga_meta.ensure_meta_cached(1, cache, cache_path)
    assert result is None
    assert 1 not in cache
    assert not cache_path.exists()


# ── CLI smoke test (sin red — ids ya cacheados) ──────────────────────────────

def test_main_from_plan_with_all_ids_already_cached(tmp_path, capsys, monkeypatch):
    cache_path = tmp_path / "meta.jsonl"
    listadomanga_meta.append_meta_cache_row(cache_path, {
        "coleccion_id": 1832, "total_tomos": 25, "ongoing": False,
        "formato": "", "paginas": "", "editorial": "",
    })
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps([
        {"slug": "s1", "listado": {"coleccion_id": 1832}},
    ]), encoding="utf-8")

    def _boom(*a, **kw):
        raise AssertionError("no debería fetchear — ya está en caché")

    monkeypatch.setattr(listadomanga_meta, "fetch_collection_meta", _boom)
    rc = listadomanga_meta.main(["--from-plan", str(plan_path), "--cache", str(cache_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "a fetchear: 0" in out


def test_main_nothing_to_fetch_without_args(capsys):
    rc = listadomanga_meta.main([])
    assert rc == 0
    assert "Nada que fetchear" in capsys.readouterr().out
