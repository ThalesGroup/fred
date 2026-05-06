"""
Offline unit tests for fred_sdk.authoring.tool_args_schema.build_args_schema.

Verifies:
- first parameter (ToolContext placeholder) is skipped
- remaining parameters become schema fields with correct types and defaults
- required vs optional fields
- model class name derived from function name
- no-parameter function raises TypeError
- unsupported parameter kinds raise TypeError
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from fred_sdk.authoring.tool_args_schema import build_args_schema


# ---------------------------------------------------------------------------
# Dummy ToolContext placeholder (not imported; just a positional stand-in)
# ---------------------------------------------------------------------------


class _Ctx:
    pass


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


class TestBuildArgsSchema:
    def test_no_extra_params_yields_empty_model(self) -> None:
        def my_tool(ctx: _Ctx) -> str:
            return ""

        schema = build_args_schema(my_tool)
        assert issubclass(schema, BaseModel)
        assert schema.model_fields == {}

    def test_single_required_param(self) -> None:
        def search(ctx: _Ctx, query: str) -> str:
            return ""

        schema = build_args_schema(search)
        assert "query" in schema.model_fields
        field = schema.model_fields["query"]
        assert field.annotation is str
        assert field.is_required()

    def test_optional_param_has_default(self) -> None:
        def fetch(ctx: _Ctx, limit: int = 10) -> list:
            return []

        schema = build_args_schema(fetch)
        field = schema.model_fields["limit"]
        assert not field.is_required()
        assert field.default == 10

    def test_multiple_params_all_present(self) -> None:
        def process(ctx: _Ctx, text: str, max_tokens: int = 256) -> str:
            return ""

        schema = build_args_schema(process)
        assert set(schema.model_fields.keys()) == {"text", "max_tokens"}

    def test_model_name_derived_from_function(self) -> None:
        def my_search_tool(ctx: _Ctx, query: str) -> str:
            return ""

        schema = build_args_schema(my_search_tool)
        assert schema.__name__ == "MySearchToolArgs"

    def test_any_annotation_accepted(self) -> None:
        def flexible(ctx: _Ctx, payload: Any) -> Any:
            return payload

        schema = build_args_schema(flexible)
        assert "payload" in schema.model_fields

    def test_schema_instance_validates_correct_args(self) -> None:
        def search(ctx: _Ctx, query: str, limit: int = 5) -> list:
            return []

        schema = build_args_schema(search)
        instance = schema(query="cats", limit=3)
        assert instance.query == "cats"  # type: ignore[attr-defined]
        assert instance.limit == 3  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Error-path tests
# ---------------------------------------------------------------------------


class TestBuildArgsSchemaErrors:
    def test_no_parameters_raises_type_error(self) -> None:
        def bad_tool() -> str:
            return ""

        with pytest.raises(TypeError, match="must accept a first ToolContext"):
            build_args_schema(bad_tool)

    def test_var_positional_raises_type_error(self) -> None:
        def bad_tool(ctx: _Ctx, *args: str) -> str:
            return ""

        with pytest.raises(TypeError, match="unsupported parameter kind"):
            build_args_schema(bad_tool)

    def test_var_keyword_raises_type_error(self) -> None:
        def bad_tool(ctx: _Ctx, **kwargs: str) -> str:
            return ""

        with pytest.raises(TypeError, match="unsupported parameter kind"):
            build_args_schema(bad_tool)
