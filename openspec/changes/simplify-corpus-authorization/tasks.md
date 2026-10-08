## 0. Planning and reference measurements

One topic branch and one implementation PR target `swift`. Commit completed
single-purpose blocks within the six stages below; no dependent PRs or separate
planning PR. Record each stage's commit, targeted checks and production additions/
deletions in this task file or the PR, separating tests, generated files, migrations/
tooling and docs. Do not create another status ledger. Run broad suites/reviews at
integration, repeating only evidence invalidated by subsequent changes or failures.

- [x] 0.1 Obtain developer confirmation of the reconciled proposal, design and acceptance scenarios before implementation; record the confirmed planning commit in the PR.
  Confirmed in conversation on 2026-10-08: planning commit `58e0eeb07f6127b6425e741998da847091f5aa97`. Carry this reference into the single implementation PR when opened.
- [ ] 0.2 Capture the starting commit, relevant production LOC/concepts and a repeatable isolated performance baseline using existing fixtures/metrics; verify recorded requests, whole-turn tool counts, FGA operations/attempts, SQL rows and latency for fixed contexts at increasing corpus sizes, with real PostgreSQL/OpenFGA and controlled model behavior.
  Initial evidence at `58e0eeb`: 28 existing real-OpenFGA tests passed. An isolated
  PostgreSQL 17/OpenFGA 1.15.1 primitive probe with 200 teams/2,000 users measured
  100/1,000 individual document checks for 100/1,000 requested documents (88/709 ms,
  single local observations, not capacity claims). Global document ListObjects
  used one logical operation with growing result cardinality. Raw evidence and
  the probe are in ignored `.fred-test/rebac-baseline/`; this is not a full-turn
  baseline and does not close this task. Starting physical Python lines in the
  selected ReBAC/team/document/metadata/tag/vector-search modules: 11,016.

## 1. SQL and ReBAC foundation

- [ ] 1.1 Introduce the bounded space identity and explicit organization/team/project parentage, personal-team kind and user organization; verify database constraints reject invalid kinds/parents and permit same team names in distinct organizations without changing existing IDs.
  First schema block adds `space` and its typed parent/name/personal-owner
  constraints, owned by control-plane. User organization, existing-team linkage,
  provisioning and runtime consumers remain pending; this is not a completed
  ownership cutover. Targeted migration/ownership suite: 50 passed (SQLite and
  real PostgreSQL). Fresh PostgreSQL `alembic upgrade head` passed; `alembic check`
  found no drift; sole head `bc21d49e01a7`. These checks concern the structural
  table, not the complete offline translator or final PR readiness.
- [x] 1.2 Separate platform anchors from organizations and implement four cumulative local roles plus parent-team-dependent project permissions in the existing FGA facade; verify the allow/deny matrix with real OpenFGA, including local-admin-without-analyst and organization-analyst-without-descendant-access.
  Real OpenFGA suite: 42 passed, including all four roles in each space kind,
  parent-admin isolation and immediate project denial after parent membership
  removal with surviving local grants. Existing operational gates, suspension
  and catalog anchors now use `platform:fred`; no compatibility alias remains.
  The unused team-to-singleton tuple, startup reconciliation and import repair
  were removed. Local organization administration and retirement of the old
  platform `team_manager` responsibilities remain stage 2 work.
  Targeted checks: core security 525 passed; control-plane 464 passed plus 115
  affected catalog checks after naming cleanup; core helpers/tasks 85 passed;
  runtime authorization 25 passed; Knowledge Flow ingestion/KPI 22 passed and
  startup 10 passed after correcting the account-model fixture. Counts overlap
  between runs. Three generated API clients are unchanged after regeneration;
  Knowledge Flow used an isolated local config with all existing routes enabled.
  Ruff/diff checks passed; raw basedpyright on the new SQL model and ReBAC engine
  files reported zero errors/warnings. No end-to-end performance claim yet.
  This FGA/platform block adds 259 and removes 527 production Python lines
  (net -268, including shorter comments); tests +477/-626, FGA source +63/-35,
  generated JSON +1/-1. The SQL block is recorded separately above. The actual
  removed behavior is structural repair, not generated-client churn.
  Focused author and independent read-only review covered SQL constraints,
  migration parity, local-role/revocation semantics, platform consumers and
  retired repair callers: no actionable findings. Reviewed planning base
  `58e0eeb07` through SQL commit `72e9a776e` plus this FGA working-tree block.
  Provisioning, cross-organization service enforcement, corpus/runtime cutover,
  migration/restore, UI and full PR verification are explicitly excluded;
  independent review inspected tests but did not rerun them.
- [ ] 1.3 Add linear, correctly owned Alembic migrations and target-schema installation/provisioning inputs, preserving shared-table ownership; verify one head per backend, empty-database upgrade, schema checks and explicit initial organization/team/personal assignment.
- [ ] 1.4 Establish protected-request authorization and canonical ancestry resolution with existing higher-consistency/batch support; verify revoked access is denied on the next request and request-local reuse does not become a cross-request positive cache.

## 2. Administration and membership

