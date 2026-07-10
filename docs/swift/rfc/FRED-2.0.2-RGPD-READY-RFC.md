# RFC — Fred 2.0.2: RGPD-ready

**Status:** Target spec — **rev. 3 (2026-07-04)**. This revision states the
**ultimate target only** — the complete, final behaviour. It deliberately drops
the earlier phase/gate/option framing: there are no intermediary milestones here,
only the finished feature and how to prove it. Build order lives in
[`../FRED-2.0.2-WORKPLAN.md`](../FRED-2.0.2-WORKPLAN.md); this document is *what
done means*, not *how we got there*. **§6 (2026-07-07) amends this RFC with the
`CTRLP-13` follow-up** — observable erasure for member removal + idle expiry.
**Author:** Dimitri Tombroff · **ID:** `CTRLP-12` (bundles `DOC-RENAME`, `DOC-TAGS`)
**Area:** control-plane · fred-runtime/fred-core · knowledge-flow · frontend

> **2.0.1 made Fred C3-ready. 2.0.2 makes it RGPD-ready.**

---

## 0. What ships in 2.0.2

One flagship plus two small document features, released together, tested as one
increment:

| Workstream | ID | Detail |
|---|---|---|
| **RGPD-ready** — complete erasure + team-governed retention + governed evaluation (this RFC) | `CTRLP-12` | §1–§5 below |
| **Document rename** — rename a document's display name post-ingestion (metadata edit, no re-embed) | `DOC-RENAME` | `DOCUMENT-RENAME-RFC.md` |
| **Document labels** — user-defined business labels on documents (not ReBAC tags) | `DOC-TAGS` | `DOCUMENT-TAGS-RFC.md` |

The document features share no code with the RGPD workstream and carry no RGPD
risk; they are listed here only to record that they are in the 2.0.2 release.
Everything below is the RGPD flagship.

---

## 1. The feature (one paragraph)

Deleting a conversation **provably erases it** across every store. A team may set
a **retention window** during which a deleted conversation survives — hidden from
users but available to the team for agent evaluation — after which it is
**automatically and provably erased** by an authenticated background worker. **The
retention window is the evaluation window:** the team evaluates its agents on real
conversations for a bounded period, then RGPD erasure is guaranteed. The trade-off
is owned by the team and capped by the platform.

---

## 2. Definition of done (the acceptance — this is the target)

2.0.2 is RGPD-ready when **all seven** hold:

1. **Erasure is complete, provable, and retry-safe.** One operation erases a
   conversation across *every* store — transcript (`session_history`), LangGraph
   checkpoint, attachment files + embeddings (Knowledge Flow), and KPI — and
   returns an auditable **receipt** (per store: count, ok, error). It is
   **idempotent and retry-safe**: re-running after any partial failure converges
   to full erasure — **no store is left orphaned and no queue entry is stuck**.
   *(Requirement, not an optimisation: the store that anchors ownership and
   runtime resolution — the `session_metadata` row — is deleted **only after**
   every other store has been erased, so a retry can always re-resolve and finish.
   The checkpoint is erased before the transcript, because the runtime proves
   checkpoint ownership via the transcript.)*

