# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest

from knowledge_flow_worker.common.structures import Configuration


def test_configuration_normalizes_profile_retry_policy(app_context) -> None:
    """
    Ensure processing profile retry policy accepts compact operator-friendly values.

    Why:
        Production deployments should be able to tune ingestion retries from YAML
        without duplicating Temporal-specific parsing rules in each backend.
    How:
        Override one processing profile retry block in the config payload and
        validate the normalized values exposed by the profile model.
    """
    payload = app_context.configuration.model_dump(mode="python")
    payload["processing"]["profiles"]["medium"]["retry_initial_interval"] = "20s"
    payload["processing"]["profiles"]["medium"]["retry_maximum_interval"] = "5m"
    payload["processing"]["profiles"]["medium"]["retry_maximum_attempts"] = 8

    config = Configuration.model_validate(payload)

    medium = config.processing.profiles.medium
    assert medium.retry_initial_interval == "20s"
    assert medium.retry_maximum_interval == "5m"
    assert medium.retry_initial_interval_seconds == 20
    assert medium.retry_maximum_interval_seconds == 300
    assert medium.retry_maximum_attempts == 8


@pytest.mark.parametrize("field", ["push_metadata_activity_timeout", "output_activity_timeout"])
@pytest.mark.parametrize("value", [0, -1, "0s", "invalid"])
def test_data_stage_timeout_rejects_invalid_values(app_context, field, value):
    from pydantic import ValidationError

    payload = app_context.configuration.model_dump()
    payload["processing"]["profiles"]["medium"][field] = value
    with pytest.raises(ValidationError):
        type(app_context.configuration).model_validate(payload)
