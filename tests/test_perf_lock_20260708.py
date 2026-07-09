"""Paquete G — auditoría Fable 2026-07-08.

Cubre:
- A10: spool de flush incremental (equivalencia con el append per-flush viejo,
  durabilidad ante crash, absorción + borrado).
- A11: _COMPILED_RULES / _PRODUCT_TYPE_COMPILED alineados con las listas fuente.
- A12/S10: lock inter-proceso sobre items.jsonl con DOS procesos reales.
- Punto 5: gate del logging de unmapped_series (efecto separado de la derivación).
- B18: fixes de Playwright (backlog-aware timeout, final_url).
"""
import hashlib
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import manga_watch as mw  # noqa: E402


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _row(url, **kw):
    r = {"url": url, "title": kw.get("title", "T"), "detected_at": kw.get("detected_at", "2026-01-01"),
         "score": kw.get("score", 50), "sources": kw.get("sources", [])}
    r.update(kw)
    return r


# ---------------------------------------------------------------------------
# A10 — spool
# ---------------------------------------------------------------------------

def test_spool_equivalent_to_per_flush_append(tmp_path):
    """El spool + append final produce un items.jsonl byte-idéntico al que
    producía el append per-flush histórico. (detected_at único por URL para que
    el orden final quede totalmente determinado — sin ties.)"""
    base = [_row(f"http://x/{i}", title=f"T{i}", detected_at=f"2026-01-{i:02d}") for i in range(1, 6)]
    corpus = tmp_path / "corpus.jsonl"
    with corpus.open("w") as fh:
        for r in base:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    batches = [
        [_row("http://x/1", title="T1", detected_at="2026-01-01", stock_type="a"),
         _row("http://x/9", title="T9", detected_at="2026-01-09")],
        [_row("http://x/2", title="T2", detected_at="2026-01-02", stock_type="b")],
        [_row("http://x/9", title="T9", detected_at="2026-01-09", stock_type="c")],
    ]

    old = tmp_path / "old.jsonl"
    old.write_bytes(corpus.read_bytes())
    for b in batches:
        mw.append_jsonl(old, [dict(r) for r in b])

    new = tmp_path / "new.jsonl"
    new.write_bytes(corpus.read_bytes())
    for b in batches:
        mw._append_spool(new, [dict(r) for r in b])
    mw.append_jsonl(new, [])  # absorb spool

    assert _md5(old) == _md5(new)
    assert not mw._items_spool_path(new).exists()  # spool borrado


def test_spool_survives_without_final_append(tmp_path):
    """Durabilidad (a): si el run muere antes del append final, el corpus queda
    intacto/válido y lo flusheado sobrevive en el spool para el próximo append."""
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(json.dumps(_row("http://x/1"), sort_keys=True) + "\n")
    corpus_md5 = _md5(corpus)

    mw._append_spool(corpus, [_row("http://x/2", title="new")])
    # "Crash": no se llamó append_jsonl → corpus intacto, spool con lo flusheado.
    assert _md5(corpus) == corpus_md5
    spool = mw._items_spool_path(corpus)
    assert spool.exists()
    lines = [l for l in corpus.read_text().splitlines() if l.strip()]
    assert len(lines) == 1  # corpus sigue teniendo sólo la fila vieja, parseable
    for l in lines:
        json.loads(l)  # válido

    # Próximo append lo absorbe.
    mw.append_jsonl(corpus, [])
    urls = {json.loads(l)["url"] for l in corpus.read_text().splitlines() if l.strip()}
    assert urls == {"http://x/1", "http://x/2"}
    assert not spool.exists()


def test_spool_absorbed_by_leftover_on_next_write(tmp_path):
    """Un spool huérfano (crash previo) lo absorbe CUALQUIER append_jsonl."""
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(json.dumps(_row("http://x/1"), sort_keys=True) + "\n")
    # spool huérfano
    mw._append_spool(corpus, [_row("http://x/2")])
    # append de OTRA fila absorbe el huérfano + agrega la nueva
    mw.append_jsonl(corpus, [_row("http://x/3")])
    urls = {json.loads(l)["url"] for l in corpus.read_text().splitlines() if l.strip()}
    assert urls == {"http://x/1", "http://x/2", "http://x/3"}


