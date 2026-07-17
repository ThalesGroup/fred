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
Platform policy guard (CAPAB-01, 2026-07-17 CVSSI review): this deployment
never uses `team_scope: DEFAULT_ON`. Every team's access to every tool is an
explicit, auditable admin grant — see `docs/swift/rfc/AGENT-CAPABILITY-RFC.md`
§8.3. `team_scope` defaults to `ADMIN_GATED`
(`fred_sdk.contracts.models.TeamScopePolicy`); this test asserts nothing in
this pod's static MCP catalog opts a server into `DEFAULT_ON` without an
explicit, reviewed waiver.

This is a SCAN-based guard because `team_scope` is an author-declared field
on a static manifest here. It does NOT cover `kind="agent"` capabilities
(agent templates projected into the control-plane capability catalog,
CAPAB-01 RFC §8.6) — `AgentDefinition` has no `team_scope` field at all, so
there is nothing to scan; that guard is a narrow unit test directly on the
projection function instead (control-plane-backend
`tests/test_capability_selection_1974.py::test_agent_projection_always_hardcodes_admin_gated`).
"""

from __future__ import annotations

from pathlib import Path

import yaml

# Explicit waiver list — empty today. Adding an id here is a security-reviewed
# decision (this platform's policy, 2026-07-17), not a manifest edit someone
# makes in passing; that is the entire point of this guard existing as a test
# instead of a comment.
_DEFAULT_ON_WAIVERS: set[str] = set()

_MCP_CATALOG_PATH = Path(__file__).resolve().parents[1] / "config" / "mcp_catalog.yaml"


def test_no_mcp_server_declares_default_on_without_explicit_waiver() -> None:
    catalog = yaml.safe_load(_MCP_CATALOG_PATH.read_text())
    offenders = [
        entry["id"]
        for entry in catalog.get("servers", [])
        if entry.get("team_scope") == "default_on"
        and entry["id"] not in _DEFAULT_ON_WAIVERS
    ]
    assert offenders == [], (
        f"{offenders} declare team_scope: default_on without an explicit "
        "waiver in _DEFAULT_ON_WAIVERS. This platform's policy (2026-07-17, "
        "CVSSI review) is that every capability requires an explicit "
        "per-team admin grant — adding a waiver here needs a documented "
        "security review, not a manifest default."
    )
