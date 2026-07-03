# RFC — Fred 2.0.2 Release (RGPD-ready flagship + document rename & labels)

**Status:** Proposed — **rev. 2 (2026-07-03, post-review target correction)**
**Author:** Dimitri Tombroff
**Date:** 2026-06-30 (rev. 2: 2026-07-03)
**ID:** CTRLP-12 (flagship); bundles `DOC-RENAME`, `DOC-TAGS`

> **Rev. 2 — why this correction.** A first implementation pass + independent review
> exposed three design faults that make the increment not-yet-mature. This revision
> re-specifies the **target** (not a delivery plan) so the data model stays clean and the
> feature is *complete*, not additive-by-accretion:
> 1. **Data model** — retention was given its **own** `team_policy_override` table for two
>    settings. Wrong shape: per-team settings must extend the **existing `team_metadata`**
>    store (a new setting is a *field*, never a table). No per-setting tables.
> 2. **Server-initiated erasure was under-specified.** The background worker that must erase
>    at window expiry has **no authenticated identity**; its auth model (service token +
>    admin bypass) must be **specified, implemented and tested as a prerequisite**, not
>    assumed. Deferred delete does **not** ship — nor default on — until this is real.
> 3. **Import/export was neglected.** Per-team settings must survive a platform migration;
>    conversation/runtime state must be explicitly excluded rather than half-exported. The
>    migration bundle is a first-class requirement here.
>
> Rev. 2 changes the **target design** (§3.B, §3.C, §3.D, §5–§7). The erasure *fan-out*
> and *receipt* (§3.A) stand; the immediate-delete path is the solid core.
**Area:** `control-plane-backend`, `fred-runtime`/`fred-core`, `knowledge-flow-backend`, `frontend`
**Supersedes drafts:** folds the earlier `CONVERSATION-DATA-ERASURE` and
`TEAM-DATA-GOVERNANCE` working notes into one release increment.
**Related (unchanged, reused):** `EXECUTION-GRANT-SECURITY-HARDENING-RFC` (2.0.1 / C3),
`FRED-TEAM-CONFIG-RFC` (team policy/actors), `AGENT-EVALUATION-RFC` (EVAL-01),
`TEAM-PLATFORM-POLICY-RFC` (retention).

> **2.0.1 made Fred C3-ready. 2.0.2 makes it RGPD-ready.**
> Every core capability already exists — per-store deletes, a per-team retention engine,
> the team settings panel, per-team evaluation, pseudonymised identity, author-isolated
> reads. This increment does not build subsystems; it makes them **play together** so that
> erasure is complete and provable, retention is team-governed, and evaluation is
> authorised. One RFC, one issue, shippable together.

---

## 0. Release scope — what ships in 2.0.2

One flagship plus two small, additive document UX features, tracked as a single release so
it tests as one increment:

| Workstream | ID | RFC (detail) | Status |
|---|---|---|---|
| **Flagship — RGPD-ready** (this RFC, §1–§9): complete erasure + team-governed retention + governed evaluation | `CTRLP-12` | this document | proposed |
| **Document rename** — rename a document's display name post-ingestion (pure metadata edit of `Identity.document_name`, no re-embed, zero blast radius); one new endpoint + FRONT-09 UI | `DOC-RENAME` | `DOCUMENT-RENAME-RFC.md` | proposed |
| **Document labels** — user-defined **business labels** on documents (e.g. "CV", "DVA", "confidential"). **NOT** the ReBAC permission *tags* — a separate descriptive field | `DOC-TAGS` | `DOCUMENT-TAGS-RFC.md` | v1 (metadata+API) implemented; 2.0.2 ships the add-label UI |

The two document features are **knowledge-flow / document-metadata** changes with **no
shared code** with the RGPD workstreams (§3.A/§3.B) — so they add no risk to the RGPD core
and can be tested separately within the same release. Their design lives in their own RFCs;
this section is the single place that says "they are in 2.0.2." Everything from §1 onward is
the flagship RGPD-ready work.

---

## 1. Definition of done — what "RGPD-ready" means

2.0.2 is RGPD-ready when all five hold (the release acceptance, mirroring how C3-ready had
a checklist):

