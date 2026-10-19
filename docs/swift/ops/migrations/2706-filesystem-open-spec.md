---
schema: 1
title: "Open and edit Deep conversation files"
impact: minor
configuration: none
configuration_reason: "Uses the existing runtime conversation filesystem, bucket, quotas and erasure settings; no configuration key, chart value or credential changes."
---
## Applicability

Fred deployments upgrading Control Plane, agent runtimes and frontend with the
live Deep file editor and retirement of the temporary `open_writable_document`
importer. The main ReAct document and HTML capabilities remain supported.

## Prerequisites

The existing runtime conversation filesystem must be configured and available,
with its existing shared storage permissions. This feature adds no bucket or
permission grant.

## Configuration

No configuration changes are required. File contents, pending external changes
and published diffs use the existing conversation prefixes and namespace quotas;
the physical `scratchpad/` prefix remains unchanged.

## Upgrade

Use the normal paired application release. Where services roll independently,
update Control Plane before agent runtimes and frontend: its retirement rule
prevents the old availability sweep from treating the removed importer as a
missing capability. Then deploy the matching runtime and frontend with the
regenerated file API client. No document or database migration is required.

Saved importer selections are inactive and are removed on the next ordinary
agent configuration save. Existing imported documents remain in their legacy
store. If an old sweep suspended an importer-only agent during a mixed-version
rollout, the updated capability reconciliation clears that availability
suspension; unrelated missing/invalid capabilities still require their normal
repair. Do not remove those unrelated selections to mask a health failure.

## Validation

- With no document/HTML capability selected, ask a Deep agent to write and
  `open` a Markdown or HTML file. Edit it, send a continuation, and check that a
  later agent read sees the saved text. Markdown/Word export uses the saved file.
- After capability reconciliation, an agent selecting only the retired importer
  remains available and prepares/runs normally. An existing ReAct document can
  still be opened, edited and exported without migration.
- New external edits produce flat diffs under `/.deep/changes/<exchange-id>/` on
  the next user turn; the model receives bounded paths rather than inline diff
  or document content. HTML previews do not run scripts or fetch public assets.

## Rollback

Preserve all legacy document rows and conversation filesystem objects, including
internal change data, through rollback and existing erasure. Roll back to matching
Control Plane/runtime/frontend versions together; an older Control Plane paired
with the importer-free runtime can suspend saved importer selections. Older
viewers may not render the new file-reference parts. Retain a compatible runtime
and viewer to access them; do not convert files into legacy document rows or
reinterpret their stored contents.

## Limitations

Editor drafts survive local navigation but not browser reload; finish saves
before restarting the browser. Full replacements keep last-successful-write
semantics, with no automatic merge or stronger cross-replica transaction.
History consumes the existing internal quota and is retained until normal
conversation erasure; storage/quota failures are explicit. Binary/CSV/PDF viewers,
code execution and interactive HTML dashboards are outside this feature.
