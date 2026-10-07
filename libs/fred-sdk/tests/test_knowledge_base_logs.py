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

import pytest
from fred_sdk.knowledge_base.configuration import PodConfiguration
from fred_sdk.knowledge_base.logs import configure_logging
from pydantic import ValidationError


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
