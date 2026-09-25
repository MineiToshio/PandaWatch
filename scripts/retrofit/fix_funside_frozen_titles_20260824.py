#!/usr/bin/env python3
"""fix_funside_frozen_titles_20260824.py — retrofit puntual de títulos
basura CONGELADOS de IT - Funside Variant.

Contexto (post-mortem delta 2026-08-24, gotcha #148 en docs/reference/gotchas.md):
el `title_selector` de "IT - Funside Variant" en sources.yml era
`a[href*='/products/']`, que capturaba el <a> del badge de preventa/
descuento del card en vez del título real. Resultado: ~50 items con
`title` == "USCITA: dd/mm/yy" o "Sconto". El fix de selector
(`.product-card__title a`, aplicado 2026-08-24) corrige el problema para
CUALQUIER item nuevo o re-scrapeado — EXCEPTO los que ya tienen
`standardized_at`: el upsert (`_append_jsonl_upsert` en manga_watch.py)
CONGELA `title` para items estandarizados vía `_CURATED_FIELDS` (lo mismo
aplica a items aprobados vía `approved_at`/`is_approved()`), así que el
re-scrape con el selector ya arreglado NUNCA los va a tocar. Este script
cierra ese remanente.

Scope (decidido verificando la regla de congelamiento, no por suposición):
  - url de funside.it (item o alguna entrada de sources[])
  - title == "Sconto" o matchea `^USCITA: \\d{2}/\\d{2}/\\d{2}$`
  - standardized_at truthy (o approved_at truthy — is_approved()): es la
    ÚNICA condición bajo la cual `_append_jsonl_upsert` preserva el title
    viejo en vez de reemplazarlo con el de un re-scrape. Los items SIN
    standardized_at (raw) NO se tocan acá: son reemplazados enteros en el
    próximo delta/full ahora que el selector está arreglado — retocarlos
    en este script sería trabajo redundante y un diff sin necesidad.

Fuente del título real: la `description` de Funside sigue siempre el
patrón "... Confrontare <TÍTULO EN MAYÚSCULAS> Prezzo normale ..."
(verificado 2026-08-24 contra los 19 items afectados — el título extraído
coincide en formato/mayúsculas con los títulos reales ya presentes en el
corpus para esta misma fuente, ej. "AI TEMPI DI BOCCHAN PERFECT EDITION
VOL.4 - VARIANT").

Uso:
    python scripts/retrofit/fix_funside_frozen_titles_20260824.py             # dry-run
    python scripts/retrofit/fix_funside_frozen_titles_20260824.py --apply     # aplica
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import (  # type: ignore
    backup_and_rotate, is_approved, write_lines_atomic,
)

JUNK_TITLE_RE = re.compile(r"^(?:USCITA:\s*\d{2}/\d{2}/\d{2}|Sconto)$")
DESC_TITLE_RE = re.compile(r"Confrontare\s+(.+?)\s+Prezzo normale", re.IGNORECASE)


def extract_real_title(description: str) -> str:
    """Extrae el título real de la description de Funside a partir del
    patrón "Confrontare <TÍTULO> Prezzo normale". Devuelve "" si no matchea
    o si el resultado es sospechoso (vacío / absurdamente largo)."""
    if not description:
        return ""
    match = DESC_TITLE_RE.search(description)
    if not match:
        return ""
    title = match.group(1).strip()
    if not title or len(title) > 150:
        return ""
    return title


def is_funside_item(item: dict) -> bool:
    if "funside.it" in (item.get("url") or "").lower():
        return True
    for source in item.get("sources") or []:
        if isinstance(source, dict) and "funside.it" in (source.get("url") or "").lower():
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", default="data/items.jsonl")
    parser.add_argument("--output", default="data/items.jsonl")
    parser.add_argument("--apply", action="store_true",
                         help="Escribe los cambios. Sin este flag: dry-run (sólo reporta).")
    parser.add_argument("--evidence", default="data/diagnostics/fix_funside_frozen_titles_20260824.jsonl",
                         help="Ruta del JSONL de evidencia (slug/url/old_title/new_title).")
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
    skipped_not_frozen = 0
    skipped_no_match = 0
    evidence: list[dict] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            item = json.loads(stripped)
        except json.JSONDecodeError:
            out_lines.append(line)
            continue

        title = item.get("title") or ""
        if not (is_funside_item(item) and JUNK_TITLE_RE.match(title)):
            out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            continue

        # Golden record: el owner aprobó esta card manualmente. Convención
        # estándar de los retrofits: nunca tocar (aunque, al momento de
        # escribir esto, ninguno de los 19 afectados está aprobado).
        if is_approved(item):
            skipped_approved += 1
            out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            continue

        # Sólo los items con standardized_at tienen el title CONGELADO por
        # el upsert (_CURATED_FIELDS). Los raw se autocorrigen solos en el
        # próximo scrape ahora que el title_selector está arreglado.
        if not item.get("standardized_at"):
            skipped_not_frozen += 1
            out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            continue

        real_title = extract_real_title(item.get("description") or "")
        if not real_title:
            skipped_no_match += 1
            out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            continue

        evidence.append({
            "slug": item.get("slug"),
            "url": item.get("url"),
            "old_title": title,
            "new_title": real_title,
        })
        item["title"] = real_title
        changed += 1
        out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))

    print(f"[INFO] {len(lines)} líneas totales.")
    print(f"[INFO] {changed} títulos corregidos.")
    if skipped_not_frozen:
        print(f"[INFO] {skipped_not_frozen} items con título basura pero SIN standardized_at "
              f"(raw) -- se auto-corrigen en el próximo scrape, no tocados acá.")
    if skipped_approved:
        print(f"[INFO] {skipped_approved} aprobados saltados (golden record, nunca se tocan).")
    if skipped_no_match:
        print(f"[WARN] {skipped_no_match} items con título basura y standardized_at pero SIN "
              f"patrón 'Confrontare ... Prezzo normale' en description -- revisar a mano.")

    if evidence:
        print("\nMuestra de cambios:")
        for entry in evidence[:10]:
            print(f"  {entry['slug']}: {entry['old_title']!r} -> {entry['new_title']!r}")

    if not args.apply:
        print("\n[DRY-RUN] No se escribió ningún archivo. Usa --apply para aplicar.")
        return 0

    if changed == 0:
        print("[OK] Nada que corregir.")
        return 0

    if dst.exists():
        backup = backup_and_rotate(dst, "funside-titles")
        print(f"[OK] Backup guardado en {backup}")

    write_lines_atomic(dst, out_lines)
    print(f"[OK] Escribí {dst} con {changed} títulos corregidos.")

    evidence_path = Path(args.evidence)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with evidence_path.open("w", encoding="utf-8") as f:
        for entry in evidence:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[OK] Evidencia escrita en {evidence_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
