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

import logging
from pathlib import Path

import pandas as pd

from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseTabularProcessor

logger = logging.getLogger(__name__)


class PpsTabularProcessor(BaseTabularProcessor):
    """
    PPS Tabular Processor
    ------------------------------------------------------
    This processor is designed to handle the specific structure of PPS Excel files.
    It extracts relevant data from the specified columns and formats it into a structured DataFrame.
    It is a subclass of the BaseTabularProcessor class.
    """

    def __init__(self):
        # the expected sheet name in the Excel file
        self._default_sheet = "Fiche d'affaire"

        # Configuration of columns to extract (logical label -> Excel column)
        self._columns_to_extract = [
            ("Nom Centre", "Unnamed: 1"),
            ("Num Projet (OTP)", "Unnamed: 1"),
            ("Centre de profit", "Unnamed: 1"),
            ("Description projet", "Unnamed: 1"),
            ("PM", "Unnamed: 9"),
            ("CDG", "Unnamed: 9"),
            ("Total Prise de commande", "Unnamed: 2"),
            ("40-CHIFFRE D'AFFAIRES", "Unnamed: 2"),
            ("Marge brute corrigée", "Unnamed: 0"),
            ("40-MAIN D'ŒUVRE", "Unnamed: 2"),
            ("FACTURATION", "Unnamed: 2"),
            ("40-FRAIS DE MISSION", "Unnamed: 2"),
            ("40-AUTRES COÛTS", "Unnamed: 2"),
            ("Total Coûts de Production", "Unnamed: 2"),
        ]

    def check_file_validity(self, file_path: Path) -> bool:
        return file_path.is_file()

    def extract_file_metadata(self, file_path: Path) -> dict:
        try:
            # Try to load the configured/default sheet
            df_preview = pd.read_excel(file_path, sheet_name=self._default_sheet, nrows=5)
            df_full = pd.read_excel(file_path, sheet_name=self._default_sheet)
        except ValueError as e:
            available_sheets = self._list_excel_sheets(file_path)
            raise ValueError(f"Sheet '{self._default_sheet}' not found. Available sheets: {available_sheets}") from e

        return {
            "format": "XLSM",
            "sheet_name": self._default_sheet,
            "row_count": len(df_full),
            "num_columns": len(df_preview.columns),
            "sample_columns": df_preview.columns.tolist(),
        }

    def convert_file_to_table(self, file_path: Path) -> pd.DataFrame:
        df = self._read_excel_sheet(file_path, self._default_sheet)  # ✅ Read once

        rows = []
        for label, column in self._columns_to_extract:
            value = self._extract_value(df, label, column)
            if label == "Marge brute corrigée" and value is not None:
                try:
                    value = abs(float(value))
                except (ValueError, TypeError):
                    logger.warning(f"Failed to convert value '{value}' to float for label '{label}'")
                    pass
            rows.append({"Champ": label, "Valeur extraite": value if value is not None else "NOT FOUND"})

        return pd.DataFrame(rows)

    def _extract_value(self, df: pd.DataFrame, target_text: str, target_column: str):
        row = df[df.apply(lambda r: r.astype(str).str.contains(target_text, regex=False).any(), axis=1)]
        return row.iloc[0][target_column] if not row.empty else None

    # Private method: simple reading of Excel sheet
    def _read_excel_sheet(self, file: Path, sheet: str, n_rows: int = None) -> pd.DataFrame:
        df = pd.read_excel(file, sheet_name=sheet)
        return df.head(n_rows) if n_rows else df

    #  Private method: list available sheets
    def _list_excel_sheets(self, file_path: Path):
        xls = pd.ExcelFile(file_path)
        return xls.sheet_names
