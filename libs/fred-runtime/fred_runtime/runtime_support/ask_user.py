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

"""Pure agent question tool, resumed with one validated human answer."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Annotated, Any

from fred_sdk.contracts.runtime import (
    HumanChoiceOption,
    HumanInputRequest,
    parse_human_input_answer,
)
from langchain_core.tools import InjectedToolCallId
from langgraph.types import interrupt
from pydantic import BaseModel, Field, model_validator

ASK_USER_DESCRIPTION = (
    "Ask the user one question and continue after their answer. "
    "Call this tool whenever you need a decision, a preference or a missing detail from the user; "
    "never write the question in your reply instead. "
    "When possible, give the question a short subject title of a few words. "
    "Hard limit: at most four choices; with five or more candidates, keep the four that best fit the user's constraints. "
    "Never add an 'Other' choice: the interface always offers an editable Other answer alongside two or more choices. "
    "Ask without choices for an open answer."
)

# Labels that only mean "something else": the UI already offers an editable Other field.
_GENERIC_OTHER_LABELS = frozenset(
    {
        "autre",
        "autres",
        "autre chose",
        "autre reponse",
        "other",
        "others",
        "other answer",
        "something else",
    }
)


def _is_generic_other(label: object) -> bool:
    if not isinstance(label, str):
        return False
    text = unicodedata.normalize("NFKD", label.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\([^)]*\)\s*$", "", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split()) in _GENERIC_OTHER_LABELS


class AskUserArgs(BaseModel):
    question: str = Field(min_length=1)
    title: str | None = Field(
        default=None,
        max_length=60,
        description="A short subject for the question tab, preferably two or three words.",
    )
    choices: tuple[HumanChoiceOption, ...] = Field(
        default=(),
        max_length=4,
        description="Hard limit: at most four choices. Select the four best matches before calling. Never include an Other choice; the free-text answer covers it.",
    )
    allow_free_text: bool = False
    tool_call_id: Annotated[str, InjectedToolCallId]

    @model_validator(mode="before")
    @classmethod
    def drop_generic_other_choices(cls, data: Any) -> Any:
        """Drop a generic Other choice before the four-choice limit; it means free text."""
        if not isinstance(data, dict) or not isinstance(
            data.get("choices"), list | tuple
        ):
            return data
        choices = list(data["choices"])
        kept = [
            choice
            for choice in choices
            if not _is_generic_other(
                choice.get("label")
                if isinstance(choice, dict)
                else getattr(choice, "label", None)
            )
        ]
        if len(kept) == len(choices):
            return data
        return {**data, "choices": kept, "allow_free_text": True}

    @model_validator(mode="after")
    def validate_question(self) -> AskUserArgs:
        if not self.question.strip():
            raise ValueError("question must not be blank")
        if self.title is not None and not self.title.strip():
            raise ValueError("title must not be blank")
        ids = [choice.id for choice in self.choices]
        if any(
            not choice.id.strip()
            or choice.id != choice.id.strip()
            or not choice.label.strip()
            for choice in self.choices
        ):
            raise ValueError(
                "choice ids must be nonblank and trimmed; labels must not be blank"
            )
        if len(ids) != len(set(ids)):
            raise ValueError("choice ids must be unique")
        return self


async def ask_user(payload: dict[str, object], *, language: str | None = None) -> str:
    args = AskUserArgs.model_validate(payload)
    request = HumanInputRequest(
        stage="agent_question",
        title=args.title,
        question=args.question,
        choices=args.choices,
        free_text=args.allow_free_text or len(args.choices) != 1,
        occurrence_id=args.tool_call_id,
    )
    decision = interrupt(request.model_dump(mode="json"))
    answer = parse_human_input_answer(decision, request)
    if answer.skipped:
        is_french = language is not None and language.strip().lower().replace(
            "_", "-"
        ).startswith("fr")
        instruction = (
            "L'utilisateur n'a pas souhaité répondre à cette question. Continue ce tour "
            "avec tes propres hypothèses et explicite-les dans ta réponse, sans reposer la même question."
            if is_french
            else "The user chose not to answer this question. Continue this turn using your own "
            "assumptions and state them in your response, without asking the same question again."
        )
        return json.dumps(
            {"status": "skipped", "instruction": instruction},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    result: dict[str, str] = {"status": "answered"}
    if answer.choice_id is not None:
        result["choice_id"] = answer.choice_id
    if answer.text is not None:
        result["text"] = answer.text
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