2. **"Delete" means delete — immediate by default, deferred when a window is set.**
   - **Immediate (default):** the delete button runs the full erasure now, using
     the caller's identity.
   - **Deferred (when the conversation's space has a window):** the button hides
     the conversation immediately (`session_metadata.deleted_at`) and a background
     worker runs the full erasure at window expiry. **There is never a
     hidden-but-un-erased state**: a window that has expired without its erasure
     completing is a defect. Team window = the `team_admin`-set `team_delete_grace`;
     personal window = a platform-set `personal_delete_grace` (security /
     post-incident, not user-shortenable).

3. **Retention is team-governed and bounded.** A `team_admin` sets per-team
   retention from the UI. The values are **fields on the existing `team_metadata`
   store** (`team_delete_grace`, `max_idle`, plus an audit field) — never a
   separate table — read and written through the existing **`GET`/`PATCH
   /teams/{id}`**. Each value is **clamped to a platform cap** (platform caps;
   team may only tighten; `> cap` → 422). **The cap is a ceiling, not a default
   window:** a team that has set no value deletes **immediately** — it does not
   inherit the cap as a deferral window.

4. **Server-initiated erasure is authenticated.** The expiry worker has no user
   token, so the control-plane mints a **client-credentials service token** for
   its existing `control-plane` Keycloak service account. The runtime
   checkpoint-delete, runtime history-delete, and Knowledge-Flow
   `/fast/delete/{uid}` endpoints recognise the org-level **`can_manage_platform`**
   permission and **waive the per-user ownership check** for that principal —
   **authentication is never waived**. This reuses the platform-admin permission;
   it forks no second bypass.

5. **Retention survives a platform migration.** The export/import bundle carries
   `team_metadata` (branding + retention + every future team setting) so a team's
   governed retention round-trips into a fresh platform. Conversation/runtime
   delete state (`session_metadata.deleted_at`, checkpoint-owner rows) is
   **explicitly excluded** — conversations are not platform-migrated.

6. **Evaluation is authorised and scoped.** The evaluation endpoints enforce
   ReBAC: `CAN_READ` to view, `CAN_UPDATE_AGENTS` to create/cancel,
   `CAN_READ_CONVERSATIONS` to evaluate real conversations.

7. **Identity stays pseudonymised.** Stored `user_id` is the Keycloak `sub`; no
   email lands in any conversation store.

---

## 3. How it works (end-to-end)

**Erasure fan-out.** A control-plane `ConversationErasureService.erase_session`
fans out over the per-store deletes that already exist and returns an
`ErasureReceipt`. Store order is fixed by dependency: attachments/KF and KPI first
(independent); then the runtime **checkpoint before transcript**; then the
**`session_metadata` row last** (§2.1). Each store is isolated — one failure is
recorded and the others still run — and `receipt.ok` is true only when every
touched store erased cleanly.

**Two delete modes, one path.** The delete button and the lifecycle worker both
call `erase_session`. The button resolves the window for the conversation's space:
personal → platform `personal_delete_grace`; team → the team's own
`team_delete_grace` clamped to the cap, or **None if unset** (immediate). If a
window resolves, the conversation is hidden (`deleted_at`) and a `USER_DELETED`
purge-queue entry is enqueued due at `now + window`; otherwise it is erased now.

**The worker.** At expiry the lifecycle worker mints the service token, calls
`erase_session` with it, threading the queue row's real `user_id`/`team_id`/
`session_id`, and marks the queue entry done **only on `receipt.ok`** — a partial
receipt leaves it queued for a later, convergent retry (§2.1). The runtime and KF
delete endpoints authorise the service principal via `can_manage_platform` (§2.4).

**Data model.** Retention is three nullable columns on `team_metadata`
(`team_delete_grace`, `max_idle`, `retention_updated_by`); one nullable
`session_metadata.deleted_at`; the purge queue already carries
`session_id`/`team_id`/`user_id`. **Zero new tables.**

---

## 4. Acceptance tests (what proves it)

- **Completeness:** a session with a turn, a tool call, an uploaded attachment,
  and ≥2 checkpoint steps → `erase_session` → every store returns 0 on re-query.
- **Retry-safety:** force a runtime outage mid-erase → the receipt is not ok and
  the queue entry stays; restore the runtime and re-run → erasure completes and
  the entry is marked done. No orphaned checkpoint, no stuck entry.
- **Immediate delete:** with no window set (personal, or a team that set nothing),
  delete erases now and every store returns 0 — even when a platform cap exists.
- **Deferred delete:** a team that set `team_delete_grace` → delete hides now;
  at expiry the worker erases and every store returns 0; the queue entry is
  marked done only on `receipt.ok`.
- **Worker auth:** the service token succeeds against all three delete surfaces;
  an ordinary non-owner is still refused; an unauthenticated call is still
  rejected.
- **Bounded retention:** owner sets value ≤ cap (ok) / > cap (422); a member can
  view but not edit; an unset value yields immediate delete.
- **Migration:** export a platform, import into a fresh one → `team_metadata`
  round-trips (branding + retention); conversation/runtime state is not bundled.
- **Eval authz:** non-member create/list → 403; manager create ok;
  real-conversation campaign without `CAN_READ_CONVERSATIONS` → 403.
- **Pseudonymity:** stored `user_id` is the Keycloak `sub`; no email in any
  conversation store.

---

## 5. Out of scope (post-2.0.2)

PII detection/redaction of free-text content; per-user access isolation on KPI
*reads*; a team-admin UI for *other* platform-policy guardrails; ROPA (Art. 30) /
DPIA (Art. 35) documents; the EVAL-02 task-event cutover; a generic per-team
settings framework (retention adds plain columns to `team_metadata` — a generic
settings store is only justified when a real family of heterogeneous per-team
settings exists).

---

## 6. Amendment — CTRLP-13: observable erasure everywhere (post-2.0.2)

**Status:** proposed (2026-07-07). **ID:** `CTRLP-13` (parent `CTRLP-12`).
**Backlog:** `../backlog/BACKLOG.md §6.4.I`.

> **Scope split with OPS-04 (2026-07-07).** The *observability + display* half of this
> amendment — the shared admin Activity surface, the per-row erasure reason, moving the
> erasure view out of team Settings, and the `erasure` task kind — is owned by
> [`TASK-EVENT-STREAM-RFC.md`](TASK-EVENT-STREAM-RFC.md) (OPS-04 rev. 2 §3.4–§3.6), so the
> task/audit story lives in one place. **This section keeps only the RGPD lifecycle
> *enforcement* mechanics** below (member-removal enqueue parity, the `IDLE_EXPIRED` sweep,
> and the `last_activity_at` writer); each emits a task per the OPS-04 total-coverage
> invariant, and OPS-04 defines how those tasks surface.

### 6.1 Problem

2.0.2 shipped the erasure *schedule* (§2.1, §3) but only the **conversation-delete**
path emits the observable `erasure` task the schedule renders. Two lifecycle triggers
the product already advertises stay invisible, so an admin performing them sees nothing
and reasonably concludes the feature is broken:

- **Member removal** — `remove_team_member` revokes access immediately and enqueues each
  of the removed user's conversations into the purge queue (`LifecycleTrigger.MEMBER_REMOVED`,
  due `now + retention`), but it **never calls `schedule_erasure_task`**. The erasures happen
  at expiry, unaudited and unshown. This is the DoD-1 "auditable" promise applied unevenly.
