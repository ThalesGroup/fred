# 9. Quality and invariants

The guarantees below apply to the named manager mechanisms and first-user journey.
They do not certify every Fred component. Invariant IDs remain stable when the
explanations move between chapters.

## Invariants

| Id | Invariant | Held by |
| --- | --- | --- |
| I1 | An organization is a root, a team's parent is an organization, a project's parent is a non-personal team, a personal space has no parent. Sibling names and organization names are unique. | `domain::check_parent`, `spaces` under the organization lock, organization-name index |
| I2 | Placement never changes: a space's kind, owner and links, a folder's space, parent and path, a document's space and folder. Names may change. | triggers; links written once with the creation grants |
| I3 | A document's folder, and a sub-folder's parent, belong to the same space. | composite foreign keys |
| I4 | Holding a role on a space requires a direct content role on its parent, and a personal-space role a direct content role on its organization, under any concurrency. Inherited access does not satisfy it. | `spaces`, organization lock and atomic OpenFGA guard |
| I5 | Role and SQL mutations cannot publish a decision invalidated by an earlier successful revocation. External operations are authorized at dispatch. | checks after guard capture, atomic fence, SQL lock through commit |
| I6 | A personal space never gains a member, and its organization can always remove its owner. | `spaces::grant`, `spaces::revoke` |
| I7 | A space's search scope is its ancestors and itself, never its descendants; a personal space's scope is itself; levels only remove spaces. | `spaces::scope` |
| I8 | Space admin, organization owner and platform owner roles read no content. | OpenFGA `can_read = member or effective_editor or effective_analyst` |
| I9 | Root bootstrap promotes one caller, once; it never reopens, not even for its own admin after removal. | `bootstrap::grant_root`, marker |
| I10 | Only an RS256 token from the realm, unexpired, with an integer past `iat` and a lifetime within the ceiling, authenticates. | `auth` |
| I11 | Log lines never carry credential- or content-named fields; dependencies never log their own text. | `logging` |
| I12 | A document page continues after its cursor's sort values, even when that document is gone. | keyset cursor |
| I13 | Every line of a request carries its request id, and the request ends with one `http` event. | `logging::request_logging` |
| I14 | Every non-personal space retains at least one administrator, and every organization at least one owner, after role revocation. | `spaces::revoke`, organization lock |
| I15 | Platform owners change platform grants and the platform always retains an owner. New platform grants target an existing Keycloak subject. | `platform`, platform lock, directory lookup |
| I16 | Every acknowledged role mutation emits a security audit event before SQL commit, independently of application severity and text/JSON format. | `logging::audit_relation`, mutation services |
| I17 | Provisioning replay preserves existing identities, committed space IDs and undeclared grants, and repairs requested grants without reusing rolled-back space IDs. | `provisioning`, exact directory lookup, SQL uniqueness |
| I18 | Import requires a verified platform owner and compatible initialized state; predictable preflight failures cause no provisioning or initialization writes. | CLI read-only initialization, HTTP authority-before-upload, `Importer::preflight`, root guard |
| I19 | A human personally accepts the active CGU before business access; consent and root bootstrap create no membership, and import accepts for nobody. | `onboarding`, `OwnUser`, `AdmittedUser`, CLI admission |
| I20 | Editor, admin and analyst reach every descendant space, member stays local, and a personal space inherits nothing. | OpenFGA `effective_*` relations over `parent` links |
| I21 | New organization owner grants target an existing Keycloak subject. An owner exists only on organizations, is named by platform owners, names the organization's admins, and holds no content, management or descending permission. | `spaces::may_change`, directory checks at grant/creation/import, OpenFGA `can_own` |
| I22 | Document and folder mutations recheck existence under the organization lock; deletion winning that lock prevents a waiting mutation or workflow dispatch. | HTTP handlers, SQL transaction held through commit |

## fred-manager tests

| Command (in `apps/fred-manager`) | Runs |
| --- | --- |
| `make test` | Unit tests, offline: domain rules, token verification, logging format, request middleware |
| `make test-integration` | Integration tests against throwaway Postgres/OpenFGA containers and one disposable Keycloak container, removed afterwards; each test gets its own database and store |
| `make test-browser` | Automated Chromium UI import with real OIDC, manager governance routes and disposable dependencies, plus the integration suite; requires frontend dependencies and Chromium |
| `make code-quality` | DSL/JSON model parity, clippy with warnings as errors, rustfmt |

