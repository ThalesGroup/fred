# Deployment Guide – OpenSearch Requirements for Fred

**Use this guide only if you choose OpenSearch as your vector backend.**  
Default dev mode uses SQLite + ChromaDB; production can use PostgreSQL/pgvector instead of OpenSearch. If you do pick OpenSearch, the constraints below are **mandatory**; otherwise Fred will raise a `ValueError` at startup and **refuse to run**.

---

# Table of Contents

1. [Overview](#1-overview)
2. [Index Requirements for Vector Search](#2-index-requirements-for-vector-search)  
   2.1 [Quick Summary for DevOps](#21-quick-summary-for-devops)  
   2.2 [Supported OpenSearch Versions](#22-supported-opensearch-versions)  
   2.3 [Canonical Index Mapping Example](#23-canonical-index-mapping-example)  
   2.4 [Validation Logic (What Fred Checks Internally)](#24-validation-logic-what-fred-checks-internally)  
   2.5 [Why `metadata.tag_ids` Must Be a Keyword Field](#25-why-metadatatag_ids-must-be-a-keyword-field)  
   2.6 [Migration Guidance for Legacy Indices](#26-migration-guidance-for-legacy-indices)

---

# 1. Overview

When configured for OpenSearch, Fred relies on **OpenSearch 2.x** as its vector database in production.  
This document details the **mandatory mapping and settings** your DevOps team must apply when preparing an OpenSearch cluster.

Fred performs **fail-fast, strict validation** of these requirements.  
If any mismatch is detected (dimension, method, space type, metadata fields…), Fred will:

- log a clear error,  
- raise a `ValueError`, and  
- **refuse to start**.

---

# 2. Index Requirements for Vector Search

## 2.1 Quick Summary for DevOps

To run Fred with OpenSearch, you must configure all vector indices with:

1. **OpenSearch version**
   - Must be **OpenSearch 2.x**
   - Recommended: **≥ 2.11**
   - Optimal (but optional): **≥ 2.19** (for `knn.filter` support)

2. **KNN index settings**
   - Field type: `knn_vector`
   - Method:
     - `engine = "lucene"`
     - `space_type = "cosinesimil"`
     - `name = "hnsw"`
   - Settings:
     ```json
     "settings": {
       "index": {
         "knn": true
       }
     }
     ```

3. **Vector dimension**
   - Must match the embedding model:
     - `text-embedding-3-large` → **3072**
     - `text-embedding-3-small` → **1536**
     - `text-embedding-ada-002` → **1536**

4. **Metadata mapping: `metadata.tag_ids`**
   - **Required:**
     ```json
     "tag_ids": { "type": "keyword" }
     ```
   - **Forbidden (legacy):**
     ```json
     "tag_ids": {
       "type": "text",
       "fields": { "keyword": { "type": "keyword" } }
     }
     ```
   - Reason: Fred uses exact UUID matches; `text` fields break them.

5. **Startup validation**
   - Fred validates index compatibility on startup.
   - If incompatible → **startup fails** with a detailed error.

---

## 2.2 Supported OpenSearch Versions

Fred uses OpenSearch’s **Lucene KNN engine**:

- Supported on **OpenSearch 2.x**
- Legacy `nmslib` engine is **not supported**
- Supported space types:
  - `cosinesimil` (required)
- Unsupported space types:
  - `l2`
  - `euclidean`

### Why OpenSearch 2.19+ is optional

Fred detects if `knn.filter` is available:

- If **≥ 2.19**, uses native `knn.filter`
- If **< 2.19**, automatically falls back to `bool + knn`
- No configuration change needed

---

## 2.3 Canonical Index Mapping Example (3072-dim)

This mapping is valid for `text-embedding-3-large`.  
For other models, only `dimension` changes.

```json
PUT vector-index-3-large
{
  "settings": {
    "index": {
      "knn": true,
      "number_of_shards": 1,
      "number_of_replicas": 0
    }
  },
  "mappings": {
    "dynamic": false,
    "properties": {

      "text": {
        "type": "text",
        "fields": {
          "keyword": { "type": "keyword", "ignore_above": 256 }
        }
      },

      "vector_field": {
        "type": "knn_vector",
        "dimension": 3072,
        "method": {
          "name": "hnsw",
          "engine": "lucene",
          "space_type": "cosinesimil",
          "parameters": {
            "ef_construction": 512,
            "m": 16
          }
        }
      },

      "metadata": {
        "type": "object",
        "dynamic": false,
        "properties": {
          "document_uid": { "type": "keyword" },
          "document_name": {
            "type": "text",
            "fields": { "keyword": { "type": "keyword", "ignore_above": 256 } }
          },

          "title":          { "type": "text", "fields": { "keyword": { "type": "keyword", "ignore_above": 256 } } },
          "author":         { "type": "text", "fields": { "keyword": { "type": "keyword", "ignore_above": 256 } } },

          "created":        { "type": "date" },
          "modified":       { "type": "date" },

          "chunk_index":    { "type": "long" },
          "chunk_uid":      { "type": "keyword" },

          "section":        { "type": "text", "fields": { "keyword": { "type": "keyword", "ignore_above": 256 } } },

          "tag_ids":        { "type": "keyword" },   // REQUIRED

          "mime_type":      { "type": "keyword" },
          "language":       { "type": "keyword" }
        }
      }
    }
  }
}
