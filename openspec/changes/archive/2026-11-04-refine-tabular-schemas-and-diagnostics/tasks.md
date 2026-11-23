## 1. Targeted compact descriptions

- [x] 1.1 Add exact `table_names` selection before value scans and the selected-dataset limit; verify omitted/empty/default, targeted, duplicate, unknown, ambiguous and unauthorized selectors with service/controller tests and assertions that unselected artifacts are not read.
- [x] 1.2 Project compact public column responses with `categorical_values`, numeric-only bounds and no legacy flags; keep stored classification readable and stop computing two-value verdicts. Verify exact category casing, changed/empty current categories, null numeric bounds, legacy metadata and CSV/Excel response parity.
- [x] 1.3 Update category/table-selection references in the SQL/tabular prompts, add approved 4A/4B only to the packaged tabular prompt, and update tool parameter descriptions, frontend schema parsing/rendering and generated Knowledge Flow OpenAPI/client; verify new and historical trace shapes and unchanged recorded call arguments.

## 2. Correct temporal ingestion

- [x] 2.1 Preserve recognized Excel temporal dtypes through extraction and Parquet export without partial conversion data loss; verify native/text dates, blanks, mixed invalid/ambiguous values, timezone meaning and no-coercion behavior through physical schema and value round trips.
- [x] 2.2 Verify current CSV temporal inference and describe/query parity, and document truthful typing of unchanged historical string artifacts and explicit reprocessing of the synthetic campaign workbook only; confirm unreprocessed VARCHAR is never advertised as datetime.

## 3. Scoped SQL diagnostics

- [x] 3.1 Enrich supported binder errors from validated SQL scopes and already mounted schema metadata; test missing and ambiguous columns, quoted aliases and CTE/subquery projection cases, and assert unreferenced tables are neither consulted, read nor mounted.
- [x] 3.2 Verify enriched SQL diagnostics through the existing MCP/runtime/trusted drawer path for live and historical results; retain safe fallback, redaction, cancellation and genuine authority-loss behavior with focused integration tests.

## 4. Validation and review

- [x] 4.1 Measure old/new description sizes using the same synthetic workbook and replay the retained failing SQL plus numerical references after deliberate fixture reprocessing. Report execution success separately from answer correctness and distinguish fresh model trials from isolated SQL checks.
- [x] 4.2 Run root `make code-quality`, affected integration checks and focused concurrent description/query checks within existing capacity limits; record results and verify no cross-request/pod-local correctness state was introduced.
- [x] 4.3 Apply the full `audit-branch` procedure against the actual target, obtain independent correctness and performance reviews for changed tool paths, record base/head, findings/dispositions and exclusions, and update migration guidance.
- [x] 4.4 Reconcile the final implementation with these artifacts, sync delta specs and archive after verification; commit reviewable blocks and update the existing draft PR with the approved follow-up scope and evidence.

Verification: 222 targeted backend tests, 161 Excel tests, 47 frontend tests,
47 runtime diagnostic tests and 10 prompt/catalog tests passed. Root
`make code-quality` passed across all 17 modules; migration check and strict
change validation passed. The backend suite includes six concurrent mixed
description/query requests under existing capacity limits. No new I/O,
connection, shared correctness state or distributed coordination was introduced.

Review: actual PR target `swift` at `de9192157`, merge base `059ae1c91`.
Independent read-only full-branch correctness and tool-path performance reviews
covered the implementation integrated in `7e5931af8`, including affected stored
metadata, API/MCP, frontend/history, runtime and prompt consumers. Confirmed
findings were fixed and replayed: omitted CSV markdown parsing, missing table
selectors in failure arguments, and a filtered catalog-budget bypass. Author
review of subsequent `e19b8b04e` found only an existing-import reordering and a
static pandas Series cast, without a behavior change. Migration guidance now
requires coordinated consumer upgrades and deliberate source reprocessing.
Excluded: production rollout, live multi-pod/large-user load and full application
browser/theme validation; focused concurrency and frontend consumer tests are
the available evidence.

Final campaign: same 32 trials (28 distinct prompt/context pairs), same instance,
model and tuning. Historical / first fixes / latest: 188/325, 29/187 and 25/139
failed tabular calls; 32/31/31 finals; 21/6/1 repeated successful calls. Latest
per-call failure rate is 17.99%, versus 15.51% on the first replay, with 13 rather
than 11 affected trials: lower failure count is not better per-call reliability.
All 25 latest failures are SQL; all 12 empty successes contain the approved
message. Of 29 descriptions, 23 select tables. One extraction approval pause
was retained; no latest provider/auth interruption, approval or rerun occurred.
The same bounded numerical subset is 1/11, 2/11 and 3/11 exact; no complete
answer-accuracy or causal A/B claim is made. Historical 77 HTTP401s disappeared
after login and are not credited to code.

Reported retained input/output tokens: 8475016/112522, 5734114/84875 and
3385332/76230. Four preserved interrupted first-fix attempts add 199387/1874;
all-attempt first-fix usage is 5933501/86749. Generation IDs are deduplicated;
all 32 retained model sums reconcile with terminal parent counters in each
series. Missing usage belongs to HTTP429 and remains unknown, not zero. An
independent report audit corrected trace-completeness gating and historical
category attribution. The final offline HTML/JSON provide both token scopes.

Native description characters: 34881 before and after initial fixes, 20004
latest (22 tables), 9242 for Clients/Activite only. Original workbook SHA-256,
UID and all 22 aliases match. All five valid reference SQL rowsets match their
original expected values; harness month formatting was adapted to the new
physical type without changing model inputs, business filters or expected rows.
All 28 unchanged previously invalid SQL remain invalid; six gain scoped column
diagnostics. These direct checks are separate from the model campaign. Final
trace validation proves original prompt/context, updated packaged guidance,
all four tools and the expected model for 32/32 trials. Sources were rechecked
after the campaign. Main specs were synchronized and strictly validated before
archive; draft PR #3460 is the close-out destination.
