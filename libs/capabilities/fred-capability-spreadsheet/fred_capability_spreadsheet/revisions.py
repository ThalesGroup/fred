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

"""Targeted revisions: apply `changes` to the last delivered workbook's request.

Names and row numbers refer to the base, never shifted by earlier changes of the
same call; the result is a whole request that goes through the normal build.
Existing formulas follow rows, columns and sheets like Excel (design.md D10).
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any, cast

from fred_capability_spreadsheet.formulas import (
    FormulaError,
    Node,
    Ref,
    anchor_ranges,
    column_letters,
    column_number,
    emit,
    map_refs,
    parse,
)

Spec = dict[str, Any]

OPS = (
    "add_column",
    "remove_column",
    "edit_column",
    "add_rows",
    "remove_rows",
    "edit_rows",
    "edit_cell",
    "rename_sheet",
    "add_sheet",
    "remove_sheet",
    "move_rows",
)
_ALIASES = {
    "add_row": "add_rows",
    "insert_rows": "add_rows",
    "insert_row": "add_rows",
    "remove_row": "remove_rows",
    "delete_rows": "remove_rows",
    "delete_row": "remove_rows",
    "edit_row": "edit_rows",
    "update_rows": "edit_rows",
    "update_row": "edit_rows",
    "delete_column": "remove_column",
    "update_column": "edit_column",
    "update_cell": "edit_cell",
    "set_cell": "edit_cell",
    "delete_sheet": "remove_sheet",
    "move_row": "move_rows",
    "split_sheet": "move_rows",
}
_COLUMN_FIELDS = ("header", "type", "currency", "total", "compute", "formula", "width")
_CELL_RE = re.compile(r"^\$?([A-Za-z]{1,3})\$?([0-9]+)$")
NO_BASE = (
    "No file was written: there is no previous workbook in this conversation to "
    "change. Send the whole workbook in sheets."
)


def _is_formula(value: Any) -> bool:
    return isinstance(value, dict) and "formula" in value


class ChangeError(ValueError):
    """One or more changes cannot apply; the message lists each with its fix."""


def normalize_spec(spec: Spec) -> Spec:
    """Full-length rows (computed and formula columns hold null) and no hidden
    fields, so stored bases compare and replay exactly."""

    out = copy.deepcopy(spec)
    out.pop("charts_ignored", None)
    out.pop("changes", None)
    for sheet in out.get("sheets", []):
        columns = sheet.get("columns", [])
        holes = [bool(c.get("compute") or c.get("formula")) for c in columns]
        for column in columns:
            if column.pop("type_inferred", False):
                column.pop("type", None)
            for key in [k for k, v in column.items() if v is None]:
                del column[key]
        rows = []
        for row in sheet.get("rows", []):
            if len(row) != len(columns):
                values = iter(row)
                row = [None if hole else next(values, None) for hole in holes]
            # A formula cell in a computed column overrides it, so it is kept.
            rows.append(
                [
                    None if hole and not _is_formula(v) else v
                    for hole, v in zip(holes, row, strict=True)
                ]
            )
        sheet["rows"] = rows
    return out


@dataclass
class _Sheet:
    """A sheet being rebuilt: base rows keep their base index for addressing."""

    name: str
    base_name: str | None
    columns: list[dict[str, Any]]
    base_columns: list[dict[str, Any]]
    # (base row index or None for a new row, raw values by base column index or
    # a dict header -> value for rows added by this call)
    rows: list[tuple[int | None, list[Any]]]
    has_totals: bool
    removed_rows: set[int] = field(default_factory=set)
    moved_rows: dict[int, str] = field(default_factory=dict)
    edits: dict[int, dict[int, Any]] = field(default_factory=dict)
    removed_columns: set[int] = field(default_factory=set)
    column_edits: dict[int, dict[str, Any]] = field(default_factory=dict)
    added_columns: list[tuple[int | None, dict[str, Any], list[Any] | None]] = field(
        default_factory=list
    )
    added_rows: list[tuple[int | None, list[Any] | dict[str, Any]]] = field(
        default_factory=list
    )
    # Rows moved in by this call: (the sheet they come from, base values).
    incoming: list[tuple[str, list[Any]]] = field(default_factory=list)


class _Errors:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, index: int, op: str, message: str) -> None:
        self.items.append(f"changes[{index}] ({op}): {message}")


def apply_changes(base: Spec, changes: list[Any]) -> Spec:
    """The request that results from `changes` on `base`, or `ChangeError`."""

    base = normalize_spec(base)
    errors = _Errors()
    sheets = [_load(s) for s in base["sheets"]]
    by_name = {s.name.casefold(): s for s in sheets}
    renames: dict[str, str] = {}
    removed_sheets: set[str] = set()
    added_sheets: list[tuple[str | None, Spec]] = []
    created: dict[str, _Sheet] = {}
    touched_sheets: dict[str, str] = {}
    if not changes:
        raise ChangeError("No file was written: `changes` is empty.")
    for index, raw in enumerate(changes):
        if not isinstance(raw, dict):
            errors.add(index, "?", "each change is an object with an `op`")
            continue
        change = cast(dict[str, Any], raw)
        op = str(change.get("op", "")).strip().lower().replace("-", "_")
        op = _ALIASES.get(op, op)
        if op not in OPS:
            errors.add(index, op or "?", f"unknown op; use one of {', '.join(OPS)}")
            continue
        try:
            _resolve(
                op,
                change,
                sheets,
                by_name,
                renames,
                removed_sheets,
                added_sheets,
                created,
                touched_sheets,
            )
        except ChangeError as exc:
            errors.add(index, op, str(exc))
    if errors.items:
        raise ChangeError(_refusal(errors.items))
    result = _build(
        base, sheets, renames, removed_sheets, added_sheets, created, errors
    )
    if errors.items:
        raise ChangeError(_refusal(errors.items))
    if normalize_spec(result) == base:
        raise ChangeError(
            "No file was written: these changes leave the workbook exactly as it "
            "is, so nothing changed. Do not tell the user it was changed; send the "
            "change they asked for."
        )
    return result


def _refusal(items: list[str]) -> str:
    return (
        "No file was written; nothing was applied. Fix these changes and send all "
        "of them again (they apply to the workbook as delivered): " + "; ".join(items)
    )


def _load(spec: Spec) -> _Sheet:
    columns = [dict(c) for c in spec.get("columns", [])]
    return _Sheet(
        name=spec["name"],
        base_name=spec["name"],
        columns=columns,
        base_columns=[dict(c) for c in columns],
        rows=[(i, list(row)) for i, row in enumerate(spec.get("rows", []))],
        has_totals=any(c.get("total") for c in columns) and bool(spec.get("rows")),
    )


# --- resolution (against the base) -----------------------------------------------


def _sheet(name: Any, by_name: dict[str, _Sheet], removed: set[str]) -> _Sheet:
    if not isinstance(name, str) or not name.strip():
        raise ChangeError("give `sheet`, the name of a sheet of the workbook")
    found = by_name.get(name.strip().casefold())
    if found is None:
        names = ", ".join(f"'{s.name}'" for s in by_name.values())
        raise ChangeError(f"sheet '{name}' does not exist; the sheets are {names}")
    if found.base_name in removed:
        raise ChangeError(f"sheet '{found.name}' is removed by another change")
    return found


def _column(sheet: _Sheet, header: Any) -> int:
    if not isinstance(header, str) or not header.strip():
        raise ChangeError("give `column`, a column header")
    headers = [str(c.get("header", "")) for c in sheet.base_columns]
    matches = [i for i, h in enumerate(headers) if h.strip() == header.strip()] or [
        i
        for i, h in enumerate(headers)
        if h.strip().casefold() == header.strip().casefold()
    ]
    if not matches:
        known = ", ".join(f"'{h}'" for h in headers)
        raise ChangeError(
            f"sheet '{sheet.name}' has no column '{header}'; its columns are {known}"
        )
    return matches[0]


def _row_range(sheet: _Sheet) -> str:
    count = len(sheet.rows)
    return f"data rows 2 to {count + 1}" if count else "no data rows"


def _rows(sheet: _Sheet, change: dict[str, Any]) -> list[int]:
    """Base row indexes selected by `rows` (file row numbers) or `where`."""

    numbers = change.get("rows", change.get("row"))
    where = change.get("where")
    if (numbers is None) == (where is None):
        raise ChangeError(
            "select rows with `rows` (row numbers as in the file, the first data "
            "row is 2) or `where` ({column, equals}), one of the two"
        )
    if where is not None:
        if not isinstance(where, dict):
            raise ChangeError("`where` is {column: <header>, equals: <value>}")
        column = _column(sheet, cast(dict[str, Any], where).get("column"))
        wanted = cast(dict[str, Any], where).get("equals")
        found = [
            i for i, row in sheet.rows if i is not None and _equal(row[column], wanted)
        ]
        if not found:
            raise ChangeError(
                f"no row of sheet '{sheet.name}' has {wanted!r} in column "
                f"'{sheet.base_columns[column].get('header')}'"
            )
        return found
    items = numbers if isinstance(numbers, list) else [numbers]
    out: list[int] = []
    for item in items:
        if (
            isinstance(item, bool)
            or not isinstance(item, int | float)
            or int(item) != item
        ):
            raise ChangeError(f"row {item!r} is not a row number")
        index = int(item) - 2
        if not 0 <= index < len(sheet.rows):
            raise ChangeError(
                f"row {int(item)} does not exist; sheet '{sheet.name}' has "
                f"{_row_range(sheet)}"
            )
        out.append(index)
    return out


def _equal(value: Any, wanted: Any) -> bool:
    if isinstance(value, dict) or isinstance(wanted, dict):
        return False
    if isinstance(value, str) and isinstance(wanted, str):
        return value.strip().casefold() == wanted.strip().casefold()
    if isinstance(value, int | float) and isinstance(wanted, int | float):
        return float(value) == float(wanted)
    return str(value).strip().casefold() == str(wanted).strip().casefold()


def _claim(sheet: _Sheet, rows: list[int], what: str) -> None:
    for row in rows:
        if row in sheet.removed_rows or row in sheet.moved_rows:
            raise ChangeError(
                f"row {row + 2} of sheet '{sheet.name}' is already removed or moved "
                f"by another change; it cannot also be {what}"
            )


def _resolve(
    op: str,
    change: dict[str, Any],
    sheets: list[_Sheet],
    by_name: dict[str, _Sheet],
    renames: dict[str, str],
    removed_sheets: set[str],
    added_sheets: list[tuple[str | None, Spec]],
    created: dict[str, _Sheet],
    touched: dict[str, str],
) -> None:
    if op == "add_sheet":
        spec = change.get("sheet")
        if not isinstance(spec, dict):
            spec = {k: change[k] for k in ("name", "columns", "rows") if k in change}
        if not spec.get("name") or not spec.get("columns"):
            raise ChangeError("give the new sheet as `sheet`: {name, columns, rows}")
        name = str(spec["name"])
        if name.strip().casefold() in by_name:
            raise ChangeError(f"sheet '{name}' already exists; choose another name")
        after = change.get("after")
        added_sheets.append((str(after) if after else None, dict(spec)))
        return
    sheet = _sheet(change.get("sheet"), by_name, removed_sheets)
    key = cast(str, sheet.base_name)
    if op in ("remove_sheet", "rename_sheet"):
        previous = touched.get(key)
        if previous:
            raise ChangeError(
                f"sheet '{sheet.name}' is already {previous} by another change"
            )
        if op == "remove_sheet":
            removed_sheets.add(key)
            touched[key] = "removed"
            return
        name = change.get("name", change.get("to"))
        if not isinstance(name, str) or not name.strip():
            raise ChangeError("give `name`, the new sheet name")
        if (
            name.strip().casefold() in by_name
            and by_name[name.strip().casefold()] is not sheet
        ):
            raise ChangeError(f"sheet '{name}' already exists; choose another name")
        renames[key] = name.strip()
        touched[key] = "renamed"
        return
    if op == "add_column":
        column = change.get("column")
        if not isinstance(column, dict) or not column.get("header"):
            raise ChangeError(
                "give `column`, the new column as in sheets ({header, type, ...})"
            )
        headers = {
            str(c.get("header", "")).strip().casefold() for c in sheet.base_columns
        }
        if str(column["header"]).strip().casefold() in headers:
            raise ChangeError(
                f"column '{column['header']}' already exists; use edit_column to change it"
            )
        after = change.get("after")
        position = None if after is None else _column(sheet, after)
        values = change.get("values")
        if values is not None:
            if not isinstance(values, list) or len(values) != len(sheet.rows):
                raise ChangeError(
                    f"`values` holds one value per data row of sheet '{sheet.name}' "
                    f"({len(sheet.rows)} values, rows 2 to {len(sheet.rows) + 1}), or "
                    "leave it out"
                )
        sheet.added_columns.append((position, dict(column), values))
        return
    if op in ("remove_column", "edit_column"):
        index = _column(sheet, change.get("column"))
        if index in sheet.removed_columns or (
            op == "remove_column" and index in sheet.column_edits
        ):
            raise ChangeError(
                f"column '{sheet.base_columns[index].get('header')}' is already "
                "removed or edited by another change"
            )
        if op == "remove_column":
            sheet.removed_columns.add(index)
            return
        if index in sheet.column_edits:
            raise ChangeError(
                f"column '{sheet.base_columns[index].get('header')}' is edited twice; "
                "merge the two edits"
            )
        edits = {k: change[k] for k in _COLUMN_FIELDS if k in change}
        if not edits:
            raise ChangeError(f"give the fields to change: {', '.join(_COLUMN_FIELDS)}")
        sheet.column_edits[index] = edits
        return
    if op == "add_rows":
        rows = change.get("rows", change.get("values"))
        if isinstance(rows, list) and rows and not isinstance(rows[0], list | dict):
            rows = [rows]
        if not isinstance(rows, list) or not rows:
            raise ChangeError(
                "give `rows`, a list of rows (each a list with one value per column, "
                "or an object {header: value})"
            )
        after = change.get("after")
        position: int | None = None
        if after is not None:
            if isinstance(after, bool) or not isinstance(after, int | float):
                raise ChangeError("`after` is a row number (1 puts the rows first)")
            position = int(after) - 2
            if not -1 <= position < len(sheet.rows):
                raise ChangeError(
                    f"after row {int(after)}: sheet '{sheet.name}' has {_row_range(sheet)}"
                )
        for row in rows:
            if not isinstance(row, list | dict):
                raise ChangeError(
                    "each added row is a list or an object {header: value}"
                )
            sheet.added_rows.append((position, row))
        return
    if op == "edit_cell":
        cell = change.get("cell")
        match = _CELL_RE.match(str(cell or "").strip())
        if not match:
            raise ChangeError("give `cell`, an address such as C5")
        column = column_number(match.group(1)) - 1
        row = int(match.group(2)) - 2
        if column >= len(sheet.base_columns):
            raise ChangeError(
                f"{cell} is outside sheet '{sheet.name}' (columns A to "
                f"{column_letters(len(sheet.base_columns))})"
            )
        if not 0 <= row < len(sheet.rows):
            raise ChangeError(
                f"{cell} is not a data cell; sheet '{sheet.name}' has {_row_range(sheet)}"
            )
        if "value" not in change:
            raise ChangeError("give `value`, the new value (null to empty the cell)")
        base = sheet.base_columns[column]
        value = change["value"]
        if (base.get("compute") or base.get("formula")) and not (
            value is None or _is_formula(value)
        ):
            raise ChangeError(
                f"{cell} is in column '{base.get('header')}', which its formula "
                'fills; give {"formula": "=..."} to override this one cell'
            )
        _claim(sheet, [row], "edited")
        sheet.edits.setdefault(row, {})[column] = change["value"]
        return
    if op == "edit_rows":
        rows = _rows(sheet, change)
        values = change.get("values")
        if not isinstance(values, dict) or not values:
            raise ChangeError("give `values`, an object {header: new value}")
        columns = {_column(sheet, h): v for h, v in values.items()}
        _claim(sheet, rows, "edited")
        for row in rows:
            sheet.edits.setdefault(row, {}).update(columns)
        return
    if op == "remove_rows":
        rows = _rows(sheet, change)
        _claim(sheet, rows, "removed")
        for row in rows:
            if row in sheet.edits:
                raise ChangeError(f"row {row + 2} is edited by another change")
        sheet.removed_rows.update(rows)
        return
    # move_rows
    rows = _rows(sheet, change)
    _claim(sheet, rows, "moved")
    for row in rows:
        if row in sheet.edits:
            raise ChangeError(
                f"row {row + 2} is edited by another change; move it first, then "
                "edit it in a later request"
            )
    target_name = change.get("to_sheet", change.get("to"))
    if not isinstance(target_name, str) or not target_name.strip():
        raise ChangeError("give `to_sheet`, an existing sheet or the name of a new one")
    target = by_name.get(target_name.strip().casefold())
    if target is sheet:
        raise ChangeError("`to_sheet` is the sheet the rows are already on")
    if target is None:
        target = created.get(target_name.strip().casefold())
        if target is None:
            target = _Sheet(
                name=target_name.strip(),
                base_name=None,
                columns=[dict(c) for c in sheet.base_columns],
                base_columns=[dict(c) for c in sheet.base_columns],
                rows=[],
                has_totals=False,
            )
            target.has_totals = any(c.get("total") for c in target.columns)
            created[target_name.strip().casefold()] = target
            touched.setdefault(f"new:{target.name}", cast(str, sheet.base_name))
    else:
        source = [
            str(c.get("header", "")).strip().casefold() for c in sheet.base_columns
        ]
        dest = [
            str(c.get("header", "")).strip().casefold() for c in target.base_columns
        ]
        if sorted(source) != sorted(dest):
            raise ChangeError(
                f"sheet '{target.name}' does not have the same columns as "
                f"'{sheet.name}'; move to a new sheet name, or edit the columns first"
            )
    for row in rows:
        sheet.moved_rows[row] = target.name
        values = sheet.rows[row][1]
        if target.base_columns is not sheet.base_columns:
            order = [
                [
                    str(c.get("header", "")).strip().casefold()
                    for c in sheet.base_columns
                ].index(str(c.get("header", "")).strip().casefold())
                for c in target.base_columns
            ]
            values = [values[i] for i in order]
        target.incoming.append((cast(str, sheet.base_name), values))


# --- building the result -----------------------------------------------------------


@dataclass
class _Layout:
    """Where each base cell of a sheet ends up (file rows and columns, 1-based)."""

    name: str
    rows: dict[int, int | None]
    last_data_row: int
    new_last_data_row: int
    totals: tuple[int, int | None] | None
    columns: dict[int, int | None]
    moved_to: dict[int, str]


@dataclass
class _Built:
    spec: Spec
    # Result rows (0-based) holding base formulas, with the sheet they come from
    # (another sheet for moved rows); other rows came with this call.
    base_rows: dict[int, str]
    # Result cells and columns whose formula this call sent: written for the
    # result, never remapped.
    fresh_cells: set[tuple[int, int]]
    fresh_columns: set[int]


def _build(
    base: Spec,
    sheets: list[_Sheet],
    renames: dict[str, str],
    removed_sheets: set[str],
    added_sheets: list[tuple[str | None, Spec]],
    created: dict[str, _Sheet],
    errors: _Errors,
) -> Spec:
    layouts: dict[str, _Layout] = {}
    built: dict[str, _Built] = {}
    for sheet in sheets:
        if sheet.base_name in removed_sheets:
            continue
        built[cast(str, sheet.base_name)], layouts[cast(str, sheet.base_name)] = (
            _rebuild(sheet, errors)
        )
    origins = {target.name: _origin(sheets, target) for target in created.values()}
    for target in created.values():
        built[f"new:{target.name}"] = _Built(
            spec={
                "name": target.name,
                "columns": [dict(c) for c in target.columns],
                "rows": [list(values) for _, values in target.incoming],
            },
            base_rows={i: origins[target.name] for i in range(len(target.incoming))},
            fresh_cells=set(),
            fresh_columns=set(range(len(target.columns))),
        )
    _adjust_formulas(base, built, layouts, renames, removed_sheets, errors)
    order: list[Spec] = []
    for sheet in sheets:
        key = cast(str, sheet.base_name)
        if key in removed_sheets:
            continue
        spec = built[key].spec
        if key in renames:
            spec["name"] = renames[key]
        order.append(spec)
        for target in created.values():
            if origins[target.name] == key:
                order.append(built[f"new:{target.name}"].spec)
    for after, spec in added_sheets:
        names = [s["name"].casefold() for s in order]
        position = len(order)
        if after is not None:
            wanted = renames.get(after, after).casefold()
            if wanted in names:
                position = names.index(wanted) + 1
        order.insert(position, spec)
    result = {k: v for k, v in base.items() if k != "sheets"}
    result["sheets"] = order
    return result


def _origin(sheets: list[_Sheet], target: _Sheet) -> str:
    for sheet in sheets:
        if target.name in sheet.moved_rows.values():
            return cast(str, sheet.base_name)
    return target.name


def _rebuild(sheet: _Sheet, errors: _Errors) -> tuple[_Built, _Layout]:
    base_count = len(sheet.base_columns)
    # Columns: base columns kept in order, new ones after their anchor (or last).
    plan: list[int | tuple[str, int]] = []
    for index in range(base_count):
        if index not in sheet.removed_columns:
            plan.append(index)
        plan.extend(
            ("new", k)
            for k, (pos, _, _) in enumerate(sheet.added_columns)
            if pos == index
        )
    plan.extend(
        ("new", k) for k, (pos, _, _) in enumerate(sheet.added_columns) if pos is None
    )
    columns: list[dict[str, Any]] = []
    column_map: dict[int, int | None] = {i: None for i in range(base_count)}
    renamed_headers: dict[str, str] = {}
    fresh_columns: set[int] = set()
    for position, item in enumerate(plan):
        if isinstance(item, int):
            column = dict(sheet.base_columns[item])
            edits = sheet.column_edits.get(item, {})
            for key, value in edits.items():
                if key == "header" and value:
                    old = str(column.get("header", "")).strip().casefold()
                    renamed_headers[old] = str(value)
                if value is None:
                    column.pop(key, None)
                else:
                    column[key] = value
            if edits.get("compute"):
                column.pop("formula", None)
            if edits.get("formula"):
                column.pop("compute", None)
                fresh_columns.add(position)
            column_map[item] = position + 1
        else:
            column = dict(sheet.added_columns[item[1]][1])
            fresh_columns.add(position)
        columns.append(column)
    _follow_headers(sheet, columns, renamed_headers, errors)

    def materialize(values: list[Any] | dict[str, Any]) -> list[Any]:
        """A row sent by this call, in the result's column order."""

        if isinstance(values, dict):
            by_header = {str(k).strip().casefold(): v for k, v in values.items()}
            known = {str(c.get("header", "")).strip().casefold() for c in columns}
            for header in by_header:
                if header not in known:
                    errors.items.append(
                        f"sheet '{sheet.name}': an added row names column '{header}', "
                        "which the sheet does not have"
                    )
            return [
                by_header.get(str(c.get("header", "")).strip().casefold())
                for c in columns
            ]
        holes = [bool(c.get("compute") or c.get("formula")) for c in sheet.base_columns]
        if sum(holes) and len(values) == base_count - sum(holes):
            it = iter(values)
            values = [None if hole else next(it) for hole in holes]
        if len(values) != base_count:
            errors.items.append(
                f"sheet '{sheet.name}': an added row has {len(values)} values; give "
                f"one per column ({base_count}), or an object {{header: value}}"
            )
            values = (list(values) + [None] * base_count)[:base_count]
        return [values[item] if isinstance(item, int) else None for item in plan]

    rows: list[list[Any]] = []
    base_rows: dict[int, str] = {}
    fresh_cells: set[tuple[int, int]] = set()
    row_map: dict[int, int | None] = {}

    def add_fresh(values: list[Any] | dict[str, Any]) -> None:
        rows.append(materialize(values))
        fresh_cells.update((len(rows) - 1, c) for c in range(len(columns)))

    for pos, added in sheet.added_rows:
        if pos == -1:
            add_fresh(added)
    key = cast(str, sheet.base_name)
    for base_index, values in sheet.rows:
        assert base_index is not None
        if base_index in sheet.removed_rows or base_index in sheet.moved_rows:
            row_map[base_index + 2] = None
        else:
            out = [values[item] if isinstance(item, int) else None for item in plan]
            r = len(rows)
            for column, value in sheet.edits.get(base_index, {}).items():
                if column_map[column] is not None:
                    out[cast(int, column_map[column]) - 1] = value
                    fresh_cells.add((r, cast(int, column_map[column]) - 1))
            for k, (_, _, column_values) in enumerate(sheet.added_columns):
                if column_values is not None:
                    out[plan.index(("new", k))] = column_values[base_index]
            rows.append(out)
            base_rows[r] = key
            row_map[base_index + 2] = r + 2
        for pos, added in sheet.added_rows:
            if pos == base_index:
                add_fresh(added)
    for pos, added in sheet.added_rows:
        if pos is None:
            add_fresh(added)
    for source, values in sheet.incoming:
        rows.append(materialize(values))
        base_rows[len(rows) - 1] = source
    has_totals = any(c.get("total") for c in columns) and bool(rows)
    base_last = len(sheet.rows) + 1
    totals = None
    if sheet.has_totals:
        totals = (base_last + 1, len(rows) + 2 if has_totals else None)
    layout = _Layout(
        name=sheet.name,
        rows={1: 1, **row_map},
        last_data_row=base_last,
        new_last_data_row=len(rows) + 1,
        totals=totals,
        columns={k + 1: v for k, v in column_map.items()},
        moved_to={k + 2: v for k, v in sheet.moved_rows.items()},
    )
    built = _Built(
        spec={"name": sheet.name, "columns": columns, "rows": rows},
        base_rows=base_rows,
        fresh_cells=fresh_cells,
        fresh_columns=fresh_columns,
    )
    return built, layout


