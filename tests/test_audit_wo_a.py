"""WO-A — auditoría post-scrape: rareza, fechas, tiers CJK, títulos, traducción
stale y backups timestamped. Un test por cambio (TDD), en archivo propio para no
colisionar con test_extraction.py.

Cambios cubiertos:
  1. _extract_print_run: cupo por persona + backstop <10.
  2. derive_rarity_tier: hueco KR + acentos PT/IT + no-reimpresión ES + guard in_stock.
  3. release_date: normalización en el sink de escritura (candidate_to_json).
  4. confidence_tier: degradar Tier 1 → 2 cuando CJK + resolución latina minoritaria.
  5. TITLE_JUNK_PREFIXES: prefijo wishlist AR (Tiendanube/Cúspide).
  6. Merge/upsert: invalidar description_es cuando el hash de la description no coincide.
  7. backup_and_rotate: slot timestamped opcional.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from scripts import manga_watch as mw


# ---------------------------------------------------------------------------
# #1 — _extract_print_run: cupo por persona + backstop <10
# ---------------------------------------------------------------------------

def test_print_run_per_person_quota_is_not_a_print_run():
    # "Limited to 2 copies per person" es un cupo de COMPRA, no una tirada.
    assert mw._extract_print_run("limited to 2 copies per person") is None


def test_print_run_legit_numbered_copies_kept():
    assert mw._extract_print_run("limited to 300 numbered copies") == 300


def test_print_run_jp_per_person_quota_is_none():
    # お一人様2点限り: cupo por persona JP (el número va DESPUÉS del marcador).
    assert mw._extract_print_run("お一人様2点限り") is None


def test_print_run_backstop_under_10():
    # No existen tiradas retail de <10 ejemplares.
    assert mw._extract_print_run("limited to 5 copies") is None
    assert mw._extract_print_run("limited to 10 copies") == 10


def test_print_run_per_person_multilang():
    assert mw._extract_print_run("limitée à 3 exemplaires par personne") is None
    assert mw._extract_print_run("limitiert auf 2 Exemplare pro Person") is None


# ---------------------------------------------------------------------------
# #2 — derive_rarity_tier: KR / PT / IT / ES + guard in_stock
# ---------------------------------------------------------------------------

def test_rarity_korean_hanjeongpan_is_rare():
    # 한정판 (LE de fábrica) → rare por no-reimpresión (sin stock verificado).
    assert mw.derive_rarity_tier([], "", "", "블루 아카이브 (한정판)") == "rare"


def test_rarity_korean_chohoe_is_rare():
    assert mw.derive_rarity_tier([], "", "초회한정 특전付き", "그날의 너") == "rare"


def test_rarity_pt_copias_accent_is_ultra_rare():
    # PT-BR "cópias" (con acento) → print run 500 → ultra_rare.
    assert mw.derive_rarity_tier([], "", "limitada a 500 cópias", "Berserk") == "ultra_rare"


def test_rarity_it_copie_numerate_is_ultra_or_super():
    # "400 copie numerate" → print run 400 → ultra_rare (≤500).
    r = mw.derive_rarity_tier([], "", "400 copie numerate", "Some IT Variant 1")
    assert r in ("ultra_rare", "super_rare")


def test_rarity_es_tirada_limitada_sin_reimpresion_is_rare():
    r = mw.derive_rarity_tier([], "", "tirada limitada sin reimpresión", "Akira")
    assert r == "rare"


def test_rarity_single_run_keyword_in_stock_not_rare():
    # 限定版 con stock verificado in_stock → el stock manda, NO rare.
    r = mw.derive_rarity_tier([], "", "", "限定版", stock_status="in_stock")
    assert r != "rare"


def test_rarity_single_run_keyword_without_stock_stays_rare():
    # Sin stock verificado, 限定版 sigue siendo evidencia de no-reimpresión → rare.
    assert mw.derive_rarity_tier([], "", "", "限定版") == "rare"


# ---------------------------------------------------------------------------
# #3 — release_date normalizado en el sink (candidate_to_json)
# ---------------------------------------------------------------------------

def _candidate_with_release(raw: str) -> mw.Candidate:
    c = mw.Candidate(
        title="Some Manga 1", url="http://x/1", source="JP - Store",
        source_url="http://x", country="Japón", language="Japonés",
        publisher="KADOKAWA", source_class="official", tags=[], description="d",
    )
    c.release_date = raw
    return c


def test_release_date_store_datetime_normalized_at_sink():
    row = mw.candidate_to_json(_candidate_with_release("2025/04/25 10:00:00"))
    assert row["release_date"] == "2025-04-25"


def test_release_date_jp_kanji_normalized_at_sink():
    row = mw.candidate_to_json(_candidate_with_release("2026年04月08日"))
    assert row["release_date"] == "2026-04-08"


def test_release_date_slash_ymd_normalized_at_sink():
    row = mw.candidate_to_json(_candidate_with_release("2026/03/17 10:00:00"))
    assert row["release_date"] == "2026-03-17"


def test_release_date_already_iso_passthrough():
    row = mw.candidate_to_json(_candidate_with_release("2026-04-08"))
    assert row["release_date"] == "2026-04-08"


# ---------------------------------------------------------------------------
# #4 — confidence_tier: CJK + resolución latina minoritaria
# ---------------------------------------------------------------------------

def _cand(title: str, sigs: list[str], pub: str) -> mw.Candidate:
    c = mw.Candidate(
        title=title, url="http://x", source="S", source_url="http://x",
        country="Japón", language="Japonés", publisher=pub,
        source_class="official", tags=[], description="",
    )
    c.signal_types = sigs
    return c


def test_confidence_tier_saekano_cjk_minority_latin_not_tier1():
    # series_key='flat' (4 chars, único latín del título CJK) → NO Tier 1.
    md = mw.derive_series_metadata(
        _cand("冴えない彼女の育てかた 深崎暮人画集 上 Flat.", ["artbook"], "KADOKAWA")
    )
    assert md.get("series_key") == "flat"
    assert md.get("confidence_tier") != 1


def test_confidence_tier_one_piece_bilingual_stays_tier1():
    # Latín sustancial ("ONE PIECE") → resolución confiable → Tier 1 preservado.
    md = mw.derive_series_metadata(_cand("ワンピース ONE PIECE", ["limited"], "Shueisha"))
    assert md.get("series_key") == "one-piece"
    assert md.get("confidence_tier") == 1


def test_has_cjk_helper():
    assert mw._has_cjk("ワンピース")
    assert mw._has_cjk("鬼滅の刃")
    assert mw._has_cjk("한정판")
    assert not mw._has_cjk("ONE PIECE")
    assert not mw._has_cjk("Berserk Deluxe 1")


# ---------------------------------------------------------------------------
# #5 — TITLE_JUNK_PREFIXES: wishlist AR
# ---------------------------------------------------------------------------

def test_clean_title_strips_ar_wishlist_prefix():
    out = mw.clean_title(
        "Agregar a mi lista de deseos! BECK 2 ranking en venta Kanzenban 100"
    )
    assert out.startswith("BECK 2")
    assert "lista de deseos" not in out.lower()


# ---------------------------------------------------------------------------
# #6 — Merge/upsert: description_es stale por hash de la description
# ---------------------------------------------------------------------------

def _run_merge(old: dict, new: dict) -> dict:
    d = Path(tempfile.mkdtemp())
    p = d / "items.jsonl"
    mw.append_jsonl(p, [old])
    mw.append_jsonl(p, [new])
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    return rows[0]


_BASE = dict(url="http://x/1", title="T", source="S", description="orig desc",
             country="JP", language="JP", publisher="P")


def test_description_src_hash_formula():
    import hashlib
    assert mw.description_src_hash("hola") == hashlib.sha1(b"hola").hexdigest()[:12]
    assert len(mw.description_src_hash("x")) == 12


def test_merge_no_hash_preserves_translation_backward_compat():
    old = dict(_BASE, description_es="TRAD")
    new = dict(_BASE, description="orig desc")
    assert _run_merge(old, new).get("description_es") == "TRAD"


def test_merge_hash_match_preserves_translation_and_hash():
    h = mw.description_src_hash("orig desc")
    old = dict(_BASE, description_es="TRAD", description_es_src_hash=h)
    new = dict(_BASE, description="orig desc")
    r = _run_merge(old, new)
    assert r.get("description_es") == "TRAD"
    assert r.get("description_es_src_hash") == h


def test_merge_hash_mismatch_drops_stale_translation():
    old = dict(_BASE, description_es="TRAD",
               description_es_src_hash=mw.description_src_hash("orig desc"))
    new = dict(_BASE, description="descripción NUEVA y distinta")
    r = _run_merge(old, new)
    assert not r.get("description_es")
    assert not r.get("description_es_src_hash")


def test_merge_standardized_hash_mismatch_drops_translation_keeps_other_curated():
    old = dict(_BASE, standardized_at="2026-01-01", description_es="TRAD",
               description_es_src_hash=mw.description_src_hash("orig desc"),
               series_key="berserk", edition_key="berserk-x")
    new = dict(_BASE, description="descripción NUEVA y distinta")
    r = _run_merge(old, new)
    assert not r.get("description_es")           # traducción stale descartada
    assert r.get("series_key") == "berserk"      # resto de campos curados intacto


def test_merge_standardized_hash_match_restores_translation():
    h = mw.description_src_hash("orig desc")
    old = dict(_BASE, standardized_at="2026-01-01", description_es="TRAD",
               description_es_src_hash=h, series_key="berserk", edition_key="berserk-x")
    new = dict(_BASE, description="orig desc")
    r = _run_merge(old, new)
    assert r.get("description_es") == "TRAD"
    assert r.get("description_es_src_hash") == h


# ---------------------------------------------------------------------------
# #7 — backup_and_rotate: slot timestamped opcional
# ---------------------------------------------------------------------------

def test_backup_default_fixed_slot_idempotent_name():
    d = Path(tempfile.mkdtemp())
    f = d / "items.jsonl"
    f.write_text("data")
    b1 = mw.backup_and_rotate(f, "scrape")
    b2 = mw.backup_and_rotate(f, "scrape")
    assert b1 == b2
    assert b1.name == "items.jsonl.pre-scrape-bak"


def test_backup_timestamped_name_and_rotation():
    d = Path(tempfile.mkdtemp())
    f = d / "items.jsonl"
    f.write_text("data")
    bdir = d / "backups" / "items.jsonl"
    bdir.mkdir(parents=True, exist_ok=True)
    # Pre-seed 3 backups timestamped viejos con mtimes escalonados.
    for i, ts in enumerate(("20200101-000000", "20200102-000000", "20200103-000000")):
        fp = bdir / f"items.jsonl.{ts}.pre-snap-bak"
        fp.write_text("old")
        os.utime(fp, (1000 + i, 1000 + i))
    dest = mw.backup_and_rotate(f, "snap", max_keep=3, timestamped=True)
    assert ".pre-snap-bak" in dest.name
    assert dest.name != "items.jsonl.pre-snap-bak"  # lleva timestamp, no slot fijo
    kept = sorted(p.name for p in bdir.glob("items.jsonl.*.pre-snap-bak"))
    assert len(kept) == 3                    # rotación conservó max_keep
    assert dest.name in kept                 # el nuevo está entre los conservados
    assert "items.jsonl.20200101-000000.pre-snap-bak" not in kept  # el más viejo se podó


def test_backup_timestamped_does_not_prune_fixed_slots():
    d = Path(tempfile.mkdtemp())
    f = d / "items.jsonl"
    f.write_text("data")
    fixed = mw.backup_and_rotate(f, "scrape")  # slot fijo de otro label
    mw.backup_and_rotate(f, "snap", max_keep=1, timestamped=True)
    assert fixed.exists()  # el glob timestamped no toca los slots fijos
