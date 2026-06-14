#!/usr/bin/env python3
"""Flush self-healing de candidatas al cover_preview.json del skill watch-search-covers.

POR QUÉ EXISTE ESTE SCRIPT (anti-drift)
----------------------------------------
El flush de cover_preview.json es una operación no trivial: mantiene un acumulador
de corrida (.tmp_sc_acc.json), hace merge de candidatas sin duplicar por new_url, y
reconstruye el preview con las entradas ajenas preservadas. Antes era código inline
en el skill — al ser reescrito a mano en cada corrida, un agente reconstruyó los
dicts manualmente y perdió el campo new_image, rompiendo la cola completa.

Este script es la fuente de verdad permanente de esa lógica. Las candidatas SIEMPRE
deben pasarse EXACTAMENTE como las devolvió sc_validate.py, sin reconstruir dicts a
mano. Si un candidato no tiene 'new_image' o 'new_url', el script falla con exit 1
antes de escribir nada — esa es la guarda estructural que previene la regresión.

FORMATO DE INPUT (flush_input.json)
-------------------------------------
{
    "slug"             : "attack-on-titan-salvat-integral-es-25",
    "item"             : {... item completo de items.jsonl ...},
    "candidates"       : [... dicts EXACTOS que devolvió sc_validate.py ...],
    "candidate_action" : "replace_cover",
    "candidate_target" : "",
    "old_local"        : "d92a1476ecc69a94.jpg",
    "old_url"          : "https://static.listadomanga.com/...",
    "curr_px"          : 14700
}

USO
----
  sc_flush.py <flush_input.json> [--preview data/cover_preview.json] [--acc .tmp_sc_acc.json]

  --preview PATH  Ruta al archivo de preview (default: data/cover_preview.json)
  --acc PATH      Ruta al acumulador de corrida (default: .tmp_sc_acc.json)

STDOUT
-------
  {"flushed": false, "reason": "no candidates"}
  {"flushed": true, "products": N, "total_candidates": M}
"""
import argparse
import json
import sys
import uuid
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Flush self-healing al cover_preview.json')
    parser.add_argument('input', help='Ruta al flush_input.json')
    parser.add_argument('--preview', default='data/cover_preview.json',
                        help='Ruta al cover_preview.json (default: data/cover_preview.json)')
    parser.add_argument('--acc', default='.tmp_sc_acc.json',
                        help='Ruta al acumulador de corrida (default: .tmp_sc_acc.json)')
    return parser.parse_args()


def validate_candidates(candidates: list[dict], slug: str) -> None:
    """Valida que todos los candidatos tengan los campos requeridos.

    Exit 1 si falta new_image o new_url — es la guarda contra dicts reconstruidos
    a mano que causan datos rotos en la cola.
    """
    errors = []
    for i, c in enumerate(candidates):
        missing = []
        if not c.get('new_image'):
            missing.append('new_image')
        if not c.get('new_url'):
            missing.append('new_url')
        if missing:
            errors.append(
                f'candidata[{i}] del slug "{slug}" le falta: {", ".join(missing)}. '
                f'Pasa los dicts EXACTAMENTE como los devolvió sc_validate.py, '
                f'sin reconstruir a mano.'
            )
    if errors:
        for err in errors:
            print(f'ERROR: {err}', file=sys.stderr)
        sys.exit(1)


