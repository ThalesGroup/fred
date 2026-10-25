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
from .kubernetes_backend import KubernetesBackend, has_controller_owner
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
        ) != "Unmanaged" or not self.kubernetes.is_safe_pod_spec(pod, sig_claim=True):
            raise SandboxError("policy_unavailable")
        if self.kubernetes.mount is not None or self.settings.coordinator_dsn:
            if spec.get("volumeClaimTemplatesPolicy") != "Allowed" or spec.get(
                "volumeClaimTemplates"
            ):
                raise SandboxError("policy_unavailable")
        if self.settings.workspace_storage_class:
            await self.kubernetes._get_json(
                [
                    "kubectl",
                    "get",
                    "storageclass",
                    self.settings.workspace_storage_class,
                    "-o",
                    "json",
                ],
                "policy_unavailable",
            )

    async def prepare(
        self, view_key: str | None = None, *, name: str | None = None
    ) -> SandboxLease:
        await self.preflight()
        name = name or f"fred-sbx-{uuid4().hex[:20]}"
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
        templates = []
        if mount is not None:
            templates.append(mount.claim_template())
        if self.settings.workspace_storage_class:
            templates.append(
                {
                    "metadata": {"name": "workspace"},
                    "spec": {
                        "accessModes": ["ReadWriteOnce"],
                        "storageClassName": self.settings.workspace_storage_class,
                        "resources": {
                            "requests": {"storage": self.settings.workspace_size}
                        },
                    },
                }
            )
        if templates:
            manifest["spec"]["volumeClaimTemplates"] = templates
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
            return await self.attach(name, mounted_key)
        except BaseException:
            try:
                await self.dispose(lease)
            except Exception as exc:
                raise SandboxPrepareLeak(lease) from exc
            raise

    async def attach(self, name: str, view_key: str | None) -> SandboxLease:
        claim = await self._get("sandboxclaim", name)
        pod_name = claim.get("status", {}).get("sandbox", {}).get("name")
        # Mount Secret names are fixed before the claim is ready.
        if not isinstance(pod_name, str) or pod_name != name:
            raise SandboxError("backend_failed")
        sandbox = await self._get("sandbox", pod_name)
        sandbox_uid = sandbox.get("metadata", {}).get("uid")
        claim_uid = claim.get("metadata", {}).get("uid")
        pod = await self._get("pod", pod_name)
        if (
            not isinstance(sandbox_uid, str)
            or not isinstance(claim_uid, str)
            or not has_controller_owner(
                sandbox.get("metadata", {}),
                kind="SandboxClaim",
                name=name,
                uid=claim_uid,
            )
            or not has_controller_owner(
                pod.get("metadata", {}),
                kind="Sandbox",
                name=pod_name,
                uid=sandbox_uid,
            )
            or not self.kubernetes.is_safe_pod_spec(
                pod.get("spec"), workload_name=pod_name, sig_claim=True
            )
        ):
            raise SandboxError("policy_unavailable")
        if self.settings.workspace_storage_class:
            expected = {
                "accessModes": ["ReadWriteOnce"],
                "storageClassName": self.settings.workspace_storage_class,
                "resources": {"requests": {"storage": self.settings.workspace_size}},
            }
            templates = claim.get("spec", {}).get("volumeClaimTemplates", [])
            workspace = next(
                (
                    item
                    for item in templates
                    if item.get("metadata", {}).get("name") == "workspace"
                ),
                None,
            )
            if not isinstance(workspace, dict) or workspace.get("spec") != expected:
                raise SandboxError("policy_unavailable")
            pvc = await self._get("pvc", f"workspace-{pod_name}")
            if (
                pvc.get("status", {}).get("phase") != "Bound"
                or pvc.get("spec", {}).get("storageClassName")
                != self.settings.workspace_storage_class
                or not has_controller_owner(
                    pvc.get("metadata", {}),
                    kind="Sandbox",
                    name=pod_name,
                    uid=sandbox_uid,
                )
            ):
                raise SandboxError("policy_unavailable")
        return SandboxLease(id=name, target=pod_name, view_key=view_key)

    async def suspend(self, name: str) -> None:
        claim = await self._get("sandboxclaim", name)
        sandbox_name = claim.get("status", {}).get("sandbox", {}).get("name")
        if not isinstance(sandbox_name, str) or not sandbox_name:
            raise SandboxError("backend_failed")
        await self._set_mode(sandbox_name, "Suspended")
        await self._wait_sandbox(sandbox_name, "Suspended")

    async def resume(self, name: str, view_key: str | None) -> SandboxLease:
        claim = await self._get("sandboxclaim", name)
        sandbox_name = claim.get("status", {}).get("sandbox", {}).get("name")
        if not isinstance(sandbox_name, str) or not sandbox_name:
            raise SandboxError("backend_failed")
        await self._set_mode(sandbox_name, "Running")
        await self._wait_sandbox(sandbox_name, "Ready")
        return await self.attach(name, view_key)

    async def _set_mode(self, name: str, mode: str) -> None:
        result = await self.runner.run(
            self.kubernetes._kubectl(
                "patch",
                "sandbox",
                name,
                "--type=merge",
                "-p",
                json.dumps({"spec": {"operatingMode": mode}}),
            ),
            timeout=15,
        )
        if result.returncode != 0:
            raise SandboxError("backend_failed")

    async def _wait_sandbox(self, name: str, condition: str) -> None:
        result = await self.runner.run(
            self.kubernetes._kubectl(
                "wait",
                "sandbox",
                name,
                f"--for=condition={condition}",
                f"--timeout={self.settings.preparation_timeout_seconds}s",
            ),
            timeout=self.settings.preparation_timeout_seconds + 5,
        )
        if result.returncode != 0:
            raise SandboxError("backend_failed")

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
