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

from pathlib import Path

import pandas

from app.core.processors.input.common.base_input_processor import BaseTabularProcessor


class CsvTabularProcessor(BaseTabularProcessor):
    """
    An example tabular processor for CSV files.
    Extracts header and rows from a simple CSV file.
    """

    def check_file_validity(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".csv" and file_path.is_file()

    def extract_file_metadata(self, file_path: Path) -> dict:
        df = pandas.read_csv(file_path, nrows=5)
        return {
            "format": "CSV",
            "row_count": len(pandas.read_csv(file_path)),  # optional: use nrows param if needed
            "num_columns": len(df.columns),
            "sample_columns": df.columns.tolist(),
        }

    def convert_file_to_table(self, file_path: Path) -> pandas.DataFrame:
        return pandas.read_csv(file_path)
