#!/usr/bin/env python3
"""dedup_carousel_images.py — quita del carrusel (`images[]`) las imágenes que
son LA MISMA portada en otra resolución, conservando la de MAYOR resolución.

Caso real: artbooks/items de listadomanga que tienen la portada hi-res del
publisher (normaeditorial) + la MISMA portada como thumbnail de baja calidad de
static.listadomanga.com. El usuario ve la foto duplicada en alta y baja.

Seguridad: usa hash perceptual (aHash 8×8) con umbral Hamming ESTRICTO +
chequeo de aspect ratio para NO confundir fotos distintas (cofres, variantes,
páginas de artbook) con duplicados. Nunca deja un item sin imágenes.

Uso:
  .venv/bin/python scripts/retrofit/dedup_carousel_images.py --dry-run
  .venv/bin/python scripts/retrofit/dedup_carousel_images.py [--all]
"""
from __future__ import annotations
import hashlib, json, sys, argparse
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "retrofit"))
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_better_covers as fbc  # noqa: E402  (reusa _ahash/_dhash/_hamming/_get_dims_from_bytes)
import requests  # noqa: E402
import image_store  # noqa: E402  (fuente única de THUMB_ASPECT_TOL, hallazgo #12)
try:  # señal ADICIONAL opcional para el reporte de pares dudosos (gotcha #159) —
    # NUNCA decide el criterio auto, sólo se imprime/reporta como contexto extra
    # para el review humano. Si el paquete no está instalado el script sigue
    # funcionando igual (degrada con gracia, sin la columna pHash-imagehash).
    import imagehash  # noqa: E402
    from PIL import Image  # noqa: E402
    _HAS_IMAGEHASH = True
except ImportError:  # pragma: no cover
    _HAS_IMAGEHASH = False
try:  # import dual robusto (CLI directo vs wrapper raíz bajo pytest)
    from manga_watch import (  # noqa: E402
        backup_and_rotate, is_approved, make_session, write_items_atomic,
    )
except ImportError:  # pragma: no cover
    from scripts.manga_watch import (  # noqa: E402
        backup_and_rotate, is_approved, make_session, write_items_atomic,
    )

ITEMS = ROOT / "data" / "items.jsonl"
IMAGES = ROOT / "data" / "images"
DEFAULT_USER_AGENT = "manga-watch-personal/0.2 (+personal-use)"
MAX_HAMMING = 6        # ≤6/64 bits = misma foto (diff resolución sube ~3-5 bits)
ASPECT_TOL = 0.12      # ratios deben coincidir ±12%
# Caso thumbnail: una versión DIMINUTA (ej. el thumb ~96×150 de listadomanga,
# gotcha #39) de la misma portada pierde tanto detalle que su aHash sube por
# encima de 6 (caso real cole=52: hamming 7). Si una imagen es un thumbnail
# chico, la otra es ≥2× más grande y el aspect ratio es CASI idéntico (±5%),
# es inequívocamente la misma foto reescalada → umbral hamming relajado.
THUMB_MAX_SIDE = 170   # lado menor que delata un thumbnail
THUMB_HAMMING = 14     # umbral relajado SOLO para el par thumbnail↔full (un thumb
                       # ~100px degrada el aHash hasta ~14 bits vs su full)
# Fuente ÚNICA (2026-07-08, hallazgo #12): antes duplicado acá y en
# promote_hires_cover.py, con drift (0.12 vs 0.06) — ahora ambos importan de
# image_store.
THUMB_ASPECT_TOL = image_store.THUMB_ASPECT_TOL

