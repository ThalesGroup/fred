"""Tests for scope resolution in kf_document_client.

Semantics: both None and [] mean "no restriction at this level".
Only a non-empty list restricts the search to specific libraries.

  - None  → no restriction (passes through the other side)
  - []    → no restriction (treated identically to None)
  - ["x"] → restrict to {"x"}
"""

import pytest

from agentic_backend.common.kf_document_client import (
    _intersect_or_fallback,
    resolve_library_scope,
)
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.integrations.kf_vector_search.kf_vector_search_params import (
    KfVectorSearchParams,
)


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


# ---------------------------------------------------------------------------
# resolve_library_scope: the shared hard-binding-then-intersect priority rule
# used by search, summarize, and tree (via their respective agent_* methods).
# ---------------------------------------------------------------------------


def test_hard_binding_wins_unconditionally():
    """When the agent creator set document_library_tags_ids, it wins even if
    the user/LLM scope would otherwise suggest something else."""
    params = KfVectorSearchParams(document_library_tags_ids=["lib-1", "lib-2"])
    runtime_context = RuntimeContext(selected_document_libraries_ids=["lib-3"])

    result = resolve_library_scope(params, runtime_context, llm_library_ids=["lib-4"])

    assert set(result) == {"lib-1", "lib-2"}


def test_no_hard_binding_intersects_runtime_and_llm_scope():
    """Without hard binding, runtime user scope and LLM scope are intersected,
    exactly like the existing triple-intersection cases for search."""
    params = KfVectorSearchParams()
    runtime_context = RuntimeContext(selected_document_libraries_ids=["lib-1", "lib-2"])

    result = resolve_library_scope(params, runtime_context, llm_library_ids=["lib-2"])

    assert set(result) == {"lib-2"}


def test_no_hard_binding_and_no_runtime_scope_passes_through_llm_scope():
    params = KfVectorSearchParams()
    runtime_context = RuntimeContext()

    result = resolve_library_scope(params, runtime_context, llm_library_ids=["lib-1"])

    assert set(result) == {"lib-1"}


def test_no_restriction_anywhere_returns_none():
    """No hard binding, no runtime scope, no LLM scope → no restriction at all
    (e.g. the case used by agent_tree, which never has an LLM-side uid list)."""
    params = KfVectorSearchParams()
    runtime_context = RuntimeContext()

    result = resolve_library_scope(params, runtime_context, llm_library_ids=None)

    assert result is None
