## 1. Analysis and render

- [x] 1.1 `lexicon.KICKER_NAMES`; `analysis.kicker_keys` (shape name or layout placeholder name, never a title placeholder); records of kickers dropped on the slide and layout paths (D1, D2)
- [x] 1.2 `render._remove_kickers` at the start of `_fill`: kicker shapes holding no zone removed before the sweep (D2)
- [x] 1.3 `ANALYSIS_VERSION` 17 → 18; `make builtin-inventory` (current deck: only the version changes) (D3)
- Verification: package `make test` green

## 2. Tests

- [x] 2.1 `tests/test_kicker.py`: a layout placeholder named `kicker` and a free text box named `kicker` make no zone; the same shapes without the name stay zones; `Surtitre`, `eyebrow`, `Sur-titre 2` match; delivered slides (layout and copied slide) hold no kicker and no "removed" report line

## 3. Close-out

- [x] 3.1 `ruff check`, `ruff check --select I`, `ruff format --check`, basedpyright with baseline; `openspec validate ppt-builder-kicker-label --strict`
- [x] 3.2 Built-in deck swap measured against this change (in `ppt-builder-capability` 7.1): cover, two_columns, comparison present

## Results (2026-10-16)

- Package `make test`: 889 passed, 5 skipped (old deck, kicker change alone: only `analysis_version` changed in the stored inventory); `ruff check`, `--select I`, `format --check` clean; basedpyright with baseline 0 errors.
- `tests/test_kicker.py` (4 tests); the render test fails without `_remove_kickers` (layout slide keeps an empty kicker placeholder).
- New built-in deck: kickers gone from every pattern; `Fred Title` → cover, `Fred Two Content` → two_columns, `Fred Comparison` / `Fred Before After` → comparison, Title Only layouts → section.
- Not fixed (design Follow-ups): `Fred Statement` (×2) and `Fred Big Number` stay `bullets` with no title zone, so they are never picked for a titled slide.
