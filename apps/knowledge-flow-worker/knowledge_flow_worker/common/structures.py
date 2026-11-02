# Copyright Thales 2025
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


import re
from enum import Enum
from typing import List, Literal, Optional

from fred_core import LogStorageConfig
from fred_core.common import KpiObservabilityConfig, ModelConfiguration, OpenSearchStoreConfig, PostgresStoreConfig, TemporalSchedulerConfig
from fred_core.documents.processing_profile import IngestionProcessingProfile as IngestionProcessingProfile
from fred_knowledge.configuration import ArtifactStorageConfig, TabularStoreConfig, TextSplitterConfig, VectorStorageConfig
from fred_knowledge.configuration import OpenSearchVectorIndexConfig as OpenSearchVectorIndexConfig
from fred_knowledge.configuration import PgVectorStorageConfig as PgVectorStorageConfig
from fred_knowledge.configuration import TabularQueryConfig as TabularQueryConfig
from fred_pod.common.structures import LogOutputFormat
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

"""
This module defines the top level data structures used by controllers, processors
unit tests. It helps to decouple the different components of the application and allows
to define clear workflows and data structures.
"""


class IngestionWorkerRole(str, Enum):
    """What one knowledge-flow worker process is there to do.

    `common` runs every ingestion workflow plus every activity but extraction.
    The three extraction roles run nothing but the two extraction activities,
    each on its own queue, so a slow profile cannot hold the activity slots the
    others need.
    """

    common = "common"
    extraction_fast = "extraction-fast"
    extraction_medium = "extraction-medium"
    extraction_rich = "extraction-rich"

    @property
    def extraction_profile(self) -> Optional[IngestionProcessingProfile]:
        """The profile this role extracts for, or None for the common role."""
        if self is IngestionWorkerRole.common:
            return None
        return IngestionProcessingProfile(self.value.removeprefix("extraction-"))


def extraction_task_queue(base_task_queue: str, profile: IngestionProcessingProfile) -> str:
    """Name the Temporal queue carrying one profile's extraction activities.

    The single source of truth for profile → queue: the side that submits derives
    it per document, the worker derives it from its own role. Two sides spelling a
    queue name by hand lose every submission in silence.
    """
    return f"{base_task_queue}-{IngestionProcessingProfile(profile).value}"


_DURATION_PATTERN = re.compile(r"^(?P<value>\d+)\s*(?P<unit>[smhd]?)$")
_DURATION_MULTIPLIER_SECONDS = {
    "": 1,
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}


def parse_duration_seconds(value: object, *, field_name: str) -> int:
    """
    Parse duration values expressed as:
      - integer seconds (e.g. 3600)
      - compact strings (e.g. "45s", "10m", "1h", "2d")
    """
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive duration, got {value!r}")

    if isinstance(value, (int, float)):
        seconds = int(value)
        if seconds <= 0:
            raise ValueError(f"{field_name} must be > 0 seconds")
        return seconds

    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be an integer seconds value or a compact duration string like '1h'",
        )

    token = value.strip().lower()
    match = _DURATION_PATTERN.fullmatch(token)
    if not match:
        raise ValueError(
            f"{field_name}='{value}' is invalid. Use formats like '45s', '10m', '1h', '2d' or integer seconds.",
        )

    amount = int(match.group("value"))
    unit = match.group("unit")
    seconds = amount * _DURATION_MULTIPLIER_SECONDS[unit]
    if seconds <= 0:
        raise ValueError(f"{field_name} must be > 0 seconds")
    return seconds


class ProcessorConfig(BaseModel):
    """
    Configuration structure for a file processor.
    Attributes:
        suffix (str): The file extension this processor handles (e.g., '.pdf').
        class_path (str): Dotted import path of the processor class.
        description (str): Human readable explanation of what the processor does.
    """

    suffix: str = Field(..., description="The file extension this processor handles (e.g., '.pdf')")
    class_path: str = Field(..., description="Dotted import path of the processor class")
    description: Optional[str] = Field(
        default=None,
        min_length=1,
        description="Human-readable description of the processor purpose shown in the UI.",
    )


