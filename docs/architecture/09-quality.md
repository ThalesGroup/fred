# 9. Quality and invariants

The guarantees below apply to the named manager mechanisms and first-user journey.
They do not certify every Fred component. Invariant IDs remain stable when the
explanations move between chapters.

## Invariants

| Id | Invariant | Held by |
| --- | --- | --- |
| I1 | An organization is a root, a team's parent is an organization, a project's parent is a non-personal team, a personal space has no parent. Sibling names and organization names are unique. | `domain::check_parent`, `spaces` under the organization lock, organization-name index |
| I2 | Placement is immutable: a space's kind, owner and links, a folder's space, parent and path, a document's space and folder. Names may change; the authorized deletion lifecycle removes retired space links. | triggers; links written once with the creation grants |
| I3 | A document's folder, and a sub-folder's parent, belong to the same space. | composite foreign keys |
| I4 | Holding a role on a space requires a direct content role on its parent, and a personal-space role a direct content role on its organization, under any concurrency. Inherited access does not satisfy it. Personal creation eligibility also requires direct organization content. | `spaces`, organization lock and atomic OpenFGA guard |
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
| I23 | A person holds roles in at most one organization per Fred instance. Business access requires that unique context as well as permission; platform governance is independent. | committed direct roles and placement, context validation, platform lock and guard on attachment writers |
| I24 | Space retirement is atomic; cleanup starts no earlier than the frozen deadline, preserves retry identifiers and declares completion only after SQL/FGA cleanup. | `lifecycle`, retired consumer gates, bounded activities and receipts |

## fred-manager tests

| Command (in `apps/fred-manager`) | Runs |
| --- | --- |
| `make test` | Unit tests, offline: domain rules, token verification, logging format, request middleware |
| `make test-integration` | Integration tests against throwaway Postgres/OpenFGA containers and one disposable Keycloak container, removed afterwards; each test gets its own database and store |
| `make test-lifecycle-temporal` | HTTP acceptance, real Temporal worker interruption/restart, schedule reconciliation and workflow-history replay on disposable services |
| `make test-browser` | Automated Chromium UI import with real OIDC, manager governance routes and disposable dependencies, plus the integration suite; requires frontend dependencies and Chromium |
| `make code-quality` | DSL/JSON model parity, clippy with warnings as errors, rustfmt |

The authorization matrix exercises all 64 space-role subsets and 16 platform-role
subsets against every typed capability, with cross-space and content isolation checks.
A controlled Keycloak HTTP fixture checks directory failures, service-token refresh,
identity mapping and authenticated governance routes.

Authorization-after-revocation tests hold the relevant advisory lock to force the
interleaving they prove. Last-admin tests issue simultaneous revocations and assert
that at most one succeeds.

## Space deletion acceptance and recovery

The lifecycle fixture exercises retirement at all three levels, document refusal,
personal descendants, durable receipts after missing hierarchy links, reserved names,
last-parent-role protection, concurrent acceptance and late activities after UUID
replacement. Faults cover FGA commits with lost acknowledgments and SQL failure
after the final organization guard disappears. A blocked candidate does not starve
other due operations. Both supported predecessor models upgrade in place; the test
also injects failure when publishing the SQL model pointer.

The real Temporal fixture starts the separate binary, interrupts it after the first
folder batch and replays workflow history. It also holds the platform SQL lock while
sending SIGTERM, verifies bounded process exit and release of the server-side wait,
then restarts to completion. An injected SQL delete failure exhausts activity retries,
produces a safe `retrying` receipt and recovers after the fault is removed.

Let `L` be target placement Reads (0/1/2 for organization/team/project), and `D`
the descendant page Reads. Lifecycle discovery requests 96 tuples per page and
exhausts cursors: an organization reads child-team and personal-space pages and
each team's project pages; a team reads project pages; a project reads none.
These counts exclude authentication/admission, SQL and startup.

| Phase | OpenFGA client RPCs and filters | SQL lock boundary |
| --- | --- | --- |
| First acceptance | `4 + L + D`: platform version Read, owner capability Check, placement Reads, organization version Read, descendant Reads by exact parent/organization subject plus `object=space:`, one four-operation guard Write | Platform then organization locks, held through complete subtree validation, retirement and commit; no Temporal RPC |
| Receipt replay/status | One current platform capability Check | Indexed receipt lookup, no mutation lock for an already committed receipt |
| Ordinary cleanup batch | Five Reads: platform version, organization guard existence, organization version, exact target object, and incoming `user=space:<id>, object=space:`; zero or one Write, at most 96 payload deletes plus four guard operations | One bounded transaction, up to 1000 folder leaves or one tuple batch or one space row; no retention/retry sleep under locks |
| Final organization removal | Seven Reads and one Write with the guard present; recovery after its removal uses five Reads and one platform fence Write | Final root metadata and receipt completion commit together |
| Due candidate selection | No FGA RPC; indexed SQL selection and visit timestamp update | Row locks use `SKIP LOCKED`; at most configured batch size |

