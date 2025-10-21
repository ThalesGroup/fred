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

import inspect
import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import yaml

from app.common.structures import (
    Configuration,
)

logger = logging.getLogger(__name__)


def parse_server_configuration(configuration_path: str) -> Configuration:
    """
    Parses the server configuration from a YAML file.

    Args:
        configuration_path (str): The path to the configuration YAML file.

    Returns:
        Configuration: The parsed configuration object.
    """
    with open(configuration_path, "r") as f:
        try:
            config: Dict = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"Error while parsing configuration file {configuration_path}: {e}")
            exit(1)
    return Configuration(**config)


def get_class_path(cls: type) -> str:
    """
    Returns the fully qualified class path as a string, e.g.:
    'app.core.agents.mcp_agent.MCPAgent'
    """
    module = inspect.getmodule(cls)
    if not module or not hasattr(cls, "__name__"):
        raise ValueError(f"Could not determine class path for {cls}")
    return f"{module.__name__}.{cls.__name__}"


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
    logger.error("🧵 Stack trace:\n%s", stack_trace, stacklevel=2)

    return summary


def truncate_datetime(dt: datetime, precision: str) -> datetime:
    """
    Truncate a datetime to the start of the given precision.
    Supported precisions: 'minute', 'hour', 'day', 'week', 'month'.
    Always returns a timezone-aware UTC datetime.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    match precision:
        case "minute":
            return dt.replace(second=0, microsecond=0)
        case "hour":
            return dt.replace(minute=0, second=0, microsecond=0)
        case "day":
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        case "week":
            # ISO weeks: Monday is start of week
            start_of_week = dt - timedelta(days=dt.weekday())
            return start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        case "month":
            return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        case _:
            raise ValueError(f"Unsupported precision: {precision}")
