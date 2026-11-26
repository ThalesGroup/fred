# Deployment Configuration

This directory contains Docker Compose files and Helm Charts for deployment of **Fred** elements.

An importable operational dashboard for agent runtimes is in
[`grafana/`](grafana/README.md).

## Image publication

The existing Docker workflows publish every image marked `publish: true` in
`.github/docker-images.json` to `ghcr.io/thalesgroup/fred-agent/<image>`:

| Git event | Image tag |
| --- | --- |
| Push to `swift` | `swift-dev` |
| Push to `weaver` (major version 5) | `v5-dev` |
| Push `code/vX.Y.Z` | `vX.Y.Z` and `latest` |
| Push `code/vX.Y.Z-alpha.N` (or another prerelease) | `vX.Y.Z-alpha.N` only |

For example, a `weaver` branch push publishes
`ghcr.io/thalesgroup/fred-agent/control-plane-backend:v5-dev`.
The v5 set includes `monitor`, alongside the core application images and the optional
PyMuPDF ingestion worker. Image repositories keep the component name; the development tag identifies the
major version rather than its codename. The Git branch name remains `weaver`.
Branch publications are serialized per branch. Dev tags are mutable and images
are pushed individually. A failed publication can leave only some aliases updated;
development charts below use exact digests from a successful build.

