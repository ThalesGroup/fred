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
from typing import Any

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
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
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
async def test_a_deck_not_ending_on_the_closing_is_refused_then_retried(monkeypatch):
    """Nothing is appended: the closing counts within the slide count asked."""
    build = await build_tool(monkeypatch, _first_turn(), validate_plan=True)
    refused, result = await build(slides=DECK, no_closing=None)
    assert refused.startswith("No deck was built") and not result.is_error
    assert '"closing": "missing"' in refused
    text, _ = await build(slides=[*DECK, {"title": "Merci"}], no_closing=None)
    assert text.startswith("Plan proposed"), text
    assert any(line.startswith("4. closing — Merci") for line in text.splitlines())
    assert not any(line.startswith("5.") for line in text.splitlines())


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


def _asked(answer: dict) -> list:
    """The model's approval question and the user's answer to it."""
    call = {"id": f"ask-{len(json.dumps(answer))}", "name": "ask_user", "args": {}}
    return [
        AIMessage(content="", tool_calls=[call]),
        ToolMessage(content=json.dumps(answer), tool_call_id=call["id"]),
    ]


APPROVED = {"status": "answered", "choice_id": "approve"}
REVISED = {"status": "answered", "text": "Enlève la slide 3"}
SKIPPED = {"status": "skipped", "instruction": "..."}


def test_a_proposal_or_a_delivery_closes_the_answer_until_the_user_speaks():
    proposed = answered("Plan proposed: nothing was built yet. Show this outline")
    delivered = answered("Delivered: 'deck.pptx', 3 slides.")
    revision = answered('Not built: needs_revision. {"status": "needs_revision"}')
    assert tools.answer_stage(proposed) == "proposed"
    assert tools.answer_stage(delivered) == "delivered"
    # A revision or a failure still lets the model call again.
    assert tools.answer_stage(revision) is None
    assert (
        tools.answer_stage(answered("No deck was built: the template could not"))
        is None
    )
    assert tools.answer_stage(proposed + [HumanMessage(content="Ok, vas-y")]) is None
    assert (
        tools.answer_stage(proposed + [AIMessage(content="Voici le plan")])
        == "proposed"
    )
    assert tools.answer_stage(proposed + _asked(APPROVED)) == "approved"
    assert tools.answer_stage(proposed + _asked(REVISED)) == "revise"
    assert tools.answer_stage(proposed + _asked(SKIPPED)) == "skipped"


def test_only_the_approve_button_approves_a_plan():
    proposed = answered("Plan proposed: nothing was built yet.")
    assert tools.plan_approved(proposed + _asked(APPROVED))
    assert not tools.plan_approved(proposed + _asked(REVISED))
    assert not tools.plan_approved(proposed + _asked(SKIPPED))
    assert not tools.plan_approved(proposed)
    # Asked and answered otherwise, a later message is still no approval.
    later = proposed + _asked(REVISED) + [HumanMessage(content="ok vas-y")]
    assert not tools.plan_approved(later)
    # Without the question tool, the user's reply is their answer.
    assert tools.plan_approved(proposed + [HumanMessage(content="ok")])
    # A newer proposal needs its own approval.
    again = (
        proposed
        + _asked(APPROVED)
        + answered("Plan proposed: nothing was built yet.")[1:]
    )
    assert not tools.plan_approved(again)


@pytest.mark.asyncio
async def test_the_approve_button_builds_and_a_free_answer_revises(monkeypatch):
    first = await build_tool(monkeypatch, _first_turn(), validate_plan=True)
    proposed, _ = await first(slides=DECK)
    for answer, call, expected in (
        (REVISED, {"changes": [{"op": "remove", "slide": 3}]}, "Plan proposed"),
        (APPROVED, {"slides": DECK}, "Delivered"),
    ):
        build = await build_tool(
            monkeypatch,
            answered(proposed) + _asked(answer),
            validate_plan=True,
            workspace=FakeWorkspace(),
        )
        text, _ = await build(**call)
        assert text.startswith(expected), text


def _middleware():
    ctx = CapabilityContext(
        identity=CapabilityIdentity(
            user_id="u-1", session_id="s", agent_instance_id="i"
        ),
        config=PptBuilderConfig(validate_plan=True),
        turn_options=EmptyModel(),
        services=RuntimeServices(workspace_fs=FakeWorkspace()),
    )
    (middleware,) = PptBuilderCapability().middleware(ctx)
    return middleware


class _Tool:
    def __init__(self, name: str) -> None:
        self.name = name


class _Request:
    system_prompt = ""

    def __init__(self, messages: list, seen: list, tools: list) -> None:
        self.messages = messages
        self.tools = tools
        self.seen = seen

    def override(self, **update):
        self.seen.append(update)
        return self


async def _handler(request):
    return request


@pytest.mark.asyncio
async def test_the_model_call_after_a_proposal_gets_no_tool():
    """Live: medium re-called the tool after a proposal up to the call cap."""
    middleware = _middleware()
    seen: list = []
    proposed = answered("Plan proposed: nothing was built yet.")
    for history in (proposed, _first_turn(), proposed + [HumanMessage(content="ok")]):
        await middleware.awrap_model_call(_Request(history, seen, []), _handler)  # type: ignore[arg-type]
    assert [u.get("tool_choice") for u in seen] == ["none", None, None]


@pytest.mark.asyncio
async def test_with_ask_user_a_proposal_asks_and_an_approval_builds():
    middleware = _middleware()
    ask, build = _Tool("ask_user"), _Tool(tools.BUILD_TOOL_NAME)
    proposed = answered("Plan proposed: nothing was built yet.")
    cases = [
        (proposed, ["ask_user"], "any"),
        (proposed + _asked(APPROVED), [tools.BUILD_TOOL_NAME], "any"),
        (proposed + _asked(SKIPPED), None, "none"),
        (proposed + _asked(REVISED), None, None),
    ]
    for history, offered, choice in cases:
        seen: list = []
        request: Any = _Request(history, seen, [ask, build])
        await middleware.awrap_model_call(request, _handler)
        (update,) = seen
        names = [t.name for t in update["tools"]] if offered else None
        assert (names if offered else None, update.get("tool_choice")) == (
            offered,
            choice,
        )


@pytest.mark.asyncio
async def test_the_approval_question_offers_approve_and_a_free_answer():
    middleware = _middleware()
    proposed = answered(
        "Plan proposed: nothing was built yet.\n1. cover\n"
        + json.dumps({"status": "plan_proposed", "slides": 1, "language": "fr"})
    )
    call = {
        "id": "ask-1",
        "name": "ask_user",
        "args": {
            "question": "On construit ?",
            "choices": [{"id": "x", "label": "Oui"}],
        },
    }
    history = proposed + [AIMessage(content="", tool_calls=[call])]
    sent: list = []

    class _Call:
        tool_call = call
        state = {"messages": history}

        def override(self, **update):
            sent.append(update["tool_call"]["args"])
            return self

    await middleware.awrap_tool_call(_Call(), _handler)  # type: ignore[arg-type]
    assert sent == [
        {
            "question": "On construit ?",
            "choices": [{"id": "approve", "label": "Approuver"}],
            "allow_free_text": True,
        }
    ]


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
    assert "show the outline and end your answer" in gated
    assert "only once the user approved it" in gated
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
