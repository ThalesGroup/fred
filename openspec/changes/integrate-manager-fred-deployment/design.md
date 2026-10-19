## Context

The factory owns the Fred instance values and Helmfile; Fred owns its chart and `deploy/k3d/build`. The latter currently builds agents, knowledge-flow, control-plane and frontend. Manager uses a separate release and a symlinked chart without the strict values schema. Its image is absent from the shared CI image catalog. Frontend nginx resolves the agents and control-plane hosts at startup. The factory checkout contains existing staged work that this change must preserve.

## Goals / Non-Goals

Deliver the composition in the proposal through the ordinary Fred command. Preserve the boundary between product defaults and instance-specific addresses/secrets. Do not convert a deployment change into reconstruction of missing APIs, UI redesign, automatic data reset or removal of legacy source packages. This is the reconstruction branch's topology; an older published Fred release still requires its matching configuration.

## Decisions

1. **One Fred release.** Add manager API/worker as regular applications in the existing chart and schema generator. Use the existing manager configuration, mounts, probes and lifecycle catalog; API/worker share an image and compatible configuration. Keep lifecycle cleanup activation unchanged. Disable agents and control-plane in the resulting composition, including their migration Jobs. Remove the standalone chart wrapper/build instead of retaining two installation paths.
2. **Three local image builds, five workloads.** Extend the existing build map, preserving content tags, failure handling and API/worker identity. Add manager to the common CI image catalog with its actual app-directory Docker context. Legacy source and image publication can remain for other consumers; they do not make those services part of this deployment.
3. **Factory keeps instance ownership.** Put addresses, foundation secret references and the manager service identity in the factory's Fred definition. Bootstrap guidance queries manager. Keep the engine generic and validate the effective chart schema before mutations. Do not silently break the factory's pinned older published release; select configuration compatible with the actual chart, without inferring behavior from a Git branch name. Preserve the existing bootstrap secret key and Keycloak client identity.
4. **Retire the separate release explicitly.** Before installing manager resources under `fred-app`, preflight the existing `fred-manager` release's owned resource inventory. Refuse unexpected ownership or persistent resources. Once images and new manifests are validated, stop/remove only this known stateless application release and upgrade `fred-app`. This avoids two controllers and Helm ownership conflicts. No direct edits of Helm release secrets or unguarded ownership takeover. A rerun detects that the separate release is absent.
5. **Frontend remains independent of absent backends.** Reuse the proxy's existing runtime DNS resolution mechanism for control-plane and agents. Preserve routes and response failures when the service is absent; no fake successful responses or hidden UI. Verify knowledge-flow and frontend startup with neither service available. Review reset/health/image consumers against the new composition, without executing a data reset.

## Risks / Trade-offs

- Transferring the stateless release creates a short manager interruption. Retain protected local recovery artifacts for the old release and report an actionable retry if the Fred upgrade fails; do not claim the multi-release transition is atomic.
- Shared storage is external to the old manager release. Preserve PostgreSQL schemas, OpenFGA stores/tuples, accounts, accepted terms and foundation/model secrets. Refuse a migration whose inventory violates this assumption.
- The manager and frontend still roll separately inside one Helm release. One command prevents the observed forgotten manager update; it does not promise request-level atomic deployment.
- Existing control-plane/agent calls continue to fail until their own reconstruction lots. Keeping the UI is an explicit acceptance criterion.
- Broad CI/service tests and destructive fresh-cluster verification are not part of this short iteration. Report only focused evidence; do not wipe the user's test installation.

## Migration Plan

Implement the product and companion factory changes against isolated baselines, keeping unrelated edits out of commits. Validate command tests, image selection, strict chart renders and proxy startup with absent legacy hosts. Exercise first-install and legacy-release transition ordering with command fixtures, including refusal and retry paths. Update arc42 from the implemented topology and document the exact command and bounded interruption in the migration note.

The deployment command remains `make k3d-app APP=fred DIR=../fred`. Before declaring live success, verify exactly the five expected application deployments, shared API/worker image references, no legacy service/migration workload, frontend health and the manager folder response contract. Check readiness again on a convergent rerun. Keep live deployment evidence distinct from render/unit evidence. On failure, preserve data and retry the coordinated deployment; retained manifests/values are inspection artifacts, not a standalone rollback chart. Recreating an older release requires explicit operational recovery and must not race an active integrated manager.

Review refinements: validate live configuration, lifecycle catalog and environment sources before retirement; use foreground cascading so old producers have stopped before sync. Both manager pod templates hash their actual shared configuration/catalog. Hooks receive the invocation's normalized values arguments so their preflight matches the engine render.
