"""Tests para standardize_apply.py — paquete E-standardize (auditoría Fable,
2026-07-08). Protección de golden records + invariantes del corpus.

Cubre:
  #1  outliers de serie: guard `approved_at` (no reescribir golden records) +
      guard de serie dominante vacía (no crear huérfanos).
  #2  backup_and_rotate al inicio de tier1/merge.
  #3  tier1 no marca standardized_at con keys que se vacían al sanitizar
      (y no pisa keys existentes con "").
  #4  tier1 recomputa cluster_key + consolida (no deja CLKEY stale).
  #5  el writer de unmapped honra MANGA_WATCH_DATA_DIR (_unmapped_path).
  #7  la canónica no-ASCII no se reintroduce (sanitize sin fallback al crudo).
  #8  path de fallo del merge sin mutación parcial de series_key/display.
  #14 veredictos LLM malformados: contados y reportados (no descartados en mudo).

Corpora sintéticos en tmp_path; JAMÁS se toca data/items.jsonl real.
"""

from __future__ import annotations

import json
import os

import pytest

import standardize_apply
from manga_watch import derive_cluster_key


# ── Helpers ─────────────────────────────────────────────────────────────────

def make_item(**overrides) -> dict:
    it = {
        "url": "https://example.com/x",
        "title": "Test Title",
        "title_original": "Test Title",
        "series_key": "e-test-series",
        "series_display": "E Test Series",
        "edition_key": "",
        "edition_display": "",
        "volume": "",
        "source": "AR - Some Store",
        "sources": [{"name": "AR - Some Store", "url": "https://example.com/x"}],
        "images": [],
        "signal_types": [],
        "tags": [],
        "country": "Argentina",
        "language": "Español",
        "publisher": "Some Pub",
        "product_type": "manga",
        "description": "",
        "isbn": "",
        "score": 50,
        "status": "new",
    }
    it.update(overrides)
    return it


def write_jsonl(path, rows) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def write_result(base, results):
    base.mkdir(parents=True, exist_ok=True)
    with (base / "result_00.jsonl").open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def setup_items(tmp_path, monkeypatch, items):
    items_path = tmp_path / "items.jsonl"
    write_jsonl(items_path, items)
    monkeypatch.setattr(standardize_apply, "ITEMS", items_path)
    return items_path


# ── #1a: outliers NO reescriben golden records (approved) ───────────────────

def _cole_url(cid, kind, vol):
    return f"https://listadomanga.es/coleccion.php?id={cid}&item={kind}-{vol}-abcd1234ef"


def test_outliers_do_not_rewrite_approved_golden_record(tmp_path, monkeypatch):
    cid = "100"
    dom_ek = "dominant-series-pub-regular-es"
    dominant = [
        make_item(url=_cole_url(cid, "regular", v), series_key="dominant-series",
                  series_display="Dominant Series", edition_key=dom_ek, volume=str(v),
                  standardized_at="2026-07-01T00:00:00+00:00")
        for v in (1, 2, 3)
    ]
    approved = make_item(
        url=_cole_url(cid, "regular", 4), series_key="curated-series",
        series_display="Curated Series", edition_key="curated-series-pub-regular-es",
        volume="4", standardized_at="2026-07-01T00:00:00+00:00",
        approved_at="2026-06-01T00:00:00+00:00",
    )
    items_path = setup_items(tmp_path, monkeypatch, dominant + [approved])
    base = tmp_path / "run"
    base.mkdir()

    assert standardize_apply.cmd_merge(base, force_all=False) == 0
    out = {it["volume"]: it for it in read_jsonl(items_path)}
    # El golden record conserva su serie curada pese a la dominancia estadística.
    assert out["4"]["series_key"] == "curated-series"
    assert out["4"]["edition_key"] == "curated-series-pub-regular-es"


# ── #1c: outlier con edition_key stale/truncado usa la cascada de ───────────
# rebuild_edition_key_prefix (no el startswith plano, que lo deja stale) ─────

