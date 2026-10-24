# Agent sandbox: browser evidence on k3d

These screenshots come from real Fred conversations in `k3d-fred-secondary` on 24 October 2026. The test agent had only the `code_sandbox` capability. The guest used gVisor, SIG Agent Sandbox with zero warm replicas, and read-only rclone CSI mounts. The synthetic source files were uploaded to the team corpus or attached to a conversation. The approved Python image included `pypdf`, `python-docx`, `python-pptx`, `openpyxl`, `pandas` and `duckdb`.

Small 4 Reasoning and Medium 3.5 Reasoning used separate conversations. The Large 4 security probes used their own conversations. A screenshot of the chat and of the tool detail is retained for each scenario; later scenarios also have a screenshot scrolled to the tool output. These are observed local results, not proof of production isolation or a load test.

## Fresh cluster retest

After deleting and recreating `k3d-fred-secondary`, `make k3d-up` installed gVisor, SIG Agent Sandbox, rclone CSI and the broker without hand-editing resource names or persistent volumes. The documents image and file demo were installed with the factory `make` targets, then Fred was built and deployed from this branch. `make k3d-sandbox-smoke` passed Python, Bash, gVisor, a zero-replica warm pool and a read-only CSI file read. The first code tool in the fresh browser run took 5.9 seconds; subsequent tools in the same conversation took under one second. This is a single local observation, not a cold-start percentile.

The cluster inventory was checked with `kubectl --context k3d-fred-secondary get runtimeclass`, `kubectl --context k3d-fred-secondary get crds`, and `kubectl --context k3d-fred-secondary -n fred-sandbox get sandboxtemplates,sandboxwarmpools`. gVisor was available as `runsc`; Kata was not installed on this k3d cluster. Both sandbox warm pools had `DESIRED=0`. The rclone CSI controller and node pods were running in `fred-sandbox-csi`.

| Scenario | Observation | Chat | Tool detail |
| --- | --- | --- | --- |
| Small 4, selective corpus search | In a new conversation, the agent chose `search_files` on its own. It returned only the matching line at 8538 from the 1.1 MB corpus file, then answered in one sentence without source code or package details. | [Chat](65-selective-small-chat.png) | [Search criteria and match](65-selective-small-search-tool.png) |
| Medium 3.5, selective Excel lookup | In a separate conversation, the agent located the workbook by glob, filtered Lyon and Paris rows, and computed weighted margins of 41.22% and 38.02%. The final answer contained only those values. This run used five tools, including two attempts with no output; the previous exploratory run used eleven. These are single-run observations. | [Chat](66-selective-medium-xlsx-chat.png) | [File lookup](66-selective-medium-xlsx-search-tool.png), [calculation code](66-selective-medium-xlsx-code-tool.png), [result](66-selective-medium-xlsx-code-result.png) |
| Small 4, fresh team corpus | Bash `find` traversed the fixed `pages/block-00/block-00/page-0000` WebDAV tree; `grep -n` found `POLARIS-7319` on line 8538 with the correct owner, deadline and risk. | [Chat](60-fresh-small-paged-corpus-chat.png) | [Code](60-fresh-small-paged-corpus-tool.png), [result](60-fresh-small-paged-corpus-tool-result.png) |
| Small 4, same conversation, mounted Python skill | Read `/skills/tabular-evidence/SKILL.md`, found the mounted CSV and ran `/skills/tabular-evidence/analyze.py`. It returned operations 75, research 120, support 40 and physical CSV line 5. | [Chat](61-fresh-small-python-skill-chat.png) | [Code](61-fresh-small-python-skill-tool.png), [result](61-fresh-small-python-skill-tool-result.png) |
| Medium 3.5, separate conversation, Excel | Used pandas on the original mounted workbook, combined the sheets and computed weighted margins: Lyon 41.22%, Paris 38.02%. | [Chat](62-fresh-medium-xlsx-chat.png) | [Code](62-fresh-medium-xlsx-tool.png), [result](62-fresh-medium-xlsx-tool-result.png) |
| Small 4, separate conversation, attachment | Located a newly attached original below `/inputs/attachments/<attachment-id>/` and used Bash `grep -n -C 2` to find `NEBULA-8842` on line 6135 with its surrounding lines. | [Chat](63-fresh-attachment-chat.png) | [Code](63-fresh-attachment-tool.png) |
| Large 4, separate conversation, isolation probe | Found no service-account token, `kubectl`, Docker socket or `/host` path. Writes to `/inputs` and `/skills` failed with read-only filesystem errors; TCP connections to the local Kubernetes API IP and metadata IP were refused. These are local probe results, not a complete isolation proof. | [Chat](64-fresh-large-security-chat.png) | [Code](64-fresh-large-security-tool.png), [result](64-fresh-large-security-tool-result.png) |

