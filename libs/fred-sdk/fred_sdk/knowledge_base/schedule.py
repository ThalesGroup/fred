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
How often a Knowledge Base runs — declared once here, for every author.

Recurrence is the one part of the instance form Fred understands and acts on,
so it is the one part an author does not write. Declaring it here rather than
leaving it to each author means every Knowledge Base offers a team the same
vocabulary, and nobody invents a competing one two releases later.

It is declared with the same `FieldSpec` vocabulary an author uses for their
own fields, so one renderer draws both zones. Deliberately outside the
author-facing exports: an author neither declares nor reads any of it, and the
package's public surface stays free of execution-engine terms.
"""

from __future__ import annotations

from enum import StrEnum

from fred_sdk.contracts.models import FieldSpec, UIHints

# Every key Fred owns in the instance form sits under this one segment, so what
# belongs to the platform and what belongs to the author are told apart by
# reading a key rather than by consulting a list.
FRED_FIELD_NAMESPACE = "fred"
FRED_FIELD_PREFIX = f"{FRED_FIELD_NAMESPACE}."

CADENCE_KEY = f"{FRED_FIELD_PREFIX}cadence"
SUSPENDED_KEY = f"{FRED_FIELD_PREFIX}suspended"


class RunCadence(StrEnum):
    """How often an instance runs.

    Three intervals and nothing else. A recurrence surface reaches the user,
    the database and the workflow engine at once, so it is cheap to write and
    expensive to have written wrongly — time zones, overlap policy and calendar
    recurrence are deliberately absent until something asks for them.
    """

    hourly = "hourly"
    daily = "daily"
    weekly = "weekly"


DEFAULT_CADENCE = RunCadence.daily


def platform_fields() -> list[FieldSpec]:
    """The zone Fred declares on every instance form, whatever the author wrote.

    Returned fresh each call: a caller that renders them is free to annotate
    its own copy without the next caller inheriting the edit.
    """
    return [
        FieldSpec(
            key=CADENCE_KEY,
            type="select",
            title="Runs",
            description="How often this folder synchronizes with its source.",
            required=True,
            default=DEFAULT_CADENCE.value,
            enum=[cadence.value for cadence in RunCadence],
            ui=UIHints(group=FRED_FIELD_NAMESPACE),
        ),
        FieldSpec(
            key=SUSPENDED_KEY,
            type="boolean",
            title="Paused",
            description=(
                "While paused, nothing runs on its own. What was already "
                "synchronized stays where it is."
            ),
            required=False,
            default=False,
            ui=UIHints(group=FRED_FIELD_NAMESPACE),
        ),
    ]


def is_platform_field(key: str) -> bool:
    """Whether this form key belongs to Fred rather than to the author."""
    return key == FRED_FIELD_NAMESPACE or key.startswith(FRED_FIELD_PREFIX)
