## Context

Since the first v2 ReAct loop, a tool error was surfaced as the final response and the
model's later text was discarded ("the LLM is NOT trusted to relay it"). §8.42 (#2244)
narrowed this to rounds where every call failed, because partial failures were throwing
away good results. §8.74 then made the error text itself safe (Fred-owned typed text or a
bounded generic message, never raw `message.content`). #2588 asked how to exempt Fred
policy refusals (Deep's filesystem gate, the per-turn tool-call cap) from the override
while keeping it for genuine failures, and noted no signal distinguishes the two.

## Goals / Non-Goals

**Goals**

- Never replace an answer the model actually produced after a failed round.
- Keep a clear, safe error when the model produced nothing after the failure.
- Keep the §8.74 text boundary for every user-facing error string.

**Non-goals**

- A policy-refusal marker on `ToolMessage`/`ToolInvocationResult`.
- Localizing the generic message or changing the tool-row text of a cap refusal.
- Logging when `ToolCallLimitMiddleware` fires (separate follow-up in #2588's comments).

## Decisions

### D1 — The model's answer wins; the error is the fallback

`FinalRuntimeEvent.content` is the model's last non-tool-calling answer when it is
non-empty and arrived after the last error that claimed the final response. Otherwise the
claimed error text is used, as before. Assistant deltas are no longer suppressed, so the
streamed text and the final content agree.

Rejected: a policy-refusal marker (#2588's candidate). It needs a new contract field set by
every guard, still leaves genuine failures (Workspace briefly unavailable, a tool's
revision request) discarding honest answers, and the observed incidents involved both
kinds.

Rejected: appending a fixed notice ("some tool calls failed") to the model's answer. The
runtime has no locale, so the notice would be English inside French answers, it would
differ from the streamed text, and the failed rows already carry that information.

Rejected: keeping the answer only when it does not claim success. Detecting a success
claim in free text is a heuristic that cannot be made reliable.

### D2 — The trust concern is covered where it already is for partial failures

The original override guarded against a model misreporting a failure. Since §8.42 the
runtime already trusts the model to report a failed call when one sibling succeeded; the
same safeguards now apply to a wholly-failed round:

- every failed call keeps `is_error=True` and its §8.74-bounded text on its tool row;
- the read-only platform instructions tell the model never to claim a call it did not make
  and never to paste a raw tool error as its answer.

## Risks / Trade-offs

- A model can still claim success after a failure; the failed tool row is then the only
  contradicting signal. This is the trade-off already accepted for partial failures, and it
  is the explicit reviewer question on #2588.
- The model may paraphrase raw tool content it received; this was already true for partial
  failures and for any successful result.
- Performance: one fewer flag on the per-chunk path; no I/O, awaits, or new state.

## Migration Plan

No data, API, or configuration migration. Rollback is a plain revert.

## Open Questions

- Reviewer to confirm that relying on the failed tool rows (no appended notice) is enough
  for the trust concern. Archive this change only after `reliable-agent-work-completion`
  is archived, since this delta modifies its requirement.