1. **Erasure is complete and provable.** One operation erases a conversation across *all*
   stores (transcript, checkpoint blobs, attachment files, embeddings, KPI) and returns an
   auditable receipt — no shadow copies left behind.
2. **"Delete" means delete.** The conversation delete button actually erases. Two modes,
   and the deferred one is **gated on the worker auth of §3.C**:
   - **Immediate (default, always available):** delete runs the full `erase_session` now,
     using the caller's identity. This is the complete, tested core.
   - **Deferred (only once §3.C is real):** delete hides the conversation immediately
     (`session_metadata.deleted_at`) and a **server-initiated** `erase_session` runs at
     window expiry — **team** by the owner-set `team_delete_grace` (for evaluation),
     **personal** by a **platform-set `personal_delete_grace`** (security/post-incident,
     not user-overridable). Until the worker can *authenticate and complete* that erasure
     (§3.C), the deferred path and any default grace window **do not ship** — delete stays
     immediate. A hidden-but-never-erased state is not acceptable.
3. **Retention is bounded and team-governed.** A team owner sets per-team retention from
   the UI, bounded by a platform cap (platform caps, team may only tighten).
4. **Evaluation is authorised and scoped.** The evaluation endpoints enforce ReBAC; reading
   real conversations requires `CAN_READ_CONVERSATIONS`.
5. **Identity stays pseudonymised.** Stored `user_id` is the Keycloak `sub` (already true);
   no email lands in conversation stores. Keep it that way.

---

## 2. The gap today (why it isn't already done)

The pieces are wired to nothing:

- The automated purge deletes **one** store (`lifecycle_actions.py` → a single
  `session_store.delete`); checkpoint blobs, attachment files, embeddings, and KPI survive.
- The checkpoint store is keyed by `thread_id` only — **no owner, no age** — so it can't be
  erased per-user or swept by retention.
- The delete button removes **sidebar metadata only** (`product/api.py` `delete_team_session`).
- Retention is **static ops-owned YAML**; no team can see or set it.
- The evaluation API enforces **no authorization at all** (EVAL-01 §8.4 unimplemented).

---

## 3. The increment — two workstreams, one release

### A. Complete, provable erasure

A control-plane `ConversationErasureService` fans out over the per-store deletes that
**already exist** and returns an auditable `ErasureReceipt` (per store: count, ok, error);
the lifecycle purge and the delete button call it instead of their single-store deletes.

- Reused unchanged: `delete_session`, `adelete_thread`, `SessionMetadataStore.delete`,
  attachment `delete_for_session`, and Knowledge Flow's existing
  `DELETE /fast/delete/{document_uid}` cleanup surface for session-owned fast-ingest
  attachments.
- **Genuinely new (small):** a KPI delete/anonymise method (the only store lacking one),
  matched to the dim the runtime actually emits (`dims.session_id`), with the index-mapping
  migration so existing indices gain the field on startup.
- **Per-user / age erase (`checkpoint_thread_owner`):** a
  `checkpoint_thread_owner(thread_id, user_id, team_id, last_activity_at)` side table gives
  per-user erase + age sweep — but it is **introduced together with its reader** (the
  server-initiated per-user/idle erase of §3.C). It is **not** shipped write-only ahead of a
  consumer (rev. 2: write-only scaffolding is dead code and is cut until §3.C lands).
  Coordinate the shared checkpoint schema with **MEMORY-02 (Marc)** before it is
  reintroduced.
- **Delete semantics:** **immediate by default** (see §1.2). The **deferred** "hide now
  (`session_metadata.deleted_at`) + erase at window expiry" mode ships **only with §3.C**;
  team window = owner-set `team_delete_grace`, personal window = platform-set
  `personal_delete_grace` (not user-overridable). Triggers: `USER_DELETED`, `IDLE_EXPIRED`,
  plus the existing `MEMBER_REMOVED`.
- **Safety boundary (verified):** fast-ingest assigns a fresh `document_uid` per upload
  (`ingestion_controller.py:951`), so erasing a session's attachments can never reach a
  shared library document; the orchestrator only deletes `document_uid`s in that session's
  `session_attachments`.

### B. Team governance console

Add a **"Data & Retention" tab** to the existing `TeamSettingsPanel` (already hosts
Members / Parameters / Evaluations):

