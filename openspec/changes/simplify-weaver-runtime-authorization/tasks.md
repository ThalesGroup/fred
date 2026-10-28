2026-10-26 sequencing update: Dimi prioritizes complete agent/model and
pod-scoped capability administration before the first chat. Design decision 5b
supersedes the earlier no-tool-first sequence below; those tasks remain technical
work, not the current delivery order. Arc42 now contains a proposed explanatory
introduction and the agreed administrator journey. No production implementation
or schema migration is included in this documentation step.

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

## Administration increments under decision 5b (2026-10-26)

1. Pod-owned persistence: additive catalog observation, capability offerings keyed
   by `(runtime_id, capability_id)`, and template links constrained to that owner.
2. Complete pod inventory and organization-authorized read/refresh contracts;
   unavailable/withdrawn states, public OpenAPI and generated clients together.
3. Organization agent decisions and platform-discovered model offers keyed by
   source/upstream ID; no per-pod manual model catalog (decision 5e, M1-M5).
   Approved endpoints and credentials remain platform-owned.
4. Instance configuration validation at the owning pod and persistence of its
   envelopes, including incompatible/unavailable diagnostics and policy checks.

Increments 1 and 2 are implemented locally: `0014` catalog storage, complete pod
registry advertisement, organization read/single-pod refresh and generated contracts.
No UI, model policy, configuration validation/saving or runtime execution is included.
The existing no-tool guards remain. No migration is applied and no functional
validation is claimed. The parent administration/chat tasks remain open.

Manual checks for Dimi (not executed in this increment):

| Setup/action | Expected observation |
| --- | --- |
| Configure A and B; same local ID, versions v2/v1; refresh A | Separate `(runtime_id, capability_id)` offers; B unchanged |
| Install a tool with no compatible declared consumer | Offer present, no consumer link |
| Remove an A offer and successfully refresh | Retained descriptor with `advertised=false`; instance settings/history intact |
| Stop A or return non-success HTTP after a successful snapshot | Refresh 503; `unavailable`, updated `checked_at`, prior `observed_at`, offers/links preserved |
| Return malformed/incomplete/oversized data, `complete=false`, duplicate offer/link or contradictory runtime/source/version | Refresh 502; no partial replacement or successful empty inventory |
| Link a template to an offer absent from A but present on B | Refresh 502; no cross-pod link |
| Restore a valid A response, including a legitimately empty complete inventory | Refresh 204; A observation/advertised flags and links match this snapshot; B unchanged |
| Call as organization manager, member without Manage, platform-only identity, foreign-organization identity or non-admitted identity | Existing admission/Manage/placement/lifecycle refusal; no implicit platform bypass |
| Retire the organization or revoke Manage while the pod call waits | Post-discovery authorization prevents the write |
| Configure a disabled source or request an unknown runtime | GET includes disabled source without URL; refresh 409/404; no browser-chosen destination |
| Compare backend JSON with regenerated OpenAPI/TypeScript | Required completeness/collections, observation enum, nullable timestamps, explicit runtime identity and failure statuses agree |

Quality and generation evidence is recorded in F25. No tests, validation campaign,
installation migration, deployment, commit or push were run. These manual cases do
not establish model policy, configuration compatibility or runtime availability.

## Platform model catalog: accepted sequence (decision 5e)

2026-10-26: Dimi requested M1 implementation after accepting 5e. M1 code is
implemented locally; functional validation and migration application remain open.
Capability increments 1/2 are preserved. Real source credential grants remain
separate. The later accepted M4 turn-boundary arbitration removes the proposed
SQL authority view/grant and per-invocation authority reads. M2 administration was subsequently
requested and implemented locally. M3 now adds instance settings and resolver data;
M4-M5 remain untouched. Quality and generation
evidence is recorded in F25, separately from unexecuted functional acceptance.

- [x] M1 Apply the accepted source/authentication, chat/completeness and outage
  decisions. Add platform source definitions and Rust
  observation/offer persistence with composite identity and revision fencing.
  Implement bounded API-only discovery; no manual offer creation or pod aggregation.
  Delivered in `apps/control-plane/src/model_catalog`, additive migration 0015,
  platform configuration and generated configuration/chart schemas. Internal
  refresh/read only; checked here means implemented, not functionally validated.
- [x] M2 Expose organization Manage-protected inventory/read/refresh and explicit
  permitted-set/default/fallback policy, with backend-generated contracts. Keep
  new discoveries unpermitted and source provisioning platform-only. Delivered in
  `model_catalog/{http,policy,store,discovery}`, additive migration 0016 and the generated
  Control Plane contract/client. Checked means implemented, not functionally validated;
  this delivers administration, not effective runtime prohibition.
- [x] M3 Connect instance recommendation/options validation and the existing
  runtime resolver to offer references and trusted non-secret bindings. Preserve
  unrelated tuning and diagnosed stale choices. Specify explicit re-selection of
  old profile references; no automatic name-based migration or compatibility mode.
  Implemented locally in `agent_instances/{http,tuning,runtime}` and
  `model_catalog/instance`, with M2 selection guard reuse, generated OpenAPI/client
  and targeted existing-form display/save adaptation. Checked means implementation
  and technical quality only, not functional validation or Python invocation wiring.
- [x] M4 In the separately launched runtime lot, adapt the existing router/factory,
  source-bound pod credentials and the existing resolver interaction: one complete
  authorized context per turn, local checks for every model call/retry/descendant,
  no extra HTTP/SQL/OpenFGA authority reads. Initially support OpenAI-compatible
  inference. Remove replaced paths and platform/fallback bypasses at cutover,
  without dual dispatch. Revocations/decommissioning take effect next turn; retain
  explicit cancellation and terminal cleanup, not the superseded five-minute bound.
  Implementation and final static quality are complete, including the explicitly
  authorized retirement. Checked does not claim functional acceptance: prepared
  scenarios remain unexecuted at Dimi's request. See decision 5e and F25.
- [x] M5a Supply private space-scoped session metadata and browser execution
  preparation only: idempotent registration, owner-scoped read/list/title/activity,
  immutable provenance, retained history after instance removal, approved public
  routing and M2/M3 model facts without connections. Generate contracts and perform
  scoped static quality checks. Prepare functional cases without executing them.
  No UI/chat wiring, tests, migration application, commit or parallel assistant.
