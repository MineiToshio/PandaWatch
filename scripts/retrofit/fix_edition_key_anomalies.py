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
      2) el GRUPO DE REGISTRO del ISBN identifica el país de publicación
         (978-84→es, 978-3→de, 978-612→pe, 607→mx, …) — es el país de la
         editorial que registró el libro, exactamente la semántica de la regla
         país=edición. Grupos anglófonos (0/1) NO se mapean (US/UK ambiguo).
      3) la EDITORIAL del edition_key es de UN solo país (norma/planeta/milkyway→es,
         pika/kana/glenat→fr, star/jpop→it, viz/yenpress→us, …).
      4) otro item de la MISMA edición (mismo edition_key) ya resolvió país —
         por la regla coleccion=edición, hermanos comparten país por definición.
      Editoriales multi-país (panini, kodansha) o `unknown` sin ISBN se quedan
      en `xx` (honesto: no inventamos país, regla país=edición es dura).
      Si el item tenía `country` top-level vacío, se rellena con el nombre
      display del país inferido (consistencia con el filtro de país de la UI).

Reescribe edition_key + re-deriva cluster_key y consolida (los que ahora matchean
una edición con país real se fusionan). Idempotente. Respeta `approved_at`.

Uso:
  .venv/bin/python scripts/retrofit/fix_edition_key_anomalies.py --dry-run
  .venv/bin/python scripts/retrofit/fix_edition_key_anomalies.py
