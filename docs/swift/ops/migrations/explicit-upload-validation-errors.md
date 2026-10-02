---
schema: 1
title: "Explain empty and unreadable document uploads"
impact: none
configuration: none
configuration_reason: "Only ingestion validation error messages change; no configuration keys or chart values change."
no_action_reason: "Existing validation outcomes and progress event fields remain unchanged; normal deployment is sufficient."
---
## Applicability

All deployments accepting document uploads.

## Prerequisites

No additional prerequisites.

## Configuration

No configuration changes.

## Upgrade

Deploy normally. No migration or re-ingestion is required.

## Validation

Upload a zero-byte PDF and confirm the UI explains that the file is empty and
suggests downloading or exporting it again, without a server path. A nonempty
unreadable PDF should advise checking the file in a reader and obtaining a new copy.

## Rollback

Deploy the previous version; only the error wording reverts.

## Limitations

The unreadable-PDF message does not identify a unique cause. Detailed parser
errors remain in the backend logs. Messages follow the existing English backend
error convention.
