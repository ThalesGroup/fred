---
schema: 1
title: "Knowledge Base publication requires operator-registered publishers"
impact: minor
configuration: production
configuration_reason: "The Control Plane gains knowledge_bases.publishers, documented in the Fred chart values and its generated schema; when omitted it is empty and no client may publish a Knowledge Base definition."
---
## Applicability

Deployments that run Knowledge Base pods. Until now any service identity could
publish a Knowledge Base definition, and the first client to publish under a
prefix owned it. From this release the Control Plane only accepts publications
from clients listed in `knowledge_bases.publishers`, each under the one prefix
listed for it. The list is empty by default: a deployment that does not list
its Knowledge Base clients sees their next publication refused with HTTP 403:
the pod's publish step, run once per deployment, exits with an error.

Deployments without Knowledge Base pods need no action: the empty default
changes nothing for them.

## Prerequisites

For each Knowledge Base pod, know its confidential client id (the token's
`azp`) and the prefix it publishes under (its `knowledge_base.prefix`
setting). No IAM, OpenFGA or database change is needed.

## Configuration

Before upgrading, list each Knowledge Base client and its prefix in the Fred
chart values, under
`applications.control-plane-backend.configuration.knowledge_bases.publishers`:

```yaml
knowledge_bases:
  publishers:
    - client_id: kb-acme
      prefix: acme.kb
```

A client may hold several entries. A prefix may appear only once, and no
registered prefix may cover another (`acme` and `acme.kb`): the Control Plane
refuses to start and names both entries. The prefix must be exactly the one the
pod publishes under, not a parent or a child of it.

## Upgrade

1. Add the `publishers` list above to the Control Plane values.
2. In Admin > Features > Knowledge Bases, review the published definitions.
   A definition already stored by a client you do not list stays in the
   catalog: it stays usable by the teams it is enabled for, but its pod can no
   longer republish it. Disable it for those teams if it should not be there.
3. Deploy the Control Plane normally, then deploy Knowledge Base pods as
   usual: each deployment replays its publication.

A prefix already bound to one client in the catalog stays bound to it: listing
it for another client does not move it, and that client's publication is
refused.

## Validation

- The Control Plane starts with the new values.
- Each Knowledge Base pod's publish step succeeds, and its definition appears
  in Admin > Features > Knowledge Bases.
- A refused publication answers 403 with a detail naming the client and
  `knowledge_bases.publishers`.

## Rollback

`helm rollback` restores the previous revision with its own values and needs
nothing more. To deploy the previous chart version with your current values
instead, remove `knowledge_bases.publishers` first: the previous chart's values
schema refuses the unknown key. No data is migrated, and publication returns to
the previous rule (the first client to publish under a prefix owns it).

## Limitations

Registration controls who publishes, not what a published pod may write: one
client still serves every team a definition is enabled for. Definitions stored
before the upgrade are not revoked automatically. The upgrade has been checked
with unit tests and configuration validation, not rehearsed on a production
deployment.
