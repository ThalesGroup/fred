# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

import asyncio
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fred_core.history.content_policy_jobs import (
    ClaimedContentPolicyJob,
    ContentPolicyJob,
)
from fred_core.history.history_models import SessionHistoryRow
from fred_core.history.history_schema import (
    Channel,
    ChatMessage,
    ChatMetadata,
    ContentNotice,
    Role,
)
from fred_core.history.postgres_history_store import PostgresHistoryStore
from fred_runtime.app.content_policy_analysis import explain
from fred_runtime.migrations import upgrade_sqlite_database
from langchain_core.messages import AIMessage, SystemMessage
from sqlalchemy import update
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ({"explanation_code": "self_harm", "evidence_ids": ["e0"]}, "self_harm"),
        ({"explanation_code": "violence", "evidence_ids": ["e0"]}, None),
        ({"explanation_code": "self_harm", "evidence_ids": ["another-id"]}, None),
        ({"explanation_code": "self_harm", "evidence_ids": []}, None),
        (
            {
                "explanation_code": "self_harm",
                "evidence_ids": ["e0"],
                "text": "free text",
            },
            None,
        ),
        ({"explanation_code": "indeterminate", "evidence_ids": []}, None),
    ],
)
async def test_analysis_uses_application_binding_and_validates_evidence(
    answer, expected
):
    response = AsyncMock(return_value=answer)
    model = Mock()
    model.with_structured_output.return_value = SimpleNamespace(ainvoke=response)
    factory = Mock()
    factory.build_chat_for_binding.return_value = model
    job = ClaimedContentPolicyJob(
        ("private-session", "private-user", 1),
        "private-reference",
        "lease",
        ("self_harm", "violence"),
        {"provider": "openai", "name": "default"},
        "ignored-profile",
    )
    assert await explain(factory, job) == expected
    factory.build_chat_for_profile.assert_not_called()
    assert response.await_args is not None
    system, request = response.await_args.args[0]
    assert isinstance(system, SystemMessage)
    assert "Do not infer" in system.content
    assert "self_harm" in request.content
    assert "private-" not in request.content
    assert len(request.content.encode()) < 2048


@pytest.mark.asyncio
async def test_analysis_uses_configured_pod_default_when_no_platform_binding():
    model = Mock()
    model.with_structured_output.side_effect = NotImplementedError
    model.ainvoke = AsyncMock(
        return_value=AIMessage(
            content='{"explanation_code":"violence","evidence_ids":["e0"]}'
        )
    )
    factory = Mock()
    factory.build_chat_for_profile.return_value = (model, "application-default", None)
    job = ClaimedContentPolicyJob(
        ("s", "u", 0), "ref", "lease", ("violence",), None, "default"
    )
    assert await explain(factory, job) == "violence"
    factory.build_chat_for_profile.assert_called_once_with("default")
    factory.build_chat_for_binding.assert_not_called()
    factory.build_chat_for_profile.side_effect = RuntimeError("unavailable routing")
    assert await explain(factory, job) is None


