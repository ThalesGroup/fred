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

"""The deterministic web research self-test agent (`fred.github.self_test_web`).

A no-LLM graph agent that runs a fixed battery of web research probes through
the real per-user port and returns one JSON report the admin self-test page
reads step by step. When web research is not enabled on the deployment, or its
restricted activity sink is not ready, the report says so and runs no probe.
"""

from __future__ import annotations

from fred_sdk import GraphAgent, GraphWorkflow

from .graph_state import WebSelfTestInput, WebSelfTestState
from .graph_steps import finalize_step, probe_step


class WebSelfTestGraphAgent(GraphAgent):
    """No-LLM harness proving web research protections and behavior end to end."""

    agent_id: str = "fred.github.self_test_web"
    role: str = "Self-Test (web research, deterministic)"
    description: str = (
        "Deterministic web research self-test agent (no LLM). Runs a fixed battery "
        "of probes through the governed web research port: refused URLs and "
        "internal destinations, redirects, content limits, SafeSearch policy, and "
        "a working search and page read. Fails when web research is not enabled."
    )
    tags: tuple[str, ...] = ("test", "web", "deterministic", "no-llm")
    # Internal harness agent, enrolled by the self-test page (include_non_public).
    public: bool = False

    input_schema = WebSelfTestInput
    state_schema = WebSelfTestState
    input_to_state = {"message": "latest_user_text"}
    output_state_field = "final_text"

    workflow = GraphWorkflow(
        entry="probe",
        nodes={"probe": probe_step, "finalize": finalize_step},
        edges={"probe": "finalize"},
    )


WEB_SELF_TEST_AGENT = WebSelfTestGraphAgent()
