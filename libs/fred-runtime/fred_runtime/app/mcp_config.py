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
