#!/usr/bin/env python3
"""lint_series_aliases.py — gate de integridad de data/series_aliases.yml.

Gate del skill `/watch-enrich-series-aliases`: se corre después de CADA edición
del YAML (y en la verificación final). Detecta dos fallos SILENCIOSOS que
`yaml.safe_load` no reporta, con semánticas DISTINTAS:

1. **Claves DUPLICADAS** (top-level y anidadas) — SIEMPRE fatal (exit 1).
   `yaml.safe_load` con claves repetidas se queda con la ÚLTIMA sin avisar
   (reproducido): si el LLM del skill re-agrega una canónica que ya existía en
   el YAML (344 KB, edición a ciegas), la entrada original y TODOS sus aliases
   se pierden sin señal. El Loader estricto de acá (`UniqueKeyLoader`) LEVANTA
   `DuplicateKeyError` en vez de tragarse el duplicado — la única defensa antes
   de que el backfill escriba `items.jsonl` con un mapeo mutilado.

2. **Colisiones de normalización entre canonicals DISTINTAS** (gotcha #70): dos
   keys cuyo display/key/alias normalizan idéntico bajo el resolver
   (`series_aliases._normalize`) → el resolver sólo puede mapear a UNA, la otra
   queda sombreada. Se reusa `find_canonical_duplicates` de
   `scripts/audit/unmapped_series.py` (import, NO copia — fuente única).

   El corpus REAL ya tiene colisiones históricas (deuda pre-existente que el
   skill NO introdujo; algunas quizá legítimas de revisar con calma) — por eso
   las colisiones por defecto se REPORTAN como warning con **exit 0**, y el
   gate duro del skill usa la mecánica snapshot/baseline:

     --snapshot out.json   captura el conjunto ACTUAL de colisiones a un JSON
                           (pre-edición; el skill lo hace al arrancar).
     --baseline out.json   compara contra ese snapshot: exit 1 SOLO si hay
                           colisiones NUEVAS (introducidas después del
                           snapshot); las pre-existentes quedan como warning.

100% INFORMATIVO sobre los datos: NO modifica el YAML ni items.jsonl. Sólo lee
(y escribe el snapshot JSON si se pide — típicamente en `data/diagnostics/`).

Exit codes:
    0 — sin claves duplicadas y sin colisiones NUEVAS (colisiones sin baseline,
        o pre-existentes en el baseline, se reportan como warning).
    1 — clave duplicada (siempre), colisión NUEVA respecto a --baseline, o
        error de I/O (YAML/baseline inexistente o inválido).

Uso:
    python scripts/audit/lint_series_aliases.py                       # warning-only
    python scripts/audit/lint_series_aliases.py --snapshot base.json  # captura
    python scripts/audit/lint_series_aliases.py --baseline base.json  # gate
    python scripts/audit/lint_series_aliases.py --input FILE --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (_REPO / "scripts", _REPO / "scripts" / "audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import yaml  # noqa: E402

# Fuente única de la detección de colisiones de normalización (NO se copia).
from unmapped_series import find_canonical_duplicates  # noqa: E402,F401


DEFAULT_YAML = _REPO / "data" / "series_aliases.yml"


class DuplicateKeyError(ValueError):
    """Se levantó una clave duplicada al parsear el YAML (top-level o anidada)."""


class UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader que ERROREA ante claves duplicadas en cualquier mapping.

    `construct_mapping` se invoca recursivamente por cada nodo mapping del
    documento, así que el chequeo cubre tanto las canónicas top-level como las
    claves anidadas (`display`, `aliases`, …) de cada entrada.
    """

    def construct_mapping(self, node, deep=False):  # type: ignore[override]
        seen: set = set()
        for key_node, _value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                mark = key_node.start_mark
                raise DuplicateKeyError(
                    f"clave duplicada {key!r} (línea {mark.line + 1}, "
                    f"columna {mark.column + 1})"
                )
            seen.add(key)
        return super().construct_mapping(node, deep)


def load_strict(path: Path) -> dict:
    """Carga el YAML con el Loader estricto. Levanta DuplicateKeyError si hay dups."""
    with Path(path).open("r", encoding="utf-8") as fh:
        return yaml.load(fh, Loader=UniqueKeyLoader) or {}


