# Fred architecture

A compact explanation of Fred: its user journeys, domain boundaries, security
rules and runtime interactions. The structure adapts arc42's context, building
blocks, runtime, cross-cutting concepts and quality views to Fred's domains.
Read the journeys first, then follow the relevant domain chapter.

| Chapter | Reader's question |
| --- | --- |
| [2. User journeys](02-user-journeys.md) | How do the architectural rules work together in practice? |
| [Document journey: Priya ingests a PDF](02a-document-journey.md) | What happens to one document, and how do we inspect each store? |
| [3. Security](03-security.md) | Who is authenticated, admitted and authorized, and why? |
| [Action and role matrix](03a-action-role-matrix.md) | Exactly which actions does each role allow, at which scope, and with which additional conditions? |
| [4. Organizations and provisioning](04-organizations.md) | How are people, spaces and their relationships organized? |
| [5. Documents and knowledge](05-documents.md) | How does knowledge enter, circulate and leave Fred? |
| [8. Operations](08-operations.md) | How is Fred configured, deployed and observed? |
| [9. Quality and invariants](09-quality.md) | Which guarantees are proved, and what do they cost? |

The primary reading path is the user journey through folder creation, followed by
organizations/security and the SQL catalogue. The document-ingestion journey is
separate. The dossier describes code behavior, not proof that the current build has
passed its tests or that Dimi has validated every screen.

## Find a function

| Question | Canonical explanation | Implementation entry |
| --- | --- | --- |
| Login, CGU, first platform owner | [Journey](02-user-journeys.md#from-an-empty-platform-to-an-organizations-first-user), [Security](03-security.md) | [Source map](../../apps/control-plane/src/README.md) rows authentication, CGU, bootstrap |
| Organization owner/admin selection and creation | [Organization creation](02-user-journeys.md#a-platform-owner-creates-an-organization), [Organizations](04-organizations.md#platform-organization-administration) | Source map rows directory and organizations |
| Import accounts, teams and roles | [Provisioning journey](02-user-journeys.md#provisioning-the-business-account), [ZIP contract](A2-manager-contracts.md#provisioning-declarations) | Source map row ZIP import |
| Who can enter a space or create a folder? | [Resources journey](02-user-journeys.md#priya-opens-resources), [Action/role matrix](03a-action-role-matrix.md) | Source map rows spaces, folders and roles |
| Where are data and permissions stored? | [SQL catalogue](A2-manager-contracts.md#control-plane-sql-catalogue), [OpenFGA model](A2-manager-contracts.md#openfga-model) | `migrations/`, `db.rs`, `openfga/model.fga` in the source map |
| API endpoints and frontend bindings | [Generated routes](A2-manager-contracts.md#control-plane-http-surface) | Source map section contracts/generated code |
| Startup, SQL migration or local deployment | [Operations](08-operations.md), [SQLx procedure](A3-manager-operations.md#sqlx-schema-evolution) | Source map rows startup/migrations and local profile |
| Upload/process a PDF | [Separate document journey](02a-document-journey.md), [Documents](05-documents.md) | Source map section beyond folder creation |

Follow this map before searching historical OpenSpec changes or Swift documentation.
For an audit, trace the named UI consumer through the handler, authorization and
persistence; record discrepancies rather than treating prose or a test name as proof.

## Separate work history

Outside this dossier, the internal [working journal](../WORKING-JOURNAL.md) indexes the functions explored
with Dimi, observed failures, focused changes, explicit manual validation and
pending architecture updates. Read it when resuming this work. It records work
in progress, not verified architecture.

## Technical references

Exact implementation detail is available without making it the main reading path:
[control-plane runtime](A1-manager-runtime.md), [schemas and contracts](A2-manager-contracts.md),
the [SQL table catalogue](A2-manager-contracts.md#control-plane-sql-catalogue),
and [control-plane operations](A3-manager-operations.md). Generated blocks remain tied to
source code; they are references, not another handwritten API specification.

## Reconstruction method

The [reconstruction method](../../.agents/skills/fred-reconstruction-method/SKILL.md)
defines how this dossier converges with the implementation: current journeys and
schemas, a separately labelled feature plan, and key design decisions. Proposed
features are not implemented guarantees. Superseded RFC/OpenSpec prose leaves the
active corpus only after its useful information and consumers are reconciled.
The [review prompt](../../.agents/skills/fred-reconstruction-method/references/review-prompt.md)
provides a bounded, independent audit request.

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

The [branch workflow](../../AGENTS.md#control-plane-reconstruction-on-chorerust-rebac)
sets review and commit requirements. Only documented behavior belongs in the reading path.

For a repeatable independent review of the Rust reconstruction, use
[`audit-control-plane`](../../.agents/skills/audit-control-plane/SKILL.md). It checks
implemented control-plane behavior against this dossier and affected Fred contracts,
with explicit coverage and exclusions. It does not audit the whole platform or
treat future migration features as defects.