The authorization matrix exercises all 32 space-role subsets and 16 platform-role
subsets against every typed capability, with cross-space and content isolation checks.
A controlled Keycloak HTTP fixture checks directory failures, service-token refresh,
identity mapping and authenticated governance routes.

Authorization-after-revocation tests hold the relevant advisory lock to force the
interleaving they prove. Last-admin tests issue simultaneous revocations and assert
that at most one succeeds.

## Generated HTTP contract

`tests/openapi.rs` checks offline, deterministic schema emission with invalid runtime
configuration paths, the complete route inventory, bearer security, role enums,
required nullable response fields, flattening, multipart upload, optional ingestion
body and empty success responses. Frontend client tests execute the generated RTK
endpoints through the shared base query and check the multipart bytes, bearer,
completed report, error propagation and flat space responses. Regenerating with
`make -C apps/frontend update-fred-manager-api` produces the committed client.

## Provisioning UI acceptance

Frontend component tests cover loading, unavailable and denied authority, duplicate
submit events, pending controls, server counts, report reset, unsupported ZIP,
partial HTTP failure and connection loss. The Playwright journey runs the actual
Fred UI and generated slice against the manager governance router, with real
Keycloak login/service credentials, PostgreSQL and OpenFGA. It imports the Make
ZIP, replays without changing space IDs, imports a project variant, checks hierarchy
and roles, rejects a member, lets a second platform owner replay, and displays
legacy-format refusal. Desktop and narrow screenshots exercise the shared layout.

The journey starts without root grants or consent. It exercises initial configuration
failure/reload, personal terms, wrong secret, successful bootstrap, empty root
memberships, import/replay, and same-browser logout/login as an imported person.
The second person accepts independently and sees their declared spaces. No manager
or Python response is fabricated; any control-plane, knowledge-flow or agent-runtime
call fails. The browser traverses Fred's existing sidebar and administration console,
checks unsupported direct URLs, selects a project on Home, and exercises keyboard
logout before consent, before bootstrap and after admission. A pending-consent
member can return to root and back without inheriting root's consent or memberships.
Each run owns its database, FGA store and Keycloak container. The frontend command
`make test-provisioning-browser` invokes this journey and the integration suite.
Nginx smoke tests verify canonical paths, multipart bodies and bearer forwarding.

Frontend regressions prove that unavailable onboarding fails closed, stale consent
never advances the journey, and a changed version reloads the displayed legal text.
Account tests cover missing name/username claims and menu focus restoration.
Membership tests distinguish an empty result, a missing selection and a failed query;
a failed query hides cached memberships.
Integration regressions exercise version changes, timestamp-preserving retry,
service/delegation refusal, CLI admission and absence of membership side effects.

## OpenFGA request costs

Direct roles and the space tree live in OpenFGA. The client uses `Check`, paginated
`Read` and `Write`; it does not issue `ListObjects`, `ListUsers`, `Expand` or `BatchCheck`.
`Check` and `Read` request `HIGHER_CONSISTENCY`. A content check addresses one
user, permission and space; the model evaluates descending roles through at most two
`parent` links inside OpenFGA. A fixed number of HTTP calls does not specify OpenFGA's
datastore work, latency or throughput.

The frontend navigation and provisioning guard share one cached `/me` query.
Navigation and page subscribers refetch `/me` data older than 60 seconds when
they mount; this threshold does not schedule periodic refresh.
Concurrent subscribers deduplicate the request. Home and the space navigation
share `/me/spaces`; Home requests a fresh result on mount, and selection within
Home uses that result without per-space requests. Each `/me` network fetch performs
the four concurrent Checks listed below; `/me/spaces` uses the tuple and link Reads listed below. There is no polling or additional import-specific FGA query. The
browser fixture (15 imported users, one organization, three teams and one project,
one active import at a time) proves behavior, not throughput or scalability.

With CGU enabled, each business HTTP request and CLI import adds one indexed SQL
acceptance read by subject, without an OpenFGA call or authorization lock. Bootstrap
checks consent before its existing lock. Personal onboarding reads acceptance and
bootstrap completion; it does not enumerate spaces or roles.