def _resolve_default() -> Path:
    data_dir = os.environ.get("MANGA_WATCH_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "series_aliases.yml"
    return DEFAULT_YAML


def _pair_id(d: dict) -> tuple[str, str]:
    """Identidad estable de un par de colisión (`a`/`b` ya vienen ordenados)."""
    return (d["a"], d["b"])


def _load_baseline(path: Path) -> set[tuple[str, str]]:
    """Lee un snapshot previo (--snapshot) y devuelve el set de pares baseline."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {_pair_id(d) for d in data.get("canonical_duplicates", [])}


def _write_snapshot(path: Path, dups: list[dict], source: Path) -> None:
    """Escribe el snapshot de colisiones actuales (insumo de --baseline)."""
    payload = {
        "yaml": str(source),
        "canonical_duplicates": dups,
        "total": len(dups),
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")


def lint(
    path: Path, baseline: set[tuple[str, str]] | None = None,
) -> tuple[bool, list[str], list[str], list[dict], bool]:
    """Devuelve `(ok, errors, warnings, canonical_duplicates, parseable)`.

    `errors` (→ exit 1): clave duplicada / YAML ilegible, o colisiones NUEVAS
    respecto a `baseline`. `warnings` (→ exit 0): colisiones sin baseline, o
    pre-existentes en él. `parseable` indica si el YAML se pudo cargar (gate
    para --snapshot: no congelar el estado de un archivo corrupto).
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not Path(path).exists():
        return False, [f"no existe {path}"], [], [], False

    try:
        data = load_strict(path)
    except DuplicateKeyError as exc:
        # Fallo estructural fatal: no se puede confiar en el resto del análisis.
        return False, [f"CLAVE DUPLICADA: {exc}"], [], [], False
    except yaml.YAMLError as exc:  # pragma: no cover - YAML malformado
        return False, [f"YAML inválido: {exc}"], [], [], False

    dups = find_canonical_duplicates(data)
    for d in dups:
        msg = f"colisión de normalización: `{d['a']}` ⇄ `{d['b']}` (via `{d['via']}`)"
        if baseline is None:
            warnings.append(msg)
        elif _pair_id(d) in baseline:
            warnings.append(f"{msg} — PRE-EXISTENTE (en baseline)")
        else:
            errors.append(f"COLISIÓN NUEVA respecto al baseline: {msg}")

    return (len(errors) == 0), errors, warnings, dups, True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--input", type=Path, default=None,
                    help="YAML a validar (default: data/series_aliases.yml / "
                         "MANGA_WATCH_DATA_DIR).")
    ap.add_argument("--snapshot", type=Path, default=None,
                    help="Escribe el conjunto ACTUAL de colisiones a este JSON "
                         "(insumo para --baseline en corridas posteriores).")
    ap.add_argument("--baseline", type=Path, default=None,
                    help="JSON de un --snapshot previo: exit 1 SOLO si hay "
                         "colisiones NUEVAS respecto a él (las pre-existentes "
                         "quedan como warning).")
    ap.add_argument("--json", action="store_true",
                    help="Salida JSON estructurada a stdout.")
    args = ap.parse_args(argv)

    path = args.input if args.input is not None else _resolve_default()

    baseline: set[tuple[str, str]] | None = None
    if args.baseline is not None:
        if not args.baseline.exists():
            print(f"[ERROR] baseline no existe: {args.baseline}", file=sys.stderr)
            return 1
        baseline = _load_baseline(args.baseline)

    ok, errors, warnings, dups, parseable = lint(path, baseline=baseline)

    # El snapshot sólo tiene sentido sobre un YAML parseable (sin dup keys):
    # congelar el estado de un archivo corrupto daría un baseline inservible.
    if args.snapshot is not None and parseable:
        _write_snapshot(args.snapshot, dups, path)
        print(f"[SNAPSHOT] {len(dups)} colisiones capturadas → {args.snapshot}",
              file=sys.stderr)

    if args.json:
        json.dump(
            {"ok": ok, "errors": errors, "warnings": warnings,
             "canonical_duplicates": dups, "path": str(path)},
            sys.stdout, ensure_ascii=False, indent=2,
        )
        print()
    else:
        for w in warnings:
            print(f"  ⚠ {w}", file=sys.stderr)
        if ok:
            extra = (f" ({len(warnings)} colisiones warning/pre-existentes)"
                     if warnings else "")
            print(f"✓ {path} — sin claves duplicadas ni colisiones nuevas{extra}.")
        else:
            print(f"✗ {path} — {len(errors)} problema(s) fatales:", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
