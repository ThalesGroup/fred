---
schema: 1
title: "Relay binary bodies between hosted applications and their services"
impact: none
configuration: none
configuration_reason: "The frontend host page and the iframe SDK change; no setting, chart value or gateway rule is added. Upload size stays bounded by the existing FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE."
no_action_reason: "The host announces the new capability by itself and applications without the matching SDK keep the text transport, so a normal frontend deployment is enough."
after: [3211-compose-chart-registrations]
---

## Applicability

Fred deployments hosting applications in team iframes. The host now relays
`Blob` request bodies and, when the frame asks, `Blob` responses, and announces
`binary-bodies` in its context. Applications use it from
`@fred-oss/iframe-sdk` 0.1.1-alpha.1.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. An application that uploads files larger
than 10 MB needs `FRONTEND_APPLICATION_CLIENT_MAX_BODY_SIZE` raised on the Fred
frontend, as before this change.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.
Application owners adopt binary bodies by upgrading the iframe SDK.

## Validation

Open a hosted application and check that the `fred:context` message the frame
receives carries `capabilities: ["binary-bodies"]`.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
Applications then fall back to text: their binary bodies reject locally.

## Limitations

Transfers stay buffered in browser memory, without streaming or progress.
