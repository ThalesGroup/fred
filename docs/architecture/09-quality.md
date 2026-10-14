# 9. Quality

## fred-manager tests

| Command (in `apps/fred-manager`) | Runs |
| --- | --- |
| `make test` | Unit tests, offline: domain rules, token verification, logging format, request middleware |
| `make test-integration` | Integration tests against throwaway Postgres and OpenFGA containers, removed afterwards; each test gets its own database and store |
| `make code-quality` | DSL/JSON model parity, clippy with warnings as errors, rustfmt |

The authorization matrix exercises all 16 space-role subsets and 32 platform-role
subsets against every typed capability, with cross-space and content isolation checks.
A controlled Keycloak HTTP fixture checks directory failures, service-token refresh,
identity mapping and authenticated governance routes.

Authorization-after-revocation tests hold the relevant advisory lock to force the
interleaving they prove. Last-admin tests issue simultaneous revocations and assert
that at most one succeeds.

## Invariants and their proofs

Generated from the `// Proves:` markers.

<!-- generated: invariants -->
| Invariant | Proved by |
| --- | --- |
| I1 | `apps/fred-manager/src/domain.rs::parent_rules` |
| I2 | `apps/fred-manager/tests/integration.rs::placement_is_immutable_and_folders_stay_in_their_space` |
| I3 | `apps/fred-manager/tests/integration.rs::placement_is_immutable_and_folders_stay_in_their_space` |
| I4 | `apps/fred-manager/tests/integration.rs::concurrent_revocations_keep_parent_access`<br>`apps/fred-manager/tests/integration.rs::concurrent_grant_and_revoke_keep_the_invariant`<br>`apps/fred-manager/tests/integration.rs::analyst_membership_is_content_and_personal_roles_remain_fixed` |
| I5 | `apps/fred-manager/tests/integration.rs::a_revoked_admin_cannot_finish_a_waiting_request`<br>`apps/fred-manager/tests/integration.rs::revoked_platform_actor_cannot_complete_waiting_role_or_team_creation` |
| I6 | `apps/fred-manager/tests/integration.rs::a_member_with_a_personal_space_can_leave_the_organization`<br>`apps/fred-manager/tests/integration.rs::analyst_membership_is_content_and_personal_roles_remain_fixed` |
| I7 | `apps/fred-manager/src/domain.rs::search_scope_is_ancestors_then_self` |
| I8 | `apps/fred-manager/tests/integration.rs::admin_roles_grant_no_content_access`<br>`apps/fred-manager/tests/integration.rs::complete_role_permission_matrix_and_space_isolation`<br>`apps/fred-manager/tests/integration.rs::delegated_creation_is_team_only_and_never_grants_caller_membership` |
| I9 | `apps/fred-manager/tests/integration.rs::bootstrap_promotes_one_person_once`<br>`apps/fred-manager/tests/integration.rs::a_finished_bootstrap_stays_closed_after_its_admin_is_removed`<br>`apps/fred-manager/tests/integration.rs::concurrent_retries_finish_a_bootstrap_once`<br>`apps/fred-manager/tests/integration.rs::an_interrupted_bootstrap_is_finished_by_its_caller_only` |
| I10 | `apps/fred-manager/src/auth.rs::rejects_expired_and_overlong_tokens`<br>`apps/fred-manager/src/auth.rs::lifetime_ceiling_cannot_be_skipped`<br>`apps/fred-manager/src/auth.rs::rejects_missing_kid_and_bad_signature`<br>`apps/fred-manager/src/auth.rs::strict_mode_checks_issuer_and_audience` |
| I11 | `apps/fred-manager/src/keycloak.rs::directory_failures_do_not_echo_credentials_or_payloads`<br>`apps/fred-manager/src/logging.rs::sensitive_and_reserved_fields_never_leak`<br>`apps/fred-manager/src/logging.rs::dependencies_get_a_fixed_message_without_their_fields` |
| I12 | `apps/fred-manager/tests/integration.rs::pagination_survives_deleting_the_cursor_row` |
| I13 | `apps/fred-manager/src/logging.rs::requests_carry_ids_and_end_with_one_http_event` |
| I14 | `apps/fred-manager/tests/integration.rs::concurrent_admin_revocations_leave_one_admin_at_every_level` |
| I15 | `apps/fred-manager/tests/integration.rs::platform_roles_enforce_root_identity_and_direct_grant_semantics` |
| I16 | `apps/fred-manager/src/logging.rs::audit_records_survive_warning_application_threshold`<br>`apps/fred-manager/tests/integration.rs::durable_grants_are_audited_even_when_sql_commit_fails` |
<!-- end generated -->
