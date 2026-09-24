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

import ast
import asyncio
from contextlib import contextmanager
from pathlib import Path
from importlib.util import resolve_name

from knowledge_flow_backend.common.processing_metrics import processing_metrics_scope, processing_timer


def test_metrics_context_propagates_to_thread_and_restores_after_error():
    calls = []

    @contextmanager
    def timer(name, dims):
        calls.append((name, dims))
        yield

    def work():
        with processing_timer("ocr", {"file_type": "pdf"}):
            pass

    async def scenario():
        with processing_metrics_scope(timer):
            await asyncio.to_thread(work)
            try:
                with processing_metrics_scope(lambda *_: (_ for _ in ()).throw(ValueError("setup"))):
                    work()
            except ValueError:
                pass
            work()
        work()  # No collector outside scope.

    asyncio.run(scenario())
    assert calls == [("ocr", {"file_type": "pdf"})] * 2


def test_input_processors_do_not_import_scheduler_or_temporal():
    root = Path(__file__).resolve().parents[2] / "knowledge_flow_backend"
    paths = list((root / "core/processors/input").rglob("*.py")) + [root / "common/processing_metrics.py"]
    violations = []
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                package = "knowledge_flow_backend." + ".".join(path.relative_to(root).parent.parts)
                name = resolve_name("." * node.level + (node.module or ""), package) if node.level else (node.module or "")
                names = [name] + [name + "." + alias.name for alias in node.names]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            for name in names:
                if name == "temporalio" or name.startswith(("temporalio.", "knowledge_flow_backend.features.scheduler")):
                    violations.append(f"{path.relative_to(root)}:{node.lineno}: {name}")
    assert not violations, "\n".join(violations)
