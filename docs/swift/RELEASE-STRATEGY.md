# Release Branch Strategy

## Principle

Fred uses **long-lived release branches** as its primary unit of delivery.
There is no `main` or `develop` branch. The branch _is_ the release.

```
swift ──────────────────────────────────── v2.1.0 ─── v2.2.0 ──► HEAD
eagle ──────────────────────────────────── v3.0.0 ──► HEAD
```

---

## Branch model

| Concept                        | Mechanism                                     |
| ------------------------------ | --------------------------------------------- |
| Current release in development | `HEAD` of the release branch                  |
| Shipped release                | Git tag on the release branch (e.g. `v2.1.0`) |
| Previous release maintenance   | Commits and tags stay on their branch         |
| Branch naming                  | Short codename: `swift`, `eagle`, `kea`, …    |

**There are no merge-back flows between release branches.** Each branch is
fully autonomous. Bug fixes that apply to multiple releases are **cherry-picked**
(see Hotfix workflow below).

---

## Documentation is release-scoped

Every release branch carries its **complete documentation tree** under
`docs/<release>/`:

```
docs/swift/       ← all docs for the swift release
  STATUS.md
  WORKPLAN.md
  data/sprint.yaml
  data/id-legend.yaml
  backlog/
  design/
  platform/
  rfc/
  ...

docs/eagle/       ← all docs for the eagle release (once created)
  STATUS.md
  WORKPLAN.md
  ...
```

This separation is the key to conflict-free hotfix cherry-picks: a commit
that touches `docs/swift/WORKPLAN.md` will never conflict with eagle's
`docs/eagle/WORKPLAN.md` because the paths are disjoint.

### Why not a shared `docs/` at root?

A flat `docs/` at root becomes a merge conflict surface the moment two release
branches evolve in parallel. Their backlogs, sprint states, RFCs, and design
decisions diverge immediately — they must live in separate trees.

---

## Creating a new release branch

When cutting `eagle` from `swift`:

```bash
# 1. Branch from the current HEAD of swift
git checkout swift
git checkout -b eagle

# 2. Rename the doc tree to the new release name
git mv docs/swift docs/eagle

# 3. Update all doc-path references in root-level files
#    (CLAUDE.md, AGENTS.md, AGENT.md, GEMINI.md, README.md,
#     .github/copilot-instructions.md, .github/pull_request_template.md,
#     apps/*/CLAUDE.md, apps/*/AGENTS.md, knowledge-flow-backend/CLAUDE.md, etc.)
#    Replace every occurrence of  docs/swift/  →  docs/eagle/
sed -i 's|docs/swift/|docs/eagle/|g' CLAUDE.md AGENTS.md AGENT.md GEMINI.md README.md
sed -i 's|docs/swift/|docs/eagle/|g' .github/copilot-instructions.md .github/pull_request_template.md
find apps -name "CLAUDE.md" -o -name "AGENTS.md" | xargs sed -i 's|docs/swift/|docs/eagle/|g'
sed -i 's|docs/swift/|docs/eagle/|g' knowledge-flow-backend/CLAUDE.md knowledge-flow-backend/AGENTS.md

# 4. Update the id-legend + sprint.yaml release marker
sed -i "s|release: swift|release: eagle|g" docs/eagle/data/sprint.yaml

# 5. Reset sprint.yaml for the new release cycle
#    (archive the swift sprint state, start eagle with a clean slate)
#    Edit docs/eagle/data/sprint.yaml manually: clear recently_closed, reset milestones.

# 6. Commit
git add -A
git commit -m "cut eagle release branch from swift"
```

---

## Hotfix workflow — cherry-pick without doc conflicts

When a bug fixed on `swift` must also land on `eagle`:

```bash
# On swift — fix the bug and commit normally
git commit -m "fix: <description>"

# Switch to eagle — cherry-pick CODE ONLY
git checkout eagle
git cherry-pick -n <sha>          # -n = no auto-commit (staged only)
git restore --staged docs/        # drop all doc changes from the stage
git commit -m "fix: <description> (cherry-pick from swift)"
```

The `git restore --staged docs/` step drops any doc changes that came with
the cherry-picked commit. Since `docs/swift/` paths don't exist in eagle
(eagle has `docs/eagle/`), this is always the correct behaviour.

**If the doc change is meaningful for eagle too** (e.g. a design doc correction),
apply it manually to `docs/eagle/` in the same commit or a follow-up commit.

---

## Tagging a release

```bash
git checkout swift
git tag -a v2.1.0 -m "Release v2.1.0"
git push origin swift --tags
```

Tags live on the branch they were created from. No promotion to `main` is needed
or expected.

---

## Branch lifecycle

| Phase              | Action                                                |
| ------------------ | ----------------------------------------------------- |
| Active development | Commits flow freely on the branch                     |
| Release candidate  | Tag `vX.Y.0-rc1`, run full validation                 |
| Released           | Tag `vX.Y.0`                                          |
| Maintenance        | Bug fixes only; each fix tagged as `vX.Y.Z`           |
| End of life        | Branch archived (no deletion — tags remain reachable) |

---

## Current release branches

| Branch  | Status                    | Latest tag | Doc tree               |
| ------- | ------------------------- | ---------- | ---------------------- |
| `swift` | Active — v2.x development | —          | `docs/swift/`          |
| `eagle` | Not yet created           | —          | `docs/eagle/` (future) |
