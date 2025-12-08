### v1.0.7

_Release date: 2025-12-06_

This release brings in major improvments to go production with rag agents. Rag agents such as Rico
expose a new switch for the user to easily choose to search in the corpus or not. Keyword selection has
been added as an option.

#### Features

- major improvments including the rag expert (#874)
- make mcp & agent deletion persistent accross redeployments (#872)
- make all files starting with ignore\_ ignored by git

### v1.0.6

_Release date: 2025-12-04_

image in preview doc versionning and clean delete

#### Features

- improve robustness of UI and audit with many documents (#873)
- Update tabular controller for security and performance issues (#868)

#### Bug fixes

- delete documents cleanly in all backend storeage (#870)

### v1.0.5

_Release date: 2025-12-03_

mcp hub

#### Features

- Add mcp servers store and stdio support (#863)

#### Bug fixes

- Fix selected mcp servers (#865)
- fix chart values mcp.servers with id and name (#861)

### v1.0.4

_Release date: 2025-12-01_

Internal release

### v1.0.3

_Release date: 2025-12-01_

opensearch mapping tolerance

#### Features

- improve error handling with respect to guardrails (#860)
- display mcp servers as cards with switches (#848)
- Add vectors and chunks visualizations in Datahub (#852)
- give agents a mini filesystem dev local prod minio with basic list read write delete capabilities (#835)

#### Bug fixes

- Fix agentfs (#849)
- Non recursive doc count in DocumentTreeLibrary (#858)
- fixe the nw chunk vector UI when security is enabled (#856)
- Add back role in agent selector chip and improve layout (#854)

### v1.0.2

_Release date: 2025-11-27_

official opensearch support with documentation

#### Features

- Add documents count for collection (#838)
- Improve logo rendering (#837)
- improve pipline drawer and add descriptions to processors (#833)
- add a neo4j mcp connecteur to help support graph based rag strategies (#812)
- change mcp agent to be a more generic agent (#829)
- fred academy changes after the 2011 hackathon (#828)
- adapt configuration of values.yaml for openfga (#822)
- add an academy streetmap agent (#823)

#### Bug fixes

- fixe config file env variable regression (#843)
- fix missing async functions for ingestion (#832)

### v1.0.1

_Release date: 2025-11-19_

Internal release : v1.0.1

### v1.0.0

_Release date: 2025-11-03_

Major release aligning the codebase with the latest LangChain versions.
This version supersedes v0.0.9 and enables access to the newest LLM ecosystem capabilities.

#### Features

- 734 use the latest stable langchain langraph version (#737)
