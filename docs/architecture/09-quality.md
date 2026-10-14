# 9. Quality

## fred-manager tests

| Command (in `apps/fred-manager`) | Runs |
| --- | --- |
| `make test` | Unit tests, offline: domain rules, token verification, logging format, request middleware |
| `make test-integration` | Integration tests against throwaway Postgres/OpenFGA containers and one disposable Keycloak container, removed afterwards; each test gets its own database and store |
| `make code-quality` | DSL/JSON model parity, clippy with warnings as errors, rustfmt |

The authorization matrix exercises all 16 space-role subsets and 32 platform-role
subsets against every typed capability, with cross-space and content isolation checks.
A controlled Keycloak HTTP fixture checks directory failures, service-token refresh,
identity mapping and authenticated governance routes.

Authorization-after-revocation tests hold the relevant advisory lock to force the
interleaving they prove. Last-admin tests issue simultaneous revocations and assert
that at most one succeeds.

## OpenFGA request costs

Direct roles live in OpenFGA. The client uses `Check`, paginated `Read` and `Write`;
it does not issue `ListObjects`, `ListUsers`, `Expand` or `BatchCheck`.
`Check` and `Read` request `HIGHER_CONSISTENCY`. A content check addresses one
user, permission and space; the model combines direct roles without traversing
parents. A fixed number of HTTP calls does not specify OpenFGA's datastore work,
latency or throughput.

The following source-derived successful-path counts exclude startup, authentication, SQL and
Keycloak calls. `C` is one Check; `W(n)` is one Write with `n` total inserts and deletes.
`R_g` is one guard Read filtered by exact object and relation `version`.
`P_u`, `P_p` and `P_a(s)` are the actual Read page counts for a user's direct space
roles, all platform grants, and the admins of space `s`. Each includes at least
one request, even for an empty result. The client does not specify `page_size`.

| Operation | OpenFGA calls | Read filter or decision scope |
| --- | --- | --- |
| Content access; authorize document/scope/space/platform | `1 C` | Exact user, permission, object |
| `GET /me` | `5 C`, concurrent | Caller's five effective platform roles |
| `GET /me/spaces` | `P_u Read` | Caller + object type `space:` across organizations |
| Team registry page | `1 C` | Platform registry permission; SQL returns at most 100 teams |
| List platform grants | `1 C + P_p Read` | Admin check, then all subjects/roles on `platform:root` |
| Grant platform role | `1 R_g + 1 C + W(3)` | Actor admin; separate Keycloak subject lookup |
| Revoke platform role | `1 R_g + 1 C + P_p Read + W(3)` | All platform grants are read to locate one direct grant |
| Grant organization role | `1 R_g + 1 C + W(3)` | Actor manages organization |
| Grant team/project role | `1 R_g + 2 C + W(3)` | Actor manages space; target reads parent |
| Revoke space role | `1 R_g + 1 C + P_u Read + W(2 + d)` | Target's direct roles across all spaces |
| Revoke a held admin role on a non-personal space | Previous row + `P_a(s) Read` | All direct admins of that space |
| Create team using local authority | `2 R_g + 2 C + W(5)` | Actor manages parent; nominated admin reads parent |
| Create project | `1 R_g + 2 C + W(3)` | Actor manages parent; nominated admin reads parent |
| Create team using platform delegation | `2 R_g + 3 C + W(5)` | Adds platform creation permission |
| Create personal space | `1 R_g + 1 C + W(4)` | Caller reads organization; member/editor grants |
| Operator create organization | `W(2) + 1 R_g + W(4)` | Initialize guard, then initial admin/member grants |
| Root bootstrap | `1 R_g + W(3)` | Bearer/secret and SQL marker govern admission |

`d` is 1 when the revoked role exists, otherwise 0. A successful absent space-role
revocation still advances its guard. A platform-role revoke returns 404 when absent.
SQL folder/document mutations and Temporal dispatch use `1 R_g + 1 C + W(2)`;
the fence contains no role change. Each successful guard replacement adds two
operations per scope, independent of the number of existing roles.

Sources: [client](../../apps/fred-manager/src/fga.rs),
[space mutations](../../apps/fred-manager/src/spaces.rs),
[platform mutations](../../apps/fred-manager/src/platform.rs), and
[HTTP handlers](../../apps/fred-manager/src/api.rs).

