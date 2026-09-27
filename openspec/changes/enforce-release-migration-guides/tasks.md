## 1. Note contract and validation

- [x] 1.1 Add the English note template and strict metadata/body validator in a shared helper; test missing notes, invalid impact, duplicate keys, placeholders and explicit no-operation declarations.
- [x] 1.2 Convert the existing delegated-execution note in place to the schema and add this implementation PR's own note; validate both and verify that PR #2808 retains its default-off and rollback details.
- [x] 1.3 Add merge-base contribution checks, released-note immutability and deterministic high-risk checks; test base advancement, an Alembic revision declared none, and configuration changes with or without chart evidence.

## 2. Release planning and generation

- [x] 2.1 Implement ancestry-based baseline selection and stable/prerelease version validation; test unrelated branch tags, missing history, non-increasing targets, maximum impact and candidate promotion.
- [x] 2.2 Implement deterministic guide generation and verification outside UI assets; test inclusion of merged notes, readable exported links, none summaries and stale output rejection.
- [x] 2.3 Establish the policy activation boundary and explicit legacy coverage acknowledgement; test that the first release cannot silently ignore the pre-policy range or uncovered post-policy contributions.
- [x] 2.4 Dry-run planning over the current branch since its previous release, including PR #2808; report any legacy coverage still needing release-time audit without placing tags or claiming that audit complete.

## 3. CI and publication

- [x] 3.1 Add the stable Migration notes PR check without path filters, secret access or write permissions; validate workflow syntax and fixtures for docs-only PRs and merge-base behavior.
- [x] 3.2 Gate both tagged publication workflows on guide/version/tag-pair verification before pushing artifacts while preserving branch image builds; test absent/mismatched tag pairs and bounded propagation retry.
- [x] 3.3 Attach the committed migration.md to both GitHub releases; validate that both workflows select the same versioned file and fail for a missing artifact.

## 4. Shared developer and release workflow

- [x] 4.1 Update release strategy, PR template, root assistant instructions and configuration conventions with the note requirement and local/production ownership distinction; inspect consistency and internal links.
- [x] 4.2 Update the existing push-release skill through its shared .agents/skills entry point; verify a dry-run walkthrough uses the helper, presents both documents, rejects insufficient versions and still stops before tags without release approval.

## 5. Verification and rollout

- [x] 5.1 Run offline helper/integration tests and root make code-quality, then obtain independent correctness/CI review; record exact evidence and fix findings before pushing.
- [x] 5.2 Push the dedicated implementation branch and open a draft PR linked to issue #2809 with scope, migration declaration, test evidence and pending protection activation; verify its CI status.
- [ ] 5.3 After merge and an observed successful status, add Migration notes to effective GitHub required checks while preserving all other settings; inspect effective protections and report any access/bypass limitation.
- [ ] 5.4 Reconcile completion evidence, sync/archive this OpenSpec change and close issue #2809 only after implemented behavior and enforcement match the specification; keep release-time customer acceptance outside tooling completion claims.
