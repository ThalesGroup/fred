---
schema: 1
title: "Capture managed conversation traces for Fred support"
impact: minor
configuration: production
configuration_reason: "The Fred chart disables local trace access and labels model HTTP evidence with the Fred Agents image tag."
---

## Applicability

Fred deployments with a registered Fred Agents runtime. Capture starts off in shared deployments.

## Prerequisites

Control Plane must be able to migrate PostgreSQL and install the current OpenFGA authorization model. Fred Agents must use its registered workload client when calling Control Plane and have read, write, and delete access to its private runtime object storage.

## Configuration

Existing deployments can keep their configured values. The chart and backend schema default `conversation_trace_local_development` to false. Use Admin > Conversation traces to operate capture and grant the Trace reader role from Platform roles.

The explicit loopback-only, unsecured developer profile starts capture on and allows local content inspection. Shared profiles retain normal authentication and consent enforcement.

## Upgrade

Apply the Control Plane migrations for the catalog, consent, HTTP attempt index, SSE timeline, LangChain evidence index, and tool evidence index (`4d81a3f9b2c6`), then update its OpenFGA model using the standard deployment process. Deploy Fred Agents and the frontend. Enable capture in Admin when needed for an investigation. Existing rows retain their previous evidence. New captures populate the LangChain and tool indexes.

## Validation

Open Conversation traces as a platform admin or trace reader and verify capture is off. Enable it, run a managed chat turn, and confirm its masked entry appears under All. Disable capture and verify a subsequent unshared conversation does not appear. From the owner's Debug panel, share through a saved turn, confirm support can read that turn, then withdraw access and verify it is denied.

For a captured streaming turn, open the model attempt's SSE tab. Verify the provider and Fred lanes, the shared zoom window, and the consent requirement for original frames.

Open the LangChain tab on a shared turn and verify the invocation, bound tools, and output availability. For a known correction, follow its link to the original provider frame and verify the literal tool-call ID there.

For a shared turn with remote tool evidence, select the tool and open its HTTP tab. Verify the individual tool outcome, HTTP status, and turn outcome. Check that the raw response is readable only through consent.

## Rollback

Switch capture off before rolling back. An older runtime does not write trace summaries. Leave the additive catalog tables in place if the evidence must be retained during rollback. The migration downgrades drop the catalog, its settings, and consent records.

## Limitations

Capture starts at turn admission. Running turns admitted before disable can finalize. Masked views show diagnostic metadata. HTTP bytes are collected through the shared model, MCP, and direct Knowledge Flow clients within the runtime buffer budget. Slow, unavailable, or oversized evidence can be partial. Ordinary session erasure includes the private trace prefix.
