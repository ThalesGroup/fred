---
schema: 1
title: "Enforce current document scope in corpus search"
impact: none
configuration: none
configuration_reason: "The fix uses existing metadata and authorization services; no chart or service setting changes."
no_action_reason: "Normal Knowledge Flow deployment applies the search restriction without a schema migration or reindex."
---
## Applicability

Deployments using Knowledge Flow corpus search, including OpenSearch. Explicit
document selections now respect the requested ownership context. Stale indexed
library memberships no longer authorize results after a document is unlinked.
Selecting a corpus document also preserves enabled conversation attachments.
Search result KPIs now count authorized hits per strategy branch. Rejected
candidates can therefore lower hit counts and increase empty-result counts;
metric names and the per-branch sampling unit remain unchanged.

## Prerequisites

Running Fred services, demo identities and teams, Knowledge Flow ingestion and
embeddings, and the public test assistant with the `document_access` capability.
See the [local integration-test prerequisites](../../../../validation/README.md#run-against-the-existing-k3d-deployment),
including password-grant login and model authorization for the no-LLM agent.

## Configuration

Use the existing validation endpoint variables to target the intended deployment.
For local k3d, use the realm URL trusted by its pods (`http://keycloak:8080/realms/app`),
with the workstation's existing `keycloak` host alias. See the README's complete
command and local direct-grant prerequisite. Keep test settings enabled across
manual reruns and restore their original values when the testing session ends.
No chart or service configuration changes are required.

## Upgrade

Deploy the updated Knowledge Flow image normally. No migration, reindex or
production data repair is required for search containment. Requests relying on
out-of-context document IDs or obsolete library memberships stop returning those
documents. When stale candidates occupy the retrieval pool, fewer than top_k
eligible results may be returned.

## Validation

Run `make integration-test-k3d` for the local cluster or
`make integration-test-docker` for the local Docker-backed setup with direct app
ports. Both call the existing `make validation-report`, which remains available
for custom endpoint configuration. These targets configure URLs only; the running
services, demo import and test authorizations remain prerequisites.

Document access, revocation and conversation freshness appear as a separate report group. Run the focused document-access
campaign with `VALIDATION_ARGS="scenarios/test_document_access.py"` to verify the
corrected service, including an existing runtime conversation with a new attachment
and a selected corpus document.

## Rollback

Reverting the Knowledge Flow image restores the vulnerable search behavior. The
campaign cleans up its own disposable fixtures; it does not change demo memberships
or existing documents.

## Limitations

This fix does not repair partially failed metadata/OpenFGA unlink operations or
establish active-team confinement for other document tools. Those parts of #3091
remain open. The live HTTP tests do not cover browser upload state or inject
OpenFGA outages; offline tests cover search authority failures. No atomic revocation
guarantee is added for requests already in progress.
