---
schema: 1
title: "Copy an agent to other teams or the personal space from the agent card"
impact: none
configuration: none
configuration_reason: "Frontend and UI package change only; no configuration key, default or chart value changes."
no_action_reason: "The feature uses the control plane and agent pod operations shipped with it; existing agents are unchanged and Duplicate now goes through the same server copy."
---

## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

The control plane and the agent pods must run the same release, which adds the
copy endpoints and the pods' `copy-config` operation.

## Configuration

No change is required. Deployments that maintain their own MCP catalog should
make sure `chat_options.bound_library_ids` fields carry `scope_private: true`, as
the bundled catalog does. Without it, an agent copied to another team keeps the
origin team's library ids for that MCP server, which point to nothing there.

## Upgrade

Deploy Fred normally; no additional operator action is required.

## Validation

On an agent card, open the "⋮" menu and choose "Copy to…": the dialog lists
your personal space and the teams you edit. Copy an agent that uses the
PowerPoint filler: the copy fills a presentation without a new upload.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
Copied agents stay valid.

## Limitations

`@fred-oss/ui` consumers see an additive `Dialog` prop (`titleAddon`) and one
more bundled icon in the next package release.
