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


2026-10-25: a read-only sub-increment of 1.4 adds
`fred_core.security.rebac.authorization_binding.read_authorization_binding`.
It borrows the caller's AsyncEngine, reads the published singleton, checks nonblank
text fields and exact configured store identity, and returns an immutable typed
binding. It releases the connection and reports failures without driver details.
Static reading only; no tests, lint, build, deployment or generation run. No OpenFGA
calls or startup wiring. Task 1.4 remains unchecked: exact model retrieval/validation,
image distribution and lifespan integration belong to subsequent increments.

2026-10-25: the next sub-increment of 1.4 adds
`authorization_model.validate_authorization_binding(binding, config, *, token=None)`.
It owns/closes one HTTP client, GETs only the published store/model and returns the
same binding after raw-JSON comparison matching Rust Fga::bind/normalized_model.
Canonical resource, missing remote model, malformed response, incompatibility and
communication errors are distinct and credential-safe. No SQL or FGA mutation.
Setuptools wheel/sdist/editable hooks and the final fred-agents Docker COPY prepare
distribution from the sole Rust model source; provenance/commands are in fred-core's
README. No copy generation, installation, test, lint, build or deployment was run.
Static review only; task 1.4 remains unchecked, with startup/admission still unwired.
Dimi's checks: exact/default-only model accepted; changed ID/schema/relation/condition,
unknown nonempty fields and reordered arrays rejected; 404/invalid JSON/network
errors distinguished; exact GET only; installed/image resource available outside
the checkout; HTTP closure on success/failure/cancellation and SQL ownership intact.

2026-10-25: distribution-only follow-up adds the same canonical COPY to Knowledge
Flow prod (all variants) and dev before installation. Fred-agents already has it;
prod builders exclude local installs. Docker context now excludes the generated
resource, retaining the tracked Rust source. Static review only; no tests, build,
generation or deployment, and no dynamic packaging validation. The pre-existing
dev layout mismatch (/app versus ../../libs and ../../scripts) remains out of scope.
Lots 1/2 are preserved and task 1.4 stays unchecked.

2026-10-25: Dimi retained all Swift global admission features but explicitly
prioritized core Weaver ReBAC for the next increment. Global filtering is deferred,
not a prerequisite for that increment and not abandoned. See design decision 2a
and task 4.1. Do not substitute organization membership as the global policy or add
a temporary execution refusal/catalog mode. Existing identity, delegation, CGU,
resource authorization and departure/lifecycle decisions remain in scope as agreed.
This records sequencing only; it closes no task and claims no runtime validation.

2026-10-25: startup wiring now borrows runtime SQL for the published binding,
releases it before exact-model validation and constructs a pinned OpenFGA client
using the existing transport/KPIs. The pod removes Swift global admission,
suspension and user-store wiring; all its common user dependencies retain shared
JWT/delegation verification and read Rust-owned terms_acceptance for the effective
canonical person. Remaining Swift consumers retain their admission helpers.
C3/PostgreSQL and matching store/terms configuration are explicit prerequisites;
shipped pod settings are aligned without activation. Runtime/catalog/Custom,
durable storage and resource permission checks remain. Static reading only:
no startup, tests, lint, build, generation or deployment run. Task 1.4 remains
unchecked pending Dimi's validation and remaining scoped authorization work;
instance resolution, sessions, execution gates and the five-minute bound follow.

2026-10-25: the Rust half of 1.5 implements the space/instance runtime resolver
using persisted instances, complete saved tuning and canonical placement. Its
route-scoped receiver accepts verified persons or the existing person/run/agent
assertion from a trusted workload (configured incoming delegation, issuer,
audience, role, client restrictions and optional Keycloak service markers).
It checks effective-person terms, active/readable space, instance ownership and
enabled state, canonical template provenance and can_use. No runtime catalog
round trip, agent execution, token issuance or authorization lease. Source
OpenAPI/config schemas updated through Rust declarations only; generation and
all dynamic validation remain Dimi's. Python consumption, sessions, frontend
and the embedded Rust agent are unchanged; task 1.5 stays unchecked.

