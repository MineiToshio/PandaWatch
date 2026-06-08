#!/usr/bin/env python3
"""fix_edition_key_anomalies.py — normaliza dos anomalías del edition_key que
violan invariantes del corpus (validate_corpus: COLED / PAIS):

  (A) **publisher con país horneado** `panini-es` → `panini`. El país va SIEMPRE
      en el sufijo del edition_key (gotcha #46), nunca en el slug de la editorial.
      `berserk-panini-es-special-es` → `berserk-panini-special-es`. Panini codifica
      su mercado en el sufijo (-es/-it/-mx/-br), así que `panini-es` como editorial
      es siempre el bug (artefacto stale de un standardize viejo).

  (B) **país `xx` (desconocido) inferible** → país real, SÓLO cuando es seguro:
      1) algún source trae country explícito (`españa`→es, etc.), o
      2) la EDITORIAL del edition_key es de UN solo país (norma/planeta/milkyway→es,
         pika/kana/glenat→fr, star/jpop→it, viz/yenpress→us, …).
      Editoriales multi-país (panini, kodansha) o `unknown` se quedan en `xx`
      (honesto: no inventamos país, regla país=edición es dura).

Reescribe edition_key + re-deriva cluster_key y consolida (los que ahora matchean
una edición con país real se fusionan). Idempotente. Respeta `approved_at`.

Uso:
  .venv/bin/python scripts/retrofit/fix_edition_key_anomalies.py --dry-run
  .venv/bin/python scripts/retrofit/fix_edition_key_anomalies.py
"""
from __future__ import annotations
import json, sys, argparse, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import manga_watch as mw  # noqa: E402
    mw._COUNTRY_SLUG_MAP  # type: ignore  # el wrapper raíz no lo tiene (en pytest)
except (ImportError, AttributeError):
    import scripts.manga_watch as mw  # type: ignore  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"
_VALID = set(mw._COUNTRY_SLUG_MAP.values())

# Editoriales de UN solo país (slug en el edition_key → país). Conservador: sólo
# las inequívocamente mono-país. Ambiguas (panini ES/IT/MX/BR, kodansha JP/US) NO.
_PUB_COUNTRY = {
    "norma": "es", "planeta": "es", "milkyway": "es", "ecc": "es",
    "pika": "fr", "kana": "fr", "glenat": "fr", "kioon": "fr", "kurokawa": "fr",
    "star": "it", "jpop": "it",
    "viz": "us", "yenpress": "us", "darkhorse": "us", "sevenseas": "us",
}


def _publisher_slug(ek: str) -> str:
    """editorial del edition_key `{serie}-{pub}-{slug}-{pais}` → parts[-3]."""
    parts = ek.split("-")
    return parts[-3] if len(parts) >= 3 else ""


def _src_country(it: dict) -> str:
    for s in it.get("sources", []) or []:
        c = (s.get("country", "") or "").strip().lower()
        if c:
            cs = mw._country_slug(c)
            if cs in _VALID:
                return cs
    return ""


def _fix_ek(it: dict) -> str | None:
    ek = it.get("edition_key", "") or ""
    if not ek:
        return None
    new = ek
    # (A) panini-es → panini
    if "-panini-es-" in new:
        new = new.replace("-panini-es-", "-panini-")
    # (B) xx → país inferido
    if new.endswith("-xx"):
        country = _src_country(it) or _PUB_COUNTRY.get(_publisher_slug(new), "")
        if country:
            new = new[:-3] + f"-{country}"
    return new if new != ek else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]
    changed, ex = 0, []
    for it in items:
        if it.get("approved_at"):
            continue
        new = _fix_ek(it)
        if new:
            if len(ex) < 30:
                ex.append((it.get("edition_key"), new))
            it["edition_key"] = new
            it["cluster_key"] = mw.derive_cluster_key(it)
            changed += 1
    print(f"[ek-anomalies] edition_key normalizados: {changed}")
    for o, n in ex:
        print(f"    {o}  →  {n}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if changed:
        from manga_watch import consolidate_by_cluster
        before = len(items)
        items = consolidate_by_cluster(items)
        print(f"[ek-anomalies] consolidate: {before} → {len(items)}")
        shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-ekanom-bak"))
        tmp = ITEMS.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        tmp.replace(ITEMS)
        print(f"[ek-anomalies] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
