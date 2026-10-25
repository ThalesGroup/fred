## 1. Mount compatibility and boundary

- [ ] 1.1 Validate a read-only mounted view on the available k3d gVisor runtime and Docker runtime, and record actual `mount`, write-denial and latency observations in the PR; do not claim Kata support without a Kata node test.
- [ ] 1.2 Define a backend-neutral approved mount descriptor and broker preflight; verify that a missing driver, writable mount or unexpected source rejects file-backed execution.
- [ ] 1.3 Add an empty lease-specific mount to on-demand Kubernetes, SIG Agent Sandbox and Docker workloads; enforce zero ready workloads in broker configuration, admin API and SIG pool preflight; verify manifests and backend tests.

## 2. Authorized file gateway

- [ ] 2.1 Implement an authenticated read-only source view with opaque lease handles, bounded listing and range reads; verify traversal, cross-lease, write, expiry and cache invalidation tests.
- [ ] 2.2 Establish the conversation scope before execution, then enumerate readable team or personal corpus documents under `/inputs/corpus` without a selection call or guest scratch copy; verify allowed, denied, missing, oversized and newly added document tests.
- [ ] 2.3 Retain originals of new conversation attachments in existing private content storage, authorize mounted reads by uploader and persisted session membership, and erase originals on attachment/session deletion; verify ingestion, ownership, legacy and deletion tests.
- [ ] 2.4 Expose published platform skill scripts through a read-only `/skills` mount and reject escaping links and unsupported files; verify script source and path tests.

## 3. Agent runtime integration

- [ ] 3.1 Preserve current skill and document behavior with `code_sandbox` off and declare dependency for script-based skills; verify ReAct, Deep parent and child baseline tests.
- [ ] 3.2 Connect Deep's logical `CompositeBackend` and ReAct sandbox tools to the mounted path contract without copying source files; remove the selection tool and verify browsing does not start a workload before execution.
- [ ] 3.3 Gate Deep native `execute`, ReAct code execution and skill scripts through the same conversation sandbox lease and isolation profile; verify capability absence, Python file analysis and scratch reuse tests.
- [x] 3.4 Guide `execute_code` to use selective Bash or Python queries over mounted files, then verify a real conversation keeps large source content out of the tool result and final answer.
- [x] 3.5 Group consecutive code calls in the thought trace through a reusable presentation rule, preview the active intent on one ellipsized heading line, preserve individual details and chronology, and verify that another tool splits groups and streaming calls append to the current group.
- [x] 3.6 Replace the language-selecting sandbox request with one Bash script argument across the capability, SDK, broker backends, smoke test and UI; verify explicit Python invocation, command previews, and strict rejection of the removed argument.
- [x] 3.7 Show a leading shell comment alone with the command count in the group heading and beside the submitted code flattened onto one ellipsized expanded row, without heredoc parsing; verify exact code and result remain in the detail.
- [x] 3.8 Guide every Bash or Python execution to start with an intent comment, and show only the intent in the group heading and distinguish it from the formatted command in expanded rows; verify both a single Bash command and a Python heredoc in the UI.

## 4. Integration and close-out

- [ ] 4.1 Run a real Python analysis of a mounted workbook on an isolated backend and measure first and subsequent request latency with the mount; record commands and timings in the PR.
- [ ] 4.2 Update runtime/operator contracts, mount driver prerequisites and migration note; verify the docs distinguish tested runtimes and code-only fallback.
- [ ] 4.3 Run targeted tests, root code quality, branch audit and independent read-only review, then push and verify all PR checks are green.
- [ ] 4.4 Reconcile implementation with delta specs, sync and archive the OpenSpec change; verify `openspec status` and canonical spec content.
- [x] 4.5 Remove obsolete per-file selection routes and port methods while keeping the already-deployed `sources` column compatible; consolidate Job/SIG Pod admission, verify the SIG owner chain, and throttle expired-view cleanup, preserving mounted file authorization and targeted backend tests.
