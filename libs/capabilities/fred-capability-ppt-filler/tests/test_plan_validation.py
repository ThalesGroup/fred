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

"""The "Validate the plan before building" setting: the first build of a
conversation returns an outline, the next one after the user's answer builds,
a skip needs the user's own words, a delivered deck's edits never wait."""

from __future__ import annotations

import json

import pytest
from fred_capability_ppt_filler.builder import capability as capability_mod
from fred_capability_ppt_filler.builder import tools
from fred_capability_ppt_filler.builder.builtin import builtin_template
from fred_capability_ppt_filler.builder.capability import (
    PptBuilderCapability,
    PptBuilderConfig,
)
from fred_capability_ppt_filler.builder.plan import DeckPlan
from fred_capability_ppt_filler.fill import PptPreviewPart
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.runtime import RuntimeServices
from langchain_core.messages import AIMessage, HumanMessage
from port_fakes import FakeWorkspace
from story_tools import CHART, COVER, DECK, POINTS, USER, answered, build_tool, deck


@pytest.fixture(autouse=True)
def preview_union():
    from fred_sdk.contracts.ui_part_union import rebuild_ui_part_union

    rebuild_ui_part_union([PptPreviewPart])
    yield
    rebuild_ui_part_union(())


def _first_turn(user: str = USER):
    return [HumanMessage(content=user)]


@pytest.mark.asyncio
async def test_setting_off_builds_directly(monkeypatch):
    build = await build_tool(monkeypatch, _first_turn())
    text, _ = await build(slides=DECK, skip_plan="whatever")
    assert text.startswith("Delivered"), text


@pytest.mark.asyncio
async def test_the_first_build_returns_the_outline_and_stores_the_plan(
    monkeypatch, deck_plan_store
):
    workspace = FakeWorkspace()
    build = await build_tool(
        monkeypatch, _first_turn(), validate_plan=True, workspace=workspace
    )
    text, result = await build(
        slides=DECK, audience="Comité de direction", main_message="Recruter en Italie"
    )
    assert (
        text.startswith("Plan proposed: nothing was built yet.") and not result.is_error
    )
    assert not workspace.writes
    assert "Audience: Comité de direction" in text
    assert "Main message: Recruter en Italie" in text
    lines = [line for line in text.splitlines() if line[:2] in ("1.", "2.", "3.")]
    assert lines[1] == (f"2. bullets — {POINTS['title']} — {POINTS['takeaway']} — —")
    assert lines[2] == (
        f"3. chart — {CHART['title']} — {CHART['takeaway']} — {CHART['source']}"
    )
    (stored,) = deck_plan_store.plans.values()
    plan = DeckPlan.model_validate_json(stored)
    assert plan.proposed and not plan.delivered and len(plan.slides) == 3
    # A second call before the user answers gets the outline again.
    again, _ = await build(slides=DECK)
    assert again.startswith("Plan proposed") and not workspace.writes


@pytest.mark.asyncio
async def test_the_outline_carries_no_notes_the_delivery_tells_them(
    monkeypatch, deck_plan_store
):
    """Owner decision: a proposal has nothing for the model to relay but the
    outline; what was adapted is told once the deck is delivered."""
    early = [COVER, {**POINTS, "kind": "closing"}, CHART]
    fact = (
        "Slide 2: built as 'section' instead of 'closing': a closing slide can only "
        "end the deck."
    )
    gated = await build_tool(monkeypatch, _first_turn(), validate_plan=True)
    proposed, _ = await gated(slides=early)
    direct = await build_tool(monkeypatch, _first_turn())
    delivered, _ = await direct(slides=early)
    assert f"{fact} To make it the closing slide, move it to the end." in delivered
    assert "instead of" not in proposed and "Notes for the user" not in proposed
    assert proposed.startswith("Plan proposed")


@pytest.mark.asyncio
async def test_after_the_users_answer_the_deck_is_built(monkeypatch):
    first = await build_tool(monkeypatch, _first_turn(), validate_plan=True)
    proposed, _ = await first(slides=DECK)
    workspace = FakeWorkspace()
    build = await build_tool(
        monkeypatch,
        answered(proposed) + [HumanMessage(content="Ok, vas-y")],
        validate_plan=True,
        workspace=workspace,
    )
    text, _ = await build(slides=DECK)
    assert text.startswith("Delivered"), text


@pytest.mark.asyncio
async def test_a_correction_applies_to_the_proposed_plan(monkeypatch):
    first = await build_tool(monkeypatch, _first_turn(), validate_plan=True)
    proposed, _ = await first(slides=DECK)
    workspace = FakeWorkspace()
    build = await build_tool(
        monkeypatch,
        answered(proposed) + [HumanMessage(content="Enlève la slide 3")],
        validate_plan=True,
        workspace=workspace,
    )
    text, _ = await build(changes=[{"op": "remove", "slide": 3}])
    assert text.startswith("Delivered"), text
    assert len(deck(workspace).slides) == 2


@pytest.mark.asyncio
async def test_skip_plan_is_the_model_s_call_in_any_language(
    monkeypatch, deck_plan_store
):
    """No word list second-guesses the field: the model quotes the request."""
    asked = await build_tool(
        monkeypatch,
        _first_turn("Hazlo directamente, sin plan. " + USER),
        validate_plan=True,
    )
    text, _ = await asked(slides=DECK, skip_plan="hazlo directamente, sin plan")
    assert text.startswith("Delivered"), text
    deck_plan_store.plans.clear()  # another conversation
    # The user's words alone, without the argument, never skip.
    words_only = await build_tool(
        monkeypatch, _first_turn("Sans plan : " + USER), validate_plan=True
    )
    text, _ = await words_only(slides=DECK)
    assert text.startswith("Plan proposed")


