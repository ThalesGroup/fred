# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

Fred is a production-ready multi-agent AI platform with three main components:
- **Agentic Backend** (FastAPI + LangGraph) - Multi-agent orchestration
- **Knowledge Flow Backend** (FastAPI) - Document ingestion and vector search  
- **React Frontend** - User interface

### Development Setup
1. **Prerequisites**: Python 3.12.8, Node 22.13.0, Make
2. **API Key**: Add `OPENAI_API_KEY=sk-...` to both backend `config/.env` files
3. **Start services** in separate terminals:
   ```bash
   cd agentic_backend && make run      # Port 8000
   cd knowledge_flow_backend && make run # Port 8111  
   cd frontend && make run             # Port 5173
   ```

## Common Commands

### Agentic Backend (`agentic_backend/`)
- `make run` - Start FastAPI server with hot reload on port 8000
- `make test` - Run pytest with coverage report
- `make clean` - Remove virtualenv and build artifacts
- `make list-tests` - List all available tests
- `make test-one TEST=path::to::test` - Run specific test

### Knowledge Flow Backend (`knowledge_flow_backend/`)
- `make run` - Start FastAPI server with hot reload on port 8111
- `make run-worker` - Start Temporal ingestion worker (requires Temporal daemon)
- `make test` - Run pytest with coverage report  
- `make lint` - Run ruff linter
- `make lint-fix` - Auto-fix linting issues
- `make format` - Format code with ruff
- `make sast` - Run bandit security analysis
- `make code-quality` - Run pre-commit checks

### Frontend (`frontend/`)
- `make run` - Start Vite dev server on port 5173
- `make format` - Format codebase with Prettier
- `make update-knowledge-flow-api` - Update RTK Query hooks from backend OpenAPI (requires backend running)

## Architecture Overview

### Multi-Agent System (Agentic Backend)

**Core Framework**: LangGraph with specialized expert agents coordinated by a Leader agent.

**Key Agents**:
- `Georges` - General-purpose reasoning and coordination
- `DocumentsExpert` - Document analysis via MCP server (knowledge-flow backend)  
- `Tessa` - Data analysis via MCP server (knowledge-flow backend)
- `RagsExpert` - RAG-based document search and retrieval
- `MonitoringExpert` - System observability and metrics
- `JiraExpert` - Jira integration (via MCP server)
- `K8SOperatorExpert` - Kubernetes operations (via MCP server)

**Agent Configuration**: Agents defined in `agentic_backend/config/configuration.yaml` with enable/disable flags, MCP server connections, and model overrides.

**MCP Integration**: Agents connect to Model Context Protocol servers for external tool access (Jira, Kubernetes, knowledge management).

### Knowledge Management (Knowledge Flow Backend)

**Document Processing Pipeline**:
1. **Input Processors** - Parse files (.pdf, .docx, .csv, .txt, .md, .pptx, .xlsm) into structured documents
2. **Output Processors** - Route to vectorization (text) or tabular analysis (structured data)
3. **Storage Layers** - Content, metadata, vectors, and tabular data with pluggable backends

**Storage Backends** (configurable):
- **Content**: Local filesystem, MinIO, Google Cloud Storage
- **Metadata**: Local JSON (deprecated), DuckDB, OpenSearch  
- **Vector**: In-memory (dev), OpenSearch, Weaviate
- **Tabular**: DuckDB

**Scheduling**: Temporal workflow engine for document ingestion pipelines.

### Frontend Architecture

**Tech Stack**: React 18 + TypeScript + Vite + Material-UI + Redux Toolkit

**Key Features**:
- Multi-agent chat interface with streaming responses
- Document library management with preview and bulk operations
- Kubernetes resource analysis (FrugalIt module) - toggled by `enableK8Features` flag
- Token usage monitoring and metrics dashboard
- Knowledge context/workspace management

**State Management**: 
- RTK Query for API calls with auto-generated hooks from OpenAPI specs
- Redux slices for global state (auth, settings, document management)
- Context providers for feature-specific state (ApplicationContext, FootprintContext, etc.)

## Configuration Files

- `.env` for secret (like `OPENAI_API_KEY`)
- `configuration.yaml` for everything else

**Agentic Backend** (`agentic_backend/config/configuration.yaml`):
- Agent definitions with enable/disable flags
- MCP server connections (SSE or STDIO transport)
- Model provider settings (OpenAI/Azure/Ollama)  
- Feature flags (`enableK8Features`, `enableElecWarfare`)
- Storage configurations (metrics, sessions, feedback)
- Kubernetes and security settings

**Knowledge Flow Backend** (`knowledge_flow_backend/config/configuration.yaml`):
- Input/output processor mappings by file extension
- Storage backend configurations (content, metadata, vector, tabular)
- Embedding provider settings
- Document source definitions (uploads, local docs, GitHub repos)
- Temporal scheduler settings

## Development Patterns

### Document Processing Extensions  
1. **Input Processors**: Add new file type support in `knowledge_flow_backend/app/core/processors/input/`
2. **Output Processors**: Custom processing logic in `knowledge_flow_backend/app/core/processors/output/`
3. Update processor mappings in `configuration.yaml`
4. Add file extension to frontend upload validation

### Frontend Feature Development
1. Check existing CLAUDE.md in `frontend/` directory for detailed frontend guidance
2. Use RTK Query for all API calls - regenerate hooks when backend changes
3. Follow Material-UI patterns for consistent theming
4. Add feature flags to control visibility of new modules
5. Implement proper loading states and error handling
6. For navigation, always use `<Link />` (from react-router) and never user `onClick` with `navigate` (as its create a poor user experience)
- When writing text, always use react-i18n library to translate and update the translation files: @src/locales/en/translation.json and @src/locales/fr/translation.json

### Frontend UI/UX Patterns
- To handle error, info or success in frontend, you can use `useToast` in @src/components/ToastProvider.tsx

### Testing Strategy
- **Backend**: Use pytest with async support, test agents in isolation

## Security & Production

- **Authentication**: Keycloak integration (can be disabled for development)
- **Secrets**: Never commit API keys - use `.env` files only
- **Storage**: Production deployments should use persistent backends (OpenSearch, MinIO)
- **Monitoring**: Built-in metrics collection and token usage tracking

## Debugging Tips

- **Agent Tracing**: Enable debug logging in configuration.yaml (`log_level: debug`)
- **MCP Server Issues**: Check SSE connection timeouts and server availability  
- **Frontend API Issues**: Use browser dev tools Network tab and Redux DevTools
- **Document Processing**: Check input processor logs for file parsing errors
- **Vector Search**: Verify embedding model consistency across ingestion and query