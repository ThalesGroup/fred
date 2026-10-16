## Context

See proposal.md for motivation. The factory's `bin/k3d-fred-deploy.sh` builds four images using each application's `docker-build`, derives tags from Docker image IDs, imports them, updates the model secret, recovers Helm and installs Fred. It also installs dashboards and prints access/bootstrap information. It currently changes the global kube context and does not lint/render before mutations.

At inspection, `fred-app` revision 2 and `fred-stack` revision 3 are deployed in `k3d-fred`; all six Fred deployments are ready. Helm 3.21.2 is available; Helmfile is absent. Factory has unrelated uncommitted edits to `bin/k3d-observe` and its skill. Fred's selected branch is `chore/fred-k3d-helm`.

## Goals / Non-Goals

**Goals:** expose the release configuration through ordinary Helmfile; retain a convenient local build/deploy loop; validate independently; preserve installation and data identity.

**Non-Goals:** custom blueprint/schema/variant discovery; a general plugin framework; changing production charts or infrastructure ownership; migrating Maxwell or evaluator; resetting the cluster. The first state covers the Fred application release, not a new one-command infrastructure lifecycle.

## Decisions

1. **The instance owns its installation composition** (revised 2026-10-16, see "Instance definitions in the factory" below). Retain `fred-app`, namespace `fred`, and explicit `k3d-<cluster>` targeting by default. Do not introduce synthetic product variants; existing `STACK=base|extended` remains an infrastructure choice.
2. **Explicit image preparation in Fred.** Add `deploy/k3d/` build tooling, using existing app Make targets and their image naming. Emit ordinary Helm image values and an image list as generated local artifacts. The worker mapping is owned by Fred. Do not reinterpret the CI-only image-selection change or duplicate Docker build commands.
3. **Generic factory entrypoint.** `make k3d-app DIR=<checkout>`, `make k3d-app-validate DIR=...` and `make k3d-app-uninstall DIR=...` deploy any product whose `deploy/k3d/` follows the contract (helmfile, values, optional `build`, `prepare`, `finish`). The factory names no product. Helmfile can also be used directly against prepared image values.
4. **Ordering and validation.** Resolve files/tools and lint/render installation values before builds. Build images, write their effective overrides, then lint/render again before importing images, secret updates or release recovery. Validation uses provided/generated image overrides when present, otherwise explicitly reports that it validates chart/installation values only. It never silently builds. A failure stops subsequent phases.
5. **Product operations have narrow interfaces.** Fred owns model-key lookup/consumer selection, dashboard preparation and bootstrap guidance. Factory owns cluster operations and calls existing import/recovery utilities. Use explicit context on every cluster call, including recovery, without changing the user's current context; preserve evaluator callers when extending shared utilities. Secrets remain out of values, argv and logs; give a local retrieval instruction instead of printing the bootstrap token in captured deployment output.
6. **Keep Helmfile state declarative.** No build or mutating preparation hooks, and no shell `exec` in templates. Pre/post product operations are explicit phases of the documented wrapper; direct Helmfile commands deploy prepared artifacts and do not implicitly perform them. State values precedence is chart defaults, one installation values file, generated image overrides.

## Generalization (2026-10-05)

The developer asked for one generic command able to deploy Fred, the evaluation application, knowledge bases or other products from their own repositories. The first slice's Fred-only factory state became a contract each product implements in `deploy/k3d/`: Fred's `build-images.py` became `build` (writing to the factory-provided `$K3D_APP_OUT`), `configure.sh key|finish` became the `prepare` and `finish` hooks, and the instance values moved here. fred-agent-evaluator implements the same contract. The factory keeps the cluster side (context, image import, recovery, sync) and documents a platform contract: namespace, service names and `fred-secrets` keys.

## Instance definitions in the factory (2026-10-16)

The 2026-10-05 contract assumed every deployment starts from a checkout. Deploying a published release needs no checkout, and values that name the instance's services, `fred-secrets` keys and Keycloak clients belong to the instance, as in a GitOps repository. For Fred's open-source ecosystem the factory therefore holds the definition; products keep only what needs their source.

| Element | Home |
| --- | --- |
| helmfile, k3d values, default release version | factory `k3d-apps/<app>/` |
| `identities.yaml` | factory `k3d-apps/<app>/` |
| `prepare` (model key from the environment), `finish` (login guidance) | factory `k3d-apps/<app>/` |
| `build` (images from source), `reset` | product `deploy/k3d/` |
| Grafana dashboards | product chart (separate slice, see below) |

- **Commands.** `make k3d-app APP=fred` deploys the default published release; `RELEASE=<version>` another one (a release version only, never `latest`). `APP=fred DIR=<checkout>` is the development mode: the helmfile takes the chart from the checkout and the engine runs the checkout's `deploy/k3d/build`. `DIR` alone keeps the product-owned contract for proprietary applications.
- **Engine.** `bin/k3d-app.sh` gains one resolution step: `APP` selects `k3d-apps/<APP>/`, which follows the same contract as a product's `deploy/k3d/`; with `DIR`, the checkout is exported to the helmfile (`K3D_APP_CHECKOUT`) and its `build` runs. Nothing else in the engine changes.
- **Version pinning.** Each factory helmfile pins the published version it deploys by default; a Fred or evaluator release is followed by a factory PR bumping it, as in any GitOps repository.
- **Coupling cost.** A product PR adding a required configuration key needs a companion factory PR; schema validation at render reports it immediately.
- **Overlays.** Proprietary registrations (other runtimes, other applications) go in a private values file passed with `VALUES=`. Helm replaces lists, so such an overlay repeats the `evaluation` entries it keeps.
- **Dashboards.** Until the chart ships them, the factory's `finish` loads them only in development mode, from the checkout. Shipping them in the chart is a production-chart change and stays its own slice.
- **Factory model.** The factory's "Applications stay with their product" and "names no application" rules become: open-source ecosystem applications are defined in `k3d-apps/`, the engine stays generic.

## Risks / Trade-offs

- Helmfile adds a local prerequisite → select and verify a compatible version during implementation, document installation and supported Helm version; do not silently install unverified executables.
- A factory companion change is necessary → use a dedicated branch/worktree, preserving current observability edits, and link both PRs to one tracking issue.
- Existing recovery can uninstall a failed first release → retain the PVC guard and never call recovery for the infrastructure as part of this slice.
- Rendered manifests can contain secrets → discard/protect render output; no secret values in test evidence or logs.
- Existing-cluster success cannot prove a fresh install → clearly report this limitation; no wipe, cluster deletion or infrastructure uninstall.

## Migration Plan

Prepare and test both repositories together, then replace the old target/launcher and update active references, excluding historical archives and immutable migration notes. Record the local command change and Helmfile prerequisite in the migration note. Validate with simulated commands, real Helm rendering, then a real build/deploy and a repeat deployment on the existing cluster. Verify readiness, image mappings, dashboard availability and Fred HTTP access, distinguishing authenticated checks from unauthenticated reachability. Roll back code and, if necessary, the Fred release to its previous known deployed revision; never uninstall infrastructure or delete volumes.

Developer confirmed implementation on 2026-10-05, explicitly limiting investment to local k3d. No multi-environment framework or future deployment support is part of this slice.
