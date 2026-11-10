# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Explicit broker settings; absence of isolation settings is a startup error."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

BackendKind = Literal["docker", "kubernetes", "agent_sandbox"]
IsolationKind = Literal["kata", "gvisor"]
MountKind = Literal["none", "rclone_csi", "rclone_docker"]


@dataclass(frozen=True, slots=True)
class BrokerSettings:
    backend: BackendKind
    isolation: IsolationKind
    runtime_name: str
    image: str
    token: str
    namespace: str = "fred-sandbox"
    agent_pool_name: str = "fred-code"
    network_policy_verified: bool = False
    pid_limit_verified: bool = False
    max_sandboxes: int = 8
    warm_pool_size: int = 0
    cold_start_on_miss: bool = True
    execution_timeout_seconds: int = 15
    output_limit_bytes: int = 8192
    preparation_timeout_seconds: int = 90
    idle_timeout_seconds: int = 1200
    settings_url: str | None = None
    settings_token: str | None = None
    mount_provider: MountKind = "none"
    file_gateway_url: str | None = None
    file_gateway_revoke_url: str | None = None
    file_gateway_secret: str | None = None
    file_storage_class: str | None = None
    docker_volume_plugin: str | None = None
    skills_volume: str | None = None
    coordinator_dsn: str | None = None
    workspace_storage_class: str | None = None
    workspace_size: str = "1Gi"
    active_idle_seconds: int = 120
    max_retained_sessions: int = 1000
    max_preparations: int = 8
    max_queue_length: int = 256
    max_queue_per_tenant: int = 8
    queue_wait_seconds: int = 30

    def __post_init__(self) -> None:
        if self.backend not in {"docker", "kubernetes", "agent_sandbox"}:
            raise ValueError(
                "Sandbox backend must be docker, kubernetes or agent_sandbox"
            )
        if self.isolation not in {"kata", "gvisor"}:
            raise ValueError("Sandbox isolation must be kata or gvisor")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,62}", self.runtime_name):
            raise ValueError("Sandbox runtime name is invalid")
        if not re.fullmatch(r"[^\s]+@sha256:[a-f0-9]{64}", self.image):
            raise ValueError("Sandbox image must be pinned by digest")
        if len(self.token) < 32:
            raise ValueError("Sandbox broker token must have at least 32 characters")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", self.namespace):
            raise ValueError("Sandbox namespace is invalid")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", self.agent_pool_name):
            raise ValueError("Agent Sandbox pool name is invalid")
        if (
            self.backend in {"kubernetes", "agent_sandbox"}
            and not self.network_policy_verified
        ):
            raise ValueError("Kubernetes NetworkPolicy enforcement must be verified")
        if (
            self.backend in {"kubernetes", "agent_sandbox"}
            and not self.pid_limit_verified
        ):
            raise ValueError("Kubernetes pod PID limit must be verified")
        if not 1 <= self.max_sandboxes <= 1000:
            raise ValueError("Sandbox capacity must be 1-1000")
        if self.warm_pool_size != 0 or not self.cold_start_on_miss:
            raise ValueError("Sandboxes must be provisioned on demand")
        if not 1 <= self.execution_timeout_seconds <= 120:
            raise ValueError("Sandbox execution timeout must be 1-120 seconds")
        if not 1024 <= self.output_limit_bytes <= 16_384:
            raise ValueError("Sandbox output limit must be 1024-16384 bytes")
        if not 5 <= self.preparation_timeout_seconds <= 300:
            raise ValueError("Sandbox preparation timeout must be 5-300 seconds")
        if not 60 <= self.idle_timeout_seconds <= 7200:
            raise ValueError("Sandbox idle timeout must be 60-7200 seconds")
        if bool(self.settings_url) != bool(self.settings_token):
            raise ValueError(
                "Sandbox settings URL and token must be configured together"
            )
        if self.settings_url:
            url = urlsplit(self.settings_url)
            if (
                not url.hostname
                or url.scheme not in {"http", "https"}
                or (
                    url.scheme == "http"
                    and url.hostname not in {"localhost", "127.0.0.1", "::1"}
                )
            ):
                raise ValueError("Sandbox settings URL requires HTTPS outside loopback")
            if self.settings_token is None or len(self.settings_token) < 32:
                raise ValueError(
                    "Sandbox settings token must have at least 32 characters"
                )
        if self.mount_provider not in {"none", "rclone_csi", "rclone_docker"}:
            raise ValueError("Sandbox mount provider is invalid")
        if self.mount_provider == "rclone_csi" and self.backend not in {
            "kubernetes",
            "agent_sandbox",
        }:
            raise ValueError("Rclone CSI requires a Kubernetes backend")
        if self.mount_provider == "rclone_docker" and self.backend != "docker":
            raise ValueError("Rclone Docker volume requires the Docker backend")
        if self.mount_provider != "none":
            url = urlsplit(self.file_gateway_url or "")
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or not url.path.endswith("/sandbox-mount")
            ):
                raise ValueError("Sandbox file gateway requires an HTTPS mount URL")
            if self.file_gateway_revoke_url:
                revoke_url = urlsplit(self.file_gateway_revoke_url)
                if (
                    revoke_url.scheme not in {"http", "https"}
                    or not revoke_url.hostname
                    or (
                        revoke_url.scheme == "http"
                        and not revoke_url.hostname.endswith(".svc.cluster.local")
                    )
                    or revoke_url.username
                    or revoke_url.password
                    or revoke_url.query
                    or revoke_url.fragment
                    or not revoke_url.path.endswith("/sandbox-mount")
                ):
                    raise ValueError(
                        "Sandbox file revoke URL must be a trusted mount endpoint"
                    )
            if not self.file_gateway_secret or len(self.file_gateway_secret) < 32:
                raise ValueError(
                    "Sandbox file gateway secret must have at least 32 characters"
                )
            if self.mount_provider == "rclone_csi" and not self.file_storage_class:
                raise ValueError("Sandbox file StorageClass is required")
            if self.mount_provider == "rclone_docker" and not re.fullmatch(
                r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", self.docker_volume_plugin or ""
            ):
                raise ValueError("An approved Docker volume plugin is required")
        elif any(
            (
                self.file_gateway_url,
                self.file_gateway_revoke_url,
                self.file_gateway_secret,
                self.file_storage_class,
                self.docker_volume_plugin,
            )
        ):
            raise ValueError("Sandbox file mount settings require a mount provider")
        if self.skills_volume and not re.fullmatch(
            r"[a-z0-9][a-z0-9.-]{0,62}", self.skills_volume
        ):
            raise ValueError("Sandbox skills volume name is invalid")
        if self.coordinator_dsn:
            if not self.coordinator_dsn.startswith(("postgresql://", "postgres://")):
                raise ValueError("Shared coordinator requires a PostgreSQL DSN")
            if self.backend != "agent_sandbox" or not self.workspace_storage_class:
                raise ValueError(
                    "Shared coordination requires Agent Sandbox and persistent workspace storage"
                )
            if self.active_idle_seconds >= self.idle_timeout_seconds:
                raise ValueError("Active idle period must be shorter than final expiry")
        elif self.workspace_storage_class:
            raise ValueError("Persistent workspace storage requires shared coordination")
        if not 60 <= self.active_idle_seconds <= 3600:
            raise ValueError("Active idle period must be 60-3600 seconds")
        if not 1 <= self.max_retained_sessions <= 100_000:
            raise ValueError("Retained session ceiling must be 1-100000")
        if not 1 <= self.max_preparations <= 1000 or (
            self.coordinator_dsn and self.max_preparations > self.max_sandboxes
        ):
            raise ValueError("Preparation ceiling must fit active capacity")
        if not 1 <= self.max_queue_per_tenant <= self.max_queue_length <= 100_000:
            raise ValueError("Queue limits are invalid")
        if not 1 <= self.queue_wait_seconds <= 120:
            raise ValueError("Queue wait must be 1-120 seconds")
        if not re.fullmatch(r"[1-9][0-9]*(Mi|Gi)", self.workspace_size):
            raise ValueError("Workspace size is invalid")

    @classmethod
    def from_environment(cls) -> BrokerSettings:
        def required(name: str) -> str:
            value = os.getenv(name)
            if not value:
                raise ValueError(f"{name} is required")
            return value

        return cls(
            backend=required("SANDBOX_BACKEND"),  # type: ignore[arg-type]
            isolation=required("SANDBOX_ISOLATION"),  # type: ignore[arg-type]
            runtime_name=required("SANDBOX_RUNTIME_NAME"),
            image=required("SANDBOX_IMAGE"),
            token=required("SANDBOX_BROKER_TOKEN"),
            namespace=os.getenv("SANDBOX_NAMESPACE", "fred-sandbox"),
            agent_pool_name=os.getenv("SANDBOX_AGENT_POOL_NAME", "fred-code"),
            network_policy_verified=os.getenv(
                "SANDBOX_NETWORK_POLICY_VERIFIED", "false"
            ).lower()
            == "true",
            pid_limit_verified=os.getenv("SANDBOX_PID_LIMIT_VERIFIED", "false").lower()
            == "true",
            max_sandboxes=int(os.getenv("SANDBOX_MAX_SANDBOXES", "8")),
            warm_pool_size=int(os.getenv("SANDBOX_WARM_POOL_SIZE", "0")),
            cold_start_on_miss=os.getenv("SANDBOX_COLD_START_ON_MISS", "true").lower()
            == "true",
            execution_timeout_seconds=int(os.getenv("SANDBOX_EXECUTION_TIMEOUT", "15")),
            output_limit_bytes=int(os.getenv("SANDBOX_OUTPUT_LIMIT_BYTES", "8192")),
            preparation_timeout_seconds=int(os.getenv("SANDBOX_PREPARE_TIMEOUT", "90")),
            idle_timeout_seconds=int(os.getenv("SANDBOX_IDLE_TIMEOUT", "1200")),
            settings_url=os.getenv("SANDBOX_SETTINGS_URL") or None,
            settings_token=os.getenv("SANDBOX_SETTINGS_TOKEN") or None,
            mount_provider=os.getenv("SANDBOX_MOUNT_PROVIDER", "none"),  # type: ignore[arg-type]
            file_gateway_url=os.getenv("SANDBOX_FILE_GATEWAY_URL") or None,
            file_gateway_revoke_url=os.getenv("SANDBOX_FILE_GATEWAY_REVOKE_URL")
            or None,
            file_gateway_secret=os.getenv("SANDBOX_FILE_GATEWAY_SECRET") or None,
            file_storage_class=os.getenv("SANDBOX_FILE_STORAGE_CLASS") or None,
            docker_volume_plugin=os.getenv("SANDBOX_DOCKER_VOLUME_PLUGIN") or None,
            skills_volume=os.getenv("SANDBOX_SKILLS_VOLUME") or None,
            coordinator_dsn=os.getenv("SANDBOX_COORDINATOR_DSN") or None,
            workspace_storage_class=os.getenv("SANDBOX_WORKSPACE_STORAGE_CLASS")
            or None,
            workspace_size=os.getenv("SANDBOX_WORKSPACE_SIZE", "1Gi"),
            active_idle_seconds=int(os.getenv("SANDBOX_ACTIVE_IDLE_SECONDS", "120")),
            max_retained_sessions=int(os.getenv("SANDBOX_MAX_RETAINED", "1000")),
            max_preparations=int(os.getenv("SANDBOX_MAX_PREPARATIONS", "8")),
            max_queue_length=int(os.getenv("SANDBOX_MAX_QUEUE", "256")),
            max_queue_per_tenant=int(os.getenv("SANDBOX_MAX_QUEUE_PER_TENANT", "8")),
            queue_wait_seconds=int(os.getenv("SANDBOX_QUEUE_WAIT_SECONDS", "30")),
        )
