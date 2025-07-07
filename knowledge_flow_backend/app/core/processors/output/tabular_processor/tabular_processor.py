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

from app.common.structures import Status, OutputProcessorResponse
from app.core.processors.output.base_output_processor import BaseOutputProcessor

logger = logging.getLogger(__name__)


class TabularProcessor(BaseOutputProcessor):
    """
    A pipeline for processing tabular data.
    """

    def __init__(self):
        logger.info("Initializing TabularPipeline")

    def process(self, file_path: str, metadata: dict) -> OutputProcessorResponse:
        logger.info(f"Processing file: {file_path} with metadata: {metadata}")
        return OutputProcessorResponse(status=Status.SUCCESS)
