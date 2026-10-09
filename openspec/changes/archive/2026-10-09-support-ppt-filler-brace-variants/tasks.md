## 1. Marker recognition

- [x] 1.1 Obtain developer confirmation and create a dedicated branch for #3020 from the agreed target; verify that unrelated platform-access-control work is excluded from the branch diff.
- [x] 1.2 Extend the shared marker grammar and update all capture consumers in traversal and notes parsing; verify targeted `test_parser.py` cases for both forms, mixed headers, whitespace, repeats, malformed/nested delimiters, inline mentions, and kept notes.
- [x] 1.3 Add real-PPTX round-trip coverage for markers split across runs, grouped shapes, and table text; verify discovery and replacement agree and leave no delimiter residue for either form.
- [x] 1.4 Extend existing anchors, fill, and formatting tests for both forms, image metadata and invalid table image locations; verify the relevant targeted tests pass and normalized tool/schema keys remain compatible.

## 2. Author guidance

- [x] 2.1 Update both public help pages and the capability README with equivalent single/double examples, mixed headers, images, and syntax limits; verify every added template example against the parser and check consistency between English and French wording.
- [x] 2.2 Add one English migration note with operational impact `none` following `docs/swift/ops/MIGRATION-GUIDES.md`; verify its scope and format with the repository migration-note check.

## 3. Verification and delivery

- [x] 3.1 Run the full capability offline test suite and one root `make code-quality` near commit/push; record commands and outcomes here.
- [x] 3.2 Apply the full branch audit against its actual target and obtain an independent read-only review, including performance review of fill-time matching; record base/head, coverage, findings, dispositions, and exclusions here or in the PR.
- [x] 3.3 Reconcile planning artifacts with the implementation, sync specs, and archive via the repository skills; verify OpenSpec validation passes and no active completed change remains.
- [x] 3.4 Commit the coherent changes, push, and open an English draft PR linked to #3020; verify the PR includes the intended diff, migration note, and verification evidence.

## Verification evidence

- Base: `origin/swift` at `9a57933e24325ae75ffb52e291aed44edf69c46d`; isolated worktree `/tmp/fred-ppt-filler-braces`, branch `feat/3020-ppt-filler-brace-variants`. Developer confirmed implementation and draft delivery in chat.
- Package `make test` with an absolute worktree `PYTHONPATH`: 199 passed, one existing Starlette deprecation warning. Offline sockets remain disabled; execution outside the sandbox was required because the sandbox hangs even a standalone `asyncio.to_thread(lambda: 1)`.
- Help examples: all eight note headers in each locale checked against the shared grammar. Folder documentation now accurately limits case-insensitivity to metadata keywords and type values, and locates folder-existence validation at template save.
- `make migration-check MIGRATION_BASE=origin/swift`: one new declaration valid.
- Author review and independent read-only branch/performance review cover parser, traversal, normalized schema/tool consumers, text/image fill paths, tests, both help languages, README, and migration note. The independent review found one duplicate table parameter case, corrected before the final 199-test run. Follow-up confirmed capture compatibility, with 29,524 scanner comparisons showing equivalent recognition after the regex correction.
- No introduced I/O, shared mutable state, metric changes, or event-loop blocking; analyze/save/fill retain existing bounded thread offloading. No live load campaign or browser feature validation was performed. Final publication metadata is verified separately at delivery.
- Raw package `basedpyright`: 105 existing diagnostics both before and after the change; the package baseline remains unchanged. Root baseline-aware type checking reports zero new errors. Final parser-only check after signature annotations: 90 passed.
- Final root `make code-quality`: passed all 17 configured modules, including frontend TypeScript, Prettier, and ESLint. Existing Python environments were reused with `UV_NO_SYNC=1`; `libs/frontend` dependencies were provisioned from the committed lockfile in this worktree.
- Implementation commit: `9030949bc9d2c3e23fc775dbaf74738e1a5febe8`. Draft PR: https://github.com/ThalesGroup/fred/pull/3026, targeting `swift`; issue #3020 remains open until merge.
- Delta/main spec equality verified before archival; all artifacts complete, all tasks complete. Archived on 2026-10-09 after tests, quality, reviews, and draft publication.
