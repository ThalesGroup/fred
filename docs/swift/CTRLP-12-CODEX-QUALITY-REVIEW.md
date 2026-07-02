# CTRLP-12 Codex Quality Review

Review target: `swift..HEAD` on branch `1883-fred-202-rgpd-ready-increment-ctrlp-12` at `1864748bffdb9fb623951221ee0f62edb3e5820a`.

## Executive Summary

Not production-ready for an RGPD-ready release. The team-settings read/write surface is mostly coherent, but the erasure and retention execution path still has release-blocking gaps.

Top risks:

1. Deferred deletes are enqueued but the lifecycle runner still drains the legacy queue as `MEMBER_REMOVED` work and calls the old metadata-only delete path, so conversations hidden by the delete button are not fully erased at expiry.
2. KPI anonymisation does not match the KPI shapes emitted by runtime/tool paths, so a successful erasure receipt can still leave `user_id`, `session_id`, or `exchange_id` in OpenSearch KPI rows.
3. The shipped policy catalog does not define `team_delete_grace` or `max_idle` platform caps, so the advertised "platform caps, team may only tighten" guarantee is not true in the default deployment.

## Findings

| Severity | File:line | Issue | Why it matters | Suggested fix |
| --- | --- | --- | --- | --- |
| blocker | `apps/control-plane-backend/control_plane_backend/scheduler/lifecycle_actions.py:41` | Deferred delete queue items lose their trigger and are processed as `MEMBER_REMOVED`; the runner then calls `session_store.delete()` instead of `erase_session`. | `delete_or_defer_session()` enqueues due work, but expiry does not erase attachments, KPI, checkpoint, or runtime history; the product contract already warns the legacy `session_purge_queue` must not be the runtime retention mechanism. | Add trigger/operation to the queue, route `USER_DELETED`/idle work to `ConversationErasureService`, and mark done only when the receipt is ok. |
| blocker | `libs/fred-core/fred_core/kpi/opensearch_kpi_store.py:255` | KPI anonymisation only matches `dims.scope_type=session` + `dims.scope_id=session_id`. | Runtime turn KPIs and tool/KF KPIs emit `user_id`, `session_id`, and `exchange_id` through other dims, so RGPD erasure can report success while identifiable KPI rows remain. | Match all current KPI session shapes, or ensure runtime emits a session-scoped OpenSearch-only key and anonymise by that key. |
| blocker | `apps/control-plane-backend/config/conversation_policy_catalog.yaml:12` | Default catalog has no `team_delete_grace` or `max_idle` cap. | With `platform_max=None`, the resolver accepts any team value as-is, so retention is not bounded by a read-only platform cap in production defaults. | Define platform caps/defaults in the catalog or reject team overrides when no platform cap exists. |
| major | `apps/control-plane-backend/control_plane_backend/sessions/erasure_service.py:106` | Attachment/KF cleanup is not isolated. | A single Knowledge Flow cleanup failure raises before metadata, KPI, checkpoint, or history erasure are attempted, contradicting the per-store receipt contract and leaving partial writes without a receipt. | Wrap attachment cleanup as its own receipt-producing store step and continue to independent stores on failure. |
| major | `libs/fred-runtime/fred_runtime/runtime_support/sql_checkpointer.py:617` | Checkpoint owner identity is not populated at write time and backfill/purge helpers are not wired. | New owner rows default to `user_id=None`; per-user checkpoint purge only works after a manual backfill that has no endpoint/startup hook in this diff. | Inject `__fred_user_id`/`__fred_team_id` at invocation time and/or wire a controlled backfill/admin purge path. |
| major | `apps/control-plane-backend/control_plane_backend/scheduler/policies/policy_models.py:71` | `IDLE_EXPIRED` and max-idle sweep are missing. | The UI exposes `max_idle`, but no lifecycle trigger or sweep exists to erase sessions past that limit. | Add the trigger, scheduler query, dry-run preview, and tests that expired sessions are erased through the receipt path. |
| major | `apps/frontend/src/rework/components/pages/TeamSettingsPage/TeamSettingsPage.tsx:38` | Read-only retention view is blocked by broader settings permission. | Backend GET allows `CAN_READ`, and `TeamSettingsRetention` has read-only mode, but the page redirects users without `can_administer_owners`; members/managers cannot view the platform cap. | Gate each settings section by its own permission; allow retention GET for readers and only disable PATCH controls for non-owners. |
| major | `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md:457` | Product contract still says not to use `session_purge_queue`, while the new delete path enqueues into it. | Contract and implementation disagree on the retention mechanism; reviewers/operators cannot rely on the documented purge model. | Update the contract only after the queue is made trigger-aware and wired to runtime erase, or keep the implementation out of release scope. |
| major | `docs/swift/FRED-2.0.2-WORKPLAN.md:39` | Workplan checkboxes claim B1-B6 and A1-A5 reviewed/done, while `id-legend`/PMO/backlog still say CTRLP-12 is proposed/TBD. | Governance state is not converged, and green ticks in the workplan overstate production readiness. | Align PMO, id legend, backlog, and workplan to the actual partial state before release signoff. |
| minor | `apps/control-plane-backend/control_plane_backend/product/api.py:1023` | DELETE session docstring says missing sessions return 204, but the service raises 404. | API clients and tests can encode the wrong idempotency expectation. | Either make delete idempotent or update the endpoint docs/tests to expect 404. |
| minor | `apps/control-plane-backend/control_plane_backend/sessions/store.py:153` | `get()` and update helpers do not filter `deleted_at`. | A soft-deleted conversation is hidden from list views but remains directly fetchable/updateable by ID during the retention window; this may be intended for evaluation but is not documented. | Decide the access contract for soft-deleted sessions and test direct GET/PATCH behavior explicitly. |

