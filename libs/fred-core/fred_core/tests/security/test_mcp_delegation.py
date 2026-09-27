"""The grant's journey from a tool mount into the route that serves the call.

Everything here decides which person a tool call acts for, so each rule is
pinned on its own rather than left to whichever copy happened to be read.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from fastapi import HTTPException, Request

from fred_core.security import mcp_delegation, oidc
from fred_core.security.delegation import AssertedUser, DelegationGrant

GRANT = DelegationGrant(person="a-person", run="a-run", agent="an-agent")


def _a_request() -> Request:
    """A stand-in: the mount only hands it to grant resolution."""
    return cast(Request, object())


async def _drain(dependency: Any) -> Any:
    """Run a yielding dependency to completion and return what it yielded."""
    agen = dependency
    value = await agen.__anext__()
    with pytest.raises(StopAsyncIteration):
        await agen.__anext__()
    return value


@pytest.mark.asyncio
async def test_a_tool_mount_refuses_a_request_carrying_no_bearer() -> None:
    """The bearer scheme does not fail on its own, so without this an
    unauthenticated request reaches token decoding as an empty value."""
    with pytest.raises(HTTPException) as refused:
        await _drain(
            mcp_delegation.mcp_mount_auth(
                request=_a_request(),
                token="",  # nosec B106 - the absence under test
            )
        )

    assert refused.value.status_code == 401


@pytest.mark.asyncio
async def test_a_grant_reaches_the_mount_from_the_endpoint_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The body of a tool mount is the tool call, which the model influences.

    Reading a grant from there would let a caller name a person through content
    it partly controls, so only the endpoint is read.
    """
    seen: dict[str, Any] = {}

    async def fake_resolve(request: Any, caller: Any, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return caller

    monkeypatch.setattr(oidc, "decode_jwt", lambda token: object())
    monkeypatch.setattr(oidc, "resolve_request_principal", fake_resolve)

    mount = mcp_delegation.mcp_mount_auth(
        request=_a_request(),
        token="a-bearer",  # nosec B106 - synthetic fixture
    )
    await _drain(mount)

    assert seen.get("query_only") is True


@pytest.mark.asyncio
async def test_the_verified_grant_is_visible_only_while_its_call_is_served(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two calls must never observe each other's grant."""
    asserted = AssertedUser(
        uid=GRANT.person, client_id="a-caller", run_id=GRANT.run, agent_id=GRANT.agent
    )

    async def fake_resolve(request: Any, caller: Any, **kwargs: Any) -> Any:
        return asserted

    monkeypatch.setattr(oidc, "decode_jwt", lambda token: object())
    monkeypatch.setattr(oidc, "resolve_request_principal", fake_resolve)

    assert mcp_delegation.verified_grant() is None
    agen = mcp_delegation.mcp_mount_auth(request=_a_request(), token="a-bearer")  # nosec B106
    await agen.__anext__()
    during = mcp_delegation.verified_grant()
    with pytest.raises(StopAsyncIteration):
        await agen.__anext__()

    assert during is not None and during.person == GRANT.person
    # Released once the call it belonged to is finished.
    assert mcp_delegation.verified_grant() is None


def test_a_verified_grant_is_placed_on_the_inner_call() -> None:
    reset = mcp_delegation._verified_grant.set(GRANT)
    try:
        sent = mcp_delegation.apply_verified_grant({"a_tool_argument": "kept"})
    finally:
        mcp_delegation._verified_grant.reset(reset)

    assert sent["person"] == GRANT.person
    assert sent["run"] == GRANT.run
    assert sent["agent"] == GRANT.agent
    assert sent["a_tool_argument"] == "kept"


def test_a_grant_invented_by_the_model_never_survives() -> None:
    """Tool arguments are model-controlled, so one naming a person is a forgery
    attempt: it is dropped, and the verified grant replaces it."""
    reset = mcp_delegation._verified_grant.set(GRANT)
    try:
        sent = mcp_delegation.apply_verified_grant(
            {"person": "someone-else", "run": "x", "agent": "y"}
        )
    finally:
        mcp_delegation._verified_grant.reset(reset)

    assert sent["person"] == GRANT.person


def test_an_undelegated_call_names_nobody() -> None:
    sent = mcp_delegation.apply_verified_grant({"person": "someone-else", "k": "v"})

    assert "person" not in sent and "run" not in sent and "agent" not in sent
    assert sent["k"] == "v"


def test_the_model_never_sees_the_grant_in_a_tool_schema() -> None:
    class _Tool:
        def __init__(self) -> None:
            self.inputSchema = {
                "properties": {
                    "a_real_argument": {},
                    "person": {},
                    "run": {},
                    "agent": {},
                },
                "required": ["a_real_argument", "person"],
            }

    class _Mcp:
        def __init__(self) -> None:
            self.tools = [_Tool()]

    stripped = mcp_delegation.strip_grant_tool_fields(_Mcp())

    schema = stripped.tools[0].inputSchema
    assert set(schema["properties"]) == {"a_real_argument"}
    assert schema["required"] == ["a_real_argument"]


def test_the_bridge_needs_no_tool_server_package() -> None:
    """A service that mounts no tools must not be made to install one."""
    import importlib.util

    assert importlib.util.find_spec("fastapi_mcp") is None
    # Everything above this line ran without it.
    assert mcp_delegation.apply_verified_grant({"k": "v"}) == {"k": "v"}


def test_a_missing_tool_server_package_names_the_extra() -> None:
    with pytest.raises(ImportError) as missing:
        import fred_core.security.mcp_delegation_fastapi  # noqa: F401

    assert "'mcp' extra" in str(missing.value)


@pytest.mark.asyncio
async def test_two_calls_never_observe_each_others_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The grant is per-call state; a shared one would act for the wrong person."""

    async def fake_resolve(request: Any, caller: Any, **kwargs: Any) -> Any:
        return caller

    monkeypatch.setattr(oidc, "resolve_request_principal", fake_resolve)

    async def one_call(person: str) -> str | None:
        monkeypatch.setattr(
            oidc,
            "decode_jwt",
            lambda token: AssertedUser(
                uid=person, client_id="a-caller", run_id="a-run", agent_id="an-agent"
            ),
        )
        agen = mcp_delegation.mcp_mount_auth(
            request=_a_request(),
            token="a-bearer",  # nosec B106 - synthetic fixture
        )
        await agen.__anext__()
        await asyncio.sleep(0)  # let the other call interleave here
        seen = mcp_delegation.verified_grant()
        with pytest.raises(StopAsyncIteration):
            await agen.__anext__()
        return seen.person if seen else None

    first, second = await asyncio.gather(one_call("person-a"), one_call("person-b"))

    assert {first, second} == {"person-a", "person-b"}
    assert mcp_delegation.verified_grant() is None


def test_a_route_declares_the_grant_parameters_once() -> None:
    """The parameters must appear on the route, which is what lets a tool mount
    place them on the inner request; a route without them is unaffected."""
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.get(
        "/declared",
        dependencies=[Depends(mcp_delegation.declare_delegation_parameters)],
    )
    async def declared() -> dict[str, str]:
        return {"reached": "yes"}

    @app.get("/undeclared")
    async def undeclared() -> dict[str, str]:
        return {"reached": "yes"}

    client = TestClient(app)
    grant = {"person": "a-person", "run": "a-run", "agent": "an-agent"}

    assert client.get("/declared", params=grant).status_code == 200
    assert client.get("/declared").status_code == 200
    assert client.get("/undeclared", params=grant).status_code == 200

    declared_params = {
        p["name"]
        for p in app.openapi()["paths"]["/declared"]["get"].get("parameters", [])
    }
    undeclared_params = {
        p["name"]
        for p in app.openapi()["paths"]["/undeclared"]["get"].get("parameters", [])
    }
    assert {"person", "run", "agent"} <= declared_params
    assert not ({"person", "run", "agent"} & undeclared_params)
