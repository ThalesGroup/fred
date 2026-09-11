## Context

The resume path validates `request.interrupt_id` against the ids of the checkpoint's
pending `__interrupt__` writes (`_pending_react_v2_interrupt_ids`), and the SQL claim
table keys single-use admission on `(thread_id, checkpoint_ns, interrupt_id)`. Both rest
on the same FRED-specific fact, documented in three places: the platform HITL middleware
has exactly one `interrupt()` call site, so distinct occurrences always land in distinct
LangGraph tasks and receive distinct ids.

LangGraph itself does not guarantee that. `Interrupt.id` is a hash of the interrupted
task's checkpoint namespace, so two `interrupt()` calls in one task share it and are
matched by call order - already pinned against the installed version by
`test_langgraph_interrupt_id_semantics.py`. A probe confirmed the consequence for the
tool the epic introduces: `ToolNode` executes all of a turn's tool calls in one task, so
N tool-raised pauses in one turn share a single id, and a targeted resume re-interrupts
on the next sibling rather than distinguishing them.

## Goals / Non-Goals

Goals:

- Make the identity of one pause explicit and verifiable end to end.
- Keep single-use admission correct when siblings share an `interrupt_id`.
- Give a human answer a truthful storage shape, and let one exchange hold several.
- Change nothing observable for the single-pause flows that exist today.

Non-Goals:

- The `ask_user` tool, its composer control, and its skip path (change 2).
- HITL UI rework and free text on the approval gate (change 3).
- Pause lifetime, expiry, orphan recovery, and a per-turn question cap: those stay with
  epic #1080, whose design gate has not been passed.
- Sub-agent HITL at depth >= 1.

## Decisions

### Derive the occurrence identifier from the tool call, do not generate one

`occurrence_id` is the `tool_call_id` of the call that raised the pause, not a fresh
identifier minted at pause time.

This is forced by LangGraph's resume semantics rather than chosen for elegance: a resumed
task is replayed from the top, so anything generated per execution - a `uuid4()`, a
counter, a timestamp - would differ between the pause and its replay and would fail its
own validation. `tool_call_id` is assigned by the model call that requested the tool, is
already checkpointed in the assistant message, and is unique per call within a turn.

The field stays optional. A pause raised outside any tool call - the approval gate, and
the legacy Graph runtime - has no tool call to derive from, and for those the existing
one-occurrence-per-task invariant still holds, so `interrupt_id` alone remains sufficient.
Validation therefore requires the pair only when the pending occurrence declares one,
which is what keeps this change invisible to today's flows.

The same replay rule constrains who may raise a pause at all, which is why the contract
is worded around a tool call rather than an arbitrary call site: any side effect performed
inside a tool *before* its pause is replayed when the resumed task re-executes. A pause is
therefore only safe in a tool that does nothing but ask. That rules out pausing in the
middle of an effectful business tool, and it is the reason the epic's trigger is a
dedicated, pure tool rather than a `request_human_input()` an author could call from
anywhere.

### Extract pending occurrences, not just pending ids

`_pending_react_v2_interrupt_ids` returns a set of ids read from the pending writes. It
becomes a function returning `(interrupt_id, occurrence_id | None)` pairs, read from the
same writes: the interrupt's payload is the serialized human input request, so the
occurrence identifier travels with it and needs no second lookup.

The surrounding constraint is preserved: this runs before authorization and before the
agent definition is resolved, so it must keep reading `CheckpointTuple.pending_writes`
directly rather than building a compiled graph to call `aget_state`.

### Key the claim by occurrence without altering the claim table

The claim table is deliberately not Alembic-tracked: it self-initializes through
`create_all`, which creates a missing table but never alters an existing one. Adding a
primary-key column would therefore need manual DDL on every existing deployment, for a
table whose whole purpose is short-lived admission bookkeeping.

Instead, the claim's `interrupt_id` column holds the occurrence key: the bare
`interrupt_id` when no `occurrence_id` exists, and a composite of the two when one does.
The column is already an opaque string to every query - all of them match it for exact
equality - so uniqueness per occurrence is obtained with no schema change and no
migration. The composite form must be unambiguous enough that a bare id can never collide
with a composite one.

Alternative considered and rejected: add an `occurrence_id` primary-key column. Cleaner to
read, but it requires hand-written DDL outside the migration system this repository
otherwise keeps strictly linear, and it buys nothing a composite key does not.

### Store the answer truthfully rather than reinterpreting `choice_id`

`HitlResponsePart.choice_id` currently doubles as the free-text field, by a runtime
convention inherited from `choice_step`. It gains a sibling text field instead, and
`choice_id` becomes optional so a pure free-text answer records no choice.

Existing rows are not rewritten and not reinterpreted. A stored `choice_id` keeps
rendering as it does today; only new rows use the new shape. Message parts are stored as
JSONB, so this is an additive model change with no migration.

## Risks / Trade-offs

- **A second identity field to keep straight.** The contract already carries
  `checkpoint_id` (legacy Graph) and `interrupt_id` (ReAct), which have been confused
  before. `occurrence_id` is a third. Mitigation: it is the only one derived from data the
  UI already holds, and its docstring states the one rule that matters - it names a pause
  within an interrupt, never an interrupt and never a checkpoint.
- **A composite claim key is less legible than a column.** Someone reading the table by
  hand sees a concatenated value rather than two fields. Accepted deliberately over
  hand-written DDL on a self-initializing table.
- **Optional-by-default hides mistakes.** A future pause that should declare an
  `occurrence_id` but does not would silently fall back to interrupt-only validation.
  Mitigation: a test asserts that any pause raised from within a tool call declares one.
- **This change alone is not user-visible.** It ships contract and plumbing whose payoff
  arrives with change 2. That is the point of sequencing it first, but it means its own
  verification rests on tests rather than on a demonstrable behaviour change.

## Deferred

- The resume payload's `skipped` form belongs to the `ask_user` tool's semantics and is
  specified in change 2, not here.
- Whether a pending-occurrence projection API is needed for reliable multi-tab
  convergence stays an open question under epic #1080; this change deliberately keeps
  history as the discovery surface it is today.