# ---------------------------------------------------------------------------
# A11 — compiled rules alineadas con la fuente
# ---------------------------------------------------------------------------

def test_compiled_rules_match_keyword_rules():
    assert len(mw._COMPILED_RULES) == len(mw.KEYWORD_RULES)
    for (phrase, pattern, score, rtype, fuzzy), rule in zip(mw._COMPILED_RULES, mw.KEYWORD_RULES):
        assert phrase == str(rule["phrase"])
        assert score == int(rule["score"])
        assert rtype == str(rule["type"])


def test_product_type_compiled_match_keywords():
    assert len(mw._PRODUCT_TYPE_COMPILED) == len(mw.PRODUCT_TYPE_KEYWORDS)
    for (ptype, patterns), (ptype2, words) in zip(mw._PRODUCT_TYPE_COMPILED, mw.PRODUCT_TYPE_KEYWORDS):
        assert ptype == ptype2
        assert len(patterns) == len(words)


def test_detect_signals_still_scores():
    score, phrases, types = mw.detect_signals("Berserk Deluxe Edition hardcover limited")
    assert score > 0
    assert types  # detectó algo


# ---------------------------------------------------------------------------
# A12 / S10 — lock inter-proceso con 2 procesos reales
# ---------------------------------------------------------------------------

def _rmw_worker(target_str: str, tag: str, k: int, use_lock: bool, barrier):
    """Read-modify-write con ventana de carrera de 0.25s. Corre en OTRO proceso.

    El barrier va ANTES de tomar el lock (adentro se auto-bloquearía: el 2º
    proceso no llegaría nunca al barrier). Con lock, ambos arrancan a la vez y el
    flock serializa el read-modify-write. Sin lock, ambos leen el MISMO estado."""
    import sys as _sys
    _sys.path.insert(0, str(ROOT))
    _sys.path.insert(0, str(ROOT / "scripts"))
    import manga_watch as _mw
    target = Path(target_str)

    def _do():
        lines = target.read_text().splitlines() if target.exists() else []
        time.sleep(0.25)        # ensancha la ventana de carrera
        lines = lines + [f"{tag}-{i}" for i in range(k)]
        tmp = target.with_suffix(".tmp." + tag)
        tmp.write_text("\n".join(lines) + "\n")
        tmp.replace(target)

    barrier.wait()  # sincroniza el ARRANQUE (fuera del lock)
    if use_lock:
        with _mw.items_write_lock(target):
            _do()
    else:
        _do()


@pytest.mark.skipif(mw.fcntl is None, reason="fcntl no disponible")
def test_lock_prevents_lost_update_two_processes(tmp_path):
    mgr = mp.Manager()
    barrier = mgr.Barrier(2)
    target = tmp_path / "shared_lock.txt"
    n_initial, k = 3, 5
    target.write_text("\n".join(f"init-{i}" for i in range(n_initial)) + "\n")
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=_rmw_worker, args=(str(target), tag, k, True, barrier))
             for tag in ("A", "B")]
    for p in procs:
        p.start()
    for p in procs:
        p.join(30)
    lines = [l for l in target.read_text().splitlines() if l.strip()]
    # Con lock: sin lost update → init + A*k + B*k
    assert len(lines) == n_initial + 2 * k, f"con lock esperaba {n_initial+2*k}, hubo {len(lines)}"
    assert sum(1 for l in lines if l.startswith("A-")) == k
    assert sum(1 for l in lines if l.startswith("B-")) == k


@pytest.mark.skipif(mw.fcntl is None, reason="fcntl no disponible")
def test_no_lock_reproduces_lost_update_two_processes(tmp_path):
    mgr = mp.Manager()
    barrier = mgr.Barrier(2)
    target = tmp_path / "shared_nolock.txt"
    n_initial, k = 3, 5
    target.write_text("\n".join(f"init-{i}" for i in range(n_initial)) + "\n")
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=_rmw_worker, args=(str(target), tag, k, False, barrier))
             for tag in ("A", "B")]
    for p in procs:
        p.start()
    for p in procs:
        p.join(30)
    lines = [l for l in target.read_text().splitlines() if l.strip()]
    # Sin lock: ambos leyeron el mismo estado inicial y el último write gana →
    # se pierde el aporte de uno → MENOS de init + 2k líneas.
    assert len(lines) < n_initial + 2 * k, f"sin lock esperaba lost update, hubo {len(lines)}"


