# Copyright Thales 2026
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

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
import yaml
from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.config.models import Configuration
from control_plane_backend.conversation_traces.api import router
from control_plane_backend.conversation_traces.schemas import TraceConsentGrant
from control_plane_backend.conversation_traces.store import (
    ConversationTraceStore,
    TraceConversationReference,
)
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.conversation_trace_models import (
    ConversationTraceConsentRow,
)
from control_plane_backend.models.session_metadata_models import SessionMetadataRow
from control_plane_backend.sessions.store import SessionMetadataStore
from fastapi import FastAPI, HTTPException, Request
from fred_core import KeycloakUser, OrganizationPermission
from fred_core.common import TeamId
from fred_core.conversation_trace import (
    TraceHistoryBoundary,
    TraceHttpAttempt,
    TraceHttpCompleteness,
    TraceSseSegment,
    TraceToolCall,
    TraceToolOutcome,
    TraceToolSource,
)
from fred_core.security.oidc import get_current_user_or_service, require_own_credential
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

_ADMIN = "/admin/conversation-traces"
_INGEST = "/internal/runtimes/fred-agents/conversation-traces"
_AGENT = {"x-test-principal": "agentic"}
_READER = {"x-test-principal": "reader"}


def _sse_segment(rank: int) -> TraceSseSegment:
    return TraceSseSegment.model_validate(
        {
            "observed_through_rank": rank,
            "outgoing": {
                "ref": uuid4().hex,
                "started_ms": 0,
                "headers_ms": 0,
                "end_ms": 20,
                "last_event_ms": 19,
                "longest_gap": [0, 19],
                "availability": "captured",
                "ending": "failed",
                "frame_count": 1,
                "frames": [{"at_ms": 19, "kind": "error", "size": 8, "offset": 0}],
            },
            "provider": [],
        }
    )


def test_trace_local_development_is_explicit_and_rejects_shared_profiles():
    path = Path(__file__).resolve().parents[1] / "config" / "configuration.yaml"
    config = yaml.safe_load(path.read_text())
    assert Configuration.model_validate(config).conversation_trace_local_development
    assert not Configuration.model_validate(
        {**config, "conversation_trace_local_development": False}
    ).conversation_trace_local_development
    config["security"]["profile"] = "c3"
    with pytest.raises(ValidationError, match="requires loopback"):
        Configuration.model_validate(config)


class _TraceRebac:
    async def check_user_permission_or_raise(self, user, permission, resource_id):
        assert permission is OrganizationPermission.CAN_MANAGE_CONVERSATION_TRACES
        assert resource_id == "fred"
        if user.uid not in {"reader", "admin"}:
            raise HTTPException(403)


async def _test_user(request: Request) -> KeycloakUser:
    principal = request.headers.get("x-test-principal", "outsider")
    return KeycloakUser(
        uid=principal,
        username=principal,
        roles=["service_agent"] if principal == "agentic" else [],
        client_id="agentic" if principal == "agentic" else "app",
    )


