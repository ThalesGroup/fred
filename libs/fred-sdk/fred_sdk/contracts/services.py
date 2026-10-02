# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Deployment service addresses supplied to SDK catalog loaders at startup."""

from enum import StrEnum
from typing import Protocol


class FredService(StrEnum):
    """Fred backends with an outbound address in pod configuration."""

    KNOWLEDGE_FLOW = "knowledge_flow"
    CONTROL_PLANE = "control_plane"


class ServiceEndpointsPort(Protocol):
    """Resolve configured addresses without importing runtime configuration."""

    def get_base_url(self, service: FredService) -> str:
        """Return an HTTP(S) base URL including port and API prefix, without query/fragment.

        Raise ValueError when the requested service is unconfigured or invalid.
        """
        ...