def test_outliers_rewrite_uses_rebuild_cascade_for_stale_edition_key(tmp_path, monkeypatch):
    cid = "300"
    dom_ek = "dominant-series-panini-regular-es"
    dominant = [
        make_item(url=_cole_url(cid, "regular", v), series_key="dominant-series",
                  series_display="Dominant Series", edition_key=dom_ek, volume=str(v),
                  standardized_at="2026-07-01T00:00:00+00:00")
        for v in (1, 2, 3)
    ]
    # El series_key del outlier NO calza con el prefijo realmente horneado en
    # su edition_key (simula un series_key stale tras una re-canonicalización
    # previa). El startswith plano (`old_ek.startswith(series_key + "-")`) NO
    # lo detecta y dejaría el edition_key con un prefijo mezclado/stale;
    # rebuild_edition_key_prefix parsea la cola `-panini-regular-es` desde la
    # derecha y re-arma correctamente con la serie dominante.
    outlier = make_item(
        url=_cole_url(cid, "regular", 4), series_key="stale-key-mismatch",
        series_display="Stale Key Mismatch",
        edition_key="actual-baked-series-panini-regular-es",
        volume="4", standardized_at="2026-07-01T00:00:00+00:00",
    )
    items_path = setup_items(tmp_path, monkeypatch, dominant + [outlier])
    base = tmp_path / "run"
    base.mkdir()

    standardize_apply.cmd_merge(base, force_all=False)
    out = {it["volume"]: it for it in read_jsonl(items_path)}
    assert out["4"]["series_key"] == "dominant-series"
    # Reconstruido vía rebuild_edition_key_prefix, no dejado stale/mezclado.
    assert out["4"]["edition_key"] == "dominant-series-panini-regular-es"


# ── #1b: serie dominante vacía NO crea huérfanos ────────────────────────────

def test_outliers_empty_dominant_does_not_orphan_healthy_items(tmp_path, monkeypatch):
    cid = "200"
    empties = [
        make_item(url=_cole_url(cid, "regular", v), series_key="", series_display="",
                  edition_key=f"-pub-regular-es-{v}", volume=str(v),
                  standardized_at="2026-07-01T00:00:00+00:00")
        for v in (1, 2, 3)
    ]
    healthy = make_item(
        url=_cole_url(cid, "regular", 4), series_key="healthy-series",
        series_display="Healthy Series", edition_key="healthy-series-pub-regular-es",
        volume="4", standardized_at="2026-07-01T00:00:00+00:00",
    )
    items_path = setup_items(tmp_path, monkeypatch, empties + [healthy])
    base = tmp_path / "run"
    base.mkdir()

    # (rc puede ser 1: los 3 empties SON huérfanos a propósito para forzar
    # dom_sk=""; lo que se prueba es que el item sano NO se contagie).
    standardize_apply.cmd_merge(base, force_all=False)
    out = {it["volume"]: it for it in read_jsonl(items_path)}
    # El item sano NO se reescribe a series_key="" (no se convierte en huérfano).
    assert out["4"]["series_key"] == "healthy-series"


# ── #2: backup al inicio de tier1 y merge ───────────────────────────────────

def test_merge_creates_backup(tmp_path, monkeypatch):
    it = make_item(url="https://example.com/b1", standardized_at="2026-07-01T00:00:00+00:00")
    items_path = setup_items(tmp_path, monkeypatch, [it])
    base = tmp_path / "run"
    base.mkdir()
    standardize_apply.cmd_merge(base, force_all=False)
    bak = tmp_path / "backups" / "items.jsonl" / "items.jsonl.pre-standardize-merge-bak"
    assert bak.exists()


def test_tier1_creates_backup(tmp_path, monkeypatch):
    it = make_item(url="https://example.com/t1", series_key="", edition_key="")
    items_path = setup_items(tmp_path, monkeypatch, [it])
    base = tmp_path / "run"
    base.mkdir()
    (base / "tier1.json").write_text(json.dumps([
        {"url": "https://example.com/t1", "proposed_series_key": "sk",
         "proposed_series_display": "SK", "proposed_edition_key": "sk-pub-regular-es",
         "proposed_edition_display": "Reg", "proposed_volume": "1"},
    ]), encoding="utf-8")
    standardize_apply.cmd_tier1(base, force_all=False)
    bak = tmp_path / "backups" / "items.jsonl" / "items.jsonl.pre-standardize-tier1-bak"
    assert bak.exists()


