---
schema: 1
title: "Use canonical document inventory for folder reads and deletion"
impact: none
configuration: none
configuration_reason: "Existing SQL membership and OpenFGA checks are reused; no service, chart or authorization-model setting changes."
no_action_reason: "A normal Knowledge Flow image deployment applies the fix without migration or reindexing."
---
## Applicability

Known-document and known-folder reads no longer intersect their SQL candidates
with a potentially truncated global document ListObjects response. Folder deletion
uses the stored owner/type/path subtree and canonical memberships, checks existing
permissions before removal, and refuses to delete a folder with remaining links.
Documents attached to another surviving folder are preserved.

## Prerequisites

Use the existing demo identities and teams, an idle local test deployment, and
working Knowledge Flow ingestion and embeddings for the validation campaign.

## Configuration

No application configuration change is required. The optional large test is
enabled only with `FRED_VALIDATION_LARGE_CORPUS=1` on the validation command.

## Upgrade

Deploy Knowledge Flow normally. No schema, FGA model, chart or frontend change is
required.

## Validation

Follow the [folder validation instructions](../../../../validation/README.md#folder-inventory-and-deletion)
for the small campaign and explicit opt-in workload above 1,000 readable documents.
Run against an idle local test deployment with the documented k3d login/demo and
embedding prerequisites. The large workload is not enabled by default.

Authorization cost follows the selected candidates: N unique document READ Checks,
at most ten concurrently, with no added document checks for irrelevant documents.
For deletion of F folders with N unique documents and M memberships, the healthy
path performs 1 + 2F + N + 2M permission Checks, plus the existing admission
account-status Check when enabled. Existing ownership ListUsers calls for quota
resolution and M parent-relation writes remain. This is a client RPC description,
not a bound on OpenFGA's graph evaluation work or a latency measurement.
Folder preflight checks also run in batches of ten; mutation remains sequential
between folders and in batches of five documents within each folder.

## Rollback

Reverting the image restores the truncation defect.

## Limitations

This change does not repair
previously orphaned data or make ingestion and deletion atomic. Artifact-store
failure recovery (#2144), partial revocation retry (#3121), and global authorization
concurrency (#2561) remain separate work. General discovery and label APIs can still
use truncated ListObjects results: #2845 remains open for that remaining scope.
Existing synchronous artifact deletion and folder-update mutation fan-out are
unchanged; this is not an asynchronous deletion or performance redesign.
