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

from datetime import date, datetime

import pytest
from fred_capability_spreadsheet.evaluator import (
    MAX_CELL_READS,
    MAX_SOLVER_ITERATIONS,
    Evaluator,
    FormulaCell,
    LocatedFormulaError,
    SheetGrid,
    XLError,
    from_serial,
    to_serial,
)
from fred_capability_spreadsheet.formulas import FUNCTIONS, FormulaError, parse

NOW = datetime(2026, 10, 28, 14, 30)

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
    evaluator = Evaluator([data, out], max_rows=5002, now=NOW)
    evaluator.run()
    return evaluator.results[("S", 2, 1)]


def _spill(text: str) -> list[list[object]]:
    data = _grid()
    out = SheetGrid("S", 5)
    out.formulas[(2, 1)] = FormulaCell(parse(text, ["D", "S"]), may_spill=True)
    evaluator = Evaluator([data, out], max_rows=5002, now=NOW)
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
    # text and information
    ('=TEXT(1234.567,"#,##0.00")', "1,234.57"),
    ('=TEXT(1234567,"# ##0")', "1234 567"),  # en-US: the space is a literal
    ('=TEXT(-0.5,"0")', "-1"),
    ('=TEXT(0.256,"0.0%")', "25.6%"),
    ('=TEXT(D!C2,"dd/mm/yyyy")', "31/01/2026"),
    ('=TEXT(D!C2,"mmm yyyy")', "Jan 2026"),
    ('=TEXT(0.5+1/1440,"hh:mm")', "12:01"),
    ('=TEXT("abc","0")', "abc"),
    ('=FIND("b","abcb",3)', 4.0),
    ('=FIND("B","abc")', XLError("#VALUE!")),
    ('=SEARCH("B*","aab")', 3.0),
    ('=SEARCH("z","a")', XLError("#VALUE!")),
    ('=REPT("ab",3)', "ababab"),
    ('=REPT("a",-1)', XLError("#VALUE!")),
    ('=EXACT("a","A")', False),
    ("=ISBLANK(D!A6)", True),
    ('=ISBLANK("")', False),
    ("=ISNUMBER(D!B2)", True),
    ("=ISNUMBER(D!B6)", False),
    ("=ISTEXT(D!B6)", True),
    ("=ISERROR(1/0)", True),
    ("=ISNA(1/0)", False),
    ('=ISNA(XLOOKUP("q",D!A2:A6,D!B2:B6))', True),
    # statistics (numbers only from ranges: B6 "x" is skipped)
    ("=STDEV.S(D!B2:B6)", 5.446711546122731),
    ("=STDEV(D!B2:B6)", 5.446711546122731),
    ("=STDEV.S(1)", XLError("#DIV/0!")),
    ("=STDEV.P(D!B2:B6)", 4.716990566028302),
    ("=VAR.S(D!B2:B6)", 29.666666666666668),
    ("=VAR.P(D!B2:B6)", 22.25),
    ("=PERCENTILE.INC(D!B2:B6,0.3)", 1.5),
    ("=PERCENTILE.INC(D!B2:B6,2)", XLError("#NUM!")),
    ("=QUARTILE.INC(D!B2:B6,1)", 0.75),
    ("=QUARTILE.INC(D!B2:B6,5)", XLError("#NUM!")),
    ("=RANK.EQ(D!B3,D!B2:B6)", 2.0),
    ("=RANK(D!B3,D!B2:B6,1)", 3.0),
    ("=RANK(7,D!B2:B6)", XLError("#N/A")),
    ("=LARGE(D!B2:B6,2)", 5.0),
    ("=SMALL(D!B2:B6,1)", -3.0),
    ("=SMALL(D!B2:B6,5)", XLError("#NUM!")),
    ("=AVERAGEA(D!A2:B6)", 1.5555555555555556),
    ("=AVERAGEA(D!C4:C5)", XLError("#DIV/0!")),
    # finance
    ("=PMT(0.05/12,60,10000)", -188.7123364401099),
    ("=PMT(0,10,1000)", -100.0),
    ("=PMT(0.05,0,100)", XLError("#NUM!")),
    ("=FV(0.05/12,60,-200)", 13601.216568168567),
    ("=FV(0.05,10,-100,-1000,1)", 2949.57334301007),
    ("=PV(0.05/12,60,-200)", 10598.14126478543),
    ("=NPV(0.1,-1000,300,400,500)", -19.124376750222126),
    ("=NPV(-1,1)", XLError("#DIV/0!")),
    ("=IRR(D!B2:B3)", XLError("#NUM!")),  # no negative flow
    ("=RATE(60,-200,10000)", 0.006183413161253943),
    # lookup
    ('=HLOOKUP("Amt",D!A1:C3,3,FALSE)', 5.0),
    ('=HLOOKUP("zz",D!A1:C3,2,FALSE)', XLError("#N/A")),
    ('=HLOOKUP("Amt",D!A1:C3,9,FALSE)', XLError("#REF!")),
    ('=CHOOSE(2,"a","b")', "b"),
    ("=SUM(CHOOSE(1,D!B2:B3,D!B4))", 15.0),
    ("=CHOOSE(4,1,2)", XLError("#VALUE!")),
    # dates (2026-01-31 is a Saturday)
    ("=DAYS(D!C3,D!C2)", 15.0),
    ("=DAYS(-1,1)", XLError("#NUM!")),
    ("=WORKDAY(D!C2,5)", to_serial(date(2026, 2, 6))),
    ("=WORKDAY(D!C2,-1)", to_serial(date(2026, 1, 30))),
    ("=WORKDAY(DATE(2026,1,2),10,D!C2:C3)", to_serial(date(2026, 1, 16))),
    ("=WORKDAY(DATE(2026,2,13),1,D!C2:C3)", to_serial(date(2026, 2, 16))),
    ("=NETWORKDAYS(D!C2,D!C3)", 10.0),
    ("=NETWORKDAYS(D!C3,D!C2)", -10.0),
    ("=NETWORKDAYS(DATE(2026,2,9),DATE(2026,2,20),DATE(2026,2,13))", 9.0),
    ("=YEARFRAC(DATE(2024,1,1),DATE(2025,3,1),1)", 1.1627906976744187),
    ("=YEARFRAC(DATE(2024,1,31),DATE(2024,3,31))", 0.16666666666666666),
    ("=YEARFRAC(DATE(2024,2,29),DATE(2025,2,28),4)", 0.9972222222222222),
    ("=YEARFRAC(1,2,5)", XLError("#NUM!")),
    ("=TODAY()", to_serial(date(2026, 10, 28))),
    ("=NOW()-TODAY()", 14.5 / 24),
    # rounding
    ("=TRUNC(-8.97,1)", -8.9),
    ("=TRUNC(8.97)", 8.0),
    ("=MROUND(10,3)", 9.0),
    ("=MROUND(-5,-2)", -6.0),
    ("=MROUND(5,-2)", XLError("#NUM!")),
    ("=CEILING(2.2,0.1)", 2.2),
    ("=CEILING(-2.5,2)", -2.0),
    ("=CEILING(2.5,-2)", XLError("#NUM!")),
    ("=FLOOR(-2.5,2)", -4.0),
    ("=FLOOR(2.5,0)", XLError("#DIV/0!")),
    ("=CEILING.MATH(-5.5)", -5.0),
    ("=CEILING.MATH(-5.5,2,1)", -6.0),
    ("=FLOOR.MATH(-5.5)", -6.0),
    ("=FLOOR.MATH(5.5,2)", 4.0),
    # arrays and names
    ("=SUM(SEQUENCE(4,1,10,5))", 70.0),
    ("=SEQUENCE(0)", XLError("#CALC!")),
    ("=LET(x,D!B2,y,x*2,y+1)", 21.0),
    ("=LET(rng,D!B2:B6,SUM(rng)/COUNT(rng))", 3.5),
    ("=LET(x,1,LET(y,x+1,y*10))", 20.0),
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


