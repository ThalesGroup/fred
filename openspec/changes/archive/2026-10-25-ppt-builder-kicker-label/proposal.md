## Why

`ppt_builder` (GitHub issue #2679) is getting a new built-in deck from the owner ("fred-default-showcase", 45 slides on "Fred …" layouts). Almost every layout of that deck holds a small `kicker` placeholder (an eyebrow line, 11 pt, above the title). The rules analysis reads it as one more body (or heading) zone, so on the new deck the built-in agents would lose `cover`, `comparison` and `two_columns` (the slides read as `bullets`), a kicker on a Title Only layout makes it read as a `bullets` slide, and `_fullest` counts the kicker as an empty zone on every slide that leaves it unfilled. Inventory of the new deck before this change: `~/fred-tmp/builtin-new/new.inventory.json`.

## What Changes

- **Analysis.** A text shape whose name, or whose layout placeholder's name, says kicker (`kicker`, `eyebrow`, `surtitre`, `sur titre`, `overline`, `pretitle`) is no zone: the slide is analysed as if it were not there (kind, pairs, rows, headings, takeaway). Never by geometry. Title placeholders are never kickers. `ANALYSIS_VERSION` 17 → 18: stored analyses refresh in the background.
- **Render.** The builder writes nothing in a kicker and removes it from the delivered slide, whether the slide is a copied example slide (no "template example text removed" note) or a layout slide (no empty "Click to add text" box).
- Templates without such a name: no change (their inventory only changes its version number).
- The new built-in deck itself (table body emptied, asset swap) is tracked by `ppt-builder-capability` task 7.1, not here.

## Capabilities

### New Capabilities

- none

### Modified Capabilities

- `ppt-builder`: adds requirement "A named kicker line is a label, not a zone". The base requirements live in the in-flight change `ppt-builder-capability`; this change is applied and archived after it.

## Impact

- `builder/lexicon.py` (`KICKER_NAMES`), `builder/analysis.py` (`kicker_keys`, records filtered on the slide and layout paths, version bump), `builder/render.py` (`_remove_kickers`), `assets/fred_template.inventory.json` (regenerated).
- Tests: `tests/test_kicker.py` (new).
- No model, API or frontend change (no new zone field or role), no migration beyond the background re-analysis the version bump triggers.
- Migration: same PR as `ppt-builder-capability`, whose migration note covers re-analysis; no operator action.
- Tracking: #2679.
