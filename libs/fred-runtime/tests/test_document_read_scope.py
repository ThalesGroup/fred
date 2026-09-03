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

import fred_runtime.integrations.v2_runtime.adapters as adapters_module
import pytest
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from fred_sdk.contracts.runtime import DocumentScopeRefusedError

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
        return _Tree()


class _Summary:
    document_uid = "in-scope"
    summary = "a summary"
    shrunk_for_budget = False
    keywords: list[str] = []


class _Extraction:
    document_uid = "in-scope"
    extraction = "- one item"
    item_count = 1
    chunks_processed = 1
    truncated = False


class _Tree:
    tree = "Sales/"
    truncated = False


def _binding(**runtime_kwargs: Any) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id="s-1", team_id="team-1", **runtime_kwargs
        ),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="u-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapters_module, "KfDocumentClient", _RecordingKfClient)
    _RecordingKfClient.calls = []


async def test_markdown_read_refuses_a_uid_outside_the_selection() -> None:
    adapter = adapters_module.DocumentMarkdownAdapter(
        binding=_binding(selected_document_uids=["in-scope"]),
        settings=_FakeSettings(),
    )

    with pytest.raises(DocumentScopeRefusedError) as raised:
        await adapter.fetch_markdown("other-document")

    assert raised.value.requested_uids == ("other-document",)
    # Refused locally: Knowledge Flow was never asked for the document.
    assert _RecordingKfClient.calls == []


async def test_markdown_read_allows_a_selected_uid() -> None:
    adapter = adapters_module.DocumentMarkdownAdapter(
        binding=_binding(selected_document_uids=["in-scope"]),
        settings=_FakeSettings(),
    )

    page = await adapter.fetch_markdown("in-scope")

    assert page.text == "the whole document"
    assert _RecordingKfClient.calls[0][0] == "fetch_markdown"


async def test_no_selection_bounds_nothing() -> None:
    adapter = adapters_module.DocumentMarkdownAdapter(
        binding=_binding(), settings=_FakeSettings()
    )

    page = await adapter.fetch_markdown("any-document")

    assert page.text == "the whole document"


async def test_a_library_pick_disarms_the_gate() -> None:
    """Library and document picks UNION, and a library cannot be resolved to its
    documents pod-side - so enforcing the document list alone would refuse a
    document the user selected through its library."""

    adapter = adapters_module.DocumentMarkdownAdapter(
        binding=_binding(
            selected_document_uids=["in-scope"],
            selected_document_libraries_ids=["lib-a"],
        ),
        settings=_FakeSettings(),
    )

    page = await adapter.fetch_markdown("a-document-of-lib-a")

    assert page.text == "the whole document"


async def test_an_attached_file_stays_readable_under_a_corpus_selection() -> None:
    """The picker lists the corpus, so an attachment uid is never in the
    selection - refusing it would make the conversation's own files unreadable
    while the attachment prompt tells the model to read them by uid."""

    adapter = adapters_module.DocumentMarkdownAdapter(
        binding=_binding(
            selected_document_uids=["in-scope"],
            attachments_markdown=(
                "## Attached files for this conversation\n"
                "- notes.pdf [attached-1]: conversation document"
            ),
        ),
        settings=_FakeSettings(),
    )

    page = await adapter.fetch_markdown("attached-1")

    assert page.text == "the whole document"


async def test_summarize_refuses_a_uid_outside_the_selection() -> None:
    adapter = adapters_module.DocumentSummarizeAdapter(
        binding=_binding(selected_document_uids=["in-scope"]),
        settings=_FakeSettings(),
    )

    with pytest.raises(DocumentScopeRefusedError):
        await adapter.summarize("other-document")

    assert _RecordingKfClient.calls == []


async def test_extract_refuses_a_uid_outside_the_selection() -> None:
    adapter = adapters_module.DocumentExtractionAdapter(
        binding=_binding(selected_document_uids=["in-scope"]),
        settings=_FakeSettings(),
    )

    with pytest.raises(DocumentScopeRefusedError):
        await adapter.extract("other-document", instruction="list every risk")

    assert _RecordingKfClient.calls == []


async def test_tree_carries_the_selection_down_the_wire() -> None:
    adapter = adapters_module.DocumentTreeAdapter(
        binding=_binding(selected_document_uids=["a", "b"]),
        settings=_FakeSettings(),
    )

    await adapter.tree(document_uids=["b", "c"])

    name, kwargs = _RecordingKfClient.calls[0]
    assert name == "tree"
    # `params ⊆ session_binding`: "c" was never in the conversation's selection.
    assert kwargs["document_uids"] == ["b"]


async def test_tree_without_a_selection_sends_no_document_filter() -> None:
    adapter = adapters_module.DocumentTreeAdapter(
        binding=_binding(), settings=_FakeSettings()
    )

    await adapter.tree()

    assert _RecordingKfClient.calls[0][1]["document_uids"] is None