def test_irr_converges_and_charges_its_iterations():
    data = _grid()
    data.values.update({(2, 4): -1000.0, (3, 4): 300.0, (4, 4): 400.0, (5, 4): 500.0})
    # 1, -3, 3 has no rate that zeroes it: the solver stops at its cap.
    data.values.update({(2, 5): 1.0, (3, 5): -3.0, (4, 5): 3.0})
    data.columns = 5
    out = SheetGrid("S", 2)
    out.formulas[(2, 1)] = FormulaCell(parse("=IRR(D!D2:D5)", ["D"]))
    out.formulas[(2, 2)] = FormulaCell(parse("=IRR(D!E2:E4)", ["D"]))
    evaluator = Evaluator([data, out], max_rows=10)
    evaluator.run()
    assert evaluator.results[("S", 2, 1)] == pytest.approx(0.08896, abs=1e-5)
    assert evaluator.results[("S", 2, 2)] == XLError("#NUM!")
    assert evaluator.reads < 3 * 4 * MAX_SOLVER_ITERATIONS * 2 + 100


def test_rank_column_sorts_the_range_once():
    rows = 5000
    data = SheetGrid("D", 2)
    for r in range(2, rows + 2):
        data.values[(r, 1)] = float(r % 977)
    template = parse(f"=RANK.EQ(A2,$A$2:$A${rows + 1})")
    for offset in range(rows):
        data.formulas[(offset + 2, 2)] = FormulaCell(template, rows=offset)
    evaluator = Evaluator([data], max_rows=rows + 1)
    evaluator.run()
    values = [r % 977 for r in range(2, rows + 2)]
    assert evaluator.results[("D", 2, 2)] == 1 + sum(v > 2 for v in values)
    assert evaluator.reads < MAX_CELL_READS // 20


