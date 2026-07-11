"""Tests para scripts/audit/lint_series_aliases.py.

El lint es el gate del skill /watch-enrich-series-aliases (Lote B): se corre
después de CADA edición del YAML. Cubre dos clases de fallo silencioso:

  1. Claves DUPLICADAS (top-level y anidadas): `yaml.safe_load` se queda con la
     ÚLTIMA silenciosamente — si el LLM re-agrega una canónica ya existente, la
     entrada original + sus aliases se pierden sin señal. El Loader estricto
     ERROREA en vez de tragarse el duplicado.
  2. Colisiones de normalización entre canonicals DISTINTAS (gotcha #70): dos
     keys que normalizan idéntico bajo el resolver → una queda sombreada.
     Se reusa `find_canonical_duplicates` de unmapped_series.py (import, NO copia).

Semántica de exit codes (ajuste del orquestador — el YAML real tiene colisiones
HISTÓRICAS que el skill no introdujo; el gate no debe bloquearse por ellas):
  - dup key → SIEMPRE exit 1 (corrupción real), con o sin baseline.
  - colisiones sin --baseline → warning, exit 0.
  - --snapshot captura el set actual; --baseline → exit 1 SOLO ante colisiones
    NUEVAS respecto al snapshot (las pre-existentes → warning, exit 0).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "scripts", _ROOT / "scripts" / "audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import lint_series_aliases as lint  # type: ignore


# ── Fixtures de YAML ────────────────────────────────────────────────────────

_CLEAN = """\
apothecary-diaries:
  display: The Apothecary Diaries
  aliases:
    - apothicaire
witch-hat-atelier:
  display: Witch Hat Atelier
  aliases:
    - atelier-des-sorciers
"""

# Clave canónica top-level repetida: safe_load se quedaría con la última y
# perdería 'apothicaire' + display original en silencio.
_DUP_TOPLEVEL = """\
apothecary-diaries:
  display: The Apothecary Diaries
  aliases:
    - apothicaire
witch-hat-atelier:
  display: Witch Hat Atelier
apothecary-diaries:
  display: Apothecary
  aliases:
    - kusuriya
"""

# Clave anidada repetida dentro de una entrada.
_DUP_NESTED = """\
apothecary-diaries:
  display: The Apothecary Diaries
  display: Apothecary
  aliases:
    - apothicaire
"""

# Dos canonicals DISTINTAS cuyo display normaliza idéntico ("one piece") →
# el resolver sólo mapea a una, la otra queda sombreada. Colisión "histórica".
_COLLISION = """\
one-piece:
  display: One Piece
onepiece:
  display: One Piece
"""

# La colisión histórica de arriba + una NUEVA (berserk ⇄ berserk-guts vía
# display idéntico) introducida "después del snapshot".
_COLLISION_PLUS_NEW = """\
berserk:
  display: Berserk
berserk-guts:
  display: Berserk
one-piece:
  display: One Piece
onepiece:
  display: One Piece