# ── #3: tier1 con keys vacías no marca ni pisa ──────────────────────────────

def test_tier1_empty_keys_not_marked_not_overwritten(tmp_path, monkeypatch):
    # proposed_series_key íntegramente CJK → sanitize_key_ascii la vacía.
    it = make_item(url="https://example.com/cjk", series_key="prev-sk",
                   edition_key="prev-sk-pub-regular-es")
    items_path = setup_items(tmp_path, monkeypatch, [it])
    base = tmp_path / "run"
    base.mkdir()
    (base / "tier1.json").write_text(json.dumps([
        {"url": "https://example.com/cjk", "proposed_series_key": "日本語のみ",
         "proposed_series_display": "X", "proposed_edition_key": "日本語-pub-regular-es",
         "proposed_edition_display": "R", "proposed_volume": "1"},
    ]), encoding="utf-8")

    assert standardize_apply.cmd_tier1(base, force_all=False) == 0
    out = read_jsonl(items_path)[0]
    assert not out.get("standardized_at")          # NO marcado
    assert out["series_key"] == "prev-sk"          # keys previas intactas
    assert out["edition_key"] == "prev-sk-pub-regular-es"


# ── #4: tier1 recomputa cluster_key (no queda stale) ────────────────────────

def test_tier1_recomputes_cluster_key(tmp_path, monkeypatch):
    it = make_item(url="https://example.com/t4", series_key="", edition_key="",
                   cluster_key="url:stale-value")
    items_path = setup_items(tmp_path, monkeypatch, [it])
    base = tmp_path / "run"
    base.mkdir()
    (base / "tier1.json").write_text(json.dumps([
        {"url": "https://example.com/t4", "proposed_series_key": "t4-series",
         "proposed_series_display": "T4", "proposed_edition_key": "t4-series-pub-regular-es",
         "proposed_edition_display": "Reg", "proposed_volume": "1"},
    ]), encoding="utf-8")

    assert standardize_apply.cmd_tier1(base, force_all=False) == 0
    out = read_jsonl(items_path)[0]
    assert out.get("standardized_at")
    assert out["cluster_key"] == derive_cluster_key(out)   # CLKEY auto-consistente
    assert out["cluster_key"] != "url:stale-value"


# ── #5: unmapped honra MANGA_WATCH_DATA_DIR ─────────────────────────────────

def test_unmapped_path_honors_env_var(tmp_path, monkeypatch):
    # Sin monkeypatchear UNMAPPED (== default) y con la env var seteada
    # (fixture autouse del conftest ya la setea a tmp_path/_serve_data).
    data_dir = os.environ["MANGA_WATCH_DATA_DIR"]
    target = standardize_apply._unmapped_path()
    assert target == (__import__("pathlib").Path(data_dir) / "unmapped_series.jsonl")


def test_unmapped_write_lands_in_env_dir(tmp_path, monkeypatch):
    data_dir = os.environ["MANGA_WATCH_DATA_DIR"]
    it = make_item(series_key="e-unmapped-series", url="https://store.example/u1")
    wrote = standardize_apply.append_unmapped_from_item(it, "llm_non_manga")
    assert wrote is True
    env_file = __import__("pathlib").Path(data_dir) / "unmapped_series.jsonl"
    recs = read_jsonl(env_file)
    assert any(r["series_key"] == "e-unmapped-series" for r in recs)
    # NO se ensució el archivo real del repo.
    assert not standardize_apply.UNMAPPED.exists() or standardize_apply.UNMAPPED != env_file


def test_unmapped_monkeypatched_wins_over_env(tmp_path, monkeypatch):
    ad_hoc = tmp_path / "ad_hoc_unmapped.jsonl"
    monkeypatch.setattr(standardize_apply, "UNMAPPED", ad_hoc)
    assert standardize_apply._unmapped_path() == ad_hoc