- [x] M5b Secure runtime history consultation through persisted M4 provenance and
  the existing M5a metadata GET with the person's own credential. Cover messages,
  session IDs and checkpoint detail/index with one guard; retain current space Read
  after instance removal without execution resolution. Prepare cases without running
  them; scoped formatting/quality, strict OpenSpec and diff checks only.
- [x] M5c Rebind the existing chat, private session list and Discuss entry to the
  generated M5a/M5b contracts and M4 runtime. Retain frontend session IDs, canonical
  space/instance associations, direct public pod SSE, composite model choices and
  the existing UI. Separate history reads from execution preparation; suppress
  stale/denied content with existing RTK refresh and request cancellation.
  Implementation/static quality only; the functional cases below are not executed.
- [ ] M5 Validate the complete UI/chat journey after deploying the integrated lots;
  check the cutover of replaced manual catalog/profile/discovery consumers.
  Check remaining shared consumers before deletion; preserve Knowledge Flow models
  and processing. No parallel legacy mode. Only then validate the complete journey.

M5c technical handoff (2026-10-26), **implemented, not functionally validated**:

- Existing routes, page, cards, sidebar, model popover and SSE event renderer are
  retained. Agent/chat shells use the existing Weaver membership context; the
  personal alias resolves only through `/me/spaces`. No old team/template/model
  association is inferred. Discuss opens the selected canonical instance.
- Generated create/list/get/update/prepare operations replace selected-journey
  legacy session and model requests. The existing client-generated UUID is reused
  for registration retries; registration settles before per-send preparation.
  Owner isolation remains server-side. Session tags refresh the exact space/list
  and detail after title/activity writes; current RTK errors hide retained data.
- Metadata supplies the public history URL independently of live instance state.
  A history visit never prepares execution. Preparation is requested for a new
  draft, typing intent in an existing conversation, and every actual send. Deleted
  or disabled instances retain history but cannot send; a template/preparation
  failure uses the existing notice/toast and never prevents a separate history read.
- The pod receives only the explicit `model_choice` composite, canonical `space_id`
  and selected `agent_instance_id`. Recommendation/default/fallback/options stay
  server-owned. The existing model menu presents generated preparation facts;
  revoked/missing/legacy choices are not replaced with the first available model.
  No local profile/catalog, inferred endpoint or new grant is introduced.
- Browser history requests are abortable, no-store and reject redirects. Scope
  switches clear the displayed thread; stale completions cannot cross person,
  space or conversation. No cache is shown before a current read. Refusals and
  technical failures clear both display and the corresponding snapshot; 200 + []
  remains empty. Existing focus/poll refresh is reused, without a new watcher.
  A successful but older history snapshot cannot erase a newer streamed exchange.
- Only advertised controls are active. M5a currently advertises no tool controls
  and no HITL. Attachments, prompt/skill discovery, voice, capability panels and
  session deletion have no enabled path in this slice. Their unrelated owners
  are not migrated or removed. No document/Knowledge Flow work is included.
- No backend or generated contract was changed, so no regeneration was needed.
  Targeted `node_modules/.bin/prettier --write <lot files>` and frontend
  `make code-quality` (tsc --noEmit, Prettier check, ESLint) passed after correction
  of introduced typing/fixture errors. OpenSpec strict and `git diff --check`
  passed. No test suite, application build, service, provider, migration,
  deployment, commit, push or other assistant was run.
- Model-menu/composer fixtures were adapted to M5 preparation; they are prepared,
  not executed. The broader Swift chat/SSE/history test harnesses still contain
  old endpoint/cache/HITL expectations and need migration in an authorized test
  lot. Passing TypeScript is not passing those suites.

M5c functional cases **prepared, not executed**:

| Case | Expected observation / boundary |
| --- | --- |
| New draft, lost registration response, retry, first message | One frontend UUID; identical space/instance POST; M5a idempotence; no stream before registration/preparation; draft retained on failure |
| Stream, second turn, reload/reopen | Direct approved pod URL and existing SSE frames; current history read; no Rust message proxy; persistence timing caveat below |
| Own private list, other owner, rename/activity | Only own rows in current space; exact-space list refresh; title persists, server activity ordering retained; foreign IDs refused |
| Instance deleted/disabled; template unavailable | Metadata/history remain independently readable under current rights; sending disabled or explicit preparation failure; history visit issues no prepare |
| Revoke Read between consultations/focus refresh | Current refusal clears visible thread and snapshot; no cached successful response presented as authorized |
| Authorized empty, 401/403/404, 5xx/network | 200 + [] stays empty; unavailable/access versus technical states; no failure rewritten to [] |
| Switch person/space/session while GET, POST or preparation is pending | Old content never appears under the new scope; old continuations cannot start a turn; mismatched metadata association refused |
| Same upstream ID from two sources; recommendation/options saved in M3 | Keys stay distinct; explicit choice wins server-side; no client override of saved options/recommendation; stale/withdrawn/forbidden choice retained for server refusal/fallback decision |
| No recommendation/default but selectable offers; legacy recommendation | Existing menu permits explicit composite selection; never first-offer auto-selection or silent legacy adoption |
| Existing navigation/layout/model menu and unsupported controls | Same interaction/layout components; no legacy session/model/attachments/prompt/skill network calls from selected journey; unadvertised controls unavailable |
| Repeated LLM calls/retries/descendants | Preparation remains informational; M4 still owns one complete admission per external turn, with local checks thereafter |

Prerequisites/limits: deploy the existing M1-M5b contracts and generated clients
consistently; apply migrations 0015-0017 only in a separately authorized deployment;
configure approved `public_base_url`, runtime/history storage, delegation and pod
source credentials, successful model discovery and organization model policy.
The initial supported no-tool React/Graph instance must be enabled and authorized.
No legacy history adoption is performed. A registered session with no M4 provenance
returns M5b's uniform 404, not a proven empty history; a new send is independently
checked by preparation/M4, never by reinterpreting that refusal.

