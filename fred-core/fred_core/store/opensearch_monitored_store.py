# app/core/stores/opensearch/base_opensearch_store.py

from typing import Dict
from opensearchpy import OpenSearch

class BaseOpenSearchStoreMixin:
    def report_index_metrics(self, client: OpenSearch, index_name: str) -> Dict[str, int]:
        """
        Returns a dictionary of basic index stats: document count, deleted docs, store size.
        """
        try:
            stats = client.indices.stats(index=index_name)
            primary = stats["indices"][index_name]["primaries"]
            total = stats["indices"][index_name]["total"]

            return {
                "docs_count": total["docs"]["count"],
                "docs_deleted": total["docs"]["deleted"],
                "store_size_in_bytes": total["store"]["size_in_bytes"],
                "primary_store_size_in_bytes": primary["store"]["size_in_bytes"],
            }
        except Exception as e:
            return {"error": str(e)}
