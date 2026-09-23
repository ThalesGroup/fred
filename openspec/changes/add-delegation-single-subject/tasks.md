## 1. Two principals

- [x] 1.1 Add the caller/subject principal pair to the request context and derive
      the caller from the bearer; verify tests that the service-role predicate is
      false for an asserted person and true for a service caller holding the role,
      without bypassing the subject's permission checks.
- [x] 1.2 Apply the whitelist access control to asserted persons; verify a test
      that a person outside the list is refused whether authenticated or asserted.

## 2. Standing

- [ ] 2.6 Define `organization#suspended` as `[user]` and `organization#active` as
      `[user:*] but not suspended`, keep `organization#standing_ready`, and
      generate the model JSON; publish the model
      and update every reader/writer's selection, including explicit model-ID pins,
      before 2.3 or gate activation. Verify that model validation accepts only this
      shape, that the source and generated JSON stay in sync, and an upgrade from a
      deployment pinned to the old model. Publishing the model to a real store and
      re-pointing deployment pins needs a live environment.
- [x] 2.1 Refactor the engine's check, batch-check and list-lookup into template
      methods with standing enforcement for person subjects, inactive until 2.7;
      preserve typed standing denial through list, batch and filtering helpers and
      REST/MCP authorization responses. Verify tests that a
      person without `active` is denied on a team permission, a direct tag grant,
      a platform role and a public read; a list/search next call must end the run
      and its children with `authority_lost`. Verify unavailable standing denies
      and ordinary empty authorized-resource results remain successful.
- [ ] 2.2 Restrict the standing relations to the lifecycle path: the generic relation
      add and delete operations refuse `active`, `standing_ready` and `suspended` on
      the platform organization, removing all relations of a person keeps a
      `suspended` tuple, and neither authenticated requests, personal-space
      self-heal nor grants write them. Verify each refusal, the retained suspension,
      and that a suspended person's still-valid token or a grant naming them cannot
      lift the suspension or restore delegated access.
- [x] 2.3 Establish standing at control-plane startup with delegation enabled:
      validate the model, write the default standing entry and the ready marker,
      confirm the marker, and refuse to start on any failure, on every start and
      before the other startup reconciliations. Verify a clean start, an idempotent
      restart that keeps suspensions, refusal on an incompatible model, a failed
      write and an unconfirmed marker, no standing writes with delegation disabled,
      and that startup needs no identity administration and runs no background
      standing task.
      Verified by the control-plane startup tests (exact call order, each refusal,
      no call with delegation disabled, lifespan order through the application
      factory, a container exposing only the relationship engine, and
      `test_starts_over_a_stored_ban_keeps_that_person_refused`: two starts over a
      stored suspension keep that person refused and another person in good
      standing), the core library's test that every lifecycle write tolerates an
      already stored tuple, the model shape test
      `test_rebac_schema_authz05::test_organization_standing_is_everyone_except_the_suspended`,
      and the core library's standing tests over a store double that evaluates that
      shape from its stored tuples
      (`test_a_pinned_deployment_recovers_once_the_new_model_is_published`,
      `test_a_person_fred_removed_is_refused_beside_the_everyone_entry`). No
      background standing task: the control-plane entry point creates no task
      (inspection).
