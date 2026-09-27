# Complexity rubric → slide budget

Score the spec on six axes (0–4 each, max 24). Count from the spec *and* from
the Step 2 grounding — a short RFC that touches five sub-projects is not short.

| Axis | 0 | 1 | 2 | 3 | 4 |
|------|---|---|---|---|---|
| **Length** (lines of prose, code blocks excluded) | < 80 | 80–150 | 150–350 | 350–600 | > 600 |
| **Sub-projects touched** (apps, libs, frontend, Helm) | 1 | 2 | 3 | 4–5 | ≥ 6 |
| **Contract surface** (new/changed endpoints, SDK types, events, config keys) | 0 | 1–2 | 3–5 | 6–10 | > 10 |
| **Data & migration** | none | additive column | new table(s) | backfill or dual-write | multi-step with cutover |
| **Runtime flows** (distinct sequences that change) | 0 | 1 | 2 | 3–4 | ≥ 5 |
| **Uncertainty** (open questions, live alternatives, `Status:` draft) | settled | 1 open point | several | draft with alternatives | contested |

## Tiers (presented slides; appendix slides are not counted)

| Tier | Score | Budget | Talk (≈ 1.5 min/slide) | Notes |
|------|-------|--------|-------------------------|-------|
| **S** | 0–6 | 9–13 | 14–20 min | Context in 2 slides; one slicing pair (one lot vs two). |
| **M** | 7–12 | 14–22 | 20–33 min | The common RFC. Full skeleton. |
| **L** | 13–18 | 22–32 | 33–48 min | Section 5 has one touch map per sub-project; before/after sequences. |
| **XL** | 19–24 | 32–45 | 48–70 min | Propose two sessions (design walkthrough / slicing workshop); section 5 grouped by domain with a divider each. |

Rules:

- The budget is a range, not a target. Land where the content stops; never pad,
  never cram — over a density cap, a slide splits.
- More content means **more slides**, never denser slides.
- `--duration` caps the upper bound at 1.5 min per presented slide. If the
  tier's lower bound exceeds the cap, say so and propose what to drop
  (usually per-component depth for additive-only components).
- Print `Tier: <T> (score n/24) Budget: a–b presented slides Talk: ~x–y min`
  in the final reply, with the per-axis scores on request.