- **Retention, team-governed — on `team_metadata`, no new table (rev. 2):** the per-team
  retention values (`team_delete_grace`, `max_idle`, plus an audit field) are **columns on
  the existing `team_metadata`** store, read/written through the **existing
  `GET`/`PATCH /teams/{id}`** surface. There is **no `team_policy_override` table** and no
  dedicated `/retention` endpoints. Principle: **a per-team setting is a field on
  `team_metadata`, never its own table** — the same home will hold future settings (e.g.
  model routing) without proliferating tables. The page shows the **platform cap read-only**
  (from the policy catalog) and the **per-team value editable** by the owner
  (`CAN_UPDATE_INFO`), validated `≤ cap`. Resolution reuses `evaluate_purge_policy` for the
  cap, clamps the team value to it (**platform caps; team may only tighten**), and the
  **cap is a ceiling, not a default retention** — an unset team value means *immediate*
  delete, not "defer for the cap".
  - **`team_metadata` lives in `fred_core`** (shared lib): adding these two typed columns
    (`str | None`) + an audit field touches fred_core — **accepted (2026-07-03)**. The
    resolver's callers (`_resolve_delete_window`, `GET`/`PATCH /teams/{id}`) then read the
    values off the **already-fetched** `TeamMetadataStore` record instead of a separate
    override store — this **removes** a store dependency, it does not add one. Typed columns,
    not a generic settings blob (§8).
  - **Migration bonus:** with retention on `team_metadata`, the migration bundle needs only
    **one** table to carry it — and that same addition fixes a **pre-existing gap**: team
    branding in `team_metadata` is not exported today either (see §3.D).
  - **UI honesty:** while the deferred path is not yet enforced (before §3.C), the retention
    control is shown as **"preview — not yet enforced"**, never a knob that silently does
    nothing.
- **Evaluation, governed:** close the EVAL-01 §8.4 gap — `CAN_READ` to view, `CAN_UPDATE_AGENTS`
  to create/cancel, `CAN_READ_CONVERSATIONS` to evaluate real conversations. The evaluation
  backend and UI are already per-team; this makes them governed.

### C. Server-initiated erasure — the worker auth model (rev. 2, prerequisite)

Deferred delete (window expiry) and the idle sweep run in a **background worker** with **no
user request**, so no bearer token — yet they must call the runtime and Knowledge-Flow
delete surfaces, which today authorize by **per-user ownership**. This is the piece that was
under-specified; it is a **hard prerequisite** for any deferred/idle erasure.

- **Authentication — control-plane service token.** The control-plane mints a Keycloak
  **client-credentials** token for its **existing `control-plane` service account** (the SA
  config already exists, e.g. `configuration_prod.yaml`), with an audience the runtime and
  Knowledge-Flow accept. No new unauthenticated internal endpoints.
- **Authorization — `can_manage_platform` admin branch on 3 surfaces.** The runtime
  **checkpoint-delete**, runtime **history/session-delete**, and Knowledge-Flow
  **`/fast/delete/{document_uid}`** gain an admin branch that **skips only the ownership
  check** (authentication stays enforced) when the caller holds `can_manage_platform`. This
  lives in the authorization layer and is **owned by `AUTHZ-01`** (its RFC already specifies
  `can_manage_platform`): **reuse that bypass — do not fork a second one.**
- **Consumer contract.** The lifecycle consumer calls
  `ConversationErasureService.erase_session` with the **service bearer**, threading the
  **real** `user_id`/`team_id`/`session_id` from the queue entry, reusing the A2
  checkpoint-before-history order + orphan skip, and marks the queue entry **done only on
  `receipt.ok`** (retry on partial receipt). The queue's **`trigger` (reason) is not
  carried**: `erase_session` does not depend on it and the queue does not store it — erase
  is erase whatever the reason (no `trigger` column, no audit-of-reason for now).
- **Offline-testable form.** Unit-test the lifecycle activity with a fake erase service
  asserting: (i) `erase_session` is called with the queue row's own `user_id`/`team_id`/
  `session_id` (not a hard-coded value); (ii) the queue entry stays *not-done* until
  `receipt.ok`; (iii) an endpoint test where a service principal deletes by `session_id`
  succeeds while a non-admin non-owner still gets 403 and an unauthenticated call is still
  rejected.

