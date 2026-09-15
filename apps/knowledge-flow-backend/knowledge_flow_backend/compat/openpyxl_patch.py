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
Workaround for openpyxl's chart reader (3.1.5): `read_chart` indexes
`plotArea._charts[0]` unguarded, so a chart whose plotArea carries no plot type
openpyxl knows makes `load_workbook` raise IndexError and the whole workbook
unreadable. Charts are irrelevant to Excel extraction (cells only), so such a
chart is read as an empty placeholder instead. Applied once at import,
from `excel_processor.py`.
"""

from __future__ import annotations

from typing import Any, cast

import openpyxl.reader.drawings as _drawings
from openpyxl.chart import BarChart
from openpyxl.chart.chartspace import ChartSpace
from openpyxl.chart.reader import read_chart as original_read_chart


def tolerant_read_chart(chartspace: ChartSpace) -> Any:
    # `_charts` is an openpyxl descriptor, invisible to the type checker.
    plot = cast(Any, chartspace.chart.plotArea)
    if not plot._charts:
        plot._charts = [BarChart()]
    return original_read_chart(chartspace)


# `find_images` resolves `read_chart` from its own module globals, so this is
# the one binding that matters.
cast(Any, _drawings).read_chart = tolerant_read_chart
