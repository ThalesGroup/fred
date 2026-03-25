# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from fred_core.security.models import AuthorizationError, Resource

logger = logging.getLogger(__name__)

_TEAM_PERMISSION_MESSAGES: dict[str, str] = {
    "can_update_resources": "You are not allowed to manage resources in this team. Ask a team owner or manager.",
    "can_update_agents": "You are not allowed to manage agents in this team. Ask a team owner or manager.",
    "can_administer_members": "You are not allowed to manage members in this team.",
    "can_administer_managers": "You are not allowed to manage managers in this team.",
    "can_administer_owners": "You are not allowed to manage owners in this team.",
    "can_read_members": "You are not allowed to view team members.",
    "can_update_info": "You are not allowed to update this team.",
}


def _humanize_action(action: str) -> str:
    return action.replace(":", " ").replace("_", " ")


def _authorization_detail_for_client(exc: AuthorizationError) -> str:
    action = str(exc.action)
    if exc.resource == Resource.TEAM and action in _TEAM_PERMISSION_MESSAGES:
        return _TEAM_PERMISSION_MESSAGES[action]

    readable_action = _humanize_action(action)
    readable_resource = exc.resource.value.replace("_", " ")
    return f"You are not allowed to {readable_action} {readable_resource}."


def register_exception_handlers(app: FastAPI) -> None:
    """Register authorization and generic exception handlers for FastAPI application."""

    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(
        request: Request, exc: AuthorizationError
    ) -> JSONResponse:
        """Handle AuthorizationError by returning a 403 Forbidden response."""
        logger.warning(f"Authorization denied for user {exc.user_id}: {exc}")
        return JSONResponse(
            status_code=403,
            content={"detail": _authorization_detail_for_client(exc)},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle all unhandled exceptions by logging and returning 500."""
        logger.error(
            f"Unhandled exception in {request.method} {request.url}: {exc}",
            exc_info=True,
        )
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )
