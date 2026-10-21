## Proven offline

Run in `apps/frontend` on branch `feat/self-test-families`, 2026-10-20.

| Command                                                                                      | Result                                                    |
| -------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| `make code-quality`                                                                          | tsc, prettier and eslint clean                            |
| `make test`                                                                                  | 369 files passed, 1 skipped; 4496 tests passed, 7 skipped after review fixes |
| `npx vitest run src/rework/features/pipeline/scenarios src/rework/components/pages/admin/SelfTestPage` | 164 tests passed after review fixes |

Every family scenario is unit-tested with fakes beside it, under
`apps/frontend/src/rework/features/pipeline/scenarios/`: a passing deployment
with full cleanup, and at least one failing deployment per claim. The page test
covers registry order, Run all continuing after a family that throws, the
credential-expiry check staying out of Run all, and the authorization extras
staying inside the authorization family.

The format fixtures were fed to the default `fast` profile's processors from
`apps/knowledge-flow-backend/config/configuration_prod.yaml`, outside the
platform: each of text, Markdown, JSON Lines, PDF, Word, Excel and PowerPoint
extracted its marker, and the CSV rendered its marker row.

## First live run

Local Docker Compose stack with Keycloak, 2026-10-20, every family but
knowledge: 78 passed, 6 failed, 35 skipped. The platform, identity,
authorization, teams and observability families passed. Fixed since:

- Enrollment in the personal space was refused (HTTP 409) after an interrupted
  run left an agent under the fixed self-test name, which took out the agents,
  prompts, conversations and web research families. Each enrollment now gets
  its own name.
- Generated-client failures were reported as `[object Object]`; they now carry
  the status and the backend's detail.
- The inactive-conversations query was called without its argument object.
- The name-conflict, conversation-listing and disabled-agent checks could pass
  without testing anything; they now skip, or require the 409 refusal.

The knowledge family was interrupted by a sign-in redirect. The cause was
the local realm, not this change: its SSO idle timeout (60 s) was shorter
than the access token lifetime (300 s), so the refresh token expired before
the first refresh. Restored to the template value of 1800 s.

## Pgvector live run

Local Docker Compose and Keycloak, 2026-10-20 16:42 UTC. Knowledge Flow API and
worker selected `storage.vector_store.type: pgvector` with collection
`fred_selftest_pgvector_20261020`; OpenSearch operations were disabled for
Knowledge Flow. Its `/knowledge-flow/v1/os/health` returned HTTP 404. The
other services still used their existing OpenSearch KPI/log settings, so this
proves the vector-search path without OpenSearch, not a wholly OpenSearch-free
deployment.

Run all: **192 passed, 5 failed, 7 skipped, 204 steps**. Knowledge: 30/32
passed; hybrid, semantic and strict direct searches all found the ALPHA marker;
CSV and Excel SQL checks each returned the marker row. The link into BETA did
not become retrievable after 41,052 ms. The non-retrievable document remained
searchable. Agent edits failed twice with HTTP 403, saying the template access
had been revoked. The SVG stream failed the safety check: inline
`image/svg+xml` without a sandbox policy. Search-cluster health skipped on HTTP
404; the metrics backend also skipped. The other families were green apart
from expected identity, authorization and security skips.

The pre-cleanup store audit reported all **10 run documents consistent** in
81 ms. Folder and agent cleanup succeeded; the post-cleanup audit found no
anomaly for those 10 document UIDs in 46 ms. That audit returns anomalies only:
it cannot prove that a document still present consistently in all stores is
absent. A later local commit adds a direct search for those UIDs to catch a
surviving searchable chunk. The three follow-up commits that skip dependent
steps and strengthen post-delete search have fake-backed unit tests.

## Second pgvector live run

Run all from `http://localhost:5173`, 2026-10-20 17:52:27 UTC, after the
self-test fixes: **190 passed, 5 failed, 9 skipped, 204 steps**. The five
failures were the same platform defects. The BETA link still failed after
41,657 ms, and its dependent unlink assertion skipped with "linking into BETA
was not proven". The non-retrievable check still returned the document; its
dependent recovery assertion skipped with "non-retrievability was not proven".
This accounts exactly for the change from 192 passed and 7 skipped in the
first run, with the failure count unchanged.

Hybrid, semantic and strict direct search again found the ALPHA marker. The
pre-cleanup audit found **10 run documents consistent** in 62 ms. After folder
deletion, the strengthened check passed in 82 ms: **no audit anomaly or search
hit for the 10 deleted document UIDs**. The search-cluster health check skipped
because the deployment has no search cluster. The agents' two HTTP 403s and
the unsafe inline SVG response recurred. All other families passed apart
from the expected environment skips.

