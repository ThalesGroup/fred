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

# app/core/processors/output/empty_output_processor.py

import logging

from app.common.document_structures import DocumentMetadata
from app.core.processors.output.base_output_processor import BaseOutputProcessor

logger = logging.getLogger(__name__)


class EmptyOutputProcessor(BaseOutputProcessor):
    """
    A no-op output processor that does nothing.

    Used to intentionally skip output processing for specific file types.
    """

    def __init__(self):
        super().__init__()

    def process(self, document_uid: str, document_content: str, metadata: DocumentMetadata) -> None:
        logger.info(f"Skipping output processing for document UID: {document_uid}")
        return  # Do nothing
