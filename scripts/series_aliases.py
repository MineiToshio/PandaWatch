"""series_aliases.py — normaliza series_key a su forma canónica + logging
de series sin mapear (queue para curación periódica via skill).

Lee `data/series_aliases.yml` (mantenido a mano) con la forma:

```yaml
demon-slayer:
  display: Demon Slayer
  aliases:
    - kimetsu no yaiba
    - 鬼滅の刃
    - guardianes de la noche
```

Función pública `canonical_series_key(title, current_series_key, current_display)`
devuelve `(canonical_key, canonical_display)` aplicando estas reglas:

1. Si el `current_series_key` ya es una key canónica del YAML → devolver tal cual.
2. Si algún alias del YAML aparece (substring case-insensitive, sin diacríticos) en
   `title` o en `current_display` → devolver el canónico.
3. Si nada matchea → devolver `(current_series_key, current_display)` sin cambio.

Diseño:
- El matching es por SUBSTRING normalizado para tolerar prefijos/sufijos
  ("Demon Slayer Vol 5" matchea alias "demon slayer").
- Empate de aliases entre varias canónicas → ganar la canonical con alias
  MÁS LARGO (preferimos match más específico).
- El YAML se cachea al primer acceso.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import threading
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


_ALIASES_FILE = Path(__file__).resolve().parent.parent / "data" / "series_aliases.yml"
_UNMAPPED_FILE = Path(__file__).resolve().parent.parent / "data" / "unmapped_series.jsonl"
_UNMAPPED_LOCK = threading.Lock()
# Dentro de la misma corrida del scraper, no querés loguear 100 veces la misma
# series_key — el writer dedupea contra este set en memoria.
_UNMAPPED_LOGGED_THIS_RUN: set[str] = set()


def _normalize(s: str) -> str:
    """Lowercase, sin diacríticos, sin puntuación. Preserva CJK."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    # Reemplazar puntuación/espacio por un solo espacio
    s = re.sub(r"[^\w぀-ヿ一-鿿]+", " ", s)
    return s.strip()


@lru_cache(maxsize=1)
def _load_aliases() -> dict[str, dict[str, Any]]:
    """Carga el YAML una vez. Devuelve {canonical_key: {display, aliases}}."""
    if not _ALIASES_FILE.exists():
        return {}
    with _ALIASES_FILE.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data


@lru_cache(maxsize=1)
def _build_lookup() -> dict[str, tuple[str, str]]:
    """Pre-procesa los aliases en un dict {alias_normalized: (canonical_key, display)}.

    Cada entry del YAML aporta múltiples lookups:
    - El propio canonical_key normalizado (para items que ya están canónicos).
    - El display normalizado.
    - Cada alias normalizado.
    - Cada alias slugificado (para matching contra series_keys auto-generados).

    Si dos canonicals colisionan en el mismo alias, gana la que fue declarada
    primero en el YAML.
    """
    aliases_db = _load_aliases()
    lookup: dict[str, tuple[str, str]] = {}
    for canonical_key, info in aliases_db.items():
        display = (info or {}).get("display", "") or canonical_key
        variants = [display, canonical_key, *(info or {}).get("aliases", [])]
        for variant in variants:
            n = _normalize(variant)
            if n and n not in lookup:
                lookup[n] = (canonical_key, display)
            # También indexar la versión slugificada con guiones
            slug = re.sub(r"\s+", "-", n)
            if slug and slug != n and slug not in lookup:
                lookup[slug] = (canonical_key, display)
    return lookup


def canonical_series_key(
    title: str,
    current_series_key: str = "",
    current_display: str = "",
) -> tuple[str, str]:
    """Devuelve `(canonical_key, canonical_display)` consultando el aliases.yml.

    Matching estricto: solo hace lookup exacto sobre los campos `series_key` y
    `series_display` (normalizados). NO hace substring-match en `title` para
    evitar falsos positivos del tipo "Monster Musume → Monster".

    Args:
        title: título del producto (no usado para matching; reservado para
            extensiones futuras vía `--strict` toggle).
        current_series_key: series_key actual del item.
        current_display: series_display actual del item.

    Returns:
        Tupla `(series_key, series_display)`. Si ningún alias matchea, devuelve
        los valores actuales sin tocar.
    """
    aliases_db = _load_aliases()

    # 1) Si current_series_key ya es canónica del YAML → devolver con display canónico.
    if current_series_key and current_series_key in aliases_db:
        return current_series_key, aliases_db[current_series_key].get(
            "display", current_display or current_series_key
        )

    # 2) Buscar current_series_key / current_display normalizados en el lookup.
    lookup = _build_lookup()
    for candidate in (current_series_key, current_display):
        if not candidate:
            continue
        n = _normalize(candidate)
        if n in lookup:
            return lookup[n]
        # También probar slug form (guiones)
        slug = re.sub(r"\s+", "-", n)
        if slug in lookup:
            return lookup[slug]

    # 3) Sin match
    return current_series_key, current_display


def is_canonical_key(series_key: str) -> bool:
    """Devuelve True si `series_key` ya es una entry canónica del YAML.

    Útil para decidir si vale la pena loguear un item al unmapped queue.
    """
    if not series_key:
        return False
    return series_key in _load_aliases()


def log_unmapped_series(
    series_key: str,
    series_display: str,
    title: str,
    url: str,
    source: str = "",
) -> None:
    """Append una línea al unmapped_series.jsonl si la series no es canónica.

    Idempotente DENTRO de la misma corrida: el writer dedupea por series_key
    contra `_UNMAPPED_LOGGED_THIS_RUN`. Si llamás 50 veces con el mismo key,
    solo se escribe la PRIMERA muestra. Entre corridas hay duplicados — el
    skill de enrichment los agrupa al procesar.

    Thread-safe (escritura serializada vía `_UNMAPPED_LOCK`).

    NO loguea si:
    - `series_key` está vacío.
    - `series_key` es una canonical key conocida (ya está mapeada).
    """
    if not series_key:
        return
    if is_canonical_key(series_key):
        return

    with _UNMAPPED_LOCK:
        if series_key in _UNMAPPED_LOGGED_THIS_RUN:
            return
        _UNMAPPED_LOGGED_THIS_RUN.add(series_key)

        record = {
            "series_key": series_key,
            "series_display": series_display or "",
            "sample_title": title or "",
            "sample_url": url or "",
            "source": source or "",
            "detected_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        _UNMAPPED_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _UNMAPPED_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def reset_unmapped_run_state() -> None:
    """Limpia el set en memoria que evita logs duplicados dentro de la misma
    corrida. Usar al inicio de cada scrape (o test).
    """
    with _UNMAPPED_LOCK:
        _UNMAPPED_LOGGED_THIS_RUN.clear()