Reference cleanup drains fresh first pages; it never reuses a cursor across a
mutation. Current model metadata allows incoming space references only. Guard reads
are exact and independent of role volume. Discovery cost grows with spaces and
hierarchy pages; cleanup cost grows with target tuples and folders. Unrelated users,
memberships and documents do not induce full-store scans. OpenFGA's internal Check
evaluation work is separate from these client RPC counts.

On the local disposable-service fixture (six lifecycle tests running concurrently),
one acceptance took 17.740 ms with three spaces, 1001 target folders and 243 target
tuples. Another organization held 241 member tuples plus its owner/admin grants.
Acceptance used exactly four Reads, one Check and one Write. Six cleanup attempts,
including one committed FGA delete with a lost acknowledgment, took 149 ms; combined
acceptance/cleanup used 34 Reads, one Check and seven Writes. Assertions cap every
Write at 100 tuple operations and require filtered Reads. SQL progress records
1001 folders and one space removed; all 241 unrelated member tuples remain.
Eight concurrent receipt retries in a separate two-space fixture returned one UUID
in 165 ms. These are service elapsed times, not isolated lock-hold measurements or
throughput guarantees. Forced lock waiters verify ordering and retirement rechecks;
atomic subtree acceptance holds its locks for the whole discovery and commit.

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
The second person accepts independently and sees their declared spaces. Normal success responses come from real manager/Keycloak; one injected 401 tests
explicit retry without automatic replay; any control-plane, knowledge-flow or agent-runtime
call fails. The browser traverses Fred's existing sidebar and administration console,
checks unsupported direct URLs, selects a project on Home, and exercises keyboard
logout before consent, before bootstrap and after admission. Priya creates/reopens one personal UUID, returns to fredlab and reloads; Bob
without eligibility is refused. A pending-consent
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

## Resource browsing acceptance

The same real browser journey seeds metadata after provisioning in its disposable
SQL database: one private document for Priya, one fredlab root document, a library
with 53 documents and an empty child folder. It verifies personal/team separation,
keyboard folder entry, breadcrumb return, Next/Previous, true emptiness and narrow
layout. Injected 403/500 responses exercise denial, failure and explicit reload;
Bob's direct personal-space URL receives a real server refusal. Python-service
requests remain forbidden by the fixture.

Frontend regressions additionally hold responses across folder/space changes and
re-entry after revocation, including React StrictMode cleanup. API regressions
verify invalid/foreign folder filters, role semantics, revoked access and cursor
boundaries. These are fixture-based functional tests, not a load campaign.

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
share `/me/spaces`; Home and scoped navigation request a fresh result on mount.
Space selection uses those memberships; opening Resources performs its separate
folder/document reads. Each `/me` network fetch performs
the four concurrent platform Checks listed below; it does not select an organization; `/me/spaces` uses the tuple and link Reads listed below. There is no polling or additional import-specific FGA query. The
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
`Q(u) = P_u + sum L(s)` Reads resolves a subject's organization over distinct committed
direct-grant spaces. The resolver filters roles by `user=user:<u>, object=space:`
and placements by exact space object and `parent` or `organization` relation.
It exhausts all pages, grants no permissions, and fails on distinct organization IDs.
`Q` counts client RPCs, not OpenFGA server evaluation work.

