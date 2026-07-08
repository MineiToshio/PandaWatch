#!/usr/bin/env python3
"""op_series_guard.py — validación pura de "¿este título es realmente One Piece?"

Contexto (auditoría post-scrape WO-2, GRUPO 3, 2026-07-07): un import manual
one-shot ("Research import (One Piece special publications/volumes/Jump
Remix)", scripts `import_op_remix.py` / `fix_op_special_vols.py`) arrastró
~11 series ajenas — índices de antologías Jump Remix/GIGA con ISBN mal
resuelto listados como "volúmenes de One Piece" (ej. 地獄楽, 終末のハーレム,
RURIDRAGON, 青の祓魔師, 遊☆戯☆王, 逃げ上手の若君). El retrofit de limpieza es
`scripts/retrofit/purge_op_import_foreign.py`; ESTE módulo es la prevención
estructural — la MISMA función la usan los dos scripts de import (guard antes
de escribir) y el retrofit (detección de residuos), así la regla vive en un
solo lugar (fuente única, no reimplementar el matcher en cada script).

Regla: un título es "de One Piece" si el título (o `title_original`) contiene,
case-insensitive, alguna de las keywords ONE_PIECE_KEYWORDS. Deliberadamente
simple (substring match) — cualquier falso positivo/negativo se resuelve
ampliando esta lista, no la lógica.

Spin-offs oficiales conocidos (ONE_PIECE_SPINOFF_ALLOWLIST): "Shokugeki no
Sanji" es un spin-off oficial de One Piece (protagonista Sanji, editado por
Shueisha) pero su título no contiene ninguna keyword genérica — sin allowlist
el matcher lo clasificaría como foreign (false positive). Se whitelista por
título de spin-off, que es el fix correcto del mecanismo: acepta el spin-off
en el import guard Y evita que el retrofit de purga lo expulse a futuro. Si
aparece otro spin-off oficial, se agrega su título a esta lista (no se relaja
la regla genérica de keywords).
"""

from __future__ import annotations

# Case-insensitive; "one piece" cubre también "ONE PIECE"/"One Piece".
ONE_PIECE_KEYWORDS = ("one piece", "ワンピース", "尾田")

# Spin-offs oficiales de la familia One Piece cuyo título NO contiene ninguna
# keyword genérica. Substring match, case-insensitive (mismo criterio que arriba).
ONE_PIECE_SPINOFF_ALLOWLIST = ("shokugeki no sanji", "食戟のサンジ")


def is_one_piece_title(title: str, title_original: str = "") -> bool:
    """True si `title`/`title_original` referencian a la serie One Piece.

    Cubre la serie principal (ONE_PIECE_KEYWORDS) y los spin-offs oficiales
    conocidos (ONE_PIECE_SPINOFF_ALLOWLIST). Usada como guard ANTES de escribir
    un item nuevo (import_op_remix.py, fix_op_special_vols.py) y como detector
    de residuos ya escritos (purge_op_import_foreign.py) — misma función, dos
    momentos.
    """
    combined = f"{title or ''} {title_original or ''}".lower()
    return any(kw in combined for kw in ONE_PIECE_KEYWORDS) or any(
        kw in combined for kw in ONE_PIECE_SPINOFF_ALLOWLIST
    )