@pytest.mark.asyncio
async def test_catalog_admission_finalization_and_erasure_through_api(
    control_plane_sql_engine: AsyncEngine,
):
    engine = control_plane_sql_engine
    async with async_sessionmaker(engine).begin() as session:
        session.add(
            AgentInstanceRow(
                agent_instance_id="agent",
                team_id="team",
                template_id="synthetic",
                source_runtime_id="fred-agents",
                source_agent_id="synthetic",
                display_name="Synthetic assistant",
            )
        )
        session.add(
            SessionMetadataRow(
                session_id="session",
                team_id="team",
                user_id="owner",
                agent_instance_id="agent",
                title="Private conversation title",
            )
        )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_own_credential] = _test_user
    app.dependency_overrides[get_current_user_or_service] = _test_user
    app.dependency_overrides[get_application_container] = lambda: SimpleNamespace(
        get_rebac_engine=_TraceRebac,
        get_conversation_trace_store=lambda: ConversationTraceStore(engine),
        configuration=SimpleNamespace(
            security=SimpleNamespace(m2m=SimpleNamespace(enabled=True)),
            platform=SimpleNamespace(
                runtime_catalog_sources=[
                    SimpleNamespace(
                        runtime_id="fred-agents",
                        enabled=True,
                        preparation_client_id="agentic",
                    ),
                ]
            ),
        ),
    )
    admission = {
        "session_id": "session",
        "exchange_id": str(uuid4()),
        "user_id": "owner",
        "agent_instance_id": "agent",
        "history_rank": 8,
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get(f"{_ADMIN}/settings", headers=_READER)).json() == {
            "enabled": False
        }
        for path in (_ADMIN, f"{_ADMIN}/session", f"{_ADMIN}/settings"):
            assert (await client.get(path)).status_code == 403
        assert (
            await client.put(f"{_ADMIN}/settings", json={"enabled": True})
        ).status_code == 403
        assert (
            await client.post(f"{_INGEST}/admit", headers=_READER, json=admission)
        ).status_code == 403
        assert (
            await client.post(f"{_INGEST}/admit", headers=_AGENT, json=admission)
        ).json() is None

        enabled = await client.put(
            f"{_ADMIN}/settings", headers=_READER, json={"enabled": True}
        )
        assert enabled.json() == {"enabled": True}
        result = await client.post(f"{_INGEST}/admit", headers=_AGENT, json=admission)
        capture_id = result.json()["capture_id"]
        later = {**admission, "exchange_id": str(uuid4()), "history_rank": 14}
        later_id = (
            await client.post(f"{_INGEST}/admit", headers=_AGENT, json=later)
        ).json()["capture_id"]
        disabled = await client.put(
            f"{_ADMIN}/settings", headers=_READER, json={"enabled": False}
        )
        assert disabled.json() == {"enabled": False}
        off_turn = {**admission, "exchange_id": str(uuid4()), "history_rank": 18}
        assert (
            await client.post(f"{_INGEST}/admit", headers=_AGENT, json=off_turn)
        ).json() is None

        failed = {
            "outcome": "failed",
            "duration_ms": 20,
            "turn_number": 2,
            "call_ids": ["call-1"],
            "sse": _sse_segment(10).model_dump(mode="json"),
        }
        assert (
            await client.put(f"{_INGEST}/{capture_id}", headers=_READER, json=failed)
        ).status_code == 403
        assert (
            await client.put(f"{_INGEST}/{capture_id}", headers=_AGENT, json=failed)
        ).status_code == 204
        tool = TraceToolCall(
            ref=uuid4().hex,
            call_id="tool-call-1",
            tool_name="lookup",
            source=TraceToolSource.MCP,
            outcome=TraceToolOutcome.ERROR,
            attempt=1,
            duration_ms=2,
            observed_through_rank=16,
            completeness=TraceHttpCompleteness.COMPLETE,
        ).model_dump(mode="json")
        done = {
            "outcome": "completed",
            "duration_ms": 2,
            "turn_number": 3,
            "tool_calls": [tool],
        }
        assert (
            await client.put(f"{_INGEST}/{later_id}", headers=_AGENT, json=done)
        ).status_code == 204

        assert (
            await client.put(f"{_INGEST}/{later_id}", headers=_AGENT, json=done)
        ).status_code == 204
        assert (
            await client.put(
                f"{_INGEST}/{later_id}",
                headers=_AGENT,
                json={**done, "tool_calls": [{**tool, "ref": uuid4().hex}]},
            )
        ).status_code == 409
        tool_path = f"{_ADMIN}/session/tool/{later['exchange_id']}"
        assert (await client.get(tool_path, headers=_READER)).json() == [tool]
        assert (await client.get(tool_path)).status_code == 403
        assert (
            await client.get(f"{tool_path}/{tool['ref']}", headers=_READER)
        ).status_code == 403

        failure_page = (await client.get(_ADMIN, headers=_READER)).json()[
            "conversations"
        ]
        all_page = (
            await client.get(_ADMIN, headers=_READER, params={"failed_only": False})
        ).json()["conversations"]
        assert [row["outcome"] for row in failure_page] == ["failed"]
        assert [row["outcome"] for row in all_page] == ["completed"]
        detail = await client.get(
            f"{_ADMIN}/session", headers=_READER, params={"limit": 1}
        )
        assert "Private conversation title" not in detail.text
        first = detail.json()
        assert first["agent_display_name"] == "Synthetic assistant"
        assert [turn["turn_number"] for turn in first["turns"]] == [2]
        assert first["turns"][0]["call_ids"] == ["call-1"]
        timeline = f"{_ADMIN}/session/sse/{admission['exchange_id']}"
        masked = await client.get(timeline, headers=_READER)
        assert masked.json() == [failed["sse"]]
        assert "data" not in masked.json()[0]["outgoing"]["frames"][0]
        assert (await client.get(timeline)).status_code == 403
        outgoing = masked.json()[0]["outgoing"]
        assert (
            await client.get(f"{timeline}/{outgoing['ref']}/0", headers=_READER)
        ).status_code == 403
        second = await client.get(
            f"{_ADMIN}/session",
            headers=_READER,
            params={"cursor": first["next_cursor"]},
        )
        assert [turn["turn_number"] for turn in second.json()["turns"]] == [3]

        assert await SessionMetadataStore(engine).delete(
            "session", TeamId("team"), "owner"
        )
        assert (
            await client.put(f"{_INGEST}/{later_id}", headers=_AGENT, json=done)
        ).status_code == 409
        assert (
            await client.get(f"{_ADMIN}/session", headers=_READER)
        ).status_code == 404
        assert (await client.get(_ADMIN, headers=_READER)).json()["conversations"] == []


