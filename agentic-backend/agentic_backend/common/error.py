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

from fastapi import HTTPException


class UnavailableError(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=503, detail=f"Resource unavailable: {message}")


class InvalidCacheError(FileNotFoundError): ...


# ------------------------------
# MCP & Agent setup Exceptions
# ------------------------------
# agentic_backend/features/dynamic_agent/exceptions.py


class MCPClientConnectionException(Exception):
    def __init__(self, agent_id: str, reason: str):
        super().__init__(f"Failed to connect MCP client for '{agent_id}': {reason}")
        self.agent_id = agent_id
        self.reason = reason


class UnsupportedTransportError(ValueError): ...


class MCPToolFetchError(ValueError): ...


class NoToolkitProvidedError(ValueError): ...


# ------------------------------
# Session storage exceptions
# ------------------------------


class SessionNotFoundError(Exception):
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Session '{session_id}' not found")