| Operation | OpenFGA calls | Read filter or decision scope |
| --- | --- | --- |
| Content access; authorize document/space | `Q(caller) + L Read + 1 C` | Unique caller context, target placement, exact permission; a foreign context short-circuits before Check |
| Authorize platform | `1 C` | Exact platform permission; no business context |
| Authorize scope | `Q(caller) + 1 C + L Read` | Target placement, caller context, then read permission Check |
| `GET /me` | `4 C`, concurrent | Caller's four effective platform roles |
| `GET /me/spaces` | `P_u + D + A + sum P_c(s) Read` | Direct roles; one link per directly granted team, project or personal space (`D`, concurrent); `A` missing team-parent links for direct orphan projects; all child pages of each organization and team reached by a descending role, concurrent per level |
| Team registry page | `1 C + t Read` | Platform registry permission; one concurrent `parent` Read per returned team, `t ≤ 100` |
| List platform grants | `1 C + P_p Read` | Owner check, then all subjects/roles on `platform:root` |
| Grant platform role | `1 R_g + 1 C + W(3)` | Actor owner; separate Keycloak subject lookup |
| Revoke platform role | `1 R_g + 1 C + P_p Read + W(3)` | All platform grants are read to locate one direct grant and another owner |
| Grant organization owner | `Q(target) + 2 R_g + 1 C + W(5)` | Platform and organization guards; actor platform owner; separate Keycloak subject lookup |
| Grant organization admin | `Q(caller) + Q(target) + 2 R_g + 1-2 C + W(5)` | Actor manages organization, else owns it |
| Grant other organization role | `Q(caller) + Q(target) + 2 R_g + 1 C + W(5)` | Actor manages organization |
| Grant team/project role | `Q(caller) + Q(target) + L Read + 2 R_g + 1 C + P_d Read + W(5)` | Actor manages space; target's direct parent roles |
| Revoke space role | `Q(caller) + L Read + 2 R_g + 1-2 C + P_u Read + P_c(s) Read + W(4 + d)` | Target's direct roles across all spaces; children (an organization adds `P_o(s)` personal-space Reads); the second Check is only for an organization admin change |
| Revoke a held admin or owner role on a non-personal space | Previous row + `P_a(s) Read` | All direct holders of that role; an owner revocation omits `Q(caller)` and uses the independent platform-owner Check |
| Create team or project | `Q(caller) + Q(admin) + L_p Read + 1 R_g + 1 C + P_d Read + P_c(parent) Read + W(4)` | Actor manages parent; nominated admin's direct parent roles; sibling names; link and admin in one Write |
| Create personal space | `Q(caller) + 1 R_g + 2 C + P_o(org) Read + W(5)` | Organization read and explicit eligibility; all personal links; link, member and editor in one Write |
| Reuse personal space | `Q(caller) + 1 R_g + 2 C + P_o(org) Read` | Organization and personal read; no SQL/FGA mutation |
| Operator create organization | `W(2) + 2 R_g + Q(first person) + W(7)` | Directory subject lookup, initialize guard, then initial owner/admin/member grants |
| Public configuration, personal onboarding and consent | `0` | SQL bootstrap/acceptance reads or consent upsert only |
| Root bootstrap | `1 R_g + W(3)` | Bearer/secret and SQL marker govern admission |

`d` is 1 when the revoked role exists, otherwise 0. A successful absent space-role
revocation still advances its guard. A platform-role revoke returns 404 when absent.
`L_p` places the parent. SQL folder/document mutations and Temporal dispatch use `Q(caller) + L Read + 1 R_g + 1 C + W(2)`;
the fence contains no role change. Existing-object mutation adds one indexed SQL
existence read under the organization lock (I22), independently of document count. Each successful guard replacement adds two
operations per scope, independent of the number of existing roles.

Sources: [client](../../apps/fred-manager/src/fga.rs),
[space mutations, memberships and scope](../../apps/fred-manager/src/spaces.rs),
[platform mutations](../../apps/fred-manager/src/platform.rs), and
[HTTP handlers](../../apps/fred-manager/src/api.rs).

Resource entry and each folder/document-page transition issue two concurrent manager
list requests, in addition to admission/navigation queries. Each list costs
`Q(caller) + L Read + 1 C`, with zero Writes and no SQL transaction/advisory lock.
An additional `POST /authorize/space` checks write visibility on each entry and
explicit refresh, costing `Q(caller) + L Read + 1 C`. A create POST costs
`Q(caller) + L Read + 1 R_g + 1 C + W(2)`: its Write replaces one guard revision
(delete one, write one), not a content grant. A successful UI create remounts the
first page, repeating the two list reads and write-visibility probe. No role is
inferred by the UI. A failed probe hides the create action.

After authorization, a supplied folder adds one indexed SQL existence lookup.
Document SQL returns at most 51 rows to the UI; folder SQL returns all direct children.
A retry or abandoned-request recovery can issue another pair.

A fixture with one organization, one team, one personal space and five direct role
tuples for the reader forces one tuple per Read page. At HTTP concurrency 1, each
list of either zero or 53 stored documents measures 8 Reads, 1 Check and 0 Writes.
An additional fixture with one organization, 40 teams and 41 direct member tuples
forces 10 tuples per page and a 20 ms proxy delay: one organization resolution uses
45 Reads, no Checks/Writes, and overlapping Reads with a peak at most 32. The limit
is per resolution, not global; concurrent HTTP callers multiply it. Project parent
reads remain ordered. SQL mutation callers retain their existing locks across context
resolution; listing takes no such lock. Cardinalities remain direct memberships,
hierarchy depth, direct child folders and requested document-page size, not a claimed
constant server-side authorization cost. These fixtures do not measure production
latency or throughput.

