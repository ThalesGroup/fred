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

import asyncio
import json
from io import BytesIO
from pathlib import Path
from re import fullmatch
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from zipfile import ZipFile

import httpx
import pytest
import yaml
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.config.models import Configuration
from control_plane_backend.conversation_traces import api as trace_api
from control_plane_backend.conversation_traces.api import router
from control_plane_backend.conversation_traces.schemas import (
    ConversationTraceSettingsUpdate,
    TraceCatalogFilters,
    TraceConsentGrant,
)
from control_plane_backend.conversation_traces.store import (
    ConversationTraceStore,
    TraceConversationReference,
)
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.conversation_trace_models import (
    ConversationTraceConsentRow,
    ConversationTraceInvalidToolRow,
    ConversationTraceTurnRow,
)
from control_plane_backend.models.session_metadata_models import SessionMetadataRow
from control_plane_backend.sessions.store import SessionMetadataStore
from fastapi import FastAPI, HTTPException, Request
from fred_core import KeycloakUser, OrganizationPermission
from fred_core.common import TeamId
from fred_core.conversation_trace import (
    OtlpTraceSpan,
    TraceAdmissionRequest,
    TraceFinalization,
    TraceHistoryBoundary,
    TraceHttpAttempt,
    TraceHttpCompleteness,
    TraceModelIndex,
    TraceOutcome,
    TraceSseSegment,
    TraceToolCall,
    TraceToolOutcome,
    TraceToolSource,
)
from fred_core.security.oidc import get_current_user_or_service, require_own_credential
from fred_core.teams.team_metatada_models import TeamMetadataRow
from fred_core.users.user_models import UserRow
from pydantic import ValidationError
from sqlalchemy import Connection, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

_ADMIN = "/admin/conversation-traces"
_INGEST = "/internal/runtimes/fred-agents/conversation-traces"
_AGENT = {"x-test-principal": "agentic"}
_READER = {"x-test-principal": "reader"}


def _otel_span(span_id: str, *, parent: str = "") -> OtlpTraceSpan:
    return OtlpTraceSpan(
        trace_id="1" * 32,
        span_id=span_id,
        parent_span_id=parent,
        name="agent.stream",
        start_time_unix_nano="1",
        end_time_unix_nano="2",
    )


def _sse_segment(rank: int) -> TraceSseSegment:
    return TraceSseSegment.model_validate(
        {
            "observed_through_rank": rank,
            "outgoing": {
                "ref": uuid4().hex,
                "started_ms": 0,
                "headers_ms": 0,
                "headers_available": True,
                "end_ms": 20,
                "last_event_ms": 19,
                "longest_gap": [0, 19],
                "availability": "captured",
                "ending": "failed",
                "frame_count": 1,
                "page_starts_ms": [19],
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
async def test_export_slots_follow_delivery_and_release_on_cancel_or_deadline(
    monkeypatch: pytest.MonkeyPatch,
):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_own_credential] = _test_user
    store = SimpleNamespace(local_development=False)
    app.dependency_overrides[get_application_container] = lambda: SimpleNamespace(
        get_rebac_engine=_TraceRebac, get_conversation_trace_store=lambda: store
    )
    state = [SimpleNamespace(session_id="session")]
    content = b"x" * (3 * 64 * 1024)
    assembling = asyncio.Event()
    canceled = asyncio.Event()
    disconnect = asyncio.Event()

    async def assemble(_store, body, _read, **_options):
        if body.session_ids == ["disconnected"]:
            assembling.set()
            try:
                await asyncio.Future()
            finally:
                canceled.set()
        return content, state

    monkeypatch.setattr(trace_api, "build_trace_archive", assemble)
    monkeypatch.setattr(trace_api, "trace_export_state", AsyncMock(return_value=state))
    path = "/admin/conversation-traces/export"
    payload = {"session_ids": ["session"], "mode": "metadata_only"}
    held = {name: asyncio.Event() for name in (b"first", b"second", b"deadline")}
    chunks: list[int] = []

    async def pause_body(scope, receive, send):
        label = dict(scope["headers"]).get(b"x-test-hold")
        body_read = False

        async def receive_or_disconnect():
            nonlocal body_read
            if label == b"disconnect" and body_read:
                await disconnect.wait()
                return {"type": "http.disconnect"}
            message = await receive()
            body_read = message["type"] == "http.request" and not message.get(
                "more_body"
            )
            return message

        async def observe(message):
            if message["type"] == "http.response.body" and message.get("body"):
                if label in held:
                    chunks.append(len(message["body"]))
                    held[label].set()
                    await asyncio.Future()
            await send(message)

        await app(scope, receive_or_disconnect, observe)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=pause_body), base_url="http://test"
    ) as client:
        holders = [
            asyncio.create_task(
                client.post(
                    path, headers={**_READER, "x-test-hold": label}, json=payload
                )
            )
            for label in ("first", "second")
        ]
        try:
            await asyncio.wait_for(held[b"first"].wait(), 2)
            await asyncio.wait_for(held[b"second"].wait(), 2)
            refused = await client.post(path, headers=_READER, json=payload)
            assert refused.status_code == 429
            assert refused.json()["detail"] == "trace_export_busy"
            assert (await client.post(path, json=payload)).status_code == 403
        finally:
            for task in holders:
                task.cancel()
            await asyncio.gather(*holders, return_exceptions=True)

        unfinished = asyncio.create_task(
            client.post(
                path,
                headers={**_READER, "x-test-hold": "disconnect"},
                json={**payload, "session_ids": ["disconnected"]},
            )
        )
        try:
            await asyncio.wait_for(assembling.wait(), 2)
            disconnect.set()
            assert (await asyncio.wait_for(unfinished, 2)).status_code == 499
            assert canceled.is_set()
        finally:
            unfinished.cancel()
            await asyncio.gather(unfinished, return_exceptions=True)

        monkeypatch.setattr(trace_api, "_EXPORT_DELIVERY_TIMEOUT", 0.02)
        with pytest.raises(TimeoutError):
            await client.post(
                path, headers={**_READER, "x-test-hold": "deadline"}, json=payload
            )
        assert held[b"deadline"].is_set()
        recovered = await client.post(path, headers=_READER, json=payload)
        assert recovered.content == content
        assert recovered.headers["content-length"] == str(len(content))
        assert fullmatch(
            r'attachment; filename="conversation-trace-session-\d{8}T\d{6}Z\.zip"',
            recovered.headers["content-disposition"],
        )
        state.append(SimpleNamespace(session_id="another-session"))
        bulk = await client.post(
            path,
            headers=_READER,
            json={**payload, "session_ids": ["session", "another-session"]},
        )
        assert fullmatch(
            r'attachment; filename="conversation-traces-\d{8}T\d{6}Z\.zip"',
            bulk.headers["content-disposition"],
        )
        assert chunks == [64 * 1024] * 3
        assert trace_api._EXPORTS.borrowed_tokens == 0


