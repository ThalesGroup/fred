from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable, TypeAlias

if TYPE_CHECKING:
    from fred_core.session.stores import BaseSessionStore

    from control_plane_backend.app.container import ControlPlaneContainer
    from control_plane_backend.scheduler.queue_store import PurgeQueueStore
    from control_plane_backend.sessions.erasure_service import ErasureReceipt

# Erase one conversation across every store and return its receipt (CTRLP-12 E1).
# Kept as a callable on the deps bundle so the scheduler layer never imports the
# product/erasure modules at import time (that would cycle:
# scheduler.dependencies → product.dependencies → teams.dependencies →
# scheduler.dependencies). The concrete binding is built lazily below.
EraseSessionFn: TypeAlias = Callable[..., Awaitable["ErasureReceipt"]]
ServiceBearerFn: TypeAlias = Callable[[], Awaitable[str]]


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
    # CTRLP-12 E1: server-initiated erase at window expiry + the service bearer it
    # authenticates with. Provided as callables so this bundle stays free of the
    # product/erasure imports (see the cycle note above).
    erase_session: EraseSessionFn
    get_service_bearer: ServiceBearerFn


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
    # Lazy imports: importing these at module scope would cycle back through
    # teams.dependencies into this module (see the EraseSessionFn note above).
    from control_plane_backend.product.dependencies import (
        build_product_service_dependencies,
    )
    from control_plane_backend.sessions.erasure_service import (
        ConversationErasureService,
    )

    async def _erase_session(**kwargs: Any) -> ErasureReceipt:
        product_deps = build_product_service_dependencies(container)
        return await ConversationErasureService(product_deps).erase_session(**kwargs)

    return LifecycleActionDependencies(
        get_session_store=container.get_session_store,
        get_purge_queue_store=container.get_purge_queue_store,
        erase_session=_erase_session,
        get_service_bearer=container.get_service_bearer,
    )