def _follow_headers(
    sheet: _Sheet,
    columns: list[dict[str, Any]],
    renamed: dict[str, str],
    errors: _Errors,
) -> None:
    """Compute operands follow renamed headers and may not name a removed column."""

    removed = {
        str(sheet.base_columns[i].get("header", "")).strip().casefold(): str(
            sheet.base_columns[i].get("header", "")
        )
        for i in sheet.removed_columns
    }
    for column in columns:
        compute = column.get("compute")
        if not isinstance(compute, dict):
            continue
        compute = dict(cast(dict[str, Any], compute))
        for key in ("left", "right", "column"):
            operand = compute.get(key)
            if not isinstance(operand, str):
                continue
            folded = operand.strip().casefold()
            if folded in removed:
                errors.items.append(
                    f"column '{removed[folded]}' of sheet '{sheet.name}' is used by "
                    f"the computed column '{column.get('header')}'; remove or edit "
                    "that column in the same changes"
                )
            elif folded in renamed:
                compute[key] = renamed[folded]
        column["compute"] = compute


# --- formulas follow the changes -----------------------------------------------------


def _adjust_formulas(
    base: Spec,
    built: dict[str, _Built],
    layouts: dict[str, _Layout],
    renames: dict[str, str],
    removed_sheets: set[str],
    errors: _Errors,
) -> None:
    names = [s["name"] for s in base["sheets"]]
    by_fold = {n.casefold(): n for n in names}
    final_names = {n: renames.get(n, n) for n in names}

    def remapper(here: str, template: bool) -> Callable[[Ref], Node]:
        def remap(ref: Ref) -> Node:
            sheet = by_fold.get((ref.sheet or here).casefold(), ref.sheet or here)
            if sheet in removed_sheets:
                raise _Broken(f"it reads sheet '{sheet}', which these changes remove")
            qualified = None if ref.sheet is None else final_names.get(sheet, sheet)
            layout = layouts.get(sheet)
            if layout is None:
                return replace(ref, sheet=qualified)
            c1, c2 = _map_columns(layout, ref)
            r1, r2 = ref.r1, ref.r2
            # A filled-down formula's relative rows follow its own row.
            if not (template and not ref.abs_r1):
                r1 = _map_row(layout, ref.r1, low=True, single=not ref.is_range)
            if not (template and not ref.abs_r2):
                r2 = _map_row(layout, ref.r2, low=False, single=not ref.is_range)
            return replace(ref, sheet=qualified, c1=c1, c2=c2, r1=r1, r2=r2)

        return remap

    for key, item in built.items():
        spec = item.spec
        here = key if not key.startswith("new:") else ""
        for position, column in enumerate(spec["columns"]):
            text = column.get("formula")
            if position in item.fresh_columns or not isinstance(text, str):
                continue
            where = f"the formula of column '{column.get('header')}' of sheet '{spec['name']}'"
            column["formula"] = _rewrite(
                text, names, remapper(here, True), where, errors, template=True
            )
        for r, row in enumerate(spec["rows"]):
            origin = item.base_rows.get(r)
            if origin is None:
                continue
            for c, value in enumerate(row):
                if (r, c) in item.fresh_cells or not isinstance(value, dict):
                    continue
                text = cast(dict[str, Any], value).get("formula")
                if not isinstance(text, str):
                    continue
                where = (
                    f"the formula in sheet '{spec['name']}', cell "
                    f"{column_letters(c + 1)}{r + 2}"
                )
                moved = origin != here
                row[c] = {
                    "formula": _rewrite(
                        text,
                        names,
                        remapper(origin, False),
                        where,
                        errors,
                        qualify=origin if moved else None,
                    )
                }


