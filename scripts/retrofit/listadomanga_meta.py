#!/usr/bin/env python3
"""listadomanga_meta.py — caché + fetch de metadata REMOTA de una colección de
listadomanga.es (`coleccion.php?id=N`), endurecimiento #1 de
`/watch-whakoom-covers` (owner, tanda 3, 2026-09-02).

Motivación: `we_plan.py` calculaba `listado.total_tomos` SOLO contando items
del corpus LOCAL que comparten `edition_key` — subestima series en curso con
tomos aún no ingestados, y ese heurístico es el criterio DURO de
`we_resolve.py` para desambiguar ediciones hermanas. En la tanda 2, 63/144
rechazos fueron `total_tomos_mismatch` (ver docs/reference/images.md §
"Whakoom tanda 2"), varios de ellos con el contador de Whakoom "adelantado"
respecto al heurístico local. Este módulo trae el número REAL desde
`listadomanga.es` (la fuente de la que salió el item en primer lugar) en vez
de inferirlo del corpus.

Reutiliza EXCLUSIVAMENTE el parser canónico
`scripts.wikis.listadomanga_collections` (`parse_collection_page` +
`_extract_formato` + `_extract_publisher_from_header`) — nunca reimplementa
el parsing de HTML acá (fuente única; los gotchas #73-#75 documentan el
costo de duplicar ese parser en otro lado).

`fetch_collection_meta(coleccion_id)` hace UN GET a
`listadomanga.es/coleccion.php?id=N` (mismo endpoint que
`listadomanga_collections.fetch_collection`) y devuelve:
  - total_tomos: int|None — tomos PUBLICADOS (no `status:upcoming`) que el
    parser canónico emite para esa colección (misma clasificación de
    secciones/premium-gate que usó la ingestión real; box-level cuenta 1).
  - ongoing: bool — True si la colección tiene una sección "Números en
    preparación" con tomos anunciados aún no editados (serie no cerrada).
    Whakoom también puede llevar su propio contador desactualizado en
    ediciones "Ongoing" (ver docs/scraper/sources/whakoom.md § 6) — por eso
    `we_resolve.py` acepta `>=` en vez de igualdad estricta cuando CUALQUIERA
    de los dos lados está en curso.
  - formato: str — `<b>Formato:</b> ...` del header.
  - paginas: str — línea de páginas del ÚNICO tomo si `total_tomos == 1`
    (oneshot); "" si hay más de un tomo (ambiguo por diseño, no se reporta).
  - editorial: str — `<b>Editorial española:</b> ...` del header.

Cachea en `data/listadomanga_collection_meta.jsonl` (append-only, misma
convención que `data/whakoom_edition_map.jsonl` — última fila por
`coleccion_id` gana). El FETCH sólo lo dispara este módulo cuando se invoca
explícitamente (CLI, o `ensure_meta_cached` desde el loop del skill) —
`we_plan.py` sigue sin red por diseño propio (ver su docstring), sólo LEE
este caché vía `load_meta_cache`; si no hay fila cacheada para un
`coleccion_id`, cae al heurístico local con `source: "local_count"` y menor
confianza (ver we_plan.py § listado).

Uso:
    listadomanga_meta.py --coleccion-id 1832
    listadomanga_meta.py --coleccion-ids 1832,4139,6242
    listadomanga_meta.py --from-plan .tmp_we_plan.json   # todos los coleccion_id del plan
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

_SCRIPTS_RETROFIT = Path(__file__).resolve().parent
_SCRIPTS_DIR = _SCRIPTS_RETROFIT.parent
for _p in (_SCRIPTS_DIR, _SCRIPTS_RETROFIT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from wikis import listadomanga_collections as lmc  # type: ignore

_PAGES_RE = re.compile(r"(\d+)\s*p[áa]ginas", re.IGNORECASE | re.UNICODE)


def _default_data_path(name: str) -> Path:
    data_dir = os.environ.get("MANGA_WATCH_DATA_DIR")
    base = Path(data_dir) if data_dir else _SCRIPTS_DIR.parent / "data"
    return base / name


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def parse_meta_from_html(html_text: str, coleccion_id: int) -> dict[str, Any] | None:
    """Deriva `{total_tomos, ongoing, formato, paginas, editorial}` de una
    página `coleccion.php?id=N` ya descargada.

    `total_tomos` = cantidad de volúmenes distintos (`c.volume`) entre los
    candidates PUBLICADOS (`"status:upcoming" not in c.tags`) que el parser
    canónico emite para esta colección. Si ningún candidate publicado trae
    volumen numerado (box-level único, o un oneshot sin nº), se usa la
    cantidad de candidates publicados como total (mínimo 1 producto = 1
    "tomo" a efectos de esta comparación). `None` si la colección no tiene
    NINGÚN candidate publicado (no se pudo determinar).

    NOTA: cuenta volúmenes DISTINTOS, no candidates — una misma sección
    especial/portada-alternativa del mismo volumen no duplica el conteo.
    Es un proxy razonable de "cuántos tomos tiene esta edición", no
    necesariamente idéntico al contador propio de Whakoom (que a veces va
    retrasado en ediciones "Ongoing", ver whakoom.md § 6)."""
    if not html_text or len(html_text) < 1000:
        return None
    candidates = lmc.parse_collection_page(html_text, coleccion_id)
    formato = lmc._extract_formato(html_text)
    editorial = lmc._extract_publisher_from_header(html_text)

    published = [c for c in candidates if "status:upcoming" not in (c.tags or [])]
    ongoing = any("status:upcoming" in (c.tags or []) for c in candidates)

    # `Candidate.volume` sólo se asigna dinámicamente cuando el parser
    # detectó un nº (ver listadomanga_collections.parse_collection_page) —
    # ausente (AttributeError) en oneshots/box-level sin volumen numerado,
    # de ahí el getattr con default.
    volumes = {getattr(c, "volume", "") for c in published if getattr(c, "volume", "")}
    if volumes:
        total_tomos: int | None = len(volumes)
    elif published:
        total_tomos = len(published)
    else:
        total_tomos = None

    paginas = ""
    if total_tomos == 1 and len(published) == 1:
        m = _PAGES_RE.search(published[0].description or "")
        if m:
            paginas = m.group(0)

    return {
        "coleccion_id": coleccion_id,
        "total_tomos": total_tomos,
        "ongoing": ongoing,
        "formato": formato,
        "paginas": paginas,
        "editorial": editorial,
    }


def fetch_collection_meta(
    coleccion_id: int, session: Any = None, timeout: tuple[int, int] = (10, 30)
) -> dict[str, Any] | None:
    """Descarga `coleccion.php?id=N` y devuelve la meta parseada, o `None`
    si hubo un error de red o la página no existe."""
    import requests

    sess = session or requests.Session()
    url = lmc.COLECCION_URL_TEMPLATE.format(cid=coleccion_id)
    try:
        response = sess.get(url, timeout=timeout)
        response.raise_for_status()
        if not response.encoding:
            response.encoding = response.apparent_encoding
        html_text = response.text
    except requests.RequestException as exc:
        print(f"[WARN] coleccion {coleccion_id}: error de red obteniendo meta "
              f"({exc.__class__.__name__}: {exc})", file=sys.stderr)
        return None
    return parse_meta_from_html(html_text, coleccion_id)


def load_meta_cache(cache_path: Path) -> dict[int, dict[str, Any]]:
    """Última fila por `coleccion_id` (append-only, última gana) —
    MISMA convención que `we_plan._load_cache` sobre `whakoom_edition_map.jsonl`."""
    cache: dict[int, dict[str, Any]] = {}
    if not cache_path.exists():
        return cache
    for line in cache_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        cid = row.get("coleccion_id")
        if isinstance(cid, int):
            cache[cid] = row
    return cache


def append_meta_cache_row(cache_path: Path, meta: dict[str, Any]) -> None:
    row = dict(meta)
    row["fetched_at"] = _now_iso()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def ensure_meta_cached(
    coleccion_id: int,
    cache: dict[int, dict[str, Any]],
    cache_path: Path,
    *,
    session: Any = None,
    sleep_seconds: float = 2.0,
) -> dict[str, Any] | None:
    """Devuelve la meta cacheada si ya existe (0 red); si no, la fetchea, la
    persiste en `cache`/`cache_path` y espera `sleep_seconds` (throttle
    conservador sobre listadomanga.es, mismo perfil que el resto del
    pipeline) antes de devolver."""
    if coleccion_id in cache:
        return cache[coleccion_id]
    meta = fetch_collection_meta(coleccion_id, session=session)
    if meta is None:
        return None
    append_meta_cache_row(cache_path, meta)
    cache[coleccion_id] = meta
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coleccion-id", type=int, default=None)
    ap.add_argument("--coleccion-ids", default="", help="CSV de ids.")
    ap.add_argument("--from-plan", type=Path, default=None,
                     help="Ruta a un .tmp_we_plan.json — fetchea todos los "
                          "coleccion_id distintos del plan que no estén ya en caché.")
    ap.add_argument("--cache", type=Path, default=None)
    ap.add_argument("--sleep-seconds", type=float, default=2.0)
    args = ap.parse_args(argv)

    cache_path = args.cache if args.cache is not None else _default_data_path("listadomanga_collection_meta.jsonl")
    cache = load_meta_cache(cache_path)

    ids: list[int] = []
    if args.coleccion_id is not None:
        ids.append(args.coleccion_id)
    if args.coleccion_ids:
        ids.extend(int(s.strip()) for s in args.coleccion_ids.split(",") if s.strip())
    if args.from_plan is not None:
        if not args.from_plan.exists():
            print(f"[ERROR] no existe {args.from_plan}", file=sys.stderr)
            return 1
        plan = json.loads(args.from_plan.read_text(encoding="utf-8"))
        for t in plan:
            cid = (t.get("listado") or {}).get("coleccion_id")
            if isinstance(cid, int):
                ids.append(cid)

    ids = sorted(set(ids))
    if not ids:
        print("Nada que fetchear (sin --coleccion-id/--coleccion-ids/--from-plan).")
        return 0

    pending = [i for i in ids if i not in cache]
    print(f"Colecciones pedidas: {len(ids)} — ya en caché: {len(ids) - len(pending)} — a fetchear: {len(pending)}")

    ok = 0
    err = 0
    for cid in pending:
        meta = ensure_meta_cached(cid, cache, cache_path, sleep_seconds=args.sleep_seconds)
        if meta is None:
            err += 1
            print(f"  [ERROR] coleccion {cid}: no se pudo obtener meta")
        else:
            ok += 1
            print(f"  [OK] coleccion {cid}: total_tomos={meta['total_tomos']} "
                  f"ongoing={meta['ongoing']} formato={meta['formato'][:40]!r}")

    print(f"Listo. {ok} fetcheadas, {err} con error. Caché: {cache_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
