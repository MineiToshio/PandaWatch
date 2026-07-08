"""Candado de regresión del harness de evaluación del gate de portadas.

Corre `scripts/eval/eval_cover_gate.py` SOLO sobre las trampas sintéticas
(deterministas, sin red, sin data/images/) y verifica que las métricas esperadas
se cumplan. Si alguien relaja el gate `_same_cover` / `_is_soft_image`, el eval lo
detecta acá antes de que llegue a la cola de portadas.

Contrato verificado (política NUEVA = _same_cover + _is_soft_image):
  - 0 falsos positivos en negativos sintéticos, EXCEPTO la limitación conocida
    (a) arte-sin-logo (cat 6), marcada expected_fail.
  - 0 falsos negativos en positivos sintéticos (LN fondo sólido dos-res, y
    recompresión JPEG fuerte DEBEN pasar).
  - la referencia diminuta (<10k px) se clasifica como 'no_reference'.
  - cada caso sintético produce el outcome ``expected`` declarado en el manifest
    (candado byte-a-byte del comportamiento del gate).

Y el contraste con la política VIEJA (aspect ±0.30), que prueba que el hardening
realmente cierra la fuga:
  - la vieja ACEPTA el negativo (b) otro-tomo-misma-plantilla (FP que la nueva
    corrige) → demuestra que aspect-only no discriminaba identidad.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "eval"))

import eval_cover_gate as ecg  # noqa: E402


def _synthetic_result():
    return ecg.run_eval(include_real=False, include_synthetic=True)


def test_new_policy_zero_real_false_positives_on_synthetics():
    """La nueva no acepta ningún negativo sintético salvo la limitación conocida."""
    res = _synthetic_result()
    assert res["new"]["false_positives"] == []  # excluye expected_fail


def test_new_policy_zero_false_negatives_on_synthetics():
    """Los positivos sintéticos (LN dos-res, recompresión JPEG) DEBEN pasar."""
    res = _synthetic_result()
    assert res["new"]["false_negatives"] == []  # excluye expected_fail


def test_arte_sin_logo_is_expected_fail_and_accepted():
    """(a) arte-sin-logo: limitación conocida — la nueva la ACEPTA (FP), pero
    está marcada expected_fail (no cuenta como falla del harness)."""
    res = _synthetic_result()
    assert "synthetic:a_arte_sin_logo" in res["new"]["expected_fail"]
    row = next(r for r in res["rows"] if r["slug"] == "synthetic:a_arte_sin_logo")
    assert row["new"] == "accept"
    assert row["new_result"] == "FP"


def test_crop_3pct_is_documented_false_negative():
    """(f) crop ±3%: el gate estricto la rechaza (NCC<0.90); FN documentado."""
    res = _synthetic_result()
    assert "synthetic:f_crop_3pct" in res["new"]["expected_fail"]
    row = next(r for r in res["rows"] if r["slug"] == "synthetic:f_crop_3pct")
    assert row["new"] == "reject"


def test_tiny_reference_is_no_reference():
    """(d) referencia <10k px → política 'sin referencia'."""
    res = _synthetic_result()
    row = next(r for r in res["rows"] if r["slug"] == "synthetic:d_tiny_ref")
    assert row["new"] == "no_reference"
    assert res["new"]["counts"]["NR"] == 1


def test_each_synthetic_matches_expected_outcome():
    """Candado byte-a-byte: cada sintético produce su outcome ``expected``."""
    res = _synthetic_result()
    for r in res["rows"]:
        if r.get("source") != "synthetic":
            continue
        case = next(c for c in ecg.synthetic_cases(Path(_tmp())) if c["slug"] == r["slug"])
        assert r["new"] == case["expected"], (r["slug"], r["new"], case["expected"])


def test_old_policy_accepts_other_tomo_template_new_rejects():
    """El hardening cierra la fuga: la vieja (aspect ±0.30) ACEPTA el negativo
    (b) otro-tomo-misma-plantilla; la nueva lo RECHAZA."""
    res = _synthetic_result()
    row = next(r for r in res["rows"] if r["slug"] == "synthetic:b_otro_tomo_plantilla")
    assert row["old"] == "accept"   # aspect-only no discrimina → FP
    assert row["new"] == "reject"   # _same_cover sí


def test_old_policy_has_more_false_positives_than_new():
    """La vieja acumula FP que la nueva no tiene (prueba de la mejora)."""
    res = _synthetic_result()
    old_fp = res["old"]["counts"]["FP"]
    new_fp_real = len(res["new"]["false_positives"])
    assert old_fp > new_fp_real
    assert new_fp_real == 0


def test_deterministic():
    """Dos corridas → resultado idéntico (sin red, sin fecha)."""
    a = _synthetic_result()
    b = _synthetic_result()
    assert a["new"]["counts"] == b["new"]["counts"]
    assert a["old"]["counts"] == b["old"]["counts"]


def _tmp():
    import tempfile
    return tempfile.mkdtemp(prefix="cover_gate_test_")
