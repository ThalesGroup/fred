"""
Example usage of search_assets tool
===================================

This script demonstrates how to use the search_assets tool to query
the Kuzzle assets collection with various filters.
"""

import asyncio
from postal_service_mcp_server.geosecur_client import create_default_client


async def main():
    """Example usage of the assets search functionality."""
    client = create_default_client()

    print("🔍 Testing Assets Search Tool\n")

    # Example 1: Search all assets (basic query)
    print("1. Search all assets (first 10):")
    result = await client.search_assets(size=10)
    if result["success"]:
        total = result["data"]["result"]["total"]
        hits = len(result["data"]["result"]["hits"])
        print(f"   ✅ Found {total} total assets, showing first {hits}")
        if hits > 0:
            first_asset = result["data"]["result"]["hits"][0]["_source"]
            print(
                f"   📦 Example asset: {first_asset.get('model')} - {first_asset.get('reference')}"
            )
    else:
        print(f"   ❌ Error: {result['error']}")

    print()

    # Example 2: Filter by model
    print("2. Search assets with model 'Semi':")
    result = await client.search_assets(model="Semi", size=5)
    if result["success"]:
        hits = len(result["data"]["result"]["hits"])
        print(f"   ✅ Found {hits} 'Semi' assets")
        for hit in result["data"]["result"]["hits"]:
            asset = hit["_source"]
            designation = asset.get("metadata", {}).get("designation", "N/A")
            print(f"   🚛 {asset.get('reference')} - {designation}")
    else:
        print(f"   ❌ Error: {result['error']}")

    print()

    # Example 3: Filter by designation
    print("3. Search by specific designation:")
    result = await client.search_assets(designation="428RNK75", size=5)
    if result["success"]:
        hits = len(result["data"]["result"]["hits"])
        print(f"   ✅ Found {hits} assets with designation '428RNK75'")
        for hit in result["data"]["result"]["hits"]:
            asset = hit["_source"]
            model = asset.get("model", "N/A")
            active = asset.get("metadata", {}).get("actif", "N/A")
            print(f"   📋 {asset.get('reference')} - Model: {model}, Active: {active}")
    else:
        print(f"   ❌ Error: {result['error']}")

    print()

    # Example 4: Filter by creation date (recent assets)
    print("4. Search assets created after 2024-01-01:")
    result = await client.search_assets(created_after="2024-01-01T00:00:00Z", size=5)
    if result["success"]:
        hits = len(result["data"]["result"]["hits"])
        print(f"   ✅ Found {hits} assets created after 2024-01-01")
        for hit in result["data"]["result"]["hits"]:
            asset = hit["_source"]
            created_at = asset.get("_kuzzle_info", {}).get("createdAt", 0)
            created_date = (
                datetime.fromtimestamp(created_at / 1000) if created_at else "N/A"
            )
            print(f"   📅 {asset.get('reference')} - Created: {created_date}")
    else:
        print(f"   ❌ Error: {result['error']}")

    print()

    # Example 5: Custom Elasticsearch DSL query
    print("5. Custom query - Active assets with position data:")
    custom_query = {
        "bool": {
            "must": [
                {"term": {"metadata.actif": "true"}},  # JSON boolean format
                {"exists": {"field": "measures.positionSpeed.values.position"}},
            ]
        }
    }
    result = await client.search_assets(query=custom_query, size=3)
    if result["success"]:
        hits = len(result["data"]["result"]["hits"])
        print(f"   ✅ Found {hits} active assets with position data")
        for hit in result["data"]["result"]["hits"]:
            asset = hit["_source"]
            position = (
                asset.get("measures", {})
                .get("positionSpeed", {})
                .get("values", {})
                .get("position", {})
            )
            lat = position.get("lat", "N/A")
            lon = position.get("lon", "N/A")
            print(f"   📍 {asset.get('reference')} - Position: ({lat}, {lon})")
    else:
        print(f"   ❌ Error: {result['error']}")

    print("\n🎉 Asset search examples completed!")


if __name__ == "__main__":
    # Note: You need to set GEOSECUR_USERNAME and GEOSECUR_PASSWORD environment variables
    # or the client will use defaults: geosecur-admin/pass
    from datetime import datetime

    asyncio.run(main())
