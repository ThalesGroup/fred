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
from collections import deque

from dotenv import load_dotenv

# Pod-local, bounded bootstrap diagnostics wait until the selected formatter exists.
_startup_events: deque[tuple[logging.Logger, logging.LogRecord]] = deque(maxlen=32)
_logging_ready = False


def defer_startup_log(logger: logging.Logger, level: int, message: str) -> None:
    """Preserve event time while deferring config diagnostics until logging setup."""
    record = logger.makeRecord(logger.name, level, __file__, 0, message, (), None)
    if _logging_ready:
        if logger.isEnabledFor(level):
            logger.handle(record)
        return
    _startup_events.append((logger, record))


def flush_startup_logs() -> None:
    """Emit bounded bootstrap diagnostics after the application's handlers exist."""
    global _logging_ready
    _logging_ready = True
    while _startup_events:
        try:
            logger, record = _startup_events.popleft()
        except IndexError:
            break
        if logger.isEnabledFor(record.levelno):
            logger.handle(record)


class ConfigFiles:
    """Resolve and track startup config paths for Fred backends.

    Why this exists:
    - Every backend starts the same way: load environment variables, then load a
      YAML configuration file.
    - Exact selected paths stay available to operational inspection, outside logs.

    Example:
    - `ENV_FILE=./config/.env.prod`
    - `CONFIG_FILE=./config/configuration_prod.yaml`
    """

    def __init__(
        self,
        *,
        logger: logging.Logger,
        default_env_file: str = "./config/.env",
        default_config_file: str = "./config/configuration.yaml",
        env_var_name: str = "ENV_FILE",
        config_var_name: str = "CONFIG_FILE",
        log_prefix: str = "[CONFIG]",
    ) -> None:
        """Create a resolver with Fred defaults.

        Example:
        - Keep defaults for regular startup.
        - Override `default_config_file` in tests to point to a fixture.
        """
        self._logger = logger
        self._default_env_file = default_env_file
        self._default_config_file = default_config_file
        self._env_var_name = env_var_name
        self._config_var_name = config_var_name
        self._loaded_env_file_path: str | None = None
        self._loaded_config_file_path: str | None = None

    def get_loaded_env_file_path(self) -> str | None:
        """Return the effective env file path used at runtime.

        Example:
        - Returns `./config/.env` when no override is provided.
        - Returns `/etc/fred/agentic.env` in a production deployment override.
        """
        return self._loaded_env_file_path

    def get_loaded_config_file_path(self) -> str | None:
        """Return the effective YAML config file path used at runtime.

        Example:
        - `./config/configuration.yaml` in local mode.
        - `./config/configuration_worker.yaml` for worker startup.
        """
        return self._loaded_config_file_path

    def load_environment(self, dotenv_path: str | None = None) -> str:
        """Load environment variables from the selected env file.

        Selection order:
        1. Explicit `dotenv_path` argument.
        2. `ENV_FILE` environment variable.
        3. Default `./config/.env`.

        Example:
        - Calling `load_environment()` with `ENV_FILE=./config/.env.prod`
          loads production secrets and returns that path.
        """
        env_path = dotenv_path or os.getenv(self._env_var_name, self._default_env_file)
        loaded = load_dotenv(env_path)
        defer_startup_log(
            self._logger,
            logging.INFO if loaded else logging.WARNING,
            "Environment configuration loaded"
            if loaded
            else "Environment file unavailable; using process environment",
        )
        self._loaded_env_file_path = env_path
        return env_path

    def resolve_config_file_path(self, config_file: str | None = None) -> str:
        """Resolve and validate the YAML configuration path.

        Selection order:
        1. Explicit `config_file` argument.
        2. `CONFIG_FILE` environment variable.
        3. Default `./config/configuration.yaml`.

        Raises:
        - `FileNotFoundError` if the resolved file does not exist.
        """
        resolved = config_file or os.getenv(
            self._config_var_name, self._default_config_file
        )
        if not os.path.exists(resolved):
            raise FileNotFoundError(f"Configuration file not found: {resolved}")
        return resolved

    def mark_config_loaded(self, config_file: str) -> None:
        """Record the selected file and defer its identifier-free load status.

        Example:
        - After parsing `configuration_prod.yaml`, call this method so startup
          inspection exposes the profile while logs contain only load status.
        """
        self._loaded_config_file_path = config_file
        defer_startup_log(
            self._logger, logging.INFO, "Application configuration loaded"
        )