Git tags belong to the repository, not to a branch. Create the paired
`code/vX.Y.Z` and `chart/vX.Y.Z` tags on the same intended source commit, following
the [operator release workflow](release-notes/README.md#prepare-a-release).
It validates the committed guide before publishing. Weaver uses the 5.x version
line (for example `5.0.0-alpha.1`); keep versions distinct from Swift. Both lines
share `latest`. Preproduction and production pin an exact release version;
development platforms can follow the v5 development charts. The environment selects a version,
and is not part of the image tag. Prereleases do not update `latest`.

## Development charts

After all images from a `weaver` push succeed, the same workflow publishes `fred`,
`agent-pod` and `knowledge-base` to `ghcr.io/thalesgroup/fred-helm`, with version
`5.0.0-dev.<GitHub-run-id>.<attempt>`. The Fred chart pins every built-in workload,
worker, init container and migration hook to that build's image digest, including
monitor. It also includes `files/image-digests.json` for all published variants and
a source-revision annotation. Generic pod charts still deploy the consumer's own image.
A failed image build publishes no dev chart; a failed chart job can be retried with
a new attempt number. Dev charts are not tagged GitHub releases and have no attached
operator release report; the paired `code/v*` / `chart/v*` release workflow is unchanged.

The deployment factory follows the latest numbered dev chart with the existing
`make k3d-app FRED=weaver APP=fred` command. It uses the Helm version range
`>=5.0.0-dev.0 <5.0.0-dev.zzz`; alpha, RC and stable releases are excluded.
Use `RELEASE=<exact-chart-version>` to repeat a build. Publication does not redeploy
a platform: run the deployment command again to consume the new chart and images.
Weaver supports fresh installations only; a chart update does not provide a data
upgrade path from an incompatible development schema.

The `v5-dev` image aliases remain available for direct image consumers, which must
arrange image refresh and rollout themselves. For Helm deployments, consume the
chart defaults and override only platform settings. See [image overrides](charts/fred/README.md#images).

## Security profiles & classification tiers

Fred deployments target a classification level (e.g. **C1** baseline, **C2**, **C3**
hardened). The single chart knob that drives the hardened posture is
`...security.profile`, exposed in `charts/fred/values.yaml` on the workloads that act
as request authorities.

| `security.profile` | Meaning |
| ------------------ | ------- |
| _unset_ (default)  | Baseline (C1/C2). Authentication follows the individual `user` / `m2m` toggles; dev conveniences (mock-admin, soft JWT) remain possible. |
| `c3`               | Hardened, **fail-closed at startup**. Forces strict JWT issuer/audience validation, forbids no-security / mock-admin, and requires `user` and `m2m` authentication. Control Plane evaluates permissions in PostgreSQL; pods validate identity and enforce the admitted turn context. |

**Where it is enforced today.** `profile: c3` is honored by the services that call
`apply_security_profile` at startup:

- **control-plane-backend** — ✅ enforced
- **fred-agents** (and any `fred-runtime` agentic pod via `create_agent_app`) — ✅ enforced
- **knowledge-flow-backend** — ✅ enforced
- **\*-worker** (temporal workers) — n/a; they serve no authenticated request surface

> The broader, cross-environment deployment strategy (a full C1/C2/C3 configuration
> matrix, NetworkPolicies, per-pod Keycloak audiences) is being consolidated under a
> dedicated OPS RFC. This section documents only the chart knob available today.

## Root bootstrap secret contract (AUTHZ-07)

`charts/fred` is a portable Apps-layer chart: it knows nothing about GCP, GKE, AKS,
ArgoCD, Flux, Vault, SOPS, or External Secrets. The one thing it does know is that
`control-plane-backend` — and only that pod — needs a single environment variable to
validate `POST /control-plane/v1/bootstrap/platform-admin` (the RFC Part 8 §40-42 root
bootstrap endpoint, closes the very first `platform_admin` grant on a fresh install):

```yaml
applications:
  control-plane-backend:
    configuration:
      app:
        bootstrap_token_env_var: FRED_BOOTSTRAP_TOKEN   # already the chart default
    extraEnvVars:
      - name: FRED_BOOTSTRAP_TOKEN
        valueFrom:
          secretKeyRef:
            name: <an existing Secret owned by the instance's Foundation layer>
            key: <bootstrap token key>
            optional: false
```

The chart never creates that Secret, never carries a literal value in a tracked file,
and never mounts `bootstrap_token_file` (local-dev only, not rendered here) inside
Kubernetes. Each instance supplies this reference to a Secret it already owns.
Helm replaces the `extraEnvVars` list: append this entry while retaining the chart's
identity, storage and optional encryption references. See the
[chart Secret contract](charts/fred/README.md#external-secret-contract).

`extraEnvVars` is an application-Deployment-only extension point: it reaches
`control-plane-backend`'s Deployment and no other workload. The schema-init Job
(rendered when `applications.control-plane-backend.migration.enabled` is `true`)
runs `control-plane initialize-schema`. It receives only the database coordinates
and `migration.extraEnvVars` (or the hook's password Secret), never application
`env`, `envFrom` or `extraEnvVars`.

**If the overlay omits `extraEnvVars`** (the chart's own default), no
`FRED_BOOTSTRAP_TOKEN` variable is injected at all: the backend's own fail-closed logic
(`control_plane_backend/bootstrap/service.py::_read_configured_token`) makes the root
bootstrap endpoint explicitly unavailable rather than silently open. **If the overlay
configures a reference to a Secret/key that does not exist**, `optional: false` makes
Kubernetes itself refuse to start the pod — fail-closed at the platform level, not only
the application level. Both failure modes are intentional; neither is a bug to work
around with a fallback.

**Contract for a future AKS/Flux instance (out of scope here, tracked separately as
`INST-1` in `fred-deployment-factory`).** A new platform overlay reuses this exact same
chart contract unchanged and supplies, per instance:

- the target namespace;
- a pre-existing Kubernetes Secret (created by that platform's own secrets pipeline —
  Vault, External Secrets, sealed-secrets, whatever the target classification requires;
  this chart does not prescribe which) carrying the bootstrap token under a chosen key;
- that Secret's name and key, wired through `extraEnvVars`/`secretKeyRef` exactly as
  above — no forked template, no second chart;
- the instance's own Fred chart values (image tags, Foundation endpoint hostnames,
  ingress, etc.), independent of this contract;
- the Foundation endpoints the Apps layer expects to already exist (Postgres, OpenSearch,
  Keycloak, Temporal — see `fred-deployment-factory`'s RFC-0001 §2-3 for the
  Foundation/Apps boundary those names must satisfy);
- the same fresh-install sequence as every other instance: empty Foundation → user
  self-registers in Keycloak → authenticated root bootstrap (this contract) → declarative
  platform import (`CONTROL-PLANE-PRODUCT-CONTRACT.md §27`) — never a Swift-to-Swift upgrade path;
- a recommendation (not enforced by Fred) to rotate or remove the Secret's bootstrap key
  once root bootstrap has completed, mirroring `KC_BOOTSTRAP_ADMIN_*`'s own operational
  hygiene note.

No Fred identity, team, or role ever belongs in that overlay's chart values — every
identity and role is either the self-promoted root bootstrap admin or a name in a
declarative import bundle, never a deployment-config literal.

## Image SBOMs

`make sbom` writes one CycloneDX report per image with `publish: true` in
`.github/docker-images.json`. It needs `jq`, Docker and the images already built;
Trivy runs from its pinned container. From the repository root:

```bash
make docker-build
make -C apps/knowledge-flow-worker docker-build IMAGE_NAME=knowledge-flow-worker-pymupdf INSTALL_PYMUPDF=true
make sbom                  # every published image
make sbom IMAGE=frontend   # one image, by its name in docker-images.json
make sbom CVES=true        # include detected vulnerabilities
```

Reports are written to `target/sbom/<image>.cdx.json`, ignored by Git. On a release
tag (`code/v*`), CI publishes a report with CVEs as the `sbom-<image>` workflow artifact.

## Contact

For any security or deployment-related concerns, please reach out via the [Fred GitHub repository](https://github.com/ThalesGroup/fred).
