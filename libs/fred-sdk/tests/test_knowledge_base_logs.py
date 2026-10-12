# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A pod's log line names the pod, so it joins the metric it explains."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import replace
from threading import Event

import pytest
from fred_sdk.knowledge_base import KnowledgeBase, worker
from fred_sdk.knowledge_base.configuration import PodConfiguration
from fred_sdk.knowledge_base.logs import (
    LogFormat,
    configure_logging,
    hold_until_configured,
    release_unconfigured,
)
from pydantic import ValidationError
from temporalio.runtime import LoggingConfig, Runtime, TelemetryConfig


@pytest.fixture(autouse=True)
def _restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    root.setLevel(logging.INFO)
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)


def _lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return [line for line in capsys.readouterr().out.splitlines() if line]


def test_a_json_line_carries_the_pod_and_the_definition(capsys):
    configure_logging(
        service="webdav-kb", knowledge_base="fred.samples.webdav", log_format="json"
    )

    logging.getLogger("acme.sync").info("wrote %d documents", 3)

    [line] = _lines(capsys)
    record = json.loads(line)
    assert record["service"] == "webdav-kb"
    assert record["knowledge_base"] == "fred.samples.webdav"
    assert record["msg"] == "wrote 3 documents"
    assert record["level"] == "INFO"
    assert record["logger"] == "acme.sync"
    assert isinstance(record["ts"], float)


def test_an_exception_stays_inside_its_one_line(capsys):
    configure_logging(service="webdav-kb", knowledge_base="k.b", log_format="json")

    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("acme").exception("run failed")

    [line] = _lines(capsys)
    assert "ValueError: boom" in json.loads(line)["exc"]


def test_text_keeps_the_runtime_id_on_every_line(capsys):
    configure_logging(service="webdav-kb", knowledge_base="k.b", log_format="text")

    logging.getLogger("acme").warning("slow share")

    [line] = _lines(capsys)
    assert "| webdav-kb |" in line
    assert line.endswith("slow share")


def test_earlier_handlers_write_no_unattributed_copy(capsys):
    logging.getLogger().addHandler(logging.StreamHandler())
    configure_logging(service="webdav-kb", knowledge_base="k.b", log_format="json")

    logging.getLogger("acme").info("once")

    assert len(_lines(capsys)) == 1
    assert capsys.readouterr().err == ""


def _payload(**observability: object) -> dict[str, object]:
    return {
        "app": {"runtime_id": "acme-kb"},
        "knowledge_base": {
            "prefix": "acme.kb",
            "control_plane_url": "http://example.invalid/control-plane/v1",
        },
        "security": {
            "m2m": {
                "realm_url": "http://keycloak.invalid/realms/app",
                "client_id": "kb",
                "secret_env_var": "ACME_KB_CLIENT_SECRET",  # pragma: allowlist secret
            }
        },
        "observability": observability,
    }


def test_logs_default_to_json_and_refuse_an_unknown_format():
    assert (
        PodConfiguration.model_validate(_payload()).observability.logs.format == "json"
    )
    with pytest.raises(ValidationError, match="format"):
        PodConfiguration.model_validate(_payload(logs={"format": "xml"}))


def test_lines_logged_while_the_configuration_loads_are_written_as_the_pod(capsys):
    """The first lines of a pod are JSON with its service, like every other."""
    hold_until_configured()
    logging.getLogger("fred_pod.config").info("Loaded configuration from: %s", "x.yaml")
    assert _lines(capsys) == []

    configure_logging(service="webdav-kb", knowledge_base="k.b", log_format="json")

    [line] = _lines(capsys)
    record = json.loads(line)
    assert record["service"] == "webdav-kb"
    assert record["msg"] == "Loaded configuration from: x.yaml"


def test_a_configuration_that_cannot_load_still_shows_why(capsys):
    hold_until_configured()
    logging.getLogger("fred_pod.config").error("No configuration at %s", "x.yaml")

    release_unconfigured()

    captured = capsys.readouterr()
    assert "No configuration at x.yaml" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("metrics_enabled", [False, True])
@pytest.mark.parametrize("log_format", ["json", "text"])
def test_native_engine_logs_use_the_pod_output(
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    metrics_enabled: bool,
    log_format: LogFormat,
) -> None:
    def runtime_with_test_filter(*, telemetry: TelemetryConfig) -> Runtime:
        assert telemetry.logging is not None
        assert telemetry.logging.filter == LoggingConfig.default.filter
        # The native test hook emits INFO. Change only its filter; exercise the
        # worker's actual forwarding configuration and the real Rust bridge.
        return Runtime(
            telemetry=replace(
                telemetry, logging=replace(telemetry.logging, filter="INFO")
            )
        )

    monkeypatch.setattr(worker, "Runtime", runtime_with_test_filter)
    configure_logging(
        service="acme-kb", knowledge_base="acme.kb.runtime", log_format=log_format
    )
    received = Event()
    records: list[logging.LogRecord] = []

    class NativeRecords(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if hasattr(record, "temporal_log"):
                records.append(record)
                received.set()

    # Runs after the stdout handler: the event means the line has been flushed.
    logging.getLogger().addHandler(NativeRecords())
    runtime = worker.build_runtime(
        KnowledgeBase(
            id="acme.kb.runtime", version="1.0.0", name="R", description="Runtime"
        ),
        PodConfiguration.model_validate(
            _payload(temporal={"prometheus": {"enabled": metrics_enabled, "port": 0}})
        ),
    )
    capfd.readouterr()  # Discard the optional exporter startup log.
    runtime._core_runtime.write_test_debug_log("filtered debug", "test-only")
    runtime._core_runtime.write_test_info_log("native engine message", "test-only")
    assert received.wait(timeout=5), "Native log was not forwarded to Python"

    captured = capfd.readouterr()
    assert captured.err == ""
    [line] = captured.out.splitlines()
    [record] = records
    assert record.levelno == logging.INFO
    assert record.created == getattr(record, "temporal_log").time
    assert "temporal_sdk_bridge" in record.name
    if log_format == "json":
        data = json.loads(line)
        assert data["service"] == "acme-kb"
        assert data["knowledge_base"] == "acme.kb.runtime"
        assert data["level"] == "INFO"
        assert data["ts"] == record.created
        assert data["logger"] == record.name
        assert data["msg"].startswith("native engine message")
    else:
        assert "| acme-kb |" in line
        assert "native engine message" in line
