"""Successful discovery watermarks, committed only after corpus and state writes."""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path
import tempfile


def read_checkpoint(data_dir: Path, source: str) -> dt.datetime | None:
    path = data_dir / '.ingestion-checkpoints' / f'{source}.json'
    if not path.exists():
        return None
    value = dt.datetime.fromisoformat(json.loads(path.read_text())['started_at'])
    if value.tzinfo is None:
        raise ValueError(f'Checkpoint without timezone: {path}')
    return value


def resume_month(requested: tuple[int, int], checkpoint: dt.datetime | None) -> tuple[int, int]:
    """Retain the requested overlap, extending backwards after interrupted runs."""
    if checkpoint is None:
        return requested
    overlap = checkpoint - dt.timedelta(days=7)
    return min(requested, (overlap.year, overlap.month))


def write_checkpoint(data_dir: Path, source: str, started_at: dt.datetime) -> None:
    directory = data_dir / '.ingestion-checkpoints'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{source}.json'
    # Distinct temp names avoid cross-process clobbering. An older watermark
    # merely widens replay; it cannot cause a gap.
    fd, name = tempfile.mkstemp(prefix=source + '.', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump({'started_at': started_at.isoformat()}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
