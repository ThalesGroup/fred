"""
Example usage of the MCP search_assets tool
===========================================

This script demonstrates how to test the search_assets tool through the MCP server
using the MCP SDK client functionality.
"""

import asyncio
import os


async def test_search_assets_tool():
    """Test the search_assets MCP tool with various scenarios."""
    print("🧪 Testing search_assets MCP Tool\n")

    # Set environment variables if not already set
    if not os.getenv("GEOSECUR_USERNAME"):
        os.environ["GEOSECUR_USERNAME"] = "geosecur-admin"
    if not os.getenv("GEOSECUR_PASSWORD"):
        os.environ["GEOSECUR_PASSWORD"] = "pass"

    # Import and test the function directly since we're in the same process
    from postal_service_mcp_server.server_mcp import search_assets

    try:
        # Test 1: Basic search (all assets, limited to 5)
        print("1. Testing basic search (first 5 assets):")
        result = await search_assets(size=2000)

        if result.get("success"):
            total = result["data"]["result"]["total"]
            hits = len(result["data"]["result"]["hits"])
            print(f"   ✅ Success! Found {total} total assets, showing {hits}")

            if hits > 0:
                first_asset = result["data"]["result"]["hits"][0]["_source"]
                print(
                    f"   📦 Example: {first_asset.get('model')} - {first_asset.get('reference')}"
                )
        else:
            print(f"   ❌ Failed: {result.get('error')}")

        print()

        # Test 2: Search by model
        print("2. Testing search by model 'Semi':")
        result = await search_assets(model="Semi", size=3)

        if result.get("success"):
            hits = len(result["data"]["result"]["hits"])
            print(f"   ✅ Found {hits} 'Semi' assets")

            for hit in result["data"]["result"]["hits"]:
                asset = hit["_source"]
                ref = asset.get("reference", "N/A")
                designation = asset.get("metadata", {}).get("designation", "N/A")
                print(f"   🚛 {ref} - {designation}")
        else:
            print(f"   ❌ Failed: {result.get('error')}")

        print()

        # Test 3: Custom Elasticsearch query
        print("3. Testing custom query (assets with position data):")
        custom_query = {
            "bool": {
                "must": [
                    {"exists": {"field": "measures.positionSpeed.values.position"}}
                ]
            }
        }
        result = await search_assets(query=custom_query, size=2)

        if result.get("success"):
            hits = len(result["data"]["result"]["hits"])
            print(f"   ✅ Found {hits} assets with position data")

            for hit in result["data"]["result"]["hits"]:
                asset = hit["_source"]
                ref = asset.get("reference", "N/A")
                position_data = asset.get("measures", {}).get("positionSpeed", {})
                if position_data:
                    position = position_data.get("values", {}).get("position", {})
                    lat = position.get("lat", "N/A")
                    lon = position.get("lon", "N/A")
                    print(f"   📍 {ref} - Position: ({lat}, {lon})")
        else:
            print(f"   ❌ Failed: {result.get('error')}")

        print()

        # Test 4: Error handling - invalid size
        print("4. Testing error handling (invalid size):")
        result = await search_assets(size=15000)  # Too large

        if not result.get("success"):
            print(f"   ✅ Correctly handled error: {result.get('error')}")
        else:
            print("   ⚠️  Expected error but got success")

        print()

        # Test 5: Date filter test
        print("5. Testing date filter (created after 2023-01-01):")
        result = await search_assets(created_after="2023-01-01T00:00:00Z", size=2)

        if result.get("success"):
            hits = len(result["data"]["result"]["hits"])
            print(f"   ✅ Found {hits} assets created after 2023-01-01")

            for hit in result["data"]["result"]["hits"]:
                asset = hit["_source"]
                ref = asset.get("reference", "N/A")
                created_at = asset.get("_kuzzle_info", {}).get("createdAt", 0)
                if created_at:
                    from datetime import datetime

                    created_date = datetime.fromtimestamp(created_at / 1000)
                    print(
                        f"   📅 {ref} - Created: {created_date.strftime('%Y-%m-%d %H:%M:%S')}"
                    )
        else:
            print(f"   ❌ Failed: {result.get('error')}")

        print("\n🎉 All search_assets tool tests completed!")

    except Exception as e:
        print(f"❌ Test failed with exception: {str(e)}")
        import traceback

        traceback.print_exc()


async def main():
    """Main test runner."""
    await test_search_assets_tool()


if __name__ == "__main__":
    asyncio.run(main())
