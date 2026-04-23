"""Tests for _intersect_or_fallback in kf_vectorsearch_client.

Verifies the null-vs-empty-list distinction:
  - None  → "no restriction at this level" (passes through the other side)
  - []    → "explicitly no libraries" (deny all)
"""

import pytest

from agentic_backend.common.kf_vectorsearch_client import _intersect_or_fallback


@pytest.mark.parametrize(
    "a, b, expected",
    [
        # Both None → no restriction
        (None, None, None),
        # One side None → pass through the other (preserving [] vs populated)
        (["a"], None, {"a"}),
        (None, ["a"], {"a"}),
        # Both populated → intersection
        (["a", "b"], ["b", "c"], {"b"}),
        (["a"], ["b"], set()),
        # Empty list on either side → deny all (empty set, not None)
        ([], ["a"], set()),
        (["a"], [], set()),
        ([], [], set()),
        # Empty list paired with None → the explicit empty wins
        ([], None, []),
        (None, [], []),
    ],
)
def test_intersect_or_fallback(a, b, expected):
    result = _intersect_or_fallback(a, b)
    if expected is None:
        assert result is None
    else:
        assert set(result) == set(expected)


def test_triple_intersection_deny_all_when_user_selects_nothing():
    """
    creator=["a","b"], user=[], LLM=None → result must be empty (deny all).

    This mirrors the three-level intersection in agent_search():
      final = intersect(intersect(creator, user), llm)
    """
    creator = ["a", "b"]
    user: list = []
    llm = None

    after_creator_user = _intersect_or_fallback(creator, user)
    final = _intersect_or_fallback(after_creator_user, llm)

    assert set(final) == set()


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
