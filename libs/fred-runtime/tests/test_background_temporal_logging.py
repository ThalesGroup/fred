from __future__ import annotations

import logging
from dataclasses import replace

from fred_runtime.background.temporal_logging import confine_background_temporal_logs
from temporalio import activity
from temporalio.testing import ActivityEnvironment


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.format(record)
        self.records.append(record)


def _emit_from_real_activity_adapter(activity_type: str) -> logging.LogRecord:
    environment = ActivityEnvironment()
    environment.info = replace(
        environment.info,
        activity_id="SYNTHETIC-ACTIVITY-ID-CANARY",
        activity_type=activity_type,
        workflow_id="SYNTHETIC-WORKFLOW-ID-CANARY",
        workflow_run_id="SYNTHETIC-RUN-ID-CANARY",
        workflow_type="fred.agent_run.v1"
        if activity_type.startswith("fred.")
        else "other.workflow",
    )

    def emit() -> None:
        try:
            raise RuntimeError("SYNTHETIC-EXCEPTION-CANARY")
        except RuntimeError:
            activity.logger.warning("SYNTHETIC-MESSAGE-CANARY", exc_info=True)

    environment.run(emit)
    return _HANDLER.records[-1]


_HANDLER = _Records()


def test_owned_temporal_activity_log_removes_metadata_and_exception_payload() -> None:
    logger = activity.logger.base_logger
    old_level = logger.level
    logger.setLevel(logging.WARNING)
    logger.addHandler(_HANDLER)
    _HANDLER.records.clear()
    try:
        with confine_background_temporal_logs():
            record = _emit_from_real_activity_adapter(
                "fred.execute_background_agent_run.v1"
            )
    finally:
        logger.removeHandler(_HANDLER)
        logger.setLevel(old_level)

    rendered = _HANDLER.format(record)
    payload = repr(record.__dict__)
    assert rendered == "Background agent run Temporal event"
    assert "CANARY" not in rendered
    assert "CANARY" not in payload
    assert record.exc_info is None
    assert not hasattr(record, "temporal_activity")


def test_unrelated_temporal_activity_log_is_unchanged() -> None:
    logger = activity.logger.base_logger
    old_level = logger.level
    logger.setLevel(logging.WARNING)
    logger.addHandler(_HANDLER)
    _HANDLER.records.clear()
    try:
        with confine_background_temporal_logs():
            record = _emit_from_real_activity_adapter("other.activity")
    finally:
        logger.removeHandler(_HANDLER)
        logger.setLevel(old_level)

    assert "SYNTHETIC-MESSAGE-CANARY" in record.getMessage()
    assert record.exc_info is not None
    details = getattr(record, "temporal_activity")
    assert details["activity_id"] == "SYNTHETIC-ACTIVITY-ID-CANARY"