The five failures are platform defects. The agent update gate
(`control_plane_backend/product/service.py:2964`) caused both 403s. Document
link saves tags only to metadata (`features/metadata/service.py:448`), while
pgvector filters indexed chunk tags (`core/stores/vector/pgvector_store.py:452`).
Pgvector inherits an unsupported retrievability method
(`core/stores/vector/base_vector_store.py:104`), and
`features/metadata/service.py:747-755` swallows its error. Raw content streams
inline SVG without a sandbox (`features/content/content_controller.py:428-453`).
The earlier unlink and retrievable-on passes were self-test limits because
their prerequisites failed; they now skip in that case. The old post-delete
check proved only that the audit returned no anomalies; a direct search now
also checks for surviving searchable chunks by run document UID.

Isolated pytest reproductions outside the self-test, stored only under
`/tmp/selftest-pgvector-20261020/`, failed as expected:

- Agent exemption: `test_repro_agent_exemption.py` raised `EnrollmentError`
  at `product/service.py:2971` when disabling an exempt harness instance.
- Linked document: `test_repro_linked_document.py` persisted `['alpha',
  'beta']` in metadata while the pgvector chunk retained `['alpha']` and
  `_matches_tag_ids(..., ['beta'])` returned false.
- SVG stream: `test_repro_svg_stream.py` returned HTTP 200 semantics with
  `content-type: image/svg+xml` and inline disposition, without CSP or
  `nosniff`.
- Audit: `test_repro_audit_session_attachment.py` reported
  `orphan_vectors` for a session-scoped attachment; an independent OpenSearch
  delete test showed `params={'conflicts': 'proceed'}` without `refresh`.
- Pgvector retrievability: `test_repro_pgvector_retrievable.py` raised
  `NotImplementedError` from `base_vector_store.py:104`. The live API log also
  recorded that the vector index was unchanged after the toggle.

