---
name: inspect-conversation
description: Reconstruct what an agent actually did in a past chat session on the local stack — messages and tool calls from Postgres, sub-agent fan-out and tool arguments from the Langfuse trace. Use when asked why an agent answered as it did, to replay a session outside the browser, to attribute a tool call or error to one specific sub-agent, or to check whether an agent really received the data it claimed.
user-invocable: true
argument-hint: [session id, or what happened and roughly when]
---

# Inspect a conversation

Two stores hold a session, and each is blind where the other sees. Read both.

| Store | Holds | Blind to |
| --- | --- | --- |
| Postgres `session_history` | What the user saw: their messages, the agent's thoughts, its tool calls and results, its final answers | Everything inside a sub-agent |
| Langfuse (ClickHouse) | Every LLM call and tool call with full arguments and responses, nested parent→child | Nothing, when tracing is on — and nothing at all when it is off |

The **attribution** work in step 4 — deciding which sub-agent made a given call — exists only in
Langfuse. With tracing off, a `run_subagent` fan-out is opaque from Postgres alone.

## 1. Resolve the session

The user usually gives a session id, or a description and a rough time.

```sql
SELECT session_id, title, user_id, team_id, agent_instance_id, updated_at
FROM session_metadata WHERE title ILIKE '%exigences%' ORDER BY updated_at DESC;
```

Connection details: the `psql` skill. The database is `fred`.

## 2. Postgres — what the user saw

```sql
SELECT rank, role, channel, parts_json
FROM session_history WHERE session_id = '<uuid>' ORDER BY rank;
```

`role` is `user` / `assistant` / `tool`; `channel` is `final`, `thought`, `tool_call` or
`tool_result`. `parts_json` is an array — a `tool_call` part carries `name`, `args` and
`call_id`, and the matching `tool_result` carries the same `call_id` plus `content` and
`latency_ms`.

Two shapes worth knowing before you read a row count as evidence:

- **Sub-agent internals are absent.** A child turn writes nothing here. The parent records only
  `run_subagent`'s final answer, as one ordinary `tool_result`. An error raised inside a child
  never appears — grepping `parts_json` for it returns nothing, which means "not the parent",
  not "did not happen".
- **Streamed `thought` rows fragment.** Reasoning deltas can land as dozens of 3-20 character
  rows. Judge a turn by its `tool_call` / `tool_result` / `final` rows.

Start wide and cheap, then open single rows:

```bash
# survey
docker exec app-postgres psql -U admin -d fred -c \
  "select rank, role, channel, left(parts_json::text, 200) from session_history
   where session_id='<uuid>' order by rank;"

# which tools this agent has
docker exec app-postgres psql -U admin -tA -d fred -c \
  "select distinct parts_json->0->>'name' from session_history
   where session_id='<uuid>' and channel='tool_call';"

# one full argument, without flooding context
docker exec app-postgres psql -U admin -tA -d fred -c \
  "select parts_json::text from session_history where session_id='<uuid>' and rank=30;" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['args']['prompt'])"
```

## 3. Langfuse — what actually ran

Langfuse v3 keeps traces in the `app-clickhouse` container, database `default`, tables `traces`
and `observations`. Query it directly; the web UI cannot join or grep.

`traces.session_id` **is** the Fred session id, so the two stores join on a real key. There is
**one trace per exchange** (per user turn), so a five-turn session has five traces:

```bash
docker exec app-clickhouse clickhouse-client -q \
  "select id, timestamp, name from traces where session_id='<uuid>'
   order by timestamp format TSV"
```

`traces.metadata` carries `agent_id`, `exchange_id` and `correlation_id`.

Three observation names make up a turn:

| `name` | Is |
| --- | --- |
| `agent.stream` | One agent turn — the parent's, or one sub-agent's |
| `v2.react.model` | One LLM call |
| `v2.react.runtime_tool` | One tool call; `input` is the arguments, `output` the result |

Every tool call of one exchange, in order:

```bash
docker exec app-clickhouse clickhouse-client -q \
  "select start_time, substring(toString(input),1,150), substring(toString(output),1,200)
   from observations where trace_id='<trace>' and name='v2.react.runtime_tool'
   order by start_time format Vertical"
```

Hunting a specific failure whose exchange you do not know yet:

```bash
docker exec app-clickhouse clickhouse-client -q \
  "select trace_id, start_time, substring(toString(input),1,200), toString(output)
   from observations where output like '%Not authorized%'
   order by start_time desc limit 10 format Vertical"
```

## 4. Attribution — which sub-agent made this call

`parent_observation_id` builds the tree, and one `run_subagent` fan-out nests like this:

```
agent.stream                  the parent turn
└── v2.react.runtime_tool     the run_subagent call
    └── agent.stream          the child turn
        ├── v2.react.model    the child's LLM calls
        └── v2.react.runtime_tool   the child's own tool calls
```

So a child's whole history is the subtree under its `agent.stream` id:

```bash
docker exec app-clickhouse clickhouse-client -q \
  "select start_time, id, parent_observation_id, name from observations
   where trace_id='<trace>' order by start_time format TSV"
```

Read that once and map each `agent.stream` id to a child, then filter tool calls by
`parent_observation_id`. Timestamps alone will mislead you: parallel children interleave, so
a successful query at 15:40:52 and a file write at 15:40:26 routinely belong to different
sub-agents. Attribute before concluding — it is the difference between "an agent got a 403"
and "*this* child got a 403, never retried, and wrote its answer anyway".

## 5. Keep the output small

Tool arguments and results here run to tens of KB, and `select *` will flood the context.

- Truncate in the query: `substring(toString(input),1,150)`.
- `format Vertical` to survey, `format TSV` for id/tree listings.
- Pull one full record at a time with `format TabSeparatedRaw`, piped into `python3 -c` to print
  just the field you need.

## What these two stores will not answer

- **OpenSearch / the KPI store** records that a turn happened and what it cost —
  `agent.subagent_turn_completed` gives per-child spend and depth — and never what was called or
  what came back.
- **Backend logs** (`fred-agents`, `knowledge-flow`) show a failure from the server's side, with
  no way to attribute it to a child.

Reach for either only when the question is genuinely about cost or about server-side state.
