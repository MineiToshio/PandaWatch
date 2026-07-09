"""Tests para las invariantes nuevas de validate_corpus.py — paquete
E-standardize (auditoría Fable, 2026-07-08). Todas nacen WARNING.

Cubre: PAISKEY, URLDUP, IMGTOP, COVER0, APPROVED, TSISO, SRCFMT (+ el guard
isinstance que evita el crash del validador ante una entrada no-dict en
sources[], hallazgo #11).

Corpora sintéticos en tmp_path; se invoca validate_corpus.main() con --file y se
parsea el conteo del reporte. JAMÁS se toca data/items.jsonl real.
"""

from __future__ import annotations

import json
import re
import sys

import pytest

import validate_corpus


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def run_validate(items, tmp_path, monkeypatch, capsys):
    p = tmp_path / "corpus.jsonl"
    write_jsonl(p, items)
    monkeypatch.setattr(sys, "argv", ["validate_corpus.py", "--file", str(p)])
    rc = validate_corpus.main()
    out = capsys.readouterr().out
    return rc, out


def count(out, kind):
    m = re.search(rf"\b{kind}\s+violaciones:\s+(\d+)", out)
    assert m, f"no encontré la línea de {kind} en el reporte:\n{out}"
    return int(m.group(1))


def _item(**ov):
    it = {
        "slug": "s", "title": "T", "url": "https://x/1",
        "series_key": "sk", "edition_key": "sk-pub-regular-es",
        "country": "España", "volume": "1",
        "sources": [{"url": "https://x/1"}], "images": [],
        "cluster_key": "edition:sk-pub-regular-es|1",
    }
    it.update(ov)
    return it


# ── PAISKEY ─────────────────────────────────────────────────────────────────

def test_paiskey_flags_country_edition_mismatch(tmp_path, monkeypatch, capsys):
    items = [
        _item(slug="a", url="https://x/a", cluster_key="ck-a", sources=[{"url": "https://x/a"}],
              country="Hong Kong", edition_key="work-pub-regular-tw"),   # hk != tw → flag
        _item(slug="b", url="https://x/b", cluster_key="ck-b", sources=[{"url": "https://x/b"}],
              country="España", edition_key="work-pub-regular-es"),      # es == es → ok
    ]
    _, out = run_validate(items, tmp_path, monkeypatch, capsys)
    assert count(out, "PAISKEY") == 1


def test_paiskey_skips_unparseable_country_suffix(tmp_path, monkeypatch, capsys):
    # sufijo 'glob' no es país conocido → PAISKEY skip (lo cubren PAIS/EKMALFORMED).
    items = [_item(country="Japón", edition_key="work-pub-variant-glob")]
    _, out = run_validate(items, tmp_path, monkeypatch, capsys)
    assert count(out, "PAISKEY") == 0


# ── URLDUP ──────────────────────────────────────────────────────────────────

def test_urldup_flags_same_url_in_two_items(tmp_path, monkeypatch, capsys):
    shared = "https://shop.example/same-product"
    items = [
        _item(slug="a", cluster_key="ck-a", url=shared, sources=[{"url": shared}]),
        _item(slug="b", cluster_key="ck-b", url=shared, sources=[{"url": shared}]),
    ]
    _, out = run_validate(items, tmp_path, monkeypatch, capsys)
    assert count(out, "URLDUP") == 1


def test_urldup_same_url_within_one_item_is_ok(tmp_path, monkeypatch, capsys):
    u = "https://shop.example/only-here"
    items = [_item(url=u, sources=[{"url": u}, {"url": u}])]
    _, out = run_validate(items, tmp_path, monkeypatch, capsys)
    assert count(out, "URLDUP") == 0


# ── IMGTOP ──────────────────────────────────────────────────────────────────

def test_imgtop_flags_toplevel_image_fields(tmp_path, monkeypatch, capsys):
    items = [
        _item(slug="a", cluster_key="ck-a", url="https://x/a",
              sources=[{"url": "https://x/a"}], image_url="http://cdn/x.jpg"),
        _item(slug="b", cluster_key="ck-b", url="https://x/b",
              sources=[{"url": "https://x/b"}], image_local="x.avif"),
    ]
    _, out = run_validate(items, tmp_path, monkeypatch, capsys)
    assert count(out, "IMGTOP") == 2


# ── COVER0 ──────────────────────────────────────────────────────────────────

def test_cover0_flags_first_image_without_url(tmp_path, monkeypatch, capsys):
    items = [_item(images=[{"kind": "gallery"}])]   # images[0] sin url
    _, out = run_validate(items, tmp_path, monkeypatch, capsys)
    assert count(out, "COVER0") == 1


def test_cover0_ok_when_first_image_has_url(tmp_path, monkeypatch, capsys):
    items = [_item(images=[{"url": "http://cdn/c.jpg", "kind": "gallery"}])]
    _, out = run_validate(items, tmp_path, monkeypatch, capsys)
    assert count(out, "COVER0") == 0


# ── APPROVED ────────────────────────────────────────────────────────────────

def test_approved_flags_incoherent_golden_record(tmp_path, monkeypatch, capsys):
    items = [
        # approved sin standardized_at → flag.
        _item(slug="a", cluster_key="ck-a", url="https://x/a",
              sources=[{"url": "https://x/a"}], approved_at="2026-06-01T00:00:00+00:00"),
        # approved coherente → ok.
        _item(slug="b", cluster_key="ck-b", url="https://x/b",
              sources=[{"url": "https://x/b"}], approved_at="2026-06-01T00:00:00+00:00",
              standardized_at="2026-06-01T00:00:00+00:00"),
    ]
    _, out = run_validate(items, tmp_path, monkeypatch, capsys)
    assert count(out, "APPROVED") == 1


# ── TSISO ───────────────────────────────────────────────────────────────────

def test_tsiso_flags_non_iso_timestamp(tmp_path, monkeypatch, capsys):
    items = [_item(standardized_at="ayer por la tarde")]
    _, out = run_validate(items, tmp_path, monkeypatch, capsys)
    assert count(out, "TSISO") == 1


def test_tsiso_ok_for_iso(tmp_path, monkeypatch, capsys):
    items = [_item(standardized_at="2026-07-08T12:00:00+00:00",
                   approved_at="2026-07-08T12:00:00+00:00")]
    _, out = run_validate(items, tmp_path, monkeypatch, capsys)
    assert count(out, "TSISO") == 0


# ── SRCFMT + no-crash (#11) ─────────────────────────────────────────────────

def test_srcfmt_flags_non_dict_source_without_crashing(tmp_path, monkeypatch, capsys):
    items = [_item(sources=["https://x/1", {"url": "https://x/1"}])]
    rc, out = run_validate(items, tmp_path, monkeypatch, capsys)
    # No crashea (main devuelve un int de exit, no una excepción).
    assert isinstance(rc, int)
    assert count(out, "SRCFMT") == 1
