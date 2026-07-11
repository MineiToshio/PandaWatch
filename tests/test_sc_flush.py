"""Tests del script permanente sc_flush.py (skill watch-search-covers).

Todos los tests usan tmp_path + parámetros --preview / --acc para no tocar
data/ real. Se invoca el script como subproceso, igual que lo haría el skill.

Cobertura:
  1. test_flush_valid_candidate         — candidata válida crea la entrada completa
  2. test_flush_missing_new_image       — candidata sin new_image → exit 1
  3. test_flush_merge_same_slug         — segundo flush del mismo slug hace merge sin duplicar
  4. test_flush_preserves_external      — entradas ajenas en preview se preservan
  5. test_flush_owner_approval_survives — SC-7: aprobación del owner tras el 1er flush
                                          de un slug sobrevive a flushes posteriores
  6. test_flush_rejects_fabricated      — SC-2: dict sin campos de proveniencia → exit 1
  7. test_flush_rejects_missing_file    — SC-2: new_image que no existe en disco → exit 1
  8. test_flush_accepts_sc_validate_out — SC-2: el output real de sc_validate pasa la guarda
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


def _run(flush_input: dict, preview: Path, acc: Path,
         images_dir: Path | None = None, make_files: bool = True) -> subprocess.CompletedProcess:
    """Corre sc_flush.py como subproceso (igual que el skill).

    Crea en el espejo local (images_dir) un archivo por cada new_image de las
    candidatas del input, para satisfacer la guarda de existencia (SC-2). Pasar
    make_files=False para probar el rechazo de new_image inexistente.
    """
    if images_dir is None:
        images_dir = preview.parent / 'images'
    images_dir.mkdir(parents=True, exist_ok=True)
    if make_files:
        for c in flush_input.get('candidates', []):
            ni = c.get('new_image')
            if ni:
                (images_dir / ni).write_bytes(b'\xff\xd8\xff\xe0\x00\x10JFIF-stub')
    inp = preview.parent / 'flush_input.json'
    inp.write_text(json.dumps(flush_input, ensure_ascii=False), encoding='utf-8')
    return subprocess.run(
        [str(_PYTHON), str(_FLUSH), str(inp),
         '--preview', str(preview), '--acc', str(acc),
         '--images-dir', str(images_dir)],
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


def test_flush_owner_approval_survives(tmp_path):
    """SC-7 (regresión del red team): una aprobación del owner hecha en la UI
    DESPUÉS del primer flush de un slug DEBE sobrevivir a los flushes posteriores
    de la misma corrida.

    Repro: flush slug A → el owner aprueba la candidata de A en el JSON (como haría
    el panel serve) → flush slug B (con A todavía en el acumulador de la corrida).
    Antes, el flush de B reconstruía A desde el acc y pisaba la aprobación
    (last-writer-wins). Ahora releé el disco bajo lock y la decisión de disco gana.
    """
    preview    = tmp_path / 'cover_preview.json'
    acc        = tmp_path / '.tmp_sc_acc.json'
    images_dir = tmp_path / 'images'

    # 1. Flush del slug A (candidata a, pending)
    cand_a = _candidate(new_image='a.jpg', new_url='https://cdn.example.com/a.jpg')
    r1 = _run(_flush_input(slug='series-a-es-1', candidates=[cand_a]),
              preview, acc, images_dir=images_dir)
    assert r1.returncode == 0, f'stderr: {r1.stderr}'

    # 2. El owner APRUEBA la candidata de A directamente en el JSON (como serve POST)
    data = json.loads(preview.read_text(encoding='utf-8'))
    entry_a = next(e for e in data if e['slug'] == 'series-a-es-1')
    entry_a['candidates'][0]['status'] = 'approved'
    entry_a['candidates'][0]['reviewed_at'] = '2026-07-11T12:00:00Z'
    preview.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    # 3. Flush del slug B (A sigue en el acumulador de la corrida — mismo --acc)
    cand_b = _candidate(new_image='b.jpg', new_url='https://cdn.example.com/b.jpg')
    r2 = _run(_flush_input(slug='series-b-es-1', candidates=[cand_b]),
              preview, acc, images_dir=images_dir)
    assert r2.returncode == 0, f'stderr: {r2.stderr}'

    # 4. La aprobación de A DEBE seguir viva (status + reviewed_at preservados)
    data = json.loads(preview.read_text(encoding='utf-8'))
    slugs = {e['slug'] for e in data}
    assert slugs == {'series-a-es-1', 'series-b-es-1'}
    a_cand = next(e for e in data if e['slug'] == 'series-a-es-1')['candidates'][0]
    assert a_cand['status'] == 'approved', 'la aprobación del owner se pisó (SC-7)'
    assert a_cand['reviewed_at'] == '2026-07-11T12:00:00Z'


def test_flush_rejects_fabricated(tmp_path):
    """SC-2: una candidata fabricada a mano (sin los campos de proveniencia que
    sc_validate emite SIEMPRE) se rechaza con exit 1 antes de escribir nada."""
    preview    = tmp_path / 'cover_preview.json'
    acc        = tmp_path / '.tmp_sc_acc.json'
    images_dir = tmp_path / 'images'

    # Dict mínimo reconstruido a mano: tiene new_image/new_url pero le faltan
    # new_pixels/verified/confidence/status/match_dist.
    fabricated = {
        'new_image': 'fab.jpg',
        'new_url'  : 'https://cdn.example.com/fab.jpg',
        'action'   : 'replace_cover',
        'target'   : '',
    }
    result = _run(_flush_input(candidates=[fabricated]), preview, acc, images_dir=images_dir)

    assert result.returncode == 1
    # El mensaje debe nombrar campos de proveniencia faltantes y sc_validate
    assert 'proveniencia' in result.stderr
    assert 'sc_validate' in result.stderr
    assert not preview.exists()


def test_flush_rejects_missing_file(tmp_path):
    """SC-2: una candidata cuyo new_image NO existe en el espejo local se rechaza."""
    preview    = tmp_path / 'cover_preview.json'
    acc        = tmp_path / '.tmp_sc_acc.json'
    images_dir = tmp_path / 'images'

    # make_files=False → NO se crea el archivo de la candidata en images_dir.
    result = _run(_flush_input(), preview, acc, images_dir=images_dir, make_files=False)

    assert result.returncode == 1
    assert 'no existe' in result.stderr
    assert not preview.exists()


def test_flush_accepts_sc_validate_out(tmp_path):
    """SC-2: el dict EXACTO que emite sc_validate.validate() pasa la guarda.

    Se construye con la misma forma que produce sc_validate (todos los campos de
    proveniencia presentes, match_dist int, verified bool) para verificar que la
    guarda no es demasiado estricta contra el output real."""
    preview    = tmp_path / 'cover_preview.json'
    acc        = tmp_path / '.tmp_sc_acc.json'
    images_dir = tmp_path / 'images'

    sc_validate_output = {
        'new_image' : 'validated.jpg',
        'new_url'   : 'https://cdn.example.com/validated.jpg',
        'new_pixels': 480_000,
        'ref_pixels': 14_700,
        'match_dist': 1,
        'verified'  : True,
        'page_title': 'Serie Vol 1',
        'domain'    : 'cdn.example.com',
        'query'     : 'Serie 1 cover',
        'confidence': 'low',
        'action'    : 'replace_cover',
        'target'    : '',
        'kind'      : 'gallery',
        'status'    : 'pending',
    }
    result = _run(_flush_input(candidates=[sc_validate_output]), preview, acc,
                  images_dir=images_dir)

    assert result.returncode == 0, f'stderr: {result.stderr}'
    data = json.loads(preview.read_text(encoding='utf-8'))
    assert data[0]['candidates'][0]['new_image'] == 'validated.jpg'


def test_flush_accepts_match_dist_none(tmp_path):
    """SC-2: match_dist=None (item --include-no-image, verified False) es válido —
    la CLAVE debe estar presente pero el valor None se acepta."""
    preview    = tmp_path / 'cover_preview.json'
    acc        = tmp_path / '.tmp_sc_acc.json'
    images_dir = tmp_path / 'images'

    cand = _candidate()
    cand['match_dist'] = None
    cand['verified'] = False
    result = _run(_flush_input(candidates=[cand]), preview, acc, images_dir=images_dir)

    assert result.returncode == 0, f'stderr: {result.stderr}'