class _Broken(Exception):
    pass


def _rewrite(
    text: str,
    names: list[str],
    remap: Callable[[Ref], Node],
    where: str,
    errors: _Errors,
    *,
    template: bool = False,
    qualify: str | None = None,
) -> str:
    try:
        node = parse(text, names)
    except FormulaError:
        return text  # the build reports it with its location
    if template:
        node = anchor_ranges(node)
    if qualify is not None:
        node = map_refs(
            node, lambda ref: ref if ref.sheet else replace(ref, sheet=qualify)
        )
    try:
        return emit(map_refs(node, remap))
    except _Broken as exc:
        errors.items.append(
            f"{where} ({text.strip()}) would break: {exc}; edit or remove that "
            "formula in the same changes"
        )
        return text


def _map_columns(layout: _Layout, ref: Ref) -> tuple[int, int]:
    if not ref.is_range:
        new = layout.columns.get(ref.c1, ref.c1)
        if new is None:
            raise _Broken(
                f"it reads column {column_letters(ref.c1)} of sheet '{layout.name}', "
                "which these changes remove"
            )
        return new, new
    kept = [layout.columns.get(c, c) for c in range(ref.c1, ref.c2 + 1)]
    kept_cols = [c for c in kept if c is not None]
    if not kept_cols:
        raise _Broken(
            f"it reads columns {column_letters(ref.c1)} to {column_letters(ref.c2)} of "
            f"sheet '{layout.name}', which these changes remove"
        )
    return min(kept_cols), max(kept_cols)