The fixed page path remains stable when a library grows from 100 to 101 pages; a focused WebDAV test verifies this boundary. The authorized document is checked on each read. A full-page rclone scan and FGA latency at thousands of concurrent users have not yet been measured.

## What worked

| Scenario | Observation | Chat | Tool detail |
| --- | --- | --- | --- |
| Large 4: big corpus | Bash `grep -n` found `POLARIS-7319` at line 8538 in a 1.1 MB file, with the correct owner, deadline and risk. | [Chat](01-corpus-chat.png) | [Code and result](01-corpus-tool.png) |
| Large 4: existing skill | Read the mounted `summarize-document` skill and the original DOCX file. | [Chat](02-existing-skill-chat.png) | [Code and result](02-existing-skill-tool.png) |
| Large 4: attachment | Bash searched an attached 407 KB CSV and found `NEBULA-8842` at line 6135. | [Chat](03-attachment-chat.png) | [Code and result](03-attachment-tool.png) |
| Large 4: custom skill | Read `tabular-evidence/SKILL.md`, ran its mounted Python script against an attachment, and reported category totals and the maximum source row. | [Chat](04-python-skill-chat.png) | [Code and result](04-python-skill-tool.png) |
| Large 4: CSV choice | Chose Python's `csv` module without being told which language to use; totals were correct. | [Chat](05-csv-spontaneous-chat.png) | [Code and result](05-csv-spontaneous-tool.png) |
| Large 4: PDF | Used `pypdf` to extract EUR 275,000, Marta Silva's review deadline and the second-signature exception. | [Chat](06-pdf-chat.png) | [Code and result](06-pdf-tool.png) |
| Large 4: PPTX | Used `python-pptx` to locate `MERIDIAN-56` on slide 3 with the correct date, owner and release consequence. | [Chat](07-pptx-chat.png) | [Code and result](07-pptx-tool.png) |
| Large 4: XLSX | Used `openpyxl` and aggregated revenue and cost before calculating city margin rates. | [Chat](08-xlsx-chat.png) | [Code and result](08-xlsx-tool.png) |

## Small 4 versus Medium 3.5

The model comparison below uses separate conversations per model. Both had High Reasoning selected. For tabular data, Small often wrote short Python or Bash; Medium used pandas more readily. Both selected Bash `grep` for the large text file. These are observations from one run per prompt, not a statistical model benchmark.

