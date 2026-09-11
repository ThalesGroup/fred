One working branch, one potential PR. The groups are ordered as a single
vertical slice: each is worth starting only because the previous one works.

The HTTP/WebDAV/Markdown synchronizer is **not** in this plan. It is the
immediate external consumer that will validate the published contract once
group 6 passes.

A first consumer proof already exists outside this repository — a complete
local-folder Knowledge Base written against the published surface. Group 2b
records what building it found.

Recurring schedules are **not** in this plan. An instance carries configuration
and runs, not a cadence; the scheduling surface is its own change, scoped once
this slice has shown what Knowledge Flow's REST API actually needs.

## 1. SDK author contract and the declaration's JSON-safe projection

- [x] 1.1 Add the Knowledge Base declaration to `libs/fred-sdk` — identifier, version, display metadata and one list of instance configuration fields as `FieldSpec`; verify with tests that a well-formed declaration validates, a malformed identifier is rejected, and a duplicate field key is rejected naming the key
- [x] 1.2 Add the synchronization-handler decorator accepting exactly one handler per declaration; verify with tests that a declaration with no handler fails with a clear error and that a second handler is rejected
- [x] 1.3 Add the run context and the bounded sync result — five generic counters, bounded summary, bounded warnings and errors, optional JSON-safe metrics map; verify with tests that bounds truncate and that a metrics map round-trips unmodified
- [x] 1.4 Add the JSON-safe projection of a declaration — built as an installable artifact, and repurposed by task 2c.5 into the payload an image publishes; verify with a round-trip test and a test that the projection carries no configured value and no secret
- [x] 1.5 Add a test asserting the author-facing package's public exports and handler signature contain no workflow, activity, task-queue, retry, heartbeat or schedule type or term — public surface only, not module imports

## 2. Control Plane catalog and team enablement

