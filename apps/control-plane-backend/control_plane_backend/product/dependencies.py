from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import Request
from fred_core.kpi.base_kpi_writer import BaseKPIWriter

from control_plane_backend.agent_instances.store import AgentInstanceStore
from control_plane_backend.app.container import ControlPlaneContainer
from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.config.models import Configuration
from control_plane_backend.prompts.store import PromptStore
from control_plane_backend.sessions.attachment_store import SessionAttachmentStore
from control_plane_backend.sessions.store import SessionMetadataStore
from control_plane_backend.teams.dependencies import (
    TeamServiceDependencies,
    build_team_service_dependencies,
)


@dataclass(slots=True)
class ProductServiceDependencies:
    """
    Bundle the collaborators required by product/session control-plane operations.

    Why this type exists:
    - Slice 3 moves `product/` away from hidden singleton lookups and toward
      explicit dependency injection
    - grouping the collaborators keeps route handlers small while making the
      product service contract visible and testable

    How to use it:
    - build it from the application container in FastAPI dependencies
    - pass it to `control_plane_backend.product.service` functions

    Example:
    - `deps = build_product_service_dependencies(container)`
    """

    configuration: Configuration
    team_dependencies: TeamServiceDependencies
    get_agent_instance_store: Callable[[], AgentInstanceStore]
    get_session_metadata_store: Callable[[], SessionMetadataStore]
    get_session_attachment_store: Callable[[], SessionAttachmentStore]
    get_prompt_store: Callable[[], PromptStore]
    get_kpi_writer: Callable[[], BaseKPIWriter]


def build_product_service_dependencies(
    container: ControlPlaneContainer,
) -> ProductServiceDependencies:
    """
    Build explicit product-service collaborators from the application container.

    Why this function exists:
    - `product/` still relies on shared stores and `teams/` resolution, but
      Slice 3 needs those dependencies to be visible instead of global
    - this helper keeps container-to-service wiring centralized in one place

    How to use it:
    - call from FastAPI dependencies for request-scoped product routes
    - reuse it from compatibility bridges until all legacy callers are migrated

    Example:
    - `deps = build_product_service_dependencies(container)`
    """
    return ProductServiceDependencies(
        configuration=container.configuration,
        team_dependencies=build_team_service_dependencies(container),
        get_agent_instance_store=container.get_agent_instance_store,
        get_session_metadata_store=container.get_session_metadata_store,
        get_session_attachment_store=container.get_session_attachment_store,
        get_prompt_store=container.get_prompt_store,
        get_kpi_writer=container.get_kpi_writer,
    )


def get_product_service_dependencies(request: Request) -> ProductServiceDependencies:
    """
    Resolve request-scoped product-service collaborators from FastAPI state.

    Why this function exists:
    - product routes should consume explicit dependencies from the app container
      instead of relying on hidden globals in business code

    How to use it:
    - declare it with `Depends(...)` in product route handlers
    - pass the returned bundle to product service functions

    Example:
    - `deps: ProductServiceDependencies = Depends(get_product_service_dependencies)`
    """
    return build_product_service_dependencies(get_application_container(request))