| Task | Small 4 Reasoning | Medium 3.5 Reasoning |
| --- | --- | --- |
| CSV totals, unconstrained method | Python standard library `csv`, correct totals: [chat](20-small-csv-fresh-chat.png), [tool](20-small-csv-fresh-tool.png). | Python pandas, correct totals: [chat](21-medium-csv-fresh-chat.png), [tool](21-medium-csv-fresh-tool.png). |
| PDF before package hint | Tried other readers and failed despite installed `pypdf`: [chat](22-small-pdf-fresh-chat.png), [tool](22-small-pdf-fresh-tool.png). | Reached the tool limit after manual extraction attempts and failed despite installed `pypdf`: [chat](23-medium-pdf-fresh-chat.png), [tool](23-medium-pdf-fresh-tool.png). |
| PDF after capability described installed packages | Used `pypdf`, correct answer: [chat](40-small-pdf-hint-chat.png), [code](40-small-pdf-hint-tool.png), [result](40-small-pdf-hint-tool-result.png). | Used `pypdf`, correct answer: [chat](41-medium-pdf-hint-chat.png), [code](41-medium-pdf-hint-tool.png), [result](41-medium-pdf-hint-tool-result.png). |
| PPTX | Used `python-pptx`, correct slide, date and owner: [chat](42-small-pptx-chat.png), [code](42-small-pptx-tool.png), [result](42-small-pptx-tool-result.png). | Correct after one unsuccessful import attempt: [chat](43-medium-pptx-chat.png), [code](43-medium-pptx-tool.png), [result](43-medium-pptx-tool-result.png). |
| XLSX | Read both sheets with pandas but **incorrectly averaged row margin percentages**, reporting 40.37% for Lyon and 37.78% for Paris: [chat](44-small-xlsx-chat.png), [code](44-small-xlsx-tool.png), [result](44-small-xlsx-tool-result.png). On a follow-up, reran Python and corrected them to 41.22% and 38.02%: [chat](46-small-xlsx-correction-chat.png), [code](46-small-xlsx-correction-tool.png), [result](46-small-xlsx-correction-tool-result.png). | Aggregated revenue and cost first, correct 41.22% and 38.02% on the first try: [chat](45-medium-xlsx-chat.png), [code](45-medium-xlsx-tool.png), [result](45-medium-xlsx-tool-result.png). |
| DOCX | Used `python-docx` and found the Geneva backup gate and Lea Fournier: [chat](47-small-docx-chat.png), [code](47-small-docx-tool.png), [result](47-small-docx-tool-result.png). | Same correct finding: [chat](48-medium-docx-chat.png), [code](48-medium-docx-tool.png), [result](48-medium-docx-tool-result.png). |
| Mounted Python skill | Read `tabular-evidence/SKILL.md` and ran its script; operations 75, research 120, support 40, maximum on physical CSV line 5: [chat](49-small-skill-chat.png), [code](49-small-skill-tool.png), [result](49-small-skill-tool-result.png). | Same correct computation: [chat](50-medium-skill-chat.png), [code](50-medium-skill-tool.png), [result](50-medium-skill-tool-result.png). |
| Large corpus | Chose Bash `grep`, found `POLARIS-7319` on line 8538: [chat](51-small-large-corpus-chat.png), [code](51-small-large-corpus-tool.png), [result](51-small-large-corpus-tool-result.png). | Chose Bash `grep`, same correct line: [chat](52-medium-large-corpus-chat.png), [code](52-medium-large-corpus-tool.png), [result](52-medium-large-corpus-tool-result.png). |
| SQL over CSV | Not tested. | Used embedded DuckDB SQL over the mounted CSV after a failed CLI attempt; totals matched the Python results: [chat](53-medium-duckdb-chat.png), [code](53-medium-duckdb-tool.png), [result](53-medium-duckdb-tool-result.png). SQL row number 4 counts data rows; the Python skill's row 5 counts the CSV header. |

One earlier Medium CSV turn in a shared exploratory conversation reported the known totals without a tool call. Session history confirmed there was no `execute_code` event for that exchange. This prompted a stronger capability description: the model must execute a tool before claiming an execution result. It does not guarantee model compliance. Evidence: [chat](12-medium-csv-chat.png). A later fresh Medium conversation did call the tool and produced the correct result above.

## Isolation probes with Large 4

| Probe | Observation | Chat | Tool detail |
| --- | --- | --- | --- |
| Guest and mount boundaries | The guest had no Kubernetes service-account token, `kubectl`, Docker binary or socket, or `/host` path. Writes under `/inputs` and `/skills` failed with a read-only filesystem error. | [Chat](09-security-boundaries-chat.png) | [Code and result](09-security-boundaries-tool.png) |
| Network destinations | Connections to the Kubernetes API IP, metadata IP and a public IP failed with `ConnectionRefusedError` in this local cluster. This does not validate every possible route or future policy change. | [Chat](10-security-network-ip-chat.png) | [Code and result](10-security-network-ip-tool.png) |
| Other conversation's attachment | In a new conversation, `/inputs/attachments` was empty and the guest could not find the `NEBULA-8842` attachment from the earlier conversation. One initial tool attempt was temporarily unavailable; subsequent calls completed. | [Chat](54-large-cross-conversation-chat.png) | [Code](54-large-cross-conversation-tool.png), [result](54-large-cross-conversation-tool-result.png) |

The security result is a bounded probe. Production acceptance still requires runtime verification on each target cluster, including CNI policy enforcement, CSI behavior, gVisor or Kata availability, Pod PID limits and concurrent admission. A separate authorization review found and corrected a personal-space scope error: a team-owned library shared directly with the user must not enter a personal sandbox view. The new filter checks the stored library owner as well as document permission, and file mounts fail closed when ReBAC is disabled.
