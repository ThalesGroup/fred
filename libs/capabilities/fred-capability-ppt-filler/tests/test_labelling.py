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

"""Vision labelling against a fake `CapabilityModelPort`: merge, malformed
answers, refusal, port absent, toggle off. The patterns PDF is drawn with
Pillow (one blank page per pattern), so no LibreOffice and no network."""

from __future__ import annotations

import io
import json
from typing import Callable, List, Optional, Sequence

import pytest
from builder_decks import build_showcase_template
from fred_capability_ppt_filler.builder import labelling
from fred_capability_ppt_filler.builder.analysis import analyze_template
from fred_capability_ppt_filler.builder.labelling import label_inventory, parse_label
from fred_capability_ppt_filler.builder.models import TemplateInventory
from fred_capability_ppt_filler.builder.preview import (
    marked_pattern_images,
    numbered_slots,
)
from fred_sdk.contracts.runtime import (
    CapabilityModelPort,
    CapabilityModelUnavailableError,
)
from langchain_core.messages import AIMessage, BaseMessage
from PIL import Image

Responder = Callable[[Sequence[BaseMessage]], AIMessage]


class FakeModelPort(CapabilityModelPort):
    def __init__(self, respond: Responder) -> None:
        self.respond = respond
        self.calls: List[Sequence[BaseMessage]] = []
        self.require_vision: List[bool] = []

    async def ainvoke(
        self,
        messages: Sequence[BaseMessage],
        *,
        profile_id: Optional[str] = None,
        require_vision: bool = False,
    ) -> AIMessage:
        self.calls.append(messages)
        self.require_vision.append(require_vision)
        return self.respond(messages)


def _slot_count(messages: Sequence[BaseMessage]) -> int:
    content = messages[-1].content
    assert isinstance(content, list) and isinstance(content[0], dict)
    return len(str(content[0]["text"]).splitlines()) - 1


def _answer(messages: Sequence[BaseMessage]) -> AIMessage:
    slots = {str(n): f"slot {n}" for n in range(1, _slot_count(messages) + 1)}
    body = {"kind": "quote", "label": "Vision label", "slots": slots}
    body |= {"max_items": None, "reusable": False}
    return AIMessage(content="```json\n" + json.dumps(body) + "\n```")


@pytest.fixture(scope="module")
def template() -> bytes:
    return build_showcase_template()


@pytest.fixture(scope="module")
def inventory(template: bytes) -> TemplateInventory:
    result = analyze_template(template)
    assert result.inventory is not None
    return result.inventory


@pytest.fixture(scope="module")
def patterns_pdf(inventory: TemplateInventory) -> bytes:
    pages = [Image.new("RGB", (400, 225), "white") for _ in inventory.patterns]
    buffer = io.BytesIO()
    pages[0].save(buffer, format="PDF", save_all=True, append_images=pages[1:])
    return buffer.getvalue()


def _targets(inventory: TemplateInventory) -> List[str]:
    return [p.id for p in inventory.patterns if p.source == "slide" and p.included]


@pytest.mark.asyncio
async def test_valid_answers_merge_into_the_inventory(
    template: bytes, inventory: TemplateInventory, patterns_pdf: bytes
) -> None:
    port = FakeModelPort(_answer)
    labelled = await label_inventory(inventory, template, patterns_pdf, port)

    assert len(port.calls) == len(_targets(inventory)) > 0
    assert all(port.require_vision)
    image = port.calls[0][-1].content[1]
    assert isinstance(image, dict)
    assert image["image_url"]["url"].startswith("data:image/png;base64,")
    for before, after in zip(inventory.patterns, labelled.patterns):
        assert [z.box for z in after.zones] == [z.box for z in before.zones]
        if after.id not in _targets(inventory):
            assert after.labelled_by == "heuristic"
            continue
        assert after.labelled_by == "vision"
        assert after.label == "Vision label"
        assert after.reusable is False
        slots = numbered_slots(after)
        assert [z.purpose for z in slots] == [
            f"slot {n + 1}" for n in range(len(slots))
        ]
    # The input inventory is left untouched.
    assert all(p.labelled_by == "heuristic" for p in inventory.patterns)


@pytest.mark.asyncio
async def test_notes_kind_outranks_vision(
    template: bytes, inventory: TemplateInventory, patterns_pdf: bytes
) -> None:
    labelled = await label_inventory(
        inventory, template, patterns_pdf, FakeModelPort(_answer)
    )
    declared = labelling._annotated(template)
    noted = [pid for pid, (kind, _) in declared.items() if kind]
    assert noted, "the showcase deck carries an intent: note"
    for pattern in labelled.patterns:
        if pattern.id in noted and pattern.labelled_by == "vision":
            assert pattern.kind == next(
                p.kind for p in inventory.patterns if p.id == pattern.id
            )
        elif pattern.labelled_by == "vision":
            assert pattern.kind == "quote"


