## 1. Analysis and render

- [ ] 1.1 `lexicon.KICKER_NAMES`; `analysis.kicker_keys` (shape name or layout placeholder name, never a title placeholder); records of kickers dropped on the slide and layout paths (D1, D2)
- [ ] 1.2 `render._remove_kickers` at the start of `_fill`: kicker shapes holding no zone removed before the sweep (D2)
- [ ] 1.3 `ANALYSIS_VERSION` 17 → 18; `make builtin-inventory` (current deck: only the version changes) (D3)
- Verification: package `make test` green

## 2. Tests

- [ ] 2.1 `tests/test_kicker.py`: a layout placeholder named `kicker` and a free text box named `kicker` make no zone; the same shapes without the name stay zones; `Surtitre`, `eyebrow`, `Sur-titre 2` match; delivered slides (layout and copied slide) hold no kicker and no "removed" report line

## 3. Close-out

- [ ] 3.1 `ruff check`, `ruff check --select I`, `ruff format --check`, basedpyright with baseline; `openspec validate ppt-builder-kicker-label --strict`
- [ ] 3.2 Built-in deck swap measured against this change (in `ppt-builder-capability` 7.1): cover, two_columns, comparison present
