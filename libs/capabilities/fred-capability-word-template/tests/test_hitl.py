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

"""The platform HITL declarations: a batch that removes content,
and switching the document's base."""

from __future__ import annotations

from typing import Any

import pytest
from fred_capability_word_template.capability import (
    WordTemplateCapability,
)
from fred_capability_word_template.config import (
    WordTemplateConfig,
)
from fred_runtime.capabilities.assembly import build_capability_agent_block
from fred_runtime.capabilities.registry import CapabilityRegistry
from fred_runtime.runtime_support.tool_approval import ToolApproval
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
    HitlGateRequest,
)
from fred_sdk.contracts.models import ToolApprovalPolicy
from fred_sdk.contracts.runtime import RuntimeServices


def _ctx() -> CapabilityContext[Any, Any]:
    return CapabilityContext(
        identity=CapabilityIdentity(user_id="u-1", session_id="s-1"),
        config=WordTemplateConfig(),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
    )


def _specs() -> dict[str, Any]:
    return {s.tool: s for s in WordTemplateCapability().hitl_specs()}


def _edit(operations: Any) -> dict[str, Any]:
    return {"name": "edit_document", "args": {"operations": operations}, "id": "c1"}


def test_declared_specs_and_their_questions():
    specs = _specs()
    assert set(specs) == {
        "edit_document",
        "use_attached_document",
        "undo_last_edit",
        "remove_unused_template_parts",
    }
    assert specs["remove_unused_template_parts"].require is True
    assert "message ci-dessus" in (specs["remove_unused_template_parts"].question or "")
    assert specs["use_attached_document"].require is True
    assert specs["use_attached_document"].question is None
    assert specs["edit_document"].require is False
    assert specs["edit_document"].when is not None
    # The structure gate points the collaborator to the agent's message.
    assert "message ci-dessus" in (specs["edit_document"].question or "")


@pytest.mark.parametrize(
    ("operations", "gated"),
    [
        ([{"op": "set_text", "address": "P1", "text": "x"}], False),
        (
            [
                {"op": "set_text", "address": "P1", "text": "x"},
                {"op": "remove", "from": "P2", "to": "P3"},
            ],
            True,
        ),
        ([{"op": "repeat", "from": "T1", "to": "T1", "count": 2}], False),
        ([{"op": "write", "from": "P2", "to": "P3", "markdown": "Text."}], False),
        # A heading without changes_template is refused by the engine (the
        # template's outline is followed): no approval for it.
        (
            [
                {
                    "op": "write",
                    "from": "P2",
                    "to": "P3",
                    "markdown": "### Planning\n\nText.",
                }
            ],
            False,
        ),
        ([{"op": "insert_after", "address": "P3", "markdown": "# New chapter"}], False),
        ([{"op": "set_text", "address": "P2", "text": "# Planning\n\nText."}], False),
        ([{"op": "set_text", "address": "P2", "text": "One.\n\nTwo."}], False),
        # A batch the engine will refuse asks for no approval.
        ([{"op": "remove", "from": "P2"}, {"op": "remove", "to": "P3"}], False),
        ([{"op": "remove", "address": "P83"}], True),
        ([{"op": "move", "from": "P5", "before": "P3"}], True),
        ([], False),
        ("not a list", False),
    ],
)
def test_a_batch_that_changes_the_structure_is_gated(operations, gated):
    when = _specs()["edit_document"].when
    assert when is not None
    request = HitlGateRequest(tool_call=_edit(operations), tool=None, context=_ctx())
    assert when(request) is gated


def test_a_declared_change_of_fixed_wording_is_gated():
    when = _specs()["edit_document"].when
    assert when is not None
    call = _edit([{"op": "set_text", "address": "P1", "text": "x"}])
    call["args"]["changes_template"] = True
    assert when(HitlGateRequest(tool_call=call, tool=None, context=_ctx())) is True


def test_assembled_gate_applies_without_operator_approval():
    registry = CapabilityRegistry()
    registry.register(WordTemplateCapability())
    block = build_capability_agent_block(registry, {"word_template": _ctx()})
    # Tools come from tools(), so each binding carries its real tool object.
    assert block.hitl["edit_document"].tool is not None
    assert block.hitl["use_attached_document"].tool is not None

    approval = ToolApproval(
        approval_policy=ToolApprovalPolicy(enabled=False),
        capability_hitl=block.hitl,
    )
    remove = [{"op": "remove", "from": "P2", "to": "P3"}]
    fill = [{"op": "set_text", "address": "P1", "text": "x"}]
    gated, question = approval.decision("edit_document", _edit(remove))
    assert gated is True and "structure de votre document" in (question or "")
    assert approval.decision("edit_document", _edit(fill))[0] is False
    call = {"name": "use_attached_document", "args": {"attachment": "doc1"}}
    assert approval.decision("use_attached_document", call) == (True, None)
    # Undoing an earlier turn's edit, on the collaborator's request: approved.
    undo = {"name": "undo_last_edit", "args": {}}
    assert approval.decision("undo_last_edit", undo)[0] is False
    undo["args"] = {"collaborator_asked": True}
    gated, question = approval.decision("undo_last_edit", undo)
    assert gated is True and "échange précédent" in (question or "")
    assert approval.decision("read_template", {"name": "read_template"}) == (
        False,
        None,
    )
