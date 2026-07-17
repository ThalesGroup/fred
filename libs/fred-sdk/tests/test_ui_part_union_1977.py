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
`UiPart` union registration (#1977, RFC AGENT-CAPABILITY-RFC §3.6/§4).

What is verified:
- the frozen base union (link/geo) rejects unknown kinds — the pinned baseline
- `rebuild_ui_part_union` folds a capability chat part into every model that
  carries `ui_parts`, including the deep OpenAI-compat embedding chain
- the rebuild is deterministic (base + exactly the given extras) and reversible
- the generated JSON schema (the OpenAPI source) includes registered parts
- `_extract_ui_parts` (OpenAI-compat) accepts registered kinds and still skips
  unknown ones instead of crashing
"""

from __future__ import annotations

import json
from typing import Iterator, Literal

import pytest
from fred_sdk.contracts.context import GeoPart, LinkPart, ToolInvocationResult
from fred_sdk.contracts.openai_compat import (
    OpenAICompletionChunk,
    _extract_ui_parts,
)
from fred_sdk.contracts.runtime import (
    FinalRuntimeEvent,
    RuntimeEvent,
    ToolResultRuntimeEvent,
)
from fred_sdk.contracts.ui_part_union import (
    current_ui_part_union,
    rebuild_ui_part_union,
)
from pydantic import BaseModel, TypeAdapter, ValidationError


class DemoCardTestPart(BaseModel):
    """A capability-contributed chat part, as `manifest.chat_parts` declares."""

    type: Literal["demo_card_test"] = "demo_card_test"
    title: str
    body: str = ""


DEMO_PART = {"type": "demo_card_test", "title": "hello", "body": "world"}
LINK_PART = {"type": "link", "href": "https://example.test/a.pdf", "title": "A"}
GEO_PART = {"type": "geo", "geojson": {"type": "FeatureCollection", "features": []}}


@pytest.fixture(autouse=True)
def _restore_base_union() -> Iterator[None]:
    """Every test leaves the process on the frozen base union."""

    yield
    rebuild_ui_part_union(())


def _tool_result(parts: list[dict]) -> dict:
    return {"tool_ref": "t", "ui_parts": parts}


# -- pinned baseline ----------------------------------------------------------


def test_base_union_accepts_link_and_geo() -> None:
    result = ToolInvocationResult.model_validate(_tool_result([LINK_PART, GEO_PART]))
    assert isinstance(result.ui_parts[0], LinkPart)
    assert isinstance(result.ui_parts[1], GeoPart)


def test_base_union_rejects_unregistered_kind() -> None:
    with pytest.raises(ValidationError):
        ToolInvocationResult.model_validate(_tool_result([DEMO_PART]))


# -- registration -------------------------------------------------------------


def test_registered_part_validates_on_tool_invocation_result() -> None:
    rebuild_ui_part_union((DemoCardTestPart,))
    result = ToolInvocationResult.model_validate(
        _tool_result([LINK_PART, DEMO_PART]),
    )
    assert isinstance(result.ui_parts[0], LinkPart)
    part = result.ui_parts[1]
    assert isinstance(part, DemoCardTestPart)
    assert part.title == "hello"


def test_registered_part_validates_on_runtime_events() -> None:
    rebuild_ui_part_union((DemoCardTestPart,))
    tool_event = ToolResultRuntimeEvent.model_validate(
        {"kind": "tool_result", "call_id": "c1", "ui_parts": [DEMO_PART]}
    )
    assert isinstance(tool_event.ui_parts[0], DemoCardTestPart)
    final_event = FinalRuntimeEvent.model_validate(
        {"kind": "final", "ui_parts": [DEMO_PART, GEO_PART]}
    )
    assert isinstance(final_event.ui_parts[0], DemoCardTestPart)
    assert isinstance(final_event.ui_parts[1], GeoPart)


def test_runtime_event_adapter_built_after_rebuild_sees_new_part() -> None:
    """Validators must resolve the union lazily — the execute-route pattern."""

    rebuild_ui_part_union((DemoCardTestPart,))
    adapter: TypeAdapter = TypeAdapter(RuntimeEvent)
    event = adapter.validate_python({"kind": "final", "ui_parts": [DEMO_PART]})
    assert isinstance(event.ui_parts[0], DemoCardTestPart)


def test_deep_embedding_chain_re_captures_extended_union() -> None:
    """OpenAICompletionChunk → FredChunkMetadata → UiPart (nested rebuild)."""

    rebuild_ui_part_union((DemoCardTestPart,))
    chunk = OpenAICompletionChunk.model_validate(
        {
            "id": "chunk-1",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": "hi"}}],
            "fred": {"ui_parts": [DEMO_PART]},
        }
    )
    assert chunk.fred is not None
    assert isinstance(chunk.fred.ui_parts[0], DemoCardTestPart)


def test_json_schema_includes_registered_part() -> None:
    """The OpenAPI source of truth: the schema names the registered part."""

    rebuild_ui_part_union((DemoCardTestPart,))
    schema = json.dumps(FinalRuntimeEvent.model_json_schema())
    assert "DemoCardTestPart" in schema
    assert "demo_card_test" in schema


# -- determinism and reversibility --------------------------------------------


def test_rebuild_is_not_cumulative_and_is_reversible() -> None:
    rebuild_ui_part_union((DemoCardTestPart,))
    ToolInvocationResult.model_validate(_tool_result([DEMO_PART]))

    rebuild_ui_part_union(())
    with pytest.raises(ValidationError):
        ToolInvocationResult.model_validate(_tool_result([DEMO_PART]))
    # The frozen members survive the round-trip.
    result = ToolInvocationResult.model_validate(_tool_result([LINK_PART, GEO_PART]))
    assert isinstance(result.ui_parts[0], LinkPart)


def test_rebuild_deduplicates_and_ignores_base_members() -> None:
    rebuild_ui_part_union((LinkPart, DemoCardTestPart, DemoCardTestPart))
    result = ToolInvocationResult.model_validate(
        _tool_result([LINK_PART, GEO_PART, DEMO_PART])
    )
    assert len(result.ui_parts) == 3


def test_current_ui_part_union_tracks_rebuilds() -> None:
    base = current_ui_part_union()
    rebuild_ui_part_union((DemoCardTestPart,))
    extended = current_ui_part_union()
    assert extended is not base
    TypeAdapter(extended).validate_python(DEMO_PART)


# -- OpenAI-compat extraction (one of the collapsed scatter points) ------------


def test_extract_ui_parts_parses_base_kinds_and_skips_unknown() -> None:
    parts = _extract_ui_parts([LINK_PART, {"type": "nope"}, GEO_PART, "junk"])
    assert len(parts) == 2
    assert isinstance(parts[0], LinkPart)
    assert isinstance(parts[1], GeoPart)


def test_extract_ui_parts_accepts_registered_capability_kind() -> None:
    rebuild_ui_part_union((DemoCardTestPart,))
    parts = _extract_ui_parts([DEMO_PART, {"type": "still_unknown"}])
    assert len(parts) == 1
    assert isinstance(parts[0], DemoCardTestPart)


def test_extract_ui_parts_passes_through_typed_instances() -> None:
    rebuild_ui_part_union((DemoCardTestPart,))
    typed = DemoCardTestPart(title="t")
    link = LinkPart(href="https://example.test", title="l")
    parts = _extract_ui_parts([typed, link])
    assert parts == [typed, link]
