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

"""Evaluator: each allowed function against hand-checked Excel results."""

from __future__ import annotations

from datetime import date

import pytest
from fred_capability_spreadsheet.evaluator import (
    MAX_CELL_READS,
    Evaluator,
    FormulaCell,
    LocatedFormulaError,
    SheetGrid,
    XLError,
    from_serial,
    to_serial,
)
from fred_capability_spreadsheet.formulas import FUNCTIONS, parse

# Sheet "D": A = category, B = amount, C = date; rows 2..6.
DATA = [
    ("Cat", "Amt", "Due"),
    ("a", 10.0, to_serial(date(2026, 1, 31))),
    ("b", 5.0, to_serial(date(2026, 2, 15))),
    ("a", 2.0, None),
    ("Abc", -3.0, None),
    (None, "x", None),
]


def _grid() -> SheetGrid:
    grid = SheetGrid("D", 3)
    for r, row in enumerate(DATA, start=1):
        for c, value in enumerate(row, start=1):
            if value is not None:
                grid.values[(r, c)] = value
    return grid


def _eval(text: str) -> object:
    data = _grid()
    out = SheetGrid("S", 5)
    out.formulas[(2, 1)] = FormulaCell(parse(text, ["D", "S"]), may_spill=True)
    evaluator = Evaluator([data, out], max_rows=5002)
    evaluator.run()
    return evaluator.results[("S", 2, 1)]


def _spill(text: str) -> list[list[object]]:
    data = _grid()
    out = SheetGrid("S", 5)
    out.formulas[(2, 1)] = FormulaCell(parse(text, ["D", "S"]), may_spill=True)
    evaluator = Evaluator([data, out], max_rows=5002)
    evaluator.run()
    spill = evaluator.spills[("S", 2, 1)]
    spilled = evaluator.spilled()
    return [
        [
            evaluator.results[("S", 2, 1)]
            if (r, c) == (0, 0)
            else spilled.get(("S", 2 + r, 1 + c))
            for c in range(spill.width)
        ]
        for r in range(spill.height)
    ]