2026-10-25: secondary deployment preparation enables the real Python pod and
runtime/capability migrations, configures Rust discovery of its existing catalog,
and exposes the pod prefix through ingress. The ingestion preparation hook now
expects the four application deployments. No automatic organization activation,
Python protocol/execution changes or embedded-agent changes. Deployment, catalog
visibility and UI activation remain for Dimi to validate; the chat journey and
all related tasks stay open. No rendering, generation, tests, build or rollout run.

## Small delivery sequence for the first Weaver chat (2026-10-25)

Dimi confirms that Rust keeps only the product responsibilities already owned by
Swift's Python Control Plane: configured instances, session metadata, authorization
of its own operations, binding resolution and execution preparation. The browser
streams directly from the pod. Models, tools, messages/checkpoints, execution,
credential renewal and run termination stay in Python. No new Control Plane
orchestrator, streaming proxy, signed grant or per-operation authorization REST.

These are increments of the existing lot 1, not a second feature plan. Deliver one
focused diff and its concrete check at a time; Dimi owns dynamic validation. No
automatic test/build/deployment campaign. A partial increment does not establish
execution readiness; keep chat unavailable until the complete path is connected.

| Increment | Small implementation boundary | Focused handoff check |
| --- | --- | --- |
| A — Python binding (1.5) | Consume the existing Rust resolver and canonical space/person/instance/runtime/template contract; reuse saved AgentTuning and credential transport. Replace the old resolver path without a team alias or fallback. No Rust execution service. | In isolation, saved prompt is preserved; mismatched subject, space, instance or runtime is refused. No claim that existing execution gates already work. |
| B — Python execution (1.4–1.6) | Replace scoped Swift gates with the agreed Weaver operation gate; retain configured model routing and dependency checks. Bind telemetry from canonical context. Implement bounded run/delegation lifetime using existing cancellation. | Configured no-tool Custom executes through the pod; disabled/revoked/foreign targets are refused, denial stops the run, credentials cannot extend terminated authority. The maximum turn duration and cleanup budget must be explicit before implementing the five-minute bound. |
| C — Session metadata (1.3/1.5) | Add Rust storage and space-scoped create/list/get/rename/activity APIs from the Swift product behavior. Capture owner, instance and runtime provenance; preserve history after instance deletion. Complete runtime association checks before history/checkpoint loading. | Own session can be reopened/renamed; foreign owner/space or different instance is refused, including resume; instance deletion does not erase messages. No message store in Rust. |
| D — Preparation (1.3) | Restore instance prepare-execution with trusted browser-facing runtime/history URLs, supported controls and configured model facts. Validate a supplied session association. Generate affected API clients from their sources. | Correct saved instance routes to its configured pod; disabled instance or mismatched session is refused; no internal service URL is sent to the browser. |
| E — Existing chat UI (1.7/1.8) | Rebind existing chat, session list and shell to generated Weaver contracts/canonical spaces; enable Discuss. Preserve streaming, interruption/HITL contracts and persistence behavior for supported operations. | First answer streams, second turn retains context, reload/reopen and rename work; no selected-journey Python Control Plane request or cross-space state leak. Check terminal error/cancellation and saved history separately. |

The first target remains the existing Custom with no tools and a configured model.
Documents, Planning, MCP, attachments, prompt library and conversation erasure are
not prerequisites. Leave their controls explicitly unavailable. Existing engine,
model/client and transport implementations remain the owners; remove replaced
wiring inside each increment without broad shared-module deletion.

Creation is now confirmed by Dimi in the deployed UI. Other management operations
and the chat journey are not thereby validated. All parent tasks remain open.

## 1. Next lot — restore the existing Custom Assistant journey

