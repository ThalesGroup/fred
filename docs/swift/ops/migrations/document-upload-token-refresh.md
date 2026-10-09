---
schema: 1
title: "Renew the browser token before document uploads and recover one HTTP 401"
impact: none
configuration: none
configuration_reason: "Only the browser multipart upload path changes; existing identity provider settings and chart values are unaffected."
no_action_reason: "The frontend reuses its existing token renewal service. No API, permission, stored data or deployment order changes are required."
---

## Applicability

Existing Fred deployments using document imports from the browser, in upload-only or upload-and-process mode.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Start a document import near the access token's expiry and verify that every file reaches its recorded outcome. A first HTTP 401 on the upload request triggers one token renewal and retry; a persistent refusal remains a visible upload failure.

## Rollback

Use the normal rollback procedure; this change introduces no data migration. Rolling back restores the previous upload behavior, including possible failures when a token expires.

## Limitations

The fix recovers one authentication refusal before ingestion starts. It does not retry denied permissions, expired login sessions, processing failures or interrupted accepted streams. Each attempt must still reach the backend's authentication check before its own token expires.