CASES = [
    ("=SUM(D!B2:B6)", 14.0),
    ('=SUM(1,"2",TRUE)', 4.0),
    ("=SUMPRODUCT(D!B2:B3,D!B2:B3)", 125.0),
    ("=PRODUCT(D!B2:B3)", 50.0),
    ("=ROUND(2.675,2)", 2.68),
    ("=ROUND(-0.125,2)", -0.13),
    ("=ROUND(1234.5,-2)", 1200.0),
    ("=ROUNDUP(1.21,1)", 1.3),
    ("=ROUNDDOWN(-1.29,1)", -1.2),
    ("=INT(-1.5)", -2.0),
    ("=ABS(-3)", 3.0),
    ("=MOD(-7,3)", 2.0),
    ("=POWER(2,10)", 1024.0),
    ("=SQRT(16)", 4.0),
    ("=SQRT(-1)", XLError("#NUM!")),
    ("=AVERAGE(D!B2:B6)", 3.5),
    ("=MEDIAN(D!B2:B5)", 3.5),
    ("=MIN(D!B2:B6)", -3.0),
    ("=MAX(D!B2:B6)", 10.0),
    ("=COUNT(D!B2:B6)", 4.0),
    ("=COUNTA(D!A2:A6)", 4.0),
    ("=COUNTBLANK(D!A2:A6)", 1.0),
    ('=COUNTIF(D!A2:A6,"a")', 2.0),
    ('=COUNTIF(D!A2:A6,"A*")', 3.0),
    ('=COUNTIF(D!B2:B6,">2")', 2.0),
    ('=COUNTIF(D!A2:A6,"<>a")', 3.0),
    ('=COUNTIFS(D!A2:A6,"a",D!B2:B6,">5")', 1.0),
    ('=SUMIF(D!A2:A6,"a",D!B2:B6)', 12.0),
    ('=SUMIF(D!B2:B6,">0")', 17.0),
    ('=SUMIFS(D!B2:B6,D!A2:A6,"a",D!B2:B6,"<5")', 2.0),
    ('=AVERAGEIF(D!A2:A6,"a",D!B2:B6)', 6.0),
    ('=AVERAGEIFS(D!B2:B6,D!A2:A6,"zzz")', XLError("#DIV/0!")),
    ('=MINIFS(D!B2:B6,D!A2:A6,"a")', 2.0),
    ('=MAXIFS(D!B2:B6,D!A2:A6,"a")', 10.0),
    ('=IF(D!B2>5,"big","small")', "big"),
    ("=IF(FALSE,1)", False),
    ('=IFS(D!B3>5,"a",D!B3>1,"b")', "b"),
    ("=IFERROR(1/0,-1)", -1.0),
    ('=IFNA(XLOOKUP("zz",D!A2:A6,D!B2:B6),0)', 0.0),
    ("=AND(TRUE,D!B2>1)", True),
    ("=OR(FALSE,D!B2<1)", False),
    ("=NOT(0)", True),
    ('=SWITCH(D!A3,"a",1,"b",2,0)', 2.0),
    ("=TRUE()", True),
    ("=FALSE()", False),
    ('=CONCAT(D!A2:A3,"-")', "ab-"),
    ('=CONCATENATE("a",1.5,TRUE)', "a1.5TRUE"),
    ('=TEXTJOIN(", ",TRUE,D!A2:A6)', "a, b, a, Abc"),
    ('=LEFT("Bonjour",3)&RIGHT("Bonjour")&MID("Bonjour",2,2)', "Bonron"),
    ('=LEN("été")', 3.0),
    ('=UPPER("été")&LOWER("AB")&PROPER("jean-paul dupont")', "ÉTÉabJean-Paul Dupont"),
    ('=TRIM("  a   b ")', "a b"),
    ('=SUBSTITUTE("a-b-c","-","+",2)', "a-b+c"),
    ('=VALUE("12.5")+VALUE("50%")', 13.0),
    ('=VALUE("abc")', XLError("#VALUE!")),
    ("=DATE(2026,14,1)", to_serial(date(2027, 2, 1))),
    ("=YEAR(D!C2)*100+MONTH(D!C2)", 202601.0),
    ("=DAY(D!C3)", 15.0),
    ("=WEEKDAY(D!C2)", 7.0),  # 2026-01-31 is a Saturday
    ("=WEEKDAY(D!C2,2)", 6.0),
    ("=EDATE(D!C2,1)", to_serial(date(2026, 2, 28))),
    ("=EOMONTH(D!C2,1)", to_serial(date(2026, 2, 28))),
    ('=DATEDIF(D!C2,D!C3,"D")', 15.0),
    ('=DATEDIF(DATE(2020,5,10),DATE(2026,2,1),"Y")', 5.0),
    ('=DATEDIF(DATE(2020,5,10),DATE(2026,2,1),"YM")', 8.0),
    ('=VLOOKUP("b",D!A2:B6,2,FALSE)', 5.0),
    ('=VLOOKUP("B*",D!A2:B6,2,FALSE)', 5.0),
    ('=VLOOKUP("zz",D!A2:B6,2,FALSE)', XLError("#N/A")),
    ("=INDEX(D!B2:B6,2)", 5.0),
    ("=INDEX(D!A2:B6,3,2)", 2.0),
    ('=MATCH("a",D!A2:A6,0)', 1.0),
    ('=XLOOKUP("a",D!A2:A6,D!B2:B6,,0,-1)', 2.0),
    ('=XLOOKUP("q",D!A2:A6,D!B2:B6,"none")', "none"),
    ("=XLOOKUP(6,D!B2:B5,D!A2:A5,,1)", "a"),
    ("=XLOOKUP(6,D!B2:B5,D!A2:A5,,-1)", "b"),
    ('=XMATCH("abc",D!A2:A6)', 4.0),
    ("=1/0", XLError("#DIV/0!")),
    ('="a"+1', XLError("#VALUE!")),
    ("=D!A6", 0.0),
    ('=D!A6=""', True),
    ("=-2^2", 4.0),
    ("=2^3^2", 64.0),
    ("=50%*2", 1.0),
    ('="Abc"="aBC"', True),
    ('=1<"a"', True),
    ('=0.1+0.2&""', "0.3"),
    ('=1E+20&""', "1E+20"),
]


@pytest.mark.parametrize(("text", "expected"), CASES)
def test_functions_follow_excel(text, expected):
    result = _eval(text)
    if isinstance(expected, float):
        assert result == pytest.approx(expected)
    else:
        assert result == expected