###########################################################
#
#  --- Vector storage configuration
#


class ManagerProcessingConfig(ArtifactStorageConfig):
    """Workload identity and persistence for manager-owned documents."""

    model_config = ConfigDict(extra="forbid")
    url: str
    issuer: str
    audience: str = "control-plane"
    client_id: str = "knowledge-flow-worker"
    client_secret_env: str = "MANAGER_WORKER_CLIENT_SECRET"
    access_key_env: str = "MANAGER_DERIVED_ACCESS_KEY"
    secret_key_env: str = "MANAGER_DERIVED_SECRET_KEY"
    vector_store: VectorStorageConfig
    temporary_bytes: int = Field(default=1_073_741_824, ge=1_048_576, le=21_474_836_480, description="Per-activity original plus output byte budget; size the worker volume for concurrent activities.")

    @model_validator(mode="after")
    def validate_transport(self):
        for url in (self.url, self.issuer):
            if not url.startswith("https://") and not (self.allow_insecure and url.startswith("http://")):
                raise ValueError("manager processing endpoints require HTTPS")
        return self


class ProcessingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class PdfPipelineConfig(BaseModel):
        model_config = ConfigDict(extra="forbid")

        extractor: Literal["docling", "pymupdf"] = Field(
            default="docling",
            description="PDF text extractor engine: 'docling' for layout-aware extraction, 'pymupdf' for fast page-oriented extraction.",
        )
        do_ocr: bool = Field(
            default=False,
            description="Enable PaddleOCR post-processing on extracted images when using the docling extractor.",
        )
        docling_num_threads: int = Field(
            default=4,
            ge=1,
            description="OMP/accelerator threads docling uses per PDF extraction. Tune down when "
            "scheduler.temporal.ingestion_max_concurrent_activities x this value exceeds the "
            "CPU cores available to the worker (host or pod), or extractions will thrash instead of progressing.",
        )

    class ProfileInputProcessorConfig(BaseModel):
        model_config = ConfigDict(extra="forbid")

        suffix: str = Field(..., description="The file suffix this processor handles (e.g., '.pdf').")
        class_path: str = Field(..., description="Dotted import path of the processor class.")
        description: Optional[str] = Field(
            default=None,
            min_length=1,
            description="Human-readable description of the processor purpose shown in the UI.",
        )

    class ProfileConfig(BaseModel):
        model_config = ConfigDict(extra="forbid")

        use_gpu: bool = Field(
            default=True,
            description="Enable/disable GPU usage for this profile (if supported by the selected processors).",
        )
        process_images: bool = Field(
            default=False,
            description="Enable/disable semantic image description in markdown for this profile.",
        )
        generate_summary: bool = Field(
            default=False,
            description="Enable/disable human-centric abstract and keyword generation for this profile.",
        )
        input_activity_timeout: str = Field(
            default="1h",
            description="Temporal start-to-close timeout for input processing activities (e.g., '1h', '45m').",
        )
        push_metadata_activity_timeout: str = Field(default="5m", description="Per-attempt timeout for uploaded-file metadata lookup; excludes queue wait.")
        output_activity_timeout: str = Field(default="1h", description="Per-attempt timeout for indexing; excludes queue wait.")

        activity_heartbeat_timeout: str = Field(
            default="5m",
            description="Temporal heartbeat timeout for extraction and indexing activities (e.g., '5m', '10m'). Must be larger than the worker's heartbeat interval (~5s).",
        )
        pdf: "ProcessingConfig.PdfPipelineConfig" = Field(
            default_factory=lambda: ProcessingConfig.PdfPipelineConfig(),
            description="PDF processing options for this profile.",
        )
        text_splitter: "TextSplitterConfig" = Field(
            default_factory=lambda: TextSplitterConfig(),
            description="Text splitter configuration for vectorization and summarization.",
        )
        input_processors: List["ProcessingConfig.ProfileInputProcessorConfig"] = Field(
            default_factory=list,
            description="Input processors selected for this profile (suffix-specific).",
        )
        retry_initial_interval: str = Field(
            default="30s",
            description="Temporal retry delay before the first retry for this profile's ingestion activities.",
        )
        retry_backoff_coefficient: float = Field(
            default=2.0,
            ge=1.0,
            description="Temporal retry backoff coefficient for this profile's ingestion activities.",
        )
        retry_maximum_interval: str = Field(
            default="10m",
            description="Maximum Temporal retry delay for this profile's ingestion activities.",
        )
        retry_maximum_attempts: int = Field(
            default=6,
            ge=1,
            description="Maximum Temporal activity attempts for this profile, including the first attempt.",
        )
        retry_non_retryable_error_types: List[str] = Field(
            default_factory=list,
            description="Temporal application error types that should fail fast for this profile without retry.",
        )

        @field_validator("push_metadata_activity_timeout", "output_activity_timeout", mode="before")
        @classmethod
        def _normalize_stage_timeout(cls, value: object) -> str:
            seconds = parse_duration_seconds(value, field_name="processing.profiles.*.stage_activity_timeout")
            return f"{seconds}s"

        @property
        def retry_initial_interval_seconds(self) -> int:
            return parse_duration_seconds(self.retry_initial_interval, field_name="processing.profiles.*.retry_initial_interval")

        @property
        def retry_maximum_interval_seconds(self) -> int:
            return parse_duration_seconds(self.retry_maximum_interval, field_name="processing.profiles.*.retry_maximum_interval")

        @field_validator("input_activity_timeout", mode="before")
        @classmethod
        def _normalize_input_activity_timeout(cls, value: object) -> str:
            if value is None:
                return "1h"
            if isinstance(value, (int, float)):
                seconds = parse_duration_seconds(
                    value,
                    field_name="processing.profiles.*.input_activity_timeout",
                )
                return f"{seconds}s"

            normalized = str(value).strip().lower()
            parse_duration_seconds(
                normalized,
                field_name="processing.profiles.*.input_activity_timeout",
            )
            return normalized

        @property
        def input_activity_timeout_seconds(self) -> int:
            return parse_duration_seconds(
                self.input_activity_timeout,
                field_name="processing.profiles.*.input_activity_timeout",
            )

        @field_validator("activity_heartbeat_timeout", mode="before")
        @classmethod
        def _normalize_activity_heartbeat_timeout(cls, value: object) -> str:
            if value is None:
                return "5m"
            if isinstance(value, (int, float)):
                seconds = parse_duration_seconds(
                    value,
                    field_name="processing.profiles.*.activity_heartbeat_timeout",
                )
                return f"{seconds}s"

            normalized = str(value).strip().lower()
            parse_duration_seconds(
                normalized,
                field_name="processing.profiles.*.activity_heartbeat_timeout",
            )
            return normalized

        @property
        def activity_heartbeat_timeout_seconds(self) -> int:
            return parse_duration_seconds(
                self.activity_heartbeat_timeout,
                field_name="processing.profiles.*.activity_heartbeat_timeout",
            )

        @field_validator("retry_initial_interval", mode="before")
        @classmethod
        def _normalize_retry_initial_interval(cls, value: object) -> str:
            if value is None:
                return "30s"
            if isinstance(value, (int, float)):
                seconds = parse_duration_seconds(
                    value,
                    field_name="processing.profiles.*.retry_initial_interval",
                )
                return f"{seconds}s"

            normalized = str(value).strip().lower()
            parse_duration_seconds(
                normalized,
                field_name="processing.profiles.*.retry_initial_interval",
            )
            return normalized

        @field_validator("retry_maximum_interval", mode="before")
        @classmethod
        def _normalize_retry_maximum_interval(cls, value: object) -> str:
            if value is None:
                return "10m"
            if isinstance(value, (int, float)):
                seconds = parse_duration_seconds(
                    value,
                    field_name="processing.profiles.*.retry_maximum_interval",
                )
                return f"{seconds}s"

            normalized = str(value).strip().lower()
            parse_duration_seconds(
                normalized,
                field_name="processing.profiles.*.retry_maximum_interval",
            )
            return normalized

        @model_validator(mode="after")
        def validate_retry_intervals(self) -> "ProcessingConfig.ProfileConfig":
            """
            Keep per-profile Temporal retry intervals coherent.

            Why:
            - A retry cap smaller than the initial retry delay is almost always a
              configuration mistake for one processing profile.

            How to use:
            - Keep `retry_maximum_interval` greater than or equal to
              `retry_initial_interval`.
            """
            if self.retry_maximum_interval_seconds < self.retry_initial_interval_seconds:
                raise ValueError("processing.profiles.*.retry_maximum_interval must be >= retry_initial_interval")
            return self

    class ProfilesConfig(BaseModel):
        model_config = ConfigDict(extra="forbid")

        fast: "ProcessingConfig.ProfileConfig" = Field(default_factory=lambda: ProcessingConfig.ProfileConfig())
        medium: "ProcessingConfig.ProfileConfig" = Field(default_factory=lambda: ProcessingConfig.ProfileConfig())
        rich: "ProcessingConfig.ProfileConfig" = Field(default_factory=lambda: ProcessingConfig.ProfileConfig())

    path_base_model: str = Field(
        default=".",
        description="Base directory prepended to the 'models/' subfolder when loading or downloading ML models. Defaults to '.' (current working directory).",
    )
    default_profile: IngestionProcessingProfile = Field(
        default=IngestionProcessingProfile.medium,
        description="Default ingestion processing profile when no request-level profile is provided.",
    )
    profiles: ProfilesConfig = Field(
        default_factory=ProfilesConfig,
        description="Named ingestion profiles for request-level pipeline/option selection.",
    )

    def normalize_profile(self, profile: IngestionProcessingProfile | str | None) -> IngestionProcessingProfile:
        if profile is None:
            return self.default_profile
        # IngestionProcessingProfile is itself a str subclass, so this also covers
        # (and is idempotent for) an already-valid enum member.
        return IngestionProcessingProfile(profile)

    def get_profile_config(self, profile: IngestionProcessingProfile | str | None) -> "ProcessingConfig.ProfileConfig":
        profile = self.normalize_profile(profile)

        if profile == IngestionProcessingProfile.fast:
            return self.profiles.fast
        if profile == IngestionProcessingProfile.rich:
            return self.profiles.rich
        return self.profiles.medium

    def is_gpu_enabled_any_profile(self) -> bool:
        return any(self.get_profile_config(profile).use_gpu for profile in IngestionProcessingProfile)


