**v2.1.15** — 2026-07-24

- **Summary**

  Agent cards get a redesigned "more" menu with a new Duplicate action and a hover
  tooltip showing who created or last updated the agent. Team avatars now show an admin
  shield badge, and the team banner lists every role you hold on that team. The team
  banner also stays legible over any custom background image and is back to its full
  original size.

- **Features**

  - Agent cards: a top-right "more" menu now holds Edit and Deactivate, plus a new Duplicate action that clones an existing agent's setup into a new one, and Delete reachable directly from the card; a hover tooltip shows the agent's origin and who created or last updated it, and when (#2096, #2099)
  - Team avatars in the left rail show an admin shield badge when you're an admin of that team, and the team banner now lists every role you hold there (#2100, #2101)

- **Bug Fixes**

  - The team banner stays readable over any custom banner image, and is restored to its original taller size (#2097, #2098)

**v2.1.14** — 2026-07-24

- **Summary**

  The admin Capabilities page loads about twice as fast and shows team reach as clear
  badges instead of stacked text. A data-erasure request could get stuck forever if the
  agent behind one of its conversations had since been deleted — it now completes
  reliably. The message composer no longer clips your text after pasting, and no longer
  jumps you to the bottom while you edit earlier in a long draft. Closing side panels like
  "Manage teams" no longer strands keyboard focus.

- **Improvements**

  - The admin Capabilities page loads roughly twice as fast (#2089)
  - "Enabled teams" reach on the admin Capabilities page now shows as clear badges instead of stacked "3 team(s)" text (#2010)

- **Bug Fixes**

  - A data-erasure request could stay stuck forever if the agent behind one of its conversations had since been deleted — erasure now completes reliably (#2089)
  - The message composer no longer clips the top of your text after pasting, and no longer jumps you to the bottom while editing earlier in a long draft (#2010)
  - Closing a side panel (e.g. "Manage teams") no longer strands keyboard focus in a hidden area (#2089)

- **Deployment note**

  Adds a new nullable database column that tracks a session's originating runtime, applied via the standard migration step on upgrade — no manual action needed. Sessions created before the upgrade keep working via the previous lookup, unless the session's agent instance has already been deleted.

**v2.1.13** — 2026-07-24

- **Summary**

  Teams get flexible join rules (open, request-to-join, invite-only, or closed) with
  self-service join and leave; agent cards are redesigned with a dedicated Chat button and
  role display; you can now drag and drop whole folders onto the document library; and
  agents no longer surface a tool's raw internal error text as their final answer when a
  tool call fails.

- **Features**

  - Teams: choose how people join — open, request-to-join, invite-only, or closed — with instant self-service join for open teams, and any member can now leave a team on their own (#2084, #2086)
  - Redesigned agent cards: see an agent's origin and role at a glance, a dedicated Chat button, and an icon automatically guessed from its role (#2076, #2079)
  - Drag and drop files or whole folders straight onto a library folder to start uploading (#2078, #2080)
  - Admins can configure a custom warning banner on upload surfaces, with a one-time acknowledgment for chat attachments (#2077, #2081)

- **Improvements**

  - Asking an agent to "generate a PPT" or "write me a document" now reliably triggers the right capability in any phrasing, and PowerPoint generation grounds itself by searching your documents first (#2071, #2072)
  - "PPT Filler" is now called "PowerPoint generator" in the interface (#2072)
  - The chat's reasoning trace shows real SQL queries and document-search results with timing again, instead of a content-free "Done" (#2067)

- **Bug Fixes**

  - Agents no longer show a tool's raw internal error message as their final answer when a tool call fails — they retry or answer from what they already know instead (#2073)
  - Personal team spaces no longer appear in the team marketplace (#2069)
  - Fixed nested-folder drag-and-drop uploads failing outright (#2078)
  - Fixed a color conflict that could corrupt error-state colors across the app after opening the document editor
  - Fixed a crash that could occur closing a PDF viewer while a PowerPoint deck was regenerating
  - Fixed the new-agent template picker appearing off-center with only a few templates
  - Map locations in chat now show as a count summary instead of an interactive map, pending a replacement, due to a licensing issue with the previous map library

- **Deployment note**

  Additive only. The new team join-mode field is added via the standard migration step on upgrade — existing teams migrate automatically to request-only, preserving current behavior. The upload-warning banner is optional and stays off unless configured. No other operator action needed.

**v2.1.11** — 2026-07-22

- **Summary**

  Agents can now work directly with your document library: they browse the folders you
  have access to, summarize any document or chat attachment on demand, and use those
  summaries to search your corpus far more effectively. This release also adds two more
  capabilities: documents the agent and you write together in a live side pane (with
  Word/Markdown export), and PowerPoint templates filled straight from a conversation.

- **Features**

  - Writable Documents: the agent drafts a document in a side pane you can edit together — it sees your changes and revises in place, and you can export to Word or Markdown (#1905, #2027)
  - PPT Filler: give an agent your PowerPoint template and it fills the slides from the conversation and your documents, with an in-chat preview and a built-in authoring guide (#1903, #2020)
  - Agents can now browse your document library and summarize any document or chat attachment on demand, making corpus search far more effective (#1906, #2056)

- **Security**

  - Routine dependency updates: pyasn1 and setuptools (Python), fast-uri, immutable and svgo (frontend) (#2062, #2063)

- **Bug Fixes**

  - Clicking "Process" on a document now shows a live Processing status that flips to Ready/Failed on its own, instead of staying stale until a page reload (#2020)

- **Deployment note**

  Additive only — the new capabilities ship in the standard images and their database tables are created by the usual migration step on upgrade; the new `timeouts.summarize_read` knob is optional with a sensible default. Admins enable the new capabilities for their teams; no other operator action needed.

**v2.1.10** — 2026-07-22

- **Summary**

  Defense-in-depth authorization hardening for agent tool execution: every tool call in a
  ReAct turn is now individually re-authorized, and JWTs are rejected if their issued
  lifetime exceeds one hour, independent of what the issuing IdP was configured to allow.

- **Security**

  - Every tool call in a ReAct turn is now individually re-authorized against the caller's team (`CAN_READ`), not just once at turn start — a denied or stale team membership now blocks the specific tool call instead of being silently trusted for the rest of a long-running turn (`fred-runtime` 3.3.7)
  - JWTs are now rejected when their issued lifetime (`exp - iat`) exceeds one hour, regardless of what the issuing IdP was configured to grant — closes a gap where token lifetime was entirely delegated to IdP configuration with no application-side ceiling; Fred's own service-to-service tokens are short-lived and auto-refreshed, so this does not affect normal traffic (`fred-core` 3.4.7)

**v2.1.9** — 2026-07-21

- **Summary**

  Bug-fix release: ReBAC/authz gap closures (personal-team tuples, agent-kind
  capability id collisions, AuthorizationError 500s), evaluation-agent reachability
  fixes, and several UX/chart papercuts.

- **Bug Fixes**

  - Personal teams now get a real, self-healing ReBAC tuple — closes 500s/wrong 403s across filesystem, corpus, tags, tasks, evaluations (AUTHZ-08, #2038)
  - `AuthorizationError` now inherits from `PermissionError`, so a real ReBAC denial surfaces as 403 instead of an unhandled 500 (EVAL-03, #2042)
  - Reserve a namespaced id range for `kind="agent"` capabilities so they can no longer collide with `kind="tool"` ids (CTRLP-14, #2031)
  - Make the evaluation agent reachable from the frontend (#2037); forward the caller's bearer token to pod chat-controls evaluation, which was silently dropping all composer capability controls on auth-enabled deployments (#2030)
  - Tabular (CSV/XLSX) documents now reach "Ready" status instead of showing "Raw" forever (#2041)
  - Fix KPI preset endpoints 503ing due to an unhandled resilient KPI store wrapper (#2041)
  - Fix evaluation telemetry polling and conversation erasure edge cases (#2041)
  - UX pass: personal prompts no longer leak into team spaces, prompt categories trimmed to 7, library tree picker and capability-toggle fixes (#2032)
  - Fix Helm chart schema rejecting valid pod-level keys (`resources`, `imagePullSecrets`, `extraVolumes`, …) and migration hooks (#2025)
  - Fix worktree dev configs still binding a shared Prometheus metrics port (#2028)
  - Finish agent audit fields: `updated_by` column and creator/editor name resolution in the UI (#1952)

**v2.1.7** — 2026-07-20

- **Summary**

  Adds native Google Cloud Storage support for control-plane's team personalization assets (banner/logo images), and fixes GCS authentication on Trusted Partner Cloud / sovereign deployments such as S3NS.

- **Features**

  - Control-plane can now load team banner/logo assets from a native GCS bucket via Application Default Credentials / Workload Identity, in addition to the existing MinIO/S3-compatible and local filesystem backends (`content_storage.type: gcs`, control-plane-backend, fred-core, #2022)
  - New `signing_service_account_email` config knob for control-plane's GCS content store — mints short-lived V4 signed URLs via IAM `signBlob` (keyless) so team banners/logos remain viewable in the browser, extending the signing mechanism already used for knowledge-flow's internal tabular Parquet reads (`docs/swift/rfc/GCS-TABULAR-SIGNED-URL-RFC.md` §6)

- **Bug Fixes**

  - Fix `UniverseMismatchError` ("The configured universe domain (googleapis.com) does not match the universe domain found in the credentials") on every native-GCS backend (control-plane's new content store, knowledge-flow's content store and file store, fred-core's virtual filesystem) when deployed on a Trusted Partner Cloud / sovereign GCP variant such as S3NS — the GCS client now derives its universe domain from the loaded ADC credentials instead of assuming the public `googleapis.com` default, so the same code works unmodified on public GCP and on S3NS (`fred-core` 3.4.6, `knowledge-flow-backend` 1.5.3, `control-plane-backend` 1.6.1)

- **Deployment note**

  No new required config for existing MinIO/local deployments — additive only. GCS deployments (including already-running knowledge-flow-on-S3NS instances) pick up the universe-domain fix automatically on upgrade, no config change needed. Control-plane's new `gcs` backend needs `storage.content_storage.signing_service_account_email` set (see `deploy/charts/fred/values-gcp.yaml`) — the signing service account needs `storage.objects.get` on the control-plane `-objects` bucket, and the Workload Identity service account needs `iam.serviceAccounts.signBlob` on it (may reuse the same signing account already configured for knowledge-flow's tabular reads).

**v2.1.6** — 2026-07-20

- **Summary**

  First release with production ready agent evaluation framework.

- **Features**

  - One-click "Rerun" on the evaluation runs list, reusing the most recent run's target — the daily re-run workflow is a single click instead of a target picker every time (falls back to "New run…" when there's nothing rerunnable yet)
  - New shared `Breadcrumb` navigation component (Evaluations list → one Evaluation's runs → one Run's cases), replacing the duplicate back-button pattern on each page

- **Improvements**

  - Evaluation run/case progress now polls the run data directly instead of depending on the shared task-activity SSE stream, which opens one long-lived connection per active task per browser tab and can exhaust the browser's shared per-origin connection limit across two open tabs
  - Run and case progress queries no longer poll out of lockstep: the cases table forces one final refresh exactly when a run reaches a terminal state, closing a race where the run showed "Done" while a case row stayed stuck on "Running"
  - The "Scores by metric" panel is now labelled as a partial, still-updating average while a run is live, instead of reading as the final score under the same "Global score" label
  - Evaluation creation now returns to the full evaluations list instead of jumping straight into the new evaluation's (empty) run list, keeping "starting a run" a deliberate next step
  - Evaluation empty states (list and per-evaluation runs) now use the same sober `ServiceNotice` component already used elsewhere for "no X available" messaging, instead of a large standalone icon with its own redundant call-to-action button
  - The evaluation run detail page's Langfuse action no longer renders as a permanently-disabled "offline" button when telemetry is enabled in config but was never actually reachable — only shown when a session is available or genuinely still pending
  - `GET /teams/{team_id}/candidate-members` (new, team-scoped): a team admin can now search for a user to add to their team without requiring platform-admin rights, which the existing org-wide `/users` listing required

- **Bug Fixes**

  - Fix the evaluation worker's service-account identity being denied on every run case (`prepare-execution` requires `CAN_USE_TEAM_AGENTS`, which the service-agent allowlist never carried) — every evaluation run was blocked from executing (fred-core 3.4.5)
  - Fix the evaluation worker's service-account identity being denied on `get_tabular_dataset_schema` — the same service-agent ReBAC bypass already used for document/tag access was never applied to tabular datasets, 403'ing every evaluation case touching a team's tabular corpus (`knowledge-flow-backend`, #2018)
  - Fix evaluation run rows never reaching a terminal state on a full workflow failure, and never showing incremental per-case progress while running — both left the runs list stuck at "Pending 0/N" (`fred-evaluation-backend`)
  - Fix a case-drawer table column overflow where a long judge-profile label could clip the Detail/Delete action buttons
  - Fix a team admin's "add member" search silently returning nothing (403 swallowed) because it called the platform-admin-only `/users` listing instead of a team-scoped endpoint

**v2.1.5** — 2026-07-20

- **Summary**

  Closes the remaining CAPAB-01 agent-template capability gating gaps (`depends_on`
  enforcement, suspend/revive symmetry, import-sweep idempotency), ships increment 1 of
  tabular dataset discovery via semantic search, and lands a native in-app PDF viewer
  alongside continued MUI-to-rework frontend migration. Includes a full independent
  4-lens code review pass with fixes for every blocking/should-fix finding, several of
  them deploy-relevant.

- **Features**

  - `depends_on` gate: enabling a `kind="agent"` capability for a team or personal space now rejects (409) when its default tool capabilities aren't yet usable, closing the live bug where an agent could be enabled with a still-disabled dependent tool (CTRLP-14, #2004, #2015)
  - Dataset pointer chunks (increment 1): tabular/SQL datasets are now discoverable by a generalist agent via semantic search, gated off by default pending a deliberate rollout decision (RUNTIME-10, #2014)
  - Native PDF rendering unified into a single `DocumentViewer`, shared by chat citations and the corpus workspace preview drawer — every PDF previously rendered as markdown-only text regardless of upload format (FRONT-13, #1956)
  - SQL agent grounds generated queries in real, sampled column values instead of guessing string casing/format, removing a silent wrong-case "no data found" failure mode
  - First deep-agent template exposed: `fred.github.deep_assistant` (blank-slate, plans before it acts, same enrollment model as the general assistant). No filesystem tool by default — operators add it explicitly once ready

- **Improvements**

  - Revoking a team's grant on an agent-template capability now suspends its dependent instances consistently, and re-granting it reliably revives them again — previously revival only matched tool-level selections, so a template-suspended instance could never come back (CAPAB-01, #2004)
  - Import capability sweeps stay correctly scoped and idempotent across retried/duplicate import jobs
  - Checkpoint erasure now reports a real deleted-row count instead of always `None`, matching its sibling history-erasure endpoint (fred-runtime 3.3.5)
  - ReAct thought events now carry a real `duration_ms` instead of always `None`
  - DeepAgent (the minimal multi-step planning runtime) now emits the same audit/KPI/log trail as every other agent, closing a gap that predated any Deep agent being exposed
  - Removed dead frontend code: the unused `monitoringApi` slice, the kubernetes/statistics endpoints and Helm flag, and five npm dependencies with zero import sites
  - Continued MUI → rework migration: `Protected` guard, `ConfirmationDialogProvider`, `PageError`/`PageUnauthorized`, `LibraryTreePlayground`, and `PdfStreamingDocumentViewer` ported off MUI
  - Removed the unused Weaviate vector-store backend (not selected by any checked-in config)
  - Routine dependency bump: langchain 1.3.10→1.3.14, langgraph 1.2.5→1.2.9, deepagents 0.6.10→0.6.12

- **Bug Fixes**

  - Fix in-memory and Chroma vector stores not upserting by `chunk_uid` — re-ingesting a dataset appended a duplicate pointer chunk or silently dropped the update instead of overwriting it
  - Fix dataset pointer chunks being invisible to search (never marked retrievable) and orphaned on deletion (never marked vectorized)
  - Exclude dataset-pointer and low-relevance chunks from the chat Sources panel — a discovery-pivot chunk or near-zero-relevance hit was previously cited as if it were the answer's real source
  - Fix checkpoint/history erasure crashing the whole erase-session fan-out on a non-JSON or empty 2xx response, instead of isolating the single store failure
  - Fix a `DocumentViewer` race where switching documents mid-fetch let a stale response overwrite the newer document's content and title
  - Revert a live-testing config leftover that had left dataset pointer chunks enabled by default in 7 checked-in config/Helm files, including the GCP values file — now correctly gated off pending a deliberate rollout decision

**v2.1.4** — 2026-07-19

- **Summary**

  Production observability and capability-admin consolidation release for the GKE validation campaign.
  This release narrows Fred’s runtime surface and clarifies the production observability target:
  Fred emits structured application/KPI logs and metrics, but no longer exposes its own raw log
  exploration UI, endpoint, or agent tool. Log exploration is delegated to OpenSearch Dashboards;
  KPIs/metrics are exposed for Prometheus scraping. The release also improves capability-admin
  health/impact visibility so platform administrators can see which agents are affected by
  capability availability changes before or after they happen.

- **Features**

  - Capability admin health now distinguishes healthy, suspended, and unknown/unreachable agent impact, with drill-downs for affected instances.
  - Capability default/team/personal-scope changes now report suspended/revived agent impact in the admin UI.
  - Production configs are consolidated around the current target deployment posture for Control Plane, Knowledge Flow, workers, and Fred Agents.

- **Security / Observability**

  - Generic application/KPI logs remain emitted and storable in OpenSearch, but security/audit events stay structurally separated from the generic application log store.
  - Generic log records now carry a closed structural category (`application` or `kpi`) derived from logger identity, never from message text.
  - KPI/log sink writes are resilient/fail-open so an unavailable observability backend does not break business requests.
  - Sensitive content confinement was hardened so prompts, responses, tool arguments, and document fragments are not written into KPI/log records.
  - OpenSearch Ops surfaces remain gated behind platform-observer authorization.

**v2.1.3** — 2026-07-16

- **Summary**

This release hardens the import swift contract in order to safely be used a first production release.

- **Improvement**

  - make the swift import production ready (#1993)

**v2.1.2** — 2026-07-16

- **Summary**

  Follow-up hardening on the v2.1.1 bootstrap/provisioning candidate. Closes the AUTHZ-07
  chart secret-boundary release gate and consolidates its remaining review notes into the
  canonical AUTHZ-07/OPS-04 backlogs. No application behavior change. (AUTHZ-07, #1991)

- **Security**

  - The Control Plane's Alembic migration Job no longer receives `FRED_BOOTSTRAP_TOKEN` (or any other app-only `extraEnvVars`) — scoped to the Deployment only, with CI now proving exactly one rendering location (AUTHZ-07, #1991)

**v2.1.1** — 2026-07-15

- **Summary**

  Root platform-admin bootstrap and declarative platform provisioning. A fresh Fred
  deployment now creates its first `platform_admin` through a one-time, secret-gated
  bootstrap page instead of a config-seeded subject list, and every subsequent
  platform/team role can be provisioned declaratively via a `users.json` import bundle.
  (AUTHZ-07, #1986, #1987)

- **Features**

  - Root platform-admin bootstrap: a one-time, deploy-secret-gated flow (env var or file, Kubernetes-Secret-safe) grants the very first `platform_admin`, replacing the removed config-seeded `platform_admin_subjects`/`platform_observer_subjects` path (AUTHZ-07, #1987)
  - Declarative platform provisioning: a `users.json` import bundle grants platform and cumulative team roles directly, reconciling roles on both new and pre-existing teams (AUTHZ-07, #1987)
  - Platform import outcomes are now visible in Activity — a partial "with warnings" import is distinguishable from full success, with per-phase granted/skipped/processed counters (AUTHZ-07, #1987)

- **Bug Fixes**

  - Fix `BootstrapGuard` trapping auth/ReBAC-disabled deployments (the default insecure/dev config) on a bootstrap form that could never succeed (AUTHZ-07, #1987)
  - Fail closed instead of silently succeeding when a `users.json` import runs with ReBAC disabled (AUTHZ-07, #1987)
  - Normalize the env-sourced bootstrap secret (strip trailing newline) so Kubernetes-Secret-backed tokens compare correctly (AUTHZ-07, #1987)

**v2.1.0** — 2026-07-13

- **Summary**

  Authorization milestone. Fred's authorization model is now fully self-owned: Keycloak
  authenticates identity only (login, JWT, stable `sub`), and every platform and team
  permission — `platform_admin`/`platform_observer`, `team_admin`/`team_editor`/`team_analyst`/
  `team_member` — is a stored OpenFGA relation, never derived from a Keycloak role or group.
  Team roles are now cumulative (one person can hold several roles on the same team at once),
  and teams are no longer backed by Keycloak groups at all — a team is purely an
  OpenFGA-governed registry entry. (AUTHZ-05, AUTHZ-06, #1957)

- **Features**

  - Keycloak is identity-only; Fred/OpenFGA owns all platform and team authorization, with no legacy role/group bridge remaining (AUTHZ-05, #1957)
  - Team roles are cumulative — a user may hold `team_admin`, `team_editor`, and `team_analyst` on the same team at once, each granted and revoked independently (AUTHZ-06, #1957)
  - Teams fully decoupled from Keycloak — team creation, membership, and role management are pure OpenFGA operations (AUTHZ-05, #1957)
  - Platform-admin-gated team registry governance: list every team, delete a team, rescue an orphaned team left with no admin (AUTHZ-05, #1957)

- **Security**

  - Closed a live escalation where any Keycloak `admin` role holder implicitly became `owner` of every team (AUTHZ-05, #1957)
  - Closed an organization-level content bypass that let any global `editor` role holder read or process any team's content (AUTHZ-05, #1957)

**v2.0.2** — 2026-07-06

- **Summary**

  RGPD-ready increment. Deleting a conversation now **provably erases it** — its
  history, checkpoints, and attachments are removed across every store, not just
  hidden. Teams get a **Data & Retention** setting to defer erasure by a chosen
  window (capped by the platform), and platform/team admins get an **erasure
  schedule** showing what is scheduled, in progress, and completed.

  Security remediation increment. Sweeps the open Dependabot and CodeQL alerts on
  the `swift` branch: vulnerable frontend and Python dependencies are upgraded,
  an unused developer tool is removed, CI token scope is tightened, and the
  published libraries are re-released with the patched dependency floors so
  downstream agent pods cannot resolve the vulnerable stack. (#1917)

- **Features**

  - Data & Retention team setting: choose how long deleted conversations are kept before full erasure, within the platform-allowed limit (CTRLP-12, #1914)
  - Erasure schedule view for platform and team admins — scheduled (with due date), in progress, completed; a wedged erasure is flagged as **stalled** instead of failing silently (CTRLP-12, #1914)
  - Governed evaluation runs on real conversations within the retention window (CTRLP-12, #1914)

- **Security**

  - Patch vulnerable frontend dependencies — `react-router`, `dompurify`, `vite`, `http-proxy-middleware`, `echarts` (5→6), `js-yaml`, `@babel/core` (#1917)
  - Bump **FastAPI 0.116.1 → 0.139.0** and **Starlette → 1.3.1** across all backends, with patched floors baked into the published lib bounds — `fred-core` 3.4.1, `fred-runtime` 3.3.1, `fred-sdk` 3.3.1 (#1917)
  - Remove the unused `developer_tools/ai_tools`, retiring its dependency alerts (#1917)
  - Set least-privilege `GITHUB_TOKEN` permissions on the migration-check workflow; triage and dismiss the remaining CodeQL findings as documented false positives (#1917)

- **Bug Fixes**

  - Deleting a conversation always converges: if the erase can't complete immediately, it is hidden right away and retried automatically until fully erased — never left half-deleted (CTRLP-12, #1914)
  - Retrying or double-clicking a scheduled deletion no longer creates duplicate entries in the erasure schedule (CTRLP-12, #1914)
  - Fix the team banner upload breaking the build after the generated API client was refreshed (#1917)

**v2.0.1** — 2026-06-28

- **Summary**

  Security milestone. As of this release, Fred's runtime security model is **final and
  solid**: each agent pod is the execution authority and authorizes every request itself —
  validating the Keycloak JWT and running a pod-side OpenFGA ReBAC check (audience and
  team-binding enforced). It introduces the opt-in `security.profile: c3` hardened posture
  (fail-closed: strict JWT issuer/audience validation, no no-security/mock-admin, ReBAC
  required). Alongside the security work it ships a native Google Cloud Storage content
  backend (Workload Identity), a new PDF extractor, evaluation-campaign support on the
  task/event-bus API, config-driven branding, and human-friendly chat tool-call traces.

- **Features**

  - Hardened runtime authorization model, now final: each agent pod authorizes every request via the Keycloak JWT + a pod-side OpenFGA ReBAC check, with audience and team-binding enforced (RUNTIME-07, #1862)
  - Opt-in `security.profile: c3` hardened posture — fail-closed strict JWT issuer/audience validation, no no-security/mock-admin, ReBAC required (RUNTIME-07, #1862)
  - Native Google Cloud Storage content backend via ADC / Workload Identity for the content store and virtual filesystem (#1805)
  - Evaluation-campaign support on the task and event-bus API (#1827)
  - Config-driven branding: frontend branding wired from `config_json` (#1842, #1851)
  - Scheduled live-stack validation of GKE releases via an admin self-test harness (VALID-02, #1837)

- **Improvements**

  - New PDF extractor for higher-fidelity ingestion (#1790)
  - Human-friendly tool-call labels in the chat trace (CHAT-12 / CHAT-14, #1816, #1824)
  - Durable agent runtime store on Postgres, replacing the ephemeral sqlite path (#1862)
  - Repeatable review protocol and audit signals; RFC/doc cleanup pass (#1841, #1849)
  - Remove dead frontend components and untrack the benchmark binary (#1856)
  - RFC for a deterministic Excel extraction pipeline (INGEST-02, #1845)
  - Flag AGPL dependency pending removal (#1846)

- **Bug Fixes**

  - Fix `values-local` mismatch with `schema.json` (config schema drift)
  - Fix full-width CSV markdown rendering in the attachments preview drawer
  - Fix Personal Team avatar shape hover styling
  - Use Mistral models for `configuration_worker.yaml`
  - Revert default knowledge-flow configuration to the public Mistral API
  - Fix typos in translation files

**v2.0.0** — 2026-06-24

- **Summary**

  Major release. This version establishes the **agentic pod** architecture: agents are
  now built and deployed as standalone services in their own repositories — the control
  plane discovers them, enrolls their agents, and routes execution to them, with no
  dependency on the Fred monorepo. It also ships an in-app KPI analytics dashboard, a
  substantially reworked chat UI (attachments, prompts, voice dictation, reasoning
  traces), a unified virtual filesystem with provenance, and a richer ingestion stack
  (audio/video transcription, faster PDF extraction). Helm packaging is hardened with
  generated config schemas and Gateway API support.

- **Features**

  - Agentic pod architecture — design and run agents as independent HTTP services in their own repository; the control plane is the sole authority for pod discovery and agent enrollment (see `docs/swift/SWIFT_ARCHITECTURE.md`)
  - KPI analytics dashboard — active users, conversations & messages, agents, resources (OBSERV-02, #1722)
  - Reworked chat UI: in-chat attachments and enhanced composer (#1712), wired-in prompt library (#1782), document picker and local MCP config (#1731)
  - Voice dictation in the managed chat composer (CHAT-11, #1769)
  - Model reasoning support with improved thought traces (#1770)
  - Unified virtual filesystem with bounded paginated reads and provenance (#1794, AGENT-FILESYSTEM)
  - AudioProcessor for audio/video transcription via faster-whisper (#1708)
  - Shared global base prompts for all default agents (#1696)
  - Mindmap agent and deeper mindmap rendering (FILES-02)

- **Improvements**

  - Switched the ingestion processor from pymupdf to pymupdf4llm for improved PDF-to-Markdown handling performance in Fast mode (#1626)
  - New medium and rich extractors for higher-fidelity ingestion (#1718)
  - Targeted similarity comparison search in knowledge-flow (#1778)
  - Helm: Gateway API HTTPRoute support (#1759), values.schema.json generated from backend config schemas (#1729), JSON-schema generation and CI validation (#1725)
  - Use control-plane auth settings for the frontend instead of config.json (#1750)
  - Reconcile abandoned tasks against Temporal and emit ingestion task events (OPS-04, #1763, #1776)

**v1.5.4** — 2026-05-11

- **Features**

  - Add markdown processor for chat attachments (#1593)
  - Expose metrics for prometheus scraping on control plane (#1592)
  - Add configurable upload warning alert to document upload drawer (#1597)

- **Bug Fixes**

  - Typo in link in mail to request to join a team (#1589)
  - Spurious langfuse error log (#1594)
  - Cannot read properties of undefined (reading 'toLowerCase') in TeamContentNavbar (#1609)

**v1.5.3** — 2026-05-03

- **Improvements**

  - Add capacity to specify custom RetryPolicy for Temporal activities (#1576)

- **Bug Fixes**

  - Fixed semantics versus hybrid default values (#1580)
  - Fixed runtime binding error in agentic when publishing KPIs (#1577)

**v1.5.2** — 2026-05-02

- **Features**

  - Streaming responses now enabled for all agent types — previously limited to v2 ReAct agents
  - Token usage metrics (`llm.tokens_input`, `llm.tokens_output`, `llm.tokens_total`) now emitted per streaming session for all agents

- **Bug Fixes**
  - Fix team identity not resolved in `_stream()`, causing KPI and conversation history to miss the personal team default

---

**v1.5.1** — 2026-05-01

- **Features**

  - Default search policy selector in agent creation form

- **Improvements**

  - Default search policy changed from semantic to hybrid
  - Human-readable agent names on all Prometheus metrics; consistent `agent_id` dimension across all KPI actors
  - New `llm.call_latency_ms` metric for per-model Grafana panels
  - Automatic retry on transient gateway errors for Mistral-hosted models
  - Clearer error messages on AI service unavailability (502 / 503)
  - Fix Langfuse observation latency unit (field is in seconds, not milliseconds)

- **Bug Fixes**
  - Fix SQL agent not listing tables when directly queried and responding in the wrong language
  - Fix DOCX embedded image processing to match PDF and PPTX behavior

**v1.5.0** — 2026-04-24

- **Features**

  - Allow knowledge base of agent to be scoped at agent creation
  - Add join team mail to link on the teams marketplace
  - Add mandatory CGU full screen modal (#1531)
  - Add rich PPTX multimodal on basic react agent v2 with vector search tool (#1529)
  - Add Vertex Model Garden for embedding models & update MODEL_CONFIGURATION.md (#1525)

- **Improvements**
  - Improve temporal worker concurrency and add appropriate metrics (#1521)

**v1.4.1** — 2026-04-13

- **Bug Fixes**
  - Typo on personal team name
  - Public team displayed in sidebar even when you're not a member
  - Personal conversation not listed in personal space
  - Image link in markdown render using internal Minio address instead of ingress

**v1.4.0** — 2026-04-10

- **Summary**

  This release introduces the first full v2 agent stack for production use (ReAct + Graph), with a cleaner configuration model based on catalogs and a simplified agent creation flow. It keeps backward compatibility for existing v1 agents while preparing multimodal model selection (chat, language, embedding, image) through policy-based routing. It also ships a new Marketplace, team-scoped conversations, Alembic-based database migrations, and significant improvements to the ingestion pipeline and UI.

- **Features**

  - Add v2 ReAct profiles so a generic agent can be specialized with default prompt, MCP servers, and approval policy
  - Allow generic v2 ReAct agents to consume UI-configured MCP tools at runtime
  - Add a geo demo v2 profile and structured geo/link capability support for ReAct tool outputs
  - Add the first executable GraphAgentDefinition runtime contract with typed state, node handlers, tool calls, HITL resume, and structured final output
  - Add catalog-based model routing policies with deterministic matching (`capability`/`purpose`/`operation` + team/user/agent scope)
  - Add dedicated catalog files for models, agents, and MCP servers (`models_catalog.yaml`, `agents_catalog.yaml`, `mcp_catalog.yaml`)
  - Add support for Human In the Loop for react agent (#1207)
  - Add Alembic to handle Postgres and Sqlite migrations across all backends (#1409, #1451, #1452)
  - Implement new navigation and frontend team separation (#1345)
  - Implement new team settings
  - Implement new user settings
  - Rework agent page
  - Add a marketplace menu with team exploration pages (#1410)
  - Scope conversations by teams and fix personal team workflow (#1462)
  - Setup branding in new UI (#1482)
  - Add Prometheus agent and related KF MCP endpoints (#1340)
  - Add Clickhouse as vector store (#1255)
  - Add support for VertexAI (#1254)
  - Add PostgreSQL checkpointer backend for durable agentic runs (#1281)
  - Add Fred filesystem completion (#1434)
  - Add vision PPTX enrichment pipeline (#1419)
  - Add stateless connection support with MCP protocol (#1417)

- **Improvements**

  - Move default v2 agent prompts to packaged Markdown resources
  - Move ReAct profile selection to agent creation so admins choose a starting profile or custom class up front
  - Replace the experimental graph endpoint with a dedicated v2 inspection endpoint and model
  - Improve MCP runtime resilience with retry and short backoff on transient connection failures
  - Improve the debug drawer with sanitized runtime context, grouping by exchange, per-exchange copy, and local scrolling
  - Keep startup compatibility: when catalogs are absent, runtime falls back to legacy `configuration.yaml` sections
  - Document Helm wiring for optional catalog mounts and env overrides
  - Remove A2A proxy registration/card flow from backend and UI to simplify the runtime surface
  - Added configurable start-to-close timeout for Temporal ingestion activities (#1307)
  - Full page OCR on medium PDF ingestion profile (#1444)
  - Improve PDF markdown extraction for medium/rich profiles (#1320)
  - Improve PPTX processor (#1349)
  - Remove unnecessary packages from knowledge-flow Docker image (#1258)
  - Split embedding processing into more batches (#1461)
  - Add metrics to knowledge-flow worker (#1450)
  - Implement correct delta streaming protocol (#1439)
  - Wrap AgentToolsSelection and TuningForm with memo to reduce lag in agent form (#1479)

- **Bug Fixes**
  - Fix duplicate assistant bubbles during streamed tool-based exchanges
  - Fix transient duplicate user messages during optimistic send and server echo reconciliation
  - Fix restored ReAct tool-call history so multi-turn conversations resume correctly after tool usage
  - Fixed OpenSearch vectorization failures on large ingestions by splitting document indexing into multiple batches that respect bulk_size (#1299)
  - Fixed ingestion regression when using the standalone mode (#1329)
  - Fix support for docling_parse PDF backend due to deprecation of dlparse_v4 (#1309)
  - Fix missing image processors in local and production deployments (#1326, #1327)
  - Fix missing i18n translation keys (#1404, #1319)
  - Fix ingestion error when embeddings count exceeds bulk size (#1305)
  - Fix automatically create vector index with vector dims inferred from embedding model (#1289)
  - Fix starlette file header encoding with latin-1 codec (#1493)

**v1.3.0** — 2026-03-04

- **Summary**

  This release introduces real-time agent response streaming in the UI and adds Human In the Loop support for react agents. It also hardens production deployments by removing exposed API documentation endpoints and fixes file download permissions and image rendering issues in production mode.

- **Features**

  - Stream agent response in the UI
  - Add support for Human In the Loop for react agent (#1207)

- **Improvements**

  - Remove FastAPI /docs /redoc /openapi.json from production images (#1242)
  - improve opensearchops mcp endpoints for cluster debugging new routes better route description (#1239)

- **Bug Fixes**
  - Fix permission problem when downlading file generated by agents (like Kelia) in production mode (#1238)
  - Fix images not displayed in documents markdown preview in production mode (#1245)

**v1.2.7** — 2026-02-26

- **Summary**

  This release focuses on reliability and security. Mermaid diagram rendering has been significantly improved with robust error handling and clean fallbacks. Vector search security is tightened so agents only access vectors they are authorized to see.

- **Improvements**

  - Improve Mermaid diagram rendering with clean fallback and scoped HTML checks (#1206,#1211)
  - Create a proper KF markdown media client method and fix sync function calls (#1214)

- **Bug Fixes**
  - Fix vector search returning all vectors when agent has no authorized tags (#1225)
  - Fix editor permission to receive ingestion updates (#1212)

**v1.2.6** — 2026-02-22

- **Summary**

  This release focuses on stability, offline compatibility, and team features. It introduces the Aegis agent, improves offline deployment support (Dockerfiles, knowledge flow), and refines team-based vector search and agent selection. It also includes significant updates to dependencies (removing unstructured) and fixes for PDF loading and SVG processing.

- **Features**

  - Add Aegis agent (#1166,#1182)
  - Add k3d configuration (#1174)
  - Add team filter in vector search and rework agent selection with team (#1158)
  - Improve pipeline initialisation and deliver new test tool (#1152)
  - Viewers can CRUD attachments (#1176)

- **Improvements**

  - Remove unstructured dependency and update dependencies for security (#1202)
  - Make knowledge flow and Dockerfiles work in truly offline environments (#1163,#1184)
  - Move cv skill detection and refactor agent architecture (#1185)
  - Rename default agentic secret m2m env var (#1186)
  - Config storage for Raph & Kellia and move to async utils (#1197)

- **Bug Fixes**
  - Fix failure of pdf loading (#1192)
  - Fix svg images breaking ingestion process (#1172)
  - Fix metric kpi loading regression (#1154)
  - Fix conversation switches and remove agent_name (#1156)
  - Fix frontend settings in helm values (#1171)
  - Fix crossencoder_model in helm values
  - Fix cannot read properties of undefined in coming soon page (#1159)

**v1.2.5** — 2026-02-14

- **Summary**

  This releases brings in key performance improvements. Temporal is now fully supported
  for running ingestion workloads. Knowledge flow and agentic have been rendered
  asynchronous and equipped with additional performance metrics.

  In terms of feature, Fred now allow teams to share corpus and agents.
  Fred ships with an integrated benchmark tools.
  Last, psotgres (sqlite or real postgres) is now used for persistence. Support for
  duckdb has been removed.

- **Features**
  d

  - add missing kpi (#1129)
  - add frontend properties to hide enable/disable agent button (#1139)
  - allow admin to set class path of agent when creating them (#1133)
  - Improve jira agent (#1137)
  - make agent private + allow team to own agents (#1114)
  - Use temporal as a processing backend for general corpus & fast(attachments) pipeline execution (#1084)
  - make all postgres connectors truly async (#1104)

- **Improvements**

  - Execute temporal workflows concurrently and handle errors properly (#1127)
  - add option to pass minio public url + use it to create presigned url (#1111)

- **Bug Fixes**
  - fixed temporal in distributed settings (#1146)
  - refactor agent manager to work with multi workers/replicas (#1122)

**v1.2.4** — 2026-02-02

- **Summary**

  This relase brings in two major features: the support for interrupt to cleanly implement human in the loop
  and a clean support for a shared filesystem, exposde to agnt using a well defined workspace
  concept. This allow configuration files or working files to be cleanly exchanged between admins, users
  and agents.

- **Features**

  - new KPIs and bench logging, finer grain http outgoing configurability (#1061)

- **Improvements**
  - handling of token expiry (#1061)

---

**v1.2.3** — 2026-01-25

- **Summary**
  This release bring in new KPIs, a bench tools to stress the agentic fred backend. As part of KPIs and performance improvements,
  the various langchain dependencies have been updated:

  - "langchain>=1.2.7",
  - "langchain-community>=0.4.1",
  - "langchain-mcp-adapters>=0.2.1",
  - "langchain-core>=1.2.7",
  - "langchain-ollama>=1.0.1",
  - "langchain-openai>=1.1.7",
  - "langchain-text-splitters>=1.1.0",
  - "langchain-postgres>=0.0.16",

- **Features**

  - new KPIs and bench logging, finer grain http outgoing configurability (#1059)
  - new bench tools (#1049)
  - new core temporal agentic API (#1038)

- **Improvements**
  - use of shared http clients (#1055)
  - reshaping of prometheus metrics (#1023)
  - updated langchain version to latest (#1059)
  - improve applicative KPIs (#1066)

**v1.2.2** — 2026-01-23

- **Summary**
  This release bring in UI improvments in particular allow agents to have the UI display their options
  on a nicer and more ergonomic conversation right side panel.

  - **Features**

    - allow per document search (#1022)
    - leverage unstructured for attachement files processing (#1012)
    - added Log Genius agent (#1004)

  - **Bug fixes**
    - fixe the delete UI issue not refreshin (#1026)
    - UI improvements (#1015,#999,#1014)

**v1.2.1** — 2026-01-16

- **Features**

  - add favicon override front setting (#987)

- **Improvements**

  - use kpi store to expose prometheus metrics (#983)
  - batch "load more" calls to max 500 docs and paginate long user chat messages (#975)

- **Bug fixes**
  - fix the dot loader (#986)
  - fix UI leak when selecting a library affecting other conversations (#981)

---

**v1.2.0** — 2026-01-10

This release brings in a major UI revamp. This revamp has been proposed and designed
by the Prism team to make Fred evolve towards a state-of-the-art agentic orchestration platform.

- **Improvements**
  - Side bar now integrated into the main left side bar. (#976)

---

**v1.1.3** — 2026-01-09

- **Summary**

  This release brings in kpi, language and logging improvments to facilitate operations.
  It also leverage the rebac feature to start proposing a clean sresource sharing policy.
  Please not the rebac coverage is not yet complete and will be fully delivered in a future
  major release.

- **Improvements**

  - reduce log verbosity (#963)
  - log and update the vector search mapping for attachements required fields (#964)
  - take into account frontend language (#962)

- **Bug fixes**
  - fixed the missing attachement file number in the UI (#966)
  - fixed the error preview attached files from the 'My Files' area (#965)
  - removed the display button fro user files list (#969)
  - prevent viewer to share libraries in turn with others (#972)

---

**v1.1.2** — 2026-01-08

- **Summary**
  - Dynamic ReAct agents now support source citations, and agent code inspection works for all agents (#950).
- **Features**

  - Add source citation support to dynamic ReAct agents (#950)
  - Fix agent code inspection to display source for all agents (#950)

- **v1.1.1** — 2026-01-07

  - **Summary**
    - This release completes the support for per conversation attachements, and improve the capabilities of dynamic agents.
  - **Features**
    - Dynamic agent can now leverage the chat options to benefit from depp searchn attachements library scoping (#941)
    - New duckdb and opensearch connectors to manage per conversation attachments (#941)

- **v1.1.0** — 2026-01-04
  - **Summary**
    - New PostgreSQL/pgvector option so Fred can run fully without OpenSearch, plus in-UI Mermaid rendering for agent replies.
    - This version provides full support of per conversation attachments. Attached files are vectorized using lite markdown processors.
    - The Rico agent expose now a first deep search capability that leverage the Rico Senior document agent.
  - **Features**
    - Add a Postgres-first deployment path (metadata + vectors) across knowledge-flow and agentic backends (#933)
    - Surface vector backend details (pgvector or OpenSearch) in the admin views (#933)
    - Rag support for per conversation attachements files
  - **Bug fixes**
    - Fix Mermaid diagrams rendering in chat by generating safe SVG previews and stabilizing layout (#933)
  - **Impact**
    - Teams can choose a single Postgres stack for persistence; diagrams now display cleanly without layout jumps.

---

- **v1.0.9** — 2025-12-09
  - **Summary**
    - Corrected the OpenSearch k-NN query to use the proper `{ knn: … }` structure with filters inside the k-NN block, avoiding sub-optimal or inconsistent results.
  - **Features**
    - Select multiple chat contexts (#890)
    - Provide feedback on downloads (#892)
  - **Bug fixes**
    - Fixed the OpenSearch vector search query (#888)
  - **Impact**
    - Improved relevance, faster filtered searches, and full compatibility with OpenSearch 2.19+.

---

- **v1.0.8** — 2025-12-08
  - **Summary**
    - Added a selector for corpus-only, general-knowledge-only, or hybrid search for RAG agents.

---

- **v1.0.7** — 2025-12-06
  - **Summary**
    - Production-hardening for RAG agents (e.g., Rico) with corpus toggles and keyword selection.
  - **Features**
    - Major improvements including the RAG expert (#874)
    - Persist MCP & agent deletion across redeployments (#872)
    - Ignore all files starting with `ignore_` in git

---

- **v1.0.6** — 2025-12-04
  - **Summary**
    - Preview image versioning and cleaner deletion flows.
  - **Features**
    - Improve robustness of UI and audit with many documents (#873)
    - Update tabular controller for security and performance issues (#868)
  - **Bug fixes**
    - Delete documents cleanly in all backend storage (#870)

---

- **v1.0.5** — 2025-12-03
  - **Summary**
    - MCP hub improvements.
  - **Features**
    - Add MCP servers store and stdio support (#863)
  - **Bug fixes**
    - Fix selected MCP servers (#865)
    - Fix chart values `mcp.servers` with id and name (#861)

---

- **v1.0.4** — 2025-12-01
  - **Summary**
    - Internal release.

---

- **v1.0.3** — 2025-12-01
  - **Summary**
    - OpenSearch mapping tolerance updates.
  - **Features**
    - Improve error handling with respect to guardrails (#860)
    - Display MCP servers as cards with switches (#848)
    - Add vectors and chunks visualizations in Datahub (#852)
    - Give agents a mini filesystem (dev local, prod MinIO) with list/read/write/delete (#835)
  - **Bug fixes**
    - Fix agentfs (#849)
    - Non-recursive doc count in DocumentTreeLibrary (#858)
    - Fix the new chunk vector UI when security is enabled (#856)
    - Add back role in agent selector chip and improve layout (#854)

---

- **v1.0.2** — 2025-11-27
  - **Summary**
    - Official OpenSearch support with documentation.
  - **Features**
    - Add documents count for collection (#838)
    - Improve logo rendering (#837)
    - Improve pipeline drawer and add descriptions to processors (#833)
    - Add a Neo4j MCP connector to support graph-based RAG strategies (#812)
    - Change MCP agent to be a more generic agent (#829)
    - Fred academy changes after the 2011 hackathon (#828)
    - Adapt configuration of values.yaml for openfga (#822)
    - Add an academy streetmap agent (#823)
  - **Bug fixes**
    - Fix config file env variable regression (#843)
    - Fix missing async functions for ingestion (#832)

---

- **v1.0.1** — 2025-11-19
  - **Summary**
    - Internal release: v1.0.1.

---

- **v1.0.0** — 2025-11-03
  - **Summary**
    - Major release aligning the codebase with the latest LangChain versions; supersedes v0.0.9 and unlocks the newest LLM capabilities.
  - **Features**
    - Use the latest stable LangChain/LangGraph version (#737)
