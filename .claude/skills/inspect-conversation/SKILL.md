---
name: inspect-conversation
description: Reconstruct a local conversation from Postgres history and configured traces. Use to explain an answer, attribute concurrent native child/tool activity, or check what evidence an agent received.
user-invocable: true
argument-hint: [session id, or description and approximate time]
---

# Inspect a conversation

Read durable history first, then the configured trace store when available. Neither is a
complete execution transcript by definition: exporter filtering, sampling, failed flushes,
retention and runtime version affect coverage. Report missing evidence explicitly.

## 1. Resolve the session and exchange

Use the sibling `psql` skill for local connection details. Query the `fred` database:

```sql
SELECT session_id, title, user_id, team_id, agent_instance_id, updated_at
FROM session_metadata WHERE title ILIKE '%description%' ORDER BY updated_at DESC;

SELECT rank, exchange_id, role, channel, parts_json
FROM session_history WHERE session_id = '<uuid>' ORDER BY rank;
```

Start with a small preview (`left(parts_json::text, 200)`), then inspect individual rows.
Keep user/tool content private and redact credentials before quoting or sharing it.
History records persisted runtime events; it is not proof that every child event reached
SSE or persistence. Inspect actual channel/part shapes before interpreting them. Tool-call
parts use `name`, `args`, `call_id`; match tool results by `call_id` within the exchange.
Final answers and tool results carry different meaning even if their text is identical.

## 2. Resolve configured tracing

Inspect the running runtime's tracing configuration without printing secrets. If disabled,
unreachable, or empty for this exchange, state that child attribution and model-call detail
cannot be established from history alone. Do not infer absence of execution from no traces.

For the local Langfuse v3 stack, inspect the ClickHouse schema before querying; deployment
names and schema can differ. The local `app-clickhouse` usually holds `traces` and
`observations` in database `default`. If tracing uses another provider, use its supported
read API with the same identifier-based workflow.

```bash
docker exec app-clickhouse clickhouse-client -q \
  "SELECT id, session_id, timestamp, name, metadata FROM traces
   WHERE session_id='<uuid>' ORDER BY timestamp FORMAT Vertical"
```

Correlate `session_id` plus `exchange_id`/`correlation_id` metadata when present. A session
can span multiple exchanges/traces; deduplicate versioned Langfuse rows according to the
installed schema before counting. Timestamp proximity alone is insufficient correlation.

## 3. Attribute calls through the observation tree

Discover observation names from the actual trace rather than filtering to a presumed runtime:

```bash
docker exec app-clickhouse clickhouse-client -q \
  "SELECT id, parent_observation_id, name, start_time
   FROM observations WHERE trace_id='<trace-id>' ORDER BY start_time FORMAT TSV"
```

Build the parent tree using `(trace_id, id)` and `parent_observation_id`; walk ancestors
recursively, since the immediate parent may be middleware/model/framework instrumentation.
Locate native Deep `task` calls and their child spans using recorded names, inputs and
metadata. Match tool-call IDs when exported. ReAct may expose `v2.react.model` and
`v2.react.runtime_tool`; those names are not a universal Deep trace contract. Native
children need not produce another Fred `agent.stream` span.

Concurrent children interleave. Attribute a call only when parent links or explicit
call/child identifiers connect it to that child; mark missing links as unattributed.
Do not relabel a parent tool result as the child's full internal history.

Read bounded payloads for the specific observations relevant to the question:

```bash
docker exec app-clickhouse clickhouse-client -q \
  "SELECT id, parent_observation_id, name, substring(toString(input),1,500),
   substring(toString(output),1,500) FROM observations
   WHERE trace_id='<trace-id>' AND id='<observation-id>' FORMAT Vertical"
```

## 4. Report observations and limits

State the session/exchange/trace identifiers, observed call/result IDs, final answer and
reported token usage where available. Separate direct evidence from hypotheses; identify
missing/filtered traces and unresolved attribution. Exported inputs may themselves be
redacted or truncated, so absence of a field does not prove the model never received it.

Use backend logs for server-side failure context and KPI stores for recorded costs/counts;
correlate explicit IDs when available. Neither automatically reconstructs child inputs.
For a new reproduction, use the sibling `test-agent-instance` skill rather than writing
another execution script.
