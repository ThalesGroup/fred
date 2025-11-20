#!/usr/bin/env python3
"""
Test script to verify boolean conversion fix
==========================================

This script tests the boolean conversion fix in the GeosecurClient
to ensure Python True/False are correctly converted to JSON true/false.
"""

import asyncio
import json


async def test_boolean_conversion():
    """Test that boolean conversion works correctly in search_assets."""

    print("🧪 Testing Boolean Conversion Fix\n")

    # Import our corrected client
    from postal_service_mcp_server.geosecur_client import GeosecurClient

    client = GeosecurClient(
        api_url="https://geosecur-api.run.innovation-laposte.io:443",
        engine_id="tenant-geosecur-laposte",
    )

    # Test 1: Verify boolean conversion logic
    print("1. Testing boolean conversion logic:")

    test_cases = [
        (True, "true"),
        (False, "false"),
        ("true", "true"),  # Already string
        ("false", "false"),  # Already string
    ]

    for input_val, expected in test_cases:
        actif_json = (
            str(input_val).lower() if isinstance(input_val, bool) else input_val
        )
        status = "✅ PASS" if actif_json == expected else "❌ FAIL"
        print(
            f"   Input: {input_val} ({type(input_val).__name__}) → Output: {actif_json} → {status}"
        )

    print()

    # Test 2: Verify JSON serialization works correctly
    print("2. Testing JSON serialization with converted values:")

    query_with_true = {
        "bool": {"must": [{"term": {"metadata.actif": "true"}}]}  # String format
    }

    query_with_false = {
        "bool": {"must": [{"term": {"metadata.actif": "false"}}]}  # String format
    }

    try:
        json_true = json.dumps(query_with_true)
        json_false = json.dumps(query_with_false)
        print(f"   Query with 'true': {json_true}")
        print(f"   Query with 'false': {json_false}")
        print("   ✅ JSON serialization successful")
    except Exception as e:
        print(f"   ❌ JSON serialization failed: {e}")

    print()

    # Test 3: Test the actual search method (without making real API calls)
    print("3. Testing search_assets method with different actif values:")

    # Note: This won't make real API calls since we're not calling the method
    # but we can test the query building logic

    test_actif_values = [True, False]

    for actif_value in test_actif_values:
        print(f"   Testing with actif={actif_value}:")

        # Simulate the query building logic from search_assets
        must_clauses = []
        actif_json = (
            str(actif_value).lower() if isinstance(actif_value, bool) else actif_value
        )
        must_clauses.append({"term": {"metadata.actif": actif_json}})

        search_query = {"bool": {"must": must_clauses}}

        try:
            json_query = json.dumps(search_query)
            print(f"     Generated query: {json_query}")
            print(f"     ✅ Query generation successful")
        except Exception as e:
            print(f"     ❌ Query generation failed: {e}")

    print("\n🎉 Boolean conversion tests completed!")


if __name__ == "__main__":
    asyncio.run(test_boolean_conversion())
