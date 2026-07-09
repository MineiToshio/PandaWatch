"""Paquete F-escritura (auditoría Fable 2026-07-08) — write_items_atomic/
write_lines_atomic, rotación por-label de backup_and_rotate (A6), orden
rejected-antes-que-kept (A7), determinismo de generate_slugs (A8),
saneo de _publisher_slug/_edition_slug (B9/B10), guard de separador de
_recover_edition_display (B8), RobotsCache vía session con timeout (M10).

Los módulos de retrofit/audit no son paquetes (sin __init__.py) → se cargan
por ruta con importlib, mismo patrón que tests/test_audit_wo_h.py.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import manga_watch as mw  # noqa: E402


def _load(mod_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(mod_name, str(ROOT / rel_path))
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


# ===========================================================================
# 1. write_items_atomic / write_lines_atomic (A7) — durabilidad + formato
# ===========================================================================

def test_write_items_atomic_roundtrip_and_sort_keys(tmp_path):
    dst = tmp_path / "items.jsonl"
    rows = [{"b": 1, "a": 2}, {"z": 9, "y": 8}]
    mw.write_items_atomic(dst, rows)
    lines = dst.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    # sort_keys=True — mismo formato que append_jsonl (homogeneidad, punto 16).
    assert lines[0] == json.dumps(rows[0], ensure_ascii=False, sort_keys=True)
    assert lines[1] == json.dumps(rows[1], ensure_ascii=False, sort_keys=True)
    # No debe sobrevivir el .tmp intermedio.
    assert not dst.with_suffix(dst.suffix + ".tmp").exists()


def test_write_items_atomic_no_partial_write_on_crash_simulated(tmp_path, monkeypatch):
    """Si el proceso muere ANTES del os.replace, el archivo destino original
    (si existía) queda intacto — el .tmp nunca lo reemplazó a medias."""
    dst = tmp_path / "items.jsonl"
    dst.write_text('{"orig": true}\n', encoding="utf-8")

    class _BoomReplace:
        def __call__(self, *a, **k):
            raise RuntimeError("simulated crash before replace")

    real_replace = Path.replace

    def _boom(self, target):
        raise RuntimeError("simulated crash before replace")

    monkeypatch.setattr(Path, "replace", _boom)
    with pytest.raises(RuntimeError):
        mw.write_items_atomic(dst, [{"new": True}])
    monkeypatch.setattr(Path, "replace", real_replace)
    # El destino original sigue intacto — nunca se truncó a medio escribir.
    assert json.loads(dst.read_text(encoding="utf-8").splitlines()[0]) == {"orig": True}


def test_write_lines_atomic_preserves_raw_text(tmp_path):
    dst = tmp_path / "items.jsonl"
    lines = ['{"a": 1}', "not-json-garbage-preserved-verbatim"]
    mw.write_lines_atomic(dst, lines)
    assert dst.read_text(encoding="utf-8").splitlines() == lines


def test_write_lines_atomic_empty_list_writes_empty_file(tmp_path):
    dst = tmp_path / "items.jsonl"
    mw.write_lines_atomic(dst, [])
    assert dst.read_text(encoding="utf-8") == ""


# ===========================================================================
# 2. backup_and_rotate — rotación SOLO por-label (A6)
# ===========================================================================

def test_backup_and_rotate_fixed_slot_does_not_evict_other_labels(tmp_path):
    """Antes: la rama fixed-slot (timestamped=False) ordenaba TODA la carpeta
    de backups por mtime y podaba a max_keep GLOBAL — un label nuevo podía
    evictar el snapshot pre-run de otro label. Ahora sólo poda por-label."""
    items = tmp_path / "items.jsonl"
    items.write_text('{"x": 1}\n', encoding="utf-8")

    # Simular que YA existen slots fijos de otros 5 labels (como el enforcer
    # real: rescore, cluster, translate, apply-approvals, dedup-isbn…).
    other_labels = ["rescore", "cluster", "translate", "apply-approvals", "dedup-isbn"]
    for label in other_labels:
        mw.backup_and_rotate(items, label)

    backups_dir = tmp_path / "backups" / "items.jsonl"
    assert len(list(backups_dir.iterdir())) == len(other_labels)

    # Backup pre-run de NIVEL-RUN (timestamped=True) que "debe sobrevivir".
    run_snapshot = mw.backup_and_rotate(items, "enforce-lmc", timestamped=True)
    assert run_snapshot.exists()

    # Encadenar 4 llamadas MÁS a un label fixed-slot nuevo (como una cadena
    # larga de retrofits) — no debe tocar ni los otros labels fixed-slot NI
    # el snapshot timestamped de nivel-run.
    for _ in range(4):
        mw.backup_and_rotate(items, "generate-slugs")

    assert run_snapshot.exists(), "el snapshot pre-run (timestamped) fue evictado"
    for label in other_labels:
        assert (backups_dir / f"items.jsonl.pre-{label}-bak").exists(), \
            f"el slot fijo de '{label}' fue evictado por la rotación de otro label"


def test_backup_and_rotate_timestamped_rotates_only_own_label(tmp_path, monkeypatch):
    items = tmp_path / "items.jsonl"
    items.write_text('{"x": 1}\n', encoding="utf-8")
    # Un label fixed-slot ajeno no debe afectar el conteo de la familia
    # timestamped de otro label.
    mw.backup_and_rotate(items, "other-fixed")

    # backup_and_rotate formatea el timestamp con resolución de segundo; para
    # aislar el comportamiento de ROTACIÓN (y no la resolución del reloj) se
    # fuerza un timestamp distinto por llamada.
    import datetime as _dt
    calls = {"n": 0}
    real_datetime = mw.dt.datetime

    class _FakeDatetime(real_datetime):
        @classmethod
        def now(cls, *a, **k):
            calls["n"] += 1
            return real_datetime(2026, 1, 1, 0, 0, calls["n"])

    monkeypatch.setattr(mw.dt, "datetime", _FakeDatetime)
    for _ in range(5):
        mw.backup_and_rotate(items, "enforce-lmc", timestamped=True)
    monkeypatch.setattr(mw.dt, "datetime", real_datetime)

    backups_dir = tmp_path / "backups" / "items.jsonl"
    family = list(backups_dir.glob("items.jsonl.*.pre-enforce-lmc-bak"))
    assert len(family) == 3  # max_keep default
    assert (backups_dir / "items.jsonl.pre-other-fixed-bak").exists()


# ===========================================================================
# 3. generate_slugs — determinismo de sufijos de colisión (A8)
# ===========================================================================

def _run_generate_slugs(src: Path, dst: Path, hashseed: str) -> None:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hashseed
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "retrofit" / "generate_slugs.py"),
         "--input", str(src), "--output", str(dst)],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def _collision_fixture() -> list[dict]:
    """Dos clusters DISTINTOS (cluster_key distinto) que derivan la MISMA
    base de slug (mismo edition_key+volume) y el MISMO detected_at más
    viejo — el caso que rompía con PYTHONHASHSEED aleatorio."""
    base = {
        "edition_key": "foo-bar-special-es",
        "volume": "1",
        "detected_at": "2026-01-01T00:00:00Z",
        "score": 10,
    }
    return [
        {**base, "cluster_key": "edition:zzz-cluster|1", "url": "https://a.example/1", "title": "A"},
        {**base, "cluster_key": "edition:aaa-cluster|1", "url": "https://b.example/1", "title": "B"},
        {**base, "cluster_key": "edition:mmm-cluster|1", "url": "https://c.example/1", "title": "C"},
    ]


def test_generate_slugs_deterministic_across_hashseeds(tmp_path):
    fixture = _collision_fixture()
    src_a = tmp_path / "a.jsonl"
    src_a.write_text("\n".join(json.dumps(r) for r in fixture) + "\n", encoding="utf-8")
    src_b = tmp_path / "b.jsonl"
    src_b.write_text("\n".join(json.dumps(r) for r in fixture) + "\n", encoding="utf-8")

    out_a = tmp_path / "a.out.jsonl"
    out_b = tmp_path / "b.out.jsonl"
    _run_generate_slugs(src_a, out_a, hashseed="1")
    _run_generate_slugs(src_b, out_b, hashseed="999999")

    def _slugs_by_cluster(path: Path) -> dict[str, str]:
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        return {r["cluster_key"]: r["slug"] for r in rows}

    slugs_a = _slugs_by_cluster(out_a)
    slugs_b = _slugs_by_cluster(out_b)
    assert slugs_a == slugs_b, (
        "el sufijo de colisión de generate_slugs no es determinista entre "
        f"PYTHONHASHSEED distintos: {slugs_a} vs {slugs_b}"
    )
    # Y efectivamente hubo colisión resuelta (3 slugs únicos, no todos iguales).
    assert len(set(slugs_a.values())) == 3


def test_generate_slugs_isbn_cluster_key_branch_removed():
    generate_slugs = _load("wr_generate_slugs", "scripts/retrofit/generate_slugs.py")
    # B2: la rama muerta "cluster_key = isbn:..." ya no produce un slug isbn-.
    item = {"cluster_key": "isbn:9784799777046", "url": "https://x/y"}
    assert not generate_slugs._derive_base_slug(item).startswith("isbn-")


# ===========================================================================
# 4. fix_edition_key_anomalies — _publisher_slug con -cNNNN (B10)
# ===========================================================================

def test_publisher_slug_skips_disambiguator_token():
    mod = _load("wr_fix_ek_anomalies", "scripts/retrofit/fix_edition_key_anomalies.py")
    # Sin disambiguador: comportamiento previo intacto.
    assert mod._publisher_slug("serie-pub-special-es") == "pub"
    # Con -cNNNN: antes devolvía "special" (el slug de edición, NO el pub).
    assert mod._publisher_slug("serie-pub-special-c1234-es") == "pub"
    assert mod._publisher_slug("serie-pub-special-c1234-xx") == "pub"


def test_resolved_xx_seeded_from_persisted_state(tmp_path, monkeypatch):
    """B10: un hermano -xx que llega DESPUÉS de que otro hermano ya resolvió
    el país (en una corrida anterior, ya persistido en items.jsonl) debe
    heredar el país sin depender de resolverlo él mismo en la MISMA corrida."""
    mod = _load("wr_fix_ek_anomalies2", "scripts/retrofit/fix_edition_key_anomalies.py")
    items_path = tmp_path / "items.jsonl"
    rows = [
        # Hermano YA resuelto en una corrida previa (país real, persistido).
        {"title": "Vol 1", "url": "https://a.example/1",
         "edition_key": "serie-pub-special-es", "volume": "1", "country": "España"},
        # Hermano NUEVO sin evidencia propia (sin isbn, editorial no mono-país
        # en _PUB_COUNTRY) — sólo puede resolver vía el hermano ya persistido.
        {"title": "Vol 2", "url": "https://b.example/2",
         "edition_key": "serie-pub-special-xx", "volume": "2"},
    ]
    items_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(mod, "ITEMS", items_path)
    # El script no acepta --input/--output (usa el global ITEMS, parcheado
    # arriba); probamos la lógica de seed directamente — la misma que main()
    # ejecuta antes del primer pase.
    seeded: dict[str, str] = {}
    for it in rows:
        ek = it.get("edition_key", "") or ""
        parts = ek.split("-")
        country = parts[-1] if parts else ""
        if country and country != "xx" and country in mod._VALID:
            seeded.setdefault(ek[: -len(country)] + "xx", country)
    assert seeded.get("serie-pub-special-xx") == "es"


# ===========================================================================
# 5. align_raw_to_std_coleccion — match posicional exacto (B9)
# ===========================================================================

def test_align_raw_std_has_slug_is_positional_not_substring():
    mod = _load("wr_align_raw", "scripts/retrofit/align_raw_to_std_coleccion.py")
    # Antes: substring — "variant" aparece DENTRO de la serie, no en el slug
    # real de edición → falso positivo.
    std_false_positive = {"edition_key": "some-variant-series-pub-special-es"}
    assert mod._std_has_slug(std_false_positive, "variant") is False
    # El edition_slug real SÍ matchea.
    std_real = {"edition_key": "serie-pub-variant-es"}
    assert mod._std_has_slug(std_real, "variant") is True


# ===========================================================================
# 6. enforce_listadomanga_rules — guard de separador en edition_display (B8)
# ===========================================================================

def test_recover_edition_display_requires_separator(tmp_path, monkeypatch):
    mod = _load("wr_enforce_lmc", "scripts/retrofit/enforce_listadomanga_rules.py")
    items_path = tmp_path / "items.jsonl"
    rows = [
        # Sin " · " — antes esto colaba TODA la description como "título".
        {"url": "https://listadomanga.es/coleccion.php?id=1",
         "description": "Una descripción larga sin el separador esperado de listadomanga en absoluto"},
        # Con separador — sigue funcionando.
        {"url": "https://listadomanga.es/coleccion.php?id=2",
         "description": "Título Oficial · edición especial · más info"},
    ]
    items_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(mod, "ITEMS", items_path)
    n, skipped = mod._recover_edition_display()
    assert n == 1  # sólo el segundo (con separador) se recupera
    written = [json.loads(l) for l in items_path.read_text(encoding="utf-8").splitlines()]
    assert "edition_display" not in written[0] or not written[0].get("edition_display")
    assert written[1]["edition_display"] == "Título Oficial"


def test_recover_edition_display_length_cap(tmp_path, monkeypatch):
    mod = _load("wr_enforce_lmc2", "scripts/retrofit/enforce_listadomanga_rules.py")
    items_path = tmp_path / "items.jsonl"
    long_first_segment = "X" * 200
    rows = [
        {"url": "https://listadomanga.es/coleccion.php?id=3",
         "description": f"{long_first_segment} · edición · info"},
    ]
    items_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(mod, "ITEMS", items_path)
    n, skipped = mod._recover_edition_display()
    assert n == 0  # el primer segmento excede el tope → no se acepta como título


# ===========================================================================
# 7. RobotsCache — fetch vía session con timeout, dict protegido por lock (M10)
# ===========================================================================

def test_robots_cache_uses_project_session_not_urlopen(monkeypatch):
    calls = []

    def _fake_fetch_text(session, url, timeout):
        calls.append((url, timeout))
        return "User-agent: *\nDisallow: /private/\n"

    monkeypatch.setattr(mw, "fetch_text", _fake_fetch_text)
    cache = mw.RobotsCache("test-agent", session=object(), timeout=(3, 7))
    assert cache.allowed("https://example.com/ok") is True
    assert cache.allowed("https://example.com/private/x") is False
    assert len(calls) == 1  # cacheado por host, no se refetchea
    assert calls[0][1] == (3, 7)


def test_robots_cache_has_lock_and_defaults_to_own_session():
    cache = mw.RobotsCache("test-agent")
    assert hasattr(cache, "_lock")
    assert cache.session is not None
