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

from typing import Literal

# Name of the unique index on `(team_id, lower(display_name))` (names are stored
# trimmed), matched in integrity errors to tell a name conflict from others.
AGENT_NAME_INDEX = "uq_agent_instance_team_name"


def normalize_agent_name(name: str) -> str:
    """The form two agent names are compared in: trimmed on write, lowered by the index."""

    return name.strip().lower()


def is_agent_name_violation(exc: BaseException) -> bool:
    return AGENT_NAME_INDEX in str(exc)


# Leaves room for ` (copie N)` within the 255-character column.
_COPY_NAME_BASE_MAX = 240

CopyLocale = Literal["fr", "en"]

# Fixed words only: the client picks a language, never the text stored in the name.
_COPY_WORD: dict[str, str] = {"fr": "copie", "en": "copy"}


def free_imported_name(
    name: str, taken: set[str], locale: CopyLocale | None = None
) -> str:
    """`name` when free, else the first free `<name> (<word> <n>)`, n from 1.

    `taken` holds the team's names already normalised; `<word>` is the copying
    user's UI language ("copie" / "copy"), English when unknown.
    """

    if normalize_agent_name(name) not in taken:
        return name
    base = name[:_COPY_NAME_BASE_MAX].rstrip()
    word = _COPY_WORD.get(locale or "en", _COPY_WORD["en"])
    n = 1
    while normalize_agent_name(f"{base} ({word} {n})") in taken:
        n += 1
    return f"{base} ({word} {n})"


def free_numbered_name(name: str, taken: set[str]) -> str:
    """`name` when free, else the first free `<name> (<n>)`, n from 2: a platform
    import restores data rather than copying it, so no language-bound word."""

    if normalize_agent_name(name) not in taken:
        return name
    base = name[:_COPY_NAME_BASE_MAX].rstrip()
    n = 2
    while normalize_agent_name(f"{base} ({n})") in taken:
        n += 1
    return f"{base} ({n})"
