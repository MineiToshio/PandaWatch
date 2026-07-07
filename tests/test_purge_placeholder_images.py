"""Tests para image_store.placeholder_reason y el retrofit
scripts/retrofit/purge_placeholder_images.py.

Sin red — usan imágenes sintéticas PIL en tmp_path.

Cubre:
  - placeholder_reason: tiny (1×1), solid (blanco), real (con textura),
    signature (sha1 registrado), broken (bytes no-imagen / vacío).
  - retrofit: quita placeholders de images[], conserva portadas reales,
    re-posiciona la portada por posición, deja items sin foto cuando toca,
    limpia sources[] que apuntan al placeholder, y NO toca lo real.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import image_store  # noqa: E402


# ── helpers de imágenes sintéticas ────────────────────────────────────────────

def _png_bytes(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _solid(w: int, h: int, color=(255, 255, 255)) -> bytes:
    return _png_bytes(Image.new("RGB", (w, h), color))


def _textured(w: int, h: int) -> bytes:
    """Imagen con estructura (std alta) — una portada real."""
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 5) % 256)
    return _png_bytes(im)


# ── placeholder_reason ────────────────────────────────────────────────────────

def test_tiny_pixel_is_placeholder():
    assert image_store.placeholder_reason(_solid(1, 1)).startswith("tiny")


def test_solid_white_is_placeholder():
    assert image_store.placeholder_reason(_solid(300, 450)).startswith("solid")


def test_textured_cover_is_real():
    assert image_store.placeholder_reason(_textured(300, 450)) == ""


def test_broken_bytes():
    assert image_store.placeholder_reason(b"") == "broken"
    assert image_store.placeholder_reason(b"<html>not an image</html>") == "broken"


def test_signature_match():
    body = _textured(120, 120)  # textura ⇒ no caería por solid/tiny
    sha1 = hashlib.sha1(body).hexdigest()
    sigs = {sha1: "Fake 'no disponible'"}
    assert image_store.placeholder_reason(body, signatures=sigs) == "signature:Fake 'no disponible'"
    # sin la firma, la misma imagen es real
    assert image_store.placeholder_reason(body, signatures={}) == ""


def test_reads_from_path(tmp_path):
    p = tmp_path / "x.png"
    p.write_bytes(_solid(1, 1))
    assert image_store.placeholder_reason(p).startswith("tiny")
    missing = tmp_path / "nope.png"
    assert image_store.placeholder_reason(missing) == "broken"


# ── retrofit end-to-end ───────────────────────────────────────────────────────

@pytest.fixture
def harness(tmp_path, monkeypatch):
    """Monta data/items.jsonl + data/images/ sintéticos y apunta el retrofit ahí."""
    import purge_placeholder_images as ppi

    images = tmp_path / "images"
    images.mkdir()

    def _write(name: str, body: bytes) -> str:
        (images / name).write_bytes(body)
        return name

    real = _write("real_cover.png", _textured(300, 450))
    real2 = _write("real_gallery.png", _textured(280, 400))
    white = _write("white.png", _solid(300, 450))
    pixel = _write("pixel.gif", _solid(1, 1))

    items_path = tmp_path / "items.jsonl"
    monkeypatch.setattr(ppi, "ITEMS", items_path)
    monkeypatch.setattr(ppi, "IMAGES", images)
    monkeypatch.setattr(ppi, "ORPHANS", images / "_orphans")
    monkeypatch.setattr(ppi, "COVER_PREVIEW", tmp_path / "cover_preview.json")
    return ppi, items_path, images, {"real": real, "real2": real2, "white": white, "pixel": pixel}


def _run(ppi, argv):
    old = sys.argv
    sys.argv = ["purge_placeholder_images.py", *argv]
    try:
        return ppi.main()
    finally:
        sys.argv = old


def test_purge_removes_placeholder_keeps_real(harness):
    ppi, items_path, images, f = harness
    items = [
        # placeholder en portada, real en galería ⇒ la real pasa a images[0]
        {"slug": "a", "title": "A", "images": [
            {"url": "http://x/w.png", "local": f["white"], "kind": "gallery"},
            {"url": "http://x/r.png", "local": f["real2"], "kind": "gallery"},
        ], "sources": []},
        # solo placeholder ⇒ queda sin imágenes
        {"slug": "b", "title": "B", "images": [
            {"url": "http://x/p.gif", "local": f["pixel"], "kind": "gallery"},
        ], "sources": [
            {"name": "S", "image_local": f["pixel"], "image_url": "http://x/p.gif"},
        ]},
        # solo real ⇒ intacto
        {"slug": "c", "title": "C", "images": [
            {"url": "http://x/r.png", "local": f["real"], "kind": "gallery"},
        ], "sources": []},
    ]
    items_path.write_text("\n".join(json.dumps(it) for it in items) + "\n")

    assert _run(ppi, []) == 0
    out = [json.loads(l) for l in items_path.read_text().splitlines() if l.strip()]
    by = {it["slug"]: it for it in out}

    # A: la galería real quedó como única foto y es la portada
    assert len(by["a"]["images"]) == 1
    assert by["a"]["images"][0]["local"] == f["real2"]
    # B: sin imágenes (mostrará 📚) y el source quedó limpio
    assert by["b"]["images"] == []
    assert by["b"]["sources"][0]["image_local"] == ""
    assert by["b"]["sources"][0]["image_url"] == ""
    # C: intacto
    assert len(by["c"]["images"]) == 1
    assert by["c"]["images"][0]["local"] == f["real"]

    # huérfanos a cuarentena: white y pixel ya no se referencian
    orphans = images / "_orphans"
    assert (orphans / f["white"]).exists()
    assert (orphans / f["pixel"]).exists()
    # las reales siguen en su lugar
    assert (images / f["real"]).exists()
    assert (images / f["real2"]).exists()


def test_purge_idempotent(harness):
    ppi, items_path, images, f = harness
    items = [{"slug": "a", "title": "A", "images": [
        {"url": "http://x/w.png", "local": f["white"], "kind": "gallery"},
        {"url": "http://x/r.png", "local": f["real"], "kind": "gallery"},
    ], "sources": []}]
    items_path.write_text("\n".join(json.dumps(it) for it in items) + "\n")
    assert _run(ppi, []) == 0
    first = items_path.read_text()
    assert _run(ppi, []) == 0  # 2ª corrida: nada que quitar
    assert items_path.read_text() == first


def test_dry_run_writes_nothing(harness):
    ppi, items_path, images, f = harness
    items = [{"slug": "a", "title": "A", "images": [
        {"url": "http://x/p.gif", "local": f["pixel"], "kind": "gallery"},
    ], "sources": []}]
    raw = "\n".join(json.dumps(it) for it in items) + "\n"
    items_path.write_text(raw)
    assert _run(ppi, ["--dry-run"]) == 0
    assert items_path.read_text() == raw
    assert (images / f["pixel"]).exists()  # no movido a cuarentena


# ── placeholders por URL: conocidos (a) + cross-series (b) ─────────────────────

_KNOWN_HASH = "08a02c268a6d6b2304c152aa0acdc7a0"  # censored-cover listadomanga (LM7)
_KNOWN_URL = f"https://static.listadomanga.com/{_KNOWN_HASH}.png"


def _by_slug(items_path: Path) -> dict:
    return {
        json.loads(l)["slug"]: json.loads(l)
        for l in items_path.read_text().splitlines() if l.strip()
    }


def test_known_hash_registered_in_image_store():
    """El hash del placeholder censurado vive en el registro único de image_store."""
    assert _KNOWN_HASH in image_store.KNOWN_PLACEHOLDER_URL_STEMS
    assert image_store.known_placeholder_url_reason(_KNOWN_URL).startswith("known:")
    # con query params / mayúsculas sigue matcheando (stem case-insensitive)
    assert image_store.known_placeholder_url_reason(_KNOWN_URL + "?v=2").startswith("known:")


def test_purge_known_placeholder_url_keeps_owner(harness):
    """Rule (a): la MISMA URL placeholder conocida (local="") se purga de las
    series ROBADAS (kind=gallery) pero se CONSERVA en el dueño legítimo (el único
    item que la lleva como extra de su propia colección)."""
    ppi, items_path, images, f = harness
    items = [
        {"slug": "owner", "title": "Sexy Cosplay Doll 8", "series_display": "Sexy Cosplay Doll",
         "images": [{"url": _KNOWN_URL, "local": "", "kind": "extra"}], "sources": []},
        {"slug": "v1", "title": "Ayako 1", "series_display": "Ayako",
         "images": [{"url": _KNOWN_URL, "local": "", "kind": "gallery"}], "sources": []},
        {"slug": "v2", "title": "Bastard 1", "series_display": "Bastard",
         "images": [{"url": _KNOWN_URL, "local": "", "kind": "gallery"}], "sources": []},
    ]
    items_path.write_text("\n".join(json.dumps(it) for it in items) + "\n")
    assert _run(ppi, []) == 0
    by = _by_slug(items_path)
    assert by["v1"]["images"] == [] and by["v2"]["images"] == []
    assert len(by["owner"]["images"]) == 1
    assert _KNOWN_HASH in by["owner"]["images"][0]["url"]


def test_purge_cross_series_purges_gallery_not_cover(harness):
    """Rule (b) SEGURA: una URL DESCONOCIDA compartida por ≥4 series distintas es
    sospechosa, pero SOLO se purga de posiciones de GALERÍA (idx>0). NUNCA se toca
    la portada (images[0]): una misma foto puede ser la portada legítima de UNA
    serie y contaminar el carrusel de otras (bug de scrape de búsqueda). Quitar la
    portada destruiría un cover real."""
    ppi, items_path, images, f = harness
    shared = "https://cdn.example.com/thumb-blue.jpg"
    # dueño legítimo: `shared` ES su portada (images[0]) → debe sobrevivir.
    items = [
        {"slug": "bluebox", "title": "Blue Box 16", "series_display": "Blue Box",
         "images": [{"url": shared, "local": "", "kind": "gallery"}], "sources": []},
    ]
    # 4 series distintas la llevan como foto de galería (idx>0) contaminando su carrusel.
    for i, name in enumerate(["Alpha", "Beta", "Gamma", "Delta"]):
        items.append({"slug": f"v{i}", "title": f"{name} 1", "series_display": name,
                      "images": [
                          {"url": f"http://x/{name}.jpg", "local": "", "kind": "gallery"},
                          {"url": shared, "local": "", "kind": "gallery"},
                      ], "sources": []})
    items_path.write_text("\n".join(json.dumps(it) for it in items) + "\n")
    assert _run(ppi, []) == 0
    by = _by_slug(items_path)
    # portada legítima preservada
    assert len(by["bluebox"]["images"]) == 1
    assert shared in by["bluebox"]["images"][0]["url"]
    # contaminación de galería purgada, la portada propia de cada víctima intacta
    for i in range(4):
        urls = [im["url"] for im in by[f"v{i}"]["images"]]
        assert shared not in urls, "la copia de galería contaminante se purga"
        assert len(by[f"v{i}"]["images"]) == 1, "la portada propia (idx0) se conserva"


def test_purge_known_fragment_placeholder_cover(harness):
    """Rule (a) por FRAGMENTO: un asset de sitio conocido (icono/logo/placeholder
    adulto) se purga aunque esté en posición de portada — nunca es un cover real."""
    ppi, items_path, images, f = harness
    twitter = "https://otakucalendar.com/Images/Site/TwitterFollow.png"
    items = [
        {"slug": "a", "title": "Series A 1", "series_display": "A",
         "images": [{"url": twitter, "local": "", "kind": "gallery"}], "sources": []},
        {"slug": "b", "title": "Series B 1", "series_display": "B",
         "images": [{"url": twitter, "local": "", "kind": "gallery"}], "sources": []},
    ]
    items_path.write_text("\n".join(json.dumps(it) for it in items) + "\n")
    assert _run(ppi, []) == 0
    by = _by_slug(items_path)
    assert by["a"]["images"] == [] and by["b"]["images"] == []


def test_purge_cross_series_below_threshold_kept(harness):
    """Una URL desconocida compartida por MENOS de 4 series NO se purga."""
    ppi, items_path, images, f = harness
    shared = "https://cdn.example.com/maybe.jpg"
    items = []
    for i, name in enumerate(["One", "Two", "Three"]):  # 3 series < 4
        items.append({"slug": f"s{i}", "title": f"{name} 1", "series_display": name,
                      "images": [{"url": shared, "local": "", "kind": "gallery"}], "sources": []})
    items_path.write_text("\n".join(json.dumps(it) for it in items) + "\n")
    assert _run(ppi, []) == 0
    by = _by_slug(items_path)
    assert all(len(by[f"s{i}"]["images"]) == 1 for i in range(3)), "bajo umbral → intacto"


def test_purge_intra_series_shared_url_preserved(harness):
    """Falso positivo a evitar: un box y sus tomos de la MISMA serie comparten
    legítimamente una foto. Aunque sean muchos items, es UNA sola serie → NO se
    purga (la regla agrupa por serie, no por item)."""
    ppi, items_path, images, f = harness
    shared = "https://cdn.example.com/box-photo.jpg"
    items = [
        {"slug": "box", "title": "MySeries Box", "series_display": "MySeries",
         "images": [{"url": shared, "local": "", "kind": "gallery"}], "sources": []},
    ]
    for v in range(1, 6):  # 5 tomos misma serie
        items.append({"slug": f"t{v}", "title": f"MySeries {v}", "series_display": "MySeries",
                      "images": [{"url": shared, "local": "", "kind": "extra"}], "sources": []})
    items_path.write_text("\n".join(json.dumps(it) for it in items) + "\n")
    assert _run(ppi, []) == 0
    by = _by_slug(items_path)
    assert len(by["box"]["images"]) == 1
    assert all(len(by[f"t{v}"]["images"]) == 1 for v in range(1, 6)), "misma serie → conservado"
