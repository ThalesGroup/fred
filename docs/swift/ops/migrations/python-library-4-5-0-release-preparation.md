---
schema: 1
title: "Prepare the coordinated FRED Python library 4.5.0 release"
impact: none
configuration: none
configuration_reason: "Only Python distribution versions, internal dependency floors, lockfiles and release documentation change; deployment configuration is unaffected."
no_action_reason: "This preparation builds and validates artifacts but does not publish packages or change a running deployment."
---
## Applicability

Maintainers publishing the FRED Python distributions for external PyPI
consumers, including DT Agents and Aegis.

Version 4.5.0 is a minor release because the changes since 4.4.3 add
backward-compatible public behavior, including governed web research and PR
#3050's included-capability behavior in the SDK and runtime. No exported API
removal or mandatory operator migration was found, so a major version is not
required; a patch release would understate the added behavior.

## Prerequisites

Complete the build-only dry run and artifact inspection for every distribution
before approving publication. Confirm that the release credential has
account-wide authority to create the five capability project names that do not
yet exist on PyPI before updating any existing project.

## Configuration

No configuration changes are required.

## Upgrade

Publish the packages in the dependency order documented in
`docs/swift/RELEASE-STRATEGY.md`. This preparation stops before publication.

## Validation

Confirm every wheel reports version 4.5.0, carries only expected package files,
and floors its FRED runtime dependencies at 4.5.0.

## Rollback

Discard the uncommitted release-preparation changes. Published package versions
are immutable, but this preparation publishes nothing.

## Limitations

The five capability project names not already present on PyPI require verified
project-creation authority during the approved manual publication step. Do not
begin the coordinated upload until that prerequisite is satisfied.
