# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""M4 fixtures. No network, credential provisioning or deployment."""

from fred_sdk.contracts.weaver import WeaverRuntimeBinding


def resolved_binding(
    *, source="a", default="first", permitted=True, candidate=True, diagnostics=()
):
    key = {"source_id": source, "upstream_model_id": "first"}
    fallback = {"source_id": source, "upstream_model_id": "second"}
    observation = dict(
        source_id=source,
        source_revision=1,
        enabled=True,
        state="ok",
        error_code=None,
        checked_at=None,
        last_success_at=None,
        snapshot_revision=1,
        snapshot_source_revision=1,
    )
    metadata = dict(
        chat=True,
        chat_provenance="source_guarantee",
        display_name=None,
        context_window_tokens=1000,
        max_input_tokens=None,
        max_output_tokens=100,
    )

    def offer(k, allowed, usable, reasons):
        return dict(
            key=k,
            permitted=allowed,
            candidate=usable,
            selectable=usable,
            diagnostics=reasons,
            metadata=metadata,
            observation=observation,
            connection=dict(
                provider="openai",
                api_root=f"https://{source}.invalid/v1",
                credential_binding=source,
            )
            if usable
            else None,
        )

    org = "00000000-0000-0000-0000-000000000001"
    return WeaverRuntimeBinding.model_validate(
        dict(
            subject_id="person",
            run_id="run",
            conversation_id=None,
            space=dict(
                id="00000000-0000-0000-0000-000000000002",
                kind="team",
                organization_id=org,
                team_id="00000000-0000-0000-0000-000000000002",
                project_id=None,
            ),
            agent=dict(
                instance_id="00000000-0000-0000-0000-000000000003",
                runtime_id="pod",
                template_id="00000000-0000-0000-0000-000000000004",
                template_key="template",
                configuration_updated_at="2026-10-26T00:00:00Z",
                configuration={"role": "Assistant", "description": "Example"},
            ),
            models=dict(
                policy=dict(
                    organization_id=org,
                    revision=1,
                    permitted=[key, fallback] if permitted else [fallback],
                    default=key if default == "first" else fallback,
                    fallback=fallback,
                    created_by=None,
                    created_at=None,
                    updated_by=None,
                    updated_at=None,
                ),
                recommendation=key,
                options={"max_tokens": 50},
                legacy_profile_id=None,
                requires_reselection=False,
                offers=[
                    offer(key, permitted, candidate, diagnostics),
                    offer(fallback, True, True, ()),
                ],
            ),
        )
    )
