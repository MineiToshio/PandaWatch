"""Tests para `--slugs` en scripts/retrofit/mirror_images.py.

Sin red — `image_store.download_image` mockeado. Cubre:
  - `_run_backfill(..., slugs=...)` sólo baja imágenes de los items cuyo slug
    matchea; el resto queda con `local` vacío intacto.
  - Regresión crítica: `--slugs` acota los TARGETS, nunca la lista `items` que
    se escribe — un flush (parcial o final) durante una corrida acotada debe
    seguir escribiendo el corpus COMPLETO, no sólo el subconjunto pedido (si
    filtráramos `items` en vez de sólo los targets, un flush a mitad de la
    descarga truncaría items.jsonl).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "retrofit"))

import mirror_images as mi  # noqa: E402


def _items():
    return [
        {"slug": "a", "title": "A", "images": [{"url": "http://x/a.jpg", "local": ""}], "sources": []},
        {"slug": "b", "title": "B", "images": [{"url": "http://x/b.jpg", "local": ""}], "sources": []},
        {"slug": "c", "title": "C", "images": [{"url": "http://x/c.jpg", "local": ""}], "sources": []},
    ]


def test_run_backfill_slugs_only_downloads_targeted_items(tmp_path, monkeypatch):
    calls = []

    def fake_download(url, images_dir, session=None, timeout=None, referer=""):
        calls.append(url)
        return "downloaded.jpg"

    monkeypatch.setattr(mi.image_store, "download_image", fake_download)
    monkeypatch.setattr(mi.image_store, "placeholder_reason", lambda *a, **k: "")
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    __import__('PIL.Image', fromlist=['Image']).new('RGB', (300, 450), 'blue').save(images_dir / 'downloaded.jpg')

    items = _items()
    updated = mi._run_backfill(
        items, images_dir,
        workers=2, per_host_limit=2, timeout=(5, 5), limit=0,
        user_agent="test", dry_run=False, slugs=frozenset({"b"}),
    )
    assert updated == 1
    assert calls == ["http://x/b.jpg"]
    by = {it["slug"]: it for it in items}
    assert by["b"]["images"][0]["local"] == "downloaded.jpg"
    assert by["a"]["images"][0]["local"] == ""  # no tocado
    assert by["c"]["images"][0]["local"] == ""  # no tocado


def test_run_backfill_slugs_empty_means_all(tmp_path, monkeypatch):
    def fake_download(url, images_dir, session=None, timeout=None, referer=""):
        return "downloaded.jpg"

    monkeypatch.setattr(mi.image_store, "download_image", fake_download)
    monkeypatch.setattr(mi.image_store, "placeholder_reason", lambda *a, **k: "")
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    __import__('PIL.Image', fromlist=['Image']).new('RGB', (300, 450), 'blue').save(images_dir / 'downloaded.jpg')

    items = _items()
    updated = mi._run_backfill(
        items, images_dir,
        workers=2, per_host_limit=2, timeout=(5, 5), limit=0,
        user_agent="test", dry_run=False, slugs=frozenset(),
    )
    assert updated == 3


def test_main_cli_with_slugs_never_truncates_the_full_corpus(tmp_path, monkeypatch):
    """Regresión: correr `main()` con --slugs acotado a UN item no debe dejar
    items.jsonl con sólo ese item — el resto del corpus debe sobrevivir intacto,
    incluso pasando por el flush periódico/final."""
    def fake_download(url, images_dir, session=None, timeout=None, referer=""):
        return "downloaded.jpg"

    monkeypatch.setattr(mi.image_store, "download_image", fake_download)
    monkeypatch.setattr(mi.image_store, "placeholder_reason", lambda *a, **k: "")

    items_path = tmp_path / "items.jsonl"
    items = _items()
    items_path.write_text("\n".join(json.dumps(it) for it in items) + "\n", encoding="utf-8")
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    __import__('PIL.Image', fromlist=['Image']).new('RGB', (300, 450), 'blue').save(images_dir / 'downloaded.jpg')

    old_argv = sys.argv
    sys.argv = [
        "mirror_images.py",
        "--input", str(items_path), "--output", str(items_path),
        "--slugs", "b", "--no-gc",
    ]
    try:
        rc = mi.main()
    finally:
        sys.argv = old_argv
    assert rc == 0

    out = [json.loads(l) for l in items_path.read_text().splitlines() if l.strip()]
    assert {it["slug"] for it in out} == {"a", "b", "c"}  # corpus completo, no truncado
    by = {it["slug"]: it for it in out}
    assert by["b"]["images"][0]["local"] == "downloaded.jpg"
    assert by["a"]["images"][0]["local"] == ""
    assert by["c"]["images"][0]["local"] == ""
