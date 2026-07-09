"""tests/test_script_registry.py — anti-drift entre script_registry.py y los
argparse REALES de cada script (4.3, auditoría Fable 2026-07-08).

Es el "mecanismo, no el síntoma" del paquete C-panel-registry: toda la deriva
de los Grupos 1-2 de data/diagnostics/fable-audit-script-registry-20260708.md
(presets con schema viejo, defaults desincronizados, choices incompletas) es
detectable por AST sin ejecutar ningún script. Este test parsea cada script
del registry con `ast` (nunca lo importa/ejecuta) y compara, por flag:

  - el flag existe en el argparse real (cualquier .add_argument(), incluso
    dentro de grupos mutuamente excluyentes);
  - action/type son compatibles (bool↔store_true, int/float↔type=int/float,
    choice↔choices=[...], csv_multi↔action="append");
  - choices del registry ⊆ choices reales;
  - default del registry == default real, cuando AMBOS son resolvables
    estáticamente (constantes de módulo simples se resuelven; expresiones
    complejas se saltean — mejor no reportar que reportar un falso positivo).

El registry puede tener MENOS flags que el argparse real (hay ausencias
deliberadas documentadas en script_registry.py — golden records, gotcha #61).
Lo que este test NUNCA permite es que el registry tenga MÁS o DISTINTO de lo
que el script real soporta.

Además valida el schema de los presets (values/id/desc, no 'flags') — el
bug 1.1 exacto que motivó esta auditoría.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import script_registry as sr  # noqa: E402


# ---------------------------------------------------------------------------
# Extracción por AST del argparse real de un script
# ---------------------------------------------------------------------------

_UNRESOLVED = object()


def _literal(node: ast.AST | None, constants: dict[str, Any]) -> tuple[Any, bool]:
    """Intenta resolver un nodo AST a un valor Python. (valor, resuelto?)."""
    if node is None:
        return None, False
    if isinstance(node, ast.Constant):
        return node.value, True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        val, ok = _literal(node.operand, constants)
        if ok and isinstance(val, (int, float)):
            return -val, True
        return None, False
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        vals = []
        for elt in node.elts:
            v, ok = _literal(elt, constants)
            if not ok:
                return None, False
            vals.append(v)
        return vals, True
    if isinstance(node, ast.Name):
        if node.id in constants:
            return constants[node.id], True
        return None, False
    return None, False


def _module_constants(tree: ast.Module) -> dict[str, Any]:
    """NAME = <literal> a nivel de módulo (una pasada; no sigue cadenas de
    constantes que referencian otras constantes definidas MÁS ABAJO)."""
    constants: dict[str, Any] = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            val, ok = _literal(node.value, constants)
            if ok:
                constants[node.targets[0].id] = val
    return constants


class ArgSpec:
    __slots__ = ("action", "type", "default", "default_resolved", "choices", "choices_resolved")

    def __init__(self, action, type_, default, default_resolved, choices, choices_resolved):
        self.action = action
        self.type = type_
        self.default = default
        self.default_resolved = default_resolved
        self.choices = choices
        self.choices_resolved = choices_resolved


def extract_argparse_flags(path: Path) -> dict[str, ArgSpec]:
    """Parsea `path` y devuelve {"--flag": ArgSpec} de TODAS las llamadas
    .add_argument(...) del módulo (parser.add_argument, group.add_argument,
    a cualquier nivel de anidamiento — dentro de main(), de un mutually
    exclusive group, etc.)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    constants = _module_constants(tree)
    flags: dict[str, ArgSpec] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"):
            continue
        names: list[str] = []
        for arg_node in node.args:
            v, ok = _literal(arg_node, constants)
            if ok and isinstance(v, str) and v.startswith("--"):
                names.append(v)
        if not names:
            continue
        kw = {k.arg: k.value for k in node.keywords if k.arg}

        action_val, action_ok = _literal(kw.get("action"), constants)
        action = action_val if action_ok else None

        type_node = kw.get("type")
        type_name = type_node.id if isinstance(type_node, ast.Name) else None

        default_val, default_ok = _literal(kw.get("default"), constants)
        choices_val, choices_ok = _literal(kw.get("choices"), constants)

        spec = ArgSpec(
            action=action,
            type_=type_name,
            default=default_val if default_ok else _UNRESOLVED,
            default_resolved=default_ok,
            choices=choices_val if choices_ok else None,
            choices_resolved=choices_ok,
        )
        for name in names:
            flags[name] = spec
    return flags


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _py_scripts() -> list[tuple[str, Path]]:
    """(script_id, path) para las entradas del registry cuyo command apunta
    a un .py (los .sh — scrape_delta/full — no tienen argparse propio: se
    controlan por env vars, ver script_registry.py)."""
    out = []
    for spec in sr.SCRIPTS:
        cmd = spec["command"]
        last = cmd[-1]
        if isinstance(last, str) and last.endswith(".py"):
            out.append((spec["id"], ROOT / last))
    return out


