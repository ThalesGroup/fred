# Model routing primer

Model routing separates model choice from application logic. The application
asks for a technical client appropriate to its work; configuration and policy
select a concrete provider and model.

## Common approaches

Model selection is commonly implemented in four ways:

| Approach | Decision owner | Main trade-off |
| --- | --- | --- |
| Hard-coded | Application code | Simple initially, difficult to govern |
| Query classifier | Heuristic or learned router | Adaptive, but harder to explain and reproduce |
| Expert router | Domain routing layer | Specialized, but operationally complex |
| Explicit policy | Operator-authored configuration | Deterministic and auditable |

Fred uses explicit policy for its production routing surface. This does not
mean Fred implements arbitrary rule matching: the current policy is a small,
typed fallback chain for chat models.

## Model, profile, and capability

- A **model** is the concrete `(provider, name)` pair an administrator enables.
- A **profile** is a pod-authored model configuration with a stable id and
  settings.
- A **model capability** is the technical client family required by a
  consumer, such as `chat` or `embedding`.

These axes are related but not interchangeable. Two profiles can construct the
same concrete model, and one concrete model can potentially serve more than one
technical usage. Administrative enablement is therefore keyed by the concrete
model, while routing policy is typed by its consumer.

## Fred's current boundary

Fred V1 routes chat models using platform, pod, team, and per-agent defaults.
It does not inspect query complexity and does not route by shared `planning`,
`analysis`, `purpose`, or other operation conventions.

Embeddings remain a distinct future policy case. They should be introduced
with the document processor or other component that consumes them, rather than
through a generic rule language created in advance.

See [LLM_ROUTING_FRED.md](LLM_ROUTING_FRED.md) for the implemented precedence,
multi-pod behavior, administration workflow, and pod catalog contract.
