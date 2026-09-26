## 1. Implemented contract and source coverage

Checked items confirm inspected source behavior and existing acceptance coverage. Test execution is recorded separately below; a test file reference does not claim a passing run.

- [x] 1.1 Provide directional delegation configuration, token trust checks, caller/subject separation and grant parsing. Evidence: shared `delegation.py`, `oidc.py`, configuration models and their delegation/OIDC tests.
- [x] 1.2 Provide local admission, managed read-only binding lookup, direct execution without control-plane admission, required managed team and per-call credential injection across ReAct, DeepAgent and supported child agents. Evidence: `agent_app.py`, `outbound_credentials.py`, SDK execution models, `test_delegated_admission.py` and `test_outbound_credential_paths.py`.
- [x] 1.3 Provide workload-token caching, synchronized renewal and transport-error compatibility. Evidence: `M2MTokenProvider`, `test_m2m_token_provider.py` and the document publisher polling test.
- [x] 1.4 Provide typed stop reasons and propagation through engines, capability wrappers and child scopes. Evidence: SDK runtime contracts, `run_scope.py`, `test_run_scope.py`, `test_run_stop_authority.py` and capability stop tests.
- [x] 1.5 Provide response-finally cleanup, explicit outer iterator closing, terminal marking on cancellation, human-pause stream completion and fresh answer admission. Evidence: `_RunStreamingResponse`, `_stream_finisher`, `test_delegated_foreground_route.py` and `test_openai_compat_router.py`. Full teardown acceptance remains in section 2.
- [x] 1.6 Keep delegated execution free of platform run-duration, child-count, admitted-run-count and live-record-age limits. Evidence: local record store, run scope and runtime configuration; existing tests cover concurrent children and long-lived admission records.
- [x] 1.7 Provide delegated HTTP tool authentication, per-call token acquisition, isolated grant-bearing connections and ordinary service own-bearer behavior. Evidence: MCP client/interceptor code, `test_delegated_mcp.py` and service-identity admission tests.
- [x] 1.8 Enforce current account standing, startup readiness, protected standing writes and suspension-first account deletion with other relations preserved. Evidence: authorization model/engine, control-plane startup and delete route, standing/startup/delete tests.
- [x] 1.9 Apply service-role shortcuts only to callers without the delegation caller role and retain own-credential endpoint policies. Evidence: runtime admission, receiver service guards, service-identity and knowledge-base ownership tests.
- [x] 1.10 Provide shared first-party configuration, receiver grant declarations, optional tool-mount integration, schema filtering and request isolation. Evidence: `env_config.py`, `mcp_delegation.py`, `mcp_delegation_fastapi.py`, package exports and bridge tests.
- [x] 1.11 Provide bounded authorization and execution diagnostics, grant/standing audit events, token metrics and request-log confinement. Evidence: shared exception handler, authentication metrics, execution diagnostics and corresponding test definitions.
- [x] 1.12 Preserve frontend request ownership, unmount abort, silent intentional abort and single reporting of an unexpected drop. Evidence: `useChatSse.ts` and its stream/abort tests.
- [x] 1.13 Preserve existing shared task and scheduler contracts, explicitly select the control-plane worker configuration, validate the knowledge backend's required secret at startup and keep scheduler connection logs identifier-free. Evidence: shared task sources, worker Makefile target, startup validation and its test.
- [x] 1.14 Provide explicit local delegation overlays, the local setup helper and workload rotation guidance. Evidence: configuration loader and tests, local helper, run-target wiring and operations documentation.

## 2. Focused lifecycle, authority and diagnostic acceptance

These tasks record the executable acceptance still required for ReAct, DeepAgent and the shared implementation. They remain open until their checks pass; source inspection and regression test definitions alone do not complete them.

- [ ] 2.1 Recheck run liveness and stop state after awaited workload-token acquisition, before returning credentials. Verify that ending the run while acquisition or renewal is suspended returns no credential and starts no outbound request.
- [ ] 2.2 Make the owner terminal before asynchronous teardown on normal completion and human pause as well as cancellation. Verify with a still-running child that credential acquisition is refused throughout disposal and pause cleanup.
- [ ] 2.3 Cancel and await the execution producer and every registered descendant, and explicitly close the full iterator chain before response handling returns. Verify that all child tasks are done and all owned iterators are closed at the response boundary, without joining children afterwards in the test.
- [ ] 2.4 Keep asynchronous teardown effective under cancellation and safe on repeated entry. Verify cancellation while iterator closure, descendant cleanup or runtime disposal is awaiting, including cancellation while a child is disposing; require completed cleanup and an absent record on both streaming APIs.
- [ ] 2.5 Preserve the structured standing-unavailable refusal across REST and tool clients and convert it into `authority_lost`, terminating the run and descendants. Verify the same typed stop for local delegated per-tool permission and standing refusals. Verify that this specific 503 response cannot enter ordinary tool-error or retry handling; unrelated 503 responses retain their existing semantics.
- [ ] 2.6 Preserve inner-route authorization refusals in the tool protocol and recognize them before ordinary tool-result conversion. Verify an actual mounted route returning 403 or standing-unavailable 503 over a successful outer transport, with no upstream text surfaced and no further execution.
- [ ] 2.7 Preserve standing refusal and unavailability through native, compatibility and managed admission and control-plane handlers. Verify distinct 403/503 responses, bounded machine-readable causes and standing audit events.
- [ ] 2.8 Confine request logs before authentication and body parsing whenever delegation is configured. Verify JSON-body grants, malformed bodies, authentication failures and redirects without client addresses, paths, identifiers or upstream details; retain ordinary diagnostics with both switches off.
- [ ] 2.9 Share the live person-token provider with child agents when outgoing delegation is disabled. Verify parent and child calls after token replacement, with no delegation grant and ordinary service-identity behavior preserved.

