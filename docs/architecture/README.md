# Fred architecture dossier

The architecture of Fred's `fred-manager` service, as implemented. Structure follows
[arc42](https://arc42.org), reduced to the chapters that carry decisions. Diagrams are
Mermaid, rendered by GitHub.

| # | Chapter | Answers |
| --- | --- | --- |
| 1 | [Introduction and goals](01-goals-and-scope.md) | Responsibilities, constraints, vocabulary |
| 2 | [Context](02-context.md) | Who talks to whom |
| 3 | [Building blocks](03-building-blocks.md) | Modules and their dependencies |
| 4 | [Runtime](04-runtime.md) | The flows that matter, step by step |
| 5 | [Data and authorization](05-data-and-authorization.md) | Schema, OpenFGA model, invariants |
| 6 | [Cross-cutting](06-cross-cutting.md) | Authentication, logging, errors, configuration |
| 7 | [Deployment](07-deployment.md) | Host run and k3d |
| 8 | [Decisions](08-decisions.md) | Why, one entry per decision |
| 9 | [Quality](09-quality.md) | Invariants and the tests proving them |

## Keeping it true

- **Same commit.** A change to code described here updates its chapter in the same
  commit. The dossier describes what is implemented, in the present tense; plans,
  progress and status belong elsewhere.
- **Generated, never copied.** Anything derivable from code sits in a generated block
  (`<!-- generated: ... -->`): routes, the SQL schema (tbls, from the migrations), the
  OpenFGA model, the reference configuration, the invariant-to-test table.
- **Invariants are proved.** Chapter 5 numbers them (`I1`, `I2`, ...). A test proving
  one carries `// Proves: I<n>` above it; chapter 9 lists them.
- **Checked.** From this directory:

  ```
  make generate   # rewrite generated blocks (Docker: Postgres + tbls)
  make check      # stale block, unproved invariant, unknown citation, unrenderable diagram
  ```

Write concrete statements: names, values, rules, consequences. A sentence that would
stay true for any system does not belong here.
