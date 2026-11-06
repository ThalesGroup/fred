# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""One event, one expected output: Rust checks the same file in fred-rust-sdk's logging."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fred_core.logs.context import RESERVED_FIELDS, SENSITIVE_FIELDS, log_context
from fred_core.logs.log_setup import log_setup

CONTRACT = json.loads((Path(__file__).parent / "log_contract.json").read_text())


def _emit() -> None:
    with log_context(correlation_id="correlation-1"):
        logging.getLogger("contract.event").warning(
            "Contract event",
            extra={
                "operation_id": "operation-1",
                "error_code": "contract_failed",
                "attempt": 3,
                "done": False,
                "token": "SENTINEL",  # nosec B105
                "email": "SENTINEL",
                "severity": "SENTINEL",
            },
        )


def test_reserved_and_sensitive_lists_match_rust() -> None:
    assert RESERVED_FIELDS == set(CONTRACT["reserved_fields"])
    assert SENSITIVE_FIELDS == set(CONTRACT["sensitive_fields"])


def test_json_line_matches_the_contract(capsys: pytest.CaptureFixture[str]) -> None:
    log_setup(
        service_name="contract-service",
        service_role="api",
        log_format="json",
        include_uvicorn=False,
    )
    _emit()
    event = json.loads(capsys.readouterr().out)
    stamp = event.pop("timestamp")
    assert isinstance(stamp["seconds"], int) and isinstance(stamp["nanos"], int)
    source = event.pop("logging.googleapis.com/sourceLocation")
    assert isinstance(source["file"], str) and isinstance(source["line"], str)
    assert isinstance(source["function"], str)
    assert isinstance(event.pop("process"), int)
    assert isinstance(event.pop("thread"), str)
    # Python only: the asyncio task has no Rust counterpart.
    assert isinstance(event.pop("task_name"), str)
    assert event == CONTRACT["event"]


def test_text_line_matches_the_contract(capsys: pytest.CaptureFixture[str]) -> None:
    log_setup(
        service_name="contract-service",
        service_role="api",
        log_format="text",
        use_rich=False,
        include_uvicorn=False,
    )
    _emit()
    _, line = capsys.readouterr().out.strip().split(" ", 1)
    assert line.startswith(CONTRACT["text"]["line"])
    detail = line.removeprefix(CONTRACT["text"]["line"]).split()
    assert sorted(detail) == CONTRACT["text"]["fields"]


@pytest.mark.parametrize(
    ("service", "role"),
    [
        ("knowledge-flow", "api"),
        ("knowledge-flow", "worker"),
        ("fred-agents", "api"),
        ("fred-agents", "worker"),
        ("fred-runtime", "migration"),
    ],
)
def test_every_python_process_writes_the_same_fields(
    capsys: pytest.CaptureFixture[str], service: str, role: str
) -> None:
    log_setup(
        service_name=service,
        service_role=role,
        log_format="json",
        include_uvicorn=False,
    )
    _emit()
    line = capsys.readouterr().out
    # Shown by `pytest -rP`.
    print(line)
    event = json.loads(line)
    assert (event["service"], event["service_role"]) == (service, role)
    assert {key for key in CONTRACT["event"]} - {"service", "service_role"} <= set(
        event
    )
