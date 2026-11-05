---
schema: 1
title: "Prepare Fred v3.10.0 release inputs"
impact: none
configuration: none
configuration_reason: "Release notes, Python release coordinates, dependency locks and pod chart appVersion metadata add no deployment settings."
no_action_reason: "This contribution consolidates the release inputs and corrects unpublished migration guidance; operational actions remain in the corresponding feature notes."
covers:
  - e6b471f70a76ab3a05ee20f2629a1466376d076b
  - 119a662d2ec06fb3e663158bb8e859f424142abc
  - 8710f3600211453964eead26e8b2c962d77186df
  - fb61751eedfb7006ee5e5c01dccd17ab703e04ee
  - 58561e5d9549fbcde0943a9292e88371d55cafa1
  - 9d7b5f9538e854028608439d90524ae9e4249537
  - 3a83244325f0f527f9789ace494eaf0e0854b345
  - a997ee4b3f8ff3053477c0d2399c2f79abadd580
---

## Applicability

Release preparation from code/v3.9.2, including reviewed contributions
without their own declarations: shared local uv cache reuse and two updates to
the maintainer Jira workflow. They change development tooling and instructions,
not deployed services, configuration, data or permissions.

Five dependency contributions update Black, OpenTelemetry and its exporter,
packaging, virtualenv, filelock, pyasn1, pypdf, fast-uri, happy-dom, undici,
KaTeX and minimatch. Their manifest and lock diffs add no deployment setting,
new service, schema migration or stored-data conversion. The existing Node 24
procedure covers frontend tooling requirements. PR and artifact checks validate
the resolved dependency graph; no extra operator action is introduced.

## Prerequisites

Follow the feature procedures in this release guide before deploying.

## Configuration

No additional configuration changes are introduced by release preparation.

The standard helper selects shared-library 4.5.10 from the stable code baseline,
but those coordinates were independently published after that tag with different
wheel contents. The merged PPT contribution advances fred-core, fred-sdk and
fred-runtime to 4.6.0 for its readiness and model interfaces. Release
preparation preserves that reviewed minor version and synchronizes selected
dependency floors and locks. The baseline remains code/v3.9.2; no existing
coordinate is overwritten.
The writable-document distribution advances to 4.5.2; only its editor manifest
advances from 0.1.0 to 0.1.1. The import-tool manifest remains 0.1.0.
The ppt-filler distribution advances to 4.5.3 and its existing ppt_filler manifest
to 0.1.1. The new ppt_builder manifest keeps its initial 0.1.0 version.

## Upgrade

Follow the ordered feature procedures. The unpublished frontend registry note
previously referenced an internal commit of squashed PR #3276; its aggregate
contribution already contains that note and needs no separate coverage entry.

## Validation

Verify the committed guide, prepared package artifacts, synchronized lockfiles
and release-preparation PR checks before approving the paired release tags.

## Rollback

Follow the feature-specific rollback limits. This preparation adds no migration.

## Limitations

Code/chart tag approval and Python package publication are separate decisions.
