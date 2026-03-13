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

import logging
import re
import traceback
from datetime import datetime, timezone
from typing import Dict, Optional, TypeVar

import yaml
from pydantic import ValidationError
from pydantic_settings import BaseSettings

from knowledge_flow_backend.common.structures import Configuration

logger = logging.getLogger(__name__)


def deep_merge(dict1: dict, dict2: dict) -> dict:
    """
    Deep merges dict2 into dict1.
    """
    result = dict1.copy()
    for key, value in dict2.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def parse_server_configuration(configuration_path: str, override_path: Optional[str] = None) -> Configuration:
    """
    Parses the server configuration from a YAML file.
    If an override_path is provided, it deep merges the override configuration
    into the base configuration.

    Args:
        configuration_path (str): The path to the base configuration YAML file.
        override_path (Optional[str]): The path to the override configuration YAML file.

    Returns:
        Configuration: The parsed and merged configuration object.
    """
    with open(configuration_path, "r") as f:
        try:
            config: Dict = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            print(f"Error while parsing base configuration file {configuration_path}: {e}")
            exit(1)

    if override_path and __import__("os").path.exists(override_path):
        with open(override_path, "r") as f:
            try:
                override_config: Dict = yaml.safe_load(f) or {}
                config = deep_merge(config, override_config)
            except yaml.YAMLError as e:
                print(f"Error while parsing override configuration file {override_path}: {e}")
                exit(1)

    return Configuration(**config)


B = TypeVar("B", bound=BaseSettings)


def validate_settings_or_exit(cls: type[B], name: str = "Settings") -> B:
    try:
        return cls()
    except ValidationError as e:
        logger.critical(f"❌ Invalid {name}:")
        for error in e.errors():
            field = error.get("loc", ["?"])[0]
            msg = error.get("msg", "")
            logger.critical(f"   - Missing or invalid: {field} → {msg}")
        logger.critical("📌 Tip: Check your .env file or environment variables.")
        raise SystemExit(1)


def log_exception(e: Exception, context_message: Optional[str] = None) -> str:
    """
    Logs an exception with full details (preserving caller's location)
    and returns a short, user-friendly summary string for UI display.

    Args:
        e (Exception): The exception to log.
        context_message (Optional[str]): Additional context for the logs.

    Returns:
        str: A human-readable summary of the exception.
    """
    error_type = type(e).__name__
    error_message = str(e)
    stack_trace = traceback.format_exc()

    # Detect root cause if chained exception
    cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
    root_cause = repr(cause) if cause else error_message

    # Short, user-friendly summary
    user_hint = ""
    if "Connection refused" in error_message:
        user_hint = "A service might be down or unreachable."
    elif "timeout" in error_message.lower():
        user_hint = "The system took too long to respond."
    elif "not found" in error_message.lower():
        user_hint = "Something you're trying to access doesn't exist."
    elif "authentication" in error_message.lower():
        user_hint = "There might be a credentials or permissions issue."
    else:
        user_hint = "An unexpected error occurred."

    # ✅ Compose final summary string
    summary = f"{error_type}: {error_message} — {user_hint}"

    # Log full details
    logger.error("Exception occurred: %s", error_type, stacklevel=2)
    if context_message:
        logger.error("🔍 Context: %s", context_message, stacklevel=2)
    logger.error("🧩 Error message: %s", error_message, stacklevel=2)
    logger.error("📦 Root cause: %s", root_cause, stacklevel=2)
    logger.debug("🧵 Stack trace:\n%s", stack_trace, stacklevel=2)

    return summary


def utc_now_iso() -> str:
    """
    Returns the current UTC timestamp as an ISO 8601 formatted string.

    This utility is useful for ensuring consistent and timezone-aware
    timestamps across metadata (e.g., `created_at`, `updated_at`).

    Example:
        >>> utc_now_iso()
        '2025-06-21T14:32:05.123456+00:00'

    Returns:
        str: The current UTC time in ISO 8601 format with timezone info.
    """
    return datetime.now(timezone.utc).isoformat()


def sanitize_sql_name(name: str) -> str:
    """
    Sanitize a table or column name to be SQL-friendly:
    - Lowercase
    - Replace spaces and invalid characters with underscores
    - Remove leading/trailing underscores
    """
    name = name.lower()
    name = re.sub(r"[^a-z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name)
    name = name.strip("_")
    return name
