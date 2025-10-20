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

import pandas as pd

from knowledge_flow_backend.common.document_structures import DocumentMetadata
from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseMarkdownProcessor, BaseTabularProcessor
from knowledge_flow_backend.core.processors.output.base_output_processor import BaseOutputProcessor


class TestMarkdownProcessor(BaseMarkdownProcessor):
    def check_file_validity(self, file_path: Path) -> bool:
        return True

    def extract_file_metadata(self, file_path: Path) -> dict:
        return {"title": "test-markdown"}

    def convert_file_to_markdown(self, file_path: Path, output_dir: Path, document_uid: str) -> dict:
        output_path = output_dir / "output.md"
        output_path.write_text("# Test Markdown Content")
        return {"markdown_path": str(output_path)}


class TestTabularProcessor(BaseTabularProcessor):
    def check_file_validity(self, file_path: Path) -> bool:
        return True

    def extract_file_metadata(self, file_path: Path) -> dict:
        return {"title": "test-tabular"}

    def convert_file_to_table(self, file_path: Path) -> pd.DataFrame:
        return pd.DataFrame({"col1": [1, 2], "col2": ["A", "B"]})


class TestOutputProcessor(BaseOutputProcessor):
    def process(self, file_path: str, metadata: DocumentMetadata) -> DocumentMetadata:
        return metadata
