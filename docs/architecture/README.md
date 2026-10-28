# Fred architecture

A compact explanation of Fred: its user journeys, domain boundaries, security
rules and runtime interactions. The structure adapts arc42's context, building
blocks, runtime, cross-cutting concepts and quality views to Fred's domains.
Start with the introduction and system overview, then read the journeys and
follow the relevant domain chapter.

| Chapter | Reader's question |
| --- | --- |
| [0. Introduction](00-introduction.md) | What is Fred and what can you build with it? |
| [1. System overview](01-system-overview.md) | What are Fred's main components? |
| [2. Journeys](02-journeys.md) | How do the architectural rules work together in practice? |
| [2.1. User journeys](02.1-user-journeys.md) | How does a user go from first login to creating a folder? |
| [2.2. Document journey](02.2-document-journey.md) | How does a user import a document and read the result? |
| [2.3. Models and first chat](02.3-agent-administration.md) | How does Alice authorize models for Acme, and how does Bob get his first answer? |
| [3. Security](03-security.md) | Who is authenticated, admitted and authorized, and why? |
| [4. Organizations and spaces](04-organizations.md) | How are people, spaces and their relationships organized? |
| [5. Documents and knowledge](05-documents.md) | How does knowledge enter, circulate and leave Fred? |
| [8. Operations](08-operations.md) | How is Fred configured, deployed and observed? |
| [9. Quality and invariants](09-quality.md) | Which guarantees are proved, and what do they cost? |

Chapter 2 follows people through access, document ingestion and a first assistant
exchange. The main chapters explain who acts, which component is responsible and
what the user experiences. Technical contracts and source references belong in
the annexes. Validation records live in each lot's PR; remaining work in GitHub issues.

## Find a function

| Question | Canonical explanation | Implementation entry |
| --- | --- | --- |
| Login, CGU, first platform owner | [Journey](02.1-user-journeys.md#from-an-empty-platform-to-an-organizations-first-user), [Security](03-security.md) | [Source map](../../apps/control-plane/src/README.md) rows authentication, CGU, bootstrap |
| Organization owner/admin selection and creation | [Organization creation](02.1-user-journeys.md#a-platform-owner-creates-an-organization), [Organizations](04-organizations.md#platform-organization-administration) | Source map rows directory and organizations |
| Organization totals, team detail and their disclosure boundary | [Overview](04-organizations.md#organization-supervision), [Supervision contract](A8-organizations.md#organization-supervision), [Read budget](09-quality.md#organization-supervision-read-budget) | [Implementation trace](A8-organizations.md#pagination-freshness-and-implementation-trace); organization supervision page |
| Import accounts, teams and roles | [Provisioning journey](02.1-user-journeys.md#provisioning-the-business-account), [ZIP contract](A2-manager-contracts.md#provisioning-declarations) | Source map row ZIP import |
| What does each role mean, and where do current permissions differ? | [Roles and responsibility boundaries](A11-roles.md) | Role definitions, attribution and SSI comparison in the annex |
| Who can enter a space or create a folder? | [Resources journey](02.1-user-journeys.md#bob-opens-resources), [Action/role matrix](A7-action-role-matrix.md), [Security](03-security.md) | Source map rows spaces, authorization, folders and roles |
| Where are data and permissions stored? | [SQL catalogue](A2-manager-contracts.md#control-plane-sql-catalogue), [OpenFGA model](A2-manager-contracts.md#openfga-model) | `migrations/`, `db.rs`, `openfga/model.fga` in the source map |
| API endpoints and frontend bindings | [REST API reference](A12-control-plane-api.md), [HTTP surface rules](A2-manager-contracts.md#control-plane-http-surface) | Source map section contracts/generated code |
| Startup, SQL migration or local deployment | [Operations](08-operations.md), [SQLx procedure](A3-manager-operations.md#sqlx-schema-evolution) | Source map rows startup/migrations and local profile |
| Upload/process a PDF | [Document journey](02.2-document-journey.md), [Documents](05-documents.md) | Source map section beyond folder creation |
| Assistant answering from a space's documents | [Journey](02.3-agent-administration.md#bobs-assistant-answers-from-researchs-documents), [Security](03-security.md#36-documents-used-by-an-assistant) | [Document search annex](A6-security.md#document-search-within-a-turn) |

Follow this map before searching historical OpenSpec changes or Swift documentation.
For an audit, trace the named UI consumer through the handler, authorization and
persistence; record discrepancies rather than treating prose or a test name as proof.

## Technical references

Exact implementation detail is available without making it the main reading path.

| Annex | Reader's question |
| --- | --- |
| [A1. Control-plane runtime](A1-manager-runtime.md) | Which dependencies and runtime sequences does the Control Plane rely on? |
| [A2. Schemas and contracts](A2-manager-contracts.md) | Which HTTP rules, [SQL tables](A2-manager-contracts.md#control-plane-sql-catalogue) and OpenFGA model back the domain? |
| [A3. Control-plane operations](A3-manager-operations.md) | How is the Control Plane configured, logged and diagnosed? |
| [A4. Document journey trace](A4-document-journey.md) | Which code and state does a document upload go through, and how do I inspect it? |
| [A5. User journey contracts](A5-user-journeys.md) | Which admission, provisioning and folder contracts back the user journeys? |
| [A6. Security mechanisms](A6-security.md) | How are authentication, consent, authorization and lifecycle enforced? |
| [A7. Action and role matrix](A7-action-role-matrix.md) | Which role may perform which action, through which entry point? |
| [A8. Organizations and provisioning](A8-organizations.md) | How are context, placement, membership and retirement resolved? |
| [A9. Document storage and processing](A9-documents.md) | How are originals stored, processed, published and cleaned up? |
| [A10. Open issues](A10-open-issues.md) | Which quality questions remain open, and what evidence would settle them? |
| [A11. Roles](A11-roles.md) | What does each role mean, and where do current permissions differ? |
| [A12. Control-plane REST API](A12-control-plane-api.md) | Which operations and JSON schemas does the Control Plane expose? |

Generated blocks remain tied to source code; they are references, not another
handwritten API specification.

## Convergence with the implementation

The dossier converges with the implementation through current journeys, schemas
and key design decisions. Implementation plans belong in GitHub issues, RFCs or
OpenSpec, outside this dossier. Superseded RFC/OpenSpec prose leaves the active
corpus only after its useful information and consumers are reconciled.

## Keeping one useful account

- Explain current behavior and the reason for its boundaries, in the present tense.
  Describe a rule in its domain chapter; journeys illustrate it and link back.
- RFCs hold unresolved choices; active OpenSpec changes hold proposed deltas;
  capability specs hold acceptance contracts; issues track work. Link to those
  sources when needed, without importing their plans or histories here.
- Component READMEs contain developer commands. This dossier explains how Fred's
  parts fit together. An implementation change updates its relevant chapters.
- Define each invariant once in chapter 9. Tests cite `// Proves: I<n>`; the proof
  table, route tables, SQL diagram, model and configuration are generated.
- Run `make -C docs/architecture generate` after source changes and
  `make -C docs/architecture check` to verify sources, proofs and diagrams.

The [branch workflow](../../AGENTS.md#control-plane-reconstruction-on-weaver)
sets review and commit requirements. Only documented behavior belongs in the reading path.

For a repeatable independent review of the Rust reconstruction, use
[`audit-control-plane`](../../.agents/skills/audit-control-plane/SKILL.md). It checks
implemented control-plane behavior against this dossier and affected Fred contracts,
with explicit coverage and exclusions. It does not audit the whole platform or
treat future migration features as defects.