def test_every_allowed_function_is_exercised():
    used = {name for text, _ in CASES for name in FUNCTIONS if f"{name}(" in text}
    assert used | {"FILTER", "SORT", "UNIQUE"} == set(FUNCTIONS)


def test_dynamic_arrays_spill():
    assert _spill('=FILTER(D!A2:B5,D!B2:B5>2,"none")') == [["a", 10.0], ["b", 5.0]]
    # Text compares greater than numbers; an empty source cell spills as 0.
    assert _spill("=FILTER(D!A5:B6,D!B5:B6>2)") == [[0.0, "x"]]
    assert _spill("=SORT(D!B2:B5,1,-1)") == [[10.0], [5.0], [2.0], [-3.0]]
    assert _spill("=UNIQUE(D!A2:A5)") == [["a"], ["b"], ["Abc"]]
    assert _eval('=FILTER(D!A2:A5,D!B2:B5>100,"none")') == "none"


def test_spill_into_a_filled_cell_is_refused():
    data = _grid()
    out = SheetGrid("S", 3)
    out.values[(3, 1)] = "taken"
    out.formulas[(2, 1)] = FormulaCell(parse("=SORT(D!B2:B5)", ["D"]), may_spill=True)
    with pytest.raises(LocatedFormulaError, match="A3 is not empty"):
        Evaluator([data, out], max_rows=5002).run()


def test_approximate_lookup_on_unsorted_data_is_refused():
    with pytest.raises(LocatedFormulaError, match="sorted ascending"):
        _eval('=VLOOKUP("b",D!A2:B6,2)')


def test_circular_reference_is_refused():
    grid = SheetGrid("S", 2)
    grid.formulas[(2, 1)] = FormulaCell(parse("=B2+1"))
    grid.formulas[(2, 2)] = FormulaCell(parse("=A2+1"))
    with pytest.raises(LocatedFormulaError, match="circular reference"):
        Evaluator([grid], max_rows=10).run()


def test_running_total_down_a_column_is_linear():
    grid = SheetGrid("S", 2)
    rows = 5000
    for r in range(2, rows + 2):
        grid.values[(r, 1)] = 1.0
    template = parse("=SUM($A$2:A2)")
    for offset in range(rows):
        grid.formulas[(offset + 2, 2)] = FormulaCell(template, rows=offset)
    with pytest.raises(LocatedFormulaError, match="too many cells"):
        Evaluator([grid], max_rows=rows + 1).run()
    chained = SheetGrid("S", 2)
    for r in range(2, rows + 2):
        chained.values[(r, 1)] = 1.0
    step = parse("=B1+A2")
    chained.values[(1, 2)] = 0.0
    for offset in range(rows):
        chained.formulas[(offset + 2, 2)] = FormulaCell(step, rows=offset)
    evaluator = Evaluator([chained], max_rows=rows + 1)
    evaluator.run()
    assert evaluator.results[("S", rows + 1, 2)] == rows


def test_reverse_chain_is_refused_with_a_remedy():
    grid = SheetGrid("S", 1)
    step = parse("=A3+1")
    for offset in range(200):
        grid.formulas[(offset + 2, 1)] = FormulaCell(step, rows=offset)
    with pytest.raises(LocatedFormulaError, match="other direction"):
        Evaluator([grid], max_rows=300).run()


def test_sumif_column_uses_the_value_index():
    rows = 5000
    data = SheetGrid("D", 2)
    for r in range(2, rows + 2):
        data.values[(r, 1)] = f"k{r % 50}"
        data.values[(r, 2)] = 1.0
    template = parse(f"=SUMIF($A$2:$A${rows + 1},A2,$B$2:$B${rows + 1})")
    for offset in range(rows):
        data.formulas[(offset + 2, 3)] = FormulaCell(template, rows=offset)
    data.columns = 3
    evaluator = Evaluator([data], max_rows=rows + 1)
    evaluator.run()
    assert evaluator.results[("D", 2, 3)] == 100.0
    assert evaluator.reads < MAX_CELL_READS // 4


def test_serials_follow_the_1900_system():
    assert to_serial(date(1900, 1, 1)) == 1
    assert to_serial(date(1900, 3, 1)) == 61
    assert to_serial(date(2026, 10, 28)) == 46323
    assert from_serial(46323) == date(2026, 10, 28)
