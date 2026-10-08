---
schema: 1
title: "Split document access into Attachments and Team documents"
impact: minor
configuration: none
configuration_reason: "The document_access capability config and the agent form change; no deployment configuration key, chart value or default changes."
---
## Applicability

Existing Fred deployments upgrading to this release, and authors of out-of-tree capabilities that call or implement `DocumentSearchPort.search`.

## Prerequisites

After this PR merges, publish the new library versions before upgrading consumers: the four core Python libraries are `4.4.2`, document access is `0.1.2`, and the frontend packages are `0.1.1-alpha.0`. Every other publishable library under `libs/` also advances by one patch. Publication is a separate maintainer action. External capabilities must migrate the removed SDK keyword before deployment. These library patch increments are explicitly developer-approved despite the API break; this note records the required coordinated upgrade for the paired code/chart release.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The `document_access` capability (shown as "Documents") now has two positive settings, `attachments` and `team_documents`, replacing `show_attach_files_control` and `search_attachments_only`. Stored agents keep their behavior through a compatibility read: paperclip off means team documents only; paperclip on with attachments-only search means attachments only; otherwise both. Each agent is rewritten to the new keys the next time it is saved. A configuration with both sources off is rejected on save; in the agent form, turning off the last source turns "Documents" off instead.

The Simple agent form replaces the "Team resources" pack and its "Search in attachments only" switch with two packs, "Attachments" and "Team documents". The per-turn "Documents only" mode searches whichever sources the agent enables, including session attachments; it is available for attachments-only agents too.

`DocumentSearchPort.search(attachments_only=...)` has been removed immediately.
Replace `attachments_only=True` with `include_attachments=True,
include_team_documents=False`; omit the removed argument for the former
`False` default. Preserve any tighter source ceilings chosen by the caller.
Old calls now raise `TypeError`; no warning or compatibility alias remains.
Out-of-tree implementers must accept the two new keywords. Upgrade SDK and
runtime to `4.4.2` or later together with `fred-capability-document-access>=0.1.2`;
its SDK dependency now requires `fred-sdk[agents]>=4.4.2`. Deploy pods only after
these versions are published.

Behavior changes: a legacy agent with its paperclip off no longer searches
session attachments. "Documents only" (`corpus_only`) now includes attachments
when enabled, bounded by the agent and explicit turn scope. ReAct and Deep agents
receive a document-evidence-only instruction with no general-knowledge fallback;
custom Graph agents must enforce their own answer policy.

## Validation

Open an agent that used "Search in attachments only" and confirm the "Attachments" pack reads on and "Team documents" reads off. In a conversation with that agent, confirm the paperclip is present and "Documents only" is offered and searches attachments without reaching team documents. Check that SDK callers no longer pass `attachments_only`.

## Rollback

Roll back SDK, runtime, capability packages and migrated caller code together; there is no data migration. Agents not re-saved since the upgrade keep working unchanged. An agent re-saved after the upgrade stores only the new keys, which the previous version ignores: it falls back to the defaults (paperclip on, team documents and attachments searched) until it is configured and saved again.

## Limitations

Summarize, verbatim reading and extraction are not bounded by the agent's sources; that ceiling remains an open question in the capability scope RFC.