# ── Regla AUTO validada por red-team visual (37 casos, 0 falsos positivos,
#    OLA 2 de depuración de imágenes, 2026-09-01, gotcha #159) ────────────────
# Dentro de un MISMO item, un par es duplicado AUTO-eliminable SOLO si:
#   (a) SHA-256 de bytes idéntico, O
#   (b) dHash Hamming <= REDTEAM_DHASH_AUTO_MAX Y dimensiones DISTINTAS
#       Y |aspect1-aspect2|/aspect1 <= REDTEAM_ASPECT_TOL
# El falso positivo típico (shikishi de colores distintos, caja llena vs
# vacía) tiene dimensiones EXACTAMENTE iguales — por eso "dimensiones
# distintas" es una condición DURA de (b), no un detalle cosmético: dos
# fotos DISTINTAS del mismo producto casi siempre comparten resolución
# (misma cámara/escaneo), mientras que la MISMA foto en dos resoluciones
# (el caso real que sí hay que dedupear) por definición no. NUNCA relajar
# estos 3 valores sin repetir el red-team (ver docs/reference/images.md).
REDTEAM_DHASH_AUTO_MAX = 2      # dHash Hamming máximo para el criterio (b)
REDTEAM_ASPECT_TOL = 0.02       # aspect ratio ±2% para el criterio (b)
# Banda de "vale la pena mirar el par" (no auto-elimina, sólo entra al
# análisis): dHash <= este valor. Fuera de esta banda el par se ignora
# (imágenes claramente distintas). DHASH_MAX_DIST (8) es el mismo tope que
# usa `_same_cover` para el gate de identidad de portadas — reusado como
# banda de "candidato a revisar", no reimplementado.
REDTEAM_DHASH_SCAN_MAX = fbc.DHASH_MAX_DIST

# Sesión HTTP con retry + UA del pipeline (hallazgo #5c, 2026-07-08): antes un
# UA propio ("Mozilla/5.0 (dedup)") distinto al del resto del scraper — fuentes
# como Manga-Sanctuary sirven 404 a UAs desconocidos → dedup omitido en
# silencio para esas fotos. make_session() es la fuente única (retry + headers
# consistentes con el resto del pipeline).
_S = make_session(DEFAULT_USER_AGENT)

# Cache de bytes de imágenes bajadas por URL (fallback cuando no hay `local`
# en disco) con cota LRU (hallazgo #5d): sin tope, una corrida sobre TODO el
# corpus (--all) podía acumular gigabytes de imágenes en memoria.
_BYTES_CACHE_MAX = 200
_bytes_cache: "OrderedDict[str, bytes]" = OrderedDict()


def _cache_get(url: str) -> bytes | None:
    if url not in _bytes_cache:
        return None
    _bytes_cache.move_to_end(url)
    return _bytes_cache[url]


def _cache_put(url: str, data: bytes) -> None:
    _bytes_cache[url] = data
    _bytes_cache.move_to_end(url)
    if len(_bytes_cache) > _BYTES_CACHE_MAX:
        _bytes_cache.popitem(last=False)


def _img_bytes(im: dict) -> bytes:
    local = im.get("local") or ""
    if local:
        p = IMAGES / local
        if p.exists():
            return p.read_bytes()
    url = im.get("url") or ""
    if not url:
        return b""
    cached = _cache_get(url)
    if cached is not None:
        return cached
    try:
        data = _S.get(url, timeout=(10, 30)).content
    except requests.RequestException:
        data = b""
    _cache_put(url, data)
    return data


def _fingerprint(im: dict):
    """(ahash, pixels, w, h) o None si no se pudo leer."""
    data = _img_bytes(im)
    if not data:
        return None
    h = fbc._ahash(data)
    if h is None:
        return None
    w, ht = fbc._get_dims_from_bytes(data)
    return (h, w * ht, w, ht)


def _redteam_fingerprint(im: dict) -> dict | None:
    """(sha256, dhash, px, w, h) para la regla AUTO — None si no es dedupable
    (no es kind=gallery, o no se pudieron leer bytes/dims). Los `extra`
    (cofres, bonuses) NUNCA son candidatos, igual que `_dedupable` de arriba."""
    if im.get("kind", "gallery") != "gallery":
        return None
    data = _img_bytes(im)
    if not data:
        return None
    w, h = fbc._get_dims_from_bytes(data)
    if w <= 0 or h <= 0:
        return None
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "dhash": fbc._dhash(data),
        "px": w * h,
        "w": w,
        "h": h,
    }


