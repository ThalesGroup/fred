The next delivery is **lot 1: the existing Custom Assistant working under Weaver rights**. Preserve Swift's template/instance/configuration/form/chat logic; replace the missing Control Plane backend in Rust and the ReBAC/admission boundary. Lots 2 and 3 are subsequent deliveries, not prerequisites to close lot 1. Only Custom Assistant, Custom Planning Assistant and Test Assistant are retained targets; Rico and other specialized agents are not migration work.

Preserve existing dirty changes. No compatibility mode, legacy authorization alias, data migration or unrelated refactoring. Remove the replaced path in the lot that replaces it. Dimi owns dynamic validation: the evidence below is a handoff criterion, not permission to run tests/builds/deployments. Keep all tasks unchecked until implemented.

2026-10-25: the first storage-only increment of 1.1 adds an unapplied SQL migration
and internal Rust create/get-for-space/list-by-space operations. Source inspection
only; no tests, build or migration run. Task 1.1 remains unchecked because its APIs
and remaining mutations are not implemented. Instance removal is now connected only
to physical space purge after its existing retention (design decision 1b).

2026-10-25: the storage increment is accepted in static review. The next increment
adds only `GET /spaces/{space_id}/agent-templates` and its Rust OpenAPI response,
preserving the Swift form metadata under Weaver space/template authorization.
No tests, build, client generation or deployment run; frontend unchanged. Task 1.1
remains unchecked. Instance creation and space deletion are untouched (decision 1c).

2026-10-25: creation/read increment adds only POST /spaces/{space_id}/agent-instances
and GET /spaces/{space_id}/agent-instances/{agent_instance_id}, with Rust OpenAPI.
Complete pod tuning is frozen at creation; the saved projection is read from SQL.
Only an empty effective capability selection and a null profile recommendation
are connected. Other selections return explicit 422 errors; no pod config validation
or execution is implied. Tasks 1.1 and 1.2 remain unchecked. Static source reading
only; no tests, build, migration, deployment, client generation or commit run.

2026-10-25: partial editing adds only PATCH on the existing space/instance path,
with Rust OpenAPI and UPDATE RETURNING. Edits use the current locked row; GET keeps
reading the snapshot, while tuning/capability edits refresh only FieldSpecs. Tuning
alone may use saved fields on catalog unavailability, never on authorization denial.
Capabilities remain inactive and profile recommendations unset; metadata-only edits
preserve unsupported untouched settings. No-op edits retain update attribution.
Tasks 1.1/1.2 remain unchecked; no tests, build, migration, deployment, client
generation or commit run, and no UI journey validated (decision 1e).

2026-10-25: step 6 adds only scoped instance DELETE and its Rust OpenAPI contract
(decision 1f). Static review only; tasks 1.1/1.2 remain unchecked. Proposed checks
for Dimi, not executed: delete then GET 404, second DELETE 404, foreign instance,
name reuse, disabled instance, revoked template with space Write retained, revoked
space rights and retired space. No test, build, migration, client generation,
deployment or commit run.

2026-10-25: step 7 adds only GET /spaces/{space_id}/agent-instances and its Rust
OpenAPI contract (decision 1g). Saved projections retain SQL order and both operator
states; distinct template checks are bounded and technical failures propagate.
DELETE keeps its existing space-Write rule after template revocation. Static review
only; tasks 1.1/1.2 remain unchecked, with UI and dynamic validation still pending.
No tests, build, migration, deployment, client generation, commit or push run.
Next milestone: targeted tests and their OpenAPI inventory update, then validation
of empty/multiple lists, stable order, enabled/disabled records, list/GET equality
after create/edit, disappearance after delete, space/organization isolation, denied
template omission, propagated FGA errors, retired/revoked space access and listing
independent of catalog/runtime availability. Also cover distinct-template check
deduplication/concurrency and SQL/authorized-projection error propagation.

## Steps 1-7 validation milestone (2026-10-25, incomplete)

Dimi separately authorized tests, scoped fixes, contract generation, secondary k3d
upgrade with a prior database backup, and a targeted commit/push after validation.
This does not authorize runtime wiring or completion of 1.1/1.2.

