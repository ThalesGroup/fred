# Copyright Thales 2026
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

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path


def test_lifecycle_workflow_validates_in_temporal_sandbox() -> None:
    """Ensure the workflow import graph stays sandbox-safe for Temporal."""

    script = textwrap.dedent(
        """
        import asyncio
        from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner
        from temporalio.workflow import _Definition
        from control_plane_backend.scheduler.temporal.workflow import LifecycleManagerWorkflow

        async def main() -> None:
            runner = SandboxedWorkflowRunner()
            runner.prepare_workflow(_Definition.must_from_class(LifecycleManagerWorkflow))

        asyncio.run(main())
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
