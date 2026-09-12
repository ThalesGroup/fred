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
Authorization helpers for configured Knowledge Base definitions.

The authorized object is the definition, and its type is distinct from
`capability` and `app` so neither of their grants can make a Knowledge Base
usable. Instances are not authorization objects: they are team-scoped rows
whose access follows their team.

This module covers the WRITE and DISPLAY side only: composing the catalog id
and naming the authorization object. Nothing here answers "may this team use
this definition?" — no caller asks yet, because instances do not exist. The
consumption helper belongs with whatever first needs it.
"""

from __future__ import annotations

from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import (
    RebacReference,
)

KNOWLEDGE_BASE_CATALOG_NAMESPACE_PREFIX = "kb__"

__all__ = [
    "KNOWLEDGE_BASE_CATALOG_NAMESPACE_PREFIX",
    "knowledge_base_catalog_id",
    "knowledge_base_definition_ref",
    "knowledge_base_name_from_catalog_id",
]


def knowledge_base_catalog_id(name: str) -> str:
    """Return the key this definition takes in the shared administration catalog.

    The catalog is one flat dictionary shared with capabilities, agents and
    applications, so each kind reserves a prefix and no two kinds can collide in
    it. That prefix is an internal key, never part of the contributed name — see
    `fred_core.common.naming`.
    """

    return f"{KNOWLEDGE_BASE_CATALOG_NAMESPACE_PREFIX}{name}"


def knowledge_base_name_from_catalog_id(catalog_id: str) -> str:
    """Return the contributed name a catalog key carries.

    A removal, not a split: the name keeps whatever depth its contributor chose,
    and nothing here has to guess where a prefix ends.
    """

    if not catalog_id.startswith(KNOWLEDGE_BASE_CATALOG_NAMESPACE_PREFIX):
        raise ValueError(f"Not a Knowledge Base catalog id: {catalog_id!r}")
    name = catalog_id[len(KNOWLEDGE_BASE_CATALOG_NAMESPACE_PREFIX) :]
    if not name:
        raise ValueError(f"Knowledge Base catalog id carries no name: {catalog_id!r}")
    return name


def knowledge_base_definition_ref(name: str) -> RebacReference:
    """Return the typed authorization reference for one definition.

    The object id is the contributed name itself — the catalog key minus its
    namespace prefix, the same relationship `app__<app_id>` has to `app:<id>`.
    """

    return RebacReference(type=Resource.KNOWLEDGE_BASE_DEFINITION, id=name)