@pytest.mark.asyncio
async def test_a_skip_quote_the_user_never_wrote_proposes_the_plan(
    monkeypatch, deck_plan_store
):
    """Live: medium invented "sans validation intermédiaire" to force a build."""
    build = await build_tool(monkeypatch, _first_turn(), validate_plan=True)
    text, _ = await build(
        slides=DECK, skip_plan="Prépare la présentation sans validation intermédiaire"
    )
    assert text.startswith("Plan proposed"), text
    # Case, spacing, quote marks and punctuation may differ from the user's words.
    loose = await build_tool(
        monkeypatch,
        _first_turn("Pas de plan, construis-le ! " + USER),
        validate_plan=True,
    )
    text, _ = await loose(slides=DECK, skip_plan="« pas de  PLAN construis-le »")
    assert text.startswith("Delivered"), text


def test_a_proposal_or_a_delivery_closes_the_answer_until_the_user_speaks():
    proposed = answered("Plan proposed: nothing was built yet. Show this outline")
    delivered = answered("Delivered: 'deck.pptx', 3 slides.")
    revision = answered('Not built: needs_revision. {"status": "needs_revision"}')
    assert tools.answer_closed(proposed) and tools.answer_closed(delivered)
    # A revision or a failure still lets the model call again.
    assert not tools.answer_closed(revision)
    assert not tools.answer_closed(
        answered("No deck was built: the template could not")
    )
    assert not tools.answer_closed(proposed + [HumanMessage(content="Ok, vas-y")])
    assert tools.answer_closed(proposed + [AIMessage(content="Voici le plan")])


@pytest.mark.asyncio
async def test_the_model_call_after_a_proposal_gets_no_tool():
    """Live: medium re-called the tool after a proposal up to the call cap."""
    ctx = CapabilityContext(
        identity=CapabilityIdentity(
            user_id="u-1", session_id="s", agent_instance_id="i"
        ),
        config=PptBuilderConfig(validate_plan=True),
        turn_options=EmptyModel(),
        services=RuntimeServices(workspace_fs=FakeWorkspace()),
    )
    (middleware,) = PptBuilderCapability().middleware(ctx)
    seen: list = []

    class _Request:
        system_prompt = ""
        tools: list = []

        def __init__(self, messages: list) -> None:
            self.messages = messages

        def override(self, **update):
            seen.append(update)
            return self

    async def _handler(request):
        return request

    proposed = answered("Plan proposed: nothing was built yet.")
    for history in (proposed, _first_turn(), proposed + [HumanMessage(content="ok")]):
        await middleware.awrap_model_call(_Request(history), _handler)  # type: ignore[arg-type]
    assert [u.get("tool_choice") for u in seen] == ["none", None, None]


@pytest.mark.asyncio
async def test_a_plan_with_problems_gets_a_revision_not_the_outline(monkeypatch):
    build = await build_tool(monkeypatch, _first_turn(), validate_plan=True)
    mixed = {
        **CHART,
        "chart": {
            **CHART["chart"],
            "series": [{"name": "E", "values": ["12 %", "3 M€"]}],
        },
    }
    text, _ = await build(slides=[COVER, POINTS, mixed])
    assert '"status": "needs_revision"' in text and "chart mixes units" in text


def test_the_plan_gate_is_visible_to_the_model_only_when_it_is_on():
    """Gate on, an outline written in the chat was validated twice; gate off,
    `skip_plan` was still in every schema."""
    gated = capability_mod.build_instructions(True, validate_plan=True)
    direct = capability_mod.build_instructions(True)
    assert "never write an outline in the chat" in gated
    assert "never write an outline" not in direct
    assert "validate an outline first only when they asked" in direct
    for rules in (gated, direct):
        assert "plan_proposed" not in rules and "skip_plan" not in rules
    inventory = builtin_template()[1]
    schema = json.dumps(tools._args_schema(inventory).model_json_schema())
    assert "skip_plan" not in schema
    gate = tools._args_schema(inventory, True).model_json_schema()
    assert "skip_plan" in gate["properties"]


def test_a_proposed_plan_ends_the_answer():
    """Live loop: the model re-called the tool up to the call cap instead of
    showing the outline."""
    gated = capability_mod.build_instructions(True, validate_plan=True)
    assert "never call the tool again in that answer" in gated
    assert "its notes" not in gated


def test_a_refused_call_is_resent_as_its_result_says():
    """The rules said `changes` for the listed slides, while a refused
    `changes` call must be resent whole: the result owns the remedy."""
    rules = capability_mod.build_instructions(False)
    assert "for the listed slides" not in rules
    assert "with the fixes applied as its result says" in rules


def test_the_working_rules_name_the_template_and_keep_revisions_truthful():
    """The tool cannot switch template: the rules say which one is used and where
    another is set; a revision does only what was asked and is described from its result."""
    builtin = capability_mod.build_instructions(True)
    uploaded = capability_mod.build_instructions(False)
    assert "the platform's default template" in builtin
    assert "default template" not in uploaded
    assert "uploaded in this agent's settings" in uploaded
    for rules in (builtin, uploaded):
        assert "cannot switch template" in rules and "{" not in rules
        assert "do only that (propose any other slide or content instead)" in rules
        assert "act on the one slide it can mean" in rules
        assert "ask only when several could match" in rules
        assert "Never drop or replace a slide to keep an earlier slide count" in rules
        assert "only when build_presentation delivered it in this answer" in rules
        assert "Never invent one" in rules
