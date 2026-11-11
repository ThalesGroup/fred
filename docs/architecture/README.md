# Fred architecture

Read the architecture through responsibilities, resources and access boundaries.
Each rule has one home; journeys illustrate it. Diagrams and matrices carry the
explanation. Field-level contracts remain in OpenAPI and implementation detail
stays next to the code.

## Reading path

| View | Reader's question |
| --- | --- |
| [Introduction](00-introduction.md) and [system overview](01-system-overview.md) | What does Fred provide, and which component is responsible? |
| [Journeys](02-journeys.md) | How do access, documents and an assistant fit together? |
| [Models and MCP for an assistant](02.3-agent-administration.md#models-and-mcp) | Who connects, authorizes and selects the means an assistant can use? |
| [Security](03-security.md) and [organizations/spaces](04-organizations.md) | Where are identity, authority and isolation enforced? |
| [Resources, prompts and skills](06-resources.md) | What belongs to a space, and how are instructions reused? |
| [Documents and knowledge](05-documents.md) | How do stored documents become usable knowledge? |
| [Operations](08-operations.md) | What does deployment and operation require? |
| [Quality and invariants](09-quality.md) | What guarantees and evidence support the design? |

## Decision tables and generated references

| Reference | Purpose |
| --- | --- |
| [Action/role matrices](A7-action-role-matrix.md) and [role definitions](A11-roles.md) | SSI review of permissions, scope and administration boundaries |
| [REST inventory](A12-control-plane-api.md) | Registered methods, paths and operation names; naming and API consistency |
| [Storage responsibilities and evidence](A2-manager-contracts.md) | Ownership, SQL catalogue, three prompt anchors and links to checks |
| [Model and MCP governance](A13-models.md) | Source offers, organization policy and trusted admission contracts |

Start with the diagrams and comparisons above. For a client architecture dossier,
follow the component responsibilities; for an SSI review, continue with security
and the role matrices. REST and source references are the final level of detail,
not prerequisites for understanding the product.

## Specialist references

These remain linked for a specific investigation; they are not a second sequential
reading path. Use the [component documentation](../../apps/control-plane/README.md)
for commands and the [source map](../../apps/control-plane/src/README.md) to locate code.

| Subject | References |
| --- | --- |
| Runtime and operations | [Runtime](A1-manager-runtime.md), [operations](A3-manager-operations.md) |
| Security and organizations | [Security mechanisms](A6-security.md), [organizations/provisioning](A8-organizations.md) |
| Journey evidence | [User journey contracts](A5-user-journeys.md), [document trace](A4-document-journey.md), [storage/processing](A9-documents.md) |
| Open architectural questions | [Evidence and tradeoffs](A10-open-issues.md) |

## Reliability and maintenance

- Current implementation contracts, automated checks and deployed acceptance are distinct.
  Acceptance results belong in the lot PR; outstanding work belongs in its task/issue.
- `make -C docs/architecture generate-models` updates the SQL diagram, API inventory
  and selected references. `make -C docs/architecture check-models` checks freshness,
  links, generator tests and the selected diagrams.
- Code anchors verify named symbols and their comments, not semantic correctness.
  Tests establish behavior only when executed; they do not replace application reception.
- Link to stable section anchors when reusing an explanation. Generate selected
  source, schema and REST fragments through the existing `generated:` blocks in
  annexes; do not maintain a second paraphrase of their fields or handlers.
- Keep security matrices and useful exceptions. Remove duplicated API fields,
  function-by-function prose and generated bulk from the reading path.
- Use the [shared workflow](../../AGENTS.md) for changes. Historical Swift documentation
  and planned features are not current contracts.