- [x] 2.4 Person deletion suspends first: after the permission and root-account
      checks, refuse an id naming no person (`*` or an id containing `#`) as not
      found, then resolve identity administration (unavailable: service
      unavailable, nothing changed); under the run lifecycle lock write the
      suspension when standing is enforced, remove the person's other relations,
      purge admission records, background tasks and schedules; after that
      transaction commits, delete the identity-provider account. Verify the order,
      that the suspension survives relation cleanup, that an identity-provider
      failure leaves the person suspended and a retry completes, that an
      already-missing account completes the cleanup and reports not found, that no
      suspension is written with the control plane's delegation disabled, that an
      id naming no person and the bootstrap root are refused before any change,
      that a failed suspension write stops the deletion before any cleanup, that a
      schedule failure after the suspension rolls back the record and schedule
      purge and keeps the identity-provider account until a retry completes, and
      that a deleted person's in-flight run stops locally with a non-recreating
      late end report.
      Verified over HTTP with real SQLite stores (`test_user_delete_route`) for the
      order, the retained suspension, the identity-provider failure and retry, the
      missing account, the unavailable identity administration and the
      delegation-disabled case; by
      `test_an_id_naming_no_person_is_refused_as_not_found_before_any_change` for
      `*`, `#x` and `team#member`, with standing enforced and not enforced;
      `test_deleting_the_bootstrap_root_is_refused_before_any_change`;
      `test_a_failed_ban_write_stops_the_delete_before_any_cleanup`;
      `test_schedule_failure_after_the_ban_rolls_back_the_purge_and_keeps_the_account`;
      by the core library's reference-cleanup tests for the retained suspension; and
      by the registry and runtime registration tests for the non-recreating late end
      report.
- [ ] 2.5 A suspension applies from the person's next decision and identity-provider
      account changes do not change standing. Verify a delegated run ends with
      `authority_lost` on its next call after a suspension, without a person token
      or a receiver calling the control plane or identity provider; work already
      authorized completes; a person never suspended and a service identity checked
      as a person are in good standing; and no standing path reads identity-provider
      account state.
- [ ] 2.7 After 2.1–2.6, gate activation on compatible model selection and the
      ready marker: each receiver refuses to start, reporting that account standing
      is not ready, until its model validates and the marker exists. The control
      plane activates first because its startup writes the default standing entry
      and the marker. Verify startup refuses an old pin or a missing marker, and an
      existing deployment retains authorized access after a successful migration.
      Verify rollback disables the gate before reverting readers. Activating the
      gate in an environment, proving existing persons retain access after
      migration and exercising rollback need a live environment.
- [x] 2.8 Delegation enforces account standing with no separate setting: the engine
      factory feeds enforcement from delegation and refuses an engine that would
      authorize everyone. Verified by factory tests that fail without the rule and by
      the full suites of the core library, the agent runtime, the control plane and
      the document backend.
- [x] 2.9 A person's relation cleanup reads only that person's relations: one
      higher-consistency read per object type whose model accepts a person
      directly, plus `group`, run together and paged to the end, skipping the
      standing tuples on the organization; any other reference keeps the full
      scan; the wildcard `*`, a userset id and an empty id are refused before any
      read. Verified by the core library's reference-cleanup tests over a client
      double that filters reads as OpenFGA's Read does:
      `test_person_types_derive_from_the_published_schema`,
      `test_person_cleanup_reads_each_person_type_never_the_store`,
      `test_person_cleanup_clears_every_type_and_keeps_the_ban`,
      `test_person_reads_page_through_every_continuation_token`,
      `test_person_type_reads_run_together`,
      `test_every_enumeration_asks_for_higher_consistency`,
      `test_person_cleanup_removes_a_retired_group_membership`,
      `test_person_cleanup_reads_every_type_its_schema_opens_to_a_person`,
      `test_team_cleanup_still_scans_the_whole_store` and
      `test_a_reference_naming_no_single_person_is_refused_before_any_call`.
      `test_person_cleanup_reads_each_person_type_never_the_store` fails with the
      person read reverted to the full scan, and the refusal test fails without the
      engine's refusal. The double's read filter is not checked against a live
      OpenFGA server.

## 3. No shortcuts

- [x] 3.1 Runtime: accept the grant parameters as admission input from an
      allow-listed caller, write the run record from them, register the run and
      call receivers for that person; verify a test that a grant-admitted run
      needs no person token/session, names the worker at admission, and registers
      and calls downstream under the runtime's client with the same person/run.
      Depend on the foundation's registration API and standing enforcement; reject
      admission or registration failure before execution.
- [x] 3.2 With delegation enabled, remove the service-role shortcuts in runtime admission; the control plane's
      team-permission validator and its product and knowledge-base services;
      Knowledge Flow's ingestion, tabular, library-sync and tag services; verify
      that a service bearer without a grant is denied on each former path. Preserve
      feature-disabled behavior and explicit own-workload operations.
