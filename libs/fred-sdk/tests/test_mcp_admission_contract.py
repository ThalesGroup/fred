# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Internal services cannot impersonate published external connections."""

import pytest
from fred_sdk.contracts.managed_mcp import (
    McpBinding,
    McpConfiguration,
    McpTabularBinding,
)
from pydantic import TypeAdapter, ValidationError


def test_internal_binding_has_no_connection_or_publication():
    wire = {
        "kind": "knowledge_flow_tabular",
        "url": "https://kf.invalid/api/mcp/tabular",
    }
    binding = TypeAdapter(McpBinding).validate_python(wire)
    assert isinstance(binding, McpTabularBinding)
    assert binding.capability_id == "mcp-knowledge-flow-mcp-tabular"
    assert binding.model_dump(mode="json") == wire
    for extra in (
        {"tools": []},
        {"connection_id": "00000000-0000-0000-0000-000000000000"},
        {"capability_id": "managed-mcp:forged"},
    ):
        with pytest.raises(ValidationError):
            TypeAdapter(McpBinding).validate_python({**wire, **extra})


def test_external_configuration_cannot_request_fred_delegation():
    with pytest.raises(ValidationError):
        McpConfiguration.model_validate(
            {
                "url": "https://kf.invalid/api/mcp/tabular",
                "authentication": {"kind": "knowledge_flow_tabular"},
            }
        )