@pytest.mark.asyncio
async def test_owner_share_catalog_extension_and_revocation(
    control_plane_sql_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
):
    engine = control_plane_sql_engine
    async with async_sessionmaker(engine).begin() as session:
        session.add(
            AgentInstanceRow(
                agent_instance_id="share-agent",
                team_id="personal-owner",
                template_id="synthetic",
                source_runtime_id="fred-agents",
                source_agent_id="synthetic",
                display_name="Synthetic assistant",
            )
        )
        session.add(
            SessionMetadataRow(
                session_id="shared-session",
                team_id="personal-owner",
                user_id="owner",
                agent_instance_id="share-agent",
                title="Private title",
            )
        )

    turns = [
        {
            "exchange_id": f"exchange-{number}",
            "first_rank": rank,
            "last_rank": rank + 1,
            "turn_number": number,
            "started_at": "2026-01-01T12:00:00Z",
        }
        for number, rank in ((1, 0), (2, 2))
    ]
    latest = 0
    error_ref = uuid4().hex
    audit = Mock()
    monkeypatch.setattr(
        "control_plane_backend.conversation_traces.api.emit_audit_log", audit
    )

    def runtime(request: httpx.Request) -> httpx.Response:
        if "/trace-history-incident/" in request.url.path:
            assert request.headers["Authorization"] == "Bearer owner"
            incident = {"cutoff": turns[0], "support_error_ref": error_ref}
            if request.url.path.endswith(error_ref):
                return httpx.Response(200, json=incident)
            return httpx.Response(200, content=b"null")
        if request.url.path.endswith("/trace-history-boundary"):
            assert request.headers["Authorization"] == "Bearer owner"
            selected = request.url.params.get("exchange_id")
            turn = next(
                (item for item in turns if item["exchange_id"] == selected), None
            )
            return httpx.Response(200, json=turn if selected else turns[latest])
        if request.url.path.endswith("/trace-history-turns/exchange-2"):
            return httpx.Response(403, json={"detail": "trace_history_access_denied"})
        assert request.url.path.endswith("/trace-history-turns")
        assert request.headers["Authorization"] == "Bearer reader"
        return httpx.Response(200, json=turns)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_own_credential] = _test_user
    store = ConversationTraceStore(engine)
    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(runtime)) as runtime_http,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        app.dependency_overrides[get_application_container] = lambda: SimpleNamespace(
            get_rebac_engine=_TraceRebac,
            get_conversation_trace_store=lambda: store,
            get_runtime_http_client=lambda: runtime_http,
            configuration=SimpleNamespace(
                platform=SimpleNamespace(
                    runtime_catalog_sources=[
                        SimpleNamespace(
                            runtime_id="fred-agents",
                            enabled=True,
                            base_url="http://runtime",
                        )
                    ]
                ),
            ),
        )
        path = "/teams/personal/sessions/shared-session/trace-consent"
        owner = {"x-test-principal": "owner", "Authorization": "Bearer owner"}
        reader = {**_READER, "Authorization": "Bearer reader"}
        assert (await client.get(path, headers=_READER)).status_code == 404
        assert (
            await client.get(f"{_ADMIN}/shared-session", headers=reader)
        ).status_code == 404

        state = (await client.get(path, headers=owner)).json()
        cutoff = state["available_cutoff"]
        request = {
            "exchange_id": cutoff["exchange_id"],
            "last_rank": cutoff["last_rank"],
            "expected_version": state["consent_version"],
        }
        response = await client.put(path, headers=owner, json=request)
        assert response.status_code == 200
        first_id = response.json()["consent"]["grant_id"]
        catalog = await client.get(
            _ADMIN, headers=reader, params={"failed_only": False}
        )
        assert [item["availability"] for item in catalog.json()["conversations"]] == [
            "history_only"
        ]
        detail = await client.get(f"{_ADMIN}/shared-session", headers=reader)
        assert "Private title" not in detail.text
        assert [item["access"] for item in detail.json()["turns"]] == [
            "shared",
            "masked",
        ]

        latest = 1
        state = (await client.get(path, headers=owner)).json()
        new_cutoff = state["available_cutoff"]
        extension = {
            "exchange_id": new_cutoff["exchange_id"],
            "last_rank": new_cutoff["last_rank"],
            "expected_version": first_id,
        }
        extended = await client.put(path, headers=owner, json=extension)
        assert extended.status_code == 200
        assert extended.json()["consent"]["grant_id"] != first_id
        assert extended.json()["consent"]["cutoff"]["turn_number"] == 2
        assert (await client.delete(path, headers=owner)).status_code == 204
        assert (
            await client.put(path, headers=owner, json=extension)
        ).status_code == 409
        assert (
            await client.get(f"{_ADMIN}/shared-session", headers=reader)
        ).status_code == 404
        assert (
            await client.get(
                f"{_ADMIN}/shared-session/history/exchange-1", headers=reader
            )
        ).status_code == 403

        report = f"/teams/personal/sessions/shared-session/trace-incident/{error_ref}"
        offer = await client.get(report, headers=owner)
        assert offer.status_code == 200
        assert offer.json()["capture_available"] is False
        assert offer.json()["reported"] is False
        assert (await client.get(report, headers=reader)).status_code == 404
        assert (
            await client.get(report.replace(error_ref, uuid4().hex), headers=owner)
        ).status_code == 404
        # Opening and dismissing the offer has no grant/catalog side effect.
        assert (await client.get(_ADMIN, headers=reader)).json()["conversations"] == []
        request = {
            "exchange_id": turns[0]["exchange_id"],
            "last_rank": turns[0]["last_rank"],
            "expected_version": offer.json()["consent_version"],
        }
        assert (
            await client.put(report, headers=owner, json={**request, "last_rank": 3})
        ).status_code == 409
        assert (
            await client.put(
                report, headers=owner, json={**request, "outcome": "failed"}
            )
        ).status_code == 422
        shared_incident = await client.put(report, headers=owner, json=request)
        assert shared_incident.status_code == 200
        active_id = shared_incident.json()["consent_version"]
        rows = (await client.get(_ADMIN, headers=reader)).json()["conversations"]
        assert [
            (row["availability"], row["outcome"], row["support_error_ref"])
            for row in rows
        ] == [("history_only", "failed", error_ref)]
        assert (
            await client.get(
                f"{_ADMIN}/shared-session/history/exchange-2", headers=reader
            )
        ).status_code == 403

        manual_path = f"{_ADMIN}/shared-session/consent"
        note = "Consent confirmed in a private support call."
        manual = {**extension, "expected_version": active_id, "source_note": note}
        assert (
            await client.put(manual_path, headers=owner, json=manual)
        ).status_code == 403
        assert (
            await client.put(
                manual_path, headers=reader, json={**manual, "source_note": " \n "}
            )
        ).status_code == 422
        assert (
            await client.put(
                manual_path,
                headers=reader,
                json={**manual, "expected_version": first_id},
            )
        ).status_code == 409
        recorded = await client.put(manual_path, headers=reader, json=manual)
        assert recorded.status_code == 200
        recorded_id = recorded.json()["consent_version"]
        assert note not in recorded.text
        assert recorded.json()["consent"]["cutoff"]["turn_number"] == 2
        audit.assert_called_with(
            "conversation_trace.consent.recorded",
            user_id="reader",
            session_id="shared-session",
            grant_id=recorded_id,
            cutoff_exchange_id="exchange-2",
            cutoff_turn=2,
            source="manual",
        )
        async with async_sessionmaker(engine)() as session:
            assert (
                await session.scalar(
                    select(ConversationTraceConsentRow.source_note).where(
                        ConversationTraceConsentRow.grant_id == recorded_id
                    )
                )
                == note
            )
        detail = await client.get(f"{_ADMIN}/shared-session", headers=reader)
        assert note not in detail.text
        assert detail.json()["turns"][0]["support_error_ref"] == error_ref
        assert (await client.delete(path, headers=owner)).status_code == 204
        assert (await client.get(_ADMIN, headers=reader)).json()["conversations"] == []
        assert (
            await client.put(manual_path, headers=reader, json=manual)
        ).status_code == 404


