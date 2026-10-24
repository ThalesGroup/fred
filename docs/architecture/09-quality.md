# 9. Quality and invariants

The guarantees below apply to the named manager mechanisms and first-user journey.
They do not certify every Fred component. Invariant IDs remain stable when the
explanations move between chapters.

## Invariants

| Id | Invariant | Held by |
| --- | --- | --- |
| I1 | An organization is a root, a team's parent is an organization, a project's parent is a non-personal team, a personal space has no parent. Sibling names and organization names are unique. | `domain::check_parent`, `spaces` under the organization lock, organization-name index |
| I2 | Placement is immutable: a space's kind, owner and links, a folder's space, parent and path, a document's space and folder. Names may change; the authorized deletion lifecycle removes retired space links. | SQL placement triggers; matching FGA links published with creation grants before SQL commit |
| I3 | A document's folder, and a sub-folder's parent, belong to the same space. | composite foreign keys |
| I4 | Holding a role on a space requires a direct content role on its parent, and a personal-space role a direct content role on its organization, under any concurrency. Inherited access does not satisfy it. Personal creation eligibility also requires direct organization content. | `spaces`, organization lock and atomic OpenFGA guard |
| I5 | Role and SQL mutations cannot publish a decision invalidated by an earlier successful revocation. External operations are authorized at dispatch. | checks after guard capture, atomic fence, SQL lock through commit |
| I6 | A personal space never gains a member, and its organization can always remove its owner. | `spaces::grant`, `spaces::revoke` |
| I7 | A space's search scope is its ancestors and itself, never its descendants; a personal space's scope is itself; levels only remove spaces. | `spaces::scope` |
| I8 | Space admin, organization owner and platform owner roles read no content. | OpenFGA `can_read = member or effective_editor or effective_analyst` |
| I9 | Root bootstrap promotes one caller, once; it never reopens, not even for its own admin after removal. | `bootstrap::grant_root`, marker |
| I10 | Only an RS256 token signed by the realm, issued by a configured realm for the configured audience, unexpired, with an integer past `iat` and a lifetime within the ceiling, authenticates. | `auth` |
| I11 | Log lines never carry credential- or content-named fields; dependencies never log their own text. | `logging` |
| I13 | Every line of a request carries its request id, and the request ends with one `http` event. | `logging::request_logging` |
| I14 | Every non-personal space retains at least one administrator, and every organization at least one owner, after role revocation. | `spaces::revoke`, organization lock |
| I15 | Platform owners change platform grants and the platform always retains an owner. New platform grants target an existing Keycloak subject. | `platform`, platform lock, directory lookup |
| I16 | Every acknowledged role mutation emits exactly one security audit event before SQL commit, independently of application severity and text/JSON format; revoking a role that is not held emits none. | `logging::audit_relation`, mutation services |
| I17 | Provisioning replay preserves existing identities, committed space IDs and undeclared grants, and repairs requested grants without reusing rolled-back space IDs. | `provisioning`, exact directory lookup, SQL uniqueness |
| I18 | Import requires a platform owner, authenticated at admission and rechecked in OpenFGA at every mutation boundary, and compatible initialized state; predictable preflight failures cause no provisioning or initialization writes. | CLI read-only initialization, HTTP authority-before-upload, `Importer::preflight`, root guard |
| I19 | A human personally accepts the active CGU before business access; consent and root bootstrap create no membership, and import accepts for nobody. | `onboarding`, `OwnUser`, `AdmittedUser`, CLI admission |
| I20 | Editor, admin and analyst reach every descendant space, member stays local, and a personal space inherits nothing. | OpenFGA `effective_*` relations over `parent` links |
| I21 | New organization owner grants target an existing Keycloak subject. An owner exists only on organizations, is named by platform owners, names the organization's admins, and holds no content, management or descending permission. | `spaces::may_change`, directory checks at grant/creation/import, OpenFGA `can_own_organization` |
| I22 | Folder mutations recheck existence under the organization lock; deletion winning that lock prevents a waiting mutation. | HTTP handlers, SQL transaction held through commit |
| I23 | A person holds roles in at most one organization per Fred instance. Business access requires that unique context as well as permission; platform governance is independent. | committed direct roles and placement, context validation, platform lock and guard on attachment writers |
| I24 | Space retirement is atomic; cleanup starts no earlier than the frozen deadline, preserves retry identifiers and declares completion only after SQL/FGA cleanup. | `lifecycle`, retired consumer gates, bounded activities and receipts |
| I25 | A published original has verified immutable bytes; pending reservations protect quota/name/targets, and cleanup never removes a published or live pending object. | upload journal, guarded reservation/publication, conditional S3 Put and SQL-checked inventory |
| I26 | Processing preserves its immutable original and scope; only the current authorized, fenced generation publishes a verified result. | atomic processing intent, stage leases, guarded manifest commit and isolated cleanup |
| I27 | A direct space-role grant writes only a subject usable as an OpenFGA user that the configured user directory knows; a consumed guard is a conflict, a tuple OpenFGA rejects is invalid input. | `domain::valid_subject`, `users::Directory::exists` after authorization, `fga::write_guarded` error codes |
| I28 | A committed processing intent is started at most once and is never lost: a missed notification only delays its delivery. | workflow identity with `REJECT_DUPLICATE`, describe before retry, notification in the admission transaction, periodic poll |

## control-plane tests

| Command (in `apps/control-plane`) | Runs |
| --- | --- |
| `make test` | Unit tests, offline: domain rules, token verification, logging format, request middleware |
| `make test-integration` | Integration tests against throwaway Postgres/OpenFGA, Keycloak and SeaweedFS containers, removed afterwards; each test gets its own database and store |
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
other due operations.

The real Temporal fixture starts the separate binary, interrupts it after the first
folder batch and replays workflow history. It also holds the platform SQL lock while
sending SIGTERM, verifies bounded process exit and release of the server-side wait,
then restarts to completion. An injected SQL delete failure exhausts activity retries,
produces a safe `retrying` receipt and recovers after the fault is removed.

Let `D` be the descendant page Reads. Target placement comes from SQL. Lifecycle discovery requests 96 tuples per page and
exhausts cursors: an organization reads child-team and personal-space pages and
each team's project pages; a team reads project pages; a project reads none.
These counts exclude authentication/admission, SQL and startup.

| Phase | OpenFGA client RPCs and filters | SQL lock boundary |
| --- | --- | --- |
| First acceptance | `4 + D`: platform version Read, owner capability Check, organization version Read, descendant Reads by exact parent/organization subject plus `object=space:`, one four-operation guard Write | Platform then organization locks, held through complete subtree validation, retirement and commit; no Temporal RPC |
| Receipt replay/status | One current platform capability Check | Indexed receipt lookup, no mutation lock for an already committed receipt |
| Ordinary cleanup batch | Five Reads: platform version, organization guard existence, organization version, exact target object, and incoming `user=space:<id>, object=space:`; zero or one Write, at most 96 payload deletes plus four guard operations | One bounded transaction, up to 1000 folder leaves or one tuple batch or one space row; no retention/retry sleep under locks |
| Orphan descendant cleanup | Ordinary five Reads plus at most four filtered Reads per absent descendant level (two placement checks, exact object, incoming references); at most two levels, hence 13 Reads and one guarded Write for a supported chain | SQL existence is checked under the same platform/organization locks before each descent; no SQL space counter increment for ghosts |
| Final organization removal | Seven Reads and one Write with the guard present; recovery after its removal uses five Reads and one platform fence Write | Final root metadata and receipt completion commit together |
| Due candidate selection | No FGA RPC; indexed SQL selection and visit timestamp update | Row locks use `SKIP LOCKED`; at most configured batch size |

