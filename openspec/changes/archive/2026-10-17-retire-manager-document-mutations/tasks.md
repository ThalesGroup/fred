## 1. Remove the provisional surface

- [x] 1.1 Remove document mutations/client and obsolete startup/configuration dependencies; verify absent HTTP operations and API startup with Temporal unreachable.
- [x] 1.2 Regenerate OpenAPI/frontend client and remove the optional-ingestion workaround; verify schema/client contract and Resources tests.

## 2. Review and document

- [x] 2.1 Obtain independent review of retained consumers, security and worker behavior; fix actionable findings and re-review corrections.
- [x] 2.2 Reconcile arc42 with the reduced surface, run manager unit/integration/quality, lifecycle Temporal, root quality and architecture checks, validate and archive this change with verification evidence here.

## Review and verification evidence

Independent read-only review compared the working change against base/HEAD
`7387684683229a2c8477fefc7d47fbdf6ac67191` on `weaver`.
Coverage: removed HTTP/schema/client operations; retained authorization, Resources
and folders; API startup; lifecycle worker/configuration; deployment/reset consumers
and arc42. Three findings were corrected and re-reviewed: stale generated-hook
export (module-export regression), lifecycle-only k3d reset configuration (positive
preflight and external namespace rejection), and stale dependency/source references.
The reviewer independently ran 7 client and 20 mocked reset tests and found no
remaining actionable issue in this bounded scope. This is not full-Fred or full-PR
readiness review; admission implementation and unrelated Python code are excluded.

Verification on the final implementation: manager `make test` (40 unit, 6 OpenAPI),
`make test-integration` (85), `make code-quality`, and `make test-lifecycle-temporal`
(1 real API/worker restart, schedule reconciliation and replay test); 14 frontend
client/Resources tests; 20 mocked reset tests; architecture generation/render check;
strict delta validation and all 33 canonical specs validated. The real-binary
regression starts with unavailable Temporal, verifies reads and folder creation,
rejects the four removed operations with 404/405, and preserves existing metadata.
An obsolete ingestion-403 assertion and a one-element Clippy loop were also removed
before the passing final runs. The dedicated arc42 pass regenerated derived blocks
and documented the API/worker dependency boundary. No manual UI session or load
campaign was performed.

Root `make code-quality` also passes, including frontend TypeScript, Prettier and
ESLint. Canonical specs are synchronized with all four deltas; the completed
change is archived after strict validation.
