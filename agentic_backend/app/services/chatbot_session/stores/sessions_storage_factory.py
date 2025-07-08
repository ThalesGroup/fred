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

from app.application_context import get_configuration

from app.services.chatbot_session.abstract_session_backend import AbstractSessionStorage
from app.services.chatbot_session.stores.in_memory_session_store import InMemorySessionStorage
from app.services.chatbot_session.stores.opensearch_session_store import OpensearchSessionStorage

def get_sessions_store() -> AbstractSessionStorage:
    """
    Factory function to create a sessions store instance based on the configuration.
    As of now, it supports in_memory and OpenSearch sessions storage.
    Returns:
        AbstractSessionStorage: An instance of the sessions store.
    """
    # Get the sessions storage configuration from the application context
    config = get_configuration().session_storage

    if config.type == "in_memory":
        return InMemorySessionStorage()
    elif config.type == "opensearch":
        settings = config.settings
        return OpensearchSessionStorage(
            host=settings.host,
            username=settings.username,
            password=settings.password,
            secure=settings.secure,
            verify_certs=settings.verify_certs,
            sessions_index=settings.sessions_index,
            history_index=settings.history_index
        )
    else:   
        raise ValueError(f"Unsupported sessions storage backend: {config.type}")
