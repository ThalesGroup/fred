# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Only M3 instance options are accepted by Weaver."""

import pytest
from fred_sdk.contracts.weaver import ModelOptions
from pydantic import ValidationError


def test_weaver_instance_options_refuse_reasoning_settings() -> None:

    with pytest.raises(ValidationError):
        ModelOptions.model_validate({"reasoning_effort": "high"})
