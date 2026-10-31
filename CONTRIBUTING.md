# Contributing to Fred

Contributions are welcome. Weaver consolidates Fred into a simpler, more robust
system after the growth of Swift. Our small maintaining team owns architectural
decisions and integration; a useful contribution improves that shared system.

## Start with how it fits

Before writing code, explain the user need and where the behavior belongs in Fred.
Identify what the change will **reuse, extend, replace or remove**. Do not start
with a standalone new feature, endpoint or screen and fit the architecture around it.

For a domain or persistence change, reason in this order:

**Business need -> invariants and lifecycle -> schema and transactions ->
application usages -> API -> UI.**

Discuss decisions affecting rights, isolation, retention, cardinality or lifecycle
with the maintaining team. Ordinary SQL details do not need a separate design
ceremony. The [shared development instructions](AGENTS.md) and
[Weaver method](.agents/skills/fred-reconstruction-method/SKILL.md) contain the
agreed business constraints and capacity targets. Do not treat targets as measured
performance or prepared tables as operational features.

## Reduce the maintained surface

Adding code is not our default solution. Search the existing domain implementation,
shared libraries and design system first. Reuse them or improve the shared primitive.
Avoid a local wrapper, duplicated validator, alternate state model, custom UI control
or second policy path that creates another mechanism for the team to maintain.

State which old paths or concepts the change makes unnecessary, and remove them
within the agreed scope after checking consumers. If additional production code is
unavoidable, explain the concrete gap and agree that exception in the increment's
scope before building it. "It is a new feature" is not a justification.

Reduction must preserve readability, useful tests, invariants and security. Do not
minify code, drop coverage or move complexity into generated artifacts to improve a
line count. Show production-code additions and removals separately from tests,
generated files and documentation. Small, coherent changes are easier to accept
than a large feature followed by a promise to simplify it later.

UX work is valuable for discovering needs and validating interactions. Persistence,
authorization and component boundaries still follow the shared software design.
Use the existing UI components and design tokens; an alternative visual design does
not justify a second design system or duplicate business rules in the browser.

## Make the result reviewable

- Keep a bounded scope and preserve other contributors' work.
- Identify each invariant's SQL, transaction, authorization or projection owner.
- Preserve applied migrations; add new migrations in the current sequence.
- Run scoped formatting and component code-quality checks. Agree functional and
  performance validation appropriate to the increment; report actual evidence and
  limits without implying a broader campaign occurred.
- Update [arc42](docs/architecture/README.md) when current architecture changes,
  including the relevant generated references. Component READMEs hold usage commands.
- Include an [operator note](deploy/release-notes/README.md) as required by CI.

RFCs and the retired documentation/spec corpus are not current contracts. OpenSpec
is optional for a specific increment when explicitly useful and agreed; it is not
a prerequisite for contributing. Do not recreate a parallel documentation corpus.

A PR may be sent back for redesign even if its tests pass when it duplicates shared
mechanisms, adds unjustified concepts, leaves replaced paths active, or bypasses
these ownership decisions. Explain the integration and removal choices early so
contributors and maintainers can settle them before substantial implementation.

Follow the [Code of Conduct](CODE_OF_CONDUCT.md).
