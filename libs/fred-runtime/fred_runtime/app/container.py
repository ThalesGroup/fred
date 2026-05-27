"""Pod container factory — single composition-root entry point."""

from __future__ import annotations

from fred_runtime.app.config import AgentPodConfig
from fred_runtime.app.context import PodApplicationContext

PodContainer = PodApplicationContext


def build_pod_container(configuration: AgentPodConfig) -> PodContainer:
    """Create a fresh PodApplicationContext with no side effects."""
    return PodApplicationContext(configuration)
