# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
from typing import Optional

from fred_core import LogStorageConfig, SecurityConfiguration
from fred_core.common import KpiObservabilityConfig, ModelConfiguration, OpenSearchStoreConfig, PostgresStoreConfig
from fred_knowledge.configuration import ArtifactStorageConfig, TabularStoreConfig, TextSplitterConfig, VectorStorageConfig
from fred_knowledge.configuration import OpenSearchVectorIndexConfig as OpenSearchVectorIndexConfig
from fred_knowledge.configuration import PgVectorStorageConfig as PgVectorStorageConfig
from fred_knowledge.configuration import TabularQueryConfig as TabularQueryConfig
from fred_pod.common.structures import LogOutputFormat
from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    crossencoder_model: Optional[ModelConfiguration] = None
    security: SecurityConfiguration
    control_plane_url: str | None = None
    published_artifacts: ArtifactStorageConfig | None = None
    storage: StorageConfig
    use_gpu: bool = True
    text_splitter: TextSplitterConfig = Field(default_factory=TextSplitterConfig)

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
