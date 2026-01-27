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

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from agentic_backend.common.structures import Configuration
from agentic_backend.common.utils import parse_server_configuration

_last_env_file_path: str | None = None
_last_config_file_path: str | None = None


def load_environment(dotenv_path: str | None = None) -> str:
    env_path = dotenv_path or os.getenv("ENV_FILE", "./config/.env")
    if load_dotenv(env_path):
        logging.getLogger().info(
            "[CONFIG] Loaded environment variables from: %s",
            env_path,
        )
    else:
        logging.getLogger().warning("No .env file found at: %s", env_path)
    global _last_env_file_path
    _last_env_file_path = env_path
    return env_path


def load_configuration() -> Configuration:
    load_environment()
    default_config_file = "./config/configuration.yaml"
    config_file = os.environ.get("CONFIG_FILE", default_config_file)
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Configuration file not found: {config_file}")
    configuration: Configuration = parse_server_configuration(config_file)
    logging.getLogger(__name__).info(
        "[CONFIG] Loaded configuration from: %s",
        config_file,
    )
    global _last_config_file_path
    _last_config_file_path = config_file
    return configuration


def get_loaded_env_file_path() -> str | None:
    return _last_env_file_path


def get_loaded_config_file_path() -> str | None:
    return _last_config_file_path
