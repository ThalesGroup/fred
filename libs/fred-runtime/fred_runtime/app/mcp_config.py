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

"""Typed representation of the mcp_catalog.yaml loaded by an agent pod."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class McpServerEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    url: str
    transport: str = "sse"
    description: str | None = None


class McpCatalogConfiguration(BaseModel):
    """
    Typed representation of mcp_catalog.yaml.

    extra="allow" is intentional: the catalog format is versioned externally and
    may carry fields not yet known to this model.
    """

    model_config = ConfigDict(extra="allow")

    servers: list[McpServerEntry] = []
