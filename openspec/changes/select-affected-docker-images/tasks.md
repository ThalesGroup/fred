## 1. Selection

- [x] 1.1 Add `pr_selection` rules and knowledge-flow `pr_inputs` to `.github/docker-images.json`.
- [x] 1.2 Add `scripts/select_docker_images.py`: diff against the merge base, select, write the matrix and a per-image step summary; full build for release, manual run or failed diff.
- [x] 1.3 Wire it into `Docker-images.yml` (full-history checkout for PRs, tests before selection, skip the build job on an empty matrix) and add `workflow_dispatch` to `Check-docker-images.yml`.

## 2. Verification

- [x] 2.1 Add `scripts/tests/test_select_docker_images.py`: documentation, frontend, npm producer, libraries, knowledge-flow inputs, unknown paths, union, missing-COPY regression, renames and deletions, and guards that every knowledge-flow COPY source and local dependency is in `pr_inputs`.
- [x] 2.2 Replay the selection on `swift` history since 2026-07-01 to measure job savings.
- [ ] 2.3 Observe the check on the PR itself: step summary present, documentation-only push builds nothing.

## 3. Close-out

- [x] 3.1 Add the PR migration note.
- [x] 3.2 Replace the "CI runs all tests" sentence in `docs/swift/CONTRIBUTING.md` with how selection works and how to force a full check.
- [ ] 3.3 Archive this change once the PR is merged.
