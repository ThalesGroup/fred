"""Closed tabular failure reasons and metadata-only resolution summaries."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from fred_core.logs.context import safe_context

DescriptionFailureReason = Literal["datasets_not_resolved", "preview_not_ready", "preview_artifact_unavailable"]
DiscoveryEmptyReason = Literal["no_readable_documents", "empty_authorized_scope", "no_documents_in_scope", "no_registered_tables"]
logger = logging.getLogger(__name__)


class TabularDescriptionNotFound(FileNotFoundError):
    """Preserve the HTTP/message contract with a reason determined at its source."""

    def __init__(self, message: str, *, reason: DescriptionFailureReason) -> None:
        super().__init__(message)
        self.reason = reason


def log_description_failure(error: TabularDescriptionNotFound) -> None:
    logger.warning("tabular.description_failure", extra={"reason": error.reason})


@dataclass
class ResolutionSummary:
    """Only counts observed during existing lookups, never a global inventory."""

    readable_metadata_count: int = 0
    scoped_metadata_count: int = 0
    resolved_table_count: int = 0
    authorized_scope_empty: bool = False
    scope_applied: bool = False

    def log_empty(self) -> None:
        reason: DiscoveryEmptyReason
        if self.authorized_scope_empty:
            reason = "empty_authorized_scope"
        elif self.readable_metadata_count == 0 and not self.scope_applied:
            reason = "no_readable_documents"
        elif self.scoped_metadata_count == 0:
            reason = "no_documents_in_scope"
        else:
            reason = "no_registered_tables"
        fields = safe_context({"reason": reason, **{name: min(max(0, getattr(self, name)), 2**63 - 1) for name in ("readable_metadata_count", "scoped_metadata_count", "resolved_table_count")}})
        logger.info("tabular.discovery_empty", extra=fields)