def _redteam_classify(rf1: dict, rf2: dict) -> str | None:
    """'auto' | 'dudoso' | None (par fuera de la banda de interés).

    Ver constantes arriba para la justificación de cada umbral — validadas
    por red-team visual (37 casos, 0 falsos positivos)."""
    if rf1["px"] <= 0 or rf2["px"] <= 0:
        return None
    sha1, sha2 = rf1["sha256"], rf2["sha256"]
    if sha1 and sha2 and sha1 == sha2:
        return "auto"
    dh1, dh2 = rf1["dhash"], rf2["dhash"]
    if dh1 is None or dh2 is None:
        return None
    dist = fbc._hamming(dh1, dh2)
    if dist > REDTEAM_DHASH_SCAN_MAX:
        return None  # fuera de la banda de interés, ni auto ni dudoso
    w1, h1, w2, h2 = rf1["w"], rf1["h"], rf2["w"], rf2["h"]
    dims_distinct = (w1, h1) != (w2, h2)
    r1 = (w1 / h1) if h1 else 0
    r2 = (w2 / h2) if h2 else 0
    aspect_diff = abs(r1 - r2) / r1 if r1 else 1.0
    if dist <= REDTEAM_DHASH_AUTO_MAX and dims_distinct and aspect_diff <= REDTEAM_ASPECT_TOL:
        return "auto"
    return "dudoso"  # dentro de la banda pero no cumple (b): dims iguales o
                      # dHash 3-8 — el caso típico de falso positivo del red-team.


def _imagehash_phash_signal(data1: bytes, data2: bytes) -> int | None:
    """Distancia pHash (librería `imagehash`) entre dos imágenes — señal
    ADICIONAL sólo informativa para el reporte de pares dudosos (nunca decide
    el criterio auto). None si `imagehash` no está instalado o el par no es
    decodificable."""
    if not _HAS_IMAGEHASH:
        return None
    try:
        import io
        h1 = imagehash.phash(Image.open(io.BytesIO(data1)))
        h2 = imagehash.phash(Image.open(io.BytesIO(data2)))
        return int(h1 - h2)  # numpy.int64 no serializa a JSON — normalizar a int nativo
    except Exception:
        return None


