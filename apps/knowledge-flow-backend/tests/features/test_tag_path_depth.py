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

"""Depth guardrail on tag paths (#2355) — a tag's full path (parent path +
its own name) is capped at MAX_TAG_PATH_DEPTH levels, so a dropped folder
tree cannot mirror itself into arbitrarily deep nested tags."""

import pytest
from pydantic import ValidationError

from knowledge_flow_backend.features.tag.structure import (
    MAX_TAG_PATH_DEPTH,
    TagCreate,
    TagUpdate,
)


def _parent_path(levels: int) -> str:
    return "/".join(f"d{i}" for i in range(levels))


def test_create_at_exactly_max_depth_is_accepted():
    # Parent chain of MAX-1 + the tag's own name = exactly MAX levels.
    tag = TagCreate(name="leaf", path=_parent_path(MAX_TAG_PATH_DEPTH - 1), type="document")
    assert tag.path == _parent_path(MAX_TAG_PATH_DEPTH - 1)


def test_create_beyond_max_depth_is_rejected():
    with pytest.raises(ValidationError, match="too deep"):
        TagCreate(name="leaf", path=_parent_path(MAX_TAG_PATH_DEPTH), type="document")


def test_depth_counts_normalized_segments_not_raw_slashes():
    # Duplicate slashes and blank segments collapse before the depth check —
    # padding a path with "//" must not trip (or dodge) the guardrail.
    raw = "//".join(f"d{i}" for i in range(MAX_TAG_PATH_DEPTH - 1))
    tag = TagCreate(name="leaf", path=raw, type="document")
    assert tag.path == _parent_path(MAX_TAG_PATH_DEPTH - 1)


def test_update_shares_the_same_depth_cap():
    with pytest.raises(ValidationError, match="too deep"):
        TagUpdate(name="leaf", path=_parent_path(MAX_TAG_PATH_DEPTH), type="document")


def test_rootless_tag_is_unaffected():
    tag = TagCreate(name="leaf", path=None, type="document")
    assert tag.path is None


def test_slashed_name_cannot_smuggle_extra_levels():
    # A name carrying "/" would create several levels in one call — the depth
    # check only counts path segments + 1, so it must be rejected outright
    # (found live: "a/b/c" typed in the folder-name field bypassed the cap).
    with pytest.raises(ValidationError, match="single folder level"):
        TagCreate(name="a/b/c", path=None, type="document")
    with pytest.raises(ValidationError, match="single folder level"):
        TagUpdate(name="a\\b", type="document")


def test_blank_name_is_rejected():
    with pytest.raises(ValidationError, match="empty"):
        TagCreate(name="   ", type="document")
