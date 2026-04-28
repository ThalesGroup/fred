"""Tests for _intersect_or_fallback in kf_vectorsearch_client.

Semantics: both None and [] mean "no restriction at this level".
Only a non-empty list restricts the search to specific libraries.

  - None  → no restriction (passes through the other side)
  - []    → no restriction (treated identically to None)
  - ["x"] → restrict to {"x"}
"""

import pytest

from agentic_backend.common.kf_vectorsearch_client import _intersect_or_fallback


@pytest.mark.parametrize(
    "a, b, expected",
    [
        # Both None → no restriction
        (None, None, None),
        # One side None → pass through the other
        (["a"], None, {"a"}),
        (None, ["a"], {"a"}),
        # Both populated → intersection
        (["a", "b"], ["b", "c"], {"b"}),
        (["a"], ["b"], set()),
        # Empty list treated as None (no restriction) → other side passes through
        ([], ["a"], {"a"}),
        (["a"], [], {"a"}),
        ([], [], None),
        ([], None, None),
        (None, [], None),
    ],
)
def test_intersect_or_fallback(a, b, expected):
    result = _intersect_or_fallback(a, b)
    if expected is None:
        assert result is None
    else:
        assert set(result) == set(expected)


def test_triple_intersection_empty_user_falls_back_to_creator():
    """
    creator=["a","b"], user=[], LLM=None → creator scope applies.

    user=[] means "user made no explicit selection" — creator scope is not
    narrowed. This is the default state for a new conversation.
    """
    creator = ["a", "b"]
    user: list = []
    llm = None

    after_creator_user = _intersect_or_fallback(creator, user)
    final = _intersect_or_fallback(after_creator_user, llm)

    assert set(final) == {"a", "b"}


def test_triple_intersection_partial_user_selection():
    """creator=["a","b","c"], user=["a","b"], LLM=["b"] → {"b"}."""
    creator = ["a", "b", "c"]
    user = ["a", "b"]
    llm = ["b"]

    after_creator_user = _intersect_or_fallback(creator, user)
    final = _intersect_or_fallback(after_creator_user, llm)

    assert set(final) == {"b"}


def test_triple_intersection_no_creator_restriction():
    """creator=None, user=["a","b"], LLM=None → {"a","b"} (user scope passes through)."""
    creator = None
    user = ["a", "b"]
    llm = None

    after_creator_user = _intersect_or_fallback(creator, user)
    final = _intersect_or_fallback(after_creator_user, llm)

    assert set(final) == {"a", "b"}


def test_triple_intersection_all_none():
    """creator=None, user=None, LLM=None → None (no restriction)."""
    result = _intersect_or_fallback(_intersect_or_fallback(None, None), None)
    assert result is None