@pytest.mark.asyncio
async def test_malformed_answer_keeps_the_heuristic_label(
    template: bytes, inventory: TemplateInventory, patterns_pdf: bytes
) -> None:
    first = _targets(inventory)[0]
    answers = iter(
        [AIMessage(content="I think it is a cover slide.")]
        + [None] * len(_targets(inventory))
    )

    def respond(messages: Sequence[BaseMessage]) -> AIMessage:
        return next(answers) or _answer(messages)

    port = FakeModelPort(respond)
    labelled = await label_inventory(inventory, template, patterns_pdf, port)

    original = next(p for p in inventory.patterns if p.id == first)
    kept = next(p for p in labelled.patterns if p.id == first)
    assert kept == original
    assert sum(p.labelled_by == "vision" for p in labelled.patterns) == (
        len(_targets(inventory)) - 1
    )


@pytest.mark.parametrize(
    "content",
    [
        '{"kind": "poster", "label": "x", "slots": {}, "reusable": true}',
        '{"kind": "cover", "label": "", "slots": {}, "reusable": true}',
        '{"kind": "cover", "label": "x", "slots": {"9": "title"}, "reusable": true}',
        '{"kind": "cover", "label": "x", "slots": {"1": " "}, "reusable": true}',
        '{"kind": "cover", "label": "x", "slots": {}}',
        '{"kind": "cover", "label": "x", "reusable": true, "max_items": -1}',
        "not json at all",
    ],
)
def test_invalid_answers_are_rejected(content: str) -> None:
    assert parse_label(AIMessage(content=content), slot_count=2) is None


def test_answer_in_content_parts_is_parsed() -> None:
    text = '{"kind": "cards", "label": " Four cards ", "slots": {"1": "title"}, "reusable": true}'
    answer = parse_label(AIMessage(content=[{"type": "text", "text": text}]), 1)
    assert answer is not None
    assert (answer.kind, answer.label, answer.slots) == (
        "cards",
        "Four cards",
        {1: "title"},
    )


@pytest.mark.asyncio
async def test_vision_refused_stops_calls_and_keeps_heuristics(
    template: bytes,
    inventory: TemplateInventory,
    patterns_pdf: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(labelling, "LABELLING_CONCURRENCY", 1)

    def refuse(_: Sequence[BaseMessage]) -> AIMessage:
        raise CapabilityModelUnavailableError("profile does not support vision")

    port = FakeModelPort(refuse)
    labelled = await label_inventory(inventory, template, patterns_pdf, port)
    assert len(port.calls) == 1
    assert labelled == inventory


@pytest.mark.asyncio
async def test_provider_error_costs_only_that_slide(
    template: bytes, inventory: TemplateInventory, patterns_pdf: bytes
) -> None:
    calls = {"n": 0}

    def flaky(messages: Sequence[BaseMessage]) -> AIMessage:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("gateway 502")
        return _answer(messages)

    labelled = await label_inventory(
        inventory, template, patterns_pdf, FakeModelPort(flaky)
    )
    assert sum(p.labelled_by == "vision" for p in labelled.patterns) == (
        len(_targets(inventory)) - 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("port_absent, use_vision", [(True, True), (False, False)])
async def test_no_call_without_port_or_with_toggle_off(
    template: bytes,
    inventory: TemplateInventory,
    patterns_pdf: bytes,
    port_absent: bool,
    use_vision: bool,
) -> None:
    port = FakeModelPort(_answer)
    labelled = await label_inventory(
        inventory,
        template,
        patterns_pdf,
        None if port_absent else port,
        use_vision=use_vision,
    )
    assert port.calls == []
    assert labelled is inventory


@pytest.mark.asyncio
async def test_missing_pdf_keeps_heuristics(
    template: bytes, inventory: TemplateInventory
) -> None:
    port = FakeModelPort(_answer)
    assert await label_inventory(inventory, template, None, port) is inventory
    assert port.calls == []


def test_page_count_mismatch_yields_no_image(inventory: TemplateInventory) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(buffer, format="PDF")
    images = marked_pattern_images(buffer.getvalue(), inventory, _targets(inventory))
    assert images == {}


def test_marked_images_are_pngs_at_the_requested_width(
    inventory: TemplateInventory, patterns_pdf: bytes
) -> None:
    images = marked_pattern_images(
        patterns_pdf, inventory, _targets(inventory), width_px=320
    )
    assert set(images) == set(_targets(inventory))
    image = Image.open(io.BytesIO(next(iter(images.values()))))
    assert (image.format, image.width) == ("PNG", 320)
