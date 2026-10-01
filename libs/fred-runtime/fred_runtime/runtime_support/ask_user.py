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
from typing import Annotated

from fred_sdk.contracts.runtime import (
    HumanChoiceOption,
    HumanInputRequest,
    parse_human_input_answer,
)
from langchain_core.tools import InjectedToolCallId
from langgraph.types import interrupt
from pydantic import BaseModel, Field, model_validator


class AskUserArgs(BaseModel):
    question: str = Field(min_length=1)
    choices: tuple[HumanChoiceOption, ...] = Field(
        default=(),
        max_length=4,
        description="Select up to four of the most relevant options before asking; do not submit a longer list.",
    )
    allow_free_text: bool = False
    tool_call_id: Annotated[str, InjectedToolCallId]

    @model_validator(mode="after")
    def validate_question(self) -> AskUserArgs:
        if not self.question.strip():
            raise ValueError("question must not be blank")
        if not self.choices and not self.allow_free_text:
            raise ValueError("ask_user requires choices or free text")
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
        question=args.question,
        choices=args.choices,
        free_text=args.allow_free_text or len(args.choices) >= 2,
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
