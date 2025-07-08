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

logger = logging.getLogger(__name__)


class ContentStoreGcsSettings(BaseSettings):
    gcs_bucket_name: str = Field(..., validation_alias="GCS_BUCKET_NAME")
    gcs_credentials_path: str = Field(..., validation_alias="GCS_CREDENTIALS_PATH")
    gcs_project_id: str = Field(..., validation_alias="GCS_PROJECT_ID")

    model_config = {"extra": "ignore"}
