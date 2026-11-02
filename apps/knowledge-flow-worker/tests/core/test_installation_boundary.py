"""Worker imports and schema must be independent of the HTTP application."""

import subprocess
import sys


def test_worker_import_without_api():
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
        if fullname.split('.')[0] == 'knowledge_flow_backend':
            raise AssertionError(f'Worker crossed API boundary: {fullname}')
sys.meta_path.insert(0, Boundary())
from knowledge_flow_worker.main import main
from knowledge_flow_worker.common.structures import Configuration, IngestionWorkerRole
assert callable(main)
assert 'security' not in Configuration.model_json_schema()['properties']
assert {r.value for r in IngestionWorkerRole} == {'common', 'extraction-fast', 'extraction-medium', 'extraction-rich'}
""",
        ],
        check=True,
    )
