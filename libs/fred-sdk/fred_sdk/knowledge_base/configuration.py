# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
What a Knowledge Base pod is configured with.

Configured the way every other Fred component is, and deliberately not in a
style of its own: one `configuration.yaml` resolved from `$CONFIG_FILE`, the
models fred-core already owns, the same keys under `security.m2m` and
`scheduler.temporal`, and environment variables carrying secrets only.

A contributor writing a Knowledge Base is already writing Fred. Making them
learn a second configuration model costs more than the few lines of plumbing a
shared one asks for — and a non-secret value hidden in an environment variable
is a value nobody reviews in the ConfigMap beside the rest.
"""

from __future__ import annotations

import logging

from fred_pod.common import (
    ConfigFiles,
    TemporalSchedulerConfig,
    load_configuration_with_config_files,
    parse_yaml_mapping_file,
)
from fred_pod.security.backend_to_backend_auth import M2MAuthConfig
from fred_pod.security.structure import M2MSecurity
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

_CONFIG_FILES = ConfigFiles(logger=logger, log_prefix="[CONFIG][KB]")


class MissingPodConfiguration(RuntimeError):
    """Raised when a pod starts with no configuration file to read.

    Distinct from an *invalid* one: a file that is present and wrong stops the
    process with a rendered banner, because there is nothing sensible to do
    with it. A file that is absent is a legitimate state for a developer tool
    running with no Fred at all, so it is an exception a caller may catch.
    """


class KnowledgeBaseSettings(BaseModel):
    """Where this pod publishes, and what it is allowed to publish under.

    `prefix` is the dotted prefix this image owns — `fred.samples`. Every name
    it publishes lives under it, Fred binds the prefix to this pod's client on
    the first publication, and no other client may write there afterwards.
    """

    prefix: str = Field(min_length=1)
    control_plane_url: str = Field(min_length=1)
    # Optional: only a pod that ingests through Knowledge Flow needs it. One
    # that keeps its own store leaves it out — the service is an offer, not a
    # contract.
    knowledge_flow_url: str = ""

    @field_validator("control_plane_url", "knowledge_flow_url")
    @classmethod
    def _without_trailing_slash(cls, value: str) -> str:
        # A trailing slash doubles every path built from these, and an operator
        # copying a base URL out of a browser leaves one more often than not.
        return value.rstrip("/")


class PodSecurity(BaseModel):
    """The machine half of `security`, and only that half.

    The key path is the one every Fred backend uses, and `M2MSecurity` is the
    same model they parse it with. What is absent is `security.user`: a
    Knowledge Base pod serves no user, opens no inbound port and validates no
    user token, so requiring a block it would never read would be configuration
    theatre.
    """

    m2m: M2MSecurity


class PodScheduler(BaseModel):
    """Where Temporal is, in the shape the Control Plane already reads it.

    `TemporalSchedulerConfig` is the model the dispatching side parses for
    Knowledge Bases too, so both halves of the contract describe Temporal
    identically.

    `scheduler.temporal.task_queue` is ignored on purpose: a run's queue is
    derived from the definition id by `routing.task_queue_for`, identically on
    both sides, so that a pod and a Control Plane cannot disagree about it.
    Configuring it would be the bug — two sides disagreeing would lose every
    run in silence.
    """

    temporal: TemporalSchedulerConfig = Field(default_factory=TemporalSchedulerConfig)


class PodConfiguration(BaseModel):
    """Everything a Knowledge Base pod needs to reach Fred and Temporal."""

    knowledge_base: KnowledgeBaseSettings
    security: PodSecurity
    scheduler: PodScheduler = Field(default_factory=PodScheduler)

    # ── the values the rest of the SDK reads ──────────────────────────────────

    @property
    def prefix(self) -> str:
        return self.knowledge_base.prefix

    @property
    def control_plane_url(self) -> str:
        return self.knowledge_base.control_plane_url

    @property
    def knowledge_flow_url(self) -> str:
        return self.knowledge_base.knowledge_flow_url

    @property
    def temporal_host(self) -> str:
        return self.scheduler.temporal.host

    @property
    def temporal_namespace(self) -> str:
        return self.scheduler.temporal.namespace

    @property
    def m2m(self) -> M2MAuthConfig:
        """How this pod authenticates, built once rather than at each call site.

        The secret is named, never carried: `secret_env_var` says which
        environment variable holds it, and the token provider reads that
        variable itself. Nothing here ever holds the value.
        """
        return M2MAuthConfig(
            keycloak_realm_url=str(self.security.m2m.realm_url).rstrip("/"),
            client_id=self.security.m2m.client_id,
            secret_env=self.security.m2m.secret_env_var,
        )

    # ── loading ───────────────────────────────────────────────────────────────

    @classmethod
    def load(cls) -> "PodConfiguration":
        """Read `$CONFIG_FILE`, the way every Fred component reads its own.

        `$ENV_FILE` is loaded first, so a local run picks up the secret the
        configuration names without it ever being written into the YAML.
        """
        try:
            return load_configuration_with_config_files(
                _CONFIG_FILES,
                lambda path: cls.model_validate(parse_yaml_mapping_file(path)),
            )
        except FileNotFoundError as error:
            # Absent, not invalid. The environment file is loaded first, so
            # $CONFIG_FILE may itself have come from it — which is why this is
            # decided here rather than before the load.
            raise MissingPodConfiguration(
                f"No Knowledge Base configuration: {error}. Set $CONFIG_FILE, "
                "or put one at ./config/configuration.yaml."
            ) from error
