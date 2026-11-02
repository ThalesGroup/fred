"""Common primitives must not resolve application singletons or processors."""

import subprocess
import sys


def test_shared_primitives_without_either_application():
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
        if fullname.startswith(('knowledge_flow_backend', 'knowledge_flow_worker', 'temporalio')):
            raise AssertionError(f'Common library crossed its boundary: {fullname}')
sys.meta_path.insert(0, Boundary())
from fred_knowledge.artifacts.reader import ArtifactReader
from fred_knowledge.tabular.artifacts import read_tabular_artifact
from fred_knowledge.vector.factory import build_vector_store
from fred_knowledge.text.smart_llm_summarizer import SmartDocSummarizer
""",
        ],
        check=True,
    )
