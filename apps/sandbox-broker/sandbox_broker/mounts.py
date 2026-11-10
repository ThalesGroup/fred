# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Operator-approved, per-workload read-only mount credentials and claims."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any
from uuid import uuid4

import httpx
from fred_sdk.contracts.sandbox import SandboxError

from .command import CommandRunner
from .config import BrokerSettings

_VIEW_KEY = re.compile(r"[a-f0-9]{64}\Z")


def view_key_for_mount(key: str | None) -> str:
    if key is None:
        return uuid4().hex + uuid4().hex
    if not _VIEW_KEY.fullmatch(key):
        raise SandboxError("invalid_request")
    return key


def mount_bearer(secret: str, key: str) -> str:
    return hmac.new(
        secret.encode(), b"fred-sandbox-files-v1\0" + key.encode(), hashlib.sha256
    ).hexdigest()


async def revoke_view(settings: BrokerSettings, key: str) -> None:
    if not settings.file_gateway_url or not settings.file_gateway_secret:
        raise SandboxError("policy_unavailable")
    token = hmac.new(
        settings.file_gateway_secret.encode(),
        b"fred-sandbox-files-revoke-v1\0" + key.encode(),
        hashlib.sha256,
    ).hexdigest()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.delete(
                f"{(settings.file_gateway_revoke_url or settings.file_gateway_url).rstrip('/')}/views/{key}",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SandboxError("backend_failed") from exc


class RcloneCsiMount:
    def __init__(self, settings: BrokerSettings, runner: CommandRunner) -> None:
        self.settings = settings
        self.runner = runner

    def _kubectl(self, *args: str) -> list[str]:
        return ["kubectl", "--namespace", self.settings.namespace, *args]

    async def preflight(self) -> None:
        result = await self.runner.run(
            [
                "kubectl",
                "get",
                "storageclass",
                self.settings.file_storage_class or "",
                "-o",
                "json",
            ],
            timeout=10,
        )
        if result.returncode != 0:
            raise SandboxError("policy_unavailable")
        try:
            storage_class = json.loads(result.stdout)
        except ValueError as exc:
            raise SandboxError("policy_unavailable") from exc
        parameters = storage_class.get("parameters", {})
        expected_parameters = {
            "remotePath": "/",
            "csi.storage.k8s.io/node-publish-secret-name": "${pvc.name}",
            "csi.storage.k8s.io/node-publish-secret-namespace": self.settings.namespace,
        }
        if (
            storage_class.get("provisioner") != "rclone.csi.veloxpack.io"
            or parameters != expected_parameters
            or storage_class.get("mountOptions", [])
            != ["dir-cache-time=1s", "vfs-cache-mode=off"]
            or storage_class.get("reclaimPolicy", "Delete") != "Delete"
        ):
            raise SandboxError("policy_unavailable")

    async def create_secret(self, workload_name: str, key: str) -> None:
        settings = self.settings
        if not settings.file_gateway_url or not settings.file_gateway_secret:
            raise SandboxError("policy_unavailable")
        url = f"{settings.file_gateway_url.rstrip('/')}/{key}"
        bearer = mount_bearer(settings.file_gateway_secret, key)
        name = f"inputs-{workload_name}"
        config_data = (
            f"[{name}]\n"
            "type = webdav\n"
            f"url = {url}\n"
            "vendor = other\n"
            f"bearer_token = {bearer}\n"
        )
        manifest: dict[str, Any] = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": name,
                "namespace": settings.namespace,
                "labels": {"app.kubernetes.io/name": "fred-sandbox-inputs"},
            },
            "type": "Opaque",
            "stringData": {
                "remote": name,
                "remotePath": "/",
                "configData": config_data,
            },
        }
        result = await self.runner.run(
            self._kubectl("create", "-f", "-"),
            timeout=15,
            input_data=json.dumps(manifest).encode(),
        )
        if result.returncode != 0:
            raise SandboxError("backend_failed")

    def claim_template(self) -> dict[str, Any]:
        return {
            "metadata": {"name": "inputs"},
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "storageClassName": self.settings.file_storage_class,
                "resources": {"requests": {"storage": "1Gi"}},
            },
        }

    async def create_pvc(self, workload_name: str) -> None:
        manifest = {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": f"inputs-{workload_name}",
                "namespace": self.settings.namespace,
                "labels": {"app.kubernetes.io/name": "fred-sandbox-inputs"},
            },
            "spec": self.claim_template()["spec"],
        }
        result = await self.runner.run(
            self._kubectl("create", "-f", "-"),
            timeout=15,
            input_data=json.dumps(manifest).encode(),
        )
        if result.returncode != 0:
            raise SandboxError("backend_failed")

    async def attach_owner(self, workload_name: str, kind: str, *, pvc: bool) -> None:
        owner = await self.runner.run(
            self._kubectl("get", kind, workload_name, "-o", "json"), timeout=10
        )
        if owner.returncode != 0:
            raise SandboxError("backend_failed")
        try:
            uid = json.loads(owner.stdout)["metadata"]["uid"]
        except (ValueError, KeyError, TypeError) as exc:
            raise SandboxError("backend_failed") from exc
        if not isinstance(uid, str) or not uid:
            raise SandboxError("backend_failed")
        reference = {
            "apiVersion": "batch/v1"
            if kind == "job"
            else "extensions.agents.x-k8s.io/v1beta1",
            "kind": "Job" if kind == "job" else "SandboxClaim",
            "name": workload_name,
            "uid": uid,
        }
        for resource in ["secret", "pvc"] if pvc else ["secret"]:
            result = await self.runner.run(
                self._kubectl(
                    "patch",
                    resource,
                    f"inputs-{workload_name}",
                    "--type=merge",
                    "-p",
                    json.dumps({"metadata": {"ownerReferences": [reference]}}),
                ),
                timeout=10,
            )
            if result.returncode != 0:
                raise SandboxError("backend_failed")

    async def clean_orphans(self) -> None:
        result = await self.runner.run(
            self._kubectl(
                "delete",
                "pvc,secret",
                "-l",
                "app.kubernetes.io/name=fred-sandbox-inputs",
                "--ignore-not-found=true",
                "--wait=true",
            ),
            timeout=90,
        )
        if result.returncode != 0:
            raise SandboxError("backend_failed")

    async def delete(self, workload_name: str) -> None:
        result = await self.runner.run(
            self._kubectl(
                "delete",
                "pvc,secret",
                f"inputs-{workload_name}",
                "--ignore-not-found=true",
                "--wait=true",
            ),
            timeout=90,
        )
        if result.returncode != 0:
            raise SandboxError("backend_failed")
