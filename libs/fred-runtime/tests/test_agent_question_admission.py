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

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fred_core.history.history_schema import Channel
from fred_runtime.app import agent_app as app
from fred_sdk.contracts.execution import RuntimeExecuteRequest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer, accepted",
    [
        ({"choice_id": "yes"}, True),
        ({"text": "An explanation"}, True),
        ({"choice_id": "yes", "text": "Please"}, True),
        ({"skipped": True}, True),
        ({"choice_id": "other"}, False),
        ({"choice_id": "yes", "skipped": True}, False),
        ({"text": ""}, False),
    ],
)
async def test_pending_agent_question_answer_is_checked_before_claim(
    monkeypatch, answer, accepted
) -> None:
    pending = [
        (
            "task-1",
            "__interrupt__",
            {
                "id": "interrupt-1",
                "value": {
                    "stage": "agent_question",
                    "occurrence_id": "call-1",
                    "question": "Continue?",
                    "choices": [{"id": "yes", "label": "Yes"}],
                    "free_text": True,
                },
            },
        )
    ]
    loader = AsyncMock(return_value=({}, pending))
    monkeypatch.setattr(app, "load_checkpoint", loader)
    monkeypatch.setattr(
        app,
        "get_runtime_context",
        lambda: SimpleNamespace(config=SimpleNamespace(checkpointer=object())),
    )
    request = RuntimeExecuteRequest(
        agent_id="test",
        input="",
        session_id="session-1",
        interrupt_id="interrupt-1",
        occurrence_id="call-1",
        resume_payload=answer,
    )
    if accepted:
        assert await app._validate_agent_question_answer(request) is True
    else:
        with pytest.raises(app.HTTPException) as exc:
            await app._validate_agent_question_answer(request)
        assert exc.value.status_code == 422
    loader.assert_awaited_once()


@pytest.mark.asyncio
async def test_skip_is_persisted_as_a_hitl_response() -> None:
    store = AsyncMock()
    store.next_rank.return_value = 0
    await app._write_turn_history(
        session_id="session-1",
        user_id="user-1",
        request_message=None,
        payloads=[],
        history_store=store,
        resume_payload={"skipped": True},
        occurrence_id="call-1",
    )
    rows = store.save.call_args.kwargs["messages"]
    assert len(rows) == 1
    assert rows[0].channel == Channel.hitl_response
    assert rows[0].parts[0].skipped is True
    assert rows[0].parts[0].occurrence_id == "call-1"


@pytest.mark.asyncio
async def test_tool_approval_does_not_accept_agent_question_skip(monkeypatch) -> None:
    loader = AsyncMock(
        return_value=(
            {},
            [
                (
                    "task-1",
                    "__interrupt__",
                    {
                        "id": "interrupt-1",
                        "value": {
                            "stage": "tool_approval",
                            "occurrence_id": "call-1",
                            "question": "Approve?",
                            "choices": [{"id": "proceed", "label": "Proceed"}],
                        },
                    },
                )
            ],
        )
    )
    monkeypatch.setattr(app, "load_checkpoint", loader)
    monkeypatch.setattr(
        app,
        "get_runtime_context",
        lambda: SimpleNamespace(config=SimpleNamespace(checkpointer=object())),
    )
    request = RuntimeExecuteRequest(
        agent_id="test",
        input="",
        session_id="session-1",
        interrupt_id="interrupt-1",
        occurrence_id="call-1",
        resume_payload={"skipped": True},
    )
    with pytest.raises(app.HTTPException) as exc:
        await app._validate_agent_question_answer(request)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_shared_interrupt_id_validates_the_matching_sibling(monkeypatch) -> None:
    pending = [
        (
            f"task-{index}",
            "__interrupt__",
            {
                "id": "interrupt-shared",
                "value": {
                    "stage": "agent_question",
                    "occurrence_id": f"call-{index}",
                    "question": f"Question {index}?",
                    "choices": [{"id": option, "label": option}],
                },
            },
        )
        for index, option in ((1, "first"), (2, "second"))
    ]
    monkeypatch.setattr(app, "load_checkpoint", AsyncMock(return_value=({}, pending)))
    monkeypatch.setattr(
        app,
        "get_runtime_context",
        lambda: SimpleNamespace(config=SimpleNamespace(checkpointer=object())),
    )
    request = RuntimeExecuteRequest(
        agent_id="test",
        input="",
        session_id="session-1",
        interrupt_id="interrupt-shared",
        occurrence_id="call-2",
        resume_payload={"choice_id": "first"},
    )
    with pytest.raises(app.HTTPException) as exc:
        await app._validate_agent_question_answer(request)
    assert exc.value.status_code == 422
    request.resume_payload = {"choice_id": "second"}
    assert await app._validate_agent_question_answer(request) is True
