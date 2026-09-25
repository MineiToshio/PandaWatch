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
mano. La guarda estructural (validate_candidates) falla con exit 1 antes de escribir
nada si una candidata: le falta new_image/new_url, su new_image no existe en el
espejo local (--images-dir), o le falta algún campo de proveniencia que sc_validate
emite SIEMPRE (new_pixels/verified/confidence/status/match_dist) o lo trae con el
tipo equivocado.

PARIDAD CON EL MOTOR (SC-7)
----------------------------
El rewrite del preview corre bajo el MISMO lock cross-proceso
(`cover_preview.json.lock`) y usa el MISMO merge anti-carrera
(`fetch_better_covers.preview_write_lock` + `_merge_preview_entries`) que
`fetch_better_covers._write_preview` (F19 + hallazgo #14). En CADA flush se relee
el disco y las decisiones del owner (status/reviewed_at/reject_reason) GANAN sobre
el acumulador de corrida — una aprobación hecha después del primer flush de un slug
ya no se pisa.

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
  sc_flush.py <flush_input.json> [--preview data/cover_preview.json]
              [--acc .tmp_sc_acc.json] [--images-dir data/images]

  --preview PATH     Ruta al archivo de preview (default: data/cover_preview.json)
  --acc PATH         Ruta al acumulador de corrida (default: .tmp_sc_acc.json)
  --images-dir PATH  Espejo local donde sc_validate guardó new_image; se verifica
                     que exista (sólo lectura). Default: data/images

STDOUT
-------
  {"flushed": false, "reason": "no candidates"}
  {"flushed": true, "products": N, "total_candidates": M}
"""
import argparse
import json
import os
import sys
import uuid
from pathlib import Path

# El lock cross-proceso y el merge anti-carrera son la MISMA maquinaria que usa
# fetch_better_covers._write_preview (F19 + hallazgo #14). Se IMPORTAN de ahí
# (fuente única) para que el flush del skill y el rewrite del motor tengan
# PARIDAD real: ambos toman `cover_preview.json.lock` sobre todo el intervalo
# read→merge→replace, y ambos preservan las decisiones del owner (status/
# reviewed_at/reject_reason) que estén en disco. Antes el flush no tomaba lock ni
# releía el disco en cada flush → una aprobación del owner hecha DESPUÉS del primer
# flush de un slug se pisaba (last-writer-wins) durante el resto de la corrida (SC-7).
_SCRIPTS_RETROFIT = Path(__file__).resolve().parent
if str(_SCRIPTS_RETROFIT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_RETROFIT))

import fetch_better_covers as fbc  # type: ignore

# Campos de PROVENIENCIA que sc_validate.py emite SIEMPRE para cada candidata. Un
# dict reconstruido a mano (la regresión que este script existe para prevenir) no
# los tiene, o los tiene con el tipo equivocado. La guarda los exige ANTES de
# escribir. `match_dist` puede ser None (item --include-no-image) pero la CLAVE
# siempre está presente. Ver sc_validate.validate() → dict de salida.
_REQUIRED_PROVENANCE = {
    'new_pixels': int,          # resolución del archivo ya normalizado (AVIF)
    'verified': bool,           # pasó _same_cover contra la referencia
    'confidence': str,          # siempre 'low' (candidata sin auto-aplicar)
    'status': str,              # siempre 'pending' al salir de sc_validate
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Flush self-healing al cover_preview.json')
    parser.add_argument('input', help='Ruta al flush_input.json')
    parser.add_argument('--preview', default='data/cover_preview.json',
                        help='Ruta al cover_preview.json (default: data/cover_preview.json)')
    parser.add_argument('--acc', default='.tmp_sc_acc.json',
                        help='Ruta al acumulador de corrida (default: .tmp_sc_acc.json)')
    parser.add_argument('--images-dir', default='data/images',
                        help='Directorio del espejo local donde sc_validate guardó '
                             'new_image (default: data/images). Sólo LECTURA: se '
                             'verifica que el archivo exista.')
    return parser.parse_args()


def validate_candidates(candidates: list[dict], slug: str, images_dir: Path) -> None:
    """Valida que cada candidata venga EXACTAMENTE como la emitió sc_validate.py.

    Exit 1 (antes de escribir nada) si una candidata:
      - no tiene new_image o new_url (dict reconstruido a mano), o
      - su new_image no existe en disco bajo images_dir (archivo fantasma), o
      - le falta algún campo de proveniencia de sc_validate (`_REQUIRED_PROVENANCE`)
        o lo trae con el tipo equivocado.

    Es la guarda estructural contra la regresión histórica: un agente reconstruyó
    los dicts a mano, perdió new_image y rompió la cola completa (2026-06-11).
    """
    errors = []
    for i, c in enumerate(candidates):
        problems = []
        if not c.get('new_image'):
            problems.append('falta new_image')
        elif not (images_dir / c['new_image']).exists():
            problems.append(f'new_image "{c["new_image"]}" no existe en {images_dir}')
        if not c.get('new_url'):
            problems.append('falta new_url')
        for field, typ in _REQUIRED_PROVENANCE.items():
            if field not in c:
                problems.append(f'falta el campo de proveniencia "{field}"')
            elif not isinstance(c[field], typ):
                problems.append(
                    f'"{field}" debe ser {typ.__name__}, vino {type(c[field]).__name__}'
                )
        # match_dist: la CLAVE debe estar presente; el valor es int o None.
        if 'match_dist' not in c:
            problems.append('falta el campo de proveniencia "match_dist"')
        elif c['match_dist'] is not None and not isinstance(c['match_dist'], int):
            problems.append('"match_dist" debe ser int o None')
        if problems:
            errors.append(
                f'candidata[{i}] del slug "{slug}": {"; ".join(problems)}. '
                f'Las candidatas deben venir EXACTAMENTE como las devolvió '
                f'sc_validate.py (sin reconstruir dicts a mano ni fabricarlos).'
            )
    if errors:
        for err in errors:
            print(f'ERROR: {err}', file=sys.stderr)
        sys.exit(1)


# Campos que el guard de URL compartida agrega a una candidata NO desambiguada.
# `shared_with` lleva los OTROS slugs que reclaman la misma imagen; el owner los
# revisa uno a uno en el panel. Nunca se auto-aprueba una candidata así marcada.
_SHARED_GUARD_FIELDS = ('shared_with', 'confidence', 'needs_visual_review')


def _apply_shared_url_guard(acc: dict) -> dict:
    """Guard de URL compartida entre slugs (gotcha #173, 2026-09-02).

    Hallazgo de la Etapa 2 tanda 1: para items SIN imagen de referencia,
    `sc_validate.py` no puede correr `_same_cover` (no hay con qué comparar) y
    acepta cualquier candidata plausible (aspect-ratio + `_is_soft_image` +
    `candidate_metadata_conflict`). Consecuencia medida: 36/50 (72%) de esas
    candidatas `verified:false` compartían la MISMA `new_url` con la candidata
    de OTRO slug de la MISMA serie con OTRO volumen (whakoom devolviendo la
    miniatura de la serie o de otro tomo cuando el tomo específico no tiene
    página propia indexada) — matemáticamente no pueden ser todas correctas.

    Corre sobre TODO el acumulador de la corrida (`acc`, uno por slug, con las
    candidatas que ya pasaron `sc_validate.py`) y agrupa por la clave canónica
    de imagen (`fbc._img_stem(new_url)` — la MISMA que usa el resto del
    pipeline para dedup de `images[]`, así que variantes de tamaño/CDN de la
    misma imagen caen en el mismo grupo). Para cada grupo con ≥2 slugs
    distintos:

      - Si el `page_title`/`new_url` de la candidata declara un número de
        tomo EXPLÍCITO (`fbc._extract_candidate_volumes`) que coincide con el
        `volume` de UN solo slug del grupo → esa candidata se conserva sólo
        ahí; en los demás slugs se marca `status="rejected"`,
        `reject_reason="otro_tomo"` (se queda en el acumulador/preview como
        registro auditable, no desaparece en silencio).
      - Si no hay forma de desambiguar (ningún marcador explícito, o el
        marcador no resuelve a un único slug) → TODAS quedan `pending` pero
        con `shared_with` (los otros slugs del grupo), `confidence="low"` y
        `needs_visual_review=True` — nunca se auto-aprueban.

    Idempotente y seguro de re-invocar en cada flush de la corrida: las
    candidatas ya `rejected` se excluyen de la agrupación (no se re-evalúan),
    y los campos de un grupo no resuelto se recalculan igual cada vez a partir
    del estado actual del acumulador — si un slug nuevo se suma al grupo en un
    flush posterior, `shared_with` crece para reflejarlo.

    Devuelve el resumen para el stdout del flush:
      {'shared_groups': N, 'kept_disambiguated': N, 'rejected_otro_tomo': N,
       'unresolved_flagged': N}
    """
    groups: dict[str, list[tuple[str, int]]] = {}
    for slug, entry in acc.items():
        for idx, c in enumerate(entry.get('candidates', [])):
            if c.get('status') == 'rejected':
                continue
            stem = fbc._img_stem(c.get('new_url', ''))  # noqa: SLF001
            if not stem:
                continue
            groups.setdefault(stem, []).append((slug, idx))

    counts = {
        'shared_groups'      : 0,
        'kept_disambiguated' : 0,
        'rejected_otro_tomo' : 0,
        'unresolved_flagged' : 0,
    }

    for stem, occurrences in groups.items():
        slugs_involved = {slug for slug, _ in occurrences}
        if len(slugs_involved) < 2:
            # También limpiar el marcador si un grupo dejó de compartirse (p.ej.
            # el resto se rechazó en un flush anterior y sólo queda 1 slug vivo).
            for slug, idx in occurrences:
                c = acc[slug]['candidates'][idx]
                for f in _SHARED_GUARD_FIELDS:
                    c.pop(f, None)
            continue
        counts['shared_groups'] += 1

        # ¿Alguna candidata del grupo declara EXPLÍCITAMENTE un tomo que
        # coincide con el `volume` de exactamente UN slug del grupo?
        vol_matches: list[tuple[str, int]] = []
        for slug, idx in occurrences:
            c = acc[slug]['candidates'][idx]
            text = f"{c.get('page_title', '')} {c.get('new_url', '')}"
            explicit, _bare = fbc._extract_candidate_volumes(text)  # noqa: SLF001
            item_vol = str(acc[slug].get('volume', '') or '').strip()
            if explicit and item_vol.isdigit() and int(item_vol) in explicit:
                vol_matches.append((slug, idx))

        if len(vol_matches) == 1:
            keep_slug, keep_idx = vol_matches[0]
            for slug, idx in occurrences:
                c = acc[slug]['candidates'][idx]
                if slug == keep_slug and idx == keep_idx:
                    for f in _SHARED_GUARD_FIELDS:
                        c.pop(f, None)
                    counts['kept_disambiguated'] += 1
                else:
                    c['status'] = 'rejected'
                    c['reject_reason'] = 'otro_tomo'
                    for f in _SHARED_GUARD_FIELDS:
                        c.pop(f, None)
                    counts['rejected_otro_tomo'] += 1
        else:
            for slug, idx in occurrences:
                c = acc[slug]['candidates'][idx]
                c['shared_with'] = sorted(slugs_involved - {slug})
                c['confidence'] = 'low'
                c['needs_visual_review'] = True
                counts['unresolved_flagged'] += 1

    return counts


def flush(input_path: str, preview_path: str, acc_path: str,
          images_dir: str = 'data/images') -> None:
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
    validate_candidates(candidates, slug, Path(images_dir))

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
        acc[slug] = {
            'slug'          : slug,
            'title'         : item.get('title', ''),
            'title_original': item.get('title_original', ''),
            'series_display': item.get('series_display', ''),
            'publisher'     : item.get('publisher', ''),
            'country'       : item.get('country', ''),
            # 'volume' es SÓLO para el guard de URL compartida (abajo): compara
            # el volumen de items DISTINTOS que comparten la misma new_url dentro
            # de la corrida. No es campo de esquema del preview (no lo lee la UI).
            'volume'        : item.get('volume', ''),
            'old_image'     : old_local,
            'old_url'       : old_url,
            'old_pixels'    : curr_px,
            'current_images': current_images,
            'candidates'    : list(candidates),
        }

    # Guard de URL compartida (gotcha #173, 2026-09-02): dentro de esta corrida,
    # si la MISMA new_url se propuso para ≥2 slugs distintos, no puede ser
    # correcta para todos — se re-evalúa sobre TODO el acumulador en cada flush
    # (idempotente, ver docstring de _apply_shared_url_guard).
    shared_url_guard = _apply_shared_url_guard(acc)

    # Persistir acumulador (estado CRUDO de esta corrida — las decisiones del owner
    # se reconcilian contra el disco en cada flush, ver abajo).
    acc_p.write_text(json.dumps(acc, ensure_ascii=False), encoding='utf-8')

    # Reconstruir preview bajo el MISMO lock cross-proceso que fetch_better_covers.
    # _write_preview (F19 + hallazgo #14). El intervalo read→merge→replace corre
    # entero bajo `cover_preview.json.lock`, así que un save del owner desde el panel
    # (serve, otro proceso) cae ENTERO antes o después, nunca en el medio.
    #
    # SC-7 — clave del fix: se relee el disco y se funde con `_merge_preview_entries`
    # en CADA flush (no sólo el primero por slug). El estado de revisión de disco
    # (status/reviewed_at/reject_reason de candidatas approved/rejected) GANA sobre
    # el acumulador: una aprobación del owner hecha DESPUÉS del primer flush de un
    # slug ya NO se pisa en los flushes siguientes de la corrida.
    preview_p = Path(preview_path)
    try:
        with fbc.preview_write_lock(preview_p):
            disk: list[dict] = []
            if preview_p.exists():
                try:
                    disk_raw = json.loads(preview_p.read_text(encoding='utf-8'))
                    if isinstance(disk_raw, list):
                        disk = [fbc._normalize_preview_entry(e)
                                for e in disk_raw if isinstance(e, dict)]
                except (ValueError, OSError):
                    pass

            # memory = entradas de ESTA corrida (acc); disk = lo que hay en el archivo
            # (que la UI/panel pudo modificar). El merge preserva las decisiones de
            # disco y conserva las entradas ajenas (slugs que no tocó esta corrida).
            merged = fbc._merge_preview_entries(list(acc.values()), disk)

            # Escritura atómica: tmp + fsync + replace (misma disciplina que _write_preview)
            tmp_out = preview_p.with_name(f'{preview_p.name}.{uuid.uuid4().hex[:8]}.tmp')
            try:
                with tmp_out.open('w', encoding='utf-8') as f:
                    f.write(json.dumps(merged, ensure_ascii=False, indent=2))
                    f.flush()
                    os.fsync(f.fileno())
                tmp_out.replace(preview_p)
            except OSError as e:
                tmp_out.unlink(missing_ok=True)
                print(f'ERROR al escribir preview: {e}', file=sys.stderr)
                sys.exit(1)
    except TimeoutError as e:
        print(f'ERROR: no se pudo tomar el lock del preview: {e}', file=sys.stderr)
        sys.exit(1)

    total_candidates = sum(len(e.get('candidates', [])) for e in merged)
    print(json.dumps({'flushed': True, 'products': len(merged),
                      'total_candidates': total_candidates,
                      'shared_url_guard': shared_url_guard}))


def main() -> None:
    args = parse_args()
    flush(args.input, args.preview, args.acc, args.images_dir)


if __name__ == '__main__':
    main()
