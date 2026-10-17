## Context

See [proposal.md](proposal.md) for the outcome and accepted scope. This is a proposal; the arc42 dossier continues to describe shipped behavior only.

### Verified source contract

| Surface | Current behavior | Consequence for this lot |
| --- | --- | --- |
| Python `teams/service.py::delete_team` | Checks `CAN_DELETE_TEAM` at higher consistency; synchronously removes team relations, agent instances and registry row | Preserve technical deletion authority, but explicitly introduce deferred container deletion |
| Python `remove_team_member` | Removes all direct roles immediately, protects the last admin, queues each conversation with a due time | Full removal is excluded by the developer; do not confuse it with removing one role |
| Python `revoke_team_member_role` | Removes one role, can retain membership, does not queue cleanup | Keep Rust's already documented role contract unchanged |
| Python `scheduler/temporal/` | A ten-minute Temporal Schedule lists due SQL candidates; activities execute effects; incomplete cleanup stays recoverable | Reuse a durable SQL queue plus scheduled, bounded Temporal work |
| Python `sessions/erasure_service.py` and product contract section 35 | Dependent stores first, metadata last; success only after all required stores confirm completion | Apply to the current OpenFGA/SQL pair, without invented remote-store success |
| Python policy models/engine | Strict frozen models, `default/rules/match/action`, ISO durations, most-specific rule then file-order tie break | Port the relevant policy vocabulary and validate it at startup |
| Rust `spaces.rs`, `fga.rs`, migration 0006 | Hierarchy and roles are canonical only in OpenFGA; platform-then-organization locks and fenced writes serialize mutations | Deletion must retain a bounded operational manifest without making SQL a second authorization tree |
| Rust `db.rs`, `api.rs`, `ingestion.rs` | Folder/document rows and document dispatch routes already exist, despite the UI journey stopping at folders | Reject any document-bearing deletion scope and fence all existing producers |

Do not copy unsupported source settings: `cancel_on_rejoin` is represented in Python policy results but has no production cancellation consumer in the inspected tree; `max_idle` is documented as unenforced. Neither belongs to space deletion. The product contract's member-removal task claim also exceeds the inspected service, which queues sessions without calling `schedule_erasure_task`. The new operation must have its own truthful status endpoint.

## Goals / Non-Goals

**Goals:** exercise real deferred deletion, retry and replay in a small Rust module; keep policy decisions pure, workflows deterministic, and effects in activities; preserve organization isolation and current roles under concurrency.

**Non-Goals:** UI changes, complete member removal, account deletion, document/conversation cleanup, evaluation access during retention, cancellation/restoration, a generic plugin registry for imaginary stores, or replacing Python workers. Retention here preserves recoverability and audit evidence; it does not introduce a new content-reading permission.

## Decisions

### 1. Explicit API and authority

- `DELETE /spaces/{id}` returns 202 and a deletion receipt with operation ID, target kind/ID, request time, scheduled deletion time and status. No client-supplied deadline, subtree list or force flag.
- `GET /deletions/{operation_id}` returns the durable status, bounded per-store progress, completion time and sanitized error code. It remains usable after the target disappears.
- Add OpenFGA `platform.can_delete_space: owner`, plus its typed permission probe. Both endpoints check this capability at higher consistency and require normal authenticated admission. An organization/team/project admin or organization owner alone receives no new deletion power. Existing `can_delete_team` remains supported.
- A request covers a project, an ordinary team and its projects, or an organization and all its ordinary/personal spaces and projects. A standalone personal-space deletion is refused in this lot.
- Retry of the same target returns the original receipt and deadline (202 pending, 200 completed). Overlapping ancestor/descendant requests return 409; neither silently absorbs the other. Unknown targets return 404 after authorization. Existing nonempty document scope returns 409 without retiring anything.
- No restore API: the delay is not an undo window. Recreating a name after successful cleanup creates a new UUID; a delayed activity for the old ID cannot affect it.

This is deliberately platform governance, following the existing Python team-delete permission. Granting local admins deletion would be an additional role decision, not a consequence of the word "admin".

### 2. Durable acceptance, separate from Temporal availability

Add one operational `space_deletion` table and a nullable `space.deletion_id` reference. The request stores actor subject, target ID/kind, target parent ID (null for an organization), organization ID, fixed request/due times, resolved mode/rule, status, progress and safe error code. A unique target constraint supplies idempotency. It must survive physical target deletion; no cascading foreign key from the receipt to `space`.

