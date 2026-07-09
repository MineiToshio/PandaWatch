#!/usr/bin/env python3
"""normalize_languages.py — normaliza `language` al canon en español en items.jsonl.

La invariante WARN `LANG_ENUM` de `scripts/validate_corpus.py` detecta items
cuyo `language` no pertenece al set canónico `_LANG_CANON` (nombre completo en
ESPAÑOL — single-user app en español, ver CLAUDE.md "14 idiomas"). Hoy ~1206
filas: nombres en inglés ("English", "Japanese"), códigos ISO-639-1 sueltos
("ja", "en", "fr", "es", "de", "it") y la variante alemana "Deutsch" (802
filas — hardcodeada por `scripts/wikis/mangapassion.py::_virtual_source`,
fixeado en el mismo turn que este script; ver docs/scraper/sources/mangapassion.md).

El mapa de sinónimos ACÁ es explícito (no heurístico) — se construyó leyendo
los valores REALES no-canónicos del corpus. Un valor que no está en el mapa
queda intacto y se reporta agrupado (no inventamos idiomas).

Uso:
    python scripts/retrofit/normalize_languages.py --dry-run
    python scripts/retrofit/normalize_languages.py
    python scripts/retrofit/normalize_languages.py --include-approved
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import backup_and_rotate, is_approved, write_lines_atomic  # type: ignore

# Mismo set que `_LANG_CANON` en scripts/validate_corpus.py (14 idiomas del
# proyecto + el valor compuesto legítimo "Español / Catalán"). No se importa
# de ahí para no acoplar un retrofit a un script de validación (ambos apuntan
# al mismo canon documentado en CLAUDE.md "14 idiomas"); si el canon cambia,
# actualizar los dos.
_LANG_CANON = frozenset({
    "Español", "Inglés", "Francés", "Japonés", "Italiano", "Portugués",
    "Alemán", "Polaco", "Turco", "Coreano", "Chino", "Checo", "Vietnamita",
    "Tailandés", "Español / Catalán",
})

# Sinónimos → canon. Construido a partir de los valores REALES no-canónicos
# vistos en data/items.jsonl (2026-07-07): nombres en inglés, códigos
# ISO-639-1 sueltos, y "Deutsch" (nombre alemán, hardcodeado por el parser
# de mangapassion). Case-sensitive a propósito — normalizar casing es un
# problema aparte y agregaría falsos mapeos (evita adivinar variantes que
# no vimos en el corpus real).
_LANG_SYNONYMS: dict[str, str] = {
    # Alemán
    "Deutsch": "Alemán",
    "German": "Alemán",
    "de": "Alemán",
    # Inglés
    "English": "Inglés",
    "en": "Inglés",
    # Japonés
    "Japanese": "Japonés",
    "ja": "Japonés",
    # Francés
    "French": "Francés",
    "fr": "Francés",
    # Español
    "Spanish": "Español",
    "es": "Español",
    # Italiano
    "Italian": "Italiano",
    "it": "Italiano",
    # Portugués
    "Portuguese": "Portugués",
    "pt": "Portugués",
    # Polaco
    "Polish": "Polaco",
    "pl": "Polaco",
    # Turco
    "Turkish": "Turco",
    "tr": "Turco",
    # Coreano
    "Korean": "Coreano",
    "ko": "Coreano",
    # Chino
    "Chinese": "Chino",
    "zh": "Chino",
    # Checo
    "Czech": "Checo",
    "cs": "Checo",
    # Vietnamita
    "Vietnamese": "Vietnamita",
    "vi": "Vietnamita",
    # Tailandés
    "Thai": "Tailandés",
    "th": "Tailandés",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/items.jsonl")
    parser.add_argument("--output", default="data/items.jsonl")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe el archivo; solo cuenta qué cambiaría.")
    parser.add_argument("--include-approved", action="store_true",
                        help="Procesar también items aprobados (golden records). Por "
                             "defecto se saltean para no pisar metadata aprobada.")
    args = parser.parse_args()

    src = Path(args.input)
    dst = Path(args.output)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    lines = src.read_text(encoding="utf-8").splitlines()
    out_lines: list[str] = []
    changed = 0
    skipped_approved = 0
    unmapped: Counter[str] = Counter()
    changes_by_pair: Counter[tuple[str, str]] = Counter()

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            out_lines.append(line)
            continue

        lang = (item.get("language") or "").strip()
        needs_fix = bool(lang) and lang not in _LANG_CANON

        if needs_fix and is_approved(item) and not args.include_approved:
            skipped_approved += 1
            out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            continue

        if needs_fix:
            new = _LANG_SYNONYMS.get(lang)
            if new is None:
                unmapped[lang] += 1
            else:
                changed += 1
                changes_by_pair[(lang, new)] += 1
                item["language"] = new

        out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))

    print(f"[INFO] {len(lines)} líneas totales, {changed} language se normalizarían.")
    if skipped_approved:
        print(f"[INFO] {skipped_approved} aprobados saltados (usa --include-approved para incluirlos)")
    if changes_by_pair:
        print("\nCambios por valor:")
        for (old, new), cnt in changes_by_pair.most_common():
            print(f"  {cnt:5d}  {old!r} → {new!r}")
    if unmapped:
        print(f"\n[REPORT] {sum(unmapped.values())} valores no-canónicos SIN mapeo conocido — SIN tocar:")
        for val, cnt in unmapped.most_common():
            print(f"  {cnt:5d}  {val!r}")

    if args.dry_run:
        print("\n[DRY-RUN] No se escribió ningún archivo.")
        return 0

    if changed == 0:
        print("[OK] Nada que normalizar.")
        return 0

    if dst.exists():
        backup = backup_and_rotate(dst, "langnorm")
        print(f"[OK] Backup guardado en {backup}")

    write_lines_atomic(dst, out_lines)
    print(f"[OK] Escribí {dst} con {changed} language normalizados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
