---
schema: 1
title: "Show deliverable generation before publication"
impact: none
configuration: none
configuration_reason: "Preparation tools follow existing capability activation and template configuration; no new chart or application setting is needed."
no_action_reason: "Deploy the updated frontend and agent pod normally. No stored data migration or operator action is required."
---

## Applicability

This change adds preparation tools and live composition/publication labels for
writable documents, configured PowerPoint templates, and static HTML artifacts.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

On an enabled ReAct agent, request a document or HTML artifact, or fill a
configured PowerPoint template. Confirm preparation completes before the content
generation label appears, followed by publication and the existing deliverable.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The instructed workflow adds one ordinary tool call and one model round per
generation, including revisions. Existing call budgets still apply. Publication
tools remain callable directly; old pods continue to work with the updated UI.