def _process_item_redteam(it: dict, imgs: list[dict]):
    """Aplica la regla AUTO red-team (ver constantes arriba) a los `images[]`
    de UN item. Devuelve (new_imgs_or_None, dropped, dudosos):

    - `new_imgs_or_None`: nueva lista de `images[]` (con la portada
      re-promovida si hizo falta) si hubo ≥1 auto-drop, o `None` si no
      cambió nada.
    - `dropped`: detalle de lo auto-eliminado (para el reporte/summary).
    - `dudosos`: pares que quedan en la banda de interés pero NO cumplen el
      criterio auto (dims iguales o dHash 3-8) — se reportan, NUNCA se tocan.
    """
    slug = it.get("slug", "")
    rfs = [_redteam_fingerprint(im) for im in imgs]
    keep = [True] * len(imgs)
    dropped: list[dict] = []
    for i in range(len(imgs)):
        if not keep[i] or rfs[i] is None:
            continue
        for j in range(i + 1, len(imgs)):
            if not keep[j] or rfs[j] is None:
                continue
            if _redteam_classify(rfs[i], rfs[j]) != "auto":
                continue
            reason = "sha256" if rfs[i]["sha256"] == rfs[j]["sha256"] else "dhash_rescale"
            drop, win = (j, i) if rfs[j]["px"] <= rfs[i]["px"] else (i, j)
            keep[drop] = False
            dropped.append({
                "slug": slug, "reason": reason, "was_cover": drop == 0,
                "dropped_url": imgs[drop].get("url", ""),
                "dropped_local": imgs[drop].get("local", ""),
                "dropped_px": rfs[drop]["px"],
                "kept_url": imgs[win].get("url", ""),
                "kept_local": imgs[win].get("local", ""),
                "kept_px": rfs[win]["px"],
            })
            if drop == i:
                break  # i descartado, no seguir comparándolo

    # Pares DUDOSOS: se evalúan sobre los SOBREVIVIENTES tras el auto-drop
    # (si A y B eran dup y se auto-drop B, un dudoso B-C ya no existe en la
    # galería final — reportar sobre lo que va a quedar, no sobre lo viejo).
    dudosos: list[dict] = []
    surv = [k for k, kp in enumerate(keep) if kp]
    for a in range(len(surv)):
        ia = surv[a]
        if rfs[ia] is None:
            continue
        for b in range(a + 1, len(surv)):
            ib = surv[b]
            if rfs[ib] is None:
                continue
            if _redteam_classify(rfs[ia], rfs[ib]) != "dudoso":
                continue
            dh = None
            if rfs[ia]["dhash"] is not None and rfs[ib]["dhash"] is not None:
                dh = fbc._hamming(rfs[ia]["dhash"], rfs[ib]["dhash"])
            phash_dist = _imagehash_phash_signal(_img_bytes(imgs[ia]), _img_bytes(imgs[ib]))
            dudosos.append({
                "slug": slug,
                "dhash_dist": dh, "phash_dist_imagehash": phash_dist,
                "same_dims": (rfs[ia]["w"], rfs[ia]["h"]) == (rfs[ib]["w"], rfs[ib]["h"]),
                "image_a": {"url": imgs[ia].get("url", ""), "local": imgs[ia].get("local", ""),
                            "px": rfs[ia]["px"]},
                "image_b": {"url": imgs[ib].get("url", ""), "local": imgs[ib].get("local", ""),
                            "px": rfs[ib]["px"]},
            })

    if not dropped:
        return None, [], dudosos
    new_imgs = [im for k, im in zip(keep, imgs) if k]
    if not new_imgs:
        return None, [], dudosos  # nunca dejar sin imágenes (guard defensivo, ídem path legacy)
    repromoted = False
    if not keep[0]:
        for gi, im in enumerate(new_imgs):
            if im.get("kind", "gallery") == "gallery":
                if gi != 0:
                    new_imgs.insert(0, new_imgs.pop(gi))
                    repromoted = True
                break
    for d in dropped:
        d["repromoted_cover"] = repromoted if d["was_cover"] else False
    return new_imgs, dropped, dudosos


def _write_items(dst: Path, items: list[dict]) -> None:
    """Escritura atómica (tmp + fsync + replace) con `sort_keys=True`
    (idempotencia byte-idéntica entre corridas, hallazgo #5e, 2026-07-08)."""
    write_items_atomic(dst, items)


DUDOSOS_REPORT = ROOT / "data" / "diagnostics" / "dedup-wave2-dudosos.json"


