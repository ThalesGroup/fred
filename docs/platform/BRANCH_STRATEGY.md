# Branch Strategy

Fred uses a **long-lived release branch** model. There is no `main`/`develop` split.
Each release cycle lives on a named branch (bird names), and releases are tags on
that branch. Feature work branches off the current release branch and merges back
into it.

---

## Model overview

```
swift  ── long-lived integration branch for release 1.x
  │
  ├── feat/my-feature        ← cut from swift, PR → swift
  ├── fix/my-bug             ← cut from swift, PR → swift
  ├── refactor/split-router  ← cut from swift, PR → swift
  │
  ├── tag v1.0.0             ← release tag on swift
  ├── tag v1.1.0
  ├── tag v1.2.0
  └── tag v1.2.1             ← patch tag (hotfix branch → swift → tag)

                                                     ↓ new major cycle

falcon  ── long-lived integration branch for release 2.x
           (born from a swift tag)
  ├── feat/next-feature      ← cut from falcon, PR → falcon
  └── tag v2.0.0
```

At any point there is **one active integration branch** per supported release.
Old branches are kept read-only for history; no new merges after the next cycle opens.

---

## Daily workflow for developers

```bash
# 1. Sync the current release branch
git checkout swift
git pull origin swift

# 2. Cut a feature branch
git checkout -b feat/my-feature

# 3. Work and commit
git add <files>
git commit -m "feat: describe the change"

# 4. Push and open a PR targeting swift
git push origin feat/my-feature
# → GitHub: open PR, set base = swift

# 5. After the PR is merged, clean up
git checkout swift
git pull origin swift
git branch -d feat/my-feature
```

---

## Branch naming conventions

| Type | Prefix | Example |
|---|---|---|
| New feature | `feat/` | `feat/mcp-tri-state` |
| Bug fix | `fix/` | `fix/prompt-crash` |
| Refactoring | `refactor/` | `refactor/agent-app-split` |
| Documentation | `docs/` | `docs/operating-modes` |
| Hotfix on a released tag | `hotfix/` | `hotfix/v1.2.1-auth` |

Branch names use lowercase kebab-case. No ticket numbers in branch names —
those belong in the PR description.

---

## Creating a release

```bash
git checkout swift
git pull origin swift

# Code release tag → triggers image builds
git tag v1.2.0
git push origin v1.2.0

# Helm chart release tag (if needed)
git tag chart/v1.2.0
git push origin chart/v1.2.0
```

See [`VERSIONING.md`](VERSIONING.md) for the full tag convention and what each tag triggers in CI.

---

## Hotfix on a released version

When a critical fix is needed on a shipped release while `swift` has already moved forward:

```bash
# Branch from the specific release tag
git checkout -b hotfix/v1.2.1-auth v1.2.0

# Fix, commit, push
git commit -m "fix: auth bypass on token refresh"
git push origin hotfix/v1.2.1-auth

# PR into swift (and cherry-pick forward to newer release branches if needed)
# Then tag the fix
git checkout swift && git pull
git tag v1.2.1
git push origin v1.2.1

# Clean up
git branch -d hotfix/v1.2.1-auth
```

---

## Opening a new release cycle

When the team decides to start release 2.x, a new long-lived branch is created from
a stable `swift` tag:

```bash
git checkout -b falcon v1.5.0   # or whichever tag is the cut point
git push origin falcon
```

From that point:
- New features for 2.x target `falcon`
- Security fixes for 1.x still go to `swift` and get `v1.x.y` patch tags
- `swift` becomes a maintenance branch until 1.x is end-of-life

---

## Why not `main` + `develop`?

The `main`/`develop` split requires merging every change twice: once into `develop`
for integration, then again into `main` for release. This creates divergence,
cherry-pick conflicts, and ambiguity about which branch is "the truth".

With the long-lived branch model:
- There is exactly one branch to target per release cycle
- Tags are the authoritative record of what was shipped
- CI always builds from the same source as production
- Parallel release maintenance is explicit (one branch per release, clear lifetime)

---

## Current release branches

| Branch | Release | Status |
|---|---|---|
| `swift` | 1.x | **Active** — target for all current PRs |

Future entries will be added here when new release cycles open.

---

## Cross-references

| Topic | Document |
|---|---|
| Tag convention and CI triggers | [`VERSIONING.md`](VERSIONING.md) |
| Developer setup and PR checklist | [`DEVELOPER_CONTRACT.md`](DEVELOPER_CONTRACT.md) |
| French onboarding guide (Claire · Arnaud) | [`CLAUDE_CODE_ONBOARDING_FR.md`](CLAUDE_CODE_ONBOARDING_FR.md) |
