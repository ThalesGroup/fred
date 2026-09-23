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

from fred_core.security.models import (
    AuthorizationError,
    Resource,
    StandingAuthorizationError,
)

logger = logging.getLogger(__name__)

_TEAM_PERMISSION_MESSAGES: dict[str, str] = {
    "can_update_resources": "You are not allowed to manage resources in this team. Ask a team admin or editor.",
    "can_update_agents": "You are not allowed to manage agents in this team. Ask a team admin or editor.",
    "can_administer_members": "You are not allowed to manage members in this team.",
    "can_administer_editors": "You are not allowed to manage editors in this team.",
    "can_administer_analysts": "You are not allowed to manage analysts in this team.",
    "can_administer_admins": "You are not allowed to manage admins in this team.",
    "can_read_members": "You are not allowed to view team members.",
    "can_update_info": "You are not allowed to update this team.",
}


# Standing decides whether a person may act at all, so a refusal on it belongs
# beside the delegation decisions on the same audit surface.
AUDIT_STANDING_REFUSED = "authorization.standing.refused"

# Bounded on purpose: the caller learns the cause is its own account standing,
# never who was denied, which team was consulted, or what exists.
_STANDING_REFUSED_DETAIL = (
    "Your account standing does not currently permit this request."
)
_STANDING_UNAVAILABLE_DETAIL = (
    "Account standing could not be checked. Try again shortly."
)


def _humanize_action(action: str) -> str:
    return action.replace(":", " ").replace("_", " ")


def _denial_cause(exc: AuthorizationError) -> str:
    if isinstance(exc, StandingAuthorizationError):
        return "standing_unavailable" if exc.unavailable else "standing_refused"
    return "permission_refused"


def _denial_fields(exc: AuthorizationError) -> dict[str, object]:
    """Types and actions only: enough to tell the causes apart, never who."""
    cause = _denial_cause(exc)
    return {
        "denial_cause": cause,
        "decision_reached": cause != "standing_unavailable",
        "subject_type": exc.subject_type.value if exc.subject_type else "unspecified",
        "action": str(exc.action),
        "resource_type": exc.resource.value,
    }


def _authorization_detail_for_client(exc: AuthorizationError) -> str:
    if isinstance(exc, StandingAuthorizationError):
        return (
            _STANDING_UNAVAILABLE_DETAIL
            if exc.unavailable
            else _STANDING_REFUSED_DETAIL
        )

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
        """Report a denial, preserving whether a decision was actually reached."""
        logger.warning("Authorization denied", extra=_denial_fields(exc))
        if isinstance(exc, StandingAuthorizationError):
            # Imported here: the logging package reaches back into this one,
            # so a module-level import closes a cycle at startup.
            from fred_core.logs.audit_log import emit_audit_log

            emit_audit_log(
                AUDIT_STANDING_REFUSED,
                "warning",
                outcome="refused",
                reason=(
                    "standing_unavailable" if exc.unavailable else "standing_not_active"
                ),
            )
            if exc.unavailable:
                # The dependency never decided, so this is an outage, not a
                # statement about the caller.
                return JSONResponse(
                    status_code=503,
                    content={"detail": _authorization_detail_for_client(exc)},
                )
        return JSONResponse(
            status_code=403,
            content={"detail": _authorization_detail_for_client(exc)},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle all unhandled exceptions by logging and returning 500."""
        logger.error("Unhandled request failure")
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )
