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

from app.common.structures import AppConfig, Configuration, FrontendFlags, FrontendSettings, Properties
from app.application_context import ApplicationContext
from app.common.structures import PathOrIndexPrefix
from app.core.chatbot.chatbot_controller import ChatbotController
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
             security=SecurityConfiguration(enabled=False, keycloak_url="", client_id="app", authorized_origins=[])
        ),
         
        frontend_settings=FrontendSettings(
            feature_flags=FrontendFlags(enableK8Features=False, enableElecWarfare=False),
            properties=Properties(logoName="fred"),
            security=SecurityConfiguration(enabled=False, keycloak_url="", client_id="app", authorized_origins=[])
         ),

        database={
            "type": "csv",
            "csv_files": PathOrIndexPrefix(
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
        },
        kubernetes={
            "kube_config": "~/.kube/config",
            "timeout": {"connect": 5, "read": 15},
        },
        ai={
            "timeout": {"connect": 5, "read": 15},
            "default_model": {
                "provider": "openai",
                "name": "gpt-4o",
                "settings": {
                    "temperature": 0.0,
                    "max_retries": 2,
                    "request_timeout": 30,
                },
            },
            "leader": {
                "name": "Fred",
                "class_path": "app.agents.leader.leader.Leader",
                "enabled": True,
                "max_steps": 5,
                "model": {},
            },
            "services": [],
            "agents": [
                {
                    "name": "GeneralistExpert",
                    "class_path": "app.agents.generalist.generalist_expert.GeneralistExpert",
                    "enabled": True,
                    "model": {},
                }
            ],
            "recursion": {"recursion_limit": 40},
        },
        dao={"type": "file", "base_path": "/tmp/fred-dao"},
        security={
            "enabled": False,
            "keycloak_url": "",
            "client_id": "fred",
            "authorized_origins": [],
        },
        node_metrics_storage={"type": "local", "local_path": "/tmp/node-metrics"},
        tool_metrics_storage={"type": "local", "local_path": "/tmp/tool-metrics"},
        feedback_storage={"type": "ducckdb", "duckdb_path": "/tmp/ducckdb.db"},
        session_storage={"type": "in_memory"},
        agent_storage={"type": "duckdb", "duckdb_path": "/tmp/duckdb.db"},
    )


@pytest.fixture(scope="session")
def app_context(minimal_generalist_config):
    return ApplicationContext(minimal_generalist_config)


@pytest.fixture
def client(app_context) -> TestClient:
    app = FastAPI()
    router = APIRouter(prefix="/agentic/v1")
    ChatbotController(router)
    app.include_router(router)
    return TestClient(app)
