# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""SIG Agent Sandbox claim lifecycle with Fred admission and exec transport."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fred_sdk.contracts.sandbox import SandboxError, SandboxRequest, SandboxResult

from .backend import SandboxLease, SandboxPrepareLeak
from .command import CommandRunner
from .config import BrokerSettings
from .kubernetes_backend import KubernetesBackend
from .mounts import view_key_for_mount


class AgentSandboxBackend:
    def __init__(self, settings: BrokerSettings, runner: CommandRunner) -> None:
        self.settings = settings
        self.runner = runner
        self.kubernetes = KubernetesBackend(settings, runner)

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
        pool_status = pool.get("status", {})
        generation = pool.get("metadata", {}).get("generation", 1)
        observed = pool_status.get("observedGeneration", 0)
        if (
            not isinstance(target, int)
            or target != 0
            or any(
                not isinstance(pool_status.get(field, 0), int)
                or pool_status.get(field, 0) != 0
                for field in ("replicas", "readyReplicas", "availableReplicas")
            )
            or not isinstance(generation, int)
            or not isinstance(observed, int)
            or observed < generation
        ):
            raise SandboxError("policy_unavailable")
        template = await self._get("sandboxtemplate", template_name)
        spec = template.get("spec", {})
        pod = spec.get("podTemplate", {}).get("spec", {})
        if spec.get(
            "networkPolicyManagement"
        ) != "Unmanaged" or not self._is_safe_pod_spec(pod):
            raise SandboxError("policy_unavailable")
        if self.kubernetes.mount is not None:
            if spec.get("volumeClaimTemplatesPolicy") != "Allowed" or spec.get(
                "volumeClaimTemplates"
            ):
                raise SandboxError("policy_unavailable")

    def _is_safe_pod_spec(self, pod: Any, *, workload_name: str | None = None) -> bool:
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
            and container.get("workingDir") == "/work"
            and container.get("env")
            == [
                {"name": "HOME", "value": "/work"},
                {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
            ]
            and not container.get("envFrom")
            and container.get("volumeMounts")
            == (
                [
                    {"name": "scratch", "mountPath": "/tmp"},
                    {"name": "scratch", "mountPath": "/work"},
                ]
                + (
                    [{"name": "inputs", "mountPath": "/inputs", "readOnly": True}]
                    if self.kubernetes.mount
                    else []
                )
                + (
                    [{"name": "skills", "mountPath": "/skills", "readOnly": True}]
                    if self.settings.skills_volume
                    else []
                )
            )
            and security.get("allowPrivilegeEscalation") is False
            and security.get("readOnlyRootFilesystem") is True
            and security.get("capabilities", {}).get("drop") == ["ALL"]
            and security.get("privileged") is not True
            and container.get("resources", {}).get("limits", {}).get("memory")
            == "256Mi"
            and container.get("resources", {}).get("limits", {}).get("cpu") == "500m"
            and pod.get("volumes")
            == (
                [{"name": "scratch", "emptyDir": {"sizeLimit": "16Mi"}}]
                + (
                    [
                        {
                            "name": "inputs",
                            "persistentVolumeClaim": {
                                "claimName": f"inputs-{workload_name}",
                            },
                        }
                    ]
                    if self.kubernetes.mount and workload_name
                    else []
                )
                + (
                    [
                        {
                            "name": "skills",
                            "persistentVolumeClaim": {
                                "claimName": self.settings.skills_volume,
                                "readOnly": True,
                            },
                        }
                    ]
                    if self.settings.skills_volume
                    else []
                )
            )
        )

    async def prepare(self, view_key: str | None = None) -> SandboxLease:
        return await self._prepare_claim(view_key)

    async def _prepare_claim(self, view_key: str | None) -> SandboxLease:
        await self.preflight()
        name = f"fred-sbx-{uuid4().hex[:20]}"
        mount = self.kubernetes.mount
        mounted_key = view_key_for_mount(view_key) if mount else None
        lease = SandboxLease(id=name, target=name, view_key=mounted_key)
        expiry = datetime.now(timezone.utc) + timedelta(
            seconds=self.settings.preparation_timeout_seconds
            + self.settings.execution_timeout_seconds
            + self.settings.idle_timeout_seconds
        )
        manifest: dict[str, Any] = {
            "apiVersion": "extensions.agents.x-k8s.io/v1beta1",
            "kind": "SandboxClaim",
            "metadata": {
                "name": name,
                "namespace": self.settings.namespace,
                "labels": {"app.kubernetes.io/name": "fred-sandbox"},
            },
            "spec": {
                "warmPoolRef": {"name": self.settings.agent_pool_name},
                "lifecycle": {
                    "shutdownTime": expiry.isoformat().replace("+00:00", "Z"),
                    "shutdownPolicy": "DeleteForeground",
                },
            },
        }
        if mount is not None:
            manifest["spec"]["volumeClaimTemplates"] = [mount.claim_template()]
        try:
            if mount is not None and mounted_key is not None:
                await mount.create_secret(name, mounted_key)
            result = await self.runner.run(
                self.kubernetes._kubectl("create", "-f", "-"),
                timeout=15,
                input_data=json.dumps(manifest).encode(),
            )
            if result.returncode != 0:
                raise SandboxError("backend_failed")
            if mount is not None:
                await mount.attach_owner(name, "sandboxclaim", pvc=False)
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
                not self._is_safe_pod_spec(pod.get("spec"), workload_name=name)
                or pod.get("metadata", {}).get("ownerReferences", [{}])[0].get("name")
                != pod_name
            ):
                raise SandboxError("policy_unavailable")
            return SandboxLease(id=name, target=pod_name, view_key=mounted_key)
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
        if self.kubernetes.mount is not None:
            await self.kubernetes.mount.delete(lease.id)

    async def recover(self) -> None:
        result = await self.runner.run(
            self.kubernetes._kubectl(
                "delete",
                "sandboxclaim",
                "-l",
                "app.kubernetes.io/name=fred-sandbox",
                "--ignore-not-found=true",
                "--cascade=foreground",
                "--wait=true",
            ),
            timeout=90,
        )
        if result.returncode != 0:
            raise SandboxError("backend_failed")
        if self.kubernetes.mount is not None:
            await self.kubernetes.mount.clean_orphans()

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