def _map_row(layout: _Layout, row: int, *, low: bool, single: bool) -> int:
    if row in layout.moved_to:
        raise _Broken(
            f"it reads row {row} of sheet '{layout.name}', which these changes move "
            f"to '{layout.moved_to[row]}'"
        )
    if layout.totals and row == layout.totals[0]:
        if layout.totals[1] is None:
            raise _Broken(
                f"it reads the totals row of sheet '{layout.name}', which goes"
            )
        return layout.totals[1]
    if row == 1 or row > layout.last_data_row:
        return (
            row if row == 1 else row - layout.last_data_row + layout.new_last_data_row
        )
    mapped = layout.rows.get(row)
    if mapped is not None:
        # A range that ended on the last data row follows rows appended after it.
        if not low and row == layout.last_data_row and not single:
            return layout.new_last_data_row
        return mapped
    if single:
        raise _Broken(
            f"it reads row {row} of sheet '{layout.name}', which these changes remove"
        )
    # A removed end row: the range shrinks to the nearest surviving row, as Excel.
    step = 1 if low else -1
    probe = row
    while 2 <= probe <= layout.last_data_row:
        if layout.rows.get(probe) is not None:
            return cast(int, layout.rows[probe])
        if probe in layout.moved_to:
            raise _Broken(
                f"it reads row {probe} of sheet '{layout.name}', which these changes "
                f"move to '{layout.moved_to[probe]}'"
            )
        probe += step
    raise _Broken(f"every row it reads on sheet '{layout.name}' is removed")


# --- what the model sees after a delivery --------------------------------------------

SUMMARY_LIMIT = 600


def describe(sheets: list[tuple[str, list[str], int, bool]]) -> str:
    """One bounded line: each sheet's headers and row range, for later `changes`."""

    parts = []
    for name, headers, data_rows, has_totals in sheets:
        rows = f"data rows 2-{data_rows + 1}" if data_rows else "no data rows"
        if has_totals and data_rows:
            rows += f", totals row {data_rows + 2}"
        parts.append(f"'{name}' columns {', '.join(headers)}; {rows}")
    text = "Sheets: " + " · ".join(parts)
    return text if len(text) <= SUMMARY_LIMIT else text[: SUMMARY_LIMIT - 1] + "…"
