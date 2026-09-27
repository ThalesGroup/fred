# RFC OPS-04 — Task visibility and worker-action coverage

**Status:** core task infrastructure implemented; remaining scope is coverage,
operational retention and consistent presentation. This RFC does not approve new
persistence or scheduler abstractions.

## Current references

- [Product contract — task persistence](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md#persistence): service-owned tables, shared-library boundary and API context.
- [Observability and audit](../platform/OBSERVABILITY-AND-AUDIT.md): separate operational metrics, product analytics and security audit responsibilities.
- [Ingestion architecture](../design/INGESTION.md): workflows, activities, queues and their relationship to document tasks.
- [Task models](../../../libs/fred-core/fred_core/tasks/models.py), [service](../../../libs/fred-core/fred_core/tasks/service.py), [store](../../../libs/fred-core/fred_core/tasks/store.py), [authorization](../../../libs/fred-core/fred_core/tasks/authz.py) and [SSE](../../../libs/fred-core/fred_core/tasks/sse.py): actual contracts; do not maintain copied Python/TypeScript models here.

## Settled choices

Each backend owns its tasks and event journal. Control Plane and Knowledge Flow
use distinct prefixed tables in the shared database; this does not require a
dedicated database per service. There is no central Control Plane task writer or
`RemoteTaskClient`. Frontend aggregation reads the owning backends.

The mutable task summary and durable event journal have different purposes.
The journal supports SSE replay; the live bus alone is not durable history.
Task kinds and typed details come from shared models and generated OpenAPI.
A document task is not the same object as its executor's workflow.

Persisted acknowledgement is implemented (`acknowledged_at`, `acknowledged_by`,
service/store support and task acknowledgement endpoints). Earlier descriptions
of acknowledgement as only a local Redux flag are obsolete. Eligibility and
permission rules belong to the current models, authorization helpers and routes.

Executor bindings and reconciliation exist. An unreachable executor must not be
interpreted as failure. A completed executor with a still-nonterminal task needs
an explicit terminal correction, not a permanent spinner. Do not assume every
service runs reconciliation as a Temporal schedule; inspect its lifecycle wiring.

## Remaining questions to scope before implementation

1. **Coverage:** inventory actual worker/admin actions and verify each required
   durable receipt exists. Do not reuse the old “missing” table as a current bug
   list: ingestion, evaluation, erasure and account deletion have evolved.
2. **Presentation:** confirm the shared activity surface, inline indicators and
   acknowledgement remain coherent across scopes, reloads and backend outages.
   Reuse existing components rather than adding one activity UI per feature.
3. **Retention/export:** establish an explicit operational retention and archival
   policy. An append-only application journal does not by itself prove regulatory
   immutability or retention guarantees for the storage deployment.
4. **Receipt survival:** verify data erasure preserves the appropriate content-free
   audit evidence, and that all ownership/scope checks also apply to historical reads.

These are review questions, not claims that corresponding features are absent.
Any uncovered gap needs a bounded change with observable acceptance criteria.

## Guardrails to preserve

- Record enough to identify the action, target, actor/scope, timestamps and outcome.
  Erasure receipts carry reason and per-store counts, not erased content.
- Keep prompts, answers, document text and tool payloads out of worker-action audit
  records. Sanitize errors; pseudonymous identifiers still require access control.
- Task visibility and mutation authorization are distinct; enforce both server-side.
- Register the target and executor binding before dispatch where the execution path
  requires them, so a fast worker cannot race registration.
- Preserve ordered replay/deduplication and reload rehydration; lost live events
  must not be the only record of completion.
- Keep cancellation separate from failure. Expose only supported actions and verify
  the actual computation stops, not merely the UI indicator.
- Do not silently prune audit evidence or use Temporal history retention as the
  application audit policy. Task journals do not replace the security audit stream.

The former revision log, copied model definitions and superseded central-writer /
dedicated-database designs have been removed. Current behavior is documented at
its owning contract or implementation; this RFC retains only cross-cutting scope
and the decisions still requiring verification.
