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
from app.core.stores.knowledge_context.base_knowledge_context_store import BaseKnowledgeContextStore
from .local_knowledge_context_store import LocalKnowledgeContextStore
from pathlib import Path


def get_knowledge_context_store() -> BaseKnowledgeContextStore:
    """
    Factory method that returns the appropriate KnowledgeContextStore implementation
    based on the current application configuration.

    A KnowledgeContextStore is responsible for persisting and retrieving user- or
    project-specific context information that should be accessible to an agent during
    a conversation.

    This typically includes:
    - Structured or semi-structured **textual data** (e.g. notes, project descriptions)
    - Uploaded **files** (e.g. documents, reports, contracts)
    - Any other input that contributes to the *knowledge state* associated with a user or profile.

    The goal is to allow the agent to retrieve and leverage this context dynamically
    during a chat session to offer more personalized and relevant answers.

    The backing implementation can vary:
    - 'local' for local filesystem-based persistence
    - other types (e.g., cloud, database, S3) may be added in the future

    Returns:
        An instance of a subclass of BaseKnowledgeContextStore.
    """
    config = ApplicationContext.get_instance().get_config()
    backend_type = config.knowledge_context_storage.type  # e.g., "local"

    if backend_type == "local":
        # For the "local" backend, we store all profile context data (text/files)
        # in a user-defined directory path on the local filesystem.
        # Expand ~ if present (e.g., "~/myapp/data")
        local_path = Path(config.knowledge_context_storage.settings.local_path).expanduser()

        # Ensure that the directory exists. If it doesn't, create it (including parents).
        # This allows the application to initialize correctly without manual setup.
        local_path.mkdir(parents=True, exist_ok=True)

        # Return a LocalKnowledgeContextStore instance pointing to this path.
        # This store will be used by the agent to access per-profile context info.
        return LocalKnowledgeContextStore(local_path)
    else:
        # Unknown backend type — this is treated as a configuration error.
        raise ValueError(f"Unsupported backend for chat profile: {backend_type}")
