# Release And Versioning Policy

This document defines Fred release delivery and versioning conventions.

We follow [Semantic Versioning 2.0.0](https://semver.org/).

## Weaver 5.x preparation

The `weaver` branch starts a coordinated 5.0.0 generation for Fred application
packages, Rust crates, Python libraries and capabilities, npm libraries, chart
versions/appVersions and local image-tag defaults. Published package names and
Python import names are retained. Swift keeps its existing version lines and can
continue releasing maintenance patches independently.

Weaver Python consumers require internal libraries in `>=5.0.0,<6`; the npm UI
requires `@fred-oss/design-tokens` in `^5.0.0`. Application lockfiles select the
local 5.0.0 packages without updating third-party dependencies. The k3d build
continues to use content-derived tags for imported images.

This is source preparation, not a publication or compatibility certification.
It does not adapt Python authorization to Weaver. Capability manifest/schema
versions, HTTP API versions, protocol versions, migration identifiers, historical
release evidence and synthetic test fixtures keep their existing meaning and
are not distribution versions.

Before publication, adapt and validate the release tooling for the two maintained
branches: the Python patch-preparation helper currently accepts only unbounded
`>=` dependency floors, the PyPI publication guard compares against the latest
published version, and the approved npm release contract still targets `swift`.
Do not reuse that approval as a Weaver release approval or rewrite historical
registry evidence. Review branch/tag routing, npm dist-tags, dependency bounds
on the Swift branch, and publication order in that separate release task.

## Delivery Flow

Fred uses a **long-lived release branch** model. See [`BRANCH_STRATEGY.md`](BRANCH_STRATEGY.md)
for the full branching workflow. This document covers only the tag convention and
what each tag triggers in CI.

### Integration

Features are merged into the current long-lived release branch (currently `swift`)
via pull requests. The branch is continuously deployed to the integration environment
for validation. There is no separate `develop` or `main` branch.

### Release tags

We use two tag families, applied directly on the release branch:

- Code release tag: `vX.Y.Z`
- Chart release tag: `chart/vA.B.C`

#### Code tag (`vX.Y.Z`)

Tagging the release branch with `vX.Y.Z` triggers image builds:

- `fred-agents:<X.Y.Z>`
- `control-plane-backend:<X.Y.Z>`
- `knowledge-flow-backend:<X.Y.Z>`
- `frontend:<X.Y.Z>`

#### Chart tag (`chart/vA.B.C`)

Tagging the release branch with `chart/vA.B.C` triggers Helm chart packaging.

Production deployment uses chart versions that reference images built from the
release branch tag.

## Customer Forks

Many production deployments are done from customer forks of Fred.

The expected pattern remains the same:

- integration branch auto-deployed for validation,
- promotion to production branch,
- release tags for code and charts,
- production rollout from images/charts generated from that production branch.

For rules on how to structure a fork so that merging from the release branch remains permanently conflict-free, see [FORKING_GUIDE.md](./FORKING_GUIDE.md).

## Tagging Sequence (Recommended)

1. Validate on the release branch (currently `swift`).
2. Create code tag `vX.Y.Z` on the release branch.
3. Update chart image references and deployment defaults as needed.
4. Create chart tag `chart/vA.B.C`.
5. Deploy production from the released chart/images.

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
