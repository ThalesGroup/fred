# Tasks

This file is the state of the work. Nothing else tracks it.

## Done

- [x] `fred-runtime` 4.0.0 — `app.runtime_id` required and slug-validated,
      replacing the hardcoded `"fred-runtime"` KPI service name (`fred` 7e6188000)
- [x] `fred-core` and `fred-sdk` to 4.0.0; 28 dependency floors aligned on
      `>=4.0.0` across 12 packages; 13 lockfiles regenerated
- [x] `[tool.uv.sources]` overrides onto the monorepo checkout for the 5
      consumers that lacked them
- [x] `runtime_id` declared: `fred-agents`, `fred-samples/agents`, `rags-agents`
- [x] `rags-services` on the platform observability path — `log_setup`,
      `build_kpi_writer`, `KPIMiddleware`, exporter on 9012, `/healthz`
- [x] `fred-rags` root `run-*` targets repointed at `apps/`
- [x] `site.fredlab.dev` used for site links across 4 repositories
- [x] `live-observability-session` skill: metrics table corrected
- [x] Publish `fred-core`, `fred-sdk`, `fred-runtime` 4.0.0 — 2026-09-18,
      verified on PyPI

## Open

- [ ] **← current. Rework how the UI presents identity.** Review the UX problem
      and decide the target — placement and shape are open, this task is the
      thinking as much as the code. The defect is established: the three pages
      use three vocabularies (`TeamAgentsPage` → `runtimeId` + `version`,
      `TeamApplicationsPage` → `version` only, `TeamKnowledgeBasesPage` →
      `definition_id` only), none shows a full identity, and nothing in
      `shared/atoms` / `shared/molecules` renders one — every badge there is
      about state.

      The model to present, decided: an **application** and a **knowledge base**
      are equivalent — one deployed unit, one identity. An **agent pod** is not:
      one deployed unit (`runtime_id`) holds many agents (`agent_id`), so it is
      the one case where identity has two levels.

      Three steps, contract first (see `design.md`):
      - [ ] `CapabilityCatalogEntry` gains `runtime_id` and `source_id`; the pod
            populates both instead of leaving provenance encoded in the FGA-safe
            composite `id`
      - [ ] `version` becomes optional; the agent and model projections stop
            stamping a literal (`"1"` at `product/service.py:775` and `:875`).
            Tools and applications keep the real semver they already declare.
      - [ ] one shared component renders identity, used by `FeaturesPage` and the
            three team pages; `FeaturesPage` can then group by runtime. No
            version is displayed until a real one exists.
- [ ] `make code-quality` and `make test` green at the `fred` root on 4.0.0
- [ ] **4.1.0 lockstep.** `fred-pod` joins as a fourth library and `fred-core`
      moves behind `fred-sdk[agents]`, so a Knowledge Base pod stops installing
      the agents platform. Publish in the mandatory order fred-pod → fred-core
      → fred-sdk → fred-runtime (each floors the ones below it at the same
      version). Agent-surface consumers declare `fred-sdk[agents]>=4.1.0`; a KB
      pod declares `fred-sdk[knowledge-base]`.
- [ ] **devops — pod configmaps.** Add `runtime_id` to
      `fred-deployment-factory/gcp-c1/argocd/fred-apps/templates/fred-agents-configmap.yaml`
      and `gcp-c1/helm/templates/fred-agents-configmap.yaml`. Without it the pod
      fails to boot on 4.0.0. Value must equal the `runtimeId` already set in the
      control-plane catalog (`fred-agents`).
- [ ] **devops — upgrade note.** One short section telling integration and
      production what changes and in which order.
- [ ] `rags-agents` — migrate `tessa` off `GuardrailDefinition` (removed by
      `0f2b45adf`). The pod does not start until this is done.
- [ ] `fred-samples`, `fred-website`, `fred-deployment-factory` — commits sit on
      `swift`; decide whether they move to `swift-satellites` like `fred` and
      `fred-rags`.
- [ ] Update the website to reflect what Fred has become.

## Not in this change

- `agent_id` naming — open question, `docs/swift/rfc/AGENT-ID-NAMING-RFC.md`.
- Agent versioning — decided in that RFC, not yet implemented.
- **Extracting the evaluation UI.** `fred-agent-evaluator` predates the
  application concept, so its UI was hardcoded into Fred's frontend — it lives in
  `TeamSettingsPanel/TeamSettingsEvaluations/` (8 views) plus its own
  `slices/evaluation/` RTK slice, as a tab in team settings rather than a surface
  of its own. Turning it into a proper application was blocked on having an npm
  package model; that is now nearly in place (`@fred-oss` publishes,
  `@fred-oss/ui` ships 10 primitives). Its own change, once
  `add-frontend-independent-releases` lands.