For the JSON importer, let `U` be input users, `N_o` organization tuples, `N_t`
tuples for team `t`, `G` normalized platform grants, `N` be 1 for a new organization
and 0 otherwise, and `B = ceil(N_o / 96) + sum_t ceil(N_t / 96)`. `N_o` counts one
admin tuple per distinct organization admin and one member tuple per user who is
an organization admin or has a team role. `Importer::run` performs:

- `U + 3 + B + G` Checks;
- `U + 2` exact guard Reads;
- `U + N + B + G` Writes: one guard-only identity-dispatch fence per user, optional
  organization guard initialization, then guarded space batches and platform grants.

Space batches contain at most 96 role inserts plus four guard operations. Platform
grants inside reconciliation contain five operations. Calls are sequential. The CLI
adds one admin Check and two GETs (configured-store discovery and pinned-model
verification), for `3U + 8 + N + 2B + 2G` total OpenFGA requests on this path.
The [importer](../../apps/fred-manager/src/provisioning.rs) and
[CLI](../../apps/fred-manager/src/main.rs) define these counts.

The integration fixture with 105 users, 106 organization grants, 210 team grants,
no platform grants and one new organization checks 113 Checks, 107 Reads and 111
Writes: 548 total tuple operations, at most 100 in any Write. These are wire counts
for one import, not latency or throughput measurements.

For offline cutover, `K` is source tuples, `P_K` their Read pages, `O` organizations
and `H` distinct parent/subject pairs. Including discovery, the successful path uses
`1 GET + P_K Reads + (K > 0 ? 1 GET : 0) + 2 POSTs + ceil(K / 100) Writes + H Checks
+ (O + 1) Writes`. The GETs discover the configured source and verify its legacy
model; POSTs create the destination and model. Copy and guard initialization total
`K + 2(O + 1)` tuple operations. SQL publication adds no FGA request.

Cutover holds `O(K + S + H)` application memory for `S` SQL spaces and uses ordered
indexes for hierarchy, administrators and distinct parent checks; local processing
is `O((K + S) log(S + 1) + K log(H + 1))`, apart from model normalization. It is an
offline operation. Existing-binding startup uses discovery GET plus pinned-model
GET, without recopying roles. Failed unpublished attempts are never reused.

Read pagination bounds each response, not the operation's memory: `read_keys`
accumulates all matching tuples. With `R` role tuples and `S` returned spaces,
`/me/spaces` uses `O(R + S)` application memory and
`O(R log R + S * R)` processing for sorting and per-space role selection.
Space revocation tests child membership in `O(R * D)` worst-case application
work for `D` immediate children. These costs concern Fred's processing of returned
tuples, not OpenFGA's internal query plan.

Organization-scoped role/space/content mutations retain a SQL connection and advisory lock across remote
calls. Platform changes and import also use the platform lock; team creation
takes it even with local authority. HTTP server waiters acquire a connection before
waiting for that lock, sharing its ten-connection pool with other SQL work. CLI
import uses a separate two-connection pool.
The configured default FGA timeout is five seconds per request, not per complete
paginated operation. Document count does not multiply role tuples in this model:
content authorization is scoped to the owning space.

## Invariants and their proofs

Generated from the `// Proves:` markers.