def test_items_write_lock_reentrant_same_thread(tmp_path):
    """append_jsonl (que toma el lock) llama a write_items_atomic (que también lo
    toma) sin auto-bloquearse."""
    target = tmp_path / "c.jsonl"
    target.write_text(json.dumps(_row("http://x/1"), sort_keys=True) + "\n")
    with mw.items_write_lock(target):
        with mw.items_write_lock(target):  # reentrante
            mw.write_items_atomic(target, [_row("http://x/1"), _row("http://x/2")])
    assert {json.loads(l)["url"] for l in target.read_text().splitlines() if l.strip()} == {"http://x/1", "http://x/2"}


# ---------------------------------------------------------------------------
# Punto 5 — gate del logging de unmapped
# ---------------------------------------------------------------------------

def test_unmapped_logging_off_by_default_no_write(tmp_path, monkeypatch):
    import series_aliases as sa
    d = tmp_path / "d"
    d.mkdir()
    monkeypatch.setenv("MANGA_WATCH_DATA_DIR", str(d))
    sa.set_unmapped_logging(False)  # explícito (conftest ya lo apaga)
    sa.reset_unmapped_run_state()
    sa.log_unmapped_series("some-brand-new-series-abc", "X", "X 1", "http://x", "src")
    assert not (d / "unmapped_series.jsonl").exists()


def test_unmapped_logging_on_writes(tmp_path, monkeypatch):
    import series_aliases as sa
    d = tmp_path / "d"
    d.mkdir()
    monkeypatch.setenv("MANGA_WATCH_DATA_DIR", str(d))
    sa.set_unmapped_logging(True)
    sa.reset_unmapped_run_state()
    sa.log_unmapped_series("some-brand-new-series-abc", "X", "X 1", "http://x", "src")
    target = d / "unmapped_series.jsonl"
    assert target.exists()
    assert len(target.read_text().strip().splitlines()) == 1


def test_candidate_to_json_read_mode_no_unmapped(tmp_path, monkeypatch):
    """Derivar una fila con serie NO canónica en modo lectura (default) NO toca
    el archivo."""
    import series_aliases as sa
    d = tmp_path / "d"
    d.mkdir()
    monkeypatch.setenv("MANGA_WATCH_DATA_DIR", str(d))
    sa.set_unmapped_logging(False)
    sa.reset_unmapped_run_state()
    c = mw.Candidate(
        title="Zzz Totally Unknown Xyz Vol 1", url="http://x/u1", source="JP - Store",
        source_url="http://x", country="Japón", language="Japonés",
        publisher="KADOKAWA", source_class="official", tags=[], description="d",
    )
    mw.candidate_to_json(c)
    assert not (d / "unmapped_series.jsonl").exists()


# ---------------------------------------------------------------------------
# B18 — Playwright final_url (unit, sin browser)
# ---------------------------------------------------------------------------

def test_playwright_metadata_uses_open_page_url():
    """Regresión B18(c): final_url debe leerse mientras la page está abierta.
    Usamos un fake page/context para ejercitar _fetch_with_playwright_impl."""
    class FakeResp:
        status = 200

    class FakePage:
        def __init__(self):
            self._closed = False
            self.url = "http://final/redirected"
        def goto(self, *a, **k):
            return FakeResp()
        def title(self):
            return "ok"
        def wait_for_timeout(self, *a, **k):
            pass
        def wait_for_function(self, *a, **k):
            pass
        def evaluate(self, *a, **k):
            pass
        def content(self):
            return "<html>ok</html>"
        def close(self):
            self._closed = True
        def is_closed(self):
            return self._closed

    class FakeContext:
        def __init__(self, page):
            self._page = page
        def add_init_script(self, *a, **k):
            pass
        def new_page(self):
            return self._page
        def close(self):
            pass

    class FakeBrowser:
        def new_context(self, *a, **k):
            return FakeContext(FakePage())

    html, meta = mw._fetch_with_playwright_impl(FakeBrowser(), "http://start", 5000, "domcontentloaded")
    assert html == "<html>ok</html>"
    # final_url refleja el redirect (page.url leído ANTES del close), no el original.
    assert meta["final_url"] == "http://final/redirected"
