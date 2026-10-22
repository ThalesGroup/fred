# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""SIG Agent Sandbox claim lifecycle with Fred admission and exec transport."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fred_sdk.contracts.sandbox import SandboxError, SandboxRequest, SandboxResult

from .backend import SandboxLease, SandboxPrepareLeak
from .command import CommandRunner
from .config import BrokerSettings
from .kubernetes_backend import KubernetesBackend


class AgentSandboxBackend:
    def __init__(self, settings: BrokerSettings, runner: CommandRunner) -> None:
        self.settings = settings
        self.runner = runner
        self.kubernetes = KubernetesBackend(settings, runner)
        self._ready_lock = asyncio.Lock()

    async def preflight(self) -> None:
        await self.kubernetes.preflight()
        pool = await self._get("sandboxwarmpool", self.settings.agent_pool_name)
        pool_spec = pool.get("spec", {})
        template_name = pool_spec.get("sandboxTemplateRef", {}).get("name")
        if not isinstance(template_name, str) or not template_name:
            raise SandboxError("policy_unavailable")
        if pool_spec.get("updateStrategy", {}).get("type") != "Recreate":
            raise SandboxError("policy_unavailable")
        target = pool_spec.get("replicas", 1)
        if (
            not isinstance(target, int)
            or target != 0
        ):
            raise SandboxError("policy_unavailable")
        template = await self._get("sandboxtemplate", template_name)
        spec = template.get("spec", {})
        pod = spec.get("podTemplate", {}).get("spec", {})
        if spec.get(
            "networkPolicyManagement"
        ) != "Unmanaged" or not self._is_safe_pod_spec(pod):
            raise SandboxError("policy_unavailable")

    def _is_safe_pod_spec(self, pod: Any) -> bool:
        if not isinstance(pod, dict):
            return False
        containers = pod.get("containers", [])
        if len(containers) != 1 or not isinstance(containers[0], dict):
            return False
        container = containers[0]
        security = container.get("securityContext", {})
        pod_security = pod.get("securityContext", {})
        return (
            pod.get("runtimeClassName") == self.settings.runtime_name
            and pod.get("automountServiceAccountToken") is False
            and pod.get("hostNetwork", False) is False
            and pod.get("hostPID", False) is False
            and pod.get("hostIPC", False) is False
            and not pod.get("shareProcessNamespace", False)
            and not pod.get("initContainers")
            and not pod.get("ephemeralContainers")
            and pod_security.get("runAsNonRoot") is True
            and pod_security.get("runAsUser") == 65534
            and pod_security.get("seccompProfile", {}).get("type") == "RuntimeDefault"
            and container.get("image") == self.settings.image
            and container.get("name") == "sandbox"
            and container.get("command") == ["sleep", "infinity"]
            and container.get("env")
            == [
                {"name": "HOME", "value": "/tmp"},
                {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
            ]
            and not container.get("envFrom")
            and container.get("volumeMounts")
            == [{"name": "scratch", "mountPath": "/tmp"}]
            and security.get("allowPrivilegeEscalation") is False
            and security.get("readOnlyRootFilesystem") is True
            and security.get("capabilities", {}).get("drop") == ["ALL"]
            and security.get("privileged") is not True
            and container.get("resources", {}).get("limits", {}).get("memory")
            == "256Mi"
            and container.get("resources", {}).get("limits", {}).get("cpu") == "500m"
            and pod.get("volumes")
            == [{"name": "scratch", "emptyDir": {"sizeLimit": "16Mi"}}]
        )

    async def warm_state(self) -> tuple[int, int]:
        pool = await self._get("sandboxwarmpool", self.settings.agent_pool_name)
        desired = pool.get("spec", {}).get("replicas", 1)
        ready = pool.get("status", {}).get("readyReplicas", 0)
        observed = pool.get("status", {}).get("observedGeneration", 0)
        generation = pool.get("metadata", {}).get("generation", 1)
        if (
            not isinstance(desired, int)
            or desired != 0
            or not isinstance(ready, int)
            or observed < generation
        ):
            raise SandboxError("policy_unavailable")
        return ready, desired

    async def prepare(self) -> SandboxLease:
        if not self.settings.cold_start_on_miss:
            async with self._ready_lock:
                if (await self.warm_state())[0] < 1:
                    raise SandboxError("busy")
                return await self._prepare_claim()
        return await self._prepare_claim()

    async def _prepare_claim(self) -> SandboxLease:
        await self.preflight()
        name = f"fred-sbx-{uuid4().hex[:20]}"
        lease = SandboxLease(id=name, target=name)
        expiry = datetime.now(timezone.utc) + timedelta(
            seconds=self.settings.preparation_timeout_seconds
            + self.settings.execution_timeout_seconds
            + self.settings.idle_timeout_seconds
        )
        manifest: dict[str, Any] = {
            "apiVersion": "extensions.agents.x-k8s.io/v1beta1",
            "kind": "SandboxClaim",
            "metadata": {"name": name, "namespace": self.settings.namespace},
            "spec": {
                "warmPoolRef": {"name": self.settings.agent_pool_name},
                "lifecycle": {
                    "shutdownTime": expiry.isoformat().replace("+00:00", "Z"),
                    "shutdownPolicy": "DeleteForeground",
                },
            },
        }
        try:
            result = await self.runner.run(
                self.kubernetes._kubectl("create", "-f", "-"),
                timeout=15,
                input_data=json.dumps(manifest).encode(),
            )
            if result.returncode != 0:
                raise SandboxError("backend_failed")
            result = await self.runner.run(
                self.kubernetes._kubectl(
                    "wait",
                    "sandboxclaim",
                    name,
                    "--for=condition=Ready",
                    f"--timeout={self.settings.preparation_timeout_seconds}s",
                ),
                timeout=self.settings.preparation_timeout_seconds + 5,
            )
            if result.returncode != 0:
                raise SandboxError("backend_failed")
            claim = await self._get("sandboxclaim", name)
            pod_name = claim.get("status", {}).get("sandbox", {}).get("name")
            if not isinstance(pod_name, str) or not pod_name:
                raise SandboxError("backend_failed")
            pod = await self._get("pod", pod_name)
            if (
                not self._is_safe_pod_spec(pod.get("spec"))
                or pod.get("metadata", {}).get("ownerReferences", [{}])[0].get("name")
                != pod_name
            ):
                raise SandboxError("policy_unavailable")
            if not self.settings.cold_start_on_miss:
                sandbox = await self._get("sandbox", pod_name)
                if (
                    sandbox.get("metadata", {})
                    .get("labels", {})
                    .get("agents.x-k8s.io/launch-type")
                    != "warm"
                ):
                    raise SandboxError("busy")
            return SandboxLease(id=name, target=pod_name)
        except BaseException:
            try:
                await self.dispose(lease)
            except Exception as exc:
                raise SandboxPrepareLeak(lease) from exc
            raise

    async def execute(
        self, lease: SandboxLease, request: SandboxRequest
    ) -> SandboxResult:
        return await self.kubernetes.execute(lease, request)

    async def dispose(self, lease: SandboxLease) -> None:
        result = await self.runner.run(
            self.kubernetes._kubectl(
                "delete",
                "sandboxclaim",
                lease.id,
                "--ignore-not-found=true",
                "--cascade=foreground",
                "--wait=true",
            ),
            timeout=90,
        )
        if result.returncode != 0:
            raise SandboxError("backend_failed")

    async def renew(self, lease: SandboxLease, seconds: int) -> None:
        expiry = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        patch = {
            "spec": {
                "lifecycle": {"shutdownTime": expiry.isoformat().replace("+00:00", "Z")}
            }
        }
        result = await self.runner.run(
            self.kubernetes._kubectl(
                "patch",
                "sandboxclaim",
                lease.id,
                "--type=merge",
                "-p",
                json.dumps(patch),
            ),
            timeout=15,
        )
        if result.returncode != 0:
            raise SandboxError("backend_failed")

    async def _get(self, kind: str, name: str) -> dict[str, Any]:
        return await self.kubernetes._get_json(
            self.kubernetes._kubectl("get", kind, name, "-o", "json"),
            "policy_unavailable"
            if kind in {"sandboxwarmpool", "sandboxtemplate"}
            else "backend_failed",
        )
