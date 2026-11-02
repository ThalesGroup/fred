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

"""Unit tests for the plain-data helper functions in `features/scheduler/workflow.py`."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("envelope", [None, "opaque-safe-envelope"])
async def test_extraction_handoff_carries_optional_context(monkeypatch, envelope):
    import logging

    from knowledge_flow_backend.features.scheduler import workflow as scoped

    calls = []

    async def execute(name, **kwargs):
        calls.append((name, kwargs))
        return {"document_uid": "doc-a"}

    monkeypatch.setattr(scoped.workflow, "execute_activity", execute)
    monkeypatch.setattr(scoped.workflow, "logger", logging.getLogger("test.workflow"))
    file = {"extraction_task_queue": "ingestion-fast"}
    if envelope is not None:
        file["logging_context"] = envelope
    user, metadata = {"uid": "person-a"}, {"document_uid": "doc-a"}
    await scoped.PushInputProcess().run(file, user, metadata, "fast")
    expected = [user, metadata, "fast"]
    if envelope is not None:
        expected += [envelope]
    assert len(calls) == 1 and calls[0][1]["args"] == expected