- [ ] 1.1 Add Rust instance persistence and space-scoped template/instance APIs using the existing Swift contracts as the reference, with additive schema changes only. Preserve source runtime/template identity, display metadata, enabled state, name uniqueness, created/updated attribution and the existing tuning payload. Evidence: the current form can create/list/read/edit/toggle/delete an instance; no prompt-only schema, persisted executable template copy or per-instance FGA tuple.
- [ ] 1.2 Preserve save-time configuration behavior: FieldSpec/value validation, saved snapshots on read and fields-only refresh on edit, omitted/null/empty selection semantics, model-profile selection and pod-owned capability validation/envelopes. Keep registry/router/clients in Python. Evidence: an edit/read/resolution round trip preserves supported configuration; unsupported dependency selection returns an explicit error without dropping settings or recreating capability/model ReBAC.
- [ ] 1.3 Restore Rust execution preparation and the session metadata APIs used by the existing chat, using the same saved instance. Supply trusted ingress-relative runtime/history URLs, supported chat controls and effective configured model facts; retain user/space/instance association checks, titles and availability behavior. Evidence: session creation/list/reopen/rename and preparation work while messages/checkpoints remain in the existing runtime store; instance removal does not erase history. No new synchronization or conversation engine.
- [ ] 1.4 Replace the core Python startup/ReBAC wiring with read-only published authorization_store consumption, exact canonical model validation and the agreed Weaver identity/resource/lifecycle controls. Separate the legacy global-filtering dependency from this increment: its full port is deferred to 4.1, not a prerequisite (design 2a). Preserve JWT, trusted delegation and CGU within their agreed scope. Evidence: one pinned binding; missing/mismatched/unavailable binding/model prerequisites fail explicitly; no create/sync/latest-model/Noop, old admission-table fallback, substitute global policy or temporary execution refusal. Do not claim full Swift admission parity from this task.
- [ ] 1.5 Implement the Rust space/instance runtime resolver and adapt the existing Python boundary to its canonical person/space/template binding. Preserve effective tuning, model/capability construction, credential providers and verified workload delegation. Evidence: ordinary-bearer assertions, foreign instances, wrong runtime/template and mismatched conversation/checkpoint associations are refused; no team_id authorization alias or direct/service bypass. No ReAct or Custom definition rewrite.
- [ ] 1.6 Replace scoped execution/model/tool authorization with the shared Weaver gate and terminal refusal; retain configured-set/availability checks. Close the five-minute active-run/delegation bound with existing cancellation/lifetime mechanisms, accounting for continuous streaming and retries; a transport timeout alone is insufficient. Bind canonical context once to existing logs/product KPIs, preserving performance/cost and concurrency isolation. Evidence: next-operation denial, bounded termination and renewal without authority extension; no polling/revocation service or per-token FGA checks.
- [ ] 1.7 Rebind the existing agent form, agent list, preparation, session index and chat to the Rust/generated contracts and canonical scope. Preserve UI behavior, tuning/model selection and SSE/HITL/event payloads for supported operations. Evidence: no selected-journey calls to the Python Control Plane; no rewritten chat or duplicated frontend server state. Unconnected capabilities/actions are explicitly unavailable, not silently replaced with different behavior.
  - [x] Agent-management sub-lot implemented locally (2026-10-25): generated space CRUD/catalog, canonical team/personal context, server Write decision, partial PATCH preservation, scoped RTK refresh and explicit unavailable adjacent actions. Existing UI retained; no generated client or backend edit.
  - [ ] Dimi validates this management UI after redeployment with Editor, Reader and refused access. Preparation, session index and chat still remain outside this sub-lot; do not close 1.7.
- [ ] 1.8 Configure and hand off the existing fred.github.assistant with its empty default tool selection and configured model. Evidence for Dimi: create/edit/reopen with saved values, streamed answer, history and subsequent turn, disabled instance and foreign/revoked scope refusals, correct terminal attribution, all without Python Control Plane/KF API. No worker/vector changes. Remove replaced wiring/configuration and report scoped production additions/deletions separately. Retain Test Assistant for supported transport scenarios; its real model/tool branches require their actual gate/dependencies and must not become a first-lot blocker.

## 2. Subsequent lot — local documents on the same Custom

- [ ] 2.1 Reuse the deployed vector backend's existing read adapter behind one shared scope/filter/grouped SQL-publication primitive. Map document/space/generation/chunk provenance and make only the demonstrated worker projection correction. Evidence: TSN visible from fredlab, siblings/descendants excluded, unpublished/deleted/stale results excluded before external reranker/model exposure; committed chunk membership uses the manifest's exact ordinals, not ordinal < chunk_count.
- [ ] 2.2 Wire the existing document capability and follow-up reads/citations to that primitive without changing the Custom definition, form selection or result contracts. Evidence: saved capability configuration remains effective, model arguments only narrow scope, later reads reauthorize, and no KF HTTP API participates. Do not port tabular, remote MCP, attachments or unrelated tools to unblock this path.
- [ ] 2.3 Remove the replaced scoped KF clients/authorization filters/configuration after checking consumers, and hand off the documentary journey on the same Custom. Evidence: configured local dependencies and citations work under Weaver rights, with provenance/inclusion/revocation cases stated for Dimi; keep worker processing/publication and useful storage libraries. No blanket module deletion or second backend implementation required for the first deployed path.

