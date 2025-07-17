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

from app.common.structure import Configuration, PathOrIndexPrefix
from app.application_context import ApplicationContext
from app.chatbot.chatbot_controller import ChatbotController
from app.features.frugal.ai_service import AIService
from app.features.k8.kube_service import KubeService


@pytest.fixture(scope="session")
def minimal_generalist_config() -> Configuration:
    return Configuration(
        frontend_settings={
            "feature_flags": {"enableK8Features": False, "enableElecWarfare": False},
            "properties": {"logoName": "fred"},
        },
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
                signal_identification_guide="dummy.csv"
            )
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
                "settings": {"temperature": 0.0, "max_retries": 2, "request_timeout": 30},
            },
            "leader": {
                "name": "Fred",
                "class_path": "app.leader.leader.Leader",
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
        security={"enabled": False, "keycloak_url": "", "client_id": "fred", "authorized_origins": []},
        node_metrics_storage={"type": "local", "local_path": "/tmp/node-metrics"},
        tool_metrics_storage={"type": "local", "local_path": "/tmp/tool-metrics"},
        feedback_storage={"type": "local", "local_path": "/tmp/feedback"},
        session_storage={"type": "in_memory"},
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
