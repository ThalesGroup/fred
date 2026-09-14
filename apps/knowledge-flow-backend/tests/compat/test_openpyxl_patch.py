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
Tests of the openpyxl chart-reader workaround.

`empty_plotarea_workbook` builds a real workbook whose only chart had its
`<barChart>` element stripped: the plotArea keeps its layout and axes but no
plot type, which is what a chart written by a tool openpyxl does not
understand looks like.
"""

from __future__ import annotations

import re
import zipfile

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.chartspace import ChartContainer, ChartSpace
from openpyxl.chart.plotarea import PlotArea

from knowledge_flow_backend.compat import openpyxl_patch


def _add_chart(ws, chart, anchor):
    chart.add_data(Reference(ws, min_col=2, min_row=1, max_row=4))
    ws.add_chart(chart, anchor)


@pytest.fixture
def empty_plotarea_workbook(tmp_path):
    """Sheet with values, one chart openpyxl cannot read (chart1) and one valid line chart (chart2)."""
    wb = Workbook()
    ws = wb.active
    for r in range(1, 5):
        ws.append([r, r * 2])
    _add_chart(ws, BarChart(), "D2")
    _add_chart(ws, LineChart(), "D20")
    src = tmp_path / "src.xlsx"
    wb.save(src)

    dst = tmp_path / "empty_plotarea.xlsx"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/charts/chart1.xml":
                data, n = re.subn(rb"<barChart>.*?</barChart>", b"", data, flags=re.S)
                assert n == 1
            zout.writestr(item, data)
    return dst


def test_original_read_chart_still_fails_on_empty_plotarea():
    # Canary: exercises openpyxl itself, not the workaround. If this test fails,
    # openpyxl fixed the bug upstream — delete openpyxl_patch.py, its import in
    # excel_processor.py and this test file.
    chartspace = ChartSpace(chart=ChartContainer(plotArea=PlotArea()))
    with pytest.raises(IndexError):
        openpyxl_patch.original_read_chart(chartspace)


def test_workbook_with_unreadable_chart_loads_and_keeps_valid_chart(empty_plotarea_workbook):
    wb = load_workbook(empty_plotarea_workbook)
    ws = wb.active
    assert [c.value for c in ws["A"]] == [1, 2, 3, 4]
    assert [c.value for c in ws["B"]] == [2, 4, 6, 8]
    assert [type(c).__name__ for c in ws._charts] == ["BarChart", "LineChart"]
    placeholder, kept = ws._charts
    assert placeholder.series == []
    assert len(kept.series) == 1


def test_patch_is_installed_where_find_images_looks():
    import openpyxl.reader.drawings as drawings

    assert drawings.read_chart is openpyxl_patch.tolerant_read_chart