Reference cleanup drains fresh first pages; it never reuses a cursor across a
mutation. Current model metadata allows incoming space references only. Guard reads
are exact and independent of role volume. Discovery cost grows with spaces and
hierarchy pages; cleanup cost grows with target tuples, folders and reachable abandoned creations. Unrelated users,
memberships and documents do not induce full-store scans. OpenFGA's internal Check
evaluation work is separate from these client RPC counts.

For SQL-absent descendants, each placement is checked with bounded first pages;
multiple parents or an unsupported depth block cleanup. Grants and descendants
are drained before a separate batch removes their parent/organization anchor.
Each retry rediscovers the remaining work, including after a lost write acknowledgment.
A committed incoming space outside the retired manifest is never deleted.
Disconnected orphan roots are outside this targeted cleanup.

The lifecycle budget fixture has three spaces, 1001 target folders and 243 target
tuples; another organization holds 241 member tuples plus its owner/admin grants.
Its expected acceptance budget is three Reads, one Check and one Write. Six cleanup
attempts, including one committed FGA delete with a lost acknowledgment, bring the
total to 33 Reads, one Check and seven Writes. Assertions cap each Write at 100 tuple
operations and require filtered Reads; SQL progress records 1001 folders and one
space removed while unrelated grants remain.
An additional single-cleanup-stream fixture, run alongside the 85-test integration
suite, has one committed organization, one absent team, 100 absent projects and
240 ghost grants. Alternating lost acknowledgments still converge: 1360 filtered
Reads and 106 Writes in total, with a maximum of 13 Reads per supported orphan
batch. A malformed ghost with 161 parent links blocks after six Reads and no Write.
These counts include retry work; no orphan contributes to the SQL space counter.
Eight concurrent receipt retries in a separate two-space fixture returned one UUID
in 165 ms. These are service elapsed times, not isolated lock-hold measurements or
throughput guarantees. Forced lock waiters verify ordering and retirement rechecks;
atomic subtree acceptance holds its locks for the whole discovery and commit.

