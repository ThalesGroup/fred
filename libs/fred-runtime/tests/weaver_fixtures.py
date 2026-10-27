# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""M4 fixtures. No network, credential provisioning or deployment."""

from collections.abc import Awaitable
from contextlib import contextmanager
from typing import TypeVar

from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    RuntimeContext,
)
from fred_sdk.contracts.weaver import WeaverRuntimeBinding


def resolved_binding(
    *, source="a", default="first", permitted=True, candidate=True, diagnostics=()
):
    key = {"source_id": source, "upstream_model_id": "first"}
    fallback = {"source_id": source, "upstream_model_id": "second"}
    observation = dict(
        source_id=source,
        source_revision=1,
        enabled=True,
        state="ok",
        error_code=None,
        checked_at=None,
        last_success_at=None,
        snapshot_revision=1,
        snapshot_source_revision=1,
    )
    metadata = dict(
        chat=True,
        chat_provenance="source_guarantee",
        display_name=None,
        context_window_tokens=1000,
        max_input_tokens=None,
        max_output_tokens=100,
    )

    def offer(k, allowed, usable, reasons):
        return dict(
            key=k,
            permitted=allowed,
            candidate=usable,
            selectable=usable,
            diagnostics=reasons,
            metadata=metadata,
            observation=observation,
            connection=dict(
                provider="openai",
                api_root=f"https://{source}.invalid/v1",
                credential_binding=source,
            )
            if usable
            else None,
        )

    org = "00000000-0000-0000-0000-000000000001"
    return WeaverRuntimeBinding.model_validate(
        dict(
            subject_id="person",
            run_id="run",
            conversation_id=None,
            space=dict(
                id="00000000-0000-0000-0000-000000000002",
                kind="team",
                organization_id=org,
                team_id="00000000-0000-0000-0000-000000000002",
                project_id=None,
            ),
            agent=dict(
                instance_id="00000000-0000-0000-0000-000000000003",
                runtime_id="pod",
                template_id="00000000-0000-0000-0000-000000000004",
                template_key="template",
                configuration_updated_at="2026-10-26T00:00:00Z",
                configuration={"role": "Assistant", "description": "Example"},
            ),
            models=dict(
                policy=dict(
                    organization_id=org,
                    revision=1,
                    permitted=[key, fallback] if permitted else [fallback],
                    reasoning_enabled=[],
                    default=key if default == "first" else fallback,
                    fallback=fallback,
                    created_by=None,
                    created_at=None,
                    updated_by=None,
                    updated_at=None,
                ),
                recommendation=key,
                options={"max_tokens": 50},
                legacy_profile_id=None,
                requires_reselection=False,
                offers=[
                    offer(key, permitted, candidate, diagnostics),
                    offer(fallback, True, True, ()),
                ],
            ),
        )
    )


SPACE_ID = "00000000-0000-0000-0000-000000000002"
INSTANCE_ID = "00000000-0000-0000-0000-000000000003"


def turn_binding(template, *, user="alice", session=None, run="run", tuning=None):
    """A complete trusted response for a test's registered template."""
    data = resolved_binding().model_dump(mode="json")
    data.update(subject_id=user, conversation_id=session, run_id=run)
    data["agent"].update(template_key=template, runtime_id="test-pod")
    if tuning is not None:
        data["agent"]["configuration"] = tuning
    return WeaverRuntimeBinding.model_validate(data)


def managed_payload(body):
    """Build a managed request for the single instance in create_managed_app."""
    body = dict(body)
    body.pop("agent_id", None)
    body["agent_instance_id"] = INSTANCE_ID
    context = dict(body.get("runtime_context") or {})
    context["space_id"] = SPACE_ID
    context["team_id"] = SPACE_ID
    body["runtime_context"] = context
    return body


