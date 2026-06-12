#!/usr/bin/env python3
"""export_series_aliases.py — exporta data/series_aliases.yml a
data/series_aliases.json para que las UIs busquen por alias.

Las UIs (dashboard Alpine.js y web-next) no parsean YAML; este JSON
`{series_key: [alias, …]}` es la vista de búsqueda de los aliases: permite
que "demon slayer", "kimetsu no yaiba" y "guardianes de la noche" encuentren
los mismos items aunque el `title` sea el nombre oficial de cada edición
(política de títulos 2026-06-12).

Se regenera en cada build de la web (scripts/build_web.py lo invoca) y puede
correrse suelto después de editar el YAML (ej. tras /watch-enrich-series-aliases).

Uso:
    .venv/bin/python scripts/export_series_aliases.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
YML = ROOT / "data" / "series_aliases.yml"
OUT = ROOT / "data" / "series_aliases.json"


def export(yml: Path = YML, out: Path = OUT) -> int:
    """Escribe el JSON y devuelve la cantidad de series exportadas."""
    if not yml.exists():
        print(f"[WARN] no existe {yml}; escribo {{}} en {out}", file=sys.stderr)
        out.write_text("{}", encoding="utf-8")
        return 0
    data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
    index: dict[str, list[str]] = {}
    for key, entry in data.items():
        if not isinstance(entry, dict):
            continue
        names: list[str] = []
        display = (entry.get("display") or "").strip()
        if display:
            names.append(display)
        for alias in entry.get("aliases") or []:
            alias = str(alias).strip()
            if alias and alias not in names:
                names.append(alias)
        if names:
            index[str(key)] = names
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    tmp.replace(out)
    return len(index)


def main() -> int:
    n = export()
    print(f"[OK] {n} series exportadas a {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