"""


def _write(tmp_path, text, name="series_aliases.yml") -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# ── Clave duplicada (SIEMPRE fatal) ─────────────────────────────────────────

def test_duplicate_toplevel_key_detected(tmp_path):
    p = _write(tmp_path, _DUP_TOPLEVEL)
    rc = lint.main(["--input", str(p)])
    assert rc == 1


def test_duplicate_toplevel_key_raises_in_loader(tmp_path):
    p = _write(tmp_path, _DUP_TOPLEVEL)
    with pytest.raises(lint.DuplicateKeyError):
        lint.load_strict(p)


def test_duplicate_nested_key_detected(tmp_path):
    p = _write(tmp_path, _DUP_NESTED)
    rc = lint.main(["--input", str(p)])
    assert rc == 1
    with pytest.raises(lint.DuplicateKeyError):
        lint.load_strict(p)


# ── YAML limpio ─────────────────────────────────────────────────────────────

def test_clean_yaml_passes(tmp_path):
    p = _write(tmp_path, _CLEAN)
    rc = lint.main(["--input", str(p)])
    assert rc == 0
    # load_strict no debe levantar sobre un YAML sin duplicados.
    data = lint.load_strict(p)
    assert set(data.keys()) == {"apothecary-diaries", "witch-hat-atelier"}


# ── Colisión de normalización — default: warning, exit 0 ───────────────────

def test_normalization_collision_is_warning_by_default(tmp_path, capsys):
    """Sin --baseline las colisiones NO bloquean (deuda histórica del YAML
    real): se reportan como warning y el exit es 0."""
    p = _write(tmp_path, _COLLISION)
    rc = lint.main(["--input", str(p)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "one-piece" in err and "onepiece" in err  # reportada igual


def test_normalization_collision_reported_via_shared_fn(tmp_path):
    """El lint reusa find_canonical_duplicates de unmapped_series.py."""
    p = _write(tmp_path, _COLLISION)
    data = lint.load_strict(p)
    dups = lint.find_canonical_duplicates(data)
    pairs = {(d["a"], d["b"]) for d in dups}
    assert ("one-piece", "onepiece") in pairs


def test_clean_yaml_no_collisions(tmp_path):
    p = _write(tmp_path, _CLEAN)
    data = lint.load_strict(p)
    assert lint.find_canonical_duplicates(data) == []


# ── Snapshot / baseline ─────────────────────────────────────────────────────

def test_snapshot_writes_current_collisions(tmp_path):
    p = _write(tmp_path, _COLLISION)
    snap = tmp_path / "baseline.json"
    rc = lint.main(["--input", str(p), "--snapshot", str(snap)])
    assert rc == 0  # colisiones sin baseline → warning
    data = json.loads(snap.read_text(encoding="utf-8"))
    pairs = {(d["a"], d["b"]) for d in data["canonical_duplicates"]}
    assert ("one-piece", "onepiece") in pairs


def test_baseline_unchanged_collisions_pass(tmp_path):
    """Colisiones pre-existentes (presentes en el baseline) → exit 0."""
    p = _write(tmp_path, _COLLISION)
    snap = tmp_path / "baseline.json"
    assert lint.main(["--input", str(p), "--snapshot", str(snap)]) == 0

    rc = lint.main(["--input", str(p), "--baseline", str(snap)])
    assert rc == 0


def test_baseline_new_collision_fails(tmp_path, capsys):
    """Una colisión NUEVA respecto al baseline → exit 1; la pre-existente no
    aparece entre los errores fatales."""
    p = _write(tmp_path, _COLLISION)
    snap = tmp_path / "baseline.json"
    assert lint.main(["--input", str(p), "--snapshot", str(snap)]) == 0

    # "El LLM edita el YAML" e introduce una colisión nueva (berserk ⇄ berserk-guts).
    p.write_text(_COLLISION_PLUS_NEW, encoding="utf-8")
    rc = lint.main(["--input", str(p), "--baseline", str(snap)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "berserk" in err and "NUEVA" in err
    # La histórica queda como warning (⚠), no como problema fatal (- COLISIÓN NUEVA).
    assert "COLISIÓN NUEVA respecto al baseline: colisión de normalización: `one-piece`" not in err


def test_dup_key_fails_even_with_baseline(tmp_path):
    """La clave duplicada es corrupción real: exit 1 aunque haya baseline."""
    clean = _write(tmp_path, _CLEAN)
    snap = tmp_path / "baseline.json"
    assert lint.main(["--input", str(clean), "--snapshot", str(snap)]) == 0

    dup = _write(tmp_path, _DUP_TOPLEVEL, name="dup.yml")
    rc = lint.main(["--input", str(dup), "--baseline", str(snap)])
    assert rc == 1


def test_missing_baseline_file_fails(tmp_path):
    p = _write(tmp_path, _CLEAN)
    rc = lint.main(["--input", str(p), "--baseline", str(tmp_path / "nope.json")])
    assert rc == 1


def test_snapshot_not_written_on_dup_key(tmp_path):
    """No se congela el estado de un YAML corrupto como baseline."""
    p = _write(tmp_path, _DUP_TOPLEVEL)
    snap = tmp_path / "baseline.json"
    rc = lint.main(["--input", str(p), "--snapshot", str(snap)])
    assert rc == 1
    assert not snap.exists()
