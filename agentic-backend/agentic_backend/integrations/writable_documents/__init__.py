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

from agentic_backend.integrations.writable_documents.writable_document_tools import (
    WRITABLE_DOCUMENTS_PROVIDER,
    build_writable_document_tools,
)

__all__ = ["WRITABLE_DOCUMENTS_PROVIDER", "build_writable_document_tools"]
