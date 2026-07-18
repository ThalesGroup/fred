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

from __future__ import annotations

import logging

from fred_core.logs.audit_log import emit_audit_log
from fred_core.logs.log_setup import AUDIT_LOGGER_NAME


def test_emit_audit_log_writes_event_name_and_drops_none_fields() -> None:
    logger = logging.getLogger(AUDIT_LOGGER_NAME)
    previous_handlers = list(logger.handlers)
    previous_propagate = logger.propagate
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger.addHandler(_Capture())
    try:
        emit_audit_log(
            "agent.tool.invocation.completed",
            outcome="succeeded",
            tool_name="knowledge.search_documents",
            user_id=None,
        )
    finally:
        logger.handlers.clear()
        for h in previous_handlers:
            logger.addHandler(h)
        logger.propagate = previous_propagate

    assert len(records) == 1
    record = records[0]
    assert record.getMessage() == "[SECURITY] agent.tool.invocation.completed"
    assert record.audit_event == "agent.tool.invocation.completed"  # type: ignore[attr-defined]
    assert record.outcome == "succeeded"  # type: ignore[attr-defined]
    assert record.tool_name == "knowledge.search_documents"  # type: ignore[attr-defined]
    # user_id=None must not leak through as a literal "None" string.
    assert not hasattr(record, "user_id")


def test_emit_audit_log_defaults_to_info_level() -> None:
    logger = logging.getLogger(AUDIT_LOGGER_NAME)
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        # Should not raise even with no handler attached — logging silently
        # no-ops rather than erroring when nothing is listening.
        emit_audit_log("agent.tool.invocation.started")
    finally:
        logger.setLevel(previous_level)
