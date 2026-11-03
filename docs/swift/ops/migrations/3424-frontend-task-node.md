---
schema: 1
title: "Select installed Node 24 in the VS Code frontend task"
impact: none
configuration: local
configuration_reason: "Only the local VS Code frontend task initializes nvm; production configuration and chart values are unaffected."
no_action_reason: "Deployed images and runtime behavior are unchanged; normal deployment suffices."
---

## Applicability

Developers launching the frontend through VS Code tasks.

## Prerequisites

When using nvm, install a Node 24 version satisfying the frontend's existing
minimum version. Without nvm, keep a compatible Node version on PATH.

## Configuration

The frontend task loads nvm from NVM_DIR, defaulting to ~/.nvm, when present.
It selects the latest installed Node 24 on each launch and stops if activation
fails. Without nvm, the existing PATH-based Node check still applies.

## Upgrade

Deploy Fred normally; no operator action is required. Developers can relaunch
the frontend task without restarting VS Code or activating Node manually.

## Validation

Launch the frontend task with an older Node version inherited from the IDE.
Confirm it selects the installed Node 24 and passes the Make version check.

## Rollback

Use the normal rollback procedure. Reverting the task restores inherited PATH
selection and may require developers to activate Node manually again.

## Limitations

The task does not install Node or nvm. This change affects local development
only and introduces no data migration or runtime scaling changes.
