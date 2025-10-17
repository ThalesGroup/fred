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

import csv
import logging
from pathlib import Path

import pandas as pd

from knowledge_flow_backend.core.processors.input.common.base_input_processor import BaseTabularProcessor

logger = logging.getLogger(__name__)


class CsvTabularProcessor(BaseTabularProcessor):
    """
    An example tabular processor for CSV files.
    Extracts header and rows from a simple CSV file.
    """

    def check_file_validity(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".csv" and file_path.is_file()

    def detect_delimiter(self, file_path: Path, encodings: list[str]) -> str:
        for enc in encodings:
            try:
                with open(file_path, encoding=enc) as f:
                    sample = f.read(4096)
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                    return dialect.delimiter
            except Exception as e:
                logger.warning(f"Failed to detect the delemiter, error: {e}")
        return ","

    def check_column_consistency(self, file_path: Path, delimiter: str, encoding: str, max_lines: int = 10) -> bool:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                header = f.readline().rstrip("\n")
                expected_cols = len(header.split(delimiter))

                for i in range(max_lines):
                    line = f.readline()
                    if not line:  # fin de fichier avant max_lines
                        break
                    cols = line.rstrip("\n").split(delimiter)
                    if len(cols) != expected_cols:
                        logger.warning(f"Inconsistent number of columns at line {i + 2}: expected {expected_cols}, got {len(cols)}")
                        return False
            return True
        except Exception as e:
            logger.error(f"Error while checking column consistency: {e}")
            return False

    def read_csv_flexible(self, path: Path, encodings: list[str] = ["utf-8", "latin1", "iso-8859-1"]) -> pd.DataFrame:
        if not self.check_file_validity(path):
            logger.error(f"File invalid or not found: {path}")
            return pd.DataFrame()

        delimiter = self.detect_delimiter(path, encodings)
        if delimiter is None:
            logger.error(f"Could not detect delimiter for file {path}")
            return pd.DataFrame()

        # if not self.check_column_consistency(path, delimiter):
        #     logger.error(f"CSV file '{path}' has inconsistent column counts. Skipping.")
        #     return pd.DataFrame()

        for enc in encodings:
            try:
                df = pd.read_csv(path, sep=delimiter, encoding=enc, engine="python")
                logger.info(f"CSV loaded successfully with delimiter '{delimiter}' and encoding '{enc}'")
                return df
            except Exception as e:
                logger.warning(f"Failed to read CSV with encoding '{enc}': {e}")

        logger.error(f"Failed to read CSV file '{path}' with detected delimiter '{delimiter}' and encodings {encodings}")
        return pd.DataFrame()

    def extract_file_metadata(self, file_path: Path) -> dict:
        df = self.read_csv_flexible(file_path)
        return {
            "suffix": "CSV",
            "row_count": len(df),  # optional: use nrows param if needed
            "num_columns": len(df.columns),
            "sample_columns": df.columns.tolist(),
        }

    def convert_file_to_table(self, file_path: Path) -> pd.DataFrame:
        return self.read_csv_flexible(file_path)
