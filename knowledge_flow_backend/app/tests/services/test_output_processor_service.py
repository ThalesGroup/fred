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

# app/tests/services/test_output_processor_service.py

import shutil
from pathlib import Path
import pytest
import pandas as pd
from typing import Tuple,List

from app.features.wip.input_processor_service import InputProcessorService
from app.features.wip.output_processor_service import OutputProcessorService
from app.features.wip import output_processor_service
from app.common.structures import OutputProcessorResponse
from app.core.processors.input.common.base_image_describer import BaseImageDescriber
from app.application_context import ApplicationContext
from app.core.processors.input.pdf_markdown_processor.pdf_markdown_processor import PdfMarkdownProcessor
from app.core.stores.vector.base_vector_store import BaseDocumentLoader
from app.core.stores.tabular.base_tabular_store import BaseTabularStore
from langchain.schema.document import Document


class DummyProcessor:
    def process(self, path, metadata):
        return OutputProcessorResponse(chunks=1, vectors=[], metadata=metadata)

class DummyDescriber(BaseImageDescriber):
    def describe(self, base64_image: str) -> str:
        return "This is a test image description"
    
class DummyDocumentLoader(BaseDocumentLoader):
    def load(self, file_path: str, metadata: dict) -> Document:
        return Document(page_content="abcdefg", metadata={})

class DummyTabularStore(BaseTabularStore):
    """
    Ultra-simple in-memory implementation for testing.
    """

    def __init__(self):
        self._store = {}

    def save_table(self, table_name: str, df: pd.DataFrame) -> None:
        self._store[table_name] = df

    def load_table(self, table_name: str) -> pd.DataFrame:
        return self._store[table_name]

    def delete_table(self, table_name: str) -> None:
        del self._store[table_name]

    def list_tables(self) -> List[str]:
        return list(self._store.keys())

    def get_table_schema(self, table_name: str) -> List[Tuple[str, str]]:
        df = self._store[table_name]
        return list(zip(df.columns, df.dtypes.astype(str)))





# ✅ Correct — define fixture at module level
@pytest.fixture
def prepared_pdf_dir(tmp_path, monkeypatch):
    from shutil import copy

    class DummyDescriber(BaseImageDescriber):
        def describe(self, base64_image: str) -> str:
            return "This is a test image description"

    context = ApplicationContext.get_instance()
    monkeypatch.setattr(
        context,
        "get_input_processor_instance",
        lambda ext: PdfMarkdownProcessor(image_describer=DummyDescriber()) if ext == ".pdf" else None,
    )

    source_file = Path("app/tests/assets/sample.pdf")
    target_file = tmp_path / source_file.name
    copy(source_file, target_file)

    InputProcessorService().process(tmp_path, target_file.name, {"origin": "test"})
    return tmp_path

class TestOutputProcessorService:
    @pytest.fixture
    def service(self):
        return OutputProcessorService()

    @pytest.fixture
    def prepared_docx_dir(self, tmp_path):
        source = Path("app/tests/assets/sample.docx")
        target = tmp_path / source.name
        shutil.copy(source, target)
        InputProcessorService().process(tmp_path, target.name, {"origin": "test"})
        return tmp_path

    # ✅ Nominal
    def test_process_real_pdf_success(self, service, prepared_pdf_dir):
        result = service.process(prepared_pdf_dir, "sample.pdf", {"meta": "pdf", "document_uid": "uid-123"})
        assert isinstance(result, OutputProcessorResponse)

    def test_process_real_docx_success(self, service, prepared_docx_dir):
        result = service.process(prepared_docx_dir, "sample.docx", {"meta": "docx", "document_uid": "uid-456"})
        assert isinstance(result, OutputProcessorResponse)

    # ❌ Failure
    def test_output_processor_missing_output_dir(self, service, tmp_path):
        with pytest.raises(ValueError, match="does not exist"):
            service.process(tmp_path, "fake.pdf", {})

    @pytest.mark.parametrize(
        "file_name, create_file, content",
        [
            ("not_a_dir", False, None),
            ("output/no_output_file", True, None),
            ("output/output.txt", True, ""),
            ("output/output.md", True, ""),
        ],
    )
    def test_output_processor_error_cases(self, service, tmp_path, file_name, create_file, content):
        output_path = tmp_path / file_name
        if create_file:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content or "")
        elif "not_a_dir" in file_name:
            (tmp_path / "output").write_text("this is not a directory")

        with pytest.raises(ValueError):
            service.process(tmp_path, "test.md", {"document_uid": "fail-case"})

    def test_output_processor_rejects_non_markdown_csv(self, monkeypatch, service, tmp_path):
        (tmp_path / "output").mkdir(parents=True)
        (tmp_path / "output" / "output.xlsx").write_text("fake content")

        class DummyContext:
            def get_output_processor_instance(self, ext):
                return DummyProcessor()
            def get_document_loader(self):
                return DummyDocumentLoader()
            def get_tabular_store(self):
                return DummyTabularStore()

        monkeypatch.setattr(output_processor_service.ApplicationContext, "get_instance", DummyContext)

        with pytest.raises(ValueError, match="is not a markdown or csv file"):
            service.process(tmp_path, "sample.xlsx", {"document_uid": "bad-ext"})

    def test_output_processor_empty_output_file(self, service, tmp_path):
        doc_path = tmp_path / "sample.pdf"
        output_dir = doc_path / "output"
        output_dir.mkdir(parents=True)
        (output_dir / "output.md").touch()

        with pytest.raises(ValueError, match="does not exist"):
            service.process(tmp_path, "sample.pdf", {})
