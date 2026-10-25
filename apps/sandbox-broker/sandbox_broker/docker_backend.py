# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Docker adapter for disposable Kata or gVisor containers."""

from __future__ import annotations

import json
import re
from uuid import uuid4

from fred_sdk.contracts.sandbox import SandboxError, SandboxRequest, SandboxResult

from .backend import SandboxLease, SandboxPrepareLeak
from .command import CommandRunner, CommandTimeout
from .config import BrokerSettings
from .mounts import mount_bearer, view_key_for_mount
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
        if self.settings.mount_provider == "rclone_docker":
            plugin = await self.runner.run(
                [
                    "docker",
                    "plugin",
                    "inspect",
                    self.settings.docker_volume_plugin or "",
                    "--format",
                    "{{.Enabled}}",
                ],
                timeout=10,
            )
            if plugin.returncode != 0 or plugin.stdout.strip() != "true":
                raise SandboxError("policy_unavailable")
        if self.settings.skills_volume:
            volume = await self.runner.run(
                ["docker", "volume", "inspect", self.settings.skills_volume],
                timeout=10,
            )
            if volume.returncode != 0:
                raise SandboxError("policy_unavailable")
            try:
                details = json.loads(volume.stdout)
            except ValueError as exc:
                raise SandboxError("policy_unavailable") from exc
            if (
                not isinstance(details, list)
                or len(details) != 1
                or not isinstance(details[0], dict)
                or (details[0].get("Labels") or {}).get("fred.sandbox/skills")
                != "approved"
            ):
                raise SandboxError("policy_unavailable")

    async def prepare(self, view_key: str | None = None) -> SandboxLease:
        name = f"fred-sbx-{uuid4().hex[:20]}"
        settings = self.settings
        mounted_key = (
            view_key_for_mount(view_key)
            if settings.mount_provider == "rclone_docker"
            else None
        )
        lease = SandboxLease(id=name, target=name, view_key=mounted_key)
        args = [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--pull",
            "never",
            "--name",
            name,
            "--label",
            "fred.sandbox/managed=true",
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
            "--tmpfs",
            "/work:rw,nosuid,nodev,size=16m,mode=1777",
            "--workdir",
            "/work",
            "--env",
            "HOME=/work",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
        ]
        if mounted_key is not None:
            args.extend(
                ["--mount", f"type=volume,src=inputs-{name},dst=/inputs,readonly"]
            )
        if settings.skills_volume:
            args.extend(
                [
                    "--mount",
                    f"type=volume,src={settings.skills_volume},dst=/skills,readonly",
                ]
            )
        args.extend([settings.image, "sleep", "86400"])
        try:
            if mounted_key is not None:
                await self._create_volume(name, mounted_key)
            result = await self.runner.run(
                args, timeout=settings.preparation_timeout_seconds
            )
            if result.returncode != 0:
                raise SandboxError("backend_failed")
            return lease
        except BaseException:
            try:
                await self.dispose(lease)
            except Exception as exc:
                raise SandboxPrepareLeak(lease) from exc
            raise

    async def execute(
        self, lease: SandboxLease, request: SandboxRequest
    ) -> SandboxResult:
        try:
            try:
                result = await self.runner.run(
                    ["docker", "exec", lease.target, "/bin/bash", "-c", request.code],
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
        if lease.view_key is not None:
            result = await self.runner.run(
                ["docker", "volume", "rm", f"inputs-{lease.id}"], timeout=30
            )
            if result.returncode != 0 and "No such volume" not in result.stderr:
                raise SandboxError("backend_failed")

    async def recover(self) -> None:
        containers = await self.runner.run(
            ["docker", "ps", "-aq", "--filter", "label=fred.sandbox/managed=true"],
            timeout=10,
        )
        if containers.returncode != 0:
            raise SandboxError("backend_failed")
        for container_id in containers.stdout.splitlines():
            if not re.fullmatch(r"[a-f0-9]{12,64}", container_id):
                raise SandboxError("backend_failed")
            await self._remove(container_id)
        volumes = await self.runner.run(
            [
                "docker",
                "volume",
                "ls",
                "-q",
                "--filter",
                "label=fred.sandbox/managed=true",
            ],
            timeout=10,
        )
        if volumes.returncode != 0:
            raise SandboxError("backend_failed")
        for volume_name in volumes.stdout.splitlines():
            if not re.fullmatch(r"inputs-fred-sbx-[a-f0-9]{20}", volume_name):
                raise SandboxError("backend_failed")
            result = await self.runner.run(
                ["docker", "volume", "rm", volume_name], timeout=30
            )
            if result.returncode != 0:
                raise SandboxError("backend_failed")

    async def _create_volume(self, name: str, key: str) -> None:
        settings = self.settings
        if not settings.file_gateway_url or not settings.file_gateway_secret:
            raise SandboxError("policy_unavailable")
        result = await self.runner.run(
            [
                "docker",
                "volume",
                "create",
                "--name",
                f"inputs-{name}",
                "--label",
                "fred.sandbox/managed=true",
                "--driver",
                settings.docker_volume_plugin or "",
                "--opt",
                "type=webdav",
                "--opt",
                f"webdav-url={settings.file_gateway_url.rstrip('/')}/{key}",
                "--opt",
                f"webdav-bearer-token={mount_bearer(settings.file_gateway_secret, key)}",
                "--opt",
                "allow-other=true",
                "--opt",
                "vfs-cache-mode=off",
                "--opt",
                "dir-cache-time=1s",
            ],
            timeout=30,
        )
        if result.returncode != 0:
            raise SandboxError("backend_failed")

    async def _remove(self, name: str) -> None:
        result = await self.runner.run(["docker", "rm", "--force", name], timeout=10)
        if result.returncode != 0 and "No such container" not in result.stderr:
            raise SandboxError("backend_failed")