### D. Migration (import/export) — first-class (rev. 2)

Per-team settings must **survive a platform migration**. Persisted conversation/runtime
delete/erase state is explicitly **out of platform migration scope**. The platform bundle
(`import_export/` exporter + importer + frontend migration) currently covers only agents,
tags, and document metadata — **not** team settings.

- **Include `team_metadata`** (with its new retention columns) in the exporter/importer +
  bundle, so a team's governed retention — and its existing branding, also not exported
  today — round-trips. One table covers branding + retention + every future team setting.
  Round-trip tested (export a platform, import into a fresh one, settings intact).
- **Explicitly exclude** session **soft-delete state** (`deleted_at`) and the runtime
  **checkpoint-owner** rows: conversations and runtime state are **not** platform-migrated,
  so they need no export. This is a documented exclusion, not a silent half-state.

---

## 4. Why it is one increment (the feature)

The **retention window is the evaluation window.** Workstream A makes erasure real and
bounded; B lets the team owner set that bound and run evaluation *inside* it. Set the team
window to 30 days → the team has 30 days to evaluate a conversation on real usage, then it
is provably erased. RGPD storage-limitation + erasure on one side, AI-Act monitoring on the
other, the trade-off owned by the team and capped by the platform: **evaluate the agent on
real conversations without compromising RGPD.** That single sentence is the 2.0.2 headline.

---

## 5. How small this actually is (rev. 2)

The **immediate erasure core** is genuinely small: the fan-out service + receipt over
existing per-store deletes, plus the one new KPI anonymise method. **Zero new tables.**

The **complete** feature adds, deliberately and no more:
- retention as **fields on `team_metadata`** (no new table; reuse `GET`/`PATCH /teams/{id}`),
- one nullable `session_metadata.deleted_at` column,
- the **worker auth** (§3.C): a service-token minter + a `can_manage_platform` admin branch
  on 3 existing delete endpoints — reuse the existing service account and the AUTHZ-01
  permission, **no new roles**,
- `checkpoint_thread_owner` **only when its reader ships** (§3.C), not before,
- migration-bundle coverage of `team_metadata` (§3.D),
- ReBAC on the evaluation endpoints.

**Complexity ledger vs the first pass:** removing `team_policy_override` and folding into
`team_metadata` turns **+2 tables into +3 columns**, drops **one migration**, deletes
**~3 backend files** (model + store + migration), and removes the two dedicated
`GET/PATCH /teams/{id}/retention` endpoints — while keeping every user-visible feature.
A future team setting is a **column**, never a table.

No new architecture. If a future family of heterogeneous per-team settings ever justifies a
generic settings blob, that is a separate decision (§8) — **not built speculatively here**.

---

## 6. Work breakdown (rev. 2 — ordered toward the complete target)

Grouped by phase; the deferred/idle erasure phases are **gated on the worker auth (§3.C)**.
The detailed, tracked sequence lives in `FRED-2.0.2-WORKPLAN.md`.

**Solid core (immediate erasure) — done / keep:**
- [x] `ConversationErasureService` + auditable `ErasureReceipt` fan-out (control-plane)
- [x] KPI anonymise method targeting `dims.session_id` + index-mapping startup migration
- [x] `session_metadata.deleted_at` column + sidebar filter (soft-hide)

**Phase R — data-model consolidation (rev. 2 correction):**
- [ ] Remove `team_policy_override` (table/model/store/migration) and the `/retention` endpoints
- [ ] Retention as columns on `team_metadata`; read/write via existing `GET`/`PATCH /teams/{id}`; resolver clamps team value ≤ platform cap; cap is a ceiling, unset ⇒ immediate delete
- [ ] Retention UI (already inside the Settings tab) points at the extended team API

**Phase C — server-initiated erasure auth (§3.C, prerequisite):**
- [ ] `can_manage_platform` admin branch on runtime checkpoint-delete, runtime history-delete, KF `/fast/delete` (authN kept, ownership skipped) — coordinate `AUTHZ-01`
- [ ] Control-plane service-token minter (client-credentials for the `control-plane` SA)

