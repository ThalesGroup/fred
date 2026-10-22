## Context

The pod loads discovery once at startup and retains one routable catalog snapshot. Control-plane reads that snapshot through `/agents/models-catalog`; managed turns already request a fresh runtime binding from control-plane. The pod holds the discovery bearer credential, while control-plane owns administrator settings. See proposal.md for the requested behavior.

## Goals / Non-Goals

**Goals:** Refresh and compare verified inventories when Models opens, apply an administrator's URL without a restart, preserve static profiles, and route a confirmed removed choice to a distinct platform fallback.

**Non-Goals:** Parse arbitrary vendor response formats, move credentials to control-plane, refresh on a timer, or substitute a model after an endpoint outage or authorization failure.

## Decisions

1. Store one override URL and the last successful model inventory per `source_id` in the existing PR's single Alembic revision. The pod YAML remains the fallback. Source state has a different lifecycle from per-model display names; keep the existing forced binding and store a separate platform fallback binding.
2. Accept absolute HTTP(S) URLs ending in `/models`, without userinfo, query, fragment, or redirects. The parent URL is the inference base, so the listed model IDs are sent to the endpoint that listed them. The pod uses its existing `OPENAI_API_KEY` for discovery and inference; control-plane never receives it.
3. Opening Features > Models requests a refresh. Control-plane passes the last successfully applied URL in each managed runtime binding. Each pod prepares a candidate using asynchronous HTTP; control-plane validates all candidates before asking pods to activate them. Activation failure triggers a best-effort rollback on every prepared pod. The active router and advertisement swap together. A failed refresh leaves the last successful source inventory intact; an unchanged URL does not trigger a discovery request on every turn.
4. Compare only successful inventories. Persist removed entries with their prior metadata and expose them as unavailable; a failed endpoint or pod fetch cannot create removals. New entries start without a platform default-on grant. Multi-pod removals require successful checks from all relevant enabled pods.
5. Send a separately configured platform fallback in the trusted per-turn binding. Apply it only when a selected profile is in the confirmed removed set. Keep the stored choice, log the actual model, and fail explicitly if the fallback cannot be used. The forced platform binding retains its absolute precedence.
6. The admin API lists source IDs with YAML defaults, saved overrides, last success, refresh error, new and removed IDs. Writes require `can_manage_capabilities`; an override can be saved only for an advertised source and commits only after a successful refresh. The Models tab shows the refresh summary before rows and states the OpenAI format limitation.
7. The pod's catalog reports the profile IDs appended by the successful discovery resolution, then projects their model IDs and source ID. Control-plane carries this provenance onto each model capability and its admin response, including across the existing multi-pod union. Features > Models renders separate manual and discovered sections with the same enablement controls. It does not infer origin from profile prefixes, model names, or wire IDs. The status panel names any advertised discovery source missing from URL management, even when other sources are registered. The inline display-name form keeps its current value and gives its label breathing room.

## Risks / Trade-offs

- A changed URL may return different IDs. Stable IDs retain their identities; confirmed removed IDs route to the fallback only when selected. Admin grants for new IDs remain explicit.
- A malicious endpoint could receive the pod credential. Only platform administrators may save URLs, and the UI describes the credential scope. Production operators should allowlist reachable hosts at the network layer.
- A pod or endpoint outage leaves the last verified inventory visible with a failure status. It does not prove that a model disappeared. A changed URL that cannot be verified cannot replace the active router.
- A pod can boot with static profiles if its YAML discovery endpoint is unavailable. A managed turn then applies the last successfully saved URL. A discovery-only pod cannot serve direct local turns until one endpoint responds.
- Activation across pods has no distributed transaction. If an activation response or rollback is lost, a pod may briefly carry a different snapshot. Each prepared pod reports its active revision; the next refresh chooses a revision above every pod and the stored revision so it can reconcile the deployment. No removals are committed from the failed attempt.

## Migration Plan

Deploy the migration and control-plane/pod/frontend together. Existing rows are absent, so YAML URLs and existing forced bindings remain effective. Rollback removes source state and fallback storage and returns to YAML-only discovery.