The following source-derived successful-path counts exclude startup, authentication, SQL and
Keycloak calls. `C` is one Check; `W(n)` is one Write with `n` total inserts and deletes.
`R_g` is one guard Read filtered by exact object and relation `version`.
`P_u`, `P_p` and `P_a(s)` are the actual Read page counts for a user's direct space
roles, all platform grants, and holders of the admin/owner role being revoked on `s`. Each includes at least
one request, even for an empty result. The client does not specify `page_size`.
`L` is the number of link Reads placing a space: 0 for an organization, 1 for a team
or personal space, 2 for a project. `P_c(s)` counts the Read pages of a space's
children; `P_o(s)` counts its personal-space pages. `P_d` counts the pages of a
user's direct roles on one space. Link and guard reads each return at most one
matching tuple. Other Read counts vary with pagination, including empty results.

| Operation | OpenFGA calls | Read filter or decision scope |
| --- | --- | --- |
| Content access; authorize document/space/platform | `1 C` | Exact user, permission, object |
| Authorize scope | `1 C + L Read` | Read check, then the parent links |
| `GET /me` | `4 C`, concurrent | Caller's four effective platform roles |
| `GET /me/spaces` | `P_u + D + sum P_c(s) Read` | Direct roles; one link per directly granted team, project or personal space (`D`, concurrent); all child pages of each organization and team reached by a descending role, concurrent per level |
| Team registry page | `1 C + t Read` | Platform registry permission; one concurrent `parent` Read per returned team, `t ≤ 100` |
| List platform grants | `1 C + P_p Read` | Owner check, then all subjects/roles on `platform:root` |
| Grant platform role | `1 R_g + 1 C + W(3)` | Actor owner; separate Keycloak subject lookup |
| Revoke platform role | `1 R_g + 1 C + P_p Read + W(3)` | All platform grants are read to locate one direct grant and another owner |
| Grant organization owner | `2 R_g + 1 C + W(5)` | Platform and organization guards; actor platform owner; separate Keycloak subject lookup |
| Grant organization admin | `1 R_g + 1-2 C + W(3)` | Actor manages organization, else owns it |
| Grant other organization role | `1 R_g + 1 C + W(3)` | Actor manages organization |
| Grant team/project role | `L Read + 1 R_g + 1 C + P_d Read + W(3)` | Actor manages space; target's direct parent roles |
| Revoke space role | `L Read + 1 R_g + 1-2 C + P_u Read + P_c(s) Read + W(2 + d)` | Target's direct roles across all spaces; children (an organization adds `P_o(s)` personal-space Reads); the second Check is only for an organization admin change |
| Revoke a held admin or owner role on a non-personal space | Previous row + `P_a(s) Read` | All direct holders of that role; an owner revocation adds `R_g` and two Write operations for the platform guard |
| Create team or project | `L_p Read + 1 R_g + 1 C + P_d Read + P_c(parent) Read + W(4)` | Actor manages parent; nominated admin's direct parent roles; sibling names; link and admin in one Write |
| Create personal space | `1 R_g + 1 C + P_o(org) Read + W(5)` | Caller reads organization; existing personal spaces; link, member and editor in one Write |
| Operator create organization | `W(2) + 1 R_g + W(5)` | Directory subject lookup, initialize guard, then initial owner/admin/member grants |
| Public configuration, personal onboarding and consent | `0` | SQL bootstrap/acceptance reads or consent upsert only |
| Root bootstrap | `1 R_g + W(3)` | Bearer/secret and SQL marker govern admission |

`d` is 1 when the revoked role exists, otherwise 0. A successful absent space-role
revocation still advances its guard. A platform-role revoke returns 404 when absent.
`L_p` places the parent. SQL folder/document mutations and Temporal dispatch use `L Read + 1 R_g + 1 C + W(2)`;
the fence contains no role change. Existing-object mutation adds one indexed SQL
existence read under the organization lock (I22), independently of document count. Each successful guard replacement adds two
operations per scope, independent of the number of existing roles.

Sources: [client](../../apps/fred-manager/src/fga.rs),
[space mutations, memberships and scope](../../apps/fred-manager/src/spaces.rs),
[platform mutations](../../apps/fred-manager/src/platform.rs), and
[HTTP handlers](../../apps/fred-manager/src/api.rs).

For the ZIP importer, let `U` be users, `O` organizations, `N` new organizations,
`G` normalized platform grants, `D` space-role tuples, `C` new teams and projects,
and `B = sum_s ceil((role_tuples(s) + new(s)) / 96)` over all declared spaces, where `new(s)` is 1 only for a new team or project. `Z`
counts organization subtrees with no declared role tuples. `H` counts child/subject
pairs lacking a declared parent content role and therefore requiring an existing
direct-parent-role Read; siblings with the same subject each contribute a Read. `E`
counts existing parents whose children resolve declared names. With one page per tree Read, on a successful attempt:

