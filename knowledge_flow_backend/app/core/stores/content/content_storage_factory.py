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

from app.application_context import ApplicationContext
from app.config.content_store_local_settings import ContentStoreLocalSettings
from pathlib import Path

from app.core.stores.content.base_content_store import BaseContentStore
from app.core.stores.content.local_content_store import LocalStorageBackend
from app.core.stores.content.minio_content_store import MinioStorageBackend


def get_content_store() -> BaseContentStore:
    """
    Factory function to get the appropriate storage backend based on configuration.
    Returns:
        StorageBackend: An instance of the storage backend.
    """
    # Get the singleton application context and configuration
    config = ApplicationContext.get_instance().get_config().content_storage
    backend_type = config.type

    if backend_type == "minio":
        return MinioStorageBackend(
            endpoint=config.endpoint,
            access_key=config.access_key,
            secret_key=config.secret_key,
            bucket_name=config.content_bucket_name,
            secure=config.secure
        )
    elif backend_type == "local":
        settings = ContentStoreLocalSettings()
        return LocalStorageBackend(Path(settings.root_path).expanduser())
    else:
        raise ValueError(f"Unsupported storage backend: {backend_type}")
