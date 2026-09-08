---
name: test-agent-instance
description: Run a real turn against a managed agent instance on the local stack and inspect what the agent actually did — event trace, tool fan-out, token usage, final answer. Use when asked to test or talk to an agent instance, reproduce a chat session outside the browser, debug a sub-agent (`run_subagent`) fan-out, or check whether a runtime or middleware change reached agent behaviour. `fred-agents-cli` cannot reach a managed instance; this can.
user-invocable: true
argument-hint: [agent instance id or session id, and what to ask it]
---

# Test an agent instance

A **managed agent instance** is a tuned agent living in a team (`agent_instance` table): a
template plus its own prompt, capability selection and config. It is what the frontend
actually executes, and what a user means by "my agent".

`fred-agents-cli` cannot run one. Its REPL only ever sends `agent_id` (the bare template),
and the pod rejects a request carrying both ids — `_AgentExecuteRequest` requires *exactly
one* of `agent_id` or `agent_instance_id` (`agent_app.py`). Testing the template instead of
the instance silently drops the tuning, which is usually the whole thing under test.

`scripts/run_agent_turn.py` posts to `/agents/execute/stream` with `agent_instance_id` +
`runtime_context.team_id`, reusing `fred_core.cli.auth` for the bearer token. Run it; do not
rebuild it inline.

## 1. Find the instance and team

The user usually names a session or an agent, not ids. Resolve them against the `fred`
database (the `psql` skill, or `PGPASSWORD=… psql -h localhost -p 5432 -U fred -d fred`):

```sql
-- from an agent name
SELECT agent_instance_id, team_id, template_id, display_name, enabled
FROM agent_instance WHERE display_name ILIKE '%tv%';

-- from a session the user points at
SELECT session_id, team_id, agent_instance_id, user_id, title
FROM session_metadata WHERE session_id = '<uuid>';
```

Ask which identity to run as if it is not obvious. Local demo users (`alice`, `bob`, …) take
their password from `apps/control-plane-backend/tests/fixtures/import_export/demo_provisioning/users.json`.
The instance's team is private: an identity outside it fails the ReBAC check.

## 2. Confirm the pod runs the code you are testing

**The fred-agents uvicorn has no `--reload`.** Source edits under `libs/` and `apps/` reach it
only on restart, and a stale pod makes a change look like it did nothing:

```bash
ps -eo pid,lstart,args | grep fred_agents.main | grep -v grep   # pod start time
stat -c '%y' <the file you edited>                              # must be older
```

Ask the developer to restart when the file is newer — the pod runs in their terminal.

## 3. Run the turn

From `apps/fred-agents` (its venv holds `fred_runtime` and `fred_core`):

```bash
FRED_USERNAME=alice FRED_PASSWORD=<fixture password> \
./.venv/bin/python ../../.claude/skills/test-agent-instance/scripts/run_agent_turn.py \
  --instance <agent_instance_id> --team <team_id> \
  --out-dir /tmp/agent-turn --message "…"
```

Pass a long prompt on stdin instead of `--message`. `--session <id>` continues an existing
conversation; omitted, each run starts fresh — prefer fresh, since prior history changes what
the agent does. Add `--fanout-tool <name>` to summarise a tool other than `run_subagent`.

A turn is a real LLM spend and can run for minutes. Run it once, in the foreground, and read
the trace rather than re-running to look again.

Output: a live trace on stdout, a report, and in `--out-dir` the raw `events.jsonl` plus
`final.md` (the whole answer — only its head is printed).

## 4. Read the trace

The report gives wall clock, tool-call count, fan-out width, per-child duration and size, and
the final answer's `finish_reason` and token usage. Five traps hide inside a run that looks
successful:

- **Sub-agent output lands on the parent's stream.** A child's graph runs inside the parent's
  tool coroutine, so LangChain callbacks propagate and the child's `assistant_delta` and
  `thought_*` events surface on the parent's SSE stream — and persist into the parent's
  `session_history`. Text streamed between a fan-out `tool_call` and its `tool_result` is the
  children's, not the orchestrator's. Attribute it to the child.
- **An over-limit tool call reports success.** Past `MAX_TOOL_CALLS_PER_TURN`
  (`apps/fred-agents/fred_agents/tool_pacing.py`), `ToolCallLimitMiddleware` returns
  `"Tool call limit exceeded"` as a tool result with `is_error: false` in ~2 ms. A delegation
  that never ran looks like one that succeeded. Compare the fan-out count against the tool
  total before trusting a merged answer.
- **A truncated answer still says `finish_reason: "stop"`.** Check whether `final.md` ends
  mid-sentence, and whether it covers every range the children were assigned. Fan-out
  multiplies output volume, and the merge step is the funnel.
- **A rate-limited child costs a range.** `RateLimitRetryMiddleware` absorbs provider 429s and
  reports `"The model provider is rate-limiting this deployment"`. The turn survives; that
  child's work is still gone. Raw `Error code: 429 - {...}` instead means the middleware never
  ran — suspect a stale pod (step 2).
- **The session appears in the UI only once the control plane knows it.** The script creates
  the `session_metadata` row before executing. With `--no-register` the turn runs and persists
  history that no UI can reach.

Report what the trace shows, quoting the numbers. The tuned instance's own prompt drives most
of the behaviour: read `agent_instance.tuning_json` before calling a result a runtime bug.
