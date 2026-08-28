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
Registry invariants for the `platform_ops` ready-made admin-ops template.

Why this test exists:
- the template is the admin-ops family's user-visible entry point
  (`docs/swift/rfc/admin-ops-capabilities/PLATFORM-POSTGRES.md` §5): it must be
  registered, its packaged prompt must load, and its default capability
  selection must carry `platform_postgres` — each later admin-ops capability WP
  appends itself to that list, so pinning the current content catches an
  accidental drop

How to use it:
- run via the default offline `fred-agents` test suite

Example:
- `pytest tests/test_platform_ops_template.py -q`
"""

from __future__ import annotations

from fred_agents.platform_ops import PLATFORM_OPS_AGENT
from fred_agents.registry import build_registry


def test_platform_ops_is_registered() -> None:
    registry = build_registry()

    assert PLATFORM_OPS_AGENT.agent_id == "fred.github.platform_ops"
    assert registry[PLATFORM_OPS_AGENT.agent_id] is PLATFORM_OPS_AGENT


def test_platform_ops_prompt_loads_non_empty() -> None:
    prompt = PLATFORM_OPS_AGENT.system_prompt_template

    assert prompt.strip()
    # Load-bearing spec instructions (PLATFORM-POSTGRES §5): grounding and the
    # row-cap teaching must survive prompt edits.
    assert "postgres_list_tables" in prompt
    assert "200 rows" in prompt

    prompt_field = next(
        field for field in PLATFORM_OPS_AGENT.fields if field.key == "prompts.system"
    )
    assert prompt_field.default == prompt


def test_platform_ops_defaults_to_platform_postgres() -> None:
    default_ids = [ref.id for ref in PLATFORM_OPS_AGENT.default_mcp_servers]

    assert "platform_postgres" in default_ids