Response, run-scope, credential-provider and downstream-error handling share ownership. Update completion evidence only after the combined behavior passes its focused acceptance checks.

- [x] 2.10 Preserve the curated `read_query` HTTP 400 diagnostic through the actual MCP mount and LangChain adapter into the runtime error artifact. Verify other tools/statuses, malformed bodies and extra response fields cannot expose diagnostics, while typed authority refusals remain unchanged.

Task 2.10 verification (2026-09-25): the mounted regression failed before the fix and passed afterward. The receiver-integration, context-aware-tool and delegated-MCP suites passed all 60 tests, with the existing knowledge-flow environment supplying the optional `fastapi_mcp` dependency. The core/runtime module suites passed 2,380 tests (11 skipped); raw type checks reported zero errors in both packages. Root `make code-quality` passed across all modules using installed dependencies (`UV_NO_SYNC=1 UV_OFFLINE=1`, `MAKE='make -o dev -o node_modules'`). Independent review found no actionable issues. This evidence closes only task 2.10.

## 3. Executable acceptance verification

- [ ] 3.1 Run the native and compatibility streaming matrix through the real application and request-metrics middleware: normal completion, pause, detected disconnect, request cancellation, response-start failure and ASGI 2.4 body-send failure. Assert no leaked record, iterator or child task and no synthetic success on cancellation.
- [ ] 3.2 Verify old live records, more than eight concurrent children and more than 128 concurrently admitted runs; require continuing credential acquisition while each run remains active.
- [ ] 3.3 Run the signed receiver matrix for valid/invalid workload tokens, caller-role and audience checks, grant tampering, expired person/workload tokens, and REST/tool/binding calls. Include ordinary service identity execution with both switches enabled and a delegation caller without a grant. With outgoing delegation disabled, verify that parent and child calls observe live person-token updates and send no grant.
- [ ] 3.4 Verify suspended-person admission for direct, managed and personal-team targets, and suspension during a delegated run. Require the next receiver call to fail with the typed standing refusal and the run to stop; valid old tokens and grants must not restore standing. Include a standing-unavailable 503 through REST and tool clients in ReAct and DeepAgent, requiring `authority_lost` and completed descendant cancellation, plus an unrelated 503 that retains ordinary error handling.
- [ ] 3.5 Verify every knowledge-backend catalog entry uses the intended delegated mode and that service identities retain their own bearer. Run a complete evaluation campaign with both delegation directions enabled.
- [ ] 3.6 Execute frontend stream/unmount tests, denial and log-canary tests, token cache and acquisition metrics tests and grant-decision counter checks. Verify browser refresh diagnostics contain bounded outcome and duration only.
- [ ] 3.7 Verify local overlay dry-run/write/reset behavior against an authorized development environment, including preservation of tracked configuration.
- [ ] 3.8 Verify runtime, control-plane and knowledge-backend OpenAPI clients and configuration/chart schemas match their sources. Run the applicable suites, root code-quality checks and independent hot-path review when execution is authorized.

## 4. Deployment acceptance

- [ ] 4.1 Confirm the database migration head, task-event records and scheduled workflows are compatible with the deployed code while preserving unrelated data.
- [ ] 4.2 Provision and inspect workload client roles, audiences, allowed authentication flows and secret access. Ordinary service identities must not hold the delegation caller role.
- [ ] 4.3 Verify encrypted dependency transport, certificate validation and rejection of external requests carrying delegation grants.
- [ ] 4.4 Publish/select the standing model for every participant, establish the readiness marker from the control plane and verify that incompatible models or missing readiness refuse startup.
- [ ] 4.5 Run the operational acceptance matrix, workload secret rotation and failure/recovery checks. Confirm required metrics are visible in the deployment's monitoring surface.

## 5. Specification validation

- [x] 5.1 Validate the consolidated change with the installed OpenSpec strict validator and check internal links and capability coverage. Evidence: strict validation passed with no issues; all local links and anchors resolve; independent review covered all four capability specifications.

## PR review regressions

- [x] Recheck current standing before delegated personal-team native/local tools; preserve the ordinary service bypass and avoid duplicate organization-team checks.
- [x] Preserve the bounded standing-unavailable 503 and denial header during managed binding resolution; retain generic handling for unrelated upstream failures.

Review regression evidence (2026-09-26): 88 focused tests passed; the complete runtime suite passed 1,563 tests (11 optional-dependency skips, 16 integration cases deselected). After replacing the binding-test double with HTTPX MockTransport for type compatibility, all 29 outbound credential-path tests passed again. Independent correctness and hot-path review found no actionable issue. Root `make code-quality` passed across all modules. These checks close only the two review regressions above, not the remaining deployment acceptance tasks.
