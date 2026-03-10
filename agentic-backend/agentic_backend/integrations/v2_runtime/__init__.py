"""
Fred integration adapters for v2 runtime contracts.

This package intentionally depends on application context and external services.
Core v2 contracts remain in `agentic_backend.core.agents.v2`.
"""

from .adapters import (
    CompositeToolInvoker,
    DefaultFredChatModelFactory,
    FredArtifactPublisher,
    FredKnowledgeSearchToolInvoker,
    FredMcpToolProvider,
    FredResourceReader,
    InProcessToolInvoker,
    build_langfuse_tracer,
)

__all__ = [
    "CompositeToolInvoker",
    "DefaultFredChatModelFactory",
    "FredArtifactPublisher",
    "FredKnowledgeSearchToolInvoker",
    "FredMcpToolProvider",
    "FredResourceReader",
    "InProcessToolInvoker",
    "build_langfuse_tracer",
]
