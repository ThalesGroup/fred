# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Kubernetes Job adapter with an explicit VM or user-space-kernel RuntimeClass."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from uuid import uuid4

from fred_sdk.contracts.sandbox import SandboxError, SandboxRequest, SandboxResult

from .backend import SandboxLease, SandboxPrepareLeak
from .command import CommandRunner, CommandTimeout
from .config import BrokerSettings
from .mounts import RcloneCsiMount, view_key_for_mount
from .process_cleanup import remove_code_processes

_DENY_POLICY = "fred-sandbox-deny-all"


class KubernetesBackend:
    def __init__(self, settings: BrokerSettings, runner: CommandRunner) -> None:
        self.settings = settings
        self.runner = runner
        self.mount = (
            RcloneCsiMount(settings, runner)
            if settings.mount_provider == "rclone_csi"
            else None
        )

    async def preflight(self) -> None:
        settings = self.settings
        runtime = await self._get_json(
            ["kubectl", "get", "runtimeclass", settings.runtime_name, "-o", "json"],
            "runtime_unavailable",
        )
        handler = str(runtime.get("handler", "")).lower()
        marker = "kata" if settings.isolation == "kata" else "runsc"
        if marker not in handler and not (
            settings.isolation == "gvisor" and "gvisor" in handler
        ):
            raise SandboxError("runtime_unavailable")
        namespace = await self._get_json(
            ["kubectl", "get", "namespace", settings.namespace, "-o", "json"],
            "policy_unavailable",
        )
        labels = namespace.get("metadata", {}).get("labels", {})
        if labels.get("pod-security.kubernetes.io/enforce") != "restricted":
            raise SandboxError("policy_unavailable")
        policies = await self._get_json(
            self._kubectl("get", "networkpolicies", "-o", "json"),
            "policy_unavailable",
        )
        items = policies.get("items", [])
        if not isinstance(items, list) or len(items) != 1:
            raise SandboxError("policy_unavailable")
        policy = items[0]
        if (
            not isinstance(policy, dict)
            or policy.get("metadata", {}).get("name") != _DENY_POLICY
        ):
            raise SandboxError("policy_unavailable")
        spec = policy.get("spec", {})
        if (
            spec.get("podSelector") != {}
            or not {"Ingress", "Egress"}.issubset(set(spec.get("policyTypes", [])))
            or spec.get("ingress")
            or spec.get("egress")
        ):
            raise SandboxError("policy_unavailable")
        if self.mount is not None:
            await self.mount.preflight()

    async def prepare(self, view_key: str | None = None) -> SandboxLease:
        name = f"fred-sbx-{uuid4().hex[:20]}"
        mounted_key = view_key_for_mount(view_key) if self.mount else None
        lease = SandboxLease(id=name, target=name, view_key=mounted_key)
        manifest = self.job_manifest(name)
        try:
            if self.mount is not None and mounted_key is not None:
                await self.mount.create_secret(name, mounted_key)
                await self.mount.create_pvc(name)
            result = await self.runner.run(
                self._kubectl("create", "-f", "-"),
                timeout=15,
                input_data=json.dumps(manifest).encode(),
            )
            if result.returncode != 0:
                raise SandboxError("backend_failed")
            if self.mount is not None:
                await self.mount.attach_owner(name, "job", pvc=True)
            deadline = time.monotonic() + self.settings.preparation_timeout_seconds
            while time.monotonic() < deadline:
                pods = await self._get_json(
                    self._kubectl(
                        "get",
                        "pods",
                        "-l",
                        f"batch.kubernetes.io/job-name={name}",
                        "-o",
                        "json",
                    ),
                    "backend_failed",
                )
                for pod in pods.get("items", []):
                    status = pod.get("status", {})
                    if status.get("phase") == "Failed":
                        raise SandboxError("backend_failed")
                    if any(
                        condition.get("type") == "Ready"
                        and condition.get("status") == "True"
                        for condition in status.get("conditions", [])
                    ):
                        pod_name = pod.get("metadata", {}).get("name")
                        if isinstance(pod_name, str) and pod_name:
                            return SandboxLease(
                                id=name, target=pod_name, view_key=mounted_key
                            )
                await asyncio.sleep(0.25)
            raise SandboxError("backend_failed")
        except BaseException:
            try:
                await self.dispose(lease)
            except Exception as exc:
                raise SandboxPrepareLeak(lease) from exc
            raise

    async def execute(
        self, lease: SandboxLease, request: SandboxRequest
    ) -> SandboxResult:
        interpreter = "/bin/bash" if request.language == "bash" else "python"
        try:
            try:
                result = await self.runner.run(
                    self._kubectl(
                        "exec", lease.target, "--", interpreter, "-c", request.code
                    ),
                    timeout=self.settings.execution_timeout_seconds,
                    output_limit=self.settings.output_limit_bytes,
                )
            except CommandTimeout:
                return SandboxResult(
                    exit_code=None, stdout="", stderr="", timed_out=True
                )
        finally:
            await remove_code_processes(
                self.runner, self._kubectl("exec", lease.target, "--")
            )
        return SandboxResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            truncated=result.truncated,
        )

    async def dispose(self, lease: SandboxLease) -> None:
        await self._delete(lease.id)
        if self.mount is not None:
            await self.mount.delete(lease.id)

    async def recover(self) -> None:
        result = await self.runner.run(
            self._kubectl(
                "delete",
                "jobs",
                "-l",
                "app.kubernetes.io/name=fred-sandbox",
                "--ignore-not-found=true",
                "--wait=true",
            ),
            timeout=90,
        )
        if result.returncode != 0:
            raise SandboxError("backend_failed")
        if self.mount is not None:
            await self.mount.clean_orphans()

    def job_manifest(self, name: str) -> dict[str, Any]:
        settings = self.settings
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": name,
                "namespace": settings.namespace,
                "labels": {"app.kubernetes.io/name": "fred-sandbox"},
            },
            "spec": {
                "backoffLimit": 0,
                "activeDeadlineSeconds": 86400,
                "ttlSecondsAfterFinished": 60,
                "template": {
                    "metadata": {"labels": {"app.kubernetes.io/name": "fred-sandbox"}},
                    "spec": {
                        "runtimeClassName": settings.runtime_name,
                        "automountServiceAccountToken": False,
                        "enableServiceLinks": False,
                        "hostNetwork": False,
                        "hostPID": False,
                        "hostIPC": False,
                        "restartPolicy": "Never",
                        "terminationGracePeriodSeconds": 1,
                        "securityContext": {
                            "runAsNonRoot": True,
                            "runAsUser": 65534,
                            "runAsGroup": 65534,
                            "fsGroup": 65534,
                            "seccompProfile": {"type": "RuntimeDefault"},
                        },
                        "containers": [
                            {
                                "name": "sandbox",
                                "image": settings.image,
                                "imagePullPolicy": "IfNotPresent",
                                "command": ["sleep", "infinity"],
                                "workingDir": "/work",
                                "env": [
                                    {"name": "HOME", "value": "/work"},
                                    {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
                                ],
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "readOnlyRootFilesystem": True,
                                    "capabilities": {"drop": ["ALL"]},
                                },
                                "resources": {
                                    "requests": {
                                        "cpu": "100m",
                                        "memory": "64Mi",
                                        "ephemeral-storage": "16Mi",
                                    },
                                    "limits": {
                                        "cpu": "500m",
                                        "memory": "256Mi",
                                        "ephemeral-storage": "16Mi",
                                    },
                                },
                                "volumeMounts": [
                                    {"name": "scratch", "mountPath": "/tmp"},
                                    {"name": "scratch", "mountPath": "/work"},
                                ]
                                + (
                                    [
                                        {
                                            "name": "inputs",
                                            "mountPath": "/inputs",
                                            "readOnly": True,
                                        }
                                    ]
                                    if self.mount
                                    else []
                                ),
                            }
                        ],
                        "volumes": [
                            {"name": "scratch", "emptyDir": {"sizeLimit": "16Mi"}}
                        ]
                        + (
                            [
                                {
                                    "name": "inputs",
                                    "persistentVolumeClaim": {
                                        "claimName": f"inputs-{name}",
                                        "readOnly": True,
                                    },
                                }
                            ]
                            if self.mount
                            else []
                        ),
                    },
                },
            },
        }

    async def _get_json(self, args: list[str], error_code: str) -> dict[str, Any]:
        result = await self.runner.run(args, timeout=10)
        if result.returncode != 0:
            raise SandboxError(error_code)
        try:
            value = json.loads(result.stdout)
        except ValueError as exc:
            raise SandboxError(error_code) from exc
        if not isinstance(value, dict):
            raise SandboxError(error_code)
        return value

    async def _delete(self, name: str) -> None:
        result = await self.runner.run(
            self._kubectl(
                "delete",
                "job",
                name,
                "--ignore-not-found=true",
                "--cascade=foreground",
                "--wait=true",
            ),
            timeout=90,
        )
        if result.returncode != 0:
            raise SandboxError("backend_failed")

    def _kubectl(self, *args: str) -> list[str]:
        return ["kubectl", "--namespace", self.settings.namespace, *args]
