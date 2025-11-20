"""
Geosecur API Client
==================

Portable module for interacting with the Geosecur API.
Handles JWT authentication, token caching, and API calls.

Usage:
    from postal_service_mcp_server.geosecur_client import GeosecurClient

    client = GeosecurClient(
        api_url="xxx",
        engine_id="tenant-geosecur-laposte",
        username="geosecur-admin",
        password="pass"
    )

    # Get maintenance events
    result = await client.get_maintenance_events(
        start_at="13-11-2025 00:00:00",
        end_at="13-11-2025 23:59:59"
    )
"""

from __future__ import annotations

import time
import os
from typing import Dict, Any, Optional, Literal
import aiohttp
from datetime import datetime


class GeosecurClient:
    """Client for Geosecur API with automatic JWT authentication."""

    def __init__(
        self,
        api_url: str,
        engine_id: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """Initialize the Geosecur API client.

        Args:
            api_url: Base URL of the Geosecur API
            engine_id: Engine/tenant ID for the API
            username: Username for authentication (can be None to use env var)
            password: Password for authentication (can be None to use env var)
        """
        self.api_url = api_url.rstrip("/")
        self.engine_id = engine_id
        self.username = username or os.getenv("GEOSECUR_USERNAME", "geosecur-admin")
        self.password = password or os.getenv("GEOSECUR_PASSWORD", "pass")

        # JWT token cache
        self._cached_jwt: Optional[str] = None
        self._jwt_expires_at: Optional[int] = None

    async def _login_and_get_jwt(self) -> Dict[str, Any]:
        """Login to Geosecur API and get JWT token.

        Returns:
            Dictionary with success status and JWT token or error message
        """
        login_url = f"{self.api_url}/_login/local"

        login_data = {"username": self.username, "password": self.password}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    login_url,
                    json=login_data,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == 200 and data.get("result"):
                            result = data["result"]
                            jwt_token = result.get("jwt")
                            expires_at = result.get("expiresAt")

                            if jwt_token and expires_at:
                                return {
                                    "success": True,
                                    "jwt": jwt_token,
                                    "expires_at": expires_at,
                                }
                            else:
                                return {
                                    "success": False,
                                    "error": "Invalid response format: missing jwt or expiresAt",
                                }
                        else:
                            return {
                                "success": False,
                                "error": f"Login failed: {data.get('error', 'Unknown error')}",
                            }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"HTTP {response.status}: {error_text}",
                        }
        except Exception as e:
            return {"success": False, "error": f"Login request failed: {str(e)}"}

    async def _get_valid_jwt(self) -> Dict[str, Any]:
        """Get a valid JWT token, refreshing if necessary.

        Returns:
            Dictionary with success status and JWT token or error message
        """
        # Check if we have a cached token that's still valid
        current_time_ms = int(time.time() * 1000)

        if (
            self._cached_jwt
            and self._jwt_expires_at
            and current_time_ms < (self._jwt_expires_at - 60000)
        ):  # 1 minute buffer
            return {"success": True, "jwt": self._cached_jwt}

        # Need to get a new token
        login_result = await self._login_and_get_jwt()

        if login_result["success"]:
            self._cached_jwt = login_result["jwt"]
            self._jwt_expires_at = login_result["expires_at"]
            return {"success": True, "jwt": self._cached_jwt}
        else:
            return login_result

    async def get_maintenance_events(
        self,
        start_at: str,
        end_at: Optional[str] = None,
        timezone: str = "Europe/Paris",
        size: int = 100,
        format_type: Literal["json", "csv", "xml"] = "json",
        csv_separator: Literal[",", ";"] = ",",
    ) -> Dict[str, Any]:
        """Get maintenance events from the Geosecur API.

        Args:
            start_at: Start date in French format (dd-mm-yyyy hh:mm:ss)
            end_at: End date in French format (optional)
            timezone: Timezone for date interpretation
            size: Number of results to return
            format_type: Output format (json, csv, xml)
            csv_separator: CSV separator character

        Returns:
            Dictionary containing the API response with maintenance events data
        """
        # Validate date format
        try:
            datetime.strptime(start_at, "%d-%m-%Y %H:%M:%S")
            if end_at:
                datetime.strptime(end_at, "%d-%m-%Y %H:%M:%S")
        except ValueError as e:
            return {
                "success": False,
                "error": f"Invalid date format. Use dd-mm-yyyy hh:mm:ss format. Error: {str(e)}",
            }

        # Get valid JWT token
        jwt_result = await self._get_valid_jwt()
        if not jwt_result["success"]:
            return jwt_result

        url = f"{self.api_url}/_/gestionmaintenance/getMaintenanceEvents"

        # Prepare request body
        request_body = {
            "startAt": start_at,
            "timezone": timezone,
            "size": size,
            "format": format_type,
            "csvseparator": csv_separator,
        }

        if end_at:
            request_body["endAt"] = end_at

        # Prepare query parameters
        params = {"engineId": self.engine_id}

        # Prepare headers with JWT token
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {jwt_result['jwt']}",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=request_body,
                    params=params,
                    headers=headers,
                ) as response:
                    if response.status == 200:
                        # Handle different response content types
                        content_type = response.headers.get("Content-Type", "")
                        if "application/json" in content_type:
                            data = await response.json()
                        else:
                            data = await response.text()
                        print(f"nombre de maintenance events reçus: ${len(data)}")
                        return {
                            "success": True,
                            "status_code": response.status,
                            "data": data,
                            "content_type": content_type,
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "status_code": response.status,
                            "error": error_text,
                        }
        except Exception as e:
            return {"success": False, "error": f"Request failed: {str(e)}"}

    async def search_assets(
        self,
        query: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        designation: Optional[str] = None,
        actif: bool = True,
        created_after: Optional[str] = None,
        created_before: Optional[str] = None,
        measured_after: Optional[str] = None,
        measured_before: Optional[str] = None,
        size: int = 10000,
        from_: int = 0,
    ) -> Dict[str, Any]:
        """Search assets in the Kuzzle collection with optional filters.

        Args:
            query: Custom Elasticsearch DSL query (overrides other filters if provided)
            model: Filter by asset model
            designation: Filter by metadata.designation
            actif: Filter by metadata.actif (default: true)
            created_after: Filter documents created after this date (ISO format or timestamp)
            created_before: Filter documents created before this date (ISO format or timestamp)
            measured_after: Filter by positionSpeed measuredAt after this date (ISO format or timestamp)
            measured_before: Filter by positionSpeed measuredAt before this date (ISO format or timestamp)
            size: Number of results to return (default: 100)
            from_: Start from result number (for pagination, default: 0)

        Returns:
            Dictionary containing the search results
        """
        # Get valid JWT token
        jwt_result = await self._get_valid_jwt()
        if not jwt_result["success"]:
            return jwt_result

        url = f"{self.api_url}/_query"

        # Build the query
        if query is not None:
            # Use custom query if provided
            search_query = query
        else:
            # Build query from filters
            must_clauses = []

            # Model filter
            if model:
                must_clauses.append({"term": {"model": model}})

            # Designation filter
            if designation:
                must_clauses.append({"term": {"metadata.designation": designation}})

            # Actif filter (default to True)
            # Convert Python boolean to JSON boolean (true/false)
            actif_json = str(actif).lower() if isinstance(actif, bool) else actif
            must_clauses.append({"term": {"metadata.actif": actif_json}})

            # Created date filters
            if created_after or created_before:
                range_filter = {}
                if created_after:
                    range_filter["gte"] = created_after
                if created_before:
                    range_filter["lte"] = created_before
                must_clauses.append({"range": {"_kuzzle_info.createdAt": range_filter}})

            # Measured date filters
            if measured_after or measured_before:
                range_filter = {}
                if measured_after:
                    range_filter["gte"] = measured_after
                if measured_before:
                    range_filter["lte"] = measured_before
                must_clauses.append(
                    {"range": {"measures.positionSpeed.measuredAt": range_filter}}
                )

            # Build final query
            if must_clauses:
                search_query = {"bool": {"must": must_clauses}}
            else:
                search_query = {"match_all": {}}

        # Prepare request body
        request_body = {
            "controller": "document",
            "action": "search",
            "index": "tenant-geosecur-laposte",
            "collection": "assets",
            "body": {"query": search_query},
            "size": size,
        }
        print(request_body)

        # Prepare headers with JWT token
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {jwt_result['jwt']}",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=request_body,
                    headers=headers,
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "success": True,
                            "status_code": response.status,
                            "data": data,
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "status_code": response.status,
                            "error": error_text,
                        }
        except Exception as e:
            return {"success": False, "error": f"Request failed: {str(e)}"}

    def clear_token_cache(self):
        """Clear the cached JWT token (useful for testing or forced refresh)."""
        self._cached_jwt = None
        self._jwt_expires_at = None


# Factory function for easy instantiation with default config
def create_default_client() -> GeosecurClient:
    """Create a GeosecurClient with default Geosecur configuration.

    Returns:
        Configured GeosecurClient instance
    """
    return GeosecurClient(
        api_url="xxx",
        engine_id="tenant-geosecur-laposte",
    )
