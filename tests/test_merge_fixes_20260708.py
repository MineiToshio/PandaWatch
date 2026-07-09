"""Tests del paquete MERGE de la auditoría Fable 2026-07-08.

Cubre los fixes del corazón del merge/estado (manga_watch.py):

  A4  — description entrante vacía NO destruye description / description_es.
  A5  — process_state NO colapsa dos productos distintos por ISBN pelado.
  A9  — union-merge de images[] es FUENTE ÚNICA (merge_cluster == append_jsonl).
  B15 — merge_cluster rellena por confiabilidad (source_class), no orden físico.
  M11 — rarity sticky condicionada a evidencia curada/verificada.
  M13 — detected_at fuera de _VOLATILE_FIELDS (no salta al re-scrapear aprobados).
  #9  — normalize_isbn REAL: checksum 10/13, 10→13, X, multi-ISBN, GS1 978/979.
  #10 — PRODUCT_TYPE_ENUM export + derive_product_type ⊆ enum.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import manga_watch as mw


def _read_rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _row_by_url(rows: list[dict], url: str) -> dict:
    key = mw.normalize_url_for_dedup(url)
    for r in rows:
        srcs = r.get("sources") or []
        urls = [s.get("url", "") for s in srcs] + [r.get("url", "")]
        if any(mw.normalize_url_for_dedup(u) == key for u in urls if u):
            return r
    raise AssertionError(f"no row for {url}")


# ---------------------------------------------------------------------------
# A4 — description entrante vacía no destruye description ni description_es
# ---------------------------------------------------------------------------

def test_a4_empty_description_preserves_raw_description(tmp_path):
    url = "https://ex/a4-raw"
    path = tmp_path / "items.jsonl"
    old = {"url": url, "title": "Berserk 1", "country": "Japan",
           "description": "Descripción original del tomo"}
    mw.append_jsonl(path, [old])
    # Re-scrape que NO recapturó la descripción (drift de selector).
    mw.append_jsonl(path, [{"url": url, "title": "Berserk 1", "country": "Japan"}])
    row = _row_by_url(_read_rows(path), url)
    assert row.get("description") == "Descripción original del tomo"


def test_a4_empty_description_preserves_translation(tmp_path):
    url = "https://ex/a4-tr"
    path = tmp_path / "items.jsonl"
    desc = "Original description in English"
    old = {"url": url, "title": "Berserk 1", "country": "Japan",
           "description": desc, "description_es": "Descripción en español",
           "description_es_src_hash": mw.description_src_hash(desc)}
    mw.append_jsonl(path, [old])
    # Re-scrape sin descripción → la traducción pagada NO se descarta.
    mw.append_jsonl(path, [{"url": url, "title": "Berserk 1", "country": "Japan"}])
    row = _row_by_url(_read_rows(path), url)
    assert row.get("description_es") == "Descripción en español"
    assert row.get("description") == desc


def test_a4_new_description_marks_translation_stale(tmp_path):
    url = "https://ex/a4-stale"
    path = tmp_path / "items.jsonl"
    desc = "Original description in English"
    old = {"url": url, "title": "Berserk 1", "country": "Japan",
           "description": desc, "description_es": "Descripción vieja",
           "description_es_src_hash": mw.description_src_hash(desc)}
    mw.append_jsonl(path, [old])
    # Re-scrape CON una descripción NUEVA y distinta → traducción stale, se descarta.
    mw.append_jsonl(path, [{"url": url, "title": "Berserk 1", "country": "Japan",
                            "description": "A completely different synopsis"}])
    row = _row_by_url(_read_rows(path), url)
    assert row.get("description") == "A completely different synopsis"
    assert not row.get("description_es")


def test_a4_translation_is_stale_empty_new_is_not_stale():
    old = {"description_es_src_hash": mw.description_src_hash("Some text")}
    assert mw._translation_is_stale(old, "") is False
    assert mw._translation_is_stale(old, "Different text") is True


def test_a4_standardized_empty_description_preserved(tmp_path):
    url = "https://ex/a4-std"
    path = tmp_path / "items.jsonl"
    old = {"url": url, "title": "One Piece Kanzenban 1", "country": "Japan",
           "standardized_at": "2026-06-01", "edition_key": "op-kanzenban-jp",
           "volume": "1", "description": "Sinopsis estandarizada"}
    mw.append_jsonl(path, [old])
    mw.append_jsonl(path, [{"url": url, "title": "One Piece 1", "country": "Japan"}])
    row = _row_by_url(_read_rows(path), url)
    assert row.get("description") == "Sinopsis estandarizada"


# ---------------------------------------------------------------------------
# A5 — process_state no colapsa dos productos distintos por ISBN pelado
# ---------------------------------------------------------------------------

def _coll_candidate(**over):
    base = dict(
        title="Berserk Deluxe Edition 1",
        url="https://ex/deluxe-1",
        source="Dark Horse",
        source_url="https://darkhorse.com/manga",
        country="USA",
        language="Inglés",
        publisher="Dark Horse",
        source_class="official",
        tags=[],
        description="Deluxe hardcover edition",
        score=80,
        signal_types=["deluxe"],
        content_hash="h1",
    )
    base.update(over)
    return mw.Candidate(**base)


def test_a5_same_isbn_distinct_products_both_survive():
    # Dos productos DISTINTOS (Devilman #3 y Mao Dante #1) comparten el mismo
    # ISBN pelado en manga — la decisión #4 eliminó el tier isbn: por esto.
    c1 = _coll_candidate(title="Devilman Deluxe 3", url="https://ex/devilman-3",
                         isbn="9788419177629", content_hash="h1")
    c2 = _coll_candidate(title="Mao Dante Deluxe 1", url="https://ex/mao-dante-1",
                         isbn="9788419177629", content_hash="h2")
    reportable, state = mw.process_state([c1, c2], {}, min_score=20, include_seen=False)
    urls = {c.url for c in reportable}
    assert urls == {"https://ex/devilman-3", "https://ex/mao-dante-1"}
    # Ambos entran al state (si no, el perdedor se re-flushea como "new" para
    # siempre — el churn que describe A5).
    assert len(state) == 2


# ---------------------------------------------------------------------------
# A9 — union-merge de images[] es FUENTE ÚNICA (merge_cluster == append_jsonl)
# ---------------------------------------------------------------------------

def test_a9_merge_cluster_fills_local_from_duplicate():
    # La canónica tiene la portada SIN local; otro miembro la tiene con el
    # espejo (local). Al consolidar, el local no se pierde (síntoma de #87).
    canonical = {"url": "https://ex/canon", "cluster_key": "edition:x|1",
                 "approved_at": "2026-01-01",
                 "images": [{"url": "https://cdn/cover.jpg", "kind": "cover"}]}
    other = {"url": "https://ex/other", "cluster_key": "edition:x|1",
             "images": [{"url": "https://cdn/cover.jpg", "kind": "cover",
                         "local": "abc123.avif"}]}
    merged = mw.merge_cluster([canonical, other])
    cover = merged["images"][0]
    assert cover["local"] == "abc123.avif"


def test_a9_merge_cluster_key_is_kind_plus_stem():
    # Misma URL-stem pero kind distinto (cover vs extra) → NO se deduplican
    # (paridad con append_jsonl, que dedupea por (kind, stem)). Dos miembros
    # para forzar el path real de union (con 1 miembro merge_cluster retorna).
    canonical = {"url": "https://ex/canon", "cluster_key": "edition:x|1",
                 "approved_at": "2026-01-01",
                 "images": [{"url": "https://cdn/img.jpg", "kind": "cover"}]}
    other = {"url": "https://ex/other", "cluster_key": "edition:x|1",
             "images": [{"url": "https://cdn/img.jpg", "kind": "extra"}]}
    merged = mw.merge_cluster([canonical, other])
    kinds = sorted(im.get("kind") for im in merged["images"])
    assert kinds == ["cover", "extra"]


def test_a9_merge_cluster_no_aliasing():
    # El dict de imagen del resultado NO es el mismo objeto que el del miembro
    # (append hace dict(im); merge_cluster debe hacer lo mismo).
    src_img = {"url": "https://cdn/cover.jpg", "kind": "cover"}
    canonical = {"url": "https://ex/canon", "cluster_key": "edition:x|1",
                 "approved_at": "2026-01-01", "images": [src_img]}
    other = {"url": "https://ex/other", "cluster_key": "edition:x|1",
             "images": [{"url": "https://cdn/cover.jpg", "kind": "cover"}]}
    merged = mw.merge_cluster([canonical, other])
    assert merged["images"][0] is not src_img


def test_a9_union_merge_images_helper_exists():
    # La función única debe existir y ser usable por ambos sitios.
    out = mw._union_merge_images([
        {"url": "https://cdn/a.jpg", "kind": "cover"},
        {"url": "https://cdn/a.jpg", "kind": "cover", "local": "l.avif"},
    ])
    assert len(out) == 1
    assert out[0]["local"] == "l.avif"


# ---------------------------------------------------------------------------
# B15 — merge_cluster rellena por confiabilidad (source_class), no orden físico
# ---------------------------------------------------------------------------

def test_b15_publisher_prefers_reliable_source():
    # Canónica (aprobada, source_class bajo) SIN publisher. Dos miembros con
    # publisher: uno retailer ruidoso (primero en orden físico), uno official.
    # Debe ganar el official aunque venga después.
    canonical = {"url": "https://ex/canon", "cluster_key": "edition:x|1",
                 "approved_at": "2026-01-01", "source_class": "social",
                 "publisher": ""}
    retailer = {"url": "https://ex/retailer", "cluster_key": "edition:x|1",
                "source_class": "retailer", "publisher": "Tienda Ruidosa SL"}
    official = {"url": "https://ex/official", "cluster_key": "edition:x|1",
                "source_class": "official", "publisher": "Editorial Oficial"}
    merged = mw.merge_cluster([canonical, retailer, official])
    assert merged["publisher"] == "Editorial Oficial"


def test_b15_tie_keeps_physical_order():
    # Empate de confiabilidad (dos retailers) → primer no-vacío en orden físico.
    canonical = {"url": "https://ex/canon", "cluster_key": "edition:x|1",
                 "approved_at": "2026-01-01", "source_class": "social",
                 "release_date": ""}
    a = {"url": "https://ex/a", "cluster_key": "edition:x|1",
         "source_class": "retailer", "release_date": "2025-01-01"}
    b = {"url": "https://ex/b", "cluster_key": "edition:x|1",
         "source_class": "retailer", "release_date": "2025-02-02"}
    merged = mw.merge_cluster([canonical, a, b])
    assert merged["release_date"] == "2025-01-01"


# ---------------------------------------------------------------------------
# M11 — rarity sticky condicionada a evidencia curada/verificada
# ---------------------------------------------------------------------------

def test_m11_rarity_verified_is_sticky(tmp_path):
    url = "https://ex/m11-verified"
    path = tmp_path / "items.jsonl"
    old = {"url": url, "title": "Berserk 1", "country": "Japan",
           "rarity": "common", "rarity_verified_at": "2026-06-01"}
    mw.append_jsonl(path, [old])
    # Re-scrape que deriva 'rare' — NO debe pisar la rareza verificada por web.
    mw.append_jsonl(path, [{"url": url, "title": "Berserk 1", "country": "Japan",
                            "rarity": "rare"}])
    row = _row_by_url(_read_rows(path), url)
    assert row.get("rarity") == "common"


def test_m11_rarity_raw_over_raw_takes_new(tmp_path):
    url = "https://ex/m11-raw"
    path = tmp_path / "items.jsonl"
    # Fila vieja RAW (sin verified/standardized/approved): la evidencia nueva gana.
    old = {"url": url, "title": "Berserk 1", "country": "Japan", "rarity": "common"}
    mw.append_jsonl(path, [old])
    mw.append_jsonl(path, [{"url": url, "title": "Berserk 1", "country": "Japan",
                            "rarity": "super_rare"}])
    row = _row_by_url(_read_rows(path), url)
    assert row.get("rarity") == "super_rare"


def test_m11_rarity_sticky_when_standardized(tmp_path):
    url = "https://ex/m11-std"
    path = tmp_path / "items.jsonl"
    old = {"url": url, "title": "Berserk 1", "country": "Japan",
           "standardized_at": "2026-06-01", "rarity": "common"}
    mw.append_jsonl(path, [old])
    mw.append_jsonl(path, [{"url": url, "title": "Berserk 1", "country": "Japan",
                            "rarity": "rare"}])
    row = _row_by_url(_read_rows(path), url)
    # Estandarizado va por la rama _CURATED_FIELDS (rarity no está ahí) pero el
    # sticky condicionado lo protege por standardized_at.
    assert row.get("rarity") == "common"


# ---------------------------------------------------------------------------
# M13 — detected_at fuera de _VOLATILE_FIELDS
# ---------------------------------------------------------------------------

def test_m13_approved_rescrape_preserves_detected_at(tmp_path):
    url = "https://ex/m13"
    path = tmp_path / "items.jsonl"
    old = {"url": url, "title": "Berserk 1", "country": "Japan",
           "approved_at": "2026-01-01", "detected_at": "2025-01-01T00:00:00+00:00"}
    mw.append_jsonl(path, [old])
    mw.append_jsonl(path, [{"url": url, "title": "Berserk 1", "country": "Japan",
                            "detected_at": "2026-07-08T00:00:00+00:00",
                            "stock_type": "in_stock"}])
    row = _row_by_url(_read_rows(path), url)
    assert row.get("detected_at") == "2025-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# #9 — normalize_isbn REAL: checksum, 10→13, X, multi-ISBN, GS1
# ---------------------------------------------------------------------------

def test_isbn_valid_13_passthrough():
    assert mw.normalize_isbn("9781506711980") == "9781506711980"


def test_isbn_strips_fullwidth_colon_and_hyphens():
    assert mw.normalize_isbn("： 978-1-5067-1198-0") == "9781506711980"


def test_isbn_valid_10_converts_to_13():
    # 1974718190 (ISBN-10 válido) → 9781974718191.
    assert mw.normalize_isbn("1974718190") == "9781974718191"


def test_isbn_valid_10_with_x_converts():
    # 080442957X (ISBN-10 válido con dígito de control X).
    assert mw.normalize_isbn("0-8044-2957-X") == "9780804429573"


def test_isbn_x_in_wrong_position_not_valid():
    # X solo válida como último dígito de un ISBN-10; en medio no valida.
    out = mw.normalize_isbn("08044X957X")
    assert out != "9780804429573"  # no se trató como ISBN-10 válido


def test_isbn_multi_takes_first_valid():
    # Dos ISBN-13 válidos en un campo → el primero.
    assert mw.normalize_isbn("9781506711980 / 9784592143741") == "9781506711980"


def test_isbn_gs1_979_valid():
    # 9791234567896 (prefijo GS1 979, checksum válido).
    assert mw.normalize_isbn("9791234567896") == "9791234567896"


def test_isbn_gs1_wrong_prefix_rejected(capsys):
    # 9770000000003: checksum válido pero prefijo 977 (ISSN) → NO es ISBN.
    out = mw.normalize_isbn("9770000000003")
    # No se acepta como ISBN válido (fail-safe + anomaly).
    assert "ISBN_ANOMALY" in capsys.readouterr().err


def test_isbn_deluxe_junk_not_corrupted():
    # Caso podrido del reporte: "...980 Deluxe" NO debe almacenarse con la X de
    # "Deluxe" pegada (…980X). El ISBN válido gana; la X de Deluxe se ignora.
    assert mw.normalize_isbn("9781506711980 Deluxe Edition") == "9781506711980"


def test_isbn_invalid_checksum_failsafe(capsys):
    # ISBN-13 con checksum inválido: fail-safe conserva el valor limpio + anomaly.
    out = mw.normalize_isbn("9781506711981")
    assert out == "9781506711981"
    assert "ISBN_ANOMALY" in capsys.readouterr().err


def test_isbn_empty_and_only_junk():
    assert mw.normalize_isbn("") == ""
    assert mw.normalize_isbn("： ") == ""


def test_isbn_idempotent_on_valid():
    once = mw.normalize_isbn("1974718190")
    assert mw.normalize_isbn(once) == once == "9781974718191"


def test_isbn10_check_helper():
    assert mw._isbn10_check("1974718190") is True
    assert mw._isbn10_check("080442957X") is True
    assert mw._isbn10_check("1974718191") is False  # checksum malo
    assert mw._isbn10_check("08044X957X") is False  # X mal puesta


def test_isbn10_to_13_helper():
    assert mw._isbn10_to_13("1974718190") == "9781974718191"


# ---------------------------------------------------------------------------
# B7 — extractores estructurados exigen checksum ISBN-10
# ---------------------------------------------------------------------------

def test_b7_extract_isbn_rejects_bad_10():
    # Un SKU de 10 dígitos sin checksum válido NO debe entrar como ISBN.
    from bs4 import BeautifulSoup
    soup = BeautifulSoup('<meta itemprop="isbn" content="1234567890">', "html.parser")
    assert mw.extract_isbn("", soup) == ""


def test_b7_extract_isbn_accepts_valid_10_as_13():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup('<meta itemprop="isbn" content="1974718190">', "html.parser")
    assert mw.extract_isbn("", soup) == "9781974718191"


# ---------------------------------------------------------------------------
# #10 — PRODUCT_TYPE_ENUM export
# ---------------------------------------------------------------------------

def test_product_type_enum_exported():
    assert isinstance(mw.PRODUCT_TYPE_ENUM, frozenset)
    assert {"manga", "artbook", "boxset", "novel", "magazine"} <= mw.PRODUCT_TYPE_ENUM


def test_derive_product_type_within_enum():
    cases = [
        ("Naruto 1", "", []),
        ("One Piece Artbook Color Walk", "", []),
        ("Berserk Box Set", "", []),
        ("Re:Zero Light Novel 1", "", []),
        ("ONE PIECE magazine Vol.1", "", []),
        ("Kimetsu Fanbook", "", []),
        ("", "", []),
    ]
    for title, desc, sig in cases:
        pt = mw.derive_product_type(title, desc, sig)
        assert pt == "" or pt in mw.PRODUCT_TYPE_ENUM, f"{title!r} → {pt!r}"
