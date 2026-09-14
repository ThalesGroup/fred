# Application ReBAC verification map

This map covers the dedicated app resource and configuration-based registration.
Offline suites pass; live integration and deployment readiness remain unverified.
Execution details, coverage limits and future gaps are recorded below.

## Test file key

Each reference names a function in its linked file. Integration test definitions
do not establish live execution.

| Key | Local test file |
| --- | --- |
| A | [test_application_authz.py](../../../libs/fred-core/fred_core/tests/security/test_application_authz.py) |
| S | [test_rebac_sdk.py](../../../libs/fred-core/fred_core/tests/security/test_rebac_sdk.py) |
| P | [test_applications.py](../../../apps/control-plane-backend/tests/test_applications.py) |
| C | [test_capability_relations_cache_2181.py](../../../apps/control-plane-backend/tests/test_capability_relations_cache_2181.py) |
| B | [test_capability_enablement_1980.py](../../../apps/control-plane-backend/tests/test_capability_enablement_1980.py) |
| Q | [test_enablement_relations_cache_race.py](../../../apps/control-plane-backend/tests/test_enablement_relations_cache_race.py) |
| I | [test_rebac.py](../../../libs/fred-core/fred_core/tests/integration/test_rebac.py) |
| Z | [test_sensitive_logging.py](../../../libs/fred-core/fred_core/tests/security/test_sensitive_logging.py) |
| E | [test_openfga_reference_cleanup.py](../../../libs/fred-core/fred_core/tests/security/test_openfga_reference_cleanup.py) |
| H | [test_fastapi_handlers.py](../../../libs/fred-core/fred_core/tests/common/test_fastapi_handlers.py) |

## Scenario coverage

Partial coverage and inherited/external boundaries are explicitly limited below.
Test presence does not establish execution or deployment readiness.