"""
from __future__ import annotations
import json, re, sys, argparse
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


# Grupo de registro ISBN → país. Sólo grupos inequívocos de UN país; los
# anglófonos (0/1 y 979-8 cubre US pero editoriales UK usan 978-1 también…
# en realidad 979-8 es exclusivo US, se incluye). Longest-prefix match.
_ISBN_GROUP_COUNTRY = {
    "2": "fr", "3": "de", "4": "jp", "84": "es", "85": "br", "88": "it",
    "89": "kr", "956": "cl", "957": "tw", "968": "mx", "970": "mx",
    "972": "pt", "974": "th", "986": "tw", "989": "pt",
    "604": "vn", "607": "mx", "612": "pe", "616": "th", "950": "ar",
}
_ISBN979_GROUP_COUNTRY = {"10": "fr", "11": "kr", "12": "it", "8": "us"}

# slug → nombre display (como aparece en `country` top-level / filtro de la UI).
_SLUG_DISPLAY = {
    "jp": "Japón", "it": "Italia", "es": "España", "fr": "Francia",
    "de": "Alemania", "us": "Estados Unidos", "vn": "Vietnam", "mx": "México",
    "br": "Brasil", "th": "Tailandia", "ar": "Argentina", "tw": "Taiwán",
    "gb": "Reino Unido", "pt": "Portugal", "pe": "Perú", "cl": "Chile",
    "kr": "Corea",
}


def _isbn_country(isbn: str) -> str:
    """País del grupo de registro del ISBN ('' si no se puede inferir)."""
    digits = "".join(ch for ch in (isbn or "") if ch.isdigit() or ch in "Xx")
    if len(digits) == 13:
        if digits.startswith("978"):
            group = digits[3:]
        elif digits.startswith("979"):
            g = digits[3:]
            for ln in (2, 1):
                if g[:ln] in _ISBN979_GROUP_COUNTRY:
                    return _ISBN979_GROUP_COUNTRY[g[:ln]]
            return ""
        else:
            return ""
    elif len(digits) == 10:
        group = digits
    else:
        return ""
    for ln in (3, 2, 1):
        if group[:ln] in _ISBN_GROUP_COUNTRY:
            return _ISBN_GROUP_COUNTRY[group[:ln]]
    return ""


def _publisher_slug(ek: str) -> str:
    """editorial del edition_key `{serie}-{pub}-{slug}[-cNNNN]-{pais}` → el
    tercer segmento contando desde el final.

    B10 (Fable 2026-07-08): antes usaba `parts[-3]` a secas, que sólo es
    correcto SIN el desambiguador `-cNNNN`. Con él (`serie-pub-special-c1234-es`),
    `parts[-3]` apuntaba a `special` (el slug de edición) en vez de a `pub` —
    el lookup en `_PUB_COUNTRY` fallaba en silencio. Se saltea el token
    `cNNNN` (si el que precede al país lo es) antes de indexar.
    """
    parts = ek.split("-")
    if len(parts) >= 2 and re.fullmatch(r"c\d+", parts[-2]):
        parts = parts[:-2] + parts[-1:]  # drop sólo el token -cNNNN
    return parts[-3] if len(parts) >= 3 else ""


def _src_country(it: dict) -> str:
    for s in it.get("sources", []) or []:
        c = (s.get("country", "") or "").strip().lower()
        if c:
            cs = mw._country_slug(c)
            if cs in _VALID:
                return cs
    return ""


def _infer_country(it: dict, ek: str) -> str:
    """Tier de inferencia de país: source explícito → ISBN → editorial mono-país."""
    return (
        _src_country(it)
        or _isbn_country(it.get("isbn", "") or "")
        or _PUB_COUNTRY.get(_publisher_slug(ek), "")
    )


def _fix_ek(it: dict) -> tuple[str | None, str]:
    """→ (nuevo edition_key o None si no cambia, slug de país inferido o '')."""
    ek = it.get("edition_key", "") or ""
    if not ek:
        return None, ""
    new, country = ek, ""
    # (A) panini-es → panini
    if "-panini-es-" in new:
        new = new.replace("-panini-es-", "-panini-")
    # (B) xx → país inferido
    if new.endswith("-xx"):
        country = _infer_country(it, new)
        if country:
            new = new[:-3] + f"-{country}"
    return (new if new != ek else None), country


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    # B11 (Fable 2026-07-08): una línea corrupta se preserva tal cual en vez
    # de tumbar el script; se mantiene fuera de `items` y se reinyecta
    # verbatim al escribir.
    items: list[dict] = []
    raw_lines: list[str] = []
    with ITEMS.open(encoding="utf-8") as fh:
        for l in fh:
            if not l.strip():
                continue
            try:
                items.append(json.loads(l))
            except json.JSONDecodeError:
                raw_lines.append(l.rstrip("\n"))
    if raw_lines:
        print(f"[ek-anomalies][WARN] {len(raw_lines)} línea(s) corrupta(s) preservada(s) tal cual.")

    changed, ex = 0, []
    # ek original -xx → país resuelto (para propagar a hermanos sin evidencia
    # propia: misma edición ⇒ mismo país por definición).
    resolved_xx: dict[str, str] = {}
    # B10 (Fable 2026-07-08): sembrar resolved_xx con ediciones YA resueltas
    # en corridas ANTERIORES (persistidas en items.jsonl con país real) — antes
    # sólo se acumulaba en memoria durante ESTA corrida, así que un hermano
    # `-xx` llegado en un scrape posterior (después de que la edición ya se
    # resolvió) no heredaba el país: la evidencia vivía sólo en el proceso
    # viejo, no en el estado persistido.
    for it in items:
        ek = it.get("edition_key", "") or ""
        parts = ek.split("-")
        country = parts[-1] if parts else ""
        if country and country != "xx" and country in _VALID:
            resolved_xx.setdefault(ek[: -len(country)] + "xx", country)
    for it in items:
        if it.get("approved_at"):
            continue
        old_ek = it.get("edition_key", "") or ""
        new, country = _fix_ek(it)
        if new:
            if len(ex) < 30:
                ex.append((old_ek, new))
            it["edition_key"] = new
            it["cluster_key"] = mw.derive_cluster_key(it)
            if country:
                resolved_xx[old_ek] = country
                if not (it.get("country") or "").strip():
                    it["country"] = _SLUG_DISPLAY.get(country, "")
            changed += 1
    # Segunda pasada: hermanos de una edición resuelta heredan su país.
    for it in items:
        if it.get("approved_at"):
            continue
        ek = it.get("edition_key", "") or ""
        country = resolved_xx.get(ek, "")
        if ek.endswith("-xx") and country:
            new = ek[:-3] + f"-{country}"
            if len(ex) < 30:
                ex.append((ek + " (hermano)", new))
            it["edition_key"] = new
            it["cluster_key"] = mw.derive_cluster_key(it)
            if not (it.get("country") or "").strip():
                it["country"] = _SLUG_DISPLAY.get(country, "")
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
        # A13 (Fable 2026-07-08): backup_and_rotate en vez de shutil.copy a un
        # path propio sin rotar.
        mw.backup_and_rotate(ITEMS, "ek-anomalies")
        out_lines = [json.dumps(it, ensure_ascii=False, sort_keys=True) for it in items] + raw_lines
        mw.write_lines_atomic(ITEMS, out_lines)
        print(f"[ek-anomalies] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
