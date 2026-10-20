# Fred architecture

A compact explanation of Fred: its user journeys, domain boundaries, security
rules and runtime interactions. The structure adapts arc42's context, building
blocks, runtime, cross-cutting concepts and quality views to Fred's domains.
Read the journeys first, then follow the relevant domain chapter.

| Chapter | Reader's question |
| --- | --- |
| [1. System overview](01-system-overview.md) | What makes up Fred, and where are its boundaries? |
| [2. User journeys](02-user-journeys.md) | How do the architectural rules work together in practice? |
| [Document journey: Priya ingests a PDF](02a-document-journey.md) | What happens to one document, and how do we inspect each store? |
| [3. Security](03-security.md) | Who is authenticated, admitted and authorized, and why? |
| [Action and role matrix](03a-action-role-matrix.md) | Exactly which actions does each role allow, at which scope, and how does Rust differ from Python? |
| [4. Organizations and provisioning](04-organizations.md) | How are people, spaces and their relationships organized? |
| [5. Documents and knowledge](05-documents.md) | How does knowledge enter, circulate and leave Fred? |
| [6. Agents and conversations](06-agents.md) | How does a conversation become an agent execution? |
| [7. Capabilities and integrations](07-capabilities.md) | How do agents acquire tools and interact with other systems? |
| [8. Operations](08-operations.md) | How is Fred configured, deployed and observed? |
| [9. Quality and invariants](09-quality.md) | Which guarantees are proved, and what do they cost? |

Empty sections define the editorial structure only. They make no implementation
claim. Populated sections name their execution context: in particular, the
organization/team/project journey uses Fred's existing UI connected to manager on this branch. A rule
implemented there does not imply that every Python product surface uses it.

## Technical references

Exact implementation detail is available without making it the main reading path:
[manager runtime](A1-manager-runtime.md), [schemas and contracts](A2-manager-contracts.md),
and [manager operations](A3-manager-operations.md). Generated blocks remain tied to
source code; they are references, not another handwritten API specification.

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

The [branch workflow](../../AGENTS.md#fred-manager-reconstruction-on-chorerust-rebac)
sets review and commit requirements. New domain chapters start with headings;
verified explanations replace the headings' empty bodies as their scope is documented.

For a repeatable independent review of the Rust reconstruction, use
[`audit-fred-manager`](../../.agents/skills/audit-fred-manager/SKILL.md). It checks
implemented manager behavior against this dossier and affected Fred contracts,
with explicit coverage and exclusions. It does not audit the whole platform or
treat future migration features as defects.
