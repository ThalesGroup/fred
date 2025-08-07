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

from typing import Dict, Optional
from app.common.error import SESSION_NOT_INITIALIZED
from app.common.structures import (
    Configuration,
)
from fastapi import HTTPException
import logging
import traceback
import yaml
from functools import wraps
import inspect

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


# Decorator for wrapping methods to protect by authentication
def authorization_required(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        sig = inspect.signature(method)
        bound_args = sig.bind(self, *args, **kwargs)
        bound_args.apply_defaults()

        arguments = bound_args.arguments
        session_id = arguments.get("session_id")
        user_id = arguments.get("user_id")

        if user_id is None:
            raise ValueError(f"Missing 'user_id' in method '{method.__name__}'")
        if session_id is None:
            raise ValueError(f"Missing 'session_id' in method '{method.__name__}'")
        if not isinstance(user_id, str):
            raise ValueError("'user_id' must be of type 'str'")
        if not isinstance(session_id, str):
            raise ValueError("'session_id' must be of type 'str'")
        if not hasattr(self, "get_authorized_user_id") or not callable(
            getattr(self, "get_authorized_user_id")
        ):
            raise NotImplementedError(
                f"{self.__class__.__name__} must implement 'get_authorized_user_id'"
            )

        # Get the value of the authorized_user that can access the method. The way to get it depends on the storage type so we have it defined here
        authorized_user_id = self.get_authorized_user_id(session_id)

        # In case we want to load messages for a user with a non initialized session (i.e when first loading the page, we should not throw an unauthorized exception)
        if authorized_user_id is SESSION_NOT_INITIALIZED:
            logger.debug(
                f"Session '{session_id}' not yet initialized — skipping auth check for method '{method.__name__}'"
            )
            return method(self, *args, **kwargs)

        if authorized_user_id != user_id:
            logger.warning(
                f"Unauthorized access: user {user_id} to session {session_id} in method '{method.__name__}'"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Unauthorized access: user {user_id} to session {session_id}",
            )

        return method(self, *args, **kwargs)

    return wrapper
