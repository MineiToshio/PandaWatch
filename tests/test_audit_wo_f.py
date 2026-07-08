"""Tests para WO-F (auditoría post-scrape, 2026-07-07):

- scripts/validate_corpus.py: flag --file, y las invariantes WARN nuevas
  (DATEISO, PTYPE_ENUM, LANG_ENUM, VOLRANGE, EKMALFORMED, SLUGUNIQ, SLUGFMT,
  STDKEYS, MIRRORREF, SRCURL). Ninguna es DURA — nunca deben mover el exit
  code (regla de oro del red team: nacen con violaciones vivas en el corpus
  real, promoverlas a dura frenaría el build).
- scripts/audit/data_quality.py: _compute_readiness (rarity_verify fiel al
  Step 0 del skill watch-validate-rarity, split traducción real vs sólo-marcar,
  filas nuevas dates_iso/no_image).
- scripts/audit/split_edition_buckets.py: detector read-only de ediciones que
  difieren SOLO en el slug de tipo.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scripts import manga_watch as mw
from scripts import validate_corpus as vc
from scripts.audit import data_quality as dq
from scripts.audit import split_edition_buckets as seb


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _base_item(**overrides) -> dict:
    """Item mínimo que pasa TODAS las invariantes (duras y warn) — punto de
    partida para tests que sólo quieren violar UNA cosa a la vez. El
    cluster_key se recalcula SIEMPRE con derive_cluster_key sobre el dict ya
    con overrides aplicados, así CLKEY nunca se rompe por accidente."""
    it = {
        "title": "Base Manga Regular 1",
        "url": "https://example.com/base-manga-regular-1",
        "series_key": "base-manga",
        "edition_key": "base-manga-panini-regular-es",
        "volume": "1",
        "slug": "base-manga-regular-1",
        "product_type": "manga",
        "release_date": "2025-01",
        "language": "Español",
        "country": "España",
        "publisher": "Panini",
        "sources": [{"url": "https://example.com/base-manga-regular-1", "name": "Test Source"}],
        "images": [],
    }
    it.update(overrides)
    it["cluster_key"] = mw.derive_cluster_key(it)
    return it


def _write_items(path: Path, items: list[dict]) -> Path:
    lines = [json.dumps(it, ensure_ascii=False) for it in items]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def _run_validate(tmp_path: Path, items: list[dict], monkeypatch, capsys,
                   examples: int = 10) -> tuple[int, str]:
    p = _write_items(tmp_path / "items.jsonl", items)
    monkeypatch.setattr(sys, "argv",
                        ["validate_corpus.py", "--file", str(p), "--examples", str(examples)])
    rc = vc.main()
    out = capsys.readouterr().out
    return rc, out


def _count_of(out: str, kind: str) -> int:
    m = re.search(rf"\]\s+{re.escape(kind)}\s+violaciones:\s+(\d+)", out)
    assert m, f"no se encontró la línea de {kind} en la salida:\n{out}"
    return int(m.group(1))


# --------------------------------------------------------------------------- #
# validate_corpus.py — --file
# --------------------------------------------------------------------------- #

def test_file_flag_reads_alternate_corpus(tmp_path, monkeypatch, capsys):
    items = [_base_item()]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert "(1 items)" in out
    assert rc == 0


def test_clean_corpus_triggers_no_new_warning(tmp_path, monkeypatch, capsys):
    """El item base no dispara NINGUNA invariante nueva (ni las viejas)."""
    items = [_base_item()]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert rc == 0
    for kind in ("DATEISO", "PTYPE_ENUM", "LANG_ENUM", "VOLRANGE", "EKMALFORMED",
                 "SLUGUNIQ", "SLUGFMT", "STDKEYS", "MIRRORREF", "SRCURL"):
        assert _count_of(out, kind) == 0, f"{kind} debería ser 0 en el corpus limpio"


# --------------------------------------------------------------------------- #
# validate_corpus.py — invariantes nuevas, una por una (siempre WARN, exit 0)
# --------------------------------------------------------------------------- #

def test_dateiso_flags_non_iso_release_date(tmp_path, monkeypatch, capsys):
    items = [_base_item(release_date="2025/04/25 10:00:00")]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert _count_of(out, "DATEISO") == 1
    assert rc == 0  # warning, nunca dura


def test_dateiso_accepts_year_and_year_month(tmp_path, monkeypatch, capsys):
    items = [_base_item(release_date="2025"), _base_item(
        url="https://example.com/2", release_date="2025-06",
        slug="base-manga-regular-2", volume="2")]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert _count_of(out, "DATEISO") == 0
    assert rc == 0


def test_ptype_enum_flags_unknown_product_type(tmp_path, monkeypatch, capsys):
    items = [_base_item(product_type="deluxe")]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert _count_of(out, "PTYPE_ENUM") == 1
    assert rc == 0


@pytest.mark.parametrize("ptype", ["manga", "artbook", "fanbook", "guidebook",
                                    "boxset", "novel", "magazine", "audiobook"])
def test_ptype_enum_accepts_all_known_values(tmp_path, monkeypatch, capsys, ptype):
    items = [_base_item(product_type=ptype)]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert _count_of(out, "PTYPE_ENUM") == 0
    assert rc == 0


def test_lang_enum_flags_non_canonical_and_reports_top_values(tmp_path, monkeypatch, capsys):
    items = [_base_item(language="Deutsch", url="https://example.com/a", slug="a-1"),
             _base_item(language="Deutsch", url="https://example.com/b", slug="b-1",
                        series_key="other-manga", edition_key="other-manga-panini-regular-es"),
             _base_item(language="ja", url="https://example.com/c", slug="c-1",
                        series_key="third-manga", edition_key="third-manga-panini-regular-es")]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert _count_of(out, "LANG_ENUM") == 3
    assert "'Deutsch' ×2" in out
    assert rc == 0


def test_lang_enum_accepts_canonical_spanish_names(tmp_path, monkeypatch, capsys):
    items = [_base_item(language="Japonés")]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert _count_of(out, "LANG_ENUM") == 0


def test_volrange_flags_zero_and_absurd_values(tmp_path, monkeypatch, capsys):
    items = [
        _base_item(volume="0", url="https://example.com/a", slug="a-1"),
        _base_item(volume="4000000000", url="https://example.com/b", slug="b-1",
                   series_key="other-manga", edition_key="other-manga-panini-regular-es"),
        _base_item(volume="2025", url="https://example.com/c", slug="c-1",
                   series_key="third-manga", edition_key="third-manga-panini-regular-es"),
    ]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert _count_of(out, "VOLRANGE") == 3
    assert rc == 0


def test_volrange_accepts_valid_range(tmp_path, monkeypatch, capsys):
    items = [_base_item(volume="120")]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert _count_of(out, "VOLRANGE") == 0


def test_ekmalformed_flags_broken_suffix_but_not_xx(tmp_path, monkeypatch, capsys):
    items = [
        _base_item(edition_key="base-manga-panini-variant-glob",
                   series_key="base-manga"),
        _base_item(url="https://example.com/xx", slug="base-manga-regular-2",
                   volume="2", edition_key="base-manga-panini-regular-xx",
                   series_key="base-manga"),
    ]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert _count_of(out, "EKMALFORMED") == 1  # sólo el sufijo "glob", NO "xx"
    assert _count_of(out, "PAIS") == 2          # PAIS sí flaggea ambos (incl. xx)
    assert rc == 0


def test_slugfmt_flags_invalid_slug_chars(tmp_path, monkeypatch, capsys):
    items = [_base_item(slug="Base_Manga Regular 1")]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert _count_of(out, "SLUGFMT") == 1
    assert rc == 0


def test_sluguniq_flags_same_slug_different_clusters(tmp_path, monkeypatch, capsys):
    items = [
        _base_item(slug="same-slug", url="https://example.com/a"),
        _base_item(slug="same-slug", url="https://example.com/b",
                   series_key="other-manga", edition_key="other-manga-panini-regular-es",
                   volume="2"),
    ]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert _count_of(out, "SLUGUNIQ") == 1
    assert rc == 0


def test_stdkeys_flags_standardized_without_keys(tmp_path, monkeypatch, capsys):
    items = [_base_item(standardized_at="2026-07-07T00:00:00Z", edition_key="")]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert _count_of(out, "STDKEYS") == 1
    assert rc == 0


def test_stdkeys_ok_when_standardized_with_keys(tmp_path, monkeypatch, capsys):
    items = [_base_item(standardized_at="2026-07-07T00:00:00Z")]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert _count_of(out, "STDKEYS") == 0


def test_mirrorref_flags_missing_local_file(tmp_path, monkeypatch, capsys):
    items = [_base_item(images=[{"local": "definitely_missing_test_file_xyz123.avif",
                                  "url": "https://example.com/x.jpg"}])]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert _count_of(out, "MIRRORREF") == 1
    assert "refs con local revisadas" in out
    assert rc == 0


def test_srcurl_flags_empty_sources_and_missing_url(tmp_path, monkeypatch, capsys):
    items = [
        _base_item(sources=[], url="https://example.com/a"),
        _base_item(sources=[{"url": ""}], url="https://example.com/b",
                   series_key="other-manga", edition_key="other-manga-panini-regular-es",
                   volume="2", slug="other-manga-regular-2"),
    ]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert _count_of(out, "SRCURL") == 2
    assert rc == 0


def test_hard_invariants_still_gate_exit_code(tmp_path, monkeypatch, capsys):
    """Sanity: una violación DURA real (slug vacío) sigue devolviendo exit 2 —
    las invariantes nuevas no interfieren con el gate existente."""
    items = [_base_item(slug="")]
    rc, out = _run_validate(tmp_path, items, monkeypatch, capsys)
    assert rc == 2
    assert _count_of(out, "SLUG") == 1


def test_real_corpus_exit_code_unchanged():
    """El corpus real sigue dando el MISMO exit code (0) con las invariantes
    nuevas activas — sólo agregan warnings, no rompen el gate del pipeline.
    Lee data/items.jsonl (permitido: sólo lectura, para verificar conteos)."""
    root = Path(__file__).resolve().parent.parent
    items_path = root / "data" / "items.jsonl"
    if not items_path.exists():
        pytest.skip("data/items.jsonl no existe en este entorno")
    import subprocess
    result = subprocess.run(
        [".venv/bin/python", "scripts/validate_corpus.py"],
        cwd=root, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout[-2000:]


# --------------------------------------------------------------------------- #
# data_quality.py — _uncertainty_reason / _is_hispanic_source
# --------------------------------------------------------------------------- #

def test_uncertainty_reason_referencia():
    it = {"title": "Some Manga Special", "description": "", "source": "Global - Mangavariant",
          "sources": [{"name": "Global - Mangavariant"}]}
    assert dq._uncertainty_reason(it) == "referencia"


def test_uncertainty_reason_retailer_exclusive():
    it = {"title": "Some Manga", "description": "", "source": "AnimeClick",
          "signal_types": ["retailer_exclusive"], "sources": [{"name": "AnimeClick"}]}
    assert dq._uncertainty_reason(it) == "retailer_exclusive"


def test_uncertainty_reason_none_when_out_of_stock():
    it = {"title": "Some Manga", "description": "", "source": "Global - Mangavariant",
          "stock_status": "out_of_stock", "sources": [{"name": "Global - Mangavariant"}]}
    assert dq._uncertainty_reason(it) is None


def test_uncertainty_reason_none_with_structural_evidence():
    it = {"title": "Some Manga", "description": "tirada limitada de 300 copias",
          "source": "Global - Mangavariant", "sources": [{"name": "Global - Mangavariant"}]}
    assert dq._uncertainty_reason(it) is None


def test_uncertainty_reason_none_for_retailer_source():
    it = {"title": "Some Manga", "description": "", "source": "Starcomics",
          "sources": [{"name": "Starcomics"}]}
    assert dq._uncertainty_reason(it) is None


def test_is_hispanic_source_by_language():
    assert dq._is_hispanic_source({"language": "Español", "country": "Alemania"})
    assert not dq._is_hispanic_source({"language": "Deutsch", "country": "España"})


def test_is_hispanic_source_falls_back_to_country():
    assert dq._is_hispanic_source({"language": "", "country": "México"})
    assert not dq._is_hispanic_source({"language": "", "country": "Japón"})


# --------------------------------------------------------------------------- #
# data_quality.py — _compute_readiness
# --------------------------------------------------------------------------- #

def test_compute_readiness_splits_translation_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(dq, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    items = [
        # Fuente NO hispana, sin description_es → traducción real.
        {"description": "German text", "language": "Deutsch", "country": "Alemania"},
        # Fuente hispana, sin description_es → sólo falta marcar.
        {"description": "Texto en español", "language": "Español", "country": "España"},
        # Ya tiene la key → no cuenta en ninguna cubeta.
        {"description": "Something", "description_es": "Algo", "language": "Inglés",
         "country": "Estados Unidos"},
    ]
    readiness = dq._compute_readiness(items, multi_clusters=0, card_ne_carrusel=0)
    by_id = {r["id"]: r for r in readiness}
    assert by_id["translate"]["pending"] == 1
    assert by_id["translate_mark_es"]["pending"] == 1


def test_compute_readiness_dates_iso_row(tmp_path, monkeypatch):
    monkeypatch.setattr(dq, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    items = [
        {"release_date": "2025/04/25 10:00:00"},
        {"release_date": "2025-06"},
        {"release_date": ""},
    ]
    readiness = dq._compute_readiness(items, multi_clusters=0, card_ne_carrusel=0)
    by_id = {r["id"]: r for r in readiness}
    assert by_id["dates_iso"]["pending"] == 1


def test_compute_readiness_no_image_row_passthrough(tmp_path, monkeypatch):
    monkeypatch.setattr(dq, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    readiness = dq._compute_readiness([], multi_clusters=0, card_ne_carrusel=0, sin_imagen=205)
    by_id = {r["id"]: r for r in readiness}
    assert by_id["no_image"]["pending"] == 205


def test_compute_readiness_rarity_verify_uses_uncertainty_criterion(tmp_path, monkeypatch):
    monkeypatch.setattr(dq, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    items = [
        # rare por incertidumbre (referencia) → cuenta.
        {"rarity": "rare", "title": "A", "description": "", "source": "Global - Mangavariant",
         "sources": [{"name": "Global - Mangavariant"}]},
        # rare con evidencia ESTRUCTURAL → NO cuenta (el skill no lo toca).
        {"rarity": "rare", "title": "B", "description": "tirada limitada",
         "source": "Starcomics", "sources": [{"name": "Starcomics"}]},
        # boxset rare pero de retailer normal, sin incertidumbre → NO cuenta
        # bajo el criterio nuevo (el filtro viejo product_type lo hubiera contado).
        {"rarity": "rare", "title": "C", "description": "", "product_type": "boxset",
         "source": "Starcomics", "sources": [{"name": "Starcomics"}]},
        # ya verificado → no cuenta.
        {"rarity": "rare", "title": "D", "description": "", "source": "Global - Mangavariant",
         "sources": [{"name": "Global - Mangavariant"}], "rarity_verified_at": "2026-07-01"},
        # approved → no cuenta.
        {"rarity": "rare", "title": "E", "description": "", "source": "Global - Mangavariant",
         "sources": [{"name": "Global - Mangavariant"}], "approved_at": "2026-07-01"},
    ]
    readiness = dq._compute_readiness(items, multi_clusters=0, card_ne_carrusel=0)
    by_id = {r["id"]: r for r in readiness}
    assert by_id["rarity_verify"]["pending"] == 1


def test_audit_items_end_to_end_readiness_wiring(tmp_path, monkeypatch):
    """audit_items() pasa correctamente sin_imagen a _compute_readiness (no
    recorre el corpus dos veces)."""
    monkeypatch.setattr(dq, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    items = [
        {"title": "No image item", "url": "https://x/1", "cluster_key": "url:1",
         "sources": [{"url": "https://x/1"}]},
        {"title": "Has image", "url": "https://x/2", "cluster_key": "url:2",
         "sources": [{"url": "https://x/2"}],
         "images": [{"url": "https://x/img.jpg"}]},
    ]
    report = dq.audit_items(items, px=90000, measure=False)
    by_id = {r["id"]: r for r in report["readiness"]}
    assert by_id["no_image"]["pending"] == 1


# --------------------------------------------------------------------------- #
# split_edition_buckets.py
# --------------------------------------------------------------------------- #

def test_parse_edition_key_valid_single_token_publisher():
    countries = set(mw._COUNTRY_SLUG_MAP.values())
    slugs = mw._KNOWN_EDITION_SLUGS
    pubs = set(mw._PUBLISHER_SLUG_MAP.values()) | {"unknown"}
    parsed = seb._parse_edition_key("berserk-panini-deluxe-it", countries, slugs, pubs)
    assert parsed == ("berserk", "panini", "deluxe", "it")


def test_parse_edition_key_two_token_publisher():
    countries = set(mw._COUNTRY_SLUG_MAP.values())
    slugs = mw._KNOWN_EDITION_SLUGS
    pubs = set(mw._PUBLISHER_SLUG_MAP.values()) | {"unknown"}
    assert "ivrea-ar" in pubs
    parsed = seb._parse_edition_key("gon-ivrea-ar-collector-ar", countries, slugs, pubs)
    assert parsed == ("gon", "ivrea-ar", "collector", "ar")


def test_parse_edition_key_strips_collision_suffix():
    countries = set(mw._COUNTRY_SLUG_MAP.values())
    slugs = mw._KNOWN_EDITION_SLUGS
    pubs = set(mw._PUBLISHER_SLUG_MAP.values()) | {"unknown"}
    parsed = seb._parse_edition_key("berserk-panini-deluxe-it-c2", countries, slugs, pubs)
    assert parsed == ("berserk", "panini", "deluxe", "it")


def test_parse_edition_key_rejects_unknown_slug_or_country():
    countries = set(mw._COUNTRY_SLUG_MAP.values())
    slugs = mw._KNOWN_EDITION_SLUGS
    pubs = set(mw._PUBLISHER_SLUG_MAP.values()) | {"unknown"}
    assert seb._parse_edition_key("some-series-panini-totallybogus-it", countries, slugs, pubs) is None
    assert seb._parse_edition_key("some-series-panini-deluxe-zz", countries, slugs, pubs) is None


def _ek_item(edition_key, series_key, volume, slug_title, isbn="", cluster_key=None,
             source_name="Test Source"):
    it = {
        "title": slug_title,
        "url": f"https://example.com/{edition_key}",
        "series_key": series_key,
        "edition_key": edition_key,
        "volume": volume,
        "isbn": isbn,
        "sources": [{"name": source_name, "url": f"https://example.com/{edition_key}"}],
        "source": source_name,
    }
    it["cluster_key"] = cluster_key or mw.derive_cluster_key(it)
    return it


def test_find_buckets_detects_type_slug_only_split():
    items = [
        _ek_item("berserk-panini-deluxe-it", "berserk", "1", "Berserk Deluxe 1"),
        _ek_item("berserk-panini-boxset-it", "berserk", "1", "Berserk Boxset 1"),
    ]
    buckets, n_non_lmc = seb.find_buckets(items)
    assert n_non_lmc == 2
    assert len(buckets) == 1
    b = buckets[0]
    assert b["series_key"] == "berserk"
    assert b["country"] == "it"
    assert {e["edition_key"] for e in b["edition_keys"]} == {
        "berserk-panini-deluxe-it", "berserk-panini-boxset-it"}
    assert b["shared_isbn"] == []


def test_find_buckets_flags_shared_isbn_as_strong_signal():
    items = [
        _ek_item("devilman-mangaline-special-mx", "devilman", "3", "Devilman #3",
                 isbn="9788419177629"),
        _ek_item("devilman-mangaline-variant-mx", "devilman", "3", "Devilman #3 variant",
                 isbn="9788419177629"),
    ]
    buckets, _ = seb.find_buckets(items)
    assert len(buckets) == 1
    assert buckets[0]["shared_isbn"] == ["9788419177629"]


def test_find_buckets_excludes_lmc_clustered_items():
    items = [
        _ek_item("berserk-panini-deluxe-it", "berserk", "1", "Berserk Deluxe 1",
                 cluster_key="lmc:123:deluxe:1"),
        _ek_item("berserk-panini-boxset-it", "berserk", "1", "Berserk Boxset 1",
                 cluster_key="lmc:123:boxset:1"),
    ]
    buckets, n_non_lmc = seb.find_buckets(items)
    assert n_non_lmc == 0
    assert buckets == []


def test_find_buckets_no_bucket_for_single_edition_key():
    items = [_ek_item("berserk-panini-deluxe-it", "berserk", "1", "Berserk Deluxe 1")]
    buckets, n_non_lmc = seb.find_buckets(items)
    assert n_non_lmc == 1
    assert buckets == []


def test_find_buckets_different_publisher_does_not_bucket():
    """Mismo (series, país, volumen) pero editorial DISTINTA — no es 'difieren
    SOLO en el slug de tipo', así que no debe agruparse como sospechoso."""
    items = [
        _ek_item("berserk-panini-deluxe-it", "berserk", "1", "Berserk Deluxe 1"),
        _ek_item("berserk-star-boxset-it", "berserk", "1", "Berserk Boxset 1"),
    ]
    buckets, _ = seb.find_buckets(items)
    assert buckets == []


def test_split_edition_buckets_script_is_read_only(tmp_path, monkeypatch, capsys):
    """Corrida sin --json no debe escribir NADA."""
    items = [
        _ek_item("berserk-panini-deluxe-it", "berserk", "1", "Berserk Deluxe 1"),
        _ek_item("berserk-panini-boxset-it", "berserk", "1", "Berserk Boxset 1"),
    ]
    p = _write_items(tmp_path / "items.jsonl", items)
    before = set(tmp_path.iterdir())
    monkeypatch.setattr(sys, "argv", ["split_edition_buckets.py", "--file", str(p)])
    rc = seb.main()
    after = set(tmp_path.iterdir())
    assert rc == 0
    assert before == after  # no se creó ningún archivo nuevo
    out = capsys.readouterr().out
    assert "SPLIT EDITION BUCKETS" in out