def test_sequence_spills_and_is_charged_before_it_is_built():
    assert _spill("=SEQUENCE(2,3,0,2)") == [[0.0, 2.0, 4.0], [6.0, 8.0, 10.0]]
    with pytest.raises(LocatedFormulaError, match="too many cells"):
        _eval("=SUM(SEQUENCE(100000,100))")


def test_workday_jumps_whole_weeks():
    assert _eval("=WORKDAY(DATE(2026,1,1),100000)") == pytest.approx(
        to_serial(date(2026, 1, 1)) + 140_000
    )


def test_text_refuses_exotic_formats():
    for code in ("0.0E+00", "[h]:mm", "0;-0", "hh:mm AM/PM", "#,##0,"):
        with pytest.raises(LocatedFormulaError, match="TEXT format"):
            _eval(f'=TEXT(1,"{code}")')


def test_let_names_are_checked_at_parse_time():
    for text, message in (
        ("=LET(x,1)", "name, value pairs"),
        ("=LET(a1,1,a1)", "must not look like a cell"),
        ("=LET(x,1,y)", "defined names"),
        ("=LET(x,y,1,x)", "name, value pairs"),
        ("=LET(x,1,LET(x,2,x))", "already defined"),
        ("=LET(x,1,x,2,x)", "already defined"),
    ):
        with pytest.raises(FormulaError, match=message):
            parse(text)


def test_clock_is_frozen_and_reported():
    out = SheetGrid("S", 2)
    out.formulas[(2, 1)] = FormulaCell(parse("=NOW()"))
    out.formulas[(2, 2)] = FormulaCell(parse("=NOW()"))
    evaluator = Evaluator([out], max_rows=10)
    evaluator.run()
    assert evaluator.clock_read and evaluator.now is not None
    assert evaluator.results[("S", 2, 1)] == evaluator.results[("S", 2, 2)]
    quiet = Evaluator([SheetGrid("S", 1)], max_rows=10)
    quiet.run()
    assert not quiet.clock_read


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