- `U + 3 + O + B + G` Checks;
- `U + 2O + (G > 0 ? 1 : 0)` exact guard Reads, plus `3H + 2E` tree Reads;
- `U + N + B + G + Z` Writes;
- `D + C + 2U + 2N + 4B + 3G + 4Z` tuple operations across those Writes.

Direct-parent-role Reads use `user:<subject>` and `space:<parent>` in whole-bundle
preflight, whole-bundle reconciliation and the guarded subtree check. Children
Reads use `space:<parent>`, relation `parent`, in preflight and reconciliation.
Authority Checks use `owner` on `platform:root`. Guard Reads use the exact
`guard:<scope>` object/revision relation; no role enumeration is needed by import. Space batches
contain at most 96 link and role inserts plus four guard operations; a new space's
`parent` link shares its first batch. Platform grants contain
three operations, with only the platform guard. FGA calls are sequential. Multi-page direct-role or child lists add their extra
pages at each corresponding traversal.
HTTP adds one owner Check before upload reading. CLI adds that Check plus two GETs
(configured-store discovery and pinned-model verification). Model evaluation remains
inside OpenFGA; these RPC counts do not measure its internal work.

The [importer](../../apps/fred-manager/src/provisioning.rs) holds the platform lock
per identity dispatch, then platform plus all declared organization locks through
reconciliation commit. Organizations are locked in UUID order; child name resolution
follows locking. Preflight directory lookups hold no lock. Parser memory is bounded
by compressed/expanded bytes plus decoded declarations; ordered reference/name
indexes require `O((U + S) log(U + S))` operations for `S` declarations, in addition
to decoding and role traversal. Reconciliation scans declarations for each organization,
so its application work includes `O(O * (S + D))`; it retains `O(U + S + D)` data.
Documents do not contribute to these cardinalities.

The actual Make demo artifact (15 users, one new organization, three teams,
27 space grants, four platform grants, four batches, `C=3`, `H=Z=E=0`)
exercises HTTP with 28 Checks, 18 Reads and 24 Writes: 90 tuple operations. The
batch-boundary fixture (105 users, 107 organization grants, 210 team grants, one new
organization and team, no platform grants, `H=Z=E=0`) checks 114 Checks, 107 Reads
and 111 Writes: 550 tuple operations and at most 100 per Write. Its replay variant
(`U=2`, `H=2`, `E=2`) checks 9 Checks and 14 Reads. The hierarchy fixture (one
organization, team and project, an organization analyst with a personal space)
checks 4 Reads for `/me/spaces`, and `1 C + 2 Read` and `1 C + 1 Read` for project
and team scopes. These are wire-count assertions in disposable
integration environments, not latency, throughput or scalability measurements.

Startup with a published binding uses the discovery GET plus the pinned-model GET.
An empty installation adds one full tuple Read, two POSTs (store and model) and the
platform guard initialization Write; existing state without a binding is refused.

Read pagination bounds each response, not the operation's memory: `read_keys`
accumulates all matching tuples. With `R` direct role tuples and `S` returned spaces,
`/me/spaces` uses `O(R + S)` application memory and `O(S log S + S * R)` processing
for ordering, path walks and per-space role selection; its concurrent Reads are
unbounded within one level. Space revocation tests child membership in `O(R * D)`
worst-case application work for `D` children and personal spaces. These costs concern Fred's processing of returned
tuples, not OpenFGA's internal query plan.

Organization-scoped role/space/content mutations retain a SQL connection and advisory lock across remote
calls. Platform changes, organization-owner changes and import also use the platform lock;
team/project creation takes only the organization lock. HTTP server waiters acquire a connection before
waiting for that lock, sharing its ten-connection pool with other SQL work. CLI
import uses a separate two-connection pool.
The configured default FGA timeout is five seconds per request, not per complete
paginated operation. Document count does not multiply role tuples in this model:
content authorization is scoped to the owning space.

## Directory and content verification costs

