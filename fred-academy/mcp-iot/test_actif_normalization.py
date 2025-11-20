#!/usr/bin/env python3
"""
Test script to verify actif parameter normalization in MCP server
===============================================================

This script tests the normalize_boolean function to ensure that the MCP server
can correctly handle both boolean and string values for the 'actif' parameter.
"""

import asyncio


async def test_actif_normalization():
    """Test that actif parameter normalization works correctly."""

    print("🧪 Testing actif Parameter Normalization\n")

    # Import the search_assets function
    from postal_service_mcp_server.server_mcp import search_assets

    # Test cases for actif parameter normalization
    test_cases = [
        # (input_value, expected_result, description)
        (True, True, "Python boolean True"),
        (False, False, "Python boolean False"),
        ("true", True, "String 'true' (lowercase)"),
        ("false", False, "String 'false' (lowercase)"),
        ("TRUE", True, "String 'TRUE' (uppercase)"),
        ("FALSE", False, "String 'FALSE' (uppercase)"),
        ("True", True, "String 'True' (capitalized)"),
        ("False", False, "String 'False' (capitalized)"),
    ]

    print("1. Testing valid actif values:")
    for input_val, expected, description in test_cases:
        try:
            # Test with minimal parameters and size=1 to avoid large requests
            result = await search_assets(actif=input_val, size=1)

            if result.get("success"):
                print(f"   ✅ {description}: {input_val} → Success")
            else:
                print(
                    f"   ❌ {description}: {input_val} → Failed: {result.get('error')}"
                )
        except Exception as e:
            print(f"   ❌ {description}: {input_val} → Exception: {str(e)}")

    print()

    # Test invalid cases
    invalid_test_cases = [
        (123, "Integer value"),
        ("maybe", "Invalid string"),
        ("yes", "Non-boolean string"),
        (None, "None value"),
        ([], "List value"),
        ({}, "Dict value"),
    ]

    print("2. Testing invalid actif values (should return errors):")
    for input_val, description in invalid_test_cases:
        try:
            result = await search_assets(actif=input_val, size=1)

            if not result.get("success"):
                error_msg = result.get("error", "Unknown error")
                if "Invalid actif parameter" in error_msg:
                    print(f"   ✅ {description}: {input_val} → Correctly rejected")
                else:
                    print(
                        f"   ⚠️  {description}: {input_val} → Unexpected error: {error_msg}"
                    )
            else:
                print(
                    f"   ❌ {description}: {input_val} → Should have failed but succeeded"
                )
        except Exception as e:
            print(f"   ❌ {description}: {input_val} → Unexpected exception: {str(e)}")

    print()

    # Test edge cases
    print("3. Testing edge cases:")
    edge_cases = [
        ("  true  ", "String with whitespace"),
        ("", "Empty string"),
        ("1", "String '1'"),
        ("0", "String '0'"),
    ]

    for input_val, description in edge_cases:
        try:
            result = await search_assets(actif=input_val, size=1)

            if result.get("success"):
                print(
                    f"   ✅ {description}: '{input_val}' → Success (treated as valid)"
                )
            else:
                error_msg = result.get("error", "Unknown error")
                print(f"   ⚠️  {description}: '{input_val}' → Rejected: {error_msg}")
        except Exception as e:
            print(f"   ❌ {description}: '{input_val}' → Exception: {str(e)}")

    print("\n🎉 actif parameter normalization tests completed!")


if __name__ == "__main__":
    asyncio.run(test_actif_normalization())
