## Context

The runtime already raises `tool_approval` through `HumanInputRequest`, and ReAct, Deep, and Graph validate the pending interrupt on resume. The managed frontend has one `HitlPrompt` and one `sendHitlResume` path. A tool-approval request includes the names of every gated call in `pending_calls`. Agent questions use the same card but have a separate skip action.

## Goals / Non-Goals

**Goals:** Remember deliberate approval by tool name within one managed conversation and keep future resumes on the existing runtime path. Share one neutral choice layout across approval and question prompts.

**Non-Goals:** Change operator or capability approval policies, add a server-side grant, or suppress the runtime pause itself.

## Decisions

- Use browser local storage keyed by signed-in user ID, agent instance ID, and session ID. A conversation can be reopened after the browser restarts, so tab-scoped session storage would not cover its lifetime. Store only tool names. Reject malformed storage and avoid reading grants without a user ID.
- The third button is a frontend action that sends the existing `proceed` decision on the wire. It does not add a new runtime choice ID. Remember the prompt's gated tool names only after the resume reaches the runtime; a failed preflight restores the prompt and leaves grants unchanged.
- After the original stream settles, an effect checks each pending `tool_approval` request against the stored names. It resumes automatically only when `pending_calls` is nonempty and all names match. Record one automatic attempt per pending occurrence so a failed resume restores the card instead of looping.
- Keep the runtime gate and per-call authorization unchanged. A forged browser grant can cause the same authenticated client to send an approval automatically, but it cannot remove the runtime pause or grant a tool permission the user lacks.
- Apply the same outlined, vertically stacked choice treatment to approval and agent-question cards. The approval-only third action joins the choice list; the question-only Skip and close controls remain separate.

## Risks / Trade-offs

- [A stored grant has no explicit revoke control] -> Scope it to one conversation and delete it when that conversation is deleted; clearing browser storage also removes it.
- [A later batch includes a new tool] -> Require all gated names to match; otherwise show the entire prompt.
- [A resume request fails or a saved prompt is malformed] -> Restore or retain the manual prompt and prevent repeated automatic attempts for that occurrence.

## Migration Plan

No server or database migration. Shipping the frontend enables the new action; clearing its local-storage keys rolls back remembered grants without changing existing approval history.
