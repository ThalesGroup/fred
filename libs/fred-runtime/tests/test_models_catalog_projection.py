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


def test_selected_reranker_is_part_of_the_strict_runtime_contract():
    value = resolved_binding().model_dump(mode="json")
    key = {"source_id": "rerank", "upstream_model_id": "ranker"}
    offer = value["models"]["offers"][0].copy()
    offer.update(
        key=key,
        permitted=True,
        candidate=False,
        selectable=True,
        diagnostics=["chat_not_established"],
    )
    offer["metadata"] = {**offer["metadata"], "chat": False, "rerank": True}
    value["models"]["policy"]["reranker"] = key
    value["models"]["policy"]["permitted"].append(key)
    value["models"]["offers"].append(offer)
    assert WeaverRuntimeBinding.model_validate(value).models.policy.reranker is not None
    value["models"]["offers"].pop()
    with pytest.raises(ValidationError, match="Incomplete or duplicate model facts"):
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


@pytest.mark.parametrize(
    "value", [None, ["invalid"], ["00000000-0000-0000-0000-000000000002"] * 2]
)
def test_invalid_admitted_corpus_is_rejected(value):
    data = resolved_binding().model_dump(mode="json")
    data["authorized_space_ids"] = value
    with pytest.raises(ValidationError):
        WeaverRuntimeBinding.model_validate(data)


def test_corpus_authority_is_required_and_cannot_come_from_browser_context():
    from fred_sdk.contracts.context import RuntimeContext

    data = resolved_binding().model_dump(mode="json")
    del data["authorized_space_ids"]
    with pytest.raises(ValidationError, match="authorized_space_ids"):
        WeaverRuntimeBinding.model_validate(data)
    browser = RuntimeContext.model_validate({"authorized_space_ids": ["forged"]})
    assert "authorized_space_ids" not in browser.model_dump()