The backend defects are tracked separately: [A agent update](https://github.com/ThalesGroup/fred/issues/3198),
[B folder link](https://github.com/ThalesGroup/fred/issues/3199),
[C inline SVG](https://github.com/ThalesGroup/fred/issues/3200),
[D session-vector audit](https://github.com/ThalesGroup/fred/issues/3201),
[D OpenSearch deletion visibility](https://github.com/ThalesGroup/fred/issues/3202),
and [pgvector retrievability](https://github.com/ThalesGroup/fred/issues/3203).

## Remaining limits

- The post-delete check combines the audit with public search. A document
  retained consistently in all stores but no longer readable through the
  deleted folder can still evade both checks; no current browser API exposes
  an exact per-UID store inventory.
- The second live run confirms the dependent-step skips and the strengthened
  post-delete check. It does not establish an exact per-UID inventory across
  every underlying store.
- The SVG exploitability depends on how a deployment opens the preview; this
  run proves the unsafe response headers and inline content type.

## Branch review

An independent, read-only review covered `origin/swift` at `1cfde953` through
`c42f552be`: all 60 changed files, affected frontend consumers, backend route
contracts, the migration note, and OpenSpec artifacts. The uncommitted
verification edit was excluded. The review found four self-test limits.
Fixture IDs are now saved before post-create assertions (`f439548dd`), the
team check verifies its personal copy is gone (same commit), report copying
is disabled during a run (`64e1de005`), and fixture names carry their run
token (`33011510d`). The generic cleanup helper still trusts a successful
delete response for some sessions, prompts, and agents because the current
dependency contract has no exact read-after-delete method for every object.
This is a remaining limit of the branch and should be resolved before
declaring full cleanup proven.

The follow-up read-only review covered `c42f552be` through `529e8d9fd` and
found no new regression. It confirmed the ID, naming and report-action fixes,
and retained the delete-verification limit above. Frontend `make code-quality`
and `make test` passed after these commits; the full test run covered 4496
passing tests and 7 skips, with 77.21% statement coverage across the frontend.

## Authorization and deletion regression coverage (21 October)

The authorization scenario now accepts only HTTP 403 or 404 as a denial for a
valid non-admin token. Its three missing, malformed and altered-signature
sweeps each have a route-leak case. The shared authorization probe applies the
same rule to platform-admin and team-write checks. A team permissions read
that fails no longer becomes an empty permission list. The temporary prompt's
DELETE must return 204 and a subsequent GET must return 404; a creation
response without a prompt ID fails and names the possible leftover fixture
for manual cleanup.

The common post-delete assertion now rejects 401, 429 and 5xx. Prompt and
conversation reads in spaces still owned by the caller require 404. Fake and
HTTP-adapter tests cover each of these responses; the focused scenario suite
passed with 176 tests in 15 files. This is local unit evidence only: the
authorization and deletion changes have not been rerun against the live stack.

The full frontend `make code-quality` and `make test` passed: 371 test files
passed and 1 skipped; 4,529 tests passed and 7 skipped. Statement coverage
was 77.30% overall and 92.07% for the family scenario directory.

An independent read-only review of the new working diff against
`9e299f156` covered the authorization probes, deletion assertions, their
consumers, tests and OpenSpec updates. It found that a successful prompt POST
without an ID could leave a fixture whose generated name was absent from the
error. The error now includes that name; automatic cleanup is still impossible
without the ID. The reviewer found no other actionable issue in this focused
scope. The earlier full-branch review remains the coverage for prior commits.

## Second-account probe (21 October)

The Keycloak form still accepts a selected account and password. For an OIDC
provider, including Entra ID, the separate probe accepts an API access token
from another browser session. Both tokens must return different canonical user
IDs from `/frontend/bootstrap` before the authorization probe runs. The probe
checks both directions for the personal team, prompts, sessions and agent
instances: the owner must receive HTTP 200 and the other account HTTP 403 or
404. The token field clears when the run starts; no token is put in the report.

Fake-backed tests cover the successful path, same identity, bootstrap HTTP
401/403/500 and missing identity, owner denial, foreign HTTP 200/401/500 and
foreign HTTP 404, plus provider-specific UI and token clearing. Focused
scenario and page tests: 32 passed. Frontend `make code-quality` passed.
Frontend `make test` passed: 372 files passed, 1 skipped; 4,546 tests passed,
7 skipped. Statement coverage was 77.24% overall and 92.22% for the scenario
directory. A separate read-only review of this working diff against HEAD found
no actionable issue; it did not re-review the full branch against `origin/swift`.

No live Entra ID run has been performed. The local application services were
stopped at the developer's request; this evidence proves the local code paths
with fakes and the frontend suite, not provider interoperability in a running
deployment. The pasted access token stays in the browser's memory during the
run and must remain valid until the probe completes.

## Deeper two-account isolation (21 October)

The separate probe now verifies that each caller's `/teams` list includes its
own personal team and excludes the other personal team. It checks both
directions for team metadata, prompts, prompt context, categories, commands,
agent templates, sessions and agent instances. For any collaborative team
exclusive to one account, it checks the member's metadata access and the
other account's refusal on eight member-only content routes; this step skips
when neither account has an exclusive team.

In each personal space the probe creates a run-named prompt, verifies the
owner's exact read and the other account's refusal, then attempts a foreign
prompt write. It looks up the run command and verifies the exact prompt's ID,
name and text before scheduling deletion. Each successful DELETE is followed
by an owner GET that must return 404. Fake cases include a write persisted
despite HTTP 403, an owner create persisted despite HTTP 500, a mismatched
create-response ID, and a command collision with an existing user prompt.
The collision fails without deleting the existing prompt.

Focused authorization scenario suite: 3 files, 90 tests passed. Frontend
`make code-quality` passed. Full `make test` passed after the sandbox-blocked
theme test was rerun with local execution permission: 372 files passed, 1
skipped; 4,578 tests passed, 7 skipped. Statement coverage was 77.35% overall
and 92.65% for the scenario directory. An independent read-only review of the
new scenario, fake tests, token adapter and backend route contracts against
HEAD `983d246` found no remaining actionable issue after the cleanup fix;
it was not a full review of the branch against `origin/swift`.

If creation persists but the owner cannot read the command or exact prompt,
the probe cannot safely identify it for deletion. It fails and reports the
run-named prompt for manual cleanup. The local services remain stopped, so
these new checks have no live Keycloak or Entra ID evidence yet.

## Authorization family presentation (21 October)

Authorization is last in the family registry, so it is last on the page, in
Run all and in the combined report. An informational notice before the family's
step report explains the access checks, the conditional foreign-team check,
and the separate second-account and session-expiry actions. The page test
passed with 19 tests; frontend typecheck, targeted ESLint, Prettier and
`git diff --check` passed. The frontend suite was not repeated for this
presentation-only follow-up. No live run was possible while the application
services remained stopped.

## Expected account roles (21 October)

Optional direct platform-role and multi-team expectations now run with either
Keycloak credentials or an OIDC access token. All 32 platform-role sets have
fake coverage. Real access probes cover 12 platform routes, 19 projected team
permissions, four member routes and a temporary prompt write. Only verified
run fixtures are deleted, including writes persisted before an error.
Inaccessible private-team grants and uninspectable denied writes explicitly
skip their unprovable claims. KPI HTTP 503 skips only with the same admin baseline.

Focused checks: 216 tests passed in six files. Full frontend `make test`:
373 files passed, one skipped; 4,680 tests passed, seven skipped. Statement
coverage: 77.54% overall, 92.90% for scenarios. Typecheck, Prettier, ESLint
and `git diff --check` passed. Root `make code-quality` stopped before its
Python migration tests because `uv` is unavailable. The `openspec` CLI is
also unavailable; no CLI validation or archive is claimed.

A bounded independent review against HEAD `31a400061` covered the role
scenario, token adapters, form, helper and backend FGA/route contracts. Its
unsafe fixture cleanup and inaccessible-team proof findings were addressed;
no remaining actionable finding was reported. This is not a full branch review.

The developer confirmed the prior Entra ID state works on 21 October. No raw
report or counts were supplied. That confirmation covers the previous state,
not the new expected-role controls or automatic mutation campaign. Services
remain stopped locally.

## Focused isolation and role campaign (21 October)

The developer narrowed the automatic campaign to about 100 actual checks,
explicitly rejecting an exhaustive matrix hidden behind fewer report rows.
The implementation no longer calls the full role or second-account scenarios.
It executes six platform profiles (none and each role alone), six team profiles
per visibility (nonmember, member, editor, analyst, charter-resolved admin,
and admin/editor/analyst union), reciprocal personal-space reads, platform-admin
team isolation, revocation and recovery. Platform access uses a representative
route per role; team content checks use prompts. This is deliberately bounded
coverage, not every endpoint or Cartesian role combination. The earlier 32-set
evidence above refers to offline tests of expected-role comparisons only.

Fake tests verify exactly 98 scenario steps plus one transport step, hence
99 normal checks; an interruption adds at most one step. They also cap actual
HTTP requests including setup/recovery at 400 on the full successful fake run,
so reduction is not just presentation. All five platform roles are exercised
independently; the charter decides active versus pending team administrator.

The original root keeps its roles. The target's original direct grants and
run-team/prompt intentions are saved before mutation without credentials.
Recovery independently attempts every original grant and verified fixture,
persists partial cleanup, and retains the journal if incomplete. No existing
team content or personal-space content is mutated by this campaign. A browser
lock excludes same-origin campaign/recovery tabs; concurrent administration
in other browsers and automatic teardown after browser closure are not promised.

Focused checks: 238 tests passed in eight files, including 26 campaign tests,
eight transport tests and the page controls. Both charter states, access leaks,
projection mismatches, expired credentials, cancellation, lost create responses,
failed role restoration, persisted refused writes and interrupted cleanup have
fake coverage. Independent campaign reviews against working HEADs `20a589d49`
and `fbdc7b8ff` found the pending-admin POST contract and unjournaled personal/
existing-team writes; these were corrected, then superseded by the focused
engine. The final focused engine and migration/UX documentation review found
no remaining actionable issue. It did not execute a live campaign.

The full-branch independent review covered local `origin/swift`/merge base
`1cfde953717d661d6c9a059aa2ff492da374b27d` through HEAD `20a589d49` and the
then-current working tree: family scenarios, adapters, identity, reports, UI,
backend contracts and documentation. Three additional self-test defects were
fixed separately: strict copy-conflict code (`d3a8bbb9b`), effective sandbox
restrictions (`86e27e16d`), and stopping new families after navigation
(`fbdc7b8ff`). Follow-up review confirmed those dispositions. Their 38 focused
tests passed. The campaign's later narrowing is covered by its separate review.

Local services remain stopped. No new live Keycloak or Entra ID campaign has
been run; the earlier developer Entra confirmation predates this feature.
Root `make code-quality` still stops at the migration-test prerequisite because
`uv` is unavailable. The absent `openspec` CLI prevents CLI validation/archive.
No push, new GitHub issue or PR was performed.

Final frontend verification for this narrowed implementation: `make test`
passed with **376 files passed, one skipped; 4,741 tests passed, seven skipped**.
Statement coverage: 77.81% overall and 93.09% for scenario files. `npm run
typecheck`, `npm run lint`, `npm run format` and `git diff --check` passed.
The existing global Python prerequisite remains blocked as stated above;
this is not a claim that root quality or live campaign validation passed.

## Single role/isolation campaign (21 October)

The supplied live report was the previous observation-only path: 30 passed,
9 failed, one skipped, 40 steps. The target account had no direct/effective
platform roles while four were manually expected. Those nine failures were
expectation mismatches and corresponding HTTP 403s, not proof of a role leak.
Reciprocal personal catalog/exact prompt isolation and cleanup passed there.

The developer requested a single campaign, no team or role selection, and at
most 150 actual checks. The observation-only action, manual expectation form,
old scenarios and their dead hook entry points were removed. Shared permission
expectations remain in rolePermissions.ts. The old scenario-specific tests
were replaced by campaign, permission-contract and exact fixture identity
regressions, rather than retaining an uncallable alternate implementation.

The campaign now adds seven platform routes for both no-role/admin profiles,
three delegated allow checks, four additional reciprocal personal catalogs,
personal-team discovery, exact admin-owned prompt isolation and foreign write,
and member/session/agent own/foreign team reads for member/nonmember profiles.
Fake successful paths assert exactly 148 scenario checks plus one transport
check = 149, including restoration; interruption adds at most one. The fake
also bounds setup/probe/recovery HTTP requests at 500, distinct from report
checks. Both active and pending charter states satisfy the same budget.

Personal exact fixture and foreign write execute while the test account is
platform admin, but only in the current admin's personal space. This permits
verified recovery without the second credential; reverse exact fixtures and
foreign writes are deliberately excluded. All eight personal catalog reads
remain reciprocal. Personal prompt intentions use the same credential-free
journal and exact identity checks; recovery accepts only the recorded admin's
personal team or the verified disposable collaborative teams.

Independent read-only review against cd06d8a42 covered removals, route gates,
consumer integrations, personal recovery and budget; no actionable defect
remained. It did not validate a live campaign, and its attempted test run had
no completed result due to environment constraints. Author focused evidence:
69 tests passed in four files before the additional fixture-helper regressions.
Typecheck passed; final complete frontend verification recorded below.

The global gate still stops before migration tests: `make: uv: No such file
or directory` (Makefile:421). The openspec CLI remains unavailable. No backend
fix, application startup, push, new issue or PR was performed.

Final single-campaign frontend verification: full `make test` passed with
375 files passed, one skipped; 4,610 tests passed, seven skipped. Ten additional
fixture-helper tests added after full-suite collection passed separately.
Typecheck, lint, Prettier and `git diff --check` passed. Overall statement
coverage for that full run: 77.71%.

### Developer live campaign report

The developer supplied the actual 149-step campaign report: **146 passed,
3 failed, 0 skipped**; the transport step took 101,802 ms. All failures (steps
55, 64, 75) were GET `/teams/4400a8e0c814436db0e80e0dccb587ea/sessions`
returning 200 for a public-team nonmember. Private session denials, personal
isolation, role transitions, prompt cleanup, both team deletions and restoration
to the original empty platform-role set passed. This validates the campaign's
149-step budget in a real run while exposing one backend guard defect.

Isolated controller wiring reproduction under `/tmp/selftest-public-team-sessions-20261021/`:
1 failed, 1 passed in 3.58s. The handler uses CAN_READ instead of
CAN_READ_CONVERSATIONS (product/api.py:1804, teams/service.py:1011, schema.fga:134/160).
The passing companion verifies authenticated-owner filtering; the supplied
report has no response bodies, so cross-user session disclosure is not proven.
No direct duplicate was found in read-only GitHub searches; closed issue 2146
is related, open issue 2770 addresses different runtime identity semantics.
A single English issue draft is prepared locally, awaiting user confirmation.
No backend fix or GitHub write has been performed.

## Session membership fix

The three role-campaign failures (public-team session list returning HTTP 200
to a non-member) are fixed in the Control Plane: `get_team_sessions` now
requires `CAN_READ_CONVERSATIONS` (team members only) instead of the default
`CAN_READ`, which public visibility also satisfies.
`apps/control-plane-backend/tests/test_product_api_authz.py` covers the guard
permission, the canonical team ID and owner filter, and that a denial stops
before any session lookup.

Using `apps/control-plane-backend/.venv/bin/python -m pytest --noconftest`
on that file: **17 passed**. `ruff check` and `ruff format --check` on the
touched files: passed. `make test` stalls in the shared conftest's SQLite
schema setup (as before) and was not completed. A fresh two-account
campaign run against restarted backends is still pending.
