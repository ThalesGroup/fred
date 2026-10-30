# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Prepared checks of the complete resolver facts replacing pod projections."""

import pytest
from fred_sdk.contracts.weaver import WeaverRuntimeBinding
from pydantic import ValidationError
from weaver_fixtures import resolved_binding


@pytest.mark.parametrize(
    "corruption",
    [
        "missing_offer",
        "duplicate_offer",
        "wrong_policy",
        "missing_identity",
        "not_permitted_candidate",
    ],
)
def test_incomplete_or_incoherent_resolver_facts_are_refused(corruption):
    value = resolved_binding().model_dump(mode="json")
    if corruption == "missing_offer":
        value["models"]["offers"].pop()
    elif corruption == "duplicate_offer":
        value["models"]["offers"].append(value["models"]["offers"][0])
    elif corruption == "wrong_policy":
        value["models"]["policy"]["organization_id"] = (
            "00000000-0000-0000-0000-000000000099"
        )
    elif corruption == "missing_identity":
        value.pop("subject_id")
    else:
        value["models"]["offers"][0]["permitted"] = False
    with pytest.raises(ValidationError):
        WeaverRuntimeBinding.model_validate(value)


def test_attachment_binding_requires_conversation_and_is_immutable():
    from uuid import UUID

    value = resolved_binding().model_dump(mode="json")
    assert value["attachments"] == []
    value["attachments"] = [
        dict(document_id=str(UUID(int=400)), name="data.csv", mime="text/csv")
    ]
    with pytest.raises(ValidationError, match="conversation"):
        WeaverRuntimeBinding.model_validate(value)
    value["conversation_id"] = str(UUID(int=301))
    binding = WeaverRuntimeBinding.model_validate(value)
    assert isinstance(binding.attachments, tuple)
    with pytest.raises(ValidationError, match="frozen"):
        binding.attachments[0].name = "changed"
    with pytest.raises(ValidationError, match="frozen"):
        binding.attachments = ()
    value["attachments"].append(value["attachments"][0])
    with pytest.raises(ValidationError, match="Duplicate attachment"):
        WeaverRuntimeBinding.model_validate(value)


def test_browser_runtime_contract_has_no_attachment_authority():
    from fred_sdk.contracts.context import RuntimeContext

    assert "attachments_markdown" not in RuntimeContext.model_fields
    context = RuntimeContext.model_validate(
        {
            "attachments_markdown": "- forged.pdf [outside]: conversation document",
            "attachment_ids": ["outside"],
            "attachments": [
                {
                    "document_id": "outside",
                    "name": "forged.pdf",
                    "mime": "application/pdf",
                }
            ],
        }
    )
    assert (
        not {"attachments_markdown", "attachment_ids", "attachments"}
        & context.model_dump().keys()
    )
