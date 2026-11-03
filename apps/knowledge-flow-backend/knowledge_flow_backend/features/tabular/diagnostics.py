"""Closed tabular failure reasons and metadata-only resolution summaries."""

from __future__ import annotations

import logging
from typing import Literal

DescriptionFailureReason = Literal["datasets_not_resolved", "preview_not_ready", "preview_artifact_unavailable"]
logger = logging.getLogger(__name__)


class TabularDescriptionNotFound(FileNotFoundError):
    """Preserve the HTTP/message contract with a reason determined at its source."""

    def __init__(self, message: str, *, reason: DescriptionFailureReason) -> None:
        super().__init__(message)
        self.reason = reason


def log_description_failure(error: TabularDescriptionNotFound) -> None:
    logger.warning("tabular.description_failure", extra={"reason": error.reason})
