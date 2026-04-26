from __future__ import annotations

from fastapi import FastAPI, Request

from control_plane_backend.app.container import ControlPlaneContainer
from control_plane_backend.config.models import Configuration

_CONTAINER_STATE_KEY = "control_plane_container"


def attach_application_container(
    app: FastAPI,
    container: ControlPlaneContainer,
) -> None:
    """
    Attach the control-plane container to FastAPI application state.

    Why this function exists:
    - Slice 1 starts moving dependency resolution toward explicit app wiring
      instead of hidden globals
    - storing the container on `app.state` lets future route dependencies fetch
      collaborators directly from the request/application state

    How to use it:
    - call once during FastAPI startup immediately after creating the app
    - use `get_application_container(...)` in request-scoped dependencies later

    Example:
    - `attach_application_container(app, container)`
    """
    setattr(app.state, _CONTAINER_STATE_KEY, container)


def get_application_container_from_app(app: FastAPI) -> ControlPlaneContainer:
    """
    Resolve the control-plane container from a FastAPI application instance.

    Why this function exists:
    - application bootstrap and tests sometimes need the shared container
      outside a request context
    - keeping the lookup in one helper avoids duplicating the state-key logic

    How to use it:
    - pass the already-created FastAPI app
    - expect a `RuntimeError` if startup forgot to attach the container

    Example:
    - `container = get_application_container_from_app(app)`
    """
    container = getattr(app.state, _CONTAINER_STATE_KEY, None)
    if container is None:
        raise RuntimeError(
            "Control-plane container is not attached to the FastAPI application."
        )
    return container


def get_application_container(request: Request) -> ControlPlaneContainer:
    """
    Resolve the control-plane container from the current FastAPI request.

    Why this function exists:
    - future DI-based route handlers should fetch collaborators from request
      state instead of using global singleton access

    How to use it:
    - declare it in FastAPI dependencies that receive a `Request`
    - use the returned container to access shared stores and configuration

    Example:
    - `container = get_application_container(request)`
    """
    return get_application_container_from_app(request.app)


def get_application_configuration(request: Request) -> Configuration:
    """
    Return the control-plane configuration from the request-bound container.

    Why this function exists:
    - some request-scoped dependencies only need typed configuration, not the
      full container
    - this keeps configuration lookup aligned with the new explicit container
      storage on `app.state`

    How to use it:
    - declare it as a FastAPI dependency for request-scoped helpers
    - prefer it when only configuration is needed

    Example:
    - `configuration = get_application_configuration(request)`
    """
    return get_application_container(request).configuration
