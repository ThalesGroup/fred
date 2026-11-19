---
schema: 1
title: "Capture managed conversation traces for Fred support"
impact: minor
configuration: none
configuration_reason: "Capture is persisted in Control Plane. It uses existing runtime registration, machine authentication and OpenFGA configuration."
---

## Applicability

Fred deployments with a registered Fred Agents runtime. Capture starts off in shared deployments.

## Prerequisites

Control Plane must be able to migrate PostgreSQL and install the current OpenFGA authorization model. Fred Agents must use its registered workload client when calling Control Plane.

## Configuration

No production configuration changes are required. Use Admin > Conversation traces to operate capture. Platform admins can grant the Trace reader role from Platform roles.

## Upgrade

Apply the Control Plane migration and update its OpenFGA model using the standard deployment process. Deploy Fred Agents and the frontend. Enable capture in Admin when needed for an investigation.

## Validation

Open Conversation traces as a platform admin or trace reader and verify capture is off. Enable it, run a managed chat turn, and confirm its masked entry appears under All. Disable capture and verify a subsequent conversation does not appear.

## Rollback

Switch capture off before rolling back. An older runtime does not write trace summaries. Leave the additive catalog tables in place if the evidence must be retained during rollback. The migration downgrade drops the catalog and its settings.

## Limitations

Capture starts at turn admission. Running turns admitted before disable can finalize. Masked views show diagnostic metadata.