def create_managed_app(
    monkeypatch,
    *,
    registry,
    config,
    tuning=None,
    resolver_status=200,
    user_id="alice",
    mock_identity=True,
    binding_transform=None,
    **kwargs,
):
    """Mock identity and Control Plane HTTP, preserving real admission and storage."""
    import httpx
    from conftest import StaticWorkloadTokens, install_delegation_runtime
    from fred_core.security.structure import KeycloakUser
    from fred_runtime.app import agent_app
    from fred_runtime.app.context import PodApplicationContext

    definition = next(iter(registry.values()))
    requests = []

    def resolve(request):
        requests.append(request)
        if "/sessions/" in request.url.path:
            assert request.headers["Authorization"] == "Bearer test-person-token"
            return httpx.Response(
                200,
                json={
                    "session_id": request.url.path.rsplit("/", 1)[-1],
                    "space_id": SPACE_ID,
                    "agent_instance_id": INSTANCE_ID,
                    "template_id": str(
                        turn_binding(definition.agent_id).agent.template_id
                    ),
                    "runtime_id": "test-pod",
                },
            )
        assert request.url.path.endswith(
            f"/spaces/{SPACE_ID}/agent-instances/{INSTANCE_ID}/runtime"
        )
        assert request.headers["Authorization"] == "Bearer workload-token"
        params = dict(request.url.params)
        assert params["person"] == user_id
        assert params["agent"] == INSTANCE_ID
        binding = turn_binding(
            definition.agent_id,
            user=params["person"],
            session=params.get("conversation"),
            run=params["run"],
            tuning=tuning,
        )
        data = binding.model_dump(mode="json")
        if binding_transform is not None:
            binding_transform(data)
        return httpx.Response(resolver_status, json=data)

    def initialize(container):
        container._control_plane_http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(resolve)
        )

    monkeypatch.setattr(
        PodApplicationContext, "initialize_control_plane_client", initialize
    )
    config.platform.control_plane_url = "https://cp.invalid/api"
    user = KeycloakUser(uid=user_id, username=user_id, roles=[])
    if mock_identity:
        monkeypatch.setattr(
            agent_app, "_make_user_dependency", lambda *args: lambda: user
        )
        monkeypatch.setattr(
            agent_app, "_make_execution_dependency", lambda *args: lambda: user
        )
    app = agent_app.create_agent_app(registry=registry, config=config, **kwargs)
    install_delegation_runtime(StaticWorkloadTokens())
    app.state.resolver_requests = requests
    return app


@contextmanager
def active_turn(template, *, user="alice", session=None):
    """Enter a real parent scope for tests of admitted local descendants."""
    from fred_runtime.model_routing.turn import TurnAuthority
    from fred_runtime.runtime_support.run_scope import RunScope

    if isinstance(template, BoundRuntimeContext):
        context = template.portable_context
        assert context.agent_id is not None and context.user_id is not None
        template, user, session = context.agent_id, context.user_id, context.session_id
    with RunScope.open() as scope:
        authority = TurnAuthority(
            turn_binding(template, user=user, session=session), None
        )
        authority.start(scope)
        scope.turn_authority = authority
        yield authority


def invocation_context(**kwargs):
    from fred_sdk.contracts.context import PortableContext

    baggage = {"space_id": SPACE_ID, "agent_instance_id": INSTANCE_ID}
    baggage.update(kwargs.pop("baggage", {}))
    return PortableContext(**{"user_id": "alice", **kwargs}, baggage=baggage)


def conversation_provenance(template="rags.sample.echo"):
    b = turn_binding(template)
    return dict(
        subject_id=b.subject_id,
        space_id=str(b.space.id),
        instance_id=str(b.agent.instance_id),
        template_id=str(b.agent.template_id),
        runtime_id=b.agent.runtime_id,
    )


def local_binding(
    template: str, *, runtime_context: RuntimeContext, portable_context: PortableContext
) -> BoundRuntimeContext:
    """Bind local-engine fixtures as the trusted admission layer would.

    HTTP/admission tests must use create_managed_app instead.
    """
    runtime, portable = runtime_context, portable_context
    identity = {
        "user_id": runtime.user_id or portable.user_id or "alice",
        "session_id": runtime.session_id or portable.session_id,
    }
    return BoundRuntimeContext(
        runtime_context=runtime.model_copy(
            update={
                **identity,
                "space_id": SPACE_ID,
                "agent_instance_id": INSTANCE_ID,
                "template_agent_id": template,
            }
        ),
        portable_context=portable.model_copy(
            update={
                **identity,
                "agent_id": template,
                "baggage": {
                    **portable.baggage,
                    "space_id": SPACE_ID,
                    "agent_instance_id": INSTANCE_ID,
                    "template_agent_id": template,
                },
            }
        ),
    )


_Result = TypeVar("_Result")


async def in_turn(binding: BoundRuntimeContext, work: Awaitable[_Result]) -> _Result:
    """Run a local invocation in a fresh scope, including every HITL resume."""
    with active_turn(binding):
        return await work
