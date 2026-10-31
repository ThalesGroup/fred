---
name: fred-performance-campaign-runner
description: Run guarded, repeatable local performance campaigns against FRED's Swift managed-SSE question/answer path using the canonical mock OpenAI server. Use only for an explicitly requested local campaign against that supported legacy protocol; never select it automatically for a Weaver change. Produces durable redacted artifacts and a fact-versus-hypothesis report. Do not use against shared, staging, or production endpoints.
---

# FRED Performance Campaign Runner

Run the campaign with the bundled `scripts/run_campaign.py`; do not recreate
its orchestration by hand. This skill complements `fred-performance-reviewer`:
the runner collects evidence, then the reviewer interprets hot paths and
findings. It never claims a performance gain from instrumentation alone.

## Preconditions

1. Read the active checkout's `AGENTS.md`, applicable nested instructions and
   the current endpoint/model configuration. Check the script's protocol against
   the actual target before any traffic; it is not automatically Weaver-compatible.
2. Verify that the target is the local Swift managed SSE endpoint and that the
   selected personal-space agent instance routes to `mock-openai-chat`.
3. Require `AGENTIC_TOKEN` in the environment. Never request it in chat, pass
   it on the command line, or print it.
4. Ensure the operator is not simultaneously using the laptop for meaningful
   work. The script refuses non-loopback endpoints and checks memory/load.
5. Do not edit `config.yaml` to tune a run. Start the canonical mock with
   `RESPONSE_DELAY_MS=1000 SUMMARY_LOG_INTERVAL_MS=1000 make run`, or verify an
   already-running mock exposes that exact profile through `/health`.

The mock has deterministic response delay but emits essentially one response
chunk and has no fault injection. This campaign validates server-side FRED
concurrency and robustness, not browser rendering, real-provider variability,
token-by-token streaming, rate limiting, or production capacity.

## Mandatory confirmation flow

Resolve the actual Fred and mock checkouts and a scratch artifact destination.
Pass `--fred-root`, `--mock-root`, `--results-root` and the verified endpoint/metrics
arguments explicitly in both plan and execution. The script's historical personal
paths and port defaults are not configuration authority. Use the script path
relative to this skill directory, not an assumed repository-root script.

First show the plan without executing:

```bash
python3 scripts/run_campaign.py --plan
```

Before any requests, tell the user the exact target, maximum concurrency,
request count, expected duration, mock delay, and artifact directory. Use existing explicit authorization when it already covers those limits; otherwise
obtain confirmation before traffic. Then run with both matching confirmation values:

```bash
AGENTIC_TOKEN="$AGENTIC_TOKEN" python3 scripts/run_campaign.py \
  --execute \
  --confirm-max-clients 50 \
  --confirm-total-requests 266 \
  --agent-instance-id "<UUID>" \
  --team-id "personal-<ADMIN_UID>"
```

Use `--start-mock` only when the canonical mock is not already running. The
script starts only that process and stops only the process it owns. If another
mock is alive with a different profile, abort; never kill or reconfigure it.

Overload is a separate experiment. Explain that it adds 75 concurrent requests
plus a 1x3 recovery probe. Obtain authorization for that larger plan unless the
user already explicitly authorized it, then add:

```text
--allow-overload --confirm-overload-max-clients 75 --confirm-total-requests 344
```

Never silently raise these limits.

## Campaign contract

The default consolidation ladder is:

| Stage | Clients x requests/client | Purpose |
| --- | ---: | --- |
| preflight | 1x1 | Validate auth, routing, SSE final, mock model/profile |
| baseline | 1x10 | Establish the warm sequential reference |
| scale-05 | 5x3 | Detect immediate serialization/pool contention |
| scale-10 | 10x3 | Check the first meaningful concurrency level |
| scale-20 | 20x3 | Consolidate scaling behavior |
| scale-50 | 50x3 | Find an obvious knee without abusing the workstation |
| overload, opt-in | 75x1 | Observe controlled saturation |
| recovery, opt-in | 1x3 | Prove service recovery after saturation |

The preflight is excluded from comparisons but included in the request budget.
Use the same commit, agent instance, team, prompt, mock profile, replica count,
and host conditions for comparisons.

The script stops rather than pushing onward when:

- preflight/model/profile/metrics validation fails;
- benchmark errors exceed 1%;
- median latency exceeds 3x the 1x10 baseline;
- available memory falls below 20% or host load per CPU exceeds 0.85;
- a stage times out.

An adaptive stop is evidence, not a failed automation run. Preserve and report
the last safe stage and the first degraded stage.

## Interpret and report

Read `references/report-contract.md`, the generated `report.md`,
`campaign.json`, per-stage JSON, mock health snapshots/logs, and Prometheus
snapshots. Then invoke `fred-performance-reviewer` on the artifacts and relevant
hot-path code.

Separate:

- observed facts;
- derived values such as ratios and deltas;
- hypotheses requiring code inspection or another controlled experiment.

Prioritize LLM latency, tool latency, then runtime/binding/authz/persistence.
Report findings with evidence, impact and limits in the requested artifacts or
current task/issue. Do not create a standing documentation/finding corpus.

End with one of:

- `PASS`: no obvious knee or robustness defect within the tested envelope;
- `PASS WITH FINDINGS`: usable baseline plus bounded improvements to pursue;
- `STOPPED AT <stage>`: adaptive guard triggered;
- `INVALID`: setup, routing, metrics, or mock contract was not trustworthy.

Never convert this local mock result into a production capacity claim.
