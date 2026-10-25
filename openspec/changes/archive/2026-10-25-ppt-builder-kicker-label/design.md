## Context

The rules analysis (`builder/analysis.py`) turns every placeholder with a text role (`_placeholder_role`: BODY/OBJECT → `body`, or `heading` on the top band) and every free text box into a zone. The owner's new built-in deck names its layout placeholders (`kicker`, `title`, `subtitle`, `stat_value`…), but its slides keep PowerPoint's automatic names (`Text Placeholder 1`), so `_declared_role` (slide shape name only) never sees `kicker`. On that deck the kicker (idx 90, ≈ 37 ‰ high, 11 pt) became a `body` zone, or a `heading` when no title placeholder was present, and:

- `_kind` saw one more body: "Fred Comparison" and "Fred Two Content" read `bullets`, "Fred Title" (slide 1) `bullets` instead of `cover`, "Fred Title Only" `bullets` instead of `section`;
- `assign._weigh` counted it as an empty zone on every slide (`_EMPTY_ZONE` cost, and `_fullest` prefers slides with fewer empty zones);
- left empty, the renderer removed the placeholder; on a copied example slide the sweep would otherwise have reported its sample text as removed.

Owner's earlier rule (`ppt-builder-intent-fields` Q1, 2026-10-15): a takeaway zone is detected by shape/placeholder name or vision purpose, "never by geometry alone".

## Goals / Non-Goals

**Goals:** the kicker never changes a slide's kind, zone count or fit; it does not show empty or with example text on a delivered slide; templates without a kicker name are unchanged.

**Non-Goals:** filling the kicker (section name, a plan field); geometry-based detection; reading layout placeholder names for other roles (e.g. `statement`, `stat_value`); the Statement and Big Number slides' kinds (see Follow-ups).

## Decisions

### D1. Recognised by name only

A text shape is a kicker when its own name or, for a placeholder, its layout placeholder's name matches `lexicon.KICKER_NAMES` (`kicker`, `eyebrow`, `surtitre`, `sur titre`, `overline`, `pretitle`; normalised and matched as word prefixes by `lexicon.name_matches`, like `TAKEAWAY_NAMES`). Title placeholders (`TITLE`, `CENTER_TITLE`, `VERTICAL_TITLE`) never are. No geometry, consistent with Q1: a short line above a title can just as well be a subtitle or a date a template wants filled; a name is the designer saying what it is.

Alternative rejected: geometry (a short single-line box directly above the title, small font). It would also catch dates, breadcrumbs and section labels some templates expect filled, and it contradicts Q1.

### D2. No zone at all, removed at render

`kicker_keys(slide or layout)` returns the kicker shapes' zone keys. The analysis drops those records before reading the slide (slide path in `run`, layout path in `_layout_pattern`), so every downstream rule (pairs, rows, `_promote_headings`, `_kind`, `mark_takeaway`, `_covers`) sees the slide as if the kicker were absent. `_weigh` and `_fullest` therefore never count it. At render, `_remove_kickers` (start of `_fill`) removes the slide's kicker shapes that hold no zone, before the example-text sweep, so no "template example text removed" line reaches the agent and no empty placeholder is left on a layout slide.

Alternatives rejected:
- A zone with role `label`: `_kind` counts labels (a title + one label reads as a cover), closing slides place contact lines in every non-title text zone, and `_weigh` counts it empty; each would need an exception.
- A new role or a `Zone.kicker` flag: changes the public inventory schema (`Zone` is in the capability OpenAPI), so a regenerated frontend client for a value the UI never shows.
- Filling it with the section name or an optional `kicker` plan field: more schema and prompt surface for a decorative line; can come later if the owner asks.
- Role `keep`: the renderer never writes it, so every delivered slide would show the template's example kicker.

### D3. Version bump

`ANALYSIS_VERSION` 17 → 18: a stored analysis of a template with a kicker name is stale. Templates without one get the same patterns under the new version. A pattern analysed before this change keeps its kicker zone until the background refresh; the renderer removes only kickers holding no zone, so such a pattern still renders as before.

### D4. Owner decision B (2026-10-16)

"Teach the analysis to treat a small eyebrow/kicker line above the title as a label, not a body zone." Implemented as D1–D2: a label the builder leaves out, never a zone.

## Risks / Trade-offs

- [A template names a line `kicker` and expects it filled] → it is removed; the name says decoration, and the template author can rename it. Noted in the Help Center only if a user reports it.
- [The kicker's design accent disappears from built decks] → accepted (owner decision B); a fill rule can be added later without changing detection.

## Follow-ups

- **Statement and Big Number slides read `bullets`** (not fixed here): with the kicker gone, "Fred Statement" holds two bodies and no title, "Fred Big Number" three bodies and no title. Their roles are only in the layout placeholder names (`statement`, `stat_value`, `stat_label`), which the analysis does not read for roles. With no title zone, `_weigh` refuses them for any slide with a title (title not placed), so they are not picked by mistake. Making them `quote` and `figures` needs either layout-placeholder names read as declared roles (a wider analysis change) or a `kind:` notes directive in the deck.
