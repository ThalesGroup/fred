# Copyright Thales 2025
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

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import AliasChoices, BaseModel, Field

FieldType = Literal[
    "string",
    "text",
    "text-multiline",
    "number",
    "integer",
    "boolean",
    "select",
    "array",
    "object",
    "prompt",
    "secret",
    "url",
]


class UIHints(BaseModel):
    """UI hints for rendering the field in a user interface."""

    multiline: bool = False
    max_lines: int = 6
    placeholder: Optional[str] = None
    markdown: bool = False
    textarea: bool = False
    group: Optional[str] = None  # e.g., "Prompts", "MCP", "Advanced"


class FieldSpec(BaseModel):
    """Specification for a tunable field in an agent."""

    key: str  # dotted path under agent.settings (e.g., "prompts.system")
    type: FieldType
    title: str
    description: Optional[str] = None  # "why this matters" → your style
    required: bool = False
    default: Optional[Any] = None
    enum: Optional[List[str]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    pattern: Optional[str] = None
    item_type: Optional[FieldType] = None  # for arrays
    ui: UIHints = UIHints()


class ClientAuthMode(str, Enum):
    # Sends the Authorization: Bearer token (standard OAuth flow)
    USER_TOKEN = "user_token"  # nosec B105
    # Suppresses the Authorization header (Forces server to use global auth/PAT)
    NO_TOKEN = "no_token"  # nosec B105
    # Use the token if available, otherwise no token (similar to 'no_token' logic but explicit)
    # The current code only supports 'user_token' or 'no_token' logic for simplicity.


class MCPServerConfiguration(BaseModel):
    """
    Configuration for an MCP server.
    """

    id: str
    name: str = Field(
        ..., description="react-i18next key for the name of the MCP server."
    )
    description: Optional[str] = Field(
        None, description="react-i18next key for the description of the MCP server."
    )
    transport: Optional[str] = Field(
        "sse",
        description="MCP server transport. Can be sse, stdio, websocket or streamable_http",
    )
    url: Optional[str] = Field(None, description="URL and endpoint of the MCP server")
    sse_read_timeout: Optional[int] = Field(
        60 * 5,
        description="How long (in seconds) the client will wait for a new event before disconnecting",
    )
    command: Optional[str] = Field(
        None,
        description="Command to run for stdio transport. Can be uv, uvx, npx and so on.",
    )
    args: Optional[List[str]] = Field(
        None,
        description="Args to give the command as a list. ex:  ['--directory', '/directory/to/mcp', 'run', 'server.py']",
    )
    env: Optional[Dict[str, str]] = Field(
        None, description="Environment variables to give the MCP server"
    )
    enabled: bool = Field(True, description="If false, this MCP server is ignored.")
    auth_mode: ClientAuthMode = Field(
        ClientAuthMode.USER_TOKEN, description="Client authentication mode."
    )


class MCPServerRef(BaseModel):
    """
    Reference to an MCP server.
    Fred rationale:
    - Agents reference logical servers by name.
    - Resolution (URL/transport/env) is done at runtime per env/tenant/user.
    """

    id: str = Field(
        ..., validation_alias=AliasChoices("id", "name")
    )  # Accept both "id" and "name" on input for backward compatibility; always serializes as "id"
    require_tools: list[str] = []  # optional: "os.*", "kpi.*" capabilities


class AgentTuning(BaseModel):
    role: str = Field(..., description="The agent's mandatory role for discovery.")
    description: str = Field(
        ..., description="The agent's mandatory description for the UI."
    )
    tags: List[str] = Field(default_factory=list)
    fields: List[FieldSpec] = Field(default_factory=list)
    mcp_servers: list[MCPServerRef] = Field(default_factory=list)

    def dump(self) -> str:
        """
        Returns a human-readable, concise JSON string representation of the tuning
        for logging purposes, excluding default and empty values.
        """
        # 1. Use model_dump to get a clean dictionary
        #    - exclude_defaults=True removes empty lists and default values (like FieldSpec defaults)
        data = self.model_dump(
            exclude_defaults=True,
            mode="json",  # ensures all fields are compatible with JSON serialization
        )

        # 2. Extract key tuning parameters for a concise summary
        tuning_summary = {
            "description": data.get("description", self.description),
            "role": data.get("role", self.role),
            "tags": data.get("tags", []),
        }

        # 3. Add field count instead of the full list
        field_count = len(self.fields)
        if field_count > 0:
            tuning_summary["tunable_fields_count"] = field_count

        # 4. Use json.dumps to format the dictionary nicely for the log file
        import json

        return json.dumps(tuning_summary, indent=2)
