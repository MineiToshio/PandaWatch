"""Tests para scripts/retrofit/sc_plan.py — planificador del Step 1 del skill
/watch-search-covers (auditoría Fable 2026-07-08, hallazgo F9).

Cobertura:
  1. Skip por estado: un (slug, action, target) que ya tiene una candidata DEL
     SKILL (campo match_dist) en pending/approved/rejected se salta.
  2. Guard MIN_REF_PX: referencia degenerada (< 2 500 px, típico placeholder
     1x1) se salta por default; con include_no_image entra con referencia
     blanqueada y SIN variante yandex-reverse.
  3. Exclusión de 30 días: target con último intento 0-matches reciente se
     salta; uno viejo (> 30 días) entra; --retry-failed ignora la exclusión.
  4. Orden de variantes por idioma: Español → whakoom primero, luego
     yandex-reverse; otros idiomas → yandex-reverse primero, sin whakoom.
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

from PIL import Image

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))
if str(_ROOT / "scripts" / "retrofit") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import sc_plan  # type: ignore


def _make_image(path: Path, w: int, h: int) -> None:
    Image.new("RGB", (w, h), color=(200, 50, 50)).save(path)


def _item(slug="test-1", lang="Español", images=None, **extra) -> dict:
    it = {
        "slug": slug,
        "title": "Test Manga 1",
        "title_original": "テスト",
        "series_display": "Test Manga",
        "volume": "1",
        "language": lang,
        "publisher": "Editorial X",
        "edition_key": "test-manga-x-special",
        "images": images if images is not None else [],
        "signal_types": [],
    }
    it.update(extra)
    return it


# ── 1. Skip por estado ───────────────────────────────────────────────────────

def test_skip_when_already_in_preview_pending(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "cover.jpg", 100, 100)  # 10_000 px: baja calidad
    item = _item(images=[{"url": "https://cdn.example.com/cover.jpg", "local": "cover.jpg"}])

    already = {("test-1", "replace_cover", "")}
    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=already, recently_failed=set())
    assert targets == []


def test_included_when_not_in_preview(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "cover.jpg", 100, 100)
    item = _item(images=[{"url": "https://cdn.example.com/cover.jpg", "local": "cover.jpg"}])

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set())
    assert len(targets) == 1
    assert targets[0]["slug"] == "test-1"


# ── 2. Guard MIN_REF_PX (referencia degenerada) ─────────────────────────────

def test_degenerate_reference_skipped_by_default(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "tiny.jpg", 1, 1)  # 1 px < MIN_REF_PX
    item = _item(images=[{"url": "https://cdn.example.com/tiny.jpg", "local": "tiny.jpg"}])

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set())
    assert targets == []


def test_degenerate_reference_included_with_include_no_image_and_no_yandex_variant(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "tiny.jpg", 1, 1)
    item = _item(images=[{"url": "https://cdn.example.com/tiny.jpg", "local": "tiny.jpg"}])

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set(),
                                 include_no_image=True)
    assert len(targets) == 1
    t = targets[0]
    assert t["image_ref_local"] == ""
    assert t["pixels"] == 0
    labels = [v["label"] for v in t["variants"]]
    assert "yandex-reverse" not in labels


# ── 3. Exclusión de 30 días ──────────────────────────────────────────────────

def _attempts_line(slug, action, target, days_ago, matches=0):
    ts = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago))
    return json.dumps({
        "slug": slug, "action": action, "target": target,
        "attempted_at": ts.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "matches": matches,
    })


def test_recently_failed_target_skipped(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "cover.jpg", 100, 100)
    attempts_path = tmp_path / "attempts.jsonl"
    attempts_path.write_text(_attempts_line("test-1", "replace_cover", "", days_ago=5) + "\n",
                             encoding="utf-8")

    recently_failed = sc_plan._load_recently_failed(attempts_path, retry_failed=False)
    item = _item(images=[{"url": "https://cdn.example.com/cover.jpg", "local": "cover.jpg"}])
    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=recently_failed)
    assert targets == []


def test_old_failed_target_included(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "cover.jpg", 100, 100)
    attempts_path = tmp_path / "attempts.jsonl"
    attempts_path.write_text(_attempts_line("test-1", "replace_cover", "", days_ago=45) + "\n",
                             encoding="utf-8")

    recently_failed = sc_plan._load_recently_failed(attempts_path, retry_failed=False)
    assert recently_failed == set()
    item = _item(images=[{"url": "https://cdn.example.com/cover.jpg", "local": "cover.jpg"}])
    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=recently_failed)
    assert len(targets) == 1


def test_retry_failed_ignores_recent_exclusion(tmp_path):
    attempts_path = tmp_path / "attempts.jsonl"
    attempts_path.write_text(_attempts_line("test-1", "replace_cover", "", days_ago=5) + "\n",
                             encoding="utf-8")
    recently_failed = sc_plan._load_recently_failed(attempts_path, retry_failed=True)
    assert recently_failed == set()


# ── 4. Orden de variantes por idioma ─────────────────────────────────────────

def test_spanish_variant_order_whakoom_then_yandex():
    item = _item(lang="Español")
    variants = sc_plan.build_variants(item, ref_url="https://cdn.example.com/cover.jpg")
    labels = [v["label"] for v in variants]
    assert labels[0] == "whakoom"
    assert labels[1] == "yandex-reverse"


def test_non_spanish_variant_order_yandex_first_no_whakoom():
    item = _item(lang="Inglés")
    variants = sc_plan.build_variants(item, ref_url="https://cdn.example.com/cover.jpg")
    labels = [v["label"] for v in variants]
    assert labels[0] == "yandex-reverse"
    assert "whakoom" not in labels


def test_listadomanga_thumbnail_reference_skips_yandex_variant():
    item = _item(lang="Inglés")
    variants = sc_plan.build_variants(
        item, ref_url="https://static.listadomanga.com/thumb.jpg")
    labels = [v["label"] for v in variants]
    assert "yandex-reverse" not in labels


def test_no_ref_url_skips_yandex_variant():
    item = _item(lang="Inglés")
    variants = sc_plan.build_variants(item, ref_url="")
    labels = [v["label"] for v in variants]
    assert "yandex-reverse" not in labels