@pytest.mark.asyncio
async def test_catalog_admission_finalization_and_erasure_through_api(
    control_plane_sql_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
):
    engine = control_plane_sql_engine
    owner_id = uuid4()
    avatar_key = f"users/{owner_id}/avatar.png"
    avatar_url = "https://example.test/signed-profile-picture"
    content_store = Mock()
    team_image_key = f"teams/team/avatar-{uuid4().hex}.png"
    team_image_url = "https://example.test/signed-team-image"
    image_urls = {avatar_key: avatar_url, team_image_key: team_image_url}
    content_store.get_presigned_url.side_effect = lambda key, **_: image_urls[key]
    async with async_sessionmaker(engine).begin() as session:
        session.add(
            TeamMetadataRow(
                id="team",
                name="Synthetic team",
                description="Team for the trace test",
                banner_object_storage_key=team_image_key,
            )
        )
        session.add(
            UserRow(
                id=owner_id,
                username="cdurand",
                first_name="Camille",
                email="camille@example.test",
                last_name="Durand",
                avatar_object_storage_key=avatar_key,
            )
        )
        session.add(
            AgentInstanceRow(
                agent_instance_id="agent",
                team_id="team",
                template_id="synthetic",
                source_runtime_id="fred-agents",
                source_agent_id="synthetic",
                display_name="Synthetic assistant",
                description="Looks up support cases",
                tuning_json=json.dumps(
                    {
                        "role": "Support specialist",
                        "description": "Looks up support cases",
                    }
                ),
            )
        )
        session.add(
            SessionMetadataRow(
                session_id="session",
                team_id="team",
                user_id=str(owner_id),
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
        get_content_store=lambda: content_store,
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
        "user_id": str(owner_id),
        "agent_instance_id": "agent",
        "history_rank": 8,
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get(f"{_ADMIN}/settings", headers=_READER)).json() == {
            "enabled": False,
            "sampling_percent": 100,
            "retention_days": 30,
            "storage_cap_bytes": 20_000_000_000,
            "used_bytes": 0,
            "reserved_bytes": 0,
            "degraded": False,
            "degradation_reason": None,
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
        assert enabled.json()["enabled"] is True
        updated = await client.put(
            f"{_ADMIN}/settings",
            headers=_READER,
            json={
                "sampling_percent": 0,
                "retention_days": 60,
                "storage_cap_bytes": 10_000,
            },
        )
        assert (updated.json()["enabled"], updated.json()["retention_days"]) == (
            True,
            60,
        )
        assert (
            await client.post(f"{_INGEST}/admit", headers=_AGENT, json=admission)
        ).json() is None
        assert (
            await client.put(
                f"{_ADMIN}/settings", headers=_READER, json={"sampling_percent": 101}
            )
        ).status_code == 422
        assert (
            await client.put(
                f"{_ADMIN}/settings", headers=_READER, json={"sampling_percent": 100}
            )
        ).status_code == 200
        result = await client.post(f"{_INGEST}/admit", headers=_AGENT, json=admission)
        capture_id = result.json()["capture_id"]
        later = {**admission, "exchange_id": str(uuid4()), "history_rank": 14}
        later_id = (
            await client.post(f"{_INGEST}/admit", headers=_AGENT, json=later)
        ).json()["capture_id"]
        disabled = await client.put(
            f"{_ADMIN}/settings", headers=_READER, json={"enabled": False}
        )
        assert disabled.json()["enabled"] is False
        off_turn = {**admission, "exchange_id": str(uuid4()), "history_rank": 18}
        assert (
            await client.post(f"{_INGEST}/admit", headers=_AGENT, json=off_turn)
        ).json() is None
        recovery = f"{_INGEST}/reconcile/{uuid4()}"
        facts_only = {"outcome": "completed", "duration_ms": 2}
        report = {"admission": off_turn, "facts": facts_only}
        assert (
            await client.put(recovery, headers=_READER, json=report)
        ).status_code == 403
        assert (
            await client.put(recovery, headers=_AGENT, json=report)
        ).status_code == 409
        assert (
            await client.put(
                recovery,
                headers=_AGENT,
                json={**report, "facts": {**facts_only, "sse": None}},
            )
        ).status_code == 422

        lane = _sse_segment(10)
        assert lane.outgoing is not None
        failed_reservation = {
            "publication_id": str(uuid4()),
            "objects": {lane.outgoing.ref: 12},
        }
        assert (
            await client.post(
                f"{_INGEST}/{capture_id}/reserve",
                headers=_READER,
                json=failed_reservation,
            )
        ).status_code == 403
        assert (
            await client.post(
                f"{_INGEST}/{capture_id}/reserve",
                headers=_AGENT,
                json=failed_reservation,
            )
        ).json() == "reserved"
        failed = {
            "outcome": "failed",
            "checkpoint_status": "persisted",
            "failure_category": "http_400",
            "support_error_ref": "a" * 32,
            "duration_ms": 20,
            "turn_number": 2,
            "call_ids": ["call-1"],
            "otel_spans": [
                _otel_span("2" * 16).model_dump(mode="json"),
                _otel_span("3" * 16, parent="2" * 16).model_dump(mode="json"),
            ],
            "sse": lane.model_dump(mode="json"),
            "storage": {
                "publication_id": failed_reservation["publication_id"],
                "stored": {lane.outgoing.ref: 8},
                "uncertain": [],
            },
        }
        assert (
            await client.put(f"{_INGEST}/{capture_id}", headers=_READER, json=failed)
        ).status_code == 403
        assert (
            await client.put(f"{_INGEST}/{capture_id}", headers=_AGENT, json=failed)
        ).status_code == 204
        spans_path = f"{_ADMIN}/session/spans/{admission['exchange_id']}"
        assert (await client.get(spans_path)).status_code == 403
        spans = await client.get(spans_path, headers=_READER)
        assert spans.status_code == 200
        assert spans.headers["Cache-Control"] == "no-store"
        assert spans.json() == failed["otel_spans"]
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
        ).status_code == 409
        publication_id = str(uuid4())
        assert (
            await client.post(
                f"{_INGEST}/{later_id}/reserve",
                headers=_AGENT,
                json={"publication_id": publication_id, "objects": {tool["ref"]: 25}},
            )
        ).json() == "reserved"
        done["storage"] = {
            "publication_id": publication_id,
            "stored": {tool["ref"]: 22},
            "uncertain": [],
        }
        assert (
            await client.put(f"{_INGEST}/{later_id}", headers=_AGENT, json=done)
        ).status_code == 204
        assert (
            await client.get(
                f"{_ADMIN}/session/spans/{later['exchange_id']}", headers=_READER
            )
        ).json() == []

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
        assert [row["outcome"] for row in all_page] == ["failed"]
        assert failure_page[0]["failure_category"] == "http_400"
        assert failure_page[0]["support_error_ref"] == "a" * 32
        assert failure_page[0]["user_display_name"] == "Camille Durand"
        assert "user_email" not in failure_page[0]
        for search in (
            "CAMILLE DURAND",
            "camille",
            "DuRaNd",
            "cdurand",
            str(owner_id),
            "agent",
            "Synthetic",
            "session",
            "http_400",
        ):
            matches = await client.get(
                _ADMIN, headers=_READER, params={"query": search}
            )
            assert matches.json()["conversations"] == failure_page, search
        localized = await client.get(
            _ADMIN,
            headers=_READER,
            params={"query": "Requête incorrecte", "query_outcomes": "http_400"},
        )
        assert localized.json()["conversations"] == failure_page
        assert (
            len(
                (
                    await client.get(
                        f"{_ADMIN}?outcomes=http_400&team_ids=team", headers=_READER
                    )
                ).json()["conversations"]
            )
            == 1
        )
        assert (
            len(
                (
                    await client.get(
                        f"{_ADMIN}?outcomes=http_5xx&outcomes=http_400&team_ids=other&team_ids=team",
                        headers=_READER,
                    )
                ).json()["conversations"]
            )
            == 1
        )
        assert (
            await client.get(f"{_ADMIN}?outcomes=http_5xx", headers=_READER)
        ).json()["conversations"] == []
        assert (
            await client.get(f"{_ADMIN}?outcomes=completed", headers=_READER)
        ).json()["conversations"] == []
        assert (await client.get(f"{_ADMIN}?query={'a' * 32}", headers=_READER)).json()[
            "conversations"
        ] == failure_page
        assert (
            await client.get(
                f"{_ADMIN}?query=Private+conversation+title&sort=title", headers=_READER
            )
        ).json()["conversations"] == []
        detail = await client.get(
            f"{_ADMIN}/session", headers=_READER, params={"limit": 1}
        )
        assert "Private conversation title" not in detail.text
        assert detail.headers["Cache-Control"] == "no-store"
        first = detail.json()
        assert first["team_name"] == "Synthetic team"
        assert first["team_avatar_image_url"] == team_image_url
        assert first["agent_display_name"] == "Synthetic assistant"
        assert first["agent_role"] == "Support specialist"
        assert first["agent_description"] == "Looks up support cases"
        assert first["agent_instance_id"] == "agent"
        assert first["agent_kind"] == "synthetic"
        assert first["user_id"] == str(owner_id)
        assert first["user_display_name"] == "Camille Durand"
        assert first["user_first_name"] == "Camille"
        assert first["user_email"] == "camille@example.test"
        assert first["has_failed_turn"] is True
        assert first["user_avatar_image_url"] == avatar_url
        assert avatar_key not in detail.text
        assert team_image_key not in detail.text
        assert {
            call.args[0] for call in content_store.get_presigned_url.call_args_list
        } == {
            avatar_key,
            team_image_key,
        }
        assert [turn["turn_number"] for turn in first["turns"]] == [2]
        assert first["turns"][0]["call_ids"] == ["call-1"]
        assert first["turns"][0]["checkpoint_status"] == "persisted"
        for untrusted_key in (
            "https://example.test/external-avatar",
            team_image_key.replace("teams/team/", "teams/other/"),
        ):
            async with async_sessionmaker(engine).begin() as session:
                await session.execute(
                    update(TeamMetadataRow)
                    .where(TeamMetadataRow.id == "team")
                    .values(banner_object_storage_key=untrusted_key)
                )
            content_store.get_presigned_url.reset_mock()
            updated_detail = await client.get(f"{_ADMIN}/session", headers=_READER)
            assert updated_detail.json()["team_avatar_image_url"] is None
            assert untrusted_key not in updated_detail.text
            content_store.get_presigned_url.assert_called_once()
            assert content_store.get_presigned_url.call_args.args == (avatar_key,)
        timeline = f"{_ADMIN}/session/sse/{admission['exchange_id']}"
        masked = await client.get(timeline, headers=_READER)
        assert masked.json() == [failed["sse"]]
        assert masked.json()[0]["outgoing"]["page_starts_ms"] == [19]
        assert (await client.get(timeline)).status_code == 403
        outgoing = masked.json()[0]["outgoing"]
        runtime_history = trace_api._runtime_history

        async def runtime_with_index(
            container, reference, authorization, path, decoder, **kwargs
        ):
            if path.startswith("trace-masked/"):
                assert path == f"trace-masked/{admission['exchange_id']}/sse"
                assert kwargs["params"]["ref"] == outgoing["ref"]
                return decoder.validate_python(
                    {"documents": {"0": {"data": {"text": "<redacted>"}}}}
                )
            if path.startswith("trace-sse-index/"):
                return decoder.validate_python(
                    {
                        "start_index": 0,
                        "frames": [
                            {"at_ms": 19, "kind": "text", "offset": 4, "size": 20}
                        ],
                        "raw_data": "private",
                    }
                )
            return await runtime_history(
                container, reference, authorization, path, decoder, **kwargs
            )

        monkeypatch.setattr(trace_api, "_runtime_history", runtime_with_index)
        index_path = (
            f"{_ADMIN}/session/sse-index/{admission['exchange_id']}/{outgoing['ref']}/0"
        )
        frame_index = await client.get(index_path, headers=_READER)
        assert frame_index.json() == {
            "start_index": 0,
            "frames": [{"at_ms": 19, "kind": "text"}],
        }
        assert frame_index.headers["Cache-Control"] == "no-store"
        masked_path = f"{_ADMIN}/session/masked/{admission['exchange_id']}/sse"
        masked_payload = await client.get(
            masked_path, headers=_READER, params={"ref": outgoing["ref"]}
        )
        assert masked_payload.status_code == 200
        assert masked_payload.json()["documents"]["0"]["data"] == {"text": "<redacted>"}
        assert masked_payload.headers["Cache-Control"] == "no-store"
        assert (
            await client.get(masked_path, params={"ref": outgoing["ref"]})
        ).status_code == 403
        assert (
            await client.get(masked_path, headers=_READER, params={"ref": uuid4().hex})
        ).status_code == 404
        assert (await client.get(index_path)).status_code == 403
        assert (
            await client.get(f"{index_path[:-1]}1", headers=_READER)
        ).status_code == 404
        assert (
            await client.get(
                index_path.replace(outgoing["ref"], uuid4().hex), headers=_READER
            )
        ).status_code == 404
        assert (
            await client.get(
                index_path.replace("sse-index", "sse-frames"), headers=_READER
            )
        ).status_code == 403
        assert (
            await client.get(f"{timeline}/{outgoing['ref']}/0", headers=_READER)
        ).status_code == 403
        assert (
            await client.get(
                f"{_ADMIN}/session/sse-headers/{admission['exchange_id']}/{outgoing['ref']}",
                headers=_READER,
            )
        ).status_code == 403
        second = await client.get(
            f"{_ADMIN}/session",
            headers=_READER,
            params={"cursor": first["next_cursor"]},
        )
        assert [turn["turn_number"] for turn in second.json()["turns"]] == [3]
        assert second.json()["turns"][0]["checkpoint_status"] == "unknown"

        deleted = await SessionMetadataStore(engine).delete(
            "session", TeamId("team"), str(owner_id)
        )
        assert deleted
        assert (
            await client.put(f"{_INGEST}/{later_id}", headers=_AGENT, json=done)
        ).status_code == 409
        assert (
            await client.put(f"{_INGEST}/{later_id}", headers=_AGENT, json=facts_only)
        ).status_code == 409
        assert (
            await client.get(f"{_ADMIN}/session", headers=_READER)
        ).status_code == 404
        assert (await client.get(_ADMIN, headers=_READER)).json()["conversations"] == []
        settings = (await client.get(f"{_ADMIN}/settings", headers=_READER)).json()
        assert settings["used_bytes"] == 30 and settings["reserved_bytes"] == 0
        for _ in range(2):
            job = (await client.post(f"{_INGEST}/cleanup", headers=_AGENT)).json()
            assert job["session_id"] == "session"
            assert (
                await client.put(
                    f"{_INGEST}/cleanup/{job['id']}",
                    headers=_AGENT,
                    json={"lease": job["lease"]},
                )
            ).status_code == 204
        assert (await client.get(f"{_ADMIN}/settings", headers=_READER)).json()[
            "used_bytes"
        ] == 0


@pytest.mark.asyncio
async def test_catalog_in_progress_requires_one_unfinished_first_turn(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    engine = control_plane_sql_engine
    cases = ("running", "finalized-unknown", "earlier-uncaptured", "multi-turn")
    async with async_sessionmaker(engine).begin() as session:
        for session_id in cases:
            session.add(
                SessionMetadataRow(
                    session_id=session_id, team_id="team", user_id="owner"
                )
            )
        await session.flush()
        for session_id in cases:
            session.add(
                ConversationTraceTurnRow(
                    capture_id=str(uuid4()),
                    session_id=session_id,
                    exchange_id="first-capture",
                    runtime_id="fred-agents",
                    agent_display_name="Agent",
                    history_rank=8 if session_id == "earlier-uncaptured" else 0,
                    completed_at=utcnow()
                    if session_id == "finalized-unknown"
                    else None,
                )
            )
        session.add(
            ConversationTraceTurnRow(
                capture_id=str(uuid4()),
                session_id="multi-turn",
                exchange_id="second-capture",
                runtime_id="fred-agents",
                agent_display_name="Agent",
                history_rank=8,
            )
        )
    store = ConversationTraceStore(engine)
    catalog = await store.list_conversations(TraceCatalogFilters(failed_only=False))
    assert {row.session_id: row.outcomes for row in catalog.conversations} == {
        session_id: ["in_progress" if session_id == "running" else "unknown"]
        for session_id in cases
    }
    filtered = await store.list_conversations(
        TraceCatalogFilters(outcomes=["in_progress"])
    )
    assert [row.session_id for row in filtered.conversations] == ["running"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "policy",
    [
        ConversationTraceSettingsUpdate(enabled=False),
        ConversationTraceSettingsUpdate(sampling_percent=0),
        ConversationTraceSettingsUpdate(sampling_percent=1),
    ],
)
async def test_filtered_capture_resumes_only_an_existing_exchange(
    control_plane_sql_engine: AsyncEngine,
    policy: ConversationTraceSettingsUpdate,
) -> None:
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
            )
        )
    store = ConversationTraceStore(engine)
    turn = TraceAdmissionRequest(
        session_id="session",
        exchange_id="exchange",
        user_id="owner",
        agent_instance_id="agent",
        history_rank=4,
    )
    await store.set_settings(ConversationTraceSettingsUpdate(enabled=True))
    opening = await store.admit("fred-agents", turn, segment_id=uuid4())
    assert opening is not None
    pause = TraceFinalization(
        segment_id=opening.segment_id,
        outcome=TraceOutcome.PAUSED,
        duration_ms=10,
        otel_spans=[_otel_span("2" * 16)],
    )
    assert await store.finalize("fred-agents", opening.capture_id, pause)

    await store.set_settings(policy)
    assert await store.admit("fred-agents", turn, segment_id=uuid4()) is None
    assert (
        await store.admit(
            "fred-agents",
            turn.model_copy(update={"exchange_id": "new"}),
            segment_id=uuid4(),
            resuming=True,
        )
        is None
    )
    assert (
        await store.admit(
            "fred-agents",
            turn.model_copy(update={"user_id": "not-owner"}),
            segment_id=uuid4(),
            resuming=True,
        )
        is None
    )

    resume = await store.admit(
        "fred-agents",
        turn.model_copy(update={"history_rank": 1}),
        segment_id=uuid4(),
        resuming=True,
    )
    assert resume is not None
    assert resume.capture_id == opening.capture_id
    assert resume.segment_id != opening.segment_id
    assert await store.capture_start_rank("session", "exchange") == 1
    done = TraceFinalization(
        segment_id=resume.segment_id,
        outcome=TraceOutcome.COMPLETED,
        duration_ms=10,
        otel_spans=[_otel_span("3" * 16, parent="2" * 16)],
    )
    assert await store.finalize("fred-agents", resume.capture_id, done)
    assert await store.finalize("fred-agents", resume.capture_id, done)
    assert await store.otel_spans("session", "exchange") == [
        *pause.otel_spans,
        *done.otel_spans,
    ]
    assert await store.flush_captures() == 1
    assert (
        await store.admit("fred-agents", turn, segment_id=uuid4(), resuming=True)
        is None
    )
    assert not await store.finalize("fred-agents", resume.capture_id, done)