class SchedulerConfig(BaseModel):
    enabled: bool = False
    backend: Literal["temporal"] = "temporal"
    temporal: TemporalSchedulerConfig
    worker_roles: List[IngestionWorkerRole] = Field(
        default_factory=lambda: list(IngestionWorkerRole),
        description=(
            "Roles this worker process serves, one Temporal worker each. A Kubernetes deployment "
            "declares exactly one so its pods size and scale independently; the default serves all "
            "four, which is a single process covering every queue (local development). Leaving a "
            "role unserved parks its work silently, so the four roles must be covered between them. "
            "ingestion_max_concurrent_activities applies per role, so a process serving several of "
            "them may run that many activities times the number of roles."
        ),
    )

    @field_validator("worker_roles")
    @classmethod
    def _validate_worker_roles(cls, roles: List[IngestionWorkerRole]) -> List[IngestionWorkerRole]:
        if not roles:
            raise ValueError("scheduler.worker_roles must name at least one role")
        if len(set(roles)) != len(roles):
            raise ValueError("scheduler.worker_roles must not repeat a role")
        return roles


class AppConfig(BaseModel):
    name: Optional[str] = "Knowledge Flow Backend"
    base_url: str = "/knowledge-flow/v2"
    address: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    log_format: LogOutputFormat = "text"
    reload: bool = False
    reload_dir: str = "."
    gcu_version: str | None = None


