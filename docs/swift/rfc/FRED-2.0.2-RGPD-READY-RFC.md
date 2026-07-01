# RFC — Fred 2.0.2 Release (RGPD-ready flagship + document rename & labels)

**Status:** Proposed
**Author:** Dimitri Tombroff
**Date:** 2026-06-30
**ID:** CTRLP-12 (flagship); bundles `DOC-RENAME`, `DOC-TAGS`
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
2. **"Delete" means delete.** The conversation delete button actually erases — after a
   governed grace window: **team** space by the owner-set `team_delete_grace` (for
   evaluation), **personal** space by a **platform-set `personal_delete_grace`** (for
   security/post-incident access, e.g. `P3D`, not user-overridable). Both then run the full
   `erase_session`; both are hidden from the user immediately.
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
  attachment `delete_for_session`, and knowledge-flow's ready-but-unused
  `delete_document_and_artifacts(document_uid)` (one call removes a document's vectors +
  content + tabular + metadata).
- **Genuinely new (small): two things only** — a `checkpoint_thread_owner(thread_id,
  user_id, team_id, last_activity_at)` side table (gives per-user erase + age sweep), and a
  KPI delete/anonymise method (the only store lacking one).
- **Delete semantics:** both spaces **hide now** (`session_metadata.deleted_at`) + **defer**
  the full `erase_session`; only the window source differs. **Team** (`is_personal_team_id`
  false) → the owner-set `team_delete_grace` (history survives for evaluation). **Personal**
  → a **platform-set `personal_delete_grace`** (a bounded security/post-incident retention;
  **not user-overridable**, so a user cannot evade it). If either window is unset/null the
  delete is immediate (back-compat default). Triggers: `USER_DELETED`, `IDLE_EXPIRED`, plus
  the existing `MEMBER_REMOVED`.
- **Safety boundary (verified):** fast-ingest assigns a fresh `document_uid` per upload
  (`ingestion_controller.py:951`), so erasing a session's attachments can never reach a
  shared library document; the orchestrator only deletes `document_uid`s in that session's
  `session_attachments`.

### B. Team governance console

Add a **"Data & Retention" tab** to the existing `TeamSettingsPanel` (already hosts
Members / Parameters / Evaluations):

- **Retention, team-governed:** a `team_policy_override` table (the first concrete
  `TeamPlatformPolicy` slice) + `GET`/`PATCH /teams/{id}/retention`. The page shows the
  **platform cap read-only** and the **per-team value editable** by the owner
  (`CAN_UPDATE_INFO`), validated `≤ cap`. Resolution reuses `evaluate_purge_policy`:
  `team_override ?? yaml_rule ?? yaml_default`, clamped to the cap. **Platform caps; team
  may only tighten** — RGPD-safe by construction, and exactly "platform settings read-only
  + updatable field."
- **Evaluation, governed:** close the EVAL-01 §8.4 gap — `CAN_READ` to view, `CAN_UPDATE_AGENTS`
  to create/cancel, `CAN_READ_CONVERSATIONS` to evaluate real conversations. The evaluation
  backend and UI are already per-team; this makes them governed.

---

## 4. Why it is one increment (the feature)

The **retention window is the evaluation window.** Workstream A makes erasure real and
bounded; B lets the team owner set that bound and run evaluation *inside* it. Set the team
window to 30 days → the team has 30 days to evaluate a conversation on real usage, then it
is provably erased. RGPD storage-limitation + erasure on one side, AI-Act monitoring on the
other, the trade-off owned by the team and capped by the platform: **evaluate the agent on
real conversations without compromising RGPD.** That single sentence is the 2.0.2 headline.

---

## 5. How small this actually is

New code: the checkpoint owner table, the KPI anonymise method, the `team_policy_override`
table + two endpoints, one settings tab, and ReBAC on the evaluation endpoints. Everything
else is orchestration over primitives that already ship. No new architecture, no new roles
(reuses `CAN_UPDATE_INFO` / `CAN_UPDATE_AGENTS` / `CAN_READ_CONVERSATIONS`), no schema churn
beyond two small tables and one nullable `deleted_at` column.

---

## 6. Work breakdown (one consolidated list)

- [ ] `ConversationErasureService` + per-store `StoreEraser` registry → auditable `ErasureReceipt` (control-plane)
- [ ] `checkpoint_thread_owner` table + best-effort write on `aput` + backfill; per-user checkpoint purge (runtime)
- [ ] KPI delete/anonymise method (KPI store)
- [ ] Thin knowledge-flow endpoint exposing the existing `delete_document_and_artifacts`
- [ ] `session_metadata.deleted_at` column + sidebar filter
- [ ] Delete button → hide + deferred `erase_session` (`USER_DELETED`): team window = `team_delete_grace`, personal window = platform `personal_delete_grace` (not user-overridable)
- [ ] Lifecycle purge action → `erase_team_member`; add `IDLE_EXPIRED` sweep
- [ ] `team_policy_override` table + `GET`/`PATCH /teams/{id}/retention` (`CAN_READ` / `CAN_UPDATE_INFO`), clamp ≤ cap
- [ ] Evaluation endpoints: add `CAN_READ` / `CAN_UPDATE_AGENTS` / `CAN_READ_CONVERSATIONS` authz
- [ ] `TeamSettingsRetention.tsx` tab + governance copy; regenerate control-plane client
- [ ] Retention config: `team_delete_grace` + `max_idle` (per-team cap) + platform `personal_delete_grace` in the policy catalog

Each item is independently shippable; nothing deletes more than before until its receipt is
verified, and destructive paths default to `dry_run`.

---

## 7. Acceptance (the RGPD-ready proof)

- **Completeness:** create a session with a turn, a tool call, an uploaded attachment, and
  ≥2 checkpoint steps → `erase_session` → every store returns 0 on re-query (no forgotten leak).
- **Delete semantics:** both hide now + defer, then erase after the window. Team uses
  `team_delete_grace`; personal uses the platform `personal_delete_grace` and the user
  cannot shorten it. A security reviewer can read a deleted personal conversation during its
  window; after it, `erase_session` runs and every store returns 0.
- **Bounded retention:** owner sets value ≤ cap (ok) / > cap (422); member can view, not edit.
- **Eval authz:** non-member create/list → 403; manager create ok; real-conversation campaign
  without `CAN_READ_CONVERSATIONS` → 403.
- **Pseudonymity:** stored `user_id` is the Keycloak `sub`; no email in conversation stores.

---

## 8. Out of scope (post-2.0.2)

PII detection/redaction of free-text content; per-user access isolation on KPI **reads**;
team-admin UI for *other* platform-policy guardrails; ROPA (Art. 30) / DPIA (Art. 35)
documents; the EVAL-02 task-event cutover (Odélia) — independent of this authz change.

---

## 9. Execution

**One GitHub issue** ("Fred 2.0.2") tracks the whole release: the §6 RGPD checklist plus the
two bundled document features (`DOC-RENAME`, `DOC-TAGS`) per their RFCs (§0). Backlog:
`BACKLOG.md §6.4.H`. Coordinate the checkpoint side table with `MEMORY-02` (Marc), the
evaluation authz with EVAL-01 (Odélia), and add the eval/policy authz checks through the
new ReBAC pattern from the in-flight `AUTHZ-01` migration (not `require_admin`/`@authorize`).
