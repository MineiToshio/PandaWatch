"""Explicit pipeline outputs exist even when every input passes."""
import json
import sys
import pytest
from scripts.retrofit import filter_non_manga, filter_collectible


@pytest.mark.parametrize("module", [filter_non_manga, filter_collectible])
def test_all_kept_writes_requested_output(module, tmp_path, monkeypatch):
    src=tmp_path/'input.jsonl'; kept=tmp_path/'kept.jsonl'; rejected=tmp_path/'rejected.jsonl'
    row={'url':'https://test/item','title':'One Piece Artbook','approved_at':'2026-09-24'}
    src.write_text(json.dumps(row)+'\n')
    monkeypatch.setattr(sys,'argv',['filter','--input',str(src),'--kept-output',str(kept),'--rejected-output',str(rejected)])
    assert module.main()==0
    assert json.loads(kept.read_text())==row
    assert rejected.read_text()==''
    assert json.loads(src.read_text())==row