class StorageConfig(BaseModel):
    postgres: PostgresStoreConfig
    opensearch: Optional[OpenSearchStoreConfig] = Field(default=None, description="Optional OpenSearch store")
    tabular_store: "TabularStoreConfig" = Field(
        default_factory=lambda: TabularStoreConfig(),  # type: ignore
        description="Dataset-centric tabular runtime configuration backed by Parquet artifacts in content storage.",
    )
    vector_store: VectorStorageConfig
    log_store: Optional[LogStorageConfig] = Field(default=None, description="Optional log store")


class ObservabilityConfig(BaseModel):
    kpi: KpiObservabilityConfig = Field(default_factory=KpiObservabilityConfig)


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app: AppConfig
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    chat_model: ModelConfiguration
    embedding_model: ModelConfiguration
    vision_model: Optional[ModelConfiguration] = None
    ocr_model: Optional[ModelConfiguration] = Field(
        default=None,
        description="Optional remote OCR model configuration. When set, PDF OCR can be delegated to an external API instead of local Docling OCR.",
    )
    attachment_processors: Optional[List[ProcessorConfig]] = Field(
        default=None,
        description="Optional fast-text processors for attachments. Uses the same ProcessorConfig structure, but classes must subclass BaseFastTextProcessor. If omitted, the default fast processor is used.",
    )
    output_processors: Optional[List[ProcessorConfig]] = None
    scheduler: SchedulerConfig
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig, description="A collection of feature flags to enable or disable optional functionality.")
    manager_processing: ManagerProcessingConfig | None = None
    storage: StorageConfig

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_root_input_processors(cls, values: dict):
        if isinstance(values, dict) and "input_processors" in values:
            raise ValueError(
                "Legacy root field 'input_processors' is no longer supported. Move processors under processing.profiles.<profile>.input_processors.",
            )
        return values

    @model_validator(mode="before")
    @classmethod
    def resolve_tabular_store_config(cls, values: object):
        """
        Validate the modern tabular-store configuration shape.

        Why this exists:
        - Tabular storage is now exposed through one single dataset-centric
          `storage.tabular_store` block.
        - The removed `storage.tabular_stores` key should fail loudly instead
          of being silently ignored.

        How to use:
        - Configure `storage.tabular_store.artifacts_prefix`,
          `storage.tabular_store.format`, `storage.tabular_store.compression`,
          and `storage.tabular_store.query.*`.
        - Omit `storage.tabular_store` only when you want the defaults.

        Example:
        ```yaml
        storage:
          tabular_store:
            artifacts_prefix: "tabular/datasets"
        ```
        """

        if not isinstance(values, dict):
            return values

        storage_value = values.get("storage")

        if isinstance(storage_value, dict) and "tabular_stores" in storage_value and storage_value.get("tabular_stores") is not None:
            raise ValueError(
                "'storage.tabular_stores' is no longer supported. Configure tabular settings under 'storage.tabular_store'.",
            )

        if isinstance(storage_value, dict):
            tabular_store_value = storage_value.get("tabular_store")
            if isinstance(tabular_store_value, dict):
                tabular_query_value = tabular_store_value.get("query")
                if isinstance(tabular_query_value, dict) and "presigned_ttl_seconds" in tabular_query_value:
                    raise ValueError(
                        "'storage.tabular_store.query.presigned_ttl_seconds' is no longer supported. Use 'storage.tabular_store.query.internal_presigned_ttl_seconds'.",
                    )

        return values
