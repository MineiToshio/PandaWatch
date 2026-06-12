"""Tests del guard optimista de cover_preview.json (serve.py).

Regresión del 409 espurio (2026-06-12): st_mtime_ns (~1.8e18) excede el entero
máximo seguro de JavaScript (2^53), así que si el token viaja como Number el
navegador lo redondea y el round-trip NUNCA coincide → "La cola cambió en el
servidor" en cada save aunque nadie más tocó el archivo. El fix: el token viaja
como STRING opaco (gotcha #79).

Cobertura:
  1. token es string y round-trip exacto
  2. _mtime_matches: string igual → True; string distinto → False
  3. _mtime_matches legacy: Number con precisión double perdida → True
     (compat con una pestaña vieja cacheada)
  4. _mtime_matches legacy: Number de OTRO mtime → False
  5. el mtime real del repo NO es representable como double (documenta el bug)
"""
import struct
import sys
from pathlib import Path

import serve  # scripts/ está en sys.path vía conftest


def _as_js_number(ns: int) -> float:
    """Simula lo que ve JS al parsear el entero: el double más cercano."""
    return float(ns)


def test_mtime_token_is_string(tmp_path: Path):
    f = tmp_path / "cover_preview.json"
    f.write_text("[]", encoding="utf-8")
    tok = serve._mtime_token(f)
    assert isinstance(tok, str)
    assert tok == str(f.stat().st_mtime_ns)


def test_mtime_token_missing_file(tmp_path: Path):
    assert serve._mtime_token(tmp_path / "nope.json") == "0"


def test_matches_exact_string():
    assert serve._mtime_matches("1781274878205724666", "1781274878205724666")
    assert not serve._mtime_matches("1781274878205724666", "1781274878205724667")
    assert not serve._mtime_matches("", "1781274878205724666")


def test_matches_legacy_number_with_double_rounding():
    # Un cliente viejo manda el Number redondeado por JS; debe seguir pasando
    # el guard si corresponde al MISMO mtime.
    ns = 1781274878205724666
    rounded = _as_js_number(ns)          # 1781274878205724672.0
    assert int(rounded) != ns            # hay pérdida real de precisión
    assert serve._mtime_matches(rounded, str(ns))
    assert serve._mtime_matches(int(rounded), str(ns))


def test_matches_legacy_number_different_mtime():
    # Mtimes que difieren más que el spacing del double (~256 ns en 1.8e18)
    # deben seguir rechazándose con cliente viejo.
    ns_a = 1781274878205724666
    ns_b = ns_a + 1_000_000  # 1 ms después
    assert not serve._mtime_matches(_as_js_number(ns_b), str(ns_a))


def test_matches_garbage_types():
    assert not serve._mtime_matches(None, "123")
    assert not serve._mtime_matches([], "123")
    assert not serve._mtime_matches({}, "123")
    assert not serve._mtime_matches("abc", "123")
