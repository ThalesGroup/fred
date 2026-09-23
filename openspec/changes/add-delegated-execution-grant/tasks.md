## 1. Guardrails (no trust change)

- [x] 1.1 Add the outbound credential provider in the shared runtime and route the
      tool-protocol wrapper and every native client (documents, media, workspace,
      control-plane binding) through it; verify with an enumeration test that
      every outbound call path obtains its credentials from the provider,
      including the built-in similarity adapter after rebinding.
- [x] 1.2 Hand the live provider to child agents and team members on every spawn
      path instead of a copied credential string; verify a test that a provider
      change after spawn is observed by a running child.
- [x] 1.3 Add the `reason` enum to the terminal error event, map a 401/403 from a
      receiver to `authority_lost`, cancel the run and its children, and bypass
      error-to-text; verify per-engine tests that an injected 401 ends the run with
      the typed event, no retry, all children cancelled. Exercise the real document
      capability error handlers and the real local child invoker; preserve the
      stop through error-to-result boundaries and emit exactly one parent terminal
      event when a child stops the shared run.
- [x] 1.4 Redact upstream error bodies before any sink; verify canary tests on
      transcript, log, trace, checkpoint and event sinks for parent and child.
- [x] 1.5 Add the wall-clock run ceiling and the concurrent-child bound in shared
      engine code, configurable per deployment with an agent-override resolver
      hook; verify a test that a run past the ceiling ends with `run_ceiling_reached` while
      per-call timeouts are unchanged. Verify nested children and graph parallel
      members cannot deadlock waiting for capacity held by an ancestor; preserve
      the configured in-flight bound, reject unavailable nested capacity with
      `child_limit_reached`, and distinguish it from elapsed time.
- [x] 1.6 Add the dated runtime-execution-contract entry for the event field and
      the ceiling and regenerate the runtime client; verify the generated contract
      contains the field and declared stop reasons, including
      `child_limit_reached` for unavailable nested capacity.
- [x] 1.7 Make the team identifier a required field on team-scoped execution
      requests instead of an optional one documented as required; regenerate the
      client; verify that a request without it is rejected with a clear error.
- [x] 1.8 Resolve the agent ceiling through definition/tuning, registration and
      finalized admission limits after 1.5, preserving the
      deployment default when unset; verify admission with two differently
      configured agents, invalid-value rejection and unchanged per-call timeouts.
- [x] 1.9 Add the shared failed-refresh cooldown and its configuration to the
      workload token provider; verify concurrent failures cause one network attempt,
      bounded waiter completion and no attempts during cooldown, followed by one
      recovery probe; verify errors expose no upstream details or credentials.

## 2. Grant model and acceptance (shared security library)

- [x] 2.1 Add the delegation configuration block (flag, canonical `person`/`run`/`agent`
      parameters and caller client/subject identities)
      beside the machine-to-machine settings; verify
      config tests, including rejection of an enabled flag with an empty
      allow-list.
- [x] 2.2 Implement the grant model as request parameters and its parsing in the
      shared user dependency with the existing client-allow-list checks, building
      the asserted principal; verify the parsing matrix — parameters with an allow-listed
      bearer (subject built), parameters with a bearer not on the allow-list
      (ignored, no subject, audited), bearer without parameters (caller only),
      malformed or partial parameters (no subject), parameters in tool arguments
      (ignored). The D3 identity and person-authorization checks are covered by 2.6–2.7.
- [x] 2.3 Add the asserted principal type, distinct from the authenticated user and
      never carrying the service role; verify that the service-role predicate is
      false for it and that a dependency requiring an authenticated principal
      rejects it.
- [x] 2.4 Add the `delegated` value to the MCP client auth mode; verify contract
      tests.
- [x] 2.5 Declare the grant parameters on every receiver endpoint a run can call and
      regenerate the generated clients; verify generated clients declare the
      canonical parameters and stable operation identifiers.
