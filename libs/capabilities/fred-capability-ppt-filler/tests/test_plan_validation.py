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
from fred_capability_ppt_filler.builder.plan import DeckPlan
from fred_capability_ppt_filler.fill import PptPreviewPart
from langchain_core.messages import HumanMessage
from port_fakes import FakeWorkspace
from story_tools import CHART, COVER, DECK, POINTS, USER, answered, build_tool, deck

pytestmark = pytest.mark.storytelling


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
async def test_skip_plan_needs_the_users_own_request(monkeypatch, deck_plan_store):
    asked = await build_tool(
        monkeypatch,
        _first_turn("Construis-la directement, sans plan. " + USER),
        validate_plan=True,
    )
    text, _ = await asked(slides=DECK, skip_plan="construis-la directement, sans plan")
    assert text.startswith("Delivered"), text
    deck_plan_store.plans.clear()  # another conversation

    not_asked = await build_tool(monkeypatch, _first_turn(), validate_plan=True)
    text, _ = await not_asked(slides=DECK, skip_plan="the user is in a hurry")
    assert text.startswith("Plan proposed")
    assert "does not ask to skip the plan" in text
    # The user's words alone, without the argument, never skip.
    words_only = await build_tool(
        monkeypatch, _first_turn("Sans plan : " + USER), validate_plan=True
    )
    text, _ = await words_only(slides=DECK)
    assert text.startswith("Plan proposed")


@pytest.mark.asyncio
async def test_a_delivered_decks_edit_never_waits(monkeypatch):
    first = await build_tool(monkeypatch, _first_turn())
    delivered, _ = await first(slides=DECK)
    build = await build_tool(
        monkeypatch,
        answered(delivered) + [HumanMessage(content="Change le titre de la slide 2")],
        validate_plan=True,
    )
    text, _ = await build(
        changes=[{"op": "edit", "slide": 2, "field": "title", "value": "Nos équipes"}]
    )
    assert text.startswith("Delivered"), text


@pytest.mark.asyncio
async def test_a_plan_with_problems_gets_a_revision_not_the_outline(monkeypatch):
    build = await build_tool(monkeypatch, _first_turn(), validate_plan=True)
    untold = {k: v for k, v in POINTS.items() if k != "takeaway"}
    text, _ = await build(slides=[COVER, untold, CHART])
    assert '"status": "needs_revision"' in text and "no takeaway" in text


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
    assert "Fred's built-in template" in builtin and "built-in" not in uploaded
    assert "uploaded in this agent's settings" in uploaded
    for rules in (builtin, uploaded):
        assert "cannot switch template" in rules and "{" not in rules
        assert "do only that (propose any other slide or content instead)" in rules
        assert "Ask which slide when the request does not say" in rules
        assert "only when build_presentation delivered it in this answer" in rules
        assert "Never invent one" in rules
