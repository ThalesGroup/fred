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
