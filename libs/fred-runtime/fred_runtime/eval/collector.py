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
EvalTrace collector — aggregates Fred SSE events into an evaluation-ready dict.

Why this module exists:
- evaluators (Promptfoo, deepeval, custom scorers) need the full execution trace,
  not just the final answer — tool calls, tool results, latency, token usage, errors
- all the information is already in the SSE stream; this collector assembles it
  into the stable EvalTrace format defined in docs/rfc/AGENT-EVALUATION-RFC.md
- zero new dependencies: only the Python stdlib is used

How to use it:
- collect SSE events via `AgentPodClient.stream_events()`
- pass the event list to `collect_eval_trace()` along with call metadata
- the returned dict is ready for Promptfoo, deepeval, or custom scorers

Example:
    import time
    from fred_runtime.eval.collector import collect_eval_trace
    started = time.monotonic()
    events = client.stream_events(agent_id=..., message=..., session_id=...)
    trace = collect_eval_trace(
        events, agent_id=..., input=..., session_id=..., started_at=started
    )
"""

import time
from typing import Any


def collect_eval_trace(
    events: list[dict[str, Any]],
    *,
    agent_id: str,
    input: str,
    session_id: str,
    started_at: float,
) -> dict[str, Any]:
    """
    Aggregate a list of SSE event dicts into a structured EvalTrace.

    Why this function exists:
    - encoding the Fred SSE event vocabulary (kind=tool_call/tool_result/final/…)
      in one place keeps that protocol knowledge in fred-runtime
    - everything else — scoring, reporting, baseline comparison — belongs in
      external tooling (Promptfoo, deepeval) that imports this function

    How to use it:
    - call after `AgentPodClient.stream_events()` finishes collecting events
    - record `started_at = time.monotonic()` just before the first HTTP byte

    EvalTrace fields:
    - session_id, agent_id, input  — call identity
    - output                       — canonical final answer (from the `final` event)
    - error                        — first error seen, or None
    - latency_ms                   — wall-clock time from started_at to call end
    - model, finish_reason         — from the `final` event
    - usage                        — {prompt_tokens, completion_tokens}
    - steps                        — ordered list of tool_call / tool_result / final dicts

    Example:
    - `trace = collect_eval_trace(events, agent_id="sql-analyst", input="...", session_id="s1", started_at=t0)`
    """

    output: str = ""
    steps: list[dict[str, Any]] = []
    error: str | None = None
    model: str | None = None
    finish_reason: str | None = None
    usage: dict[str, int] = {}

    for event in events:
        if "error" in event and event.get("kind") not in ("tool_result", "node_error"):
            error = str(event["error"])
            continue

        kind = event.get("kind")

        if kind == "tool_call":
            steps.append(
                {
                    "kind": "tool_call",
                    "name": event.get("tool_name", ""),
                    "input": event.get("arguments"),
                }
            )

        elif kind == "tool_result":
            steps.append(
                {
                    "kind": "tool_result",
                    "name": event.get("tool_name", ""),
                    "output": event.get("content"),
                    "is_error": bool(event.get("is_error", False)),
                }
            )
            if event.get("is_error") and error is None:
                error = str(event.get("content") or "tool_result error")

        elif kind == "node_error":
            error = str(
                event.get("error_message") or event.get("error") or "node_error"
            )

        elif kind == "final":
            content = event.get("content")
            output = content if isinstance(content, str) else ""
            model = event.get("model_name")
            finish_reason = event.get("finish_reason")
            tu = event.get("token_usage") or {}
            if tu:
                usage = {
                    "prompt_tokens": int(tu.get("input_tokens") or 0),
                    "completion_tokens": int(tu.get("output_tokens") or 0),
                }
            steps.append({"kind": "final", "content": output})

    latency_ms = int((time.monotonic() - started_at) * 1000)

    return {
        "session_id": session_id,
        "agent_id": agent_id,
        "input": input,
        "output": output,
        "error": error,
        "latency_ms": latency_ms,
        "model": model,
        "finish_reason": finish_reason,
        "usage": usage,
        "steps": steps,
    }
