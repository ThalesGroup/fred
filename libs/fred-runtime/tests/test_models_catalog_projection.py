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
