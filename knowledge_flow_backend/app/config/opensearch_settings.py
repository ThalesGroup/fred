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


class OpenSearchSettings(BaseSettings):
    """
    Opensearch Settings
    -----------------
    This class is used to manage the configuration settings for OpenSearch. Opensearch is used
    possibly for metadata storage and/or vector storage in the application.
    Attributes:
        opensearch_host (str): The OpenSearch server host.
        opensearch_user (str): The username for OpenSearch authentication.
        opensearch_password (str): The password for OpenSearch authentication.
        opensearch_secure (bool): Whether to use HTTPS for the connection.
        opensearch_vector_index (str): The name of the vector index in OpenSearch.
        opensearch_metadata_index (str): The name of the metadata index in OpenSearch.
    """

    opensearch_host: str = Field(..., validation_alias="OPENSEARCH_HOST")
    opensearch_user: str = Field(..., validation_alias="OPENSEARCH_USER")
    opensearch_password: str = Field(..., validation_alias="OPENSEARCH_PASSWORD")
    opensearch_secure: bool = Field(False, validation_alias="OPENSEARCH_SECURE")
    opensearch_vector_index: str = Field(..., validation_alias="OPENSEARCH_VECTOR_INDEX")
    opensearch_metadata_index: str = Field(..., validation_alias="OPENSEARCH_METADATA_INDEX")
    opensearch_verify_certs: bool = Field(False, validation_alias="OPENSEARCH_VERIFY_CERTS")
    model_config = {
        "extra": "ignore"  # allows unrelated variables in .env or os.environ
    }
