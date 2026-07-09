"""WO-H (auditoría post-scrape) — dedup por ISBN, slugs ISBN, sufijos de edición,
canonicals duplicados y saneo ASCII de las claves canónicas.

Cubre los 5 fixes del WO-H:

1. `merge_isbn_duplicates.apply_merges` — el ganador ya no puede ser una fila con
   `edition_key` vacío ni un `series_key` con pinta de junk; el contador converge
   (2ª corrida → 0 cambios).
2. `generate_slugs._derive_base_slug` — el slug ISBN se deriva SIEMPRE del ISBN-13
   normalizado (idempotente 10↔13), sin churn.
3. `series_aliases.canonical_series_key` — colapsa sufijos de edición de uno y de
   dos tokens contra una canónica EXACTA, sin colapsar spin-offs.
4. `unmapped_series.find_canonical_duplicates` — detecta canonicals que colapsan a
   la misma forma normalizada del resolver (comparación EXACTA), con un snapshot de
   regresión de los 30 pares conocidos (un duplicado NUEVO rompe el test).
5. `data/series_aliases.yml` — todas las canonical keys son ASCII kebab puro.

Los módulos de retrofit/audit no son paquetes (sin __init__.py) → se cargan por
ruta con importlib, mismo patrón que tests/test_audit_wo_e.py.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

import series_aliases

ROOT = Path(__file__).resolve().parent.parent


def _load(mod_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(mod_name, str(ROOT / rel_path))
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


merge_isbn = _load("wo_h_merge_isbn", "scripts/retrofit/merge_isbn_duplicates.py")
generate_slugs = _load("wo_h_generate_slugs", "scripts/retrofit/generate_slugs.py")
unmapped_series = _load("wo_h_unmapped_series", "scripts/audit/unmapped_series.py")

ALIASES_YML = ROOT / "data" / "series_aliases.yml"


# ===========================================================================
# 1. merge_isbn_duplicates — ganador correcto + convergencia
# ===========================================================================

def _watashi_trio() -> list[dict]:
    """El trío real del ISBN 9784799221334 (mismo libro físico, 3 filas):
    una std con edition_key real, una pending con series_key basura (`4-2-ss`)
    y una de referencia con ek/sk None (ISBN-10 del mismo libro)."""
    winner = {
        "title": "Watashi wo Sukisugiru Yuusha Vol.1 (Limited)",
        "url": "https://store-a.example/watashi-1",
        "isbn": "9784799221334",  # ISBN-13
        "edition_key": "watashi-wo-sukisugiru-yuusha-limited-jp",
        "series_key": "watashi-wo-sukisugiru-yuusha",
        "series_display": "Watashi wo Sukisugiru Yuusha",
        "volume": "1",
        "country": "JP",
        "standardized_at": "2026-07-01T00:00:00Z",
        "sources": [{"url": "https://store-a.example/watashi-1"}],
        "cluster_key": "edition:watashi-wo-sukisugiru-yuusha-limited-jp|1",
    }
    junk = {
        "title": "私を好きすぎる勇者",
        "url": "https://store-b.example/item-4-2-ss",
        "isbn": "978-4-7992-2133-4",  # mismo ISBN-13, con guiones
        "edition_key": "",
        "series_key": "4-2-ss",  # basura de extracción
        "series_display": "4-2-ss",
        "volume": "1",
        "country": "JP",
        "sources": [{"url": "https://store-b.example/item-4-2-ss"}],
        "cluster_key": "url:https://store-b.example/item-4-2-ss",
    }
    ref = {
        "title": "Watashi wo Sukisugiru Yuusha (reference)",
        "url": "https://ref.example/watashi",
        "isbn": "4799221337",  # ISBN-10 del mismo libro → normaliza al 13
        "edition_key": None,
        "series_key": None,
        "series_display": None,
        "volume": "",
        "country": "JP",
        "sources": [{"url": "https://ref.example/watashi"}],
        "cluster_key": "url:https://ref.example/watashi",
    }
    return [winner, junk, ref]


def test_merge_isbn_winner_is_the_watashi_row():
    result = merge_isbn.apply_merges(_watashi_trio())
    assert result["changed"] >= 1
    # El trío colapsa a una sola fila con las keys de la fila std (watashi…),
    # NUNCA con el series_key basura ni con ek vacío.
    assert len(result["items"]) == 1
    row = result["items"][0]
    assert row.get("edition_key") == "watashi-wo-sukisugiru-yuusha-limited-jp"
    assert row.get("series_key") == "watashi-wo-sukisugiru-yuusha"
    assert row.get("series_key") != "4-2-ss"
    assert (row.get("edition_key") or "") != ""


def test_merge_isbn_converges_on_second_run():
    run1 = merge_isbn.apply_merges(_watashi_trio())
    run2 = merge_isbn.apply_merges(run1["items"])
    assert run2["changed"] == 0, "el contador debe converger a 0 en la 2ª corrida"


def test_merge_isbn_empty_ek_never_beats_a_keyed_row():
    """El bug vacuo: `'unknown' not in ''.split('-')` == True → una fila sin
    edition_key ganaba a una con keys reales. Ahora la fila con ek gana."""
    keyed = {
        "title": "Keyed row", "url": "https://a.example/1", "isbn": "9784799221334",
        "edition_key": "some-series-limited-jp", "series_key": "some-series",
        "series_display": "Some Series", "volume": "3", "country": "JP",
        "sources": [{"url": "https://a.example/1"}],
        "cluster_key": "edition:some-series-limited-jp|3",
    }
    keyless = {
        "title": "Keyless row", "url": "https://b.example/2", "isbn": "4799221337",
        "edition_key": "", "series_key": "", "series_display": "", "volume": "3",
        "country": "JP", "sources": [{"url": "https://b.example/2"}],
        "cluster_key": "url:https://b.example/2",
    }
    result = merge_isbn.apply_merges([keyless, keyed])  # keyless primero a propósito
    assert len(result["items"]) == 1
    assert result["items"][0].get("edition_key") == "some-series-limited-jp"


def test_merge_isbn_junk_series_key_helper():
    assert merge_isbn._is_junk_series_key("4-2-ss") is True
    assert merge_isbn._is_junk_series_key("12-3") is True
    assert merge_isbn._is_junk_series_key("7") is True
    assert merge_isbn._is_junk_series_key("one-piece") is False
    assert merge_isbn._is_junk_series_key("07-ghost") is False  # sufijo largo
    assert merge_isbn._is_junk_series_key("") is False
    assert merge_isbn._is_junk_series_key(None) is False


# ===========================================================================
# 2. generate_slugs — slug ISBN estable (isbn13), sin churn 10↔13
# ===========================================================================

def test_slug_isbn_field_10_and_13_converge():
    """71 items reales oscilaban isbn-9784799777046 ↔ isbn-4799777041."""
    thirteen = {"isbn": "9784799777046", "url": "https://x/a"}
    ten = {"isbn": "4799777041", "url": "https://x/b"}
    s13 = generate_slugs._derive_base_slug(thirteen)
    s10 = generate_slugs._derive_base_slug(ten)
    assert s13 == "isbn-9784799777046"
    assert s10 == "isbn-9784799777046"
    assert s13 == s10


def test_slug_isbn_cluster_key_branch_is_dead_b2():
    """B2 (Fable 2026-07-08): la Regla vieja "cluster_key = isbn:{isbn13}" se
    quitó — el tier `isbn:` de derive_cluster_key fue eliminado 2026-07-07 (un
    ISBN pelado repite entre ediciones/series distintas en manga; ver
    CLAUDE.md decisión #4). La rama nunca ejecutaba en el corpus real (0
    items con ese prefijo), así que un `cluster_key` con ese prefijo YA NO
    produce un slug "isbn-…" — cae al fallback por URL, igual que cualquier
    item sin edition_key/isbn field."""
    c13 = {"cluster_key": "isbn:9784799777046", "url": "https://x/c"}
    c10 = {"cluster_key": "isbn:4799777041", "url": "https://x/d"}
    assert generate_slugs._derive_base_slug(c13) == generate_slugs._derive_base_slug({"url": "https://x/c"})
    assert generate_slugs._derive_base_slug(c10) == generate_slugs._derive_base_slug({"url": "https://x/d"})
    assert not generate_slugs._derive_base_slug(c13).startswith("isbn-")


def test_slug_isbn_is_idempotent():
    item = {"isbn": "4799777041", "url": "https://x/b"}
    assert generate_slugs._derive_base_slug(item) == generate_slugs._derive_base_slug(item)


def test_slug_partial_identifier_falls_back_to_cleaned():
    # No es un ISBN válido → limpiado crudo, comportamiento previo preservado.
    assert generate_slugs._derive_base_slug({"isbn": "ABC-123", "url": "u"}) == "isbn-123"


# ===========================================================================
# 3. series_aliases — sufijos de edición de uno y dos tokens
# ===========================================================================

@pytest.mark.parametrize("series_key,expected", [
    ("vagabond-definitive", "vagabond"),
    ("jujutsu-kaisen-complete", "jujutsu-kaisen"),
    ("dragon-ball-full-color", "dragon-ball"),      # dos tokens
    ("vagabond-edicao-definitiva", "vagabond"),      # dos tokens
])
def test_edition_suffix_collapses_to_canonical(series_key, expected):
    got, _ = series_aliases.canonical_series_key("", series_key, "")
    assert got == expected


def test_edition_suffix_does_not_collapse_spinoff():
    # broken-horizon NO es un sufijo de edición → spin-off, no debe colapsar.
    got, _ = series_aliases.canonical_series_key("", "dragon-ball-broken-horizon", "")
    assert got == "dragon-ball-broken-horizon"


# ===========================================================================
# 4. unmapped_series — canonical-vs-canonical duplicate detection
# ===========================================================================

def test_canonical_dups_synthetic_detects_pair_and_ignores_spinoff():
    db = {
        # par duplicado: comparten un alias que normaliza idéntico
        "blue-box": {"display": "Blue Box", "aliases": ["ao no hako"]},
        "ao-no-hako": {"display": "Ao no Hako", "aliases": ["blue box"]},
        # spin-off: substring pero NO igual bajo normalización → no debe flaguear
        "gto": {"display": "GTO", "aliases": []},
        "gto-paradise-lost": {"display": "GTO Paradise Lost", "aliases": []},
        # entrada sola, sin colisión
        "one-piece": {"display": "One Piece", "aliases": []},
    }
    pairs = {(d["a"], d["b"]) for d in unmapped_series.find_canonical_duplicates(db)}
    assert ("ao-no-hako", "blue-box") in pairs
    # ningún par debe involucrar el spin-off
    assert not any("gto-paradise-lost" in p for p in pairs)
    assert not any("one-piece" in p for p in pairs)


# Snapshot de regresión: pares de canonicals que COMPARTEN un alias normalizado pero
# NO son la misma obra (partes/gaiden/secuela/artbook/homónimos), verificados a mano.
# El test asegura que los detectados ⊆ este set: un duplicado NUEVO (p. ej. si el
# skill vuelve a acuñar uno) rompe el test; el estado conocido no.
#
# 2026-07-07 (Lote B post-scrape audit): se fusionaron 24 pares que SÍ eran la misma
# obra (merge gateado hacia el canonical más reconocible/comercial; backfill vía
# canonical_series_key). Quedan estos 6 pares que se MANTIENEN separados por evidencia:
#   - baki-dou-part-4 / bakidou-part-5  → partes distintas de Baki (secuela).
#   - fuse / fuse-kenichi-sonoda        → obras homónimas distintas (Sonoda vs.
#                                          adaptación de Nansō Satomi Hakkenden).
#   - hai-step-jun / hello-spank        → series distintas (WebSearch); hai-step-jun
#                                          arrastra aliases "Hello Spank" erróneos.
#   - kizumono-no-hanayome / …-gaiden   → el key -gaiden es un spin-off; se mantiene.
#   - twilight-out-of-focus / …-long-take → secuela ("Long Take").
#   - zelda-breath-of-the-wild / …-creating-a-champion → artbook específico distinto.
_KNOWN_CANONICAL_DUP_PAIRS = frozenset({
    ('baki-dou-part-4', 'bakidou-part-5'),
    ('fuse', 'fuse-kenichi-sonoda'),
    ('hai-step-jun', 'hello-spank'),
    ('kizumono-no-hanayome', 'koukoku-no-souheki-kizumono-no-hanayome-gaiden'),
    ('twilight-out-of-focus', 'twilight-outfocus-long-take'),
    ('zelda-breath-of-the-wild', 'zelda-breath-of-the-wild-creating-a-champion'),
})


def test_canonical_dups_real_yaml_subset_of_snapshot():
    db = series_aliases._load_aliases()
    detected = {(d["a"], d["b"]) for d in unmapped_series.find_canonical_duplicates(db)}
    new_dups = detected - _KNOWN_CANONICAL_DUP_PAIRS
    assert not new_dups, (
        "Se detectaron pares de canonicals DUPLICADOS nuevos (no en el snapshot). "
        "Fusionalos (merge gateado del Lote B) o actualizá el snapshot: "
        f"{sorted(new_dups)}"
    )


# ===========================================================================
# 5. series_aliases.yml — todas las canonical keys son ASCII kebab puro
# ===========================================================================

def test_all_canonical_keys_are_ascii_kebab():
    """Sin allowlist: tras el fix de las 3 keys no-ASCII (gotcha #81) TODAS las
    keys canónicas cumplen ^[a-z0-9][a-z0-9-]*[a-z0-9]$."""
    data = yaml.safe_load(ALIASES_YML.read_text(encoding="utf-8"))
    rx = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    bad = [k for k in data if not rx.match(k)]
    assert bad == [], f"canonical keys que no son ASCII kebab puro: {bad}"
