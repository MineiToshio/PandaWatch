#!/usr/bin/env python3
"""Unattended same-asset cover upgrades. No search APIs and no approval queue.

Uncertain matches retain the current cover. Every change has durable provenance;
failed attempts cool down, and a changed reference automatically permits retry.
"""
from __future__ import annotations
import argparse
import fcntl
import concurrent.futures
import datetime as dt
import hashlib
import json
import io
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts/retrofit'))
from scripts import manga_watch as m
from scripts import image_store
from scripts.cover_identity import automatic_upgrade, POLICY_VERSION, same_asset_url
from scripts.retrofit.upgrade_image_resolution import derive_original_url
from PIL import Image


def sha(data):
    return hashlib.sha256(data).hexdigest()


def item_identity(item):
    return {k: item.get(k) for k in ('isbn', 'country', 'language', 'publisher',
                                    'edition_key', 'volume', 'identity_review_required')}


def attempt_key(item, cover, reference):
    return sha(json.dumps([POLICY_VERSION, item['url'], item_identity(item), cover['url'], sha(reference)]).encode())


def inspect_target(task, images):
    item, cover, reference, key, target = task
    result = {'key': key, 'item_url': item['url'], 'old_url': cover['url'],
              'old_local': cover['local'], 'old_sha256': sha(reference), 'item_identity': item_identity(item),
              'new_url': target, 'policy': POLICY_VERSION, 'attempted_at': time.time()}
    try:
        session = m.make_session('manga-watch-cover-maintenance/1.0')
        try:
            local = image_store.download_image(target, images, session=session,
                timeout=(8, 20), referer=item['url'])
        finally:
            session.close()
        if not local:
            return {**result, 'status': 'retained', 'reason': 'download_failed'}
        candidate = (images / local).read_bytes()
        with Image.open(images / cover['local']) as a, Image.open(images / local) as b:
            gain = (b.width * b.height) / (a.width * a.height)
        evidence = automatic_upgrade(cover['url'], target, reference, candidate)
        if gain < 1.2 or not evidence['ok']:
            return {**result, 'status': 'retained', 'reason': 'no_gain' if gain < 1.2 else evidence['reason'], 'evidence': evidence}
        return {**result, 'status': 'ready', 'new_local': local, 'new_sha256': sha(candidate),
                'pixel_gain': round(gain, 3), 'evidence': evidence}
    except (OSError, ValueError) as exc:
        return {**result, 'status': 'retained', 'reason': type(exc).__name__}


def apply_result(path, images, result):
    """Compare-and-swap inside the canonical lock; never overwrite a snapshot."""
    with m.items_write_lock(path):
        rows = m.read_jsonl_strict(path)
        owners = [r for r in rows if r.get('url') == result['item_url']]
        if len(owners) != 1:
            return 'identity_drift'
        row = owners[0]
        if m.is_approved(row):
            return 'approved'
        if result.get('item_identity') != item_identity(row):
            return 'metadata_drift'
        cover = (row.get('images') or [{}])[0]
        if cover.get('url') != result['old_url'] or cover.get('local') != result['old_local']:
            return 'reference_drift'
        ref_path, new_path = images / result['old_local'], images / result['new_local']
        if (not ref_path.is_file() or not new_path.is_file()
                or sha(ref_path.read_bytes()) != result['old_sha256']
                or sha(new_path.read_bytes()) != result['new_sha256']):
            return 'bytes_drift'
        # Record original mapping in the product itself, in the SAME atomic write.
        row.setdefault('cover_history', []).append({k: v for k, v in result.items() if k != 'key'})
        cover.update(url=result['new_url'], local=result['new_local'],
                     identity_method=POLICY_VERSION, source_sha256=result['new_sha256'])
        cover.pop('upscaled', None)
        m.write_items_atomic(path, rows)
    return 'applied'


def run(data_dir, *, limit=200, workers=4, apply=False, retry_days=7):
    path, images = data_dir / 'items.jsonl', data_dir / 'images'
    ledger = data_dir / 'cover_maintenance.jsonl'
    # Prevent overlapping maintenance jobs, independently of brief corpus locks.
    data_dir.mkdir(parents=True, exist_ok=True)
    with ledger.with_suffix(".run.lock").open("a") as run_lock:
        fcntl.flock(run_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous = {r['key']: r for r in m.read_jsonl_strict(ledger)}
        rows = m.read_jsonl_strict(path)
        tasks = []
        for item in rows:
            covers = item.get('images') or []
            if not covers or m.is_approved(item) or item.get('identity_review_required'):
                continue
            cover = covers[0]
            target = derive_original_url(cover.get('url', ''))
            if not target or not same_asset_url(cover['url'], target):
                continue
            local = images / cover.get('local', '')
            if not local.is_file():
                continue
            reference = local.read_bytes()
            key = attempt_key(item, cover, reference)
            if time.time() - previous.get(key, {}).get('attempted_at', 0) < retry_days * 86400:
                continue
            tasks.append((item, cover, reference, key, target))
        def priority(task):
            try:
                with Image.open(io.BytesIO(task[2])) as im:
                    return im.width * im.height
            except OSError:
                return float('inf')
        tasks.sort(key=priority)  # Small covers first; bounded daily work is useful.
        total = len(tasks)
        if limit > 0:
            tasks = tasks[:limit]
        print(json.dumps({'eligible': total, 'scheduled': len(tasks), 'apply': apply}), flush=True)
        if not apply:
            return {'eligible': total, 'scheduled': len(tasks), 'applied': 0}
        if tasks:
            with m.items_write_lock(path):
                m.backup_and_rotate(path, 'maintain-covers')
        results = []
        # Sequential per-host requests: partition by host, one worker per host.
        from urllib.parse import urlsplit
        groups = {}
        for task in tasks:
            groups.setdefault(urlsplit(task[-1]).hostname, []).append(task)
        def process_group(group):
            return [inspect_target(t, images) for t in group]
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for future in concurrent.futures.as_completed([pool.submit(process_group, g) for g in groups.values()]):
                for result in future.result():
                    if result['status'] == 'ready':
                        result['status'] = apply_result(path, images, result)
                    previous[result['key']] = result
                    results.append(result)
                    m.write_items_atomic(ledger, list(previous.values()))
                print(json.dumps({'processed': len(results), 'applied': sum(r['status']=='applied' for r in results)}), flush=True)
        from collections import Counter
        summary = {'eligible': total, 'scheduled': len(tasks), 'outcomes': dict(Counter(r['status'] for r in results)), 'policy': POLICY_VERSION}
        print(json.dumps(summary), flush=True)
        return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    p.add_argument('--limit', type=int, default=200)
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--retry-days', type=int, default=7)
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    run(args.data_dir, limit=args.limit, workers=args.workers, apply=args.apply, retry_days=args.retry_days)

if __name__ == '__main__':
    main()
