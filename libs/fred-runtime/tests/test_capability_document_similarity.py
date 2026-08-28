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

"""`DocumentSimilarityCapability` - targeted document-to-document comparison.

Covers the boot invariant, the hard split (no runtime state in the tool
schema), argument handling at the seam the model drives, and the two places
this capability deliberately differs from its `document_access` sibling:
targeting is mandatory, and a weak match is still a citable source.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from importlib.metadata import EntryPoint
from typing import Any

import pytest
from fred_core.store.vector_search import DATASET_POINTER_CHUNK_KIND, VectorSearchHit
from fred_runtime.capabilities import build_capability_context
from fred_runtime.capabilities.document_similarity import DocumentSimilarityCapability
from fred_runtime.capabilities.errors import DuplicateCapabilityIdError
from fred_runtime.capabilities.registry import (
    FRED_CAPABILITIES_ENTRY_POINT_GROUP,
    CapabilityRegistry,
)
from fred_sdk.contracts.capability import CapabilityContext, CapabilityIdentity
from fred_sdk.contracts.runtime import (
    DocumentPortCallError,
    DocumentScopeRefusedError,
    DocumentSearchResult,
    DocumentSimilarityPort,
    RuntimeServices,
)

_ENTRY_POINT_VALUE = (
    "fred_runtime.capabilities.document_similarity:DocumentSimilarityCapability"
)


def _hit(
    uid: str, score: float = 1.0, chunk_kind: str | None = None
) -> VectorSearchHit:
    return VectorSearchHit(
        uid=uid,
        title=f"Doc {uid}",
        content="body",
        score=score,
        type="document",
        chunk_kind=chunk_kind,
    )


def _identity() -> CapabilityIdentity:
    return CapabilityIdentity(user_id="u-1", session_id="s-1", team_id=None)


class _FakePort(DocumentSimilarityPort):
    """Records the parameters the capability handed the port."""

    def __init__(
        self,
        hits: Sequence[VectorSearchHit] = (),
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._hits = tuple(hits)
        self._error = error

    async def find_similar(
        self,
        anchor: str,
        *,
        document_uids: Sequence[str],
        top_k: int = 10,
        rerank: bool = True,
        min_score: float | None = None,
    ) -> DocumentSearchResult:
        self.calls.append(
            {
                "anchor": anchor,
                "document_uids": list(document_uids),
                "top_k": top_k,
                "rerank": rerank,
                "min_score": min_score,
            }
        )
        if self._error is not None:
            raise self._error
        return DocumentSearchResult(hits=self._hits)


def _ctx(
    port: DocumentSimilarityPort | None = None,
    config: dict[str, Any] | None = None,
) -> CapabilityContext[Any, Any]:
    return build_capability_context(
        DocumentSimilarityCapability(),
        identity=_identity(),
        services=RuntimeServices(document_similarity=port),
        config=config or {},
    )


def _tool(ctx: CapabilityContext[Any, Any]):
    cap = DocumentSimilarityCapability()
    middleware = cap.middleware(ctx)
    assert len(middleware) == 1
    tools = {t.name: t for t in middleware[0].tools}  # type: ignore[attr-defined]
    assert set(tools) == {"find_similar_passages"}
    return tools["find_similar_passages"]


async def _invoke(ctx: CapabilityContext[Any, Any], args: dict[str, Any]):
    """Returns the `ToolMessage` create_agent's tool loop builds: `.content` is
    the model-facing string, `.artifact` the `ToolInvocationResult`."""
    return await _tool(ctx).ainvoke(
        {"type": "tool_call", "name": "find_similar_passages", "args": args, "id": "c1"}
    )


# ---------------------------------------------------------------------------
# Registration / boot invariant
# ---------------------------------------------------------------------------


def test_entry_point_registers_and_passes_boot_validation() -> None:
    registry = CapabilityRegistry()
    entry = EntryPoint(
        name="document_similarity",
        value=_ENTRY_POINT_VALUE,
        group=FRED_CAPABILITIES_ENTRY_POINT_GROUP,
    )

    assert registry.discover(entry_points=[entry]) == ["document_similarity"]
    assert isinstance(
        registry.capability("document_similarity"), DocumentSimilarityCapability
    )
    registry.validate(env={})


def test_double_registration_trips_boot_invariant() -> None:
    registry = CapabilityRegistry()
    registry.register(DocumentSimilarityCapability())
    with pytest.raises(DuplicateCapabilityIdError):
        registry.register(DocumentSimilarityCapability())


def test_tool_schema_exposes_only_llm_arguments() -> None:
    """The hard split (RFC §3.5): config and identity reach the tool through the
    closure, never the schema the model sees."""
    schema = _tool(_ctx(_FakePort())).args_schema.model_json_schema()  # type: ignore[union-attr]

    assert set(schema["properties"]) == {"anchor", "document_uids", "top_k"}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forwards_the_call_and_returns_ranked_hits() -> None:
    port = _FakePort(hits=(_hit("d1", 0.9), _hit("d2", 0.4)))
    ctx = _ctx(port, config={"default_top_k": 7, "rerank": False, "min_score": 0.3})

    message = await _invoke(
        ctx, {"anchor": "the service exposes a REST API", "document_uids": ["doc-b"]}
    )

    assert port.calls == [
        {
            "anchor": "the service exposes a REST API",
            "document_uids": ["doc-b"],
            # Config supplies the defaults the model did not give.
            "top_k": 7,
            "rerank": False,
            "min_score": 0.3,
        }
    ]
    payload = json.loads(message.content)
    assert payload["anchor"] == "the service exposes a REST API"
    assert [hit["uid"] for hit in payload["hits"]] == ["d1", "d2"]
    # LLM slice: citation/reasoning fields only, no operational fields.
    assert set(payload["hits"][0]) <= {
        "uid",
        "title",
        "content",
        "file_name",
        "page",
        "section",
        "score",
    }
    assert message.artifact.tool_ref == "document_similarity"
    assert not message.artifact.is_error


@pytest.mark.asyncio
async def test_a_weak_match_stays_citable_but_a_dataset_pointer_never_is() -> None:
    """Where this deliberately differs from document_access: the caller named
    the documents, so a low-scoring hit is a real finding, not corpus noise.
    Dataset pointers are still metadata and still never citable."""
    port = _FakePort(
        hits=(
            _hit("d1", 0.9),
            _hit("d2", 0.02),
            _hit("d3", 0.8, chunk_kind=DATASET_POINTER_CHUNK_KIND),
        )
    )

    message = await _invoke(_ctx(port), {"anchor": "x", "document_uids": ["doc-b"]})

    assert [hit.uid for hit in message.artifact.sources] == ["d1", "d2"]


@pytest.mark.asyncio
async def test_model_supplied_top_k_is_clamped_to_the_declared_ceiling() -> None:
    port = _FakePort()

    await _invoke(
        _ctx(port), {"anchor": "x", "document_uids": ["doc-b"], "top_k": 5000}
    )

    assert port.calls[0]["top_k"] == 50


@pytest.mark.asyncio
async def test_a_nonsense_top_k_falls_back_to_the_configured_default() -> None:
    port = _FakePort()

    await _invoke(
        _ctx(port, config={"default_top_k": 4}),
        {"anchor": "x", "document_uids": ["doc-b"], "top_k": -1},
    )

    assert port.calls[0]["top_k"] == 4


# ---------------------------------------------------------------------------
# Malformed calls and failures - all degrade, none raise past the tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "args",
    [
        {"anchor": "   ", "document_uids": ["doc-b"]},
        {"anchor": "x", "document_uids": []},
    ],
    ids=["blank-anchor", "no-target"],
)
async def test_a_malformed_call_is_an_error_artifact_and_never_reaches_the_port(
    args: dict[str, Any],
) -> None:
    port = _FakePort()

    message = await _invoke(_ctx(port), args)

    assert message.artifact.is_error
    assert message.content
    # Targeting is the point of this mode: an empty target must never widen
    # into a corpus-wide search.
    assert port.calls == []


@pytest.mark.asyncio
async def test_a_port_failure_degrades_to_an_error_artifact() -> None:
    """A raised exception would be re-raised by the default ToolNode handler and
    take the whole turn down with an empty error detail."""
    port = _FakePort(error=DocumentPortCallError("kf exploded"))

    message = await _invoke(_ctx(port), {"anchor": "x", "document_uids": ["doc-b"]})

    assert message.artifact.is_error
    assert "find similar passages" in message.content


@pytest.mark.asyncio
async def test_a_missing_port_fails_loudly() -> None:
    """A capability wired without its port must not look like 'no matches'."""
    with pytest.raises(RuntimeError, match="document_similarity"):
        await _invoke(_ctx(None), {"anchor": "x", "document_uids": ["doc-b"]})


@pytest.mark.asyncio
async def test_a_scope_refusal_is_never_rendered_as_no_matches() -> None:
    """The adapter refused because nothing was searched. If that reached the
    model as an empty hit list it would report 'nothing in that document
    resembles this passage' about a document it never looked at."""
    port = _FakePort(
        error=DocumentScopeRefusedError("out of scope", requested_uids=("doc-x",))
    )

    message = await _invoke(_ctx(port), {"anchor": "x", "document_uids": ["doc-x"]})

    assert message.artifact.is_error
    assert "doc-x" in message.content
    assert "NOT a 'no matches' answer" in message.content
    # Not the transport wording - nothing failed downstream.
    assert "Knowledge Flow" not in message.content
