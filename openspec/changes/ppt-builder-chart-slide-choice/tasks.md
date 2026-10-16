## 1. Assignment

- [x] 1.1 `assign._weigh`: count the zones a fitting pattern leaves unfilled (text zones swept away, empty pictures, item picture holes); `misfit` keeps its signature (D1)
- [x] 1.2 `_fullest`: drop a candidate when one of its kind leaves fewer zones unfilled at no higher cost; applied after the design pin (`_kept`) and to split parts (D1, D3)
- [x] 1.3 `_repeats`: a variant dropped on every slide of the group is not offered (D2)
- [x] 1.4 `_tiers`: a chart without a requested kind tries `chart` alone first (D4)
- Verification: package `make test` green

## 2. Tests

- [x] 2.1 `test_chart_slides.py`: three chart slides (centred, left, right); six bare charts with `variety_max_uses` 1 all take the centred slide, no variety ask; four chart + bullets slides alternate left and right
- [x] 2.2 Built-in: `test_a_takeaway_goes_beside_the_chart_and_a_bare_chart_spans_the_slide` and `test_chart_slides_are_never_asked_to_become_another_kind` unchanged and green
- [x] 2.3 `test_assign.py` / `test_build_tool.py`: expectations that relied on variety picking an emptier variant updated to an equally filled one; the emptier variant asserted never taken

## 3. Docs and close-out

- [x] 3.1 `ppt-builder-charts/design.md` D10: point to this change for the "wide one wins" assumption
- [x] 3.2 `ruff check`, `ruff check --select I`, `ruff format --check`, bandit, detect-secrets, basedpyright with baseline (`make code-quality`); `openspec validate ppt-builder-chart-slide-choice --strict`
- [x] 3.3 Migration: covered by the PR's `ppt-builder-capability` note (no operator action)
