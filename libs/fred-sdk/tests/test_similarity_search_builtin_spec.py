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

"""`knowledge.similarity_search` is reachable through the built-in catalog.

A tool ref that exists as a constant but is missing from `_BUILTIN_TOOL_SPECS`
fails silently in the worst way: the ReAct resolver falls through to its generic
branch and binds the model a tool whose whole schema is `payload: dict`, so the
LLM never learns `anchor` and `document_uids` exist and every call dies on the
invoker's own guard. Testing the invoker directly does not catch it - the
resolver is what reads the catalog.
"""

from __future__ import annotations

from fred_sdk.support.builtins import (
    TOOL_REF_SIMILARITY_SEARCH,
    BuiltinToolBackend,
    get_builtin_tool_spec,
    list_builtin_tool_specs,
)
from fred_sdk.support.builtins.catalog import SimilaritySearchToolArgs


def test_similarity_search_is_registered_in_the_catalog() -> None:
    spec = get_builtin_tool_spec(TOOL_REF_SIMILARITY_SEARCH)

    assert spec is not None
    assert spec.args_schema is SimilaritySearchToolArgs
    # TOOL_INVOKER, not a workspace backend: it reads Knowledge Flow.
    assert spec.backend is BuiltinToolBackend.TOOL_INVOKER
    assert spec.default_description
    assert spec in list_builtin_tool_specs()


def test_the_model_facing_schema_names_the_arguments_the_invoker_requires() -> None:
    schema = SimilaritySearchToolArgs.model_json_schema()

    assert set(schema["required"]) == {"anchor", "document_uids"}
    assert set(schema["properties"]) == {
        "anchor",
        "document_uids",
        "top_k",
        "rerank",
        "min_score",
    }
    # Every argument carries a description - it is all the model gets.
    assert all(prop.get("description") for prop in schema["properties"].values())


def test_defaults_match_the_targeted_comparison_contract() -> None:
    args = SimilaritySearchToolArgs(anchor="x", document_uids=["doc-a"])

    assert args.top_k == 10
    assert args.rerank is True
    assert args.min_score is None
