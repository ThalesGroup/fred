# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Docker adapter for disposable Kata or gVisor containers."""

from __future__ import annotations

import json
from uuid import uuid4

from fred_sdk.contracts.sandbox import SandboxError, SandboxRequest, SandboxResult

from .backend import SandboxLease, SandboxPrepareLeak
from .command import CommandRunner, CommandTimeout
from .config import BrokerSettings
from .process_cleanup import remove_code_processes


class DockerBackend:
    def __init__(self, settings: BrokerSettings, runner: CommandRunner) -> None:
        self.settings = settings
        self.runner = runner

    async def preflight(self) -> None:
        result = await self.runner.run(
            ["docker", "info", "--format", "{{json .Runtimes}}"], timeout=10
        )
        if result.returncode != 0:
            raise SandboxError("unavailable")
        try:
            runtimes = json.loads(result.stdout)
            runtime = runtimes[self.settings.runtime_name]
        except (ValueError, KeyError, TypeError) as exc:
            raise SandboxError("runtime_unavailable") from exc
        if not isinstance(runtime, dict):
            raise SandboxError("runtime_unavailable")
        path = str(runtime.get("path") or runtime.get("Path") or "").lower()
        marker = "kata" if self.settings.isolation == "kata" else "runsc"
        if marker not in path and not (
            self.settings.isolation == "gvisor" and "gvisor" in path
        ):
            raise SandboxError("runtime_unavailable")

    async def prepare(self) -> SandboxLease:
        name = f"fred-sbx-{uuid4().hex[:20]}"
        settings = self.settings
        args = [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--pull",
            "never",
            "--name",
            name,
            "--runtime",
            settings.runtime_name,
            "--network",
            "none",
            "--read-only",
            "--user",
            "65534:65534",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "64",
            "--cpus",
            "0.5",
            "--memory",
            "256m",
            "--memory-swap",
            "256m",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=16m,mode=1777",
            "--workdir",
            "/tmp",
            "--env",
            "HOME=/tmp",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            settings.image,
            "sleep",
            "86400",
        ]
        try:
            result = await self.runner.run(
                args, timeout=settings.preparation_timeout_seconds
            )
            if result.returncode != 0:
                raise SandboxError("backend_failed")
            return SandboxLease(id=name, target=name)
        except BaseException:
            try:
                await self._remove(name)
            except Exception as exc:
                raise SandboxPrepareLeak(SandboxLease(id=name, target=name)) from exc
            raise

    async def execute(
        self, lease: SandboxLease, request: SandboxRequest
    ) -> SandboxResult:
        interpreter = "/bin/bash" if request.language == "bash" else "python"
        try:
            try:
                result = await self.runner.run(
                    ["docker", "exec", lease.target, interpreter, "-c", request.code],
                    timeout=self.settings.execution_timeout_seconds,
                    output_limit=self.settings.output_limit_bytes,
                )
            except CommandTimeout:
                return SandboxResult(
                    exit_code=None, stdout="", stderr="", timed_out=True
                )
        finally:
            await remove_code_processes(self.runner, ["docker", "exec", lease.target])
        return SandboxResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            truncated=result.truncated,
        )

    async def dispose(self, lease: SandboxLease) -> None:
        await self._remove(lease.id)

    async def _remove(self, name: str) -> None:
        result = await self.runner.run(["docker", "rm", "--force", name], timeout=10)
        if result.returncode != 0 and "No such container" not in result.stderr:
            raise SandboxError("backend_failed")
