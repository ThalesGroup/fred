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
Helper functions to extract user authentication context for OAuth2 Token Exchange.

This module provides utilities to capture the user's JWT token from FastAPI requests
and integrate it with RuntimeContext for proper user identity propagation in MCP calls.
"""

from typing import Optional
from fastapi import Request, Depends, Security
from fastapi.security import OAuth2PasswordBearer
from fred_core import KeycloakUser, get_current_user

from app.core.agents.runtime_context import RuntimeContext

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token", auto_error=False)


def get_user_token_from_request(request: Request) -> Optional[str]:
    """
    Extract the raw JWT token from the Authorization header.
    
    Args:
        request: FastAPI request object
        
    Returns:
        The raw JWT token string (without "Bearer " prefix) or None if not found
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    
    if not auth_header.startswith("Bearer "):
        return None
    
    return auth_header[7:]  # Remove "Bearer " prefix


def create_runtime_context_with_user_token(
    request: Request,
    user: KeycloakUser,
    base_context: Optional[RuntimeContext] = None
) -> RuntimeContext:
    """
    Create or enhance a RuntimeContext with the user's JWT token for OAuth2 Token Exchange.
    
    This function extracts the user's JWT token from the request and adds it to the 
    RuntimeContext. This enables MCP calls to exchange the user token for a service 
    token that preserves the user's identity.
    
    Args:
        request: FastAPI request object containing the Authorization header
        user: Authenticated user information from Keycloak
        base_context: Optional existing RuntimeContext to enhance
        
    Returns:
        RuntimeContext with user_token populated for token exchange
    """
    # Start with base context or create new one
    if base_context:
        context = base_context.model_copy()
    else:
        context = RuntimeContext()
    
    # Extract and add user token
    user_token = get_user_token_from_request(request)
    if user_token:
        context.user_token = user_token
    
    return context


def get_user_with_token_context(
    request: Request = Depends(),
    user: KeycloakUser = Depends(get_current_user)
) -> tuple[KeycloakUser, RuntimeContext]:
    """
    FastAPI dependency that returns both the authenticated user and a RuntimeContext 
    with their token for OAuth2 Token Exchange.
    
    Usage in FastAPI endpoints:
    ```python
    @router.post("/some-endpoint")
    def some_endpoint(
        user_and_context: tuple[KeycloakUser, RuntimeContext] = Depends(get_user_with_token_context)
    ):
        user, context = user_and_context
        # Use context in agent calls...
    ```
    
    Returns:
        Tuple of (authenticated_user, runtime_context_with_token)
    """
    context = create_runtime_context_with_user_token(request, user)
    return user, context