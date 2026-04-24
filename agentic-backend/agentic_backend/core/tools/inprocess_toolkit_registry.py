from __future__ import annotations

from typing import Callable, Optional

from langchain_core.tools import BaseTool

from agentic_backend.common.kf_base_client import KnowledgeFlowAgentContext
from agentic_backend.integrations.kf_vector_search.kf_vector_search_params import (
    KF_VECTOR_SEARCH_PROVIDER,
)
from agentic_backend.integrations.kf_vector_search.kf_vector_search_tools import (
    build_kf_vector_search_tools,
)
from agentic_backend.integrations.web_github_readonly import (
    build_web_github_readonly_tools,
)


class UnknownInprocessToolkitProvider(ValueError):
    """Raised when an unknown local toolkit provider key is requested."""


InprocessToolkitFactory = Callable[[KnowledgeFlowAgentContext], list[BaseTool]]

_INPROCESS_TOOLKIT_FACTORIES: dict[str, InprocessToolkitFactory] = {
    "web_github_readonly": build_web_github_readonly_tools,
    KF_VECTOR_SEARCH_PROVIDER: build_kf_vector_search_tools,
}


def normalize_inprocess_provider(provider: str | None) -> str:
    if not provider or not provider.strip():
        raise UnknownInprocessToolkitProvider(
            "Missing inprocess provider. Set MCP server field 'provider' (e.g. 'web_github_readonly')."
        )
    return provider.strip().lower()


def create_inprocess_tools(
    provider: str | None, agent: Optional[KnowledgeFlowAgentContext] = None
) -> list[BaseTool]:
    key = normalize_inprocess_provider(provider)
    factory = _INPROCESS_TOOLKIT_FACTORIES.get(key)
    if not factory:
        known = ", ".join(sorted(_INPROCESS_TOOLKIT_FACTORIES))
        raise UnknownInprocessToolkitProvider(
            f"Unknown inprocess toolkit provider '{key}'. Known providers: {known or 'none'}."
        )
    if agent is None:
        raise UnknownInprocessToolkitProvider(
            f"Inprocess toolkit provider '{key}' requires an agent context."
        )
    return factory(agent)


def list_inprocess_toolkit_providers() -> list[str]:
    return sorted(_INPROCESS_TOOLKIT_FACTORIES.keys())
