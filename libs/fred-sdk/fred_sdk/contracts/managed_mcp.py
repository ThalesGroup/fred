# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Non-secret managed MCP facts shared with Control Plane. No business policy."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class McpFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class McpNoAuthentication(McpFact):
    kind: Literal["none"]


class McpBearerAuthentication(McpFact):
    kind: Literal["bearer"]
    credential_binding: str = Field(min_length=1, max_length=128)


class McpApiKeyAuthentication(McpFact):
    kind: Literal["api_key"]
    credential_binding: str = Field(min_length=1, max_length=128)
    header: str = Field(pattern=r"^[xX]-[A-Za-z0-9_-]+$")

    @model_validator(mode="after")
    def external_header(self) -> Self:
        if self.header.lower().startswith("x-fred-"):
            raise ValueError("Reserved MCP header")
        return self


class McpConfiguration(McpFact):
    url: str = Field(min_length=1, max_length=2048)
    authentication: Annotated[
        McpNoAuthentication | McpBearerAuthentication | McpApiKeyAuthentication,
        Field(discriminator="kind"),
    ]
    allow_insecure_http: bool = False

    @model_validator(mode="after")
    def destination(self) -> Self:
        parsed = urlsplit(self.url)
        if (
            parsed.scheme
            not in ({"https", "http"} if self.allow_insecure_http else {"https"})
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or self.url.strip() != self.url
            or any(ord(c) < 33 for c in self.url)
        ):
            raise ValueError("Invalid MCP destination")
        return self


class McpCredentialBinding(McpFact):
    """Provisioned locally in each workload. Never received through admission."""

    credential_binding: str = Field(min_length=1, max_length=128)
    url: str
    secret_env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")


class McpTool(McpFact):
    name: str = Field(min_length=1, max_length=128)
    description: str | None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    annotations: dict[str, Any] | None


class McpBinding(McpFact):
    connection_id: UUID
    capability_id: str
    revision: int = Field(gt=0, strict=True)
    display_name: str
    configuration: McpConfiguration
    tools: tuple[McpTool, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.capability_id != f"managed-mcp:{self.connection_id}":
            raise ValueError("Invalid managed MCP offer identity")
        if len({tool.name for tool in self.tools}) != len(self.tools):
            raise ValueError("Duplicate published MCP tool")
        return self