**Phase E — erase-at-expiry + sweeps (after Phase C):**
- [ ] Lifecycle consumer → `erase_session` with service bearer; thread `user_id`/`team_id`/`session_id` (not the `trigger` — erase doesn't need it); queue done only on `receipt.ok`
- [ ] `IDLE_EXPIRED` idle sweep (`updated_at < now − max_idle`; dry-run preview)
- [ ] `checkpoint_thread_owner` table + write-on-`aput` **+ its reader** (per-user / age erase)

**Phase M — migration (§3.D):**
- [ ] Add `team_metadata` (incl. retention) to exporter/importer + bundle; round-trip test
- [ ] Explicitly document/test the exclusion of session `deleted_at` / checkpoint-owner from migration

**Phase D — deferred UX + explicit grace windows (last, gated on Phase E proven):**
- [ ] Enable deferred delete semantics + explicit grace windows **only after** erase-at-expiry is proven end-to-end. A platform cap is a ceiling, not an implicit default window.

**Independent:**
- [ ] Evaluation endpoints: `CAN_READ` / `CAN_UPDATE_AGENTS` / `CAN_READ_CONVERSATIONS` authz (after `AUTHZ-01`)
- [ ] Reference chart values + configmap parity with code (no implicit grace window that activates deferral before Phase E)

Nothing deletes more than before until its receipt is verified; destructive server-initiated
paths default to `dry_run`; **deferred delete is never enabled or defaulted before its
erase-at-expiry can authenticate and complete (§3.C).**

---

## 7. Acceptance (the RGPD-ready proof)

- **Completeness:** create a session with a turn, a tool call, an uploaded attachment, and
  ≥2 checkpoint steps → `erase_session` → every store returns 0 on re-query (no forgotten leak).
- **Delete semantics (immediate):** delete runs `erase_session` now and every store returns
  0 on re-query — for both personal and team, with no default grace window.
- **Delete semantics (deferred, only once §3.C ships):** hide now + defer, then a
  **server-initiated** `erase_session` runs at window expiry and every store returns 0; the
  queue entry is marked done **only** on `receipt.ok`. Team uses `team_delete_grace`;
  personal uses the platform `personal_delete_grace` (not user-shortenable). A hidden
  conversation whose window expired but was not erased is a **test failure**.
- **Worker auth (§3.C):** the service token succeeds against all 3 delete surfaces; an
  ordinary non-owner is still refused; an unauthenticated call is still rejected.
- **Bounded retention:** owner sets value ≤ cap (ok) / > cap (422); member can view, not
  edit; an unset team value yields *immediate* delete (cap is a ceiling, not a default).
- **Migration:** export a platform, import into a fresh one → `team_metadata` round-trips
  intact, including each team's retention settings. The bundle documents the explicit
  exclusion of conversation/runtime state (`session_metadata.deleted_at`,
  `checkpoint_thread_owner`).
- **Eval authz:** non-member create/list → 403; manager create ok; real-conversation campaign
  without `CAN_READ_CONVERSATIONS` → 403.
- **Pseudonymity:** stored `user_id` is the Keycloak `sub`; no email in conversation stores.

---

## 8. Out of scope (post-2.0.2)

PII detection/redaction of free-text content; per-user access isolation on KPI **reads**;
team-admin UI for *other* platform-policy guardrails; ROPA (Art. 30) / DPIA (Art. 35)
documents; the EVAL-02 task-event cutover (Odélia) — independent of this authz change.

**Also explicitly out of scope (rev. 2 — YAGNI):** a *generic per-team settings framework*
(typed settings blob / key-value store). Retention adds plain columns to `team_metadata`;
a generic settings model is only justified when a real family of heterogeneous per-team
settings exists — it is not built ahead of that need.

---

## 9. Execution

**One GitHub issue** ("Fred 2.0.2") tracks the whole release: the §6 RGPD checklist plus the
two bundled document features (`DOC-RENAME`, `DOC-TAGS`) per their RFCs (§0). Backlog:
`BACKLOG.md §6.4.H`. Coordinate the checkpoint side table with `MEMORY-02` (Marc), the
evaluation authz with EVAL-01 (Odélia), and add the eval/policy authz checks through the
new ReBAC pattern from the in-flight `AUTHZ-01` migration (not `require_admin`/`@authorize`).
