# Release Branch Strategy

## Principle

Fred uses **long-lived release branches** as its primary unit of delivery.
There is no `main` or `develop` branch. The branch _is_ the release.

```
swift ──────────────────────────────────── v2.1.0 ─── v2.2.0 ──► HEAD
eagle ──────────────────────────────────── v3.0.0 ──► HEAD
```

Each labeled point above is actually a pair of Git tags on the same commit
(`code/vX.Y.Z` + `chart/vX.Y.Z` — see "Tagging a release" below), not a single tag.

---

## Branch model

| Concept                        | Mechanism                                                          |
| ------------------------------- | ------------------------------------------------------------------- |
| Current release in development | `HEAD` of the release branch                                       |
| Shipped release                | A pair of Git tags on the release branch: `code/vX.Y.Z` + `chart/vX.Y.Z` |
| Previous release maintenance   | Commits and tags stay on their branch                              |
| Branch naming                  | Short codename: `swift`, `eagle`, `kea`, …                         |

**There are no merge-back flows between release branches.** Each branch is
fully autonomous. Bug fixes that apply to multiple releases are **cherry-picked**
(see Hotfix workflow below).

---

## Documentation is release-scoped

Every release branch carries its **complete documentation tree** under
`docs/<release>/`:

```
docs/swift/       ← all docs for the swift release
  WORKPLAN.md
  backlog/
  design/
  platform/
  rfc/
  ...

docs/eagle/       ← all docs for the eagle release (once created)
  WORKPLAN.md
  ...
```

This separation is the key to conflict-free hotfix cherry-picks: a commit
that touches `docs/swift/WORKPLAN.md` will never conflict with eagle's
`docs/eagle/WORKPLAN.md` because the paths are disjoint.

When creating a new release branch, also update the documentation paths in
`.github/migration-policy.json` and both release-attachment workflows. Preserve the
activation boundary's meaning; do not reset it to exempt already governed history.

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

# 4. Commit
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

## Migration guides and version policy

Every PR provides an operator migration note, including an explicit no-operation
declaration. Follow [the migration workflow](ops/MIGRATION-GUIDES.md). The release
helper aggregates the actual release range and requires patch for none, minor for
operations including conditional activation, and major for substantial incompatible
changes. The maximum impact sets the minimum version for both tags.

Commit the generated `docs/swift/ops/releases/vX.Y.Z/migration.md` alongside the
user-facing release notes in a release-preparation PR targeting `swift`. Review the
Python package versions and synchronized `uv.lock` files in that PR and wait for
relevant CI before merging. Both publication workflows reject an
absent/stale guide, insufficient version or mismatched tag pair, and attach the
guide to the GitHub release. The shared push-release skill retains explicit
approval after merge and before tags; it no longer defaults blindly to a patch.

## Tagging a release

A release is **two Git tags on the same commit**, not one — each drives its own CI
workflow:

- `code/vX.Y.Z` — triggers `.github/workflows/Build-and-push-docker.yml`, which
  builds and pushes `fred-agents`, `knowledge-flow-backend`, `control-plane-backend`,
  and `frontend` images to `ghcr.io/thalesgroup/fred-agent/*`, tagged `vX.Y.Z`.
- `chart/vX.Y.Z` — triggers `.github/workflows/Package-and-push-charts.yml`, which
  injects `version`/`appVersion: vX.Y.Z` into `deploy/charts/fred/Chart.yaml` at
  build time (the value committed in `Chart.yaml` itself is not used and does not
  need to be bumped by hand), packages the chart, and pushes it to
  `oci://ghcr.io/thalesgroup/fred-helm/fred`.

A tag with neither prefix (a bare `vX.Y.Z`) matches neither workflow's trigger and
publishes nothing.

After the release-preparation PR is reviewed and merged, verify its contents on
`swift` and obtain explicit tag approval:

```bash
git checkout swift
git pull --ff-only origin swift
git tag -a code/v2.1.0 -m "Release v2.1.0 — images"
git tag -a chart/v2.1.0 -m "Release v2.1.0 — chart"
git push origin code/v2.1.0 chart/v2.1.0
```

Tags live on the branch they were created from. No promotion to `main` is needed
or expected.

---

## Publishing the Python libraries

