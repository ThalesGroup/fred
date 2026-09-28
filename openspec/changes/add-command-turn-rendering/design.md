## Context

See proposal.md — Why. The behaviour contract is in
`specs/prompt-commands/spec.md`; this document covers only how it is reached,
and the one question the RFC left unanswered.

What the existing code already gives, and what it does not:

- `ChatMessage` (`libs/fred-core/fred_core/history/history_schema.py`) holds
  `parts` and a `metadata: ChatMetadata`. `ChatMetadata` is
  `ConfigDict(extra="allow")`, so an extra key stores and round-trips with no
  schema change, and an older reader ignores it.
- `postgres_history_store.py` persists `parts_json` and the metadata as
  written; nothing there needs to learn about commands.
- The user turn is built from a bare string: `agent_app.py` calls
  `make_user_text(session_id, exchange_id, rank, request_message)`. But
  `_AgentExecuteRequest.context` travels alongside it as an open
  `dict[str, Any]`, is read by key where the turn is assembled
  (`session_id`, `user_id`, `team_id`), and the frontend already sends it as
  `runtime_context`. That is the seam.

## Goals / Non-Goals

**Goals:**

- A command turn that reads as its command, and replays to the model as its
  full text.
- Every merged state correct: this change is invisible until the trigger slice
  writes a descriptor.
- Additive on the wire, so an unaware reader degrades rather than breaks.

**Non-Goals:**

- The `/` trigger, the menu, the placeholder, the Help Center. Next slice.
- Any agent, capability or runtime-execution behaviour. The agent receives an
  ordinary turn and knows nothing about commands.
- Prompt versioning. The turn keeps its own text precisely so no version
  history is needed.

## Decisions

**Carry the descriptor in the existing `context` dict.** It is a client fact —
which command the user typed, what they appended — and `context` is already
the channel for exactly that class of per-turn caller fact. One key added, one
optional argument threaded to `make_user_text`, no model touched.

`RUNTIME-EXECUTION-CONTRACT.md` still gets a line: a new `context` key is a
contract addition even when no schema changes, and the next reader needs to
know the key exists and is optional.

Alternative rejected: a typed descriptor field on `_AgentExecuteRequest`.
Better typing — validation and an OpenAPI shape the frontend could generate
against — but it extends a frozen model to gain a type on one optional key.
Not worth it. If the descriptor ever grows beyond "render this turn
differently", promoting it to a typed field is a contained follow-up.

Alternative rejected: deriving the descriptor server-side by matching the sent
text against the team's prompts. It would break the moment two prompts share
text or a prompt is edited, and it puts a lookup on the hot send path for
something the client already knows.

Alternative rejected: storing the descriptor only in the browser. It would not
survive a reload, and the transcript must render the same way on every device.

Alternative rejected: storing it in control-plane against `exchange_id`. It
splits one turn across two stores, with the ordering and orphan-row problems
that follow.

**Store the assembled text, and read the panel from it.** Both halves of the
same decision. `prompt.text` is overwritten on edit, `prompt.version` is a
counter on the live row with no history table, and a prompt can be deleted —
so `prompt_id` is not a durable pointer to what was said. The turn keeps its
own content and the panel reads that. The id in the descriptor is for
attribution ("this came from *Revue hebdo*"), never for resolution.

`session_context_prompts` references prompts by id with no copy; that is a
precedent for referencing live session state, not a model for a historical
record.

**Render by presence of the descriptor, not by parsing the text.** The
renderer picks the command component when the descriptor is there and the text
part otherwise. Sniffing a leading `/` out of the content would misfire on any
turn a user began with a slash.

**Keep the component inside the user bubble** (RFC §2.8): no fill of its own
so the bubble's `--secondary-container` shows through, a `1px solid
--outline-muted` outline to mark it actionable, `--radius-xs` well inside the
bubble's own `--radius-m` so it reads as nested rather than as a second
bubble, and hover through `--state-on-secondary-container-hover` — the state
layer mixed from the bubble's own content colour, not a generic surface tone.
Design-system tokens only; no new token for this work.

## Risks / Trade-offs

**The descriptor rides untyped in `context`.** → No validation, and the
frontend cannot generate against it. Accepted: the key is optional and drives
rendering only, so a malformed one degrades to a plain text turn. The parse
site owns the shape and must tolerate junk rather than assume it.

**This change ships invisible.** → Deliberate. The alternative order makes the
trigger slice briefly print prompt text in the chat body, which the RFC rules
out. Renderer first is the only order where no merged state is wrong for
users.

**The descriptor is client-supplied and therefore untrusted.** → It decides
rendering only. The text sent to the model is the turn's content, which the
client was always free to set; a forged descriptor can mislabel a turn in that
user's own transcript and nothing more. Worth stating so nobody later treats
it as provenance.

**A turn's stored text can be long where the prompt is long.** → Unchanged
from today: a user who pasted the same prompt by hand stores exactly as much.
The trigger changes how the text is produced, not how much of it there is.

**The component must be reachable without a mouse.** → It is an activatable
control, not a decorated span: keyboard-focusable, with an accessible name
naming the command, so opening the panel is not a click-only path.

## Migration Plan

No data migration and no schema change: `ChatMetadata` already accepts the
key, and every existing turn simply has no descriptor.

Deployment order does not matter. A newer frontend against an older runtime
sends a field the ask request rejects as unknown — the same failure shape as
any other request-field addition — and until the trigger slice ships, nothing
sends one at all.