## Test Coverage

Well covered:

- Pure retention resolver boundaries, including inherit/team/clamp/no-cap cases.
- GET/PATCH retention happy path, 422 above cap, partial update semantics, and non-owner PATCH denial.
- `personal_delete_grace` non-overridability at the model/service level.
- Runtime erasure ordering: checkpoint before history, unresolved runtime receipt entries, KPI store absent/failing, and skip-history-on-checkpoint-failure.
- Checkpointer owner-row upsert, best-effort failure logging, backfill helper, and per-user purge helper in isolated SQLite tests.

Specific gaps:

- No test runs the real default `conversation_policy_catalog.yaml`; tests inject caps that the shipped catalog does not have.
- No lifecycle test drains a real due `USER_DELETED` queue item through `erase_session`.
- No test covers Knowledge Flow attachment cleanup failure isolation.
- No KPI test uses actual runtime/tool/KF emitted dim shapes with `dims.session_id` and injected `user_id`.
- No frontend test covers retention read-only access for `CAN_READ` users.
- No test covers soft-deleted direct `GET/PATCH /sessions/{id}` behavior.
- No migration edge test verifies the queue can distinguish `MEMBER_REMOVED` from `USER_DELETED` or future `IDLE_EXPIRED`.

I attempted focused pytest commands, but this checkout has no `.venv/bin/uv` and no `uv` on `PATH`, so the tests could not be executed locally.

## Missing Apache Headers

New `.py`/`.ts`/`.tsx` source files missing the Apache header:

- `apps/control-plane-backend/alembic/versions/c1d2e3f4a5b6_add_team_policy_override.py`
- `apps/control-plane-backend/alembic/versions/d2e3f4a5b6c7_add_session_metadata_deleted_at.py`
- `apps/control-plane-backend/control_plane_backend/models/team_policy_override_models.py`
- `apps/control-plane-backend/control_plane_backend/scheduler/policies/retention_resolver.py`
- `apps/control-plane-backend/control_plane_backend/sessions/erasure_service.py`
- `apps/control-plane-backend/control_plane_backend/teams/policy_override_store.py`
- `apps/control-plane-backend/tests/test_retention_resolver.py`

The new TypeScript/TSX files and new fred-core/fred-runtime tests have headers.

## Duplicate Code And Reuse

No large copy-paste block stood out as a blocker. Good reuse signals: retention endpoints delegate to the pure resolver; the frontend uses generated RTK hooks; checkpoint delete reuses `adelete_thread`.

Small duplication to watch: runtime HTTP delete helpers in `erasure_service.py` repeat client/exception handling. That is not the core risk today, but once lifecycle/user erasure is added, a shared runtime-delete helper would reduce drift.

## Verified

- Reviewed only `git diff swift..HEAD`.
- Ran `git diff --check swift..HEAD`: no whitespace errors.
- Ran `scripts/quality/quick_review_signals.sh swift`: produced mechanical signals; no TODO/FIXME in touched files; generated client touched; existing local dirty file noted.
- Checked Apache headers on every new `.py`, `.ts`, and `.tsx` file.
- Checked docs convergence across `CLAUDE.md` workflow, `id-legend.yaml`, `BACKLOG.md`, `PMO-BOARD.md`, the CTRLP-12 RFC, and the workplan.
- Inspected backend erasure, retention, queue/lifecycle, migrations, KPI anonymise, runtime checkpointer, frontend settings, and generated-client enhancement paths.

## Could Not Verify

- Local pytest/tsc/prettier results, because the expected `.venv/bin/uv` executable is absent.
- Live OpenSearch `update_by_query` behavior.
- Browser rendering of the Team Settings page.
- GKE/service-to-service behavior, service-token auth, and live runtime/KF delete calls.
- The actual `/audit-branch` and `/test-gaps` skill bodies; this checkout references `.claude/skills/...`, but those files are not present.
