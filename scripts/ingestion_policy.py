"""Durable receipts for complete scans of configured source endpoints.

A receipt does not claim complete coverage of a publisher's historical universe.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile

import yaml

DEFAULT_POLICY = Path(__file__).resolve().parents[1] / 'ingestion_policy.yml'


def load_policy(path=DEFAULT_POLICY):
    value = yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}
    if not isinstance(value, dict) or not isinstance(value.get('wikis'), dict):
        raise ValueError('ingestion_policy.wikis must be a mapping')
    for name, spec in value['wikis'].items():
        if not isinstance(spec, dict) or not isinstance(spec.get('enabled'), bool):
            raise ValueError(f'{name}: enabled must be a boolean')
        if spec['enabled']:
            dt.datetime.strptime(spec['full_from'], '%Y-%m')
        elif not spec.get('reason'):
            raise ValueError(f'{name}: retirement requires a reason')
    return value


def fingerprint(config):
    if dataclasses.is_dataclass(config):
        config = dataclasses.asdict(config)
        # Administrative labels do not change discovery coverage.
        config = {k: v for k, v in config.items()
                  if k not in {'notes', 'enabled', 'user_agent', 'throttle_group'}}
    encoded = json.dumps(config, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def receipt_path(data_dir, source):
    name = hashlib.sha256(source.encode()).hexdigest() + '.json'
    return Path(data_dir) / '.source-baselines' / name


def has_baseline(data_dir, source, config, *, min_score=20):
    path = receipt_path(data_dir, source)
    if not path.exists():
        return False
    # Corrupt receipts must not silently enable delta.
    value = json.loads(path.read_text(encoding='utf-8'))
    return (value.get('fingerprint') == fingerprint(config)
            and value.get('complete') is True
            and value.get('source') == source
            and value.get('min_score') == min_score)


def commit_baseline(data_dir, source, config, *, evidence, min_score=20):
    path = receipt_path(data_dir, source)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.stem + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump({'source': source, 'fingerprint': fingerprint(config),
                       'complete': True, 'min_score': min_score, 'evidence': evidence},
                      handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def needs_full(mode, data_dir, source, config, *, min_score=20):
    return mode == 'full' or (mode == 'delta' and not has_baseline(
        data_dir, source, config, min_score=min_score))