| Scenario | Exact test evidence | Coverage and limit |
| --- | --- | --- |
| Catalog id maps to an app object | `A::test_application_catalog_id_is_separate_from_openfga_reference`; `P::test_app_enablement_writes_only_entitlement_and_skips_agent_stores` | mapping and app-targeted writes; no legacy capability tuple is written. |
| A capability check cannot stand in for an app check | `S::test_check_team_capability_refuses_application_catalog_ids` | rejects before an engine call. |
| Same-id resources retain separate cached grants | `C::test_enablement_cache_isolates_app_and_capability_with_same_raw_id` | separate typed direct reads, distinct grants, repeat reads use two independent cache entries. |
| An app grant does not grant the same-id capability | `I::test_app_can_use_is_typed_and_team_scoped`; `A::test_use_is_decided_by_team_grants_without_a_platform_wide_marker` | Integration isolation case remains unrun; offline structure proves no extra gate, not live authorization. |
| App mutation refreshes only the app cache entry | `C::test_app_write_invalidates_only_the_app_row_of_a_shared_raw_id` | Successful app mutation refetches the app row while the same-id capability retains its cached row and tuples. |
| A local cache fill overlaps a mutation | `Q::test_in_flight_read_invalidated_mid_flight_does_not_repopulate_cache`; `Q::test_read_started_after_invalidation_caches_normally`; `Q::test_repeated_write_then_read_cycles_always_cache` | Process-local invalidation and reusable subsequent fills; not cross-replica coherence. |
| An entitlement mutation partially fails | `B::test_enable_half_failure_leaves_capability_disabled`; `C::test_failed_app_grant_invalidates_only_the_app_row` | Partial app mutation propagates failure and refetches changed state without invalidating or altering the same-id capability. |
| A member of an entitled team is admitted | `S::test_check_application_access_asks_membership_then_the_app_grant`; `P::test_discovery_filters_with_team_subject_application_admission` | SDK uses ordered typed checks; discovery filters using raw app ids. Separate fake-engine tests do not establish end-to-end parity. |
| A platform administrator is not a member | `S::test_check_application_access_stops_at_membership_for_a_non_member`; `P::test_discovery_authorizes_before_team_or_application_metadata` | Partial, inherited: mocked membership denial and early exit; neither establishes a real platform-admin/non-member tuple fixture. |
| Membership alone is insufficient | `S::test_check_application_access_denies_a_member_whose_team_lacks_the_grant` | membership succeeds, app check denies, and the SDK raises. |
| Default-on admits a collaborative team | `A::test_application_can_use_encodes_default_and_disabled_precedence`; `I::test_app_default_on_is_inherited_and_can_be_disabled` | Compiled-model structure and retained integration case. Integration not run. |
| A deny wins over both grant sources | `A::test_application_can_use_encodes_default_and_disabled_precedence`; `I::test_app_can_use_is_typed_and_team_scoped`; `I::test_app_default_on_is_inherited_and_can_be_disabled` | Static combined rule; integration cases exercise grant/default denial separately and remain unrun. |
| Registration is not enablement | `P::test_registration_seeding_leaves_configured_applications_untouched`; `I::test_app_can_manage_and_lookup_resources` | Admin-gated registration writes no tuples, with a seedable control entry proving the double works. Anchor-only lookup integration remains unrun. |
| Default-on does not admit a personal space | `A::test_usable_application_ids_rejects_personal_spaces`; `P::test_personal_team_is_authorized_then_returns_empty_without_team_lookup`; `S::test_check_application_access_refuses_personal_spaces` | plus inherited SDK guard: locally rejects/empties before app lookup even when the fake would allow access. No default-on real-engine fixture; this is an application-layer ceiling. |
| A stale personal grant can be removed but not recreated | `P::test_app_personal_tuple_cleanup_remains_available`; `P::test_public_app_enable_rejects_personal_team_before_app_write` | removes both stale team relations without replacement; rejects a new personal grant before writes. |
| Changing an app grant does not change managed agents | `P::test_app_enablement_writes_only_entitlement_and_skips_agent_stores`; `P::test_app_default_off_and_personal_scope_never_touch_agent_store`; `P::test_catalog_hidden_application_grant_stays_revocable` | Store tripwires and app tuple assertions, not a populated external database comparison. |
| App administration does not become an agent capability | `P::test_admin_app_row_forces_agent_impact_and_reasoning_fields_empty`; `P::test_app_is_wire_only_not_runtime_manifest_kind` | row assertions plus inherited manifest-kind rejection; no agent capability is added. |
| A first-party app receives the wrong audience | `S::test_factory_initializes_the_process_jwt_verifier` | Partial, inherited: proves issuer/audience strictness is configured, not that a wrong-audience JWT is rejected end to end. Authentication suites outside this delta were not audited. |
| The frame requests an authenticated operation | No automated test covers this. | Boundary: existing frontend request-adapter contract; no frontend behavior test is added or changed by this delta. |
| Unsafe first-party configuration is refused | `S::test_factory_rejects_permissive_security_profiles`; `S::test_factory_rejects_openfga_owner_configuration`; `S::test_factory_rejects_unbounded_or_invalid_timeouts` | Inherited: exercises configuration rejection, including disabled ReBAC. |
| OpenFGA startup cannot complete | `S::test_factory_propagates_missing_openfga_token`; `S::test_factory_propagates_openfga_initialization_failure` | Partial, inherited: missing local credential and simulated initialization failure; not live invalid-credential/missing-store/connection-failure coverage. |
| An arm's-length backend is not entitled | No automated test covers this. | Boundary: independently deployed backend behavior; no sibling sample tests are claimed as coverage. |
| An enabled application is registered | `P::test_registration_seeding_leaves_configured_applications_untouched`; `P::test_listed_application_is_activated_from_configuration_alone`; `P::test_app_enablement_writes_only_entitlement_and_skips_agent_stores` | Configured catalog projection, tuple-free seeding, and authorized typed anchor/grant writes without lifecycle adoption. |
| A configured entry is hidden from the catalog | `P::test_configured_source_serves_enabled_apps_and_projects_app_catalog_entry`; `P::test_catalog_hidden_application_grant_stays_revocable`; `P::test_catalog_hidden_application_cannot_be_granted` | Catalog filtering and retained management constraints, not global revocation. |
| An application entry is removed and re-added | `P::test_delisting_an_application_leaves_its_permissions_in_place` | Catalog withdrawal/re-registration preserves the stored tuple snapshot, including same-id capability and unrelated app state. This establishes the deferred cleanup gap, not lifecycle support. |
| A team grant is revoked or denied | `A::test_discovery_reads_applications_at_higher_consistency`; `A::test_team_application_check_reads_at_higher_consistency`; `S::test_application_grant_check_reads_at_higher_consistency`; `P::test_discovery_does_not_read_through_the_admin_relations_cache` | Explicit consistency and no presentation-cache admission; live revocation latency unverified. |
| A database constructor fails with sensitive details | `Z::test_engine_creation_failure_logs_no_connection_identity`; `Z::test_sqlite_engine_failure_logs_no_path_and_still_raises`; `Z::test_the_canary_probe_can_see_a_leak_through_a_traceback` | Mocked driver errors, chained/rendered exception checks and detector control; upstream driver's own logs outside this proof. |
| An authorization check denies a request | `Z::test_an_authorization_denial_logs_no_subject_or_resource`; `S::test_check_team_capability_denial_reaches_the_rebac_denial_log`; `H::test_authorization_handler_logs_no_identity_or_exception_chain`; `H::test_generic_handler_logs_no_request_or_chained_exception_details` | Changed denial and shared-handler emissions exclude identity, request and exception-chain canaries; exact static messages still occur. Scoped to those handlers' own records, not the whole request pipeline. Not a repository-wide logging audit. |
| Revocation defeats default-on access | `P::test_catalog_hidden_application_grant_stays_revocable`; `I::test_app_default_on_is_inherited_and_can_be_disabled` | Deny-write assertion; integration enforcement remains unrun. |
| Disabled ReBAC remains confined to the existing permissive mode | `A::test_usable_application_ids_preserves_disabled_rebac_signal`; `P::test_discovery_returns_all_installed_apps_when_rebac_is_disabled`; `S::test_factory_rejects_permissive_security_profiles` | helper plus inherited discovery/factory cases: permissive platform discovery does not enable a permissive first-party SDK. |
| An app user cannot read a forbidden corpus document | No automated test covers this. | Boundary: owning-backend authorization remains required. No corpus or sample end-to-end work is included. |
| An app grant is not a delegated Workspace credential | No implemented Workspace test claimed. | Boundary: planned Workspace contract remains separate; this does not implement its binding validator. |
| A legacy deny is present | No automated preflight test. | Operational: deployment owner must perform the documented legacy-state check; no migration tool is delivered. |
| An old grant cannot override a new denial | `S::test_check_application_access_denies_a_member_whose_team_lacks_the_grant`; `S::test_check_team_capability_refuses_application_catalog_ids` | Partial, denied app path makes only membership and app checks; catalog ids are refused in capability checks. No fixture seeds both a legacy grant and a new denial. |
| A late old write prevents reopening administration | No automated rollout test. | Operational: manual fence/drain/recheck procedure, not an automated deployment gate. |