The runtime documents history persistence after stream close and emits no durable
`turn_persisted` acknowledgement. Immediate reload can therefore precede the write;
M5c cannot promise read-after-final durability. The smallest future arbitration is
to emit the existing persistence event only after the write succeeds (or explicitly
accept this visibility delay), in a separately scoped runtime change. No retry loop,
synchronizer or persistence change is added here. M5, 1.7 and 1.8 remain open.

M5b technical close-out (2026-10-26), implementation/static quality only:

| Command | Observed result |
| --- | --- |
| `libs/fred-runtime/.venv/bin/ruff check --select I --fix` and `ruff format` on the five changed Python files | Passed; targeted imports/formatting only |
| `make code-quality` in `libs/fred-runtime` | Final exit 0, zero errors and five pre-existing unreachable-code warnings. One introduced Optional access error corrected; full check rerun after the last test-fixture edit. |
| `make code-quality` in `apps/fred-agents` | Final exit 0, zero errors/warnings |
| `make update-runtime-api` in `apps/frontend`, then `npx --no-install prettier --write src/slices/runtime/runtimeOpenApi.ts` | Exit 0; OpenAPI generated canonically, resulting RTK client identical to the pre-lot file. No HTTP parameter/response type change or frontend component change. |
| `openspec validate simplify-weaver-runtime-authorization --strict` | Passed |
| `git diff --check` | Passed |

Four obsolete direct HTTP read cases in test_history.py were replaced by the
prepared Weaver route cases; mutation and execution cases were preserved. Static
review confirms the existing client has a 10-second timeout and a bounded pool,
provenance SQL is released before HTTP, and no execution path calls this guard.
No performance or functional measurement is claimed. No tests, real providers,
applied migrations, deployment, commit, push or other assistant. M5 stays open.

M5b handoff (2026-10-26): implementation and prepared cases in
`libs/fred-runtime/tests/test_weaver_history_access.py`; **not executed**.

| Prepared case | Expected result |
| --- | --- |
| Owner, current Read, matching provenance | Content returned after M5a; authenticated uid filters messages |
| Different person, including same-space reader | Uniform 404, no message/checkpoint load |
| Same owner loses Read between two consultations | Second consultation denied by a fresh M5a GET; no old decision reused |
| Instance deleted/disabled, template unavailable | Read succeeds if M5a authorizes; no prepare-execution/resolver/template lookup |
| Session/space/instance/template/runtime mismatch | Uniform refusal before content, including wrong receiving pod |
| Old data or metadata-only registration without M4 provenance | Explicit unavailable; no binding creation, adoption or repair |
| Authorized bound session has zero messages | 200 with [] and no-store |
| CP 401/403/404/503, redirect, network failure | Auth/refusal/technical errors separated; no redirect, retry or content |
| Provenance or message SQL unavailable | Technical error, never fake [] |
| Substitute session path or user/space/runtime query IDs | Authenticated identity and persisted placement still govern |
| Service marker/role or AssertedUser | Refused before storage/CP; no fabricated delegation or run |
| Checkpoint detail and both indexes | Same guard; lists omit refusals only and abort on technical failures |
| Old run terminal, LLM retries/descendants active | History has no run dependency; M4 still one resolver per external turn |
| Actual PersonCredentialProvider with a client auth default | Own bearer reaches configured M5a URL, client auth disabled, no grant params |

Read-only consumer review: CLI `PodClient` raises HTTP errors; existing
`useSessionHistory` uses the supplied URL, refreshes its person bearer and marks
non-2xx unavailable. Frontend cached content behavior remains a separate M5 concern;
no frontend wiring or cache modification is claimed. `_stats` exposes aggregate
counts/bytes only; mutation endpoints remain outside M5b. Earlier Swift integration
fixtures in test_history/test_agent_app still require their M4/M5 migration when
functional suites resume; these are not successful validation evidence.

M5a technical close-out: targeted rustfmt and generated-client Prettier applied;
`make code-quality` passes in control-plane and frontend. Canonical
`make update-control-plane-api`, `make generate-config-schema` and
`generate_chart_schema.py` succeeded. Chart values/schema validation, Helm lint,
strict OpenSpec validation and diff whitespace checks pass. SQLx 0.9 compilation
was corrected to use static parameterized SQL before the successful rerun. Browser
DTO/schema inspection confirms no inference connection/credential reference.
Migration 0017 remains unapplied; SQL and product behavior are not functionally
validated. No test, provider, deployment, commit, push or other assistant was used.
Detailed evidence and remaining integration boundary are recorded in F25.

2026-10-26 resumption: M5a implementation and migration 0017 already existed in
the checkout. Canonical generation and the quality/strict validation commands above
were rerun successfully; generated contracts are unchanged. No additional migration,
UI wiring or functional execution was introduced. M5 remains open.

M5a handoff (2026-10-26), functional cases **prepared, not executed**:

Use two admitted people A/B with Read in space S, another space T, an enabled
no-tool Custom instance I, another instance J, and an explicitly approved public
runtime route. These are a manual checklist, not executed tests or provider calls.

