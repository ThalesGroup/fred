# GraphRAG MCP Server
Python microservice dedicated to **GraphRAG (Graph-based Retrieval-Augmented Generation)**,
exposing:
- an **MCP (Model Context Protocol) server** for LLMs
- **FastAPI endpoints** for ingestion, search, and graph exploration
This service relies on **Neo4j** and a **Graphiti-style** approach to transform
unstructured documents into a **knowledge graph usable by LLMs**.
---
## 🧠 GraphRAG & Graphiti
### What is GraphRAG?
**GraphRAG** is an evolution of classic RAG:
- ❌ Classic RAG: vector search → isolated chunks
- ✅ GraphRAG: semantic search **+ explicit relations**
Documents are transformed into:
- nodes (documents, chunks, concepts, entities)
- relationships (references, similarities, dependencies)
This enables:
- better **contextual understanding**
- **multi-hop navigation**
- more coherent and traceable answers
---
### Graphiti Usage

This project leverages the open-source framework Graphiti (https://github.com/getzep/graphiti
) to build and maintain a rich knowledge graph. This graph serves as a persistent memory for LLMs, enabling them to reason over interconnected data and provide more contextualized responses.
---
## 🗂️ Project Structure
```
contrib/
└── graphrag_mcp_server/ 
    │   ├── controller.py                 # FastAPI endpoints and MCP
    │   ├── graph_alimentation_pipeline.py# GraphRAG ingestion pipeline
    │   ├── service.py                    # Graphiti implementation
    │   └── utils.py                      # Helpers
    ├── main.py                           # FastAPI + MCP entrypoint
    ├── pyproject.toml
    ├── uv.lock
    ├── Makefile
    ├── .env.template
    └── .env
```
---
## 📥 Document ingestion (GraphRAG Pipeline)
Ingestion is done via the script:
```bash
uv run python graph_alimentation_pipeline.py 
--folder_path <path_to_data_folder>   # Path to the folder containing the data (default: data/)
--chunk_size <int>                    # Chunk size used for splitting text (default: 1500)
--chunk_overlap <int>                 # Chunk overlap used during splitting (default: 150)
```
### Pipeline workflow
1. Reads documents from `folder_path`
2. Performs semantic chunking of texts
3. Creates nodes:
   - Document
   - Chunk
4. Creates relationships:
   - Document → Chunk
   - Chunk → Chunk (continuity / similarity)
5. (Optional) Embeddings calculation
6. Inserts into Neo4j
Each run can:
- enrich an existing graph
- add new documents
- be replayed idempotently

WARNING: This task is labor-intensive and may require significant time and a substantial number of OpenAI tokens to complete.
---
## ⚙️ Configuration
Copy the template:
```bash
cp .env.template .env
```
Main variables:
```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=changeme

OPENAI_API_KEY=
```
---
## 📦 Installation
```bash
make install
```
- creates a virtualenv in `.venv`
- installs dependencies via `uv`
---
## ▶️ Run the MCP + FastAPI server
```bash
make run
```
Default:
- Host: `0.0.0.0`
- Port: `8080`
Access:
- Swagger: http://localhost:8080/docs
- OpenAPI: http://localhost:8080/openapi.json
---
## 🌐 MCP (Model Context Protocol)
The MCP server allows LLMs to:
- query the Neo4j graph
- perform multi-hop searches
- retrieve structured context
The graph becomes a **long-term memory** exploitable by LLM agents.
---
## 🧪 Philosophy
- Graph first
- LLM as reasoner
- Neo4j as long-term memory
---
## 📝 License
Internal / experimental project.