def flush(input_path: str, preview_path: str, acc_path: str) -> None:
    inp_p = Path(input_path)
    if not inp_p.exists():
        print(json.dumps({'flushed': False, 'reason': f'input not found: {input_path}'}))
        sys.exit(1)

    data = json.loads(inp_p.read_text(encoding='utf-8'))

    slug             = data['slug']
    item             = data['item']
    candidates       = data.get('candidates', [])
    candidate_action = data.get('candidate_action', 'replace_cover')
    candidate_target = data.get('candidate_target', '')
    old_local        = data.get('old_local', '')
    old_url          = data.get('old_url', '')
    curr_px          = data.get('curr_px', 0)

    if not candidates:
        print(json.dumps({'flushed': False, 'reason': 'no candidates'}))
        return

    # VALIDACIÓN DURA — rechazar antes de escribir cualquier cosa
    validate_candidates(candidates, slug)

    # Tagear cada candidata con la acción correcta
    for c in candidates:
        c['action'] = candidate_action
        c['target'] = candidate_target

    # Cargar acumulador de la corrida
    acc_p = Path(acc_path)
    acc: dict = {}
    if acc_p.exists():
        try:
            acc = json.loads(acc_p.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            acc = {}

    # current_images: galería actual del item (images[0] es la portada, is_cover=True)
    imgs = item.get('images') or []
    current_images = [
        {
            'url'     : im.get('url', ''),
            'local'   : im.get('local', ''),
            'kind'    : im.get('kind', 'gallery'),
            'is_cover': k == 0,
        }
        for k, im in enumerate(imgs)
        if isinstance(im, dict)
    ]

    if slug in acc:
        # Merge: agregar candidatas de esta imagen sin pisar las de portada u otra galería
        existing_urls = {c['new_url'] for c in acc[slug]['candidates']}
        for c in candidates:
            if c['new_url'] not in existing_urls:
                acc[slug]['candidates'].append(c)
                existing_urls.add(c['new_url'])
    else:
        # Leer la entrada existente en el preview para este slug (si la hay) y rescatar
        # las candidatas ya revisadas (approved/rejected). Sin esto, si el skill re-corre
        # sobre un slug con candidatas aprobadas-pero-no-aplicadas, la aprobación se pierde.
        existing_reviewed: list[dict] = []
        preview_p_tmp = Path(preview_path)
        if preview_p_tmp.exists():
            try:
                for e in json.loads(preview_p_tmp.read_text(encoding='utf-8')):
                    if e.get('slug') == slug:
                        existing_reviewed = [
                            c for c in e.get('candidates', [])
                            if c.get('status') in ('approved', 'rejected')
                        ]
                        break
            except (ValueError, OSError):
                pass

        # Combinar: reviewed primero (preservar estado), luego las nuevas (dedup por new_url)
        existing_urls = {c['new_url'] for c in existing_reviewed}
        merged_cands = list(existing_reviewed)
        for c in candidates:
            if c['new_url'] not in existing_urls:
                merged_cands.append(c)
                existing_urls.add(c['new_url'])

        acc[slug] = {
            'slug'          : slug,
            'title'         : item.get('title', ''),
            'title_original': item.get('title_original', ''),
            'series_display': item.get('series_display', ''),
            'publisher'     : item.get('publisher', ''),
            'country'       : item.get('country', ''),
            'old_image'     : old_local,
            'old_url'       : old_url,
            'old_pixels'    : curr_px,
            'current_images': current_images,
            'candidates'    : merged_cands,
        }

    # Persistir acumulador
    acc_p.write_text(json.dumps(acc, ensure_ascii=False), encoding='utf-8')

    # Reconstruir preview: entradas ajenas (no de esta corrida) + mis entradas
    preview_p = Path(preview_path)
    external: list[dict] = []
    if preview_p.exists():
        try:
            for e in json.loads(preview_p.read_text(encoding='utf-8')):
                if e.get('slug') not in acc:
                    external.append(e)
        except (ValueError, OSError):
            pass

    merged = external + list(acc.values())

    # Escritura atómica: tmp + replace
    tmp_out = preview_p.with_suffix(f'.{uuid.uuid4().hex[:8]}.tmp')
    try:
        tmp_out.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp_out.replace(preview_p)
    except OSError as e:
        tmp_out.unlink(missing_ok=True)
        print(f'ERROR al escribir preview: {e}', file=sys.stderr)
        sys.exit(1)

    total_candidates = sum(len(e.get('candidates', [])) for e in merged)
    print(json.dumps({'flushed': True, 'products': len(merged),
                      'total_candidates': total_candidates}))


def main() -> None:
    args = parse_args()
    flush(args.input, args.preview, args.acc)


if __name__ == '__main__':
    main()