| Action | Expected result |
| --- | --- |
| Register frontend ID X for A/S/I | 201, same X, canonical instance/template/runtime and A ownership; one metadata row, no messages/checkpoints created by CP |
| Drop the successful registration response, then repeat; repeat concurrently | 200 original association/title/timestamps; no duplicate or reassignment; failed original transaction can instead create once on retry |
| Rename X, then replay its initial POST with the old title | Replay preserves the renamed title and current activity |
| Read/list/PATCH/prepare X as B, even with space Manage or platform role | Private record hidden as 404, absent from B's list; no metadata change or history URL leak |
| Reuse X under another space or A/S/J; alter runtime/template/owner in POST/PATCH | Wrong space/owner 404; incompatible owned instance 409; unknown authority fields 422; X unchanged |
| Advance activity, submit an older time and a future time; rename only | Activity never regresses, future value capped at server time; stable descending activity/ID order; rename does not alter activity |
| Disable I after X exists | GET/PATCH/replay remain usable; agent_disabled=true; preparation 409; no history deletion |
| Delete I after X exists, including after a lost registration response | GET/list/PATCH/replay retain X, agent_deleted=true and saved identity/name; preparation 404; messages URL retained while source remains approved; no runtime erasure |
| Revoke template Use while A retains space Read | Metadata remains privately readable; new registration/preparation/runtime turn admission refused |
| Revoke space Read, retire the space or withdraw admission | Applicable metadata and preparation operations refused by existing guards; no cached preparation grants authority |
| Omit/disable public runtime source; configure absolute URL, //host, encoded traversal or query/fragment | Missing/disabled routing explicit; invalid public config rejected; no internal URL derivation or alternate source |
| Stop discovery or fail/redirect its HTTP response | Explicit preparation error; no fallback, messages or partial authority; metadata/history routing remains independent |
| Supply no session then a matching, missing, foreign or mismatched session to preparation/resolver | No-session preparation allowed; supplied session must match; runtime resolver refuses unregistered or incompatible conversations before model execution |
| Present old runtime history/checkpoints without provenance after registering X | M4 refuses adoption; no metadata-to-runtime synchronization or implicit recovery |
| Inspect browser JSON/OpenAPI and generated TypeScript | Exact public paths/nullable history, no inference URL/credential binding/secret, model identities and diagnostics from M3, no local model profile |
| Select active capabilities or an unconnected execution family | Explicit 422/409; empty controls do not silently discard configured dependencies |
| Lose a PATCH or preparation response | Read metadata to determine persisted title/activity; a preparation retry performs ordinary checks and creates no run/grant; frontend behavior to wire in M5 |
| Later validate ten LLM calls, retries and descendants after preparation | Still one complete M4 resolution per external turn, zero subsequent authority refreshes; revocation effective next turn |

Remaining cutover prerequisites: apply additive migrations separately; approve real
public ingress and model credential provisioning; bind existing chat/sidebar hooks
to generated space/session/preparation contracts and composite model facts; add the
runtime history space/admission check without requiring a surviving instance; then
validate functional cases with Dimi. Context prompts/attachments/HITL and other
unconnected controls need their own scoped wiring. M5 remains unchecked.

M4 handoff (2026-10-26), functional cases **prepared, not executed**:

| Case | Prepared evidence / expected result |
| --- | --- |
| Ten LLM requests in one turn | `test_model_routing_provider.py` keeps one TurnAuthority across ten guarded sends. At admission integration, count exactly one resolver request and zero subsequent authority HTTP/SQL/FGA reads. |
| Mid-turn revocation | Mutate the next resolver fixture while the first scope runs: its snapshot stays valid; the next admission is refused. No timer or polling. |
| Next resolver unavailable | Close the first scope, fail the next admission HTTP call, verify no invocation or cached authority reuse. |
| Forbidden choice/fallback, legacy profile | `test_model_enforcement.py`: explicit refusal, no substitution except confirmed withdrawal to an allowed candidate. |
| Concurrent sources A/B | `test_model_routing_provider.py`: isolated destinations and credentials through a shared pool; no global env writes. |
| bind_tools / structured output / retry / child | Transport cases reject changed wire model/options; integration must exercise real LangChain transformations and both middleware and SDK retries, with no new admission. Uncovered template is refused. |
| Cancel / terminal / pause / resume | Local scope cases reject retained clients and reused authority. Integration must cover disconnect cleanup, HITL resume as a new admission and cancellation during streaming. |
| Conversation provenance | First binding, matching continuation, foreign space/instance/user, old unbound history and concurrent first binding; no permission data persisted. |

M4 technical close-out (2026-10-26):

| Command / working directory | Observed result after the final relevant edit |
| --- | --- |
| `make code-quality` in `libs/fred-core` | Exit 0; Ruff, Bandit and Basedpyright, no errors/warnings. |
| `make code-quality` in `libs/fred-sdk` | Exit 0; no errors/warnings. |
| `make code-quality` in `libs/fred-runtime` | Exit 0, rerun after cleanup; no errors, five existing unreachable-code warnings (filesystem_factory, conversation_filesystem twice, deep/conversation_port, test_delegated_admission). |
| `make code-quality` in `apps/fred-agents` | Exit 0, rerun after removing the unused model-catalog fixture; no errors/warnings. |
| `PATH=/home/dimi/.cargo/bin:$PATH make code-quality` in `apps/control-plane` | Exit 0; Clippy all targets, rustfmt, FGA model parity. No test execution. |
| `make code-quality` in `apps/frontend` | Exit 0, rerun after client generation; TypeScript, Prettier and ESLint pass. |
| `make update-runtime-api` in `apps/frontend`, then targeted Prettier | Exit 0; canonical OpenAPI/RTK regeneration after removing routes and correcting descriptions. Control Plane client was also canonically regenerated in M4. |
| `apps/fred-agents/.venv/bin/python scripts/check_chart_values.py deploy/charts/fred/values.schema.json deploy/charts/fred/values.yaml` | Exit 0. |
| `helm lint deploy/charts/fred` | Exit 0. |
| `helm lint deploy/charts/agent-pod -f /tmp/fred-m4-agent-pod-values.yaml` | Exit 0; file extracted from the documented configuration example. Bare lint first refused missing runtime_id/security, required deployment inputs already documented, not a new schema failure. |
| Canonical `generate_chart_schema.py` and `generate_pod_chart_schemas.py` with existing fred-agents Python, output to `/tmp/fred-m4-final-schema`, then `diff -q` against both affected chart schemas | Exit 0; no schema drift. This avoids the previously reported missing pip in the scripts bootstrap without changing generated files by hand. |
| `openspec validate simplify-weaver-runtime-authorization --strict` and `git diff --check` from repository root | Exit 0; repeated after this final documentation update. |

Contract/consumer review is source and generated-type evidence, not functional
execution. The runtime API client has no catalog routes or catalog DTOs; no
handwritten application consumer references those removed endpoints or modules.
M3 persistence and management APIs retain `recommended_model` and `model_options`:

