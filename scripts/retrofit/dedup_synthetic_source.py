#!/usr/bin/env python3
"""dedup_synthetic_source.py — gotcha #54: una fuente sintética de listadomanga
(`coleccion.php?id=N&item=<kind>-<vol>-<hash>`) identifica UN producto físico
único (colección + kind + volumen). Si el MISMO `item=` aparece como source en
>1 fila de items.jsonl, esas filas son el MISMO producto y deben fusionarse.

Por qué pasa (raíz):
  - cross-source merge: un tomo de listadomanga (especial-41) se fusiona con su
    ficha de tienda (Panini) bajo `edition:`+volume, pero la fila lmc-only original
    queda viva → 2 filas comparten especial-41.
  - representante base-url: la fila con primaria `coleccion.php?id=N` (sin item=)
    arrastra una copia de un synthetic y duplica al tomo real (ej. AoT regular:34
    vs special:34, ambos con especial-34).
  El upsert keyea por `cluster_key`, que difiere entre las dos filas (`edition:` vs
  `lmc:`, o regular:N vs special:N), así que NO deduplica y el dup vuelve cada scrape.

Fix: agrupa filas por synthetic `item=` compartido (union-find), las fusiona con
`merge_cluster` y re-fija URL primaria + cluster_key del resultado:
  - si la fila fusionada tiene alguna fuente EXTERNA (no listadomanga: tienda/
    comunidad) → primaria = esa fuente, cluster `edition:` (producto cross-source);
  - si es sólo-listadomanga → primaria = la URL sintética `item=` (NO la base sin
    item=, que derivaría kind 'regular' por defecto), cluster `lmc:cole:kind:vol`.
Conservador: si una componente abarca >1 volumen (señal de data corrupta) la SALTA
y la loguea para revisión manual. Idempotente. Respeta `approved_at` (merge_cluster
elige la fila aprobada como canónica).

Uso:
  .venv/bin/python scripts/retrofit/dedup_synthetic_source.py --dry-run
  .venv/bin/python scripts/retrofit/dedup_synthetic_source.py
"""
from __future__ import annotations
import json, re, sys, argparse, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from manga_watch import merge_cluster, derive_cluster_key  # noqa: E402
except ImportError:  # raíz tiene un wrapper manga_watch.py que sombrea (en pytest)
    from scripts.manga_watch import merge_cluster, derive_cluster_key  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"
# synthetic con hash hex (>=8). Para detectar la identidad del item.
_SYN = re.compile(r"item=([a-z]+)-([^-&]+)-([0-9a-f]{8,})")
# cole id de la URL de listadomanga.
_COLE = re.compile(r"coleccion\.php\?id=(\d+)")
_CANON = {"especial": "special", "alternativa": "variant", "limitada": "limited"}


def _tok_kindvol(token: str):
    """(cole, canon_kind, vol) de un token `{cole}|{kind}-{vol}-{hash}`."""
    cole, rest = token.split("|", 1)
    parts = rest.split("-")
    return (cole, _CANON.get(parts[0], parts[0]), parts[1]) if len(parts) >= 3 else (cole, parts[0], "")


def _edition_slug(it: dict) -> str:
    """slug de edición del edition_key (`{serie}-{pub}-{slug}-{pais}`)."""
    parts = (it.get("edition_key", "") or "").split("-")
    return parts[-2] if len(parts) >= 2 else "regular"


def _debundle_store_rows(items: list[dict]) -> int:
    """De-bundle: una fila de TIENDA (primaria no-listadomanga) que agrupa
    sintéticos de listadomanga de KINDS distintos (ej. Berserk Pack = especial-41
    + alternativa-41) mezcla 2 productos. Conserva el sintético que matchea el kind
    de la fila (edition-slug, o 'special' si el slug es base), y quita los AJENOS
    SÓLO si otra fila ya los tiene (sin pérdida de dato). Gotcha #54."""
    held = {}  # token "cole|kind-vol-hash" -> nº de filas que lo tienen
    for it in items:
        for t in _syn_hashes(it):
            held[t] = held.get(t, 0) + 1
    n = 0
    for it in items:
        if _is_ldm(it.get("url", "") or ""):
            continue  # sólo filas de tienda (primaria externa)
        toks = _syn_hashes(it)
        if len(toks) < 2:
            continue
        kinds_by_cv = {}
        for t in toks:
            c, k, v = _tok_kindvol(t)
            kinds_by_cv.setdefault((c, v), {})[k] = t
        for (c, v), kt in kinds_by_cv.items():
            if len(kt) < 2:
                continue  # un solo kind para este (cole,vol) → merge legítimo
            slug = _edition_slug(it)
            target = slug if slug in kt else ("special" if "special" in kt else sorted(kt)[0])
            for k, t in kt.items():
                if k == target:
                    continue
                if held.get(t, 0) > 1:  # otra fila lo tiene → quitar sin perderlo
                    it["sources"] = [s for s in (it.get("sources") or [])
                                     if t not in _syn_hashes({"url": "", "sources": [s]})]
                    held[t] -= 1
                    n += 1
    return n


