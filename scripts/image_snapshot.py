"""Optimistic corpus writes for legacy image commands that operate on snapshots.

The canonical maintenance uses per-cover CAS. Older tools abort on concurrent
changes instead of restoring a stale full-corpus snapshot.
"""
from __future__ import annotations
import hashlib
import threading
from pathlib import Path
try:
    from scripts import manga_watch as m
except ImportError:
    import manga_watch as m

_state = threading.local()


def _versions():
    if not hasattr(_state, 'versions'):
        _state.versions = {}
    return _state.versions


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def read_snapshot(path: Path):
    with m.items_write_lock(path):
        rows = m.read_jsonl_strict(path)
        _versions()[str(path.resolve())] = _digest(path)
        return rows


def write_snapshot(path: Path, rows):
    with m.items_write_lock(path):
        versions = _versions()
        key = str(path.resolve())
        if key not in versions and path.exists():
            raise RuntimeError('Image write has no source snapshot; read the corpus first')
        if _digest(path) != versions.get(key):
            raise RuntimeError('Corpus changed during image processing; changes preserved, retry the command')
        m.write_items_atomic(path, rows)
        versions[key] = _digest(path)
