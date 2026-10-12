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

"""Graph steps for the web research self-test agent — no LLM."""

from __future__ import annotations

import json

from fred_sdk import (
    GraphNodeContext,
    GraphNodeResult,
    StepResult,
    typed_node,
)
from fred_sdk import (
    finalize_step as _finalize_step,
)
from fred_sdk.contracts.web_research import WebResearchError

from .graph_state import WebSelfTestState
from .probes import ProbeReport, run_probes

REPORT_HEADER = "WEB-SELF-TEST"
# Fixed reasons the page shows as they are; no upstream text crosses the stream.
NOT_ENABLED = (
    "Web research is not enabled on this deployment "
    "(web_research.enabled in the fred-agents configuration)."
)
NOT_READY = "Web research is enabled but its restricted activity store is not ready."


def report_text(
    *, enabled: bool, ready: bool, reason: str | None, probes: list[ProbeReport]
) -> str:
    """The one line the page parses: a fixed header, then the JSON report."""
    body = {
        "enabled": enabled,
        "ready": ready,
        "reason": reason,
        "probes": [probe.model_dump() for probe in probes],
    }
    return f"{REPORT_HEADER} {json.dumps(body, ensure_ascii=False)}"


@typed_node(WebSelfTestState)
async def probe_step(state: WebSelfTestState, context: GraphNodeContext) -> StepResult:
    """Refuse when web research is off, otherwise run the battery."""
    del state
    port = context.services.web_research
    if port is None:
        return StepResult(
            state_update={
                "final_text": report_text(
                    enabled=False, ready=False, reason=NOT_ENABLED, probes=[]
                ),
                "done_reason": "web_research_disabled",
            }
        )
    try:
        await port.check_ready()
    except WebResearchError:
        return StepResult(
            state_update={
                "final_text": report_text(
                    enabled=True, ready=False, reason=NOT_READY, probes=[]
                ),
                "done_reason": "web_research_not_ready",
            }
        )

    def progress(probe: ProbeReport) -> None:
        context.emit_status("web_probe", f"{probe.id}: {probe.verdict}")

    probes = await run_probes(port, progress)
    return StepResult(
        state_update={
            "final_text": report_text(
                enabled=True, ready=True, reason=None, probes=probes
            ),
            "done_reason": "web_self_test_done",
        }
    )


@typed_node(WebSelfTestState)
async def finalize_step(
    state: WebSelfTestState, context: GraphNodeContext
) -> GraphNodeResult:
    """Terminal step — emit the report."""
    del context
    return _finalize_step(
        final_text=state.final_text,
        fallback_text=f"{REPORT_HEADER} {{}}",
        done_reason=state.done_reason,
    )