- [x] 2.6 Bind verified client and service-account subject in the shared receiver
      dependency; verify a user token with the same client claim or service role
      cannot delegate, and test wrong realm, ID token, invalid validity/algorithm
      and untrusted key-source rejection using the existing token verifier.
- [x] 2.7 Accept delegation from verified trusted client/subject pairs. Verify person action,
      object, field and team authorization, including administrative permissions,
      and preserve the explicitly listed own-credential runtime guards.

## 3. Outbound calls and registration (shared runtime)

- [x] 3.1 Write the pod-local run record at admission and drop the person's token
      from the execution context when the flag is on; verify record attribution
      and context stripping. Replacing the admission binding's person bearer and
      proving all outbound requests use workload credentials remain in 3.6.
- [x] 3.2 Compose the outbound credentials in the provider — the workload bearer plus
      the grant parameters read only from the run record; verify tests that every
      receiver call carries both, that a tool argument naming a user does not
      change the parameters, and that a run without a record gets no parameters.
- [x] 3.3 Name each child's or team member's own agent identifier with the shared
      run; verify a fan-out test with three members and cancellation of all on run
      cancel.
- [x] 3.4 Apply the MCP activation rule under the flag — `delegated` gets bearer plus
      the grant outside tool arguments, `user_token` is refused with
      `delegation_unavailable`, `no_token` is unchanged; verify tests for all
      three through actual tool invocation as well as connection setup, including
      a mixed server configuration. No-token servers receive no workload bearer.
- [x] 3.5 Fail closed: the flag on with a missing allow-list or workload client
      configuration fails admission with a clear error and forwards no bearer;
      verify test.
- [x] 3.8 Refuse to start with the flag on while user authentication is disabled,
      and keep the disabled mode unchanged with the flag off; verify tests for
      both.
- [x] 3.6 After 4.2, register the admitted record through runtime binding with the
      runtime's workload token only; replace the admission test that expects the
      person's bearer on binding and verify every outbound path under the flag.
      Verify registration failure prevents execution,
      no person token is sent, the reporting client comes from the bearer, and the
      recorded end matches the terminal event even after the person loses standing.
      Verify the terminal report is the only outbound operation after a stop and
      a purged-record 404 is not retried or used to recreate the record.
- [x] 3.7 Verify receiver acceptance across actual token expiry using a controlled
      clock, and a permitted transport retry carrying the parameters and a current
      bearer. Use the signed-token REST/MCP receiver tests and the actual
      transient-retry adapter test as local integration evidence.

## 4. Receivers

- [x] 4.1 Knowledge Flow: acceptance active through the shared dependency for REST
      and the MCP mount, caller/person request context and identifier-free log events; verify an
      integration test that a protected route and an MCP tool call succeed with
      bearer plus parameters after the person's token has expired, and that the
      dependency reads no request body on the mount, whose own request object
      does not share the framework's body cache.
- [x] 4.2 Control plane: accept lifecycle reports with a verified allow-listed
      workload bearer and record-derived parameters, authorize the team for the
      asserted person and derive the reporting client from the bearer. Restrict
      run-end updates to that reporting client and an existing run's terminal
      outcome, independently of the person's continued standing; verify rejection
      of invalid/untrusted tokens, denied admission and another client's updates,
      plus registration without any person token and no receiver registry lookup.
      Verify a late end report returns 404 after account deletion and cannot
      recreate a purged record.
- [x] 4.3 Switch the Knowledge Flow-hosted MCP catalog entries to `delegated`;
      verify configuration validation.
- [x] 4.4 Scrub the grant parameter names from access-log query strings; verify a
      test on the log format.
- [ ] 4.5 Prove that the workload token is accepted as-is, with the hardened
      profile on, by a Knowledge Flow route, an MCP mount and the control plane's
      binding endpoint, against the realm the deployment tooling provisions;
      verify the integration test fails when the service role is removed from the
      calling client.

## 5. Deployment tooling (separate repository) and rollout

