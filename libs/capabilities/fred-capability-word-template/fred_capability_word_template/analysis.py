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

"""The template analysis.

The map says what is in a template, not what it is for. One LLM call reads
the template's map once and returns a short structured result - its parts,
the role of each element that is not fixed wording, and the blocks meant to
be repeated - cached per template key and put in the prompt on every turn.

The prompt is generic: it knows no kind of document. Without a reachable
model the engine runs on the map alone (`fallback_analysis_text`).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# A long template's map is cut: the analysis needs its shape, not every word.
MAX_MAP_CHARS = 60_000
# The analysis is in the prompt on every turn: kept short.
MAX_ANALYSIS_CHARS = 4_000

ElementRoleName = Literal["fixed", "replace", "fill", "empty"]


class ElementRole(BaseModel):
    """The role of one element or range of the BLANK template."""

    address: str = Field(description='an address or a range, e.g. "T2.R2.C4", "P5–P9"')
    role: ElementRoleName
    note: str = ""


class AnalysisPart(BaseModel):
    title: str
    addresses: str = Field(description='the part\'s range, e.g. "P1–P12" or "T1–T3"')
    purpose: str = ""
    elements: list[ElementRole] = []


class RepeatableBlock(BaseModel):
    addresses: str
    one_per: str = Field(description="what one copy of the block stands for")


class TemplateAnalysis(BaseModel):
    summary: str
    parts: list[AnalysisPart] = []
    repeatable_blocks: list[RepeatableBlock] = []


ANALYSIS_SYSTEM_PROMPT = """\
You analyse a Word document template once, so that an assistant can later \
produce documents from it. You receive the template's map: every paragraph \
(P), table (T), row (R), cell (C), header (H) and footer (F) with its \
address and text; ∅ marks an empty element; {...} gives notable formatting \
such as a colour that differs from the body text, bold, or a list item.

Return ONLY a JSON object, no prose, with this shape:
{
  "summary": "one or two sentences: what kind of document this is and how it is organised",
  "parts": [
    {
      "title": "short name of the part",
      "addresses": "its range, e.g. P1–P12 or T1",
      "purpose": "what the part is for, in a few words",
      "elements": [
        {"address": "address or range", "role": "fixed|replace|fill|empty", "note": "what goes there, in a few words"}
      ]
    }
  ],
  "repeatable_blocks": [
    {"addresses": "range of the block", "one_per": "what one copy stands for"}
  ]
}

Roles:
- fixed: wording that belongs to every document made from this template \
(labels, legal text, fixed headings). Do not list fixed elements unless \
their role is not obvious.
- replace: an instruction to the writer, a guidance note, or sample / \
example content left from a previous document; it is replaced by written \
content.
- fill: a value to set in a fixed place (a name, a date, a number, a code, \
a period).
- empty: an empty place meant to receive a value or content.

Rules:
- Judge from the content and its formatting (a colour, an imperative \
instruction, a sample value), not from the position alone.
- Group consecutive elements with the same role as one range.
- A repeatable block is a group of elements meant to appear once per item \
(several identical tables or row groups, a block that clearly stands for one \
entry of a list).
- Use only addresses that appear in the map. Keep the whole answer short: \
at most 15 parts and the elements that matter.
"""


def _extract_json(text: str) -> Any:
    """The first JSON object in ``text`` (models sometimes wrap it in a
    code fence or a sentence)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in the analysis answer")
    return json.loads(candidate[start : end + 1])


def parse_analysis(text: str) -> TemplateAnalysis:
    """Parse the model's answer; raises ``ValueError`` when unusable."""
    try:
        return TemplateAnalysis.model_validate(_extract_json(text))
    except (ValidationError, json.JSONDecodeError) as exc:
        raise ValueError(f"unusable template analysis: {exc}") from exc


def _message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


def analysis_messages(template_map: str, parts_listing: str) -> list[Any]:
    if len(template_map) > MAX_MAP_CHARS:
        template_map = (
            template_map[:MAX_MAP_CHARS]
            + "\n... (map cut: the rest has the same kind of content)"
        )
    return [
        SystemMessage(content=ANALYSIS_SYSTEM_PROMPT),
        HumanMessage(
            content=f"Parts of the template:\n{parts_listing}\n\nMap:\n{template_map}"
        ),
    ]


async def run_analysis(
    model: BaseChatModel, template_map: str, parts_listing: str
) -> TemplateAnalysis:
    """One LLM call. Its callbacks are cut off from the chat turn's (and the
    run is tagged ``nostream``) so the analysis never streams to the
    collaborator. Raises on any failure; the caller falls back."""
    answer = await model.ainvoke(
        analysis_messages(template_map, parts_listing),
        config={
            "callbacks": [],
            "tags": ["nostream"],
            "run_name": "word_template_analysis",
        },
    )
    return parse_analysis(_message_text(answer))


def render_analysis(analysis: TemplateAnalysis) -> str:
    """The compact text put in the prompt."""
    lines = [analysis.summary.strip()]
    for part in analysis.parts:
        purpose = f": {part.purpose.strip()}" if part.purpose.strip() else ""
        lines.append(f"- {part.title.strip()} ({part.addresses}){purpose}")
        by_role: dict[str, list[str]] = {}
        for element in part.elements:
            note = f" ({element.note.strip()})" if element.note.strip() else ""
            by_role.setdefault(element.role, []).append(f"{element.address}{note}")
        for role in ("replace", "fill", "empty", "fixed"):
            if role in by_role:
                lines.append(f"    {role}: " + "; ".join(by_role[role]))
    if analysis.repeatable_blocks:
        lines.append("Repeatable blocks:")
        lines.extend(
            f"- {block.addresses}: one per {block.one_per.strip()}"
            for block in analysis.repeatable_blocks
        )
    text = "\n".join(lines)
    if len(text) > MAX_ANALYSIS_CHARS:
        text = text[:MAX_ANALYSIS_CHARS] + "\n... (analysis cut)"
    return text


_LIST_SPLIT = re.compile(r"\s*[,;]\s*")
_RANGE_SPLIT = re.compile(r"\s*(?:–|—|-|\.\.|\bto\b)\s*")


def address_ranges(text: str) -> list[tuple[str, str]]:
    """The (first, last) pairs an analysis address stands for: one address, a
    range, or a list of both. A range end shorter than its start is relative
    to it: "T1.R3.C1.P3–P4" ends at "T1.R3.C1.P4", not at body paragraph P4."""
    out: list[tuple[str, str]] = []
    for piece in _LIST_SPLIT.split(text.strip()):
        ends = [end for end in _RANGE_SPLIT.split(piece, maxsplit=1) if end]
        if not ends:
            continue
        first, last = ends[0], ends[-1]
        head, tail = first.split("."), last.split(".")
        if len(tail) < len(head):
            last = ".".join(head[: len(head) - len(tail)] + tail)
        out.append((first, last))
    return out


def fallback_analysis_text() -> str:
    return (
        "No analysis of this template is available. Read each part before "
        "editing it and judge each element yourself: fixed wording to keep, "
        "instructions or sample content to replace, values to fill, empty "
        "places to complete."
    )
