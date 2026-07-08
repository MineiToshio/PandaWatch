#!/usr/bin/env python3
"""eval_cover_gate.py — harness de evaluación OFFLINE del gate de identidad de portadas.

Mide, sobre una muestra etiquetada de pares (referencia, candidata), dos POLÍTICAS
de aceptación y reporta la matriz de errores (falsos positivos / falsos negativos)
por categoría de la taxonomía de fallas del owner:

    old_policy  — aspect-ratio-only (±0.30). Lo que hacía el path lens/text
                  ANTES del hardening (2026-07-08): sólo validaba la relación de
                  aspecto, sin verificación de identidad. Era la causa raíz #1 de
                  fotos equivocadas (aceptaba otra edición/otro tomo de la obra).
    new_policy  — delegación PURA al motor de producción: `_same_cover()` completo
                  (aspect ±0.25 + entropía + AND de aHash/dHash/pHash + NCC) más
                  `_is_soft_image()`. Cero copias de lógica: se importan las
                  funciones reales de fetch_better_covers.py.

Muestra (scripts/eval/cover_gate_sample.json + trampas sintéticas generadas al
vuelo). Las imágenes reales referencian data/images/ por path (no se copian
binarios al repo); las sintéticas se generan con PIL de forma determinística
(seed fijo) en un tmpdir y se borran al terminar.

Taxonomía de fallas (owner):
    (2) otro tomo · (3) otra edición/editorial · (4) foto random de la obra
    (5) parecida al tomo 1 / misma plantilla · (6) ilustración sin trade dress

Uso:
    .venv/bin/python scripts/eval/eval_cover_gate.py            # tabla legible
    .venv/bin/python scripts/eval/eval_cover_gate.py --json     # salida JSON
    .venv/bin/python scripts/eval/eval_cover_gate.py --synthetic-only

Determinístico: sin red, sin dependencia de fecha. Corre 2× → resultado idéntico.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import fetch_better_covers as fbc  # noqa: E402

_SAMPLE_PATH = Path(__file__).resolve().parent / "cover_gate_sample.json"

# Umbral de "referencia utilizable" — MISMO literal que `usable_ref` en
# fetch_better_covers._process_item (orig_px >= 10_000). Por debajo, la
# referencia deja de ser fiable para _same_cover → política "sin referencia"
# (en producción se delega al no-ref gate). El harness lo modela para no
# reportar un FP/FN espurio en ese régimen.
USABLE_REF_MIN_PX = 10_000

# Aspect tolerance de la política vieja del path lens (±0.30).
OLD_ASPECT_TOL = 0.30

CATEGORY_NAMES = {
    "positive": "misma portada (positivo)",
    "2": "otro tomo",
    "3": "otra edición/editorial",
    "4": "foto random de la obra",
    "5": "parecida al tomo 1 / plantilla",
    "6": "ilustración sin trade dress",
    "unknown": "incierta",
    "no_reference": "referencia diminuta (<10k px)",
}


# ──────────────────────────────────────────────────────────────────────────────
# Políticas evaluadas
# ──────────────────────────────────────────────────────────────────────────────

def old_policy(ref_bytes: bytes, cand_bytes: bytes) -> str:
    """Política VIEJA (pre-hardening): aspect-ratio-only ±0.30. Devuelve
    'accept'/'reject'. Modela el gate del path lens/text antes de 2026-07-08:
    sin verificación de identidad, sólo relación de aspecto."""
    ow, oh = fbc._get_dims_from_bytes(ref_bytes)
    cw, ch = fbc._get_dims_from_bytes(cand_bytes)
    if ow <= 0 or oh <= 0 or cw <= 0 or ch <= 0:
        return "reject"
    orig_ar = ow / oh
    cand_ar = cw / ch
    return "accept" if abs(orig_ar - cand_ar) / orig_ar <= OLD_ASPECT_TOL else "reject"


def _robust_pixels(data: bytes) -> int:
    """Área en píxeles vía _get_dims_from_bytes (que tiene fallback PIL para AVIF/
    GIF). El parser rápido `_get_pixels_from_bytes` NO cubre AVIF y el espejo local
    está normalizado a AVIF Q60 → devolvería 0 para todas. La revalidación usa el
    mismo criterio PIL (revalidate_cover_preview._pixels_on_disk)."""
    w, h = fbc._get_dims_from_bytes(data)
    return w * h if w > 0 and h > 0 else 0


def new_policy(ref_bytes: bytes, cand_bytes: bytes) -> str:
    """Política NUEVA: delegación pura a _same_cover + _is_soft_image. Devuelve
    'accept'/'reject'/'no_reference'. Sin ref utilizable (<10k px) → la identidad
    no es verificable por este gate → 'no_reference' (producción delega al
    no-ref gate)."""
    ref_px = _robust_pixels(ref_bytes)
    if ref_px < USABLE_REF_MIN_PX:
        return "no_reference"
    if not fbc._same_cover(ref_bytes, cand_bytes):
        return "reject"
    if fbc._is_soft_image(cand_bytes):
        return "reject"
    return "accept"


# ──────────────────────────────────────────────────────────────────────────────
# Trampas sintéticas (deterministas, seed fijo) — cubren la taxonomía donde la
# muestra real no tiene ejemplos (cat 2/4/6) y sirven de candado de regresión.
# ──────────────────────────────────────────────────────────────────────────────

def _jpeg(im, q: int = 90) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=q)
    return buf.getvalue()


def _textured(seed: int = 7, w: int = 400, h: int = 600):
    """Ilustración sintética con estructura y entropía suficiente (determinística)."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    rng = random.Random(seed)
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 255) // w, (y * 255) // h, ((x + y) * 255) // (w + h))
    d = ImageDraw.Draw(im)
    d.ellipse([w // 5, h // 6, w * 4 // 5, h * 2 // 3], fill=(200, 30, 30))
    d.rectangle([w // 8, h * 3 // 4, w * 7 // 8, h * 15 // 16], fill=(20, 20, 120))
    for _ in range(40):
        x = rng.randrange(w)
        y = rng.randrange(h)
        d.rectangle([x, y, x + 12, y + 12],
                    fill=(rng.randrange(256), rng.randrange(256), rng.randrange(256)))
    return im


def _corner_logo(im, frac: float = 0.10):
    """Añade un logo/título PEQUEÑO en la esquina inferior (la ilustración
    domina). Simula la portada del producto con trade dress mínimo."""
    from PIL import ImageDraw  # noqa: PLC0415

    im = im.copy()
    d = ImageDraw.Draw(im)
    w, h = im.size
    bw = int(w * frac)
    bh = int(h * frac * 0.5)
    d.rectangle([int(w * 0.05), int(h * 0.90), int(w * 0.05) + bw, int(h * 0.90) + bh],
                fill=(255, 255, 255))
    d.rectangle([int(w * 0.06), int(h * 0.91), int(w * 0.05) + bw - 4, int(h * 0.90) + bh - 3],
                outline=(0, 0, 0), width=3)
    return im


def _template_cover(seed: int, w: int = 400, h: int = 600):
    """Misma plantilla (barras superior/inferior fijas) con ilustración central
    distinta según el seed. Simula dos tomos de una serie con el mismo layout."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    im = Image.new("RGB", (w, h), (240, 240, 240))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w, 70], fill=(180, 20, 20))
    d.rectangle([0, 530, w, 600], fill=(20, 20, 90))
    rng = random.Random(seed)
    for _ in range(60):
        x = rng.randrange(40, w - 40)
        y = rng.randrange(90, 510)
        d.ellipse([x, y, x + 40, y + 40],
                  fill=(rng.randrange(256), rng.randrange(256), rng.randrange(256)))
    return im


def _light_novel(w: int, h: int):
    """Portada minimalista (fondo casi sólido + franja de título + motivo chico).
    Verificable (stddev >= 20) pero de bajo 'contenido' — protege contra gates
    por regiones mal calibrados que rechazarían un fondo liso."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    im = Image.new("RGB", (w, h), (230, 225, 210))
    d = ImageDraw.Draw(im)
    d.rectangle([0, int(h * 0.80), w, h], fill=(30, 30, 60))
    for i in range(12):
        x = int(w * 0.1) + i * int(w * 0.06)
        d.rectangle([x, int(h * 0.84), x + int(w * 0.03), int(h * 0.95)], fill=(240, 240, 240))
    d.ellipse([int(w * 0.35), int(h * 0.30), int(w * 0.65), int(h * 0.6)], fill=(200, 120, 90))
    d.rectangle([int(w * 0.45), int(h * 0.1), int(w * 0.55), int(h * 0.3)], fill=(120, 80, 60))
    return im


def synthetic_cases(tmpdir: Path) -> list[dict]:
    """Genera las trampas sintéticas en ``tmpdir`` y devuelve sus manifests.

    Cada caso trae ``expected`` = outcome esperado de new_policy (candado de
    regresión, independiente del label) y, si aplica, ``expected_fail`` = True
    (limitación conocida y aceptada: el gate no puede resolver ese caso)."""
    from PIL import Image  # noqa: PLC0415

    cases: list[dict] = []

    def _emit(name, ref_bytes, cand_bytes, **extra):
        ref_p = tmpdir / f"{name}_ref.jpg"
        cand_p = tmpdir / f"{name}_cand.jpg"
        ref_p.write_bytes(ref_bytes)
        cand_p.write_bytes(cand_bytes)
        case = {
            "slug": f"synthetic:{name}",
            "ref_path": str(ref_p),
            "cand_path": str(cand_p),
            "source": "synthetic",
        }
        case.update(extra)
        cases.append(case)

    base = _textured(7)

    # (a) arte-sin-logo (cat 6): item CON logo chico vs candidata = ilustración
    # SIN trade dress. LIMITACIÓN CONOCIDA: la ilustración domina, así que los
    # hashes/NCC colisionan y el gate la ACEPTA. El red team rechazó gates
    # automáticos para este caso → queda cubierto por review humano + denylist.
    _emit("a_arte_sin_logo", _jpeg(_corner_logo(base, 0.10)), _jpeg(base),
          label="negative", category="6", expected="accept", expected_fail=True,
          notas="ilustración sin trade dress; el gate NO la atrapa (limitación conocida, review humano)")

    # (b) otro-tomo-misma-plantilla (cat 2): mismas barras/layout, ilustración
    # central distinta. El gate SÍ la atrapa (aHash/NCC divergen en el centro).
    _emit("b_otro_tomo_plantilla", _jpeg(_template_cover(1)), _jpeg(_template_cover(2)),
          label="negative", category="2", expected="reject",
          notas="misma plantilla, ilustración central distinta; el gate la rechaza")

    # (c) light-novel fondo sólido, dos resoluciones (misma portada). DEBE pasar:
    # protege contra futuros gates por regiones que rechazarían fondos lisos.
    ln_big = _light_novel(600, 900)
    ln_small = ln_big.resize((300, 450), Image.LANCZOS)
    _emit("c_ln_solid_two_res", _jpeg(ln_small), _jpeg(ln_big),
          label="positive", category="positive", expected="accept",
          notas="portada minimalista en dos resoluciones; misma imagen → debe pasar")

    # (d) referencia diminuta (<10k px) → política "sin referencia".
    d_ref = _jpeg(base.resize((80, 120), Image.LANCZOS))  # 9600 px
    _emit("d_tiny_ref", d_ref, _jpeg(base),
          label="no_reference", category="no_reference", expected="no_reference",
          notas="referencia <10k px; el gate reporta 'sin referencia' (delega al no-ref gate)")

    # (e) recompresión JPEG fuerte (misma imagen) → debe pasar.
    _emit("e_jpeg_recompress",
          _jpeg(base.resize((300, 450), Image.LANCZOS), q=90), _jpeg(base, q=25),
          label="positive", category="positive", expected="accept",
          notas="misma imagen, recompresión JPEG fuerte; robusto a artefactos → debe pasar")

    # (f) crop leve ±3%. DOCUMENTADO: un recorte del 3% por lado desplaza el
    # contenido lo suficiente para que NCC caiga bajo 0.90 → el gate estricto la
    # RECHAZA (false-negative aceptable, precisión > recall).
    w, h = base.size
    dx, dy = int(w * 0.03), int(h * 0.03)
    cropped = base.crop((dx, dy, w - dx, h - dy))
    _emit("f_crop_3pct", _jpeg(base.resize((300, 450), Image.LANCZOS)), _jpeg(cropped),
          label="positive", category="positive", expected="reject", expected_fail=True,
          notas="crop ±3%; NCC<0.90 → el gate estricto la rechaza (FN aceptable, documentado)")

    return cases


# ──────────────────────────────────────────────────────────────────────────────
# Evaluación
# ──────────────────────────────────────────────────────────────────────────────

def _read(path: str) -> bytes | None:
    p = Path(path)
    if not p.is_absolute():
        p = _ROOT / path
    try:
        return p.read_bytes()
    except OSError:
        return None


def _classify(label: str, outcome: str) -> str:
    """Devuelve el tipo de resultado para un caso: TP/TN/FP/FN/NR/MISS."""
    if label == "no_reference":
        return "NR" if outcome == "no_reference" else "MISS"
    if label == "positive":
        return "TP" if outcome == "accept" else "FN"
    # negative
    return "FP" if outcome == "accept" else "TN"


def evaluate(cases: list[dict]) -> dict:
    """Corre ambas políticas sobre los casos y arma el resultado agregado."""
    rows: list[dict] = []
    for c in cases:
        ref = _read(c["ref_path"])
        cand = _read(c["cand_path"])
        if ref is None or cand is None:
            rows.append({**{k: c.get(k) for k in ("slug", "label", "category", "source")},
                         "old": "skip", "new": "skip", "skipped": True})
            continue
        old = old_policy(ref, cand)
        new = new_policy(ref, cand)
        rows.append({
            "slug": c["slug"],
            "label": c["label"],
            "category": c.get("category", "unknown"),
            "source": c.get("source", "real"),
            "expected": c.get("expected"),
            "expected_fail": bool(c.get("expected_fail", False)),
            "notas": c.get("notas", ""),
            "old": old,
            "new": new,
            "old_result": _classify(c["label"], old),
            "new_result": _classify(c["label"], new),
        })

    return {
        "rows": rows,
        "old": _summ(rows, "old_result"),
        "new": _summ(rows, "new_result"),
    }


def _summ(rows: list[dict], key: str) -> dict:
    """Agrega FP/FN/TP/TN por política, global y por categoría. Los casos
    expected_fail se contabilizan aparte (no cuentan como falla del harness)."""
    counts = {"TP": 0, "TN": 0, "FP": 0, "FN": 0, "NR": 0, "MISS": 0}
    fp_names: list[str] = []
    fn_names: list[str] = []
    expected_fail_names: list[str] = []
    by_cat: dict[str, dict] = {}
    for r in rows:
        if r.get("skipped"):
            continue
        res = r[key]
        counts[res] = counts.get(res, 0) + 1
        cat = r["category"]
        bc = by_cat.setdefault(cat, {"TP": 0, "TN": 0, "FP": 0, "FN": 0, "NR": 0, "MISS": 0})
        bc[res] += 1
        is_ef = r.get("expected_fail", False)
        if is_ef:
            expected_fail_names.append(r["slug"])
        if res == "FP" and not is_ef:
            fp_names.append(r["slug"])
        if res == "FN" and not is_ef:
            fn_names.append(r["slug"])
    return {
        "counts": counts,
        "by_category": by_cat,
        "false_positives": fp_names,       # excluye expected_fail
        "false_negatives": fn_names,       # excluye expected_fail
        "expected_fail": expected_fail_names,
    }


def load_cases(include_real: bool, include_synthetic: bool, tmpdir: Path) -> list[dict]:
    cases: list[dict] = []
    if include_real and _SAMPLE_PATH.exists():
        cases.extend(json.loads(_SAMPLE_PATH.read_text(encoding="utf-8")))
    if include_synthetic:
        cases.extend(synthetic_cases(tmpdir))
    return cases


def run_eval(include_real: bool = True, include_synthetic: bool = True) -> dict:
    """Punto de entrada programático (lo usa el test). Determinístico."""
    with tempfile.TemporaryDirectory(prefix="cover_gate_eval_") as td:
        cases = load_cases(include_real, include_synthetic, Path(td))
        return evaluate(cases)


# ──────────────────────────────────────────────────────────────────────────────
# Reporte legible
# ──────────────────────────────────────────────────────────────────────────────

def _print_report(result: dict) -> None:
    rows = result["rows"]
    n_real = sum(1 for r in rows if r.get("source") == "real")
    n_syn = sum(1 for r in rows if r.get("source") == "synthetic")
    n_skip = sum(1 for r in rows if r.get("skipped"))
    print("═" * 78)
    print("HARNESS DE EVALUACIÓN — gate de identidad de portadas")
    print(f"Casos: {len(rows) - n_skip} evaluados ({n_real} reales, {n_syn} sintéticos)"
          + (f", {n_skip} salteados (archivo faltante)" if n_skip else ""))
    print("═" * 78)

    for pol in ("old", "new"):
        s = result[pol]
        c = s["counts"]
        label = "OLD (aspect ±0.30)" if pol == "old" else "NEW (_same_cover + _is_soft_image)"
        print(f"\n▐ Política {label}")
        print(f"  TP={c['TP']}  TN={c['TN']}  FP={c['FP']}  FN={c['FN']}"
              f"  NR={c['NR']}  MISS={c['MISS']}")
        print(f"  Falsos positivos (candidata equivocada aceptada): "
              f"{len(s['false_positives'])}")
        for n in s["false_positives"]:
            print(f"      · {n}")
        print(f"  Falsos negativos (positivo rechazado): {len(s['false_negatives'])}")
        for n in s["false_negatives"]:
            print(f"      · {n}")
        if s["expected_fail"]:
            print(f"  Expected-fail (limitación conocida, no cuenta como falla): "
                  f"{len(s['expected_fail'])}")
            for n in s["expected_fail"]:
                print(f"      · {n}")

    # Matriz por categoría (política nueva)
    print("\n▐ Matriz por categoría (política NUEVA)")
    print(f"  {'categoría':<34} {'n':>3} {'FP':>3} {'FN':>3} {'TN':>3} {'TP':>3} {'NR':>3}")
    for cat, bc in sorted(result["new"]["by_category"].items()):
        name = f"{cat} · {CATEGORY_NAMES.get(cat, cat)}"
        n = sum(bc.values())
        print(f"  {name:<34} {n:>3} {bc['FP']:>3} {bc['FN']:>3} "
              f"{bc['TN']:>3} {bc['TP']:>3} {bc['NR']:>3}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="Salida JSON en vez de tabla")
    ap.add_argument("--synthetic-only", action="store_true",
                    help="Solo trampas sintéticas (no requiere data/images/)")
    ap.add_argument("--no-synthetic", action="store_true",
                    help="Solo muestra real (scripts/eval/cover_gate_sample.json)")
    args = ap.parse_args()

    include_real = not args.synthetic_only
    include_synthetic = not args.no_synthetic
    result = run_eval(include_real=include_real, include_synthetic=include_synthetic)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_report(result)


if __name__ == "__main__":
    main()
