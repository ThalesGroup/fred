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

"""Issue #3059: nullable tabular results must survive HTTP JSON serialization."""

from datetime import datetime

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from fred_core.common import register_exception_handlers
from fred_core.documents.document_structures import FileType
from openpyxl import Workbook

from knowledge_flow_backend.core.processors.input.excel_processor.excel_processor import ExcelProcessor
from knowledge_flow_backend.core.processors.output.excel_processor.excel_table_registration_processor import ExcelTableRegistrationProcessor
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.tabular.controller import TabularController, tabular_service
from knowledge_flow_backend.security.weaver_admission import delegated_person
from tests.services.tabular_engine import TabularEngineHarness
from tests.services.test_tabular_service import _ingest_csv, _metadata, _user


@pytest.fixture
def tabular_app(app_context):
    """Expose the real routes over offline stores so assertions include JSON encoding."""
    app_context.get_content_store().clear()
    app = FastAPI()
    register_exception_handlers(app)
    router = APIRouter()
    TabularController(router)
    service = TabularEngineHarness()
    app.include_router(router)
    app.dependency_overrides[delegated_person] = _user
    app.dependency_overrides[tabular_service] = lambda: service
    return app, service


@pytest.mark.asyncio
@pytest.mark.parametrize("all_dates_missing", [False, True])
async def test_csv_query_serializes_missing_cells_without_losing_values(tmp_path, metadata_store, tabular_app, all_dates_missing):
    app, service = tabular_app
    first_date = "" if all_dates_missing else "2026-02-02"
    last_date = "" if all_dates_missing else "2026-02-03"
    await _ingest_csv(
        tmp_path=tmp_path,
        metadata_store=metadata_store,
        document_uid="nullable-csv",
        file_name="nullable.csv",
        content=f"reference,date_expedition,amount,active,note\nCMD001,{first_date},0,false,hello\nCMD002,,,,\nCMD003,{last_date},12.50,true,world\n",
    )
    [dataset] = await service.list_datasets(_user())
    sql = f"SELECT reference, CAST(date_expedition AS TIMESTAMP) AS date_expedition, amount, active, note FROM {dataset.query_alias} ORDER BY reference"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        response = await client.post("/tabular/query", json={"sql": sql, "dataset_uids": ["nullable-csv"]})
        limited = await client.post("/tabular/query", json={"sql": sql, "dataset_uids": ["nullable-csv"], "max_rows": 2})
        empty = await client.post("/tabular/query", json={"sql": f"SELECT * FROM {dataset.query_alias} WHERE FALSE"})

    assert response.status_code == 200, response.text
    assert response.json()["rows"] == [
        {"reference": "CMD001", "date_expedition": None if all_dates_missing else "2026-02-02T00:00:00", "amount": 0.0, "active": False, "note": "hello"},
        {"reference": "CMD002", "date_expedition": None, "amount": None, "active": None, "note": None},
        {"reference": "CMD003", "date_expedition": None if all_dates_missing else "2026-02-03T00:00:00", "amount": 12.5, "active": True, "note": "world"},
    ]
    assert response.json()["error"] is None
    assert response.json()["dataset_uids"] == ["nullable-csv"]
    assert limited.status_code == 200, limited.text
    assert limited.json()["rows"] == response.json()["rows"][:2]
    assert empty.status_code == 200, empty.text
    assert empty.json()["rows"] == []


@pytest.mark.asyncio
async def test_csv_search_serializes_missing_dates_and_keeps_truncation(tmp_path, metadata_store, tabular_app):
    app, service = tabular_app
    await _ingest_csv(
        tmp_path=tmp_path,
        metadata_store=metadata_store,
        document_uid="search-null-dates",
        file_name="search.csv",
        content="reference,date_expedition,amount\nCMD001,2026-02-02,0\nCMD002,,12.5\nCMD003,2026-02-03,20\n",
    )
    [dataset] = await service.list_datasets(_user())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        response = await client.post("/tabular/search", json={"keyword": "CMD", "dataset_uids": ["search-null-dates"], "max_rows_per_table": 2})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["tables_truncated"] is False
    assert payload["searched_dataset_uids"] == ["search-null-dates"]
    [match] = payload["matches"]
    assert match["query_alias"] == dataset.query_alias
    assert match["matched_columns"] == ["reference"]
    assert match["row_truncated"] is True
    assert match["rows"] == [
        {"reference": "CMD001", "date_expedition": "2026-02-02T00:00:00", "amount": 0.0},
        {"reference": "CMD002", "date_expedition": None, "amount": 12.5},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("date_type", ["DATE", "TIMESTAMP"])
async def test_extracted_excel_nullable_date_query_returns_json_null(tmp_path, tabular_app, date_type):
    app, service = tabular_app
    source = tmp_path / "dates.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Commandes"
    for row in [("reference", "date_expedition", "amount"), ("CMD001", datetime(2026, 2, 2), 0), ("CMD002", None, 12.5)]:
        sheet.append(row)
    sheet["B2"].number_format = "yyyy-mm-dd"
    workbook.save(source)

    processor = ExcelProcessor()
    processor.recalc = False  # No formulas in this offline fixture.
    output_dir = tmp_path / "extracted"
    processor.convert_file_to_markdown(source, output_dir, "nullable-excel")
    metadata = _metadata(document_uid="nullable-excel", file_name="dates.xlsx")
    metadata.file.file_type = FileType.XLSX
    metadata.file.mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    metadata = ExcelTableRegistrationProcessor().process(str(output_dir / "output.md"), metadata)
    await MetadataService().save_document_metadata(_user(), metadata)

    [dataset] = await service.list_datasets(_user())
    sql = f"SELECT reference, CAST(date_expedition AS {date_type}) AS date_expedition, amount FROM {dataset.query_alias} ORDER BY reference"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        response = await client.post("/tabular/query", json={"sql": sql, "dataset_uids": ["nullable-excel"]})

    assert response.status_code == 200, response.text
    assert response.json()["rows"] == [
        {"reference": "CMD001", "date_expedition": "2026-02-02T00:00:00", "amount": 0.0},
        {"reference": "CMD002", "date_expedition": None, "amount": 12.5},
    ]
