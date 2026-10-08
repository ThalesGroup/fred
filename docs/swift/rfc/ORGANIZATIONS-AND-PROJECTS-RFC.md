# RFC: Future organization administration

**Status:** organization UI and further onboarding design remain deferred.
The major-release backend, ownership and offline-cutover target is specified in
the OpenSpec change below; it is not shipped by these planning documents.
**Author:** Dimitri Tombroff
**Related:** [#2921](https://github.com/ThalesGroup/fred/issues/2921)

## Scope and authoritative references

The [organization/team/project authorization change](../../../openspec/changes/simplify-corpus-authorization/proposal.md)
is the proposed authority for the ownership model, four local roles, corpus,
agent reach, immutable conversation context and offline migration.
Its [design](../../../openspec/changes/simplify-corpus-authorization/design.md)
and [acceptance scenarios](../../../openspec/changes/simplify-corpus-authorization/specs/corpus-authorization/spec.md)
incorporate the developer decisions of 2026-10-08.

That scope replaces this RFC's earlier single-organization project delivery,
two-role organization proposal and separate later migration. It is delivered
through one implementation PR with precise commits, not dependent PRs.
Do not use historical RFC wording as a parallel permission contract.

[REBAC.md](../platform/REBAC.md) describes the shipped model until implementation
and verification justify updating it. Planning does not establish tenant safety.

## Remaining future design

The current target provisions organizations through installation/migration
tooling. These questions remain outside that delivery:

- An organization-creation and administration UI.
- A richer organization onboarding/invitation experience beyond explicit
  provisioning.
- Additional organization-level product workflows, such as wiki or analytics.

Scope those only when requested; the presence of organization ownership and
four roles is not authorization to build every organization-level workflow.