- [ ] 3.3 Configure the evaluation worker's exact client/service-account subject
      pair on every receiver and runtime; verify an integration test with the grant
      parameters for a campaign creator passing admission and the control plane's
      prepare step.
      In repository: both integration tests exist. A workload configured through
      caller policies, presenting the grant parameters for a campaign creator and
      no person credential, is admitted at the runtime with the record written from
      the grant; and the same pair reaching the control plane's prepare step is
      authorized on the creator, not on the calling workload. The prepare routes
      now declare the grant parameters as optional, so the worker-facing contract
      is visible in the generated client. Outstanding: the worker's real client and
      service-account values on every receiver, which is deployment configuration.

## 4. Verification

- [ ] 4.1 Evaluation campaign end to end on grants with the creator retained in
      product records/request context, the worker retained at admission and the
      runtime identified at registration/downstream boundaries; verify identifier-free
      log output and include a creator with no active session.
      In repository: the identity chain is covered deterministically. A run admitted
      from a grant keeps the calling workload as its origin through admission, the
      registration body and the persisted record, while the person stays the creator
      and the reporting identity stays the runtime. The sessionless case is the one
      exercised, and the admission audit line is asserted to carry none of the
      person, caller, run, team, agent or bearer. The two halves meet on the managed
      registration shape because the runtime and the control plane are separate
      projects with isolated environments. Outstanding: the campaign itself, which
      needs the evaluation worker to send the creator's grant.
- [ ] 4.2 Run focused tests, `make code-quality`, `make test`, and the hot-path
      performance review.
- [ ] 4.3 Add synthetic-data regression tests for
      list/batch denial, old-token attempts to lift a suspension, cross-team access,
      privileged operations and model migration; verify fail-closed startup, the
      deletion order and suspension retention with deterministic tests. Measure
      how soon a suspension reaches a shared environment's receivers during final
      deployment verification. Apply the foundation's delegation logging policy.

## 5. Integration ownership

- [x] 5.1 Assign one owner for the principal/standing interface and model sources
      including generated JSON; settle these before parallel receiver changes.
      Serialize model publication, selection, standing initialisation and
      activation. Verify the runtime, control plane and Knowledge Flow consume the
      same denial contract; keep shared files, generated clients and task-state
      writes under one owner.

## 6. Admission and deletion regression coverage

- [x] 6.1 Require explicit standing for new managed/direct run registrations,
      background starts, schedule creation and occurrences, including personal
      teams; verify revoked persons cannot persist new product records.
- [x] 6.2 Make fresh standing checks and admission writes atomic relative to
      deletion without nested lifecycle-lock connections; verify both race orders
      and no recreation after purge.
- [ ] 6.3 Review combined regression evidence with the foundation and background
      changes before closing local acceptance.

## Local verification

Caller/person separation, UID whitelist, standing enforcement on each decision,
delegated runtime admission and service-role shortcut removal are implemented.
Core security tests and receiver tests cover these paths. Factory tests prove that
enabling delegation enforces standing and that an engine which would authorize
everyone is refused when built. Tasks 2.6 and 2.7 retain the external model
publication, upgrade and rollback checks. Tasks 3.3 and 4.1 retain real
evaluation integration. Cross-component test evidence is recorded in the
foundation change's `tasks.md`.

Standing lifecycle evidence (offline, synthetic data):

- `cd libs/fred-core && PYTHONPATH=../fred-pod .venv/bin/python -m pytest fred_core/tests/security -q`:
  392 passed. Without `integration`
  (`... -m pytest fred_core/tests -q --ignore=fred_core/tests/integration`): 890 passed.