<!-- generated: invariants -->
| Invariant | Proved by |
| --- | --- |
| I1 | `apps/fred-manager/src/domain.rs::parent_rules`<br>`apps/fred-manager/tests/integration.rs::cutover_rejects_changed_permissions_and_inconsistent_hierarchy` |
| I2 | `apps/fred-manager/tests/integration.rs::placement_is_immutable_and_folders_stay_in_their_space` |
| I3 | `apps/fred-manager/tests/integration.rs::placement_is_immutable_and_folders_stay_in_their_space` |
| I4 | `apps/fred-manager/tests/integration.rs::concurrent_revocations_keep_parent_access`<br>`apps/fred-manager/tests/integration.rs::concurrent_grant_and_revoke_keep_the_invariant`<br>`apps/fred-manager/tests/integration.rs::analyst_membership_is_content_and_personal_roles_remain_fixed`<br>`apps/fred-manager/tests/integration.rs::provisioning_replays_every_role_without_updating_identities_or_implicit_content`<br>`apps/fred-manager/tests/integration.rs::provisioning_repairs_every_fga_boundary_including_ambiguous_acknowledgments`<br>`apps/fred-manager/tests/integration.rs::import_rechecks_parent_after_wait_and_repairs_existing_space_grants`<br>`apps/fred-manager/tests/integration.rs::a_timed_out_child_grant_cannot_arrive_after_parent_revocation`<br>`apps/fred-manager/tests/integration.rs::a_cancelled_child_grant_is_fenced_after_client_restart`<br>`apps/fred-manager/tests/integration.rs::offline_cutover_preserves_roles_and_pins_the_published_store`<br>`apps/fred-manager/tests/integration.rs::cutover_rejects_invalid_source_and_replays_ambiguous_copies`<br>`apps/fred-manager/tests/integration.rs::noop_revocation_and_multiple_scopes_fence_stale_attempts`<br>`apps/fred-manager/tests/integration.rs::cutover_rejects_changed_permissions_and_inconsistent_hierarchy` |
| I5 | `apps/fred-manager/tests/integration.rs::a_revoked_admin_cannot_finish_a_waiting_request`<br>`apps/fred-manager/tests/integration.rs::revoked_platform_actor_cannot_complete_waiting_role_or_team_creation`<br>`apps/fred-manager/tests/integration.rs::simultaneous_imports_reuse_usernames_and_space_names`<br>`apps/fred-manager/tests/integration.rs::provisioning_waiter_rechecks_revoked_or_expired_operator`<br>`apps/fred-manager/tests/integration.rs::preflight_does_not_block_revocation_and_cancelled_identity_creation_replays`<br>`apps/fred-manager/tests/integration.rs::import_rechecks_parent_after_wait_and_repairs_existing_space_grants`<br>`apps/fred-manager/tests/integration.rs::a_timed_out_platform_grant_cannot_arrive_after_actor_revocation`<br>`apps/fred-manager/tests/integration.rs::noop_revocation_and_multiple_scopes_fence_stale_attempts`<br>`apps/fred-manager/tests/integration.rs::sql_mutation_loses_to_a_delayed_revocation_after_its_check`<br>`apps/fred-manager/tests/integration.rs::folder_creation_keeps_one_connection_through_placement_and_write` |
| I6 | `apps/fred-manager/tests/integration.rs::a_member_with_a_personal_space_can_leave_the_organization`<br>`apps/fred-manager/tests/integration.rs::analyst_membership_is_content_and_personal_roles_remain_fixed` |
| I7 | `apps/fred-manager/src/domain.rs::search_scope_is_ancestors_then_self` |
| I8 | `apps/fred-manager/tests/integration.rs::admin_roles_grant_no_content_access`<br>`apps/fred-manager/tests/integration.rs::complete_role_permission_matrix_and_space_isolation`<br>`apps/fred-manager/tests/integration.rs::delegated_creation_is_team_only_and_never_grants_caller_membership`<br>`apps/fred-manager/tests/integration.rs::provisioning_replays_every_role_without_updating_identities_or_implicit_content`<br>`apps/fred-manager/tests/integration.rs::offline_cutover_preserves_roles_and_pins_the_published_store`<br>`apps/fred-manager/tests/integration.rs::cutover_rejects_changed_permissions_and_inconsistent_hierarchy` |
| I9 | `apps/fred-manager/tests/integration.rs::bootstrap_promotes_one_person_once`<br>`apps/fred-manager/tests/integration.rs::a_finished_bootstrap_stays_closed_after_its_admin_is_removed`<br>`apps/fred-manager/tests/integration.rs::concurrent_retries_finish_a_bootstrap_once`<br>`apps/fred-manager/tests/integration.rs::an_interrupted_bootstrap_is_finished_by_its_caller_only`<br>`apps/fred-manager/tests/integration.rs::offline_cutover_preserves_roles_and_pins_the_published_store` |
| I10 | `apps/fred-manager/src/auth.rs::rejects_expired_and_overlong_tokens`<br>`apps/fred-manager/src/auth.rs::lifetime_ceiling_cannot_be_skipped`<br>`apps/fred-manager/src/auth.rs::rejects_missing_kid_and_bad_signature`<br>`apps/fred-manager/src/auth.rs::strict_mode_checks_issuer_and_audience` |
| I11 | `apps/fred-manager/src/keycloak.rs::directory_failures_do_not_echo_credentials_or_payloads`<br>`apps/fred-manager/src/logging.rs::sensitive_and_reserved_fields_never_leak`<br>`apps/fred-manager/src/logging.rs::dependencies_get_a_fixed_message_without_their_fields`<br>`apps/fred-manager/src/provisioning.rs::malformed_declarations_never_echo_payloads`<br>`apps/fred-manager/tests/integration.rs::directory_creation_conflict_pagination_preservation_and_failures` |
| I12 | `apps/fred-manager/tests/integration.rs::pagination_survives_deleting_the_cursor_row` |
| I13 | `apps/fred-manager/src/logging.rs::requests_carry_ids_and_end_with_one_http_event` |
| I14 | `apps/fred-manager/tests/integration.rs::concurrent_admin_revocations_leave_one_admin_at_every_level` |
| I15 | `apps/fred-manager/tests/integration.rs::platform_roles_enforce_root_identity_and_direct_grant_semantics`<br>`apps/fred-manager/tests/integration.rs::provisioning_preflight_failures_have_no_identity_space_or_role_writes` |
| I16 | `apps/fred-manager/src/logging.rs::audit_records_survive_warning_application_threshold`<br>`apps/fred-manager/tests/integration.rs::durable_grants_are_audited_even_when_sql_commit_fails` |
| I17 | `apps/fred-manager/tests/integration.rs::provisioning_replays_every_role_without_updating_identities_or_implicit_content`<br>`apps/fred-manager/tests/integration.rs::directory_creation_conflict_pagination_preservation_and_failures`<br>`apps/fred-manager/tests/integration.rs::provisioning_replay_after_identity_and_sql_failures_reuses_committed_state`<br>`apps/fred-manager/tests/integration.rs::simultaneous_imports_reuse_usernames_and_space_names`<br>`apps/fred-manager/tests/integration.rs::provisioning_batches_large_parent_and_child_grants_and_rejects_personal_collision`<br>`apps/fred-manager/tests/integration.rs::preflight_does_not_block_revocation_and_cancelled_identity_creation_replays`<br>`apps/fred-manager/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/fred-manager/tests/integration.rs::provisioning_repairs_every_fga_boundary_including_ambiguous_acknowledgments`<br>`apps/fred-manager/tests/integration.rs::cancellation_after_fga_write_rolls_back_new_space_and_replays`<br>`apps/fred-manager/tests/integration.rs::import_rechecks_parent_after_wait_and_repairs_existing_space_grants` |
| I18 | `apps/fred-manager/tests/integration.rs::provisioning_preflight_failures_have_no_identity_space_or_role_writes`<br>`apps/fred-manager/tests/integration.rs::provisioning_waiter_rechecks_revoked_or_expired_operator`<br>`apps/fred-manager/tests/integration.rs::import_cli_is_read_only_until_authorized_and_requires_initialized_state`<br>`apps/fred-manager/tests/integration.rs::preflight_does_not_block_revocation_and_cancelled_identity_creation_replays`<br>`apps/fred-manager/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/fred-manager/tests/integration.rs::import_rejects_incompatible_model_without_syncing_it`<br>`apps/fred-manager/tests/integration.rs::offline_cutover_preserves_roles_and_pins_the_published_store`<br>`apps/fred-manager/tests/integration.rs::cutover_rejects_invalid_source_and_replays_ambiguous_copies`<br>`apps/fred-manager/tests/integration.rs::cutover_rejects_changed_permissions_and_inconsistent_hierarchy`<br>`apps/fred-manager/tests/integration.rs::competing_empty_initializers_converge_on_the_published_binding` |
<!-- end generated -->

Provisioning tests inject failures before/after real FGA writes, fail deferred SQL commits,
and cancel after identity creation and FGA acknowledgment. Replay assertions check preserved
committed IDs, fresh IDs after rollback and restored grants. Gates force preflight/revocation
and cancellation interleavings; batch tests exceed the FGA write limit. CLI subprocess tests
verify token/mapping refusals, zero-count setup diagnostics (including after SQL errors),
migration-table absence and unchanged FGA models on failure
and success. The real Keycloak test configures a distinct `fred-manager` client with the
three declared realm-management grants and provisions all assignable roles.
