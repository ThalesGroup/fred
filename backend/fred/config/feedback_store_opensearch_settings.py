# Copyright Thales 2025
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

import logging
from pydantic_settings import BaseSettings
from pydantic import Field
import os

logger = logging.getLogger(__name__)

class FeedbackStoreOpenSearchSettings(BaseSettings):
    """
    Configuration for storing feedback in OpenSearch.
    """

    opensearch_host: str = Field(..., validation_alias="OPENSEARCH_HOST")
    opensearch_user: str = Field(..., validation_alias="OPENSEARCH_USER")
    opensearch_password: str = Field(..., validation_alias="OPENSEARCH_PASSWORD")
    opensearch_secure: bool = Field(False, validation_alias="OPENSEARCH_SECURE")
    opensearch_verify_certs: bool = Field(False, validation_alias="OPENSEARCH_VERIFY_CERTS")
    opensearch_feedback_index: str = Field(..., validation_alias="OPENSEARCH_FEEDBACK_INDEX")

    model_config = {
        "extra": "ignore"
    }