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

import asyncio
import json
from datetime import datetime

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from fred_core import get_current_user
from fred_core.common import register_exception_handlers
from fred_core.documents.document_structures import FileType
from openpyxl import Workbook

from knowledge_flow_backend.core.processors.input.excel_processor.excel_processor import ExcelProcessor
from knowledge_flow_backend.core.processors.output.excel_processor.excel_table_registration_processor import ExcelTableRegistrationProcessor
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.tabular.controller import TabularController
from tests.services.test_tabular_service import _ingest_csv, _metadata, _user


@pytest.fixture
def tabular_app(app_context):
    """Expose the real routes over offline stores so assertions include JSON encoding."""
    app_context.get_content_store().clear()
    app = FastAPI()
    register_exception_handlers(app)
    router = APIRouter()
    controller = TabularController(router)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _user
    return app, controller.service


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


@pytest.mark.asyncio
@pytest.mark.parametrize("via_mcp", [False, True])
async def test_row_limit_presence_survives_http_and_mcp(tmp_path, metadata_store, tabular_app, monkeypatch, via_mcp):
    import httpx2

    from knowledge_flow_backend import mcp_mount
    from tests.security.test_mcp_v2_mount import _request

    app, service = tabular_app
    await _ingest_csv(tmp_path=tmp_path, metadata_store=metadata_store, document_uid="limits", file_name="limits.csv", content="id\n" + "\n".join(str(i) for i in range(2105)))
    [dataset] = await service.list_datasets(_user())
    sql = f"SELECT id FROM {dataset.query_alias} ORDER BY id"

    async def authenticate(request, token):
        yield None

    monkeypatch.setattr(mcp_mount, "mcp_mount_auth", authenticate)
    if via_mcp:
        mcp_mount.mount_fastapi_tools(app, path="/mcp-test", name="Tabular", description="Tabular", tags={"Tabular"})
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test") as client:
            for extra, expected in [({}, 500), ({"max_rows": None}, 2105), ({"max_rows": 2100}, 2100), ({}, 500)]:
                arguments = {"sql": sql, **extra}
                if via_mcp:
                    response = await _request(client, "tools/call", {"name": "read_query", "arguments": arguments})
                    result = response.json()["result"]
                    assert not result.get("isError"), result
                    payload = result["structuredContent"]
                    assert json.loads(result["content"][0]["text"]) == payload
                else:
                    response = await client.post("/tabular/query", json=arguments)
                    payload = response.json()
                assert response.status_code == 200, response.text
                assert len(payload["rows"]) == expected
                assert payload["rows"][0] == {"id": 0}
                assert payload["rows"][-1] == {"id": expected - 1}
                if expected < 2105:
                    assert "dditional rows may match" in payload["message"]
                else:
                    assert payload["message"] is None
            if via_mcp:
                calls = await asyncio.gather(
                    *(_request(client, "tools/call", {"name": "read_query", "arguments": {"sql": sql, **extra}}) for extra in ({}, {"max_rows": None}, {}, {"max_rows": 2100}))
                )
                assert [len(call.json()["result"]["structuredContent"]["rows"]) for call in calls] == [500, 2105, 500, 2100]


@pytest.mark.asyncio
@pytest.mark.parametrize("max_rows,total,expected_count", [(500, 300, "300 rows matching"), (500, 600, "500 requested"), (None, 600, "Additional rows were omitted")])
async def test_character_truncation_message_counts_and_complete_rows(tmp_path, metadata_store, tabular_app, max_rows, total, expected_count):
    app, service = tabular_app
    await _ingest_csv(tmp_path=tmp_path, metadata_store=metadata_store, document_uid="wide", file_name="wide.csv", content="id,label\n" + "\n".join(f"{i},valeur-é" for i in range(total)))
    [dataset] = await service.list_datasets(_user())
    service.tabular_config.query.max_output_chars = 200
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/tabular/query", json={"sql": f"SELECT * FROM {dataset.query_alias} ORDER BY id", "max_rows": max_rows})
    assert response.status_code == 200, response.text
    payload = response.json()
    rows = payload["rows"]
    assert 0 < len(rows) < 10
    assert [row["id"] for row in rows] == list(range(len(rows)))
    assert all(row["label"] == "valeur-é" for row in rows)
    serialized = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    assert len(serialized) <= 200
    assert len(json.dumps(rows + [{"id": len(rows), "label": "valeur-é"}], ensure_ascii=False, separators=(",", ":"))) > 200
    assert expected_count in payload["message"]
    assert "avoid saturating the model context" in payload["message"]
    assert payload["error"] is None
    assert response.text.index('"rows"') < response.text.index('"message"')


@pytest.mark.asyncio
async def test_first_oversized_row_is_not_reported_as_no_matches(tmp_path, metadata_store, tabular_app):
    app, service = tabular_app
    await _ingest_csv(tmp_path=tmp_path, metadata_store=metadata_store, document_uid="huge", file_name="huge.csv", content="id,label\n0," + "x" * 100 + "\n1,small\n")
    [dataset] = await service.list_datasets(_user())
    service.tabular_config.query.max_output_chars = 30
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/tabular/query", json={"sql": f"SELECT * FROM {dataset.query_alias} ORDER BY id", "max_rows": None})
    payload = response.json()
    assert payload["rows"] == []
    assert "first row exceeds" in payload["message"]
    assert "columns" in payload["message"]
    assert "0 rows matched" not in payload["message"]
    assert payload["error"] is None