- **Idle expiry** — `max_idle` ("Durée d'inactivité maximale", cap `P365D`) is validated,
  clamped, stored, displayed and migrated, but **no sweeper enforces it**: there is no
  `IDLE_EXPIRED` trigger, no enqueue pass, and `last_activity_at` has no production writer.
  The team-settings control does nothing.

Neither is a regression against the 2.0.2 DoD (both were explicit deferrals, §2 notes and
BACKLOG Phase E/O), but together they violate the *spirit* of DoD-2 ("delete means delete,
never a hidden-but-un-erased state") from the operator's point of view: work is scheduled
that the operator cannot see.

### 6.2 Target (extends the §2 DoD)

**Every lifecycle trigger that enqueues a purge emits a matching observable erasure task.**
Concretely, extending DoD-1/2:

1. Member removal emits one `erasure` task per affected conversation, `reason=member_removed`,
   future-dated to the same `due_at` as its purge row; the lifecycle worker advances it
   `pending → running → succeeded` exactly as the user-deleted path does.
2. A conversation idle past its team's `max_idle` is swept, enqueued (`reason=idle_expired`),
   and erased through the same observable task. `last_activity_at` is written on real
   conversation activity so the sweep has truthful input.
3. The erasure schedule shows the **reason** per row, and its empty state is reassuring and
   explanatory (states *what will appear here and why it is currently empty*), not a bare
   "none". The global admin Tâches page no longer stacks two unrelated empty states (the
   server erasure schedule and the SSE task tray) without distinction.
4. Invariant: **no `queue_store.enqueue` call site exists without a paired
   `schedule_erasure_task`.** This is the structural guarantee that keeps the schedule honest.

No schema change is required: `ErasureReason` already enumerates
`user_deleted | member_removed | idle_expired` and `TaskSummary` already carries
`scheduled_for`. This amendment is about *emission* and *display*.

### 6.3 Out of scope (unchanged)

Team-wide deletion and bulk conversation deletion remain out of scope (no such flow exists).
Evaluation-side deferrals (real-conversation execution + cancel, evaluation authz) remain
tracked under EVAL-01/EVAL-03, not here.
