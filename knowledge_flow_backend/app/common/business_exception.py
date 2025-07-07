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


class BusinessException(Exception):
    """Base class for business-related errors."""

    pass


class KnowledgeContextError(Exception):
    """Base class for knowledge context errors."""

    pass


class TokenLimitExceeded(KnowledgeContextError):
    pass


class DocumentProcessingError(KnowledgeContextError):
    def __init__(self, filename: str):
        super().__init__(f"Failed to process file '{filename}'")
        self.filename = filename


class KnowledgeContextNotFound(KnowledgeContextError):
    def __init__(self, profile_id: str):
        super().__init__(f"KnowledgeContext '{profile_id}' not found")
        self.profile_id = profile_id


class KnowledgeContextDeletionError(KnowledgeContextError):
    pass


class DocumentDeletionError(KnowledgeContextError):
    pass


class DocumentNotFound(KnowledgeContextError):
    pass