| Contract | Owner and consumer evidence | Disposition |
| --- | --- | --- |
| Instance recommendation | Rust `agent_instances/tuning.rs` stores the composite key; `model_catalog/instance.rs::resolve` exposes `models.recommendation`; SDK `RuntimeModels`; Python `ModelRoutingResolver.resolve` | Preserved, below explicit choice and above organization default. `AgentTuning` is only the prompt/capability projection, not a replacement model-policy source. |
| Instance options | Rust `SavedModelSettings.model_options` -> `RuntimeModels.options` -> `RoutedChatModelFactory.build_for_chat` -> transport guard | Preserved: temperature, max_tokens, top_p; no YAML/settings merge or hidden profile. Unsupported options/provider behavior remains an explicit failure. |
| Legacy recommendation | Rust emits `legacy_profile_id` / `requires_reselection`; resolver refuses without a new composite choice | Diagnostic only, never mapped by model name. |
| One turn authority | `_authorize_and_resolve` -> `_resolve_agent_instance` -> private `TurnAuthority`/`RunScope` | One complete resolver request; LLM guards make no HTTP/SQL/FGA authority reads. Separate data/service and credential controls remain. |
| Transformed calls / retry / descendants | ReAct and Graph activate the same factory; Deep passes its bound model; `GuardedChatOpenAI` and checked shared clients; `LocalRegistryAgentInvoker` | Local checks at invocation/send, no new admission for retries/children. Uncovered templates refused. Terminal scope cannot authorize later sends; next external turn resolves again. |
| Model administration UI | Generated Control Plane types retain composite recommendation/options; existing AgentFormBody displays saved key or diagnostic legacy text, and weaverAgents preserves settings on unrelated saves | M3 behavior preserved; no M5 selector/chat flow added. |

The closed public pod-catalog endpoints and four DTOs were removed after explicit
user authorization. Discovery/catalog/authz modules, YAML, Docker/Helm mounts,
profile-policy contracts and obsolete catalog/profile cases remain deleted.
Remaining legacy execution integration fixtures need adaptation when that
functional suite is taken up; no result is claimed for them. Prepared M4 cases
above remain unexecuted. No campaign, provider, migration, deployment, commit,
push or M5 work; the full chat journey is not validated.

M3 manual acceptance handoff, **not executed**. Use the existing 0015/0016 schema
and controlled discovery fixtures after the developer's separate migration decision.
No migration, provider call or test was launched for M3.

| M3 case | Exact action and expected result |
| --- | --- |
| Create/reopen | With Write and template Use, create a team instance referencing a permitted/current/chat/advertised `(A, x)` and three valid options. POST 201 and GET/list restore the exact key/options and unrelated tuning. `(B, x)` remains a different offer. |
| Partial edit and reset | Change only name/description and compare all tuning/capability/model values. PATCH omission preserves; `recommended_model: null` clears only that key; `model_options: null` or `{}` resets only options. An options object replaces its complete three-member set; null/omitted members leave no override. |
| Invalid structure | Send booleans/strings as numbers, fractional/zero/negative max_tokens, top_p outside [0, 1], non-finite JSON numbers, unknown reasoning/provider/URL/credential/retry/timeout fields. Existing extraction/422 validation refuses the complete mutation, without partial metadata update. |
| Known limits | For known output/context caps, save max_tokens above either cap with a new recommendation or options edit: 422. At/below caps is structurally admissible; missing metadata adds no invented limit. A smaller cap observed later produces `options_exceed_known_limit` and no candidate, without rewriting saved options. Input budget and actual provider support are not validated here. |
| Unknown, forbidden and non-chat | New unknown or unpermitted key returns 422; a permitted withdrawn, disabled, non-chat or stale/unobserved-source key returns 409 from the M2 guard. No first-model selection or different-source name match. |
| Revocation | Revoke a saved recommendation through M2. GET keeps the key; descriptive PATCH succeeds. Resolver reports `not_permitted`, candidate false, no connection. Explicitly clear the recommendation successfully; no default/fallback is selected by the resolver. |
| Outage and recovery | After a successful permitted snapshot, publish unavailable/invalid/incomplete discovery. Existing current-revision candidates remain last-known, with diagnostic and selectable false. New recommendation changes fail 409; metadata edits and clears succeed. No fallback/withdrawal is inferred. Recovery makes new selection eligible again without restoring revoked permission. |
| Confirmed withdrawal | Successful complete discovery omits a previously selected key. The reference remains, diagnostic is `withdrawn`, candidate false. Default/fallback references remain explicit; no automatic substitution occurs. M4 must still verify the actual fallback and local usability. |
| Stale revision | Advance/disable source configuration while retaining its old successful snapshot. Resolver reports the current and snapshot source revisions, `source_revision_unobserved`, candidate false and no connection; a new recommendation fails 409 until fresh success. |
| Concurrent writes | Race recommendation save with policy revocation and source publication/configuration. Existing organization lock and M2 source/offer share locks serialize the decision: either write uses eligible facts then later becomes diagnosed, or current facts refuse it. Metadata saves apply to the current locked row, preserving concurrent untouched settings. |
| Canonical personal organization | Resolve/create in a personal space owned by A while the browser sends an organization/destination/binding/permission field: unknown input is refused. Without forged input, policy belongs to A from SQL placement. Foreign scope, missing consent, rejected delegation, disabled instance and revoked template retain existing refusals. |
| Connection boundary | Compare direct-person resolver, trusted workload resolver with full matching delegation, ordinary GET/list and organization inventory. Only the trusted delegated resolver receives candidate provider/root/inference-binding references. No discovery URL, discovery credential reference or secret appears anywhere. Invalid/incomplete delegation returns existing 403/422; no input can add a connection. |
| Legacy reference | Seed a saved legacy profile. Metadata save preserves it; GET retains it. Resolver exposes `legacy_profile_id`, requires_reselection true and excludes it from executable configuration. Non-null legacy writes fail 422. Explicit new composite selection retains the old string, sets requires_reselection false; explicit legacy null clears it. No name mapping. |
| Existing UX | Reopen old/new instances in team/personal Agents. Same pages, tabs, field placement and interactions; model field shows the composite key or old diagnostic string. Name/description/tuning save sends no model options/key/profile change. Failed saves retain the draft. No new selector, option control, organization flow, chat or legacy request is added. |

