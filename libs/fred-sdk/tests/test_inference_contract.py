# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""The Python consumer rejects incomplete private admissions before execution."""

import json
from pathlib import Path

import pytest
from fred_sdk.contracts.weaver import InferenceAdmission, ModelConnection
from pydantic import ValidationError


def fixture():
    return json.loads(
        (Path(__file__).parent / "fixtures/inference_admission.json").read_text()
    )


def test_common_admission_round_trip():
    data = fixture()
    admission = InferenceAdmission.model_validate(data)
    assert admission.model_dump(mode="json", exclude_none=True) == data


@pytest.mark.parametrize(
    "parent,field",
    [
        ("selection", "key"),
        ("selection", "source"),
        ("selection", "options"),
        ("selection", "source_revision"),
        ("selection", "snapshot_revision"),
        ("selection", "policy_revision"),
        ("connection", "api_root"),
        ("connection", "credential_binding"),
        ("connection", "wire"),
        ("connection", "route"),
        ("connection", "dialect"),
        ("connection", "auth"),
    ],
)
def test_incomplete_descriptor_is_refused(parent, field):
    data = fixture()
    del data[parent][field]
    with pytest.raises(ValidationError):
        InferenceAdmission.model_validate(data)


@pytest.mark.parametrize("revision", [0, -1, "1", True])
def test_provisioning_revision_is_a_positive_strict_integer(revision):
    data = fixture()
    data["selection"]["source_revision"] = revision
    with pytest.raises(ValidationError):
        InferenceAdmission.model_validate(data)


CONNECTIONS = json.loads(
    (Path(__file__).parent / "fixtures/inference_connections.json").read_text()
)


@pytest.mark.parametrize("case", CONNECTIONS["valid"], ids=lambda case: case["name"])
def test_shared_valid_connection_and_its_only_url(case):
    connection = ModelConnection.model_validate(case["connection"])
    assert connection.model_dump(mode="json", exclude_none=True) == case["connection"]
    assert connection.request_url(case["model"]) == case["url"]


@pytest.mark.parametrize("case", CONNECTIONS["invalid"], ids=lambda case: case["name"])
def test_shared_invalid_connection(case):
    data = dict(CONNECTIONS["invalid_base"])
    for field, value in case["changes"].items():
        if value is None:
            del data[field]
        else:
            data[field] = value
    with pytest.raises(ValidationError):
        ModelConnection.model_validate(data)


def test_shared_invalid_base_is_valid_and_root_length_is_bounded():
    data = dict(CONNECTIONS["invalid_base"])
    ModelConnection.model_validate(data)
    data["api_root"] = "https://gateway.invalid/" + "a" * 2048
    with pytest.raises(ValidationError):
        ModelConnection.model_validate(data)