This is the final integration phase, after local implementation, generated clients,
regression tests and review findings across all three changes are complete.
External repository work does not block implementation or isolated tests locally.

- [ ] 5.1 Allow-list values per receiver: the agent backend's client, and each
      installed application's client; verify a clean install produces matching
      lists on every receiver.
- [ ] 5.2 Ingress rule rejecting external requests that carry the grant parameters;
      verify a request carrying them from outside is refused.
- [ ] 5.5 Realm provisioning for every calling client — the agent backend, each
      installed application, the evaluation worker: a confidential client with a
      service account, the service role on the shared client, the secret handed
      to its pod; verify a token from each client carries the shared audience and
      its own client id and bound service-account subject. Disable unneeded user,
      password and exchange flows on workload clients; verify user-flow requests
      cannot obtain delegation-capable tokens and only required privileges remain.
- [ ] 5.6 Document the workload secret rotation procedure — rotated-secret grace,
      change the stored secret, roll the pods, end the grace — in the operations
      guidance; verify by a rotation drill in one environment.
      In repository: the runbook exists in the operations guidance and is listed
      in its index, carrying the four ordered steps, why a restart is required
      (the secret is captured at startup), that in-flight turns finish on the
      token they hold, and that re-reading the secret on a failed fetch is
      deliberately not implemented. The refresh cooldown it names now reaches
      every client that is built, so a configured value governs the workload it
      is set for. Outstanding: the rotation drill, which needs an environment.
- [ ] 5.3 Enable the flag in one environment and run the gate: expired-token
      success, acceptance matrix, canaries, configured agent ceiling and 1.9's
      concurrent-failure/recovery case. Before any shared-environment enablement,
      require the single-subject model migration, standing lifecycle, whitelist
      checks and shortcut removal, plus the worker change wherever evaluations run;
      run section 7's delegation security tests before shared deployment and record
      the result for each enabled deployment.
- [x] 5.4 Run focused tests, `make code-quality`, `make test`, and the hot-path
      performance review.

## 6. Integration ownership

- [x] 6.1 Assign one owner for shared parameter/registration contracts and generated
      clients (2.5, 4.2) before receiver work; list disjoint source write sets for
      runtime and each receiver, and serialize shared files and task-state updates.
      Verify each receiver integrates against the same settled contract before
      running 4.5. The single-subject and background changes consume this contract
      in that order; they do not independently redefine it.
      The next change depends on the foundation's shared and receiver interfaces,
      not on completion of its shared-environment rollout; verify the two rollout
      gates together after those dependent interfaces are implemented.

## 7. Delegation security tests

- [ ] 7.1 Verify token validation and service-account binding from 2.6 against
      provisioned tokens and each REST/MCP receiver, covering intended recipients,
      token claims and the separate caller/subject decision. Retain sanitized
      positive and negative test results.
- [x] 7.2 Verify 2.7 across REST, MCP, registration and terminal reporting:
      trusted-workload acceptance, another person's resource, another team,
      protected fields, denied administrative actions, model-supplied identity
      overrides, retained own-credential guards and reporting workload ownership.
- [ ] 7.3 Verify delegation workload configuration: approved destinations only,
      individual workload identities, least privilege, restricted secret access
      and rotation. Test
      removing a compromised caller from receiver policies as well as stopping
      token issuance; measure propagation and remaining bearer validity separately.
- [ ] 7.4 Verify transport protection on delegation's receiver, token, JWKS and
      authorization connections, including failed certificate validation and no
      insecure fallback. Deployment tooling owns this work.
- [ ] 7.5 Independently review the delegation changes and results from 7.1–7.4
      and 7.6; include the standing and background negative-path tests before
      shared enablement. Record remaining implementation failures.
- [x] 7.6 Remove delegation identifiers from application and security log events,
      including structured fields and indirect error logging; retain bounded event,
      outcome and reason fields. Verify every emitted field with synthetic canaries.
      Keep attribution in required product records separate from log output.

