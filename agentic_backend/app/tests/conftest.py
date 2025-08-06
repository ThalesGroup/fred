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

# app/tests/conftest.py


import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI, APIRouter

from app.common.structures import (
    AIConfig,
    AgentSettings,
    AppConfig,
    Configuration,
    DAOConfiguration,
    DAOTypeEnum,
    DatabaseConfiguration,
    DatabaseTypeEnum,
    DuckdbAgentStorageConfig,
    DuckdbFeedbackStorage,
    DuckdbSessionStorageConfig,
    FrontendFlags,
    FrontendSettings,
    KubernetesConfiguration,
    ModelConfiguration,
    Properties,
    RecursionConfig,
    TimeoutSettings,
)
from app.application_context import ApplicationContext
from app.common.structures import PathOrIndexPrefix
from fred_core import SecurityConfiguration


@pytest.fixture(scope="session")
def minimal_generalist_config() -> Configuration:
    return Configuration(
        app=AppConfig(
            base_url="/knowledge-flow/v1",
            address="127.0.0.1",
            port=8000,
            log_level="info",
            reload=False,
            reload_dir=".",
            security=SecurityConfiguration(
                enabled=False, keycloak_url="", client_id="app", authorized_origins=[]
            ),
        ),
        frontend_settings=FrontendSettings(
            feature_flags=FrontendFlags(
                enableK8Features=False, enableElecWarfare=False
            ),
            properties=Properties(logoName="fred"),
            security=SecurityConfiguration(
                enabled=False, keycloak_url="", client_id="app", authorized_origins=[]
            ),
        ),
        database=DatabaseConfiguration(
            type=DatabaseTypeEnum.csv,
            csv_files=PathOrIndexPrefix(
                energy_mix="dummy.csv",
                carbon_footprint="dummy.csv",
                energy_footprint="dummy.csv",
                financial_footprint="dummy.csv",
                frequencies="dummy.csv",
                sensors_test_new="dummy.csv",
                mission="dummy.csv",
                radio="dummy.csv",
                signal_identification_guide="dummy.csv",
            ),
        ),
        kubernetes=KubernetesConfiguration(
            kube_config="~/.kube/config",
            timeout=TimeoutSettings(connect=5, read=15),
        ),
        ai=AIConfig(
            timeout=TimeoutSettings(connect=5, read=15),
            default_model=ModelConfiguration(
                provider="openai",
                name="gpt-4o",
                settings={
                    "temperature": 0.0,
                    "max_retries": 2,
                    "request_timeout": 30,
                },
            ),
            agents=[
                AgentSettings(
                    name="GeneralistExpert",
                    class_path="app.agents.generalist.generalist_expert.GeneralistExpert",
                    enabled=True,
                    model=ModelConfiguration(
                        provider="openai",
                        name="gpt-4o",
                        settings={
                            "temperature": 0.0,
                            "max_retries": 2,
                            "request_timeout": 30,
                        },
                    ),
                )
            ],
            services=[],
            recursion=RecursionConfig(recursion_limit=40),
        ),
        dao=DAOConfiguration(
            type=DAOTypeEnum("file"),
            base_path="/tmp/fred-dao",
            max_cached_delay_seconds=30,
        ),
        feedback_storage=DuckdbFeedbackStorage(
            type="duckdb", duckdb_path="/tmp/ducckdb.db"
        ),
        session_storage=DuckdbSessionStorageConfig(
             type="duckdb", duckdb_path="/tmp/ducckdb.db"
        ),
        agent_storage=DuckdbAgentStorageConfig(
            type="duckdb",
            duckdb_path="/tmp/duckdb.db",
        ),
    )


@pytest.fixture(scope="session")
def app_context(minimal_generalist_config):
    return ApplicationContext(minimal_generalist_config)


@pytest.fixture
def client(app_context) -> TestClient:
    app = FastAPI()
    router = APIRouter(prefix="/agentic/v1")
    # ChatbotController(router)
    app.include_router(router)
    return TestClient(app)
