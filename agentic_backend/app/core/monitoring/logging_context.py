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
logging_context.py

Context-local utilities for tracking user, session, and agent identifiers
during request lifecycles.

Uses Python's contextvars to propagate IDs without explicitly passing them,
even across async calls.

Typical usage:
    set_logging_context(user_id, session_id, agent_name)
    context = get_logging_context()
"""

import contextvars

user_id_var = contextvars.ContextVar("user_id", default="unknown-user")
session_id_var = contextvars.ContextVar("session_id", default="unknown-session")
agent_name_var = contextvars.ContextVar("agent_name", default="unknown-agent_name")


def set_logging_context(user_id: str, session_id: str, agent_name: str)->None:
    """
    Set user, session, and agent identifiers in the context.

    Should be called at the start of a request to populate logging and metric contexts.

    Args:
        user_id (str): ID or email of the current user.
        session_id (str): ID of the active session.
        agent_name (str): Name of the agent handling the request.
    """

    user_id_var.set(user_id)
    session_id_var.set(session_id)
    agent_name_var.set(agent_name)

def get_logging_context() -> dict:
    """
    Retrieve the current context including user, session, and agent identifiers.

    Returns:
        dict: Contains 'user_id', 'session_id', and 'agent_name'.
    """
    return {
        "user_id": user_id_var.get(),
        "session_id": session_id_var.get(),
        "agent_name": agent_name_var.get(),
    }
