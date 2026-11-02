"""The API must import with ingestion packages unavailable, including transitively."""

import subprocess
import sys


def test_api_import_without_worker_or_temporal():
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            """
import sys
from importlib.abc import MetaPathFinder
class Boundary(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'knowledge_flow_worker', 'temporalio', 'docling', 'paddleocr', 'faster_whisper', 'av', 'openvino'}:
            raise AssertionError(f'API crossed ingestion boundary: {fullname}')
sys.meta_path.insert(0, Boundary())
from knowledge_flow_backend.main import create_app
from knowledge_flow_backend.common.structures import Configuration
from fred_core.documents import DocumentMetadata
assert callable(create_app)
assert not {'processing', 'scheduler', 'manager_processing'} & Configuration.model_json_schema()['properties'].keys()
""",
        ],
        check=True,
    )
