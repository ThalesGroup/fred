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

"""Agent names are unique within a team, compared without case or surrounding spaces."""

from __future__ import annotations

# Name of the unique index on `(team_id, lower(display_name))` (names are stored
# trimmed), matched in integrity errors to tell a name conflict from others.
AGENT_NAME_INDEX = "uq_agent_instance_team_name"


def normalize_agent_name(name: str) -> str:
    """The form two agent names are compared in: trimmed on write, lowered by the index."""

    return name.strip().lower()


def is_agent_name_violation(exc: BaseException) -> bool:
    return AGENT_NAME_INDEX in str(exc)


# Leaves room for `_imported-N` within the 255-character column.
_IMPORTED_NAME_BASE_MAX = 230


def free_imported_name(name: str, taken: set[str]) -> str:
    """`name` when free, else the first free `<name>_imported-<n>`.

    `taken` holds the team's names already normalised.
    """

    if normalize_agent_name(name) not in taken:
        return name
    base = name[:_IMPORTED_NAME_BASE_MAX]
    n = 1
    while normalize_agent_name(f"{base}_imported-{n}") in taken:
        n += 1
    return f"{base}_imported-{n}"
