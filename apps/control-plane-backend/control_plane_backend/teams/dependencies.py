from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable, TypeAlias

from fastapi import Request
from fred_core import (
    BaseSessionStore,
    KeycloackDisabled,
    RebacEngine,
    create_keycloak_admin,
)
from fred_core.scheduler import SchedulerBackend
from fred_core.store import ContentStore
from fred_core.teams.metadata_store import TeamMetadataStore
from keycloak import KeycloakAdmin

from control_plane_backend.app.container import ControlPlaneContainer
from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.config.models import Configuration
from control_plane_backend.scheduler.dependencies import (
    build_lifecycle_action_dependencies,
)
from control_plane_backend.scheduler.memory import run_lifecycle_manager_once_in_memory
from control_plane_backend.scheduler.policies.policy_models import (
    ConversationPolicyCatalog,
)
from control_plane_backend.scheduler.queue_store import PurgeQueueStore
from control_plane_backend.scheduler.temporal.structures import (
    LifecycleManagerInput,
    LifecycleManagerResult,
)
from control_plane_backend.users.dependencies import build_user_service_dependencies
from control_plane_backend.users.schemas import UserSummary
from control_plane_backend.users.service import get_users_by_ids

UserSummaryLookup: TypeAlias = Callable[
    [Iterable[str]],
    Awaitable[dict[str, UserSummary]],
]
LifecycleRunner: TypeAlias = Callable[
    [LifecycleManagerInput],
    Awaitable[LifecycleManagerResult],
]
KeycloakAdminFactory: TypeAlias = Callable[[], KeycloakAdmin | KeycloackDisabled]


@dataclass(slots=True)
class TeamServiceDependencies:
    """
    Bundle the collaborators required by team business operations.

    Why this type exists:
    - Slice 2 moves `teams/` away from hidden singleton lookups and toward
      explicit dependency injection
    - grouping the collaborators keeps route handlers and compatibility shims
      small while making the team service contract visible

    How to use it:
    - build it from the app container in FastAPI dependencies
    - pass it to `control_plane_backend.teams.service` functions

    Example:
    - `deps = build_team_service_dependencies(container)`
    """

    configuration: Configuration
    rebac: RebacEngine
    scheduler_backend: SchedulerBackend
    create_keycloak_admin_client: KeycloakAdminFactory
    get_team_metadata_store: Callable[[], TeamMetadataStore]
    get_content_store: Callable[[], ContentStore]
    get_session_store: Callable[[], BaseSessionStore]
    get_purge_queue_store: Callable[[], PurgeQueueStore]
    get_policy_catalog: Callable[[], ConversationPolicyCatalog]
    get_users_by_ids: UserSummaryLookup
    run_lifecycle_manager_once_in_memory: LifecycleRunner


def build_team_service_dependencies(
    container: ControlPlaneContainer,
    *,
    user_summary_lookup: UserSummaryLookup | None = None,
    lifecycle_runner: LifecycleRunner | None = None,
) -> TeamServiceDependencies:
    """
    Build explicit team-service collaborators from the application container.

    Why this function exists:
    - `teams/` now receives collaborators explicitly, but Slice 2 still needs a
      compact way to derive them from the startup container
    - this keeps app wiring centralized while avoiding new global lookups inside
      the team service module

    How to use it:
    - call from FastAPI dependencies or temporary compatibility bridges
    - pass custom lookup/runner callables in tests when a lighter fake is useful

    Example:
    - `deps = build_team_service_dependencies(container)`
    """
    if user_summary_lookup is None:
        user_deps = build_user_service_dependencies(container)

        async def _lookup_users_by_ids(
            user_ids: Iterable[str],
        ) -> dict[str, UserSummary]:
            """
            Resolve user summaries with the container-bound user dependencies.

            Why this function exists:
            - team enrichment needs user display data, but Slice 5 removes the
              old implicit fallback from `users/service.py`

            How to use it:
            - call with the set of user ids to resolve
            - the closure captures the user dependency bundle built from the
              same application container

            Example:
            - `summaries = await _lookup_users_by_ids({"user-1"})`
            """
            return await get_users_by_ids(user_ids, user_deps)

        user_summary_lookup = _lookup_users_by_ids

    if lifecycle_runner is None:
        lifecycle_deps = build_lifecycle_action_dependencies(container)

        async def _run_in_memory_lifecycle(
            input_data: LifecycleManagerInput,
        ) -> LifecycleManagerResult:
            """
            Run the in-memory lifecycle manager with explicit action dependencies.

            Why this function exists:
            - team membership removal may trigger lifecycle cleanup in memory
              mode, and that path should use explicit store wiring

            How to use it:
            - pass a lifecycle-manager input payload
            - the closure captures the lifecycle-action dependencies built from
              the application container

            Example:
            - `result = await _run_in_memory_lifecycle(input_data)`
            """
            return await run_lifecycle_manager_once_in_memory(
                input_data,
                deps=lifecycle_deps,
            )

        lifecycle_runner = _run_in_memory_lifecycle

    return TeamServiceDependencies(
        configuration=container.configuration,
        rebac=container.get_rebac_engine(),
        scheduler_backend=container.get_scheduler_backend(),
        create_keycloak_admin_client=lambda: create_keycloak_admin(
            container.configuration.security.m2m
        ),
        get_team_metadata_store=container.get_team_metadata_store,
        get_content_store=container.get_content_store,
        get_session_store=container.get_session_store,
        get_purge_queue_store=container.get_purge_queue_store,
        get_policy_catalog=container.get_policy_catalog,
        get_users_by_ids=user_summary_lookup,
        run_lifecycle_manager_once_in_memory=lifecycle_runner,
    )


def get_team_service_dependencies(request: Request) -> TeamServiceDependencies:
    """
    Resolve request-scoped team-service collaborators from FastAPI state.

    Why this function exists:
    - team routes should consume explicit dependencies from the app container
      instead of reaching into singletons from inside business code

    How to use it:
    - declare it with `Depends(...)` in team-related route handlers
    - pass the returned bundle to team service functions

    Example:
    - `deps: TeamServiceDependencies = Depends(get_team_service_dependencies)`
    """
    return build_team_service_dependencies(get_application_container(request))
