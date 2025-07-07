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
from typing import Optional
from fastapi.security import OAuth2PasswordBearer
from fastapi import Security, HTTPException
import jwt
from jwt import PyJWKClient
from pydantic import BaseModel

from fred.common.structure import Configuration

# 🔹 Create a module-level logger
logger = logging.getLogger(__name__)

# Initialize global variables (to be set later)
KEYCLOAK_ENABLED = False
KEYCLOAK_URL = ""
KEYCLOAK_JWKS_URL = ""
KEYCLOAK_CLIENT_ID = ""

def initialize_keycloak(config: Configuration):
    """
    Initialize the Keycloak authentication settings from the given configuration.
    """
    global KEYCLOAK_ENABLED, KEYCLOAK_URL, KEYCLOAK_JWKS_URL, KEYCLOAK_CLIENT_ID

    KEYCLOAK_ENABLED = config.security.enabled if hasattr(config, "security") and config.security else False
    KEYCLOAK_URL = config.security.keycloak_url if hasattr(config, "security") and config.security else "http://localhost:9080/realms/fred"
    KEYCLOAK_CLIENT_ID = config.security.client_id if hasattr(config, "security") and config.security else "fred"
    KEYCLOAK_JWKS_URL = f"{KEYCLOAK_URL}/protocol/openid-connect/certs"

    logger.info(f"Keycloak initialized. Enabled: {KEYCLOAK_ENABLED}, URL: {KEYCLOAK_URL}")


# OAuth2 Password Bearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

class KeycloakUser(BaseModel):
    """Represents an authenticated Keycloak user."""
    username: str
    roles: list[str]
    email: Optional[str] = None

def decode_jwt(token: str) -> KeycloakUser:
    """Decodes a JWT token using PyJWT and retrieves user information."""
    if not KEYCLOAK_ENABLED:
        logger.warning("Authentication is DISABLED. Returning a mock user.")
        return KeycloakUser(username="admin", roles=["admin"], email="dev@localhost")
    
    logger.debug("Starting JWT decoding process...")

    try:
        logger.debug(f"Fetching signing key from JWKS URL: {KEYCLOAK_JWKS_URL}")
        jwks_client = PyJWKClient(KEYCLOAK_JWKS_URL)

        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token).key
            logger.debug("Successfully retrieved signing key")
        except Exception as e:
            logger.error(f"Failed to retrieve signing key from JWKS: {e}")
            raise HTTPException(status_code=401, detail="Invalid token signature")

        # Decode JWT
        logger.debug("Decoding JWT token...")
        try:
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                options={"verify_exp": True, "verify_aud": False}
            )
            logger.debug("JWT token successfully decoded")

        except jwt.ExpiredSignatureError:
            logger.warning("JWT token has expired")
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid JWT token: {str(e)}")
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

        # Step 3: Validate audience in the token. This is optional
        # better to have in multi client environments.
        # logger.debug("Validating token audience...")
        # aud = payload.get("aud", [])
        # if not isinstance(aud, list):
        #    aud = [aud]

        # if KEYCLOAK_CLIENT_ID not in aud:
        #    logger.warning(f"Invalid audience in token: {aud}")
        #    raise HTTPException(status_code=401, detail="Invalid audience in token")
 
        # Extract roles (Only client roles are used)
        client_roles = []
        if "resource_access" in payload:
            client_data = payload["resource_access"].get(KEYCLOAK_CLIENT_ID, {})
            client_roles = client_data.get("roles", [])

        logger.debug(f"User roles: {client_roles}")

        # Extract user information
        logger.debug("Extracting user information from token...")
        user = KeycloakUser(
            username=payload.get("preferred_username", ""),
            roles=client_roles,
            email=payload.get("email"),
        )

        logger.debug(f"Decoded user info: {user}")
        return user

    except Exception as e:
        logger.error(f"Unexpected error while decoding JWT: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during token validation")

def get_current_user(token: str = Security(oauth2_scheme)) -> KeycloakUser:
    """Fetches the current user from Keycloak token."""
    if not KEYCLOAK_ENABLED:
        logger.warning("Authentication is DISABLED. Returning a mock user.")
        return KeycloakUser(username="admin", roles=["admin"], email="admin@mail.com")
    else:
        logger.info("Authentication is ENABLED")
    if not token:
        raise HTTPException(status_code=401, detail="No authentication token provided")
    
    logger.debug(f"Received token: {token}")
    return decode_jwt(token)
