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
import pytest

from knowledge_flow_app.core.processors.input.pps_tabular_processor.pps_tabular_processor import PpsTabularProcessor


@pytest.fixture
def processor():
    return PpsTabularProcessor()


def test_check_file_validity(processor):
    test_file = Path("knowledge_flow_app/input_processors/pps_tabular_processor/tests/assets/sample_pps.xlsm")
    assert processor.check_file_validity(test_file)


def test_extract_file_metadata(processor):
    test_file = Path("knowledge_flow_app/input_processors/pps_tabular_processor/tests/assets/sample_pps.xlsm")
    metadata = processor.extract_file_metadata(test_file)
    assert metadata["format"] == "XLSM"
    assert metadata["sheet_name"] == "Fiche d'affaire"
    assert metadata["row_count"] > 0
    assert len(metadata["sample_columns"]) > 0


def test_convert_file_to_table(processor):
    test_file = Path("knowledge_flow_app/input_processors/pps_tabular_processor/tests/assets/sample_pps.xlsm")
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir)
        df = processor.convert_file_to_table(test_file)
        assert not df.empty
        assert "Champ" in df.columns
        assert "Valeur extraite" in df.columns
