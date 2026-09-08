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
`control_plane_backend.knowledge_base_types.catalog` (docs/swift/rfc/KNOWLEDGE-BASE-RFC.md
§6) — mirrors `test_applications.py`'s configured-source coverage.
"""

from __future__ import annotations

import pytest
from control_plane_backend.knowledge_base_types.catalog import (
    ConfiguredKnowledgeBaseTypeCatalogSource,
    KnowledgeBaseTypeConfig,
)
from fred_sdk.contracts.knowledge_base import KnowledgeBaseKind, KnowledgeBaseMode


def _source(
    knowledge_base_type_id: str, *, enabled: bool = True
) -> KnowledgeBaseTypeConfig:
    return KnowledgeBaseTypeConfig(
        knowledge_base_type_id=knowledge_base_type_id,
        name="Local filesystem knowledge base",
        kind=KnowledgeBaseKind.RAG_SQL,
        mode=KnowledgeBaseMode.PULL,
        connector_kind="local_fs",
        enabled=enabled,
    )


def test_configured_source_serves_enabled_types_only() -> None:
    source = ConfiguredKnowledgeBaseTypeCatalogSource(
        (_source("local_fs_rag"), _source("parked", enabled=False))
    )

    catalog = source.load()

    assert [item.knowledge_base_type_id for item in catalog.items] == ["local_fs_rag"]


def test_config_inherits_knowledge_base_type_mode_validation() -> None:
    """`KnowledgeBaseTypeConfig` adds only `enabled` - the mode/connector_kind
    exclusivity invariant is `KnowledgeBaseType`'s own, not re-implemented here."""
    with pytest.raises(Exception):
        KnowledgeBaseTypeConfig(
            knowledge_base_type_id="rag_sql",
            name="Team RAG knowledge base",
            kind=KnowledgeBaseKind.RAG_SQL,
            mode=KnowledgeBaseMode.PUSH,
            connector_kind="local_fs",
        )


def test_config_defaults_to_enabled() -> None:
    assert _source("local_fs_rag").enabled is True