def _write_dudosos_report(dudosos: list[dict]) -> Path:
    """Reporte de pares dudosos — SOLO evidencia para review humano, NUNCA una
    cola de aprobación paralela (regla dura del repo: no inventar archivos
    tipo review_X/uncertain_X). El orquestador/owner decide qué hacer con
    cada par; este script no los toca."""
    DUDOSOS_REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": ("Pares DUDOSOS de dedup_carousel_images.py --redteam-auto: dentro de la "
                 "banda dHash<=8 pero NO cumplen la regla auto (dims iguales, o dHash 3-8). "
                 "NO se auto-eliminan. Esto NO es una cola de aprobación (cover_preview.json "
                 "no soporta hoy una acción 'eliminar imagen' pendiente) — es sólo evidencia "
                 "para que el owner decida."),
        "count": len(dudosos),
        "pairs": dudosos,
    }
    DUDOSOS_REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                               encoding="utf-8")
    return DUDOSOS_REPORT


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true",
                    help="todos los items (default: solo los que tienen una imagen de listadomanga)")
    ap.add_argument("--include-approved", action="store_true",
                    help="También dedupea items aprobados (golden records). Por defecto se "
                         "saltean: dedup puede REORDENAR images[0] (la portada) de un item "
                         "aprobado si la portada actual cae como duplicado de menor resolución.")
    ap.add_argument("--redteam-auto", action="store_true",
                     help="Usa la regla AUTO validada por red-team (SHA-256 idéntico, o dHash<=2 "
                          "+ dims DISTINTAS + aspect<=2%%) en vez de la heurística aHash histórica "
                          "de este script. Escanea TODO el corpus (ignora --all/filtro listadomanga) "
                          "y además reporta pares DUDOSOS (sin tocarlos) en "
                          "data/diagnostics/dedup-wave2-dudosos.json.")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open(encoding="utf-8") if l.strip()]

    backup = None
    if not args.dry_run:
        # Backup ANTES del loop (convención dura): el loop baja imágenes de red
        # y puede tardar — el backup es el punto de retorno de TODA la corrida,
        # no solo del write final.
        label = "wave2-dedup" if args.redteam_auto else "dedup-carousel"
        backup = backup_and_rotate(ITEMS, label)

    removed_total = 0
    items_changed = 0
    skipped_approved = 0
    cover_repromotions = 0
    dudosos: list[dict] = []
    examples = []
    _FLUSH_EVERY = 50  # flush items.jsonl cada N items con cambios (convención)
    for it in items:
        if is_approved(it) and not args.include_approved:
            skipped_approved += 1
            continue
        imgs = it.get("images") or []
        if len(imgs) < 2:
            continue

        if args.redteam_auto:
            new_imgs, dropped, item_dudosos = _process_item_redteam(it, imgs)
            dudosos.extend(item_dudosos)
            if new_imgs is None:
                continue
            if not args.dry_run:
                it["images"] = new_imgs
            removed_total += len(dropped)
            items_changed += 1
            if any(d.get("repromoted_cover") for d in dropped):
                cover_repromotions += 1
            if len(examples) < 25:
                examples.append((it.get("title", "")[:34],
                                  [(d["reason"], (d["dropped_url"] or "").split("/")[-1][:18])
                                   for d in dropped]))
            if not args.dry_run and items_changed % _FLUSH_EVERY == 0:
                _write_items(ITEMS, items)
                print(f"  → flush parcial ({items_changed} items)", flush=True)
            continue

        if not args.all and not any("listadomanga.com" in (im.get("url") or "") for im in imgs):
            continue
        fps = [_fingerprint(im) for im in imgs]
        # SOLO deduplicamos imágenes kind=gallery con dims válidas. Los `extra`
        # (cofres, tomos del box, bonuses) son contenido curado del carrusel —
        # NUNCA se tocan aunque se parezcan a la cover. Y sin dims (px=0) no
        # podemos elegir la de mayor resolución → no arriesgamos.
        def _dedupable(idx):
            return (imgs[idx].get("kind", "gallery") == "gallery"
                    and fps[idx] is not None and fps[idx][1] > 0)
        keep = [True] * len(imgs)
        # comparar pares; si son la misma foto, descartar la de MENOS píxeles.
        for i in range(len(imgs)):
            if not keep[i] or not _dedupable(i):
                continue
            for j in range(i + 1, len(imgs)):
                if not keep[j] or not _dedupable(j):
                    continue
                (h1, px1, w1, ht1), (h2, px2, w2, ht2) = fps[i], fps[j]
                hamm = fbc._hamming(h1, h2)
                r1 = (w1 / ht1) if ht1 else 0
                r2 = (w2 / ht2) if ht2 else 0
                aspect_diff = abs(r1 - r2) / r1 if r1 else 1.0
                # ¿par thumbnail↔full? (una diminuta, la otra ≥2× su lado menor)
                side1, side2 = min(w1, ht1), min(w2, ht2)
                small, big = (side1, side2) if side1 <= side2 else (side2, side1)
                is_thumb_pair = (small <= THUMB_MAX_SIDE and big >= 2 * small
                                 and aspect_diff <= THUMB_ASPECT_TOL)
                if is_thumb_pair:
                    # misma foto reescalada a thumbnail → umbral relajado
                    if hamm > THUMB_HAMMING:
                        continue
                else:
                    if hamm > MAX_HAMMING:
                        continue
                    if r1 and r2 and aspect_diff > ASPECT_TOL:
                        continue
                # misma foto → descartar la de menos píxeles (j si px2<=px1, sino i)
                drop = j if px2 <= px1 else i
                keep[drop] = False
                if drop == i:
                    break  # i descartado, no seguir comparándolo
        if all(keep):
            continue
        new_imgs = [im for k, im in zip(keep, imgs) if k]
        if not new_imgs:
            continue  # nunca dejar sin imágenes
        dropped = [im for k, im in zip(keep, imgs) if not k]
        # La portada es images[0]. Si cayó como duplicado de menor resolución,
        # el primer sobreviviente en orden original NO es necesariamente el
        # hi-res que ganó la comparación — puede ser un `extra` (bonus que
        # viene CON el producto: postal, shikishi) ubicado entre medio, que
        # ascendería a portada por accidente de posición (hallazgo #12,
        # 2026-07-08 — mismo error de clase que sync_cover_images
        # promoviendo un extra, ver docs/reference/images.md). Un `extra`
        # nunca es dedupable (ver `_dedupable`), así que si imgs[0] cayó
        # hubo SIEMPRE otro `gallery` que le ganó la comparación — lo
        # buscamos entre los sobrevivientes y lo movemos a la posición 0.
        if not keep[0]:
            for gi, im in enumerate(new_imgs):
                if im.get("kind", "gallery") == "gallery":
                    if gi != 0:
                        new_imgs.insert(0, new_imgs.pop(gi))
                    break
        if not args.dry_run:
            it["images"] = new_imgs
        removed_total += len(dropped)
        items_changed += 1
        if len(examples) < 25:
            examples.append((it.get("title", "")[:34],
                             [(d.get("kind"), (d.get("url", "") or "").split("/")[-1][:18]) for d in dropped]))
        # Flush incremental (hallazgo #5b, 2026-07-08): el loop baja imágenes
        # de red por cada par a comparar — un write único al final perdía TODO
        # si el proceso moría a mitad de una corrida sobre --all.
        if not args.dry_run and items_changed % _FLUSH_EVERY == 0:
            _write_items(ITEMS, items)
            print(f"  → flush parcial ({items_changed} items)", flush=True)

    if args.redteam_auto:
        report_path = _write_dudosos_report(dudosos)
        print(f"[dedup-redteam] items con auto-dup: {items_changed} | imágenes auto-eliminadas: "
              f"{removed_total} | portadas re-promovidas: {cover_repromotions}")
        try:
            report_rel = report_path.relative_to(ROOT)
        except ValueError:
            report_rel = report_path  # path fuera de ROOT (tests con tmp_path)
        print(f"[dedup-redteam] pares DUDOSOS (sin tocar, sólo reportados): {len(dudosos)} "
              f"→ {report_rel}")
        if not _HAS_IMAGEHASH:
            print("[dedup-redteam] aviso: paquete `imagehash` no disponible — el reporte de "
                  "dudosos no incluye la señal pHash adicional.")
    else:
        print(f"[dedup] items con duplicados de portada: {items_changed} | imágenes quitadas: {removed_total}")
    if skipped_approved:
        print(f"[dedup] items aprobados saltados (usar --include-approved): {skipped_approved}")
    for t, dr in examples:
        print(f"   {t:34} drop={dr}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    _write_items(ITEMS, items)
    print(f"[dedup] escrito {ITEMS}. Backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
