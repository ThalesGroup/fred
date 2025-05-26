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

from pydantic_settings import BaseSettings
from pydantic import Field
import os
import logging
from typing import ClassVar

logger = logging.getLogger(__name__)

class MinioSettings(BaseSettings):
    """
    Settings for MinIO integration, sourced from environment variables.
    """
    # Variables d'environnement avec validation
    minio_endpoint: str = Field("localhost:9000", validation_alias="MINIO_ENDPOINT")
    minio_access_key: str = Field("minioadmin", validation_alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field("minioadmin", validation_alias="MINIO_SECRET_KEY")
    minio_bucket_name: str = Field("fred-storage", validation_alias="MINIO_BUCKET_NAME")
    minio_secure: bool = Field(False, validation_alias="MINIO_SECURE")
    minio_bucket_context_name: str = Field("agent-contexts", validation_alias="MINIO_BUCKET_CONTEXT_NAME")
    
    # Configuration du modèle
    model_config = {
        "extra": "ignore"
    }


# Default singleton instance
minio_settings = MinioSettings()