@pytest.fixture(scope="module")
def real_flags_by_script() -> dict[str, dict[str, ArgSpec]]:
    cache: dict[str, dict[str, ArgSpec]] = {}
    for script_id, path in _py_scripts():
        cache[script_id] = extract_argparse_flags(path)
    return cache


# ---------------------------------------------------------------------------
# Test 1: schema de presets (habría atrapado el bug 1.1 solo)
# ---------------------------------------------------------------------------

class TestPresetSchema:
    @pytest.mark.parametrize("spec", sr.SCRIPTS, ids=lambda s: s["id"])
    def test_presets_use_values_not_flags(self, spec):
        for preset in spec.get("presets", []):
            assert "flags" not in preset, (
                f"{spec['id']}: preset {preset.get('label')!r} usa la clave "
                f"vieja 'flags' — el panel (web/panel.html applyPreset) sólo "
                f"lee 'values'. Este es EXACTAMENTE el bug 1.1 (2026-07-08)."
            )

    @pytest.mark.parametrize("spec", sr.SCRIPTS, ids=lambda s: s["id"])
    def test_presets_have_id_label_desc_values(self, spec):
        for preset in spec.get("presets", []):
            assert preset.get("id"), f"{spec['id']}: preset sin 'id' — {preset}"
            assert preset.get("label"), f"{spec['id']}: preset {preset.get('id')} sin 'label'"
            assert preset.get("desc"), f"{spec['id']}: preset {preset.get('id')} sin 'desc'"
            assert isinstance(preset.get("values"), dict), (
                f"{spec['id']}: preset {preset.get('id')} sin 'values' (dict)"
            )

    @pytest.mark.parametrize("spec", sr.SCRIPTS, ids=lambda s: s["id"])
    def test_preset_values_reference_known_flags(self, spec):
        known = {f["arg"] for f in spec.get("flags", [])}
        for preset in spec.get("presets", []):
            for arg in preset.get("values", {}):
                assert arg in known, (
                    f"{spec['id']}: preset {preset.get('id')} usa el flag "
                    f"{arg!r}, que no está declarado en 'flags'"
                )

    @pytest.mark.parametrize("spec", sr.SCRIPTS, ids=lambda s: s["id"])
    def test_preset_env_keys_use_allowlist(self, spec):
        for preset in spec.get("presets", []):
            env = preset.get("env")
            if not env:
                continue
            for key in env:
                assert key.startswith(sr.ALLOWED_ENV_PREFIXES), (
                    f"{spec['id']}: preset {preset.get('id')} tiene la env "
                    f"var {key!r} fuera de la allowlist {sr.ALLOWED_ENV_PREFIXES} "
                    f"— resolve_preset_env() la descartaría en silencio."
                )


# ---------------------------------------------------------------------------
# Test 2: ids únicos, mutates_items, script paths existen (redundante con los
# asserts de import del módulo — acá para que quede como test explícito).
# ---------------------------------------------------------------------------

class TestRegistryStructure:
    def test_ids_unique(self):
        ids = [s["id"] for s in sr.SCRIPTS]
        assert len(ids) == len(set(ids)), "hay ids duplicados en SCRIPTS"

    @pytest.mark.parametrize("spec", sr.SCRIPTS, ids=lambda s: s["id"])
    def test_mutates_items_is_bool(self, spec):
        assert isinstance(spec.get("mutates_items"), bool), (
            f"{spec['id']}: falta 'mutates_items' (bool)"
        )

    @pytest.mark.parametrize("script_id, path", _py_scripts(), ids=lambda x: x if isinstance(x, str) else "")
    def test_script_path_exists(self, script_id, path):
        assert path.exists(), f"{script_id}: 'command' apunta a {path}, que no existe"


# ---------------------------------------------------------------------------
# Test 3: flag-por-flag contra el argparse real (AST)
# ---------------------------------------------------------------------------

def _flag_cases():
    """(script_id, path, flag_dict) por cada flag declarado en el registry
    de un script .py — usado para parametrizar con ids legibles."""
    cases = []
    for script_id, path in _py_scripts():
        spec = sr.get_script(script_id)
        for f in spec.get("flags", []):
            cases.append((script_id, path, f))
    return cases


