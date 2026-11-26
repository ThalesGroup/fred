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

"""Targeted revisions: changes applied to the delivered request, then rebuilt."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
from fred_capability_spreadsheet.revisions import ChangeError, apply_changes
from fred_capability_spreadsheet.workbook import (
    CreateSpreadsheetInput,
    build_workbook,
    prepare,
)
from openpyxl import load_workbook
from test_capability import FakeWorkspace, _tool

BUDGET: dict[str, Any] = {
    "file_name": "Budget",
    "language": "fr",
    "sheets": [
        {
            "name": "Budget",
            "columns": [
                {"header": "Poste"},
                {"header": "Budget", "type": "currency", "total": "sum"},
                {"header": "Réel", "type": "currency", "total": "sum"},
            ],
            "rows": [
                ["Loyer", 1200, 1150],
                ["Voyages", 300, 350],
                ["Matériel", 500, 0],
            ],
        },
        {
            "name": "Synthèse",
            "columns": [
                {"header": "Indicateur"},
                {"header": "Valeur", "type": "number"},
            ],
            "rows": [
                ["Budget total", {"formula": "=SUM(Budget!B2:B4)"}],
                ["Loyer réel", {"formula": "=Budget!C2"}],
            ],
        },
    ],
}


def _apply(
    *changes: dict[str, Any], base: dict[str, Any] | None = None
) -> dict[str, Any]:
    return apply_changes(base or BUDGET, list(changes))


def _refused(*changes: dict[str, Any], base: dict[str, Any] | None = None) -> str:
    with pytest.raises(ChangeError) as info:
        _apply(*changes, base=base)
    return str(info.value)


def _sheets(spec: dict[str, Any]) -> dict[str, Any]:
    return {s["name"]: s for s in spec["sheets"]}


def _cell_formula(spec: dict[str, Any], sheet: str, row: int, column: int) -> str:
    return _sheets(spec)[sheet]["rows"][row][column]["formula"]


def test_add_a_formula_column_keeps_everything_else():
    spec = _apply(
        {
            "op": "add_column",
            "sheet": "Budget",
            "column": {
                "header": "Écart",
                "type": "currency",
                "formula": "=C2-B2",
            },
        }
    )
    budget = _sheets(spec)["Budget"]
    assert [c["header"] for c in budget["columns"]] == [
        "Poste",
        "Budget",
        "Réel",
        "Écart",
    ]
    assert budget["rows"][0] == ["Loyer", 1200, 1150, None]
    ws = load_workbook(
        io.BytesIO(build_workbook(prepare(CreateSpreadsheetInput.model_validate(spec))))
    )["Budget"]
    assert ws["D2"].value == "=C2-B2"


def test_appended_rows_extend_ranges_that_ended_on_the_last_data_row():
    spec = _apply(
        {"op": "add_rows", "sheet": "Budget", "rows": [["Formation", 100, 80]]}
    )
    assert _sheets(spec)["Budget"]["rows"][-1] == ["Formation", 100, 80]
    assert _cell_formula(spec, "Synthèse", 0, 1) == "=SUM(Budget!B2:B5)"
    assert _cell_formula(spec, "Synthèse", 1, 1) == "=Budget!C2"


def test_rows_inserted_inside_a_range_widen_it_and_shift_cells():
    spec = _apply(
        {"op": "add_rows", "sheet": "Budget", "rows": [["Taxes", 10, 10]], "after": 2}
    )
    assert _sheets(spec)["Budget"]["rows"][1][0] == "Taxes"
    assert _cell_formula(spec, "Synthèse", 0, 1) == "=SUM(Budget!B2:B5)"
    assert _cell_formula(spec, "Synthèse", 1, 1) == "=Budget!C2"
    # Above the first row of a range, as in Excel, the range moves down.
    spec = _apply(
        {"op": "add_rows", "sheet": "Budget", "rows": [["Taxes", 10, 10]], "after": 1}
    )
    assert _cell_formula(spec, "Synthèse", 0, 1) == "=SUM(Budget!B3:B5)"
    assert _cell_formula(spec, "Synthèse", 1, 1) == "=Budget!C3"


def test_rows_as_objects_by_header():
    spec = _apply(
        {"op": "add_rows", "sheet": "Budget", "rows": [{"Poste": "Taxes", "Réel": 5}]}
    )
    assert _sheets(spec)["Budget"]["rows"][-1] == ["Taxes", None, 5]


def test_split_a_table_into_two_sheets():
    base = {
        "file_name": "Ventes",
        "sheets": [
            {
                "name": "Ventes",
                "columns": [
                    {"header": "Client"},
                    {"header": "Région"},
                    {"header": "CA", "type": "number", "total": "sum"},
                ],
                "rows": [
                    ["A", "Nord", 1],
                    ["B", "Sud", 2],
                    ["C", "Nord", 3],
                    ["D", "sud", 4],
                ],
            }
        ],
    }
    spec = _apply(
        {
            "op": "move_rows",
            "sheet": "Ventes",
            "where": {"column": "Région", "equals": "Sud"},
            "to_sheet": "Sud",
        },
        {"op": "rename_sheet", "sheet": "Ventes", "name": "Nord"},
        base=base,
    )
    sheets = _sheets(spec)
    assert list(sheets) == ["Nord", "Sud"]
    assert sheets["Nord"]["rows"] == [["A", "Nord", 1], ["C", "Nord", 3]]
    assert sheets["Sud"]["rows"] == [["B", "Sud", 2], ["D", "sud", 4]]
    assert sheets["Sud"]["columns"][2]["total"] == "sum"
    prepared = prepare(CreateSpreadsheetInput.model_validate(spec))
    assert [s.totals[2] for s in prepared.sheets if s.totals] == [4, 6]


def test_move_to_an_existing_sheet_maps_columns_by_header():
    base = json.loads(json.dumps(BUDGET))
    base["sheets"].append(
        {
            "name": "Archive",
            "columns": [
                {"header": "Réel", "type": "currency"},
                {"header": "Poste"},
                {"header": "Budget", "type": "currency"},
            ],
            "rows": [],
        }
    )
    # The summary sums the moved row: refused until that formula is edited too.
    move = {"op": "move_rows", "sheet": "Budget", "rows": [4], "to_sheet": "Archive"}
    assert "move to 'Archive'" in _refused(move, base=base)
    spec = _apply(
        move,
        {
            "op": "edit_cell",
            "sheet": "Synthèse",
            "cell": "B2",
            "value": {"formula": "=SUM(Budget!B2:B3)"},
        },
        base=base,
    )
    assert _sheets(spec)["Archive"]["rows"] == [[0, "Matériel", 500]]


def test_rename_a_sheet_rewrites_every_reference():
    spec = _apply({"op": "rename_sheet", "sheet": "Budget", "name": "Données 2025"})
    assert _cell_formula(spec, "Synthèse", 0, 1) == "=SUM('Données 2025'!B2:B4)"
    assert _cell_formula(spec, "Synthèse", 1, 1) == "='Données 2025'!C2"


def test_removing_a_referenced_cell_names_the_formula():
    message = _refused({"op": "remove_rows", "sheet": "Budget", "rows": [2]})
    assert "cell B3" in message and "reads row 2 of sheet 'Budget'" in message
    # Inside a range only, the range shrinks as in Excel.
    spec = _apply(
        {"op": "remove_rows", "sheet": "Budget", "rows": [3]},
    )
    assert _cell_formula(spec, "Synthèse", 0, 1) == "=SUM(Budget!B2:B3)"


def test_removing_a_column_a_formula_column_reads_is_refused():
    base = _apply(
        {
            "op": "add_column",
            "sheet": "Budget",
            "column": {"header": "Écart", "formula": "=C2-B2"},
        }
    )
    message = _refused(
        {"op": "remove_column", "sheet": "Synthèse", "column": "Valeur"},
        {"op": "remove_column", "sheet": "Budget", "column": "Réel"},
        base=base,
    )
    assert "column 'Écart'" in message and "which these changes remove" in message


def test_removing_every_row_of_a_subrange_does_not_retarget_other_rows():
    base = {
        "file_name": "Ranges",
        "sheets": [
            {
                "name": "Data",
                "columns": [{"header": "N", "type": "number"}],
                "rows": [[10], [20], [30], [40], [50]],
            },
            {
                "name": "Summary",
                "columns": [{"header": "N", "type": "number"}],
                "rows": [[{"formula": "=SUM(Data!A3:A4)"}]],
            },
        ],
    }
    message = _refused(
        {"op": "remove_rows", "sheet": "Data", "rows": [3, 4]}, base=base
    )
    assert "sheet 'Summary', cell A2" in message
    assert "every row it reads on sheet 'Data' is removed" in message
    for removed, expected in [(3, 30), (4, 20)]:
        spec = _apply(
            {"op": "remove_rows", "sheet": "Data", "rows": [removed]}, base=base
        )
        cached = load_workbook(
            io.BytesIO(
                build_workbook(prepare(CreateSpreadsheetInput.model_validate(spec)))
            ),
            data_only=True,
        )
        assert cached["Summary"]["A2"].value == expected


def test_moving_an_interior_row_of_a_referenced_range_is_refused():
    message = _refused(
        {"op": "move_rows", "sheet": "Budget", "rows": [3], "to_sheet": "Moved"}
    )
    assert "sheet 'Synthèse', cell B2" in message
    assert "reads row 3 of sheet 'Budget'" in message
    assert "move to 'Moved'" in message


def test_cross_sheet_column_references_refuse_row_shifts_but_keep_safe_edits():
    base = {
        "file_name": "Links",
        "sheets": [
            {
                "name": "Data",
                "columns": [{"header": "N", "type": "number"}],
                "rows": [[10], [20], [30]],
            },
            {
                "name": "Summary",
                "columns": [{"header": "N", "formula": "=Data!A2"}],
                "rows": [[None], [None]],
            },
        ],
    }
    insert = {"op": "add_rows", "sheet": "Data", "after": 1, "rows": [[99]]}
    message = _refused(insert, base=base)
    assert "column 'N' of sheet 'Summary'" in message
    assert "relative reference to sheet 'Data'" in message
    assert "edit or remove that formula" in message
    message = _refused({"op": "remove_rows", "sheet": "Data", "rows": [3]}, base=base)
    assert "relative reference to sheet 'Data'" in message
    for changes in [
        [{**insert, "after": 4}],
        [{**insert, "after": 3}],
        [
            insert,
            {
                "op": "edit_column",
                "sheet": "Summary",
                "column": "N",
                "formula": "=Data!A3",
            },
        ],
    ]:
        spec = _apply(*changes, base=base)
        cached = load_workbook(
            io.BytesIO(
                build_workbook(prepare(CreateSpreadsheetInput.model_validate(spec)))
            ),
            data_only=True,
        )
        assert [cached["Summary"][f"A{r}"].value for r in [2, 3]] == [10, 20]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("op", "remove_source_row"),
    [("remove_rows", False), ("remove_rows", True), ("move_rows", False)],
)
async def test_removing_last_summary_row_keeps_surviving_cross_sheet_reference(
    op,
    remove_source_row,
):
    base = {
        "file_name": "Links",
        "sheets": [
            {
                "name": "Data",
                "columns": [{"header": "N", "type": "number"}],
                "rows": [[10], [20], [30]],
            },
            {
                "name": "Summary",
                "columns": [{"header": "N", "formula": "=Data!A2"}],
                "rows": [[None], [None]],
            },
        ],
    }
    changes = [{"op": op, "sheet": "Summary", "rows": [3], "to_sheet": "Moved"}]
    if remove_source_row:
        changes.append({"op": "remove_rows", "sheet": "Data", "rows": [3]})
    if op == "move_rows":
        workspace = FakeWorkspace()
        text, artifact = await _tool(workspace)(**base)
        assert not artifact.is_error, text
        writes = list(workspace.writes)
        text, artifact = await _tool(workspace)(
            changes=changes, **workspace.references()
        )
        assert artifact.is_error and "relative reference to sheet 'Data'" in text
        assert workspace.writes == writes
        return
    spec = _apply(*changes, base=base)
    data = build_workbook(prepare(CreateSpreadsheetInput.model_validate(spec)))
    formulas = load_workbook(io.BytesIO(data))["Summary"]
    cached = load_workbook(io.BytesIO(data), data_only=True)["Summary"]
    assert formulas.max_row == 2
    assert formulas["A2"].value == "=Data!A2"
    assert cached["A2"].value == 10


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "formula", ["=SUM(A2:A2)", "=SUM($A2:$A2)", "=SUM(Data!A2:A2)", "=Data!A2"]
)
async def test_moving_a_row_keeps_column_ranges_relative_to_each_own_row(formula):
    base = {
        "file_name": "Rows",
        "sheets": [
            {
                "name": "Data",
                "columns": [
                    {"header": "N", "type": "number"},
                    {"header": "Sum", "formula": formula},
                ],
                "rows": [[10, None], [20, None], [30, None]],
            }
        ],
    }
    change = {"op": "move_rows", "sheet": "Data", "rows": [2], "to_sheet": "Moved"}
    if "Data!" in formula:
        workspace = FakeWorkspace()
        text, artifact = await _tool(workspace)(**base)
        assert not artifact.is_error, text
        writes = list(workspace.writes)
        text, artifact = await _tool(workspace)(
            changes=[change], **workspace.references()
        )
        assert artifact.is_error and "relative reference to sheet 'Data'" in text
        assert workspace.writes == writes
        return
    spec = _apply(change, base=base)
    data = build_workbook(prepare(CreateSpreadsheetInput.model_validate(spec)))
    formulas = load_workbook(io.BytesIO(data))
    cached = load_workbook(io.BytesIO(data), data_only=True)
    assert list(cached["Data"].values)[1:] == [(20, 20), (30, 30)]
    assert list(cached["Moved"].values)[1:] == [(10, 10)]
    assert formulas["Data"]["B2"].value == formulas["Moved"]["B2"].value == formula
    assert formulas["Data"]["B3"].value == formula.replace("A2", "A3")


def test_errors_are_listed_at_once_with_the_fix():
    message = _refused(
        {"op": "remove_rows", "sheet": "Budget", "rows": [40]},
        {"op": "edit_rows", "sheet": "Budget", "rows": [2], "values": {"Montant": 1}},
        {"op": "explode", "sheet": "Budget"},
    )
    assert "changes[0] (remove_rows): row 40 does not exist" in message
    assert "data rows 2 to 4" in message
    assert (
        "changes[1] (edit_rows)" in message and "'Poste', 'Budget', 'Réel'" in message
    )
    assert "changes[2] (explode): unknown op" in message


def test_edit_cell_and_edit_rows_by_where():
    spec = _apply(
        {"op": "edit_cell", "sheet": "Budget", "cell": "C3", "value": 360},
        {
            "op": "edit_rows",
            "sheet": "Budget",
            "where": {"column": "Poste", "equals": "loyer"},
            "values": {"Réel": {"formula": "=B2*0.9"}},
        },
    )
    rows = _sheets(spec)["Budget"]["rows"]
    assert rows[1][2] == 360 and rows[0][2] == {"formula": "=B2*0.9"}


def test_conflicting_changes_are_refused():
    assert "already removed or moved" in _refused(
        {"op": "remove_rows", "sheet": "Budget", "rows": [2]},
        {"op": "edit_cell", "sheet": "Budget", "cell": "B2", "value": 1},
    )
    assert "removed by another change" in _refused(
        {"op": "remove_sheet", "sheet": "Synthèse"},
        {"op": "rename_sheet", "sheet": "Synthèse", "name": "X"},
    )


def test_add_and_remove_sheets():
    spec = _apply(
        {"op": "remove_sheet", "sheet": "Synthèse"},
        {
            "op": "add_sheet",
            "sheet": {
                "name": "Notes",
                "columns": [{"header": "Note"}],
                "rows": [["ok"]],
            },
        },
    )
    assert [s["name"] for s in spec["sheets"]] == ["Budget", "Notes"]
    message = _refused({"op": "remove_sheet", "sheet": "Budget"})
    assert "reads sheet 'Budget'" in message


def test_nothing_changed_is_an_error():
    message = _refused(
        {"op": "edit_cell", "sheet": "Budget", "cell": "B2", "value": 1200}
    )
    assert "nothing changed" in message and "Do not tell the user" in message


# --- through the tool -------------------------------------------------------------


def test_the_report_names_each_touched_row_by_its_label():
    report: list[str] = []
    apply_changes(
        BUDGET,
        [
            {"op": "remove_rows", "sheet": "Budget", "rows": [4, 3]},
            {"op": "edit_cell", "sheet": "Budget", "cell": "C2", "value": 1100},
            {
                "op": "add_rows",
                "sheet": "Budget",
                "after": 2,
                "rows": [["Formation", 1, 1]],
            },
            {
                "op": "move_rows",
                "sheet": "Synthèse",
                "rows": [3],
                "to_sheet": "Archive",
            },
        ],
        report,
    )
    (text,) = report
    assert "row numbers of the previous file" in text
    assert "sheet 'Budget': removed row 3 (Voyages), row 4 (Matériel)" in text
    assert "changed row 2 (Loyer)" in text
    assert "added 1 row after row 2 (Loyer)" in text
    assert "sheet 'Synthèse': moved row 3 (Loyer réel) to 'Archive'" in text
    assert "not the row the user meant" in text


def test_column_changes_alone_give_no_row_report():
    report: list[str] = []
    apply_changes(
        BUDGET,
        [{"op": "add_column", "sheet": "Budget", "column": {"header": "Note"}}],
        report,
    )
    assert report == []


COMPUTED: dict[str, Any] = {
    "file_name": "Notes",
    "sheets": [
        {
            "name": "Notes",
            "columns": [
                {"header": "Poste"},
                {"header": "HT", "type": "currency"},
                {"header": "TTC", "type": "currency", "formula": "=B2*1.2"},
            ],
            "rows": [["a", 10, None], ["b", 20, None], ["Total", None, None]],
        }
    ],
}


def test_edit_cell_with_a_formula_overrides_the_column_formula():
    spec = _apply(
        {
            "op": "edit_cell",
            "sheet": "Notes",
            "cell": "C4",
            "value": {"formula": "=SUM(C2:C3)"},
        },
        base=COMPUTED,
    )
    ws = load_workbook(
        io.BytesIO(
            build_workbook(prepare(CreateSpreadsheetInput.model_validate(spec)))
        ),
        data_only=True,
    )["Notes"]
    assert ws["C4"].value == pytest.approx(36)
    # The override survives as the base of the next revision.
    again = _apply(
        {"op": "edit_cell", "sheet": "Notes", "cell": "B2", "value": 5}, base=spec
    )
    assert _cell_formula(again, "Notes", 2, 2) == "=SUM(C2:C3)"


def test_edit_cell_with_a_value_in_a_formula_column_is_refused():
    message = _refused(
        {"op": "edit_cell", "sheet": "Notes", "cell": "C4", "value": 36}, base=COMPUTED
    )
    assert "column 'TTC', which its formula fills" in message
    assert '{"formula": "=..."}' in message


@pytest.mark.parametrize(
    "change",
    [
        {"op": "edit_cell", "sheet": "Notes", "cell": "C4", "value": None},
        {"op": "edit_rows", "sheet": "Notes", "rows": [4], "values": {"TTC": None}},
    ],
)
def test_null_empties_a_formula_column_cell(change: dict[str, Any]):
    spec = _apply(change, base=COMPUTED)
    ws = load_workbook(
        io.BytesIO(
            build_workbook(prepare(CreateSpreadsheetInput.model_validate(spec)))
        ),
        data_only=True,
    )["Notes"]
    assert ws["C4"].value in (None, "")
    assert ws["C3"].value == pytest.approx(24)
    # The blank survives as the base of the next revision.
    again = _apply(
        {"op": "edit_cell", "sheet": "Notes", "cell": "B2", "value": 5}, base=spec
    )
    assert _cell_formula(again, "Notes", 2, 2) == '=""'


def test_a_row_wise_column_formula_stays_relative_after_a_revision():
    base = json.loads(json.dumps(COMPUTED))
    base["sheets"][0]["columns"][2]["formula"] = "=SUM(B2:B2)*1.2"
    spec = _apply(
        {"op": "add_rows", "sheet": "Notes", "rows": [["c", 30, None]]}, base=base
    )
    assert _sheets(spec)["Notes"]["columns"][2]["formula"] == "=SUM(B2:B2)*1.2"


def test_edit_rows_with_row_objects_shows_the_expected_shape():
    message = _refused(
        {"op": "edit_rows", "sheet": "Budget", "rows": [{"values": {"Réel": 1}}]}
    )
    assert "`rows` holds row numbers, not row objects" in message
    assert "rows: [8], values:" in message
