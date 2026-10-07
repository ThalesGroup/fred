---
schema: 1
title: "Split document access into Attachments and Team documents"
impact: none
configuration: none
configuration_reason: "The document_access capability config and the agent form change; no deployment configuration key, chart value or default changes."
no_action_reason: "Stored agents are read through a compatibility mapping and rewritten to the new keys on their next save; the SDK keyword attachments_only keeps working as a deprecated alias."
---
## Applicability

Existing Fred deployments upgrading to this release, and authors of out-of-tree capabilities that call or implement `DocumentSearchPort.search`.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. The `document_access` capability (shown as "Documents") now has two positive settings, `attachments` and `team_documents`, replacing `show_attach_files_control` and `search_attachments_only`. Stored agents keep their behavior through a compatibility read: paperclip off means team documents only; paperclip on with attachments-only search means attachments only; otherwise both. Each agent is rewritten to the new keys the next time it is saved. A configuration with both sources off is rejected on save; in the agent form, turning off the last source turns "Documents" off instead.

The Simple agent form replaces the "Team resources" pack and its "Search in attachments only" switch with two packs, "Attachments" and "Team documents". The per-turn "Your documents" scope is hidden for agents without team documents.

`DocumentSearchPort.search(attachments_only=...)` is deprecated: pass `include_attachments` / `include_team_documents` instead. The old keyword still works and logs a warning once per process; its removal will be announced in a later migration note. The alias only narrows: `attachments_only=True` never re-enables attachments the caller turned off. Out-of-tree implementers of the port must accept the two new keywords. A pod that installs this `document_access` capability needs the Fred runtime from this release: an older runtime adapter rejects the new keywords.

Behavior change: an agent stored with the paperclip turned off no longer searches files attached to its conversations. It could not receive attachments through its own composer before this release. On an agent stored with attachments-only search, the "Your documents" scope (`corpus_only`) now returns no documents instead of falling back to attachments; the composer no longer offers it there.

## Validation

Open an agent that used "Search in attachments only" and confirm the "Attachments" pack reads on and "Team documents" reads off. In a conversation with that agent, confirm the paperclip is present and "Your documents" is not offered.

## Rollback

Use the normal rollback procedure; there is no data migration. Agents not re-saved since the upgrade keep working unchanged. An agent re-saved after the upgrade stores only the new keys, which the previous version ignores: it falls back to the defaults (paperclip on, team documents and attachments searched) until it is configured and saved again.

## Limitations

Summarize, verbatim reading and extraction are not bounded by the agent's sources; that ceiling remains an open question in the capability scope RFC.