## 8. Admission and receiver regression coverage

- [x] 8.1 Register OpenAI-compatible execution through the admitted workload
      provider before execution, propagate the effective ceiling and original
      admission deadline, and await bounded cleanup on admission failure. Verify
      the real resolver, exactly one registration and no execution after failure.
- [x] 8.2 Confine Knowledge Flow request logging before authentication whenever
      delegation is enabled, including body grants, malformed input, failures and
      redirects. Verify canaries never reach log fields at any level and preserve
      feature-disabled diagnostics.
- [x] 8.3 Make the fresh standing check and central registration atomic with
      account deletion, including personal-team admissions; verify neither a
      paused nor a later admission recreates a purged record.
- [x] 8.4 Return 404 when a concurrent purge removes a run before its terminal
      write; verify no recreation, retry or false success.
- [x] 8.5 Align the runtime contract and ceiling documentation with the actual
      admission path, regenerate runtime/control-plane/knowledge-flow configuration
      and chart schemas from source, review the combined changes and run affected regression
      suites plus root code quality before closing local verification.

## 9. Workload identity and person authorization

- [x] 9.1 Apply verified token and exact workload identity checks to shared
      grant acceptance, with whitelist, standing and person authorization.
- [x] 9.2 Update REST/MCP and caller-only integrations to the identity-only helper;
      preserve trusted MCP grant propagation and existing reporting/publication
      workload ownership checks. Keep every listed own-credential guard unchanged.
- [x] 9.3 Align configuration, fixtures and generated configuration/chart schemas
      with client/subject bindings and reject unknown configuration fields.
- [x] 9.4 Verify retained guards through real runtime routes and verify
      delegated endpoints still deny unauthorized persons and workloads.
- [x] 9.5 Independently review the combined changes, run affected complete suites,
      root code quality and strict OpenSpec validation, then record current evidence.

## 10. Local deployment preparation

- [x] 10.1 Build uniquely tagged application images from the current local source,
      including all runtime and capability migrations, and import them into the
      existing local cluster.
- [x] 10.2 Render and review the application update against the live configuration;
      preserve existing storage, identities, integrations and local model settings.
      Keep delegation disabled until workload identities and receiver bindings are
      provisioned in the next integration step.
- [x] 10.3 Apply required database migrations and update the application workloads;
      verify image provenance, schema heads and readiness without recreating the
      cluster or persistent storage.
- [x] 10.4 Verify authenticated application access, searchable KPI data and Usage
      and Activity pages; record deployment evidence and remaining activation gates.
- [x] 10.5 Document the ordered deployment runbook: live-state inventory,
      dependency preflight, database backup, immutable image provenance, reviewed
      rendering, migration-backed Helm upgrade, preservation and browser gates,
      followed by the separately gated delegation activation and recovery path.

## Local verification

Implementation and independent review cover the caller/subject boundary, all
outbound credential adapters, workload-only admission/completion, account standing,
REST/MCP acceptance, foreground reconnect and durable background execution.

The data-preserving local deployment completed through the deployment factory as
Helm revision 14. All migration jobs reached their expected heads; all six updated
Fred workloads are ready on immutable locally built images present on both cluster
nodes. Existing nonempty table row counts, persistent volume claims, foundation
deployments, application secrets and Review Board deployment identities were
preserved. Review Board API and UI are ready and its disabled agent runtime remains
scaled to zero. Delegation remains disabled pending identity
provisioning and receiver-binding verification. Authenticated browser verification
confirmed that Activity loads persisted tasks, Usage renders KPI charts and valid
empty states, and the embedded Review Board connects through Fred with team context
and loads its searchable persisted review summary.

- `fred_core/tests/security/` verifies token validity, exact client/subject
  binding, UID whitelist, standing enforcement, pagination and bounded refresh failure.
- Runtime `test_run_registration.py`, `test_delegation_receiver_integration.py`
  and `test_outbound_credential_paths.py` verify real request construction,
  signed-token expiry, renewable workload credentials and permitted transport retry.
