#!/usr/bin/env python3
"""Read-only corpus/cache/provenance audit. Run after full and delta ingestion."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manga_watch import item_urls, read_jsonl_strict, normalize_url_for_dedup


def audit(data_dir: Path) -> dict:
    rows = read_jsonl_strict(data_dir / 'items.jsonl')
    state_file = data_dir / 'state.json'
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    rejected = {u for r in read_jsonl_strict(data_dir / 'non_manga_blacklist.jsonl') for u in item_urls(r)}
    owners = defaultdict(list)
    sources = Counter()
    for idx, row in enumerate(rows):
        for url in item_urls(row):
            owners[url].append(idx)
        names = {s.get('name', '') for s in row.get('sources', []) if isinstance(s, dict)}
        names.add(row.get('source', ''))
        sources.update(n for n in names if n)
    missing = []
    for key, value in state.items():
        if not key.startswith('url:'):
            continue
        url = normalize_url_for_dedup(value.get('url') or key[4:])
        if url not in owners and url not in rejected:
            missing.append({'url': url, 'score': value.get('score', 0), 'source': value.get('source', '')})
    ambiguous = {u: ids for u, ids in owners.items() if len(ids)>1}
    spool = read_jsonl_strict(data_dir / 'items.jsonl.spool')
    conflicts = read_jsonl_strict(data_dir / 'items.jsonl.conflicts')
    return {
        'items':len(rows), 'state_entries':len(state), 'spool_rows':len(spool), 'pending_identity_conflicts':len(conflicts),
        'missing_from_corpus':len(missing),
        'missing_score_ge_20':sum((r['score'] or 0)>=20 for r in missing),
        'missing_by_source':dict(Counter(r['source'] for r in missing)),
        'ambiguous_source_urls':len(ambiguous),
        'secondary_only_urls':len(set(owners)-{normalize_url_for_dedup(r['url']) for r in rows if r.get('url')}),
        'missing_fields':{field:sum(not r.get(field) for r in rows) for field in
                          ('title','sources','author','isbn','release_date','images','series_key','edition_key','slug')},
        'products_by_source':dict(sorted(sources.items())),
        'missing_urls':missing, 'ambiguous_urls':ambiguous,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir',default='data')
    p.add_argument('--output',default='')
    args=p.parse_args()
    result=audit(Path(args.data_dir))
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:
        Path(args.output).write_text(text)
        print(json.dumps({k:v for k,v in result.items() if k not in
                         ('missing_urls','ambiguous_urls','products_by_source','missing_by_source')},ensure_ascii=False))
    else:
        print(text,end='')
    # A missing state entry is a recovery candidate, not proof of a lost product:
    # historical filters may legitimately have rejected it. Never auto-import it.
    return 0

if __name__=='__main__':
    raise SystemExit(main())
