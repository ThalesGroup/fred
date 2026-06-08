from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from fred_core.session.stores import BaseSessionStore

    from control_plane_backend.app.container import ControlPlaneContainer
    from control_plane_backend.scheduler.queue_store import PurgeQueueStore


@dataclass(slots=True)
class LifecycleActionDependencies:
    """
    Bundle the collaborators required by lifecycle purge actions.

    Why this type exists:
    - Slice 4 moves lifecycle action code away from direct singleton access
    - grouping the stores keeps the action contract explicit for memory mode,
      Temporal activities, and offline tests

    How to use it:
    - build it from the application container or temporary compatibility shim
    - pass it to lifecycle action functions when running them explicitly

    Example:
    - `deps = build_lifecycle_action_dependencies(container)`
    """

    get_session_store: Callable[[], BaseSessionStore]
    get_purge_queue_store: Callable[[], PurgeQueueStore]


def build_lifecycle_action_dependencies(
    container: ControlPlaneContainer,
) -> LifecycleActionDependencies:
    """
    Build explicit lifecycle-action collaborators from the application container.

    Why this function exists:
    - lifecycle actions need only two stores, so their dependency seam should
      stay tiny and obvious
    - centralizing the wiring keeps action code free of container lookups

    How to use it:
    - call from in-memory runners or other explicit lifecycle entrypoints
    - reuse it from temporary compatibility bridges until Slice 5 removes them

    Example:
    - `deps = build_lifecycle_action_dependencies(container)`
    """
    return LifecycleActionDependencies(
        get_session_store=container.get_session_store,
        get_purge_queue_store=container.get_purge_queue_store,
    )
