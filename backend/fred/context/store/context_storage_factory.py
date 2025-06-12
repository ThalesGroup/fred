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

from pathlib import Path
from fred.config.context_store_local_settings import ContextStoreLocalSettings
from fred.config.context_store_minio_settings import ContextStoreMinioSettings
from fred.main_utils import validate_settings_or_exit
from fred.context.store.base_context_store import BaseContextStore
from fred.context.store.local_context_store import LocalContextStore
from fred.context.store.minio_context_store import MinIOContextStore
from fred.application_context import get_configuration
from minio import Minio


def get_context_store() -> BaseContextStore:
    """
    Factory function to create a context store instance based on the configuration.
    Supports 'local' and 'minio' backends.
    """
    config = get_configuration().context_storage

    if config.type == "local":
        settings = validate_settings_or_exit(ContextStoreLocalSettings)
        return LocalContextStore(Path(settings.root_path).expanduser())

    elif config.type == "minio":
        settings = validate_settings_or_exit(ContextStoreMinioSettings)
        minio_client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure
        )
        return MinIOContextStore(minio_client, bucket_name=settings.minio_bucket_name)

    else:
        raise ValueError(f"Unsupported context storage backend: {config}")
