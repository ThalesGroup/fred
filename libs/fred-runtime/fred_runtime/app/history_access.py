# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Fresh private-history authorization, separate from execution turn authority."""

import re
from uuid import UUID

import httpx
from fastapi import HTTPException
from fred_core.security.delegation import AssertedUser, holds_caller_role
from fred_core.security.structure import KeycloakUser, is_service_agent
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError

from fred_runtime.common.outbound_credentials import static_person_provider
from fred_runtime.runtime_context import get_runtime_context


class _Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    subject_id: str
    space_id: str
    instance_id: str
    template_id: str
    runtime_id: str


def require_history_person(
    caller: KeycloakUser | AssertedUser | None, authorization: str | None
) -> KeycloakUser:
    # M5a is an own-person API, not the resolver's delegated receiver.
    if (
        not isinstance(caller, KeycloakUser)
        or not caller.uid
        or caller.service_account
        or is_service_agent(caller)
        or holds_caller_role(caller)
        or not authorization
    ):
        raise HTTPException(status_code=403, detail="Person credential required")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Person credential required")
    return caller


def _unavailable() -> HTTPException:
    # Unknown, foreign, revoked and unbound conversations have one public error.
    return HTTPException(
        status_code=404,
        detail="Conversation unavailable",
        headers={"Cache-Control": "no-store"},
    )


async def authorize_history_read(
    session_id: str,
    caller: KeycloakUser | AssertedUser | None,
    authorization: str | None,
) -> KeycloakUser:
    """Check persisted placement and M5a ownership/Read before loading content."""
    person = require_history_person(caller, authorization)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise _unavailable()
    runtime = get_runtime_context().config
    if (
        runtime.checkpointer is None
        or runtime.history_store is None
        or not runtime.control_plane_url
        or runtime.control_plane_http_client is None
        or not runtime.service_name
    ):
        raise HTTPException(status_code=503, detail="History access unavailable")
    # This reads provenance only, without creating/adopting an association.
    try:
        raw = await runtime.checkpointer.aget_conversation_binding(session_id)
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503, detail="History storage unavailable"
        ) from None
    if raw is None:
        raise _unavailable()
    try:
        binding = _Provenance.model_validate(raw)
        space = str(UUID(binding.space_id))
        UUID(binding.instance_id)
        UUID(binding.template_id)
    except ValueError:
        raise _unavailable() from None
    if binding.subject_id != person.uid or binding.runtime_id != runtime.service_name:
        raise _unavailable()
    token = (authorization or "").partition(" ")[2].strip()
    credentials = await static_person_provider(token).credentials()
    try:
        response = await runtime.control_plane_http_client.get(
            f"{runtime.control_plane_url.rstrip('/')}/spaces/{space}/sessions/{session_id}",
            headers={"Authorization": credentials.authorization},
            auth=None,
            follow_redirects=False,
        )
        if response.status_code == 401:
            raise HTTPException(status_code=401, detail="Person credential rejected")
        if response.status_code in (403, 404):
            raise _unavailable()
        if response.status_code != 200:
            raise HTTPException(status_code=503, detail="History authority unavailable")
        metadata = response.json()
        if not isinstance(metadata, dict):
            raise ValueError("Invalid session metadata")
        expected = {
            "session_id": session_id,
            "space_id": binding.space_id,
            "agent_instance_id": binding.instance_id,
            "template_id": binding.template_id,
            "runtime_id": binding.runtime_id,
        }
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise _unavailable()
        # SessionDetails has no subject field: M5a's owned query binds it to
        # the same authenticated person compared with the pod provenance above.
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            status_code=503, detail="History authority unavailable"
        ) from None

    return person


async def readable_history_sessions(
    session_ids: list[str],
    caller: KeycloakUser | None,
    authorization: str | None,
) -> list[str]:
    """Filter refusals only; credential and infrastructure failures abort the list."""
    require_history_person(caller, authorization)
    readable = []
    # Bound pressure on the shared CP pool; do not cache decisions across requests.
    for session_id in session_ids:
        try:
            await authorize_history_read(session_id, caller, authorization)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
        else:
            readable.append(session_id)
    return readable
