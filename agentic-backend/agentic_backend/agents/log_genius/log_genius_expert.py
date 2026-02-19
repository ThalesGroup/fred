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

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple, cast

from fred_core import LogEventDTO, LogFilter, LogQuery
from fred_core.logs.log_structures import LogLevel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.constants import END, START
from langgraph.graph import MessagesState, StateGraph

from agentic_backend.application_context import get_app_context, get_default_chat_model
from agentic_backend.common.kf_logs_client import KfLogsClient
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

LEVEL_ORDER: List[str] = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
DEFAULT_MAX_EVENTS = 200
DEFAULT_MAX_GROUPS = 8
DEFAULT_MAX_SAMPLES = 20


@dataclass(frozen=True)
class LogEventSnapshot:
    source: str
    ts: float
    level: str
    logger: str
    file: str
    line: int
    msg: str
    extra: Dict[str, Any] | None


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_msg(msg: str, max_len: int = 180) -> str:
    trimmed = re.sub(r"\s+", " ", msg or "").strip()
    return trimmed[:max_len]


LOG_GENIUS_TUNING = AgentTuning(
    role="log_genius",
    description="Log analysis agent for triage across Agentic and Knowledge Flow.",
    tags=["monitoring", "logs"],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description="Instructions for how LogGenius should analyze recent logs.",
            required=True,
            default=(
                "You are LogGenius, a log triage agent for Fred.\n"
                "Analyze the recent logs and produce:\n"
                "- A short root-cause summary.\n"
                "- 1-3 concrete next steps.\n"
                "- Evidence citations using file:line and timestamp.\n"
                "If you see a 401 with rebac/permission, explicitly call out missing ReBAC permissions.\n"
                "If logs are empty, say so and ask for a wider window.\n"
                "Recent logs context:\n"
                "{log_context}"
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="analysis.window_minutes",
            type="integer",
            title="Window (minutes)",
            description="How far back to scan logs.",
            required=True,
            default=5,
            min=1,
            max=60,
            ui=UIHints(group="Analysis"),
        ),
        FieldSpec(
            key="analysis.limit",
            type="integer",
            title="Fetch limit",
            description="Maximum number of log events to fetch per backend.",
            required=True,
            default=500,
            min=1,
            max=5000,
            ui=UIHints(group="Analysis"),
        ),
        FieldSpec(
            key="analysis.min_level",
            type="select",
            title="Minimum level",
            description="Minimum log level to include.",
            required=True,
            default="WARNING",
            enum=LEVEL_ORDER,
            ui=UIHints(group="Analysis"),
        ),
        FieldSpec(
            key="analysis.max_events",
            type="integer",
            title="Max events in context",
            description="Cap the events included in the LLM context.",
            required=True,
            default=DEFAULT_MAX_EVENTS,
            min=50,
            max=1000,
            ui=UIHints(group="Analysis"),
        ),
        FieldSpec(
            key="analysis.include_agentic",
            type="boolean",
            title="Include Agentic logs",
            description="Include logs from the agentic backend store.",
            required=True,
            default=True,
            ui=UIHints(group="Sources"),
        ),
        FieldSpec(
            key="analysis.include_knowledge_flow",
            type="boolean",
            title="Include Knowledge Flow logs",
            description="Include logs via Knowledge Flow REST API.",
            required=True,
            default=True,
            ui=UIHints(group="Sources"),
        ),
    ],
)


