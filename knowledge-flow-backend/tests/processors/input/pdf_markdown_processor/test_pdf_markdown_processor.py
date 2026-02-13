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

# tests/test_pdf_processor.py

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from knowledge_flow_backend.core.processors.input.common.base_image_describer import BaseImageDescriber
from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import PdfMarkdownProcessor

dotenv_path = os.getenv("ENV_FILE", "./config/.env")
load_dotenv(dotenv_path)


class MockImageDescriber(BaseImageDescriber):
    def describe(self, image_base64: str) -> str:
        return "There is an image showing a mocked description."


@pytest.fixture
def processor():
    return PdfMarkdownProcessor()


@pytest.fixture
def sample_pdf_file():
    return Path(__file__).parent / "assets" / "sample.pdf"


def test_pdf_processor_end_to_end(processor: PdfMarkdownProcessor, sample_pdf_file):
    output_dir = Path("/tmp/knowledge_flow/test/output")
    output_dir.mkdir(exist_ok=True, parents=True)

    assert processor.check_file_validity(sample_pdf_file)

    metadata = processor.process_metadata(sample_pdf_file, [], "uploads")

    assert metadata.document_name == "sample.pdf"
    # assert metadata.num_pages == 2
    assert metadata.document_uid

    result = processor.convert_file_to_markdown(sample_pdf_file, output_dir, metadata.document_uid)

    md_file = Path(result["md_file"])
    assert md_file.exists()
    md_content = md_file.read_text(encoding="utf-8").strip()
    assert md_content != ""
