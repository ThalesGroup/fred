## Context

See [proposal.md](proposal.md) for motivation and scope. `traversal.py` shares `KEY_PATTERN` between text discovery, replacement, styled values, and image-anchor discovery. `parser.py` duplicates the double-brace grammar in `_HEADER_PATTERN` and extracts headers using `KEY_PATTERN.findall`. Existing tests construct real PPTX bytes offline, including runs, groups, tables, image metadata, and fill-tool fakes.

## Goals / Non-Goals

**Goals:** Keep all recognition paths on one marker grammar and retain bare key names in existing schemas.

**Non-Goals:** New template engines, escaping syntax, validation error codes, cross-paragraph markers, chart/SmartArt support, or changes to storage and APIs.

## Decisions

1. Use a shared brace scanner to identify balanced regions, then match the single/double marker grammar within those regions. Keep the exported regex's sole key capture compatible with `group(1)` and `findall()`. Note headers consume the same scanner and validate only comma separators and the final colon; remove the separate header regex so its grammar cannot drift.
2. Require delimiter boundaries and skip nested brace sequences as a whole so malformed input cannot expose an inner marker. Boundary lookarounds alone do not cover nested content separated by spaces. Ignore malformed sequences rather than introducing a separate syntax-error contract. Preserve arbitrary non-brace key text and trim surrounding whitespace; exclude empty/whitespace-only keys.
3. Keep existing paragraph run merging, replacement formatting, and geometry traversal. Compute raw substitutions and styled spans together so each marker occurrence resolves its value once. Add acceptance cases to the existing parser, anchors, fill, and text-formatting tests using their fixtures. Avoid a new template engine or parallel traversal.
4. Keep double braces as a canonical display in the configuration UI and diagnostics; they refer to the same normalized field. Explain equivalence and show mixed syntax in both help languages and the package README.

## Risks / Trade-offs

- Ordinary `{text}` on a template slide becomes a field - document the supported forms and preserve current missing-description checks.
- Matcher capture changes can break `findall` consumers - inspect every `KEY_PATTERN` use and verify real-deck analysis/fill round trips.
- Previously accepted malformed brace sequences will be ignored - explicitly document that only balanced single/double markers are supported and test boundaries.
- Existing formatting and image behavior must remain consistent - reuse current traversal and run the package's offline suite after targeted regression checks.

## Migration Plan

Add one migration note with operational impact `none`. No data or configuration migration is required. Existing valid double-brace templates continue to work; authors can use single braces with the updated runtime. Rolling back requires reverting single-brace authoring to double braces before those templates can be filled again.
