from __future__ import annotations

from typing import Any, Callable

from agentic_backend.integrations.web_github_readonly import WebGithubReadonlyTools


class UnknownInprocessToolkitProvider(ValueError):
    """Raised when an unknown local toolkit provider key is requested."""


_INPROCESS_TOOLKIT_FACTORIES: dict[str, Callable[[], Any]] = {
    "web_github_readonly": WebGithubReadonlyTools,
}


def normalize_inprocess_provider(provider: str | None) -> str:
    if not provider or not provider.strip():
        raise UnknownInprocessToolkitProvider(
            "Missing inprocess provider. Set MCP server field 'provider' (e.g. 'web_github_readonly')."
        )
    return provider.strip().lower()


def create_inprocess_toolkit(provider: str | None) -> Any:
    key = normalize_inprocess_provider(provider)
    factory = _INPROCESS_TOOLKIT_FACTORIES.get(key)
    if not factory:
        known = ", ".join(sorted(_INPROCESS_TOOLKIT_FACTORIES))
        raise UnknownInprocessToolkitProvider(
            f"Unknown inprocess toolkit provider '{key}'. Known providers: {known or 'none'}."
        )
    return factory()


def list_inprocess_toolkit_providers() -> list[str]:
    return sorted(_INPROCESS_TOOLKIT_FACTORIES.keys())
