# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import pandas as pd
from tabulate import tabulate


def dataframe_to_markdown_preview(df: pd.DataFrame) -> str:
    """
    Convert one bounded DataFrame into the UI markdown preview format.

    Why this exists:
    - Markdown and Parquet-backed tabular previews should share the same
      empty-state formatting.

    How to use:
    - Pass a small preview DataFrame, typically already limited to the
      desired row count.
    """

    def _format_cell(value: object) -> str:
        text = "" if value is None else str(value)
        return text.replace("|", "&#124;").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")

    formatted_headers = [_format_cell(name) for name in df.columns.tolist()]
    formatted_rows = [[_format_cell(cell) for cell in row] for row in df.itertuples(index=False, name=None)]
    preview_str = tabulate(formatted_rows, headers=formatted_headers, tablefmt="github")
    if preview_str is None or preview_str.strip() == "":
        return "_(The CSV file is empty or has no data to display)_"
    return preview_str
