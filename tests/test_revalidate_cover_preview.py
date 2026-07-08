"""Tests de revalidate_cover_preview.revalidate_preview() — re-validación offline
de la cola de portadas contra el gate endurecido del motor.

Cubre:
  - PASA: candidata que es la misma portada en mejor resolución → match_dist +
    ref_pixels + verified:true, sigue pending.
  - FALLA: candidata que NO es la misma portada → status:rejected +
    reject_reason:auto_revalidation.
  - SIN REFERENCIA: old_image < 10k px → NO se auto-rechaza; verified:false.
  - MOOT: portada vigente ya ≥ LOW_QUALITY_PX (sync la podaría) → intacta.
  - IDEMPOTENCIA: una 2ª pasada no cambia nada (byte-idéntico).
  - No escribe el ledger de rechazos (escritor único = apply/sync).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "retrofit"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from revalidate_cover_preview import revalidate_preview, REVALIDATION_REASON  # noqa: E402
import fetch_better_covers as fbc  # noqa: E402

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers — imágenes sintéticas con estructura de baja frecuencia (invariante
# a escala) para que aHash/dHash/pHash/NCC matcheen entre resoluciones cuando
# es la MISMA portada, y con entropía suficiente (stddev ≥ 20).
# ---------------------------------------------------------------------------

def _draw_cover(path: Path, size, variant: int = 0) -> None:
    """Dibuja una 'portada' determinística: degradado + rectángulos en posiciones
    dependientes de `variant`. La misma variante a distinto tamaño = misma imagen
    (hashes coinciden); variantes distintas = imágenes distintas."""
    w, h = size
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            # Degradado diagonal → stddev alta (pasa el gate de entropía).
            px[x, y] = ((x * 255) // w, (y * 255) // h, ((x + y) * 255) // (w + h))
    d = ImageDraw.Draw(img)
    # Bloques de baja frecuencia; su layout depende de la variante.
    layouts = [
        [(0.1, 0.1, 0.5, 0.4), (0.55, 0.6, 0.9, 0.9)],
        [(0.2, 0.5, 0.8, 0.8), (0.1, 0.05, 0.4, 0.3)],
        [(0.05, 0.6, 0.45, 0.95), (0.5, 0.1, 0.95, 0.5)],
    ]
    for (x0, y0, x1, y1) in layouts[variant % len(layouts)]:
        d.rectangle([x0 * w, y0 * h, x1 * w, y1 * h],
                    fill=(20 + variant * 40, 200 - variant * 30, 90))
    img.save(path, "PNG")


def _item(slug: str, cover_local: str, cover_url: str = "http://x/cover.png") -> dict:
    return {"slug": slug, "title": f"T {slug}",
            "images": [{"url": cover_url, "local": cover_local, "kind": "gallery"}]}


def _entry(slug: str, old_image: str, candidates: list[dict],
           old_url: str = "http://x/old.png") -> dict:
    return {
        "slug": slug,
        "title": f"T {slug}",
        "old_url": old_url,
        "old_image": old_image,
        "old_pixels": 15_000,
        "current_images": [{"url": old_url, "local": old_image,
                            "kind": "gallery", "is_cover": True}],
        "candidates": candidates,
    }


def _cand(new_image: str, new_url: str = "http://x/new.png",
          action: str = "replace_cover", status: str = "pending") -> dict:
    return {"action": action, "status": status, "new_url": new_url,
            "new_image": new_image, "new_pixels": 900_000, "target": "",
            "kind": "gallery", "confidence": "low", "match_dist": None}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_pass_populates_match_dist_and_verified(tmp_path):
    """Candidata = misma portada en mejor resolución → verified + match_dist."""
    imgs = tmp_path / "images"; imgs.mkdir()
    _draw_cover(imgs / "old.png", (100, 150), variant=0)   # ref chica (15k px)
    _draw_cover(imgs / "new.png", (800, 1200), variant=0)  # misma, hi-res

    entry = _entry("s1", "old.png", [_cand("new.png")])
    items = {"s1": _item("s1", "old.png", cover_url="http://x/old.png")}
    out, stats = revalidate_preview([entry], items, imgs)

    cand = out[0]["candidates"][0]
    assert cand["status"] == "pending"
    assert cand["verified"] is True
    assert isinstance(cand["match_dist"], int) and cand["match_dist"] <= fbc.DEFAULT_MAX_HASH_DIST
    assert cand["ref_pixels"] == 15_000
    assert stats["passed"] == 1
    assert stats["rejected_same_cover"] == 0


def test_reject_when_not_same_cover(tmp_path):
    """Candidata = portada DISTINTA → rejected + reject_reason auto_revalidation."""
    imgs = tmp_path / "images"; imgs.mkdir()
    _draw_cover(imgs / "old.png", (100, 150), variant=0)
    _draw_cover(imgs / "new.png", (800, 1200), variant=2)  # otra portada

    entry = _entry("s2", "old.png", [_cand("new.png")])
    items = {"s2": _item("s2", "old.png", cover_url="http://x/old.png")}
    out, stats = revalidate_preview([entry], items, imgs)

    cand = out[0]["candidates"][0]
    assert cand["status"] == "rejected"
    assert cand["reject_reason"] == REVALIDATION_REASON
    assert stats["rejected_same_cover"] == 1
    assert stats["passed"] == 0


def test_no_usable_reference_not_rejected(tmp_path):
    """old_image < 10k px → NO auto-rechazo; solo verified:false, sigue pending."""
    imgs = tmp_path / "images"; imgs.mkdir()
    _draw_cover(imgs / "old.png", (50, 50), variant=0)     # 2500 px < 10k
    _draw_cover(imgs / "new.png", (800, 1200), variant=0)

    entry = _entry("s3", "old.png", [_cand("new.png")])
    # item cover chica (no moot) pero distinta url para no gatillar poda 3a
    items = {"s3": _item("s3", "old.png", cover_url="http://x/old.png")}
    out, stats = revalidate_preview([entry], items, imgs)

    cand = out[0]["candidates"][0]
    assert cand["status"] == "pending"
    assert cand["verified"] is False
    assert "reject_reason" not in cand
    assert stats["no_ref"] == 1
    assert stats["passed"] == 0
    assert stats["rejected_same_cover"] == 0


def test_moot_left_untouched(tmp_path):
    """Portada vigente del item ya ≥ LOW_QUALITY_PX → sync la podaría → moot:
    la candidata se deja intacta (sin verified, sin rejected)."""
    imgs = tmp_path / "images"; imgs.mkdir()
    _draw_cover(imgs / "old.png", (100, 150), variant=0)
    _draw_cover(imgs / "new.png", (800, 1200), variant=0)
    # Portada VIGENTE del item ya en alta calidad (350x260 = 91k ≥ 90k).
    _draw_cover(imgs / "hires_cover.png", (350, 260), variant=0)

    entry = _entry("s4", "old.png", [_cand("new.png")])
    items = {"s4": _item("s4", "hires_cover.png", cover_url="http://x/hires.png")}
    out, stats = revalidate_preview([entry], items, imgs)

    cand = out[0]["candidates"][0]
    assert cand["status"] == "pending"
    assert "verified" not in cand          # intacta
    assert cand["match_dist"] is None
    assert stats["moot"] == 1
    assert stats["passed"] == 0


def test_idempotent(tmp_path):
    """Una 2ª pasada no cambia nada (byte-idéntico); las ya procesadas se saltan."""
    imgs = tmp_path / "images"; imgs.mkdir()
    _draw_cover(imgs / "old.png", (100, 150), variant=0)
    _draw_cover(imgs / "new.png", (800, 1200), variant=0)      # pasa
    _draw_cover(imgs / "old2.png", (100, 150), variant=0)
    _draw_cover(imgs / "new2.png", (800, 1200), variant=2)     # rechaza

    preview = [
        _entry("a", "old.png", [_cand("new.png", new_url="http://x/n1.png")]),
        _entry("b", "old2.png", [_cand("new2.png", new_url="http://x/n2.png")]),
    ]
    items = {"a": _item("a", "old.png", cover_url="http://x/olda.png"),
             "b": _item("b", "old2.png", cover_url="http://x/oldb.png")}

    out1, stats1 = revalidate_preview(preview, items, imgs)
    assert stats1["passed"] == 1 and stats1["rejected_same_cover"] == 1

    out2, stats2 = revalidate_preview(out1, items, imgs)
    assert out2 == out1                       # byte-idéntico
    assert stats2["passed"] == 0
    assert stats2["rejected_same_cover"] == 0
    assert stats2["already_verified"] == 1    # la que pasó (tiene verified)
    assert stats2["decided"] == 1             # la rechazada (status != pending)


def test_decided_and_already_verified_skipped(tmp_path):
    """Candidatas approved/rejected o pending-con-verified no se reprocesan."""
    imgs = tmp_path / "images"; imgs.mkdir()
    _draw_cover(imgs / "old.png", (100, 150), variant=0)
    _draw_cover(imgs / "new.png", (800, 1200), variant=0)

    approved = _cand("new.png", status="approved")
    verified_pending = {**_cand("new.png", new_url="http://x/v.png"), "verified": True,
                        "match_dist": 1}
    entry = _entry("s5", "old.png", [approved, verified_pending])
    items = {"s5": _item("s5", "old.png", cover_url="http://x/old.png")}
    out, stats = revalidate_preview([entry], items, imgs)

    assert out == [entry]                      # nada cambia
    assert stats["decided"] == 1
    assert stats["already_verified"] == 1
    assert stats["passed"] == 0


def test_no_ledger_written(tmp_path, monkeypatch):
    """revalidate_preview NUNCA escribe el ledger de rechazos (escritor único =
    apply/sync)."""
    imgs = tmp_path / "images"; imgs.mkdir()
    _draw_cover(imgs / "old.png", (100, 150), variant=0)
    _draw_cover(imgs / "new.png", (800, 1200), variant=2)  # rechaza

    calls = []
    monkeypatch.setattr(fbc, "ledger_append", lambda rec: calls.append(rec))

    entry = _entry("s6", "old.png", [_cand("new.png")])
    items = {"s6": _item("s6", "old.png", cover_url="http://x/old.png")}
    out, stats = revalidate_preview([entry], items, imgs)

    assert stats["rejected_same_cover"] == 1
    assert calls == []                         # el ledger no se tocó