@pytest.mark.asyncio
async def test_job_reclaim_and_cas_share_terminal_history(tmp_path):
    path = tmp_path / "history.db"
    upgrade_sqlite_database(path)
    first = create_async_engine(f"sqlite+aiosqlite:///{path}")
    second = create_async_engine(f"sqlite+aiosqlite:///{path}")
    writer = PostgresHistoryStore(first)
    reader = PostgresHistoryStore(second)
    row = ChatMessage(
        session_id="session",
        exchange_id="exchange",
        rank=1,
        timestamp=datetime.now(timezone.utc),
        role=Role.system,
        channel=Channel.error,
        parts=[],
        metadata=ChatMetadata(
            support_error_ref="a" * 32,
            content_notice=ContentNotice(
                kind="prompt_blocked",
                categories=("self_harm",),
                analysis_state="pending",
            ),
        ),
    )

    async def save_terminal():
        return await writer.save_managed_turn(
            session_id="session",
            messages=[row],
            user_id="owner",
            team_id="team",
            agent_instance_id="instance",
            content_job=ContentPolicyJob(1, "runtime", None, None),
        )

    try:
        assert await save_terminal()
        old = await writer.content_policy_jobs.claim("runtime")
        assert old is not None
        assert await reader.content_policy_jobs.claim("runtime") is None
        assert await reader.content_policy_jobs.claim("another-runtime") is None
        assert (
            await reader.content_policy_jobs.read_notice(
                "session", 1, old.reference, "stranger"
            )
            is None
        )
        async with first.begin() as connection:
            await connection.execute(
                update(SessionHistoryRow).values(
                    content_policy_due=datetime.now(timezone.utc) - timedelta(seconds=1)
                )
            )
        claimed = await reader.content_policy_jobs.claim("runtime")
        assert claimed is not None and claimed.lease != old.lease
        await writer.content_policy_jobs.finish(old, "self_harm")
        result = await reader.content_policy_jobs.read_notice(
            "session", 1, old.reference, "owner"
        )
        assert result is not None and result[0].analysis_state == "pending"
        await reader.content_policy_jobs.finish(claimed, "self_harm")
        assert await save_terminal()  # retry must preserve the worker's result
        assert await writer.content_policy_jobs.claim("runtime") is None
        (reloaded,) = await reader.get("session", "owner")
        assert reloaded.metadata is not None
        notice = reloaded.metadata.content_notice
        assert notice is not None and notice.explanation == "self_harm"
        assert notice.analysis_state == "complete"
        assert "content_policy_job" not in reloaded.model_dump_json()
        await writer.delete_session("session", "owner")
        await reader.content_policy_jobs.finish(claimed, "self_harm")
        assert not await writer.get("session", "owner")
    finally:
        await first.dispose()
        await second.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_worker_reservations_under_parallel_chat_writes():
    url = os.environ.get("FRED_TEST_POLICY_POSTGRES_URL")
    if not url:
        pytest.skip("requires a disposable, migrated PostgreSQL database")
    first = create_async_engine(url, pool_size=3, max_overflow=1)
    second = create_async_engine(url, pool_size=3, max_overflow=1)
    first_store = PostgresHistoryStore(first)
    second_store = PostgresHistoryStore(second)
    namespace = uuid4().hex
    runtime = f"policy-fixture-{namespace}"
    notice = ContentNotice(
        kind="prompt_blocked", categories=("hate",), analysis_state="pending"
    )

    async def save(index: int, *, filtered: bool):
        session_id = f"{namespace}-{index}"
        metadata = ChatMetadata(
            support_error_ref=uuid4().hex if filtered else None,
            content_notice=notice if filtered else None,
        )
        message = ChatMessage(
            session_id=session_id,
            exchange_id="exchange",
            rank=0,
            timestamp=datetime.now(timezone.utc),
            role=Role.system if filtered else Role.assistant,
            channel=Channel.error if filtered else Channel.final,
            metadata=metadata,
            parts=[],
        )
        assert await first_store.save_managed_turn(
            session_id=session_id,
            messages=[message],
            user_id="fixture-owner",
            team_id="fixture-team",
            agent_instance_id="fixture-instance",
            content_job=ContentPolicyJob(0, runtime, None, None) if filtered else None,
        )

    try:
        await asyncio.gather(*(save(index, filtered=True) for index in range(12)))
        claims = await asyncio.gather(
            *(
                store.content_policy_jobs.claim(runtime)
                for store in (first_store, second_store) * 8
            )
        )
        (active,) = [claim for claim in claims if claim is not None]
        # Keep the lease outstanding as if the analyzer were slow. Ordinary
        # chat can use all DB connections, and other workers cannot claim.
        await asyncio.wait_for(
            asyncio.gather(*(save(index, filtered=False) for index in range(12, 44))),
            timeout=10,
        )
        assert await second_store.content_policy_jobs.claim(runtime) is None
        await second_store.content_policy_jobs.finish(active, "hate")
        result = await first_store.content_policy_jobs.read_notice(
            active.row_key[0],
            0,
            active.reference,
            "fixture-owner",
        )
        assert result is not None and result[0].explanation == "hate"
        assert await second_store.content_policy_jobs.claim(runtime) is not None
    finally:
        await asyncio.gather(
            *(
                first_store.delete_session(f"{namespace}-{index}", "fixture-owner")
                for index in range(44)
            )
        )
        await first.dispose()
        await second.dispose()