def _syn_hashes(it: dict) -> set[str]:
    """tokens de identidad sintética `{cole}|{kind}-{vol}-{hash}` que esta fila
    referencia (primaria + sources). CRÍTICO: el token incluye el `id` de
    colección — el hash del `item=` NO es único entre colecciones (ej.
    `regular-1-08a02c268a6d6b23` se repite idéntico en colecciones distintas), así
    que sin el cole id se fusionarían obras totalmente distintas (gotcha #54)."""
    out: set[str] = set()
    urls = [it.get("url", "") or ""]
    urls += [s.get("url", "") or "" for s in (it.get("sources") or [])]
    for u in urls:
        mc = _COLE.search(u)
        ms = _SYN.search(u)
        if mc and ms:
            out.add(f"{mc.group(1)}|{ms.group(0)[len('item='):]}")  # "cole|kind-vol-hash"
    return out


def _cole_of(token: str) -> str:
    return token.split("|", 1)[0]


def _is_ldm(url: str) -> bool:
    return "listadomanga.es" in (url or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    # Paso A: de-bundle de filas de tienda multi-kind (Berserk Pack/Metalizada).
    n_debundle = _debundle_store_rows(items)

    # union-find sobre índices de fila, uniendo por synthetic compartido.
    parent = list(range(len(items)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    owner: dict[str, list[int]] = {}
    for i, it in enumerate(items):
        for h in _syn_hashes(it):
            owner.setdefault(h, []).append(i)
    for h, idxs in owner.items():
        for j in idxs[1:]:
            union(idxs[0], j)

    comps: dict[int, list[int]] = {}
    for i in range(len(items)):
        comps.setdefault(find(i), []).append(i)

    merged_rows: list[dict] = []
    skipped: list[str] = []
    n_dups = 0
    kept_idx: set[int] = set()
    examples: list[str] = []

    for root, idxs in comps.items():
        if len(idxs) == 1:
            continue
        group = [items[i] for i in idxs]
        # GUARDA (bank-auditor): auto-fusionar SÓLO si toda la componente apunta a
        # UN único producto = un solo (cole, kind, vol). Distintos hashes del MISMO
        # (cole,kind,vol) son el mismo tomo con 2 imágenes (ej. cole 52 regular-1)
        # → fusionar. Distinto kind/vol/cole (packs especial+variant, sobre-merges)
        # → NO fusionar; loguear para revisión manual.
        hashes = {h for it in group for h in _syn_hashes(it)}
        ckv = {_tok_kindvol(h) for h in hashes}
        if len(ckv) != 1:
            skipped.append(f"{[items[i].get('cluster_key') for i in idxs]} "
                           f"tokens={sorted(hashes)[:4]}{'…' if len(hashes) > 4 else ''}")
            continue
        merged = merge_cluster(group)
        # re-fijar primaria + cluster_key del resultado.
        srcs = merged.get("sources") or []
        ext = next((s for s in srcs if not _is_ldm(s.get("url", ""))), None)
        if ext:
            merged["url"] = ext.get("url", merged.get("url", ""))
        else:
            syn = next((s for s in srcs if _SYN.search(s.get("url", "") or "")), None)
            if syn:
                merged["url"] = syn.get("url", merged.get("url", ""))
        merged["cluster_key"] = derive_cluster_key(merged)
        merged_rows.append(merged)
        n_dups += len(idxs) - 1
        if len(examples) < 25:
            examples.append(f"{[items[i].get('cluster_key') for i in idxs]} → "
                            f"{merged['cluster_key']} | {merged.get('title')!r}")
        for i in idxs:
            kept_idx.add(i)

    # reconstruir: filas no tocadas + filas fusionadas (1 por componente).
    out = [it for i, it in enumerate(items) if i not in kept_idx] + merged_rows

    print(f"[dedup-syn] de-bundle de filas de tienda multi-kind: {n_debundle} fuentes ajenas quitadas")
    print(f"[dedup-syn] filas: {len(items)} → {len(out)}  (dups colapsados: {n_dups})")
    for e in examples:
        print(f"    {e}")
    if skipped:
        print(f"[dedup-syn] SALTADAS (apuntan a >1 producto, revisar a mano): {len(skipped)}")
        for s in skipped[:20]:
            print(f"    {s}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if n_dups or n_debundle:
        shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-dedupsyn-bak"))
        tmp = ITEMS.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for it in out:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        tmp.replace(ITEMS)
        print(f"[dedup-syn] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