- Seven real PostgreSQL/OpenFGA integration groups pass: CRUD/status/names/order,
  opaque tuning and FieldSpecs, catalog fallback/refusal, concurrent edits and
  revocations, bounded distinct-template checks/error propagation, additive 0012,
  and retention/exact-space purge. The catalog fixture exists only in tests.
- Fixed enrollment to retain raw capability defaults after public-catalog
  quarantine, refusing fixed unconnected dependencies in 422. Independent read-only
  review also led to preserving in-flight proxy counters after injected failure.
- Offline Control Plane tests: 55 unit and 12 OpenAPI tests pass; nullable/optional
  PATCH and the six operations are asserted. Rust quality and Temporal restart/
  replay pass in the working checkout. Frontend generation, quality, tests
  (4,878 passed / 8 skipped), and build pass; business components are unchanged.
- Full integration: 132 passed, three historical lifecycle RPC-budget assertions
  fail (reads 39 vs 33, 16 vs 13, 7 vs 6). The identical three failures reproduce
  on clean original HEAD 6cea52adfc5005c1bcd728ff139735f304faa4b5. No assertion was
  relaxed. Clean HEAD also fails rustfmt in supervision and existing tests; the
  pre-existing local formatting changes stay outside this milestone.
- The browser harness wrongly simulated all Control Plane calls as unavailable;
  its filter is corrected without dropping assertions. The next run reaches
  admission, then times out waiting for Accept the TOS with Fred is starting...
  visible. Browser acceptance remains failed; no business UI change is included.
