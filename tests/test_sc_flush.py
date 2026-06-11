"""Tests del script permanente sc_flush.py (skill watch-search-covers).

Todos los tests usan tmp_path + parámetros --preview / --acc para no tocar
data/ real. Se invoca el script como subproceso, igual que lo haría el skill.

Cobertura:
  1. test_flush_valid_candidate      — candidata válida crea la entrada completa
  2. test_flush_missing_new_image    — candidata sin new_image → exit 1
  3. test_flush_merge_same_slug      — segundo flush del mismo slug hace merge sin duplicar
  4. test_flush_preserves_external   — entradas ajenas en preview se preservan
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_FLUSH = _ROOT / 'scripts' / 'retrofit' / 'sc_flush.py'
_PYTHON = _ROOT / '.venv' / 'bin' / 'python'

# ── Helpers ───────────────────────────────────────────────────────────────────

def _item(slug: str = 'test-series-es-1') -> dict:
    return {
        'slug': slug,
        'title': 'Test Series 1',
        'title_original': 'テスト',
        'series_display': 'Test Series',
        'publisher': 'Test Editorial',
        'country': 'ES',
        'language': 'Español',
        'images': [
            {'url': 'https://example.com/cover.jpg', 'local': 'abc123.jpg', 'kind': 'cover'},
        ],
    }


def _candidate(new_image: str = 'new_abc.jpg', new_url: str = 'https://cdn.example.com/big.jpg',
               new_pixels: int = 300_000, match_dist: int = 2) -> dict:
    return {
        'new_image'  : new_image,
        'new_url'    : new_url,
        'new_pixels' : new_pixels,
        'ref_pixels' : 14_700,
        'match_dist' : match_dist,
        'verified'   : True,
        'page_title' : '',
        'domain'     : 'cdn.example.com',
        'query'      : 'Test Series 1 cover',
        'confidence' : 'low',
        'action'     : 'replace_cover',
        'target'     : '',
        'kind'       : 'gallery',
        'status'     : 'pending',
    }


def _flush_input(slug: str = 'test-series-es-1', candidates: list | None = None) -> dict:
    return {
        'slug'             : slug,
        'item'             : _item(slug),
        'candidates'       : candidates if candidates is not None else [_candidate()],
        'candidate_action' : 'replace_cover',
        'candidate_target' : '',
        'old_local'        : 'abc123.jpg',
        'old_url'          : 'https://example.com/cover.jpg',
        'curr_px'          : 14_700,
    }


def _run(flush_input: dict, preview: Path, acc: Path) -> subprocess.CompletedProcess:
    inp = preview.parent / 'flush_input.json'
    inp.write_text(json.dumps(flush_input, ensure_ascii=False), encoding='utf-8')
    return subprocess.run(
        [str(_PYTHON), str(_FLUSH), str(inp),
         '--preview', str(preview), '--acc', str(acc)],
        capture_output=True, text=True,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_flush_valid_candidate(tmp_path):
    """Una candidata válida (con new_image y new_url) crea la entrada completa en preview."""
    preview = tmp_path / 'cover_preview.json'
    acc     = tmp_path / '.tmp_sc_acc.json'

    result = _run(_flush_input(), preview, acc)

    assert result.returncode == 0, f'stderr: {result.stderr}'
    out = json.loads(result.stdout)
    assert out['flushed'] is True
    assert out['products'] == 1
    assert out['total_candidates'] == 1

    data = json.loads(preview.read_text(encoding='utf-8'))
    assert len(data) == 1
    entry = data[0]
    assert entry['slug'] == 'test-series-es-1'
    assert entry['old_pixels'] == 14_700
    assert len(entry['candidates']) == 1
    c = entry['candidates'][0]
    assert c['new_image'] == 'new_abc.jpg'
    assert c['new_url'] == 'https://cdn.example.com/big.jpg'
    assert c['action'] == 'replace_cover'
    assert c['target'] == ''
    # El acumulador también debe haberse escrito
    acc_data = json.loads(acc.read_text(encoding='utf-8'))
    assert 'test-series-es-1' in acc_data


def test_flush_missing_new_image(tmp_path):
    """Candidata sin new_image → exit 1, no se escribe nada."""
    preview = tmp_path / 'cover_preview.json'
    acc     = tmp_path / '.tmp_sc_acc.json'

    broken_candidate = _candidate()
    del broken_candidate['new_image']   # simular dict reconstruido a mano

    result = _run(_flush_input(candidates=[broken_candidate]), preview, acc)

    assert result.returncode == 1
    assert 'new_image' in result.stderr
    # No se debe haber creado el preview
    assert not preview.exists()


def test_flush_merge_same_slug(tmp_path):
    """Segundo flush del mismo slug agrega candidata nueva sin duplicar por new_url."""
    preview = tmp_path / 'cover_preview.json'
    acc     = tmp_path / '.tmp_sc_acc.json'

    # Primer flush: candidata A
    cand_a = _candidate(new_image='img_a.jpg', new_url='https://cdn.example.com/a.jpg')
    _run(_flush_input(candidates=[cand_a]), preview, acc)

    # Segundo flush: candidata B (distinta URL) + candidata A de nuevo (duplicado, debe ignorarse)
    cand_b = _candidate(new_image='img_b.jpg', new_url='https://cdn.example.com/b.jpg',
                        new_pixels=400_000)
    cand_a2 = _candidate(new_image='img_a_dup.jpg', new_url='https://cdn.example.com/a.jpg')
    result = _run(_flush_input(candidates=[cand_b, cand_a2]), preview, acc)

    assert result.returncode == 0, f'stderr: {result.stderr}'

    data = json.loads(preview.read_text(encoding='utf-8'))
    assert len(data) == 1
    entry = data[0]
    # Solo deben existir 2 candidatas: A (del primer flush) + B (del segundo)
    # cand_a2 se descarta por tener la misma new_url que cand_a
    urls = {c['new_url'] for c in entry['candidates']}
    assert urls == {'https://cdn.example.com/a.jpg', 'https://cdn.example.com/b.jpg'}
    assert len(entry['candidates']) == 2


def test_flush_preserves_external(tmp_path):
    """Entradas de otros slugs en preview se preservan intactas."""
    preview = tmp_path / 'cover_preview.json'
    acc     = tmp_path / '.tmp_sc_acc.json'

    # Crear un preview con una entrada ajena (otro slug)
    external_entry = {
        'slug'       : 'otro-manga-es-1',
        'title'      : 'Otro Manga 1',
        'old_pixels' : 5_000,
        'candidates' : [
            {'new_image': 'ext.jpg', 'new_url': 'https://other.com/ext.jpg',
             'status': 'pending', 'action': 'replace_cover', 'target': ''}
        ],
    }
    preview.write_text(json.dumps([external_entry], ensure_ascii=False, indent=2),
                       encoding='utf-8')

    # Flush para un slug diferente
    result = _run(_flush_input(slug='test-series-es-1'), preview, acc)

    assert result.returncode == 0, f'stderr: {result.stderr}'
    out = json.loads(result.stdout)
    assert out['products'] == 2   # ajena + la nueva

    data = json.loads(preview.read_text(encoding='utf-8'))
    slugs = {e['slug'] for e in data}
    assert slugs == {'otro-manga-es-1', 'test-series-es-1'}

    # Verificar que la entrada ajena no fue modificada
    ajena = next(e for e in data if e['slug'] == 'otro-manga-es-1')
    assert ajena['candidates'][0]['new_image'] == 'ext.jpg'
