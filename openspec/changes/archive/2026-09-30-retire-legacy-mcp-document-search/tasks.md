## 1. Retire the duplicate search and local MCP transport

- [x] 1.1 Remove the legacy search catalog entry, prompt, runtime implementation and SDK constant; replace the three shipped template defaults with `document_access`.
- [x] 1.2 Remove the `inprocess` MCP transport contract, lifecycle and factory injection; preserve native capability invokers and remote MCP behavior. Remove the unimplemented GitHub entry as explicitly approved.
- [x] 1.3 Update catalog, native-search and remote-lifecycle regression coverage and regenerate the runtime API client.

## 2. Migrate stored selections

- [x] 2.1 Add a linear control-plane Alembic revision removing only legacy search selections and configuration, preserving inheritance and unrelated data.
- [x] 2.2 Test idempotence, malformed rows, concurrent edits and preservation; verify a real upgrade on a disposable database and a single migration head.

## 3. Verify and close locally

- [x] 3.1 Update current documentation and the feature migration note for the final behavior and operator actions.
- [x] 3.2 Run relevant suites, root code-quality, package/chart checks and independent correctness/performance review; resolve findings.
- [x] 3.3 Record evidence, reconcile and archive the OpenSpec change. Leave all work uncommitted; do not migrate a live database.

## Verification evidence

- SDK full suite: 543 passed, 3 skipped; runtime full suite: 1,659 passed,
  12 skipped (optional receiver/PostgreSQL dependencies), 1 existing serialization warning.
- Agent templates/pod suite: 92 passed, 6 existing xfails; native document-access
  suite: 41 passed; migration regression tests: 7 passed.
- Disposable SQLite control-plane database: upgrade to `b88202b8451e`, seed mixed
  tuning, upgrade to `ba2c3c7fd0c1`, repeat upgrade and check preserved columns/data.
  `alembic heads` reports exactly `ba2c3c7fd0c1`.
- Built wheel loads directly from ZIP resources: five internal servers plus Jira,
  only the tabular prompt. Rendered Helm catalog loads with four HTTP servers;
  neither retired entry remains. Chart values/schema and migration-note checks pass.
- Regenerated runtime OpenAPI/client with `make -C apps/frontend update-runtime-api`
  and pod/chart schemas with `make -C apps/fred-agents generate-config-schema`.
  Schemas have no resulting tracked diff; runtime client drops provider and uses
  the closed transport union.
- OpenSpec strict validation passes. No commits, staging, publication or live DB
  migration performed; authorized scope was confirmed in the conversation.
- Control-plane offline suite: 1,377 passed, 8 integration tests deselected,
  23 warnings; no live database used.
- Independent spec review: no findings; retirement, native invocation and
  migration preservation confirmed against the agreed scope.
- Independent standards and performance reviews: no findings introduced by this
  delta. Remote MCP retries, cache, cancellation-safe close and native search
  instrumentation remain intact; no additional load campaign was indicated.
- Full spec validation: 5 passed, 0 failed.
- Root `make code-quality` passes across all modules (exit 0), including frontend
  type-check/format/lint. Unused import, test formatting and SQLAlchemy type import
  findings were corrected; direct migration typing and its 7 tests also pass.
- Main MCP capability spec synchronized and validated; this change is archived
  locally after verification and review. HEAD remains `5a8ee56d7`, index empty.
