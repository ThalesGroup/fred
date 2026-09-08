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

"""
Offline unit tests for `sync_pull_knowledge_base` (docs/swift/rfc/KNOWLEDGE-BASE-RFC.md
§10 plan step 2).

Ingestion primitives (`extract_metadata`, `save_input`, `push_input_process`,
`output_process`, `delete_document_and_artifacts`) are mocked — same
convention as `tests/core/test_in_memory_scheduler_task_events.py` — so these
tests prove the sync orchestration (state tracking, upsert/delete/changed
handling) without a real embedding/vector pipeline. The connector itself is
already proven for real against a filesystem in
`tests/core/connectors/test_local_filesystem_connector.py`.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
from unittest.mock import AsyncMock, MagicMock

from fred_core import KeycloakUser
from fred_sdk.contracts.connector import ChangeKind, SourceChange, SourceItem
from fred_sdk.contracts.knowledge_base import KnowledgeBase, KnowledgeBaseKind, KnowledgeBaseMode, KnowledgeBaseScope, KnowledgeBaseType

from knowledge_flow_backend.features.scheduler import pull_knowledge_base_sync as sync_module


def _user() -> KeycloakUser:
    return KeycloakUser(uid="sync-user", username="sync", email="sync@localhost", roles=["admin"])


def _knowledge_base_type(*, mode: KnowledgeBaseMode = KnowledgeBaseMode.PULL) -> KnowledgeBaseType:
    if mode is KnowledgeBaseMode.PULL:
        return KnowledgeBaseType(
            knowledge_base_type_id="local_fs_rag",
            name="Local filesystem knowledge base",
            kind=KnowledgeBaseKind.RAG_SQL,
            mode=KnowledgeBaseMode.PULL,
            connector_kind="local_fs",
        )
    return KnowledgeBaseType(
        knowledge_base_type_id="local_fs_rag",
        name="Local filesystem knowledge base",
        kind=KnowledgeBaseKind.RAG_SQL,
        mode=KnowledgeBaseMode.PUSH,
    )


def _knowledge_base(*, knowledge_base_type_id: str = "local_fs_rag") -> KnowledgeBase:
    return KnowledgeBase(
        knowledge_base_id="kb-1",
        name="Team FS knowledge base",
        knowledge_base_type_id=knowledge_base_type_id,
        scope=KnowledgeBaseScope(team_id="team-1", tag_ids=["tag-a"]),
        connector_ref="conn-1",
    )


class _ScriptedConnector:
    """Returns one scripted (changes, cursor) pair per call, in order."""

    def __init__(self, script: list[tuple[list[SourceChange], str]]) -> None:
        self._script = list(script)
        self.fetch_calls: list[SourceItem] = []

    def discover_changes(self, cursor: str | None) -> tuple[list[SourceChange], str]:
        return self._script.pop(0)

    def fetch(self, item: SourceItem, destination_dir: pathlib.Path) -> pathlib.Path:
        self.fetch_calls.append(item)
        destination_dir.mkdir(parents=True, exist_ok=True)
        local_path = destination_dir / item.display_path
        local_path.write_text("content")
        return local_path


def _patch_ingestion(monkeypatch, *, document_uid: str = "doc-1"):
    metadata = MagicMock()
    metadata.document_uid = document_uid
    metadata.source = MagicMock()

    ingestion_service = MagicMock()
    ingestion_service.extract_metadata = AsyncMock(return_value=metadata)
    ingestion_service.save_input = MagicMock()

    monkeypatch.setattr(sync_module, "get_ingestion_service", lambda: ingestion_service)
    monkeypatch.setattr(sync_module, "push_input_process", AsyncMock(return_value=metadata))
    monkeypatch.setattr(sync_module, "output_process", AsyncMock(return_value=metadata))

    delete_mock = AsyncMock()
    monkeypatch.setattr(sync_module, "MetadataService", MagicMock(return_value=MagicMock(delete_document_and_artifacts=delete_mock)))

    return ingestion_service, delete_mock


def test_rejects_push_mode_knowledge_base_type() -> None:
    try:
        asyncio.run(
            sync_module.sync_pull_knowledge_base(
                user=_user(),
                knowledge_base=_knowledge_base(),
                knowledge_base_type=_knowledge_base_type(mode=KnowledgeBaseMode.PUSH),
                connector=_ScriptedConnector([]),
                state=None,
            )
        )
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_rejects_mismatched_knowledge_base_type_id() -> None:
    try:
        asyncio.run(
            sync_module.sync_pull_knowledge_base(
                user=_user(),
                knowledge_base=_knowledge_base(knowledge_base_type_id="other_type"),
                knowledge_base_type=_knowledge_base_type(),
                connector=_ScriptedConnector([]),
                state=None,
            )
        )
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_upsert_ingests_new_file_and_records_state(monkeypatch) -> None:
    _patch_ingestion(monkeypatch, document_uid="doc-1")
    item = SourceItem(source_item_id="a.txt", revision="rev-1", display_path="a.txt")
    connector = _ScriptedConnector([([SourceChange(item=item, kind=ChangeKind.UPSERT)], "cursor-1")])

    next_state = asyncio.run(sync_module.sync_pull_knowledge_base(user=_user(), knowledge_base=_knowledge_base(), knowledge_base_type=_knowledge_base_type(), connector=connector, state=None))

    parsed = json.loads(next_state)
    assert parsed["connector_cursor"] == "cursor-1"
    assert parsed["documents"] == {"a.txt": "doc-1"}
    assert len(connector.fetch_calls) == 1


def test_second_sync_with_no_changes_makes_no_ingestion_calls(monkeypatch) -> None:
    ingestion_service, delete_mock = _patch_ingestion(monkeypatch)
    connector = _ScriptedConnector([([], "cursor-1")])
    state = json.dumps({"connector_cursor": "cursor-0", "documents": {"a.txt": "doc-1"}})

    next_state = asyncio.run(sync_module.sync_pull_knowledge_base(user=_user(), knowledge_base=_knowledge_base(), knowledge_base_type=_knowledge_base_type(), connector=connector, state=state))

    assert json.loads(next_state) == {"connector_cursor": "cursor-1", "documents": {"a.txt": "doc-1"}}
    ingestion_service.extract_metadata.assert_not_called()
    delete_mock.assert_not_called()


def test_delete_change_removes_document_and_state(monkeypatch) -> None:
    _, delete_mock = _patch_ingestion(monkeypatch)
    item = SourceItem(source_item_id="a.txt", revision="rev-1", display_path="a.txt")
    connector = _ScriptedConnector([([SourceChange(item=item, kind=ChangeKind.DELETE)], "cursor-1")])
    state = json.dumps({"connector_cursor": "cursor-0", "documents": {"a.txt": "doc-1"}})

    next_state = asyncio.run(sync_module.sync_pull_knowledge_base(user=_user(), knowledge_base=_knowledge_base(), knowledge_base_type=_knowledge_base_type(), connector=connector, state=state))

    delete_mock.assert_awaited_once_with(_user(), "doc-1")
    assert json.loads(next_state)["documents"] == {}


def test_changed_content_deletes_old_document_then_recreates(monkeypatch) -> None:
    _, delete_mock = _patch_ingestion(monkeypatch, document_uid="doc-2")
    item = SourceItem(source_item_id="a.txt", revision="rev-2", display_path="a.txt")
    connector = _ScriptedConnector([([SourceChange(item=item, kind=ChangeKind.UPSERT)], "cursor-1")])
    state = json.dumps({"connector_cursor": "cursor-0", "documents": {"a.txt": "doc-1"}})

    next_state = asyncio.run(sync_module.sync_pull_knowledge_base(user=_user(), knowledge_base=_knowledge_base(), knowledge_base_type=_knowledge_base_type(), connector=connector, state=state))

    delete_mock.assert_awaited_once_with(_user(), "doc-1")
    assert json.loads(next_state)["documents"] == {"a.txt": "doc-2"}
