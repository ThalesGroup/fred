---
name: test-agent-instance
description: Run a real turn against a local managed agent instance with its team and tuning. Use to reproduce a conversation outside the browser, inspect native Deep task delegation, or verify that a runtime change reaches an instance.
user-invocable: true
argument-hint: [instance or session id, and prompt]
---

# Test a managed instance

Use `scripts/run_agent_turn.py` from this skill directory. It reuses Fred CLI auth and
`AgentPodClient`, sending only `agent_instance_id` with the owning team. A bare template
execution does not reproduce instance tuning. Both `.agents/skills` and `.claude/skills`
resolve this same shared skill; do not install a second copy.

## 1. Resolve identity and instance

Use the sibling `psql` skill to query the local `fred` database:

```sql
SELECT agent_instance_id, team_id, template_id, display_name, enabled
FROM agent_instance WHERE display_name ILIKE '%name%';

SELECT session_id, team_id, agent_instance_id, user_id, title
FROM session_metadata WHERE session_id = '<uuid>';
```

Confirm the selected authenticated user has access to that team. Reuse the cached
`fred-agents-cli --login` session, or set `FRED_USERNAME` and `FRED_PASSWORD` privately
from the developer's existing local fixture/config. Keep passwords out of command
arguments, transcripts and reports. Never invent authorization or copy another user's token.

For this local demo stack, the developer-provided test login is `alice` /
`Azerty123_`. Use it only for local instance tests and pass the password through
`FRED_PASSWORD` without printing it in test artifacts.

Inspect the instance's tuning when diagnosing prompt/capability behavior. Resolve its
runtime binding from the configured runtime catalog; `--pod-url` must target that runtime,
not whichever pod happens to listen on the default port.

## 2. Check running code

Inspect the running backend command and startup/reload logs. Development reload works only
when enabled and when the edited path is watched; production launchers do not reload.
If the process is stale, coordinate a restart with the developer rather than restarting
their backend silently. Record the running revision/config separately from the checkout
being reviewed.

## 3. Execute one turn

From `apps/fred-agents`, using its installed environment:

```bash
./.venv/bin/python ../../.agents/skills/test-agent-instance/scripts/run_agent_turn.py \
  --instance <instance-id> --team <team-id> \
  --out-dir /tmp/agent-turn-unique --message 'Reply with a short greeting; do not use tools.'
```

Run `--help` for endpoint overrides and idle read timeout. Prefer a fresh session and a
harmless prompt: execution can spend model tokens and enabled tools can modify real data.
Pass longer prompts on stdin. `--session` continues a known session after checking its
instance through control-plane; continuation inherits previous history. Fresh runs register
session metadata before execution and abort if registration fails.

The output directory must not exist. It contains private `events.jsonl` (decoded SSE
payloads, in arrival order), `final.md` (complete final-event content), `run.json` (identity
of the run), and `summary.json` (observations). Known login password/access tokens are
redacted; arbitrary tool/user secrets cannot be identified reliably, so review payloads
before sharing. The console prints counts only.

## 4. Interpret evidence

Exit 0 means a final event arrived without execution/node errors or human approval being
requested. Exit 1 indicates incomplete/error/HITL execution; exit 2 indicates setup failure.
A successful process exit alone does not prove the agent answered correctly.

- `final.md` uses the authoritative `final.content`, not concatenated deltas. An interrupted
  stream retains its received events but has no claimed complete answer. Empty final content
  may accompany UI parts: inspect the final event.
- `task` is the default delegation tool; `--fanout-tool` selects another observed tool.
  Peak outstanding calls measures overlapping SSE call/result intervals, not actual
  concurrency. Missing events are not evidence that no child ran.
- Match tool results to `call_id`. Parent SSE may omit native child internals; do not assign
  interleaved deltas to children using time windows. Use the sibling `inspect-conversation`
  skill for trace IDs and parent observation links.
- Token usage and finish reason are provider/runtime reports, not proof of semantic
  completeness. Check requested coverage and final text explicitly.
- Human approval is a pause: this helper never approves or resumes automatically.

Report observed identifiers, counts, final status and limitations separately from hypotheses.
Keep private raw artifacts local, and include only reviewed excerpts in a shared report.