Release tags build the images and the chart only. The shared libraries and
first-party capability packages reach PyPI **by hand**, with versions independent
of the Fred code/chart tag. Before every Fred release, prepare one patch increment
for `fred-core`, `fred-sdk` and `fred-runtime`. Bump a capability distribution
only when it changed since the previous stable code tag; bump each affected
`CapabilityManifest.version` separately after checking saved-config compatibility.
`fred-pod` advances only when its own package changed. The root targets require
`uv` on `PATH` and synchronize affected lockfiles:

```bash
make python-release-plan BASE_TAG=code/vX.Y.Z
# Review the changed packages and manifests, then select the affected ones.
make prepare-python-release BASE_TAG=code/vX.Y.Z \
  CAPABILITY_PACKAGES="fred-capability-documents" \
  CAPABILITY_MANIFESTS="libs/capabilities/fred-capability-documents/fred_capability_documents/document_summarize/capability.py"
make publish-libs-dry-run BASE_TAG=code/vX.Y.Z
# Inspect the target/dist artifacts. Publication uses these exact files.

export PYPI_TOKEN=...
make publish-libs BASE_TAG=code/vX.Y.Z
```

Prepare these versions and synchronized locks in the release-preparation PR.
The affected Python CI jobs install with `uv sync --locked`; review their results
before merge. Use the actual previous stable code tag from `make release-plan`, not the
placeholder above. Repeat `--capability` and `--manifest` selections through
the Make variables as needed, or leave them empty when no capability changed.
Set `POD_CHANGED=true` only when `fred-pod` changed. Preparation stops if a
changed package is omitted. It increments selected versions at most once for
that release, updates the shared-library dependency floors of selected packages,
and relocks projects resolving the new local versions. Review the `uv.lock` diff
for unrelated dependency churn. The agent-pod chart `appVersion` follows
`fred-runtime`; the knowledge-base chart `appVersion` follows `fred-sdk`.
Neither chart `version` is the Python package version. Python package publication
needs separate explicit approval after the Fred tag approval.

The order is **mandatory** and is defined by `PYPI_PACKAGES` in the root
`Makefile`:

1. `fred-pod`
2. `fred-core`
3. `fred-sdk`
4. `fred-runtime`
5. `fred-capability-code-sandbox`
6. `fred-capability-document-access`
7. `fred-capability-documents`
8. `fred-capability-html-artifact`
9. `fred-capability-mcp`
10. `fred-capability-platform-ops`
11. `fred-capability-ppt-filler`
12. `fred-capability-team-wiki`
13. `fred-capability-web-research`
14. `fred-capability-writable-document`

Selected packages floor newly prepared FRED dependencies at their corresponding
versions; unchanged packages retain compatible older floors. Publishing out of
order can therefore resolve against a release that does not exist yet.
The root target skips coordinates already present on PyPI, but any other PyPI
response stops the release. Before running it, confirm that the release
credential can create every package name that does not yet exist on PyPI; do
not discover missing project-creation authority after existing packages have
been updated. The target validates the independent version map, internal floors and
prebuilt artifact metadata for pending packages before the first upload. It then uploads each pending
package in the order above without rebuilding it;
after it completes, wait for every
`https://pypi.org/pypi/<name>/<version>/json` endpoint to return 200 before any
consumer resolves the new package coordinates because the index is not immediate.
Before publication, inspect each wheel's `METADATA` and contents under
`target/dist/`.

External consumers such as `fred-samples`, DT Agents and Aegis may install with
local sources disabled, so every referenced FRED coordinate must exist on PyPI
before their lockfiles can resolve the new versions.

---

## Branch lifecycle

| Phase              | Action                                                          |
| ------------------ | ------------------------------------------------------------------ |
| Active development | Commits flow freely on the branch                               |
| Release candidate  | Tag `code/vX.Y.0-rc1` + `chart/vX.Y.0-rc1`, run full validation |
| Released           | Tag `code/vX.Y.0` + `chart/vX.Y.0`                              |
| Maintenance        | Bug fixes only; each fix tagged as `code/vX.Y.Z` + `chart/vX.Y.Z` |
| End of life        | Branch archived (no deletion — tags remain reachable)           |

---

## Current release branches

| Branch  | Status                    | Latest tag                        | Doc tree               |
| ------- | ------------------------- | ---------------------------------- | ---------------------- |
| `swift` | Active — v2.x development | `code/v2.1.2` + `chart/v2.1.2` (2026-07-16) | `docs/swift/`          |
| `eagle` | Not yet created           | —                                  | `docs/eagle/` (future) |
