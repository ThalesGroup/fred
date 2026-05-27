# Release And Versioning Policy

This document defines Fred release delivery and versioning conventions.

We follow [Semantic Versioning 2.0.0](https://semver.org/) and [Trunk-Based Development](https://trunkbaseddevelopment.com/).

## Delivery Flow

All development happens on `main`. PRs are merged into `main` continuously. The integration platform is always deployed from `main`, allowing the team to validate behavior before releasing.

Releasing is done by tagging a commit on `main` that has been validated on integration. The CI triggered by the tag handles everything: versioning all components, building images, and packaging the Helm chart.

See: [Release from Trunk](https://trunkbaseddevelopment.com/release-from-trunk/)

### Normal release

1. Validate the current state of `main` on the integration platform.
2. Tag the commit: `X.Y.Z`.
3. CI builds images `X.Y.Z` and packages the Helm chart `X.Y.Z`.
4. Deploy production from the released chart.

### Hotfix

Prefer fixing on `main` and releasing a new tag quickly if the fix is low-risk.

If `main` contains unreleased work that is not ready to ship:

1. Fix the bug on `main` first (never skip this step).
2. Create a release branch from the currently deployed tag: `release/X.Y.Z`.
3. Cherry-pick the fix onto the release branch.
4. Tag the release branch with the hotfix version `X.Y.Z+1`.

Release branches are created late and only when necessary — they are not maintained long-term.

See: [Late Creation of Release Branches](https://trunkbaseddevelopment.com/branch-for-release/#late-creation-of-release-branches)

## Release Tag

A single tag `X.Y.Z` (e.g. `1.6.0`) triggers the full release pipeline: Docker image builds and Helm chart packaging. Code and chart share the same version.

Images produced:

- `agentic-backend:X.Y.Z`
- `knowledge-flow-backend:X.Y.Z`
- `control-plane-backend:X.Y.Z`
- `frontend:X.Y.Z`

The Helm chart uses `appVersion: X.Y.Z` as the default image tag. This can be overridden per-component with `image.tag` in `values.yaml` if needed.

## Customer Forks

Many production deployments are done from customer forks of Fred.

The expected pattern remains the same: continuous integration on `main`, release by tag, late release branches only for hotfixes.

For rules on how to structure a fork so that merging from `main` remains permanently conflict-free, see [FORKING_GUIDE.md](./FORKING_GUIDE.md).