The folder creation fixture uses one direct organization editor tuple, one tuple
per forced Read page and HTTP concurrency 1: 3 Read RPCs (team parent, guard version,
user roles), 1 Check and 1 Write with two guard tuple operations. It also exercises
15 nested levels, 255 Unicode scalar names, personal isolation, denied roles, foreign
parents/organizations, a revoked lock waiter, and two concurrent identical names
(one 201 and one 409). Neither folder depth nor document count adds FGA tuples.
The SQL lock covers guard/context/Check/fence, parent lookup and insertion until
commit; OpenFGA network waits are inside this interval. Test wall time is not a
measurement of lock duration or production capacity.

Frontend tests exercise repeated Enter, pending dismissal, retained conflict input,
revocation, disabled 401 replay and navigation before completion. The disposable
browser journey creates personal and team folders, creates a nested folder, rejects
a duplicate and checks the dialog's close control with a 255-character parent name
at a 390-pixel viewport. Its Vite cache is isolated and the router graph warms before
interactive assertions, avoiding optimizer interference from other test runs.

For the ZIP importer, let `U` be users, `O` organizations, `N` new organizations,
`G` normalized platform grants, `D` space-role tuples, `C` new teams and projects,
and `B = sum_s ceil((role_tuples(s) + new(s)) / 96)` over all declared spaces, where `new(s)` is 1 only for a new team or project. `Z`
counts organization subtrees with no declared role tuples. `H` counts child/subject
pairs lacking a declared parent content role and therefore requiring an existing
direct-parent-role Read; siblings with the same subject each contribute a Read. `E`
counts existing parents whose children resolve declared names. `X` is the sum of actual `Q(subject)` Reads at the three attachment checkpoints:
known declared subjects in preflight, all declared subjects in reconciliation, and
each subtree's declared subjects after guard capture. A subject counts only when
assigned at least one space role. Let `J` count creator declarations without declared content, each needing an existing
organization-content Read at all three dependency checkpoints. With one page per
tree Read, on a successful attempt:

- `U + 3 + O + B + G` Checks;
- `U + 2O + (G > 0 ? 1 : 0)` exact guard Reads, plus `3H + 3J + 2E` tree Reads and `X` context Reads;
- `U + N + B + G + Z` Writes;
- `D + C + 2U + 2N + 4B + 3G + 4Z` tuple operations across those Writes.

Direct-parent-role Reads use `user:<subject>` and `space:<parent>` in whole-bundle
preflight, whole-bundle reconciliation and the guarded subtree check. Children
Reads use `space:<parent>`, relation `parent`, in preflight and reconciliation.
Authority Checks use `owner` on `platform:root`. Guard Reads use the exact
`guard:<scope>` object/revision relation. Attachment validation enumerates each assigned subject's
direct roles and full committed placement at the checkpoints above. Space batches
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

Creator grants add a paginated direct-role Read on the target organization to the
ordinary grant budget. A one-organization/two-person fixture measures 1 Check,
5 Reads and 1 Write for this grant. Revocation adds no request: existing role inventory checks
the same-scope dependency. Import adds that Read at each dependency checkpoint only
when content is not declared. Batches publish content before eligibility. The
96-user existing-organization fixture fails its second role batch after 96 identity
fences, verifies content without dangling eligibility, then successfully replays.

Personal opening holds its organization SQL lock from guard capture through context,
permission reads, link pagination, row reads and creation commit. With three members,
two existing personal spaces and forced page size 1, creation measures 2 Checks,
5 Reads and 1 Write (5 tuple operations). Reuse with three personal spaces measures
2 Checks, 9 Reads and zero Writes. Exact guard: one Read; roles: 2 then 4 pages;
personal links: 2 then 3 pages; reuse context adds one placement Read. Production
page size stays unset; all continuation pages are read with higher consistency.
The two-open race is concurrency 2, not a throughput measurement. Document count
does not affect lookup. The UI waits for one membership refresh after success.
Model upgrade adds a pinned-model GET and model POST under the platform SQL lock,
then commits only the SQL model pointer; there is no tuple Write.