Technical evidence: scoped rustfmt and Prettier, `make -C apps/control-plane code-quality`,
`make update-control-plane-api` and `make code-quality` from `apps/frontend` passed.
Clippy's introduced unused variable was corrected and checks rerun. OpenSpec strict
validation and `git diff --check` passed after final documentation edits (see F25).
No tests were executed; these cases remain Dimi's functional acceptance. No claim
is made for Python selection, credentials, invocation gates or M4 restrictions.

M2 manual acceptance handoff, **not executed**. After the developer applies 0015/0016
to a disposable database, use controlled discovery fixtures and two organizations,
with independent admitted managers, ordinary members and a platform-only user.
Inspect both HTTP responses and committed SQL; no real provider is required.

| M2 case | Exact action and expected result |
| --- | --- |
| Admission, Manage, placement and lifecycle | Exercise all four routes without a bearer (401), without current consent (403), as a same-organization member without Manage (403), with foreign organization or non-organization ID (404 when otherwise authorized), and with retired organization (409). A platform role alone adds no access. Refused refresh makes no provider request or claim; refused PUT changes no policy. |
| Organization isolation and new discoveries | A/B share a source and `same-model`; GET shows the same observation but revision 0/empty policy per new organization. A permits it at expected revision 0; B remains empty. A second source with the same upstream ID remains a different unpermitted key. |
| Revocation during discovery | Hold HTTP after claim; revoke Manage, remove organization attachment, retire the organization or remove consent through the existing mechanisms, then release success and failure responses. Post-HTTP checks refuse publication in both cases; all observation/offer/snapshot fields retain their prior values. A later authorized refresh can supersede the abandoned token. |
| Concurrent refreshes | Hold A1, claim A2, complete in each order; also fail or cancel A2. Only A2 may publish, A1 returns 409 `model_refresh_superseded`. Refresh source B concurrently and verify its independence. Observe no SQL connection/transaction retained during either HTTP wait. |
| Configuration race and stale replica | Hold revision-1 HTTP; apply revision 2 or disable the source before completion. Old publication returns 409 without changing the new observation. A replica still holding revision 1 cannot claim a refresh against revision 2 SQL. Unknown source is 404; configured disabled source is 409. |
| Policy conflict | Two PUTs carry expected revision N with different permitted sets/choices. Exactly one commits N+1; the other receives 409 `model_policy_revision_conflict`. Verify no mixed set/default/fallback, correct subject/timestamps, unchanged created attribution. An old revision after an explicit empty write also conflicts. |
| Unknown/non-chat/withdrawn offer | Newly permit an unknown composite key (422 `unknown_model_offer`), or a present false/unknown-chat, disabled or confirmed-withdrawn offer (409 `model_offer_not_selectable`). A name resembling another model does not match it. No partial policy write. |
| Default/fallback consistency | Set default/fallback outside `permitted`, duplicate a key, omit a required field, submit an unknown field or exceed 4096 entries: 422. Revoke a selected key while explicitly clearing/replacing the choice: one atomic success. No automatic default or fallback is chosen. |
| Outage additions versus reductions | Seed permitted X/Y with default X, then fail discovery. Preserve the choices/diagnostics; adding Z or changing default/fallback to retained Y fails 409. Remove Y while keeping unavailable default X, clear either choice, revoke X with explicit clearing, or write an empty set: succeeds. No outage fallback. |
| New source revision without new success | Retain the old snapshot while applying a higher source revision, then fail discovery at that revision. Presence and old chat metadata remain visible, but new permission/default/fallback choices fail. Only a complete success with matching snapshot_source_revision permits them. |
| Withdrawal, changed chat metadata and reappearance | Refresh successfully removes X or marks it non-chat: policy reference/revision stays unchanged and diagnostics differ. Clearing/revoking is still possible. Reappearance creates no grant if X was revoked; a retained grant remains an explicit old choice, not an automatic new permission. |
| Eligibility race | Pause a PUT while competing refresh/configuration changes the candidate source/offer. Source/offer row locks serialize the decisions: write checks the current committed eligible facts or fails, never authorizes from a different revision mid-transaction. Permission removal does not depend on locking unavailable candidate sources. |
| Secret/configuration projection | Use synthetic distinct discovery/inference credential markers. Inspect every successful/error response, generated schemas and logs: no key values, env references, inference binding, destination, scopes, raw provider payload or internal source configuration is projected. Supplied URL/credentials are never used; policy body unknown fields are refused. |
| Physical organization purge | After the normal retention lifecycle, policy/permissions cascade only with physical organization removal; other organizations and platform observations survive. User departure or retirement alone retains organization choices. |

Technical compilation and generated contracts do not validate these SQL/HTTP/FGA
interleavings. Stop after M2; no runtime path is claimed validated.

M1 manual validation handoff, **not executed**. Use local controlled HTTP/SQL
fixtures through the internal `configure_sources`, `refresh` and `inventory`
operations; there is intentionally no model route or CLI in M1. Migration 0015
must first be applied by the developer to a disposable validation database.

| M1 case | Expected observation and persistence |
| --- | --- |
| A/B both advertise `same-model`; refresh, fail or withdraw A | Independent composite keys. Every B row/date/snapshot remains unchanged. Exact IDs survive without normalization. |
| Mixed source returns true, false, missing or malformed `capabilities.completion_chat` | All valid IDs remain advertised. Chat is respectively true, false, unknown, unknown, with API provenance only for booleans. Names suggesting tools/reasoning do not create features. |
| Missing/invalid label or token limit; chat-qualified source without metadata | Invalid optional fields stay unknown. Chat guarantee is explicitly marked as source provenance; supported positive integer limits alone are retained. |
| Complete omission, complete empty response, repeated omission, then reappearance | First withdrawal time preserved on repeated omission; first_seen and composite identity survive. Reappearance clears withdrawn_at, updates last_seen/metadata; no permission is created. |
| Timeout/refused connection, 401, redirect, duplicate/blank/oversized ID, malformed JSON, body above one MiB | Sanitized unavailable or invalid attempt. No redirect target receives a request. last_success, snapshot revision and every offer remain unchanged. |
| Truncated body/JSON, 206, Link/Content-Range, pagination/partial markers, unknown envelope field | Incomplete attempt, never replacement. A valid empty list without the configured completeness guarantee is also incomplete. |
| Hold response at source revision 1; apply revision 2 or disable before release | Old completion returns Superseded and changes no observation/offer. Same revision with changed content and lower revisions are refused. Destination/account/namespace changes require a new source ID. |
| Hold refresh A1, start A2, then finish in either order (also fail/cancel A2); refresh B concurrently | Only the latest A token may publish. No old success or failure overwrites A2. Cancellation retains the previous snapshot; a later refresh recovers without a lease. B is independent. |
| Different discovery keys for A/B, distinct catalog/inference hosts; broader credential without/with acceptance | Each request uses only its configured discovery env reference. No pod credential lookup or inferred destination. Broader authority without explicit acceptance fails validation. Missing/invalid secret yields sanitized unavailable status. |
| Inspect SQL, returned inventory and logs using synthetic secrets; attempt a configuration change during HTTP | No bearer/raw body/headers exposed; inventory omits URLs and references. Configuration can complete while HTTP is pending, demonstrating no retained SQL connection/transaction. |
| Remove an enabled source from deployment config, then disable it at a higher revision and remove | First change is refused; explicit disabling retains diagnosable source/offer rows and invalidates in-flight refreshes. |

