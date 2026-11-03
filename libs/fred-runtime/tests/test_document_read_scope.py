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

"""The turn's document selection, enforced on the tools that take a uid.

`read_document`, `summarize_document` and `extract_from_document` take a uid the
MODEL produced - from a search hit, the tree, or a turn taken before the user
narrowed the scope. The adapter seam is what keeps a document the user removed
from the conversation out of the answer; the tree carries the same selection
down the wire instead of listing the whole corpus.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

import fred_runtime.integrations.v2_runtime.adapters as adapters_module
import pytest
import pytest_asyncio
from fred_core.documents.selection import DocumentScope
from fred_runtime.model_routing.turn import TurnAuthority
from fred_runtime.runtime_support.run_scope import RunScope
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from fred_sdk.contracts.runtime import DocumentScopeRefusedError, DocumentTreeResult
from weaver_fixtures import INSTANCE_ID, SPACE_ID, turn_binding

IN_SCOPE = str(UUID(int=101))
OTHER = str(UUID(int=102))
FOLDER = str(UUID(int=201))

pytestmark = pytest.mark.asyncio


class _FakeSettings:
    id: str = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


class _RecordingKfClient:
    """Stand-in for KfDocumentClient, recording what reached Knowledge Flow."""

    calls: list[tuple[str, dict[str, Any]]] = []

    def __init__(self, agent: object) -> None:
        self._agent = agent

    async def fetch_markdown(self, **kwargs: Any) -> str:
        type(self).calls.append(("fetch_markdown", kwargs))
        return "the whole document"

    async def summarize(self, **kwargs: Any):
        type(self).calls.append(("summarize", kwargs))
        return _Summary()

    async def extract(self, **kwargs: Any):
        type(self).calls.append(("extract", kwargs))
        return _Extraction()

    async def tree(self, **kwargs: Any):
        type(self).calls.append(("tree", kwargs))
        return DocumentTreeResult()


class _Summary:
    document_uid = IN_SCOPE
    summary = "a summary"
    shrunk_for_budget = False
    keywords: list[str] = []


class _Extraction:
    document_uid = IN_SCOPE
    extraction = "- one item"
    item_count = 1
    chunks_processed = 1
    truncated = False


def _binding(**runtime_kwargs: Any) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            user_id="alice",
            session_id=str(UUID(int=301)),
            team_id="team-1",
            space_id=SPACE_ID,
            agent_instance_id=INSTANCE_ID,
            **runtime_kwargs,
        ),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="u-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


@pytest_asyncio.fixture(autouse=True)
async def _patch_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(adapters_module, "KfDocumentClient", _RecordingKfClient)
    _RecordingKfClient.calls = []
    authority = TurnAuthority(
        turn_binding(
            "agent-1",
            session=str(UUID(int=301)),
            attachments=[
                dict(
                    document_id=str(UUID(int=401)),
                    name="notes.pdf",
                    mime="application/pdf",
                )
            ],
        ),
        None,
    )
    with RunScope.open() as run:
        run.turn_authority = authority
        authority.start(run)
        yield authority


async def test_markdown_read_refuses_a_uid_outside_the_selection() -> None:
    adapter = adapters_module.DocumentMarkdownAdapter(
        binding=_binding(selected_document_uids=[IN_SCOPE]),
        settings=_FakeSettings(),
    )

    with pytest.raises(DocumentScopeRefusedError) as raised:
        await adapter.fetch_markdown(OTHER)

    assert raised.value.requested_uids == (OTHER,)
    # Refused locally: Knowledge Flow was never asked for the document.
    assert _RecordingKfClient.calls == []


async def test_markdown_read_allows_a_selected_uid() -> None:
    adapter = adapters_module.DocumentMarkdownAdapter(
        binding=_binding(selected_document_uids=[IN_SCOPE]),
        settings=_FakeSettings(),
    )

    page = await adapter.fetch_markdown(IN_SCOPE)

    assert page.text == "the whole document"
    assert _RecordingKfClient.calls[0][0] == "fetch_markdown"


async def test_no_selection_bounds_nothing() -> None:
    adapter = adapters_module.DocumentMarkdownAdapter(
        binding=_binding(), settings=_FakeSettings()
    )

    page = await adapter.fetch_markdown("any-document")

    assert page.text == "the whole document"


async def test_a_folder_pick_is_forwarded_for_server_membership_verification() -> None:
    """A folder pick requires membership verification in KF, even for a known ID."""

    adapter = adapters_module.DocumentMarkdownAdapter(
        binding=_binding(
            selected_document_uids=[IN_SCOPE],
            selected_document_libraries_ids=[FOLDER],
        ),
        settings=_FakeSettings(),
    )

    page = await adapter.fetch_markdown("a-document-of-lib-a")

    assert page.text == "the whole document"
    sent = _RecordingKfClient.calls[0][1]
    assert sent["document_context"].document_scope == DocumentScope.from_ids(
        [FOLDER], [IN_SCOPE]
    )
    assert str(sent["document_context"].space_id) == SPACE_ID


@pytest.mark.parametrize("operation", ["read", "summarize", "extract"])
@pytest.mark.parametrize("enabled", [False, True])
async def test_attachment_access_is_independent_of_corpus_selection(
    _patch_client, operation, enabled
):
    context = _binding(selected_document_uids=[])
    _patch_client.bind_documents(
        context.runtime_context, DocumentScope(), attachments_enabled=enabled
    )
    classes = {
        "read": adapters_module.DocumentMarkdownAdapter,
        "summarize": adapters_module.DocumentSummarizeAdapter,
        "extract": adapters_module.DocumentExtractionAdapter,
    }
    adapter = classes[operation](binding=context, settings=_FakeSettings())

    async def read():
        uid = str(UUID(int=401))
        if operation == "read":
            return await adapter.fetch_markdown(uid)
        if operation == "summarize":
            return await adapter.summarize(uid)
        return await adapter.extract(uid, instruction="all")

    if enabled:
        await read()
        sent = _RecordingKfClient.calls[0][1]["document_context"]
        assert sent.document_scope.is_empty
        assert sent.attachment_ids == (UUID(int=401),)
    else:
        with pytest.raises(DocumentScopeRefusedError):
            await read()
        assert _RecordingKfClient.calls == []


async def test_injected_attachment_cannot_expand_binding(_patch_client):
    context = _binding(selected_document_uids=[])
    _patch_client.bind_documents(
        context.runtime_context, DocumentScope(), attachments_enabled=True
    )
    adapter = adapters_module.DocumentMarkdownAdapter(
        binding=context, settings=_FakeSettings()
    )
    with pytest.raises(DocumentScopeRefusedError):
        await adapter.fetch_markdown(str(UUID(int=999)))
    assert _RecordingKfClient.calls == []


async def test_summarize_refuses_a_uid_outside_the_selection() -> None:
    adapter = adapters_module.DocumentSummarizeAdapter(
        binding=_binding(selected_document_uids=[IN_SCOPE]),
        settings=_FakeSettings(),
    )

    with pytest.raises(DocumentScopeRefusedError):
        await adapter.summarize(OTHER)

    assert _RecordingKfClient.calls == []


async def test_extract_refuses_a_uid_outside_the_selection() -> None:
    adapter = adapters_module.DocumentExtractionAdapter(
        binding=_binding(selected_document_uids=[IN_SCOPE]),
        settings=_FakeSettings(),
    )

    with pytest.raises(DocumentScopeRefusedError):
        await adapter.extract(OTHER, instruction="list every risk")

    assert _RecordingKfClient.calls == []


@pytest.mark.parametrize(
    "ceiling",
    [
        DocumentScope(),
        DocumentScope.from_ids([], []),
        DocumentScope.from_ids([FOLDER]),
        DocumentScope.from_ids(document_ids=[OTHER]),
    ],
)
async def test_tree_intersects_explicit_selection_with_turn_and_excludes_attachments(
    ceiling,
) -> None:
    adapter = adapters_module.DocumentTreeAdapter(
        binding=_binding(selected_document_uids=[IN_SCOPE]), settings=_FakeSettings()
    )
    await adapter.tree(folder_id=FOLDER, document_scope=ceiling, limit=42)
    name, kwargs = _RecordingKfClient.calls[0]
    assert name == "tree"
    context = kwargs["document_context"]
    assert context.document_scope == ceiling.intersect(
        DocumentScope.from_ids(document_ids=[IN_SCOPE])
    )
    assert context.attachment_ids == ()
    assert kwargs["folder_id"] == FOLDER
    assert kwargs["limit"] == 42


async def test_tree_without_selection_sends_unfiltered_corpus_context() -> None:
    adapter = adapters_module.DocumentTreeAdapter(
        binding=_binding(), settings=_FakeSettings()
    )
    await adapter.tree()
    assert (
        _RecordingKfClient.calls[0][1]["document_context"].document_scope
        == DocumentScope()
    )


async def test_tree_general_only_never_calls_kf() -> None:
    adapter = adapters_module.DocumentTreeAdapter(
        binding=_binding(search_rag_scope="general_only"), settings=_FakeSettings()
    )
    assert await adapter.tree() == DocumentTreeResult()
    assert _RecordingKfClient.calls == []


@pytest.mark.parametrize("operation", ["read", "summarize", "extract"])
async def test_agent_ceiling_applies_to_every_direct_read(operation: str) -> None:
    classes = {
        "read": adapters_module.DocumentMarkdownAdapter,
        "summarize": adapters_module.DocumentSummarizeAdapter,
        "extract": adapters_module.DocumentExtractionAdapter,
    }
    adapter = classes[operation](
        binding=_binding(),
        settings=_FakeSettings(),
        document_scope=DocumentScope.from_ids(document_ids=[IN_SCOPE]),
    )
    with pytest.raises(DocumentScopeRefusedError):
        if operation == "read":
            await adapter.fetch_markdown(OTHER)
        elif operation == "summarize":
            await adapter.summarize(OTHER)
        else:
            await adapter.extract(OTHER, instruction="all")
    assert _RecordingKfClient.calls == []


async def test_removing_last_document_never_opens_the_corpus() -> None:
    adapter = adapters_module.DocumentMarkdownAdapter(
        binding=_binding(selected_document_uids=[]), settings=_FakeSettings()
    )
    with pytest.raises(DocumentScopeRefusedError):
        await adapter.fetch_markdown(IN_SCOPE)
    assert _RecordingKfClient.calls == []


async def test_folder_ceiling_and_explicit_document_turn_are_both_forwarded() -> None:
    ceiling = DocumentScope.from_ids([FOLDER])
    adapter = adapters_module.DocumentMarkdownAdapter(
        binding=_binding(selected_document_uids=[IN_SCOPE]),
        settings=_FakeSettings(),
        document_scope=ceiling,
    )
    await adapter.fetch_markdown(IN_SCOPE)
    assert _RecordingKfClient.calls[0][1][
        "document_context"
    ].document_scope == ceiling.intersect(
        DocumentScope.from_ids(document_ids=[IN_SCOPE])
    )


async def test_reset_inherits_agent_selection() -> None:
    ceiling = DocumentScope.from_ids(document_ids=[IN_SCOPE])
    adapter = adapters_module.DocumentMarkdownAdapter(
        binding=_binding(selected_document_uids=None),
        settings=_FakeSettings(),
        document_scope=ceiling,
    )
    await adapter.fetch_markdown(IN_SCOPE)
    with pytest.raises(DocumentScopeRefusedError):
        await adapter.fetch_markdown(OTHER)
    assert len(_RecordingKfClient.calls) == 1


async def test_cached_page_remains_subject_to_terminal_turn_authority() -> None:
    from fred_runtime.runtime_support.authority import AuthorityLostError

    adapter = adapters_module.DocumentMarkdownAdapter(
        binding=_binding(), settings=_FakeSettings()
    )
    await adapter.fetch_markdown(IN_SCOPE)
    adapters_module.current_turn().close()
    with pytest.raises(AuthorityLostError):
        await adapter.fetch_markdown(IN_SCOPE)
    assert len(_RecordingKfClient.calls) == 1


async def test_tree_maps_transport_errors_and_preserves_authority_loss(
    monkeypatch,
) -> None:
    from unittest.mock import AsyncMock

    import httpx
    from fred_runtime.runtime_support.authority import AuthorityLostError
    from fred_sdk.contracts.runtime import DocumentPortCallError

    adapter = adapters_module.DocumentTreeAdapter(
        binding=_binding(), settings=_FakeSettings()
    )
    monkeypatch.setattr(
        adapter._client, "tree", AsyncMock(side_effect=httpx.ReadTimeout("slow"))
    )
    with pytest.raises(DocumentPortCallError) as error:
        await adapter.tree()
    assert error.value.timed_out
    monkeypatch.setattr(
        adapter._client, "tree", AsyncMock(side_effect=AuthorityLostError())
    )
    with pytest.raises(AuthorityLostError):
        await adapter.tree()