- [x] 2.1 Add configured-definition parsing to the control-plane deployment configuration — superseded by task 2c.3, which deletes it: the definition now reaches Fred by publication alone
- [x] 2.2 Add startup validation refusing an invalid configured definition — superseded by task 2c.3 with the configuration it validated
- [x] 2.3 Add the dedicated `knowledge_base_definition` ReBAC type (`app`'s relational shape: organization anchor, `default_on`, `enabled`, `disabled`, `can_use`), map its permissions in the exhaustive permission-to-resource mapping, regenerate the compiled `schema.fga.json` with `make transform-openfga-schema` (never by hand), and enable/disable per team by reusing the existing enablement implementation — factor the shared authorization half rather than writing a second service. **Includes the Platform Admin UI**: a dedicated `/admin/knowledge-bases` page with its own AdminNavbar entry, a team selector over the existing team list, the definitions available for the selected team, per-team enable/disable, and loading/empty/error states — generated routes and hooks are not a UI. Add a dedicated RTK tag so enable/disable invalidate the list immediately. Verify with backend permission and relation tests (`can_use` false before enablement, true after, false after disabling; `can_manage` requires platform admin; enablement stores no configuration; the compiled schema declares the type) and frontend tests (loading/empty/error, definitions listed apart from capabilities and applications, enable and disable for the chosen team, and no online/healthy/connected indication anywhere)

## 2b. Contract corrections from the first consumer proof

Found by writing a real implementation against the published surface. Recorded
as their own work rather than edited into groups 1 and 2, which shipped as
described.

- [x] 2b.1 Retype `SynchronizeHandler` as `Coroutine[Any, Any, KnowledgeBaseSyncResult]`, keeping the `inspect.iscoroutinefunction` guard; verify with a test that the resolved handler is accepted by `asyncio.run` with no typing wrapper
- [x] 2b.2 Add the required `reconciliation_complete` boolean to the sync result, independent of the terminal outcome, and document that `removed` reports retractions actually executed while an absence proves a deletion only after a complete authoritative inventory; verify with tests for a succeeded-but-incomplete pass and for a retraction reported during a partial pass
- [x] 2b.3 Add the SDK-computed, serialized `content_truncated` indicator over the existing bounds, not settable by the caller; verify with tests for a clipped summary, a clipped issue message, issues dropped past `MAX_ISSUES`, and an attempt to force it false
- [x] 2b.4 Add the optional bounded generic `subject` to `KnowledgeBaseIssue` — not a `path`, with severity still carried by `warnings` versus `errors`; verify with tests for absent, plain and over-long subjects
- [x] 2b.5 Add `KnowledgeBaseManifest.to_installable()` returning a JSON-safe dict with `exclude_none` and `exclude_defaults`, carrying no `client_id` and no `task_queue`; verify with a test that the projection is compact and free of operator bindings — no YAML is emitted from fred-sdk
- [x] 2b.6 Fix `content_truncated`, which reports truncation when nothing was clipped: both `model_post_init` in `fred_sdk/knowledge_base/models.py` re-measure the **already-truncated** value with `>=`, so a message of exactly `MAX_ISSUE_MESSAGE_CHARS`, a summary of exactly `MAX_SUMMARY_CHARS` or exactly `MAX_ISSUES` issues all read as truncated — the opposite of what the comment beside the code claims. That claim is unachievable by re-measuring afterwards: detect truncation where the clipping happens instead, and drop the comment with it. Verify with tests for a value one character under its bound, exactly at its bound and one over, and for exactly `MAX_ISSUES` issues versus one more
- [x] 2b.7 Stop `KnowledgeBaseRunContext` promising a guarantee nothing yet performs: its docstring states that configuration "arrives already validated against the definition's declared fields", while task 3.2 owns that validation, is unchecked, and the Control Plane has no instance concept — so the surface currently tells authors to delete defensive code against a platform that does not validate. Attribute the guarantee to the platform-provided runtime that dispatches a run, with task 3.2 as its precondition, rather than stating it as a property the type carries on its own. No dated note: a comment that rots on a date is exactly what the repository's Step 4 rule exists to prevent. Verify with a test that the documented guarantee names what performs it


## 2c. One write at deployment

Deployment configuration for Knowledge Bases disappears entirely: the image
declares the definition by publishing it (decision 2). Group 2 built the
configured catalog; this group deletes it and replaces it with a stored
declaration the pod writes. Nothing here is a new mechanism — publication reuses
the same exact-client verification that authorizes the run context, and the pod
side reuses the `M2MTokenProvider` client-credentials pattern of task 4.3.

- [x] 2c.1 Add the stored published declaration to control-plane — one row per definition id holding display metadata, version, `configuration_fields` and the client identity bound at first publication, with its Alembic migration re-parented onto the current `swift` head. The write is an idempotent upsert replacing that definition's row unconditionally: no history of previous declarations is kept and nothing compares a publication against what it replaces. Verify with tests that publishing the same declaration twice leaves one unchanged row, and that a changed version replaces both content and stamped version
- [x] 2c.2 Add the authenticated publication endpoint. The first publication for a definition id binds it to the signature-derived client identity; a later publication for that id is refused unless it presents the same client, and a broad service role alone never authorizes. Factor that verification once and reuse it for the run-context endpoint of task 4.4 rather than writing it twice. Verify with tests that a first publication creates the definition and records its client, that the same client may republish, that a different client is refused, and that holding a broad service role does not help
- [x] 2c.3 Delete `KnowledgeBaseDefinitionConfig`, its `knowledge_base_definitions` configuration block and their startup validation: there is no Knowledge Base entry in deployment configuration at all. Resolve display metadata, version and configuration fields from the stored declaration, and restrict reading a definition's declared fields to a member of a team it is enabled for. Verify with tests that a published definition is listed, that its declared fields are served only to a member of an enabled team, and that the admin surface carries none of them
- [x] 2c.4 Derive the task queue from the two-segment identity — provider and definition — in one place in fred-sdk as a pure function over fred-core's `knowledge_base_catalog_id`, so the queue is the catalog id itself and the two sides cannot disagree by construction; documented as part of the contract rather than left a private detail, and outside the author-facing exports so task 1.5's public-surface assertion still holds; use that single derivation on both sides — the pod's worker bootstrap (task 4.1) and Control Plane's dispatch (task 4.2). Verify with tests that both sides derive an identical queue, that two providers exposing a definition of the same name derive different queues, and that an incomplete identity is refused
- [x] 2c.5 Add the SDK's two entry points so one image either publishes or serves: a `publish` command posting the declaration and terminating on its exit status, and the run entry point of task 4.6. `publish` is the only way to publish — the worker does not publish at startup, because during a rolling upgrade a restarting old-image replica would write the retired declaration back over the new one. Both entry points authenticate with the `M2MTokenProvider` client-credentials pattern of task 4.3, and the SDK documents the pod's environment contract — what it reads to reach Control Plane, to authenticate and to reach the workflow engine — since Fred neither reads nor knows it. Document the deployment shape this produces: a `post-install,post-upgrade` hook Job runs `publish`, the long-running Deployment runs the worker, modelled on the existing `deploy/charts/fred/templates/hook-migration.yaml`; the Job belongs to the chart deploying the pod, which for a third-party Knowledge Base is outside this repository. Nothing is installed any more, so the "manifest" and "installable" vocabulary leaves the Knowledge Base surface: rename `KnowledgeBaseManifest` and `to_installable()` onto the contract's own word — the declaration an image publishes — and carry the rename through the sample consumers. Compatibility with what already imports the old names is not a consideration. Verify with tests that `publish` starts no worker and reports through its exit status, that starting the worker publishes nothing, and that neither entry point opens an inbound listener
- [x] 2c.6 Remove the Fields column from the Platform Admin Knowledge Base page and its `columns.fields` key from both translation files, and drop `configuration_fields` from `KnowledgeBaseDefinitionSummary`, regenerating the control-plane client with the documented make target. That surface collects no configuration value, so shipping it the declared fields is dead payload. Verify with a frontend test that the page offers identity and the enable/disable toggle only

## 3. Team instances and their configuration form

- [ ] 3.1 Add the instance table and store, keyed so one team holds several instances of one definition, with its Alembic migration; verify with tests that two instances coexist independently, that an instance is bound to its creating team, that creating one is refused while the definition is not enabled for that team, permitted once enabled, and refused again for new instances after it is disabled
- [ ] 3.2 Add ONE canonical strict validation of `FieldSpec` values, used both when an instance is created or updated and again before the handler is invoked, with pass-through storage; no permissive cross-type coercion (a `"500"` string is not an integer 500), and the handler never re-parses its own configuration; verify with tests for an invalid value rejected naming the field, a missing required field rejected, a string-shaped number refused rather than coerced, secret-declared values absent from display reads, and the same validator refusing a stored configuration that no longer satisfies its definition at invocation time
- [ ] 3.3 Add team isolation on instance read, update, delete and run listing; verify with tests that a non-member is refused and run listing returns only the caller's team's runs
- [ ] 3.4 Regenerate the frontend API client for the new control-plane controllers with the documented make target and commit the regenerated file alongside the backend change
- [ ] 3.5 Add the team-facing instance configuration form, rendered from the definition's stored declaration. Reuse the existing renderer rather than adding a third variant: the generated client already carries the declared fields as `FieldSpec[]`, and `TuningFieldRenderer.tsx` already renders them — but typed on the looser generated twin `ManagedAgentFieldSpec` (`type: string`, `default: any`), which `CapabilityTeamMatrixDrawer.tsx` already works around with a `field as ManagedAgentFieldSpec` cast. This form would be the second such cast, so promote the renderer to a shared component typed on the strict `FieldSpec` — closed type union, typed default — and migrate its existing callers onto it, deleting the cast. A convergence, not an addition. Verify with tests that each declared field type renders, that a secret-declared field is never prefilled from a display read, and that the migrated capability drawer and agent form render unchanged

## 4. SDK worker, generic workflow and Control Plane calls

- [x] 4.1 Add the SDK worker bootstrap, taking its task-queue identity from the shared derivation of task 2c.4, started by the run entry point; verify with a test that the queue identity is derived rather than author-declared
- [x] 4.2 Add the generic workflow and activity adapter with all I/O in the activity and heartbeat, cancellation and retry plumbing inside the adapter, dispatching on the derived queue of task 2c.4; verify with tests that the workflow performs no I/O and that a run identifier is derived at workflow start
- [x] 4.3 Add the pod's confidential M2M client using the existing `M2MTokenProvider` client-credentials pattern; verify with a test that no user token is used or propagated on any outbound Fred call
- [ ] 4.4 Add the authenticated run-context endpoint returning one run's configuration, reusing the client verification factored in task 2c.2 and scoping access to the active run, its instance and its team; verify with tests that another definition's client is refused and that a broad service role alone does not authorize
- [ ] 4.5 Add the run record, terminal states and the bounded result-reporting endpoint, contributing to the existing task state and event vocabulary rather than a parallel status surface; verify with tests for succeeded, failed and cancelled, and that oversized content is truncated
- [x] 4.6 Add `run_knowledge_base(kb)` to `fred_sdk.knowledge_base` as the run entry point task 4.1's bootstrap starts from, so an author's `main()` is the declaration, the handler and one call. It takes the declaration and nothing else — queue, client and worker are derived or read from the pod's environment. It lives in fred-sdk rather than fred-runtime because fred-runtime is the HTTP runtime and must not acquire a Temporal dependency. Verify with tests that it needs no argument beyond the declaration, that it starts the worker on the derived queue of task 2c.4, and that exporting it leaves task 1.5's public-surface assertion passing

## 5. Ingestion through Knowledge Flow's REST API

- [ ] 5.1 Ingest and delete documents from a run through the Knowledge Flow REST API as it exists today, authenticating with the pod's own M2M identity; verify with tests that no OpenSearch or object-storage credential is reachable through the SDK contract and that the source credential is used only against the external source
- [ ] 5.2 Record what that API turned out to lack — scoping, identity, bulk shape, error reporting, anything a real ingesting pod wanted and did not find. This is a finding, not a fix: write it down and scope it as its own change. Do not extend Knowledge Flow inside this one

## 6. One fixed-result end-to-end proof

- [ ] 6.1 Add an in-repo example declaration whose handler returns fixed counters and ingests one document through Knowledge Flow's REST API; verify it validates and uses only existing `FieldType` values
- [ ] 6.2 Prove the slice: image published, definition bound to its client, enabled for a team, instance created and configured from the rendered form, run dispatched, handler invoked, document ingested, structured result recorded and readable — asserting the run input carried identifiers only and no secret appears in durable run history
- [ ] 6.3 Prove the failure paths on the same example: handler raises is recorded failed, cancellation is terminal and distinguishable, and a run with no worker reaches a terminal failure without being reported at enablement time

## 7. Quality gate

- [ ] 7.1 Run `make code-quality` from the monorepo root and fix everything it reports
- [ ] 7.2 Run `make test` from the monorepo root and confirm the new tests pass with no regression elsewhere
- [ ] 7.3 Run `/code-review` on the diff before reporting done, per the repository's Step 5 rule
