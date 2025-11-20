#!/usr/bin/env python3
"""
Example usage of the géosecur maintenance API tool
=================================================

This script demonstrates how to use the get_maintenance_events tool
that calls the géosecur maintenance API with automatic JWT authentication.

Prerequisites:
- Optionally set GEOSECUR_USERNAME and GEOSECUR_PASSWORD environment variables
  (defaults to geosecur-admin/pass if not set)
- The tool automatically handles JWT token login and refresh
- Uses pre-configured géosecur API URL and engine ID
"""

import asyncio
import sys
import os

# Add the parent directory to Python path to import the server
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from postal_service_mcp_server.server_mcp import get_maintenance_events


async def example_usage():
    """Example usage of the géosecur maintenance API tool."""

    print("=== Géosecur Maintenance API Tool Example ===\n")

    # Check authentication credentials
    username = os.getenv("GEOSECUR_USERNAME", "geosecur-admin")
    password = os.getenv("GEOSECUR_PASSWORD", "pass")

    print(f"🔐 Using credentials: {username} / {'*' * len(password)}")
    print("📝 Note: JWT tokens are automatically managed and cached\n")

    # Example 1: Basic usage with JSON output
    print("1. Basic usage with JSON output:")
    result = await get_maintenance_events(
        start_at="13-11-2025 00:00:00",
        end_at="13-11-2025 23:59:59",
    )
    print(f"Result: {result}\n")

    # Example 2: CSV output with custom separator
    print("2. CSV output with semicolon separator:")
    result = await get_maintenance_events(
        start_at="12-11-2025 00:00:00",
        end_at="12-11-2025 23:59:59",
        format_type="csv",
        csv_separator=";",
    )
    print(f"Result: {result}\n")

    # Example 3: XML output with larger result set
    print("3. XML output with 200 results:")
    result = await get_maintenance_events(
        start_at="10-11-2025 00:00:00",
        end_at="11-11-2025 23:59:59",
        size=200,
        format_type="xml",
    )
    print(f"Result: {result}\n")

    # Example 4: Only start date (24h period)
    print("4. Only start date (24h period):")
    result = await get_maintenance_events(
        start_at="09-11-2025 08:00:00",
        timezone="Europe/Paris",
        size=50,
    )
    print(f"Result: {result}\n")

    # Example 5: Invalid date format (should return error)
    print("5. Invalid date format (should return error):")
    result = await get_maintenance_events(
        start_at="2025-11-13 00:00:00",  # Wrong format (ISO instead of French)
    )
    print(f"Result: {result}\n")


if __name__ == "__main__":
    asyncio.run(example_usage())