Existing `space` rows are the work manifest: mark every affected row in one SQL transaction. Reuse their kind/ID for project-before-team-before-organization ordering; do not add a separate item table, duplicate grants or restore `parent/path` columns on spaces. The request's organization and root parent are operational snapshots needed after hierarchy links are removed, not authorization grants or a second complete tree. Sibling-name/import checks consult pending receipts plus their remaining root rows, even if FGA no longer links that root. Ancestor overlap checks consult unfinished receipts by organization/root-parent independently of FGA traversal: a team's deletion must still find a pending project whose parent tuple has already disappeared.

Acceptance takes the existing platform lock and its FGA guard, checks permission before revealing target existence, resolves target placement, then takes the organization lock/guard and rechecks active target. It traverses committed descendants including personal `organization` links, checks overlap/documents, fences both authorization scopes and commits the request plus retirement markers. No Temporal RPC occurs in that transaction. Success means durably scheduled, not already erased. A crash after commit and before response is recoverable by repeating DELETE.

All business reads, lists, scope/permission probes, role changes, creation, folder/document operations, provisioning and personal-space reuse must reject or omit retired targets and descendants. Mutations recheck retirement after acquiring their lock, not before waiting. Requests authorized before retirement may finish; requests admitted afterwards cannot access the retired scope. Ordinary reads must not try to resolve partially removed FGA links for retired rows.

Organization-attachment enforcement still considers remaining direct grants on retired rows, resolving their organization from the deletion receipt when links are already gone. Workspace display omits those rows. This prevents retirement from making a still-attached person eligible for a second organization. Once their last old grant is removed, the existing no-attachment rule applies. Names/personal-space slots remain reserved while their rows are pending; import must report a pending-deletion conflict rather than restore or bypass them.

A queue is necessary: directly starting Temporal after SQL has an unrecoverable dispatch gap, and starting it first cannot atomically retire SQL. The same operational table is the durable work source and status receipt, avoiding a second outbox/task subsystem.

### 3. Configuration with supported semantics only

Keep `ENV_FILE`, `CONFIG_FILE` and `policies.purge_catalog_path`. Introduce a versioned `lifecycle_policy_catalog.yaml` with:

```yaml
version: v1
space_policies:
  purge:
    default:
      mode: deferred_delete
      retention: P7D
    rules: []
```

Rules retain `rule_id`, `match`, `action`; matches accept `space_id` and `space_kind` as a string or nonempty list; an empty match object is a catch-all, like Python. More defined criteria win; the first rule wins ties. Action overrides support `mode` and `retention` only. A validated duration newtype supports the Python subset (weeks/days/hours/minutes/seconds, including zero), normalizes case/outer whitespace, and rejects missing units, negative/calendar/fractional durations and arithmetic/timestamp overflow. New lifecycle/policy structs use Serde with unknown-field rejection and validation before serving or polling; unrelated configuration parsing stays unchanged.

`deferred_delete` freezes `due_at = requested_at + retention`; `immediate_delete` freezes `due_at = requested_at`, still executed by the worker. Restarting with changed policy affects new requests only. No per-team retention editing API, `max_idle`, `cancel_on_rejoin`, or conversation catalog compatibility claim.

Preserve current `scheduler.temporal` as the ingestion connection/queue. Add `scheduler.lifecycle` with `enabled` (default false), `temporal` (same host/namespace/task_queue/workflow_id_prefix/connect_timeout_seconds/rpc_timeout_seconds vocabulary), `sweep_interval` (default PT10M, strictly positive) and `batch_size` (default 100, range 1..5000). Its task queue and workflow IDs are manager-specific; refuse collision with the ingestion queue. Reference configs ship disabled; operators activate after the deployment barrier below, and disposable tests enable it explicitly. When disabled, new deletion requests return 503 before mutation; status reads and retries returning an existing receipt remain available. Never silently resume cleanup when the operator has disabled it.

### 4. Separate Rust worker and bounded sweep

Add `fred-manager worker` and `make run-worker`, using the same binary/image/config conventions as `serve`. The worker loads the published FGA store/model and initialized SQL schema; it must not bootstrap users or migrate authorization independently. Add the matching worker deployment to the manager overlay, a distinct command, configuration mounts, health/readiness and graceful shutdown. No service/ingress or directory client secret is needed for the worker.

