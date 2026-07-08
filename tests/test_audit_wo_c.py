"""Tests WO-C — auditoría post-scrape del skill /watch-standardize-catalog.

Cubre los 3 cambios de standardize_apply.py / standardize_audit.py:

 1. EL LLM NO EXPULSA: is_manga=false ya no manda el item a
    non_manga_blacklist.jsonl ni lo borra. Queda pendiente + registrado en
    unmapped_series.jsonl (reason "llm_non_manga"). Excepción: un item con
    source Mangavariant NUNCA se expulsa — el veredicto se ignora.
 2. ESCALADO DE RETRY: el merge cuenta `standardize_attempts` cuando deja un
    item pendiente por keys inusables; el audit excluye de Tier 2/3 los que
    llegan a MAX_STANDARDIZE_ATTEMPTS y los manda a curación (reason
    "standardize_exhausted", dedup cross-run).
 3. PRODUCT_TYPE LIMPIO: un edition-kind (special/deluxe/…) del LLM nunca
    aterriza en product_type; se conserva el existente válido o se re-deriva.

Los corpora son sintéticos en tmp_path; los resultados LLM se simulan como
archivos result_*.jsonl. JAMÁS se toca data/items.jsonl real.
"""

from __future__ import annotations

import json
import sys

import standardize_apply
import standardize_audit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_item(**overrides) -> dict:
    it = {
        "url": "https://example.com/x",
        "title": "Test Title",
        "title_original": "Test Title",
        "series_key": "wo-c-test-series",
        "series_display": "WO-C Test Series",
        "edition_key": "",
        "edition_display": "",
        "volume": "",
        "source": "AR - Some Store",
        "sources": [],
        "images": [],
        "signal_types": [],
        "tags": [],
        "country": "Argentina",
        "language": "Español",
        "publisher": "Some Pub",
        "product_type": "",
        "description": "",
        "isbn": "",
        "price": "",
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


def setup_apply(tmp_path, monkeypatch, items):
    """Aísla ITEMS/UNMAPPED de standardize_apply a tmp y escribe el corpus."""
    items_path = tmp_path / "items.jsonl"
    unmapped_path = tmp_path / "unmapped_series.jsonl"
    write_jsonl(items_path, items)
    monkeypatch.setattr(standardize_apply, "ITEMS", items_path)
    monkeypatch.setattr(standardize_apply, "UNMAPPED", unmapped_path)
    return items_path, unmapped_path


def run_audit(base, items_path, monkeypatch, tier=3):
    """Corre standardize_audit.main() con ITEMS aislado y un tier controlado."""
    monkeypatch.setattr(standardize_audit, "ITEMS", items_path)
    monkeypatch.setattr(
        standardize_audit, "derive_series_metadata",
        lambda c: {"confidence_tier": tier, "series_key": "wo-c-audit-series",
                   "series_display": "WO-C Audit Series"},
    )
    monkeypatch.setattr(sys, "argv", ["standardize_audit.py", "--base", str(base)])
    return standardize_audit.main()


# ---------------------------------------------------------------------------
# (i) Mangavariant + is_manga=false → se ignora el veredicto, item estandarizado
# ---------------------------------------------------------------------------


def test_mangavariant_non_manga_verdict_is_ignored(tmp_path, monkeypatch):
    it = make_item(
        url="https://mangavariant.example/1",
        title="Some Variant Vol 1 - Cover A",
        source="Global - Mangavariant",
        sources=[{"name": "Global - Mangavariant",
                  "url": "https://mangavariant.example/1"}],
        edition_key="wo-c-test-series-shueisha-jp",
    )
    items_path, unmapped_path = setup_apply(tmp_path, monkeypatch, [it])
    base = tmp_path / "run"
    write_result(base, [{
        "url": "https://mangavariant.example/1",
        "is_manga": False, "non_manga_reason": "light_novel",
        "series_key": "wo-c-test-series", "series_display": "WO-C Test Series",
    }])

    rc = standardize_apply.cmd_merge(base, force_all=False)
    assert rc == 0

    out = read_jsonl(items_path)
    assert len(out) == 1                      # fila NO borrada
    assert out[0].get("standardized_at")      # estandarizada igual
    assert read_jsonl(unmapped_path) == []    # NO va a unmapped
    # El LLM ya no escribe blacklist alguna.
    assert not (tmp_path / "non_manga_blacklist.jsonl").exists()


# ---------------------------------------------------------------------------
# (ii) is_manga=false normal → pendiente, 0 blacklist, 1 unmapped llm_non_manga
# ---------------------------------------------------------------------------


def test_normal_non_manga_goes_to_unmapped_not_blacklist(tmp_path, monkeypatch):
    it = make_item(
        url="https://store.example/ln1",
        title="Some Light Novel Vol 1",
        series_key="wo-c-some-light-novel",
        series_display="WO-C Some Light Novel",
        source="AR - Some Store",
    )
    items_path, unmapped_path = setup_apply(tmp_path, monkeypatch, [it])
    base = tmp_path / "run"
    write_result(base, [{
        "url": "https://store.example/ln1",
        "is_manga": False, "non_manga_reason": "light_novel",
    }])

    rc = standardize_apply.cmd_merge(base, force_all=False)
    assert rc == 0

    out = read_jsonl(items_path)
    assert len(out) == 1                        # fila NO borrada
    assert not out[0].get("standardized_at")    # queda PENDIENTE
    assert not (tmp_path / "non_manga_blacklist.jsonl").exists()

    um = read_jsonl(unmapped_path)
    assert len(um) == 1
    assert um[0]["reason"] == "llm_non_manga"
    assert um[0]["series_key"] == "wo-c-some-light-novel"
    assert um[0]["sample_url"] == "https://store.example/ln1"
    assert um[0]["note"] == "light_novel"       # veredicto/categoría del LLM


def test_normal_non_manga_unmapped_dedup_across_runs(tmp_path, monkeypatch):
    it = make_item(url="https://store.example/ln2",
                   series_key="wo-c-dup-series", title="Dup Vol 1")
    items_path, unmapped_path = setup_apply(tmp_path, monkeypatch, [it])
    base = tmp_path / "run"
    write_result(base, [{"url": "https://store.example/ln2", "is_manga": False,
                         "non_manga_reason": "western_comic"}])

    standardize_apply.cmd_merge(base, force_all=False)
    standardize_apply.cmd_merge(base, force_all=False)  # 2ª corrida

    um = [u for u in read_jsonl(unmapped_path) if u["reason"] == "llm_non_manga"]
    assert len(um) == 1                          # dedup cross-run


# ---------------------------------------------------------------------------
# (iii) 3 corridas con keys inusables → attempts=3, el audit excluye + 1 unmapped
# ---------------------------------------------------------------------------


def test_retry_escalation_exhausts_and_routes_to_curation(tmp_path, monkeypatch):
    it = make_item(
        url="https://store.example/cjk1",
        title="謎のシリーズ",
        series_key="", series_display="",
    )
    items_path, unmapped_path = setup_apply(tmp_path, monkeypatch, [it])
    base = tmp_path / "run"
    # LLM (is_manga=true) sin keys usables ni propuesta heurística → pendiente.
    write_result(base, [{"url": "https://store.example/cjk1", "is_manga": True,
                         "series_key": "", "edition_key": ""}])

    for _ in range(3):
        standardize_apply.cmd_merge(base, force_all=False)

    out = read_jsonl(items_path)
    assert len(out) == 1
    assert out[0].get("standardize_attempts") == 3
    assert not out[0].get("standardized_at")     # sigue pendiente

    # Audit (tier 3): el item exhausto se excluye de las proyecciones y se
    # manda a curación. Segunda corrida no re-appendea (dedup).
    audit_base = tmp_path / "audit"
    assert run_audit(audit_base, items_path, monkeypatch, tier=3) == 0
    assert run_audit(audit_base, items_path, monkeypatch, tier=3) == 0

    exhausted = [u for u in read_jsonl(unmapped_path)
                 if u["reason"] == "standardize_exhausted"]
    assert len(exhausted) == 1                    # 1 sola entrada
    assert exhausted[0]["sample_url"] == "https://store.example/cjk1"

    # Excluido de las proyecciones LLM.
    assert json.load((audit_base / "tier2.json").open()) == []
    assert json.load((audit_base / "tier3.json").open()) == []


def test_below_threshold_still_projected(tmp_path, monkeypatch):
    """Con < MAX intentos el item SIGUE proyectándose (no se escala todavía)."""
    it = make_item(url="https://store.example/cjk2", title="別のシリーズ",
                   series_key="", series_display="", standardize_attempts=2)
    items_path, unmapped_path = setup_apply(tmp_path, monkeypatch, [it])
    audit_base = tmp_path / "audit"
    assert run_audit(audit_base, items_path, monkeypatch, tier=3) == 0

    # attempts=2 < 3 → NO exhausto: se proyecta a tier3, 0 unmapped exhausted.
    assert len(json.load((audit_base / "tier3.json").open())) == 1
    assert [u for u in read_jsonl(unmapped_path)
            if u["reason"] == "standardize_exhausted"] == []


# ---------------------------------------------------------------------------
# (iv) LLM devuelve un edition-kind en product_type → nunca aterriza ahí
# ---------------------------------------------------------------------------


def test_llm_edition_kind_never_lands_in_product_type(tmp_path, monkeypatch):
    # A: sin product_type + LLM "special" (edition-kind) → se re-deriva.
    a = make_item(url="https://store.example/a", title="Some Manga Vol 1",
                  series_key="wo-c-a", edition_key="wo-c-a-pub-special-es",
                  product_type="")
    # B: product_type válido + LLM "deluxe" (edition-kind) → conserva el válido.
    b = make_item(url="https://store.example/b", title="Art Of Something",
                  series_key="wo-c-b", edition_key="wo-c-b-pub-deluxe-es",
                  product_type="artbook")
    # C: LLM devuelve un product_type VÁLIDO del enum → se aplica.
    c = make_item(url="https://store.example/c", title="Some Novel Vol 1",
                  series_key="wo-c-c", edition_key="wo-c-c-pub-regular-es",
                  product_type="")
    items_path, _ = setup_apply(tmp_path, monkeypatch, [a, b, c])
    base = tmp_path / "run"
    write_result(base, [
        {"url": "https://store.example/a", "is_manga": True,
         "series_key": "wo-c-a", "product_type": "special"},
        {"url": "https://store.example/b", "is_manga": True,
         "series_key": "wo-c-b", "product_type": "deluxe"},
        {"url": "https://store.example/c", "is_manga": True,
         "series_key": "wo-c-c", "product_type": "novel"},
    ])

    rc = standardize_apply.cmd_merge(base, force_all=False)
    assert rc == 0

    by_url = {it["url"]: it for it in read_jsonl(items_path)}
    for it in by_url.values():
        assert it.get("standardized_at")
        assert it["product_type"] in standardize_apply.VALID_PRODUCT_TYPES
        assert it["product_type"] not in {"special", "deluxe", "variant",
                                          "limited", "collector"}
    assert by_url["https://store.example/b"]["product_type"] == "artbook"  # conservado
    assert by_url["https://store.example/c"]["product_type"] == "novel"    # LLM válido