@expose_runtime_source("agent.LogGenius")
class LogGenius(AgentFlow):
    """
    LogGenius — log triage agent (Agentic + Knowledge Flow).
    """

    tuning = LOG_GENIUS_TUNING

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)
        self.model = get_default_chat_model()
        self.kf_logs = KfLogsClient(agent=self)
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", self._run_reasoning_step)
        builder.add_edge(START, "reasoner")
        builder.add_edge("reasoner", END)
        return builder

    def _build_log_query(self) -> Tuple[LogQuery, int, int]:
        window_minutes = self.get_tuned_int(
            "analysis.window_minutes", default=5, min_value=1, max_value=60
        )
        limit = self.get_tuned_int(
            "analysis.limit", default=500, min_value=1, max_value=5000
        )
        max_events = self.get_tuned_int(
            "analysis.max_events",
            default=DEFAULT_MAX_EVENTS,
            min_value=50,
            max_value=1000,
        )
        raw_level = self.get_tuned_any("analysis.min_level")
        min_level: LogLevel = "WARNING"
        if isinstance(raw_level, str) and raw_level in LEVEL_ORDER:
            min_level = cast(LogLevel, raw_level)

        now = datetime.now(timezone.utc)
        since = (now - timedelta(minutes=window_minutes)).isoformat()
        until = now.isoformat()
        q = LogQuery(
            since=since,
            until=until,
            limit=limit,
            order="desc",
            filters=LogFilter(level_at_least=min_level),
        )
        return q, window_minutes, max_events

    @staticmethod
    def _snap(source: str, events: List[LogEventDTO]) -> List[LogEventSnapshot]:
        return [
            LogEventSnapshot(
                source=source,
                ts=e.ts,
                level=e.level,
                logger=e.logger,
                file=e.file,
                line=e.line,
                msg=e.msg,
                extra=e.extra,
            )
            for e in events
        ]

    async def _fetch_logs(
        self, log_query: LogQuery
    ) -> Tuple[List[LogEventSnapshot], List[str]]:
        events: List[LogEventSnapshot] = []
        warnings: List[str] = []

        include_agentic = bool(self.get_tuned_any("analysis.include_agentic"))
        include_kf = bool(self.get_tuned_any("analysis.include_knowledge_flow"))

        if include_agentic:
            try:
                store = get_app_context().get_log_store()
                result = await asyncio.to_thread(store.query, log_query)
                events.extend(self._snap("agentic", result.events))
            except Exception as e:
                logger.warning("LogGenius: agentic logs query failed: %s", e)
                warnings.append(f"agentic logs query failed: {e}")

        if include_kf:
            try:
                result = await self.kf_logs.query(log_query)
                events.extend(self._snap("knowledge_flow", result.events))
            except Exception as e:
                logger.warning("LogGenius: knowledge-flow logs query failed: %s", e)
                warnings.append(f"knowledge-flow logs query failed: {e}")

        return events, warnings

    def _summarize_counts(self, events: List[LogEventSnapshot]) -> List[str]:
        counts: Dict[str, Dict[str, int]] = {}
        for e in events:
            counts.setdefault(e.source, {})
            counts[e.source][e.level] = counts[e.source].get(e.level, 0) + 1

        lines: List[str] = []
        for source in sorted(counts.keys()):
            level_counts = counts[source]
            parts = []
            for lvl in LEVEL_ORDER:
                if lvl in level_counts:
                    parts.append(f"{lvl}:{level_counts[lvl]}")
            line = f"- {source}: {', '.join(parts) if parts else 'no events'}"
            lines.append(line)
        return lines

    def _group_events(self, events: List[LogEventSnapshot]) -> List[Dict[str, Any]]:
        groups: Dict[Tuple[str, str, str, int, str], Dict[str, Any]] = {}
        for e in events:
            msg_key = _normalize_msg(e.msg)
            key = (e.source, e.level, e.file, e.line, msg_key)
            if key not in groups:
                groups[key] = {
                    "source": e.source,
                    "level": e.level,
                    "file": e.file,
                    "line": e.line,
                    "msg": msg_key,
                    "count": 1,
                    "first_ts": e.ts,
                    "last_ts": e.ts,
                }
            else:
                g = groups[key]
                g["count"] += 1
                g["first_ts"] = min(g["first_ts"], e.ts)
                g["last_ts"] = max(g["last_ts"], e.ts)

        ordered = sorted(
            groups.values(),
            key=lambda g: (-g["count"], -g["last_ts"]),
        )
        return ordered

    def _rule_hints(self, events: List[LogEventSnapshot]) -> List[str]:
        hints: List[str] = []
        seen: set[str] = set()

        for e in events:
            blob = (e.msg or "").lower()
            if e.extra:
                try:
                    blob += " " + json.dumps(e.extra).lower()
                except Exception:
                    logger.warning("LogGenius: failed to json.dumps log extra")
                    pass

            if (
                ("401" in blob or "unauthorized" in blob)
                and ("rebac" in blob or "permission" in blob or "forbidden" in blob)
                and "rebac" not in seen
            ):
                seen.add("rebac")
                hints.append(
                    f"- Missing ReBAC permission (evidence: {_fmt_ts(e.ts)} {e.file}:{e.line} {e.msg})"
                )

            if (
                "connection refused" in blob or "connection reset" in blob
            ) and "conn" not in seen:
                seen.add("conn")
                hints.append(
                    f"- Downstream service connectivity issue (evidence: {_fmt_ts(e.ts)} {e.file}:{e.line} {e.msg})"
                )

            if ("timeout" in blob or "timed out" in blob) and "timeout" not in seen:
                seen.add("timeout")
                hints.append(
                    f"- Timeout from dependency or upstream (evidence: {_fmt_ts(e.ts)} {e.file}:{e.line} {e.msg})"
                )

        return hints

    def _build_log_context(
        self,
        *,
        events: List[LogEventSnapshot],
        warnings: List[str],
        window_minutes: int,
        max_events: int,
    ) -> str:
        lines: List[str] = [f"Window: last {window_minutes} minutes."]

        if warnings:
            lines.append("Warnings:")
            for w in warnings:
                lines.append(f"- {w}")

        if not events:
            lines.append("No log events in this window.")
            return "\n".join(lines)

        events_sorted = sorted(events, key=lambda e: e.ts)
        if len(events_sorted) > max_events:
            events_sorted = events_sorted[-max_events:]

        lines.append("Counts by source/level:")
        lines.extend(self._summarize_counts(events_sorted))

        groups = self._group_events(events_sorted)[:DEFAULT_MAX_GROUPS]
        if groups:
            lines.append("Top groups:")
            for g in groups:
                lines.append(
                    f"- {g['source']} {g['level']} {g['file']}:{g['line']} "
                    f"x{g['count']} first={_fmt_ts(g['first_ts'])} "
                    f"last={_fmt_ts(g['last_ts'])} msg={g['msg']}"
                )

        samples = events_sorted[-DEFAULT_MAX_SAMPLES:]
        if samples:
            lines.append("Sample lines:")
            for e in samples:
                lines.append(
                    f"- {_fmt_ts(e.ts)} [{e.source}] [{e.level}] {e.file}:{e.line} {e.msg}"
                )

        hints = self._rule_hints(events_sorted)
        if hints:
            lines.append("Rule hints:")
            lines.extend(hints)

        return "\n".join(lines)

    async def _run_reasoning_step(self, state: MessagesState):
        if self.model is None:
            raise RuntimeError(
                "LogGenius: model is not initialized. Call async_init() first."
            )

        try:
            log_query, window_minutes, max_events = self._build_log_query()
            events, warnings = await self._fetch_logs(log_query)
            log_context = self._build_log_context(
                events=events,
                warnings=warnings,
                window_minutes=window_minutes,
                max_events=max_events,
            )

            tpl = self.get_tuned_text("prompts.system") or ""
            system_text = self.render(
                tpl,
                log_context=log_context,
                window_minutes=window_minutes,
            )
            if "{log_context}" not in tpl:
                system_text = f"{system_text}\n\nRecent logs:\n{log_context}"

            history = [
                m
                for m in self.recent_messages(state["messages"], max_messages=6)
                if isinstance(m, (HumanMessage, SystemMessage))
            ]
            messages = self.with_system(system_text, history)
            messages = await self.with_chat_context_text(messages)

            response = await self.model.ainvoke(messages)

            md = getattr(response, "response_metadata", None)
            if not isinstance(md, dict):
                md = {}
            md["log_window_minutes"] = window_minutes
            md["log_event_count"] = len(events)
            response.response_metadata = md

            return {"messages": [response]}

        except Exception:
            logger.exception("LogGenius: unexpected error")
            fallback = await self.model.ainvoke(
                [
                    HumanMessage(
                        content="An error occurred while analyzing logs. Please try again."
                    )
                ]
            )
            return {"messages": [fallback]}
