# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
"""The platform question tool is available to interactive Graph turns only."""

from __future__ import annotations

import pytest
from fred_runtime.capabilities.errors import CapabilityAssemblyError
from fred_runtime.graph.graph_runtime import _ask_user_tool
from fred_runtime.runtime_support.ask_user import AskUserArgs
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)


def _binding(*, ask_user: bool | None) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(ask_user=ask_user),
        portable_context=PortableContext(
            request_id="request",
            correlation_id="correlation",
            actor="user",
            tenant="team",
            environment=PortableEnvironment.DEV,
        ),
    )


def test_graph_ask_user_tool_is_mounted_only_when_enabled() -> None:
    for disabled in (False, None):
        assert _ask_user_tool(_binding(ask_user=disabled), existing_names=set()) == ()
    (tool,) = _ask_user_tool(_binding(ask_user=True), existing_names=set())
    assert tool.name == "ask_user"
    assert tool.args_schema is AskUserArgs
    assert tool.response_format == "content_and_artifact"


def test_graph_ask_user_tool_rejects_name_collision() -> None:
    with pytest.raises(CapabilityAssemblyError, match="collides"):
        _ask_user_tool(_binding(ask_user=True), existing_names={"ask_user"})
