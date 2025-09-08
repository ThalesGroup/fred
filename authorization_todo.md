# Authorization Implementation Todo List

## Commands to list files

```bash
# Find controller files (excluding venv)
find /home/fmuller/Documents/fred-universe/fred -path "*/.venv" -prune -o -path "*/__pycache__" -prune -o -path "*/node_modules" -prune -o -name "*controller*.py" -print

# Find service files (excluding venv)  
find /home/fmuller/Documents/fred-universe/fred -path "*/.venv" -prune -o -path "*/__pycache__" -prune -o -path "*/node_modules" -prune -o -name "*service*.py" -print
```

## Agentic Backend (3/5)

### Agents
- [X] `agentic_backend/app/core/agents/agent_controller.py`
- [X] `agentic_backend/app/core/agents/agent_service.py`

### Chatbot
- [ ] `agentic_backend/app/core/chatbot/chatbot_controller.py`

### Feedback
- [X] `agentic_backend/app/core/feedback/controller.py`
- [X] `agentic_backend/app/core/feedback/service.py`

### Monitoring
- [X] `agentic_backend/app/core/monitoring/monitoring_controller.py`
- [X] `agentic_backend/app/core/monitoring/monitoring_service.py`

### Prompts
- [X] `agentic_backend/app/core/prompts/controller.py`

## Knowledge Flow Backend (10/12)

### Catalog
- [X] `knowledge_flow_backend/app/features/catalog/controller.py`
- [X] `knowledge_flow_backend/app/features/catalog/service.py`

<!-- 
### Code Search
- [ ] `knowledge_flow_backend/app/features/code_search/controller.py`
- [ ] `knowledge_flow_backend/app/features/code_search/service.py` 
-->

### Content
- [X] `knowledge_flow_backend/app/features/content/controller.py`
- [X] `knowledge_flow_backend/app/features/content/service.py`

### Ingestion
- [X] `knowledge_flow_backend/app/features/ingestion/controller.py`
- [X] `knowledge_flow_backend/app/features/ingestion/service.py`

### Metadata
- [X] `knowledge_flow_backend/app/features/metadata/controller.py`
- [X] `knowledge_flow_backend/app/features/metadata/service.py`

### Pull
- [X] `knowledge_flow_backend/app/features/pull/controller.py`
- [X] `knowledge_flow_backend/app/features/pull/service.py`

### Resources
- [X] `knowledge_flow_backend/app/features/resources/controller.py`
- [X] `knowledge_flow_backend/app/features/resources/service.py`

### Scheduler
- [X] `knowledge_flow_backend/app/features/scheduler/controller.py`

### Tabular
- [X] `knowledge_flow_backend/app/features/tabular/controller.py`
- [X] `knowledge_flow_backend/app/features/tabular/service.py`

### Tag 
- [x] `knowledge_flow_backend/app/features/tag/controller.py`
- [x] `knowledge_flow_backend/app/features/tag/service.py`

### Vector Search
- [X] `knowledge_flow_backend/app/features/vector_search/controller.py`
- [X] `knowledge_flow_backend/app/features/vector_search/service.py`

### KPI
- [X] `knowledge_flow_backend/app/features/kpi/kpi_controller.py`

### Monitoring
- [X] `knowledge_flow_backend/app/features/kpi/opensearch_controller.py`
- [X] `knowledge_flow_backend/app/core/monitoring/monitoring_controller.py`


## Other:

- [X] Remove all `status_code=500`
- [ ] check if `_: KeycloakUser = Depends(get_current_user)` remain
- [ ] check for `TODO_USER_REAL_USER`