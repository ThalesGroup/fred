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

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.utils.image_transcription import ImageTranscription


class BasePdfExtractor(ABC):
    @abstractmethod
    def extract(self, file_path: Path, work_dir: str) -> tuple[str, List[ImageTranscription]]:
        """Extract Markdown text and image references from a PDF file.

        Args:
            file_path: Path to the source PDF file.
            work_dir: Directory where extracted image files can be written.

        Returns:
            A tuple of (markdown_text, images) where images is a list of
            ImageTranscription objects with image_path set and transcription empty.
        """
        pass