@pytest.mark.asyncio
async def test_trace_content_consent_excludes_new_attempt_in_same_exchange():
    persisted = [
        TraceHttpAttempt(
            ref=uuid4().hex,
            call_id="call",
            attempt=number,
            status=200,
            duration_ms=5,
            request_bytes=2,
            response_bytes=2,
            observed_through_rank=rank,
            completeness=TraceHttpCompleteness.COMPLETE,
        )
        for number, rank in ((1, 4), (2, 5))
    ]
    tools = [
        TraceToolCall(
            ref=uuid4().hex,
            call_id=f"tool-{item.attempt}",
            tool_name="lookup",
            source=TraceToolSource.KNOWLEDGE_FLOW,
            outcome=TraceToolOutcome.ERROR,
            attempt=item.attempt,
            duration_ms=5,
            observed_through_rank=item.observed_through_rank,
            completeness=TraceHttpCompleteness.COMPLETE,
        )
        for item in persisted
    ]
    for tool, attempt in zip(tools, persisted, strict=True):
        tool.http_attempts.append(
            attempt.model_copy(update={"ref": uuid4().hex, "tool_ref": tool.ref})
        )
    reference = TraceConversationReference(
        session_id="session",
        team_id="team",
        owner_id="owner",
        runtime_id="fred-agents",
        agent_display_name="Fixture",
        has_capture=True,
        consent=TraceConsentGrant(
            grant_id="fixture-grant",
            cutoff=TraceHistoryBoundary.model_validate(
                {
                    "exchange_id": "exchange",
                    "first_rank": 1,
                    "last_rank": 4,
                    "turn_number": 1,
                    "started_at": "2026-01-01T12:00:00Z",
                }
            ),
        ),
        consent_version="fixture-grant",
    )
    store = SimpleNamespace(
        reference=AsyncMock(return_value=reference),
        capture_start_rank=AsyncMock(return_value=1),
        http_attempts=AsyncMock(
            return_value=[*persisted, *(tool.http_attempts[0] for tool in tools)]
        ),
        tool_calls=AsyncMock(return_value=tools),
        sse_segments=AsyncMock(return_value=[_sse_segment(4), _sse_segment(5)]),
        local_development=False,
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_own_credential] = _test_user
    app.dependency_overrides[get_application_container] = lambda: SimpleNamespace(
        get_rebac_engine=_TraceRebac,
        get_conversation_trace_store=lambda: store,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = f"{_ADMIN}/session/http-access"
        for item, expected in zip(persisted, (200, 403), strict=True):
            response = await client.get(
                path,
                headers=_READER,
                params={
                    "exchange_id": "exchange",
                    "runtime_id": "fred-agents",
                    "ref": item.ref,
                },
            )
            assert response.status_code == expected
        masked = await client.get(f"{_ADMIN}/session/http/exchange", headers=_READER)
        assert masked.status_code == 200
        assert len(masked.json()) == 2
        tool_summaries = await client.get(
            f"{_ADMIN}/session/tool/exchange", headers=_READER
        )
        assert tool_summaries.json() == [tool.model_dump(mode="json") for tool in tools]
        for tool, expected in zip(tools, (200, 403), strict=True):
            for kind, ref in (("tool", tool.ref), ("http", tool.http_attempts[0].ref)):
                response = await client.get(
                    f"{_ADMIN}/session/{kind}-access",
                    headers=_READER,
                    params={
                        "exchange_id": "exchange",
                        "runtime_id": "fred-agents",
                        "ref": ref,
                    },
                )
                assert response.status_code == expected

        segments = await client.get(f"{_ADMIN}/session/sse/exchange", headers=_READER)
        assert segments.status_code == 200
        for segment, expected in zip(segments.json(), (200, 403), strict=True):
            response = await client.get(
                f"{_ADMIN}/session/sse-access",
                headers=_READER,
                params={
                    "exchange_id": "exchange",
                    "runtime_id": "fred-agents",
                    "ref": segment["outgoing"]["ref"],
                    "index": 0,
                },
            )
            assert response.status_code == expected