The actual Make demo artifact (15 users, one new organization, three teams,
28 space grants, four platform grants, four batches, `C=3`, `H=J=Z=E=0`)
exercises HTTP with 28 Checks, 44 Reads and 24 Writes: 91 tuple operations.
Two pre-existing IAM users and 12 space-assigned subjects produce `X=2+12+12=26`
on a fresh Fred store; IAM identity reuse does not attach a person to another Fred instance. The
batch-boundary fixture (105 users, 107 organization grants, 210 team grants, one new
organization and team, no platform grants, `H=J=Z=E=0`) checks 114 Checks, 422 Reads
(`X=3*105=315`, known identities, initially empty roles) and 111 Writes: 550 tuple operations and at most 100 per Write. The demo project variant
(`U=2`, `H=2`, `E=2`) checks 9 Checks and 26 Reads: two subjects with
organization/team roles each cost two Reads at each of three checkpoints. The hierarchy fixture (one
organization, team and project, an organization analyst with a personal space)
checks 4 Reads for `/me/spaces`, and `1 C + 4 Read` and `1 C + 3 Read` for project
and team scopes. These are wire-count assertions in disposable
integration environments, not latency, throughput or scalability measurements.
The pagination fixture has five roles on one organization and forces page size 2:
context takes three Reads. Adding a first member costs six Reads (two guards, three
caller pages, one empty target page), one Check and one Write with five operations.
The two-organization attachment races use concurrency 2; other wire budgets use
one active request/import. No document cardinality contributes to these lookups.

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
calls. Platform changes, all direct space-role grants/revocations, organization creation
and import also use the platform lock and guard; unrelated organization role mutations
therefore serialize at platform level. Context validation runs through the held SQL
connection, avoiding another pool checkout under that lock;
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
held. Each distinct declared owner subject is checked once in that operation; a second
organization attachment is refused before publication.
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
| I1 | `apps/fred-manager/src/domain.rs::parent_rules`<br>`apps/fred-manager/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/fred-manager/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/fred-manager/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors`<br>`apps/fred-manager/tests/integration.rs::blueprint_preflight_reads_child_names_after_organization_lock`<br>`apps/fred-manager/tests/integration.rs::sibling_names_are_unique_and_uncommitted_links_are_ignored`<br>`apps/fred-manager/tests/support/resource_browsing.rs::resource_reads_enforce_scope_and_preserve_cursor_and_role_semantics`<br>`apps/fred-manager/tests/support/resource_browsing.rs::folder_creation_governance_contract_and_request_budget`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_authority_retirement_documents_and_durable_receipts`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_partial_link_loss_reserves_name_and_organization` |
| I2 | `apps/fred-manager/tests/integration.rs::placement_is_immutable_and_folders_stay_in_their_space`<br>`apps/fred-manager/tests/support/resource_browsing.rs::folder_creation_governance_contract_and_request_budget`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_migration_preserves_existing_spaces_and_folders` |
| I3 | `apps/fred-manager/tests/integration.rs::placement_is_immutable_and_folders_stay_in_their_space` |
| I4 | `apps/fred-manager/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/fred-manager/tests/integration.rs::concurrent_revocations_keep_parent_access`<br>`apps/fred-manager/tests/integration.rs::concurrent_grant_and_revoke_keep_the_invariant`<br>`apps/fred-manager/tests/integration.rs::analyst_membership_is_content_and_personal_roles_remain_fixed`<br>`apps/fred-manager/tests/integration.rs::provisioning_replays_every_role_without_updating_identities_or_implicit_content`<br>`apps/fred-manager/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/fred-manager/tests/integration.rs::provisioning_repairs_every_fga_boundary_including_ambiguous_acknowledgments`<br>`apps/fred-manager/tests/integration.rs::import_rechecks_parent_after_wait_and_repairs_existing_space_grants`<br>`apps/fred-manager/tests/integration.rs::a_timed_out_child_grant_cannot_arrive_after_parent_revocation`<br>`apps/fred-manager/tests/integration.rs::a_cancelled_child_grant_is_fenced_after_client_restart`<br>`apps/fred-manager/tests/integration.rs::noop_revocation_and_multiple_scopes_fence_stale_attempts`<br>`apps/fred-manager/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors`<br>`apps/fred-manager/tests/integration.rs::inherited_access_does_not_replace_parent_membership`<br>`apps/fred-manager/tests/integration.rs::personal_open_requires_explicit_eligibility_and_never_repairs_revocation`<br>`apps/fred-manager/tests/integration.rs::import_orders_personal_eligibility_after_content_across_failed_batches`<br>`apps/fred-manager/tests/integration.rs::personal_grant_budget_and_failed_creation_preserve_authority`<br>`apps/fred-manager/tests/lifecycle_temporal.rs::api_worker_restart_schedule_reconciliation_and_replay`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_authority_retirement_documents_and_durable_receipts`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_partial_link_loss_reserves_name_and_organization`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_retention_personal_scope_and_final_guard_commit_failure`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_filtered_batches_lost_ack_and_unrelated_state`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_waiters_recheck_retirement_and_authority_and_accept_once`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_blocked_scope_is_visible_and_does_not_starve_candidates` |
| I5 | `apps/fred-manager/tests/integration.rs::a_revoked_admin_cannot_finish_a_waiting_request`<br>`apps/fred-manager/tests/integration.rs::revoked_platform_actor_cannot_complete_a_waiting_platform_or_owner_grant`<br>`apps/fred-manager/tests/integration.rs::simultaneous_imports_reuse_usernames_and_space_names`<br>`apps/fred-manager/tests/integration.rs::provisioning_waiter_rechecks_revoked_or_expired_operator`<br>`apps/fred-manager/tests/integration.rs::preflight_does_not_block_revocation_and_cancelled_identity_creation_replays`<br>`apps/fred-manager/tests/integration.rs::import_rechecks_parent_after_wait_and_repairs_existing_space_grants`<br>`apps/fred-manager/tests/integration.rs::a_timed_out_platform_grant_cannot_arrive_after_actor_revocation`<br>`apps/fred-manager/tests/integration.rs::noop_revocation_and_multiple_scopes_fence_stale_attempts`<br>`apps/fred-manager/tests/integration.rs::sql_mutation_loses_to_a_delayed_revocation_after_its_check`<br>`apps/fred-manager/tests/integration.rs::folder_creation_keeps_one_connection_through_placement_and_write`<br>`apps/fred-manager/tests/integration.rs::content_http_dispatch_preserves_payload_and_failure_boundaries`<br>`apps/fred-manager/tests/integration.rs::a_late_attachment_cannot_publish_after_assignment_elsewhere`<br>`apps/fred-manager/tests/support/resource_browsing.rs::folder_creation_governance_contract_and_request_budget` |
| I6 | `apps/fred-manager/tests/integration.rs::a_member_with_a_personal_space_can_leave_the_organization`<br>`apps/fred-manager/tests/integration.rs::analyst_membership_is_content_and_personal_roles_remain_fixed`<br>`apps/fred-manager/tests/integration.rs::descending_roles_reach_projects_and_member_stays_local`<br>`apps/fred-manager/tests/integration.rs::personal_open_requires_explicit_eligibility_and_never_repairs_revocation`<br>`apps/fred-manager/tests/integration.rs::personal_open_budgets_exhaust_pages_and_recheck_after_lock_wait`<br>`apps/fred-manager/tests/integration.rs::personal_grant_budget_and_failed_creation_preserve_authority`<br>`apps/fred-manager/tests/support/resource_browsing.rs::resource_reads_enforce_scope_and_preserve_cursor_and_role_semantics`<br>`apps/fred-manager/tests/support/resource_browsing.rs::folder_creation_governance_contract_and_request_budget` |
| I7 | `apps/fred-manager/src/domain.rs::search_scope_is_ancestors_then_self`<br>`apps/fred-manager/tests/integration.rs::scope_follows_ancestors_and_levels_only_narrow_it` |
| I8 | `apps/fred-manager/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/fred-manager/tests/integration.rs::admin_roles_grant_no_content_access`<br>`apps/fred-manager/tests/integration.rs::complete_role_permission_matrix_and_space_isolation`<br>`apps/fred-manager/tests/integration.rs::teams_are_created_by_organization_admins_only`<br>`apps/fred-manager/tests/integration.rs::provisioning_replays_every_role_without_updating_identities_or_implicit_content`<br>`apps/fred-manager/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/fred-manager/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors`<br>`apps/fred-manager/tests/integration.rs::descending_roles_reach_projects_and_member_stays_local`<br>`apps/fred-manager/tests/integration.rs::organization_owners_name_admins_and_read_nothing`<br>`apps/fred-manager/tests/integration.rs::ambiguous_legacy_context_fails_closed_and_remains_repairable`<br>`apps/fred-manager/tests/lifecycle_temporal.rs::api_worker_restart_schedule_reconciliation_and_replay`<br>`apps/fred-manager/tests/support/resource_browsing.rs::resource_reads_enforce_scope_and_preserve_cursor_and_role_semantics`<br>`apps/fred-manager/tests/support/resource_browsing.rs::folder_creation_governance_contract_and_request_budget`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_authority_retirement_documents_and_durable_receipts`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_filtered_batches_lost_ack_and_unrelated_state`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_blocked_scope_is_visible_and_does_not_starve_candidates` |
| I9 | `apps/fred-manager/tests/integration.rs::bootstrap_promotes_one_person_once`<br>`apps/fred-manager/tests/integration.rs::a_finished_bootstrap_stays_closed_after_its_admin_is_removed`<br>`apps/fred-manager/tests/integration.rs::concurrent_retries_finish_a_bootstrap_once`<br>`apps/fred-manager/tests/integration.rs::an_interrupted_bootstrap_is_finished_by_its_caller_only`<br>`apps/fred-manager/tests/integration.rs::consent_and_root_bootstrap_are_personal_and_do_not_create_memberships` |
| I10 | `apps/fred-manager/src/auth.rs::rejects_expired_and_overlong_tokens`<br>`apps/fred-manager/src/auth.rs::lifetime_ceiling_cannot_be_skipped`<br>`apps/fred-manager/src/auth.rs::rejects_missing_kid_and_bad_signature`<br>`apps/fred-manager/src/auth.rs::strict_mode_checks_issuer_and_audience` |
| I11 | `apps/fred-manager/src/blueprint.rs::invalid_declarations_and_duplicate_json_keys_fail_without_echoing_input`<br>`apps/fred-manager/src/keycloak.rs::directory_failures_do_not_echo_credentials_or_payloads`<br>`apps/fred-manager/src/logging.rs::sensitive_and_reserved_fields_never_leak`<br>`apps/fred-manager/src/logging.rs::dependencies_get_a_fixed_message_without_their_fields`<br>`apps/fred-manager/tests/integration.rs::directory_creation_conflict_pagination_preservation_and_failures` |
| I12 | `apps/fred-manager/tests/integration.rs::pagination_survives_deleting_the_cursor_row` |
| I13 | `apps/fred-manager/src/logging.rs::requests_carry_ids_and_end_with_one_http_event` |
| I14 | `apps/fred-manager/tests/integration.rs::concurrent_admin_revocations_leave_one_admin_at_every_level`<br>`apps/fred-manager/tests/integration.rs::organization_owners_name_admins_and_read_nothing`<br>`apps/fred-manager/tests/integration.rs::owner_grants_require_directory_identity_and_deleted_owners_can_be_revoked` |
| I15 | `apps/fred-manager/tests/integration.rs::platform_owners_manage_each_other_and_keep_one`<br>`apps/fred-manager/tests/integration.rs::provisioning_preflight_failures_have_no_identity_space_or_role_writes`<br>`apps/fred-manager/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors` |
| I16 | `apps/fred-manager/src/logging.rs::audit_records_survive_warning_application_threshold`<br>`apps/fred-manager/tests/integration.rs::durable_grants_are_audited_even_when_sql_commit_fails` |
| I17 | `apps/fred-manager/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/fred-manager/tests/integration.rs::provisioning_replays_every_role_without_updating_identities_or_implicit_content`<br>`apps/fred-manager/tests/integration.rs::directory_creation_conflict_pagination_preservation_and_failures`<br>`apps/fred-manager/tests/integration.rs::provisioning_replay_after_identity_and_sql_failures_reuses_committed_state`<br>`apps/fred-manager/tests/integration.rs::simultaneous_imports_reuse_usernames_and_space_names`<br>`apps/fred-manager/tests/integration.rs::provisioning_batches_large_parent_and_child_grants_and_keeps_personal_spaces_apart`<br>`apps/fred-manager/tests/integration.rs::preflight_does_not_block_revocation_and_cancelled_identity_creation_replays`<br>`apps/fred-manager/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/fred-manager/tests/integration.rs::provisioning_repairs_every_fga_boundary_including_ambiguous_acknowledgments`<br>`apps/fred-manager/tests/integration.rs::cancellation_after_fga_write_rolls_back_new_space_and_replays`<br>`apps/fred-manager/tests/integration.rs::import_rechecks_parent_after_wait_and_repairs_existing_space_grants`<br>`apps/fred-manager/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors`<br>`apps/fred-manager/tests/integration.rs::import_orders_personal_eligibility_after_content_across_failed_batches` |
| I18 | `apps/fred-manager/src/blueprint.rs::invalid_declarations_and_duplicate_json_keys_fail_without_echoing_input`<br>`apps/fred-manager/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/fred-manager/tests/integration.rs::provisioning_preflight_failures_have_no_identity_space_or_role_writes`<br>`apps/fred-manager/tests/integration.rs::provisioning_waiter_rechecks_revoked_or_expired_operator`<br>`apps/fred-manager/tests/integration.rs::import_cli_is_read_only_until_authorized_and_requires_initialized_state`<br>`apps/fred-manager/tests/integration.rs::preflight_does_not_block_revocation_and_cancelled_identity_creation_replays`<br>`apps/fred-manager/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/fred-manager/tests/integration.rs::import_rejects_incompatible_model_without_syncing_it`<br>`apps/fred-manager/tests/integration.rs::competing_empty_initializers_converge_on_the_published_binding`<br>`apps/fred-manager/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors`<br>`apps/fred-manager/tests/integration.rs::blueprint_preflight_reads_child_names_after_organization_lock`<br>`apps/fred-manager/tests/integration.rs::startup_refuses_existing_state_without_a_publication`<br>`apps/fred-manager/tests/integration.rs::import_rejects_cross_organization_declarations_before_identity_writes`<br>`apps/fred-manager/tests/integration.rs::import_rechecks_attachment_after_preflight_against_a_waiting_grant`<br>`apps/fred-manager/tests/integration.rs::import_orders_personal_eligibility_after_content_across_failed_batches` |
| I19 | `apps/fred-manager/src/config.rs::active_terms_version_is_explicit_and_validated`<br>`apps/fred-manager/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/fred-manager/tests/integration.rs::import_cli_is_read_only_until_authorized_and_requires_initialized_state`<br>`apps/fred-manager/tests/integration.rs::consent_and_root_bootstrap_are_personal_and_do_not_create_memberships` |
| I20 | `apps/fred-manager/tests/integration.rs::descending_roles_reach_projects_and_member_stays_local`<br>`apps/fred-manager/tests/integration.rs::memberships_list_inherited_spaces_with_their_paths`<br>`apps/fred-manager/tests/integration.rs::personal_open_requires_explicit_eligibility_and_never_repairs_revocation` |
| I21 | `apps/fred-manager/tests/integration.rs::import_cli_is_read_only_until_authorized_and_requires_initialized_state`<br>`apps/fred-manager/tests/integration.rs::organization_owners_name_admins_and_read_nothing`<br>`apps/fred-manager/tests/integration.rs::owner_grants_require_directory_identity_and_deleted_owners_can_be_revoked`<br>`apps/fred-manager/tests/integration.rs::import_rechecks_owner_identity_before_publishing_spaces`<br>`apps/fred-manager/tests/integration.rs::import_checks_distinct_owners_once_with_bounded_concurrency` |
| I22 | `apps/fred-manager/tests/integration.rs::content_http_waiters_recheck_existence_after_deletion`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_waiters_recheck_retirement_and_authority_and_accept_once` |
| I23 | `apps/fred-manager/tests/integration.rs::concurrent_attachments_choose_one_organization_and_creation_cannot_bypass_it`<br>`apps/fred-manager/tests/integration.rs::a_late_attachment_cannot_publish_after_assignment_elsewhere`<br>`apps/fred-manager/tests/integration.rs::ambiguous_legacy_context_fails_closed_and_remains_repairable`<br>`apps/fred-manager/tests/integration.rs::import_rejects_cross_organization_declarations_before_identity_writes`<br>`apps/fred-manager/tests/integration.rs::organization_context_exhausts_pages_and_grant_budget_includes_global_fencing`<br>`apps/fred-manager/tests/integration.rs::business_http_checks_context_while_platform_metadata_stays_available`<br>`apps/fred-manager/tests/integration.rs::import_rechecks_attachment_after_preflight_against_a_waiting_grant`<br>`apps/fred-manager/tests/integration.rs::personal_open_requires_explicit_eligibility_and_never_repairs_revocation`<br>`apps/fred-manager/tests/integration.rs::personal_open_budgets_exhaust_pages_and_recheck_after_lock_wait`<br>`apps/fred-manager/tests/lifecycle_temporal.rs::api_worker_restart_schedule_reconciliation_and_replay`<br>`apps/fred-manager/tests/support/resource_browsing.rs::resource_reads_enforce_scope_and_preserve_cursor_and_role_semantics`<br>`apps/fred-manager/tests/support/resource_browsing.rs::organization_placement_reads_overlap_with_a_bounded_request_budget`<br>`apps/fred-manager/tests/support/resource_browsing.rs::folder_creation_governance_contract_and_request_budget`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_authority_retirement_documents_and_durable_receipts`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_partial_link_loss_reserves_name_and_organization`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_retention_personal_scope_and_final_guard_commit_failure`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_waiters_recheck_retirement_and_authority_and_accept_once` |
| I24 | `apps/fred-manager/tests/lifecycle_temporal.rs::api_worker_restart_schedule_reconciliation_and_replay`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_authority_retirement_documents_and_durable_receipts`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_partial_link_loss_reserves_name_and_organization`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_retention_personal_scope_and_final_guard_commit_failure`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_filtered_batches_lost_ack_and_unrelated_state`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_waiters_recheck_retirement_and_authority_and_accept_once`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_blocked_scope_is_visible_and_does_not_starve_candidates`<br>`apps/fred-manager/tests/support/space_deletion.rs::lifecycle_migration_preserves_existing_spaces_and_folders` |
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
