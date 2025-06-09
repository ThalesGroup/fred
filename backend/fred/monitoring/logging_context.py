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

"""
Context-local logging utilities for tracking user and session information.

This module uses Python's `contextvars` to store `user_id` and `session_id` 
for the lifetime of an asynchronous request. This allows logs to automatically
include these identifiers across deeply nested or async function calls 
without explicitly passing them around.

Usage:
    from fred.logging_context import set_logging_context, get_logging_context

    set_logging_context(user_id="alice@example.com", session_id="abcd1234")
    context = get_logging_context()
    print(context["user_id"])  # alice@example.com
"""

import contextvars

user_id_var = contextvars.ContextVar("user_id", default="unknown-user")
session_id_var = contextvars.ContextVar("session_id", default="unknown-session")

def set_logging_context(user_id: str, session_id: str)->None:
    """
    Set the user ID and session ID in the context.

    This function should be called at the beginning of a request (e.g., in
    an API route handler or session entry point) to populate the context
    variables for downstream logging or monitoring.

    Args:
        user_id (str): The ID or email of the current user.
        session_id (str): The ID of the active chatbot session.
    """
    user_id_var.set(user_id)
    session_id_var.set(session_id)

def get_logging_context() -> dict:
    """
    Retrieve the current logging context as a dictionary.

    This function can be called from anywhere in the codebase to access
    the user and session identifiers previously set with `set_logging_context`.

    Returns:
        dict: A dictionary containing 'user_id' and 'session_id' keys.
    """
    return {
        "user_id": user_id_var.get(),
        "session_id": session_id_var.get(),
    }
