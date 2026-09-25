# Copyright Thales 2026
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

from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_plain_text_processor import (
    FastPlainTextProcessor,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_spreadsheet_processor import (
    FastSpreadsheetProcessor,
)


def test_fast_plain_text_processor_reads_markdown(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.md"
    file_path.write_text("# Sprint notes\n\nHello swift\n", encoding="utf-8")

    result = FastPlainTextProcessor().extract(file_path)

    assert result.document_name == "notes.md"
    assert "# Sprint notes" in result.text


def test_fast_spreadsheet_processor_reads_xlsx_preview(tmp_path: Path) -> None:
    file_path = tmp_path / "budget.xlsx"
    pd.DataFrame([{"city": "Paris", "amount": 10}, {"city": "Lyon", "amount": 20}]).to_excel(file_path, index=False, sheet_name="Sheet1")

    result = FastSpreadsheetProcessor().extract(file_path)

    assert "## Sheet: Sheet1" in result.text
    assert "Paris" in result.text
    assert result.page_count == 1
