# app/core/runtime_source.py
# Contains the registry and decorator for exposing runtime source code.

from typing import Callable, TypeVar

# Global registry for objects that opt-in to source exposure
_RUNTIME_SOURCE_REGISTRY: dict[str, object] = {}

F = TypeVar("F", bound=Callable)


def expose_runtime_source(key: str):
    """
    Decorator for agents/components to opt-in their source exposure.
    Usage (in any module):
        @expose_runtime_source("slide_maker.fill_placeholder")
        def fill_placeholder(...): ...
    """

    def _wrap(obj: F) -> F:
        """Adds the decorated object to the global source registry."""
        # Use an absolute key to ensure uniqueness
        _RUNTIME_SOURCE_REGISTRY[key] = obj
        return obj

    return _wrap


# Getter function for the registry (used by the API endpoint)
def get_runtime_source_registry() -> dict[str, object]:
    """Returns the dictionary of objects registered for source exposure."""
    return _RUNTIME_SOURCE_REGISTRY
