from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from temporalio import activity, workflow

_OWNED_ACTIVITY_TYPES = frozenset(
    {
        "fred.execute_background_agent_run.v1",
        "fred.create_scheduled_agent_run_occurrence.v1",
    }
)
_OWNED_WORKFLOW_TYPES = frozenset(
    {
        "fred.agent_run.v1",
        "fred.scheduled_agent_run.v1",
    }
)
_TEMPORAL_CONTEXT_FIELDS = (
    "temporal_activity",
    "temporal_workflow",
    "activity_info",
    "workflow_info",
)


class _BackgroundTemporalLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        activity_details = getattr(record, "temporal_activity", None)
        workflow_details = getattr(record, "temporal_workflow", None)
        if not (
            _is_owned(activity_details, "activity_type", _OWNED_ACTIVITY_TYPES)
            or _is_owned(activity_details, "workflow_type", _OWNED_WORKFLOW_TYPES)
            or _is_owned(workflow_details, "workflow_type", _OWNED_WORKFLOW_TYPES)
        ):
            return True

        record.msg = "Background agent run Temporal event"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        for field in _TEMPORAL_CONTEXT_FIELDS:
            record.__dict__.pop(field, None)
        return True


def _is_owned(value: Any, key: str, owned: frozenset[str]) -> bool:
    return isinstance(value, Mapping) and value.get(key) in owned


def _reachable_handlers(*loggers: logging.Logger) -> set[logging.Handler]:
    handlers: set[logging.Handler] = set()
    for logger in loggers:
        current: logging.Logger | None = logger
        while current is not None:
            handlers.update(current.handlers)
            if not current.propagate:
                break
            current = current.parent
    return handlers


@contextmanager
def confine_background_temporal_logs() -> Iterator[None]:
    """Remove identifiers and exception payloads from this worker's Temporal logs."""

    activity_logger = activity.logger.base_logger
    workflow_logger = workflow.logger.base_logger
    log_filter = _BackgroundTemporalLogFilter()
    handlers = _reachable_handlers(activity_logger, workflow_logger)

    # Logger filters cover the SDK's two adapters even when logging has no
    # configured handler yet. Handler filters cover records routed through a
    # shared handler after the adapters have appended Temporal context.
    activity_logger.addFilter(log_filter)
    workflow_logger.addFilter(log_filter)
    for handler in handlers:
        handler.addFilter(log_filter)
    try:
        yield
    finally:
        for handler in handlers:
            handler.removeFilter(log_filter)
        workflow_logger.removeFilter(log_filter)
        activity_logger.removeFilter(log_filter)
