---
schema: 1
title: "Integrate PowerPoint builder with Weaver capability ownership"
impact: minor
configuration: none
configuration_reason: "The pod discovers ppt_builder from the existing PowerPoint package; no model-catalog configuration is added."
---

## Applicability

Weaver Python agent pods installing fred-capability-ppt-filler, plus the frontend and Rust Control Plane.

## Prerequisites

Back up the pod database before applying migrations. The new independent capability:ppt_builder Alembic tree creates cap_ppt_builder_analysis and cap_ppt_builder_deck_plan, with version table cap_ppt_builder_alembic_version. Agent images need LibreOffice Impress and the fonts documented in apps/fred-agents/THIRD_PARTY_FONT_NOTICES.md.

## Configuration

A platform administrator can manage one shared default template through the capability platform drawer. Organization capability enablement remains unchanged. The drawer uses the configured pod public_base_url; internal URLs and pod-supplied URLs are not browser authority. Vision labeling is unavailable: Weaver has no admitted turn-free inference path or authoritative vision metadata. Structural analysis and manual slide labeling remain available.

## Upgrade

Run the normal fred_runtime migrate initialization hook to include the capability tree, then deploy matched Weaver components. Refresh the pod capability inventory and enable ppt_builder through existing organization policy as required. The runtime migration chain and Rust SQLx chain are not rewritten.

## Validation

Check platform-admin writes and ordinary-user refusals, upload and analyze a shared template, review its patterns, then generate and download a deck using an enabled Python agent. Verify template fallback and PDF preview. Local automated checks do not establish these deployed journeys.

## Rollback

Stop writers and retain a coordinated backup. To remove only the new capability schema use an explicitly reviewed downgrade of capability:ppt_builder to base; it destroys saved templates and plans. Never downgrade the Rust SQLx chain through this CLI.

## Limitations

Per-agent multipart template uploads and persistent capability_pending suspension are deferred because Weaver's instance-save contract does not carry them. The form refuses pending uploads rather than silently discarding them; shared and built-in templates remain usable. The pod readiness hook is retained, without an unused public endpoint accepting client-authored instance state. Vision labeling and the Swift profile picker are deferred. Template and plan tables introduce additional capability-owned data; lifecycle purge integration and deployed multi-replica acceptance remain to validate. No arc42 journey is declared validated.
