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
        )
