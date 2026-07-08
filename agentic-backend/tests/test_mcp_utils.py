from __future__ import annotations

from agentic_backend.common.mcp_utils import (
    _format_exception,
    _leaf_exceptions,
)


def test_leaf_exceptions_plain_exception_returns_itself() -> None:
    exc = ValueError("boom")
    assert _leaf_exceptions(exc) == [exc]


def test_leaf_exceptions_unwraps_single_taskgroup_leaf() -> None:
    # Mirrors the real incident: an anyio TaskGroup wraps a single HTTP 401.
    leaf = RuntimeError("Client error '401 Unauthorized' for url 'http://kf/mcp-tabular'")
    group = ExceptionGroup("unhandled errors in a TaskGroup (1 sub-exception)", [leaf])

    assert _leaf_exceptions(group) == [leaf]


def test_leaf_exceptions_unwraps_multiple_leaves() -> None:
    leaf_a = RuntimeError("a")
    leaf_b = ValueError("b")
    group = ExceptionGroup("group", [leaf_a, leaf_b])

    assert _leaf_exceptions(group) == [leaf_a, leaf_b]


def test_leaf_exceptions_unwraps_nested_groups() -> None:
    leaf = RuntimeError("deep 401")
    inner = ExceptionGroup("inner", [leaf])
    outer = ExceptionGroup("outer", [inner])

    assert _leaf_exceptions(outer) == [leaf]


def test_format_exception_uses_first_line_only() -> None:
    exc = RuntimeError("first line\nsecond line\nthird line")
    assert _format_exception(exc) == "RuntimeError: first line"


def test_format_exception_names_the_leaf_class() -> None:
    # After unwrapping, the message names the concrete error, not "ExceptionGroup".
    leaf = RuntimeError("Client error '401 Unauthorized'")
    group = ExceptionGroup("unhandled errors in a TaskGroup (1 sub-exception)", [leaf])

    (unwrapped,) = _leaf_exceptions(group)
    summary = _format_exception(unwrapped)

    assert summary == "RuntimeError: Client error '401 Unauthorized'"
    assert "ExceptionGroup" not in summary
    assert "TaskGroup" not in summary