Use `temporalio-sdk`, macros and workflow crates pinned to the existing 1.0.0 family. The official [Rust quickstart](https://github.com/temporalio/documentation/blob/main/docs/develop/rust/quickstart.mdx) documents the matching crates; [worker APIs](https://docs.rs/temporalio-sdk/1.0.0/temporalio_sdk/) provide workflow/activity registration. Do not introduce an SDK fork or a homegrown workflow engine.

`lifecycle/` contains concrete policy, request/store, cleanup activity and workflow/worker modules. Share SQL/FGA clients through explicit activity dependencies. Workflows receive operation IDs, not tokens or grants; all database access, clocks for due eligibility and network effects live in activities. Use typed inputs/results, explicit error classes and exhaustive state transitions. Add only the receipt stages implemented now.

A stable manager-owned Temporal Schedule starts a bounded sweep, with overlap skipped. Worker startup idempotently reconciles its schedule configuration; namespace, queue and prefix cannot collide with control-plane or ingestion. Disabling lifecycle pauses the owned schedule when reachable and prevents new cleanup activity execution. List due operations fairly by next attempt/last visit and ID so a large or failing scope cannot starve others. Process at most one bounded cleanup batch per candidate per tick, with three activity attempts and explicit timeouts. One exhausted candidate is recorded as retrying and does not abort the others. Subsequent sweeps rediscover unfinished work; no bearer is required after acceptance.

This follows control-plane's scheduled sweep instead of one long-lived workflow per object. Deletion runs no earlier than `due_at`; sweep interval, backlog and outages add latency. Neither API nor worker claims an exact completion deadline. Long SQL locks or sleeping inside a transaction are prohibited.

### 5. Cleanup ordering and recovery

For each due operation, choose a remaining leaf space by kind/ID. Acquire platform then organization locks and both guards for each bounded batch. Re-read the persisted operation and due time; payloads cannot nominate unrelated resources. Refuse any unexpected document row or out-of-manifest incoming hierarchy reference; report an incomplete operation, never bypass a foreign key or call an unimplemented cleanup service.

Clean one space in stages: delete its folder leaves in bounded SQL batches (up to 1000), remove OpenFGA references in guarded batches (at most 96 payload tuple operations plus four guard operations), verify both outgoing and incoming references absent, then remove its SQL row. Parent spaces are processed only after descendants. Keep the organization guard until organization cleanup is otherwise complete; its final removal must be fenced against the platform guard, without recreating it on retries. If that final FGA write committed but SQL did not, a platform-guarded finalization path verifies the persisted operation, absent references and absent organization guard before removing the root row and completing the receipt. Platform guards/roles, accounts, consent and other organizations are preserved.

Use exact-object FGA reads and model-derived type-scoped subject reads, not a whole-store scan. Current model has only `space` as an object type admitting `space` subjects, giving two filters per ID: `{object: space:<id>}` and `{object: space:, user: space:<id>}`. Derive subject-capable types/relations from the pinned model and verify no unexpected references before deleting links outside the operation. Page size is explicit (96), tokens are consumed for read-only discovery. During mutation, drain fresh first pages instead of retaining a token across deletions; never allow a shifted cursor to skip tuples.

An FGA timeout can mean the delete committed: discard the old guard, re-read a fresh page/guard on retry, and delete only currently present tuples. A failed/ambiguous SQL commit is handled by rereading operation progress. SQL counters and deletion of each SQL batch commit together. A final verification and guarded fence precede SQL row removal. No distributed rollback restores grants.

Receipt states are `queued`, `running`, `retrying`, `blocked`, `completed`. Transient failures remain eligible at the next attempt; an unsupported-content/inconsistent-manifest failure is blocked and visible for operator correction, with no false success. A later sweep may resume once the blocking condition is actually resolved. Completion requires all manifest rows and FGA references gone. Retain a minimal receipt (IDs, times, actor, policy decision, SQL counts and FGA verification outcome), never names, bearer tokens, document content or copies of role tuples. Do not claim exact FGA delete counts after an ambiguous acknowledgment.

### 6. Proposed request budgets and evidence

Let S be the committed spaces in scope, T their directly referencing tuples, F their folders, U the requesting person's other memberships, and P(k)=max(1,ceil(k/96)) for a paginated read. These are client RPC budgets, not claims about OpenFGA's internal evaluation work.

| Phase | Requests and dependency order | Lock/cost boundary |
| --- | --- | --- |
| Acceptance | Platform guard Read, one `Check can_delete_space`, then 0/1/2 placement link Reads for organization/team/project, organization guard Read, descendant Reads filtered by `space:` + exact parent subject/relation, plus personal `organization` relation for an org, then one guarded fence Write | Platform then org lock through validation, discovery and SQL commit; no Temporal call or retention wait. Scales with S and hierarchy pages, not U or unrelated store tuples |
| Candidate polling | Indexed SQL query for eligible operation IDs; no FGA call | Bounded by configured batch size, no organization lock |
| One cleanup batch | Three guard Reads (platform version, organization existence, organization version); at most one page from each reference filter while draining; zero or one guarded Write of <=100 operations; final organization removal adds a platform version Read and organization guard Read before its Write | Lock spans only that SQL/FGA batch, not a complete organization or retry sleep. Cost scales with T for the deleted scope and F for folder batches |
| Status read | One higher-consistency platform capability Check and indexed SQL lookup | No subtree traversal or mutation lock |

For first acceptance, the total is `4 + L + D` RPCs: two guard Reads, one Check, one fence Write, placement reads L, and discovery pages D. D is zero for a project, P(project links) for a team, and P(team links) + P(personal links) + the sum of P(project links) for an organization. Read-only retries/status need only a permission Check and SQL lookup. Authorization admission/setup overhead is reported separately. Final organization-guard removal has a separate platform-guarded verification budget in tests.

Acceptance traverses the selected subtree under the existing lock; measure this explicitly rather than claiming constant-time acceptance or a latency SLO. Stream pages into transaction-local SQL retirement updates rather than accumulating all grants or spaces in memory; rollback the entire request on any overlap/document/error. Do not silently cap or partially accept a subtree. Large-subtree lock duration is a stated trade-off of atomic acceptance in this preparatory lot.

Regression fixtures cover all three levels, personal descendants, multiple FGA pages (>96 tuples), >1000 folders, 1 and 8 concurrent actors, and a much larger unrelated organization. Assert filters/RPC counts, maximum tuple batch, SQL lock scope, replay and absence of cross-organization effects. Report measured fixture sizes and timings in arc42's quality chapter; no scalability claim from the demo.

## Risks / Trade-offs

- SQL and OpenFGA are not transactional together -> retirement is committed first; incremental effects remain discoverable; metadata is removed last; inject failures at every cross-store boundary.
- Retirement affects more than DELETE -> inventory every existing read/write/probe/import entry point and test pending requests, account placement and personal-space reuse. Do not hide rows by globally changing SQL lookup semantics.
- Small API changes add substantial failure-path behavior -> independent review of authority, replay, schedule configuration, deployment and documentation is required before the implementation commit.
- A retained receipt is audit data, not proof of remote artifact cleanup -> document the two implemented stores and refuse document scopes. Downstream audit-log retention remains deployment-owned.

## Migration Plan

Add a new SQL migration; leave all applied migrations intact. Existing spaces have no deletion marker. Regenerate the OpenFGA model and generated frontend API, preserving exact additive upgrades from the currently supported prior models. Ship API and worker together with explicit lifecycle configuration and the policy catalog, update deployment schema where applicable, and validate rendered manifests. The manager's dedicated chart overlay remains the deployment entry point; do not introduce a second independently maintained chart.

Deployment has an explicit activation barrier: deploy with lifecycle disabled, finish replacing every API replica and provisioning/operator producer with retirement-aware binaries, verify the worker/schema/model, then enable API acceptance and worker cleanup. A rolling update with an old replica still serving is not sufficient. Configuration is startup-loaded: activation/disable requires updating all affected processes, not just one replica or the YAML file. Document and validate this two-phase rollout.

Then test an empty disposable project with a short delay and inspect its receipt. An older binary must never serve pending-deletion state. Even after draining, direct binary rollback is unsupported: the older binary rejects the new authorization publication (and may reject the newer SQL migration set). Prefer a forward fix; a rollback requires a coordinated pre-activation SQL/OpenFGA backup restore with all producers/workers stopped, not just switching an image or editing a published model pointer. Record this restriction in the migration note. No production deletion, account removal or live-data migration is part of verification.

### Activity cancellation and deployment integration

Every activity observes its cancellation token and a 50-second local deadline,
inside the 60-second Temporal start-to-close bound. Worker SQL connections set
5-second lock and 45-second statement timeouts; cleanup repeats those locally
before its first lock. Shutdown allows two seconds before activity cancellation.
This also bounds SQL work after a Rust future is dropped. Exhaustion status is
persisted by its own activity, so failure/death bypassing a cleanup return path
does not lose visible retry state. The k3d reset inventories both optional manager
workloads and stops/restores them together, validating both lifecycle connections.