- [ ] 2.1 Adapt organization/team administration and add admin-only project creation with one-shot initial nomination, including creator self-nomination; verify editors cannot create projects and bootstrap cannot replace an existing project's admins.
- [ ] 2.2 Reuse role administration/audit for local self-grant of editor/analyst and local admission to existing closed spaces; verify outside parent admins cannot self-admit or nominate themselves and existing pending charter nominees gain no active-admin authority.
- [ ] 2.3 Scope user/team discovery, default-team enrollment and existing open-team joining to explicit organization ownership; verify same-organization member-only join and cross-organization denial without a new organization-creation UI.
- [ ] 2.4 Preserve the collaborative-team prerequisite, last-membership/account-removal lifecycle and owner-only personal teams; verify team removal denies all its projects immediately, cleans project roles, and does not affect unrelated memberships or expose personal content.
- [ ] 2.5 Regenerate changed API contracts and adapt existing membership consumers in the same stage; verify representative existing team/personal flows and record removed/retained governance paths.

## 3. Corpus conversion and deletion

- [ ] 3.1 Replace corpus membership arrays with canonical folder ownership and scalar constrained names; verify one-folder/one-space membership, same-folder conflict handling and valid folder hierarchy while preserving non-corpus tags and folderless session attachment metadata.
- [ ] 3.2 Convert upload/overwrite, source synchronization and import/export writers; verify stable UID/folder on overwrite, rejection of reparenting, synchronized-source restrictions and new-format ownership/role round trips.
- [ ] 3.3 Convert deletion, retries and quota accounting through existing lifecycle services; verify no stale/orphan hit is served, concurrent/retried mutations preserve constraints, and project storage is charged once to its parent team.
- [ ] 3.4 Gate metadata, direct content, vector and tabular retrieval by canonical contextual spaces before retrieval/ranking; verify ancestor-common reach, explicit folder subtree/document restrictions, empty intersection and stale-index rejection.
- [ ] 3.5 Replace folder item-ID payloads and per-folder permission projections with summaries and paginated document reads; verify lists/counts/deletion consumers no longer enumerate every document merely to render folders.
- [ ] 3.6 Remove corpus FGA tuples/writers, document permission loops/global lists and competing personal ownership paths after checking static/dynamic consumers; verify fixed-context authorization counts do not grow with corpus size and report gross production additions/deletions separately from generated churn.

## 4. Execution context and affected consumers

- [ ] 4.1 Separate agent owning space from immutable conversation execution space in control-plane, SDK and runtime resolution; verify organization/team agent reuse, project-local agents, server-validated ancestry and rejection of session context changes.
- [ ] 4.2 Carry context through ReAct/Deep tools, delegated calls, content URLs and service-identity evaluation paths; verify an unauthorized caller-supplied space cannot grant access and existing capability/model policies use the validated execution team.
- [ ] 4.3 Adapt history, memory, attachments, filesystem outputs and evaluation datasets to their execution space; verify ordinary conversation privacy, retrospective local analyst access, no inherited-author access and no upward publication of private outputs.
- [ ] 4.4 Preserve existing agent restrictions and fixed/selectable chat scope modes; verify team context excludes all projects, project context excludes siblings, and personal context sees only personal plus organization-common corpus.
- [ ] 4.5 Regenerate backend-derived clients and adapt required existing navigation, project/member operations and chat consumers using the design system; verify representative team/project/personal journeys without organization-creation UI, new scope widgets or document movement.
- [ ] 4.6 Expose effective context and source references through existing UI/audit surfaces; verify a new conversation is required after switching space and run only affected consumer checks before recording the stage's simplification evidence.

## 5. Offline cutover tooling

- [ ] 5.1 Complete the separate migration command around the target DDL with organization definitions, team allocation and initial organization-role inputs; verify installation and translation use the same schema and there is no translator/compatibility switch in serving code.
- [ ] 5.2 Translate supported existing users, personal teams, memberships, corpus, agents, conversations and evaluation references while preserving IDs; verify the supplied multi-organization allocation, zero initial projects and explicit reporting of the evaluation-role change.
- [ ] 5.3 Check source ownership/ACL representability before conversion, convert FGA platform/space relations and prepare index ownership metadata from SQL; verify intended role/content access, canonical counts/quotas and rejection of ambiguous/multi-folder data or exceptional legacy sharing without automatic reassignment.
- [ ] 5.4 Rehearse stop, coordinated backup, translation, validation and restart on an isolated representative copy; verify existing user journeys after restart and that no old runtime or worker remains active during cutover.
- [ ] 5.5 Rehearse restoration of old binaries/configuration, SQL, FGA and relevant file/index state; verify old-version access and content, and document exact commands, backup boundaries and loss of post-reopening writes in the PR's major-impact operator note.

## 6. Final integration and close-out

- [ ] 6.1 Run root code quality and the complete applicable offline suites, required real-store authorization/migration checks and agreed manual scenarios; verify fresh and migrated installs against the same acceptance requirements and record exact base/head and limitations.
- [ ] 6.2 Run the matched final performance workload across organizations/projects and increasing corpus sizes; verify the bounded authorization criteria, report request/whole-turn attempts, rows and latency against the baseline, and explain material regressions rather than hide them behind averages.
- [ ] 6.3 Perform one full author and independent read-only branch review, including applicable performance/contract/minimality/frontend checks; disposition all actionable findings in a batch, rerun affected evidence and record cumulative production LOC/concept reduction or any shortfall requiring developer decision.
- [ ] 6.4 Reconcile the RFC, shipped ReBAC/product/runtime contracts, relevant corpus/help docs and major-release operator note with the implementation; run migration-policy validation, sync/archive this change only after all tasks are complete, and make the single PR reviewable with no compatibility paths or unsupported readiness claims.
