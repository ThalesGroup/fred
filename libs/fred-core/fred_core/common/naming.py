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
How everything a contributor adds to Fred is named.

One rule for agents, Knowledge Bases and applications: a dotted name under a
prefix its contributor owns — `fred.github.assistant`, `fred.samples.local-folder`,
`thales.prism.triage`. Uniqueness comes from owning the prefix, the way Java
packages and Maven group ids work, so no registry has to be kept and no operator
arbitrates a name.

Ownership is a prefix test, never a split: a name is not cut into parts, it is
checked against the prefixes a caller owns. That is why no separator is needed,
and why prefixes may be of any depth.

Full rationale: docs/swift/platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md
"""

from __future__ import annotations

import re

# A run of letters/digits, then any number of single-separator groups. Written
# this way so the pattern alone rejects a leading, trailing or doubled separator
# — `a__b`, `a--b`, `-a`, `a_` — without a second check a caller could forget.
_SEGMENT = r"[a-z0-9]+(?:[_-][a-z0-9]+)*"

#: A prefix a contributor owns. One segment or more: `fred`, `fred.samples`.
PREFIX_PATTERN = rf"^{_SEGMENT}(?:\.{_SEGMENT})*$"

#: A contributed name. Two segments or more: a prefix, then what it names.
CONTRIBUTED_NAME_PATTERN = rf"^{_SEGMENT}(?:\.{_SEGMENT})+$"

MAX_NAME_CHARS = 255

_PREFIX_RE = re.compile(PREFIX_PATTERN)
_NAME_RE = re.compile(CONTRIBUTED_NAME_PATTERN)


class InvalidContributedName(ValueError):
    """Raised when a name or prefix does not follow the contributor rule."""


def is_valid_prefix(prefix: str) -> bool:
    """Whether this is a well-formed prefix a client could own."""
    return (
        len(prefix) <= MAX_NAME_CHARS
        and "__" not in prefix
        and _PREFIX_RE.match(prefix) is not None
    )


def is_valid_contributed_name(name: str) -> bool:
    """Whether this is a well-formed contributed name.

    A bare single segment is refused on purpose: a name carries its provenance,
    and `assistant` says nothing about who ships it.
    """
    return (
        len(name) <= MAX_NAME_CHARS
        and "__" not in name
        and _NAME_RE.match(name) is not None
    )


def require_contributed_name(name: str) -> str:
    """Return the name, or say precisely why it cannot be one."""
    if len(name) > MAX_NAME_CHARS:
        raise InvalidContributedName(
            f"name is longer than {MAX_NAME_CHARS} characters: {name!r}"
        )
    if "__" in name:
        raise InvalidContributedName(
            f"name must not contain a double underscore: {name!r}"
        )
    if _NAME_RE.match(name) is None:
        raise InvalidContributedName(
            "name must be lowercase dotted segments, at least two, each starting "
            f"and ending on a letter or digit: {name!r}"
        )
    return name


def prefix_covers(prefix: str, name: str) -> bool:
    """Whether a client owning `prefix` may write `name`.

    A segment boundary is required, so owning `fred.sample` does not reach
    `fred.samples.local-folder`. Kept as one function because the dispatching
    side and the publishing side must decide this identically.
    """
    return name == prefix or name.startswith(f"{prefix}.")
