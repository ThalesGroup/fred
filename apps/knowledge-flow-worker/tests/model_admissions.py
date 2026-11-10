# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Control Plane admissions for tests, attested by the test workload's binding."""

from fred_sdk.contracts.weaver import InferenceAdmission, InferenceCredentialBinding

from knowledge_flow_worker.features.manager_processing.contracts import StageModels

TEST_BINDING = InferenceCredentialBinding(credential_binding="test", api_root="https://models.invalid/v1")


def admission(model: str = "test-embed") -> InferenceAdmission:
    return InferenceAdmission.model_validate(
        {
            "selection": {
                "key": {"source_id": "test", "upstream_model_id": model},
                "source": "default",
                "options": {},
                "source_revision": 1,
                "snapshot_revision": 1,
                "policy_revision": 1,
            },
            "connection": {
                "credential_binding": "test",
                "api_root": "https://models.invalid/v1",
                "wire": "openai_chat",
                "route": "standard",
                "dialect": "openai_compatible",
                "auth": {"kind": "none"},
            },
        }
    )


def indexing_models() -> StageModels:
    return StageModels(embedding=admission(), vision=None)


def extraction_models(vision: str | None = None) -> StageModels:
    return StageModels(embedding=None, vision=admission(vision) if vision else None)
