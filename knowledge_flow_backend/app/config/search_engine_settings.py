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


class SearchEngineSettings(BaseSettings):
    """
    SearchEngine Settings
    -----------------
    This class is used to manage the configuration settings for SearchEngine. SearchEngine is used
    possibly for metadata storage and/or vector storage in the application.
    Attributes:
        search_engine_host (str): The SearchEngine server host.
        search_engine_user (str): The username for SearchEngine authentication.
        search_engine_password (str): The password for SearchEngine authentication.
        search_engine_secure (bool): Whether to use HTTPS for the connection.
        search_engine_vector_index (str): The name of the vector index in SearchEngine.
        search_engine_metadata_index (str): The name of the metadata index in SearchEngine.
    """

    search_engine_host: str = Field(..., validation_alias="OPENSEARCH_HOST")
    search_engine_user: str = Field(..., validation_alias="OPENSEARCH_USER")
    search_engine_password: str = Field(..., validation_alias="OPENSEARCH_PASSWORD")
    search_engine_secure: bool = Field(False, validation_alias="OPENSEARCH_SECURE")
    search_engine_vector_index: str = Field(..., validation_alias="OPENSEARCH_VECTOR_INDEX")
    search_engine_metadata_index: str = Field(..., validation_alias="OPENSEARCH_METADATA_INDEX")
    search_engine_verify_certs: bool = Field(False, validation_alias="OPENSEARCH_VERIFY_CERTS")
    model_config = {
        "extra": "ignore"  # allows unrelated variables in .env or os.environ
    }