# ── #7: canónica no-ASCII no se reintroduce ─────────────────────────────────

def test_canonical_non_ascii_key_not_reintroduced(tmp_path, monkeypatch):
    it = make_item(url="https://store.example/c7", series_key="valid-sk",
                   series_display="Valid", edition_key="valid-sk-pub-regular-es")
    items_path = setup_items(tmp_path, monkeypatch, [it])
    base = tmp_path / "run"
    base.mkdir()
    write_result(base, [{"url": "https://store.example/c7", "is_manga": True,
                         "series_key": "valid-sk"}])
    # canonical devuelve una key íntegramente no-ASCII (sanitize → "").
    monkeypatch.setattr(standardize_apply, "canonical_series_key",
                        lambda title, sk, sd: ("日本語", "日本語"))

    assert standardize_apply.cmd_merge(base, force_all=False) == 0
    out = read_jsonl(items_path)[0]
    assert out.get("standardized_at")
    # La key ASCII se conserva; NO se reintrodujo la no-ASCII ni se vació.
    assert out["series_key"] == "valid-sk"


# ── #8: sin mutación parcial en el path de fallo del merge ───────────────────

def test_merge_unusable_edition_key_no_partial_mutation(tmp_path, monkeypatch):
    it = make_item(url="https://store.example/c8", series_key="orig-sk",
                   series_display="Orig Display", edition_key="")  # sin edición
    items_path = setup_items(tmp_path, monkeypatch, [it])
    base = tmp_path / "run"
    base.mkdir()
    # LLM da series usable pero edición íntegramente no-ASCII (sanitize → "").
    write_result(base, [{"url": "https://store.example/c8", "is_manga": True,
                         "series_key": "new-sk", "edition_key": "日本語"}])

    assert standardize_apply.cmd_merge(base, force_all=False) == 0
    out = read_jsonl(items_path)[0]
    assert not out.get("standardized_at")                 # queda pendiente
    assert out.get("standardize_attempts") == 1
    # series_key/display NO se mutaron a medias (siguen los originales).
    assert out["series_key"] == "orig-sk"
    assert out["series_display"] == "Orig Display"


# ── E3: volumen cae a proposed_volume cuando el LLM lo deja vacío ───────────
# (rama has_edition: el item YA tiene edition_key; el LLM validó pero emitió
# volume="" confiando en el pseudo-campo accept_proposal inexistente).

def test_has_edition_volume_falls_back_to_proposed_volume(tmp_path, monkeypatch):
    it = make_item(url="https://store.example/e3", series_key="e3-series",
                   series_display="E3 Series",
                   edition_key="e3-series-pub-regular-es", volume="")
    items_path = setup_items(tmp_path, monkeypatch, [it])
    base = tmp_path / "run"
    base.mkdir()
    # El audit propuso volume="7"; el LLM (Tier 2) devuelve volume vacío.
    (base / "tier2.json").write_text(json.dumps([
        {"url": "https://store.example/e3", "proposed_series_key": "e3-series",
         "proposed_series_display": "E3 Series",
         "proposed_edition_key": "e3-series-pub-regular-es",
         "proposed_edition_display": "Reg", "proposed_volume": "7"},
    ]), encoding="utf-8")
    write_result(base, [{"url": "https://store.example/e3", "is_manga": True,
                         "series_key": "e3-series", "volume": ""}])

    assert standardize_apply.cmd_merge(base, force_all=False) == 0
    out = read_jsonl(items_path)[0]
    assert out.get("standardized_at")
    # El proposed_volume del audit se usa en vez de descartarse.
    assert out["volume"] == "7"


