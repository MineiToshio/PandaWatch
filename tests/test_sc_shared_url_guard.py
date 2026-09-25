"""Tests del guard de URL compartida entre slugs (sc_flush._apply_shared_url_guard,
gotcha #173, 2026-09-02).

Hallazgo que motiva el guard (Etapa 2 tanda 1, docs/reference/images.md): para
items SIN imagen de referencia, sc_validate.py no puede correr _same_cover y
acepta cualquier candidata plausible — en la tanda real, 36/50 (72%) de esas
candidatas verified:false compartían la MISMA new_url con la candidata de OTRO
item de la MISMA serie con OTRO volumen (whakoom devolviendo la miniatura de la
serie o de otro tomo). El guard corre en sc_flush.py (que acumula candidatas
entre flushes de la misma corrida vía --acc) porque sc_validate.py valida un
item a la vez y no puede ver el resto de la corrida.

Cobertura:
  1. test_shared_url_disambiguated_by_volume — 3 slugs comparten new_url; el
     page_title de la candidata declara el tomo de UNO solo → esa se conserva,
     las otras 2 quedan rejected/otro_tomo.
  2. test_shared_url_unresolved_flags_all    — misma new_url en 2 slugs, SIN
     marcador de tomo → ninguna se rechaza; ambas quedan pending con
     shared_with/confidence low/needs_visual_review.
  3. test_unique_url_untouched               — new_url única (1 slug) → sin
     campos del guard, comportamiento sin cambios (regresión).
  4. test_metadata_conflict_via_page_title   — candidate_metadata_conflict (ya
     existente, reusada sin duplicar) también detecta el conflicto de tomo
     cuando el marcador está en el page_title, no sólo en la URL.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_FLUSH = _ROOT / 'scripts' / 'retrofit' / 'sc_flush.py'
_PYTHON = _ROOT / '.venv' / 'bin' / 'python'

sys.path.insert(0, str(_ROOT / 'scripts' / 'retrofit'))
import fetch_better_covers as fbc  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _item(slug: str, volume: str = '') -> dict:
    return {
        'slug': slug,
        'title': f'Test {slug}',
        'title_original': '',
        'series_display': 'Bastard!!',
        'publisher': 'Test Editorial',
        'country': 'ES',
        'volume': volume,
        'images': [
            {'url': f'https://example.com/{slug}.jpg', 'local': 'abc123.jpg', 'kind': 'cover'},
        ],
    }


def _candidate(new_url: str, page_title: str = '', new_image: str = 'shared.jpg') -> dict:
    return {
        'new_image'  : new_image,
        'new_url'    : new_url,
        'new_pixels' : 300_000,
        'ref_pixels' : 0,
        'match_dist' : None,
        'verified'   : False,   # candidatas sin referencia — el caso que motiva el guard
        'page_title' : page_title,
        'domain'     : 'i1.whakoom.com',
        'query'      : 'Bastard!! cover',
        'confidence' : 'low',
        'action'     : 'replace_cover',
        'target'     : '',
        'kind'       : 'gallery',
        'status'     : 'pending',
    }


def _flush_input(slug: str, volume: str, candidates: list) -> dict:
    return {
        'slug'             : slug,
        'item'             : _item(slug, volume),
        'candidates'       : candidates,
        'candidate_action' : 'replace_cover',
        'candidate_target' : '',
        'old_local'        : '',
        'old_url'          : '',
        'curr_px'          : 0,
    }


def _run(flush_input: dict, preview: Path, acc: Path, images_dir: Path) -> subprocess.CompletedProcess:
    images_dir.mkdir(parents=True, exist_ok=True)
    for c in flush_input.get('candidates', []):
        ni = c.get('new_image')
        if ni and not (images_dir / ni).exists():
            (images_dir / ni).write_bytes(b'\xff\xd8\xff\xe0\x00\x10JFIF-stub')
    inp = preview.parent / f'flush_input_{flush_input["slug"]}.json'
    inp.write_text(json.dumps(flush_input, ensure_ascii=False), encoding='utf-8')
    return subprocess.run(
        [str(_PYTHON), str(_FLUSH), str(inp),
         '--preview', str(preview), '--acc', str(acc),
         '--images-dir', str(images_dir)],
        capture_output=True, text=True,
    )


def _candidates_by_slug(preview: Path) -> dict:
    data = json.loads(preview.read_text(encoding='utf-8'))
    return {e['slug']: e['candidates'] for e in data}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_shared_url_disambiguated_by_volume(tmp_path):
    """3 slugs (tomos 2, 4, 6 de Bastard!!) reciben la MISMA new_url de whakoom.
    El page_title de la candidata declara "Vol. 4" — coincide con el volume de
    UN solo slug (bastard-4). Esa se conserva; las otras 2 quedan rejected con
    reject_reason=otro_tomo."""
    preview    = tmp_path / 'cover_preview.json'
    acc        = tmp_path / '.tmp_sc_acc.json'
    images_dir = tmp_path / 'images'
    shared_url = 'https://i1.whakoom.com/large/bastard-cover.jpg'

    results = []
    for slug, vol in (('bastard-2-es-1', '2'), ('bastard-4-es-1', '4'), ('bastard-6-es-1', '6')):
        cand = _candidate(shared_url, page_title='Bastard!! Vol. 4 - Whakoom')
        r = _run(_flush_input(slug, vol, [cand]), preview, acc, images_dir)
        assert r.returncode == 0, f'stderr: {r.stderr}'
        results.append(json.loads(r.stdout))

    # El guard se re-evalúa en CADA flush sobre el sub-grupo aún vivo en ese
    # momento (las ya rechazadas salen de la agrupación) — por eso se suma el
    # conteo de los 3 flushes en vez de mirar sólo el último. Total: 1 grupo
    # detectado por flush en el que aparece (2), 1 candidata conservada dos
    # veces (la de bastard-4, ganadora en cada re-evaluación), 2 rechazos
    # (bastard-2 en el flush 2, bastard-6 en el flush 3).
    total_rejected = sum(r['shared_url_guard']['rejected_otro_tomo'] for r in results)
    total_kept     = sum(r['shared_url_guard']['kept_disambiguated'] for r in results)
    total_unresolved = sum(r['shared_url_guard']['unresolved_flagged'] for r in results)
    assert total_rejected == 2
    assert total_kept == 2   # bastard-4 gana en el flush 2 (vs bastard-2) y en el 3 (vs bastard-6)
    assert total_unresolved == 0

    by_slug = _candidates_by_slug(preview)
    assert by_slug['bastard-4-es-1'][0]['status'] == 'pending'
    assert 'reject_reason' not in by_slug['bastard-4-es-1'][0]

    for loser in ('bastard-2-es-1', 'bastard-6-es-1'):
        c = by_slug[loser][0]
        assert c['status'] == 'rejected'
        assert c['reject_reason'] == 'otro_tomo'


def test_shared_url_unresolved_flags_all(tmp_path):
    """2 slugs comparten la misma new_url pero el page_title NO declara ningún
    tomo — no hay forma de desambiguar. Ninguna se rechaza; ambas quedan
    pending con shared_with/confidence low/needs_visual_review=True."""
    preview    = tmp_path / 'cover_preview.json'
    acc        = tmp_path / '.tmp_sc_acc.json'
    images_dir = tmp_path / 'images'
    shared_url = 'https://i1.whakoom.com/large/bleach-series.jpg'

    for slug, vol in (('bleach-7-es-1', '7'), ('bleach-14-es-1', '14')):
        cand = _candidate(shared_url, page_title='Bleach (Manga) - Whakoom')  # sin marcador de tomo
        r = _run(_flush_input(slug, vol, [cand]), preview, acc, images_dir)
        assert r.returncode == 0, f'stderr: {r.stderr}'

    out = json.loads(r.stdout)
    guard = out['shared_url_guard']
    assert guard['shared_groups'] == 1
    assert guard['kept_disambiguated'] == 0
    assert guard['rejected_otro_tomo'] == 0
    assert guard['unresolved_flagged'] == 2

    by_slug = _candidates_by_slug(preview)
    for slug in ('bleach-7-es-1', 'bleach-14-es-1'):
        c = by_slug[slug][0]
        assert c['status'] == 'pending'
        assert c['confidence'] == 'low'
        assert c['needs_visual_review'] is True
        assert c['shared_with'] == sorted({'bleach-7-es-1', 'bleach-14-es-1'} - {slug})


def test_unique_url_untouched(tmp_path):
    """Una new_url que NO se comparte con ningún otro slug no gana ningún campo
    del guard — comportamiento idéntico al de antes del guard (regresión)."""
    preview    = tmp_path / 'cover_preview.json'
    acc        = tmp_path / '.tmp_sc_acc.json'
    images_dir = tmp_path / 'images'

    cand = _candidate('https://i1.whakoom.com/large/one-piece-99.jpg',
                      page_title='One Piece Vol. 99', new_image='op99.jpg')
    r = _run(_flush_input('one-piece-99-es-1', '99', [cand]), preview, acc, images_dir)
    assert r.returncode == 0, f'stderr: {r.stderr}'

    guard = json.loads(r.stdout)['shared_url_guard']
    assert guard['shared_groups'] == 0
    assert guard['kept_disambiguated'] == 0
    assert guard['rejected_otro_tomo'] == 0
    assert guard['unresolved_flagged'] == 0

    c = _candidates_by_slug(preview)['one-piece-99-es-1'][0]
    assert c['status'] == 'pending'
    assert 'shared_with' not in c
    assert 'needs_visual_review' not in c


def test_shared_url_group_grows_across_flushes(tmp_path):
    """El grupo se recalcula en CADA flush: si un 3er slug con la misma new_url
    aparece en un flush posterior, shared_with de los 2 primeros crece para
    reflejarlo (no queda stale desde el primer cálculo)."""
    preview    = tmp_path / 'cover_preview.json'
    acc        = tmp_path / '.tmp_sc_acc.json'
    images_dir = tmp_path / 'images'
    shared_url = 'https://i1.whakoom.com/large/tokyo-revengers.jpg'
    no_vol_title = 'Tokyo Revengers - Whakoom'

    r1 = _run(_flush_input('tr-5-es-1', '5', [_candidate(shared_url, no_vol_title)]),
              preview, acc, images_dir)
    assert r1.returncode == 0, f'stderr: {r1.stderr}'
    assert json.loads(r1.stdout)['shared_url_guard']['shared_groups'] == 0  # todavía solo

    r2 = _run(_flush_input('tr-8-es-1', '8', [_candidate(shared_url, no_vol_title)]),
              preview, acc, images_dir)
    assert r2.returncode == 0, f'stderr: {r2.stderr}'
    guard2 = json.loads(r2.stdout)['shared_url_guard']
    assert guard2['shared_groups'] == 1
    assert guard2['unresolved_flagged'] == 2

    by_slug = _candidates_by_slug(preview)
    assert by_slug['tr-5-es-1'][0]['shared_with'] == ['tr-8-es-1']
    assert by_slug['tr-8-es-1'][0]['shared_with'] == ['tr-5-es-1']


# ── candidate_metadata_conflict — reusada, no duplicada (encargo ítem 2) ──────

def test_metadata_conflict_via_page_title():
    """candidate_metadata_conflict ya cubre el caso 'item con volumen conocido +
    candidata que declara OTRO tomo' — este test cubre el canal page_title (el
    test existente en test_sc_validate.py sólo prueba el canal URL). Reusa la
    función del motor tal cual, sin reimplementar el criterio en sc_flush."""
    item = {'volume': '3', 'images': []}
    # La URL no declara tomo; el conflicto viene SOLO del page_title.
    assert fbc.candidate_metadata_conflict(
        item, 'https://i1.whakoom.com/large/generic.jpg', 'Serie Vol. 11 - Whakoom'
    ) is True


def test_metadata_conflict_no_marker_is_ambiguous():
    """Sin ningún marcador de tomo (ni URL ni page_title) el conflicto NO se
    dispara — es el caso ambiguo que exige el guard de URL compartida (no se
    puede confundir con un conflicto declarado)."""
    item = {'volume': '3', 'images': []}
    assert fbc.candidate_metadata_conflict(
        item, 'https://i1.whakoom.com/large/generic.jpg', 'Serie - Whakoom'
    ) is False
