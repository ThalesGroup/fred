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

"""Typed boundary for one resume covering simultaneous agent questions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BatchedHumanAnswer:
    interrupt_id: str
    occurrence_id: str
    answer: dict[str, Any]


def parse_batched_human_answers(payload: Any) -> tuple[BatchedHumanAnswer, ...] | None:
    """Return a complete batch shape, or None for the existing single-answer form."""
    if not isinstance(payload, dict) or "answers" not in payload:
        return None
    raw_answers = payload.get("answers")
    if (
        set(payload) != {"answers"}
        or not isinstance(raw_answers, list)
        or len(raw_answers) < 2
    ):
        raise ValueError("a HITL answer batch requires at least two answers")
    answers: list[BatchedHumanAnswer] = []
    seen_interrupts: set[str] = set()
    seen_occurrences: set[str] = set()
    for raw in raw_answers:
        if not isinstance(raw, dict) or set(raw) != {
            "interrupt_id",
            "occurrence_id",
            "answer",
        }:
            raise ValueError(
                "each HITL batch item requires interrupt_id, occurrence_id, and answer"
            )
        interrupt_id = raw["interrupt_id"]
        occurrence_id = raw["occurrence_id"]
        answer = raw["answer"]
        if (
            not isinstance(interrupt_id, str)
            or not interrupt_id.strip()
            or not isinstance(occurrence_id, str)
            or not occurrence_id.strip()
            or not isinstance(answer, dict)
        ):
            raise ValueError(
                "HITL batch identities must be nonblank and answers must be objects"
            )
        if interrupt_id in seen_interrupts or occurrence_id in seen_occurrences:
            raise ValueError("HITL batch identities must be unique")
        seen_interrupts.add(interrupt_id)
        seen_occurrences.add(occurrence_id)
        answers.append(BatchedHumanAnswer(interrupt_id, occurrence_id, answer))
    return tuple(answers)
