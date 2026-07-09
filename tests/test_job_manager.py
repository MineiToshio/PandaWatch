"""Tests de scripts/job_manager.py (Fable audit B17, 2026-07-08).

Job/JobManager estaban duplicadas byte-a-byte en scripts/serve.py y
scripts/admin_serve.py; este módulo las extrajo a una fuente única. Cobertura:

  1. import compartido: serve.py y admin_serve.py usan la MISMA clase (no
     dos copias que puedan volver a divergir).
  2. arranca un job inocuo (echo), lo deja terminar y valida status/exit_code/
     líneas capturadas + el prefijo de log inyectado (log_prefix).
  3. block_if_mutator: dos jobs "mutadores" no pueden arrancar en simultáneo
     bajo el mismo JobManager — el segundo vuelve como blocker (S10).
  4. stop() manda SIGTERM a un proceso long-running y lo marca no-running.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from job_manager import Job, JobManager  # noqa: E402


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_serve_and_admin_serve_share_the_same_job_classes():
    """Regresión directa de B17: ambos servers deben apuntar a la MISMA clase,
    no a dos copias que puedan volver a desincronizarse."""
    import admin_serve
    import serve

    assert serve.Job is Job
    assert admin_serve.Job is Job
    assert serve.JobManager is JobManager
    assert admin_serve.JobManager is JobManager
    assert isinstance(serve.JOBS, JobManager)
    assert isinstance(admin_serve.JOBS, JobManager)
    # Instancias separadas (cada server tiene su propio registro de jobs).
    assert serve.JOBS is not admin_serve.JOBS


def test_start_runs_an_inocuous_job_and_captures_output():
    jm = JobManager(log_prefix="test")
    job, blocker = jm.start(
        "echo-job",
        ["/bin/echo", "hola"],
        "echo de prueba",
        cwd=ROOT,
    )
    assert blocker is None
    assert job is not None

    assert _wait_until(lambda: job.status != "running"), (
        f"job no terminó a tiempo (status={job.status})"
    )
    assert job.status == "exited"
    assert job.exit_code == 0
    # Línea de PID inyectada por el manager con el log_prefix configurado.
    assert any(line.startswith("[test] PID ") for line in job.lines)
    assert any("hola" in line for line in job.lines)

    # to_dict expone lo mínimo por default y las líneas sólo si se piden.
    summary = job.to_dict()
    assert "lines" not in summary
    assert summary["status"] == "exited"
    full = job.to_dict(include_lines=True)
    assert "hola" in full["lines"][-1] or any("hola" in ln for ln in full["lines"])


def test_get_and_list_reflect_started_jobs():
    jm = JobManager(log_prefix="test")
    job, _ = jm.start("echo-job", ["/bin/echo", "x"], "x", cwd=ROOT)
    assert _wait_until(lambda: job.status != "running")

    assert jm.get(job.id) is job
    assert jm.get("no-existe") is None
    assert job in jm.list()


def test_block_if_mutator_prevents_concurrent_mutators():
    """S10: dos POST /api/run casi simultáneos para scripts "mutadores" no
    pueden colarse los dos — el segundo debe volver como (None, blocker)."""
    jm = JobManager(
        log_prefix="test",
        mutates_items=lambda script_id: script_id == "mutator-script",
    )
    job1, blocker1 = jm.start(
        "mutator-script",
        # long-running a propósito: el primero debe seguir "running" cuando
        # llega el segundo start().
        ["/bin/sleep", "5"],
        "mutador 1",
        cwd=ROOT,
        block_if_mutator=True,
    )
    assert blocker1 is None
    assert job1 is not None
    assert job1.status == "running"

    job2, blocker2 = jm.start(
        "mutator-script",
        ["/bin/echo", "no debería arrancar"],
        "mutador 2",
        cwd=ROOT,
        block_if_mutator=True,
    )
    assert job2 is None
    assert blocker2 is job1

    # running_mutator() ve el primero como el mutador activo.
    assert jm.running_mutator() is job1

    jm.stop(job1.id)
    assert _wait_until(lambda: job1.status != "running")


def test_non_mutator_scripts_ignore_the_block():
    jm = JobManager(log_prefix="test", mutates_items=lambda script_id: False)
    job1, blocker1 = jm.start(
        "readonly-script", ["/bin/sleep", "2"], "job1", cwd=ROOT,
        block_if_mutator=True,
    )
    job2, blocker2 = jm.start(
        "readonly-script", ["/bin/echo", "ok"], "job2", cwd=ROOT,
        block_if_mutator=True,
    )
    assert blocker1 is None and blocker2 is None
    assert job1 is not None and job2 is not None
    jm.stop(job1.id)
    assert _wait_until(lambda: job1.status != "running")
    assert _wait_until(lambda: job2.status != "running")


def test_stop_terminates_a_long_running_job():
    jm = JobManager(log_prefix="test")
    job, _ = jm.start("sleep-job", ["/bin/sleep", "30"], "sleep largo", cwd=ROOT)
    assert job is not None
    assert job.status == "running"

    ok = jm.stop(job.id)
    assert ok is True
    assert _wait_until(lambda: job.status != "running", timeout=8.0)
    assert job.status in ("exited", "error", "killed")
    assert any("SIGTERM enviado" in line for line in job.lines)


def test_stop_on_unknown_or_already_finished_job_returns_false():
    jm = JobManager(log_prefix="test")
    assert jm.stop("no-existe") is False

    job, _ = jm.start("echo-job", ["/bin/echo", "x"], "x", cwd=ROOT)
    assert _wait_until(lambda: job.status != "running")
    assert jm.stop(job.id) is False


def test_max_finished_jobs_trims_old_finished_jobs():
    jm = JobManager(log_prefix="test", max_finished_jobs=2)
    jobs = []
    for _ in range(4):
        job, _ = jm.start("echo-job", ["/bin/echo", "x"], "x", cwd=ROOT)
        assert _wait_until(lambda j=job: j.status != "running")
        jobs.append(job)

    # Sólo deben sobrevivir los 2 más recientes ya terminados.
    remaining_ids = {j.id for j in jm.list()}
    assert jobs[-1].id in remaining_ids
    assert jobs[-2].id in remaining_ids
    assert jobs[0].id not in remaining_ids


def test_max_buffered_lines_caps_the_deque():
    job = Job("s", "label", ["cmd"], max_buffered_lines=3)
    for i in range(10):
        job.append(f"line {i}")
    assert len(job.lines) == 3
    assert list(job.lines) == ["line 7", "line 8", "line 9"]
