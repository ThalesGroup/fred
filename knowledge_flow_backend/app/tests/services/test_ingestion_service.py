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

"""
Test suite for the IngestionService class in ingestion_service.py.

Covers:
- File saving from disk and UploadFile
- Metadata extraction from document files
- Error handling when metadata or files are invalid

Mocks are used to simulate processing contexts where appropriate.
"""

from pathlib import Path
from io import BytesIO
import pytest
from fastapi import UploadFile
from app.features.ingestion.service import IngestionService


# ----------------------------
# ✅ Nominal Cases
# ----------------------------


def test_ingestion_service():
    """
    Test: end-to-end ingestion service behavior with a valid .docx sample file.
    Verifies file saving and metadata extraction.
    """
    ingestion_service = IngestionService()
    temp_file = ingestion_service.save_file_to_temp(Path("app/tests/assets/sample.docx"))
    assert temp_file.exists()
    assert temp_file.is_file()
    assert temp_file.name == "sample.docx"
    metadata = ingestion_service.extract_metadata(temp_file, [])
    assert isinstance(metadata.document_uid, str)



def test_save_file_to_temp_uploadfile():
    """
    Test: saves an UploadFile instance to a temporary path and verifies content integrity.
    """
    ingestion_service = IngestionService()
    content = b"Dummy content"
    upload_file = UploadFile(filename="test.txt", file=BytesIO(content))

    result_path = ingestion_service.save_file_to_temp(upload_file)
    assert result_path.exists()
    assert result_path.read_bytes() == content


def test_extract_metadata_no_extension(monkeypatch):
    """
    Test: raises AttributeError when the input file has no extension and cannot be processed.
    """
    ingestion_service = IngestionService()
    dummy_path = Path("filewithoutextension")

    monkeypatch.setattr(ingestion_service.context, "get_input_processor_instance", lambda suffix: None)

    with pytest.raises(AttributeError):
        ingestion_service.extract_metadata(dummy_path, {})


# ----------------------------
# ❌ Failure Cases
# ----------------------------

def test_save_file_to_temp_invalid_path():
    """
    Test: raises FileNotFoundError when attempting to save from a non-existent path.
    """
    ingestion_service = IngestionService()
    invalid_path = Path("nonexistent_file.docx")

    with pytest.raises(FileNotFoundError):
        ingestion_service.save_file_to_temp(invalid_path)
