"""Tests para series_aliases.aggressive_series_norm (paquete E-standardize,
hallazgo #13, 2026-07-08).

Cubre:
  1. El colapso de vocales largas del romaji (ou/oo→o, uu→u) se aplica POR TOKEN,
     antes del join — nunca cruza el LÍMITE entre dos tokens (antes fundía series
     distintas cuando un token terminaba en 'o'/'u' y el siguiente empezaba en
     'u'/'o').
  2. El rango conservado incluye Hangul (가-힣): un título coreano no se descarta.
  3. Las transformaciones legítimas intra-token siguen funcionando (regresión).
"""

from __future__ import annotations

from series_aliases import aggressive_series_norm


# ── 1. El colapso ou/oo/uu NO cruza límites de token ────────────────────────

def test_vowel_collapse_is_per_token_not_cross_boundary():
    # "kato" + "umi" → tokens ['kato','umi']; join naïve daría "katoumi" y el
    # replace ou→o lo colapsaría a "katomi" (espurio). Per-token debe preservar
    # la 'u': "kato"+"umi" = "katoumi".
    assert aggressive_series_norm("kato-umi") == "katoumi"
    # "ao" + "uta" → "aouta" (naïve → "aota"). Per-token conserva: "aouta".
    assert aggressive_series_norm("ao-uta") == "aouta"


def test_two_distinct_series_do_not_collide_via_boundary():
    # Dos slugs distintos NO deben normalizar al mismo valor sólo porque el
    # límite entre tokens forma "ou".
    a = aggressive_series_norm("neko-udon")
    b = aggressive_series_norm("neko-don")
    assert a != b, f"colisión espuria: {a!r} == {b!r}"


# ── 2. Vocales largas intra-token SÍ colapsan (regresión de gotcha #70) ─────

def test_intra_token_long_vowels_still_collapse():
    # "kumichou" y "kumicho" son la misma obra (vocal larga del romaji).
    assert aggressive_series_norm("kumichou") == aggressive_series_norm("kumicho")
    # "shoujo" vs "shojo".
    assert aggressive_series_norm("shoujo") == aggressive_series_norm("shojo")
    # "juuni" vs "juni" (uu→u).
    assert aggressive_series_norm("juuni") == aggressive_series_norm("juni")


def test_the_article_and_apostrophe_still_normalize():
    assert (aggressive_series_norm("the-apothecary-diaries")
            == aggressive_series_norm("apothecary-diaries"))
    assert (aggressive_series_norm("hell-s-paradise")
            == aggressive_series_norm("hells-paradise"))


# ── 3. Hangul se conserva (no se descarta el título coreano) ────────────────

def test_hangul_is_preserved():
    out = aggressive_series_norm("나루토")
    assert out == "나루토", f"Hangul descartado: {out!r}"


def test_hangul_mixed_with_latin_preserved():
    # Mezcla latín + Hangul: ambos rangos se conservan y se concatenan.
    out = aggressive_series_norm("naruto-나루토")
    assert "나루토" in out
    assert "naruto" in out


def test_empty_and_none_safe():
    assert aggressive_series_norm("") == ""
    assert aggressive_series_norm(None) == ""  # str(None)→"none"? no: guard `if not key`