## 3. Subsequent lot — reuse the same boundary for Planning and Test

- [ ] 3.1 Connect fred.github.deep_assistant through the same instance/configuration/authorization owners. Retain DeepAgentRuntime, conversation filesystem and planner; explicitly resolve its current document/tabular defaults without silently changing a saved instance's selected set. Evidence: parent/child operations, files, credentials and cancellation remain within the same verified authority; no second agent-management or execution framework.
- [ ] 3.2 Complete only the retained fred.github.test_assistant scenarios as their model/document dependencies become available. Evidence: Graph model/tool calls and interruption/resume use the same canonical association and terminal gate; SSE/HITL behavior remains the existing contract. No port of Rico, SQL, Sentinel or other abandoned agents as dependencies of the three retained targets.

## 4. Deferred retained scope - Swift global admission filtering

- [ ] 4.1 Port the complete global admission feature in a separately scoped subsequent lot: filtering enabled/disabled, verified identity-attribute policies (allow/block, all/any and existing operators), access-manager admission, individual exceptions, authorized teams and Free-link-derived admission, including current membership/join provenance and delegated-person evidence. Preserve the alternative admission paths and their separation from CGU, account/departure and resource permissions. Align with the already accepted Weaver departure semantics; do not restore reversible suspension. Reuse the canonical Weaver owners rather than restoring legacy tables or a parallel authority. Evidence: each admission source and its removal, combined sources, delegated calls and unavailable dependencies behave according to the explicitly scoped contract. This retained work is not a prerequisite for the next core ReBAC increment; no temporary blocking code or substitute global policy is authorized while it is pending.

For each integrated lot, reconcile only the replaced scoped specifications and update the working journal/architecture when behavior is actually validated. Do not mark the whole documentary/Planning target complete when only the first Custom chat works. No broad cleanup, automatic validation campaign, commit, push or deployment is included.

## Agent-management UI evidence (2026-10-25)

Explicit authorization covers the following frontend checks only, executed from
`apps/frontend` against the modified checkout:

```
npx vitest run src/rework/components/pages/TeamAgentsPage src/rework/components/shared/organisms/AgentCard src/slices/controlPlane/controlPlaneApi.test.ts src/rework/components/shared/layouts/Sidebar/TeamContentNavbar src/rework/components/shared/layouts/Sidebar/MainNavBar src/rework/components/shared/molecules/UserProfile src/rework/features/applications/useTeamApplications.test.ts
npm run typecheck
npm run build
```

Results: 30 test files / 256 tests passed, TypeScript exit 0 and production build
exit 0. Vite reports non-blocking chunks over 500 kB. The generated Control Plane
client is unchanged; no regeneration was needed. `git diff --check -- apps/frontend`
also passes. Early introduced type/test-harness errors were corrected; there is
no remaining failure in this targeted set. This is not a global test result.

DOM tests use the real generated RTK endpoints and mocked HTTP, including create
then GET, metadata-only and tuning edits, failed-save draft retention, empty states,
Read/Write separation, status/delete, 401/403/404/409/422/network/server, unavailable
actions, in-flight space switch and exact-space cache invalidation. Sidebar tests
assert skipped legacy dependencies; these are not deployed browser acceptance.

Backend limits are retained: effective capabilities must be empty and model
recommendations null on creation; unsupported edits remain refused by the server.
Metadata-only edits omit existing opaque settings. GET exposes saved values but
not saved FieldSpecs; without a catalog the form still edits metadata and preserves
tuning. Authors use their raw saved identifiers without legacy directory reads.

Dimi's handoff: test Editor create/reopen/edit/toggle/confirmed delete, Reader list
without catalog/mutations, explicit forbidden access, personal space and switching
spaces with no old selection. Verify Network has no legacy team-agent or ancillary
requests and disabled chat/copy/publication/assistant/asset controls send nothing.
No deployment, migration, cluster rights change, backend tests, image build, commit,
push, OpenSpec archive or expanded arc42 validation is claimed. Task 1.7 stays open.