@pytest.mark.asyncio
async def test_model_origin_searches_beyond_the_first_page_in_call_order(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    old_key, shared_key, future_key, same_key, absent_key = (
        character * 64 for character in "abcde"
    )
    ordinary = TraceModelIndex(
        ref=uuid4().hex,
        call_id="ordinary",
        model=None,
        observed_through_rank=2,
        completeness=TraceHttpCompleteness.COMPLETE,
    )
    legacy = ordinary.model_copy(
        update={"observed_through_rank": None, "observed_invalid_tools": [old_key]}
    )
    origin = ordinary.model_copy(
        update={
            "ref": uuid4().hex,
            "call_id": "origin",
            "observed_through_rank": 130,
            "observed_invalid_tools": [old_key, shared_key],
        }
    )
    current = ordinary.model_copy(
        update={
            "ref": uuid4().hex,
            "call_id": "current",
            "observed_through_rank": 132,
            "related_tools": [old_key, shared_key, future_key, same_key],
        }
    )
    same_turn = current.model_copy(
        update={
            "ref": uuid4().hex,
            "call_id": "earlier-in-turn",
            "observed_invalid_tools": [same_key],
        }
    )
    later = ordinary.model_copy(
        update={
            "ref": uuid4().hex,
            "call_id": "later",
            "observed_through_rank": 132,
            "observed_invalid_tools": [future_key],
        }
    )
    no_match = current.model_copy(
        update={
            "ref": uuid4().hex,
            "observed_through_rank": 2400,
            "related_tools": [absent_key],
        }
    )
    calls_by_turn = {1: [legacy], 65: [origin], 66: [current, later], 1200: [no_match]}

    async with async_sessionmaker(control_plane_sql_engine).begin() as session:
        session.add(
            SessionMetadataRow(session_id="session", team_id="team", user_id="owner")
        )
        await session.flush()
        for turn_number in range(1, 1201):
            calls = calls_by_turn.get(turn_number, [ordinary])
            session.add(
                ConversationTraceTurnRow(
                    capture_id=str(uuid4()),
                    session_id="session",
                    exchange_id=f"turn-{turn_number}",
                    history_rank=2 * turn_number - 1,
                    turn_number=turn_number,
                    runtime_id="fred-agents",
                    agent_display_name="Synthetic assistant",
                    model_calls=[call.model_dump(mode="json") for call in calls],
                )
            )

    def upgrade_legacy_schema(connection: Connection) -> None:
        revision = ScriptDirectory(
            str(Path(__file__).resolve().parents[1] / "alembic")
        ).get_revision(
            "3fa0e47d652c"  # pragma: allowlist secret
        )
        assert revision is not None
        with Operations.context(MigrationContext.configure(connection)) as operations:
            operations.drop_table(ConversationTraceInvalidToolRow.__tablename__)
            revision.module.upgrade()

    async with control_plane_sql_engine.begin() as connection:
        await connection.run_sync(upgrade_legacy_schema)

    store = ConversationTraceStore(control_plane_sql_engine)
    shared = await store.model_origins("session", "turn-66", current, cutoff_rank=132)
    assert [(item.turn_number, item.call_id) for item in shared] == [(65, "origin")]
    local = await store.model_origins("session", "turn-66", current, cutoff_rank=None)
    assert [(item.turn_number, item.call_id) for item in local] == [
        (1, "ordinary"),
        (65, "origin"),
    ]
    assert not await store.model_origins(
        "session", "turn-1200", no_match, cutoff_rank=2400
    )

    turn = ConversationTraceTurnRow
    invalid = ConversationTraceInvalidToolRow
    async with async_sessionmaker(control_plane_sql_engine).begin() as session:
        assert await session.scalar(select(func.count()).select_from(invalid)) == 4
        # The source write is identical for older Control Plane pods.
        await session.execute(
            update(turn)
            .where(turn.exchange_id == "turn-66")
            .values(
                model_calls=[
                    model.model_dump(mode="json")
                    for model in (same_turn, current, later)
                ]
            )
        )
    shared = await store.model_origins("session", "turn-66", current, cutoff_rank=132)
    assert [(item.turn_number, item.call_id) for item in shared] == [
        (65, "origin"),
        (66, "earlier-in-turn"),
    ]
    cutoff = await store.model_origins("session", "turn-66", current, cutoff_rank=131)
    assert [(item.turn_number, item.call_id) for item in cutoff] == [(65, "origin")]

    async with async_sessionmaker(control_plane_sql_engine).begin() as session:
        await session.execute(delete(turn).where(turn.session_id == "session"))
        assert await session.scalar(select(func.count()).select_from(invalid)) == 0
    assert not await store.model_origins("session", "turn-66", current, cutoff_rank=132)


@pytest.mark.asyncio
async def test_trace_detail_rechecks_consent_after_signing_avatar(
    control_plane_sql_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
):
    engine = control_plane_sql_engine
    owner = uuid4()
    revision = uuid4().hex
    now = utcnow()
    async with async_sessionmaker(engine).begin() as session:
        session.add(
            UserRow(id=owner, avatar_object_storage_key="users/owner/avatar.png")
        )
        session.add(
            SessionMetadataRow(
                session_id="signing-session",
                team_id="team",
                user_id=str(owner),
                title="Private title",
                title_revision=revision,
            )
        )
        await session.flush()
        session.add(
            ConversationTraceTurnRow(
                capture_id=str(uuid4()),
                session_id="signing-session",
                exchange_id="exchange",
                runtime_id="fred-agents",
                agent_display_name="Synthetic agent",
                history_rank=0,
            )
        )
        session.add(
            ConversationTraceConsentRow(
                grant_id=str(uuid4()),
                session_id="signing-session",
                actor_id=str(owner),
                source="owner",
                title_revision=revision,
                exchange_id="exchange",
                first_rank=0,
                last_rank=1,
                turn_number=1,
                started_at=now,
            )
        )
    store = ConversationTraceStore(engine)

    async def presign(_get_store, _keys):
        reference = await store.reference("signing-session")
        assert reference is not None and reference.title_authorized
        await store.set_consent(reference, None)
        return {"owner": "https://example.test/avatar.png"}

    monkeypatch.setattr(trace_api, "presign_avatar_urls", presign)
    monkeypatch.setattr(trace_api, "_runtime_history", AsyncMock(return_value=[]))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_own_credential] = _test_user
    app.dependency_overrides[get_application_container] = lambda: SimpleNamespace(
        get_rebac_engine=_TraceRebac,
        get_conversation_trace_store=lambda: store,
        get_content_store=Mock(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"{_ADMIN}/signing-session", headers=_READER)

    assert response.status_code == 200
    detail = response.json()
    assert detail["title"] is None
    assert detail["consent_cutoff"] is None
    assert detail["consent_version"].endswith(":revoked")
    assert detail["user_avatar_image_url"] == "https://example.test/avatar.png"


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
                title_revision=uuid4().hex,
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
        for number, rank in ((1, 0), (2, 4))
    ]
    latest = 0
    withdraw_while_exporting = False
    error_ref = uuid4().hex
    second_error_ref = uuid4().hex
    audit = Mock()
    monkeypatch.setattr(
        "control_plane_backend.conversation_traces.api.emit_audit_log", audit
    )
    monkeypatch.setattr(
        "control_plane_backend.conversation_traces.api.get_current_user_without_gcu",
        AsyncMock(return_value=KeycloakUser(uid="reader", username="reader", roles=[])),
    )

    async def runtime(request: httpx.Request) -> httpx.Response:
        if "/trace-history-incident/" in request.url.path:
            assert request.headers["Authorization"] == "Bearer owner"
            incident = {
                "cutoff": turns[0],
                "support_error_ref": error_ref,
                "failure_category": "http_400",
            }
            if request.url.path.endswith(error_ref):
                return httpx.Response(200, json=incident)
            if request.url.path.endswith(second_error_ref):
                return httpx.Response(
                    200,
                    json={
                        "cutoff": turns[1],
                        "support_error_ref": second_error_ref,
                        "failure_category": "http_429",
                    },
                )
            return httpx.Response(200, content=b"null")
        if request.url.path.endswith("/trace-history-boundary"):
            assert request.headers["Authorization"] == "Bearer owner"
            selected = request.url.params.get("exchange_id")
            turn = next(
                (item for item in turns if item["exchange_id"] == selected), None
            )
            return httpx.Response(200, json=turn if selected else turns[latest])
        if request.url.path.endswith("/trace-masked/exchange-2/history"):
            return httpx.Response(404, json={"detail": "trace_masked_unavailable"})
        if request.url.path.endswith("/trace-masked/exchange-1/history"):
            assert request.headers["Authorization"] == "Bearer reader"
            return httpx.Response(
                200,
                json={
                    "documents": {
                        "history": {
                            "data": {
                                "available": True,
                                "messages": [
                                    {"role": "user", "parts": [{"text": "<redacted>"}]}
                                ],
                            }
                        }
                    }
                },
            )
        if request.url.path.endswith("/trace-history-turns/exchange-2"):
            return httpx.Response(403, json={"detail": "trace_history_access_denied"})
        if request.url.path.endswith("/trace-history-turns/exchange-1"):
            assert request.headers["Authorization"] == "Bearer reader"
            if withdraw_while_exporting:
                reference = await store.reference("shared-session")
                assert reference is not None
                await store.set_consent(reference, None)
            return httpx.Response(200, json={"available": True, "messages": []})
        assert request.url.path.endswith("/trace-history-turns")
        assert request.headers["Authorization"] == "Bearer reader"
        if request.url.params.get("latest_only") == "true":
            return httpx.Response(200, json=[turns[latest]])
        after = int(request.url.params.get("after_rank", "-1"))
        return httpx.Response(
            200, json=[turn for turn in turns if int(turn["first_rank"]) > after]
        )

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
        assert detail.json()["title"] == "Private title"
        assert (
            await client.get(
                _ADMIN,
                headers=reader,
                params={"failed_only": False, "query": "Private title"},
            )
        ).json()["conversations"][0]["title"] == "Private title"
        await SessionMetadataStore(engine).update_metadata(
            "shared-session",
            TeamId("personal-owner"),
            "owner",
            title="Revised private title",
        )
        assert (
            await client.get(
                _ADMIN,
                headers=reader,
                params={"failed_only": False, "query": "Revised private title"},
            )
        ).json()["conversations"] == []
        assert (await client.get(f"{_ADMIN}/shared-session", headers=reader)).json()[
            "title"
        ] is None
        assert [item["access"] for item in detail.json()["turns"]] == [
            "shared",
            "masked",
        ]
        export_path = f"{_ADMIN}/export"
        selection = {"session_ids": ["shared-session"], "mode": "shared_content"}
        response = await client.post(export_path, headers=owner, json=selection)
        assert response.status_code == 403
        response = await client.post(export_path, headers=reader, json=selection)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        with ZipFile(BytesIO(response.content)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            (conversation,) = manifest["conversations"]
            shared, masked = conversation["turns"]
            assert conversation["consent_cutoff"]["exchange_id"] == "exchange-1"
            assert shared["availability"] == "history_only"
            assert shared["access"] == "shared"
            assert masked["access"] == "masked"
            (history_file,) = shared["evidence"]["history"]["files"]
            assert json.loads(archive.read(history_file))["messages"] == []
            assert masked["evidence"]["history"]["files"] == []
        response = await client.post(
            export_path, headers=reader, json={**selection, "mode": "masked_content"}
        )
        assert response.status_code == 200
        with ZipFile(BytesIO(response.content)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["mode"] == "masked_content"
            (conversation,) = manifest["conversations"]
            assert "title" not in conversation
            (history_file,) = conversation["turns"][0]["evidence"]["history"]["files"]
            assert history_file.endswith(".masked.json")
            assert json.loads(archive.read(history_file))["history"]["messages"][0][
                "parts"
            ] == [{"text": "<redacted>"}]

        turns[0]["last_rank"] = 2
        detail = (await client.get(f"{_ADMIN}/shared-session", headers=reader)).json()
        assert detail["consent_cutoff"]["last_rank"] == cutoff["last_rank"]
        resumed = await client.put(
            path,
            headers=owner,
            json={**request, "last_rank": 2, "expected_version": first_id},
        )
        assert resumed.status_code == 200
        assert resumed.json()["consent"]["cutoff"]["last_rank"] == 2
        assert (
            resumed.json()["consent"]["cutoff"]["exchange_id"] == cutoff["exchange_id"]
        )
        outdated = await client.put(path, headers=owner, json=request)
        assert outdated.status_code == 409
        assert outdated.json()["detail"] == "trace_consent_turn_changed"
        resumed_id = resumed.json()["consent_version"]
        latest = 1
        state = (await client.get(path, headers=owner)).json()
        new_cutoff = state["available_cutoff"]
        extension = {
            "exchange_id": new_cutoff["exchange_id"],
            "last_rank": new_cutoff["last_rank"],
            "expected_version": resumed_id,
        }
        extended = await client.put(path, headers=owner, json=extension)
        assert extended.status_code == 200
        assert extended.json()["consent"]["grant_id"] != first_id
        assert extended.json()["consent"]["cutoff"]["turn_number"] == 2
        assert (await client.get(f"{_ADMIN}/shared-session", headers=reader)).json()[
            "title"
        ] == "Revised private title"
        deleted = await client.delete(path, headers=owner)
        assert deleted.status_code == 204
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
        assert rows[0]["title"] is None
        assert rows[0]["failure_category"] == "http_400"
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
        assert detail.json()["title"] == "Revised private title"
        assert not detail.json()["can_renew_title_consent"]
        await SessionMetadataStore(engine).update_metadata(
            "shared-session", TeamId("personal-owner"), "owner", title="Renamed again"
        )
        detail = (await client.get(f"{_ADMIN}/shared-session", headers=reader)).json()
        assert detail["title"] is None
        assert detail["can_renew_title_consent"]
        captured_only = str(uuid4())
        async with async_sessionmaker(engine).begin() as session:
            session.add(
                ConversationTraceTurnRow(
                    capture_id=captured_only,
                    session_id="shared-session",
                    exchange_id="later-capture",
                    runtime_id="fred-agents",
                    agent_display_name="Synthetic assistant",
                    history_rank=8,
                )
            )
        paged = (
            await client.get(
                f"{_ADMIN}/shared-session",
                headers=reader,
                params={"limit": 1, "cursor": "0|exchange-1"},
            )
        ).json()
        assert paged["next_cursor"] is not None
        assert paged["turns"][0]["exchange_id"] == "exchange-2"
        assert paged["can_renew_title_consent"]
        async with async_sessionmaker(engine).begin() as session:
            await session.execute(
                delete(ConversationTraceTurnRow).where(
                    ConversationTraceTurnRow.capture_id == captured_only
                )
            )
        renewed = await client.put(
            manual_path,
            headers=reader,
            json={**manual, "expected_version": recorded_id},
        )
        assert renewed.status_code == 200
        recorded_id = renewed.json()["consent_version"]
        detail = (await client.get(f"{_ADMIN}/shared-session", headers=reader)).json()
        assert detail["title"] == "Renamed again"
        assert not detail["can_renew_title_consent"]
        second_report = report.replace(error_ref, second_error_ref)
        second = await client.put(
            second_report,
            headers=owner,
            json={**extension, "expected_version": recorded_id},
        )
        assert second.status_code == 200
        assert (await client.get(report, headers=owner)).json()["reported"]
        assert (await client.get(second_report, headers=owner)).json()["reported"]
        (latest_row,) = (await client.get(_ADMIN, headers=reader)).json()[
            "conversations"
        ]
        assert latest_row["failure_category"] == "http_429"
        assert latest_row["outcomes"] == ["http_429", "http_400"]
        assert latest_row["support_error_ref"] == second_error_ref
        earlier_category = await client.get(
            _ADMIN, headers=reader, params={"query": "http_400"}
        )
        assert earlier_category.json()["conversations"] == [latest_row]
        for ref, category in ((error_ref, "http_400"), (second_error_ref, "http_429")):
            search = await client.get(
                _ADMIN, headers=reader, params={"query": ref, "outcomes": category}
            )
            assert len(search.json()["conversations"]) == 1
        detail = (await client.get(f"{_ADMIN}/shared-session", headers=reader)).json()
        assert [
            turn["reported_failures"][0]["support_error_ref"]
            for turn in detail["turns"]
        ] == [error_ref, second_error_ref]
        response = await client.post(
            export_path, headers=reader, json={**selection, "mode": "metadata_only"}
        )
        assert response.status_code == 200
        with ZipFile(BytesIO(response.content)) as archive:
            assert archive.namelist() == ["manifest.json"]
            manifest_bytes = archive.read("manifest.json")
            assert b"Revised private title" not in manifest_bytes
            assert b"Renamed again" not in manifest_bytes
            assert note.encode() not in manifest_bytes
        withdraw_while_exporting = True
        response = await client.post(export_path, headers=reader, json=selection)
        assert response.status_code == 409
        assert response.json()["detail"] == "trace_export_changed"
        assert (
            await client.post(export_path, headers=reader, json=selection)
        ).status_code == 404
        deleted = await client.delete(path, headers=owner)
        assert deleted.status_code == 204
        assert (await client.get(_ADMIN, headers=reader)).json()["conversations"] == []
        assert not (await client.get(report, headers=owner)).json()["reported"]
        assert not (await client.get(second_report, headers=owner)).json()["reported"]
        assert (
            await client.put(manual_path, headers=reader, json=manual)
        ).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("withdraw", [True, False])
async def test_catalog_restart_when_page_anchor_disappears_or_changes(
    control_plane_sql_engine: AsyncEngine,
    withdraw: bool,
):
    engine = control_plane_sql_engine
    async with async_sessionmaker(engine).begin() as session:
        session.add_all(
            SessionMetadataRow(
                session_id=f"session-{index}",
                team_id="team",
                user_id="owner",
                agent_instance_id="agent",
                title=title,
                title_revision=uuid4().hex,
            )
            for index, title in enumerate(("Alpha", "Beta", "Gamma"))
        )
    store = ConversationTraceStore(engine)
    cutoff = TraceHistoryBoundary(
        exchange_id="exchange-0",
        first_rank=0,
        last_rank=1,
        turn_number=1,
        started_at=utcnow(),
    )
    for index in range(3):
        ref = await store.reference(f"session-{index}")
        assert ref is not None
        await store.set_consent(ref, cutoff, title_covered=True)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_own_credential] = _test_user
    app.dependency_overrides[get_application_container] = lambda: SimpleNamespace(
        get_rebac_engine=_TraceRebac, get_conversation_trace_store=lambda: store
    )
    filters = {"failed_only": False, "limit": 1, "sort": "title", "direction": "asc"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = (await client.get(_ADMIN, headers=_READER, params=filters)).json()
        assert first["conversations"][0]["title"] == "Alpha"
        assert "Alpha" not in first["next_cursor"]
        params = {**filters, "cursor": first["next_cursor"]}
        following = await client.get(_ADMIN, headers=_READER, params=params)
        assert following.status_code == 200
        assert following.json()["conversations"][0]["title"] == "Beta"
        anchor = await store.reference("session-0")
        assert anchor is not None
        if withdraw:
            await store.set_consent(anchor, None)
        else:
            await SessionMetadataStore(engine).update_metadata(
                "session-0", TeamId("team"), "owner", title="Moved"
            )
        stale = await client.get(_ADMIN, headers=_READER, params=params)
        assert stale.status_code == 409
        assert stale.json()["detail"] == "stale_trace_cursor"
        restarted = (await client.get(_ADMIN, headers=_READER, params=filters)).json()
        assert restarted["conversations"]


@pytest.mark.asyncio
@pytest.mark.parametrize("start_rank", [1, 3])
async def test_trace_content_consent_excludes_new_attempt_in_same_exchange(start_rank):
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
        capture_start_rank=AsyncMock(return_value=start_rank),
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
        for kind, frame in (("sse", {"index": 0}), ("sse-header", {})):
            for segment, expected in zip(segments.json(), (200, 403), strict=True):
                response = await client.get(
                    f"{_ADMIN}/session/{kind}-access",
                    headers=_READER,
                    params={
                        "exchange_id": "exchange",
                        "runtime_id": "fred-agents",
                        "ref": segment["outgoing"]["ref"],
                        **frame,
                    },
                )
                assert response.status_code == expected