- `cd apps/control-plane-backend && .venv/bin/python -m pytest tests/test_user_delete_route.py tests/test_account_standing_startup.py tests/test_main_org_reconcile.py tests/test_main.py tests/test_agent_run_registry.py tests/test_agent_run_task_routes.py tests/test_authz_endpoint_matrix.py tests/test_capability_enablement_1980.py tests/test_capability_selection_1974.py tests/test_default_team_for_new_users.py tests/test_get_users_by_ids_bulk.py tests/test_get_users_by_ids_cache.py tests/test_import_export_task_observability.py tests/test_import_export_users.py tests/test_platform_model_binding.py tests/test_prepare_execution_model_override.py tests/test_team_registry_governance.py tests/test_team_wiki_conflict_contract.py -q`:
  545 passed; `... tests/test_capability_impact.py tests/test_capability_suspension_1975.py -q`
  (both import `test_main`): 34 passed.
- `cd apps/knowledge-flow-backend && .venv/bin/python -m pytest tests/security/test_delegation_startup.py -q`:
  3 passed.
- `cd libs/fred-runtime && .venv/bin/python -m pytest tests/test_agent_app.py tests/test_delegated_foreground_route.py tests/test_foreground_reconnect_routes.py -q`:
  133 passed; `... tests/test_run_registration.py tests/test_background_agent_run.py tests/test_background_runtime.py -q`:
  35 passed.
- `make -C apps/control-plane-backend check-config-schema-drift`: passed;
  `make check-chart-schema-drift`: passed.
- `fga model transform --file libs/fred-core/fred_core/security/rebac/schema.fga`
  is byte-identical to `schema.fga.json`.
- Standing semantics, in the repository:
  `test_rebac_schema_authz05::test_organization_standing_is_everyone_except_the_suspended`
  pins the shipped shape, `active: [user:*] but not suspended`. The core library's
  standing tests evaluate that shape over the tuples a store double holds: without
  the default entry nobody is in good standing, once it exists a person with no
  tuple keeps access
  (`test_a_pinned_deployment_recovers_once_the_new_model_is_published`), and a
  suspended person is refused beside it while another person passes
  (`test_a_person_fred_removed_is_refused_beside_the_everyone_entry`). The
  control plane's `test_starts_over_a_stored_ban_keeps_that_person_refused` keeps a
  stored suspension across two starts. An offline `fga model test` run against
  `schema.fga` is supplementary local evidence only; its cases are not in the
  repository.
- `ruff check` and `ruff format --check` on every changed Python file: clean.
- Each regression test below was seen to fail with its behaviour reverted and to
  pass once restored: the suspension written before relation cleanup and before
  the identity-provider deletion; that deletion after the lifecycle transaction
  commits; identity administration resolved before any change; no suspension
  without enforcement; the deletion sharing the admission lock (both race orders);
  startup order, the skip without enforcement, model validation, the default entry,
  the marker after it and its read-back; the suspension kept by reference cleanup;
  the default entry written for `user:*`; the suspension written as `suspended`;
  lifecycle writes tolerating a stored tuple; each model-validation rejection; the
  generic write and delete refusal, with whole batches checked first; the receiver
  refusal message in the core library, Knowledge Flow and the agent runtime; the
  targeted person read, reverted to the full scan; the engine's refusal of a
  reference naming no single person; the delete route's refusal of an id naming no
  person with standing not enforced.

Checks still to run for the standing lifecycle:

- 2.2: a suspended person's still-valid token, including a personal-space read,
  or a grant naming them cannot lift the suspension.
- 2.5: a delegated run ending with `authority_lost` at its next call after a
  suspension, a call already authorized completing, and no standing path reading
  identity-provider account state.
- Admission/deletion ordering for personal teams against the deletion order.
- Model publication, pin re-pointing, activation and rollback (2.6, 2.7).
- `make code-quality`, `make test` and the hot-path performance review (4.2).

## Unimplemented external gaps

Schedule these after local implementation and regression verification across all
three changes, immediately before full end-to-end tests. They do not block local
runtime admission, standing or receiver work with isolated dependencies.

- Evaluation worker: creator grant propagation, client configuration and the real
  campaign path in 3.3/4.1 remain unimplemented pending separate repository work.
  Local runtime support and mock tests do not close this gap.
- Deployment tooling: model publication/selection, including the deployment
  tooling's own copy of the authorization model JSON, identity configuration and
  shared-environment verification remain pending. Keep the gate disabled wherever
  these prerequisites or the evaluation integration are incomplete.
