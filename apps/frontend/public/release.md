**v2.0.1** — 2026-06-28

- **Summary**

  Security milestone. As of this release, Fred's runtime security model is **final and
  solid**: each agent pod is the execution authority and authorizes every request itself —
  validating the Keycloak JWT and running a pod-side OpenFGA ReBAC check (audience and
  team-binding enforced). It introduces the opt-in `security.profile: c3` hardened posture
  (fail-closed: strict JWT issuer/audience validation, no no-security/mock-admin, ReBAC
  required). Alongside the security work it ships a native Google Cloud Storage content
  backend (Workload Identity), a new PDF extractor, evaluation-campaign support on the
  task/event-bus API, config-driven branding, and human-friendly chat tool-call traces.

- **Features**

  - Hardened runtime authorization model, now final: each agent pod authorizes every request via the Keycloak JWT + a pod-side OpenFGA ReBAC check, with audience and team-binding enforced (RUNTIME-07, #1862)
  - Opt-in `security.profile: c3` hardened posture — fail-closed strict JWT issuer/audience validation, no no-security/mock-admin, ReBAC required (RUNTIME-07, #1862)
  - Native Google Cloud Storage content backend via ADC / Workload Identity for the content store and virtual filesystem (#1805)
  - Evaluation-campaign support on the task and event-bus API (#1827)
  - Config-driven branding: frontend branding wired from `config_json` (#1842, #1851)
  - Scheduled live-stack validation of GKE releases via an admin self-test harness (VALID-02, #1837)

- **Improvements**

  - New PDF extractor for higher-fidelity ingestion (#1790)
  - Human-friendly tool-call labels in the chat trace (CHAT-12 / CHAT-14, #1816, #1824)
  - Durable agent runtime store on Postgres, replacing the ephemeral sqlite path (#1862)
  - Repeatable review protocol and audit signals; RFC/doc cleanup pass (#1841, #1849)
  - Remove dead frontend components and untrack the benchmark binary (#1856)
  - RFC for a deterministic Excel extraction pipeline (INGEST-02, #1845)
  - Flag AGPL dependency pending removal (#1846)

- **Bug Fixes**

  - Fix `values-local` mismatch with `schema.json` (config schema drift)
  - Fix full-width CSV markdown rendering in the attachments preview drawer
  - Fix Personal Team avatar shape hover styling
  - Use Mistral models for `configuration_worker.yaml`
  - Revert default knowledge-flow configuration to the public Mistral API
  - Fix typos in translation files

**v2.0.0** — 2026-06-24

- **Summary**

  Major release. This version establishes the **agentic pod** architecture: agents are
  now built and deployed as standalone services in their own repositories — the control
  plane discovers them, enrolls their agents, and routes execution to them, with no
  dependency on the Fred monorepo. It also ships an in-app KPI analytics dashboard, a
  substantially reworked chat UI (attachments, prompts, voice dictation, reasoning
  traces), a unified virtual filesystem with provenance, and a richer ingestion stack
  (audio/video transcription, faster PDF extraction). Helm packaging is hardened with
  generated config schemas and Gateway API support.

- **Features**

  - Agentic pod architecture — design and run agents as independent HTTP services in their own repository; the control plane is the sole authority for pod discovery and agent enrollment (see `docs/swift/SWIFT_ARCHITECTURE.md`)
  - KPI analytics dashboard — active users, conversations & messages, agents, resources (OBSERV-02, #1722)
  - Reworked chat UI: in-chat attachments and enhanced composer (#1712), wired-in prompt library (#1782), document picker and local MCP config (#1731)
  - Voice dictation in the managed chat composer (CHAT-11, #1769)
  - Model reasoning support with improved thought traces (#1770)
  - Unified virtual filesystem with bounded paginated reads and provenance (#1794, AGENT-FILESYSTEM)
  - AudioProcessor for audio/video transcription via faster-whisper (#1708)
  - Shared global base prompts for all default agents (#1696)
  - Mindmap agent and deeper mindmap rendering (FILES-02)

- **Improvements**

  - Switched the ingestion processor from pymupdf to pymupdf4llm for improved PDF-to-Markdown handling performance in Fast mode (#1626)
  - New medium and rich extractors for higher-fidelity ingestion (#1718)
  - Targeted similarity comparison search in knowledge-flow (#1778)
  - Helm: Gateway API HTTPRoute support (#1759), values.schema.json generated from backend config schemas (#1729), JSON-schema generation and CI validation (#1725)
  - Use control-plane auth settings for the frontend instead of config.json (#1750)
  - Reconcile abandoned tasks against Temporal and emit ingestion task events (OPS-04, #1763, #1776)

**v1.5.4** — 2026-05-11

- **Features**

  - Add markdown processor for chat attachments (#1593)
  - Expose metrics for prometheus scraping on control plane (#1592)
  - Add configurable upload warning alert to document upload drawer (#1597)

- **Bug Fixes**

  - Typo in link in mail to request to join a team (#1589)
  - Spurious langfuse error log (#1594)
  - Cannot read properties of undefined (reading 'toLowerCase') in TeamContentNavbar (#1609)

**v1.5.3** — 2026-05-03

- **Improvements**

  - Add capacity to specify custom RetryPolicy for Temporal activities (#1576)

- **Bug Fixes**

  - Fixed semantics versus hybrid default values (#1580)
  - Fixed runtime binding error in agentic when publishing KPIs (#1577)

**v1.5.2** — 2026-05-02

- **Features**

  - Streaming responses now enabled for all agent types — previously limited to v2 ReAct agents
  - Token usage metrics (`llm.tokens_input`, `llm.tokens_output`, `llm.tokens_total`) now emitted per streaming session for all agents

- **Bug Fixes**
  - Fix team identity not resolved in `_stream()`, causing KPI and conversation history to miss the personal team default

---

**v1.5.1** — 2026-05-01

- **Features**

  - Default search policy selector in agent creation form

- **Improvements**

  - Default search policy changed from semantic to hybrid
  - Human-readable agent names on all Prometheus metrics; consistent `agent_id` dimension across all KPI actors
  - New `llm.call_latency_ms` metric for per-model Grafana panels
  - Automatic retry on transient gateway errors for Mistral-hosted models
  - Clearer error messages on AI service unavailability (502 / 503)
  - Fix Langfuse observation latency unit (field is in seconds, not milliseconds)

- **Bug Fixes**
  - Fix SQL agent not listing tables when directly queried and responding in the wrong language
  - Fix DOCX embedded image processing to match PDF and PPTX behavior

**v1.5.0** — 2026-04-24

- **Features**

  - Allow knowledge base of agent to be scoped at agent creation
  - Add join team mail to link on the teams marketplace
  - Add mandatory CGU full screen modal (#1531)
  - Add rich PPTX multimodal on basic react agent v2 with vector search tool (#1529)
  - Add Vertex Model Garden for embedding models & update MODEL_CONFIGURATION.md (#1525)

- **Improvements**
  - Improve temporal worker concurrency and add appropriate metrics (#1521)

**v1.4.1** — 2026-04-13

- **Bug Fixes**
  - Typo on personal team name
  - Public team displayed in sidebar even when you're not a member
  - Personal conversation not listed in personal space
  - Image link in markdown render using internal Minio address instead of ingress

**v1.4.0** — 2026-04-10

- **Summary**

  This release introduces the first full v2 agent stack for production use (ReAct + Graph), with a cleaner configuration model based on catalogs and a simplified agent creation flow. It keeps backward compatibility for existing v1 agents while preparing multimodal model selection (chat, language, embedding, image) through policy-based routing. It also ships a new Marketplace, team-scoped conversations, Alembic-based database migrations, and significant improvements to the ingestion pipeline and UI.

- **Features**

  - Add v2 ReAct profiles so a generic agent can be specialized with default prompt, MCP servers, and approval policy
  - Allow generic v2 ReAct agents to consume UI-configured MCP tools at runtime
  - Add a geo demo v2 profile and structured geo/link capability support for ReAct tool outputs
  - Add the first executable GraphAgentDefinition runtime contract with typed state, node handlers, tool calls, HITL resume, and structured final output
  - Add catalog-based model routing policies with deterministic matching (`capability`/`purpose`/`operation` + team/user/agent scope)
  - Add dedicated catalog files for models, agents, and MCP servers (`models_catalog.yaml`, `agents_catalog.yaml`, `mcp_catalog.yaml`)
  - Add support for Human In the Loop for react agent (#1207)
  - Add Alembic to handle Postgres and Sqlite migrations across all backends (#1409, #1451, #1452)
  - Implement new navigation and frontend team separation (#1345)
  - Implement new team settings
  - Implement new user settings
  - Rework agent page
  - Add a marketplace menu with team exploration pages (#1410)
  - Scope conversations by teams and fix personal team workflow (#1462)
  - Setup branding in new UI (#1482)
  - Add Prometheus agent and related KF MCP endpoints (#1340)
  - Add Clickhouse as vector store (#1255)
  - Add support for VertexAI (#1254)
  - Add PostgreSQL checkpointer backend for durable agentic runs (#1281)
  - Add Fred filesystem completion (#1434)
  - Add vision PPTX enrichment pipeline (#1419)
  - Add stateless connection support with MCP protocol (#1417)

- **Improvements**

  - Move default v2 agent prompts to packaged Markdown resources
  - Move ReAct profile selection to agent creation so admins choose a starting profile or custom class up front
  - Replace the experimental graph endpoint with a dedicated v2 inspection endpoint and model
  - Improve MCP runtime resilience with retry and short backoff on transient connection failures
  - Improve the debug drawer with sanitized runtime context, grouping by exchange, per-exchange copy, and local scrolling
  - Keep startup compatibility: when catalogs are absent, runtime falls back to legacy `configuration.yaml` sections
  - Document Helm wiring for optional catalog mounts and env overrides
  - Remove A2A proxy registration/card flow from backend and UI to simplify the runtime surface
  - Added configurable start-to-close timeout for Temporal ingestion activities (#1307)
  - Full page OCR on medium PDF ingestion profile (#1444)
  - Improve PDF markdown extraction for medium/rich profiles (#1320)
  - Improve PPTX processor (#1349)
  - Remove unnecessary packages from knowledge-flow Docker image (#1258)
  - Split embedding processing into more batches (#1461)
  - Add metrics to knowledge-flow worker (#1450)
  - Implement correct delta streaming protocol (#1439)
  - Wrap AgentToolsSelection and TuningForm with memo to reduce lag in agent form (#1479)

- **Bug Fixes**
  - Fix duplicate assistant bubbles during streamed tool-based exchanges
  - Fix transient duplicate user messages during optimistic send and server echo reconciliation
  - Fix restored ReAct tool-call history so multi-turn conversations resume correctly after tool usage
  - Fixed OpenSearch vectorization failures on large ingestions by splitting document indexing into multiple batches that respect bulk_size (#1299)
  - Fixed ingestion regression when using the standalone mode (#1329)
  - Fix support for docling_parse PDF backend due to deprecation of dlparse_v4 (#1309)
  - Fix missing image processors in local and production deployments (#1326, #1327)
  - Fix missing i18n translation keys (#1404, #1319)
  - Fix ingestion error when embeddings count exceeds bulk size (#1305)
  - Fix automatically create vector index with vector dims inferred from embedding model (#1289)
  - Fix starlette file header encoding with latin-1 codec (#1493)

**v1.3.0** — 2026-03-04

- **Summary**

  This release introduces real-time agent response streaming in the UI and adds Human In the Loop support for react agents. It also hardens production deployments by removing exposed API documentation endpoints and fixes file download permissions and image rendering issues in production mode.

- **Features**

  - Stream agent response in the UI
  - Add support for Human In the Loop for react agent (#1207)

- **Improvements**

  - Remove FastAPI /docs /redoc /openapi.json from production images (#1242)
  - improve opensearchops mcp endpoints for cluster debugging new routes better route description (#1239)

- **Bug Fixes**
  - Fix permission problem when downlading file generated by agents (like Kelia) in production mode (#1238)
  - Fix images not displayed in documents markdown preview in production mode (#1245)

**v1.2.7** — 2026-02-26

- **Summary**

  This release focuses on reliability and security. Mermaid diagram rendering has been significantly improved with robust error handling and clean fallbacks. Vector search security is tightened so agents only access vectors they are authorized to see.

- **Improvements**

  - Improve Mermaid diagram rendering with clean fallback and scoped HTML checks (#1206,#1211)
  - Create a proper KF markdown media client method and fix sync function calls (#1214)

- **Bug Fixes**
  - Fix vector search returning all vectors when agent has no authorized tags (#1225)
  - Fix editor permission to receive ingestion updates (#1212)

**v1.2.6** — 2026-02-22

- **Summary**

  This release focuses on stability, offline compatibility, and team features. It introduces the Aegis agent, improves offline deployment support (Dockerfiles, knowledge flow), and refines team-based vector search and agent selection. It also includes significant updates to dependencies (removing unstructured) and fixes for PDF loading and SVG processing.

- **Features**

  - Add Aegis agent (#1166,#1182)
  - Add k3d configuration (#1174)
  - Add team filter in vector search and rework agent selection with team (#1158)
  - Improve pipeline initialisation and deliver new test tool (#1152)
  - Viewers can CRUD attachments (#1176)

- **Improvements**

  - Remove unstructured dependency and update dependencies for security (#1202)
  - Make knowledge flow and Dockerfiles work in truly offline environments (#1163,#1184)
  - Move cv skill detection and refactor agent architecture (#1185)
  - Rename default agentic secret m2m env var (#1186)
  - Config storage for Raph & Kellia and move to async utils (#1197)

- **Bug Fixes**
  - Fix failure of pdf loading (#1192)
  - Fix svg images breaking ingestion process (#1172)
  - Fix metric kpi loading regression (#1154)
  - Fix conversation switches and remove agent_name (#1156)
  - Fix frontend settings in helm values (#1171)
  - Fix crossencoder_model in helm values
  - Fix cannot read properties of undefined in coming soon page (#1159)

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
  d

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