For a successful import, preflight performs a paginated exact username lookup per
user and one exact email lookup per missing identity. Username lookup continues
through an empty page; email lookup requests at most one result because any match
conflicts. Duplicate emails among new declarations are compared locally before
that declaration's directory call. Existing identities skip email checks.
Each identity dispatch repeats its username lookup; creation adds one POST and a
final username lookup. These calls reuse the shared HTTP client and service token.

Before space publication, `K` distinct organization owner subjects add `K` GETs,
in batches of at most eight concurrent calls while the reconciliation locks are
held. A subject owning several organizations is checked once in that operation.
Each platform grant also checks its subject. HTTP owner grants and operator
organization creation each add one subject GET. Every directory request has a
five-second timeout and can refresh/retry once on 401; a missing cached service
token adds its token request. These are existence checks, not permission caches or
leases across operations. Concurrent external IAM deletion can follow a check.

The 12-owner/two-organization fixture asserts 12 subject requests and concurrency
between two and eight. Content regressions exercise the real HTTP router and
Temporal SDK against a protocol fixture, including exact workflow inputs,
conflict/error responses and deletion interleavings. They verify submission,
not execution by a worker or production throughput.

## Invariants and their proofs

Generated from the `// Proves:` markers.

<!-- generated: invariants -->
| Invariant | Proved by |
| --- | --- |
| I1 | `apps/fred-manager/src/domain.rs::parent_rules`<br>`apps/fred-manager/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/fred-manager/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/fred-manager/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors`<br>`apps/fred-manager/tests/integration.rs::blueprint_preflight_reads_child_names_after_organization_lock`<br>`apps/fred-manager/tests/integration.rs::sibling_names_are_unique_and_uncommitted_links_are_ignored` |
| I2 | `apps/fred-manager/tests/integration.rs::placement_is_immutable_and_folders_stay_in_their_space` |
| I3 | `apps/fred-manager/tests/integration.rs::placement_is_immutable_and_folders_stay_in_their_space` |
| I4 | `apps/fred-manager/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/fred-manager/tests/integration.rs::concurrent_revocations_keep_parent_access`<br>`apps/fred-manager/tests/integration.rs::concurrent_grant_and_revoke_keep_the_invariant`<br>`apps/fred-manager/tests/integration.rs::analyst_membership_is_content_and_personal_roles_remain_fixed`<br>`apps/fred-manager/tests/integration.rs::provisioning_replays_every_role_without_updating_identities_or_implicit_content`<br>`apps/fred-manager/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/fred-manager/tests/integration.rs::provisioning_repairs_every_fga_boundary_including_ambiguous_acknowledgments`<br>`apps/fred-manager/tests/integration.rs::import_rechecks_parent_after_wait_and_repairs_existing_space_grants`<br>`apps/fred-manager/tests/integration.rs::a_timed_out_child_grant_cannot_arrive_after_parent_revocation`<br>`apps/fred-manager/tests/integration.rs::a_cancelled_child_grant_is_fenced_after_client_restart`<br>`apps/fred-manager/tests/integration.rs::noop_revocation_and_multiple_scopes_fence_stale_attempts`<br>`apps/fred-manager/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors`<br>`apps/fred-manager/tests/integration.rs::inherited_access_does_not_replace_parent_membership` |
| I5 | `apps/fred-manager/tests/integration.rs::a_revoked_admin_cannot_finish_a_waiting_request`<br>`apps/fred-manager/tests/integration.rs::revoked_platform_actor_cannot_complete_a_waiting_platform_or_owner_grant`<br>`apps/fred-manager/tests/integration.rs::simultaneous_imports_reuse_usernames_and_space_names`<br>`apps/fred-manager/tests/integration.rs::provisioning_waiter_rechecks_revoked_or_expired_operator`<br>`apps/fred-manager/tests/integration.rs::preflight_does_not_block_revocation_and_cancelled_identity_creation_replays`<br>`apps/fred-manager/tests/integration.rs::import_rechecks_parent_after_wait_and_repairs_existing_space_grants`<br>`apps/fred-manager/tests/integration.rs::a_timed_out_platform_grant_cannot_arrive_after_actor_revocation`<br>`apps/fred-manager/tests/integration.rs::noop_revocation_and_multiple_scopes_fence_stale_attempts`<br>`apps/fred-manager/tests/integration.rs::sql_mutation_loses_to_a_delayed_revocation_after_its_check`<br>`apps/fred-manager/tests/integration.rs::folder_creation_keeps_one_connection_through_placement_and_write`<br>`apps/fred-manager/tests/integration.rs::content_http_dispatch_preserves_payload_and_failure_boundaries` |
| I6 | `apps/fred-manager/tests/integration.rs::a_member_with_a_personal_space_can_leave_the_organization`<br>`apps/fred-manager/tests/integration.rs::analyst_membership_is_content_and_personal_roles_remain_fixed`<br>`apps/fred-manager/tests/integration.rs::descending_roles_reach_projects_and_member_stays_local` |
| I7 | `apps/fred-manager/src/domain.rs::search_scope_is_ancestors_then_self`<br>`apps/fred-manager/tests/integration.rs::scope_follows_ancestors_and_levels_only_narrow_it` |
| I8 | `apps/fred-manager/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/fred-manager/tests/integration.rs::admin_roles_grant_no_content_access`<br>`apps/fred-manager/tests/integration.rs::complete_role_permission_matrix_and_space_isolation`<br>`apps/fred-manager/tests/integration.rs::teams_are_created_by_organization_admins_only`<br>`apps/fred-manager/tests/integration.rs::provisioning_replays_every_role_without_updating_identities_or_implicit_content`<br>`apps/fred-manager/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/fred-manager/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors`<br>`apps/fred-manager/tests/integration.rs::descending_roles_reach_projects_and_member_stays_local`<br>`apps/fred-manager/tests/integration.rs::organization_owners_name_admins_and_read_nothing` |
| I9 | `apps/fred-manager/tests/integration.rs::bootstrap_promotes_one_person_once`<br>`apps/fred-manager/tests/integration.rs::a_finished_bootstrap_stays_closed_after_its_admin_is_removed`<br>`apps/fred-manager/tests/integration.rs::concurrent_retries_finish_a_bootstrap_once`<br>`apps/fred-manager/tests/integration.rs::an_interrupted_bootstrap_is_finished_by_its_caller_only`<br>`apps/fred-manager/tests/integration.rs::consent_and_root_bootstrap_are_personal_and_do_not_create_memberships` |
| I10 | `apps/fred-manager/src/auth.rs::rejects_expired_and_overlong_tokens`<br>`apps/fred-manager/src/auth.rs::lifetime_ceiling_cannot_be_skipped`<br>`apps/fred-manager/src/auth.rs::rejects_missing_kid_and_bad_signature`<br>`apps/fred-manager/src/auth.rs::strict_mode_checks_issuer_and_audience` |
| I11 | `apps/fred-manager/src/blueprint.rs::invalid_declarations_and_duplicate_json_keys_fail_without_echoing_input`<br>`apps/fred-manager/src/keycloak.rs::directory_failures_do_not_echo_credentials_or_payloads`<br>`apps/fred-manager/src/logging.rs::sensitive_and_reserved_fields_never_leak`<br>`apps/fred-manager/src/logging.rs::dependencies_get_a_fixed_message_without_their_fields`<br>`apps/fred-manager/tests/integration.rs::directory_creation_conflict_pagination_preservation_and_failures` |
| I12 | `apps/fred-manager/tests/integration.rs::pagination_survives_deleting_the_cursor_row` |
| I13 | `apps/fred-manager/src/logging.rs::requests_carry_ids_and_end_with_one_http_event` |
| I14 | `apps/fred-manager/tests/integration.rs::concurrent_admin_revocations_leave_one_admin_at_every_level`<br>`apps/fred-manager/tests/integration.rs::organization_owners_name_admins_and_read_nothing`<br>`apps/fred-manager/tests/integration.rs::owner_grants_require_directory_identity_and_deleted_owners_can_be_revoked` |
| I15 | `apps/fred-manager/tests/integration.rs::platform_owners_manage_each_other_and_keep_one`<br>`apps/fred-manager/tests/integration.rs::provisioning_preflight_failures_have_no_identity_space_or_role_writes`<br>`apps/fred-manager/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors` |
| I16 | `apps/fred-manager/src/logging.rs::audit_records_survive_warning_application_threshold`<br>`apps/fred-manager/tests/integration.rs::durable_grants_are_audited_even_when_sql_commit_fails` |
| I17 | `apps/fred-manager/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/fred-manager/tests/integration.rs::provisioning_replays_every_role_without_updating_identities_or_implicit_content`<br>`apps/fred-manager/tests/integration.rs::directory_creation_conflict_pagination_preservation_and_failures`<br>`apps/fred-manager/tests/integration.rs::provisioning_replay_after_identity_and_sql_failures_reuses_committed_state`<br>`apps/fred-manager/tests/integration.rs::simultaneous_imports_reuse_usernames_and_space_names`<br>`apps/fred-manager/tests/integration.rs::provisioning_batches_large_parent_and_child_grants_and_keeps_personal_spaces_apart`<br>`apps/fred-manager/tests/integration.rs::preflight_does_not_block_revocation_and_cancelled_identity_creation_replays`<br>`apps/fred-manager/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/fred-manager/tests/integration.rs::provisioning_repairs_every_fga_boundary_including_ambiguous_acknowledgments`<br>`apps/fred-manager/tests/integration.rs::cancellation_after_fga_write_rolls_back_new_space_and_replays`<br>`apps/fred-manager/tests/integration.rs::import_rechecks_parent_after_wait_and_repairs_existing_space_grants`<br>`apps/fred-manager/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors` |
| I18 | `apps/fred-manager/src/blueprint.rs::invalid_declarations_and_duplicate_json_keys_fail_without_echoing_input`<br>`apps/fred-manager/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/fred-manager/tests/integration.rs::provisioning_preflight_failures_have_no_identity_space_or_role_writes`<br>`apps/fred-manager/tests/integration.rs::provisioning_waiter_rechecks_revoked_or_expired_operator`<br>`apps/fred-manager/tests/integration.rs::import_cli_is_read_only_until_authorized_and_requires_initialized_state`<br>`apps/fred-manager/tests/integration.rs::preflight_does_not_block_revocation_and_cancelled_identity_creation_replays`<br>`apps/fred-manager/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/fred-manager/tests/integration.rs::import_rejects_incompatible_model_without_syncing_it`<br>`apps/fred-manager/tests/integration.rs::competing_empty_initializers_converge_on_the_published_binding`<br>`apps/fred-manager/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors`<br>`apps/fred-manager/tests/integration.rs::blueprint_preflight_reads_child_names_after_organization_lock`<br>`apps/fred-manager/tests/integration.rs::startup_refuses_existing_state_without_a_publication` |
| I19 | `apps/fred-manager/src/config.rs::active_terms_version_is_explicit_and_validated`<br>`apps/fred-manager/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/fred-manager/tests/integration.rs::import_cli_is_read_only_until_authorized_and_requires_initialized_state`<br>`apps/fred-manager/tests/integration.rs::consent_and_root_bootstrap_are_personal_and_do_not_create_memberships` |
| I20 | `apps/fred-manager/tests/integration.rs::descending_roles_reach_projects_and_member_stays_local`<br>`apps/fred-manager/tests/integration.rs::memberships_list_inherited_spaces_with_their_paths` |
| I21 | `apps/fred-manager/tests/integration.rs::import_cli_is_read_only_until_authorized_and_requires_initialized_state`<br>`apps/fred-manager/tests/integration.rs::organization_owners_name_admins_and_read_nothing`<br>`apps/fred-manager/tests/integration.rs::owner_grants_require_directory_identity_and_deleted_owners_can_be_revoked`<br>`apps/fred-manager/tests/integration.rs::import_rechecks_owner_identity_before_publishing_spaces`<br>`apps/fred-manager/tests/integration.rs::import_checks_distinct_owners_once_with_bounded_concurrency` |
| I22 | `apps/fred-manager/tests/integration.rs::content_http_waiters_recheck_existence_after_deletion` |
<!-- end generated -->

Provisioning tests inject failures before/after real FGA writes, fail deferred SQL commits,
and cancel after identity creation and FGA acknowledgment. Replay assertions check preserved
committed IDs, fresh IDs after rollback and restored grants. Gates force preflight/revocation
and cancellation interleavings; batch tests exceed the FGA write limit. CLI subprocess tests
verify token/mapping refusals, zero-count setup diagnostics (including after SQL errors),
migration-table absence and unchanged FGA models on failure
and success. The real Keycloak test configures a distinct `fred-manager` client with the
three declared realm-management grants, builds the real Make ZIP and imports it
over HTTP. It verifies every platform role, unchanged existing profiles/passwords,
visible spaces, additive replay and a nonempty-project variant. HTTP tests cover
homonymous hierarchy isolation, whole-bundle preflight, owner declarations, limits
and safe dependency failures. A lock-wait regression commits a conflicting personal
space before preflight resumes and verifies that no identity is created.
