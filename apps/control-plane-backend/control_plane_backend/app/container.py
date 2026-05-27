from __future__ import annotations

from typing import TypeAlias

from fred_core.users.store.postgres_user_store import init_user_store

from control_plane_backend.app.context import ApplicationContext
from control_plane_backend.config.models import Configuration

ControlPlaneContainer: TypeAlias = ApplicationContext


def build_application_container(configuration: Configuration) -> ControlPlaneContainer:
    """
    Create the control-plane dependency container used at startup.

    Why this function exists:
    - API and worker bootstrap need one stable composition-root entrypoint for
      constructing the shared control-plane container
    - keeping the factory in one helper makes startup wiring boring and explicit

    How to use it:
    - call once during API or worker startup
    - keep the returned container alive for the whole process lifetime

    Example:
    - `container = build_application_container(configuration)`
    """
    return ApplicationContext(configuration)


def initialize_shared_stores(container: ControlPlaneContainer) -> None:
    """
    Register shared Fred store singletons from explicit startup wiring.

    Why this function exists:
    - `fred_core` user-security dependencies expect `init_user_store()` to run
      during application startup
    - keeping this registration in one bootstrap helper removes the previous
      hidden constructor side effect from `ApplicationContext`

    How to use it:
    - call after `build_application_container(...)`
    - call once per process before serving requests or handling worker jobs

    Example:
    - `initialize_shared_stores(container)`
    """
    init_user_store(container.get_pg_async_engine())
