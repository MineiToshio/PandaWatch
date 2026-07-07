import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Para que tests puedan `from wikis import listadomanga`.
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


@pytest.fixture(autouse=True)
def _isolate_serve_data_dir(tmp_path, monkeypatch):
    """Aísla TODAS las escrituras de serve.py a un tmp por test.

    `scripts/serve.py` deriva sus paths de escritura (items/feedback/approvals/
    edits/dup_decisions) de la env var MANGA_WATCH_DATA_DIR. Sin esto, los tests
    que cargan serve vía `_load_serve()` y no setean cada path a mano escribían a
    `data/feedback.jsonl` REAL: el leak que la llenó con 670 filas de prueba
    (urls "https://a"/"https://x", reasons "dup"/"regroup") corrida tras corrida.
    El fixture corre ANTES del cuerpo del test, así el `_load_serve()` interno
    re-importa serve y lee esta env var → nunca toca los datos reales.
    """
    data_dir = tmp_path / "_serve_data"
    data_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("MANGA_WATCH_DATA_DIR", str(data_dir))
    yield
