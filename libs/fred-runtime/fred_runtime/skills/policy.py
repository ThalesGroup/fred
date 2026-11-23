# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Trusted direct-turn activation policy and versioned skill metadata projection."""

import httpx
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fred_core.common.fastapi_handlers import (
    ACCOUNT_STATUS_UNAVAILABLE_CAUSE,
    DENIAL_CAUSE_HEADER,
)
from fred_core.logs.propagation import outbound_context_headers
from fred_core.security.backend_to_backend_auth import M2MBearerAuth
from fred_sdk.contracts.skills import SkillCatalog, SkillDetail, SkillInvocation
from pydantic import BaseModel, ConfigDict, ValidationError

from fred_runtime.common.outbound_credentials import (
    DelegatedCredentialProvider,
    OutboundCredentialProvider,
    static_person_provider,
)
from fred_runtime.runtime_support.authority import DelegationUnavailableError


class _SkillPolicy(BaseModel):
    """Validate the names-only control-plane response before it reaches a runtime view."""

    model_config = ConfigDict(extra="forbid")

    disabled_skill_names: tuple[str, ...]


async def resolve_direct_skill_policy(
    *,
    control_plane_url: str | None,
    http_client: httpx.AsyncClient,
    access_token: str | None,
    credentials: OutboundCredentialProvider | None = None,
    request_id: str | None = None,
) -> tuple[str, ...]:
    """Read fresh policy once before direct execution; standalone runtimes use no opt-outs.

    Pass the pod's shared control-plane client and the authenticated execution's
    credential provider. A configured but unreachable platform fails closed.
    """
    if control_plane_url is None:
        return ()
    provider = credentials or static_person_provider(access_token)
    try:
        call_credentials = await provider.credentials()
        headers = {"X-Fred-Skill-Policy": "1"}
        if call_credentials.authorization:
            headers["Authorization"] = call_credentials.authorization
        if call_credentials.delegated:
            headers.update(outbound_context_headers())
        if request_id:
            headers["X-Request-Id"] = request_id
        auth = (
            M2MBearerAuth(provider)
            if isinstance(provider, DelegatedCredentialProvider)
            else None
        )
        response = await http_client.get(
            f"{control_plane_url.rstrip('/')}/platform/skills/policy",
            headers=headers,
            params=dict(call_credentials.parameters) or None,
            auth=auth,
            timeout=10.0,
            follow_redirects=False,
        )
    except (httpx.HTTPError, DelegationUnavailableError):
        raise HTTPException(
            status_code=503, detail="Platform skill policy unavailable"
        ) from None
    if response.status_code in {401, 403}:
        raise HTTPException(
            status_code=403, detail="Platform skill policy access denied"
        )
    if response.status_code != 200:
        extra_headers = (
            {DENIAL_CAUSE_HEADER: ACCOUNT_STATUS_UNAVAILABLE_CAUSE}
            if response.status_code == 503
            and response.headers.get(DENIAL_CAUSE_HEADER)
            == ACCOUNT_STATUS_UNAVAILABLE_CAUSE
            else None
        )
        raise HTTPException(
            status_code=503,
            detail="Platform skill policy unavailable",
            headers=extra_headers,
        )
    try:
        policy = _SkillPolicy.model_validate(response.json())
        names = {
            SkillInvocation(name=name).name for name in policy.disabled_skill_names
        }
    except (ValidationError, ValueError):
        raise HTTPException(
            status_code=503, detail="Invalid platform skill policy"
        ) from None
    return tuple(sorted(names))


def legacy_skill_metadata_response(
    value: SkillCatalog | SkillDetail, *, metadata_version: int = 0
) -> JSONResponse:
    """Preserve strict legacy clients unless they request skill metadata version 1."""
    if metadata_version == 1:
        return JSONResponse(value.model_dump(mode="json"))
    fields = {"builtin", "user_invocable", "disable_model_invocation"}
    if isinstance(value, SkillCatalog):
        payload = value.model_dump(
            mode="json",
            exclude={"policy_supported": True, "skills": {"__all__": fields}},
        )
    else:
        payload = value.model_dump(mode="json", exclude={"skill": fields})
    return JSONResponse(payload)
