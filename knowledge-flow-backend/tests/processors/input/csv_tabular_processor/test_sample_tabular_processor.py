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


import tempfile
from pathlib import Path

import pandas as pd

from knowledge_flow_backend.core.processors.input.csv_tabular_processor.csv_tabular_processor import CsvTabularProcessor


def test_valid_csv():
    processor = CsvTabularProcessor()
    content = "name,age\nAlice,30\nBob,25"
    with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".csv") as f:
        f.write(content)
        temp_path = Path(f.name)

    assert processor.check_file_validity(temp_path)
    df = processor.convert_file_to_table(temp_path)
    assert isinstance(df, pd.DataFrame)
    assert df.shape == (2, 2)

    metadata = processor.extract_file_metadata(temp_path)
    assert metadata["num_columns"] == 2
    assert metadata["sample_columns"] == ["name", "age"]

    temp_path.unlink()