@pytest.mark.parametrize(
    "script_id, path, flag", _flag_cases(),
    ids=lambda v: v if isinstance(v, str) else (v["arg"] if isinstance(v, dict) else ""),
)
def test_registry_flag_matches_real_argparse(script_id, path, flag, real_flags_by_script):
    real_flags = real_flags_by_script[script_id]
    arg = flag["arg"]
    rtype = flag["type"]

    real = real_flags.get(arg)
    assert real is not None, (
        f"{script_id} ({path.relative_to(ROOT)}): el registry declara {arg!r} "
        f"pero el argparse real NO lo tiene. Corré el script con --help para "
        f"confirmar y sincronizá script_registry.py."
    )

    # --- action/type ---
    if rtype == "bool":
        assert real.action in ("store_true", "store_false"), (
            f"{script_id}.{arg}: registry type=bool pero argparse "
            f"action={real.action!r} (esperado store_true/store_false)"
        )
    elif rtype == "csv_multi":
        assert real.action == "append", (
            f"{script_id}.{arg}: registry type=csv_multi pero argparse "
            f"action={real.action!r} (esperado 'append' — si el script SÍ "
            f"splitea comas internamente, usá type='csv' en el registry)"
        )
    elif rtype in ("int", "float"):
        assert real.type == rtype, (
            f"{script_id}.{arg}: registry type={rtype!r} pero argparse "
            f"type={real.type!r}"
        )
        if flag.get("choices"):
            if real.choices_resolved and real.choices is not None:
                caster = int if rtype == "int" else float
                reg_set = {caster(c) for c in flag["choices"]}
                real_set = {caster(c) for c in real.choices}
                assert reg_set.issubset(real_set), (
                    f"{script_id}.{arg}: choices del registry {flag['choices']} "
                    f"⊄ choices reales {real.choices}"
                )
    elif rtype == "choice":
        assert real.choices_resolved and real.choices, (
            f"{script_id}.{arg}: registry type=choice pero el argparse real "
            f"no declara choices=[...] (o no es resoluble estáticamente)"
        )
        real_set = {str(c) for c in real.choices}
        reg_set = {str(c) for c in flag.get("choices", [])}
        assert reg_set.issubset(real_set), (
            f"{script_id}.{arg}: choices del registry {flag.get('choices')} "
            f"⊄ choices reales {real.choices}"
        )
    elif rtype in ("str", "csv"):
        assert real.type in (None, "str"), (
            f"{script_id}.{arg}: registry type={rtype!r} (texto) pero "
            f"argparse type={real.type!r}"
        )
        assert real.action != "append", (
            f"{script_id}.{arg}: argparse real es action='append' pero el "
            f"registry usa type={rtype!r} (una sola toma) — si el script NO "
            f"splitea comas internamente, usá type='csv_multi'."
        )
    else:  # pragma: no cover - _validate_registry() ya lo garantiza
        pytest.fail(f"{script_id}.{arg}: tipo de flag desconocido {rtype!r}")

    # --- default (sólo si ambos lados son resolubles) ---
    reg_default = flag.get("default")
    if reg_default is None or not real.default_resolved:
        return
    real_default = real.default

    if rtype == "bool":
        real_bool = bool(real_default) if real_default is not None else False
        assert bool(reg_default) == real_bool, (
            f"{script_id}.{arg}: default del registry={reg_default!r} != "
            f"default real={real_bool!r}"
        )
    elif rtype == "int":
        try:
            assert int(reg_default) == int(real_default)
        except (TypeError, ValueError):
            pass
        else:
            assert int(reg_default) == int(real_default), (
                f"{script_id}.{arg}: default del registry={reg_default!r} != "
                f"default real={real_default!r}"
            )
    elif rtype == "float":
        try:
            rv, lv = float(reg_default), float(real_default)
        except (TypeError, ValueError):
            return
        assert rv == pytest.approx(lv), (
            f"{script_id}.{arg}: default del registry={reg_default!r} != "
            f"default real={real_default!r}"
        )
    elif rtype in ("str", "choice"):
        if reg_default == "":
            # "" en el registry suele significar "flag no seteado" (csv/str/
            # choice opcionales) — no siempre matchea el default real (p.ej.
            # None). No es una divergencia funcional: build_command trata
            # "" igual que None (omite el flag).
            return
        assert str(reg_default) == str(real_default), (
            f"{script_id}.{arg}: default del registry={reg_default!r} != "
            f"default real={real_default!r}"
        )


# ---------------------------------------------------------------------------
# Test 4: WIKI_BOOTSTRAP_IDS — fuente única sin copias a mano (J-higiene,
# auditoría Fable 2026-07-08). manga_watch.py define la lista una vez;
# source_health.py y script_registry.py la IMPORTAN. Este test es sobre todo
# un guard anti-regresión: si alguien reintroduce una copia hardcodeada en
# cualquiera de los dos lados, este test lo detecta apenas diverja.
# ---------------------------------------------------------------------------

class TestWikiBootstrapIdsSingleSource:
    def test_source_health_matches_manga_watch(self):
        from scripts import manga_watch as mw
        from scripts.audit import source_health as sh

        assert sh._WIKI_IDS == frozenset(mw.WIKI_BOOTSTRAP_IDS)

    def test_script_registry_flag_matches_manga_watch(self):
        from scripts import manga_watch as mw

        spec = sr.get_script(_bootstrap_wiki_script_id())
        flag = next(f for f in spec["flags"] if f["arg"] == "--bootstrap-wiki")
        assert set(flag["choices"]) == set(mw.WIKI_BOOTSTRAP_IDS)


def _bootstrap_wiki_script_id() -> str:
    """Encuentra el id del primer script del registry que declara el flag
    --bootstrap-wiki (evita hardcodear un id de script puntual acá)."""
    for spec in sr.SCRIPTS:
        for f in spec.get("flags", []):
            if f["arg"] == "--bootstrap-wiki":
                return spec["id"]
    pytest.fail("Ningún script del registry declara --bootstrap-wiki")