Batch counts also determine scheduled latency: one successful batch per operation
per sweep means nested folder depth, tuple pages and descendant space count add
intervals after retention expires. `batch_size` bounds candidate operations, not
batches completed for one operation. The [operations chapter](A3-manager-operations.md#space-deletion-lifecycle)
gives the completion-time model and the 15-level folder example. The millisecond
fixture above invokes batches directly; it does not measure scheduled completion
with the default PT10M interval.

## Generated HTTP contract

`tests/openapi.rs` checks offline, deterministic schema emission with invalid runtime
configuration paths, the complete route inventory, bearer security, role enums,
required nullable response fields, flattening, multipart uploads, original binary reads, processing mutations
and empty success responses. Frontend client tests execute the generated RTK
endpoints through the shared base query and check the multipart bytes, bearer,
completed report, error propagation and flat space responses. Regenerating with
`make -C apps/frontend update-control-plane-api` produces the committed client.

## Provisioning UI acceptance

Frontend component tests cover loading, unavailable and denied authority, duplicate
submit events, pending controls, server counts, report reset, unsupported ZIP,
partial HTTP failure and connection loss. The Playwright journey runs the actual
Fred UI and generated slice against the manager governance router, with real
Keycloak login/service credentials, PostgreSQL and OpenFGA. It imports the Make
ZIP, replays without changing space IDs, imports a project variant, checks hierarchy
and roles, rejects a member, lets a second platform owner replay, and displays
legacy-format refusal. Desktop and narrow screenshots exercise the shared layout.

The browser recipe exercises personal consent, bootstrap, import/replay, same-browser
account switch, manager memberships and explicit personal opening. Non-migrated
service requests are refused by the fixture and their normal UI errors are accepted;
manager operations still use real governance services. The original page destinations
remain reachable, and organization information is checked in Profile rather than Home.
Each run owns its database, FGA store and Keycloak container. The frontend command
`make test-provisioning-browser` invokes this journey and the integration suite.

Focused frontend regressions cover complete route registration, standalone account
pages, original Home widgets, team navigation, personal-command races and failures,
and profile roles/preferences/organization loading, errors and account isolation.
Manager API tests retain consent, provisioning and role-isolation coverage independently
of the UI. These fixtures do not certify every Fred component.

## Organization console acceptance

Focused HTTP integration tests exercise consent/owner authority, exact known
accounts, distinct or identical nominees, unique names, conflicting attachment,
revocation during a platform-lock wait, and FGA failures before or after publication.
Two concurrent creators sharing a nominee commit at most one organization. Registry
pagination uses 102 rows, one retired, and obtains the 101 active rows in two pages
without duplication. The successful empty-target creation fixture records two Checks,
four Reads and two Writes; each registry page records one Check and no Read/Write.
These fixtures establish correctness and RPC counts, not latency or throughput.

Frontend tests cover list loading/error/empty states, cursor navigation, creation,
duplicate submission and late completion. Stateful boundary tests preserve a draft
through normal focus refresh and block cached authority throughout error/retry.
Owner direct business URLs redirect to Organizations, including mixed-role owners;
ordinary users keep the business subtree. The owner navigation mounts no business
bootstrap hook. These checks do not replace a deployed visual recipe.

## Resource browsing acceptance

Focused API tests cover containment, role semantics, paged search/order/ancestors,
concurrent duplicate creation, revocation waiters, stable identities after rename
and atomic document-bearing subtree refusal. A concurrent SQL reader/writer fixture
checks page/total consistency. Component tests exercise the original controls,
stale completions, pending deletion deduplication, recovery after the last page becomes empty and document
write refusal, alongside the separate knowledge-base consumer. These checks do not
replace visual acceptance on a deployed instance.

## OpenFGA request costs

Direct roles and permission-evaluated links live in OpenFGA; immutable placement
is also recorded in SQL. The client uses `Check`, paginated
`Read` and `Write`; it does not issue `ListObjects`, `ListUsers`, `Expand` or `BatchCheck`.
`Check` and `Read` request `HIGHER_CONSISTENCY`. A content check addresses one
user, permission and space; the model evaluates descending roles through at most two
`parent` links inside OpenFGA. A fixed number of HTTP calls does not specify OpenFGA's
datastore work, latency or throughput.

The frontend area boundary, navigation, provisioning guard and profile share one cached `/me` query.
Navigation and page subscribers refetch `/me` data older than 60 seconds when
they mount; this threshold does not schedule periodic refresh. The mounted profile
also refreshes on window focus or an explicit retry after failure; the area boundary
revalidates on focus for both platform and business areas.
Concurrent subscribers deduplicate the request. Home navigation, scoped navigation
and Profile share `/me/spaces`; Profile requests a fresh result on mount and window
focus. Scoped navigation revalidates cached data older than 60 seconds on mount.
Space selection uses those memberships; Resources adds directory reads and retains its statistics/quota service reads. Each `/me` network fetch performs
the four concurrent platform Checks listed below; it does not select an organization; `/me/spaces` uses the tuple and link Reads listed below. There is no additional import-specific FGA query; ordinary non-migrated background consumers keep their own request behavior. The
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
`P_c(s)` counts the Read pages of a space's children; `P_o(s)` counts its
personal-space pages. `P_d` counts the pages of a user's direct roles on one space.
Guard reads return at most one matching tuple. Other Read counts vary with
pagination, including empty results.
`Q(u) = P_u` Reads resolves a subject's organization, followed by one SQL query
selecting distinct `organization_id` values for the direct-grant space IDs.
The resolver filters FGA roles by `user=user:<u>, object=space:`, exhausts every page,
ignores IDs absent from SQL and includes retired rows. It fails on distinct
organization IDs and grants no permission. Context and target loading perform zero
FGA placement Reads. `/me/spaces` reuses its already-read roles with the same SQL
resolver before filtering active rows and enumerating descendants.
`Q` counts client RPCs, not OpenFGA server evaluation work.

| Operation | OpenFGA calls | Read filter or decision scope |
| --- | --- | --- |
| Combined directory (`/entries`) | `Q(caller) + 2 C` | Unique context, target placement, current read and write decisions on that space; zero Writes |
| Content access; authorize document/space | `Q(caller) + 1 C` | Unique caller context, target placement, exact permission; a foreign context short-circuits before Check |
| Authorize platform | `1 C` | Exact platform permission; no business context |
| Authorize scope | `Q(caller) + 1 C` | Target placement, caller context, then read permission Check |
| `GET /me` | `4 C`, concurrent | Caller's four effective platform roles |
| `GET /me/spaces` | `P_u + sum P_c(s) Read` | Direct roles and SQL placement; all child pages of each organization and team reached by a descending role, concurrent per level |
| Team registry page | `1 C` | Platform registry permission; SQL placement for at most 100 returned teams |
| Organization registry page | `1 C` | Owner Check; SQL selects at most 101 active rows and returns 100; no tuple/identity enumeration or advisory lock |
| HTTP create organization | `2 C + W(2) + 2 R_g + sum Q(distinct target) + W(6)` | Preflight and guarded owner Checks; two exact directory lookups (one for identical usernames) before locking; Owner/Admin grants only |
| List platform grants | `1 C + P_p Read` | Owner check, then all subjects/roles on `platform:root` |
| Grant platform role | `1 R_g + 1 C + W(3)` | Actor owner; separate Keycloak subject lookup |
| Revoke platform role | `1 R_g + 1 C + P_p Read + W(3)` | All platform grants are read to locate one direct grant and another owner |
| Grant organization owner | `Q(target) + 2 R_g + 1 C + W(5)` | Platform and organization guards; actor platform owner; separate Keycloak subject lookup |
| Grant organization admin | `Q(caller) + Q(target) + 2 R_g + 1-2 C + W(5)` | Actor manages organization, else owns it |
| Grant other organization role | `Q(caller) + Q(target) + 2 R_g + 1 C + W(5)` | Actor manages organization |
| Grant team/project role | `Q(caller) + Q(target) + 2 R_g + 1 C + P_d Read + W(5)` | Actor manages space; target's direct parent roles |
| Revoke space role | `Q(caller) + 2 R_g + 1-2 C + P_u Read + P_c(s) Read + W(4 + d)` | Target's direct roles across all spaces; children (an organization adds `P_o(s)` personal-space Reads); the second Check is only for an organization admin change |
| Revoke a held admin or owner role on a non-personal space | Previous row + `P_a(s) Read` | All direct holders of that role; an owner revocation omits `Q(caller)` and uses the independent platform-owner Check |
| Create team or project | `Q(caller) + Q(admin) + 1 R_g + 1 C + P_d Read + P_c(parent) Read + W(4)` | Actor manages parent; nominated admin's direct parent roles; sibling names; link and admin in one Write |
| Create personal space | `Q(caller) + 1 R_g + 2 C + W(5)` | Organization read and explicit eligibility; one indexed SQL lookup finds no active personal space; link, member and editor in one Write |
| Reuse personal space | `Q(caller) + 1 R_g + 2 C + 1 Read` | Organization and personal read; the indexed SQL lookup, then that space's own organization link; no SQL/FGA mutation |
| Public configuration, personal onboarding and consent | `0` | SQL bootstrap/acceptance reads or consent upsert only |
| Root bootstrap | `1 R_g + W(3)` | Bearer/secret and SQL marker govern admission |

HTTP organization creation holds the platform advisory lock from name reservation
through new-guard initialization, both guard reads, current caller/target checks,
FGA publication and SQL commit. Keycloak lookup precedes the lock. The final Write
contains two role inserts and four guard-version operations. Target membership
pages determine its FGA read cost; total users/documents do not.
The registry's SQL page size determines its returned volume. These are client RPC
counts, separate from OpenFGA's internal Check evaluation.

`d` is 1 when the revoked role exists, otherwise 0. A successful absent space-role
revocation still advances its guard. A platform-role revoke returns 404 when absent.
SQL folder mutations use `Q(caller) + 1 R_g + 1 C + W(2)`;
the fence contains no role change. Existing-object mutation adds one indexed SQL
existence read under the organization lock (I22), independently of document count. Each successful guard replacement adds two
operations per scope, independent of the number of existing roles.

Sources: [client](../../apps/control-plane/src/fga.rs),
[space mutations, memberships and scope](../../apps/control-plane/src/spaces.rs),
[platform mutations](../../apps/control-plane/src/platform.rs), and
[HTTP handlers](../../apps/control-plane/src/api.rs).

## Folder navigation and write costs

Resources issues one combined directory request on entry, navigation, search, sort
or page change and when the window regains focus, in addition to shared
admission/membership queries. While the displayed page contains a `pending` or
`running` processing summary, it refreshes after three seconds between completed
requests. Inactive pages do not poll; hidden pages do not issue the scheduled
refresh and regain fresh data on window focus. Remote changes on an inactive page
are discovered on focus or navigation, rather than on a periodic timer. Its response
contains current read-authorized rows and a write decision: `Q` Reads and
2 Checks, zero Writes. No separate write probe or document listing is issued.
Folder mutations, uploads and processing starts invalidate the directory query.
The upload path resolves a folder-name conflict through the same `/entries` listing,
selecting an exact folder name from its typed, paginated results. A failed read hides cached
write authority until a fresh successful decision; it does not grant permission.

Mutations cost `Q + 1` Reads, 1 Check and 1 Write containing two guard-version
operations. Stored tuple count is unchanged: no folder tuple is created or deleted.
Target placement precedes locking; guard Read, context resolution, Check, fence,
local mutation and SQL commit occur while the organization lock is held.
Contending content writers use `pg_try_advisory_xact_lock`, roll back each failed
attempt and release the connection before a 50 ms retry delay. Acquisition has a
five-second deadline, including pool checkout and failed attempts after the initial
placement lookup; expiry returns the existing 503 dependency-unavailable response.
No guard or permission RPC runs during retries. I5 and I22 still apply after
acquisition, with the same connection held through checks, fence and commit.

The process shares a ten-connection pool. Content lock contenders do not retain
connections during retry delays, allowing another organization to acquire one;
active transactions and other blocking lock paths can still exhaust this pool.
Different organizations have independent locks; replicas share these database
locks and OpenFGA guards. There is no FIFO guarantee between retrying writers.
Each failed attempt adds a begin/try-lock/rollback SQL cycle, at most one attempt
per 50 ms delay plus SQL time for each waiting request. Same-organization throughput
remains limited by lock residency, and an available lock may wait until the next
retry. This mechanism does not increase the pool size or remove fencing RPCs.

The directory query has no advisory lock. Total, mixed folder/document page,
selected rows, processing summaries and up to 15 ancestors use one read-only
repeatable-read transaction. Count and page share the same selection. Root/child
predicates use `IS NULL` or equality on the existing space/parent/name indexes of
folders and documents. Search is a literal case-insensitive substring limited to
255 characters. Counts, substring searches, creation-date sorting and deep
offsets still examine work proportional to the directory; limiting returned rows
does not make that work constant. Recursive deletion scales with the removed
subtree and its foreign-key checks, under the organization lock.

The disposable `folder_scaling` fixture uses 10,000 folders: a root, 9,985
immediate children and a branch reaching depth 15. It requests `/entries`, the
Resources endpoint, including document counts and processing-summary reads even
when the fixture contains only folders. A listing returns 50 folder entries.
With one organization editor role its expected directory budget is one Read and
two Checks. With 40 additional team-member roles and forced pages of ten tuples,
`Q=5`: five Reads and two Checks. Folder mutations add one guard Read and one
Write, with one permission Check. No placement Reads or folder tuples are added.
These source-derived budgets do not establish latency or throughput. Same-organization
writes still serialize; pagination, SQL query work and FGA Check evaluation remain
cardinality-dependent. The model traverses at most two parents independently of
folder depth. The fixture samples lock residency and request latency when executed. Its
source-derived budgets are not measured results for this endpoint; folder-only
listing measurements do not establish the mixed directory's latency or throughput.

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
Authority Checks use `platform_owner` on `platform:root`. Guard Reads use the exact
`guard:<scope>` object/revision relation. Attachment validation enumerates each assigned subject's
direct-role pages and SQL placement at the checkpoints above. Space batches
contain at most 96 link and role inserts plus four guard operations; a new space's
`parent` link shares its first batch. Platform grants contain
three operations, with only the platform guard. FGA calls are sequential. Multi-page direct-role or child lists add their extra
pages at each corresponding traversal.
HTTP adds one owner Check before upload reading. CLI adds that Check plus two GETs
(configured-store discovery and pinned-model verification). Model evaluation remains
inside OpenFGA; these RPC counts do not measure its internal work.

The [importer](../../apps/control-plane/src/provisioning.rs) holds the platform lock
per identity dispatch, then platform plus all declared organization locks through
reconciliation commit. Mutations needing those locks wait at most five seconds and
then answer 503, so reconciliation length bounds their unavailability; the operator's
bearer lifetime does not bound the import. Organizations are locked in UUID order; child name resolution
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
permission reads, the personal-space lookup and creation commit. With forced page size 1,
creation expects 2 Checks, 3 Reads and 1 Write (5 tuple operations); reuse expects
2 Checks, 6 Reads and zero Writes, whether two or five other members have personal
spaces. Exact guard: one Read; roles: 2 then 4 pages; reuse reads its own link: one
page. The other members' personal spaces never enter the budget. Production
page size stays unset; all continuation pages are read with higher consistency.
The two-open race is concurrency 2, not a throughput measurement. Document count
does not affect lookup. The UI waits for one membership refresh after success.

The actual Make demo artifact (15 users, one new organization, three teams,
28 space grants, four platform grants, four batches, `C=3`, `H=J=Z=E=0`)
exercises HTTP with 28 Checks, 44 Reads and 24 Writes: 91 tuple operations.
Two pre-existing IAM users and 12 space-assigned subjects produce `X=2+12+12=26`
on a fresh Fred store; IAM identity reuse does not attach a person to another Fred instance. The
batch-boundary fixture (105 users, 107 organization grants, 210 team grants, one new
organization and team, no platform grants, `H=J=Z=E=0`) checks 114 Checks, 422 Reads
(`X=3*105=315`, known identities, initially empty roles) and 111 Writes: 550 tuple operations and at most 100 per Write. The demo project variant
(`U=2`, `H=2`, `E=2`) expects 9 Checks and 20 Reads: two subjects with
organization/team roles each cost one Read at each of three checkpoints. The hierarchy fixture (one
organization, team and project, an organization analyst with a personal space)
expects 3 Reads for `/me/spaces`, and `1 C + 1 Read` for both project
and team scopes. These are wire-count assertions in disposable
integration environments, not latency, throughput or scalability measurements.
The pagination fixture has five business roles (including personal-space eligibility)
on one organization, a separate organization owner, and forces page size 2:
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
for ordering and per-space role selection; each level of its walk keeps at most
`fga::READ_CONCURRENCY` (8) children Reads in flight, whatever the number of teams
(20 teams, 50 ms per Read: peak 8). Space revocation tests child membership in `O(R * D)`
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
Local candidate search is one SQL query: the four prefix indexes are combined by a
bitmap OR (checked by `EXPLAIN` on 20 000 profiles), then at most 20 rows are sorted;
the statement is planned with its pattern so that the indexes stay usable.
Each platform grant also checks its subject. Every direct space-role grant adds one
subject lookup after authorization, under its locks: a Keycloak GET, or one indexed
SQL query in the local directory. Organization creation adds one subject GET. Every directory request has a
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
| I1 | `apps/control-plane/src/domain.rs::parent_rules`<br>`apps/control-plane/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/control-plane/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/control-plane/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors`<br>`apps/control-plane/tests/integration.rs::blueprint_preflight_reads_child_names_after_organization_lock`<br>`apps/control-plane/tests/integration.rs::space_and_folder_names_are_unique_in_canonical_form`<br>`apps/control-plane/tests/integration.rs::sibling_names_are_unique_and_uncommitted_links_are_ignored`<br>`apps/control-plane/tests/support/organization_console.rs::organization_console_creation_authority_roles_failures_and_budget`<br>`apps/control-plane/tests/support/resource_browsing.rs::resource_reads_enforce_scope_and_role_semantics`<br>`apps/control-plane/tests/support/resource_browsing.rs::sql_placement_matches_fga_hierarchy_and_context`<br>`apps/control-plane/tests/support/resource_browsing.rs::folder_creation_governance_contract_and_request_budget`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_authority_retirement_documents_and_durable_receipts`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_partial_link_loss_reserves_name_and_organization` |
| I2 | `apps/control-plane/tests/integration.rs::placement_is_immutable_and_folders_stay_in_their_space`<br>`apps/control-plane/tests/support/document_processing.rs::processing_admission_fences_publication_and_original_survival`<br>`apps/control-plane/tests/support/document_processing.rs::processing_upload_atomic_intent_and_retry_without_new_original`<br>`apps/control-plane/tests/support/document_processing.rs::processing_workload_identity_and_revoked_publication`<br>`apps/control-plane/tests/support/document_processing.rs::processing_admission_request_budget_at_one_and_one_hundred_documents`<br>`apps/control-plane/tests/support/document_storage.rs::document_contract_guards_and_shared_project_quota`<br>`apps/control-plane/tests/support/document_storage.rs::document_creation_reads_conflicts_receipts_and_safe_download`<br>`apps/control-plane/tests/support/resource_browsing.rs::folder_creation_governance_contract_and_request_budget`<br>`apps/control-plane/tests/support/resource_browsing.rs::folder_directory_pages_and_atomic_subtree_lifecycle` |
| I3 | `apps/control-plane/tests/integration.rs::placement_is_immutable_and_folders_stay_in_their_space`<br>`apps/control-plane/tests/support/document_processing.rs::processing_admission_fences_publication_and_original_survival`<br>`apps/control-plane/tests/support/document_processing.rs::processing_upload_atomic_intent_and_retry_without_new_original`<br>`apps/control-plane/tests/support/document_processing.rs::processing_workload_identity_and_revoked_publication`<br>`apps/control-plane/tests/support/document_storage.rs::document_contract_guards_and_shared_project_quota`<br>`apps/control-plane/tests/support/document_storage.rs::document_creation_reads_conflicts_receipts_and_safe_download` |
| I4 | `apps/control-plane/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/control-plane/tests/integration.rs::concurrent_revocations_keep_parent_access`<br>`apps/control-plane/tests/integration.rs::concurrent_grant_and_revoke_keep_the_invariant`<br>`apps/control-plane/tests/integration.rs::analyst_membership_is_content_and_personal_roles_remain_fixed`<br>`apps/control-plane/tests/integration.rs::provisioning_replays_every_role_without_updating_identities_or_implicit_content`<br>`apps/control-plane/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/control-plane/tests/integration.rs::provisioning_repairs_every_fga_boundary_including_ambiguous_acknowledgments`<br>`apps/control-plane/tests/integration.rs::import_rechecks_parent_after_wait_and_repairs_existing_space_grants`<br>`apps/control-plane/tests/integration.rs::a_timed_out_child_grant_cannot_arrive_after_parent_revocation`<br>`apps/control-plane/tests/integration.rs::a_cancelled_child_grant_is_fenced_after_client_restart`<br>`apps/control-plane/tests/integration.rs::noop_revocation_and_multiple_scopes_fence_stale_attempts`<br>`apps/control-plane/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors`<br>`apps/control-plane/tests/integration.rs::inherited_access_does_not_replace_parent_membership`<br>`apps/control-plane/tests/integration.rs::personal_open_requires_explicit_eligibility_and_never_repairs_revocation`<br>`apps/control-plane/tests/integration.rs::import_orders_personal_eligibility_after_content_across_failed_batches`<br>`apps/control-plane/tests/integration.rs::personal_grant_budget_and_failed_creation_preserve_authority`<br>`apps/control-plane/tests/lifecycle_temporal.rs::api_worker_restart_schedule_reconciliation_and_replay`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_authority_retirement_documents_and_durable_receipts`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_partial_link_loss_reserves_name_and_organization`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_retention_personal_scope_and_final_guard_commit_failure`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_filtered_batches_lost_ack_and_unrelated_state`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_waiters_recheck_retirement_and_authority_and_accept_once`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_blocked_scope_is_visible_and_does_not_starve_candidates` |
| I5 | `apps/control-plane/tests/integration.rs::a_revoked_admin_cannot_finish_a_waiting_request`<br>`apps/control-plane/tests/integration.rs::revoked_platform_actor_cannot_complete_a_waiting_platform_or_owner_grant`<br>`apps/control-plane/tests/integration.rs::simultaneous_imports_reuse_usernames_and_space_names`<br>`apps/control-plane/tests/integration.rs::provisioning_waiter_rechecks_revocation_but_not_bearer_expiry`<br>`apps/control-plane/tests/integration.rs::preflight_does_not_block_revocation_and_cancelled_identity_creation_replays`<br>`apps/control-plane/tests/integration.rs::import_rechecks_parent_after_wait_and_repairs_existing_space_grants`<br>`apps/control-plane/tests/integration.rs::a_timed_out_platform_grant_cannot_arrive_after_actor_revocation`<br>`apps/control-plane/tests/integration.rs::noop_revocation_and_multiple_scopes_fence_stale_attempts`<br>`apps/control-plane/tests/integration.rs::sql_mutation_loses_to_a_delayed_revocation_after_its_check`<br>`apps/control-plane/tests/integration.rs::folder_creation_keeps_one_connection_through_placement_and_write`<br>`apps/control-plane/tests/integration.rs::a_late_attachment_cannot_publish_after_assignment_elsewhere`<br>`apps/control-plane/tests/support/document_storage.rs::document_revocation_cleanup_and_late_put_recovery`<br>`apps/control-plane/tests/support/organization_console.rs::organization_console_creation_authority_roles_failures_and_budget`<br>`apps/control-plane/tests/support/organization_console.rs::organization_console_rechecks_waiting_creator_and_serializes_attachment`<br>`apps/control-plane/tests/support/resource_browsing.rs::folder_creation_governance_contract_and_request_budget` |
| I6 | `apps/control-plane/tests/integration.rs::a_member_with_a_personal_space_can_leave_the_organization`<br>`apps/control-plane/tests/integration.rs::analyst_membership_is_content_and_personal_roles_remain_fixed`<br>`apps/control-plane/tests/integration.rs::descending_roles_reach_projects_and_member_stays_local`<br>`apps/control-plane/tests/integration.rs::personal_open_requires_explicit_eligibility_and_never_repairs_revocation`<br>`apps/control-plane/tests/integration.rs::personal_open_budgets_exhaust_pages_and_recheck_after_lock_wait`<br>`apps/control-plane/tests/integration.rs::personal_grant_budget_and_failed_creation_preserve_authority`<br>`apps/control-plane/tests/support/resource_browsing.rs::resource_reads_enforce_scope_and_role_semantics`<br>`apps/control-plane/tests/support/resource_browsing.rs::folder_creation_governance_contract_and_request_budget` |
| I7 | `apps/control-plane/src/domain.rs::search_scope_is_ancestors_then_self`<br>`apps/control-plane/tests/integration.rs::scope_follows_ancestors_and_levels_only_narrow_it` |
| I8 | `apps/control-plane/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/control-plane/tests/integration.rs::admin_roles_grant_no_content_access`<br>`apps/control-plane/tests/integration.rs::complete_role_permission_matrix_and_space_isolation`<br>`apps/control-plane/tests/integration.rs::teams_are_created_by_organization_admins_only`<br>`apps/control-plane/tests/integration.rs::provisioning_replays_every_role_without_updating_identities_or_implicit_content`<br>`apps/control-plane/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/control-plane/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors`<br>`apps/control-plane/tests/integration.rs::descending_roles_reach_projects_and_member_stays_local`<br>`apps/control-plane/tests/integration.rs::organization_owners_name_admins_and_read_nothing`<br>`apps/control-plane/tests/integration.rs::ambiguous_context_fails_closed_and_remains_repairable`<br>`apps/control-plane/tests/lifecycle_temporal.rs::api_worker_restart_schedule_reconciliation_and_replay`<br>`apps/control-plane/tests/support/document_storage.rs::document_publication_rechecks_token_and_terms_without_locking_remote_io`<br>`apps/control-plane/tests/support/document_storage.rs::document_creation_reads_conflicts_receipts_and_safe_download`<br>`apps/control-plane/tests/support/document_storage.rs::document_revocation_cleanup_and_late_put_recovery`<br>`apps/control-plane/tests/support/resource_browsing.rs::resource_reads_enforce_scope_and_role_semantics`<br>`apps/control-plane/tests/support/resource_browsing.rs::folder_creation_governance_contract_and_request_budget`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_authority_retirement_documents_and_durable_receipts`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_filtered_batches_lost_ack_and_unrelated_state`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_blocked_scope_is_visible_and_does_not_starve_candidates` |
| I9 | `apps/control-plane/tests/integration.rs::bootstrap_promotes_one_person_once`<br>`apps/control-plane/tests/integration.rs::a_finished_bootstrap_stays_closed_after_its_admin_is_removed`<br>`apps/control-plane/tests/integration.rs::concurrent_retries_finish_a_bootstrap_once`<br>`apps/control-plane/tests/integration.rs::an_interrupted_bootstrap_is_finished_by_its_caller_only`<br>`apps/control-plane/tests/integration.rs::consent_and_root_bootstrap_are_personal_and_do_not_create_memberships` |
| I10 | `apps/control-plane/src/auth.rs::rejects_expired_and_overlong_tokens`<br>`apps/control-plane/src/auth.rs::lifetime_ceiling_cannot_be_skipped`<br>`apps/control-plane/src/auth.rs::rejects_missing_kid_and_bad_signature`<br>`apps/control-plane/src/auth.rs::issuer_and_audience_are_always_checked` |
| I11 | `apps/control-plane/src/blueprint.rs::invalid_declarations_and_duplicate_json_keys_fail_without_echoing_input`<br>`apps/control-plane/src/keycloak.rs::directory_failures_do_not_echo_credentials_or_payloads`<br>`apps/control-plane/src/logging.rs::sensitive_and_reserved_fields_never_leak`<br>`apps/control-plane/src/logging.rs::dependencies_get_a_fixed_message_without_their_fields`<br>`apps/control-plane/tests/integration.rs::directory_creation_conflict_pagination_preservation_and_failures`<br>`apps/control-plane/tests/integration.rs::a_stopped_lifecycle_worker_reports_only_its_stage` |
| I13 | `apps/control-plane/src/logging.rs::requests_carry_ids_and_end_with_one_http_event` |
| I14 | `apps/control-plane/tests/integration.rs::concurrent_admin_revocations_leave_one_admin_at_every_level`<br>`apps/control-plane/tests/integration.rs::organization_owners_name_admins_and_read_nothing`<br>`apps/control-plane/tests/integration.rs::owner_grants_require_directory_identity_and_deleted_owners_can_be_revoked` |
| I15 | `apps/control-plane/tests/integration.rs::platform_owners_manage_each_other_and_keep_one`<br>`apps/control-plane/tests/integration.rs::provisioning_preflight_failures_have_no_identity_space_or_role_writes`<br>`apps/control-plane/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors` |
| I16 | `apps/control-plane/src/logging.rs::audit_records_survive_warning_application_threshold`<br>`apps/control-plane/tests/integration.rs::only_effective_role_changes_are_audited_once`<br>`apps/control-plane/tests/integration.rs::durable_grants_are_audited_even_when_sql_commit_fails` |
| I17 | `apps/control-plane/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/control-plane/tests/integration.rs::provisioning_replays_every_role_without_updating_identities_or_implicit_content`<br>`apps/control-plane/tests/integration.rs::directory_creation_conflict_pagination_preservation_and_failures`<br>`apps/control-plane/tests/integration.rs::provisioning_replay_after_identity_and_sql_failures_reuses_committed_state`<br>`apps/control-plane/tests/integration.rs::simultaneous_imports_reuse_usernames_and_space_names`<br>`apps/control-plane/tests/integration.rs::provisioning_batches_large_parent_and_child_grants_and_keeps_personal_spaces_apart`<br>`apps/control-plane/tests/integration.rs::preflight_does_not_block_revocation_and_cancelled_identity_creation_replays`<br>`apps/control-plane/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/control-plane/tests/integration.rs::provisioning_repairs_every_fga_boundary_including_ambiguous_acknowledgments`<br>`apps/control-plane/tests/integration.rs::cancellation_after_fga_write_rolls_back_new_space_and_replays`<br>`apps/control-plane/tests/integration.rs::import_rechecks_parent_after_wait_and_repairs_existing_space_grants`<br>`apps/control-plane/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors`<br>`apps/control-plane/tests/integration.rs::import_orders_personal_eligibility_after_content_across_failed_batches` |
| I18 | `apps/control-plane/src/blueprint.rs::invalid_declarations_and_duplicate_json_keys_fail_without_echoing_input`<br>`apps/control-plane/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/control-plane/tests/integration.rs::provisioning_preflight_failures_have_no_identity_space_or_role_writes`<br>`apps/control-plane/tests/integration.rs::provisioning_waiter_rechecks_revocation_but_not_bearer_expiry`<br>`apps/control-plane/tests/integration.rs::import_cli_is_read_only_until_authorized_and_requires_initialized_state`<br>`apps/control-plane/tests/integration.rs::preflight_does_not_block_revocation_and_cancelled_identity_creation_replays`<br>`apps/control-plane/tests/integration.rs::real_keycloak_service_account_provisions_complete_bundle`<br>`apps/control-plane/tests/integration.rs::import_rejects_incompatible_model_without_syncing_it`<br>`apps/control-plane/tests/integration.rs::competing_empty_initializers_converge_on_the_published_binding`<br>`apps/control-plane/tests/integration.rs::blueprint_http_hierarchy_isolation_preflight_and_safe_errors`<br>`apps/control-plane/tests/integration.rs::blueprint_preflight_reads_child_names_after_organization_lock`<br>`apps/control-plane/tests/integration.rs::startup_refuses_existing_state_without_a_publication`<br>`apps/control-plane/tests/integration.rs::import_rejects_cross_organization_declarations_before_identity_writes`<br>`apps/control-plane/tests/integration.rs::import_rechecks_attachment_after_preflight_against_a_waiting_grant`<br>`apps/control-plane/tests/integration.rs::import_orders_personal_eligibility_after_content_across_failed_batches` |
| I19 | `apps/control-plane/src/config.rs::active_terms_version_is_explicit_and_validated`<br>`apps/control-plane/tests/browser_provisioning.rs::provisioning_browser_journey`<br>`apps/control-plane/tests/integration.rs::import_cli_is_read_only_until_authorized_and_requires_initialized_state`<br>`apps/control-plane/tests/integration.rs::consent_and_root_bootstrap_are_personal_and_do_not_create_memberships` |
| I20 | `apps/control-plane/tests/integration.rs::descending_roles_reach_projects_and_member_stays_local`<br>`apps/control-plane/tests/integration.rs::memberships_list_inherited_spaces_with_their_paths`<br>`apps/control-plane/tests/integration.rs::personal_open_requires_explicit_eligibility_and_never_repairs_revocation` |
| I21 | `apps/control-plane/tests/integration.rs::import_cli_is_read_only_until_authorized_and_requires_initialized_state`<br>`apps/control-plane/tests/integration.rs::organization_owners_name_admins_and_read_nothing`<br>`apps/control-plane/tests/integration.rs::owner_grants_require_directory_identity_and_deleted_owners_can_be_revoked`<br>`apps/control-plane/tests/integration.rs::import_rechecks_owner_identity_before_publishing_spaces`<br>`apps/control-plane/tests/integration.rs::import_checks_distinct_owners_once_with_bounded_concurrency` |
| I22 | `apps/control-plane/tests/integration.rs::content_http_waiters_recheck_existence_after_deletion`<br>`apps/control-plane/tests/support/document_processing.rs::processing_admission_fences_publication_and_original_survival`<br>`apps/control-plane/tests/support/document_processing.rs::processing_existing_worker_journey_without_kf_http`<br>`apps/control-plane/tests/support/document_processing.rs::processing_upload_atomic_intent_and_retry_without_new_original`<br>`apps/control-plane/tests/support/document_processing.rs::processing_workload_identity_and_revoked_publication`<br>`apps/control-plane/tests/support/document_processing.rs::processing_admission_request_budget_at_one_and_one_hundred_documents`<br>`apps/control-plane/tests/support/document_storage.rs::document_contract_guards_and_shared_project_quota`<br>`apps/control-plane/tests/support/document_storage.rs::document_publication_rechecks_token_and_terms_without_locking_remote_io`<br>`apps/control-plane/tests/support/document_storage.rs::document_creation_reads_conflicts_receipts_and_safe_download`<br>`apps/control-plane/tests/support/document_storage.rs::document_revocation_cleanup_and_late_put_recovery`<br>`apps/control-plane/tests/support/document_storage.rs::shared_swift_bucket_cleanup_preserves_foreign_objects_and_reclaims_owned_late_writes`<br>`apps/control-plane/tests/support/document_storage.rs::cleanup_inaccessible_original_does_not_starve_other_objects`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_waiters_recheck_retirement_and_authority_and_accept_once` |
| I23 | `apps/control-plane/tests/integration.rs::business_routes_share_one_authorization_answer`<br>`apps/control-plane/tests/integration.rs::concurrent_attachments_choose_one_organization_and_creation_cannot_bypass_it`<br>`apps/control-plane/tests/integration.rs::a_late_attachment_cannot_publish_after_assignment_elsewhere`<br>`apps/control-plane/tests/integration.rs::ambiguous_context_fails_closed_and_remains_repairable`<br>`apps/control-plane/tests/integration.rs::import_rejects_cross_organization_declarations_before_identity_writes`<br>`apps/control-plane/tests/integration.rs::organization_context_exhausts_pages_and_grant_budget_includes_global_fencing`<br>`apps/control-plane/tests/integration.rs::business_http_checks_context_while_platform_metadata_stays_available`<br>`apps/control-plane/tests/integration.rs::import_rechecks_attachment_after_preflight_against_a_waiting_grant`<br>`apps/control-plane/tests/integration.rs::personal_open_requires_explicit_eligibility_and_never_repairs_revocation`<br>`apps/control-plane/tests/integration.rs::personal_open_budgets_exhaust_pages_and_recheck_after_lock_wait`<br>`apps/control-plane/tests/lifecycle_temporal.rs::api_worker_restart_schedule_reconciliation_and_replay`<br>`apps/control-plane/tests/support/organization_console.rs::organization_console_creation_authority_roles_failures_and_budget`<br>`apps/control-plane/tests/support/organization_console.rs::organization_console_registry_pagination_excludes_retired_and_costs_one_check`<br>`apps/control-plane/tests/support/organization_console.rs::organization_console_rechecks_waiting_creator_and_serializes_attachment`<br>`apps/control-plane/tests/support/resource_browsing.rs::resource_reads_enforce_scope_and_role_semantics`<br>`apps/control-plane/tests/support/resource_browsing.rs::sql_placement_matches_fga_hierarchy_and_context`<br>`apps/control-plane/tests/support/resource_browsing.rs::organization_context_reads_only_role_pages`<br>`apps/control-plane/tests/support/resource_browsing.rs::folder_creation_governance_contract_and_request_budget`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_authority_retirement_documents_and_durable_receipts`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_partial_link_loss_reserves_name_and_organization`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_retention_personal_scope_and_final_guard_commit_failure`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_waiters_recheck_retirement_and_authority_and_accept_once` |
| I24 | `apps/control-plane/tests/lifecycle_temporal.rs::api_worker_restart_schedule_reconciliation_and_replay`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_authority_retirement_documents_and_durable_receipts`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_partial_link_loss_reserves_name_and_organization`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_retention_personal_scope_and_final_guard_commit_failure`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_filtered_batches_lost_ack_and_unrelated_state`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_waiters_recheck_retirement_and_authority_and_accept_once`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_blocked_scope_is_visible_and_does_not_starve_candidates`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_aborted_creation_graph_does_not_block_cleanup`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_orphan_pages_keep_anchors_through_lost_acknowledgments`<br>`apps/control-plane/tests/support/space_deletion.rs::lifecycle_orphans_cannot_expand_the_committed_manifest_or_depth` |
| I25 | `apps/control-plane/tests/support/document_processing.rs::processing_admission_fences_publication_and_original_survival`<br>`apps/control-plane/tests/support/document_processing.rs::processing_existing_worker_journey_without_kf_http`<br>`apps/control-plane/tests/support/document_processing.rs::processing_upload_atomic_intent_and_retry_without_new_original`<br>`apps/control-plane/tests/support/document_processing.rs::processing_workload_identity_and_revoked_publication`<br>`apps/control-plane/tests/support/document_processing.rs::retrieval_delivery_restarts_closed_failure_and_preserves_running_execution`<br>`apps/control-plane/tests/support/document_storage.rs::document_creation_reads_conflicts_receipts_and_safe_download`<br>`apps/control-plane/tests/support/document_storage.rs::document_revocation_cleanup_and_late_put_recovery`<br>`apps/control-plane/tests/support/document_storage.rs::shared_swift_bucket_cleanup_preserves_foreign_objects_and_reclaims_owned_late_writes`<br>`apps/control-plane/tests/support/document_storage.rs::cleanup_inaccessible_original_does_not_starve_other_objects` |
| I26 | `apps/control-plane/tests/support/document_processing.rs::processing_admission_fences_publication_and_original_survival`<br>`apps/control-plane/tests/support/document_processing.rs::processing_existing_worker_journey_without_kf_http`<br>`apps/control-plane/tests/support/document_processing.rs::processing_upload_atomic_intent_and_retry_without_new_original`<br>`apps/control-plane/tests/support/document_processing.rs::processing_workload_identity_and_revoked_publication`<br>`apps/control-plane/tests/support/document_processing.rs::retrieval_delivery_restarts_closed_failure_and_preserves_running_execution` |
| I27 | `apps/control-plane/tests/integration.rs::grants_require_a_known_valid_subject_and_classify_openfga_errors` |
| I28 | `apps/control-plane/tests/support/document_processing.rs::processing_existing_worker_journey_without_kf_http`<br>`apps/control-plane/tests/support/document_processing.rs::processing_dispatch_wakes_on_commit_and_prefers_new_intents` |
<!-- end generated -->

Provisioning tests inject failures before/after real FGA writes, fail deferred SQL commits,
and cancel after identity creation and FGA acknowledgment. Replay assertions check preserved
committed IDs, fresh IDs after rollback and restored grants. Gates force preflight/revocation
and cancellation interleavings; batch tests exceed the FGA write limit. CLI subprocess tests
verify token/mapping refusals, zero-count setup diagnostics (including after SQL errors),
migration-table absence and unchanged FGA models on failure
and success. The real Keycloak test configures a distinct `control-plane` client with the
three declared realm-management grants, builds the real Make ZIP and imports it
over HTTP. It verifies every platform role, unchanged existing profiles/passwords,
visible spaces, additive replay and a nonempty-project variant. HTTP tests cover
homonymous hierarchy isolation, whole-bundle preflight, owner declarations, limits
and safe dependency failures. A lock-wait regression commits a conflicting personal
space before preflight resumes and verifies that no identity is created.

## Original storage costs and failure evidence

`CONTROL_PLANE_BROWSER_DOCUMENTS_ONLY=1 make -C apps/control-plane test-browser`
exercises the document journey with real OIDC, PostgreSQL, OpenFGA and SeaweedFS,
while processing services are unavailable. It drops a successful upload's response
at the browser fetch boundary, checks receipt recovery without a second POST,
reloads the folder and compares the downloaded original byte-for-byte and by SHA-256.
A mixed import checks explicit conflicts and preservation of the existing original.
Desktop and narrow captures record the existing Resources layout; they are not a
mobile-layout acceptance test.

Using `Q` above, a fresh successful upload performs `3 * Q + 2`
Reads, three space-write Checks and two Writes of two guard operations each.
The first context/Check occurs before body IO; each guarded SQL phase adds an
exact version Read, context resolution, Check and fence before commit. Direct-role
pagination determines FGA RPC cost; document count and file size add no FGA
calls or tuples. Checks' internal evaluation work is not measured by RPC count.
A combined directory uses `Q` Reads and two Checks. Individual metadata,
receipt, summary and download authorization uses `Q` Reads and one Read Check.
Receipt acknowledgment reuses that authorization. Cleanup issues no FGA call.

The storage budget fixture has five users, one organization, one team, two direct
writer roles, one 128 KiB original and upload concurrency one. With roles fitting
one page, its expected upload budget is five Reads, three Checks and two Writes
(four guard operations). Directory access costs one Read and two Checks with one
or 101 document rows. Synthetic metadata rows do not claim additional stored objects.
The implementation bounds admitted spool bytes by upload permits times file ceiling,
and streams verification/download through 64 KiB buffers. SDK, TLS, HTTP framing
and runtime allocations are additional memory. The browser keeps at most three
upload requests active and one original Blob of at most 100 MiB.
No body or S3 IO retains the organization lock. SQL mutation lock waits are bounded
to 5 s and statements to 15 s; FGA calls remain inside both guarded transactions.
Same-organization writers therefore serialize there. RPC budgets do not estimate
upload latency or throughput.

Failure fixtures cover concurrent same-name and shared-team quota reservations,
malformed/oversized bodies, lost acknowledgments, token expiry, consent withdrawal,
revocation during Put, FGA outage/fence failure, provider outage, cleanup-backlog
admission, slow download consumers and missing originals. Cleanup tests force
expiration, late Put after Delete, a contended organization, competing replicas,
paginated inventory and SQL outage, preserving every published original. A bucket
contract test refuses enabled lifecycle expiration and checks conditional writes,
read-back hash/length and paginated inventory. These bounded fixtures establish
contracts and request budgets, not production capacity or a universal provider claim.


Shared-bucket inventory lists every object under the configured root, including
Swift originals and derived artifacts. Non-input keys cause no SQL renewal or
object HEAD. Input candidates query SQL, and unknown candidates require an ownership
HEAD before deletion. A HEAD failure defers that journal item and advances the
inventory conservatively. The disposable regressions preserve unmarked Swift
objects, another installation's originals and outputs, reclaim late owned writes
after receipt expiry, and verify progress past an inaccessible original.

With the default 100 keys per 30-second sweep, one million keys require at least
83 hours for one complete scan, excluding IO and failures. This is a configuration
bound, not a measured production capacity. Monitor `inventory_completed_at`,
`orphan_bytes` and cleanup retries; larger corpora need measured batch/interval
sizing. Uploads include a full original read-back; indexing reads written vectors
back and manager verifies artifact bytes before publication. KF callback reads
currently time out after 30 seconds while individual manager S3 calls can take
120 seconds; a slow verification can therefore trigger activity retries. These
fixtures do not establish throughput or latency at the configured maximum sizes.


## Processing request costs and evidence

Processing adds no per-document OpenFGA tuples. Start/retry and final publication
reuse the guarded space-write path: resolve placement, acquire the organization
SQL lock, read its guard revision, exhaust actor membership pages, check space
Write, replace the guard revision, then commit SQL. Derived object verification
precedes that transaction. Membership pagination drives FGA RPC count; ancestor
depth affects the model's internal Check evaluation;
document/chunk count drives SQL, object and vector work, not authorization tuples.
Status/preview/original access uses the corresponding current-space checks.
Preparation claims verify actor authority without granting space roles. Later
stage claims check the bound operation and fence; original reads and final
publication recheck actor authority. Cleanup uses the persisted operation scope and makes no FGA writes.

The processing budget fixture has five users, one organization, one team and two
writer memberships. At 1 and 100 document rows, with concurrency 1 and 8 and one
tuple per Read page, start expects three Reads, one Check and one Write per request:
one guard Read and two direct-role pages. Final publication has the same budget.
The Write replaces one guard tuple; the Check asks `can_write` on the owning space.
There are no placement Reads. Concurrent matching keys return one attempt; the
100-row fixture contains one real original and 99 metadata-only rows.
Authorization runs inside the guarded SQL transaction; object and Temporal IO stay
outside it. A concurrent revocation/publication fixture queues both behind the
organization lock, revokes first and rejects publication. These fixtures carry RPC
and behavior assertions, not production latency or capacity guarantees.

Focused integration tests cover admission races, idempotent upload choices,
stale stage claims, workload identity, revoked publication, generation cleanup and
original preservation. The opt-in `processing_dispatch_wakes_on_commit_and_prefers_new_intents`
uses real Temporal without a KF worker: a committed admission is delivered well
before a 60-second poll, a new intent is leased ahead of running work due for
reconciliation, and an intent admitted while the dispatcher is stopped, or made due
without a notification, is delivered at startup or by the poll. The opt-in `processing_existing_worker_journey` uses real
Temporal, PostgreSQL/pgvector, OpenFGA and S3, with local identity/model protocol
fixtures and no KF HTTP server. It checks unchanged worker decoding, independent
profiles, text/PDF/CSV/Office outputs, persisted raw/native previews, lost dispatch
acknowledgment, completed-run reconciliation, actual worker-process restart,
populated vector-collection isolation and original byte equality. Simulated model
and renderer failures exercise explicit retries against the same stored original.
A no-ACK attempt past its admission horizon expires without creating a Temporal
execution. These are bounded
integration fixtures, not a production throughput or browser visual campaign.
