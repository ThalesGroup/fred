# Copyright Thales 2026

from __future__ import annotations

import threading
import weakref
from concurrent.futures import ThreadPoolExecutor

import pytest
from fred_capability_ppt_filler import concurrency


@pytest.mark.parametrize("chained", [False, True])
def test_worker_collects_cycles_on_success_and_failure(chained: bool) -> None:
    class Cyclic:
        def __init__(self) -> None:
            self.self = self

    refs: list[weakref.ReferenceType[Cyclic]] = []

    def create_cycle(fail: bool) -> str:
        value = Cyclic()
        refs.append(weakref.ref(value))
        if fail:
            raise ValueError("invalid deck")
        return "schema"

    def operation(fail: bool) -> str:
        try:
            return create_cycle(fail)
        except ValueError as exc:
            if chained:
                raise RuntimeError("invalid deck") from exc
            raise

    assert concurrency.run_heavy_ppt_job(operation, False) == "schema"
    assert refs[-1]() is None
    with pytest.raises((ValueError, RuntimeError), match="invalid deck"):
        concurrency.run_heavy_ppt_job(operation, True)
    assert refs[-1]() is None


def test_four_concurrent_workers_keep_the_existing_bound() -> None:
    started = threading.Barrier(concurrency.MAX_CONCURRENT_HEAVY_JOBS + 1)
    finish = threading.Event()

    def operation() -> None:
        started.wait(timeout=5)
        assert finish.wait(timeout=5)

    with ThreadPoolExecutor(max_workers=concurrency.MAX_CONCURRENT_HEAVY_JOBS) as pool:
        jobs = []
        try:
            for _ in range(concurrency.MAX_CONCURRENT_HEAVY_JOBS):
                assert concurrency.acquire_heavy_job_slot()
                jobs.append(pool.submit(concurrency.run_heavy_ppt_job, operation))
            started.wait(timeout=5)
            assert not concurrency.acquire_heavy_job_slot()
        finally:
            finish.set()
            for job in jobs:
                job.result(timeout=5)
                concurrency.release_heavy_job_slot()
    assert concurrency._active_jobs == 0