def test_has_edition_volume_prefers_existing_then_llm(tmp_path, monkeypatch):
    # Si el LLM SÍ da volume, gana sobre proposed_volume (orden de cascada).
    it = make_item(url="https://store.example/e3b", series_key="e3b-series",
                   series_display="E3b Series",
                   edition_key="e3b-series-pub-regular-es", volume="")
    items_path = setup_items(tmp_path, monkeypatch, [it])
    base = tmp_path / "run"
    base.mkdir()
    (base / "tier2.json").write_text(json.dumps([
        {"url": "https://store.example/e3b", "proposed_series_key": "e3b-series",
         "proposed_series_display": "E3b Series",
         "proposed_edition_key": "e3b-series-pub-regular-es",
         "proposed_edition_display": "Reg", "proposed_volume": "7"},
    ]), encoding="utf-8")
    write_result(base, [{"url": "https://store.example/e3b", "is_manga": True,
                         "series_key": "e3b-series", "volume": "9"}])

    assert standardize_apply.cmd_merge(base, force_all=False) == 0
    out = read_jsonl(items_path)[0]
    assert out["volume"] == "9"   # el LLM gana sobre la propuesta


# ── E4: item proyectado sin veredicto del subagente escala standardize_attempts

def test_missing_result_increments_standardize_attempts(tmp_path, monkeypatch):
    # Item pendiente proyectado a Tier 3 (está en tier3.json/proposals) pero el
    # subagente NO escribió su línea en el result → r is None. Debe contar el
    # intento para que el audit lo escale a standardize_exhausted más adelante.
    it = make_item(url="https://store.example/e4", series_key="", edition_key="",
                   standardize_attempts=1)
    items_path = setup_items(tmp_path, monkeypatch, [it])
    base = tmp_path / "run"
    base.mkdir()
    (base / "tier3.json").write_text(json.dumps([
        {"url": "https://store.example/e4", "proposed_series_key": "e4-series",
         "proposed_series_display": "E4 Series",
         "proposed_edition_key": "e4-series-pub-regular-es",
         "proposed_edition_display": "Reg", "proposed_volume": "1"},
    ]), encoding="utf-8")
    # result presente pero SIN la url del item (subagente lo omitió).
    write_result(base, [{"url": "https://store.example/other", "is_manga": True,
                         "series_key": "other-series",
                         "edition_key": "other-series-pub-regular-es"}])

    assert standardize_apply.cmd_merge(base, force_all=False) == 0
    out = {i["url"]: i for i in read_jsonl(items_path)}
    e4 = out["https://store.example/e4"]
    assert not e4.get("standardized_at")               # sigue pendiente
    assert e4.get("standardize_attempts") == 2         # 1 previo + 1 por omisión


def test_missing_result_not_in_proposals_does_not_increment(tmp_path, monkeypatch):
    # Item pendiente que NO fue proyectado (no está en proposals) — p.ej. un
    # item que ni siquiera entró al audit este run — no debe contabilizar
    # intento (no fue una omisión del subagente).
    it = make_item(url="https://store.example/e4b", series_key="", edition_key="")
    items_path = setup_items(tmp_path, monkeypatch, [it])
    base = tmp_path / "run"
    base.mkdir()
    write_result(base, [{"url": "https://store.example/other", "is_manga": True,
                         "series_key": "other-series",
                         "edition_key": "other-series-pub-regular-es"}])

    standardize_apply.cmd_merge(base, force_all=False)
    out = read_jsonl(items_path)[0]
    assert not out.get("standardized_at")
    assert "standardize_attempts" not in out or out.get("standardize_attempts") in (0, None)


# ── #14: veredictos LLM malformados contados y reportados ────────────────────

def test_malformed_verdict_lines_reported(tmp_path, monkeypatch, capsys):
    it = make_item(url="https://store.example/c14", edition_key="e-test-series-pub-regular-es",
                   standardized_at="2026-07-01T00:00:00+00:00")
    items_path = setup_items(tmp_path, monkeypatch, [it])
    base = tmp_path / "run"
    base.mkdir()
    with (base / "result_00.jsonl").open("w", encoding="utf-8") as fh:
        fh.write('{"url": "https://store.example/c14", "is_manga": true}\n')
        fh.write("{ this is not valid json ]\n")          # malformada
        fh.write('{"url": "https://store.example/z", broken\n')  # malformada

    assert standardize_apply.cmd_merge(base, force_all=False) == 0
    captured = capsys.readouterr().out
    assert "2 líneas de veredicto LLM malformadas" in captured
