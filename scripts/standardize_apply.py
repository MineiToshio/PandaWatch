#!/usr/bin/env python3
"""standardize_apply.py — pasos de APPLY del skill /watch-standardize-catalog.

Fuente ÚNICA de la lógica de aplicación que antes vivía COPIADA (y
desincronizada) en SKILL.md y en el workflow. Dos subcomandos:

  tier1   Aplica determinísticamente las propuestas de `tier1.json`
          (0 tokens LLM) y marca `standardized_at`.

  merge   Lee los veredictos LLM por chunk (`result_*.jsonl` en el dir de
          trabajo), los aplica con estas garantías:
            - PRESERVA el edition_key/edition_display YA asignados (el LLM no
              re-agrupa — decisión owner 2026-06-07); solo asigna edición a
              items que NO tienen una.
            - Fallback a la propuesta heurística (tier{2,3}.json) si el LLM
              devolvió keys vacías; sin keys usables → el item queda PENDIENTE
              con `standardize_attempts` +1 (WO-C); a los MAX_STANDARDIZE_ATTEMPTS
              el audit lo saca de las proyecciones y lo manda a curación.
            - EL LLM NO EXPULSA (WO-C): is_manga=false NO borra la fila ni la
              manda a non_manga_blacklist.jsonl. El item queda PENDIENTE y se
              registra en data/unmapped_series.jsonl (reason "llm_non_manga");
              los gates deterministas del pipeline (filter_non_manga /
              filter_collectible) deciden la expulsión real en la próxima
              corrida. Excepción: un item con source Mangavariant NUNCA se
              expulsa — el veredicto se ignora (WARN) y sigue el flujo normal.
            - product_type SIEMPRE del enum (manga/artbook/…); un edition-kind
              del LLM (special/deluxe/…) se descarta y se re-deriva (WO-C).
            - Re-chequeo canónico de serie (canonical_series_key) + outliers
              de serie dentro de una misma /coleccion.
            - Recomputa cluster_key y consolida (merge_cluster, fuente única).
          Después de `merge` correr SIEMPRE el enforcer
          (scripts/retrofit/enforce_listadomanga_rules.py — Step 6b del skill).

Uso:
  .venv/bin/python scripts/standardize_apply.py tier1 [--force-all]
  .venv/bin/python scripts/standardize_apply.py merge [--force-all]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manga_watch import (  # noqa: E402
    PRODUCT_TYPE_ENUM,
    backup_and_rotate,
    consolidate_by_cluster,
    derive_cluster_key,
    derive_product_type,
    rebuild_edition_key_prefix,
    sanitize_key_ascii,
)
from series_aliases import (  # noqa: E402
    _build_aggressive_lookup,
    _build_lookup,
    canonical_series_key,
)

ITEMS = ROOT / "data" / "items.jsonl"
UNMAPPED = ROOT / "data" / "unmapped_series.jsonl"
_DEFAULT_UNMAPPED = UNMAPPED  # slot fijo capturado al import (ver _unmapped_path)
# Run dir del skill. Alineado con standardize_audit.DEFAULT_BASE
# (data/standardize-run): el workflow/SKILL.md pasan --base explícito a AMBOS
# scripts, pero los defaults no deben divergir (paquete I1, 2026-07-08).
DEFAULT_BASE = ROOT / "data" / "standardize-run"

# Tope de intentos de estandarización LLM antes de mandar el item a curación
# manual (unmapped_series.jsonl). Evita el retry infinito de títulos con keys
# irromanizables que gastarían Tier 3 para siempre (WO-C).
MAX_STANDARDIZE_ATTEMPTS = 3

# Enum válido de product_type — fuente ÚNICA: PRODUCT_TYPE_ENUM de manga_watch
# (antes se copiaba a mano acá y en validate_corpus.py; el doble enum era el
# hallazgo #9 de la auditoría 2026-07-08). El KIND de edición (special/deluxe/
# variant/limited/collector) NUNCA va acá — vive en edition_key; si el LLM
# devuelve un edition-kind en product_type, se descarta.
VALID_PRODUCT_TYPES = PRODUCT_TYPE_ENUM


def _unmapped_path() -> Path:
    """Path de escritura de unmapped_series.jsonl, honrando MANGA_WATCH_DATA_DIR.

    Misma clase de bug ya corregida en `series_aliases._unmapped_target()`
    (hallazgo #5, 2026-07-08): antes se usaba la constante de módulo y se
    ignoraba la env var → la suite ensuciaba el `data/unmapped_series.jsonl`
    REAL. Orden de resolución:
      1. Si un test monkeypatcheó `UNMAPPED` a un path ad-hoc (≠ el slot fijo del
         import) → se honra ese path (compat con tests que fijan UNMAPPED, ej.
         WO-C). Debe ir PRIMERO: esos tests no setean env var propia.
      2. Si `MANGA_WATCH_DATA_DIR` está seteada (fixture autouse de conftest,
         o serve.py en prod) → `<dir>/unmapped_series.jsonl`.
      3. Default: el slot fijo `data/unmapped_series.jsonl`.
    """
    if UNMAPPED != _DEFAULT_UNMAPPED:
        return UNMAPPED
    data_dir = os.environ.get("MANGA_WATCH_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "unmapped_series.jsonl"
    return UNMAPPED


def _load_items() -> list[dict]:
    return [json.loads(l) for l in ITEMS.open(encoding="utf-8") if l.strip()]


def _write_items(items: list[dict]) -> None:
    tmp = ITEMS.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(ITEMS)


def _item_has_mangavariant(it: dict) -> bool:
    """¿Alguna source del item es Mangavariant? Regla dura del repo:
    Mangavariant NUNCA se expulsa (ni a blacklist ni por veredicto LLM)."""
    if "mangavariant" in (it.get("source") or "").lower():
        return True
    for s in (it.get("sources") or []):
        if not isinstance(s, dict):
            continue
        blob = f"{s.get('name', '')} {s.get('source', '')} {s.get('url', '')}"
        if "mangavariant" in blob.lower():
            return True
    return False


def _existing_unmapped_keys() -> set[tuple[str, str]]:
    """Set de identidades `(series_key|sample_url, reason)` ya presentes en
    unmapped_series.jsonl, para dedup cross-run al appendear."""
    seen: set[tuple[str, str]] = set()
    target = _unmapped_path()
    if not target.exists():
        return seen
    for line in target.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        reason = rec.get("reason", "")
        sk = (rec.get("series_key") or "").strip()
        url = (rec.get("sample_url") or "").strip()
        if sk:
            seen.add((sk, reason))
        if url:
            seen.add((url, reason))
    return seen


def append_unmapped_from_item(it: dict, reason: str, *, note: str = "",
                              seen: set[tuple[str, str]] | None = None) -> bool:
    """Appendea una entrada a data/unmapped_series.jsonl para curación manual.

    Mismo shape que `series_aliases.log_unmapped_series`
    (series_key/series_display/sample_title/sample_url/source/detected_at) +
    `reason` + `note`. Es la ÚNICA cola de "registro incierto" del repo: NO se
    crean colas paralelas (regla del owner). Dedup cross-run por
    `(series_key, reason)` y `(sample_url, reason)`; devuelve True si escribió.

    `seen` (mutable) evita re-leer el archivo por item dentro de una corrida:
    se construye una vez con `_existing_unmapped_keys()` y se actualiza acá.
    """
    sk = (it.get("series_key") or "").strip()
    url = (it.get("url") or "").strip()
    if seen is None:
        seen = _existing_unmapped_keys()
    if (sk and (sk, reason) in seen) or (url and (url, reason) in seen):
        return False
    record = {
        "series_key": sk,
        "series_display": it.get("series_display", "") or "",
        "sample_title": it.get("title", "") or "",
        "sample_url": url,
        "source": it.get("source", "") or "",
        "detected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "reason": reason,
        "note": note or "",
    }
    target = _unmapped_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    if sk:
        seen.add((sk, reason))
    if url:
        seen.add((url, reason))
    return True


def _apply_clean_product_type(it: dict, r: dict) -> None:
    """Asegura que `product_type` sea SIEMPRE un valor del enum, nunca un
    edition-kind (special/deluxe/variant/limited/collector).

    Cascada: (1) si el LLM devolvió un product_type válido del enum → se aplica;
    (2) si no, se conserva el product_type existente del item si es válido;
    (3) si no hay uno válido → se re-deriva con `derive_product_type`
    (importada de manga_watch, no se copia la lógica). El kind de edición ya
    vive en edition_key.
    """
    llm_pt = (r.get("product_type") or "").strip().lower()
    if llm_pt in VALID_PRODUCT_TYPES:
        it["product_type"] = llm_pt
        return
    cur = (it.get("product_type") or "").strip().lower()
    if cur in VALID_PRODUCT_TYPES:
        it["product_type"] = cur
        return
    it["product_type"] = derive_product_type(
        it.get("title", "") or "",
        it.get("description", "") or "",
        it.get("signal_types", []) or [],
    )


def cmd_tier1(base: Path, force_all: bool) -> int:
    tier1_file = base / "tier1.json"
    if not tier1_file.exists():
        print("tier1.json no existe — correr standardize_audit.py primero.")
        return 1
    tier1 = json.load(tier1_file.open(encoding="utf-8"))
    url_to_md = {p["url"]: p for p in tier1 if p.get("url")}

    # Backup ANTES de mutar (convención dura: todo script que modifica un archivo
    # de datos backupea una vez antes del loop — hallazgo #2).
    if ITEMS.exists():
        backup_and_rotate(ITEMS, "standardize-tier1")

    items = _load_items()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    applied = 0
    skipped_empty = 0
    for it in items:
        if it.get("approved_at"):
            continue
        if it.get("standardized_at") and not force_all:
            continue
        md = url_to_md.get(it.get("url", ""))
        if not md:
            continue
        # Sanitizar ANTES de marcar (gotcha #81): claves LLM/heurísticas pueden
        # traer no-ASCII. Si series o edición se vacían al sanitizar, NO marcar
        # standardized_at y NO pisar las keys existentes con "" — el item queda
        # pendiente (invariante STDKEYS: estandarizado ⇒ keys no vacías). #3.
        sk = sanitize_key_ascii(md.get("proposed_series_key", ""))
        ek = sanitize_key_ascii(md.get("proposed_edition_key", ""))
        if not sk or not ek:
            skipped_empty += 1
            continue
        if not it.get("title_original"):
            it["title_original"] = it.get("title", "")
        it["series_key"] = sk
        it["series_display"] = md.get("proposed_series_display", "")
        it["edition_key"] = ek
        it["edition_display"] = md.get("proposed_edition_display", "")
        it["volume"] = md.get("proposed_volume", "")
        # title intacto: es el nombre OFICIAL scrapeado, nunca se renombra
        # ni traduce (política de títulos 2026-06-12).
        it["standardized_at"] = now_iso
        applied += 1

    # Recomputar cluster_key + consolidar (mismo paso 4 del merge). tier1
    # reescribe edition_key/volume (insumos de derive_cluster_key); sin esto
    # una corrida 100% Tier 1 dejaría cluster_key STALE → validate_corpus exit 2
    # (invariante DURA CLKEY) → gate pre-build bloqueado. Fuente única:
    # derive_cluster_key + consolidate_by_cluster de manga_watch. #4.
    for it in items:
        it["cluster_key"] = derive_cluster_key(it)
    deduped = consolidate_by_cluster(items)

    _write_items(deduped)
    print(f"Tier 1 auto-standardized: {applied} items (0 tokens LLM)")
    if skipped_empty:
        print(f"Tier 1 sin marcar (keys vacías al sanitizar, siguen pending): "
              f"{skipped_empty}")
    print(f"Items: {len(items)} -> {len(deduped)} (deduped {len(items) - len(deduped)})")
    return 0


def cmd_merge(base: Path, force_all: bool) -> int:
    # Backup ANTES de mutar (convención dura; el merge es de los pasos más
    # mutantes del pipeline — hallazgo #2).
    if ITEMS.exists():
        backup_and_rotate(ITEMS, "standardize-merge")

    # Caches de aliases pueden estar stale si el YAML cambió en esta sesión.
    _build_lookup.cache_clear()
    _build_aggressive_lookup.cache_clear()

    # 1) Veredictos LLM por chunk (cubre result_NN.jsonl y result_t{2,3}_NN.jsonl).
    results: dict[str, dict] = {}
    malformed_lines = 0
    for f in sorted(base.glob("result_*.jsonl")):
        for line in f.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                # Antes se descartaba EN SILENCIO: una línea de veredicto
                # corrupta (chunk truncado, JSON mal cerrado por el subagente)
                # desaparecía sin traza. Ahora se cuenta y se reporta. #14.
                malformed_lines += 1
                continue
            if r.get("url"):
                results[r["url"]] = r
    print(f"Veredictos leídos de archivos de chunk: {len(results)}")
    if malformed_lines:
        print(f"WARN: {malformed_lines} líneas de veredicto LLM malformadas "
              f"(descartadas, no aplicadas).")

    # 2) Propuestas heurísticas (fallback para keys vacías del LLM).
    proposals: dict[str, dict] = {}
    for name in ("tier2.json", "tier3.json"):
        p = base / name
        if p.exists():
            try:
                for proj in json.load(p.open(encoding="utf-8")):
                    proposals[proj.get("url", "")] = proj
            except Exception as e:
                print(f"WARN: no se pudo parsear {name} (ignorado): {e}")

    items = _load_items()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    pending_before = sum(1 for it in items if not it.get("standardized_at"))
    left_pending = 0
    llm_non_manga = 0
    mangavariant_ignored = 0

    # Identidades ya registradas en unmapped_series.jsonl (dedup cross-run).
    unmapped_seen = _existing_unmapped_keys()

    final: list[dict] = []
    for it in items:
        if it.get("approved_at"):
            final.append(it)
            continue
        if it.get("standardized_at") and not force_all:
            final.append(it)
            continue
        r = results.get(it.get("url", ""))
        if not r:
            final.append(it)
            continue
        if not r.get("is_manga", True):
            # EL LLM NO EXPULSA (WO-C). El veredicto no borra la fila ni la
            # manda a non_manga_blacklist.jsonl: son los gates deterministas
            # del pipeline (filter_non_manga / filter_collectible, Fase 3 del
            # scrape) los que deciden en la próxima corrida. Acá el item queda
            # PENDIENTE (sin standardized_at) y se registra para curación.
            if _item_has_mangavariant(it):
                # Regla dura del repo: Mangavariant NUNCA se expulsa. Se ignora
                # el veredicto y se sigue el flujo normal de estandarización.
                print("WARN: LLM marcó no-manga un item Mangavariant "
                      f"(ignorado): {it.get('url', '')}")
                mangavariant_ignored += 1
            else:
                append_unmapped_from_item(
                    it, "llm_non_manga",
                    note=(r.get("non_manga_reason", "") or "flagged_by_review"),
                    seen=unmapped_seen,
                )
                llm_non_manga += 1
                final.append(it)
                continue
        prop = proposals.get(it.get("url", ""), {})
        sk = (r.get("series_key", "") or "").strip() or prop.get("proposed_series_key", "")
        # Claves acuñadas por el LLM: forzar ASCII kebab (gotcha #81). Si la
        # sanitización la vacía (clave íntegramente CJK), queda pending.
        sk = sanitize_key_ascii(sk)
        if not sk:
            # Keys inusables → el item queda pendiente. Contamos el intento
            # para escalar a curación tras MAX_STANDARDIZE_ATTEMPTS (WO-C).
            it["standardize_attempts"] = (it.get("standardize_attempts", 0) or 0) + 1
            left_pending += 1
            final.append(it)
            continue
        # Resolver la edición ANTES de mutar el item: si el LLM no dio edición
        # usable, el item queda PENDIENTE — y NO debe salir con series_key/
        # series_display ya pisados a medias (mutación parcial, hallazgo #8).
        # PRESERVAR la edición ya asignada determinísticamente (el parser aplicó
        # las reglas duras): el LLM solo asigna edición a items SIN edition_key.
        has_edition = bool((it.get("edition_key") or "").strip())
        new_ek = None
        if not has_edition:
            ek = (r.get("edition_key", "") or "").strip() or prop.get("proposed_edition_key", "")
            ek = sanitize_key_ascii(ek)
            if not ek:
                # Keys inusables → pendiente + intento contabilizado (WO-C).
                # Se contabiliza SIN haber mutado nada del item todavía.
                it["standardize_attempts"] = (it.get("standardize_attempts", 0) or 0) + 1
                left_pending += 1
                final.append(it)
                continue
            new_ek = ek

        # A partir de acá el item se estandariza sí o sí: seguro mutar.
        it["series_key"] = sk
        it["series_display"] = ((r.get("series_display", "") or "").strip()
                                or prop.get("proposed_series_display", ""))
        if has_edition:
            it["volume"] = it.get("volume", "") or (r.get("volume", "") or "").strip()
        else:
            it["edition_key"] = new_ek
            it["edition_display"] = ((r.get("edition_display", "") or "").strip()
                                     or prop.get("proposed_edition_display", ""))
            it["volume"] = ((r.get("volume", "") or "").strip()
                            or prop.get("proposed_volume", ""))
        # title intacto: es el nombre OFICIAL scrapeado, nunca se renombra ni
        # traduce (política de títulos 2026-06-12). Cualquier
        # `title_standardized` que devuelva el LLM se IGNORA.
        if not it.get("title_original"):
            it["title_original"] = it.get("title", "")
        new_sk, new_sd = canonical_series_key(it["title"], it["series_key"],
                                              it["series_display"])
        # La canónica del YAML también puede traer no-ASCII (gotcha #81). Se
        # sanitiza SIN fallback al valor crudo: antes `... or new_sk`
        # reintroducía la clave no-ASCII cuando la sanitización la vaciaba
        # (hallazgo #7). Si queda vacía, NO se aplica la reescritura canónica —
        # se conserva el series_key actual (ya sanitizado, nunca "" → no crea
        # huérfanos).
        new_sk = sanitize_key_ascii(new_sk)
        if new_sk and new_sk != it["series_key"]:
            old_sk = it["series_key"]
            it["series_key"] = new_sk
            it["series_display"] = new_sd
            if (it.get("edition_key") or "").startswith(old_sk + "-"):
                it["edition_key"] = new_sk + it["edition_key"][len(old_sk):]
        elif new_sd != it["series_display"]:
            it["series_display"] = new_sd
        # Si la key vino con la serie truncada/stale (no empieza con el
        # series_key actual), re-armar el prefijo parseando la cola
        # {pub}-{slug}-{pais} (invariante de formato; mismo helper que el
        # retrofit fix_edition_key_prefix.py).
        rebuilt = rebuild_edition_key_prefix(it.get("edition_key", ""),
                                             it["series_key"])
        if rebuilt:
            it["edition_key"] = rebuilt
        # product_type SIEMPRE del enum, nunca un edition-kind (WO-C).
        _apply_clean_product_type(it, r)
        it["standardized_at"] = now_iso
        final.append(it)

    # 3) Outliers de serie dentro de una misma /coleccion (consistencia).
    groups = defaultdict(list)
    for it in final:
        if not it.get("standardized_at"):
            continue
        m = re.search(r"listadomanga\.es/coleccion\.php\?id=(\d+)",
                      it.get("url", "") or "")
        if m:
            groups[m.group(1)].append(it)
    outliers = 0
    for grp in groups.values():
        if len(grp) < 4:
            continue
        dom_sk, dom_n = Counter(it.get("series_key", "") for it in grp).most_common(1)[0]
        if dom_n < 3:
            continue
        # La serie dominante NO puede ser vacía: reescribir items sanos a
        # series_key="" los convierte en huérfanos (hallazgo #1, agravante).
        if not dom_sk:
            continue
        dom_sd = next((x.get("series_display", "") for x in grp
                       if x.get("series_key") == dom_sk), "")
        for it in grp:
            # NUNCA reescribir un golden record por dominancia estadística de sus
            # hermanas no curadas (guard `approved_at` homogéneo, gotcha #121 —
            # hallazgo #1). Un item aprobado conserva la serie/edición que curó
            # el owner aunque difiera de la dominante de la /coleccion.
            if it.get("approved_at"):
                continue
            if it.get("series_key", "") and it["series_key"] != dom_sk:
                old_ek = it.get("edition_key", "")
                if old_ek.startswith(it["series_key"] + "-"):
                    it["edition_key"] = dom_sk + old_ek[len(it["series_key"]):]
                it["series_key"] = dom_sk
                if dom_sd:
                    it["series_display"] = dom_sd
                outliers += 1

    # 4) Recomputar cluster_key + consolidar (merge_cluster, fuente única).
    for it in final:
        it["cluster_key"] = derive_cluster_key(it)
    before = len(final)
    deduped = consolidate_by_cluster(final)

    _write_items(deduped)

    # NOTA: el LLM NO expulsa (WO-C). Los items marcados no-manga por el LLM
    # NO van a non_manga_blacklist.jsonl: quedan pendientes y registrados en
    # unmapped_series.jsonl. La expulsión real la hacen los gates deterministas
    # (filter_non_manga / filter_collectible) en la próxima corrida del scrape.

    still_pending = sum(1 for it in deduped if not it.get("standardized_at"))
    orphans = sum(1 for it in deduped
                  if it.get("standardized_at")
                  and not (it.get("series_key") and it.get("edition_key")))
    print(f"Items: {len(items)} -> {len(deduped)}")
    print(f"LLM non-manga (a unmapped, NO blacklist): {llm_non_manga}")
    print(f"Mangavariant no-manga ignorados: {mangavariant_ignored}")
    print(f"Deduped: {before - len(deduped)}")
    print(f"Outliers de serie corregidos: {outliers}")
    print(f"INTEGRITY: pending_before={pending_before} "
          f"left_pending(sin keys usables)={left_pending} "
          f"still_pending_after={still_pending}")
    if orphans:
        print(f"WARNING: {orphans} items estandarizados con keys VACÍAS (huérfanos).")
        return 1
    print("INTEGRITY OK: 0 items estandarizados con keys vacías.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["tier1", "merge"])
    ap.add_argument("--force-all", action="store_true")
    ap.add_argument("--base", type=Path, default=DEFAULT_BASE)
    args = ap.parse_args()
    if args.command == "tier1":
        return cmd_tier1(args.base, args.force_all)
    return cmd_merge(args.base, args.force_all)


if __name__ == "__main__":
    raise SystemExit(main())
