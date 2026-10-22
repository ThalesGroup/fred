---
schema: 1
title: "MCP SDK v2 compatibility for Fred agents and Knowledge Flow"
impact: none
configuration: none
configuration_reason: "MCP catalog keys, server URLs, transport choices and deployment values are unchanged."
no_action_reason: "The existing HTTP and stdio catalogs continue to work after a normal deployment; no data or IAM migration is required."
---

## Applicability

Fred agents using MCP tools and Knowledge Flow MCP endpoints.

## Prerequisites

Deploy the paired Fred agents and Knowledge Flow versions together. No additional
service or secret is required.

## Configuration

Keep the current MCP catalog configuration. Runtime transport support remains
`streamable_http` and `stdio`; this release does not add SSE or WebSocket.

## Upgrade

Deploy Fred normally. Knowledge Flow keeps its MCP URLs and serves each HTTP
request without an MCP session. Its private tool catalog cache hint lasts five
minutes per credential. The runtime reads a current bearer for each HTTP
request and retains the existing delegated grant rules.

## Validation

List and call a tool on the Knowledge Flow text, tabular and resources MCPs.
For delegated calls, verify the existing grant acceptance audit event.

## Rollback

Roll back Fred agents and Knowledge Flow together to the previous paired
version. No data rollback is needed.

## Limitations

Runtime support remains limited to the two transports above. Other optional
MCP v2 server features are not enabled by this compatibility change.
