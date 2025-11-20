#!/usr/bin/env python3
"""
Example of using the portable Geosecur API client directly
=========================================================

This script demonstrates how to use the GeosecurClient class directly
without the MCP server, showing its portability.
"""

import asyncio
import os
import sys

# Add the parent directory to Python path to import the client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from postal_service_mcp_server.geosecur_client import (
    GeosecurClient,
    create_default_client,
)


async def example_direct_client():
    """Example of using the GeosecurClient directly."""

    print("=== Direct Geosecur API Client Example ===\n")

    # Method 1: Use the factory function with default configuration
    print("1. Using default client configuration:")
    client = create_default_client()

    result = await client.get_maintenance_events(
        start_at="13-11-2025 00:00:00", end_at="13-11-2025 12:00:00", size=50
    )
    print(f"Default client result: {result}\n")

    # Method 2: Create a custom client instance
    print("2. Using custom client configuration:")
    custom_client = GeosecurClient(
        api_url="https://geosecur-api.run.innovation-laposte.io:443",
        engine_id="tenant-geosecur-laposte",
        username="custom-user",  # You can override defaults
        password="custom-pass",  # Or use environment variables
    )

    result = await custom_client.get_maintenance_events(
        start_at="12-11-2025 00:00:00", format_type="csv", csv_separator=";"
    )
    print(f"Custom client result: {result}\n")

    # Method 3: Test token cache functionality
    print("3. Testing token cache (multiple calls):")

    # First call - will login and cache token
    print("First call (login + cache token):")
    result1 = await client.get_maintenance_events(
        start_at="11-11-2025 09:00:00", size=10
    )
    print(f"Result 1: {result1.get('success', 'Failed')}")

    # Second call - should use cached token
    print("Second call (use cached token):")
    result2 = await client.get_maintenance_events(
        start_at="11-11-2025 10:00:00", size=10
    )
    print(f"Result 2: {result2.get('success', 'Failed')}")

    # Clear cache and try again
    print("Third call (after clearing cache):")
    client.clear_token_cache()
    result3 = await client.get_maintenance_events(
        start_at="11-11-2025 11:00:00", size=10
    )
    print(f"Result 3: {result3.get('success', 'Failed')}\n")

    # Method 4: Error handling example
    print("4. Error handling example (invalid date):")
    result_error = await client.get_maintenance_events(
        start_at="2025-11-13 00:00:00"  # Wrong format
    )
    print(f"Error result: {result_error}")


async def example_multiple_clients():
    """Example showing multiple client instances for different configurations."""

    print("\n=== Multiple Clients Example ===\n")

    # Client for production environment
    prod_client = GeosecurClient(
        api_url="https://geosecur-api.run.innovation-laposte.io:443",
        engine_id="tenant-geosecur-laposte",
        username=os.getenv("GEOSECUR_PROD_USERNAME", "geosecur-admin"),
        password=os.getenv("GEOSECUR_PROD_PASSWORD", "pass"),
    )

    # Client for testing environment (hypothetical)
    test_client = GeosecurClient(
        api_url="https://geosecur-test-api.example.com",
        engine_id="tenant-test-geosecur",
        username=os.getenv("GEOSECUR_TEST_USERNAME", "test-admin"),
        password=os.getenv("GEOSECUR_TEST_PASSWORD", "test-pass"),
    )

    print("Production client configured:")
    print(f"  API URL: {prod_client.api_url}")
    print(f"  Engine ID: {prod_client.engine_id}")
    print(f"  Username: {prod_client.username}")

    print("\nTest client configured:")
    print(f"  API URL: {test_client.api_url}")
    print(f"  Engine ID: {test_client.engine_id}")
    print(f"  Username: {test_client.username}")

    # Only test prod client since test environment doesn't exist
    print("\nTesting production client:")
    result = await prod_client.get_maintenance_events(
        start_at="13-11-2025 00:00:00", size=5
    )
    print(f"Production result: {result.get('success', 'Failed')}")


if __name__ == "__main__":

    async def main():
        await example_direct_client()
        await example_multiple_clients()

    asyncio.run(main())
