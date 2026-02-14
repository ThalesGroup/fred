**v1.2.5** — 2026-02-14

- **Summary**

  This releases brings in key performance improvements. Temporal is now fully supported
  for running ingestion workloads. Knowledge flow and agentic have been rendered
  asynchronous and equipped with additional performance metrics.

  In terms of feature, Fred now allow teams to share corpus and agents.
  Fred ships with an integrated benchmark tools.
  Last, psotgres (sqlite or real postgres) is now used for persistence. Support for
  duckdb has been removed.

- **Features**

  - add missing kpi (#1129)
  - add frontend properties to hide enable/disable agent button (#1139)
  - allow admin to set class path of agent when creating them (#1133)
  - Improve jira agent (#1137)
  - make agent private + allow team to own agents (#1114)
  - Use temporal as a processing backend for general corpus & fast(attachments) pipeline execution (#1084)
  - make all postgres connectors truly async (#1104)

- **Improvements**

  - Execute temporal workflows concurrently and handle errors properly (#1127)
  - add option to pass minio public url + use it to create presigned url (#1111)

- **Bug Fixes**

  - fixed temporal in distributed settings (#1146)
  - refactor agent manager to work with multi workers/replicas (#1122)

**v1.2.4** — 2026-02-02

- **Summary**

  This relase brings in two major features: the support for interrupt to cleanly implement human in the loop
  and a clean support for a shared filesystem, exposde to agnt using a well defined workspace
  concept. This allow configuration files or working files to be cleanly exchanged between admins, users
  and agents.

- **Features**

  - new KPIs and bench logging, finer grain http outgoing configurability (#1061)

- **Improvements**

  - handling of token expiry (#1061)

---

**v1.2.3** — 2026-01-25

- **Summary**
  This release bring in new KPIs, a bench tools to stress the agentic fred backend. As part of KPIs and performance improvements,
  the various langchain dependencies have been updated:

  - "langchain>=1.2.7",
  - "langchain-community>=0.4.1",
  - "langchain-mcp-adapters>=0.2.1",
  - "langchain-core>=1.2.7",
  - "langchain-ollama>=1.0.1",
  - "langchain-openai>=1.1.7",
  - "langchain-text-splitters>=1.1.0",
  - "langchain-postgres>=0.0.16",

- **Features**

  - new KPIs and bench logging, finer grain http outgoing configurability (#1059)
  - new bench tools (#1049)
  - new core temporal agentic API (#1038)

- **Improvements**

  - use of shared http clients (#1055)
  - reshaping of prometheus metrics (#1023)
  - updated langchain version to latest (#1059)
  - improve applicative KPIs (#1066)

**v1.2.2** — 2026-01-23

- **Summary**
  This release bring in UI improvments in particular allow agents to have the UI display their options
  on a nicer and more ergonomic conversation right side panel.

  - **Features**

    - allow per document search (#1022)
    - leverage unstructured for attachement files processing (#1012)
    - added Log Genius agent (#1004)

  - **Bug fixes**

    - fixe the delete UI issue not refreshin (#1026)
    - UI improvements (#1015,#999,#1014)

**v1.2.1** — 2026-01-16

- **Features**

  - add favicon override front setting (#987)

- **Improvements**

  - use kpi store to expose prometheus metrics (#983)
  - batch "load more" calls to max 500 docs and paginate long user chat messages (#975)

- **Bug fixes**
  - fix the dot loader (#986)
  - fix UI leak when selecting a library affecting other conversations (#981)

---

**v1.2.0** — 2026-01-10

This release brings in a major UI revamp. This revamp has been proposed and designed
by the Prism team to make Fred evolve towards a state-of-the-art agentic orchestration platform.

- **Improvements**

  - Side bar now integrated into the main left side bar. (#976)

---

**v1.1.3** — 2026-01-09

- **Summary**

  This release brings in kpi, language and logging improvments to facilitate operations.
  It also leverage the rebac feature to start proposing a clean sresource sharing policy.
  Please not the rebac coverage is not yet complete and will be fully delivered in a future
  major release.

- **Improvements**

  - reduce log verbosity (#963)
  - log and update the vector search mapping for attachements required fields (#964)
  - take into account frontend language (#962)

- **Bug fixes**
  - fixed the missing attachement file number in the UI (#966)
  - fixed the error preview attached files from the 'My Files' area (#965)
  - removed the display button fro user files list (#969)
  - prevent viewer to share libraries in turn with others (#972)

---

**v1.1.2** — 2026-01-08

- **Summary**
  - Dynamic ReAct agents now support source citations, and agent code inspection works for all agents (#950).
- **Features**

  - Add source citation support to dynamic ReAct agents (#950)
  - Fix agent code inspection to display source for all agents (#950)

- **v1.1.1** — 2026-01-07

  - **Summary**
    - This release completes the support for per conversation attachements, and improve the capabilities of dynamic agents.
  - **Features**
    - Dynamic agent can now leverage the chat options to benefit from depp searchn attachements library scoping (#941)
    - New duckdb and opensearch connectors to manage per conversation attachments (#941)

- **v1.1.0** — 2026-01-04
  - **Summary**
    - New PostgreSQL/pgvector option so Fred can run fully without OpenSearch, plus in-UI Mermaid rendering for agent replies.
    - This version provides full support of per conversation attachments. Attached files are vectorized using lite markdown processors.
    - The Rico agent expose now a first deep search capability that leverage the Rico Senior document agent.
  - **Features**
    - Add a Postgres-first deployment path (metadata + vectors) across knowledge-flow and agentic backends (#933)
    - Surface vector backend details (pgvector or OpenSearch) in the admin views (#933)
    - Rag support for per conversation attachements files
  - **Bug fixes**
    - Fix Mermaid diagrams rendering in chat by generating safe SVG previews and stabilizing layout (#933)
  - **Impact**
    - Teams can choose a single Postgres stack for persistence; diagrams now display cleanly without layout jumps.

---

- **v1.0.9** — 2025-12-09
  - **Summary**
    - Corrected the OpenSearch k-NN query to use the proper `{ knn: … }` structure with filters inside the k-NN block, avoiding sub-optimal or inconsistent results.
  - **Features**
    - Select multiple chat contexts (#890)
    - Provide feedback on downloads (#892)
  - **Bug fixes**
    - Fixed the OpenSearch vector search query (#888)
  - **Impact**
    - Improved relevance, faster filtered searches, and full compatibility with OpenSearch 2.19+.

---

- **v1.0.8** — 2025-12-08
  - **Summary**
    - Added a selector for corpus-only, general-knowledge-only, or hybrid search for RAG agents.

---

- **v1.0.7** — 2025-12-06
  - **Summary**
    - Production-hardening for RAG agents (e.g., Rico) with corpus toggles and keyword selection.
  - **Features**
    - Major improvements including the RAG expert (#874)
    - Persist MCP & agent deletion across redeployments (#872)
    - Ignore all files starting with `ignore_` in git

---

- **v1.0.6** — 2025-12-04
  - **Summary**
    - Preview image versioning and cleaner deletion flows.
  - **Features**
    - Improve robustness of UI and audit with many documents (#873)
    - Update tabular controller for security and performance issues (#868)
  - **Bug fixes**
    - Delete documents cleanly in all backend storage (#870)

---

- **v1.0.5** — 2025-12-03
  - **Summary**
    - MCP hub improvements.
  - **Features**
    - Add MCP servers store and stdio support (#863)
  - **Bug fixes**
    - Fix selected MCP servers (#865)
    - Fix chart values `mcp.servers` with id and name (#861)

---

- **v1.0.4** — 2025-12-01
  - **Summary**
    - Internal release.

---

- **v1.0.3** — 2025-12-01
  - **Summary**
    - OpenSearch mapping tolerance updates.
  - **Features**
    - Improve error handling with respect to guardrails (#860)
    - Display MCP servers as cards with switches (#848)
    - Add vectors and chunks visualizations in Datahub (#852)
    - Give agents a mini filesystem (dev local, prod MinIO) with list/read/write/delete (#835)
  - **Bug fixes**
    - Fix agentfs (#849)
    - Non-recursive doc count in DocumentTreeLibrary (#858)
    - Fix the new chunk vector UI when security is enabled (#856)
    - Add back role in agent selector chip and improve layout (#854)

---

- **v1.0.2** — 2025-11-27
  - **Summary**
    - Official OpenSearch support with documentation.
  - **Features**
    - Add documents count for collection (#838)
    - Improve logo rendering (#837)
    - Improve pipeline drawer and add descriptions to processors (#833)
    - Add a Neo4j MCP connector to support graph-based RAG strategies (#812)
    - Change MCP agent to be a more generic agent (#829)
    - Fred academy changes after the 2011 hackathon (#828)
    - Adapt configuration of values.yaml for openfga (#822)
    - Add an academy streetmap agent (#823)
  - **Bug fixes**
    - Fix config file env variable regression (#843)
    - Fix missing async functions for ingestion (#832)

---

- **v1.0.1** — 2025-11-19
  - **Summary**
    - Internal release: v1.0.1.

---

- **v1.0.0** — 2025-11-03
  - **Summary**
    - Major release aligning the codebase with the latest LangChain versions; supersedes v0.0.9 and unlocks the newest LLM capabilities.
  - **Features**
    - Use the latest stable LangChain/LangGraph version (#737)