- Receiver `tests/security/test_delegated_receiver.py` exercises signed JWTs on
  actual REST and MCP mounts, including expired user/workload tokens and forged
  tool arguments. Lifecycle route tests cover reporter mismatch, refusal and purge.
- Foreground route/manager tests exercise real admission, model success/failure,
  sequenced replay, owner checks, revocation, grace, single attachment and cleanup.
- Background tests exercise task admission, occurrence idempotency and concurrency,
  current permission checks, per-job limits, sessionless context and cancellation
  from the task API through activity and child cleanup.
- Synthetic canaries cover application, audit, access and Temporal SDK log records.
  Feature-disabled behavior retains existing diagnostics. Product attribution stays
  in protected records; this does not add a credential-checking control-plane call.
- Generated runtime, control-plane and knowledge-flow clients were regenerated
  from source. New SQL migrations applied to an isolated database with one head.
- Regression coverage includes task dispatch naming, occurrence concurrency,
  task cleanup, schedule deletion, revocation during admission, final-frame
  attachment races and SDK logging.
  Replay-buffer CPU cost under load and routing affinity remain deployment tests.

Current affected-suite verification:

| Suite | Passed | Other outcomes |
| --- | ---: | --- |
| Shared security/core | 837 | 32 integration tests deselected |
| Runtime | 1,478 | 16 integration tests deselected |
| Control plane | 1,318 | 8 integration tests deselected |
| Knowledge-flow receiver | 1,213 | 27 integration tests deselected |
| Agent application | 76 | Complete suite |

The focused shared-authentication tests also pass after the final generic
configuration-validation test cleanup: 64 passed. Real runtime route tests verify
all 11 listed own-credential endpoints and the reconnect branch. The two runtime
production files containing these guards are unchanged.

Additional completed verification for unchanged components: SDK 450 passed and
3 skipped; frontend application 2,430 passed and 9 skipped, plus 9 proxy smoke
checks; capability packages 281 passed; frontend packages 376 passed. These
components were not rerun for this scoped change.

The admission and receiver regressions verify the real compatible-API resolver,
exactly-once registration, effective deadlines, bounded nested cleanup, early
request-log confinement, personal-team standing and concurrent terminal purge.
Task-store regressions verify cancellation across dispatch and stale ORM reads,
transaction rollback and duplicate insertion without aborting the caller's
transaction. The single-subject change records the account-deletion ordering
checks.

Tests use an isolated source copy, existing dependencies, an empty environment file
and Node 22.13.0 with local offline consumer caches. Python integration tests are
excluded. The frontend package results combine the normal run with a targeted
rerun of the 14 tests requiring loopback mock listeners. Library deprecation,
SQLite teardown and blocked-socket warnings remain in the suite output; all test
assertions pass. These results do not establish live platform integration.

Root `make code-quality` passes across every module, including Python lint,
formatting, security scanners and type checks, and frontend type, formatting and
lint checks. An additional offline secret scan passes for all 16 Python files changed in this
scope, including untracked files. Strict validation passes for all three changes;
configuration and chart schemas are regenerated from source and chart values
validate. Receiver clients regenerated from source match the existing interfaces,
with only comment whitespace variation; explicit API operation IDs are preserved.
Independent review and the hot-path performance review are complete.
Provisioned identity, transport and full-system evidence remain separate from
these local tests.

## Unimplemented external gaps

Address these last, immediately before full end-to-end verification. Complete both
integrations, run the complete system tests and fix their findings before rollout.

- Deployment tooling: section 5 and deployment-owned evidence in section 7 remain
  unimplemented. Identity provisioning, transport, ingress, rotation and shared
  rollout require separate follow-up; local mocks do not close these tasks.
- Evaluation worker: creator grant propagation and campaign integration remain
  unimplemented in the single-subject change. Environments running evaluations
  must retain the rollout gate until those tasks are verified.
