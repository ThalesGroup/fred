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

"""The one naming rule every contributed agent, Knowledge Base and application obeys."""

import re

import pytest
from fred_pod.common.naming import (
    CONTRIBUTED_NAME_PATTERN,
    PREFIX_PATTERN,
    InvalidContributedName,
    prefix_covers,
    require_contributed_name,
)


def _accepted(name: str) -> bool:
    """Whether the one public gate admits this name."""
    try:
        require_contributed_name(name)
    except InvalidContributedName:
        return False
    return True


VALID = [
    "fred.github.assistant",
    "fred.github.sql_expert",
    "fred.dt.mindmap.graph",
    "fred.samples.local-folder",
    "fred.samples.bank_transfer.graph",
    "thales.prism.triage",
]

INVALID = [
    "assistant",
    "Fred.Github.Assistant",
    "Fred default agents",
    "fred.a__b",
    "fred.a--b",
    "fred.-a",
    "fred.a_",
    "fred..a",
    "fred.",
    ".fred.a",
    "fred.a/b",
    "fred.a b",
]


@pytest.mark.parametrize("name", VALID)
def test_real_identifiers_are_valid(name: str) -> None:
    assert require_contributed_name(name) == name


@pytest.mark.parametrize("name", INVALID)
def test_malformed_names_are_refused(name: str) -> None:
    with pytest.raises(InvalidContributedName):
        require_contributed_name(name)


@pytest.mark.parametrize("name", VALID + INVALID)
def test_the_pattern_alone_decides(name: str) -> None:
    """The regex must stand on its own.

    It is used directly as a pydantic `pattern=`, where no helper runs — so a
    caller who never calls `require_contributed_name` must still be unable to
    accept a malformed name.
    """
    assert bool(re.match(CONTRIBUTED_NAME_PATTERN, name)) == _accepted(name)


def test_a_name_longer_than_the_bound_is_refused() -> None:
    assert not _accepted("fred." + "a" * 300)


def test_a_prefix_may_be_a_single_segment_but_a_name_may_not() -> None:
    assert re.match(PREFIX_PATTERN, "fred")
    assert not _accepted("fred")


@pytest.mark.parametrize(
    ("prefix", "name", "covered"),
    [
        ("fred.samples", "fred.samples.local-folder", True),
        ("fred.samples", "fred.samples", True),
        ("fred", "fred.samples.local-folder", True),
        ("fred.sample", "fred.samples.local-folder", False),
        ("fred.samples", "fred.samplesx.local-folder", False),
        ("fred.samples", "other.samples.local-folder", False),
    ],
)
def test_ownership_requires_a_segment_boundary(
    prefix: str, name: str, covered: bool
) -> None:
    """A prefix owns whole segments, never a character run.

    Without the boundary, owning `fred.sample` would silently reach everything
    under `fred.samples`.
    """
    assert prefix_covers(prefix, name) is covered