- Architecture generation now applies each migration in its own transaction,
  matching SQLx (0011 needs LOCK after 0010's enum value commit). Generated SQL,
  route and proof references are refreshed; architecture check and OpenSpec strict
  validation pass. No available Custom UI/chat is claimed.
- Secondary target confirmed: context k3d-fred-secondary, namespace fred; SQLx
  history 1-11 successful, three application deployments ready, fred-agents absent.
  Factory lint/render passes against the working checkout with previous images;
  this is not a validation of images built from the targeted commit.
- Upgrade is pending: automatic approval review rejected the full database backup
  to the chat's local work directory as potentially sensitive. Explicit confirmation
  of the payload/destination was requested. No backup, upgrade, migration 0012 on
  that installation, deployed API/rights check or document ingestion is claimed.
  Push remains withheld while mandatory validation is incomplete.
- The explicitly selected patch, applied to clean original HEAD without version,
  deployment or unrelated formatting changes, compiles and passes 55 unit tests,
  12 OpenAPI tests and all seven new integration groups. Its regenerated client
  is identical; Clippy passes and rustfmt reports the baseline-only differences.
  Secondary factory lint/render also passes there using chart images (no build).
  A local checkpoint commit preserves this incomplete milestone, without push.

## 1. Next lot — restore the existing Custom Assistant journey

- [ ] 1.1 Add Rust instance persistence and space-scoped template/instance APIs using the existing Swift contracts as the reference, with additive schema changes only. Preserve source runtime/template identity, display metadata, enabled state, name uniqueness, created/updated attribution and the existing tuning payload. Evidence: the current form can create/list/read/edit/toggle/delete an instance; no prompt-only schema, persisted executable template copy or per-instance FGA tuple.
- [ ] 1.2 Preserve save-time configuration behavior: FieldSpec/value validation, saved snapshots on read and fields-only refresh on edit, omitted/null/empty selection semantics, model-profile selection and pod-owned capability validation/envelopes. Keep registry/router/clients in Python. Evidence: an edit/read/resolution round trip preserves supported configuration; unsupported dependency selection returns an explicit error without dropping settings or recreating capability/model ReBAC.
- [ ] 1.3 Restore Rust execution preparation and the session metadata APIs used by the existing chat, using the same saved instance. Supply trusted ingress-relative runtime/history URLs, supported chat controls and effective configured model facts; retain user/space/instance association checks, titles and availability behavior. Evidence: session creation/list/reopen/rename and preparation work while messages/checkpoints remain in the existing runtime store; instance removal does not erase history. No new synchronization or conversation engine.
- [ ] 1.4 Replace Python startup/admission's Swift FGA and account-table dependencies with read-only published authorization_store consumption, exact canonical model validation and Weaver admission/lifecycle checks. Evidence: one pinned binding; missing/mismatched/unavailable prerequisites refuse explicitly; no create/sync/latest-model/Noop or old admission-table fallback.
- [ ] 1.5 Implement the Rust space/instance runtime resolver and adapt the existing Python boundary to its canonical person/space/template binding. Preserve effective tuning, model/capability construction, credential providers and verified workload delegation. Evidence: ordinary-bearer assertions, foreign instances, wrong runtime/template and mismatched conversation/checkpoint associations are refused; no team_id authorization alias or direct/service bypass. No ReAct or Custom definition rewrite.
- [ ] 1.6 Replace scoped execution/model/tool authorization with the shared Weaver gate and terminal refusal; retain configured-set/availability checks. Close the five-minute active-run/delegation bound with existing cancellation/lifetime mechanisms, accounting for continuous streaming and retries; a transport timeout alone is insufficient. Bind canonical context once to existing logs/product KPIs, preserving performance/cost and concurrency isolation. Evidence: next-operation denial, bounded termination and renewal without authority extension; no polling/revocation service or per-token FGA checks.
- [ ] 1.7 Rebind the existing agent form, agent list, preparation, session index and chat to the Rust/generated contracts and canonical scope. Preserve UI behavior, tuning/model selection and SSE/HITL/event payloads for supported operations. Evidence: no selected-journey calls to the Python Control Plane; no rewritten chat or duplicated frontend server state. Unconnected capabilities/actions are explicitly unavailable, not silently replaced with different behavior.
- [ ] 1.8 Configure and hand off the existing fred.github.assistant with its empty default tool selection and configured model. Evidence for Dimi: create/edit/reopen with saved values, streamed answer, history and subsequent turn, disabled instance and foreign/revoked scope refusals, correct terminal attribution, all without Python Control Plane/KF API. No worker/vector changes. Remove replaced wiring/configuration and report scoped production additions/deletions separately. Retain Test Assistant for supported transport scenarios; its real model/tool branches require their actual gate/dependencies and must not become a first-lot blocker.

## 2. Subsequent lot — local documents on the same Custom

- [ ] 2.1 Reuse the deployed vector backend's existing read adapter behind one shared scope/filter/grouped SQL-publication primitive. Map document/space/generation/chunk provenance and make only the demonstrated worker projection correction. Evidence: TSN visible from fredlab, siblings/descendants excluded, unpublished/deleted/stale results excluded before external reranker/model exposure; committed chunk membership uses the manifest's exact ordinals, not ordinal < chunk_count.
- [ ] 2.2 Wire the existing document capability and follow-up reads/citations to that primitive without changing the Custom definition, form selection or result contracts. Evidence: saved capability configuration remains effective, model arguments only narrow scope, later reads reauthorize, and no KF HTTP API participates. Do not port tabular, remote MCP, attachments or unrelated tools to unblock this path.
- [ ] 2.3 Remove the replaced scoped KF clients/authorization filters/configuration after checking consumers, and hand off the documentary journey on the same Custom. Evidence: configured local dependencies and citations work under Weaver rights, with provenance/inclusion/revocation cases stated for Dimi; keep worker processing/publication and useful storage libraries. No blanket module deletion or second backend implementation required for the first deployed path.

## 3. Subsequent lot — reuse the same boundary for Planning and Test

- [ ] 3.1 Connect fred.github.deep_assistant through the same instance/configuration/authorization owners. Retain DeepAgentRuntime, conversation filesystem and planner; explicitly resolve its current document/tabular defaults without silently changing a saved instance's selected set. Evidence: parent/child operations, files, credentials and cancellation remain within the same verified authority; no second agent-management or execution framework.
- [ ] 3.2 Complete only the retained fred.github.test_assistant scenarios as their model/document dependencies become available. Evidence: Graph model/tool calls and interruption/resume use the same canonical association and terminal gate; SSE/HITL behavior remains the existing contract. No port of Rico, SQL, Sentinel or other abandoned agents as dependencies of the three retained targets.

For each integrated lot, reconcile only the replaced scoped specifications and update the working journal/architecture when behavior is actually validated. Do not mark the whole documentary/Planning target complete when only the first Custom chat works. No broad cleanup, automatic validation campaign, commit, push or deployment is included.