The remaining cross-increment acceptance cases are **not executed**. Each row belongs to its
implementation increment; runtime cases do not establish M1 acceptance.

| Case | Expected result |
| --- | --- |
| Sources A/B both return `same-model`; refresh or withdraw A | Two offer keys; B and saved B choices unchanged. No identity inferred from label, URL or runtime. |
| Organizations Acme/Other share the inventory; Acme permits only A | Other's policy is unchanged; cross-organization read/write/execution context is refused. Newly discovered B gains no permission. Personal instances use their canonical owning organization. |
| Forbidden model supplied as user choice, recommendation, default, forced binding or fallback; agent authorized | Save/invocation refusal as applicable, no request to that model; activation and a higher routing priority cannot broaden Acme's set. |
| Allowed A disappears; configured allowed B exists | Saved A choice retained; only a complete successful A inventory confirms removal. B may be invoked with recorded fallback reason after the same policy/destination/local-support checks. Missing, withdrawn or forbidden B fails. |
| Discovery timeout, 401, invalid JSON, duplicate ID, oversized/truncated or paginated/incomplete response | Attempt status changes; last success/offers/permissions unchanged. No confirmed withdrawal or disappearance fallback, even if the HTTP status is 200. |
| Complete valid empty response, then A reappears | Withdrawal recorded; same key restored on return. A previously revoked organization grant is not restored. |
| Discovery fails while saved A was last advertised | Accepted outage policy retains saved A eligibility under current restrictions; new selection writes wait. Pod inference availability remains a separate result. |
| Change source destination/account/scope, or complete an old refresh after a revision change | New identity and explicit re-selection for semantic changes; old completion cannot publish. Credential rotation with identical scope preserves identity and choices. |
| Organization/browser changes catalog/inference URL or a provider returns a redirect | Refusal before any credential-bearing call to an unapproved destination. Catalog and inference URLs may legitimately differ only through platform approval. |
| Discovery succeeds with a separate key; pod has no inference key/network/client support | Inventory exists, execution explicitly unavailable; no key copied into Rust and no alternate source selected by wire name. Concurrent A/B requests use only their own bound keys. |
| Mixed source advertises chat and non-chat offers with reliable metadata | Keep the complete inventory; only established chat offers are eligible. Metadata changes do not falsely withdraw an offer still present. |
| Discovery credential also permits inference | Source requires explicit platform acceptance of that authority before use; merely issuing a different key is not proof of read-only rights. |
| Model name suggests tools/reasoning, but API metadata supplies none | Unknown features remain unknown; no inferred reasoning/limits. An agent requiring an unestablished feature is unavailable. |
| Authority revoked or source/model decommissioned after resolver response | The admitted turn may finish within its fixed context, including reused clients and retries. The next turn resolves current authority and refuses/narrows it as applicable; no old context reuse. |
| One turn makes ten LLM calls, retries or child steps | Exactly one complete resolver admission; no additional SQL/HTTP/OpenFGA reads to refresh turn authority. Local checks reject any model/target outside that context. |
| Resolver fails at turn start, or a completed turn is retried as a new turn | No inference with a prior context. Obtain a fresh successful admission for the new turn or fail explicitly. |
| Remove pod model catalog after consumer cutover | Default and fallback resolve discovered offer keys; no hidden manual default. Prompt/capability tuning and Knowledge Flow embeddings remain unchanged. |