## Supporting security evidence

Generic reference cleanup retains bounded batching, re-enumeration, explicit
incomplete-cleanup failure and higher-consistency reads, including
`E::test_every_enumeration_asks_for_higher_consistency`. These tests use fakes;
they do not establish atomic deletion or exclude concurrent external writers.

`E::test_cleanup_incomplete_is_exported_from_the_package_root` verifies that
the public package exposes the same incomplete-cleanup exception class and
includes it in its declared exports.

Database log checks include successful sync/async construction, mocked SQLite
paths, missing credential configuration and rendered error chains. They cover
the changed factory's emissions, not logs emitted independently by a real driver.
Offline isolation and monotonic cache invalidation remain separate regression
suites in the control plane.

## Execution evidence

Local offline verification on 2026-09-09:

| Check | Result |
| --- | --- |
| Control-plane offline suite | 1,097 passed; 8 integration tests deselected |
| Core offline suite | 631 passed; 28 integration tests deselected |
| SDK offline suite | 343 passed; 3 skipped |
| Touched-project quality and import-order gates | Passed for all three projects |
| Raw typing | No errors; two core unreachable-code warnings; no backend/SDK warnings |
| Model and generated artifacts | Compiled authorization model matches source; non-app definitions unchanged; configuration/chart schemas match source; generated client change is descriptive only |
| Configuration validation | Four tracked backend configurations and chart values passed |
| OpenSpec and reference checks | Strict validation passed; all 35 scenarios mapped and all 67 exact test references resolved; local links/anchors checked |
| Independent review | App authorization review complete; actionable scoped findings resolved; known limitations recorded below |
| Explicit-path secret scan | No new findings; seven chart-value findings are pre-existing; none added |

In-memory mutations verify the regressions fail in their test bodies when
explicit consistency is removed (two failures), app cache invalidation is
removed (two failures), or exception attachment is restored to the shared
error handler (one failure). Public-export checks also reject a missing export,
a different exception class and missing declared-export membership. No repository
source is modified by these probes.

Logging evidence covers the touched factories, authorization and shared
exception handlers. It does not certify independent driver, access-log,
server or middleware emissions. Generic handler sanitization does not prevent
server exception emissions; shared sink sanitization remains unimplemented.
Type checking is reported both against its suppression baseline and raw.

## Deferred and operational boundaries

Global Deactivate/Activate/Delete belongs to the
[future shared lifecycle gap](design.md#deferred-gap--shared-resource-lifecycle).
It is outside the app resource feature's implementation checklist.

The no-legacy-grant cutover, existing frame authentication boundary, downstream
object permissions, mixed-version deployment and deployed schema/model
compatibility require separate operational verification. No migration or rollout
is performed here.
