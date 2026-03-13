# Release And Versioning Policy

This document defines Fred release delivery and versioning conventions.

We follow [Semantic Versioning 2.0.0](https://semver.org/).

## Delivery Flow

### 1) Integration flow (`develop`)

- Features are merged into `develop`.
- `develop` is automatically deployed to the integration platform.
- The team validates behavior on this integration environment.

### 2) Production candidate (`main`)

- When integration validation is considered acceptable, changes are merged from `develop` to `main`.
- `main` is the reference branch for production delivery.

### 3) Release tags on `main`

We use two tag families:

- Code release tag: `code/vX.Y.Z`
- Chart release tag: `chart/vA.B.C`

#### Code tag (`code/vX.Y.Z`)

Tagging `main` with `code/vX.Y.Z` triggers image builds:

- `agentic-backend:<X.Y.Z>`
- `knowledge-flow-backend:<X.Y.Z>`
- `frontend:<X.Y.Z>`

#### Chart tag (`chart/vA.B.C`)

Tagging `main` with `chart/vA.B.C` triggers Helm chart packaging.

Production deployment uses chart versions that reference images built from `main`.

## Customer Forks

Many production deployments are done from customer forks of Fred.

The expected pattern remains the same:

- integration branch auto-deployed for validation,
- promotion to production branch,
- release tags for code and charts,
- production rollout from images/charts generated from that production branch.

## Tagging Sequence (Recommended)

1. Validate on integration (`develop`).
2. Merge to `main`.
3. Create code tag `code/vX.Y.Z`.
4. Update chart image references and deployment defaults as needed.
5. Create chart tag `chart/vA.B.C`.
6. Deploy production from the released chart/images.

## Versioning Rules (`major.minor.patch`)

### Patch (`X.Y.Z -> X.Y.Z+1`)

Use patch for backward-compatible corrections:

- bug fixes,
- security fixes,
- non-breaking reliability/performance fixes,
- internal refactors without user-visible behavior changes.

### Minor (`X.Y.Z -> X.Y+1.0`)

Use minor when user-visible behavior changes but remains backward-compatible:

- new features,
- visible behavior evolution,
- small configuration additions that do not require migration,
- no mandatory operator action.

### Major (`X.Y.Z -> X+1.0.0`)

Use major when operators must review release notes before upgrade:

- potential breaking changes,
- mandatory deployment or configuration migration,
- required data/process migration,
- compatibility contract updates.

Major releases must include explicit upgrade guidance in release notes.

## Notes

- Code and chart versions are managed independently (`code/v...` and `chart/v...`).
- In practice they are often aligned for clarity, but alignment is a convention, not a technical requirement.