The original framing used source/document reading only. M1 subsequently passed
targeted rustfmt, Control Plane `make code-quality`, configuration/chart schema
generation and static chart-values validation, strict OpenSpec validation and
`git diff --check`; exact commands and the chart-tool fallback are in F25. No tests,
provider calls, applied migration, deployment, commit, push or other assistant.
Administrative/runtime acceptance remains open.


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
instance resolution, sessions and execution gates follow under the later accepted
M4 turn-boundary arbitration; the earlier five-minute revocation bound is superseded.

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
| B — Python execution (1.4–1.6) | Replace scoped Swift gates with one complete turn-start resolution and local context enforcement; retain routing/dependency checks, telemetry, cancellation and terminal cleanup. | Configured no-tool Custom executes through the pod; disabled/revoked/foreign targets are refused at turn admission. Mid-turn changes take effect next turn. Credentials cannot revive terminal authority; no added authority polling or five-minute revocation deadline. |
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
- [ ] 1.2 Preserve save-time configuration behavior: FieldSpec/value validation, saved snapshots on read and fields-only refresh on edit, omitted/null/empty selection semantics, discovered model selection under decision 5e and pod-owned capability validation/envelopes. Keep registry/router/clients in Python. Evidence: an edit/read/resolution round trip preserves supported configuration; unsupported dependency selection returns an explicit error without dropping settings or recreating capability/model ReBAC.
- [ ] 1.3 Restore Rust execution preparation and the session metadata APIs used by the existing chat, using the same saved instance. Supply trusted ingress-relative runtime/history URLs, supported chat controls and effective configured model facts; retain user/space/instance association checks, titles and availability behavior. Evidence: session creation/list/reopen/rename and preparation work while messages/checkpoints remain in the existing runtime store; instance removal does not erase history. No new synchronization or conversation engine.
- [ ] 1.4 Replace the core Python startup/ReBAC wiring with read-only published authorization_store consumption, exact canonical model validation and the agreed Weaver identity/resource/lifecycle controls. Separate the legacy global-filtering dependency from this increment: its full port is deferred to 4.1, not a prerequisite (design 2a). Preserve JWT, trusted delegation and CGU within their agreed scope. Evidence: one pinned binding; missing/mismatched/unavailable binding/model prerequisites fail explicitly; no create/sync/latest-model/Noop, old admission-table fallback, substitute global policy or temporary execution refusal. Do not claim full Swift admission parity from this task.
- [ ] 1.5 Implement the Rust space/instance runtime resolver and adapt the existing Python boundary to its canonical person/space/template binding. Preserve effective tuning, model/capability construction, credential providers and verified workload delegation. Evidence: ordinary-bearer assertions, foreign instances, wrong runtime/template and mismatched conversation/checkpoint associations are refused; no team_id authorization alias or direct/service bypass. No ReAct or Custom definition rewrite.
- [ ] 1.6 Replace scoped execution/model/tool authorization with one complete Weaver resolver context per turn and local enforcement; retain configured-set/availability and resource-specific checks. Follow the later M4 arbitration: no authority refresh on each invocation, retry or descendant; mid-turn revocations take effect next turn. Preserve explicit cancellation, terminal cleanup and execution limits without introducing a five-minute revocation deadline. Bind canonical context once to existing logs/product KPIs, preserving performance/cost and concurrency isolation. Evidence: one admission per turn, local rejection outside its scope, next-turn revocation and renewal without widening/reviving authority.
- [ ] 1.7 Rebind the existing agent form, agent list, preparation, session index and chat to the Rust/generated contracts and canonical scope. Preserve UI behavior, tuning/model selection and SSE/HITL/event payloads for supported operations. Evidence: no selected-journey calls to the Python Control Plane; no rewritten chat or duplicated frontend server state. Unconnected capabilities/actions are explicitly unavailable, not silently replaced with different behavior.
  - [x] Agent-management sub-lot implemented locally (2026-10-25): generated space CRUD/catalog, canonical team/personal context, server Write decision, partial PATCH preservation, scoped RTK refresh and explicit unavailable adjacent actions. Existing UI retained; no generated client or backend edit.
  - [ ] Dimi validates this management UI after redeployment with Editor, Reader and refused access. Preparation, session index and chat still remain outside this sub-lot; do not close 1.7.
- [ ] 1.8 Configure and hand off the existing fred.github.assistant with its empty default tool selection and configured model. Evidence for Dimi: create/edit/reopen with saved values, streamed answer, history and subsequent turn, disabled instance and foreign/revoked scope refusals, correct terminal attribution, all without Python Control Plane/KF API. No worker/vector changes. Remove replaced wiring/configuration and report scoped production additions/deletions separately. Retain Test Assistant for supported transport scenarios; its real model/tool branches require their actual gate/dependencies and must not become a first-lot blocker.

## 2. Subsequent lot — local documents on the same Custom

- [ ] 2.1 Reuse the deployed vector backend's existing read adapter behind one shared scope/filter/grouped SQL-publication primitive. Map document/space/generation/chunk provenance and make only the demonstrated worker projection correction. Evidence: TSN visible from fredlab, siblings/descendants excluded, unpublished/deleted/stale results excluded before external reranker/model exposure; committed chunk membership uses the manifest's exact ordinals, not ordinal < chunk_count.
- [ ] 2.2 Wire the existing document capability and follow-up reads/citations to that primitive without changing the Custom definition, form selection or result contracts. Evidence: saved capability configuration remains effective, model arguments only narrow scope, later reads enforce admitted scope and current document facts, and no KF HTTP API participates. Do not port tabular, remote MCP, attachments or unrelated tools to unblock this path.
- [ ] 2.3 Remove the replaced scoped KF clients/authorization filters/configuration after checking consumers, and hand off the documentary journey on the same Custom. Evidence: configured local dependencies and citations work under Weaver rights, with provenance/inclusion/revocation cases stated for Dimi; keep worker processing/publication and useful storage libraries. No blanket module deletion or second backend implementation required for the first deployed path.

## 3. Subsequent lot — reuse the same boundary for Planning and Test

- [ ] 3.1 Connect fred.github.deep_assistant through the same instance/configuration/authorization owners. Retain DeepAgentRuntime, conversation filesystem and planner; explicitly resolve its current document/tabular defaults without silently changing a saved instance's selected set. Evidence: parent/child operations, files, credentials and cancellation remain within the same verified authority; no second agent-management or execution framework.
- [ ] 3.2 Complete only the retained fred.github.test_assistant scenarios as their model/document dependencies become available. Evidence: Graph model/tool calls and interruption/resume use the same canonical association and terminal gate; SSE/HITL behavior remains the existing contract. No port of Rico, SQL, Sentinel or other abandoned agents as dependencies of the three retained targets.

## 4. Deferred retained scope - Swift global admission filtering

- [ ] 4.1 Port the complete global admission feature in a separately scoped subsequent lot: filtering enabled/disabled, verified identity-attribute policies (allow/block, all/any and existing operators), access-manager admission, individual exceptions, authorized teams and Free-link-derived admission, including current membership/join provenance and delegated-person evidence. Preserve the alternative admission paths and their separation from CGU, account/departure and resource permissions. Align with the already accepted Weaver departure semantics; do not restore reversible suspension. Reuse the canonical Weaver owners rather than restoring legacy tables or a parallel authority. Evidence: each admission source and its removal, combined sources, delegated calls and unavailable dependencies behave according to the explicitly scoped contract. This retained work is not a prerequisite for the next core ReBAC increment; no temporary blocking code or substitute global policy is authorized while it is pending.

For each integrated lot, reconcile only the replaced scoped specifications and update the architecture in the lot's PR when behavior is actually validated. Do not mark the whole documentary/Planning target complete when only the first Custom chat works. No broad cleanup, automatic validation campaign, commit, push or deployment is included.

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
