#!/usr/bin/env python3
"""Wrapper para ejecutar el tracker desde la raíz del proyecto.

Uso:
    python manga_watch.py

El código principal vive en scripts/manga_watch.py.
"""

from scripts.manga_watch import parse_args, run


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
